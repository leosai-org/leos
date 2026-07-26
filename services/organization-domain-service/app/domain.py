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

from leos_contracts import (
    ContractValidationError,
    validate_contract,
    validate_organization_domain,
)


SERVICE_ID = "organization-domain-service"
SERVICE_VERSION = "0.2.0-dev-preview-v2"
SERVICE_CONTRACT = "leos.organization-domain-service.provisional-v1"
AUTHORITY_ID = "organization-domain-authority"
AUTHORITY_REVISION = "sha256:organization-domain-authority-v1"
AUTHORITY_PRINCIPAL = {
    "principal_id": "principal:service:organization-domain-authority",
    "principal_type": "SERVICE",
}
AUTHORITY_REF = {
    "authority_id": AUTHORITY_ID,
    "principal": AUTHORITY_PRINCIPAL,
    "authority_revision": AUTHORITY_REVISION,
}
EVENT_SOURCE_REF = {
    "resource_type": "EVENT_SOURCE",
    "resource_id": "event-source:organization-domain-service",
    "revision": "sha256:event-source-organization-domain-service-v1",
}
OBSERVED_AT_FALLBACK = "2099-01-01T00:00:00Z"

CONTRACT_BY_RESOURCE_TYPE = {
    "ORGANIZATION": "leos.organization.v1",
    "DEPARTMENT": "leos.department.v1",
    "TEAM": "leos.team.v1",
    "ROLE": "leos.role.v1",
    "POSITION": "leos.position.v1",
    "MEMBERSHIP": "leos.membership.v1",
    "POSITION_OCCUPANCY": "leos.position-occupancy.v1",
}
COLLECTION_TO_RESOURCE_TYPE = {
    "organizations": "ORGANIZATION",
    "departments": "DEPARTMENT",
    "teams": "TEAM",
    "roles": "ROLE",
    "positions": "POSITION",
    "memberships": "MEMBERSHIP",
    "position-occupancies": "POSITION_OCCUPANCY",
}
RESOURCE_TYPE_TO_COLLECTION = {
    resource_type: collection
    for collection, resource_type in COLLECTION_TO_RESOURCE_TYPE.items()
}
ORGANIZATION_STATUSES = {"DRAFT", "ACTIVE", "SUSPENDED", "ARCHIVED", "DELETED"}
RELATIONSHIP_STATUSES = {
    "MEMBERSHIP": {"PENDING", "ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED"},
    "POSITION_OCCUPANCY": {"PENDING", "ACTIVE", "ENDED", "REVOKED"},
}
TERMINAL_STATUSES = {
    "ARCHIVED",
    "DELETED",
    "EXPIRED",
    "REVOKED",
    "ENDED",
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
logger = logging.getLogger(SERVICE_ID)


def log_info(event: str, **fields: Any) -> None:
    logger.info(
        canonical_json(
            {
                "event": event,
                "service": SERVICE_ID,
                **fields,
            }
        )
    )


class OrganizationDomainError(RuntimeError):
    status_code = 422
    code = "organization_domain_error"

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
        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
        }


class NotFoundError(OrganizationDomainError):
    status_code = 404
    code = "not_found"


class ConflictError(OrganizationDomainError):
    status_code = 409
    code = "conflict"


class StaleRevisionError(OrganizationDomainError):
    status_code = 409
    code = "stale_revision"


class DependencyUnavailableError(OrganizationDomainError):
    status_code = 503
    code = "dependency_unavailable"


