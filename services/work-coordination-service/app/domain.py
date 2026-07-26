from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

from leos_contracts import ContractValidationError, validate_contract, validate_work_domain
from leos_contracts.work_domain import TRANSITIONS


SERVICE_ID = "work-coordination-service"
SERVICE_VERSION = "0.2.0-dev-preview-v2"
SERVICE_CONTRACT = "leos.work-coordination-service.provisional-v1"
AUTHORITY_ID = "work-coordination-service"
AUTHORITY_REVISION = "sha256:work-coordination-service-v1"
AUTHORITY_PRINCIPAL = {
    "principal_id": "principal:service:work-coordination",
    "principal_type": "SERVICE",
}
AUTHORITY_REF = {
    "authority_id": AUTHORITY_ID,
    "principal": AUTHORITY_PRINCIPAL,
    "authority_revision": AUTHORITY_REVISION,
}
EVENT_SOURCE_REF = {
    "resource_type": "EVENT_SOURCE",
    "resource_id": "event-source:work-coordination-service",
    "revision": "sha256:event-source-work-coordination-service-v1",
}

CONTRACT_BY_RESOURCE_TYPE = {
    "WORK_REQUEST": "leos.work-request.v1",
    "WORKFLOW_DEFINITION": "leos.workflow-definition.v1",
    "WORKFLOW_REVISION": "leos.workflow-revision.v1",
    "TASK": "leos.task-definition.v1",
    "WORK_DEPENDENCY": "leos.work-dependency.v1",
    "WORK_DELEGATION": "leos.work-delegation.v1",
    "WORK_RESULT": "leos.work-result.v1",
    "RETRY_INTENT": "leos.retry-intent.v1",
    "ESCALATION_INTENT": "leos.escalation-intent.v1",
}
COLLECTION_TO_RESOURCE_TYPE = {
    "work-requests": "WORK_REQUEST",
    "workflow-definitions": "WORKFLOW_DEFINITION",
    "workflow-revisions": "WORKFLOW_REVISION",
    "tasks": "TASK",
    "dependencies": "WORK_DEPENDENCY",
    "delegations": "WORK_DELEGATION",
    "work-results": "WORK_RESULT",
    "retry-intents": "RETRY_INTENT",
    "escalation-intents": "ESCALATION_INTENT",
}
RESOURCE_TYPE_TO_COLLECTION = {
    resource_type: collection
    for collection, resource_type in COLLECTION_TO_RESOURCE_TYPE.items()
}
EXTERNAL_REFERENCE_TYPES = {
    "ORGANIZATION",
    "DEPARTMENT",
    "TEAM",
    "POSITION",
    "EMPLOYEE",
    "SCHEDULER_JOB",
    "WORK_ASSIGNMENT",
}
RAW_SECRET_KEYS = {
    "api_key",
    "access_token",
    "auth_token",
    "client_secret",
    "credential",
    "credential_value",
    "credentials",
    "password",
    "private_key",
    "private_key_pem",
    "refresh_token",
    "secret",
    "secret_value",
}
CALLER_AUTHORITY_BOOLEAN_KEYS = {
    "authorized",
    "authorization_granted",
    "approval_granted",
    "approved",
    "verified",
    "is_authorized",
    "is_approved",
    "force",
    "force_assign",
}
FORBIDDEN_SELECTION_KEYS = {
    "selected_employee",
    "selected_employee_ref",
    "employee_score",
    "employee_scores",
    "ranked_employee_ids",
    "matching_score",
    "optimization_score",
    "selected_provider_id",
    "provider_id",
    "tool_id",
    "execute_now",
    "dispatcher_request",
}

logger = logging.getLogger(SERVICE_ID)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def revision_for(value: dict[str, Any]) -> str:
    clone = json.loads(canonical_json(value))
    identity = clone.get("identity")
    if isinstance(identity, dict):
        identity.pop("revision", None)
        identity.pop("updated_at", None)
    return "sha256:" + hashlib.sha256(canonical_json(clone).encode()).hexdigest()


