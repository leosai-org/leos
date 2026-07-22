from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from lifecycle_engine import (
    EmployeeConflictError,
    EmployeeLifecycleEngine,
    EmployeeLifecycleError,
)


def definition(employee_id: str = "content-writer"):
    return {
        "employee_id": employee_id,
        "name": "Content Writer",
        "description": "Writes governed content.",
        "role": "writer",
        "department": "marketing",
        "capabilities": ["research", "write", "review"],
        "priority": "normal",
        "schedule": {"mode": "always", "timezone": "UTC"},
        "model_preferences": [
            {"provider": "local", "model": "qwen2.5:7b-instruct", "priority": 1}
        ],
        "resource_profile": {
            "resource_profile": {
                "cpu_cores_min": 2,
                "memory_mb_min": 2048,
                "gpu_required": False,
                "vram_mb_min": 0,
                "gpu_uuid_preferences": [],
            },
            "execution_policy": {
                "max_concurrent_jobs": 2,
                "queue_when_unavailable": True,
                "preemptible": True,
                "allow_preemption": False,
                "reservation_ttl_seconds": 600,
            },
        },
        "runtime": {"type": "http", "endpoint": "http://writer:8000"},
        "limits": {"max_parallel_jobs": 2, "max_runtime_seconds": 300, "max_retries": 2},
        "metadata": {"source": "test"},
    }


class EmployeeLifecycleEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = EmployeeLifecycleEngine(Path(self.temp.name) / "registry.db")

    def tearDown(self):
        self.temp.cleanup()

    def create_validated(self, employee_id: str = "content-writer"):
        self.engine.create(definition(employee_id), actor="test")
        return self.engine.validate_existing(employee_id, actor="test")

    def create_active(self, employee_id: str = "content-writer"):
        self.create_validated(employee_id)
        return self.engine.transition(employee_id, "active", actor="test")

    def test_create_starts_in_draft(self):
        employee = self.engine.create(definition(), actor="test")
        self.assertEqual(employee["lifecycle_status"], "draft")
        self.assertEqual(employee["revision"], 1)
        self.assertEqual(employee["validation_state"], "pending")

    def test_duplicate_create_rejected(self):
        self.engine.create(definition())
        with self.assertRaises(EmployeeConflictError):
            self.engine.create(definition())

    def test_validation_moves_draft_to_validated(self):
        employee = self.create_validated()
        self.assertEqual(employee["lifecycle_status"], "validated")
        self.assertEqual(employee["validation_state"], "valid")

    def test_activation_requires_validation(self):
        self.engine.create(definition())
        with self.assertRaises(EmployeeConflictError):
            self.engine.transition("content-writer", "active")

    def test_activate_pause_resume_disable_archive(self):
        active = self.create_active()
        self.assertEqual(active["lifecycle_status"], "active")
        paused = self.engine.transition("content-writer", "paused")
        self.assertEqual(paused["lifecycle_status"], "paused")
        resumed = self.engine.transition("content-writer", "active")
        self.assertEqual(resumed["lifecycle_status"], "active")
        disabled = self.engine.transition("content-writer", "disabled")
        self.assertEqual(disabled["lifecycle_status"], "disabled")
        reactivated = self.engine.transition("content-writer", "active")
        self.assertEqual(reactivated["lifecycle_status"], "active")
        archived = self.engine.transition("content-writer", "archived")
        self.assertEqual(archived["lifecycle_status"], "archived")

    def test_archived_is_terminal(self):
        self.create_active()
        self.engine.transition("content-writer", "archived")
        with self.assertRaises(EmployeeConflictError):
            self.engine.transition("content-writer", "active")

    def test_active_employee_is_eligible(self):
        self.create_active()
        result = self.engine.eligibility("content-writer")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["decision"], "eligible")

    def test_paused_employee_is_queued(self):
        self.create_active()
        self.engine.transition("content-writer", "paused")
        result = self.engine.eligibility("content-writer")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["decision"], "queued")
        self.assertIn("employee-lifecycle-paused", result["reasons"])

    def test_disabled_employee_is_rejected(self):
        self.create_active()
        self.engine.transition("content-writer", "disabled")
        result = self.engine.eligibility("content-writer")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["decision"], "rejected")

    def test_schedule_window_enforced(self):
        value = definition()
        value["schedule"] = {
            "mode": "windows",
            "timezone": "UTC",
            "windows": [{"weekdays": [0], "start": "08:00", "end": "09:00", "timezone": "UTC"}],
        }
        self.engine.create(value)
        self.engine.validate_existing("content-writer")
        self.engine.transition("content-writer", "active")
        outside = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc).isoformat()
        result = self.engine.eligibility("content-writer", outside)
        self.assertFalse(result["eligible"])
        self.assertIn("employee-outside-schedule", result["reasons"])

    def test_concurrency_limit_enforced(self):
        self.create_active()
        self.engine.heartbeat("content-writer", current_jobs=2)
        result = self.engine.eligibility("content-writer")
        self.assertFalse(result["eligible"])
        self.assertIn("employee-concurrency-limit-reached", result["reasons"])

    def test_assignment_update_preserves_active_state(self):
        self.create_active()
        updated = self.engine.update_assignments(
            "content-writer",
            {
                "capabilities": ["research", "write", "review", "publish"],
                "priority": "elevated",
                "schedule": {"mode": "always", "timezone": "UTC"},
            },
        )
        self.assertEqual(updated["lifecycle_status"], "active")
        self.assertEqual(updated["priority"], "elevated")
        self.assertIn("publish", updated["capabilities"])

    def test_resource_profile_payload_matches_employee(self):
        self.create_active()
        profile = self.engine.resource_profile_payload("content-writer")
        self.assertTrue(profile["enabled"])
        self.assertEqual(profile["employee_id"], "content-writer")
        self.assertEqual(profile["execution_policy"]["max_concurrent_jobs"], 2)
        self.assertEqual(profile["provider_preferences"][0]["model"], "qwen2.5:7b-instruct")

    def test_resolve_selects_only_eligible_full_match(self):
        self.create_active("content-writer")
        other = definition("paused-writer")
        self.engine.create(other)
        self.engine.validate_existing("paused-writer")
        self.engine.transition("paused-writer", "active")
        self.engine.transition("paused-writer", "paused")
        result = self.engine.resolve(["write", "review"])
        self.assertEqual(result["resolution"]["selected_employee_id"], "content-writer")

    def test_history_is_persistent_and_revisioned(self):
        self.create_active()
        self.engine.transition("content-writer", "paused", actor="admin", reason="maintenance")
        history = self.engine.history("content-writer")
        self.assertGreaterEqual(history["event_count"], 4)
        self.assertEqual(history["events"][0]["event_type"], "employee.paused")
        self.assertEqual(history["events"][0]["reason"], "maintenance")

    def test_invalid_employee_id_rejected(self):
        value = definition()
        value["employee_id"] = "Bad Employee"
        with self.assertRaises(EmployeeLifecycleError):
            self.engine.create(value)

    def test_invalid_capability_rejected(self):
        value = definition()
        value["capabilities"] = ["Bad Capability"]
        with self.assertRaises(EmployeeLifecycleError):
            self.engine.create(value)


if __name__ == "__main__":
    unittest.main()
