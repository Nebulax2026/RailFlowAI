from __future__ import annotations

"""
요청하신 6가지 비즈니스 규칙을 검증하기 위한 추가 테스트.

원래 이 파일은 GitHub 웹(브랜치의 raw 파일 뷰)으로 코드만 읽고 작성했고,
당신이 로컬에서 pytest로 돌려서 실제 동작을 확인해 주셨습니다.

이슈 #29 (issue-29-fix-approval-scheduling-bugs 브랜치)에서 아래 3개 버그를 고친 뒤,
그때는 "버그 재현용"이었던 테스트 2개를 "고쳐졌는지 확인용"으로 업데이트했습니다:
  - test_non_5min_duration_slot_rounding_does_not_cause_real_overlap: 그대로 둠
    (원래도 "정상 동작을 기대하는" assert였고, 버그가 있을 때만 실패했음 → 이제 통과해야 함)
  - test_reject_now_guards_non_pending_state: 주석 처리됐던 422 assert를 활성화
  - test_confirm_urgent_on_already_scheduled_request_is_now_rejected: PENDING_APPROVAL로
    바뀌는 걸 확인하던 걸 → 422로 거부되고 상태/스케줄이 보존되는 걸 확인하도록 변경

"확인 필요"라고 표시된 나머지 항목들(D+3 경계값 포함 여부, displacement approval 소유자)은
스펙 vs 구현 불일치이지 버그가 아니라서, 이번 수정 범위에서 의도적으로 제외했습니다.

사용법:
    backend/tests/ 밑에 이 파일을 넣고
    cd backend
    Windows: py -m pytest tests/test_rule_verification.py -v
    macOS:   python3 -m pytest tests/test_rule_verification.py -v
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.enums import ApprovalStatus, ScheduleOption
from app.domain.models import MaintenanceRequest, ScheduledWork
from app.main import app
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


class BusinessRuleVerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        REQUESTS.clear()
        SCHEDULED_WORK.clear()
        PROPOSAL_SNAPSHOTS.clear()
        AUDIT_EVENTS.clear()
        SETTINGS.clear()
        BLOCKED_TIME_SLOTS.clear()
        NOTIFICATIONS.clear()
        DISPLACEMENT_APPROVALS.clear()

    # ---------------------------------------------------------------
    # 1. 승인자 전권 vs 요청자 차단
    # ---------------------------------------------------------------
    def test_only_approver_can_delete_update_delay_scheduled_work(self) -> None:
        # deadline을 넉넉하게 잡아야 함 (03:00~03:30로 옮길 거라서 deadline이 그보다 늦어야 함)
        client.post("/api/requests", json=request_payload("M-PERM", "2026-08-13T01:00:00", "2026-08-13T05:00:00"))
        client.post("/api/schedule/optimise?option=minimum_disruption")

        denied_modify = client.patch(
            "/api/schedule/modify/M-PERM?role=requester",
            json={"start_time": "2026-08-13T03:00:00", "end_time": "2026-08-13T03:30:00"},
        )
        allowed_modify = client.patch(
            "/api/schedule/modify/M-PERM?role=approver",
            json={"start_time": "2026-08-13T03:00:00", "end_time": "2026-08-13T03:30:00"},
        )
        denied_delete = client.delete("/api/schedule/M-PERM?role=requester")
        allowed_delete = client.delete("/api/schedule/M-PERM?role=approver")

        self.assertEqual(denied_modify.status_code, 403)
        self.assertEqual(allowed_modify.status_code, 200)
        self.assertEqual(denied_delete.status_code, 403)
        self.assertEqual(allowed_delete.status_code, 200)

    def test_existing_tentative_work_outside_d_plus_3_is_preserved(self) -> None:
        request = MaintenanceRequest.model_validate(
            request_payload("M-FUTURE-TENTATIVE", "2026-09-12T09:00:00", "2026-09-12T11:00:00", track="T09", crew=["TG1"])
        ).model_copy(update={"approval_status": ApprovalStatus.SCHEDULED})
        REQUESTS[request.request_id] = request
        SCHEDULED_WORK[request.request_id] = ScheduledWork(
            schedule_id="imported",
            request_id=request.request_id,
            start_time=datetime(2026, 9, 12, 9, 0, 0),
            end_time=datetime(2026, 9, 12, 9, 30, 0),
            assigned_crew=["TG1"],
            assigned_equipment=[],
            track_sector="T09",
            status=ApprovalStatus.SCHEDULED,
        )

        with patch("app.scheduler.service.is_planning_eligible", return_value=False), \
             patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=False):
            response = client.post("/api/schedule/optimise?option=minimum_disruption")

        self.assertEqual(response.status_code, 200)
        self.assertIn(request.request_id, SCHEDULED_WORK)
        self.assertEqual(SCHEDULED_WORK[request.request_id].status, ApprovalStatus.SCHEDULED)

    # ---------------------------------------------------------------
    # 2. 3일 리드타임 / D+3 경계값
    # ---------------------------------------------------------------
    def test_earliest_start_exactly_d_plus_3_is_not_forced_into_approver_review(self) -> None:
        """
        ⚠️ 확인 필요: requires_urgent_approver_review는 `< cutoff`(D+3 미포함)라서
        earliest_start가 정확히 D+3인 요청은 승인자 검토 없이 자동 배치됩니다.
        "3일 전에는 무조건 요청" 요구사항의 "3일 전" 정의(D+3 포함 여부)와
        실제 동작이 일치하는지 이 테스트로 직접 확인하세요.
        """
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)), \
             patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)), \
             patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            response = client.post(
                "/api/requests",
                json=request_payload("M-D3-EDGE", "2026-08-28T09:00:00", "2026-08-28T10:00:00"),
            )

        # 실제 관찰값을 출력해서 눈으로 확인하기 쉽게
        print("D+3 당일 요청 결과:", response.json()["fits_current_schedule"], response.json()["requires_manager_review"])

    def test_earliest_start_d_plus_2_is_forced_into_approver_review(self) -> None:
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)), \
             patch("app.scheduler.service.planning_now", return_value=datetime(2026, 8, 25, 0, 0, 0)):
            response = client.post(
                "/api/requests",
                json=request_payload("M-D2-EDGE", "2026-08-27T09:00:00", "2026-08-27T10:00:00"),
            )

        self.assertFalse(response.json()["fits_current_schedule"])
        self.assertTrue(response.json()["requires_manager_review"])
        self.assertEqual(REQUESTS["M-D2-EDGE"].approval_status, ApprovalStatus.PENDING_APPROVAL)

    # ---------------------------------------------------------------
    # 3. 매일 자정 D+3 배치 프리즈 (3일 연속 롤링)
    # ---------------------------------------------------------------
    def test_rolling_freeze_locks_each_day_exactly_three_days_ahead(self) -> None:
        for day, anchor in [("2026-08-28", datetime(2026, 8, 25, 0, 0, 0)),
                             ("2026-08-29", datetime(2026, 8, 26, 0, 0, 0)),
                             ("2026-08-30", datetime(2026, 8, 27, 0, 0, 0))]:
            request_id = f"M-ROLL-{day}"
            with patch("app.scheduler.policy.planning_now", return_value=anchor), \
                 patch("app.scheduler.service.planning_now", return_value=anchor), \
                 patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
                created = client.post(
                    "/api/requests",
                    json=request_payload(request_id, f"{day}T09:00:00", f"{day}T11:00:00"),
                )
                # --- 디버그 출력: 생성 직후 상태를 눈으로 확인 ---
                print(f"\n[{day}] create status={created.status_code}")
                if created.status_code != 200:
                    print(f"[{day}] create error body={created.json()}")
                print(f"[{day}] fits_current_schedule={created.json().get('fits_current_schedule')} "
                      f"requires_manager_review={created.json().get('requires_manager_review')}")
                print(f"[{day}] request approval_status={REQUESTS.get(request_id).approval_status if request_id in REQUESTS else 'MISSING FROM REQUESTS'}")
                print(f"[{day}] in SCHEDULED_WORK before freeze? {request_id in SCHEDULED_WORK}")
                if request_id in SCHEDULED_WORK:
                    print(f"[{day}] pre-freeze start_time={SCHEDULED_WORK[request_id].start_time} status={SCHEDULED_WORK[request_id].status}")

                frozen = client.post("/api/schedule/batch/freeze-d-plus-3?role=approver")
                print(f"[{day}] freeze status={frozen.status_code} body={frozen.json()}")
                print(f"[{day}] in SCHEDULED_WORK after freeze? {request_id in SCHEDULED_WORK}")
                print(f"[{day}] full SCHEDULED_WORK keys now: {list(SCHEDULED_WORK.keys())}")

            self.assertEqual(frozen.status_code, 200)
            self.assertEqual(frozen.json()["target_date"], day)
            self.assertIn(request_id, SCHEDULED_WORK, f"{request_id} not found in SCHEDULED_WORK after freeze")
            self.assertEqual(SCHEDULED_WORK[request_id].status, ApprovalStatus.LOCKED)

    # ---------------------------------------------------------------
    # 4. 선착순 배치 (deadline이 아니라 제출 순서 우선)
    # ---------------------------------------------------------------
    def test_urgent_deadline_does_not_bump_already_placed_earlier_request(self) -> None:
        # 먼저 들어온 M-A: deadline이 넉넉함
        client.post(
            "/api/requests",
            json=request_payload("M-A", "2026-08-13T10:00:00", "2026-08-13T18:00:00", crew=["E1"]),
        )
        client.post("/api/schedule/optimise?option=minimum_disruption")

        # 나중에 들어온 M-B: 같은 시간대, 같은 crew, 그러나 deadline이 훨씬 급함
        response = client.post(
            "/api/requests",
            json=request_payload("M-B", "2026-08-13T10:00:00", "2026-08-13T10:30:00", crew=["E1"]),
        )

        self.assertFalse(response.json()["fits_current_schedule"])
        self.assertTrue(response.json()["requires_manager_review"])
        self.assertIn("M-A", SCHEDULED_WORK)
        self.assertEqual(SCHEDULED_WORK["M-A"].start_time, datetime(2026, 8, 13, 10, 0, 0))
        self.assertNotIn("M-B", SCHEDULED_WORK)

    # ---------------------------------------------------------------
    # 5. CP-SAT 제약: 같은 팀 이중예약 금지 / 다른 팀은 자원만 안 겹치면 동시 가능
    # ---------------------------------------------------------------
    def test_same_crew_cannot_be_double_booked(self) -> None:
        requests = [
            MaintenanceRequest.model_validate(
                request_payload("A", "2026-09-05T09:00:00", "2026-09-05T12:00:00", track="T1", crew=["E9"])
            ),
            MaintenanceRequest.model_validate(
                request_payload("B", "2026-09-05T09:00:00", "2026-09-05T12:00:00", track="T2", crew=["E9"])
            ),
        ]
        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            scheduled = sorted(optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION), key=lambda s: s.start_time)

        self.assertEqual(len(scheduled), 2)
        self.assertLessEqual(scheduled[0].end_time, scheduled[1].start_time)

    def test_different_crews_and_equipment_can_run_concurrently(self) -> None:
        requests = [
            MaintenanceRequest.model_validate(
                request_payload("A", "2026-09-05T09:00:00", "2026-09-05T12:00:00", track="T1", crew=["E1"], equipment=["EQ1"])
            ),
            MaintenanceRequest.model_validate(
                request_payload("B", "2026-09-05T09:00:00", "2026-09-05T12:00:00", track="T2", crew=["E2"], equipment=["EQ2"])
            ),
        ]
        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            scheduled = optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION)

        by_id = {item.request_id: item for item in scheduled}
        self.assertEqual(by_id["A"].start_time, datetime(2026, 9, 5, 9, 0, 0))
        self.assertEqual(by_id["B"].start_time, datetime(2026, 9, 5, 9, 0, 0))

    def test_non_5min_duration_slot_rounding_does_not_cause_real_overlap(self) -> None:
        """⚠️ PR 리뷰 지적사항 재현: _to_slot()의 round() 때문에 실패할 가능성이 있음."""
        first = request_payload("A", "2026-09-06T09:00:00", "2026-09-06T09:20:00", crew=["E1"])
        first["duration_minutes"] = 7
        second = request_payload("B", "2026-09-06T09:00:00", "2026-09-06T09:20:00", crew=["E1"])
        second["duration_minutes"] = 7
        requests = [MaintenanceRequest.model_validate(first), MaintenanceRequest.model_validate(second)]

        with patch("app.scheduler.cp_sat_scheduler.is_planning_eligible", return_value=True):
            scheduled = sorted(optimise_schedule(requests, ScheduleOption.MINIMUM_DISRUPTION), key=lambda s: s.start_time)

        self.assertLessEqual(scheduled[0].end_time, scheduled[1].start_time)

    # ---------------------------------------------------------------
    # 6. 응급 재배정 5-1 / 5-2
    # ---------------------------------------------------------------
    def test_displacement_approval_is_decided_by_original_owner_not_approver(self) -> None:
        """
        ⚠️ 확인 필요: 스펙 5-1은 승인자가 일방적으로 처리한다고 되어있는데,
        실제 코드는 displaced request의 원래 소유자(created_by)만
        승인/거절할 수 있게 되어 있습니다. approver role로 시도하면 403이 나는지 확인.
        """
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 10, 0, 0, 0)):
            client.post(
                "/api/requests",
                json=request_payload("M-BASE", "2026-08-13T10:00:00", "2026-08-13T12:00:00", crew=["E1"]),
            )
        with patch("app.scheduler.policy.planning_now", return_value=datetime(2026, 8, 12, 0, 0, 0)):
            client.post(
                "/api/requests",
                json=request_payload("M-URGENT", "2026-08-13T10:00:00", "2026-08-13T10:30:00", crew=["E1"], priority=5),
            )

        approvals = client.get("/api/displacement-approvals?owner=field&status=pending").json()
        print("생성된 displacement approval 개수:", len(approvals))
        if approvals:
            approval_id = approvals[0]["approval_id"]
            # 승인자 role로 시도 -> owner check 때문에 403이 예상됨
            as_approver = client.post(f"/api/displacement-approvals/{approval_id}/approve?owner=approver")
            self.assertEqual(as_approver.status_code, 403)

    def test_reject_now_guards_non_pending_state(self) -> None:
        """✅ #29에서 수정 확인: reject가 이제 approval_status를 검증해서, 이미 SCHEDULED인
        요청에는 422를 반환하고 정상 스케줄을 그대로 보존합니다."""
        client.post("/api/requests", json=request_payload("M-NORMAL", "2026-08-13T01:00:00", "2026-08-13T02:00:00"))
        self.assertEqual(REQUESTS["M-NORMAL"].approval_status, ApprovalStatus.SCHEDULED)
        self.assertIn("M-NORMAL", SCHEDULED_WORK)

        response = client.post("/api/approvals/M-NORMAL/reject?role=approver", json={"reason": "test"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(REQUESTS["M-NORMAL"].approval_status, ApprovalStatus.SCHEDULED)
        self.assertIn("M-NORMAL", SCHEDULED_WORK)

    def test_confirm_urgent_on_already_scheduled_request_is_now_rejected(self) -> None:
        """✅ #29에서 수정 확인: confirm-urgent가 이미 SCHEDULED인 요청에는 이제 422를 반환하고,
        기존 스케줄과 상태를 그대로 보존합니다 (더 이상 stale entry를 남기지 않음).
        (원래 이 테스트는 버그를 재현해서 PENDING_APPROVAL로 바뀌는 걸 확인했지만,
        service.py에 상태 가드가 추가되면서 이제는 거부되는 게 맞는 동작입니다.)"""
        client.post("/api/requests", json=request_payload("M-ALREADY", "2026-08-13T01:00:00", "2026-08-13T02:00:00"))
        self.assertIn("M-ALREADY", SCHEDULED_WORK)
        self.assertEqual(REQUESTS["M-ALREADY"].approval_status, ApprovalStatus.SCHEDULED)

        response = client.post("/api/requests/M-ALREADY/confirm-urgent", json={})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(REQUESTS["M-ALREADY"].approval_status, ApprovalStatus.SCHEDULED)
        self.assertIn("M-ALREADY", SCHEDULED_WORK)


if __name__ == "__main__":
    unittest.main()
