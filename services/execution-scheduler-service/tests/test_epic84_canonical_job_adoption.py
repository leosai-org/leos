from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from leos_contracts import validate_contract

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "execution-scheduler-service"))
sys.path.insert(0, str(ROOT / "packages" / "leos-contracts" / "src"))

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="leos-epic84-scheduler-")
os.environ["EXECUTION_SCHEDULER_DATA_DIR"] = _TEST_ROOT.name
os.environ["EXECUTION_SCHEDULER_AUTO_SCHEDULE"] = "false"
os.environ["EXECUTION_SCHEDULER_RESOURCE_ENFORCEMENT"] = "true"
os.environ["EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_ENFORCEMENT"] = "false"

from app import main as scheduler  # noqa: E402


EXAMPLES = ROOT / "examples"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def actor_ref() -> dict:
    return {
        "resource_type": "ACTOR_CONTEXT",
        "resource_id": "actor-context:test:scheduler-projection",
        "revision": "sha256:actor-context-test-scheduler-projection",
    }


def auth_ref() -> dict:
    return {
        "resource_type": "AUTHORIZATION_DECISION",
        "resource_id": "authorization-decision:test:scheduler-projection",
        "revision": "sha256:authorization-test-scheduler-projection",
    }


def ref(document: dict) -> dict:
    identity = document["identity"]
    return {
        "resource_type": identity["resource_type"],
        "resource_id": identity["resource_id"],
        "revision": identity["revision"],
    }


class SchedulerCanonicalJobAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        scheduler.DATA_DIR = Path(_TEST_ROOT.name)
        scheduler.DB_PATH = scheduler.DATA_DIR / "execution-scheduler.db"
        scheduler.migrate()
        with scheduler.connect() as db:
            for table in (
                "scheduler_projection_idempotency",
                "scheduler_resource_history",
                "scheduler_terminal_transitions",
                "scheduler_events",
                "scheduler_leases",
                "scheduler_jobs",
                "scheduler_workers",
            ):
                db.execute(f"DELETE FROM {table}")
        scheduler.emit = lambda *args, **kwargs: "event"
        self.job = example("job-definition.v1.json")
        self.task = example("task-definition.v1.json")
        self.projection_ref = {
            "resource_type": "SCHEDULER_PROJECTION",
            "resource_id": "scheduler-projection:acme:market-brief:1",
            "revision": "sha256:scheduler-projection-acme-market-brief-1",
        }

    def payload(self, **overrides) -> dict:
        projection = {
            "contract_version": "leos.scheduler-job-projection.v1",
            "projection_id": self.projection_ref["resource_id"],
            "source_scheduler_projection_ref": copy.deepcopy(
                self.projection_ref
            ),
            "source_revision": self.projection_ref["revision"],
            "organization_ref": copy.deepcopy(self.job["organization_ref"]),
            "source_work_request_ref": copy.deepcopy(
                self.job["source_work_request_ref"]
            ),
            "source_workflow_definition_ref": copy.deepcopy(
                self.job["source_workflow_definition_ref"]
            ),
            "source_workflow_revision_ref": copy.deepcopy(
                self.job["source_workflow_revision_ref"]
            ),
            "source_task_ref": ref(self.task),
            "employee_ref": {
                "resource_type": "EMPLOYEE",
                "resource_id": "employee:acme:researcher",
                "revision": "sha256:employee-acme-researcher-v3",
            },
            "resource_requirements": {
                "cpu_required": 1,
                "ram_mb_required": 512,
            },
            "scheduling": {
                "max_attempts": 3,
                "required_labels": {"runtime": "persistent-employee"},
            },
            "job": copy.deepcopy(self.job),
        }
        projection.update(overrides.pop("projection_overrides", {}))
        return {
            "actor_context_ref": actor_ref(),
            "authorization_decision_ref": auth_ref(),
            "idempotency_key": overrides.pop(
                "idempotency_key", "idem:scheduler-projection"
            ),
            "projection": projection,
            **overrides,
        }

    def test_canonical_job_projection_creates_scheduler_owned_job(self):
        response = scheduler.accept_canonical_job_projection(self.payload())
        self.assertEqual("ACCEPTED", response["status"])
        self.assertEqual(
            self.job["identity"]["resource_id"],
            response["job_ref"]["resource_id"],
        )
        row = scheduler.get_job(self.job["identity"]["resource_id"])["job"]
        self.assertEqual("canonical_work_projection", row["record_origin"])
        self.assertEqual("queued", row["state"])
        self.assertEqual("employee:acme:researcher", row["employee_id"])

        canonical = scheduler.get_canonical_job(
            self.job["identity"]["resource_id"]
        )
        self.assertTrue(canonical["canonical"])
        self.assertEqual(
            "leos.job-definition.v1",
            canonical["job"]["contract_version"],
        )
        self.assertEqual("READY", canonical["job"]["status"])
        validate_contract("leos.job-definition.v1", canonical["job"])

    def test_duplicate_idempotency_replays_and_payload_conflict_fails(self):
        first = scheduler.accept_canonical_job_projection(self.payload())
        second = scheduler.accept_canonical_job_projection(self.payload())
        self.assertEqual(first, second)
        with self.assertRaises(HTTPException) as raised:
            scheduler.accept_canonical_job_projection(
                self.payload(projection_overrides={"payload": {"changed": True}})
            )
        self.assertEqual(409, raised.exception.status_code)

    def test_same_projection_cannot_create_duplicate_scheduler_job(self):
        scheduler.accept_canonical_job_projection(self.payload())
        with self.assertRaises(HTTPException) as raised:
            scheduler.accept_canonical_job_projection(
                self.payload(idempotency_key="idem:second")
            )
        self.assertEqual(409, raised.exception.status_code)

    def test_malformed_and_unsupported_contracts_fail_closed(self):
        bad_job = copy.deepcopy(self.job)
        bad_job["contract_version"] = "leos.job-definition.v999"
        with self.assertRaises(HTTPException):
            scheduler.accept_canonical_job_projection(
                self.payload(projection_overrides={"job": bad_job})
            )
        with self.assertRaises(HTTPException):
            scheduler.accept_canonical_job_projection(
                self.payload(
                    projection_overrides={
                        "contract_version": "leos.scheduler-job-projection.v999"
                    }
                )
            )

    def test_required_lineage_and_evidence_are_mandatory(self):
        for field in (
            "source_scheduler_projection_ref",
            "source_task_ref",
            "organization_ref",
        ):
            projection = self.payload()["projection"]
            projection.pop(field)
            with self.assertRaises(HTTPException):
                scheduler.accept_canonical_job_projection(
                    {
                        "actor_context_ref": actor_ref(),
                        "authorization_decision_ref": auth_ref(),
                        "idempotency_key": f"idem:missing:{field}",
                        "projection": projection,
                    }
                )

        for field in ("actor_context_ref", "authorization_decision_ref"):
            request = self.payload(idempotency_key=f"idem:missing:{field}")
            request.pop(field)
            with self.assertRaises(HTTPException):
                scheduler.accept_canonical_job_projection(request)

    def test_cross_org_and_stale_source_revision_are_rejected(self):
        job = copy.deepcopy(self.job)
        job["organization_ref"]["resource_id"] = "organization:other"
        with self.assertRaises(HTTPException):
            scheduler.accept_canonical_job_projection(
                self.payload(projection_overrides={"job": job})
            )
        with self.assertRaises(HTTPException) as raised:
            scheduler.accept_canonical_job_projection(
                self.payload(projection_overrides={"source_revision": "sha256:old"})
            )
        self.assertEqual(409, raised.exception.status_code)

    def test_work_coordination_cannot_set_scheduler_state_or_retry(self):
        for forbidden in (
            {"scheduler_state": "running"},
            {"lease_id": "lease:caller"},
            {"attempt_count": 7},
            {"not_before": "2026-07-25T00:00:00Z"},
            {
                "retry_intent_ref": {
                    "resource_type": "RETRY_INTENT",
                    "resource_id": "retry:intent:1",
                    "revision": "sha256:retry-intent-1",
                },
                "scheduler_retry_now": True,
            },
        ):
            with self.assertRaises(HTTPException):
                scheduler.accept_canonical_job_projection(
                    self.payload(
                        idempotency_key=f"idem:forbidden:{len(str(forbidden))}",
                        projection_overrides=forbidden,
                    )
                )

    def test_authority_booleans_secrets_and_selection_are_rejected(self):
        for forbidden in (
            {"authorized": True},
            {"approval_granted": True},
            {"credential": "do-not-store"},
            {"selected_by_score": True},
            {"employee_score": 0.9},
        ):
            with self.assertRaises(HTTPException):
                scheduler.accept_canonical_job_projection(
                    self.payload(
                        idempotency_key=f"idem:boundary:{len(str(forbidden))}",
                        projection_overrides=forbidden,
                    )
                )

    def test_legacy_job_view_is_not_mislabeled_canonical(self):
        scheduler.create_job(
            scheduler.JobCreate(job_id="legacy-job", employee_id="employee-1")
        )
        view = scheduler.get_canonical_job("legacy-job")
        self.assertFalse(view["canonical"])
        self.assertEqual("legacy", view["record_origin"])


if __name__ == "__main__":
    unittest.main()
