from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from google.genai import types
from app.ps1.assistant import chat
from .test_regressions import tiny
from .test_ps1 import instance
from app.ps1.models import Scenario
from app.ps1.solver import solve_scenario
from app.ps1.counterfactual import evaluate_activity_boundary


@pytest.fixture
def model(monkeypatch):
    for key in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "RAILFLOW_GEMINI_MODEL"):
        monkeypatch.setenv(key, "test")
    client = MagicMock()
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: client)
    return client.__enter__.return_value.models.generate_content


def response(text):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=text)]))])


def tool(name, args):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))])


def test_general_answer_is_model_text_with_history(model):
    model.return_value = response("10 + 10 is 20.")
    result = chat(SimpleNamespace(), "A", None, "What is 10 + 10?", [{"role": "user", "content": "Hello"}])
    assert result["answer"] == "10 + 10 is 20."
    assert result["mode"] == "gemini"
    assert result["evidence"] == []
    assert len(model.call_args.kwargs["contents"]) == 2
    instructions = model.call_args.kwargs["config"].system_instruction
    assert "You are RailFlowAI Assistant." in instructions
    assert "Reply in English" in instructions


def test_model_reads_schedule_then_writes_answer(model, tiny):
    solution = solve_scenario(tiny, Scenario.A, 3)
    job = SimpleNamespace(instance=tiny, scenarios={Scenario.A: SimpleNamespace(solution=solution)})
    model.side_effect = [tool("get_schedule_results", {}), response("Schedule results retrieved.")]
    result = chat(job, Scenario.A, solution, "What are the score drivers?", [])
    assert result["answer"] == "Schedule results retrieved."
    assert any(ref.startswith("scenario:A") for ref in result["evidence"])
    output = model.call_args.kwargs["contents"][-1].parts[0].function_response.response
    assert output["scenarios"]["A"]["scores"]["objective_score"] == solution.validation.soft_scores["objective_score"]


def test_model_can_explain_a_scenario_design_from_validated_policy_evidence(model, tiny):
    solution = solve_scenario(tiny, Scenario.A, 3)
    job = SimpleNamespace(instance=tiny, replans={}, scenarios={Scenario.A: SimpleNamespace(solution=solution)})
    model.side_effect = [tool("explain_schedule_design", {"target_scenario": "A"}), response("Scenario A is driven by its documented delay objective.")]
    result = chat(job, None, None, "Why was Scenario A scheduled this way?", [])
    assert result["answer"] == "Scenario A is driven by its documented delay objective."
    output = model.call_args.kwargs["contents"][-1].parts[0].function_response.response
    assert output["policy"]["objective"] == "Minimise priority-weighted contract delay."
    assert output["validation_status"] == "verified"


def test_model_can_read_filtered_rows_from_a_validated_generated_csv(model, tiny):
    solution = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities))
    job = SimpleNamespace(instance=tiny, replans={}, scenarios={Scenario.A: SimpleNamespace(solution=solution)})
    model.side_effect = [tool("read_generated_csv", {"filename": "SCHEDULE_ACCESS.csv", "activity_id": aid}), response("I read the generated access rows.")]
    result = chat(job, Scenario.A, solution, "Show generated access rows.", [])
    assert result["answer"] == "I read the generated access rows."
    output = model.call_args.kwargs["contents"][-1].parts[0].function_response.response
    assert output["filename"] == "SCHEDULE_ACCESS.csv"
    assert all(row["activity_id"] == aid for row in output["rows"])


def test_one_chat_can_select_another_scenario_before_reading_its_activity(model, tiny):
    a = solve_scenario(tiny, Scenario.A, 3)
    b = solve_scenario(tiny, Scenario.B, 3)
    aid = next(iter(tiny.activities))
    job = SimpleNamespace(instance=tiny, replans={}, scenarios={
        Scenario.A: SimpleNamespace(solution=a), Scenario.B: SimpleNamespace(solution=b),
    })
    model.side_effect = [tool("select_schedule", {"target_scenario": "B"}),
                         tool("get_activity", {"activity_id": aid}), response("Scenario B activity evidence read.")]
    result = chat(job, None, None, "Check this activity in Scenario B.", [])
    assert result["answer"] == "Scenario B activity evidence read."
    assert any(ref.startswith("scenario:B") for ref in result["evidence"])
    activity = model.call_args.kwargs["contents"][-1].parts[0].function_response.response
    assert activity["activity"]["activity_id"] == aid


def test_counterfactual_timing_is_validated_and_does_not_mutate_baseline(tiny):
    baseline = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities))
    original = [(row.activity_id, row.week, row.eclo, row.access_night) for row in baseline.accesses]
    start = min(row.week for row in baseline.accesses if row.activity_id == aid)
    result = evaluate_activity_boundary(tiny, Scenario.A, baseline, aid, "start", start, budget_seconds=3)
    assert result["status"] == "feasible"
    assert result["validation_status"] == "verified"
    assert result["baseline"]["activity_weeks"]
    assert [(row.activity_id, row.week, row.eclo, row.access_night) for row in baseline.accesses] == original


