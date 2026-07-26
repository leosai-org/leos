from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from leos_contracts import ContractValidationError, validate_contract


SERVICE_ID = "authorization-authority"
SERVICE_VERSION = "0.2.0-dev-preview-v2"
SERVICE_CONTRACT = "leos.authorization-authority.provisional-v1"
AUTHORITY_ID = "authorization-authority"
AUTHORITY_REVISION = "sha256:authorization-authority-policy-v1"
AUTHORITY_PRINCIPAL = {
    "principal_id": "principal:service:authorization-authority",
    "principal_type": "SERVICE",
}
AUTHORITY_REF = {
    "authority_id": AUTHORITY_ID,
    "principal": AUTHORITY_PRINCIPAL,
    "authority_revision": AUTHORITY_REVISION,
}
AUTHORITY_MANDATE_REF = {
    "authority_id": AUTHORITY_ID,
    "reference_id": "authority-mandate:authorization-evaluation",
    "revision": "sha256:authorization-authority-evaluate-v1",
}
EVENT_SOURCE_REF = {
    "resource_type": "EVENT_SOURCE",
    "resource_id": "event-source:authorization-authority",
    "revision": "sha256:event-source-authorization-authority-v1",
}

IDENTIFIER_MAX = 256
DECISION_TTL_SECONDS = 300
GRANT_TTL_SECONDS = 3600
MAX_TTL_SECONDS = 86_400

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
    "allow",
    "allowed",
    "approval",
    "approval_granted",
    "approved",
    "authorization",
    "authorization_granted",
    "authorized",
    "can_execute",
    "has_approval",
    "has_authorization",
    "is_approved",
    "is_authorized",
    "permission_granted",
    "permitted",
}
FORBIDDEN_PERMISSION_SHORTCUT_KEYS = {
    "capability_as_permission",
    "capability_present",
    "employee_role",
    "installed_plugin_grants_permission",
    "membership_grants_permission",
    "membership_permission",
    "membership_ref",
    "plugin_installation_grants_permission",
    "plugin_installation_ref",
    "plugin_installed",
    "role_grants_permission",
    "role_permission",
    "role_ref",
}
FORBIDDEN_AUTHORIZATION_DOCUMENT_KEYS = {
    "authorization_decision",
    "authorization_decision_json",
    "authorization_decision_record",
}

logger = logging.getLogger(SERVICE_ID)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def add_seconds(timestamp: str, seconds: int) -> str:
    value = parse_time(timestamp) + timedelta(seconds=seconds)
    return value.isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def revision_for(value: dict[str, Any]) -> str:
    clone = json.loads(canonical_json(value))
    identity = clone.get("identity")
    if isinstance(identity, dict):
        identity.pop("revision", None)
        identity.pop("updated_at", None)
    return sha256(clone)


def generated_id(prefix: str, value: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(value).encode()).hexdigest()[:24]
    return f"{prefix}:{digest}"


def parse_json(value: str) -> dict[str, Any]:
    return json.loads(value)


def require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationFailure(f"{field} must be an object")
    return value


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationFailure(f"{field} is required")
    if len(value) > IDENTIFIER_MAX:
        raise ValidationFailure(f"{field} is too long")
    return value


def require_ref(value: Any, field: str, *, revision_required: bool = True) -> dict[str, str]:
    ref = require_dict(value, field)
    resource_type = require_string(ref.get("resource_type"), f"{field}.resource_type")
    resource_id = require_string(ref.get("resource_id"), f"{field}.resource_id")
    normalized = {
        "resource_type": resource_type,
        "resource_id": resource_id,
    }
    if revision_required:
        normalized["revision"] = require_string(ref.get("revision"), f"{field}.revision")
    elif isinstance(ref.get("revision"), str):
        normalized["revision"] = ref["revision"]
    return normalized


def require_actor_context_ref(value: Any, field: str = "actor_context_ref") -> dict[str, Any]:
    ref = require_dict(value, field)
    if ref.get("evidence_type") != "ACTOR_CONTEXT":
        raise ValidationFailure(f"{field}.evidence_type must be ACTOR_CONTEXT")
    authority = require_dict(ref.get("authority"), f"{field}.authority")
    require_authority_ref(authority, f"{field}.authority")
    return {
        "evidence_type": "ACTOR_CONTEXT",
        "authority": authority,
        "reference_id": require_string(ref.get("reference_id"), f"{field}.reference_id"),
        "revision": require_string(ref.get("revision"), f"{field}.revision"),
    }