def evidence_revision_for(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def parse_json(value: str) -> dict[str, Any]:
    return json.loads(value)


def resource_key(document: dict[str, Any]) -> tuple[str, str]:
    identity = require_dict(document.get("identity"), "identity")
    resource_type = identity.get("resource_type")
    resource_id = identity.get("resource_id")
    if not isinstance(resource_type, str) or not isinstance(resource_id, str):
        raise ValidationFailure("identity must include resource_type and resource_id")
    return resource_type, resource_id


def resource_ref(document: dict[str, Any]) -> dict[str, str]:
    identity = document["identity"]
    return {
        "resource_type": identity["resource_type"],
        "resource_id": identity["resource_id"],
        "revision": identity["revision"],
    }


def require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationFailure(f"{field} must be an object")
    return value


def organization_id_for(document: dict[str, Any]) -> str:
    organization_ref = require_dict(document.get("organization_ref"), "organization_ref")
    if organization_ref.get("resource_type") != "ORGANIZATION":
        raise ValidationFailure("organization_ref must reference an ORGANIZATION")
    organization_id = organization_ref.get("resource_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise ValidationFailure("organization_ref.resource_id is required")
    return organization_id


def status_for(document: dict[str, Any]) -> str:
    status = document.get("status")
    return status if isinstance(status, str) else ""


class WorkCoordinationError(RuntimeError):
    status_code = 422
    code = "work_coordination_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class NotFoundError(WorkCoordinationError):
    status_code = 404
    code = "not_found"


class ConflictError(WorkCoordinationError):
    status_code = 409
    code = "conflict"


class StaleRevisionError(WorkCoordinationError):
    status_code = 409
    code = "stale_revision"


class DependencyUnavailableError(WorkCoordinationError):
    status_code = 503
    code = "dependency_unavailable"


class ValidationFailure(WorkCoordinationError):
    status_code = 422
    code = "validation_failure"


def reject_raw_secret_values(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in RAW_SECRET_KEYS:
                raise ValidationFailure(
                    "raw credential or secret fields are prohibited",
                    code="raw_secret_prohibited",
                    details={"path": f"{path}.{key}"},
                )
            reject_raw_secret_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_raw_secret_values(child, f"{path}[{index}]")


def reject_caller_authority_claims(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in CALLER_AUTHORITY_BOOLEAN_KEYS and isinstance(child, bool):
                raise WorkCoordinationError(
                    "caller-supplied authority booleans are prohibited",
                    code="caller_authority_claim_rejected",
                    status_code=403,
                    details={"path": f"{path}.{key}"},
                )
            if normalized in FORBIDDEN_SELECTION_KEYS:
                raise ValidationFailure(
                    "selection, scoring, provider, tool, or execution fields are prohibited",
                    code="authority_boundary_violation",
                    details={"path": f"{path}.{key}"},
                )
            reject_caller_authority_claims(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_caller_authority_claims(child, f"{path}[{index}]")


def validate_actor_context_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("resource_type") != "ACTOR_CONTEXT":
        raise WorkCoordinationError(
            "missing or malformed Actor Context evidence",
            code="missing_actor_context",
            status_code=401,
        )
    if not value.get("resource_id") or not value.get("revision"):
        raise WorkCoordinationError(
            "Actor Context evidence must be revision-pinned",
            code="missing_actor_context",
            status_code=401,
        )
    return value


def validate_authorization_decision_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("resource_type") != "AUTHORIZATION_DECISION":
        raise WorkCoordinationError(
            "missing or malformed Authorization Decision evidence",
            code="missing_authorization_evidence",
            status_code=403,
        )
    if not value.get("resource_id") or not value.get("revision"):
        raise WorkCoordinationError(
            "Authorization Decision evidence must be revision-pinned",
            code="missing_authorization_evidence",
            status_code=403,
        )
    return value


def collect_refs(value: Any, refs: set[tuple[str, str, str]]) -> None:
    if isinstance(value, dict):
        resource_type = value.get("resource_type")
        resource_id = value.get("resource_id")
        revision = value.get("revision")
        if isinstance(resource_type, str) and isinstance(resource_id, str) and isinstance(revision, str):
            refs.add((resource_type, resource_id, revision))
        for child in value.values():
            collect_refs(child, refs)
    elif isinstance(value, list):
        for child in value:
            collect_refs(child, refs)


def target_key(target: dict[str, Any]) -> tuple[str, str] | None:
    target_type = target.get("target_type")
    if target_type == "PRINCIPAL":
        principal = target.get("principal")
        if isinstance(principal, dict):
            return "PRINCIPAL", str(principal.get("principal_id"))
        return None
    resource = target.get("resource")
    if isinstance(resource, dict):
        return resource.get("resource_type"), resource.get("resource_id")
    return None


@dataclass(frozen=True)
class MutationContext:
    actor_context_ref: dict[str, Any]
    authorization_decision_ref: dict[str, Any]
    idempotency_key: str | None
    correlation_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MutationContext":
        reject_raw_secret_values(payload)
        reject_caller_authority_claims(payload)
        actor = validate_actor_context_ref(payload.get("actor_context_ref"))
        authorization = validate_authorization_decision_ref(payload.get("authorization_decision_ref"))
        idempotency_key = payload.get("idempotency_key")
        if idempotency_key is not None and not str(idempotency_key).strip():
            raise ValidationFailure("idempotency_key must be non-empty when supplied")
        return cls(
            actor_context_ref=actor,
            authorization_decision_ref=authorization,
            idempotency_key=str(idempotency_key) if idempotency_key else None,
            correlation_id=str(payload.get("correlation_id") or idempotency_key or uuid.uuid4()),
        )


class ReferenceAdapter(Protocol):
    def documents_for_references(self, refs: set[tuple[str, str, str]]) -> list[dict[str, Any]]:
        ...


class NoReferenceAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def documents_for_references(self, refs: set[tuple[str, str, str]]) -> list[dict[str, Any]]:
        if refs:
            raise DependencyUnavailableError(
                f"{self.name} reference validation is unavailable",
                details={"references": [list(ref) for ref in sorted(refs)]},
            )
        return []


class StaticReferenceAdapter:
    """Deterministic test adapter; not a foreign lifecycle authority."""

    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self._documents: dict[tuple[str, str], dict[str, Any]] = {}
        for document in documents or []:
            self.add(document)

    def add(self, document: dict[str, Any]) -> None:
        self._documents[resource_key(document)] = document

    def documents_for_references(self, refs: set[tuple[str, str, str]]) -> list[dict[str, Any]]:
        documents: dict[tuple[str, str], dict[str, Any]] = {}
        missing: list[tuple[str, str, str]] = []
        stale: list[tuple[str, str, str]] = []
        for resource_type, resource_id, revision in refs:
            document = self._documents.get((resource_type, resource_id))
            if document is None:
                missing.append((resource_type, resource_id, revision))
            elif document["identity"]["revision"] != revision:
                stale.append((resource_type, resource_id, revision))
            else:
                documents[(resource_type, resource_id)] = document
        if missing or stale:
            raise ValidationFailure(
                "reference cannot be validated by external authority evidence",
                code="invalid_external_reference",
                details={
                    "missing": [list(ref) for ref in missing],
                    "stale": [list(ref) for ref in stale],
                },
            )
        return list(documents.values())


class SchedulerProjectionAdapter(Protocol):
    def request_job_projection(self, projection: dict[str, Any]) -> dict[str, Any]:
        ...


class RuntimeHandoffAdapter(Protocol):
    def request_assignment_handoff(self, handoff: dict[str, Any]) -> dict[str, Any]:
        ...


class UnavailableSchedulerProjectionAdapter:
    def request_job_projection(self, projection: dict[str, Any]) -> dict[str, Any]:
        raise DependencyUnavailableError("Scheduler projection adapter is unavailable")


class UnavailableRuntimeHandoffAdapter:
    def request_assignment_handoff(self, handoff: dict[str, Any]) -> dict[str, Any]:
        raise DependencyUnavailableError("Persistent Runtime handoff adapter is unavailable")


class StaticSchedulerProjectionAdapter:
    """Deterministic test adapter; never writes Scheduler state directly."""

    def __init__(self, *, accepted: bool = True, job_ref: dict[str, Any] | None = None) -> None:
        self.accepted = accepted
        self.job_ref = job_ref or {
            "resource_type": "SCHEDULER_JOB",
            "resource_id": "job:test:projection",
            "revision": "sha256:job-test-projection",
        }
        self.requests: list[dict[str, Any]] = []

    def request_job_projection(self, projection: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(json.loads(canonical_json(projection)))
        return {
            "status": "ACCEPTED" if self.accepted else "REJECTED",
            "job_ref": self.job_ref if self.accepted else None,
            "scheduler_authority": "execution-scheduler-service",
        }


class StaticRuntimeHandoffAdapter:
    """Deterministic test adapter; never writes Persistent Runtime state directly."""

    def __init__(
        self,
        *,
        accepted: bool = True,
        assignment_ref: dict[str, Any] | None = None,
    ) -> None:
        self.accepted = accepted
        self.assignment_ref = assignment_ref or {
            "resource_type": "WORK_ASSIGNMENT",
            "resource_id": "assignment:test:handoff",
            "revision": "sha256:assignment-test-handoff",
        }
        self.requests: list[dict[str, Any]] = []

    def request_assignment_handoff(self, handoff: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(json.loads(canonical_json(handoff)))
        return {
            "status": "ACCEPTED" if self.accepted else "REJECTED",
            "assignment_ref": self.assignment_ref if self.accepted else None,
            "runtime_authority": "persistent-employee-runtime-service",
        }


class WorkCoordinationStore:
    def __init__(
        self,
        database: str | Path,
        *,
        organization_adapter: ReferenceAdapter | None = None,
        employee_adapter: ReferenceAdapter | None = None,
        scheduler_reference_adapter: ReferenceAdapter | None = None,
        runtime_reference_adapter: ReferenceAdapter | None = None,
        scheduler_projection_adapter: SchedulerProjectionAdapter | None = None,
        runtime_handoff_adapter: RuntimeHandoffAdapter | None = None,
    ) -> None:
        self.database = Path(database)
        self.organization_adapter = organization_adapter or NoReferenceAdapter("Organization Domain")
        self.employee_adapter = employee_adapter or NoReferenceAdapter("Employee Registry")
        self.scheduler_reference_adapter = scheduler_reference_adapter or NoReferenceAdapter("Scheduler")
        self.runtime_reference_adapter = runtime_reference_adapter or NoReferenceAdapter("Persistent Runtime")
        self.scheduler_projection_adapter = scheduler_projection_adapter or UnavailableSchedulerProjectionAdapter()
        self.runtime_handoff_adapter = runtime_handoff_adapter or UnavailableRuntimeHandoffAdapter()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def migrate(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS work_records (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    status TEXT,
                    revision TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id)
                );
                CREATE INDEX IF NOT EXISTS idx_work_records_org
                    ON work_records (organization_id, resource_type, resource_id);
                CREATE TABLE IF NOT EXISTS work_record_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    prior_revision TEXT,
                    new_revision TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    actor_context_ref_json TEXT NOT NULL,
                    authorization_decision_ref_json TEXT NOT NULL,
                    idempotency_key TEXT,
                    event_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    document_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS work_transitions (
                    transition_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    prior_revision TEXT NOT NULL,
                    new_revision TEXT NOT NULL,
                    transition_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS work_outbox (
                    event_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_revision TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    delivered_at TEXT
                );
                CREATE TABLE IF NOT EXISTS work_idempotency (
                    idempotency_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (idempotency_key, operation)
                );
                CREATE TABLE IF NOT EXISTS assignment_decisions (
                    decision_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    work_ref_json TEXT NOT NULL,
                    assignee_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assignment_handoffs (
                    handoff_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    handoff_json TEXT NOT NULL,
                    runtime_response_json TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scheduler_projections (
                    projection_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    projection_json TEXT NOT NULL,
                    scheduler_response_json TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS verification_records (
                    verification_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    verification_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS closure_records (
                    closure_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    subject_ref_json TEXT NOT NULL,
                    closure_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def health(self) -> dict[str, Any]:
        with self.connect() as db:
            record_count = db.execute("SELECT COUNT(*) AS count FROM work_records").fetchone()["count"]
            outbox_count = db.execute("SELECT COUNT(*) AS count FROM work_outbox").fetchone()["count"]
        return {
            "ok": True,
            "service": SERVICE_ID,
            "version": SERVICE_VERSION,
            "service_contract": SERVICE_CONTRACT,
            "database": str(self.database),
            "record_count": record_count,
            "outbox_count": outbox_count,
        }

    def ready(self) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"ok": True, "service": SERVICE_ID, "state": "ready", "database": str(self.database)}

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = require_dict(payload.get("record"), "record")
        context = MutationContext.from_payload(payload)
        self._validate_canonical_record(record)
        operation = f"create:{record['identity']['resource_type']}:{record['identity']['resource_id']}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        organization_id = organization_id_for(record)
        with self.connect() as db:
            existing = self._get_record_row(db, record["identity"]["resource_type"], record["identity"]["resource_id"])
            if existing is not None:
                existing_doc = parse_json(existing["document_json"])
                if canonical_json(existing_doc) == canonical_json(record):
                    response = {"ok": True, "changed": False, "record": existing_doc}
                    self._store_idempotent_response(db, context, operation, payload, response)
                    return response
                raise ConflictError("canonical resource identity already exists", code="duplicate_resource_identity")
            self._validate_bundle(db, organization_id, candidate=record)
            event = self._build_event(
                record,
                context,
                "work-coordination.record.created",
                {
                    "operation": "CREATE",
                    "resource_type": record["identity"]["resource_type"],
                    "resource_id": record["identity"]["resource_id"],
                    "resulting_revision": record["identity"]["revision"],
                },
            )
            self._insert_record(db, record)
            self._append_event(db, organization_id, record, event)
            self._append_history(db, record, None, "CREATE", context, event["identity"]["resource_id"])
            response = {"ok": True, "changed": True, "record": record, "outbox_event": resource_ref(event)}
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def create_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise ValidationFailure("records must be a non-empty array")
        context = MutationContext.from_payload(payload)
        for record in records:
            self._validate_canonical_record(require_dict(record, "record"))
        keys = [resource_key(record) for record in records]
        if len(keys) != len(set(keys)):
            raise ValidationFailure("bundle contains duplicate canonical identities")
        organization_ids = {organization_id_for(record) for record in records}
        if len(organization_ids) != 1:
            raise ValidationFailure("bundle cannot cross Organization boundaries")
        organization_id = next(iter(organization_ids))
        operation = "bundle-create:" + evidence_revision_for({"records": records})
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        with self.connect() as db:
            for resource_type, resource_id in keys:
                if self._get_record_row(db, resource_type, resource_id) is not None:
                    raise ConflictError("canonical resource identity already exists", code="duplicate_resource_identity")
            self._validate_bundle_many(db, organization_id, candidates=records)
            created: list[dict[str, Any]] = []
            events: list[dict[str, Any]] = []
            for record in records:
                event = self._build_event(
                    record,
                    context,
                    "work-coordination.record.created",
                    {
                        "operation": "CREATE",
                        "resource_type": record["identity"]["resource_type"],
                        "resource_id": record["identity"]["resource_id"],
                        "resulting_revision": record["identity"]["revision"],
                    },
                )
                self._insert_record(db, record)
                self._append_event(db, organization_id, record, event)
                self._append_history(db, record, None, "CREATE", context, event["identity"]["resource_id"])
                created.append(record)
                events.append(resource_ref(event))
            response = {"ok": True, "changed": True, "records": created, "outbox_events": events}
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def update(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = require_dict(payload.get("record"), "record")
        context = MutationContext.from_payload(payload)
        expected_revision = str(payload.get("expected_revision") or "")
        if not expected_revision:
            raise ValidationFailure("expected_revision is required")
        self._validate_canonical_record(record)
        actual_type, actual_id = resource_key(record)
        if actual_type != resource_type or actual_id != resource_id:
            raise ValidationFailure("record identity must match request path")
        operation = f"update:{resource_type}:{resource_id}:{expected_revision}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        organization_id = organization_id_for(record)
        with self.connect() as db:
            existing = self._require_record(db, resource_type, resource_id)
            existing_doc = parse_json(existing["document_json"])
            if existing_doc["identity"]["revision"] != expected_revision:
                raise StaleRevisionError("expected_revision does not match current revision")
            if organization_id_for(existing_doc) != organization_id:
                raise ConflictError("Organization scope cannot change", code="organization_context_mismatch")
            if status_for(existing_doc) != status_for(record):
                raise ConflictError("status changes require lifecycle transition", code="illegal_lifecycle_transition")
            if resource_type == "WORKFLOW_REVISION" and status_for(existing_doc) == "PUBLISHED":
                raise ConflictError("published Workflow Revisions are immutable", code="published_revision_immutable")
            if record["identity"]["revision"] == expected_revision:
                if canonical_json(record) == canonical_json(existing_doc):
                    response = {"ok": True, "changed": False, "record": existing_doc}
                    self._store_idempotent_response(db, context, operation, payload, response)
                    return response
                raise StaleRevisionError("material update must use a new revision")
            self._validate_bundle(db, organization_id, candidate=record, replace=(resource_type, resource_id))
            event = self._build_event(
                record,
                context,
                "work-coordination.record.updated",
                {
                    "operation": "UPDATE",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "prior_revision": expected_revision,
                    "resulting_revision": record["identity"]["revision"],
                },
            )
            self._upsert_record(db, record)
            self._append_event(db, organization_id, record, event)
            self._append_history(db, record, expected_revision, "UPDATE", context, event["identity"]["resource_id"])
            response = {"ok": True, "changed": True, "record": record, "outbox_event": resource_ref(event)}
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def transition(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        context = MutationContext.from_payload(payload)
        expected_revision = str(payload.get("expected_revision") or "")
        to_status = str(payload.get("to_status") or "")
        if not expected_revision or not to_status:
            raise ValidationFailure("expected_revision and to_status are required")
        operation = f"transition:{resource_type}:{resource_id}:{expected_revision}:{to_status}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        with self.connect() as db:
            existing = self._require_record(db, resource_type, resource_id)
            prior = parse_json(existing["document_json"])
            if prior["identity"]["revision"] != expected_revision:
                raise StaleRevisionError("expected_revision does not match current revision")
            from_status = status_for(prior)
            if to_status not in TRANSITIONS.get(resource_type, {}).get(from_status, set()):
                raise ConflictError("illegal lifecycle transition", code="illegal_lifecycle_transition")
            next_doc = json.loads(canonical_json(prior))
            now = utc_now()
            transition_revision = "sha256:" + hashlib.sha256(f"{resource_type}:{resource_id}:{expected_revision}:{to_status}:{context.correlation_id}".encode()).hexdigest()
            transition_id = f"work-transition:{uuid.uuid4()}"
            transition_ref = {
                "resource_type": "WORK_STATE_TRANSITION",
                "resource_id": transition_id,
                "revision": transition_revision,
            }
            next_doc["status"] = to_status
            next_doc["identity"]["updated_at"] = now
            if resource_type == "WORK_REQUEST" and to_status in {"ACCEPTED", "CONVERTED"}:
                next_doc["acceptance_transition_ref"] = transition_ref
            if resource_type == "WORK_REQUEST" and to_status == "CONVERTED":
                job_ref = require_dict(payload.get("conversion_job_ref"), "conversion_job_ref")
                if job_ref.get("resource_type") != "SCHEDULER_JOB":
                    raise ValidationFailure("conversion_job_ref must reference a Scheduler Job")
                next_doc["conversion_job_ref"] = job_ref
            if resource_type == "TASK" and to_status in {"COMPLETED", "AWAITING_VERIFICATION", "VERIFIED", "CLOSED"}:
                refs = payload.get("result_refs")
                if isinstance(refs, list):
                    next_doc["result_refs"] = refs
            if resource_type == "TASK" and to_status == "VERIFIED":
                evidence = payload.get("verification_evidence_refs")
                if isinstance(evidence, list):
                    next_doc["verification_evidence_refs"] = evidence
            if resource_type == "TASK" and to_status == "CLOSED":
                next_doc["closure_transition_ref"] = transition_ref
            next_doc["identity"]["revision"] = revision_for(next_doc)
            if resource_type == "TASK" and to_status == "COMPLETED" and not next_doc.get("result_refs"):
                raise ValidationFailure("Task completion requires Work Result evidence")
            if resource_type == "TASK" and to_status == "CLOSED":
                governance = next_doc.get("governance") if isinstance(next_doc.get("governance"), dict) else {}
                if governance.get("verification_required") and not next_doc.get("verification_evidence_refs"):
                    raise ValidationFailure("closure before required verification is prohibited")
            self._validate_canonical_record(next_doc)
            organization_id = organization_id_for(next_doc)
            self._validate_bundle(db, organization_id, candidate=next_doc, replace=(resource_type, resource_id))
            transition_doc = self._build_transition_doc(
                prior=prior,
                current=next_doc,
                transition_id=transition_id,
                transition_revision=transition_revision,
                context=context,
                from_status=from_status,
                to_status=to_status,
                reason=str(payload.get("reason") or "Governed lifecycle transition."),
                now=now,
                result_refs=payload.get("result_refs") if isinstance(payload.get("result_refs"), list) else [],
                verification_evidence_refs=payload.get("verification_evidence_refs") if isinstance(payload.get("verification_evidence_refs"), list) else [],
            )
            validate_contract("leos.work-state-transition.v1", transition_doc)
            event = self._build_event(
                next_doc,
                context,
                "work-coordination.record.transitioned",
                {
                    "operation": "TRANSITION",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "from_status": from_status,
                    "to_status": to_status,
                    "prior_revision": expected_revision,
                    "resulting_revision": next_doc["identity"]["revision"],
                    "transition_ref": resource_ref(transition_doc),
                },
            )
            self._upsert_record(db, next_doc)
            self._append_transition(db, transition_doc, organization_id, prior, next_doc)
            self._append_event(db, organization_id, next_doc, event)
            self._append_history(db, next_doc, expected_revision, "TRANSITION", context, event["identity"]["resource_id"])
            response = {
                "ok": True,
                "changed": True,
                "record": next_doc,
                "transition": transition_doc,
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def create_assignment_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = MutationContext.from_payload(payload)
        decision = require_dict(payload.get("decision"), "decision")
        reject_raw_secret_values(decision)
        reject_caller_authority_claims(decision)
        decision_id = str(decision.get("decision_id") or "")
        if not decision_id:
            raise ValidationFailure("decision_id is required")
        organization_ref = require_dict(decision.get("organization_ref"), "organization_ref")
        organization_id = self._organization_id_from_ref(organization_ref)
        work_ref = require_dict(decision.get("work_ref"), "work_ref")
        assignee = require_dict(decision.get("assignee"), "assignee")
        if any(key in decision for key in {"score", "ranking", "selected_by_score", "force"}):
            raise ValidationFailure("assignment decisions cannot score, rank, optimize, or force assignees")
        self._validate_references_for_internal_record(
            organization_id,
            [organization_ref, work_ref],
            assignee=assignee,
        )
        if not decision.get("assignment_reason") or not decision.get("decision_rationale"):
            raise ValidationFailure("assignment_reason and decision_rationale are required")
        decision = {**decision, "authority": AUTHORITY_REF, "status": decision.get("status", "DECIDED")}
        decision_revision = evidence_revision_for(decision)
        operation = f"assignment-decision:{decision_id}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        with self.connect() as db:
            if self._exists(db, "assignment_decisions", "decision_id", decision_id):
                raise ConflictError("assignment decision already exists")
            event = self._build_internal_event(
                organization_id,
                "ASSIGNMENT_DECISION",
                decision_id,
                decision_revision,
                "work-coordination.assignment-decision.created",
                context,
                {"decision_id": decision_id, "work_ref": work_ref, "assignee": assignee},
            )
            db.execute(
                """
                INSERT INTO assignment_decisions
                (decision_id, organization_id, work_ref_json, assignee_json, decision_json, status, revision, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    organization_id,
                    canonical_json(work_ref),
                    canonical_json(assignee),
                    canonical_json(decision),
                    decision["status"],
                    decision_revision,
                    utc_now(),
                ),
            )
            self._append_internal_event(db, organization_id, event)
            response = {
                "ok": True,
                "decision": decision,
                "decision_ref": {
                    "resource_type": "ASSIGNMENT_DECISION",
                    "resource_id": decision_id,
                    "revision": decision_revision,
                },
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def request_assignment_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = MutationContext.from_payload(payload)
        handoff = require_dict(payload.get("handoff"), "handoff")
        reject_raw_secret_values(handoff)
        reject_caller_authority_claims(handoff)
        handoff_id = str(handoff.get("handoff_id") or "")
        if not handoff_id:
            raise ValidationFailure("handoff_id is required")
        decision_ref = require_dict(handoff.get("assignment_decision_ref"), "assignment_decision_ref")
        if decision_ref.get("resource_type") != "ASSIGNMENT_DECISION":
            raise ValidationFailure("handoff must reference an assignment decision")
        organization_ref = require_dict(handoff.get("organization_ref"), "organization_ref")
        organization_id = self._organization_id_from_ref(organization_ref)
        operation = f"assignment-handoff:{handoff_id}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        with self.connect() as db:
            decision = self._require_assignment_decision(db, decision_ref)
            if decision["organization_id"] != organization_id:
                raise ValidationFailure("assignment handoff crosses Organization boundary")
            outbound = {
                **handoff,
                "authority": AUTHORITY_REF,
                "actor_context_ref": context.actor_context_ref,
                "authorization_decision_ref": context.authorization_decision_ref,
                "correlation_id": context.correlation_id,
            }
            runtime_response = self.runtime_handoff_adapter.request_assignment_handoff(outbound)
            if runtime_response.get("status") not in {"ACCEPTED", "REJECTED"}:
                raise ValidationFailure("runtime handoff response must be ACCEPTED or REJECTED")
            handoff_revision = evidence_revision_for({"handoff": outbound, "runtime_response": runtime_response})
            event = self._build_internal_event(
                organization_id,
                "ASSIGNMENT_HANDOFF",
                handoff_id,
                handoff_revision,
                "work-coordination.assignment-handoff.recorded",
                context,
                {"handoff_id": handoff_id, "status": runtime_response["status"]},
            )
            db.execute(
                """
                INSERT INTO assignment_handoffs
                (handoff_id, organization_id, decision_id, status, handoff_json, runtime_response_json, revision, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff_id,
                    organization_id,
                    decision_ref["resource_id"],
                    runtime_response["status"],
                    canonical_json(outbound),
                    canonical_json(runtime_response),
                    handoff_revision,
                    utc_now(),
                ),
            )
            self._append_internal_event(db, organization_id, event)
            response = {
                "ok": True,
                "handoff": outbound,
                "runtime_response": runtime_response,
                "handoff_ref": {
                    "resource_type": "ASSIGNMENT_HANDOFF",
                    "resource_id": handoff_id,
                    "revision": handoff_revision,
                },
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def request_scheduler_projection(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = MutationContext.from_payload(payload)
        projection = require_dict(payload.get("projection"), "projection")
        reject_raw_secret_values(projection)
        reject_caller_authority_claims(projection)
        projection_id = str(projection.get("projection_id") or "")
        if not projection_id:
            raise ValidationFailure("projection_id is required")
        organization_ref = require_dict(projection.get("organization_ref"), "organization_ref")
        organization_id = self._organization_id_from_ref(organization_ref)
        refs = [organization_ref]
        for name in ("source_work_request_ref", "source_workflow_revision_ref", "source_task_ref"):
            if isinstance(projection.get(name), dict):
                refs.append(projection[name])
        self._validate_references_for_internal_record(organization_id, refs)
        operation = f"scheduler-projection:{projection_id}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        with self.connect() as db:
            if self._exists(db, "scheduler_projections", "projection_id", projection_id):
                raise ConflictError("scheduler projection already exists")
            outbound = {
                **projection,
                "authority": AUTHORITY_REF,
                "actor_context_ref": context.actor_context_ref,
                "authorization_decision_ref": context.authorization_decision_ref,
                "correlation_id": context.correlation_id,
            }
            scheduler_response = self.scheduler_projection_adapter.request_job_projection(outbound)
            if scheduler_response.get("status") not in {"ACCEPTED", "REJECTED"}:
                raise ValidationFailure("Scheduler projection response must be ACCEPTED or REJECTED")
            projection_revision = evidence_revision_for({"projection": outbound, "scheduler_response": scheduler_response})
            event = self._build_internal_event(
                organization_id,
                "SCHEDULER_PROJECTION",
                projection_id,
                projection_revision,
                "work-coordination.scheduler-projection.recorded",
                context,
                {"projection_id": projection_id, "status": scheduler_response["status"]},
            )
            db.execute(
                """
                INSERT INTO scheduler_projections
                (projection_id, organization_id, status, projection_json, scheduler_response_json, revision, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection_id,
                    organization_id,
                    scheduler_response["status"],
                    canonical_json(outbound),
                    canonical_json(scheduler_response),
                    projection_revision,
                    utc_now(),
                ),
            )
            self._append_internal_event(db, organization_id, event)
            response = {
                "ok": True,
                "projection": outbound,
                "scheduler_response": scheduler_response,
                "projection_ref": {
                    "resource_type": "SCHEDULER_PROJECTION",
                    "resource_id": projection_id,
                    "revision": projection_revision,
                },
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def create_verification(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = MutationContext.from_payload(payload)
        verification = require_dict(payload.get("verification"), "verification")
        reject_raw_secret_values(verification)
        reject_caller_authority_claims(verification)
        verification_id = str(verification.get("verification_id") or "")
        if not verification_id:
            raise ValidationFailure("verification_id is required")
        organization_ref = require_dict(verification.get("organization_ref"), "organization_ref")
        organization_id = self._organization_id_from_ref(organization_ref)
        result_ref = require_dict(verification.get("result_ref"), "result_ref")
        if result_ref.get("resource_type") != "WORK_RESULT":
            raise ValidationFailure("verification result_ref must reference a Work Result")
        evidence_refs = verification.get("verification_evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ValidationFailure("verification requires external evidence refs")
        self._validate_references_for_internal_record(organization_id, [organization_ref, result_ref])
        verification = {**verification, "authority": AUTHORITY_REF, "status": verification.get("status", "VERIFIED")}
        return self._insert_internal_record(
            table="verification_records",
            id_column="verification_id",
            id_value=verification_id,
            organization_id=organization_id,
            status=verification["status"],
            document=verification,
            event_type="work-coordination.verification.created",
            context=context,
            extra_columns={"result_ref_json": canonical_json(result_ref), "verification_json": canonical_json(verification)},
            response_key="verification",
            ref_type="WORK_VERIFICATION",
            operation_prefix="verification",
            payload=payload,
        )

    def create_closure(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = MutationContext.from_payload(payload)
        closure = require_dict(payload.get("closure"), "closure")
        reject_raw_secret_values(closure)
        reject_caller_authority_claims(closure)
        closure_id = str(closure.get("closure_id") or "")
        if not closure_id:
            raise ValidationFailure("closure_id is required")
        organization_ref = require_dict(closure.get("organization_ref"), "organization_ref")
        organization_id = self._organization_id_from_ref(organization_ref)
        subject_ref = require_dict(closure.get("subject_ref"), "subject_ref")
        verification_ref = require_dict(closure.get("verification_ref"), "verification_ref")
        if verification_ref.get("resource_type") != "WORK_VERIFICATION":
            raise ValidationFailure("closure requires a Work Coordination verification record")
        self._validate_references_for_internal_record(organization_id, [organization_ref, subject_ref])
        closure = {**closure, "authority": AUTHORITY_REF, "status": closure.get("status", "CLOSED")}
        return self._insert_internal_record(
            table="closure_records",
            id_column="closure_id",
            id_value=closure_id,
            organization_id=organization_id,
            status=closure["status"],
            document=closure,
            event_type="work-coordination.closure.created",
            context=context,
            extra_columns={"subject_ref_json": canonical_json(subject_ref), "closure_json": canonical_json(closure)},
            response_key="closure",
            ref_type="WORK_CLOSURE",
            operation_prefix="closure",
            payload=payload,
        )

    def list_records(self, resource_type: str, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if organization_id:
                rows = db.execute(
                    "SELECT document_json FROM work_records WHERE resource_type = ? AND organization_id = ? ORDER BY resource_id",
                    (resource_type, organization_id),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT document_json FROM work_records WHERE resource_type = ? ORDER BY organization_id, resource_id",
                    (resource_type,),
                ).fetchall()
        return {"ok": True, "records": [parse_json(row["document_json"]) for row in rows]}

    def get(self, resource_type: str, resource_id: str, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            row = self._require_record(db, resource_type, resource_id)
        document = parse_json(row["document_json"])
        if organization_id and organization_id_for(document) != organization_id:
            raise NotFoundError("record not found")
        return {"ok": True, "record": document}

    def audit(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        with self.connect() as db:
            self._require_record(db, resource_type, resource_id)
            rows = db.execute(
                """
                SELECT prior_revision, new_revision, operation, actor_context_ref_json,
                       authorization_decision_ref_json, idempotency_key, event_id, recorded_at
                FROM work_record_history
                WHERE resource_type = ? AND resource_id = ?
                ORDER BY history_id
                """,
                (resource_type, resource_id),
            ).fetchall()
        return {"ok": True, "history": [dict(row) for row in rows]}

    def outbox(self, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if organization_id:
                rows = db.execute(
                    "SELECT event_json FROM work_outbox WHERE organization_id = ? ORDER BY recorded_at, event_id",
                    (organization_id,),
                ).fetchall()
            else:
                rows = db.execute("SELECT event_json FROM work_outbox ORDER BY recorded_at, event_id").fetchall()
        return {"ok": True, "events": [parse_json(row["event_json"]) for row in rows]}

    def transitions(self, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if organization_id:
                rows = db.execute(
                    "SELECT transition_json FROM work_transitions WHERE organization_id = ? ORDER BY recorded_at, transition_id",
                    (organization_id,),
                ).fetchall()
            else:
                rows = db.execute("SELECT transition_json FROM work_transitions ORDER BY recorded_at, transition_id").fetchall()
        return {"ok": True, "transitions": [parse_json(row["transition_json"]) for row in rows]}

    def _validate_canonical_record(self, record: dict[str, Any]) -> None:
        reject_raw_secret_values(record)
        reject_caller_authority_claims(record)
        resource_type, _ = resource_key(record)
        contract = CONTRACT_BY_RESOURCE_TYPE.get(resource_type)
        if contract is None:
            if resource_type in {"SCHEDULER_JOB", "WORK_ASSIGNMENT"}:
                raise ValidationFailure(
                    f"{resource_type} is owned by another authority",
                    code="foreign_authority_record_rejected",
                )
            raise ValidationFailure("unsupported Work Coordination resource type")
        if record.get("contract_version") != contract:
            raise ValidationFailure(
                "contract_version does not match resource_type",
                details={"expected": contract, "actual": record.get("contract_version")},
            )
        authority = require_dict(record["identity"].get("ownership"), "identity.ownership").get("lifecycle_authority")
        if not isinstance(authority, dict) or authority.get("authority_id") != AUTHORITY_ID:
            raise ValidationFailure(
                "Work Coordination owned records must name Work Coordination Service as lifecycle authority",
                code="wrong_lifecycle_authority",
            )
        try:
            validate_contract(contract, record)
        except ContractValidationError as exc:
            raise ValidationFailure(
                "canonical contract validation failed",
                details={"issues": [issue.__dict__ for issue in exc.issues]},
            ) from exc

    def _validate_bundle(
        self,
        db: sqlite3.Connection,
        organization_id: str,
        *,
        candidate: dict[str, Any],
        replace: tuple[str, str] | None = None,
    ) -> None:
        records = [
            parse_json(row["document_json"])
            for row in db.execute("SELECT document_json FROM work_records WHERE organization_id = ?", (organization_id,))
        ]
        if replace is not None:
            records = [doc for doc in records if resource_key(doc) != replace]
        refs: set[tuple[str, str, str]] = set()
        for document in [*records, candidate]:
            if organization_id_for(document) != organization_id:
                raise ValidationFailure("cross-Organization Work record is prohibited")
            collect_refs(document, refs)
        external_refs = {ref for ref in refs if ref[0] in EXTERNAL_REFERENCE_TYPES}
        org_refs = {ref for ref in external_refs if ref[0] in {"ORGANIZATION", "DEPARTMENT", "TEAM", "POSITION"}}
        employee_refs = {ref for ref in external_refs if ref[0] == "EMPLOYEE"}
        scheduler_refs = {ref for ref in external_refs if ref[0] == "SCHEDULER_JOB"}
        runtime_refs = {ref for ref in external_refs if ref[0] == "WORK_ASSIGNMENT"}
        external_docs: list[dict[str, Any]] = []
        external_docs.extend(self.organization_adapter.documents_for_references(org_refs))
        external_docs.extend(self.scheduler_reference_adapter.documents_for_references(scheduler_refs))
        runtime_docs = self.runtime_reference_adapter.documents_for_references(runtime_refs)
        external_docs.extend(runtime_docs)
        extra_employee_refs: set[tuple[str, str, str]] = set()
        for document in runtime_docs:
            collect_refs(document, extra_employee_refs)
        employee_refs = employee_refs | {ref for ref in extra_employee_refs if ref[0] == "EMPLOYEE"}
        external_docs.extend(self.employee_adapter.documents_for_references(employee_refs))
        try:
            validate_work_domain([*external_docs, *records, candidate])
        except ContractValidationError as exc:
            raise ValidationFailure(
                "Work Domain semantic validation failed",
                details={"issues": [issue.__dict__ for issue in exc.issues]},
            ) from exc

    def _validate_bundle_many(
        self,
        db: sqlite3.Connection,
        organization_id: str,
        *,
        candidates: list[dict[str, Any]],
    ) -> None:
        records = [
            parse_json(row["document_json"])
            for row in db.execute("SELECT document_json FROM work_records WHERE organization_id = ?", (organization_id,))
        ]
        refs: set[tuple[str, str, str]] = set()
        for document in [*records, *candidates]:
            if organization_id_for(document) != organization_id:
                raise ValidationFailure("cross-Organization Work record is prohibited")
            collect_refs(document, refs)
        external_refs = {ref for ref in refs if ref[0] in EXTERNAL_REFERENCE_TYPES}
        org_refs = {ref for ref in external_refs if ref[0] in {"ORGANIZATION", "DEPARTMENT", "TEAM", "POSITION"}}
        employee_refs = {ref for ref in external_refs if ref[0] == "EMPLOYEE"}
        scheduler_refs = {ref for ref in external_refs if ref[0] == "SCHEDULER_JOB"}
        runtime_refs = {ref for ref in external_refs if ref[0] == "WORK_ASSIGNMENT"}
        external_docs: list[dict[str, Any]] = []
        external_docs.extend(self.organization_adapter.documents_for_references(org_refs))
        external_docs.extend(self.scheduler_reference_adapter.documents_for_references(scheduler_refs))
        runtime_docs = self.runtime_reference_adapter.documents_for_references(runtime_refs)
        external_docs.extend(runtime_docs)
        extra_employee_refs: set[tuple[str, str, str]] = set()
        for document in runtime_docs:
            collect_refs(document, extra_employee_refs)
        employee_refs = employee_refs | {ref for ref in extra_employee_refs if ref[0] == "EMPLOYEE"}
        external_docs.extend(self.employee_adapter.documents_for_references(employee_refs))
        try:
            validate_work_domain([*external_docs, *records, *candidates])
        except ContractValidationError as exc:
            raise ValidationFailure(
                "Work Domain semantic validation failed",
                details={"issues": [issue.__dict__ for issue in exc.issues]},
            ) from exc

    def _validate_references_for_internal_record(
        self,
        organization_id: str,
        refs_to_check: list[dict[str, Any]],
        *,
        assignee: dict[str, Any] | None = None,
    ) -> None:
        refs: set[tuple[str, str, str]] = set()
        for value in refs_to_check:
            collect_refs(value, refs)
        if assignee is not None:
            collect_refs(assignee, refs)
        org_refs = {ref for ref in refs if ref[0] in {"ORGANIZATION", "DEPARTMENT", "TEAM", "POSITION"}}
        employee_refs = {ref for ref in refs if ref[0] == "EMPLOYEE"}
        scheduler_refs = {ref for ref in refs if ref[0] == "SCHEDULER_JOB"}
        runtime_refs = {ref for ref in refs if ref[0] == "WORK_ASSIGNMENT"}
        work_refs = {ref for ref in refs if ref[0] in CONTRACT_BY_RESOURCE_TYPE}
        org_docs = self.organization_adapter.documents_for_references(org_refs)
        employee_docs = self.employee_adapter.documents_for_references(employee_refs)
        self.scheduler_reference_adapter.documents_for_references(scheduler_refs)
        self.runtime_reference_adapter.documents_for_references(runtime_refs)
        for document in org_docs + employee_docs:
            org_ref = document.get("organization_ref")
            if isinstance(org_ref, dict) and org_ref.get("resource_id") != organization_id:
                raise ValidationFailure("cross-Organization reference is prohibited")
        with self.connect() as db:
            for resource_type, resource_id, revision in work_refs:
                row = self._require_record(db, resource_type, resource_id)
                doc = parse_json(row["document_json"])
                if doc["identity"]["revision"] != revision:
                    raise StaleRevisionError("Work reference revision is stale")
                if organization_id_for(doc) != organization_id:
                    raise ValidationFailure("cross-Organization Work reference is prohibited")

    def _organization_id_from_ref(self, ref: dict[str, Any]) -> str:
        if ref.get("resource_type") != "ORGANIZATION":
            raise ValidationFailure("organization_ref must reference an Organization")
        refs = {(ref["resource_type"], ref["resource_id"], ref["revision"])}
        self.organization_adapter.documents_for_references(refs)
        return str(ref["resource_id"])

    def _build_transition_doc(
        self,
        *,
        prior: dict[str, Any],
        current: dict[str, Any],
        transition_id: str,
        transition_revision: str,
        context: MutationContext,
        from_status: str,
        to_status: str,
        reason: str,
        now: str,
        result_refs: list[dict[str, Any]],
        verification_evidence_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "contract_version": "leos.work-state-transition.v1",
            "identity": {
                "resource_type": "WORK_STATE_TRANSITION",
                "resource_id": transition_id,
                "display_name": f"{prior['identity']['resource_id']} {from_status} to {to_status}",
                "revision": transition_revision,
                "ownership": {
                    "owner": current["identity"]["ownership"]["owner"],
                    "creator": AUTHORITY_PRINCIPAL,
                    "steward": AUTHORITY_PRINCIPAL,
                    "lifecycle_authority": AUTHORITY_REF,
                },
                "creation_actor_context_ref": context.actor_context_ref,
                "creation_authority_evidence_ref": {
                    "authority_id": "authorization-authority",
                    "reference_id": context.authorization_decision_ref["resource_id"],
                    "revision": context.authorization_decision_ref["revision"],
                },
                "audit_id": f"audit:{transition_id}",
                "created_at": now,
                "updated_at": now,
            },
            "record_mode": {"kind": "CANONICAL_TARGET"},
            "organization_ref": current["organization_ref"],
            "state_evidence": {
                "transition_authority": AUTHORITY_REF,
                "actor_context_ref": context.actor_context_ref,
                "authorization_decision_ref": context.authorization_decision_ref,
                "approval_verification_refs": [],
                "event_ref": {
                    "resource_type": "EVENT",
                    "resource_id": f"event:{transition_id}",
                    "revision": transition_revision,
                },
                "transitioned_at": now,
            },
            "subject_ref": resource_ref(prior),
            "from_state": from_status,
            "to_state": to_status,
            "expected_revision": prior["identity"]["revision"],
            "resulting_revision": current["identity"]["revision"],
            "reason": reason,
            "result_refs": result_refs,
            "verification_evidence_refs": verification_evidence_refs,
            "history_refs": [
                {
                    "authority": AUTHORITY_REF,
                    "reference_id": f"history:{prior['identity']['resource_id']}:{prior['identity']['revision']}",
                    "revision": evidence_revision_for(prior),
                }
            ],
            "rollback_behavior": "REOPEN_PROHIBITED" if to_status in {"CLOSED", "CANCELLED", "FAILED"} else "NONE",
            "occurred_at": now,
        }

    def _build_event(
        self,
        record: dict[str, Any],
        context: MutationContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_id = f"event:work-coordination:{uuid.uuid4()}"
        now = utc_now()
        event = {
            "identity": {
                "resource_type": "EVENT",
                "resource_id": event_id,
                "revision": "sha256:event-pending",
            },
            "event_type": event_type,
            "producer": AUTHORITY_REF,
            "source_ref": EVENT_SOURCE_REF,
            "organization_ref": record.get("organization_ref"),
            "aggregate_ref": resource_ref(record),
            "actor_context_ref": context.actor_context_ref,
            "authorization_decision_ref": context.authorization_decision_ref,
            "correlation_id": context.correlation_id,
            "payload": payload,
            "produced_at": now,
            "producer_local_only": True,
        }
        event["identity"]["revision"] = evidence_revision_for(event)
        return event

    def _build_internal_event(
        self,
        organization_id: str,
        resource_type: str,
        resource_id: str,
        revision: str,
        event_type: str,
        context: MutationContext,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._build_event(
            {
                "identity": {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "revision": revision,
                },
                "organization_ref": {
                    "resource_type": "ORGANIZATION",
                    "resource_id": organization_id,
                    "revision": "sha256:organization-ref-provided-by-adapter",
                },
            },
            context,
            event_type,
            payload,
        )

    def _insert_internal_record(
        self,
        *,
        table: str,
        id_column: str,
        id_value: str,
        organization_id: str,
        status: str,
        document: dict[str, Any],
        event_type: str,
        context: MutationContext,
        extra_columns: dict[str, str],
        response_key: str,
        ref_type: str,
        operation_prefix: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        operation = f"{operation_prefix}:{id_value}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached
        revision = evidence_revision_for(document)
        with self.connect() as db:
            if self._exists(db, table, id_column, id_value):
                raise ConflictError(f"{response_key} already exists")
            event = self._build_internal_event(organization_id, ref_type, id_value, revision, event_type, context, {id_column: id_value})
            columns = [id_column, "organization_id", "status", "revision", "created_at", *extra_columns.keys()]
            placeholders = ", ".join("?" for _ in columns)
            db.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                [id_value, organization_id, status, revision, utc_now(), *extra_columns.values()],
            )
            self._append_internal_event(db, organization_id, event)
            response = {
                "ok": True,
                response_key: document,
                f"{response_key}_ref": {
                    "resource_type": ref_type,
                    "resource_id": id_value,
                    "revision": revision,
                },
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            return response

    def _insert_record(self, db: sqlite3.Connection, record: dict[str, Any]) -> None:
        now = utc_now()
        db.execute(
            """
            INSERT INTO work_records
            (resource_type, resource_id, organization_id, contract_version, status, revision, document_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["identity"]["resource_type"],
                record["identity"]["resource_id"],
                organization_id_for(record),
                record["contract_version"],
                record.get("status"),
                record["identity"]["revision"],
                canonical_json(record),
                now,
                now,
            ),
        )

    def _upsert_record(self, db: sqlite3.Connection, record: dict[str, Any]) -> None:
        db.execute(
            """
            UPDATE work_records
            SET organization_id = ?, contract_version = ?, status = ?, revision = ?, document_json = ?, updated_at = ?
            WHERE resource_type = ? AND resource_id = ?
            """,
            (
                organization_id_for(record),
                record["contract_version"],
                record.get("status"),
                record["identity"]["revision"],
                canonical_json(record),
                utc_now(),
                record["identity"]["resource_type"],
                record["identity"]["resource_id"],
            ),
        )

    def _append_history(
        self,
        db: sqlite3.Connection,
        record: dict[str, Any],
        prior_revision: str | None,
        operation: str,
        context: MutationContext,
        event_id: str,
    ) -> None:
        db.execute(
            """
            INSERT INTO work_record_history
            (resource_type, resource_id, organization_id, prior_revision, new_revision,
             operation, actor_context_ref_json, authorization_decision_ref_json,
             idempotency_key, event_id, recorded_at, document_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["identity"]["resource_type"],
                record["identity"]["resource_id"],
                organization_id_for(record),
                prior_revision,
                record["identity"]["revision"],
                operation,
                canonical_json(context.actor_context_ref),
                canonical_json(context.authorization_decision_ref),
                context.idempotency_key,
                event_id,
                utc_now(),
                canonical_json(record),
            ),
        )

    def _append_transition(
        self,
        db: sqlite3.Connection,
        transition: dict[str, Any],
        organization_id: str,
        prior: dict[str, Any],
        current: dict[str, Any],
    ) -> None:
        db.execute(
            """
            INSERT INTO work_transitions
            (transition_id, resource_type, resource_id, organization_id, prior_revision, new_revision, transition_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition["identity"]["resource_id"],
                prior["identity"]["resource_type"],
                prior["identity"]["resource_id"],
                organization_id,
                prior["identity"]["revision"],
                current["identity"]["revision"],
                canonical_json(transition),
                utc_now(),
            ),
        )

    def _append_event(self, db: sqlite3.Connection, organization_id: str, record: dict[str, Any], event: dict[str, Any]) -> None:
        db.execute(
            """
            INSERT INTO work_outbox
            (event_id, organization_id, aggregate_type, aggregate_id, aggregate_revision, event_type, event_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["identity"]["resource_id"],
                organization_id,
                record["identity"]["resource_type"],
                record["identity"]["resource_id"],
                record["identity"]["revision"],
                event["event_type"],
                canonical_json(event),
                event["produced_at"],
            ),
        )

    def _append_internal_event(self, db: sqlite3.Connection, organization_id: str, event: dict[str, Any]) -> None:
        db.execute(
            """
            INSERT INTO work_outbox
            (event_id, organization_id, aggregate_type, aggregate_id, aggregate_revision, event_type, event_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["identity"]["resource_id"],
                organization_id,
                event["aggregate_ref"]["resource_type"],
                event["aggregate_ref"]["resource_id"],
                event["aggregate_ref"]["revision"],
                event["event_type"],
                canonical_json(event),
                event["produced_at"],
            ),
        )

    def _get_record_row(self, db: sqlite3.Connection, resource_type: str, resource_id: str) -> sqlite3.Row | None:
        return db.execute(
            "SELECT * FROM work_records WHERE resource_type = ? AND resource_id = ?",
            (resource_type, resource_id),
        ).fetchone()

    def _require_record(self, db: sqlite3.Connection, resource_type: str, resource_id: str) -> sqlite3.Row:
        row = self._get_record_row(db, resource_type, resource_id)
        if row is None:
            raise NotFoundError("record not found")
        return row

    def _exists(self, db: sqlite3.Connection, table: str, column: str, value: str) -> bool:
        return db.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (value,)).fetchone() is not None

    def _require_assignment_decision(self, db: sqlite3.Connection, decision_ref: dict[str, Any]) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM assignment_decisions WHERE decision_id = ?",
            (decision_ref["resource_id"],),
        ).fetchone()
        if row is None:
            raise NotFoundError("assignment decision not found")
        if row["revision"] != decision_ref.get("revision"):
            raise StaleRevisionError("assignment decision revision is stale")
        return row

    def _idempotent_response(
        self,
        context: MutationContext,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if context.idempotency_key is None:
            return None
        request_hash = evidence_revision_for(payload)
        with self.connect() as db:
            row = db.execute(
                "SELECT request_hash, response_json FROM work_idempotency WHERE idempotency_key = ? AND operation = ?",
                (context.idempotency_key, operation),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ConflictError("idempotency key was reused with a different request fingerprint")
        return parse_json(row["response_json"])

    def _store_idempotent_response(
        self,
        db: sqlite3.Connection,
        context: MutationContext,
        operation: str,
        payload: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        if context.idempotency_key is None:
            return
        db.execute(
            """
            INSERT OR REPLACE INTO work_idempotency
            (idempotency_key, operation, request_hash, response_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                context.idempotency_key,
                operation,
                evidence_revision_for(payload),
                canonical_json(response),
                utc_now(),
            ),
        )
