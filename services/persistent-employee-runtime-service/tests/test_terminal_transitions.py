from __future__ import annotations

import json
import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

_ROOT = tempfile.TemporaryDirectory(prefix="leos-runtime-terminal-")
os.environ["PERSISTENT_EMPLOYEE_RUNTIME_DATA_DIR"] = _ROOT.name
os.environ["EMPLOYEE_RUNTIME_AUTO_POLL_SCHEDULER"] = "false"

from app import main as runtime  # noqa: E402


class FakeResponse:
    def __init__(self, body: dict, status_code: int = 200):
        self.status_code = status_code
        self.body = body
        self.text = json.dumps(body)

    def json(self):
        return self.body


class FakeClient:
    calls: list[tuple[str, dict]] = []
    response = FakeResponse(
        {"ok": True, "state": "failed", "resource_released": True}
    )
    get_response = FakeResponse({"jobs": []})

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        self.calls.append((url, json))
        return self.response

    async def get(self, url):
        return self.get_response


async def no_publish(*args, **kwargs):
    return False


async def publish_succeeds(*args, **kwargs):
    return True


class RuntimeTerminalTransitionTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        runtime.DATA_DIR = Path(_ROOT.name)
        runtime.DB_PATH = (
            runtime.DATA_DIR / "persistent-employee-runtime.db"
        )
        runtime.migrate()
        with runtime.connect() as db:
            for table in (
                "employee_event_outbox",
                "assignment_terminal_transitions",
                "employee_events",
                "employee_assignments",
                "employees",
            ):
                db.execute(f"DELETE FROM {table}")
            timestamp = runtime.now()
            db.execute(
                """
                INSERT INTO employees(
                    employee_id, name, role, status, runtime_state,
                    profile_json, permissions_json, capabilities_json,
                    metadata_json, current_job_id, current_assignment_id,
                    created_at, updated_at
                ) VALUES(
                    'employee-1', 'Employee', 'worker', 'online',
                    'working', '{}', '{}', '[]', '{}', 'job-1',
                    'assignment-1', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO employee_assignments(
                    assignment_id, employee_id, job_id, lease_id, state,
                    payload_json, assigned_at, updated_at, resource_state
                ) VALUES(
                    'assignment-1', 'employee-1', 'job-1', 'lease-1',
                    'running', '{}', ?, ?, 'active'
                )
                """,
                (timestamp, timestamp),
            )
        self.client = runtime.httpx.AsyncClient
        self.publish = runtime.publish_kernel_event
        runtime.httpx.AsyncClient = FakeClient
        runtime.publish_kernel_event = no_publish
        FakeClient.calls = []
        FakeClient.response = FakeResponse(
            {"ok": True, "state": "failed", "resource_released": True}
        )
        FakeClient.get_response = FakeResponse({"jobs": []})

    def tearDown(self) -> None:
        runtime.httpx.AsyncClient = self.client
        runtime.publish_kernel_event = self.publish

    def request(self, transition_id="transition-1"):
        return runtime.AssignmentTerminalTransition(
            transition_id=transition_id,
            cognitive_run_id="run-1",
            cognitive_attempt_id="attempt-3",
            execution_id="execution-3",
            reason={
                "code": "cognitive_attempts_exhausted",
                "message": "Cognitive attempts exhausted.",
            },
            result={"artifact_id": "artifact-1"},
        )

    async def test_failure_bridges_scheduler_and_cleans_runtime(self):
        result = await runtime.fail_assignment(
            "assignment-1", self.request()
        )
        self.assertEqual("failed", result["state"])
        self.assertEqual(1, len(FakeClient.calls))
        self.assertTrue(FakeClient.calls[0][0].endswith("/jobs/job-1/fail"))
        with runtime.connect() as db:
            assignment = db.execute(
                "SELECT * FROM employee_assignments"
            ).fetchone()
            employee = db.execute("SELECT * FROM employees").fetchone()
        self.assertEqual("failed", assignment["state"])
        self.assertEqual("released", assignment["resource_state"])
        self.assertEqual("idle", employee["runtime_state"])
        self.assertIsNone(employee["current_job_id"])

    async def test_same_transition_returns_without_second_scheduler_call(self):
        first = await runtime.fail_assignment(
            "assignment-1", self.request()
        )
        second = await runtime.fail_assignment(
            "assignment-1", self.request()
        )
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(1, len(FakeClient.calls))

    async def test_conflicting_transition_is_rejected(self):
        await runtime.fail_assignment("assignment-1", self.request())
        with self.assertRaises(HTTPException):
            await runtime.cancel_assignment(
                "assignment-1", self.request()
            )

    async def test_cancel_uses_scheduler_cancel(self):
        FakeClient.response = FakeResponse(
            {"ok": True, "state": "cancelled", "resource_released": True}
        )
        result = await runtime.cancel_assignment(
            "assignment-1", self.request("transition-cancel")
        )
        self.assertEqual("cancelled", result["state"])
        self.assertTrue(
            FakeClient.calls[0][0].endswith("/jobs/job-1/cancel")
        )

    async def test_complete_uses_same_journal_and_replays(self):
        FakeClient.response = FakeResponse(
            {"ok": True, "state": "complete", "resource_released": True}
        )
        request = self.request("transition-complete")
        first = await runtime.complete_assignment("assignment-1", request)
        second = await runtime.complete_assignment("assignment-1", request)
        self.assertEqual("complete", first["state"])
        self.assertFalse(second["changed"])
        self.assertEqual(1, len(FakeClient.calls))
        with runtime.connect() as db:
            journal = db.execute(
                "SELECT * FROM assignment_terminal_transitions"
            ).fetchone()
            outbox = db.execute(
                "SELECT * FROM employee_event_outbox"
            ).fetchone()
        self.assertEqual("local_committed", journal["state"])
        self.assertEqual(
            "assignment-terminal:transition-complete", outbox["event_id"]
        )

    async def test_late_a1_cleanup_preserves_current_a2_projection(self):
        with runtime.connect() as db:
            timestamp = runtime.now()
            db.execute(
                """
                INSERT INTO employee_assignments(
                    assignment_id, employee_id, job_id, workflow_id, step_id,
                    lease_id, state, payload_json, assigned_at, updated_at,
                    resource_state
                ) VALUES(
                    'assignment-2', 'employee-1', 'job-1', 'workflow-2',
                    'step-2', 'lease-2', 'running', '{}', ?, ?, 'active'
                )
                """,
                (timestamp, timestamp),
            )
            db.execute(
                """
                UPDATE employees SET current_assignment_id='assignment-2',
                    current_job_id='job-1', current_workflow_id='workflow-2',
                    current_step_id='step-2', runtime_state='working'
                WHERE employee_id='employee-1'
                """
            )
        await runtime.fail_assignment("assignment-1", self.request("late-a1"))
        with runtime.connect() as db:
            employee = db.execute(
                "SELECT * FROM employees WHERE employee_id='employee-1'"
            ).fetchone()
        self.assertEqual("assignment-2", employee["current_assignment_id"])
        self.assertEqual("working", employee["runtime_state"])
        self.assertEqual("workflow-2", employee["current_workflow_id"])

    async def test_different_transition_id_cannot_change_terminal_state(self):
        await runtime.fail_assignment("assignment-1", self.request("winner"))
        with self.assertRaises(HTTPException) as raised:
            await runtime.cancel_assignment(
                "assignment-1", self.request("loser")
            )
        self.assertEqual(409, raised.exception.status_code)

    async def test_concurrent_fail_vs_cancel_has_one_winner(self):
        results = await asyncio.gather(
            runtime.fail_assignment("assignment-1", self.request("race-fail")),
            runtime.cancel_assignment(
                "assignment-1", self.request("race-cancel")
            ),
            return_exceptions=True,
        )
        self.assertEqual(
            1, sum(isinstance(result, dict) for result in results)
        )
        self.assertEqual(
            1, sum(isinstance(result, HTTPException) for result in results)
        )

    async def test_new_assignment_identity_can_follow_failed_history(self):
        await runtime.fail_assignment("assignment-1", self.request())
        timestamp = runtime.now()
        with runtime.connect() as db:
            db.execute(
                """
                INSERT INTO employee_assignments(
                    assignment_id, employee_id, job_id, lease_id, state,
                    payload_json, assigned_at, updated_at
                ) VALUES(
                    'assignment-2', 'employee-1', 'job-1', 'lease-2',
                    'assigned', '{}', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
            rows = db.execute(
                "SELECT assignment_id, state FROM employee_assignments "
                "WHERE job_id='job-1' ORDER BY assigned_at"
            ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertEqual("failed", rows[0]["state"])
        self.assertEqual("assigned", rows[1]["state"])

    async def test_polling_creates_new_assignment_for_new_lease(self):
        await runtime.fail_assignment("assignment-1", self.request())
        FakeClient.get_response = FakeResponse(
            {
                "jobs": [
                    {
                        "job_id": "job-1",
                        "employee_id": "employee-1",
                        "state": "leased",
                        "lease_id": "lease-2",
                        "payload": {},
                    }
                ]
            }
        )
        imported = await runtime.import_scheduler_assignments()
        self.assertEqual(1, imported["imported"])
        with runtime.connect() as db:
            rows = db.execute(
                "SELECT assignment_id, lease_id, state "
                "FROM employee_assignments WHERE job_id='job-1' "
                "ORDER BY assigned_at"
            ).fetchall()
        self.assertEqual(2, len(rows))
        self.assertEqual("assignment-1", rows[0]["assignment_id"])
        self.assertNotEqual(rows[0]["assignment_id"], rows[1]["assignment_id"])
        self.assertEqual("lease-2", rows[1]["lease_id"])

    async def test_requested_transition_recovers_with_same_identity(self):
        request = self.request("transition-recover")
        timestamp = runtime.now()
        with runtime.connect() as db:
            db.execute(
                """
                INSERT INTO assignment_terminal_transitions(
                    transition_id, assignment_id, requested_state,
                    request_json, scheduler_result_json, state,
                    created_at, updated_at
                ) VALUES(
                    ?, 'assignment-1', 'failed', ?, NULL,
                    'requested', ?, ?
                )
                """,
                (
                    request.transition_id,
                    request.model_dump_json(),
                    timestamp,
                    timestamp,
                ),
            )
        recovered = await runtime.fail_assignment(
            "assignment-1", request
        )
        self.assertEqual("failed", recovered["state"])
        self.assertEqual(1, len(FakeClient.calls))

    async def test_scheduler_acknowledged_recovery_does_not_call_scheduler(self):
        request = self.request("transition-acknowledged")
        timestamp = runtime.now()
        scheduler_result = {
            "ok": True, "state": "failed", "resource_released": True
        }
        with runtime.connect() as db:
            db.execute(
                """
                INSERT INTO assignment_terminal_transitions(
                    transition_id, assignment_id, requested_state,
                    request_json, scheduler_result_json, state,
                    created_at, updated_at
                ) VALUES(
                    ?, 'assignment-1', 'failed', ?, ?,
                    'scheduler_acknowledged', ?, ?
                )
                """,
                (
                    request.transition_id, request.model_dump_json(),
                    json.dumps(scheduler_result), timestamp, timestamp,
                ),
            )
        result = await runtime.fail_assignment("assignment-1", request)
        self.assertEqual("failed", result["state"])
        self.assertEqual([], FakeClient.calls)

    async def test_outbox_replay_uses_stable_event_identity(self):
        runtime.publish_kernel_event = publish_succeeds
        request = self.request("transition-outbox")
        await runtime.fail_assignment("assignment-1", request)
        await runtime.fail_assignment("assignment-1", request)
        with runtime.connect() as db:
            outbox = db.execute(
                "SELECT * FROM employee_event_outbox"
            ).fetchall()
            events = db.execute(
                "SELECT * FROM employee_events WHERE event_id=?",
                ("assignment-terminal:transition-outbox",),
            ).fetchall()
        self.assertEqual(1, len(outbox))
        self.assertEqual(1, len(events))
        self.assertIsNotNone(outbox[0]["delivered_at"])

    async def test_existing_unique_job_index_migrates_non_destructively(self):
        original_path = runtime.DB_PATH
        with tempfile.TemporaryDirectory(prefix="leos-runtime-migration-") as root:
            runtime.DB_PATH = Path(root) / "legacy.db"
            db = sqlite3.connect(runtime.DB_PATH)
            db.executescript(
                """
                CREATE TABLE employee_assignments(
                    assignment_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL,
                    job_id TEXT NOT NULL, workflow_id TEXT, step_id TEXT,
                    capability_id TEXT, lease_id TEXT, state TEXT NOT NULL,
                    payload_json TEXT NOT NULL, result_json TEXT, error TEXT,
                    assigned_at TEXT NOT NULL, started_at TEXT,
                    completed_at TEXT, updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX idx_employee_assignment_job
                    ON employee_assignments(job_id);
                INSERT INTO employee_assignments VALUES(
                    'historical-a1', 'employee-1', 'job-1', NULL, NULL, NULL,
                    'lease-1', 'failed', '{}', NULL, 'failed', '2026-01-01',
                    NULL, '2026-01-01', '2026-01-01'
                );
                """
            )
            db.close()
            runtime.migrate()
            runtime.migrate()
            with runtime.connect() as migrated:
                historical = migrated.execute(
                    "SELECT * FROM employee_assignments "
                    "WHERE assignment_id='historical-a1'"
                ).fetchone()
                indexes = {
                    row["name"]
                    for row in migrated.execute(
                        "PRAGMA index_list(employee_assignments)"
                    ).fetchall()
                }
                migrated.execute(
                    """
                    INSERT INTO employee_assignments(
                        assignment_id, employee_id, job_id, lease_id, state,
                        payload_json, assigned_at, updated_at
                    ) VALUES(
                        'historical-a2', 'employee-1', 'job-1', 'lease-2',
                        'complete', '{}', '2026-01-02', '2026-01-02'
                    )
                    """
                )
            self.assertIsNotNone(historical)
            self.assertNotIn("idx_employee_assignment_job", indexes)
            self.assertIn("idx_employee_assignment_job_history", indexes)
        runtime.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()