def require_authority_ref(value: Any, field: str) -> dict[str, Any]:
    ref = require_dict(value, field)
    principal = require_principal_ref(ref.get("principal"), f"{field}.principal")
    return {
        "authority_id": require_string(ref.get("authority_id"), f"{field}.authority_id"),
        "principal": principal,
        "authority_revision": require_string(
            ref.get("authority_revision"),
            f"{field}.authority_revision",
        ),
    }


def require_evidence_ref(value: Any, field: str) -> dict[str, Any]:
    ref = require_dict(value, field)
    authority = require_authority_ref(ref.get("authority"), f"{field}.authority")
    return {
        "authority": authority,
        "reference_id": require_string(ref.get("reference_id"), f"{field}.reference_id"),
        "revision": require_string(ref.get("revision"), f"{field}.revision"),
    }


def require_principal_ref(value: Any, field: str) -> dict[str, str]:
    ref = require_dict(value, field)
    return {
        "principal_id": require_string(ref.get("principal_id"), f"{field}.principal_id"),
        "principal_type": require_string(ref.get("principal_type"), f"{field}.principal_type"),
    }


def require_scope(value: Any) -> dict[str, Any]:
    scope = require_dict(value, "scope")
    return {
        "subject": require_principal_ref(scope.get("subject"), "scope.subject"),
        "action": require_string(scope.get("action"), "scope.action"),
        "resource": require_ref(scope.get("resource"), "scope.resource"),
        "context_type": require_string(scope.get("context_type"), "scope.context_type"),
        "context_id": require_string(scope.get("context_id"), "scope.context_id"),
        "context_revision": require_string(
            scope.get("context_revision"),
            "scope.context_revision",
        ),
        "context_digest": require_string(scope.get("context_digest"), "scope.context_digest"),
    }


def organization_id_for(ref: dict[str, Any]) -> str:
    if ref.get("resource_type") != "ORGANIZATION":
        raise ValidationFailure("organization_ref must reference an ORGANIZATION")
    return require_string(ref.get("resource_id"), "organization_ref.resource_id")


def resource_ref(document: dict[str, Any]) -> dict[str, str]:
    identity = document["identity"]
    return {
        "resource_type": identity["resource_type"],
        "resource_id": identity["resource_id"],
        "revision": identity["revision"],
    }


class AuthorizationAuthorityError(RuntimeError):
    status_code = 422
    code = "authorization_authority_error"

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


class NotFoundError(AuthorizationAuthorityError):
    status_code = 404
    code = "not_found"


class ConflictError(AuthorizationAuthorityError):
    status_code = 409
    code = "conflict"


class ValidationFailure(AuthorizationAuthorityError):
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


