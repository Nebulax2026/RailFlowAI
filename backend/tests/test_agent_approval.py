from __future__ import annotations

import sys
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import agent
from app.main import app
from app.storage import (
    AUDIT_EVENTS, BLOCKED_TIME_SLOTS, DISPLACEMENT_APPROVALS, NOTIFICATIONS,
    PROPOSAL_SNAPSHOTS, REQUESTS, SCHEDULED_WORK, SETTINGS,
    initialize_database,
)


client = TestClient(app)


class AgentApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        initialize_database()
        for collection in (REQUESTS, SCHEDULED_WORK, PROPOSAL_SNAPSHOTS, AUDIT_EVENTS, SETTINGS, BLOCKED_TIME_SLOTS, NOTIFICATIONS, DISPLACEMENT_APPROVALS):
            collection.clear()
        agent._pending.clear()
        client.get("/api/settings/scheduling")

    @patch("app.api.agent._openai_response")
    def test_mutation_is_staged_then_applied_exactly_once(self, model_response) -> None:
        model_response.return_value = {"output": [{"type": "function_call", "call_id": "call-1", "name": "railflow_action", "arguments": '{"action":"update_settings","params":{"payload":{"urgent_lead_days":5}}}'}]}
        staged = client.post("/api/agent/chat", json={"message": "Set the urgent lead window to 5 days", "role": "approver", "owner": "field"})
        self.assertEqual(staged.status_code, 200)
        approval_id = staged.json()["pending"]["approval_id"]
        self.assertEqual(client.get("/api/settings/scheduling").json()["urgent_lead_days"], 3)

        applied = client.post(f"/api/agent/approve/{approval_id}", json={"role": "approver", "owner": "field"})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(client.get("/api/settings/scheduling").json()["urgent_lead_days"], 5)
        repeated = client.post(f"/api/agent/approve/{approval_id}", json={"role": "approver", "owner": "field"})
        self.assertEqual(repeated.status_code, 409)

    def test_reject_makes_no_change(self) -> None:
        staged = agent._stage("update_settings", {"payload": {"urgent_lead_days": 7}}, "approver", "field")
        rejected = client.post(f"/api/agent/reject/{staged['approval_id']}", json={"role": "approver", "owner": "field"})
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(client.get("/api/settings/scheduling").json()["urgent_lead_days"], 3)

    def test_changed_state_invalidates_approval(self) -> None:
        staged = agent._stage("update_settings", {"payload": {"urgent_lead_days": 7}}, "approver", "field")
        changed = client.patch("/api/settings/scheduling?role=approver", json={"urgent_lead_days": 4})
        self.assertEqual(changed.status_code, 200)
        applied = client.post(f"/api/agent/approve/{staged['approval_id']}", json={"role": "approver", "owner": "field"})
        self.assertEqual(applied.status_code, 409)
        self.assertEqual(client.get("/api/settings/scheduling").json()["urgent_lead_days"], 4)

    def test_manager_action_cannot_be_staged_as_requester(self) -> None:
        with self.assertRaises(Exception) as error:
            agent._stage("freeze_schedule", {}, "requester", "field")
        self.assertEqual(getattr(error.exception, "status_code", None), 403)
        self.assertFalse(agent._pending)

    @patch("app.settings.demo_controls_enabled", return_value=False)
    def test_hosted_demo_control_cannot_be_staged(self, _enabled) -> None:
        with self.assertRaises(Exception) as error:
            agent._stage("reset_demo", {}, "approver", "field")
        self.assertEqual(getattr(error.exception, "status_code", None), 403)
        self.assertFalse(agent._pending)

    def test_invalid_import_never_creates_approval(self) -> None:
        response = client.post(
            "/api/agent/import/preview?role=requester&owner=field",
            files={"file": ("bad.json", b"not json", "application/json")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(agent._pending)

    def test_json_import_waits_for_approval(self) -> None:
        start = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=1, minute=0, second=0, microsecond=0)
        payload = [{
            "request_id": "AGENT-IMPORT-1", "title": "Inspect track", "track_sector": "T08",
            "work_type": "inspection", "duration_minutes": 30,
            "earliest_start": start.isoformat(), "deadline": (start + timedelta(hours=2)).isoformat(),
            "priority": 3, "required_crew": [], "required_equipment": [],
        }]
        staged = client.post(
            "/api/agent/import/preview?role=requester&owner=field",
            files={"file": ("requests.json", json.dumps(payload).encode(), "application/json")},
        )
        self.assertEqual(staged.status_code, 200)
        approval_id = staged.json()["pending"]["approval_id"]
        self.assertNotIn("AGENT-IMPORT-1", REQUESTS)
        applied = client.post(f"/api/agent/approve/{approval_id}", json={"role": "requester", "owner": "field"})
        self.assertEqual(applied.status_code, 200)
        self.assertIn("AGENT-IMPORT-1", REQUESTS)


if __name__ == "__main__":
    unittest.main()
