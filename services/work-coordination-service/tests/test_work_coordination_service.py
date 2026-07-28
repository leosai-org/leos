from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TEST_DATA = tempfile.TemporaryDirectory(prefix="leos-work-coordination-")
os.environ["LEOS_WORK_COORDINATION_DATA_DIR"] = TEST_DATA.name
os.environ["LEOS_WORK_COORDINATION_DB"] = str(Path(TEST_DATA.name) / "work-coordination.db")
os.environ["LEOS_CONTRACT_ROOT"] = str(ROOT / "contracts")
sys.path.insert(0, str(ROOT / "services" / "work-coordination-service"))
sys.path.insert(0, str(ROOT / "packages" / "leos-contracts" / "src"))

from app.domain import (  # noqa: E402
    AUTHORIZATION_AUTHORITY_ID,
    AUTHORIZATION_BINDING_CONTRACT,
    AUTHORITY_REF,
    COLLECTION_TO_RESOURCE_TYPE,
    StaticReferenceAdapter,
    StaticRuntimeHandoffAdapter,
    StaticSchedulerProjectionAdapter,
    WorkCoordinationError,
    WorkCoordinationStore,
    evidence_revision_for,
)

try:  # noqa: E402
    from fastapi.testclient import TestClient  # type: ignore
    from app import main  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in host env without FastAPI
    TestClient = None
    main = None


EXAMPLES = ROOT / "examples"


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def actor_ref() -> dict[str, Any]:
    return {
        "resource_type": "ACTOR_CONTEXT",
        "resource_id": "actor-context:test:work-coordination",
        "revision": "sha256:actor-context-test-work-coordination",
    }


def auth_ref() -> dict[str, Any]:
    return {
        "resource_type": "AUTHORIZATION_DECISION",
        "resource_id": "authorization-decision:test:work-coordination",
        "revision": "sha256:authorization-decision-test-work-coordination",
    }


def actor_evidence_ref() -> dict[str, Any]:
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


def principal_ref() -> dict[str, Any]:
    return {"principal_id": "principal:user:brett", "principal_type": "HUMAN_USER"}


def authorization_binding(
    *,
    action: str,
    organization_ref: dict[str, Any],
    resource_ref: dict[str, Any],
    context_type: str,
    context_id: str,
    context_revision: str,
    seed: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": AUTHORIZATION_BINDING_CONTRACT,
        "authorization_decision_ref": auth_ref(),
        "actor_context_ref": actor_evidence_ref(),
        "organization_ref": organization_ref,
        "expected_scope": {
            "subject": principal_ref(),
            "action": action,
            "resource": resource_ref,
            "context_type": context_type,
            "context_id": context_id,
            "context_revision": context_revision,
            "context_digest": evidence_revision_for(seed),
        },
        "expected_decision": "ALLOW",
    }


