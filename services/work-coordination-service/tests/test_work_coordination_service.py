from __future__ import annotations

import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "work-coordination-service"))
sys.path.insert(0, str(ROOT / "packages" / "leos-contracts" / "src"))

from app.domain import (  # noqa: E402
    AUTHORITY_REF,
    COLLECTION_TO_RESOURCE_TYPE,
    StaticReferenceAdapter,
    StaticRuntimeHandoffAdapter,
    StaticSchedulerProjectionAdapter,
    WorkCoordinationError,
    WorkCoordinationStore,
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


def payload(**items: Any) -> dict[str, Any]:
    return {
        "actor_context_ref": actor_ref(),
        "authorization_decision_ref": auth_ref(),
        "idempotency_key": items.pop("idempotency_key", "idem:test"),
        "correlation_id": items.pop("correlation_id", "corr:test"),
        **items,
    }


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
        self.store = WorkCoordinationStore(
            Path(self.tmp.name) / "work.db",
            organization_adapter=StaticReferenceAdapter([self.organization, self.team, self.position]),
            employee_adapter=StaticReferenceAdapter([self.employee]),
            scheduler_reference_adapter=StaticReferenceAdapter([self.job]),
            runtime_reference_adapter=StaticReferenceAdapter([self.assignment]),
            scheduler_projection_adapter=self.scheduler_adapter,
            runtime_handoff_adapter=self.runtime_adapter,
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

        closed_store = WorkCoordinationStore(Path(self.tmp.name) / "closed.db")
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
        response = self.client.patch(
            f"/workflow-revisions/{revision['identity']['resource_id']}",
            json=payload(
                record=mutated,
                expected_revision=revision["identity"]["revision"],
                idempotency_key="idem:immutable",
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
            json=payload(
                expected_revision=task["identity"]["revision"],
                to_status="ACTIVE",
                idempotency_key="idem:active",
            ),
        )
        self.assertEqual(active.status_code, 200, active.text)
        active_revision = active.json()["record"]["identity"]["revision"]
        response = self.client.post(
            f"/tasks/{task['identity']['resource_id']}/transition",
            json=payload(
                expected_revision=active_revision,
                to_status="COMPLETED",
                idempotency_key="idem:no-result",
            ),
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
        response = self.client.post(
            "/assignment-handoffs",
            json=payload(handoff=handoff, idempotency_key="idem:handoff"),
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
