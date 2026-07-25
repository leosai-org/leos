from __future__ import annotations

import json
import os
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


URLS = {
    "resource": "http://resource-profile:8000",
    "scheduler": "http://scheduler:8000",
    "runtime": "http://persistent-runtime:8000",
    "capability": "http://capability-manager:8000",
    "dispatcher": "http://dispatcher:8000",
    "cognitive": "http://cognitive:8000",
    "provider": "http://synthetic-provider:8000",
}
TIMEOUT = float(os.getenv("E2E_TIMEOUT_SECONDS", "30"))
EMPLOYEE_ID = "epic-1.2e-employee"
CAPABILITY_ID = "leos.synthetic.echo"
PROVIDER_ID = "epic-1.2e-synthetic-provider"
JOB_ID = "epic-1.2e-job"


def request(
    service: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    encoded = (
        json.dumps(body).encode("utf-8") if body is not None else None
    )
    call = urllib.request.Request(
        URLS[service] + path,
        data=encoded,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(call, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AssertionError(
            f"{method} {service}{path} returned {error.code}: {detail}"
        ) from error


def decoded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


class GovernedExecutionSpineE2E(unittest.TestCase):
    evidence: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        started = time.monotonic()
        request(
            "runtime",
            "/employees",
            method="POST",
            body={
                "employee_id": EMPLOYEE_ID,
                "name": "Epic 1.2E Employee",
                "role": "synthetic-e2e",
                "status": "online",
                "runtime_state": "idle",
                "capabilities": [CAPABILITY_ID],
            },
        )
        request(
            "resource",
            "/profiles",
            method="POST",
            body={
                "contract_version": "leos.employee-resource-profile.v1",
                "employee_id": EMPLOYEE_ID,
                "resource_profile": {
                    "cpu_cores_min": 0,
                    "memory_mb_min": 0,
                    "gpu_required": False,
                    "vram_mb_min": 0,
                    "gpu_uuid_preferences": [],
                },
                "execution_policy": {
                    "max_concurrent_jobs": 1,
                    "queue_when_unavailable": True,
                    "preemptible": True,
                    "allow_preemption": False,
                    "reservation_ttl_seconds": 120,
                },
            },
        )
        request(
            "capability",
            "/providers/register-bundle",
            method="POST",
            body={
                "provider": {
                    "provider_id": PROVIDER_ID,
                    "name": "Epic 1.2E Synthetic Provider",
                    "provider_type": "service",
                    "base_url": "http://synthetic-provider:8000",
                    "execute_path": "/invoke",
                    "health_url": "http://synthetic-provider:8000/health",
                    "status": "active",
                    "metadata": {"test_only": True},
                },
                "capabilities": [
                    {
                        "capability_id": CAPABILITY_ID,
                        "name": "Synthetic Echo",
                        "category": "test",
                        "risk_level": "low",
                        "approval_required": False,
                        "metadata": {"test_only": True},
                    }
                ],
                "bindings": [
                    {
                        "provider_id": PROVIDER_ID,
                        "capability_id": CAPABILITY_ID,
                        "enabled": True,
                        "approval_policy": "allowed",
                    }
                ],
            },
        )
        workers = request("scheduler", "/workers")
        if not any(
            worker["worker_id"] == "persistent-employee-runtime"
            for worker in workers["workers"]
        ):
            raise AssertionError("Persistent Runtime worker was not registered")

        request(
            "scheduler",
            "/jobs",
            method="POST",
            body={
                "job_id": JOB_ID,
                "mission_id": "epic-1.2e-mission",
                "workflow_id": "epic-1.2e-workflow",
                "step_id": "epic-1.2e-step",
                "employee_id": EMPLOYEE_ID,
                "capability_id": CAPABILITY_ID,
                "job_type": "synthetic-e2e",
                "cpu_required": 0,
                "ram_mb_required": 0,
                "gpu_required": 0,
                "vram_mb_required": 0,
                "payload": {
                    "message": "epic-1.2e-input",
                    "expected_response": "epic-1.2e-success",
                },
                "max_attempts": 1,
            },
        )
        schedule = request(
            "scheduler", "/schedule/tick", method="POST", body={}
        )
        if schedule["assignment_count"] != 1:
            raise AssertionError(f"Scheduler did not lease job: {schedule}")
        lease_id = schedule["assignments"][0]["lease_id"]

        imported = request(
            "runtime", "/scheduler/sync", method="POST", body={}
        )
        if imported["imported"] != 1:
            raise AssertionError(f"Runtime did not import assignment: {imported}")
        assignments = request("runtime", "/assignments")["assignments"]
        assignment = next(
            item for item in assignments if item["job_id"] == JOB_ID
        )
        assignment_id = assignment["assignment_id"]

        cognitive_tick = request(
            "cognitive", "/tick", method="POST", body={}
        )
        if cognitive_tick["selected_count"] != 1:
            raise AssertionError(
                f"Cognitive Service did not process assignment: {cognitive_tick}"
            )

        job = request("scheduler", f"/jobs/{JOB_ID}")["job"]
        resource = request(
            "scheduler", f"/jobs/{JOB_ID}/resource"
        )
        assignment = next(
            item
            for item in request("runtime", "/assignments")["assignments"]
            if item["assignment_id"] == assignment_id
        )
        employee = request(
            "runtime", f"/employees/{EMPLOYEE_ID}"
        )["employee"]
        runs = request("cognitive", "/runs")["runs"]
        run = next(
            item for item in runs if item["assignment_id"] == assignment_id
        )
        cognitive = request(
            "cognitive", f"/runs/{run['cognitive_run_id']}"
        )
        attempt = cognitive["attempts"][0]
        execution_request = decoded(attempt["execution_request_json"])
        execution_result = decoded(attempt["execution_result_json"])
        dispatcher = request(
            "dispatcher", f"/executions/{attempt['execution_id']}"
        )["execution"]
        resolution_id = execution_result["resolution_ref"]["reference_id"]
        resolution = request(
            "capability", f"/resolutions/{resolution_id}"
        )
        provider_record = next(
            item
            for item in request(
                "capability",
                f"/providers?capability_id={CAPABILITY_ID}",
            )["providers"]
            if item["provider_id"] == PROVIDER_ID
        )
        provider_evidence = request("provider", "/evidence")
        terminal_result = decoded(run["terminal_result_json"])
        invocation = execution_result["attempt_summary"]["attempts"][0]

        cls.evidence = {
            "duration_seconds": round(time.monotonic() - started, 3),
            "job_id": JOB_ID,
            "lease_id": lease_id,
            "assignment_id": assignment_id,
            "employee_id": EMPLOYEE_ID,
            "cognitive_run_id": run["cognitive_run_id"],
            "cognitive_attempt_id": attempt["cognitive_attempt_id"],
            "execution_id": attempt["execution_id"],
            "resolution_id": resolution_id,
            "invocation_attempt_id": invocation["invocation_attempt_id"],
            "terminal_transition_id": run["terminal_transition_id"],
            "provider_id": PROVIDER_ID,
            "provider_revision": resolution["selected_target"]["target_ref"][
                "revision"
            ],
            "provider_invocations": provider_evidence["invocation_count"],
            "execution_status": execution_result["status"],
            "cognitive_status": run["state"],
            "assignment_status": assignment["state"],
            "job_status": job["state"],
            "resource_state": resource["resource_state"],
            "execution_request": execution_request,
            "execution_result": execution_result,
            "dispatcher": dispatcher,
            "resolution": resolution,
            "provider_record": provider_record,
            "provider_evidence": provider_evidence,
            "assignment": assignment,
            "employee": employee,
            "job": job,
            "resource": resource,
            "terminal_result": terminal_result,
        }
        Path("/tmp/epic-1.2e-evidence.json").write_text(
            json.dumps(cls.evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def test_01_complete_governed_execution_spine(self) -> None:
        evidence = self.evidence
        request_document = evidence["execution_request"]
        result = evidence["execution_result"]
        resolution = evidence["resolution"]
        dispatcher = evidence["dispatcher"]
        provider_call = evidence["provider_evidence"]["calls"][0]

        self.assertEqual("leos.execution.v1", request_document["contract_version"])
        self.assertEqual(CAPABILITY_ID, request_document["capability_id"])
        self.assertEqual(EMPLOYEE_ID, request_document["requester"]["id"])
        self.assertEqual(evidence["execution_id"], request_document["execution_id"])
        self.assertEqual(evidence["job_id"], request_document["trace"]["job_id"])
        self.assertEqual(evidence["lease_id"], request_document["trace"]["lease_id"])
        self.assertEqual(
            evidence["assignment_id"],
            request_document["trace"]["assignment_id"],
        )
        self.assertEqual(
            evidence["cognitive_attempt_id"],
            request_document["trace"]["cognitive_attempt_id"],
        )

        self.assertEqual("RESOLVED", resolution["status"])
        self.assertEqual(CAPABILITY_ID, resolution["capability_id"])
        self.assertEqual(1, len(resolution["candidate_evaluations"]))
        self.assertEqual(
            PROVIDER_ID, resolution["selected_target"]["provider_id"]
        )
        target_ref = resolution["selected_target"]["target_ref"]
        self.assertEqual(
            evidence["provider_record"]["updated_at"], target_ref["revision"]
        )
        self.assertEqual("none", resolution["rationale"]["provider_order_source"])
        self.assertEqual("first-ranked-valid", resolution["rationale"]["selection_rule"])

        self.assertEqual("SUCCESS", result["status"])
        self.assertEqual(1, result["attempt_summary"]["attempt_count"])
        self.assertEqual(1, len(result["attempt_summary"]["attempts"]))
        self.assertEqual(
            evidence["invocation_attempt_id"],
            result["correlation"]["invocation_attempt_id"],
        )
        self.assertEqual(result, dispatcher["result"])
        self.assertEqual(request_document, dispatcher["request"])
        self.assertEqual(resolution, dispatcher["resolution"])
        self.assertEqual(PROVIDER_ID, dispatcher["outbound_evidence"]["provider_id"])
        self.assertEqual(
            "canonical_envelope",
            dispatcher["outbound_evidence"]["request_shape"],
        )

        self.assertEqual(1, evidence["provider_invocations"])
        self.assertEqual(evidence["execution_id"], provider_call["execution_id"])
        self.assertEqual(request_document, provider_call["payload"])
        self.assertEqual(
            "epic-1.2e-success",
            provider_call["response"]["message"],
        )

        self.assertEqual("completed", evidence["cognitive_status"])
        self.assertEqual("complete", evidence["assignment_status"])
        self.assertEqual("complete", evidence["job_status"])
        self.assertEqual("released", evidence["resource_state"])
        self.assertIsNotNone(evidence["resource"]["resource_released_at"])
        self.assertIsNone(evidence["job"]["lease_id"])
        self.assertEqual("idle", evidence["employee"]["runtime_state"])
        self.assertIsNone(evidence["employee"]["current_assignment_id"])
        self.assertEqual(
            "complete", evidence["terminal_result"]["state"]
        )

    def test_02_duplicate_ticks_do_not_repeat_work(self) -> None:
        before = {
            "assignments": request("runtime", "/assignments")[
                "assignment_count"
            ],
            "runs": len(request("cognitive", "/runs")["runs"]),
            "executions": request("dispatcher", "/executions")[
                "execution_count"
            ],
            "resolutions": request("capability", "/resolutions")[
                "resolution_count"
            ],
            "invocations": request("provider", "/evidence")[
                "invocation_count"
            ],
        }
        request("scheduler", "/schedule/tick", method="POST", body={})
        request("runtime", "/scheduler/sync", method="POST", body={})
        request("cognitive", "/tick", method="POST", body={})
        request("runtime", "/scheduler/sync", method="POST", body={})
        request("cognitive", "/tick", method="POST", body={})
        after = {
            "assignments": request("runtime", "/assignments")[
                "assignment_count"
            ],
            "runs": len(request("cognitive", "/runs")["runs"]),
            "executions": request("dispatcher", "/executions")[
                "execution_count"
            ],
            "resolutions": request("capability", "/resolutions")[
                "resolution_count"
            ],
            "invocations": request("provider", "/evidence")[
                "invocation_count"
            ],
        }
        self.assertEqual(before, after)
        self.assertEqual(
            {
                "assignments": 1,
                "runs": 1,
                "executions": 1,
                "resolutions": 1,
                "invocations": 1,
            },
            after,
        )


if __name__ == "__main__":
    unittest.main()

