from __future__ import annotations

import os
import tempfile
import unittest

from fastapi import HTTPException

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="leos-phase522-scheduler-")
os.environ["EXECUTION_SCHEDULER_DATA_DIR"] = _TEST_ROOT.name
os.environ["EXECUTION_SCHEDULER_AUTO_SCHEDULE"] = "false"
os.environ["EXECUTION_SCHEDULER_RESOURCE_ENFORCEMENT"] = "true"
os.environ["EXECUTION_SCHEDULER_RESOURCE_FAIL_CLOSED"] = "true"
os.environ["EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_ENFORCEMENT"] = "true"
os.environ["EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_FAIL_CLOSED"] = "true"

from app import main as scheduler  # noqa: E402


class EmployeeLifecycleSchedulerTests(unittest.TestCase):
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
        scheduler.emit = lambda *args, **kwargs: "event"
        scheduler.sync_resource_nodes = lambda workers: {
            "ok": True,
            "synced": len(workers),
            "errors": [],
        }
        scheduler.register_worker(
            scheduler.WorkerRegister(
                worker_id="worker-1",
                name="Worker 1",
                worker_type="employee-runtime",
                status="online",
                cpu_total=8,
                ram_mb_total=16384,
                max_concurrent_jobs=4,
                labels={"runtime": "persistent-employee"},
            )
        )
        self.active = {}

        def fetch(reservation_id):
            return self.active.get(reservation_id)

        scheduler.fetch_resource_reservation = fetch
        scheduler.release_resource_reservation = lambda reservation_id, reason: {
            **self.active.get(reservation_id, {}),
            "status": "released",
            "release_reason": reason,
        }

    def eligible(self, job):
        return {
            "ok": True,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": job["employee_id"],
            "eligible": True,
            "decision": "eligible",
            "reasons": [],
            "lifecycle_status": "active",
        }

    def admitted(self, job):
        reservation_id = f"reservation-{job['job_id']}"
        reservation = {
            "reservation_id": reservation_id,
            "employee_id": job["employee_id"],
            "job_id": job["job_id"],
            "node_id": "worker-1",
            "status": "active",
            "resources": {
                "cpu_cores_min": 1,
                "memory_mb_min": 512,
                "gpu_required": False,
                "vram_mb_min": 0,
                "gpu_uuid_preferences": [],
            },
            "gpu_uuid": None,
            "profile_name": "primary",
            "provider_preferences": [],
        }
        self.active[reservation_id] = reservation
        return {
            "ok": True,
            "reserved": True,
            "decision": {
                "decision": "admitted",
                "reason": "resources-available",
                "selected_node_id": "worker-1",
                "selected_profile": "primary",
            },
            "reservation": reservation,
        }

    def create(self, job_id):
        scheduler.create_job(
            scheduler.JobCreate(
                job_id=job_id,
                employee_id="employee-1",
                capability_id="content.write",
            )
        )

    def test_paused_employee_remains_queued_without_resource_call(self):
        self.create("job-paused")
        scheduler.employee_eligibility = lambda job: {
            "ok": True,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": job["employee_id"],
            "eligible": False,
            "decision": "queued",
            "reasons": ["employee-lifecycle-paused"],
        }
        called = []
        scheduler.reserve_resources = lambda job: called.append(job) or self.admitted(job)
        tick = scheduler.schedule_tick()
        self.assertEqual(tick["queued_by_employee_policy"], 1)
        self.assertEqual(tick["assignment_count"], 0)
        self.assertEqual(called, [])
        job = scheduler.get_job("job-paused")["job"]
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["employee_state"], "queued")

    def test_disabled_employee_is_rejected_without_resource_call(self):
        self.create("job-disabled")
        scheduler.employee_eligibility = lambda job: {
            "ok": True,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": job["employee_id"],
            "eligible": False,
            "decision": "rejected",
            "reasons": ["employee-lifecycle-disabled"],
        }
        called = []
        scheduler.reserve_resources = lambda job: called.append(job) or self.admitted(job)
        tick = scheduler.schedule_tick()
        self.assertEqual(tick["rejected_by_employee_policy"], 1)
        self.assertEqual(called, [])
        job = scheduler.get_job("job-disabled")["job"]
        self.assertEqual(job["state"], "rejected")
        self.assertEqual(job["employee_state"], "rejected")

    def test_eligible_employee_can_reach_resource_admission(self):
        self.create("job-active")
        scheduler.employee_eligibility = self.eligible
        scheduler.reserve_resources = self.admitted
        tick = scheduler.schedule_tick()
        self.assertEqual(tick["assignment_count"], 1)
        job = scheduler.get_job("job-active")["job"]
        self.assertEqual(job["state"], "leased")
        self.assertEqual(job["employee_state"], "eligible")
        self.assertTrue(job["employee_decision"]["eligible"])

    def test_lifecycle_authority_error_is_fail_closed(self):
        self.create("job-error")
        scheduler.employee_eligibility = lambda job: (_ for _ in ()).throw(
            scheduler.EmployeeLifecycleEnforcementError("registry unavailable")
        )
        scheduler.reserve_resources = self.admitted
        tick = scheduler.schedule_tick()
        self.assertEqual(tick["assignment_count"], 0)
        self.assertEqual(tick["employee_policy_error_count"], 1)
        job = scheduler.get_job("job-error")["job"]
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["employee_state"], "error")

    def test_start_rechecks_employee_eligibility(self):
        self.create("job-recheck")
        scheduler.employee_eligibility = self.eligible
        scheduler.reserve_resources = self.admitted
        scheduler.schedule_tick()
        job = scheduler.get_job("job-recheck")["job"]
        scheduler.employee_eligibility = lambda row: {
            "ok": True,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": row["employee_id"],
            "eligible": False,
            "decision": "queued",
            "reasons": ["employee-lifecycle-paused"],
        }
        with self.assertRaises(HTTPException) as raised:
            scheduler.mark_job_running(
                "job-recheck",
                scheduler.JobStateUpdate(lease_id=job["lease_id"]),
            )
        self.assertEqual(raised.exception.status_code, 409)
        current = scheduler.get_job("job-recheck")["job"]
        self.assertEqual(current["state"], "leased")
        self.assertEqual(current["employee_state"], "queued")


if __name__ == "__main__":
    unittest.main()
