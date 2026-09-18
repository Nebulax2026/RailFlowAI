from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from app.ps1.safety import legal_mix, possession_usage


INTENTS = {"activity_move_reason", "downstream_risk", "capacity_status", "co_share_status", "handover_brief",
           "scenario_comparison", "milestone_risk", "replan_impact_summary", "disruption_preview",
           "score_explanation", "greeting"}
_calls = defaultdict(deque)
_lock = threading.Lock()
_gemini_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="schedule-assistant")


def enforce_query_rate(job_id, limit=20, window=60):
    now = time.monotonic()
    with _lock:
        calls = _calls[job_id]
        while calls and calls[0] <= now - window: calls.popleft()
        if len(calls) >= limit: return False
        calls.append(now); return True


def answer_question(instance, solution, question, diff=None, scenarios=None):
    parsed, mode = _parse_with_gemini(question)
    if not parsed:
        parsed = _parse_deterministic(question); mode = "deterministic"
    intent = parsed.get("intent") if parsed else None
    entities = parsed.get("entities", {}) if parsed else {}
    if intent not in INTENTS:
        return {"answer": "I could not map that question to a supported schedule check. Ask about score/overrun drivers, why an activity moved, downstream risk, capacity, co-sharing, a milestone, or a handover week.",
                "intent": "unsupported", "evidence": [], "mode": mode}
    handlers = {
        "activity_move_reason": _move_reason, "downstream_risk": _downstream,
        "capacity_status": _capacity, "co_share_status": _co_share, "handover_brief": _handover,
    }
    if intent == "greeting":
        answer, evidence, data = ("Hello — I can explain validated schedule evidence, score and overrun drivers, capacity, co-sharing, milestones, handovers, scenario trade-offs, or prepare a disruption preview.", [], None)
    elif intent == "scenario_comparison":
        answer, evidence, data = _scenario_comparison(scenarios or {})
    elif intent == "milestone_risk":
        answer, evidence, data = _milestone_risk(instance, solution, entities)
    elif intent == "replan_impact_summary":
        answer, evidence, data = _replan_impact(diff, instance, solution)
    elif intent == "disruption_preview":
        answer, evidence, data = _disruption_draft(instance, entities)
    elif intent == "score_explanation":
        answer, evidence, data = _score_explanation(instance, solution, question)
    else:
        answer, evidence = handlers[intent](instance, solution, entities, diff)
        data = None
    response = {"answer": answer, "intent": intent, "evidence": evidence, "mode": mode}
    if data is not None: response["data"] = data
    return response


def _parse_deterministic(question):
    text = question.strip(); lower = text.lower()
    aids = re.findall(r"\bA\d+\b", text, re.I)
    contracts = re.findall(r"\bC\d+\b", text, re.I)
    locations = re.findall(r"\b(?:SEC|PLAT):[A-Z0-9_:]+", text, re.I)
    weeks = [int(value) for value in re.findall(r"\bweeks?\s+(\d+)\b", lower)]
    range_match = re.search(r"\bweeks?\s+(\d+)\s*(?:to|-|through)\s*(\d+)\b", lower)
    if range_match: weeks = [int(range_match.group(1)), int(range_match.group(2))]
    entities = {"activity_ids": [a.upper() for a in aids], "contract_ids": [c.upper() for c in contracts],
                "location_id": locations[0].upper() if locations else None, "weeks": weeks}
    if any(token in lower for token in ("compare scenario", "scenarios a", "scenarios b", "scenarios c")): intent = "scenario_comparison"
    elif "milestone" in lower or ("late" in lower and contracts): intent = "milestone_risk"
    elif "what changed" in lower or "unaffected" in lower or "replan impact" in lower: intent = "replan_impact_summary"
    elif locations and ("reduce" in lower or "disruption" in lower or "re-plan" in lower or "replan" in lower) and "capacity" in lower: intent = "disruption_preview"
    elif "moved" in lower or ("why" in lower and aids): intent = "activity_move_reason"
    elif "downstream" in lower or "risk" in lower or "delay" in lower: intent = "downstream_risk"
    elif "capacity" in lower or "hotspot" in lower: intent = "capacity_status"
    elif "share" in lower or "co-worker" in lower or "coworker" in lower: intent = "co_share_status"
    elif "handover" in lower or "brief" in lower or ("week" in lower and not locations): intent = "handover_brief"
    else: intent = None
    capacity = re.search(r"\b(?:to\s+|capacity\s+(?:of|is)?\s*)(\d+)\b", lower)
    entities["capacity"] = int(capacity.group(1)) if capacity else None
    return {"intent": intent, "entities": entities}


