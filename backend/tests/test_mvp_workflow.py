import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.enums import ApprovalStatus
from app.main import app
from app.storage import REQUESTS, SCHEDULED_WORK


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

    def test_valid_request_fit_without_active_conflicts(self) -> None:
        response = client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T01:00:00", "2026-08-13T02:00:00"),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["fits_current_schedule"])
        self.assertEqual(body["conflicts"], [])

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

    def test_hard_validation_rejects_engineering_hours_and_prerequisites(self) -> None:
        hours_response = client.post(
            "/api/requests",
            json=request_payload("M-001", "2026-08-13T05:30:00", "2026-08-13T06:30:00"),
        )
        dependency_response = client.post(
            "/api/requests",
            json=request_payload("M-002", "2026-08-13T01:00:00", "2026-08-13T02:00:00", work_type="signal_test"),
        )

        self.assertEqual(hours_response.status_code, 422)
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


if __name__ == "__main__":
    unittest.main()
