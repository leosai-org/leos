from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="leos-phase521-scheduler-")
os.environ["EXECUTION_SCHEDULER_DATA_DIR"] = _TEST_ROOT.name
os.environ["EXECUTION_SCHEDULER_AUTO_SCHEDULE"] = "false"
os.environ["EXECUTION_SCHEDULER_RESOURCE_ENFORCEMENT"] = "true"
os.environ["EXECUTION_SCHEDULER_RESOURCE_FAIL_CLOSED"] = "true"
os.environ["EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_ENFORCEMENT"] = "false"

from app import main as scheduler  # noqa: E402


class RuntimeResourceEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        scheduler.migrate()
        with scheduler.connect() as db:
            for table in (
                "scheduler_resource_history",
                "scheduler_events",
                "scheduler_leases",
                "scheduler_jobs",
                "scheduler_workers",
            ):
                db.execute(f"DELETE FROM {table}")

        self.active: dict[str, dict] = {}
        self.releases: list[tuple[str, str]] = []
        scheduler.emit = lambda *args, **kwargs: "event"
        scheduler.resource_request = (
            lambda method, path, payload=None, allow_not_found=False: {
                "ok": True
            }
        )
        scheduler.sync_resource_nodes = lambda workers: {
            "ok": True,
            "synced": len(workers),
            "errors": [],
        }

        def fetch(reservation_id: str):
            return self.active.get(reservation_id)

        def release(reservation_id: str, reason: str):
            self.releases.append((reservation_id, reason))
            reservation = self.active.get(reservation_id)
            if reservation is not None:
                reservation = {
                    **reservation,
                    "status": "released",
                    "release_reason": reason,
                }
                self.active[reservation_id] = reservation
            return reservation or {}

        scheduler.fetch_resource_reservation = fetch
        scheduler.release_resource_reservation = release

        scheduler.register_worker(
            scheduler.WorkerRegister(
                worker_id="worker-1",
                name="Worker 1",
                worker_type="employee-runtime",
                status="online",
                cpu_total=8,
                ram_mb_total=16384,
                gpu_count=1,
                vram_mb_total=12288,
                max_concurrent_jobs=4,
                labels={"runtime": "persistent-employee"},
                metadata={
                    "gpus": [
                        {
                            "uuid": "GPU-test-1",
                            "name": "Test GPU",
                            "vram_mb_total": 12288,
                        }
                    ]
                },
            )
        )

    def admitted_result(self, job, *, gpu_uuid=None):
        reservation_id = f"reservation-{job['job_id']}"
        reservation = {
            "contract_version": "leos.resource-reservation.v1",
            "reservation_id": reservation_id,
            "employee_id": job["employee_id"],
            "job_id": job["job_id"],
            "node_id": "worker-1",
            "status": "active",
            "priority_weight": 50,
            "preemptible": True,
            "resources": {
                "cpu_cores_min": 1,
                "memory_mb_min": 512,
                "gpu_required": gpu_uuid is not None,
                "vram_mb_min": 1024 if gpu_uuid else 0,
                "gpu_uuid_preferences": (
                    [gpu_uuid] if gpu_uuid else []
                ),
            },
            "gpu_uuid": gpu_uuid,
            "profile_name": "primary",
            "provider_preferences": [],
        }
        self.active[reservation_id] = reservation
        return {
            "ok": True,
            "reserved": True,
            "decision": {
                "contract_version": (
                    "leos.resource-admission-decision.v1"
                ),
                "employee_id": job["employee_id"],
                "job_id": job["job_id"],
                "decision": "admitted",
                "reason": "resources-available",
                "selected_node_id": "worker-1",
                "selected_gpu_uuid": gpu_uuid,
                "selected_profile": "primary",
            },
            "reservation": reservation,
        }

    def test_admission_is_required_before_lease_and_start(self) -> None:
        scheduler.reserve_resources = self.admitted_result
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-admitted",
                employee_id="employee-1",
                capability_id="content.write",
                cpu_required=1,
                ram_mb_required=512,
            )
        )

        tick = scheduler.schedule_tick()
        self.assertTrue(tick["ok"])
        self.assertEqual(tick["assignment_count"], 1)

        job = scheduler.get_job("job-admitted")["job"]
        self.assertEqual(job["state"], "leased")
        self.assertEqual(job["resource_state"], "active")
        self.assertTrue(job["resource_reservation_id"])
        self.assertEqual(job["resource_node_id"], "worker-1")

        started = scheduler.mark_job_running(
            "job-admitted",
            scheduler.JobStateUpdate(
                lease_id=job["lease_id"],
            ),
        )
        self.assertEqual(started["state"], "running")
        self.assertEqual(
            started["resource_reservation_id"],
            job["resource_reservation_id"],
        )

        completed = scheduler.complete_job(
            "job-admitted",
            scheduler.JobStateUpdate(
                lease_id=job["lease_id"],
                result={"artifact_id": "artifact-1"},
            ),
        )
        self.assertTrue(completed["resource_released"])

        final_job = scheduler.get_job("job-admitted")["job"]
        self.assertEqual(final_job["state"], "complete")
        self.assertEqual(final_job["resource_state"], "released")
        self.assertIn(
            (
                job["resource_reservation_id"],
                "job-complete",
            ),
            self.releases,
        )

        history = scheduler.list_resource_history(
            job_id="job-admitted",
            limit=100,
        )
        event_types = {
            event["event_type"]
            for event in history["events"]
        }
        self.assertIn(
            "resource_reservation_activated",
            event_types,
        )
        self.assertIn(
            "resource_reservation_start_validated",
            event_types,
        )
        self.assertIn(
            "resource_reservation_released",
            event_types,
        )

    def test_queued_decision_never_creates_scheduler_lease(self) -> None:
        scheduler.reserve_resources = lambda job: {
            "ok": False,
            "reserved": False,
            "decision": {
                "decision": "queued",
                "reason": "employee-concurrency-limit-reached",
            },
            "reservation": None,
        }
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-queued",
                employee_id="employee-1",
            )
        )

        tick = scheduler.schedule_tick()
        self.assertEqual(tick["assignment_count"], 0)
        self.assertEqual(
            tick["queued_by_resource_policy"],
            1,
        )

        job = scheduler.get_job("job-queued")["job"]
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["resource_state"], "queued")
        with scheduler.connect() as db:
            lease_count = db.execute(
                "SELECT COUNT(*) AS count FROM scheduler_leases"
            ).fetchone()["count"]
        self.assertEqual(lease_count, 0)

    def test_rejected_decision_is_terminal_and_unexecuted(self) -> None:
        scheduler.reserve_resources = lambda job: {
            "ok": False,
            "reserved": False,
            "decision": {
                "decision": "rejected",
                "reason": "employee-resource-profile-disabled",
            },
            "reservation": None,
        }
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-rejected",
                employee_id="employee-1",
            )
        )

        tick = scheduler.schedule_tick()
        self.assertEqual(tick["assignment_count"], 0)
        self.assertEqual(
            tick["rejected_by_resource_policy"],
            1,
        )
        job = scheduler.get_job("job-rejected")["job"]
        self.assertEqual(job["state"], "rejected")
        self.assertEqual(job["resource_state"], "rejected")

    def test_resource_service_failure_is_fail_closed(self) -> None:
        scheduler.sync_resource_nodes = lambda workers: {
            "ok": False,
            "synced": 0,
            "errors": [
                {
                    "worker_id": "worker-1",
                    "error": "resource service unavailable",
                }
            ],
        }
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-blocked",
                employee_id="employee-1",
            )
        )

        tick = scheduler.schedule_tick()
        self.assertFalse(tick["ok"])
        self.assertEqual(tick["assignment_count"], 0)
        job = scheduler.get_job("job-blocked")["job"]
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["resource_state"], "error")

    def test_start_is_blocked_when_reservation_is_missing(self) -> None:
        scheduler.reserve_resources = self.admitted_result
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-lost-reservation",
                employee_id="employee-1",
            )
        )
        scheduler.schedule_tick()
        job = scheduler.get_job("job-lost-reservation")["job"]
        self.active.pop(job["resource_reservation_id"])

        with self.assertRaises(HTTPException) as raised:
            scheduler.mark_job_running(
                "job-lost-reservation",
                scheduler.JobStateUpdate(
                    lease_id=job["lease_id"],
                ),
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_gpu_uuid_and_profile_are_persisted(self) -> None:
        scheduler.reserve_resources = (
            lambda job: self.admitted_result(
                job,
                gpu_uuid="GPU-test-1",
            )
        )
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-gpu",
                employee_id="employee-1",
                gpu_required=1,
                vram_mb_required=1024,
            )
        )
        tick = scheduler.schedule_tick()
        self.assertEqual(tick["assignment_count"], 1)
        job = scheduler.get_job("job-gpu")["job"]
        self.assertEqual(
            job["resource_gpu_uuid"],
            "GPU-test-1",
        )
        self.assertEqual(
            job["resource_profile_name"],
            "primary",
        )

    def test_migration_is_idempotent_and_state_survives(self) -> None:
        scheduler.reserve_resources = self.admitted_result
        scheduler.create_job(
            scheduler.JobCreate(
                job_id="job-durable",
                employee_id="employee-1",
            )
        )
        scheduler.schedule_tick()
        before = scheduler.get_job("job-durable")["job"]
        scheduler.migrate()
        after = scheduler.get_job("job-durable")["job"]
        self.assertEqual(
            after["resource_reservation_id"],
            before["resource_reservation_id"],
        )
        self.assertEqual(after["resource_state"], "active")


if __name__ == "__main__":
    unittest.main()