class ValidationFailure(OrganizationDomainError):
    status_code = 422
    code = "validation_failure"


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
    digest = hashlib.sha256(canonical_json(clone).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def evidence_revision_for(value: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def parse_json(value: str) -> dict[str, Any]:
    return json.loads(value)


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


def require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationFailure(f"{field} must be an object")
    return value


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


def organization_id_for(document: dict[str, Any]) -> str:
    resource_type, resource_id = resource_key(document)
    if resource_type == "ORGANIZATION":
        return resource_id
    organization_ref = require_dict(document.get("organization_ref"), "organization_ref")
    if organization_ref.get("resource_type") != "ORGANIZATION":
        raise ValidationFailure("organization_ref must reference an ORGANIZATION")
    organization_id = organization_ref.get("resource_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise ValidationFailure("organization_ref.resource_id is required")
    return organization_id


def validate_canonical_document(document: dict[str, Any]) -> None:
    reject_raw_secret_values(document)
    resource_type, _ = resource_key(document)
    contract = CONTRACT_BY_RESOURCE_TYPE.get(resource_type)
    if contract is None:
        raise ValidationFailure(
            f"{resource_type} is not an Organization Domain resource",
            code="unsupported_resource_type",
        )
    if document.get("contract_version") != contract:
        raise ValidationFailure(
            "contract_version does not match resource_type",
            details={"expected": contract, "actual": document.get("contract_version")},
        )
    try:
        validate_contract(contract, document)
    except ContractValidationError as exc:
        raise ValidationFailure(
            "canonical contract validation failed",
            details={"issues": [issue.__dict__ for issue in exc.issues]},
        ) from exc


def validate_actor_context_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OrganizationDomainError(
            "missing or malformed Actor Context evidence",
            code="missing_actor_context",
            status_code=401,
        )
    ref = value
    if ref.get("evidence_type") != "ACTOR_CONTEXT":
        raise OrganizationDomainError(
            "missing or malformed Actor Context evidence",
            code="missing_actor_context",
            status_code=401,
        )
    if not isinstance(ref.get("authority"), dict):
        raise OrganizationDomainError(
            "Actor Context evidence must identify its issuing authority",
            code="missing_actor_context",
            status_code=401,
        )
    if not ref.get("reference_id") or not ref.get("revision"):
        raise OrganizationDomainError(
            "Actor Context evidence must be revision-pinned",
            code="missing_actor_context",
            status_code=401,
        )
    return ref


def actor_context_resource_ref(evidence_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_type": "ACTOR_CONTEXT",
        "resource_id": evidence_ref["reference_id"],
        "revision": evidence_ref["revision"],
    }


def validate_authorization_decision_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OrganizationDomainError(
            "missing or malformed Authorization Decision evidence",
            code="missing_authorization_evidence",
            status_code=403,
        )
    ref = value
    if ref.get("resource_type") != "AUTHORIZATION_DECISION":
        raise OrganizationDomainError(
            "missing or malformed Authorization Decision evidence",
            code="missing_authorization_evidence",
            status_code=403,
        )
    if not ref.get("resource_id") or not ref.get("revision"):
        raise OrganizationDomainError(
            "Authorization Decision evidence must be revision-pinned",
            code="missing_authorization_evidence",
            status_code=403,
        )
    return ref


def reject_caller_authority_claims(payload: Any, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, child in payload.items():
            normalized = str(key).strip().lower()
            if normalized in {
                "authorized",
                "authorization_granted",
                "approval_granted",
                "verified",
                "is_authorized",
                "is_approved",
            }:
                raise OrganizationDomainError(
                    "caller-supplied authority booleans are prohibited",
                    code="caller_authority_claim_rejected",
                    status_code=403,
                    details={"path": f"{path}.{key}"},
                )
            reject_caller_authority_claims(child, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, child in enumerate(payload):
            reject_caller_authority_claims(child, f"{path}[{index}]")


@dataclass(frozen=True)
class MutationContext:
    actor_context_ref: dict[str, Any]
    authorization_decision_ref: dict[str, Any]
    idempotency_key: str | None
    correlation_id: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MutationContext":
        reject_caller_authority_claims(payload)
        actor = validate_actor_context_ref(payload.get("actor_context_ref"))
        authorization = validate_authorization_decision_ref(
            payload.get("authorization_decision_ref")
        )
        idempotency_key = payload.get("idempotency_key")
        if idempotency_key is not None and not str(idempotency_key).strip():
            raise ValidationFailure("idempotency_key must be non-empty when supplied")
        correlation_id = str(payload.get("correlation_id") or idempotency_key or uuid.uuid4())
        return cls(
            actor_context_ref=actor,
            authorization_decision_ref=authorization,
            idempotency_key=str(idempotency_key) if idempotency_key else None,
            correlation_id=correlation_id,
        )


class EmployeeReferenceAdapter(Protocol):
    def documents_for_references(
        self,
        *,
        principal_ids: set[str],
        resource_ids: set[str],
    ) -> list[dict[str, Any]]:
        ...


class NoEmployeeReferenceAdapter:
    def documents_for_references(
        self,
        *,
        principal_ids: set[str],
        resource_ids: set[str],
    ) -> list[dict[str, Any]]:
        if principal_ids or resource_ids:
            raise DependencyUnavailableError(
                "Employee Registry reference validation is unavailable",
                details={
                    "principal_ids": sorted(principal_ids),
                    "resource_ids": sorted(resource_ids),
                },
            )
        return []


class StaticEmployeeReferenceAdapter:
    """Deterministic test adapter; not an Employee lifecycle authority."""

    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self._by_resource: dict[str, dict[str, Any]] = {}
        self._by_principal: dict[str, dict[str, Any]] = {}
        for document in documents or []:
            self.add(document)

    def add(self, document: dict[str, Any]) -> None:
        validate_contract("leos.employee-definition.v3", document)
        self._by_resource[document["identity"]["resource_id"]] = document
        self._by_principal[document["employee_principal_ref"]["principal_id"]] = document

    def documents_for_references(
        self,
        *,
        principal_ids: set[str],
        resource_ids: set[str],
    ) -> list[dict[str, Any]]:
        missing_principals = sorted(pid for pid in principal_ids if pid not in self._by_principal)
        missing_resources = sorted(rid for rid in resource_ids if rid not in self._by_resource)
        if missing_principals or missing_resources:
            raise ValidationFailure(
                "Employee reference cannot be validated",
                code="invalid_employee_reference",
                details={
                    "missing_principal_ids": missing_principals,
                    "missing_resource_ids": missing_resources,
                },
            )
        docs = {
            document["identity"]["resource_id"]: document
            for document in (
                [self._by_principal[pid] for pid in principal_ids]
                + [self._by_resource[rid] for rid in resource_ids]
            )
        }
        return list(docs.values())


class OrganizationDomainStore:
    def __init__(
        self,
        database: str | Path,
        *,
        employee_adapter: EmployeeReferenceAdapter | None = None,
    ) -> None:
        self.database = Path(database)
        self.employee_adapter = employee_adapter or NoEmployeeReferenceAdapter()
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
                CREATE TABLE IF NOT EXISTS organization_records (
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (resource_type, resource_id)
                );
                CREATE INDEX IF NOT EXISTS idx_organization_records_org
                    ON organization_records (organization_id, resource_type, resource_id);
                CREATE TABLE IF NOT EXISTS organization_record_history (
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
                CREATE TABLE IF NOT EXISTS organization_transitions (
                    transition_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    prior_revision TEXT NOT NULL,
                    new_revision TEXT NOT NULL,
                    transition_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS organization_outbox (
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
                CREATE TABLE IF NOT EXISTS organization_idempotency (
                    idempotency_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (idempotency_key, operation)
                );
                """
            )

    def health(self) -> dict[str, Any]:
        with self.connect() as db:
            record_count = db.execute(
                "SELECT COUNT(*) AS count FROM organization_records"
            ).fetchone()["count"]
            outbox_count = db.execute(
                "SELECT COUNT(*) AS count FROM organization_outbox"
            ).fetchone()["count"]
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
        return {
            "ok": True,
            "service": SERVICE_ID,
            "state": "ready",
            "database": str(self.database),
        }

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = require_dict(payload.get("record"), "record")
        context = MutationContext.from_payload(payload)
        validate_canonical_document(record)
        self._validate_creation_evidence(record, context)
        organization_id = organization_id_for(record)
        operation = f"create:{record['identity']['resource_type']}:{record['identity']['resource_id']}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached

        with self.connect() as db:
            existing = self._get_record_row(
                db,
                record["identity"]["resource_type"],
                record["identity"]["resource_id"],
            )
            if existing is not None:
                existing_doc = parse_json(existing["document_json"])
                if canonical_json(existing_doc) == canonical_json(record):
                    response = {"ok": True, "changed": False, "record": existing_doc}
                    self._store_idempotent_response(db, context, operation, payload, response)
                    return response
                raise ConflictError(
                    "canonical resource identity already exists",
                    code="duplicate_resource_identity",
                )
            self._validate_domain_bundle(db, organization_id, candidate=record)
            event = self._build_event(
                record,
                context,
                event_type="organization-domain.record.created",
                payload={
                    "operation": "CREATE",
                    "resource_type": record["identity"]["resource_type"],
                    "resource_id": record["identity"]["resource_id"],
                    "resulting_revision": record["identity"]["revision"],
                },
                evidence_ref=record["identity"]["creation_authority_evidence_ref"],
            )
            self._insert_record(db, record)
            self._append_event(db, organization_id, record, event)
            self._append_history(
                db,
                record,
                prior_revision=None,
                operation="CREATE",
                context=context,
                event_id=event["identity"]["resource_id"],
            )
            response = {
                "ok": True,
                "changed": True,
                "record": record,
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            log_info(
                "organization_domain_record_created",
                resource_type=record["identity"]["resource_type"],
                resource_id=record["identity"]["resource_id"],
                organization_id=organization_id,
                revision=record["identity"]["revision"],
                outbox_event_id=event["identity"]["resource_id"],
            )
            return response

    def update(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = require_dict(payload.get("record"), "record")
        context = MutationContext.from_payload(payload)
        expected_revision = str(payload.get("expected_revision") or "")
        if not expected_revision:
            raise ValidationFailure("expected_revision is required")
        validate_canonical_document(record)
        actual_type, actual_id = resource_key(record)
        if actual_type != resource_type or actual_id != resource_id:
            raise ValidationFailure("record identity must match request path")
        self._validate_creation_evidence(record, context, allow_update=True)
        organization_id = organization_id_for(record)
        operation = f"update:{resource_type}:{resource_id}:{expected_revision}"
        cached = self._idempotent_response(context, operation, payload)
        if cached is not None:
            return cached

        with self.connect() as db:
            existing = self._require_record(db, resource_type, resource_id)
            existing_doc = parse_json(existing["document_json"])
            if existing_doc["identity"]["revision"] != expected_revision:
                raise StaleRevisionError("expected_revision does not match current revision")
            if organization_id_for(existing_doc) != organization_id:
                raise OrganizationDomainError(
                    "Organization context cannot be changed by update",
                    code="organization_context_mismatch",
                    status_code=409,
                )
            if existing_doc["status"] != record["status"]:
                raise OrganizationDomainError(
                    "status changes require a lifecycle transition",
                    code="illegal_lifecycle_transition",
                    status_code=409,
                )
            if record["identity"]["revision"] == expected_revision:
                if canonical_json(record) == canonical_json(existing_doc):
                    response = {"ok": True, "changed": False, "record": existing_doc}
                    self._store_idempotent_response(db, context, operation, payload, response)
                    return response
                raise StaleRevisionError("material update must use a new revision")
            self._validate_domain_bundle(db, organization_id, candidate=record)
            event = self._build_event(
                record,
                context,
                event_type="organization-domain.record.updated",
                payload={
                    "operation": "UPDATE",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "prior_revision": expected_revision,
                    "resulting_revision": record["identity"]["revision"],
                },
                evidence_ref={
                    "authority_id": "authorization-authority",
                    "reference_id": context.authorization_decision_ref["resource_id"],
                    "revision": context.authorization_decision_ref["revision"],
                },
            )
            self._upsert_record(db, record)
            self._append_event(db, organization_id, record, event)
            self._append_history(
                db,
                record,
                prior_revision=expected_revision,
                operation="UPDATE",
                context=context,
                event_id=event["identity"]["resource_id"],
            )
            response = {
                "ok": True,
                "changed": True,
                "record": record,
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            log_info(
                "organization_domain_record_updated",
                resource_type=resource_type,
                resource_id=resource_id,
                organization_id=organization_id,
                prior_revision=expected_revision,
                revision=record["identity"]["revision"],
                outbox_event_id=event["identity"]["resource_id"],
            )
            return response

    def transition(
        self,
        resource_type: str,
        resource_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
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
            document = parse_json(existing["document_json"])
            if document["identity"]["revision"] != expected_revision:
                raise StaleRevisionError("expected_revision does not match current revision")
            from_status = document["status"]
            if from_status == to_status:
                raise OrganizationDomainError(
                    "lifecycle transition must change status",
                    code="illegal_lifecycle_transition",
                    status_code=409,
                )
            next_document = json.loads(canonical_json(document))
            now = utc_now()
            next_document["status"] = to_status
            if resource_type in {"MEMBERSHIP", "POSITION_OCCUPANCY"} and to_status in TERMINAL_STATUSES:
                next_document.setdefault("effective_until", now)
            next_document["identity"]["updated_at"] = now
            next_document["identity"]["revision"] = revision_for(next_document)
            organization_id = organization_id_for(next_document)
            transition, event = self._build_transition_and_event(
                prior=document,
                current=next_document,
                context=context,
                from_status=from_status,
                to_status=to_status,
                now=now,
            )
            self._validate_transition(transition)
            self._validate_domain_bundle(
                db,
                organization_id,
                candidate=next_document,
                transition=transition,
                event=event,
            )
            self._upsert_record(db, next_document)
            self._append_transition(db, organization_id, transition)
            self._append_event(db, organization_id, next_document, event)
            self._append_history(
                db,
                next_document,
                prior_revision=expected_revision,
                operation=f"TRANSITION:{from_status}->{to_status}",
                context=context,
                event_id=event["identity"]["resource_id"],
            )
            response = {
                "ok": True,
                "changed": True,
                "record": next_document,
                "transition": transition,
                "outbox_event": resource_ref(event),
            }
            self._store_idempotent_response(db, context, operation, payload, response)
            log_info(
                "organization_domain_record_transitioned",
                resource_type=resource_type,
                resource_id=resource_id,
                organization_id=organization_id,
                from_status=from_status,
                to_status=to_status,
                prior_revision=expected_revision,
                revision=next_document["identity"]["revision"],
                transition_id=transition["identity"]["resource_id"],
                outbox_event_id=event["identity"]["resource_id"],
            )
            return response

    def get(self, resource_type: str, resource_id: str, *, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            row = self._require_record(db, resource_type, resource_id)
            document = parse_json(row["document_json"])
            if organization_id is not None and organization_id_for(document) != organization_id:
                raise NotFoundError("record not found in Organization scope")
            return {"ok": True, "record": document}

    def list_records(
        self,
        resource_type: str,
        *,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as db:
            if organization_id is None:
                rows = db.execute(
                    """
                    SELECT document_json FROM organization_records
                    WHERE resource_type = ?
                    ORDER BY organization_id, resource_id
                    """,
                    (resource_type,),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT document_json FROM organization_records
                    WHERE resource_type = ? AND organization_id = ?
                    ORDER BY resource_id
                    """,
                    (resource_type, organization_id),
                ).fetchall()
        records = [parse_json(row["document_json"]) for row in rows]
        return {"ok": True, "count": len(records), "records": records}

    def audit(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        with self.connect() as db:
            self._require_record(db, resource_type, resource_id)
            rows = db.execute(
                """
                SELECT * FROM organization_record_history
                WHERE resource_type = ? AND resource_id = ?
                ORDER BY history_id
                """,
                (resource_type, resource_id),
            ).fetchall()
        return {
            "ok": True,
            "count": len(rows),
            "audit": [
                {
                    "history_id": row["history_id"],
                    "resource_type": row["resource_type"],
                    "resource_id": row["resource_id"],
                    "organization_id": row["organization_id"],
                    "prior_revision": row["prior_revision"],
                    "new_revision": row["new_revision"],
                    "operation": row["operation"],
                    "actor_context_ref": parse_json(row["actor_context_ref_json"]),
                    "authorization_decision_ref": parse_json(row["authorization_decision_ref_json"]),
                    "idempotency_key": row["idempotency_key"],
                    "event_id": row["event_id"],
                    "recorded_at": row["recorded_at"],
                    "record": parse_json(row["document_json"]),
                }
                for row in rows
            ],
        }

    def outbox(self, *, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if organization_id is None:
                rows = db.execute(
                    "SELECT * FROM organization_outbox ORDER BY recorded_at, event_id"
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT * FROM organization_outbox
                    WHERE organization_id = ?
                    ORDER BY recorded_at, event_id
                    """,
                    (organization_id,),
                ).fetchall()
        events = [parse_json(row["event_json"]) for row in rows]
        return {"ok": True, "count": len(events), "events": events}

    def transitions(self, *, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if organization_id is None:
                rows = db.execute(
                    "SELECT transition_json FROM organization_transitions ORDER BY recorded_at, transition_id"
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT transition_json FROM organization_transitions
                    WHERE organization_id = ?
                    ORDER BY recorded_at, transition_id
                    """,
                    (organization_id,),
                ).fetchall()
        transitions = [parse_json(row["transition_json"]) for row in rows]
        return {"ok": True, "count": len(transitions), "transitions": transitions}

    def _idempotent_response(
        self,
        context: MutationContext,
        operation: str,
        request: dict[str, Any],
    ) -> dict[str, Any] | None:
        if context.idempotency_key is None:
            return None
        request_hash = evidence_revision_for(request)
        with self.connect() as db:
            row = db.execute(
                """
                SELECT request_hash, response_json FROM organization_idempotency
                WHERE idempotency_key = ? AND operation = ?
                """,
                (context.idempotency_key, operation),
            ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ConflictError(
                "idempotency key was reused with a different request",
                code="idempotency_conflict",
            )
        return parse_json(row["response_json"])

    def _store_idempotent_response(
        self,
        db: sqlite3.Connection,
        context: MutationContext,
        operation: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        if context.idempotency_key is None:
            return
        db.execute(
            """
            INSERT OR REPLACE INTO organization_idempotency
            (idempotency_key, operation, request_hash, response_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                context.idempotency_key,
                operation,
                evidence_revision_for(request),
                canonical_json(response),
                utc_now(),
            ),
        )

    def _get_record_row(
        self,
        db: sqlite3.Connection,
        resource_type: str,
        resource_id: str,
    ) -> sqlite3.Row | None:
        return db.execute(
            """
            SELECT * FROM organization_records
            WHERE resource_type = ? AND resource_id = ?
            """,
            (resource_type, resource_id),
        ).fetchone()

    def _require_record(
        self,
        db: sqlite3.Connection,
        resource_type: str,
        resource_id: str,
    ) -> sqlite3.Row:
        row = self._get_record_row(db, resource_type, resource_id)
        if row is None:
            raise NotFoundError("record not found")
        return row

    def _insert_record(self, db: sqlite3.Connection, document: dict[str, Any]) -> None:
        resource_type, resource_id = resource_key(document)
        db.execute(
            """
            INSERT INTO organization_records
            (resource_type, resource_id, organization_id, contract_version, status,
             revision, document_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_type,
                resource_id,
                organization_id_for(document),
                document["contract_version"],
                document["status"],
                document["identity"]["revision"],
                canonical_json(document),
                document["identity"]["created_at"],
                document["identity"]["updated_at"],
            ),
        )

    def _upsert_record(self, db: sqlite3.Connection, document: dict[str, Any]) -> None:
        resource_type, resource_id = resource_key(document)
        db.execute(
            """
            UPDATE organization_records
            SET organization_id = ?, contract_version = ?, status = ?, revision = ?,
                document_json = ?, updated_at = ?
            WHERE resource_type = ? AND resource_id = ?
            """,
            (
                organization_id_for(document),
                document["contract_version"],
                document["status"],
                document["identity"]["revision"],
                canonical_json(document),
                document["identity"]["updated_at"],
                resource_type,
                resource_id,
            ),
        )

    def _append_history(
        self,
        db: sqlite3.Connection,
        document: dict[str, Any],
        *,
        prior_revision: str | None,
        operation: str,
        context: MutationContext,
        event_id: str,
    ) -> None:
        resource_type, resource_id = resource_key(document)
        db.execute(
            """
            INSERT INTO organization_record_history
            (resource_type, resource_id, organization_id, prior_revision,
             new_revision, operation, actor_context_ref_json,
             authorization_decision_ref_json, idempotency_key, event_id,
             recorded_at, document_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_type,
                resource_id,
                organization_id_for(document),
                prior_revision,
                document["identity"]["revision"],
                operation,
                canonical_json(context.actor_context_ref),
                canonical_json(context.authorization_decision_ref),
                context.idempotency_key,
                event_id,
                utc_now(),
                canonical_json(document),
            ),
        )

    def _append_event(
        self,
        db: sqlite3.Connection,
        organization_id: str,
        document: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        validate_contract("leos.event-envelope.v1", event)
        db.execute(
            """
            INSERT INTO organization_outbox
            (event_id, organization_id, aggregate_type, aggregate_id,
             aggregate_revision, event_type, event_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["identity"]["resource_id"],
                organization_id,
                document["identity"]["resource_type"],
                document["identity"]["resource_id"],
                document["identity"]["revision"],
                event["event_type"],
                canonical_json(event),
                event["recorded_at"],
            ),
        )

    def _append_transition(
        self,
        db: sqlite3.Connection,
        organization_id: str,
        transition: dict[str, Any],
    ) -> None:
        db.execute(
            """
            INSERT INTO organization_transitions
            (transition_id, resource_type, resource_id, organization_id,
             prior_revision, new_revision, transition_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transition["identity"]["resource_id"],
                transition["subject_ref"]["resource_type"],
                transition["subject_ref"]["resource_id"],
                organization_id,
                transition["subject_ref"]["revision"],
                transition["resulting_revision"],
                canonical_json(transition),
                transition["transitioned_at"],
            ),
        )

    def _validate_creation_evidence(
        self,
        document: dict[str, Any],
        context: MutationContext,
        *,
        allow_update: bool = False,
    ) -> None:
        identity = document["identity"]
        if (
            not allow_update
            and identity["creation_actor_context_ref"]
            != actor_context_resource_ref(context.actor_context_ref)
        ):
            raise OrganizationDomainError(
                "Actor Context must match canonical creation evidence",
                code="actor_context_mismatch",
                status_code=403,
            )
        creation_auth = identity["creation_authority_evidence_ref"]
        if creation_auth.get("authority_id") != "authorization-authority":
            raise OrganizationDomainError(
                "creation authority evidence must come from Authorization Authority",
                code="missing_authorization_evidence",
                status_code=403,
            )
        if not allow_update:
            if creation_auth.get("reference_id") != context.authorization_decision_ref["resource_id"]:
                raise OrganizationDomainError(
                    "Authorization Decision must match creation evidence",
                    code="authorization_evidence_mismatch",
                    status_code=403,
                )
            if creation_auth.get("revision") != context.authorization_decision_ref["revision"]:
                raise OrganizationDomainError(
                    "Authorization Decision revision must match creation evidence",
                    code="authorization_evidence_mismatch",
                    status_code=403,
                )
        resource_type = identity["resource_type"]
        if not allow_update and resource_type in {"MEMBERSHIP", "POSITION_OCCUPANCY"}:
            if document["authorization_decision_ref"] != context.authorization_decision_ref:
                raise OrganizationDomainError(
                    "relationship authorization reference must match request evidence",
                    code="authorization_evidence_mismatch",
                    status_code=403,
                )
            if document["issued_by_actor_ref"] != context.actor_context_ref:
                raise OrganizationDomainError(
                    "relationship actor evidence must match request evidence",
                    code="actor_context_mismatch",
                    status_code=403,
                )

    def _validate_domain_bundle(
        self,
        db: sqlite3.Connection,
        organization_id: str,
        *,
        candidate: dict[str, Any],
        transition: dict[str, Any] | None = None,
        event: dict[str, Any] | None = None,
    ) -> None:
        rows = db.execute(
            "SELECT document_json FROM organization_records WHERE organization_id = ?",
            (organization_id,),
        ).fetchall()
        documents = [parse_json(row["document_json"]) for row in rows]
        candidate_type, candidate_id = resource_key(candidate)
        documents = [
            document
            for document in documents
            if resource_key(document) != (candidate_type, candidate_id)
        ]
        documents.append(candidate)
        documents.extend(
            self._employee_documents_for_bundle(documents, transition=transition)
        )
        if transition is not None:
            documents.append(transition)
        if event is not None:
            documents.append(event)
        try:
            validate_organization_domain(
                documents,
                observed_at=OBSERVED_AT_FALLBACK,
            )
        except ContractValidationError as exc:
            raise ValidationFailure(
                "Organization Domain invariant validation failed",
                details={"issues": [issue.__dict__ for issue in exc.issues]},
            ) from exc

    def _employee_documents_for_bundle(
        self,
        documents: list[dict[str, Any]],
        *,
        transition: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        principal_ids: set[str] = set()
        resource_ids: set[str] = set()
        for document in documents:
            resource_type = document["identity"]["resource_type"]
            if resource_type == "MEMBERSHIP" and document["member"]["principal_type"] == "EMPLOYEE":
                principal_ids.add(document["member"]["principal_id"])
            if resource_type == "POSITION_OCCUPANCY":
                resource_ids.add(document["employee_ref"]["resource_id"])
        if transition is not None and transition["subject_ref"]["resource_type"] == "POSITION_OCCUPANCY":
            return self.employee_adapter.documents_for_references(
                principal_ids=principal_ids,
                resource_ids=resource_ids,
            )
        return self.employee_adapter.documents_for_references(
            principal_ids=principal_ids,
            resource_ids=resource_ids,
        )

    def _validate_transition(self, transition: dict[str, Any]) -> None:
        try:
            validate_contract("leos.organization-lifecycle-transition.v1", transition)
        except ContractValidationError as exc:
            raise OrganizationDomainError(
                "illegal lifecycle transition",
                code="illegal_lifecycle_transition",
                status_code=409,
                details={"issues": [issue.__dict__ for issue in exc.issues]},
            ) from exc

    def _build_event(
        self,
        document: dict[str, Any],
        context: MutationContext,
        *,
        event_type: str,
        payload: dict[str, Any],
        evidence_ref: dict[str, Any],
        now: str | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        event_id = f"event:organization-domain:{uuid.uuid4()}"
        event_revision = f"sha256:event:{uuid.uuid4()}"
        event = {
            "contract_version": "leos.event-envelope.v1",
            "identity": {
                "resource_type": "EVENT",
                "resource_id": event_id,
                "display_name": f"Organization Domain event for {document['identity']['resource_id']}",
                "revision": event_revision,
                "ownership": {
                    "owner": document["identity"]["ownership"]["owner"],
                    "creator": AUTHORITY_PRINCIPAL,
                    "steward": AUTHORITY_PRINCIPAL,
                    "lifecycle_authority": document["identity"]["ownership"]["lifecycle_authority"],
                },
                "creation_actor_context_ref": actor_context_resource_ref(context.actor_context_ref),
                "creation_authority_evidence_ref": evidence_ref,
                "audit_id": f"audit:{event_id}",
                "created_at": now,
                "updated_at": now,
            },
            "event_type": event_type,
            "event_revision": 1,
            "source": EVENT_SOURCE_REF,
            "producer": document["identity"]["ownership"]["lifecycle_authority"]["principal"],
            "actor": {"principal_id": "principal:unknown:actor-context", "principal_type": "HUMAN_USER"},
            "actor_context_ref": context.actor_context_ref,
            "subject": resource_ref(document),
            "correlation_id": context.correlation_id,
            "causation": {
                "kind": "ROOT_ACTION",
                "reference_id": context.authorization_decision_ref["resource_id"],
            },
            "occurred_at": now,
            "recorded_at": now,
            "payload": payload,
        }
        return event

    def _build_transition_and_event(
        self,
        *,
        prior: dict[str, Any],
        current: dict[str, Any],
        context: MutationContext,
        from_status: str,
        to_status: str,
        now: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        transition_id = f"organization-transition:{prior['identity']['resource_id']}:{uuid.uuid4()}"
        transition_revision = f"sha256:transition:{uuid.uuid4()}"
        event_revision = f"sha256:event:{uuid.uuid4()}"
        event_placeholder = {
            "resource_type": "EVENT",
            "resource_id": f"event:organization-domain:{uuid.uuid4()}",
            "revision": event_revision,
        }
        transition = {
            "contract_version": "leos.organization-lifecycle-transition.v1",
            "identity": {
                "resource_type": "ORGANIZATION_TRANSITION",
                "resource_id": transition_id,
                "display_name": f"{prior['identity']['resource_id']} {from_status} to {to_status}",
                "revision": transition_revision,
                "ownership": {
                    "owner": current["identity"]["ownership"]["owner"],
                    "creator": AUTHORITY_PRINCIPAL,
                    "steward": AUTHORITY_PRINCIPAL,
                    "lifecycle_authority": current["identity"]["ownership"]["lifecycle_authority"],
                },
                "creation_actor_context_ref": actor_context_resource_ref(context.actor_context_ref),
                "creation_authority_evidence_ref": {
                    "authority_id": "authorization-authority",
                    "reference_id": context.authorization_decision_ref["resource_id"],
                    "revision": context.authorization_decision_ref["revision"],
                },
                "audit_id": f"audit:{transition_id}",
                "created_at": now,
                "updated_at": now,
            },
            "subject_ref": resource_ref(prior),
            "from_status": from_status,
            "to_status": to_status,
            "resulting_revision": current["identity"]["revision"],
            "actor_context_ref": context.actor_context_ref,
            "authorization_decision_ref": context.authorization_decision_ref,
            "approval_requirement": "NOT_REQUIRED",
            "resulting_event_ref": event_placeholder,
            "rollback_behavior": (
                "TERMINAL_NO_ROLLBACK"
                if to_status == "DELETED"
                else "COMPENSATING_TRANSITION_REQUIRED"
            ),
            "child_resource_behavior": "NO_CHILDREN",
            "transitioned_at": now,
        }
        event = {
            "contract_version": "leos.event-envelope.v1",
            "identity": {
                "resource_type": "EVENT",
                "resource_id": event_placeholder["resource_id"],
                "display_name": f"Lifecycle transition event for {current['identity']['resource_id']}",
                "revision": event_revision,
                "ownership": {
                    "owner": current["identity"]["ownership"]["owner"],
                    "creator": AUTHORITY_PRINCIPAL,
                    "steward": AUTHORITY_PRINCIPAL,
                    "lifecycle_authority": current["identity"]["ownership"]["lifecycle_authority"],
                },
                "creation_actor_context_ref": actor_context_resource_ref(context.actor_context_ref),
                "creation_authority_evidence_ref": {
                    "authority_id": transition["identity"]["ownership"]["lifecycle_authority"]["authority_id"],
                    "reference_id": transition["identity"]["resource_id"],
                    "revision": transition_revision,
                },
                "audit_id": f"audit:{event_placeholder['resource_id']}",
                "created_at": now,
                "updated_at": now,
            },
            "event_type": "organization-domain.lifecycle-transitioned",
            "event_revision": 1,
            "source": EVENT_SOURCE_REF,
            "producer": current["identity"]["ownership"]["lifecycle_authority"]["principal"],
            "actor": {"principal_id": "principal:unknown:actor-context", "principal_type": "HUMAN_USER"},
            "actor_context_ref": context.actor_context_ref,
            "subject": resource_ref(current),
            "correlation_id": context.correlation_id,
            "causation": {
                "kind": "ROOT_ACTION",
                "reference_id": context.authorization_decision_ref["resource_id"],
            },
            "occurred_at": now,
            "recorded_at": now,
            "payload": {
                "from_status": from_status,
                "to_status": to_status,
                "resulting_revision": current["identity"]["revision"],
            },
        }
        return transition, event
