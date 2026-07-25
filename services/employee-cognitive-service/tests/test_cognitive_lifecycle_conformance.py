from __future__ import annotations

import json
import asyncio
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import HTTPException

_ROOT = tempfile.TemporaryDirectory(prefix="leos-cognitive-test-")
os.environ["EMPLOYEE_COGNITIVE_DATA_DIR"] = _ROOT.name
os.environ["EMPLOYEE_COGNITIVE_AUTO_RUN"] = "false"
os.environ["LEOS_CONTRACT_ROOT"] = str(
    Path(__file__).resolve().parents[3] / "contracts"
)

from app import main as cognitive  # noqa: E402


class CognitiveLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        cognitive.DATA_DIR = Path(_ROOT.name)
        cognitive.DB_PATH = cognitive.DATA_DIR / "cognitive.db"
        cognitive.BACKOFF_SECONDS = 0
        cognitive.migrate()
        with cognitive.connect() as db:
            for table in (
                "cognitive_observations",
                "cognitive_attempts",
                "cognitive_runs",
            ):
                db.execute(f"DELETE FROM {table}")
        self.calls: list[tuple[str, str, dict | None]] = []
        self.status = "SUCCESS"
        self.fail_terminal_once = False
        self.terminal_conflict = False
        self.existing_execution = None
        self.runtime_assignment_state = "assigned"
        self.lose_start_response = False
        self.dispatch_entered = None
        self.dispatch_release = None
        self.original_request = cognitive.request_json
        cognitive.request_json = self.request
        self.assignment = {
            "assignment_id": "assignment-1",
            "employee_id": "employee-1",
            "job_id": "job-1",
            "lease_id": "lease-1",
            "workflow_id": "workflow-1",
            "step_id": "step-1",
            "capability_id": "content.write",
            "state": "assigned",
            "payload": {
                "instruction": "Produce the governed artifact.",
                "policy": {
                    "effective_intelligence_policy_ref": {
                        "authority": "employee-config",
                        "reference_id": "policy-1",
                        "revision": "3",
                    }
                },
            },
        }

    def tearDown(self) -> None:
        cognitive.request_json = self.original_request

    async def request(self, method, url, payload=None):
        self.calls.append((method, url, payload))
        if url.endswith("/employees/employee-1"):
            return 200, {"employee": {"employee_id": "employee-1"}}
        if "/assignments/" in url and url.endswith("/start"):
            self.runtime_assignment_state = "running"
            if self.lose_start_response:
                self.lose_start_response = False
                raise RuntimeError("start response lost")
            return 200, {"ok": True, "state": "running"}
        if "/assignments/" in url and any(
            url.endswith(f"/{op}") for op in ("complete", "fail", "cancel")
        ):
            if self.terminal_conflict:
                return 409, {"detail": "terminal_transition_conflict"}
            if self.fail_terminal_once:
                self.fail_terminal_once = False
                raise RuntimeError("response lost")
            return 200, {
                "ok": True,
                "state": url.rsplit("/", 1)[-1],
                "resource_released": True,
            }
        if url.endswith("/execute"):
            if self.dispatch_entered is not None:
                self.dispatch_entered.set()
                await self.dispatch_release.wait()
            return 200, self.result(payload)
        if "/executions/" in url:
            if self.existing_execution is not None:
                return 200, {"ok": True, "execution": {
                    "result": self.existing_execution
                }}
            return 404, {"detail": "not found"}
        if "/assignments?" in url:
            return 200, {"assignments": [{
                **self.assignment,
                "state": self.runtime_assignment_state,
            }]}
        raise AssertionError(f"unexpected call: {method} {url}")

    def result(self, request):
        execution_id = request["execution_id"]
        trace = dict(request["trace"])
        resolution_id = f"resolution-{execution_id}"
        trace["resolution_id"] = resolution_id
        base = {
            "contract_version": "leos.execution-result.v1",
            "execution_id": execution_id,
            "status": self.status,
            "capability_id": request["capability_id"],
            "resolution_ref": {
                "authority": "capability-manager",
                "reference_id": resolution_id,
                "revision": "1",
            },
            "attempt_summary": {"attempt_count": 0, "attempts": []},
            "correlation": trace,
            "started_at": "2026-07-24T18:00:00Z",
            "completed_at": "2026-07-24T18:00:01Z",
        }
        if self.status == "SUCCESS":
            attempt_id = f"invocation-{execution_id}"
            base["authorized_target"] = {"provider_id": "provider-1"}
            base["normalized_result"] = {"ok": True}
            base["attempt_summary"] = {
                "attempt_count": 1,
                "idempotency_key": execution_id,
                "attempts": [{
                    "invocation_attempt_id": attempt_id,
                    "attempt_number": 1,
                    "status": "SUCCESS",
                    "started_at": "2026-07-24T18:00:00Z",
                    "completed_at": "2026-07-24T18:00:01Z",
                }],
            }
            base["correlation"]["invocation_attempt_id"] = attempt_id
        elif self.status == "APPROVAL_PENDING":
            base["approval_requirement_ref"] = {
                "authority": "approval-authority",
                "reference_id": "approval-needed-1",
            }
        elif self.status in {
            "REJECTED", "PROVIDER_ERROR", "TRANSPORT_ERROR", "AMBIGUOUS_OUTCOME"
        }:
            base["error"] = {
                "code": self.status.lower(),
                "message": "governed result",
                "retryable_same_target": self.status in {
                    "PROVIDER_ERROR", "TRANSPORT_ERROR"
                },
                "remote_side_effect_possible": self.status == "AMBIGUOUS_OUTCOME",
            }
            if self.status != "REJECTED":
                attempt_id = f"invocation-{execution_id}"
                base["authorized_target"] = {"provider_id": "provider-1"}
                base["attempt_summary"] = {
                    "attempt_count": 1,
                    "idempotency_key": execution_id,
                    "attempts": [{
                        "invocation_attempt_id": attempt_id,
                        "attempt_number": 1,
                        "status": self.status,
                        "started_at": "2026-07-24T18:00:00Z",
                        "completed_at": "2026-07-24T18:00:01Z",
                    }],
                }
                base["correlation"]["invocation_attempt_id"] = attempt_id
        return base

    def create(self):
        return cognitive.create_run_from_assignment(self.assignment)

    async def execute(self):
        return await cognitive.execute_run(self.create()["cognitive_run_id"])

    def calls_to(self, suffix):
        return [call for call in self.calls if call[1].endswith(suffix)]

    def reset_case(self):
        with cognitive.connect() as db:
            for table in (
                "cognitive_observations",
                "cognitive_attempts",
                "cognitive_runs",
            ):
                db.execute(f"DELETE FROM {table}")
        self.calls = []

    def test_service_import_health_and_run_creation(self):
        run = self.create()
        self.assertEqual("run_created", run["state"])
        self.assertEqual("employee-cognitive-service", cognitive.health()["service"])
        self.assertEqual(run["cognitive_run_id"], self.create()["cognitive_run_id"])

    async def test_success_uses_canonical_dispatcher_and_runtime_complete(self):
        result = await self.execute()
        self.assertEqual("completed", result["state"])
        dispatcher = self.calls_to("/execute")[0][2]
        self.assertEqual("leos.execution.v1", dispatcher["contract_version"])
        self.assertEqual("employee", dispatcher["requester"]["type"])
        self.assertEqual("assignment-1", dispatcher["trace"]["assignment_id"])
        self.assertEqual(
            "Produce the governed artifact.",
            dispatcher["input"]["instruction"],
        )
        self.assertEqual(
            "policy-1",
            dispatcher["policy"]["effective_intelligence_policy_ref"][
                "reference_id"
            ],
        )
        self.assertEqual(1, len(self.calls_to("/start")))
        self.assertEqual(1, len(self.calls_to("/complete")))
        self.assertFalse(any("scheduler" in call[1] for call in self.calls))

    async def test_provider_error_requires_decision_without_replay(self):
        self.status = "PROVIDER_ERROR"
        first = await self.execute()
        self.assertEqual("waiting", first["state"])
        self.status = "SUCCESS"
        second = await cognitive.execute_run(first["cognitive_run_id"])
        self.assertEqual("waiting", second["state"])
        self.assertEqual(1, len(self.calls_to("/start")))
        with cognitive.connect() as db:
            attempts = db.execute(
                "SELECT * FROM cognitive_attempts ORDER BY attempt_number"
            ).fetchall()
        self.assertEqual([1], [row["attempt_number"] for row in attempts])
        self.assertEqual(1, len(self.calls_to("/execute")))

    async def test_waiting_results_do_not_busy_loop(self):
        for status, expected in (
            ("APPROVAL_PENDING", "approval_pending"),
            ("GOVERNED_ORDER_REQUIRED", "order_required"),
        ):
            with self.subTest(status=status):
                self.reset_case()
                self.status = status
                first = await self.execute()
                second = await cognitive.execute_run(first["cognitive_run_id"])
                self.assertEqual(expected, first["state"])
                self.assertFalse(second["changed"])
                self.assertEqual(1, len(self.calls_to("/execute")))

    async def test_no_eligible_and_rejected_fail_truthfully(self):
        for status in ("NO_ELIGIBLE_PROVIDER", "REJECTED"):
            with self.subTest(status=status):
                self.reset_case()
                self.status = status
                result = await self.execute()
                self.assertEqual("failed", result["state"])
                self.assertEqual(1, len(self.calls_to("/fail")))

    async def test_transport_and_provider_errors_require_cognitive_decision(self):
        for status in ("PROVIDER_ERROR", "TRANSPORT_ERROR"):
            with self.subTest(status=status):
                self.reset_case()
                self.status = status
                result = await self.execute()
                self.assertEqual("waiting", result["state"])
                self.assertEqual(0, len(self.calls_to("/fail")))

    async def assert_result_state(self, status, state):
        self.status = status
        result = await self.execute()
        self.assertEqual(state, result["state"])

    async def test_approval_pending_mapping(self):
        await self.assert_result_state("APPROVAL_PENDING", "approval_pending")

    async def test_governed_order_required_mapping(self):
        await self.assert_result_state(
            "GOVERNED_ORDER_REQUIRED", "order_required"
        )

    async def test_no_eligible_provider_mapping(self):
        await self.assert_result_state("NO_ELIGIBLE_PROVIDER", "failed")

    async def test_rejected_mapping(self):
        await self.assert_result_state("REJECTED", "failed")

    async def test_provider_error_mapping(self):
        await self.assert_result_state("PROVIDER_ERROR", "waiting")

    async def test_transport_error_mapping(self):
        await self.assert_result_state("TRANSPORT_ERROR", "waiting")

    async def test_ambiguous_outcome_never_replays(self):
        self.status = "AMBIGUOUS_OUTCOME"
        first = await self.execute()
        second = await cognitive.execute_run(first["cognitive_run_id"])
        self.assertEqual("waiting", first["state"])
        self.assertFalse(second["changed"])
        self.assertEqual(1, len(self.calls_to("/execute")))

    async def test_terminal_response_loss_reuses_same_transition(self):
        self.fail_terminal_once = True
        with self.assertRaises(RuntimeError):
            await self.execute()
        run = cognitive.get_run_row(self.create()["cognitive_run_id"])
        transition_id = run["terminal_transition_id"]
        recovered = await cognitive.execute_run(run["cognitive_run_id"])
        terminal_calls = self.calls_to("/complete")
        self.assertEqual(2, len(terminal_calls))
        self.assertEqual(
            transition_id, terminal_calls[0][2]["transition_id"]
        )
        self.assertEqual(
            terminal_calls[0][2], terminal_calls[1][2]
        )
        self.assertEqual("completed", recovered["state"])
        self.assertEqual(
            "completed",
            cognitive.get_run_row(run["cognitive_run_id"])["state"],
        )

    async def test_terminal_conflict_enters_stable_reconciliation_wait(self):
        self.terminal_conflict = True
        with self.assertRaises(HTTPException):
            await self.execute()
        run = self.create()
        stored = cognitive.get_run_row(run["cognitive_run_id"])
        self.assertEqual("waiting", stored["state"])
        terminal_count = len(self.calls_to("/complete"))
        replay = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("waiting", replay["state"])
        self.assertEqual(terminal_count, len(self.calls_to("/complete")))

    async def test_restart_reconciles_dispatcher_before_reinvocation(self):
        run = self.create()
        context = {"employee": {}, "assignment": self.assignment}
        token = cognitive.claim_run(run["cognitive_run_id"])
        attempt = cognitive.next_attempt(run, context, token)
        cognitive.release_run_claim(run["cognitive_run_id"], token)
        with cognitive.connect() as db:
            db.execute(
                "UPDATE cognitive_attempts SET state='dispatched' "
                "WHERE cognitive_attempt_id=?",
                (attempt["cognitive_attempt_id"],),
            )
            db.execute(
                "UPDATE cognitive_runs SET assignment_started_at=?, "
                "state='running' WHERE cognitive_run_id=?",
                (cognitive.now(), run["cognitive_run_id"]),
            )
        self.existing_execution = self.result(attempt["request"])
        result = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("completed", result["state"])
        self.assertEqual(0, len(self.calls_to("/execute")))
        self.assertEqual(1, len([
            call for call in self.calls if "/executions/" in call[1]
        ]))

    async def test_missing_inflight_execution_waits_without_new_id(self):
        run = self.create()
        token = cognitive.claim_run(run["cognitive_run_id"])
        attempt = cognitive.next_attempt(
            run, {"employee": {}, "assignment": self.assignment}, token
        )
        cognitive.release_run_claim(run["cognitive_run_id"], token)
        with cognitive.connect() as db:
            db.execute(
                "UPDATE cognitive_attempts SET state='dispatched' "
                "WHERE cognitive_attempt_id=?",
                (attempt["cognitive_attempt_id"],),
            )
            db.execute(
                "UPDATE cognitive_runs SET assignment_started_at=?, "
                "state='running' WHERE cognitive_run_id=?",
                (cognitive.now(), run["cognitive_run_id"]),
            )
        result = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("waiting", result["state"])
        self.assertEqual(attempt["execution_id"], result["execution_id"])
        self.assertEqual(0, len(self.calls_to("/execute")))

    async def test_cancellation_uses_runtime_only_and_is_durable(self):
        run = self.create()
        result = await cognitive.cancel_run(run["cognitive_run_id"], "stop")
        cognitive.migrate()
        reopened = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("cancelled", result["state"])
        self.assertEqual("cancelled", reopened["state"])
        self.assertEqual("cancelled", cognitive.get_run_row(run["cognitive_run_id"])["state"])
        self.assertEqual(1, len(self.calls_to("/cancel")))
        self.assertFalse(any("scheduler" in call[1] for call in self.calls))

    async def test_failed_a1_never_restarts_when_a2_exists(self):
        self.status = "NO_ELIGIBLE_PROVIDER"
        a1 = await self.execute()
        self.assignment = {
            **self.assignment,
            "assignment_id": "assignment-2",
            "lease_id": "lease-2",
        }
        a2 = self.create()
        self.assertEqual("failed", a1["state"])
        self.assertNotEqual(a1["cognitive_run_id"], a2["cognitive_run_id"])
        await cognitive.execute_run(a1["cognitive_run_id"])
        self.assertEqual(1, len(self.calls_to("/start")))

    async def test_persistence_reopen_preserves_lineage(self):
        await self.execute()
        cognitive.migrate()
        run = cognitive.get_run(self.create()["cognitive_run_id"])
        self.assertEqual("completed", run["run"]["state"])
        self.assertEqual(1, len(run["attempts"]))
        self.assertIsNotNone(run["attempts"][0]["execution_result_json"])

    def test_legitimate_secret_named_business_input_is_not_over_redacted(self):
        assignment = {
            **self.assignment,
            "assignment_id": "assignment-business-token",
            "payload": {"token": "business-domain-token"},
        }
        run = cognitive.create_run_from_assignment(assignment)
        token = cognitive.claim_run(run["cognitive_run_id"])
        request = cognitive.next_attempt(
            run, {"employee": {}, "assignment": assignment}, token
        )["request"]
        cognitive.release_run_claim(run["cognitive_run_id"], token)
        self.assertEqual(
            "business-domain-token", request["input"]["token"]
        )

    async def test_discovery_is_idempotent(self):
        first = await cognitive.discover_assignments()
        second = await cognitive.discover_assignments()
        self.assertEqual(1, first["discovered_count"])
        self.assertEqual(0, second["discovered_count"])

    async def test_assignment_start_response_loss_reconciles_running_state(self):
        run = self.create()
        self.lose_start_response = True
        first = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("run_created", first["state"])
        cognitive.migrate()
        second = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("completed", second["state"])
        self.assertEqual(1, len(self.calls_to("/start")))

    async def test_observed_unapplied_result_is_applied_after_restart(self):
        run = self.create()
        token = cognitive.claim_run(run["cognitive_run_id"])
        context = {"employee": {}, "assignment": self.assignment}
        attempt = cognitive.next_attempt(run, context, token)
        cognitive.release_run_claim(run["cognitive_run_id"], token)
        result = self.result(attempt["request"])
        cognitive.persist_observation(run["cognitive_run_id"], attempt, result)
        with cognitive.connect() as db:
            db.execute(
                "UPDATE cognitive_runs SET assignment_started_at=?, "
                "state='running' WHERE cognitive_run_id=?",
                (cognitive.now(), run["cognitive_run_id"]),
            )
        cognitive.migrate()
        recovered = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("completed", recovered["state"])
        self.assertEqual(0, len(self.calls_to("/execute")))
        with cognitive.connect() as db:
            stored = db.execute(
                "SELECT result_applied_at FROM cognitive_attempts"
            ).fetchone()
        self.assertIsNotNone(stored["result_applied_at"])

    async def test_terminal_acknowledgement_finalizes_before_execution(self):
        run = self.create()
        with cognitive.connect() as db:
            db.execute(
                "UPDATE cognitive_runs SET state='running', "
                "terminal_transition_id='terminal-1', "
                "terminal_operation='complete', "
                "terminal_request_json='{}', "
                "terminal_result_json='{\"ok\": true}' "
                "WHERE cognitive_run_id=?",
                (run["cognitive_run_id"],),
            )
        cognitive.migrate()
        recovered = await cognitive.execute_run(run["cognitive_run_id"])
        self.assertEqual("completed", recovered["state"])
        self.assertEqual(0, len(self.calls_to("/execute")))

    async def test_ambiguous_wait_survives_reopen_and_resume_is_rejected(self):
        self.status = "AMBIGUOUS_OUTCOME"
        result = await self.execute()
        cognitive.migrate()
        run = cognitive.get_run_row(result["cognitive_run_id"])
        self.assertEqual("waiting", run["state"])
        with self.assertRaises(HTTPException):
            await cognitive.resume_run(
                result["cognitive_run_id"],
                cognitive.ResumeRequest(reason="try again"),
            )
        replay = await cognitive.execute_run(result["cognitive_run_id"])
        self.assertFalse(replay["changed"])
        self.assertEqual(1, len(self.calls_to("/execute")))

    async def test_approval_and_order_waits_reject_generic_resume(self):
        for status in ("APPROVAL_PENDING", "GOVERNED_ORDER_REQUIRED"):
            with self.subTest(status=status):
                self.reset_case()
                self.runtime_assignment_state = "assigned"
                self.status = status
                result = await self.execute()
                cognitive.migrate()
                with self.assertRaises(HTTPException):
                    await cognitive.resume_run(
                        result["cognitive_run_id"],
                        cognitive.ResumeRequest(reason="no evidence"),
                    )
                tick = await cognitive.tick()
                self.assertEqual(0, tick["selected_count"])
                self.assertEqual(1, len(self.calls_to("/execute")))

    def test_simultaneous_assignment_creation_has_one_run(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    cognitive.create_run_from_assignment, self.assignment
                )
                for _ in range(2)
            ]
        rows = [future.result() for future in futures]
        self.assertEqual(
            rows[0]["cognitive_run_id"], rows[1]["cognitive_run_id"]
        )
        with cognitive.connect() as db:
            count = db.execute(
                "SELECT COUNT(*) c FROM cognitive_runs"
            ).fetchone()["c"]
        self.assertEqual(1, count)

    async def test_simultaneous_execute_has_one_dispatch_owner(self):
        run = self.create()
        self.dispatch_entered = asyncio.Event()
        self.dispatch_release = asyncio.Event()
        first = asyncio.create_task(
            cognitive.execute_run(run["cognitive_run_id"])
        )
        await self.dispatch_entered.wait()
        second = await asyncio.gather(
            cognitive.execute_run(run["cognitive_run_id"]),
            return_exceptions=True,
        )
        self.dispatch_release.set()
        await first
        self.assertIsInstance(second[0], HTTPException)
        self.assertEqual(1, len(self.calls_to("/execute")))
        self.assertEqual(1, len(self.calls_to("/start")))

    async def test_cancellation_fences_inflight_execution(self):
        run = self.create()
        self.dispatch_entered = asyncio.Event()
        self.dispatch_release = asyncio.Event()
        execution = asyncio.create_task(
            cognitive.execute_run(run["cognitive_run_id"])
        )
        await self.dispatch_entered.wait()
        cancellation = await cognitive.cancel_run(
            run["cognitive_run_id"], "operator cancelled"
        )
        self.assertEqual("cancellation_pending", cancellation["state"])
        self.dispatch_release.set()
        result = await execution
        self.assertEqual("cancelled", result["state"])
        self.assertEqual(
            "cancelled",
            cognitive.get_run_row(run["cognitive_run_id"])["state"],
        )
        self.assertEqual(1, len(self.calls_to("/cancel")))
        self.assertEqual(1, len(self.calls_to("/execute")))


if __name__ == "__main__":
    unittest.main()
