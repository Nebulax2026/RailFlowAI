from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.enums import ApprovalStatus, RequestSource, ScheduleOption
from app.domain.models import BlockedTimeSlot, MaintenanceRequest
from app.main import app
from app.repositories import unit_of_work
from app.scheduler.cp_sat_scheduler import optimise_schedule
from app.storage import (
    AUDIT_EVENTS,
    BLOCKED_TIME_SLOTS,
    DISPLACEMENT_APPROVALS,
    NOTIFICATIONS,
    PROPOSAL_SNAPSHOTS,
    REQUESTS,
    SCHEDULED_WORK,
    SETTINGS,
)


client = TestClient(app)
SAMPLE_REQUESTS_PATH = Path(__file__).resolve().parents[2] / "data" / "sample_requests.csv"


def request_payload(
    request_id: str,
    start: str,
    deadline: str,
    track: str = "T08",
    crew: list[str] | None = None,
    equipment: list[str] | None = None,
    work_type: str = "inspection",
    priority: int = 3,
) -> dict:
    return {
        "request_id": request_id,
        "title": f"{request_id} work",
        "track_sector": track,
        "work_type": work_type,
        "duration_minutes": 30,
        "earliest_start": start,
        "deadline": deadline,
        "priority": priority,
        "required_crew": crew or [],
        "required_equipment": equipment or [],
    }


class MvpWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        REQUESTS.clear()
        SCHEDULED_WORK.clear()
        PROPOSAL_SNAPSHOTS.clear()
        AUDIT_EVENTS.clear()
        SETTINGS.clear()
        BLOCKED_TIME_SLOTS.clear()
        NOTIFICATIONS.clear()
        DISPLACEMENT_APPROVALS.clear()

    def test_valid_request_fit_without_active_conflicts(self) -> None:
        response = client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["fits_current_schedule"])
        self.assertEqual(body["conflicts"], [])
        self.assertEqual(body["scheduled_work"]["request_id"], "M-001")
        self.assertFalse(body["requires_manager_review"])
        self.assertIn("M-001", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-001"].approval_status, ApprovalStatus.SCHEDULED)

        scheduled = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(scheduled.status_code, 200)
        self.assertIn("M-001", SCHEDULED_WORK)

    def test_request_reports_track_crew_and_equipment_contentions(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload(
                "M-001",
                "2026-08-13T01:00:00",
                "2026-08-13T02:00:00",
                crew=["E1"],
                equipment=["SignalKit-1"],
            ),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")

        response = client.post(
            "/api/requests",
            json=request_payload(
                "M-002",
                "2026-08-13T01:10:00",
                "2026-08-13T02:30:00",
                crew=["E1"],
                equipment=["SignalKit-1"],
            ),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["fits_current_schedule"])
        self.assertEqual({item["type"] for item in body["conflicts"]}, {"track", "crew", "equipment"})
        self.assertGreaterEqual(len(body["suggested_alternatives"]), 1)
        self.assertTrue(body["requires_manager_review"])
        self.assertIsNone(body["scheduled_work"])
        self.assertGreaterEqual(len(body["affected_changes"]), 1)
        self.assertNotIn("M-002", SCHEDULED_WORK)

    def test_incompatible_work_types_create_safety_conflict(self) -> None:
        first = request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T11:00:00", work_type="inspection")
        first["incompatible_work_types"] = ["electrical"]
        client.post("/api/requests", json=first)
        client.post("/api/schedule/optimise?option=minimum_disruption")

        response = client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T10:10:00", "2026-08-13T11:30:00", work_type="electrical"),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["fits_current_schedule"])
        self.assertIn("safety", {item["type"] for item in body["conflicts"]})

    def test_overtime_is_allowed_and_prerequisites_remain_hard_blockers(self) -> None:
        overtime_response = client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T05:30:00", "2026-08-13T06:30:00"),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")
        kpi_response = client.get("/api/kpis")
        dependency_response = client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T01:00:00", "2026-08-13T02:00:00", work_type="signal_test"),
        )

        self.assertEqual(overtime_response.status_code, 200)
        self.assertEqual(kpi_response.json()["estimated_overtime_minutes"], 30)
        self.assertEqual(dependency_response.status_code, 422)

    def test_locked_work_is_preserved_during_optimisation(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00", crew=["E1"]),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")
        client.post("/api/schedule/lock/M-001?role=schedule_manager")
        locked_before = SCHEDULED_WORK["M-001"]

        client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T01:00:00", "2026-08-13T03:00:00", crew=["E1"]),
        )
        response = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(response.status_code, 200)
        locked_after = SCHEDULED_WORK["M-001"]
        self.assertEqual(locked_after.start_time, locked_before.start_time)
        self.assertEqual(locked_after.status, ApprovalStatus.LOCKED)

    def test_schedule_manager_approval_locks_schedule_and_requester_is_denied(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")

        denied = client.post("/api/schedule/approve?role=requester")
        approved = client.post("/api/schedule/approve?role=schedule_manager")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.json()["approved"])
        self.assertEqual(SCHEDULED_WORK["M-001"].status, ApprovalStatus.LOCKED)

    def test_csv_and_json_import_validate_rows(self) -> None:
        csv_content = (
            "Request ID,Title,Track Sector,Work Type,Duration Minutes,Earliest Start,Deadline,Priority\n"
            "M-CSV,CSV job,T09,inspection,30,2026-08-13T01:00:00,2026-08-13T02:00:00,3\n"
        )
        csv_response = client.post(
            "/api/import/confirm",
            files={"file": ("requests.csv", csv_content, "text/csv")},
        )
        json_response = client.post(
            "/api/import/json/confirm",
            files={
                "file": (
                    "requests.json",
                    json.dumps(
                        [
                            request_payload(
                                "M-JSON",
                                "2026-08-13T02:00:00",
                                "2026-08-13T03:00:00",
                                track="T10",
                            )
                        ]
                    ),
                    "application/json",
                )
            },
        )

        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(json_response.status_code, 200)
        self.assertIn("M-CSV", REQUESTS)
        self.assertIn("M-JSON", REQUESTS)
        self.assertEqual(REQUESTS["M-CSV"].source, RequestSource.CSV)
        self.assertEqual(REQUESTS["M-JSON"].source, RequestSource.JSON)

    def test_sample_csv_preview_and_confirm_use_the_complete_batch(self) -> None:
        content = SAMPLE_REQUESTS_PATH.read_bytes()

        preview = client.post(
            "/api/import/preview",
            files={"file": (SAMPLE_REQUESTS_PATH.name, content, "text/csv")},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["can_import"])
        self.assertEqual(preview.json()["errors"], [])
        self.assertEqual(preview.json()["total_rows"], 20)
        self.assertEqual(REQUESTS, {})
        self.assertEqual(SCHEDULED_WORK, {})

        confirmed = client.post(
            "/api/import/confirm",
            files={"file": (SAMPLE_REQUESTS_PATH.name, content, "text/csv")},
        )

        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["imported"], 20)
        self.assertEqual(confirmed.json()["scheduled_items"], 15)
        self.assertEqual(len(REQUESTS), 20)
        self.assertEqual(len(SCHEDULED_WORK), 15)
        self.assertEqual(SCHEDULED_WORK["M-101"].status, ApprovalStatus.LOCKED)
        self.assertEqual(SCHEDULED_WORK["M-104"].status, ApprovalStatus.SCHEDULED)
        self.assertNotIn("M-102", SCHEDULED_WORK)

    def test_csv_import_accepts_common_header_and_value_whitespace(self) -> None:
        csv_content = (
            "\ufeff request id , title , track sector , work type , duration minutes , earliest start , deadline , priority , required crew \n"
            " M-CSV-SPACED , Spaced CSV job , T09 , inspection , 30 , 2026-08-13T01:00:00 , 2026-08-13T02:00:00 , 3 , MECH1 \n"
        )

        preview = client.post(
            "/api/import/preview",
            files={"file": ("requests.csv", csv_content, "text/csv")},
        )
        confirmed = client.post(
            "/api/import/confirm",
            files={"file": ("requests.csv", csv_content, "text/csv")},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["can_import"])
        self.assertEqual(preview.json()["errors"], [])
        self.assertEqual(confirmed.status_code, 200)
        self.assertIn("M-CSV-SPACED", REQUESTS)
        self.assertEqual(REQUESTS["M-CSV-SPACED"].required_crew, ["MECH1"])

    def test_json_preview_reports_detected_columns_and_total_rows(self) -> None:
        rows = [
            request_payload("M-JSON-1", "2026-08-13T02:00:00", "2026-08-13T03:00:00", track="T10"),
            request_payload("M-JSON-2", "2026-08-13T03:00:00", "2026-08-13T04:00:00", track="T11"),
        ]

        preview = client.post(
            "/api/import/json/preview",
            files={"file": ("requests.json", json.dumps(rows), "application/json")},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["can_import"])
        self.assertEqual(preview.json()["total_rows"], 2)
        self.assertIn("request_id", preview.json()["detected_columns"])
        self.assertEqual(preview.json()["missing_required_fields"], [])
        self.assertEqual(REQUESTS, {})

    def test_empty_import_previews_are_blocked(self) -> None:
        csv_content = "Request ID,Title,Track Sector,Work Type,Duration Minutes,Earliest Start,Deadline,Priority\n"

        csv_preview = client.post(
            "/api/import/preview",
            files={"file": ("requests.csv", csv_content, "text/csv")},
        )
        json_preview = client.post(
            "/api/import/json/preview",
            files={"file": ("requests.json", "[]", "application/json")},
        )

        self.assertEqual(csv_preview.status_code, 200)
        self.assertFalse(csv_preview.json()["can_import"])
        self.assertIn("at least one data row", csv_preview.json()["errors"][0])
        self.assertEqual(json_preview.status_code, 200)
        self.assertFalse(json_preview.json()["can_import"])
        self.assertIn("at least one data row", json_preview.json()["errors"][0])

    def test_import_preview_reports_row_errors_without_storing_requests(self) -> None:
        csv_content = (
            "Request ID,Title,Track Sector,Work Type,Duration Minutes,Earliest Start,Deadline,Priority\n"
            "M-BAD-CSV,Bad CSV job,T09,inspection,not-a-number,2026-08-13T01:00:00,2026-08-13T02:00:00,3\n"
        )
        csv_response = client.post(
            "/api/import/preview",
            files={"file": ("requests.csv", csv_content, "text/csv")},
        )
        json_response = client.post(
            "/api/import/json/preview",
            files={
                "file": (
                    "requests.json",
                    json.dumps([request_payload("M-BAD-JSON", "invalid-date", "2026-08-13T03:00:00")]),
                    "application/json",
                )
            },
        )

        self.assertEqual(csv_response.status_code, 200)
        self.assertFalse(csv_response.json()["can_import"])
        self.assertIn("Row 2, duration_minutes", csv_response.json()["errors"][0])
        self.assertNotIn("M-BAD-CSV", REQUESTS)

        self.assertEqual(json_response.status_code, 200)
        self.assertFalse(json_response.json()["can_import"])
        self.assertIn("Row 1, earliest_start", json_response.json()["errors"][0])
        self.assertNotIn("M-BAD-JSON", REQUESTS)

    def test_apply_alternative_requires_schedule_manager(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00", crew=["E1"]),
        )
        client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T01:05:00", "2026-08-13T03:00:00", crew=["E1"]),
        )

        denied = client.post("/api/schedule/apply?option=minimum_disruption&role=requester")
        applied = client.post("/api/schedule/apply?option=minimum_disruption&role=schedule_manager")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(len(applied.json()), 2)

    def test_selected_proposal_does_not_schedule_unselected_pending_requests(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"]),
        )
        client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"], priority=5),
        )
        client.post(
            "/api/requests",
            json=request_payload("M-003", "2026-08-13T10:05:00", "2026-08-13T12:00:00", crew=["E1"], priority=4),
        )

        proposals = client.post("/api/schedule/alternatives", json={"request_ids": ["M-002"]})
        applied = client.post(
            "/api/schedule/apply?option=critical_work_first&role=schedule_manager",
            json={"request_ids": ["M-002"]},
        )

        self.assertEqual(proposals.status_code, 200)
        self.assertTrue(all("M-002" in {item["request_id"] for item in proposal["scheduled_work"]} for proposal in proposals.json()))
        self.assertEqual(applied.status_code, 200)
        self.assertIn("M-002", SCHEDULED_WORK)
        self.assertNotIn("M-003", SCHEDULED_WORK)

    def test_approve_selected_locks_only_selected_scheduled_tasks(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T11:00:00", track="T08"),
        )
        client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T10:00:00", "2026-08-13T11:00:00", track="T09"),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")

        pending_denied = client.post("/api/schedule/approve-selected?role=schedule_manager", json={"request_ids": ["M-404"]})
        approved = client.post("/api/schedule/approve-selected?role=schedule_manager", json={"request_ids": ["M-001"]})

        self.assertEqual(pending_denied.status_code, 422)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(SCHEDULED_WORK["M-001"].status, ApprovalStatus.LOCKED)
        self.assertEqual(SCHEDULED_WORK["M-002"].status, ApprovalStatus.SCHEDULED)

    def test_manager_proposal_can_move_locked_work_without_silent_mutation(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"], priority=3),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")
        client.post("/api/schedule/lock/M-001?role=schedule_manager")

        response = client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T10:00:00", "2026-08-13T10:30:00", crew=["E1"], priority=5),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["requires_manager_review"])
        self.assertGreaterEqual(body["suggested_alternatives"][0]["changed_jobs_count"], 1)
        self.assertGreaterEqual(body["suggested_alternatives"][0]["churn_penalty"], 0)
        self.assertEqual(SCHEDULED_WORK["M-001"].status, ApprovalStatus.LOCKED)
        self.assertNotIn("M-002", SCHEDULED_WORK)

        applied = client.post("/api/schedule/apply?option=critical_work_first&role=schedule_manager")

        self.assertEqual(applied.status_code, 200)
        self.assertIn("M-002", SCHEDULED_WORK)
        self.assertEqual(SCHEDULED_WORK["M-001"].status, ApprovalStatus.SCHEDULED)
        self.assertGreaterEqual(SCHEDULED_WORK["M-001"].start_time, SCHEDULED_WORK["M-002"].end_time)

    def test_demo_seed_and_reset_manage_in_memory_state(self) -> None:
        seeded = client.post("/api/demo/seed")

        self.assertEqual(seeded.status_code, 200)
        self.assertGreaterEqual(seeded.json()["requests"], 1)
        self.assertGreaterEqual(seeded.json()["locked_schedule_items"], 1)
        self.assertGreaterEqual(seeded.json()["tentative_schedule_items"], 1)
        self.assertIn("M-101", REQUESTS)
        self.assertIn("M-101", SCHEDULED_WORK)

        reset = client.post("/api/demo/reset")

        self.assertEqual(reset.status_code, 200)
        self.assertEqual(REQUESTS, {})
        self.assertEqual(SCHEDULED_WORK, {})

    def test_request_patch_revalidates_payload_and_keeps_identity_stable(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )

        invalid_duration = client.patch("/api/requests/M-001", json={"duration_minutes": 0})
        changed_id = client.patch("/api/requests/M-001", json={"request_id": "M-999"})
        unknown_field = client.patch("/api/requests/M-001", json={"unexpected": True})

        self.assertEqual(invalid_duration.status_code, 422)
        self.assertEqual(changed_id.status_code, 422)
        self.assertEqual(unknown_field.status_code, 422)
        self.assertIn("M-001", REQUESTS)
        self.assertNotIn("M-999", REQUESTS)

    def test_schedule_modify_rejects_protected_fields_and_revalidates_times(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")

        protected = client.patch(
            "/api/schedule/modify/M-001?role=schedule_manager",
            json={"status": "locked"},
        )
        invalid_window = client.patch(
            "/api/schedule/modify/M-001?role=schedule_manager",
            json={"end_time": "2026-08-13T00:30:00"},
        )

        self.assertEqual(protected.status_code, 422)
        self.assertEqual(invalid_window.status_code, 422)
        self.assertEqual(SCHEDULED_WORK["M-001"].status, ApprovalStatus.SCHEDULED)

    def test_import_rejects_unsupported_file_type_and_non_object_json_rows(self) -> None:
        csv_as_text = client.post(
            "/api/import/confirm",
            files={"file": ("requests.txt", "not,csv\n", "text/plain")},
        )
        json_shape = client.post(
            "/api/import/json/confirm",
            files={"file": ("requests.json", json.dumps(["not an object"]), "application/json")},
        )

        self.assertEqual(csv_as_text.status_code, 415)
        self.assertEqual(json_shape.status_code, 422)

    def test_persistence_api_loads_saved_requests_and_schedule(self) -> None:
        created = client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")
        saved = client.post("/api/persistence/save")

        REQUESTS.replace_without_persist({})
        SCHEDULED_WORK.replace_without_persist({})

        loaded = client.post("/api/persistence/load")
        status = client.get("/api/persistence/status")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertIn("M-001", REQUESTS)
        self.assertIn("M-001", SCHEDULED_WORK)
        self.assertEqual(loaded.json()["requests"], 1)
        self.assertEqual(loaded.json()["scheduled_work"], 1)

    def test_unit_of_work_rolls_back_in_memory_and_database_changes(self) -> None:
        request = MaintenanceRequest.model_validate(
            request_payload("M-ROLLBACK", "2026-08-13T01:00:00", "2026-08-13T02:00:00")
        )

        with self.assertRaises(RuntimeError):
            with unit_of_work() as work:
                work.requests.save(request)
                raise RuntimeError("Rollback transaction.")

        loaded = client.post("/api/persistence/load")

        self.assertEqual(loaded.status_code, 200)
        self.assertNotIn("M-ROLLBACK", REQUESTS)

    def test_proposal_snapshots_are_saved_and_marked_applied(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"]),
        )
        client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T10:05:00", "2026-08-13T12:00:00", crew=["E1"]),
        )

        proposals = client.post("/api/schedule/alternatives", json={"request_ids": ["M-002"]})
        snapshots = client.get("/api/schedule/proposals")
        proposal_id = snapshots.json()[0]["proposal_id"]
        applied = client.post(
            "/api/schedule/apply?option=minimum_disruption&role=schedule_manager",
            json={"request_ids": ["M-002"], "proposal_id": proposal_id},
        )
        snapshot = client.get(f"/api/schedule/proposals/{proposal_id}")

        self.assertEqual(proposals.status_code, 200)
        self.assertGreaterEqual(len(proposals.json()), 1)
        self.assertEqual(snapshots.status_code, 200)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json()["status"], "applied")
        self.assertEqual(snapshot.json()["selected_option"], "minimum_disruption")

    def test_audit_events_capture_request_proposal_apply_and_approval(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"]),
        )
        client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T10:05:00", "2026-08-13T12:00:00", crew=["E1"]),
        )
        proposals = client.post("/api/schedule/alternatives", json={"request_ids": ["M-002"]})
        proposal_id = client.get("/api/schedule/proposals").json()[0]["proposal_id"]
        client.post(
            "/api/schedule/apply?option=minimum_disruption&role=schedule_manager",
            json={"request_ids": ["M-002"], "proposal_id": proposal_id},
        )
        client.post("/api/schedule/approve-selected?role=schedule_manager", json={"request_ids": ["M-002"]})

        events = client.get("/api/audit")
        request_events = client.get("/api/audit?request_id=M-002")
        event_types = {event["event_type"] for event in events.json()}

        self.assertEqual(proposals.status_code, 200)
        self.assertEqual(events.status_code, 200)
        self.assertEqual(request_events.status_code, 200)
        self.assertIn("request_created", event_types)
        self.assertIn("proposal_generated", event_types)
        self.assertIn("proposal_applied", event_types)
        self.assertIn("schedule_approved", event_types)
        self.assertTrue(all("M-002" in event["request_ids"] for event in request_events.json()))

    def test_scheduling_settings_default_and_manager_update(self) -> None:
        default_settings = client.get("/api/settings/scheduling")
        denied = client.patch("/api/settings/scheduling?role=requester", json={"urgent_lead_days": 5})
        updated = client.patch("/api/settings/scheduling?role=schedule_manager", json={"urgent_lead_days": 5})

        self.assertEqual(default_settings.status_code, 200)
        self.assertEqual(default_settings.json()["urgent_lead_days"], 3)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["urgent_lead_days"], 5)

    def test_catalog_exposes_requester_and_approver_roles(self) -> None:
        response = client.get("/api/catalog")

        self.assertEqual(response.status_code, 200)
        self.assertIn("requester", response.json()["user_roles"])
        self.assertIn("approver", response.json()["user_roles"])

    def test_rolling_planning_window_keeps_future_request_queued_until_lead_window(self) -> None:
        with (
            patch("app.scheduler.service.is_planning_eligible", return_value=False),
            patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=False),
        ):
            created = client.post(
                "/api/requests",
                json=request_payload("M-FUTURE", "2026-08-31T09:00:00", "2026-08-31T12:00:00"),
            )
            scheduled_too_early = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(created.status_code, 200)
        self.assertIsNone(created.json()["scheduled_work"])
        self.assertNotIn("M-FUTURE", SCHEDULED_WORK)
        self.assertEqual(scheduled_too_early.status_code, 200)
        self.assertNotIn("M-FUTURE", SCHEDULED_WORK)

        with (
            patch("app.scheduler.service.is_planning_eligible", return_value=True),
            patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True),
        ):
            scheduled_in_window = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(scheduled_in_window.status_code, 200)
        self.assertIn("M-FUTURE", SCHEDULED_WORK)
        self.assertGreaterEqual(SCHEDULED_WORK["M-FUTURE"].start_time, REQUESTS["M-FUTURE"].earliest_start)

    def test_manager_block_prevents_track_schedule_and_notifies_overlap_owner(self) -> None:
        client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T12:00:00", track="T08"),
        )

        block = client.post(
            "/api/schedule/blocks?role=schedule_manager",
            json={
                "track_sectors": ["T08"],
                "start_time": "2026-08-13T10:00:00",
                "end_time": "2026-08-13T11:00:00",
                "reason": "Manager possession block",
            },
        )
        scheduled = client.post("/api/schedule/optimise?option=minimum_disruption")
        notifications = client.get("/api/notifications?owner=field")

        self.assertEqual(block.status_code, 200)
        self.assertEqual(scheduled.status_code, 200)
        self.assertGreaterEqual(SCHEDULED_WORK["M-001"].start_time, datetime(2026, 8, 13, 11, 0, 0))
        self.assertEqual(notifications.status_code, 200)
        self.assertTrue(any("blocked slot" in item["message"] for item in notifications.json()))

    def test_urgent_conflict_waits_for_approver_before_schedule_changes(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 9, 0, 0, 0)):
            client.post(
                "/api/requests",
                json=request_payload("M-001", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"]),
            )
        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 10, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 10, 0, 0, 0)),
        ):
            client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 12, 0, 0, 0)):
            original_start = SCHEDULED_WORK["M-001"].start_time
            response = client.post(
                "/api/requests",
                json=request_payload("M-002", "2026-08-13T10:00:00", "2026-08-13T10:30:00", crew=["E1"], priority=5),
            )

        approvals = client.get("/api/displacement-approvals?owner=field&status=pending")
        notifications = client.get("/api/notifications?owner=approver")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["fits_current_schedule"])
        self.assertEqual(SCHEDULED_WORK["M-001"].start_time, original_start)
        self.assertEqual(approvals.status_code, 200)
        self.assertEqual(approvals.json(), [])
        self.assertEqual(notifications.status_code, 200)
        self.assertEqual(REQUESTS["M-002"].approval_status, ApprovalStatus.PENDING_APPROVAL)
        self.assertNotIn("M-002", SCHEDULED_WORK)
        self.assertTrue(any(item["type"] == "urgent_approval_requested" for item in notifications.json()))

    def test_approver_alias_can_use_manager_endpoints_and_requester_is_denied(self) -> None:
        denied = client.patch("/api/settings/scheduling?role=requester", json={"urgent_lead_days": 4})
        approved = client.patch("/api/settings/scheduling?role=approver", json={"urgent_lead_days": 4})

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["urgent_lead_days"], 4)

    def test_d_plus_three_batch_freezes_target_day(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 24, 0, 0, 0)):
            created = client.post(
                "/api/requests",
                json=request_payload("M-D3", "2026-08-28T09:00:00", "2026-08-28T11:00:00"),
            )

        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            frozen = client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(frozen.status_code, 200)
        self.assertEqual(frozen.json()["target_date"], "2026-08-28")
        self.assertEqual(SCHEDULED_WORK["M-D3"].status, ApprovalStatus.LOCKED)
        self.assertTrue(REQUESTS["M-D3"].locked)

    def test_generate_keeps_near_term_work_tentative_until_freeze(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 24, 0, 0, 0)):
            created = client.post(
                "/api/requests",
                json=request_payload("M-D3-TENTATIVE", "2026-08-28T09:00:00", "2026-08-28T11:00:00"),
            )

        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)):
            generated = client.post("/api/schedule/optimise?option=minimum_disruption")
            regenerated = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(SCHEDULED_WORK["M-D3-TENTATIVE"].status, ApprovalStatus.SCHEDULED)

        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            frozen = client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")

        self.assertEqual(frozen.status_code, 200)
        self.assertEqual(SCHEDULED_WORK["M-D3-TENTATIVE"].status, ApprovalStatus.LOCKED)

    def test_exact_d_plus_three_submission_after_freeze_requires_approval(self) -> None:
        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            frozen = client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")
            created = client.post(
                "/api/requests",
                json=request_payload("M-LATE-D3", "2026-08-28T09:00:00", "2026-08-28T10:00:00"),
            )

        self.assertEqual(frozen.status_code, 200)
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["requires_manager_review"])
        self.assertEqual(REQUESTS["M-LATE-D3"].approval_status, ApprovalStatus.PENDING_APPROVAL)
        self.assertNotIn("M-LATE-D3", SCHEDULED_WORK)

    def test_urgent_no_slot_submission_copies_notes_for_approver(self) -> None:
        BLOCKED_TIME_SLOTS["BLOCK-D1"] = BlockedTimeSlot(
            block_id="BLOCK-D1",
            track_sectors=["T08"],
            start_time=datetime(2026, 8, 26, 9, 0, 0),
            end_time=datetime(2026, 8, 26, 10, 0, 0),
            reason="No access",
            created_at=datetime(2026, 8, 25, 0, 0, 0),
        )
        payload = request_payload("M-D1-NOTE", "2026-08-26T09:00:00", "2026-08-26T10:00:00")
        payload["notes"] = "Please move another job if needed."

        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            created = client.post("/api/requests", json=payload)

        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["requires_manager_review"])
        self.assertIsNone(created.json()["request"]["recommended_start"])
        self.assertEqual(REQUESTS["M-D1-NOTE"].requester_message, "Please move another job if needed.")

    def test_recommend_slot_returns_earliest_feasible_gap_without_moving_current_schedule(self) -> None:
        with patch("app.scheduler.service.is_planning_eligible", return_value=True):
            client.post(
                "/api/requests",
                json=request_payload("M-BASE", "2026-08-29T09:00:00", "2026-08-29T10:00:00", crew=["E1"]),
            )
        client.post("/api/schedule/lock/M-BASE?role=approver")

        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            recommendation = client.post(
                "/api/requests/recommend-slot",
                json=request_payload("M-URG", "2026-08-29T09:00:00", "2026-08-29T11:00:00", crew=["E1"]),
            )

        self.assertEqual(recommendation.status_code, 200)
        self.assertTrue(recommendation.json()["available"])
        self.assertEqual(recommendation.json()["recommended_work"]["start_time"], "2026-08-29T09:30:00")
        self.assertEqual(SCHEDULED_WORK["M-BASE"].start_time, datetime(2026, 8, 29, 9, 0, 0))

    def test_recommend_slot_no_slot_allows_requester_message_for_approver(self) -> None:
        with patch("app.scheduler.service.is_planning_eligible", return_value=True):
            client.post(
                "/api/requests",
                json=request_payload("M-BASE", "2026-08-29T09:00:00", "2026-08-29T10:00:00", crew=["E1"]),
            )
        client.post("/api/schedule/lock/M-BASE?role=approver")

        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            recommendation = client.post(
                "/api/requests/recommend-slot",
                json=request_payload("M-NOSLOT", "2026-08-29T09:00:00", "2026-08-29T09:30:00", crew=["E1"]),
            )
        client.post(
            "/api/requests",
            json=request_payload("M-NOSLOT", "2026-08-29T09:00:00", "2026-08-29T09:30:00", crew=["E1"]),
        )
        confirmed = client.post(
            "/api/requests/M-NOSLOT/confirm-urgent",
            json={"requester_message": "Please review manually."},
        )

        self.assertEqual(recommendation.status_code, 200)
        self.assertFalse(recommendation.json()["available"])
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(REQUESTS["M-NOSLOT"].approval_status, ApprovalStatus.PENDING_APPROVAL)
        self.assertEqual(REQUESTS["M-NOSLOT"].requester_message, "Please review manually.")
        self.assertTrue(any(item.owner == "approver" for item in NOTIFICATIONS.values()))

    def test_urgent_confirm_approve_and_reject_reason_workflow(self) -> None:
        patch("app.scheduler.service.is_planning_eligible", return_value=False).start(); self.addCleanup(patch.stopall); client.post(
            "/api/requests",
            json=request_payload("M-URG", "2026-08-30T09:00:00", "2026-08-30T10:00:00", track="T08", crew=["E1"]),
        )
        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            confirmed = client.post("/api/requests/M-URG/confirm-urgent", json={})
        denied = client.post("/api/approvals/M-URG/approve?role=requester")
        approved = client.post("/api/approvals/M-URG/approve?role=approver")

        patch("app.scheduler.service.is_planning_eligible", return_value=False).start(); client.post(
            "/api/requests",
            json=request_payload("M-REJECT", "2026-08-30T11:00:00", "2026-08-30T12:00:00", track="T09", crew=["E2"]),
        )
        patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True).start(); client.post("/api/requests/M-REJECT/confirm-urgent", json={})
        missing_reason = client.post("/api/approvals/M-REJECT/reject?role=approver", json={"reason": ""})
        rejected = client.post("/api/approvals/M-REJECT/reject?role=approver", json={"reason": "Insufficient access window."})

        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(approved.status_code, 200)
        self.assertIn("M-URG", SCHEDULED_WORK)
        self.assertEqual(missing_reason.status_code, 422)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(REQUESTS["M-REJECT"].approval_status, ApprovalStatus.REJECTED)
        self.assertEqual(REQUESTS["M-REJECT"].rejection_reason, "Insufficient access window.")

    def test_approver_can_delete_scheduled_work(self) -> None:
        with patch("app.scheduler.service.is_planning_eligible", return_value=True):
            client.post(
                "/api/requests",
                json=request_payload("M-DELETE", "2026-08-30T09:00:00", "2026-08-30T10:00:00"),
            )

        denied = client.delete("/api/schedule/M-DELETE?role=requester")
        deleted = client.delete("/api/schedule/M-DELETE?role=approver")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(deleted.status_code, 200)
        self.assertNotIn("M-DELETE", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-DELETE"].approval_status, ApprovalStatus.DRAFT)

    def test_approver_can_delete_frozen_scheduled_work(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 24, 0, 0, 0)):
            client.post(
                "/api/requests",
                json=request_payload("M-FROZEN-DELETE", "2026-08-28T09:00:00", "2026-08-28T11:00:00", crew=["E1"]),
            )

        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")

        deleted = client.delete("/api/schedule/M-FROZEN-DELETE?role=approver")

        self.assertEqual(deleted.status_code, 200)
        self.assertNotIn("M-FROZEN-DELETE", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-FROZEN-DELETE"].approval_status, ApprovalStatus.DRAFT)
        self.assertFalse(REQUESTS["M-FROZEN-DELETE"].locked)

    def test_approver_can_move_frozen_work_inside_deadline(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 24, 0, 0, 0)):
            client.post(
                "/api/requests",
                json=request_payload("M-FROZEN-MOVE", "2026-08-28T09:00:00", "2026-08-28T11:00:00", crew=["E1"]),
            )

        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")

        moved = client.patch(
            "/api/schedule/modify/M-FROZEN-MOVE?role=approver",
            json={
                "start_time": "2026-08-28T10:00:00",
                "end_time": "2026-08-28T10:30:00",
                "change_reason": "Approver emergency override.",
            },
        )

        self.assertEqual(moved.status_code, 200)
        self.assertEqual(SCHEDULED_WORK["M-FROZEN-MOVE"].start_time, datetime(2026, 8, 28, 10, 0, 0))
        self.assertEqual(REQUESTS["M-FROZEN-MOVE"].fixed_start, datetime(2026, 8, 28, 10, 0, 0))
        self.assertTrue(REQUESTS["M-FROZEN-MOVE"].locked)

    def test_cp_sat_places_earliest_feasible_slot_and_respects_resource_conflicts(self) -> None:
        requests = [
            MaintenanceRequest.model_validate(
                request_payload("M-001", "2026-09-01T09:00:00", "2026-09-01T12:00:00", track="T01", crew=["E1"], equipment=["EQ1"])
            ),
            MaintenanceRequest.model_validate(
                request_payload("M-002", "2026-09-01T09:00:00", "2026-09-01T12:00:00", track="T01", crew=["E1"], equipment=["EQ1"])
            ),
        ]

        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            scheduled = optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION)

        self.assertEqual(len(scheduled), 2)
        first, second = sorted(scheduled, key=lambda item: item.start_time)
        self.assertEqual(first.start_time, datetime(2026, 9, 1, 9, 0, 0))
        self.assertGreaterEqual(second.start_time, first.end_time)

    def test_cp_sat_adds_break_when_same_team_would_exceed_four_continuous_hours(self) -> None:
        first = request_payload("M-LONG-1", "2026-09-02T09:00:00", "2026-09-02T18:00:00", track="T31", crew=["E7"])
        second = request_payload("M-LONG-2", "2026-09-02T09:00:00", "2026-09-02T18:00:00", track="T32", crew=["E7"])
        first["duration_minutes"] = 180
        second["duration_minutes"] = 180
        requests = [MaintenanceRequest.model_validate(first), MaintenanceRequest.model_validate(second)]

        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            scheduled = sorted(optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION), key=lambda item: item.start_time)

        self.assertEqual(len(scheduled), 2)
        self.assertGreaterEqual((scheduled[1].start_time - scheduled[0].end_time).total_seconds() / 60, 30)

    def test_cp_sat_uses_back_to_back_same_team_work_when_break_is_infeasible(self) -> None:
        first = request_payload("M-TIGHT-1", "2026-09-03T09:00:00", "2026-09-03T15:00:00", track="T41", crew=["E8"])
        second = request_payload("M-TIGHT-2", "2026-09-03T09:00:00", "2026-09-03T15:00:00", track="T42", crew=["E8"])
        first["duration_minutes"] = 180
        second["duration_minutes"] = 180
        requests = [MaintenanceRequest.model_validate(first), MaintenanceRequest.model_validate(second)]

        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            scheduled = sorted(optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION), key=lambda item: item.start_time)

        self.assertEqual(len(scheduled), 2)
        self.assertEqual((scheduled[1].start_time - scheduled[0].end_time).total_seconds() / 60, 0)

    def test_requester_urgent_in_frozen_window_requires_approver_instead_of_auto_schedule(self) -> None:
        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            created = client.post(
                "/api/requests",
                json=request_payload("M-D2-URG", "2026-08-27T09:00:00", "2026-08-27T10:00:00", crew=["E1"]),
            )

        self.assertEqual(created.status_code, 200)
        self.assertFalse(created.json()["fits_current_schedule"])
        self.assertTrue(created.json()["requires_manager_review"])
        self.assertIsNone(created.json()["scheduled_work"])
        self.assertNotIn("M-D2-URG", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-D2-URG"].approval_status, ApprovalStatus.PENDING_APPROVAL)
        self.assertEqual(REQUESTS["M-D2-URG"].recommended_start, datetime(2026, 8, 27, 9, 0, 0))

    def test_approver_cannot_approve_unconfirmed_draft_request(self) -> None:
        with patch("app.scheduler.service.is_planning_eligible", return_value=False):
            created = client.post(
                "/api/requests",
                json=request_payload("M-DRAFT-FUTURE", "2026-09-10T09:00:00", "2026-09-10T10:00:00", crew=["E1"]),
            )
        approved = client.post("/api/approvals/M-DRAFT-FUTURE/approve?role=approver")

        self.assertEqual(created.status_code, 200)
        self.assertIsNone(created.json()["scheduled_work"])
        self.assertEqual(approved.status_code, 422)
        self.assertNotIn("M-DRAFT-FUTURE", SCHEDULED_WORK)

    def test_d_plus_three_batch_locks_target_day_while_d_plus_two_request_needs_approval(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 24, 0, 0, 0)):
            client.post(
                "/api/requests",
                json=request_payload("M-D3", "2026-08-28T09:00:00", "2026-08-28T10:00:00", crew=["E2"]),
            )

        with (
            patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
            patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)),
        ):
            client.post(
                "/api/requests",
                json=request_payload("M-D2", "2026-08-27T09:00:00", "2026-08-27T10:00:00", crew=["E1"]),
            )
            frozen = client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")

        self.assertEqual(frozen.status_code, 200)
        self.assertEqual(SCHEDULED_WORK["M-D3"].status, ApprovalStatus.LOCKED)
        self.assertNotIn("M-D2", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-D2"].approval_status, ApprovalStatus.PENDING_APPROVAL)


if __name__ == "__main__":
    unittest.main()
