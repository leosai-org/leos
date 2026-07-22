from __future__ import annotations

import json
import os
import tempfile
import unittest

from fastapi import HTTPException

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="leos-phase521-runtime-")
os.environ["PERSISTENT_EMPLOYEE_RUNTIME_DATA_DIR"] = _TEST_ROOT.name
os.environ["EMPLOYEE_RUNTIME_AUTO_POLL_SCHEDULER"] = "false"

from app import main as runtime  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeAsyncClient:
    response = FakeResponse(200, {"ok": True})

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return self.response


async def no_publish(*args, **kwargs):
    return None


class RuntimeResourceGateTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        runtime.migrate()
        with runtime.connect() as db:
            for table in (
                "employee_events",
                "employee_assignments",
                "employee_memory",
                "employee_messages",
                "employees",
            ):
                db.execute(f"DELETE FROM {table}")
            timestamp = runtime.now()
            db.execute(
                """
                INSERT INTO employees (
                    employee_id, name, role, status,
                    runtime_state, profile_json,
                    permissions_json, capabilities_json,
                    metadata_json, created_at, updated_at
                ) VALUES (
                    'employee-1', 'Employee 1', 'writer',
                    'online', 'assigned', '{}', '{}', '[]',
                    '{}', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO employee_assignments (
                    assignment_id, employee_id, job_id,
                    capability_id, lease_id, state,
                    payload_json, assigned_at, updated_at,
                    resource_reservation_id, resource_node_id,
                    resource_gpu_uuid, resource_profile_name,
                    resource_decision_json, resource_state
                ) VALUES (
                    'assignment-1', 'employee-1', 'job-1',
                    'content.write', 'lease-1', 'assigned',
                    '{}', ?, ?,
                    'reservation-1', 'worker-1', 'GPU-test-1',
                    'primary', ?, 'active'
                )
                """,
                (
                    timestamp,
                    timestamp,
                    json.dumps(
                        {
                            "decision": "admitted",
                            "selected_node_id": "worker-1",
                            "selected_gpu_uuid": "GPU-test-1",
                        }
                    ),
                ),
            )

        self.original_client = runtime.httpx.AsyncClient
        self.original_publish = runtime.publish_kernel_event
        runtime.httpx.AsyncClient = FakeAsyncClient
        runtime.publish_kernel_event = no_publish

    def tearDown(self) -> None:
        runtime.httpx.AsyncClient = self.original_client
        runtime.publish_kernel_event = self.original_publish

    def assignment_state(self) -> str:
        with runtime.connect() as db:
            return db.execute(
                """
                SELECT state
                FROM employee_assignments
                WHERE assignment_id='assignment-1'
                """
            ).fetchone()["state"]

    async def test_start_remains_assigned_when_scheduler_blocks(self):
        FakeAsyncClient.response = FakeResponse(
            409,
            {
                "detail": {
                    "message": (
                        "Job cannot start without an active "
                        "resource reservation."
                    )
                }
            },
        )
        with self.assertRaises(HTTPException) as raised:
            await runtime.start_assignment("assignment-1")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.assignment_state(), "assigned")

    async def test_start_succeeds_only_after_scheduler_validation(self):
        FakeAsyncClient.response = FakeResponse(
            200,
            {
                "ok": True,
                "state": "running",
                "resource_reservation_id": "reservation-1",
            },
        )
        result = await runtime.start_assignment("assignment-1")
        self.assertEqual(result["state"], "running")
        self.assertEqual(
            result["resource_reservation_id"],
            "reservation-1",
        )
        self.assertEqual(self.assignment_state(), "running")

    async def test_completion_remains_running_when_release_fails(self):
        with runtime.connect() as db:
            db.execute(
                """
                UPDATE employee_assignments
                SET state='running'
                WHERE assignment_id='assignment-1'
                """
            )
        FakeAsyncClient.response = FakeResponse(
            503,
            {"detail": "resource release unavailable"},
        )
        with self.assertRaises(HTTPException):
            await runtime.complete_assignment(
                "assignment-1",
                runtime.AssignmentStateUpdate(
                    result={"ok": True}
                ),
            )
        self.assertEqual(self.assignment_state(), "running")

    async def test_completion_persists_released_resource_state(self):
        with runtime.connect() as db:
            db.execute(
                """
                UPDATE employee_assignments
                SET state='running'
                WHERE assignment_id='assignment-1'
                """
            )
        FakeAsyncClient.response = FakeResponse(
            200,
            {
                "ok": True,
                "state": "complete",
                "resource_released": True,
            },
        )
        result = await runtime.complete_assignment(
            "assignment-1",
            runtime.AssignmentStateUpdate(
                result={"artifact_id": "artifact-1"}
            ),
        )
        self.assertEqual(result["state"], "complete")
        self.assertTrue(result["resource_released"])
        with runtime.connect() as db:
            row = db.execute(
                """
                SELECT state, resource_state
                FROM employee_assignments
                WHERE assignment_id='assignment-1'
                """
            ).fetchone()
        self.assertEqual(row["state"], "complete")
        self.assertEqual(row["resource_state"], "released")


if __name__ == "__main__":
    unittest.main()