def _parse_with_gemini(question):
    project = os.getenv("GOOGLE_CLOUD_PROJECT"); location = os.getenv("GOOGLE_CLOUD_LOCATION")
    model = os.getenv("RAILFLOW_GEMINI_MODEL")
    if not all((project, location, model)): return None, "deterministic"
    def invoke():
        from google import genai
        client = genai.Client(vertexai=True, project=project, location=location)
        prompt = f"""Select exactly one allowed RailFlowAI PS1 Copilot capability for this user message.
The message may be in Korean or English. Infer intent semantically; do not use keyword matching.
You are selecting a server-side, read-only capability, not answering the question and not changing a schedule.
Allowed capabilities: {sorted(INTENTS)}.
Use score_explanation for questions about objective score, score drivers, overrun or trade-offs.
Use greeting for greetings or general help. Use disruption_preview only for a proposed capacity disruption.
Return JSON only: {{"intent": "allowed capability", "entities": {{"activity_ids": [], "contract_ids": [], "location_id": null, "weeks": [], "capacity": null}}}}.
Extract only explicit IDs and numeric facts; leave unknown values null or empty. User message: {question}"""
        response = client.models.generate_content(model=model, contents=prompt,
                                                  config={"response_mime_type": "application/json"})
        value = json.loads(response.text)
        return value if value.get("intent") in INTENTS and isinstance(value.get("entities", {}), dict) else None
    future = _gemini_pool.submit(invoke)
    try: return future.result(timeout=8), "gemini-assisted"
    except (Exception, TimeoutError):
        future.cancel(); return None, "deterministic"


def _move_reason(instance, solution, entities, diff):
    aid = next(iter(entities.get("activity_ids") or []), None)
    if not aid or not diff: return "Ask about a moved activity ID in a revised schedule.", []
    item = next((row for row in diff["activity_changes"] if row["activity_id"] == aid), None)
    if not item: return f"{aid} did not change between the baseline and revised schedules.", [aid]
    labels = {"direct_disruption": "its baseline possession intersects the disrupted location and weeks",
              "predecessor_impact": "an upstream predecessor is in the disruption impact chain",
              "optimizer_rebalance": "the optimiser rebalanced unaffected future work while preserving the best policy score"}
    before = ", ".join(f'W{x["week"]}' for x in item["before"]); after = ", ".join(f'W{x["week"]}' for x in item["after"])
    return f"{aid} moved from {before} to {after} because {labels[item['reason']] }.", [aid, item["contract_number"]]


def _downstream(instance, solution, entities, diff):
    seeds = set(entities.get("activity_ids") or [])
    contracts = set(entities.get("contract_ids") or [])
    if contracts: seeds |= {aid for aid, a in instance.activities.items() if a.contract_number in contracts}
    if not seeds and diff: seeds = set(diff.get("directly_affected_activities", []))
    descendants = set(); frontier = set(seeds)
    while frontier:
        parent = frontier.pop()
        for aid, activity in instance.activities.items():
            if activity.predecessor_activity_id == parent and aid not in descendants:
                descendants.add(aid); frontier.add(aid)
    late = {r.contract_number: r.overrun_days for r in solution.results if r.overrun_days}
    impacted = sorted({instance.activities[a].contract_number for a in descendants if a in instance.activities})
    return (f"{len(descendants)} downstream activities are linked to the selected work. "
            f"Impacted contracts: {', '.join(impacted) or 'none'}; currently late: "
            f"{', '.join(f'{c} ({d} days)' for c, d in late.items()) or 'none'}.", sorted(seeds | descendants))


def _capacity(instance, solution, entities, diff):
    location = entities.get("location_id"); weeks = entities.get("weeks") or []
    if not location or not weeks: return "Include a location ID and week, for example: capacity at SEC:ALP:S01_S02:EB week 8.", []
    week = weeks[0]
    item = next((u for u in possession_usage(instance, solution.accesses, solution.occupancy)
                 if u["location_id"] == location and u["week"] == week), None)
    used = item["work_possessions"] if item else 0
    nominal = instance.supply.get(location)
    if not nominal: return f"{location} is not a known supply location.", [location]
    return f"{location} uses {used} of {nominal.supply_capacity} nominal slots in week {week}.", [location, f"week:{week}"]