def test_model_can_request_one_counterfactual_timing_check(model, tiny):
    baseline = solve_scenario(tiny, Scenario.A, 3)
    aid = next(iter(tiny.activities))
    start = min(row.week for row in baseline.accesses if row.activity_id == aid)
    job = SimpleNamespace(instance=tiny, replans={}, scenarios={Scenario.A: SimpleNamespace(solution=baseline)})
    model.side_effect = [tool("test_activity_timing", {"activity_id": aid, "boundary": "start", "target_week": start}),
                         response("The validated comparison is available.")]
    result = chat(job, Scenario.A, baseline, "Why this timing?", [])
    assert result["answer"] == "The validated comparison is available."
    output = model.call_args.kwargs["contents"][-1].parts[0].function_response.response
    assert output["status"] == "feasible"


def test_unknown_write_tool_is_rejected(model):
    model.side_effect = [tool("execute_replan", {}), response("Use the approval button.")]
    result = chat(SimpleNamespace(), "A", None, "Execute", [])
    assert result["mode"] == "gemini"
    assert "error" in model.call_args.kwargs["contents"][-1].parts[0].function_response.response


def test_preview_only_returns_validated_draft(model, tiny):
    location = next(key for key, row in tiny.supply.items() if row.supply_capacity > 0)
    model.side_effect = [tool("prepare_disruption", {"location_id": location, "start_week": 1, "end_week": 1, "capacity": 0}), response("Review the draft.")]
    solution = solve_scenario(tiny, Scenario.A, 3)
    job = SimpleNamespace(instance=tiny, replans={}, scenarios={Scenario.A: SimpleNamespace(solution=solution)})
    result = chat(job, "A", solution, "Reduce capacity", [])
    assert result["intent"] == "disruption_preview"
    assert result["data"]["capacity"] == 0
    assert job.replans == {}


def test_chat_approval_is_bound_to_displayed_preview_and_does_not_execute(model):
    pending = {"preview_id": "server-issued-preview", "disruption": {"capacity": 0}}
    model.side_effect = [tool("approve_pending_replan", {}), response("Approval confirmed.")]
    job = SimpleNamespace(replans={})
    result = chat(job, "A", None, "Approve", [], pending_preview=pending)
    assert result["approved_preview_id"] == pending["preview_id"]
    assert job.replans == {}


def test_no_approval_tool_without_existing_preview(model):
    model.side_effect = [tool("approve_pending_replan", {}), response("Review the draft first.")]
    result = chat(SimpleNamespace(), "A", None, "Execute", [])
    assert "approved_preview_id" not in result
    assert "error" in model.call_args.kwargs["contents"][-1].parts[0].function_response.response


def test_changed_draft_requires_fresh_approval(model, tiny):
    location = next(key for key, row in tiny.supply.items() if row.supply_capacity > 0)
    model.side_effect = [
        tool("prepare_disruption", {"location_id": location, "start_week": 1, "end_week": 1, "capacity": 0}),
        tool("approve_pending_replan", {}), response("Review the new draft.")]
    solution = solve_scenario(tiny, Scenario.A, 3)
    result = chat(SimpleNamespace(instance=tiny, scenarios={Scenario.A: SimpleNamespace(solution=solution)}), "A", solution, "Change to week 1", [],
                  pending_preview={"preview_id": "old-preview"})
    assert result["intent"] == "disruption_preview"
    assert "approved_preview_id" not in result


def test_question_about_preview_does_not_authorize_execution(model):
    model.return_value = response("Approving runs the solver and independent validator.")
    result = chat(SimpleNamespace(), "A", None, "What happens if I approve?", [],
                  pending_preview={"preview_id": "current-preview"})
    assert "approved_preview_id" not in result


@pytest.mark.parametrize("check", ["move_reason", "downstream_risk", "capacity", "co_share", "milestone_risk", "handover", "replan_impact"])
def test_bonus_checks_are_callable(model, tiny, check):
    solution = solve_scenario(tiny, Scenario.A, 3)
    args = {"check": check, "activity_ids": [next(iter(tiny.activities))], "contract_ids": [next(iter(tiny.contracts))], "location_id": next(iter(tiny.supply)), "weeks": [1]}
    model.side_effect = [tool("inspect_schedule", args), response("Evidence queried.")]
    chat(SimpleNamespace(instance=tiny), "A", solution, "Query evidence", [])
    assert "error" not in model.call_args.kwargs["contents"][-1].parts[0].function_response.response
