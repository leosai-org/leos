from __future__ import annotations

import copy
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "persistent-employee-runtime-service"))
sys.path.insert(0, str(ROOT / "packages" / "leos-contracts" / "src"))

from fastapi import HTTPException
from leos_contracts import validate_contract

_TEST_ROOT = tempfile.TemporaryDirectory(prefix="leos-epic84-runtime-")
os.environ["PERSISTENT_EMPLOYEE_RUNTIME_DATA_DIR"] = _TEST_ROOT.name
os.environ["EMPLOYEE_RUNTIME_AUTO_POLL_SCHEDULER"] = "false"

from app import main as runtime  # noqa: E402


EXAMPLES = ROOT / "examples"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def actor_ref() -> dict:
    return {
        "resource_type": "ACTOR_CONTEXT",
        "resource_id": "actor-context:test:runtime-handoff",
        "revision": "sha256:actor-context-test-runtime-handoff",
    }


def auth_ref() -> dict:
    return {
        "resource_type": "AUTHORIZATION_DECISION",
        "resource_id": "authorization-decision:test:runtime-handoff",
        "revision": "sha256:authorization-test-runtime-handoff",
    }


def actor_evidence_ref() -> dict:
    return {
        "evidence_type": "ACTOR_CONTEXT",
        "authority": {
            "authority_id": "identity-authority",
            "principal": {
                "principal_id": "principal:service:identity-authority",
                "principal_type": "SERVICE",
            },
            "authority_revision": "sha256:identity-authority-v1",
        },
        "reference_id": actor_ref()["resource_id"],
        "revision": actor_ref()["revision"],
    }


def principal_ref() -> dict:
    return {"principal_id": "principal:user:brett", "principal_type": "HUMAN_USER"}


def ref(document: dict) -> dict:
    identity = document["identity"]
    return {
        "resource_type": identity["resource_type"],
        "resource_id": identity["resource_id"],
        "revision": identity["revision"],
    }


def authorization_binding(
    *,
    organization_ref: dict,
    assignment_ref: dict,
    handoff_ref: dict,
) -> dict:
    seed = {
        "operation": "runtime.assignment-handoff.accept",
        "organization_ref": organization_ref,
        "resource_ref": assignment_ref,
        "source_assignment_handoff_ref": handoff_ref,
    }
    return {
        "contract_version": "leos.authorization-evidence-binding.v1",
        "authorization_decision_ref": auth_ref(),
        "actor_context_ref": actor_evidence_ref(),
        "organization_ref": organization_ref,
        "expected_scope": {
            "subject": principal_ref(),
            "action": "runtime.assignment-handoff.accept",
            "resource": assignment_ref,
            "context_type": "runtime.assignment-handoff",
            "context_id": handoff_ref["resource_id"],
            "context_revision": handoff_ref["revision"],
            "context_digest": runtime.request_hash(seed),
        },
        "expected_decision": "ALLOW",
    }


class RuntimeCanonicalAssignmentAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime.DATA_DIR = Path(_TEST_ROOT.name)
        runtime.DB_PATH = runtime.DATA_DIR / "persistent-employee-runtime.db"
        runtime.migrate()
        with runtime.connect() as db:
            for table in (
                "runtime_handoff_idempotency",
                "employee_event_outbox",
                "assignment_terminal_transitions",
                "employee_events",
                "employee_assignments",
                "employee_messages",
                "employee_memory",
                "employees",
            ):
                db.execute(f"DELETE FROM {table}")
            timestamp = runtime.now()
            db.execute(
                """
                INSERT INTO employees (
                    employee_id, name, role, status, runtime_state,
                    profile_json, permissions_json, capabilities_json,
                    metadata_json, created_at, updated_at
                ) VALUES (
                    'employee:acme:researcher', 'Researcher', 'researcher',
                    'online', 'idle', '{}', '{}', '[]', '{}', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
        runtime.verify_authorization_binding = lambda binding: {
            "verification_status": "VERIFIED",
            "authorization_decision_ref": binding["authorization_decision_ref"],
            "decision": binding["expected_decision"],
            "verified_at": "2026-01-01T00:00:00Z",
            "verified_by": {"authority_id": "authorization-authority"},
            "actor_context_ref": binding["actor_context_ref"],
            "reasons": [],
        }
        self.assignment = example("work-assignment.v1.json")
        self.task = example("task-definition.v1.json")
        self.job = example("job-definition.v1.json")
        self.handoff_ref = {
            "resource_type": "ASSIGNMENT_HANDOFF",
            "resource_id": "assignment-handoff:acme:research:1",
            "revision": "sha256:assignment-handoff-acme-research-1",
        }

    def payload(self, **overrides) -> dict:
        handoff = {
            "contract_version": "leos.runtime-assignment-handoff.v1",
            "handoff_id": self.handoff_ref["resource_id"],
            "source_assignment_handoff_ref": copy.deepcopy(self.handoff_ref),
            "source_revision": self.handoff_ref["revision"],
            "organization_ref": copy.deepcopy(
                self.assignment["organization_ref"]
            ),
            "assignment_decision_ref": copy.deepcopy(
                self.assignment["assignment_decision_ref"]
            ),
            "source_task_ref": ref(self.task),
            "scheduler_job_ref": ref(self.job),
            "assignment": copy.deepcopy(self.assignment),
        }
        handoff.update(overrides.pop("handoff_overrides", {}))
        assignment = handoff["assignment"]
        assignment_ref = {
            "resource_type": "WORK_ASSIGNMENT",
            "resource_id": assignment["identity"]["resource_id"],
            "revision": assignment["identity"]["revision"],
        }
        return {
            "actor_context_ref": actor_ref(),
            "authorization_decision_ref": auth_ref(),
            "authorization_binding": authorization_binding(
                organization_ref=handoff["organization_ref"],
                assignment_ref=assignment_ref,
                handoff_ref=handoff["source_assignment_handoff_ref"],
            ),
            "idempotency_key": overrides.pop(
                "idempotency_key", "idem:runtime-handoff"
            ),
            "handoff": handoff,
            **overrides,
        }

    def test_canonical_assignment_handoff_accepts_runtime_projection(self):
        response = runtime.accept_canonical_assignment_handoff(self.payload())
        self.assertEqual("ACCEPTED", response["status"])
        assignment_id = self.assignment["identity"]["resource_id"]
        self.assertEqual(assignment_id, response["assignment_ref"]["resource_id"])

        listed = runtime.list_assignments(limit=200)["assignments"][0]
        self.assertEqual("canonical_work_handoff", listed["record_origin"])
        self.assertEqual("assigned", listed["state"])
        self.assertEqual("employee:acme:researcher", listed["employee_id"])

        canonical = runtime.get_canonical_assignment(assignment_id)
        self.assertTrue(canonical["canonical"])
        self.assertEqual(
            "leos.work-assignment.v1",
            canonical["assignment"]["contract_version"],
        )
        self.assertEqual("ACTIVE", canonical["assignment"]["status"])
        validate_contract("leos.work-assignment.v1", canonical["assignment"])

    def test_duplicate_idempotency_replays_and_payload_conflict_fails(self):
        first = runtime.accept_canonical_assignment_handoff(self.payload())
        second = runtime.accept_canonical_assignment_handoff(self.payload())
        self.assertEqual(first, second)
        with self.assertRaises(HTTPException) as raised:
            runtime.accept_canonical_assignment_handoff(
                self.payload(handoff_overrides={"payload": {"changed": True}})
            )
        self.assertEqual(409, raised.exception.status_code)

    def test_same_handoff_cannot_create_duplicate_runtime_projection(self):
        runtime.accept_canonical_assignment_handoff(self.payload())
        with self.assertRaises(HTTPException) as raised:
            runtime.accept_canonical_assignment_handoff(
                self.payload(idempotency_key="idem:second")
            )
        self.assertEqual(409, raised.exception.status_code)

    def test_malformed_and_unsupported_contracts_fail_closed(self):
        bad_assignment = copy.deepcopy(self.assignment)
        bad_assignment["contract_version"] = "leos.work-assignment.v999"
        with self.assertRaises(HTTPException):
            runtime.accept_canonical_assignment_handoff(
                self.payload(handoff_overrides={"assignment": bad_assignment})
            )
        with self.assertRaises(HTTPException):
            runtime.accept_canonical_assignment_handoff(
                self.payload(
                    handoff_overrides={
                        "contract_version": "leos.runtime-assignment-handoff.v999"
                    }
                )
            )

    def test_required_lineage_and_evidence_are_mandatory(self):
        for field in (
            "source_assignment_handoff_ref",
            "assignment_decision_ref",
            "source_task_ref",
            "scheduler_job_ref",
            "organization_ref",
        ):
            request = self.payload(idempotency_key=f"idem:missing:{field}")
            handoff = request["handoff"]
            handoff.pop(field)
            with self.assertRaises(HTTPException):
                runtime.accept_canonical_assignment_handoff(request)
        for field in ("actor_context_ref", "authorization_decision_ref", "authorization_binding"):
            request = self.payload(idempotency_key=f"idem:missing:{field}")
            request.pop(field)
            with self.assertRaises(HTTPException):
                runtime.accept_canonical_assignment_handoff(request)

    def test_authorization_binding_mismatch_and_denial_fail_closed(self):
        request = self.payload(idempotency_key="idem:wrong-binding")
        request["authorization_binding"]["expected_scope"]["action"] = (
            "runtime.assignment-handoff.update"
        )
        with self.assertRaises(HTTPException) as wrong:
            runtime.accept_canonical_assignment_handoff(request)
        self.assertEqual(403, wrong.exception.status_code)

        runtime.verify_authorization_binding = lambda binding: {
            "verification_status": "DENIED",
            "authorization_decision_ref": binding["authorization_decision_ref"],
            "decision": binding["expected_decision"],
            "verified_at": "2026-01-01T00:00:00Z",
            "verified_by": {"authority_id": "authorization-authority"},
            "actor_context_ref": binding["actor_context_ref"],
            "reasons": ["test_denial"],
        }
        with self.assertRaises(HTTPException) as denied:
            runtime.accept_canonical_assignment_handoff(
                self.payload(idempotency_key="idem:denied-binding")
            )
        self.assertEqual(403, denied.exception.status_code)

    def test_authorization_binding_requires_canonical_actor_context_evidence(self):
        request = self.payload(idempotency_key="idem:missing-actor-authority")
        request["authorization_binding"]["actor_context_ref"].pop("authority")

        with self.assertRaises(HTTPException) as raised:
            runtime.accept_canonical_assignment_handoff(request)

        self.assertEqual(403, raised.exception.status_code)
        self.assertEqual(
            "malformed_authorization_binding",
            raised.exception.detail["code"],
        )

    def test_cross_org_stale_revision_and_unknown_employee_are_rejected(self):
        assignment = copy.deepcopy(self.assignment)
        assignment["organization_ref"]["resource_id"] = "organization:other"
        with self.assertRaises(HTTPException):
            runtime.accept_canonical_assignment_handoff(
                self.payload(handoff_overrides={"assignment": assignment})
            )
        with self.assertRaises(HTTPException) as raised:
            runtime.accept_canonical_assignment_handoff(
                self.payload(handoff_overrides={"source_revision": "sha256:old"})
            )
        self.assertEqual(409, raised.exception.status_code)

        with runtime.connect() as db:
            db.execute("DELETE FROM employees")
        with self.assertRaises(HTTPException) as missing:
            runtime.accept_canonical_assignment_handoff(
                self.payload(idempotency_key="idem:unknown-employee")
            )
        self.assertEqual(503, missing.exception.status_code)

    def test_handoff_cannot_smuggle_acceptance_authority_or_execution(self):
        for forbidden in (
            {"authorized": True},
            {"approval_granted": True},
            {"credential": "do-not-store"},
            {"lease_id": "lease:caller"},
            {"runtime_state": "running"},
            {"terminal_state": "complete"},
            {"capability_resolution": {"status": "RESOLVED"}},
            {"dispatcher_request": {"execute": True}},
            {"employee_score": 0.9},
        ):
            with self.assertRaises(HTTPException):
                runtime.accept_canonical_assignment_handoff(
                    self.payload(
                        idempotency_key=f"idem:forbidden:{len(str(forbidden))}",
                        handoff_overrides=forbidden,
                    )
                )

    def test_runtime_accepts_employee_assignments_only(self):
        assignment = copy.deepcopy(self.assignment)
        assignment["assignee"] = {
            "target_type": "TEAM",
            "resource": {
                "resource_type": "TEAM",
                "resource_id": "team:acme:market-research",
                "revision": "sha256:team-acme-market-research-v1",
            },
        }
        with self.assertRaises(HTTPException):
            runtime.accept_canonical_assignment_handoff(
                self.payload(handoff_overrides={"assignment": assignment})
            )

    def test_scheduler_sync_does_not_create_canonical_assignment_from_job(self):
        job = {
            "job_id": self.job["identity"]["resource_id"],
            "employee_id": "employee:acme:researcher",
            "state": "leased",
            "lease_id": "lease:canonical",
            "record_origin": "canonical_work_projection",
            "payload": {},
        }

        class Response:
            status_code = 200
            text = ""

            def json(self):
                return {"jobs": [job]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url):
                return Response()

        original = runtime.httpx.AsyncClient
        runtime.httpx.AsyncClient = FakeClient
        try:
            result = asyncio.run(runtime.import_scheduler_assignments())
        finally:
            runtime.httpx.AsyncClient = original
        self.assertEqual(0, result["imported"])
        self.assertEqual(1, result["skipped"])
        self.assertEqual([], runtime.list_assignments(limit=200)["assignments"])

    def test_legacy_assignment_view_is_not_mislabeled_canonical(self):
        timestamp = runtime.now()
        with runtime.connect() as db:
            db.execute(
                """
                INSERT INTO employee_assignments(
                    assignment_id, employee_id, job_id, state,
                    payload_json, assigned_at, updated_at
                ) VALUES(
                    'legacy-assignment', 'employee:acme:researcher',
                    'legacy-job', 'assigned', '{}', ?, ?
                )
                """,
                (timestamp, timestamp),
            )
        view = runtime.get_canonical_assignment("legacy-assignment")
        self.assertFalse(view["canonical"])
        self.assertEqual("legacy_scheduler_sync", view["record_origin"])


if __name__ == "__main__":
    unittest.main()
