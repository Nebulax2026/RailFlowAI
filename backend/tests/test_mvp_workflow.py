import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.enums import ApprovalStatus
from app.domain.models import MaintenanceRequest
from app.main import app
from app.repositories import unit_of_work
from app.storage import AUDIT_EVENTS, PROPOSAL_SNAPSHOTS, REQUESTS, SCHEDULED_WORK


client = TestClient(app)


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

    def test_valid_request_fit_without_active_conflicts(self) -> None:
        response = client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["fits_current_schedule"])
        self.assertEqual(body["conflicts"], [])
        self.assertIsNone(body["scheduled_work"])
        self.assertFalse(body["requires_manager_review"])
        self.assertNotIn("M-001", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-001"].approval_status, ApprovalStatus.DRAFT)

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


if __name__ == "__main__":
    unittest.main()