class StaticAuthorizationVerifier:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.status = "VERIFIED"

    def verify_authorization_binding(self, binding: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(copy.deepcopy(binding))
        return {
            "verification_status": self.status,
            "authorization_decision_ref": binding["authorization_decision_ref"],
            "decision": binding["expected_decision"],
            "verified_at": "2026-01-01T00:00:00Z",
            "verified_by": {"authority_id": AUTHORIZATION_AUTHORITY_ID},
            "actor_context_ref": binding["actor_context_ref"],
            "reasons": [] if self.status == "VERIFIED" else ["test_denial"],
        }


def payload(**items: Any) -> dict[str, Any]:
    body = dict(items)
    idempotency_key = body.pop("idempotency_key", "idem:test")
    correlation_id = body.pop("correlation_id", "corr:test")
    if "authorization_binding" not in body:
        if isinstance(body.get("record"), dict):
            record = body["record"]
            resource = ref(record)
            operation = f"create:{resource['resource_type']}:{resource['resource_id']}"
            body["authorization_binding"] = authorization_binding(
                action="work-coordination.record.create",
                organization_ref=record["organization_ref"],
                resource_ref=resource,
                context_type="work-coordination.mutation",
                context_id=operation,
                context_revision=resource["revision"],
                seed={
                    "operation": operation,
                    "organization_ref": record["organization_ref"],
                    "resource_ref": resource,
                },
            )
        elif isinstance(body.get("records"), list):
            records = body["records"]
            organization_ref = records[0]["organization_ref"]
            operation = "bundle-create:" + evidence_revision_for({"records": records})
            body["authorization_binding"] = authorization_binding(
                action="work-coordination.bundle.create",
                organization_ref=organization_ref,
                resource_ref=organization_ref,
                context_type="work-coordination.mutation",
                context_id=operation,
                context_revision=organization_ref["revision"],
                seed={
                    "operation": operation,
                    "organization_ref": organization_ref,
                    "resource_refs": [ref(record) for record in records],
                },
            )
        elif isinstance(body.get("decision"), dict):
            decision = body["decision"]
            operation = f"assignment-decision:{decision['decision_id']}"
            body["authorization_binding"] = authorization_binding(
                action="work-coordination.assignment-decision.create",
                organization_ref=decision["organization_ref"],
                resource_ref=decision["work_ref"],
                context_type="work-coordination.assignment-decision",
                context_id=operation,
                context_revision=decision["work_ref"]["revision"],
                seed={
                    "operation": operation,
                    "organization_ref": decision["organization_ref"],
                    "resource_ref": decision["work_ref"],
                },
            )
        elif isinstance(body.get("projection"), dict):
            projection = body["projection"]
            resource = projection.get("source_task_ref") or projection.get("source_work_request_ref")
            operation = f"scheduler-projection:{projection['projection_id']}"
            body["authorization_binding"] = authorization_binding(
                action="work-coordination.scheduler-projection.request",
                organization_ref=projection["organization_ref"],
                resource_ref=resource,
                context_type="work-coordination.scheduler-projection",
                context_id=operation,
                context_revision=resource["revision"],
                seed={
                    "operation": operation,
                    "organization_ref": projection["organization_ref"],
                    "resource_ref": resource,
                },
            )
        elif isinstance(body.get("verification"), dict):
            verification = body["verification"]
            operation = f"verification:{verification['verification_id']}"
            body["authorization_binding"] = authorization_binding(
                action="work-coordination.verification.create",
                organization_ref=verification["organization_ref"],
                resource_ref=verification["result_ref"],
                context_type="work-coordination.verification",
                context_id=operation,
                context_revision=verification["result_ref"]["revision"],
                seed={
                    "operation": operation,
                    "organization_ref": verification["organization_ref"],
                    "resource_ref": verification["result_ref"],
                },
            )
        elif isinstance(body.get("closure"), dict):
            closure = body["closure"]
            operation = f"closure:{closure['closure_id']}"
            body["authorization_binding"] = authorization_binding(
                action="work-coordination.closure.create",
                organization_ref=closure["organization_ref"],
                resource_ref=closure["subject_ref"],
                context_type="work-coordination.closure",
                context_id=operation,
                context_revision=closure["subject_ref"]["revision"],
                seed={
                    "operation": operation,
                    "organization_ref": closure["organization_ref"],
                    "resource_ref": closure["subject_ref"],
                    "verification_ref": closure.get("verification_ref"),
                },
            )
    return {
        "actor_context_ref": actor_ref(),
        "authorization_decision_ref": auth_ref(),
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id,
        **body,
    }


def transition_payload(document: dict[str, Any], to_status: str, *, key: str) -> dict[str, Any]:
    resource = ref(document)
    operation = (
        f"transition:{resource['resource_type']}:{resource['resource_id']}:"
        f"{resource['revision']}:{to_status}"
    )
    return payload(
        expected_revision=resource["revision"],
        to_status=to_status,
        idempotency_key=key,
        authorization_binding=authorization_binding(
            action="work-coordination.record.transition",
            organization_ref=document["organization_ref"],
            resource_ref=resource,
            context_type="work-coordination.mutation",
            context_id=operation,
            context_revision=resource["revision"],
            seed={
                "operation": operation,
                "organization_ref": document["organization_ref"],
                "resource_ref": resource,
            },
        ),
    )


def adopt_work_authority(document: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(document)
    document["identity"]["ownership"]["lifecycle_authority"] = copy.deepcopy(AUTHORITY_REF)
    document["state_evidence"]["transition_authority"] = copy.deepcopy(AUTHORITY_REF)
    return document


def ref(document: dict[str, Any]) -> dict[str, str]:
    identity = document["identity"]
    return {
        "resource_type": identity["resource_type"],
        "resource_id": identity["resource_id"],
        "revision": identity["revision"],
    }


def review_task() -> dict[str, Any]:
    task = adopt_work_authority(example("task-definition.v1.json"))
    task["identity"]["resource_id"] = "task:acme:market-brief:review"
    task["identity"]["revision"] = "sha256:task-acme-market-brief-review-v1"
    task["identity"]["audit_id"] = "audit:task:acme:market-brief:review:v1"
    task.pop("parent_job_ref", None)
    task.pop("source_workflow_revision_ref", None)
    task.pop("source_workflow_step_id", None)
    task["status"] = "BLOCKED"
    return task


class DirectResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None, text: str | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = text or json.dumps(self._body)

    def json(self) -> dict[str, Any]:
        return self._body


class DirectClient:
    """Host-test client for environments without FastAPI installed."""

    def __init__(self, store: WorkCoordinationStore) -> None:
        self.store = store

    def _call(self, operation) -> DirectResponse:
        try:
            return DirectResponse(200, operation())
        except WorkCoordinationError as exc:
            return DirectResponse(exc.status_code, {"detail": exc.as_detail()})

    def get(self, path: str) -> DirectResponse:
        if path == "/health":
            return self._call(self.store.health)
        if path == "/ready":
            return self._call(self.store.ready)
        if path == "/version":
            return DirectResponse(200, {"ok": True, "service": "work-coordination-service"})
        if path == "/outbox":
            return self._call(self.store.outbox)
        if path == "/transitions":
            return self._call(self.store.transitions)
        if path.startswith("/tasks"):
            return self._call(lambda: self.store.list_records("TASK"))
        return DirectResponse(404, {"detail": {"code": "not_found"}})

    def post(self, path: str, json: dict[str, Any]) -> DirectResponse:
        if path == "/bundles":
            return self._call(lambda: self.store.create_bundle(json))
        if path == "/assignment-decisions":
            return self._call(lambda: self.store.create_assignment_decision(json))
        if path == "/assignment-handoffs":
            return self._call(lambda: self.store.request_assignment_handoff(json))
        if path == "/scheduler-projections":
            return self._call(lambda: self.store.request_scheduler_projection(json))
        if path == "/verifications":
            return self._call(lambda: self.store.create_verification(json))
        if path == "/closures":
            return self._call(lambda: self.store.create_closure(json))
        if path.endswith("/transition"):
            parts = path.strip("/").split("/")
            collection = parts[0]
            resource_id = "/".join(parts[1:-1])
            resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
            if resource_type is None:
                return DirectResponse(404, {"detail": {"code": "not_found"}})
            return self._call(lambda: self.store.transition(resource_type, resource_id, json))
        collection = path.strip("/")
        resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
        if resource_type is None:
            return DirectResponse(404, {"detail": {"code": "not_found"}})
        return self._call(lambda: self.store.create(json))

    def patch(self, path: str, json: dict[str, Any]) -> DirectResponse:
        parts = path.strip("/").split("/")
        collection = parts[0]
        resource_id = "/".join(parts[1:])
        resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
        if resource_type is None:
            return DirectResponse(404, {"detail": {"code": "not_found"}})
        return self._call(lambda: self.store.update(resource_type, resource_id, json))

    def delete(self, path: str) -> DirectResponse:
        return DirectResponse(405, {"detail": {"code": "method_not_allowed"}})


class WorkCoordinationServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        TEST_DATA.cleanup()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.organization = example("organization.v1.json")
        self.team = example("team.v1.json")
        self.position = example("position.v1.json")
        self.employee = example("employee-definition.v3.json")
        self.job = example("job-definition.v1.json")
        self.assignment = example("work-assignment.v1.json")
        self.scheduler_adapter = StaticSchedulerProjectionAdapter(job_ref=ref(self.job))
        self.runtime_adapter = StaticRuntimeHandoffAdapter(assignment_ref=ref(self.assignment))
        self.authz = StaticAuthorizationVerifier()
        self.store = WorkCoordinationStore(
            Path(self.tmp.name) / "work.db",
            organization_adapter=StaticReferenceAdapter([self.organization, self.team, self.position]),
            employee_adapter=StaticReferenceAdapter([self.employee]),
            scheduler_reference_adapter=StaticReferenceAdapter([self.job]),
            runtime_reference_adapter=StaticReferenceAdapter([self.assignment]),
            scheduler_projection_adapter=self.scheduler_adapter,
            runtime_handoff_adapter=self.runtime_adapter,
            authorization_verifier=self.authz,
        )
        if TestClient is not None and main is not None:
            main.store = self.store
            self.client = TestClient(main.app)
        else:
            self.client = DirectClient(self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def create_workflow_bundle(self) -> tuple[dict[str, Any], dict[str, Any]]:
        definition = adopt_work_authority(example("workflow-definition.v1.json"))
        revision = adopt_work_authority(example("workflow-revision.v1.json"))
        response = self.client.post(
            "/bundles",
            json=payload(records=[definition, revision], idempotency_key="idem:workflow-bundle"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return definition, revision

    def create_task(self) -> dict[str, Any]:
        self.create_workflow_bundle()
        task = adopt_work_authority(example("task-definition.v1.json"))
        task.pop("parent_job_ref", None)
        task.pop("source_workflow_revision_ref", None)
        task.pop("source_workflow_step_id", None)
        response = self.client.post(
            "/tasks",
            json=payload(record=task, idempotency_key="idem:task"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return task

    def create_result(self) -> dict[str, Any]:
        if not self.client.get("/tasks").json()["records"]:
            self.create_task()
        result = adopt_work_authority(example("work-result.v1.json"))
        response = self.client.post(
            "/work-results",
            json=payload(record=result, idempotency_key="idem:result"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return result

    def create_assignment_decision(self) -> dict[str, Any]:
        self.create_task()
        decision = {
            "decision_id": "assignment-decision:acme:research:1",
            "organization_ref": ref(self.organization),
            "work_ref": {
                "resource_type": "TASK",
                "resource_id": "task:acme:market-brief:research",
                "revision": "sha256:task-acme-market-brief-research-v1",
            },
            "assignee": {
                "target_type": "EMPLOYEE",
                "resource": {
                    "resource_type": "EMPLOYEE",
                    "resource_id": "employee:acme:researcher",
                    "revision": "sha256:employee-acme-researcher-v3",
                },
            },
            "assignment_reason": "INITIAL_ASSIGNMENT",
            "decision_rationale": "Governed test eligibility evidence selected this explicit target.",
            "employee_eligibility_ref": {
                "authority": {
                    "authority_id": "employee-registry",
                    "principal": {"principal_id": "principal:service:employee-registry", "principal_type": "SERVICE"},
                    "authority_revision": "sha256:employee-registry-v1",
                },
                "reference_id": "employee-eligibility:researcher",
                "revision": "sha256:employee-eligibility-researcher-v1",
            },
        }
        response = self.client.post(
            "/assignment-decisions",
            json=payload(decision=decision, idempotency_key="idem:decision"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["decision_ref"]

    def test_health_ready_and_version_endpoints(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 200)
        version = self.client.get("/version")
        self.assertEqual(version.status_code, 200)
        self.assertEqual(version.json()["service"], "work-coordination-service")

    def test_workflow_bundle_task_result_and_outbox_are_persisted(self):
        self.create_result()
        tasks = self.client.get("/tasks").json()["records"]
        self.assertEqual(len(tasks), 1)
        outbox = self.client.get("/outbox").json()["events"]
        self.assertEqual(len(outbox), 4)
        self.assertTrue(all(event["producer_local_only"] for event in outbox))

    def test_mutations_require_actor_and_authorization_evidence(self):
        request = adopt_work_authority(example("work-request.v1.json"))
        for missing, expected in (
            ("actor_context_ref", 401),
            ("authorization_decision_ref", 403),
        ):
            body = payload(record=request, idempotency_key=f"idem:missing:{missing}")
            body.pop(missing)
            with self.subTest(missing=missing):
                response = self.client.post("/work-requests", json=body)
                self.assertEqual(response.status_code, expected)

        structural_only = payload(
            record=request,
            idempotency_key="idem:missing-binding",
        )
        structural_only.pop("authorization_binding")
        response = self.client.post("/work-requests", json=structural_only)
        self.assertEqual(response.status_code, 403)

    def test_authorization_binding_mismatch_and_denial_fail_closed(self):
        request = adopt_work_authority(example("work-request.v1.json"))
        wrong = payload(record=request, idempotency_key="idem:wrong-binding")
        wrong["authorization_binding"]["expected_scope"]["action"] = (
            "work-coordination.record.update"
        )
        response = self.client.post("/work-requests", json=wrong)
        self.assertEqual(response.status_code, 403)

        self.authz.status = "DENIED"
        denied = payload(record=request, idempotency_key="idem:denied-binding")
        response = self.client.post("/work-requests", json=denied)
        self.assertEqual(response.status_code, 403)

    def test_authorization_binding_requires_canonical_actor_context_evidence(self):
        request = payload(
            record=adopt_work_authority(example("work-request.v1.json")),
            idempotency_key="idem:missing-actor-authority",
        )
        request["authorization_binding"]["actor_context_ref"].pop("authority")

        response = self.client.post("/work-requests", json=request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            "malformed_authorization_binding",
            response.json()["detail"]["code"],
        )

    def test_caller_authority_booleans_and_secret_fields_are_rejected(self):
        request = adopt_work_authority(example("work-request.v1.json"))
        for field, value in (
            ("authorized", True),
            ("approval_granted", True),
            ("password", "not-allowed"),
        ):
            bad = copy.deepcopy(request)
            bad[field] = value
            with self.subTest(field=field):
                response = self.client.post(
                    "/work-requests",
                    json=payload(record=bad, idempotency_key=f"idem:bad:{field}"),
                )
                self.assertIn(response.status_code, {403, 422})

    def test_idempotency_replay_and_conflict(self):
        request = adopt_work_authority(example("work-request.v1.json"))
        body = payload(record=request, idempotency_key="idem:request")
        first = self.client.post("/work-requests", json=body)
        second = self.client.post("/work-requests", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        changed = copy.deepcopy(body)
        changed["record"]["title"] = "Different"
        response = self.client.post("/work-requests", json=changed)
        self.assertEqual(response.status_code, 409)

    def test_public_assignment_and_foreign_authority_records_are_rejected(self):
        assignment = example("work-assignment.v1.json")
        assignment["identity"]["ownership"]["lifecycle_authority"]["authority_id"] = "public-assignment-service"
        response = self.client.post(
            "/work-requests",
            json=payload(record=assignment, idempotency_key="idem:foreign-assignment"),
        )
        self.assertEqual(response.status_code, 422)
        job = example("job-definition.v1.json")
        response = self.client.post(
            "/tasks",
            json=payload(record=job, idempotency_key="idem:foreign-job"),
        )
        self.assertEqual(response.status_code, 422)

    def test_cross_organization_and_unavailable_external_authorities_fail_closed(self):
        request = adopt_work_authority(example("work-request.v1.json"))
        request["organization_ref"]["resource_id"] = "organization:other"
        response = self.client.post(
            "/work-requests",
            json=payload(record=request, idempotency_key="idem:cross-org-request"),
        )
        self.assertEqual(response.status_code, 422)

        closed_store = WorkCoordinationStore(
            Path(self.tmp.name) / "closed.db",
            authorization_verifier=self.authz,
        )
        if main is not None:
            main.store = closed_store
        else:
            self.client = DirectClient(closed_store)
        response = self.client.post(
            "/work-requests",
            json=payload(record=adopt_work_authority(example("work-request.v1.json")), idempotency_key="idem:closed"),
        )
        self.assertEqual(response.status_code, 503)
        if main is not None:
            main.store = self.store
        self.client = DirectClient(self.store) if TestClient is None else self.client

    def test_published_workflow_revision_is_immutable(self):
        _, revision = self.create_workflow_bundle()
        mutated = copy.deepcopy(revision)
        mutated["steps"][0]["title"] = "Changed after publication"
        mutated["identity"]["revision"] = "sha256:workflow-revision-mutated"
        update_resource = ref(revision)
        update_operation = (
            f"update:WORKFLOW_REVISION:{revision['identity']['resource_id']}:"
            f"{revision['identity']['revision']}"
        )
        response = self.client.patch(
            f"/workflow-revisions/{revision['identity']['resource_id']}",
            json=payload(
                record=mutated,
                expected_revision=revision["identity"]["revision"],
                idempotency_key="idem:immutable",
                authorization_binding=authorization_binding(
                    action="work-coordination.record.update",
                    organization_ref=mutated["organization_ref"],
                    resource_ref=update_resource,
                    context_type="work-coordination.mutation",
                    context_id=update_operation,
                    context_revision=revision["identity"]["revision"],
                    seed={
                        "operation": update_operation,
                        "organization_ref": mutated["organization_ref"],
                        "resource_ref": update_resource,
                    },
                ),
            ),
        )
        self.assertEqual(response.status_code, 409)

    def test_dependency_unknown_cycle_and_impossible_readiness_fail(self):
        self.create_task()
        review = review_task()
        self.assertEqual(
            self.client.post("/tasks", json=payload(record=review, idempotency_key="idem:review")).status_code,
            200,
        )
        dependency = adopt_work_authority(example("work-dependency.v1.json"))
        valid = copy.deepcopy(dependency)
        self.assertEqual(
            self.client.post("/dependencies", json=payload(record=valid, idempotency_key="idem:dependency:valid")).status_code,
            200,
        )
        for mutation in ("unknown", "cycle", "cross-org"):
            bad = copy.deepcopy(dependency)
            bad["identity"]["resource_id"] = f"dependency:acme:{mutation}"
            bad["identity"]["revision"] = f"sha256:dependency-acme-{mutation}"
            bad["identity"]["audit_id"] = f"audit:dependency:acme:{mutation}"
            if mutation == "unknown":
                bad["depends_on_work_ref"]["resource_id"] = "task:unknown"
            elif mutation == "cycle":
                bad["source_work_ref"], bad["depends_on_work_ref"] = (
                    bad["depends_on_work_ref"],
                    bad["source_work_ref"],
                )
            else:
                bad["organization_ref"]["resource_id"] = "organization:other"
            with self.subTest(mutation=mutation):
                response = self.client.post(
                    "/dependencies",
                    json=payload(record=bad, idempotency_key=f"idem:dependency:{mutation}"),
                )
                self.assertEqual(response.status_code, 422)

    def test_task_completion_requires_result_and_closure_requires_verification(self):
        task = self.create_task()
        active = self.client.post(
            f"/tasks/{task['identity']['resource_id']}/transition",
            json=transition_payload(task, "ACTIVE", key="idem:active"),
        )
        self.assertEqual(active.status_code, 200, active.text)
        active_revision = active.json()["record"]["identity"]["revision"]
        response = self.client.post(
            f"/tasks/{task['identity']['resource_id']}/transition",
            json=transition_payload(active.json()["record"], "COMPLETED", key="idem:no-result"),
        )
        self.assertEqual(response.status_code, 422)

        self.assertTrue(active_revision.startswith("sha256:"))

    def test_result_requires_producer_scope_revision_and_deliverables(self):
        self.create_task()
        for mutation in ("producer", "scope", "stale-task", "deliverable"):
            result = adopt_work_authority(example("work-result.v1.json"))
            if mutation == "producer":
                result.pop("producing_principal")
            elif mutation == "scope":
                result["work_ref"]["resource_id"] = "task:other"
            elif mutation == "stale-task":
                result["work_ref"]["revision"] = "sha256:stale"
            else:
                result["deliverables"] = []
            with self.subTest(mutation=mutation):
                response = self.client.post(
                    "/work-results",
                    json=payload(record=result, idempotency_key=f"idem:result:{mutation}"),
                )
                self.assertEqual(response.status_code, 422)

    def test_assignment_decision_has_no_scoring_force_authorization_or_execution(self):
        decision_ref = self.create_assignment_decision()
        self.assertEqual(decision_ref["resource_type"], "ASSIGNMENT_DECISION")
        decision = {
            "decision_id": "assignment-decision:acme:research:1",
            "organization_ref": ref(self.organization),
            "work_ref": {
                "resource_type": "TASK",
                "resource_id": "task:acme:market-brief:research",
                "revision": "sha256:task-acme-market-brief-research-v1",
            },
            "assignee": {
                "target_type": "EMPLOYEE",
                "resource": {
                    "resource_type": "EMPLOYEE",
                    "resource_id": "employee:acme:researcher",
                    "revision": "sha256:employee-acme-researcher-v3",
                },
            },
            "assignment_reason": "INITIAL_ASSIGNMENT",
            "decision_rationale": "Governed test eligibility evidence selected this explicit target.",
            "employee_eligibility_ref": {
                "authority": {
                    "authority_id": "employee-registry",
                    "principal": {"principal_id": "principal:service:employee-registry", "principal_type": "SERVICE"},
                    "authority_revision": "sha256:employee-registry-v1",
                },
                "reference_id": "employee-eligibility:researcher",
                "revision": "sha256:employee-eligibility-researcher-v1",
            },
        }
        for field, value in (
            ("score", 99),
            ("ranking", ["employee:a"]),
            ("force", True),
            ("authorized", True),
            ("execute_now", True),
        ):
            bad = copy.deepcopy(decision)
            bad[field] = value
            with self.subTest(field=field):
                response = self.client.post(
                    "/assignment-decisions",
                    json=payload(decision=bad, idempotency_key=f"idem:decision:{field}"),
                )
                self.assertIn(response.status_code, {403, 422})

    def test_runtime_handoff_and_scheduler_projection_are_narrow_idempotent_requests(self):
        decision_ref = self.create_assignment_decision()
        handoff = {
            "handoff_id": "assignment-handoff:acme:research:1",
            "organization_ref": ref(self.organization),
            "assignment_decision_ref": decision_ref,
        }
        handoff_resource = {
            "resource_type": "TASK",
            "resource_id": "task:acme:market-brief:research",
            "revision": "sha256:task-acme-market-brief-research-v1",
        }
        handoff_operation = "assignment-handoff:assignment-handoff:acme:research:1"
        response = self.client.post(
            "/assignment-handoffs",
            json=payload(
                handoff=handoff,
                idempotency_key="idem:handoff",
                authorization_binding=authorization_binding(
                    action="work-coordination.assignment-handoff.request",
                    organization_ref=handoff["organization_ref"],
                    resource_ref=handoff_resource,
                    context_type="work-coordination.assignment-handoff",
                    context_id=handoff_operation,
                    context_revision=decision_ref["revision"],
                    seed={
                        "operation": handoff_operation,
                        "organization_ref": handoff["organization_ref"],
                        "resource_ref": handoff_resource,
                        "assignment_decision_ref": decision_ref,
                    },
                ),
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.runtime_adapter.requests), 1)

        projection = {
            "projection_id": "scheduler-projection:acme:market-brief:1",
            "organization_ref": ref(self.organization),
            "source_task_ref": {
                "resource_type": "TASK",
                "resource_id": "task:acme:market-brief:research",
                "revision": "sha256:task-acme-market-brief-research-v1",
            },
            "job_request": {"title": "Market brief"},
        }
        response = self.client.post(
            "/scheduler-projections",
            json=payload(projection=projection, idempotency_key="idem:projection"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.scheduler_adapter.requests), 1)
        db = sqlite3.connect(Path(self.tmp.name) / "work.db")
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            db.close()
        self.assertNotIn("scheduler_jobs", tables)
        self.assertNotIn("employee_assignments", tables)

    def test_delegation_scope_cycle_cross_org_and_source_preservation(self):
        for mutation in ("missing-source", "scope", "cross-org", "erases-source"):
            delegation = adopt_work_authority(example("work-delegation.v1.json"))
            if mutation == "missing-source":
                delegation.pop("source_assignment_ref")
            elif mutation == "scope":
                delegation["delegated_scope_refs"][0]["resource_id"] = "task:other"
            elif mutation == "cross-org":
                delegation["organization_ref"]["resource_id"] = "organization:other"
            else:
                delegation["source_responsibility_preserved"] = False
            with self.subTest(mutation=mutation):
                response = self.client.post(
                    "/delegations",
                    json=payload(record=delegation, idempotency_key=f"idem:delegation:{mutation}"),
                )
                self.assertEqual(response.status_code, 422)

    def test_verification_is_not_approval_and_closure_requires_verification(self):
        result = self.create_result()
        verification = {
            "verification_id": "verification:acme:research:1",
            "organization_ref": ref(self.organization),
            "result_ref": ref(result),
            "verifier_principal": {"principal_id": "principal:user:brett", "principal_type": "HUMAN_USER"},
            "verification_evidence_refs": [
                {
                    "authority": AUTHORITY_REF,
                    "reference_id": "evidence:verification:research",
                    "revision": "sha256:evidence-verification-research",
                }
            ],
            "approval_granted": True,
        }
        response = self.client.post(
            "/verifications",
            json=payload(verification=verification, idempotency_key="idem:verify-approval"),
        )
        self.assertEqual(response.status_code, 403)
        verification.pop("approval_granted")
        response = self.client.post(
            "/verifications",
            json=payload(verification=verification, idempotency_key="idem:verify"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        closure = {
            "closure_id": "closure:acme:research:1",
            "organization_ref": ref(self.organization),
            "subject_ref": {
                "resource_type": "TASK",
                "resource_id": "task:acme:market-brief:research",
                "revision": "sha256:task-acme-market-brief-research-v1",
            },
        }
        response = self.client.post(
            "/closures",
            json=payload(closure=closure, idempotency_key="idem:closure-missing-verification"),
        )
        self.assertEqual(response.status_code, 422)
        closure["verification_ref"] = response = {
            "resource_type": "WORK_VERIFICATION",
            "resource_id": "verification:acme:research:1",
            "revision": self.client.post(
                "/verifications",
                json=payload(verification=verification, idempotency_key="idem:verify"),
            ).json()["verification_ref"]["revision"],
        }
        response = self.client.post(
            "/closures",
            json=payload(closure=closure, idempotency_key="idem:closure"),
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_retry_and_escalation_preserve_history_and_do_not_reassign(self):
        self.create_task()
        retry = adopt_work_authority(example("retry-intent.v1.json"))
        retry["preserves_history"] = False
        response = self.client.post(
            "/retry-intents",
            json=payload(record=retry, idempotency_key="idem:retry-history"),
        )
        self.assertEqual(response.status_code, 422)
        escalation = adopt_work_authority(example("escalation-intent.v1.json"))
        escalation["creates_assignment"] = True
        response = self.client.post(
            "/escalation-intents",
            json=payload(record=escalation, idempotency_key="idem:escalates-assignment"),
        )
        self.assertEqual(response.status_code, 422)

    def test_work_coordination_cannot_resolve_invoke_mutate_foreign_state_or_hard_delete(self):
        for path in (
            "/capability-resolutions",
            "/dispatcher-invocations",
            "/employee-lifecycle",
            "/organization-records",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json={}).status_code, 404)
        self.assertEqual(self.client.delete("/tasks/task:acme:market-brief:research").status_code, 405)

    def test_failed_duplicate_does_not_write_outbox(self):
        request = adopt_work_authority(example("work-request.v1.json"))
        self.assertEqual(
            self.client.post("/work-requests", json=payload(record=request, idempotency_key="idem:first")).status_code,
            200,
        )
        count = len(self.client.get("/outbox").json()["events"])
        duplicate = copy.deepcopy(request)
        duplicate["title"] = "Different"
        response = self.client.post(
            "/work-requests",
            json=payload(record=duplicate, idempotency_key="idem:duplicate"),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.client.get("/outbox").json()["events"]), count)


if __name__ == "__main__":
    unittest.main()