def _co_share(instance, solution, entities, diff):
    aids = entities.get("activity_ids") or []
    if not aids: return "Include an activity ID to inspect its co-sharing assignments.", []
    aid = aids[0]
    groups = defaultdict(set)
    for row in solution.occupancy: groups[row.location_id, row.week, row.co_share_group].add(row.activity_id)
    peers = sorted({peer for members in groups.values() if aid in members for peer in members if peer != aid})
    if len(aids) > 1:
        other = aids[1]; actual = other in peers
        compatible = aid in instance.activities and other in instance.activities and legal_mix(instance, [aid, other])
        return f"{aid} and {other} {'do' if actual else 'do not'} currently co-share. Their access types are {'compatible' if compatible else 'not compatible'}.", aids[:2]
    return f"{aid} co-shares with {', '.join(peers) if peers else 'no other activities'}.", [aid, *peers]


def _handover(instance, solution, entities, diff):
    weeks = entities.get("weeks") or []
    if not weeks: return "Include a week for the handover brief.", []
    start, end = min(weeks), max(weeks)
    rows = [r for r in solution.accesses if start <= r.week <= end]
    activities = sorted({r.activity_id for r in rows}); eclo = sum(r.eclo for r in rows)
    contracts = sorted({instance.activities[a].contract_number for a in activities})
    return (f"Weeks {start}-{end}: {len(rows)} access occurrences across {len(activities)} activities and "
            f"{len(contracts)} contracts, with {eclo} ECLO nights. Contracts: {', '.join(contracts) or 'none'}.",
            [*activities, *(f"week:{w}" for w in range(start, end + 1))])


def _scenario_comparison(scenarios):
    rows = []
    for name, run in sorted(scenarios.items()):
        solution = run.solution if hasattr(run, "solution") else run
        if not solution or not solution.validation.feasible:
            continue
        scores = solution.validation.soft_scores
        rows.append({"scenario": str(name), "objective_score": scores.get("objective_score"),
                     "overrun_days": sum(item.overrun_days for item in solution.results),
                     "eclo": sum(item.eclo for item in solution.accesses),
                     "excess_supply": scores.get("excess_supply", 0), "validated": True})
    if not rows:
        return ("No internally validated available scenarios can be compared yet.", [], {"scenarios": []})
    best = min(rows, key=lambda row: (row["overrun_days"], row["objective_score"] if row["objective_score"] is not None else float("inf")))
    missing = sorted({"A", "B", "C"} - {row["scenario"] for row in rows})
    suffix = f" Unavailable or invalid: {', '.join(missing)}." if missing else ""
    return (f"Among internally validated available scenarios, Scenario {best['scenario']} has the lowest deadline overrun "
            f"({best['overrun_days']} days); this comparison is based on the documented RailFlowAI policy and does not claim parity with an unavailable official validator.{suffix}",
            [*(f"scenario:{row['scenario']}" for row in rows)], {"scenarios": rows, "criterion": "lowest deadline overrun"})


def _score_explanation(instance, solution, question):
    scores = solution.validation.soft_scores
    breakdown = solution.validation.detail.get("score_breakdown", {})
    if not breakdown:
        breakdown = {key: scores.get(key, 0) for key in ("delay", "excess_supply", "eclo")}
    components = [(name, value or 0) for name, value in breakdown.items()]
    largest_name, largest_value = max(components, key=lambda item: item[1], default=("score", 0))
    labels = {"delay": "deadline-delay / overrun", "excess_supply": "excess supply", "eclo": "ECLO use"}
    total_overrun = sum(item.overrun_days for item in solution.results)
    late = sorted((item for item in solution.results if item.overrun_days), key=lambda item: item.overrun_days, reverse=True)
    top_contracts = [{"contract_number": item.contract_number, "overrun_days": item.overrun_days} for item in late[:5]]
    score = scores.get("objective_score")
    korean = bool(re.search(r"[가-힣]", question))
    largest_contract = top_contracts[0] if top_contracts else None
    korean_tail = (f"가장 지연된 계약은 {largest_contract['contract_number']}({largest_contract['overrun_days']}일)입니다."
                   if largest_contract else "오버런이 기록된 계약은 없습니다.")
    english_tail = (f"The largest late contract is {largest_contract['contract_number']} ({largest_contract['overrun_days']} days)."
                    if largest_contract else "No contract has recorded overrun.")
    answer = (f"검증된 목적 점수는 {score}입니다. 점수를 가장 크게 높인 항목은 "
              f"{labels.get(largest_name, largest_name)}({largest_value})이고, 전체 계약 오버런은 {total_overrun}일입니다. {korean_tail}"
              if korean else f"The validated objective score is {score}. The largest score driver is {labels.get(largest_name, largest_name)} "
              f"at {largest_value}; total contract overrun is {total_overrun} days. {english_tail}")
    return (answer,
            [*(item["contract_number"] for item in top_contracts)],
            {"objective_score": score, "score_breakdown": breakdown, "largest_driver": {"component": largest_name, "value": largest_value},
             "total_overrun_days": total_overrun, "late_contracts": top_contracts})


