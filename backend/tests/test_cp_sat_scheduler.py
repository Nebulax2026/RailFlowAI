import sys
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.conflict.detector import detect_conflicts
from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest
from app.main import app
from app.scheduler.cp_sat_scheduler import SchedulingInfeasibleError, optimise_schedule
from app.storage import REQUESTS, SCHEDULED_WORK

client = TestClient(app)

ALL_OPTIONS = [
    ScheduleOption.MINIMUM_DISRUPTION,
    ScheduleOption.MINIMUM_OVERTIME,
    ScheduleOption.MAXIMUM_COMPLETION,
    ScheduleOption.CRITICAL_WORK_FIRST,
]


class CpSatSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        REQUESTS.clear()
        SCHEDULED_WORK.clear()

    def test_seeded_demo_data_is_feasible_with_no_conflicts_for_every_profile(self) -> None:
        seeded = client.post("/api/demo/seed")
        self.assertEqual(seeded.status_code, 200)
        total_requests = seeded.json()["requests"]

        for option in ALL_OPTIONS:
            response = client.post(f"/api/schedule/optimise?option={option.value}")
            self.assertEqual(response.status_code, 200, response.json())
            schedule = response.json()
            self.assertEqual(len(schedule), total_requests)

    def test_solver_places_all_jobs_without_hard_blockers(self) -> None:
        requests = [
            MaintenanceRequest(
                request_id="M-001",
                title="a",
                track_sector="T08",
                work_type="inspection",
                duration_minutes=45,
                earliest_start=datetime(2026, 8, 13, 9, 0),
                deadline=datetime(2026, 8, 13, 12, 0),
                priority=3,
                required_crew=["E1"],
            ),
            MaintenanceRequest(
                request_id="M-002",
                title="b",
                track_sector="T08",
                work_type="inspection",
                duration_minutes=45,
                earliest_start=datetime(2026, 8, 13, 9, 0),
                deadline=datetime(2026, 8, 13, 12, 0),
                priority=5,
                required_crew=["E1"],
            ),
            MaintenanceRequest(
                request_id="M-003",
                title="c",
                track_sector="T08",
                work_type="inspection",
                duration_minutes=45,
                earliest_start=datetime(2026, 8, 13, 9, 0),
                deadline=datetime(2026, 8, 13, 12, 0),
                priority=1,
                required_crew=["E1"],
            ),
        ]

        schedule = optimise_schedule(requests, ScheduleOption.CRITICAL_WORK_FIRST)

        self.assertEqual({item.request_id for item in schedule}, {"M-001", "M-002", "M-003"})
        self.assertEqual(detect_conflicts(schedule), [])
        by_id = {item.request_id: item for item in schedule}
        self.assertLessEqual(by_id["M-002"].start_time, by_id["M-001"].start_time)
        self.assertLessEqual(by_id["M-001"].start_time, by_id["M-003"].start_time)

    def test_dependency_order_is_enforced_as_a_hard_constraint(self) -> None:
        prerequisite = MaintenanceRequest(
            request_id="M-101",
            title="prereq",
            track_sector="T09",
            work_type="track_inspection",
            duration_minutes=40,
            earliest_start=datetime(2026, 8, 13, 9, 0),
            deadline=datetime(2026, 8, 13, 12, 0),
            priority=4,
        )
        dependent = MaintenanceRequest(
            request_id="M-102",
            title="follow-up",
            track_sector="T09",
            work_type="track_renewal",
            duration_minutes=40,
            earliest_start=datetime(2026, 8, 13, 9, 0),
            deadline=datetime(2026, 8, 13, 12, 0),
            priority=4,
            dependencies=["M-101"],
        )

        schedule = optimise_schedule([dependent, prerequisite], ScheduleOption.MAXIMUM_COMPLETION)

        by_id = {item.request_id: item for item in schedule}
        self.assertEqual(len(schedule), 2)
        self.assertLessEqual(by_id["M-101"].end_time, by_id["M-102"].start_time)

    def test_locked_baseline_conflict_raises_infeasible_error_with_blockers(self) -> None:
        first = MaintenanceRequest(
            request_id="M-001",
            title="a",
            track_sector="T08",
            work_type="inspection",
            duration_minutes=30,
            earliest_start=datetime(2026, 8, 13, 10, 0),
            deadline=datetime(2026, 8, 13, 10, 30),
            priority=3,
            required_crew=["E1"],
            locked=True,
            approval_status=ApprovalStatus.LOCKED,
            fixed_start=datetime(2026, 8, 13, 10, 0),
            fixed_end=datetime(2026, 8, 13, 10, 30),
        )
        second = MaintenanceRequest(
            request_id="M-002",
            title="b",
            track_sector="T08",
            work_type="inspection",
            duration_minutes=30,
            earliest_start=datetime(2026, 8, 13, 10, 10),
            deadline=datetime(2026, 8, 13, 10, 40),
            priority=3,
            required_crew=["E1"],
            locked=True,
            approval_status=ApprovalStatus.LOCKED,
            fixed_start=datetime(2026, 8, 13, 10, 10),
            fixed_end=datetime(2026, 8, 13, 10, 40),
        )

        with self.assertRaises(SchedulingInfeasibleError) as context:
            optimise_schedule([first, second], ScheduleOption.MINIMUM_DISRUPTION)

        self.assertTrue(context.exception.blockers)
        self.assertTrue(any("M-001" in blocker and "M-002" in blocker for blocker in context.exception.blockers))

    def test_optimise_api_surfaces_locked_conflict_as_actionable_422(self) -> None:
        client.post(
            "/api/requests",
            json={
                "request_id": "M-001",
                "title": "a",
                "track_sector": "T08",
                "work_type": "inspection",
                "duration_minutes": 30,
                "earliest_start": "2026-08-13T10:00:00",
                "deadline": "2026-08-13T10:30:00",
                "priority": 3,
                "required_crew": ["E1"],
            },
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")
        client.post("/api/schedule/lock/M-001?role=schedule_manager")

        # Directly corrupt the baseline to simulate two locked jobs that now overlap
        # on the same crew, which must never happen through the normal API but must
        # still fail loudly and actionably if it ever does.
        conflicting = SCHEDULED_WORK["M-001"].model_copy(
            update={"request_id": "M-002", "start_time": datetime(2026, 8, 13, 10, 10), "end_time": datetime(2026, 8, 13, 10, 40)}
        )
        SCHEDULED_WORK["M-002"] = conflicting
        REQUESTS["M-002"] = REQUESTS["M-001"].model_copy(
            update={
                "request_id": "M-002",
                "locked": True,
                "approval_status": ApprovalStatus.LOCKED,
                "fixed_start": conflicting.start_time,
                "fixed_end": conflicting.end_time,
            }
        )

        response = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(response.status_code, 422)
        detail = " ".join(response.json()["detail"])
        self.assertIn("M-001", detail)
        self.assertIn("M-002", detail)

    def test_time_limit_is_configurable_and_still_solves_a_small_batch(self) -> None:
        requests = [
            MaintenanceRequest(
                request_id="M-001",
                title="a",
                track_sector="T08",
                work_type="inspection",
                duration_minutes=30,
                earliest_start=datetime(2026, 8, 13, 9, 0),
                deadline=datetime(2026, 8, 13, 12, 0),
                priority=3,
            )
        ]

        schedule = optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION, time_limit_seconds=1.0)

        self.assertEqual(len(schedule), 1)


if __name__ == "__main__":
    unittest.main()
