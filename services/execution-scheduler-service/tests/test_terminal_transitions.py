from __future__ import annotations

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = tempfile.TemporaryDirectory(prefix="leos-scheduler-terminal-")
os.environ["EXECUTION_SCHEDULER_DATA_DIR"] = _ROOT.name
os.environ["EXECUTION_SCHEDULER_AUTO_SCHEDULE"] = "false"

from app import main as scheduler  # noqa: E402


class SchedulerTerminalTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        scheduler.DATA_DIR = Path(_ROOT.name)
        scheduler.DB_PATH = scheduler.DATA_DIR / "execution-scheduler.db"
        scheduler.migrate()
        with scheduler.connect() as db:
            for table in (
                "scheduler_terminal_transitions",
                "scheduler_events",
                "scheduler_leases",
                "scheduler_jobs",
            ):
                db.execute(f"DELETE FROM {table}")
            timestamp = scheduler.now()
            db.execute(
                """
                INSERT INTO scheduler_jobs(
                    job_id, job_type, state, max_attempts, attempt_count,
                    payload_json, required_labels_json, created_at,
                    queued_at, updated_at, lease_id,
                    resource_reservation_id, resource_state
                ) VALUES(
                    'job-1', 'workflow-step', 'running', 3, 1,
                    '{}', '{}', ?, ?, ?, 'lease-1',
                    'reservation-1', 'active'
                )
                """,
                (timestamp, timestamp, timestamp),
            )
            db.execute(
                """
                INSERT INTO scheduler_leases(
                    lease_id, job_id, worker_id, state, acquired_at,
                    expires_at
                ) VALUES(
                    'lease-1', 'job-1', 'runtime', 'active', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
        scheduler.emit = lambda *args, **kwargs: "event"
        self.release_calls: list[tuple[str, str, str]] = []
        scheduler.release_job_resources = self.release_resources

    def release_resources(
        self, job_id: str, reservation_id: str, reason: str
    ) -> bool:
        self.release_calls.append((job_id, reservation_id, reason))
        return True

    def test_cancel_is_terminal_and_idempotent(self) -> None:
        request = scheduler.JobCancelRequest(
            transition_id="transition-cancel-1",
            lease_id="lease-1",
            reason="user_cancelled",
        )
        first = scheduler.cancel_job("job-1", request)
        second = scheduler.cancel_job("job-1", request)
        self.assertEqual("cancelled", first["state"])
        self.assertEqual(first, second)
        self.assertEqual(1, len(self.release_calls))
        self.assertEqual(
            "cancelled", scheduler.get_job("job-1")["job"]["state"]
        )

    def test_failure_requeues_without_reusing_transition(self) -> None:
        request = scheduler.JobStateUpdate(
            transition_id="transition-fail-1",
            lease_id="lease-1",
            error="cognitive failure",
        )
        first = scheduler.fail_job("job-1", request)
        second = scheduler.fail_job("job-1", request)
        self.assertEqual("queued", first["state"])
        self.assertTrue(first["retry"])
        self.assertEqual(first, second)
        self.assertEqual(1, len(self.release_calls))

    def test_transition_identity_conflict_is_rejected(self) -> None:
        scheduler.cancel_job(
            "job-1",
            scheduler.JobCancelRequest(
                transition_id="transition-1",
                lease_id="lease-1",
                reason="cancel",
            ),
        )
        with self.assertRaises(Exception):
            scheduler.fail_job(
                "job-1",
                scheduler.JobStateUpdate(
                    transition_id="transition-1", error="different"
                ),
            )

    def test_requested_failure_recovers_after_job_transition(self) -> None:
        request = scheduler.JobStateUpdate(
            transition_id="transition-recover",
            error="failure",
        )
        with scheduler.connect() as db:
            timestamp = scheduler.now()
            result = {
                "ok": True, "job_id": "job-1", "state": "queued",
                "retry": True, "lease_id": "lease-1",
                "resource_reservation_id": "reservation-1",
                "resource_released": True,
            }
            db.execute(
                """
                INSERT INTO scheduler_terminal_transitions(
                    transition_id, job_id, lease_id, requested_state,
                    request_json, result_json, state, created_at, updated_at
                ) VALUES(?, 'job-1', 'lease-1', 'failed', ?, ?, 'applied', ?, ?)
                """,
                (
                    request.transition_id,
                    request.model_dump_json(),
                    __import__("json").dumps(result),
                    timestamp,
                    timestamp,
                ),
            )
            db.execute(
                "UPDATE scheduler_jobs SET state='queued', "
                "resource_state='released' WHERE job_id='job-1'"
            )
        recovered = scheduler.fail_job("job-1", request)
        self.assertEqual("queued", recovered["state"])
        self.assertTrue(recovered["retry"])

    def test_complete_uses_journal_and_replays(self) -> None:
        request = scheduler.JobStateUpdate(
            transition_id="transition-complete",
            lease_id="lease-1",
            result={"artifact_id": "artifact-1"},
        )
        first = scheduler.complete_job("job-1", request)
        second = scheduler.complete_job("job-1", request)
        self.assertEqual("complete", first["state"])
        self.assertEqual(first, second)
        with scheduler.connect() as db:
            journal = db.execute(
                "SELECT * FROM scheduler_terminal_transitions "
                "WHERE transition_id=?",
                (request.transition_id,),
            ).fetchone()
        self.assertEqual("completed", journal["state"])

    def test_stale_failure_cannot_mutate_new_lease(self) -> None:
        with scheduler.connect() as db:
            db.execute(
                "UPDATE scheduler_jobs SET lease_id='lease-2' "
                "WHERE job_id='job-1'"
            )
        with self.assertRaises(Exception):
            scheduler.fail_job(
                "job-1",
                scheduler.JobStateUpdate(
                    transition_id="stale", lease_id="lease-1", error="late"
                ),
            )
        self.assertEqual(
            "running", scheduler.get_job("job-1")["job"]["state"]
        )

    def test_fresh_failure_cannot_reapply_to_requeued_job(self) -> None:
        scheduler.fail_job(
            "job-1",
            scheduler.JobStateUpdate(
                transition_id="first", lease_id="lease-1", error="first"
            ),
        )
        with self.assertRaises(Exception):
            scheduler.fail_job(
                "job-1",
                scheduler.JobStateUpdate(
                    transition_id="second", lease_id="lease-1", error="again"
                ),
            )

    def test_concurrent_identical_transition_releases_once(self) -> None:
        request = scheduler.JobStateUpdate(
            transition_id="concurrent-same",
            lease_id="lease-1",
            result={"ok": True},
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: scheduler.complete_job("job-1", request),
                    range(2),
                )
            )
        self.assertEqual(results[0], results[1])
        self.assertEqual(1, len(self.release_calls))

    def test_concurrent_complete_vs_fail_has_one_winner(self) -> None:
        operations = (
            lambda: scheduler.complete_job(
                "job-1",
                scheduler.JobStateUpdate(
                    transition_id="race-complete",
                    lease_id="lease-1",
                    result={"ok": True},
                ),
            ),
            lambda: scheduler.fail_job(
                "job-1",
                scheduler.JobStateUpdate(
                    transition_id="race-fail",
                    lease_id="lease-1",
                    error="failed",
                ),
            ),
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(operation) for operation in operations]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("result", future.result()))
            except Exception as exc:
                outcomes.append(("error", exc))
        self.assertEqual(1, sum(kind == "result" for kind, _ in outcomes))
        self.assertEqual(1, sum(kind == "error" for kind, _ in outcomes))
        self.assertEqual(1, len(self.release_calls))


if __name__ == "__main__":
    unittest.main()