def _milestone_risk(instance, solution, entities):
    contract_id = next(iter(entities.get("contract_ids") or []), None)
    if not contract_id or contract_id not in instance.contracts:
        return "Include a contract ID, for example: What is the milestone risk for C001?", [], None
    contract = instance.contracts[contract_id]
    result = next((item for item in solution.results if item.contract_number == contract_id), None)
    activities = sorted(aid for aid, item in instance.activities.items() if item.contract_number == contract_id)
    downstream = sorted(aid for aid, item in instance.activities.items() if item.predecessor_activity_id in activities)
    if not result:
        return f"No completion result is available for {contract_id}.", [contract_id], None
    status = "late" if result.overrun_days else "on or before its deadline"
    return (f"{contract_id} completes on {result.simulated_completion_date.isoformat()} against its deadline "
            f"{contract.contract_completion_date.isoformat()} and is {status} ({result.overrun_days} overrun days). "
            f"Its evidence includes {len(activities)} contract activities and {len(downstream)} directly dependent downstream activities.",
            [contract_id, *activities, *downstream], {"contract_id": contract_id, "completion_date": result.simulated_completion_date.isoformat(),
                                                        "deadline": contract.contract_completion_date.isoformat(), "overrun_days": result.overrun_days,
                                                        "activities": activities, "downstream_activities": downstream})


def _replan_impact(diff, instance, solution):
    if not diff:
        return "Open a completed revised schedule before asking for its replan impact.", [], None
    summary = diff.get("summary", {})
    changed = diff.get("activity_changes", [])
    changed_ids = [item["activity_id"] for item in changed]
    all_ids = set(instance.activities)
    unchanged = sorted(all_ids - set(changed_ids))
    return (f"The revised schedule moved {summary.get('moved_activities', len(changed_ids))} activities, preserved "
            f"{summary.get('preserved_percent', 0)}% of work, affected {summary.get('contracts_impacted', 0)} contracts, "
            f"and changed the score by {summary.get('score_delta', 0)}. {len(unchanged)} activities remained unchanged.",
            [*changed_ids, *(f"unchanged:{aid}" for aid in unchanged)], {"summary": summary, "moved_activities": changed,
                                                                             "unchanged_activity_count": len(unchanged), "unchanged_activity_ids": unchanged})


def _disruption_draft(instance, entities):
    location = entities.get("location_id"); weeks = entities.get("weeks") or []
    capacity = entities.get("capacity")
    if not location or location not in instance.supply or not weeks or capacity is None:
        return ("Include a known location, a week or week range, and a reduced capacity; for example: Reduce "
                "SEC:ALP:S01_S02:EB capacity to 1 in week 12.", [], None)
    start, end = min(weeks), max(weeks)
    nominal = instance.supply[location].supply_capacity
    data = {"location_id": location, "start_week": start, "end_week": end, "capacity": capacity,
            "reason": "access_restriction", "nominal_capacity": nominal}
    if start < 1 or end > instance.horizon_weeks or capacity < 0 or capacity >= nominal:
        return "That disruption draft is outside the planning horizon or does not reduce the location's nominal capacity.", [location, f"week:{start}"], {**data, "valid": False}
    return (f"I prepared a disruption preview for {location}: capacity {nominal} to {capacity} in weeks {start}-{end}. "
            "No schedule has changed; review it and explicitly run the validated re-plan.", [location, *(f"week:{w}" for w in range(start, end + 1))], {**data, "valid": True})