def reject_caller_authority_shortcuts(
    value: Any,
    path: str = "$",
    *,
    reject_decision_documents: bool = True,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in CALLER_AUTHORITY_BOOLEAN_KEYS and isinstance(child, bool):
                raise ValidationFailure(
                    "caller-supplied authorization or approval booleans are prohibited",
                    code="caller_authority_boolean_rejected",
                    details={"path": f"{path}.{key}"},
                )
            if normalized in FORBIDDEN_PERMISSION_SHORTCUT_KEYS:
                raise ValidationFailure(
                    "roles, membership, capability presence, and plugin installation "
                    "are not permissions",
                    code="permission_shortcut_rejected",
                    details={"path": f"{path}.{key}"},
                )
            if reject_decision_documents and normalized in FORBIDDEN_AUTHORIZATION_DOCUMENT_KEYS:
                raise ValidationFailure(
                    "client-issued Authorization Decision JSON is not authority",
                    code="client_authorization_decision_rejected",
                    details={"path": f"{path}.{key}"},
                )
            reject_caller_authority_shortcuts(
                child,
                f"{path}.{key}",
                reject_decision_documents=reject_decision_documents,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_caller_authority_shortcuts(
                child,
                f"{path}[{index}]",
                reject_decision_documents=reject_decision_documents,
            )


@contextmanager
def sqlite_tx(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


class AuthorizationStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS capability_permission_grants (
                    grant_id TEXT PRIMARY KEY,
                    revision TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    organization_ref_json TEXT NOT NULL,
                    subject_json TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_json TEXT NOT NULL,
                    capability_ref_json TEXT,
                    grant_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    revoked_at TEXT,
                    revocation_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_authz_grants_match
                    ON capability_permission_grants (
                        organization_id,
                        action,
                        status,
                        valid_until
                    );
                CREATE TABLE IF NOT EXISTS authorization_decisions (
                    decision_id TEXT PRIMARY KEY,
                    revision TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    organization_ref_json TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    actor_context_ref_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    revoked_at TEXT,
                    revocation_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_authz_decisions_org
                    ON authorization_decisions (organization_id, decision, valid_until);
                CREATE TABLE IF NOT EXISTS revocations (
                    revocation_id TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    target_revision TEXT NOT NULL,
                    actor_context_ref_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    revoked_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    subject_ref_json TEXT,
                    resource_ref_json TEXT,
                    actor_context_ref_json TEXT NOT NULL,
                    authority_ref_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (operation, idempotency_key)
                );
                """
            )

    def health(self) -> dict[str, Any]:
        return {"ok": True, "service": SERVICE_ID}

    def ready(self) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"ok": True, "service": SERVICE_ID, "database": str(self.database)}

    def outbox(self, organization_id: str | None = None) -> dict[str, Any]:
        with self.connect() as connection:
            if organization_id:
                rows = connection.execute(
                    "SELECT * FROM outbox WHERE organization_id = ? ORDER BY sequence",
                    (organization_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM outbox ORDER BY sequence",
                ).fetchall()
        return {"events": [self._event_from_row(row) for row in rows]}

    def issue_capability_grant(self, payload: dict[str, Any]) -> dict[str, Any]:
        reject_raw_secret_values(payload)
        reject_caller_authority_shortcuts(payload)
        actor_context_ref = require_actor_context_ref(payload.get("actor_context_ref"))
        organization_ref = require_ref(payload.get("organization_ref"), "organization_ref")
        organization_id = organization_id_for(organization_ref)
        subject = require_principal_ref(payload.get("subject"), "subject")
        action = require_string(payload.get("action"), "action")
        resource = require_ref(payload.get("resource"), "resource")
        capability_ref = None
        if payload.get("capability_ref") is not None:
            capability_ref = require_ref(payload.get("capability_ref"), "capability_ref")
            if capability_ref.get("resource_type") != "CAPABILITY":
                raise ValidationFailure("capability_ref must reference a CAPABILITY")
        valid_from = require_string(payload.get("valid_from") or utc_now(), "valid_from")
        valid_until = require_string(
            payload.get("valid_until") or add_seconds(valid_from, GRANT_TTL_SECONDS),
            "valid_until",
        )
        if parse_time(valid_until) <= parse_time(valid_from):
            raise ValidationFailure("valid_until must be later than valid_from")
        policy_version = require_string(
            payload.get("policy_version") or "dev-preview-v2-minimum",
            "policy_version",
        )
        grant_basis_refs = [
            require_evidence_ref(item, "grant_basis_refs[]")
            for item in payload.get("grant_basis_refs", [])
        ]
        idempotency_key = require_string(payload.get("idempotency_key"), "idempotency_key")
        requested_id = payload.get("grant_id")
        grant_seed = {
            "organization_ref": organization_ref,
            "subject": subject,
            "action": action,
            "resource": resource,
            "capability_ref": capability_ref,
            "policy_version": policy_version,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
        grant_id = (
            require_string(requested_id, "grant_id")
            if requested_id is not None
            else generated_id("capability-permission-grant", grant_seed)
        )
        issued_at = require_string(payload.get("issued_at") or utc_now(), "issued_at")
        grant = {
            "grant_id": grant_id,
            "revision": "pending",
            "organization_ref": organization_ref,
            "subject": subject,
            "action": action,
            "resource": resource,
            "capability_ref": capability_ref,
            "authority": AUTHORITY_REF,
            "actor_context_ref": actor_context_ref,
            "grant_basis_refs": grant_basis_refs,
            "policy_version": policy_version,
            "issued_at": issued_at,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "status": "ACTIVE",
            "audit_id": f"audit:{grant_id}",
        }
        if capability_ref is None:
            grant.pop("capability_ref")
        grant["revision"] = sha256(grant)
        response = {"grant": grant}
        return self._write_idempotent(
            "issue_capability_grant",
            idempotency_key,
            payload,
            lambda connection: self._insert_grant(
                connection,
                grant,
                organization_id,
                actor_context_ref,
            ),
            response,
        )

    def get_capability_grant(self, grant_id: str) -> dict[str, Any]:
        row = self._fetch_grant(grant_id)
        return {"grant": self._grant_from_row(row)}

    def list_capability_grants(
        self,
        *,
        organization_id: str | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        query = "SELECT * FROM capability_permission_grants"
        values: list[Any] = []
        clauses: list[str] = []
        if organization_id:
            clauses.append("organization_id = ?")
            values.append(organization_id)
        if subject_id:
            clauses.append("json_extract(subject_json, '$.principal_id') = ?")
            values.append(subject_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY grant_id"
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return {"grants": [self._grant_from_row(row) for row in rows]}

    def revoke_capability_grant(self, grant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        reject_raw_secret_values(payload)
        reject_caller_authority_shortcuts(payload)
        actor_context_ref = require_actor_context_ref(payload.get("actor_context_ref"))
        reason = require_string(payload.get("reason") or "revoked", "reason")
        revoked_at = require_string(payload.get("revoked_at") or utc_now(), "revoked_at")
        idempotency_key = require_string(payload.get("idempotency_key"), "idempotency_key")
        existing = self._fetch_grant(grant_id)
        if existing["status"] == "REVOKED":
            return {"grant": self._grant_from_row(existing)}
        response: dict[str, Any] = {}

        def write(connection: sqlite3.Connection) -> dict[str, Any]:
            current = connection.execute(
                "SELECT * FROM capability_permission_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
            if current is None:
                raise NotFoundError("capability permission grant was not found")
            grant = self._grant_from_row(current)
            grant["status"] = "REVOKED"
            grant["revoked_at"] = revoked_at
            grant["revocation_reason"] = reason
            connection.execute(
                """
                UPDATE capability_permission_grants
                   SET grant_json = ?, status = ?, revoked_at = ?, revocation_reason = ?
                 WHERE grant_id = ?
                """,
                (canonical_json(grant), "REVOKED", revoked_at, reason, grant_id),
            )
            self._insert_revocation(
                connection,
                "CAPABILITY_PERMISSION_GRANT",
                grant_id,
                grant["revision"],
                actor_context_ref,
                reason,
                revoked_at,
            )
            self._insert_event(
                connection,
                "authorization.capability_grant.revoked",
                current["organization_id"],
                actor_context_ref,
                payload={
                    "grant_ref": {
                        "authority": AUTHORITY_REF,
                        "reference_id": grant_id,
                        "revision": grant["revision"],
                    },
                    "reason": reason,
                },
                subject_ref=grant["subject"],
                resource_ref=grant["resource"],
                occurred_at=revoked_at,
            )
            response["grant"] = grant
            return response

        return self._write_idempotent(
            "revoke_capability_grant",
            idempotency_key,
            payload,
            write,
            response,
        )

    def create_authorization_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        reject_raw_secret_values(payload)
        reject_caller_authority_shortcuts(payload)
        actor_context_ref = require_actor_context_ref(payload.get("actor_context_ref"))
        organization_ref = require_ref(payload.get("organization_ref"), "organization_ref")
        organization_id = organization_id_for(organization_ref)
        subject = require_principal_ref(payload.get("subject"), "subject")
        action = require_string(payload.get("action"), "action")
        resource = require_ref(payload.get("resource"), "resource")
        context = require_dict(payload.get("context"), "context")
        scope = {
            "subject": subject,
            "action": action,
            "resource": resource,
            "context_type": require_string(context.get("context_type"), "context.context_type"),
            "context_id": require_string(context.get("context_id"), "context.context_id"),
            "context_revision": require_string(
                context.get("context_revision"),
                "context.context_revision",
            ),
            "context_digest": require_string(context.get("context_digest"), "context.context_digest"),
        }
        capability_ref = None
        if payload.get("capability_ref") is not None:
            capability_ref = require_ref(payload.get("capability_ref"), "capability_ref")
            if capability_ref.get("resource_type") != "CAPABILITY":
                raise ValidationFailure("capability_ref must reference a CAPABILITY")
        idempotency_key = require_string(payload.get("idempotency_key"), "idempotency_key")
        decided_at = require_string(
            payload.get("evaluation_timestamp") or payload.get("decided_at") or utc_now(),
            "evaluation_timestamp",
        )
        ttl_seconds = int(payload.get("ttl_seconds") or DECISION_TTL_SECONDS)
        if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
            raise ValidationFailure("ttl_seconds must be between 1 and 86400")
        valid_until = require_string(
            payload.get("valid_until") or add_seconds(decided_at, ttl_seconds),
            "valid_until",
        )
        if parse_time(valid_until) <= parse_time(decided_at):
            raise ValidationFailure("valid_until must be later than decided_at")
        matched_grants = self._eligible_grants(
            organization_id=organization_id,
            organization_ref=organization_ref,
            subject=subject,
            action=action,
            resource=resource,
            capability_ref=capability_ref,
            at=decided_at,
        )
        if matched_grants:
            decision_value = "ALLOW"
            reasons: list[str] = []
            evidence_refs = [
                {
                    "authority": AUTHORITY_REF,
                    "reference_id": grant["grant_id"],
                    "revision": grant["revision"],
                }
                for grant in matched_grants
            ]
        else:
            decision_value = "DENY"
            reasons = ["no_active_capability_permission_grant"]
            evidence_refs = []
        decision_seed = {
            "organization_ref": organization_ref,
            "actor_context_ref": actor_context_ref,
            "scope": scope,
            "decision": decision_value,
            "matched_grants": evidence_refs,
            "decided_at": decided_at,
            "valid_until": valid_until,
        }
        requested_id = payload.get("decision_id")
        decision_id = (
            require_string(requested_id, "decision_id")
            if requested_id is not None
            else generated_id("authorization-decision", decision_seed)
        )
        decision = self._authorization_decision_document(
            decision_id=decision_id,
            actor_context_ref=actor_context_ref,
            subject=subject,
            scope=scope,
            decision=decision_value,
            authority_evidence_refs=evidence_refs,
            reasons=reasons,
            decided_at=decided_at,
            valid_until=valid_until,
        )
        try:
            validate_contract("leos.authorization-decision.v1", decision)
        except ContractValidationError as error:
            raise ValidationFailure(
                "generated Authorization Decision failed canonical validation",
                code="generated_contract_invalid",
                details={"issues": [issue.__dict__ for issue in error.issues]},
            ) from error
        response = {
            "authorization_decision": decision,
            "decision_ref": {
                "resource_type": "AUTHORIZATION_DECISION",
                "resource_id": decision_id,
                "revision": decision["identity"]["revision"],
            },
            "status": decision_value,
        }
        return self._write_idempotent(
            "create_authorization_decision",
            idempotency_key,
            payload,
            lambda connection: self._insert_decision(
                connection,
                decision,
                organization_ref,
                organization_id,
                actor_context_ref,
            ),
            response,
        )

    def get_authorization_decision(self, decision_id: str) -> dict[str, Any]:
        row = self._fetch_decision(decision_id)
        return self._decision_response(row)

    def list_authorization_decisions(
        self,
        *,
        organization_id: str | None = None,
        subject_id: str | None = None,
    ) -> dict[str, Any]:
        query = "SELECT * FROM authorization_decisions"
        values: list[Any] = []
        clauses: list[str] = []
        if organization_id:
            clauses.append("organization_id = ?")
            values.append(organization_id)
        if subject_id:
            clauses.append("json_extract(scope_json, '$.subject.principal_id') = ?")
            values.append(subject_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY decision_id"
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return {"authorization_decisions": [self._decision_response(row) for row in rows]}

    def verify_authorization_decision(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        reject_raw_secret_values(payload)
        reject_caller_authority_shortcuts(payload)
        actor_context_ref = require_actor_context_ref(payload.get("actor_context_ref"))
        organization_ref = require_ref(payload.get("organization_ref"), "organization_ref")
        organization_id = organization_id_for(organization_ref)
        expected_scope = require_scope(payload.get("scope"))
        expected_decision = payload.get("expected_decision", "ALLOW")
        if expected_decision not in {"ALLOW", "DENY"}:
            raise ValidationFailure("expected_decision must be ALLOW or DENY")
        row = self._fetch_decision(decision_id)
        decision = parse_json(row["decision_json"])
        reasons: list[str] = []
        status = "VERIFIED"
        if row["organization_id"] != organization_id:
            status = "DENIED"
            reasons.append("organization_scope_mismatch")
        if row["revoked_at"] is not None:
            status = "DENIED"
            reasons.append("authorization_decision_revoked")
        if parse_time(row["valid_until"]) <= parse_time(utc_now()):
            status = "DENIED"
            reasons.append("authorization_decision_expired")
        if decision["scope"] != expected_scope:
            status = "DENIED"
            reasons.append("scope_mismatch")
        if decision["decision"] != expected_decision:
            status = "DENIED"
            reasons.append("decision_mismatch")
        if decision["authority"] != AUTHORITY_REF:
            status = "DENIED"
            reasons.append("authority_mismatch")
        return {
            "verification_status": status,
            "authorization_decision_ref": resource_ref(decision),
            "decision": decision["decision"],
            "verified_at": utc_now(),
            "verified_by": AUTHORITY_REF,
            "actor_context_ref": actor_context_ref,
            "reasons": reasons,
        }

    def revoke_authorization_decision(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        reject_raw_secret_values(payload)
        reject_caller_authority_shortcuts(payload)
        actor_context_ref = require_actor_context_ref(payload.get("actor_context_ref"))
        reason = require_string(payload.get("reason") or "revoked", "reason")
        revoked_at = require_string(payload.get("revoked_at") or utc_now(), "revoked_at")
        idempotency_key = require_string(payload.get("idempotency_key"), "idempotency_key")
        row = self._fetch_decision(decision_id)
        if row["revoked_at"] is not None:
            return self._decision_response(row)
        response: dict[str, Any] = {}

        def write(connection: sqlite3.Connection) -> dict[str, Any]:
            current = connection.execute(
                "SELECT * FROM authorization_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if current is None:
                raise NotFoundError("Authorization Decision was not found")
            connection.execute(
                """
                UPDATE authorization_decisions
                   SET revoked_at = ?, revocation_reason = ?
                 WHERE decision_id = ?
                """,
                (revoked_at, reason, decision_id),
            )
            decision = parse_json(current["decision_json"])
            self._insert_revocation(
                connection,
                "AUTHORIZATION_DECISION",
                decision_id,
                decision["identity"]["revision"],
                actor_context_ref,
                reason,
                revoked_at,
            )
            self._insert_event(
                connection,
                "authorization.decision.revoked",
                current["organization_id"],
                actor_context_ref,
                payload={
                    "authorization_decision_ref": resource_ref(decision),
                    "reason": reason,
                },
                subject_ref=decision["scope"]["subject"],
                resource_ref=decision["scope"]["resource"],
                occurred_at=revoked_at,
            )
            refreshed = connection.execute(
                "SELECT * FROM authorization_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            response.update(self._decision_response(refreshed))
            return response

        return self._write_idempotent(
            "revoke_authorization_decision",
            idempotency_key,
            payload,
            write,
            response,
        )

    def _authorization_decision_document(
        self,
        *,
        decision_id: str,
        actor_context_ref: dict[str, Any],
        subject: dict[str, str],
        scope: dict[str, Any],
        decision: str,
        authority_evidence_refs: list[dict[str, Any]],
        reasons: list[str],
        decided_at: str,
        valid_until: str,
    ) -> dict[str, Any]:
        document = {
            "contract_version": "leos.authorization-decision.v1",
            "identity": {
                "resource_type": "AUTHORIZATION_DECISION",
                "resource_id": decision_id,
                "display_name": f"Authorization Decision {decision_id}",
                "revision": "pending",
                "ownership": {
                    "owner": subject,
                    "creator": AUTHORITY_PRINCIPAL,
                    "steward": AUTHORITY_PRINCIPAL,
                    "lifecycle_authority": AUTHORITY_REF,
                },
                "creation_actor_context_ref": {
                    "resource_type": "ACTOR_CONTEXT",
                    "resource_id": actor_context_ref["reference_id"],
                    "revision": actor_context_ref["revision"],
                },
                "creation_authority_evidence_ref": AUTHORITY_MANDATE_REF,
                "audit_id": f"audit:{decision_id}",
                "created_at": decided_at,
                "updated_at": decided_at,
            },
            "actor_context_ref": actor_context_ref,
            "scope": scope,
            "decision": decision,
            "authority": AUTHORITY_REF,
            "authority_evidence_refs": authority_evidence_refs,
            "reasons": reasons,
            "decided_at": decided_at,
            "valid_until": valid_until,
        }
        document["identity"]["revision"] = revision_for(document)
        return document

    def _eligible_grants(
        self,
        *,
        organization_id: str,
        organization_ref: dict[str, str],
        subject: dict[str, str],
        action: str,
        resource: dict[str, str],
        capability_ref: dict[str, str] | None,
        at: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM capability_permission_grants
                 WHERE organization_id = ?
                   AND action = ?
                   AND status = 'ACTIVE'
                   AND valid_from <= ?
                   AND valid_until > ?
                   AND revoked_at IS NULL
                 ORDER BY grant_id
                """,
                (organization_id, action, at, at),
            ).fetchall()
        grants = [self._grant_from_row(row) for row in rows]
        return [
            grant
            for grant in grants
            if grant["subject"] == subject
            and grant["organization_ref"] == organization_ref
            and grant["resource"] == resource
            and grant.get("capability_ref") == capability_ref
        ]

    def _insert_grant(
        self,
        connection: sqlite3.Connection,
        grant: dict[str, Any],
        organization_id: str,
        actor_context_ref: dict[str, Any],
    ) -> dict[str, Any]:
        existing = connection.execute(
            "SELECT grant_id FROM capability_permission_grants WHERE grant_id = ?",
            (grant["grant_id"],),
        ).fetchone()
        if existing is not None:
            raise ConflictError("capability permission grant already exists")
        connection.execute(
            """
            INSERT INTO capability_permission_grants (
                grant_id,
                revision,
                organization_id,
                organization_ref_json,
                subject_json,
                action,
                resource_json,
                capability_ref_json,
                grant_json,
                status,
                issued_at,
                valid_from,
                valid_until
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                grant["grant_id"],
                grant["revision"],
                organization_id,
                canonical_json(grant["organization_ref"]),
                canonical_json(grant["subject"]),
                grant["action"],
                canonical_json(grant["resource"]),
                canonical_json(grant.get("capability_ref"))
                if grant.get("capability_ref")
                else None,
                canonical_json(grant),
                grant["status"],
                grant["issued_at"],
                grant["valid_from"],
                grant["valid_until"],
            ),
        )
        self._insert_event(
            connection,
            "authorization.capability_grant.issued",
            organization_id,
            actor_context_ref,
            payload={
                "grant_ref": {
                    "authority": AUTHORITY_REF,
                    "reference_id": grant["grant_id"],
                    "revision": grant["revision"],
                }
            },
            subject_ref=grant["subject"],
            resource_ref=grant["resource"],
            occurred_at=grant["issued_at"],
        )
        return {"grant": grant}

    def _insert_decision(
        self,
        connection: sqlite3.Connection,
        decision: dict[str, Any],
        organization_ref: dict[str, str],
        organization_id: str,
        actor_context_ref: dict[str, Any],
    ) -> dict[str, Any]:
        decision_id = decision["identity"]["resource_id"]
        existing = connection.execute(
            "SELECT decision_id FROM authorization_decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if existing is not None:
            raise ConflictError("Authorization Decision already exists")
        connection.execute(
            """
            INSERT INTO authorization_decisions (
                decision_id,
                revision,
                organization_id,
                organization_ref_json,
                scope_json,
                actor_context_ref_json,
                decision_json,
                decision,
                decided_at,
                valid_until
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                decision["identity"]["revision"],
                organization_id,
                canonical_json(organization_ref),
                canonical_json(decision["scope"]),
                canonical_json(actor_context_ref),
                canonical_json(decision),
                decision["decision"],
                decision["decided_at"],
                decision["valid_until"],
            ),
        )
        self._insert_event(
            connection,
            "authorization.decision.created",
            organization_id,
            actor_context_ref,
            payload={
                "authorization_decision_ref": resource_ref(decision),
                "decision": decision["decision"],
            },
            subject_ref=decision["scope"]["subject"],
            resource_ref=decision["scope"]["resource"],
            occurred_at=decision["decided_at"],
        )
        return {
            "authorization_decision": decision,
            "decision_ref": resource_ref(decision),
            "status": decision["decision"],
        }

    def _insert_revocation(
        self,
        connection: sqlite3.Connection,
        target_type: str,
        target_id: str,
        target_revision: str,
        actor_context_ref: dict[str, Any],
        reason: str,
        revoked_at: str,
    ) -> None:
        revocation_id = generated_id(
            "authorization-revocation",
            {
                "target_type": target_type,
                "target_id": target_id,
                "target_revision": target_revision,
                "revoked_at": revoked_at,
                "reason": reason,
            },
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO revocations (
                revocation_id,
                target_type,
                target_id,
                target_revision,
                actor_context_ref_json,
                reason,
                revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revocation_id,
                target_type,
                target_id,
                target_revision,
                canonical_json(actor_context_ref),
                reason,
                revoked_at,
            ),
        )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        organization_id: str,
        actor_context_ref: dict[str, Any],
        *,
        payload: dict[str, Any],
        subject_ref: dict[str, Any] | None,
        resource_ref: dict[str, Any] | None,
        occurred_at: str,
    ) -> None:
        event_seed = {
            "event_type": event_type,
            "organization_id": organization_id,
            "payload": payload,
            "occurred_at": occurred_at,
        }
        event_id = generated_id("event:authorization", event_seed)
        connection.execute(
            """
            INSERT INTO outbox (
                event_id,
                event_type,
                organization_id,
                subject_ref_json,
                resource_ref_json,
                actor_context_ref_json,
                authority_ref_json,
                payload_json,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                organization_id,
                canonical_json(subject_ref) if subject_ref else None,
                canonical_json(resource_ref) if resource_ref else None,
                canonical_json(actor_context_ref),
                canonical_json(AUTHORITY_REF),
                canonical_json(payload),
                occurred_at,
            ),
        )

    def _write_idempotent(
        self,
        operation: str,
        idempotency_key: str,
        request: dict[str, Any],
        write,
        predicted_response: dict[str, Any],
    ) -> dict[str, Any]:
        request_hash = sha256(request)
        with self.connect() as connection:
            with sqlite_tx(connection):
                existing = connection.execute(
                    """
                    SELECT request_hash, response_json
                      FROM idempotency_keys
                     WHERE operation = ? AND idempotency_key = ?
                    """,
                    (operation, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_hash"] != request_hash:
                        raise ConflictError("idempotency key reused with different payload")
                    return parse_json(existing["response_json"])
                response = write(connection) or predicted_response
                connection.execute(
                    """
                    INSERT INTO idempotency_keys (
                        operation,
                        idempotency_key,
                        request_hash,
                        response_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        operation,
                        idempotency_key,
                        request_hash,
                        canonical_json(response),
                        utc_now(),
                    ),
                )
                return response

    def _fetch_grant(self, grant_id: str) -> sqlite3.Row:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM capability_permission_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("capability permission grant was not found")
        return row

    def _fetch_decision(self, decision_id: str) -> sqlite3.Row:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM authorization_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("Authorization Decision was not found")
        return row

    def _grant_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        grant = parse_json(row["grant_json"])
        if row["status"] == "REVOKED":
            grant["status"] = "REVOKED"
            grant["revoked_at"] = row["revoked_at"]
            grant["revocation_reason"] = row["revocation_reason"]
        elif parse_time(row["valid_until"]) <= parse_time(utc_now()):
            grant["status"] = "EXPIRED"
        return grant

    def _decision_response(self, row: sqlite3.Row) -> dict[str, Any]:
        decision = parse_json(row["decision_json"])
        response = {
            "authorization_decision": decision,
            "decision_ref": resource_ref(decision),
            "status": decision["decision"],
            "revoked": row["revoked_at"] is not None,
            "expired": parse_time(row["valid_until"]) <= parse_time(utc_now()),
        }
        if row["revoked_at"] is not None:
            response["revoked_at"] = row["revoked_at"]
            response["revocation_reason"] = row["revocation_reason"]
        return response

    def _event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "sequence": row["sequence"],
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "organization_id": row["organization_id"],
            "subject_ref": parse_json(row["subject_ref_json"])
            if row["subject_ref_json"]
            else None,
            "resource_ref": parse_json(row["resource_ref_json"])
            if row["resource_ref_json"]
            else None,
            "actor_context_ref": parse_json(row["actor_context_ref_json"]),
            "authority": parse_json(row["authority_ref_json"]),
            "payload": parse_json(row["payload_json"]),
            "occurred_at": row["occurred_at"],
        }
