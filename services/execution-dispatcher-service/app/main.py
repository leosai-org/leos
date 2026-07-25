from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query
from leos_contracts import (
    ContractValidationError,
    validate_contract as validate_governed_contract,
)
from pydantic import BaseModel, Field

SERVICE_VERSION = "0.2.0-dev-preview-v2"
EXECUTION_CONTRACT = "leos.execution.v1"
RESOLUTION_REQUEST_CONTRACT = "leos.capability-resolution-request.v1"
RESOLUTION_RESULT_CONTRACT = "leos.capability-resolution-result.v1"
EXECUTION_RESULT_CONTRACT = "leos.execution-result.v1"
DATA_DIR = Path(
    os.getenv(
        "EXECUTION_DISPATCHER_DATA_DIR",
        "/data/execution-dispatcher",
    )
)
DB_PATH = DATA_DIR / "execution-dispatcher.db"
CAPABILITY_MANAGER_URL = os.getenv(
    "CAPABILITY_MANAGER_URL",
    "http://capability-manager-service:8000",
).rstrip("/")
TIMEOUT = float(os.getenv("EXECUTION_DISPATCHER_TIMEOUT_SECONDS", "120"))
MAX_RETRIES = max(
    0,
    int(os.getenv("EXECUTION_DISPATCHER_MAX_PROVIDER_RETRIES", "1")),
)
DEFAULT_SHAPE = "canonical_envelope"
SCHEMA_REVISION = "epic-1.2c-v2"

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}
AUDIT_CREDENTIAL_KEYS = SENSITIVE_KEYS - {"key", "secret", "token"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def table_names(db: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def migrate() -> None:
    with connect() as db:
        existing = table_names(db)
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS dispatcher_schema (
                component TEXT PRIMARY KEY,
                revision TEXT NOT NULL,
                migrated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_adapters (
                adapter_id TEXT PRIMARY KEY,
                capability_id TEXT,
                provider_id TEXT,
                request_shape TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 100,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS canonical_executions (
                execution_id TEXT PRIMARY KEY,
                contract_version TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                status TEXT NOT NULL,
                resolution_id TEXT NOT NULL,
                request_json TEXT NOT NULL,
                resolution_json TEXT NOT NULL,
                authorized_target_json TEXT,
                outbound_evidence_json TEXT,
                attempts_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                raw_provider_evidence_json TEXT,
                correlation_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_claims (
                execution_id TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL,
                request_json TEXT NOT NULL,
                resolution_json TEXT,
                lifecycle_state TEXT NOT NULL,
                started_at TEXT NOT NULL,
                claimed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS canonical_invocation_attempts (
                invocation_attempt_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                provider_id TEXT NOT NULL,
                provider_url TEXT NOT NULL,
                request_shape TEXT NOT NULL,
                status TEXT NOT NULL,
                provider_status INTEGER,
                provider_operation_id TEXT,
                outbound_evidence_json TEXT,
                error_evidence_json TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                UNIQUE(execution_id, attempt_number)
            );
            """
        )
        claim_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(execution_claims)")
        }
        for name, declaration in (
            ("request_fingerprint", "TEXT"),
            ("request_json", "TEXT"),
            ("resolution_json", "TEXT"),
            ("lifecycle_state", "TEXT"),
            ("started_at", "TEXT"),
            ("updated_at", "TEXT"),
        ):
            if name not in claim_columns:
                db.execute(
                    f"ALTER TABLE execution_claims ADD COLUMN {name} {declaration}"
                )
        attempt_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(canonical_invocation_attempts)"
            )
        }
        for name in ("outbound_evidence_json", "error_evidence_json"):
            if name not in attempt_columns:
                db.execute(
                    "ALTER TABLE canonical_invocation_attempts "
                    f"ADD COLUMN {name} TEXT"
                )
        timestamp = now()
        db.execute(
            """
            INSERT INTO dispatcher_schema(component, revision, migrated_at)
            VALUES('execution-dispatcher', ?, ?)
            ON CONFLICT(component) DO UPDATE SET
                revision=excluded.revision,
                migrated_at=excluded.migrated_at
            """,
            (SCHEMA_REVISION, timestamp),
        )
        if "executions" in existing:
            db.execute(
                """
                INSERT INTO dispatcher_schema(component, revision, migrated_at)
                VALUES('legacy-executions', 'retained-read-only', ?)
                ON CONFLICT(component) DO NOTHING
                """,
                (timestamp,),
            )


class AdapterCreate(BaseModel):
    adapter_id: str
    capability_id: Optional[str] = None
    provider_id: Optional[str] = None
    request_shape: str
    enabled: bool = True
    priority: int = 100
    metadata: dict[str, Any] = Field(default_factory=dict)


migrate()
app = FastAPI(title="LEOS Execution Dispatcher", version=SERVICE_VERSION)


def validation_error(
    error: ContractValidationError,
    *,
    source: str,
    status_code: int,
) -> HTTPException:
    return HTTPException(
        status_code,
        {
            "code": "canonical_contract_validation_failed",
            "source": source,
            "contract": error.contract_id,
            "issues": [
                {
                    "kind": issue.kind,
                    "path": issue.path,
                    "message": issue.message,
                }
                for issue in error.issues
            ],
        },
    )


def validate_or_raise(
    contract_id: str,
    document: dict[str, Any],
    *,
    source: str,
    status_code: int,
) -> None:
    try:
        validate_governed_contract(contract_id, document)
    except ContractValidationError as error:
        raise validation_error(
            error,
            source=source,
            status_code=status_code,
        ) from error


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.lower() in AUDIT_CREDENTIAL_KEYS
                else redact_sensitive(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(child) for child in value]
    return value


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower() in SENSITIVE_KEYS or contains_sensitive_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_sensitive_key(child) for child in value)
    return False


def build_resolution_request(
    execution_request: dict[str, Any],
    *,
    requested_at: Optional[str] = None,
) -> dict[str, Any]:
    execution_policy = execution_request["policy"]
    resolution_policy: dict[str, Any] = {}
    for key in (
        "effective_intelligence_policy_ref",
        "approval_grant_refs",
    ):
        if key in execution_policy:
            resolution_policy[key] = execution_policy[key]
    request = {
        "contract_version": RESOLUTION_REQUEST_CONTRACT,
        "capability_id": execution_request["capability_id"],
        "requester": dict(execution_request["requester"]),
        "constraints": {},
        "policy": resolution_policy,
        "correlation": dict(execution_request["trace"]),
        "requested_at": requested_at or now(),
    }
    validate_or_raise(
        RESOLUTION_REQUEST_CONTRACT,
        request,
        source="execution-dispatcher",
        status_code=500,
    )
    return request


async def capability_manager_post(
    path: str,
    payload: dict[str, Any],
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.post(
            f"{CAPABILITY_MANAGER_URL}{path}",
            json=payload,
        )


async def capability_manager_get(
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.get(
            f"{CAPABILITY_MANAGER_URL}{path}",
            params=params,
        )


def response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"content": response.text}


async def resolve_capability(
    resolution_request: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = await capability_manager_post(
            "/resolve",
            resolution_request,
        )
    except httpx.RequestError as error:
        raise HTTPException(
            502,
            {
                "code": "capability_manager_unavailable",
                "message": str(error),
            },
        ) from error
    body = response_body(response)
    if response.status_code >= 400:
        raise HTTPException(
            502,
            {
                "code": "capability_resolution_failed",
                "status": response.status_code,
                "response": redact_sensitive(body),
            },
        )
    if not isinstance(body, dict):
        raise HTTPException(
            502,
            {"code": "invalid_capability_resolution_result"},
        )
    validate_or_raise(
        RESOLUTION_RESULT_CONTRACT,
        body,
        source="capability-manager",
        status_code=502,
    )
    return body


def verify_resolution_binding(
    execution_request: dict[str, Any],
    resolution: dict[str, Any],
) -> None:
    if resolution["capability_id"] != execution_request["capability_id"]:
        raise HTTPException(
            502,
            {"code": "resolution_capability_mismatch"},
        )
    if resolution["requester"] != execution_request["requester"]:
        raise HTTPException(
            502,
            {"code": "resolution_requester_mismatch"},
        )
    correlation = resolution["correlation"]
    if correlation.get("execution_id") != execution_request["execution_id"]:
        raise HTTPException(
            502,
            {"code": "resolution_execution_mismatch"},
        )


async def provider_inventory_record(
    capability_id: str,
    selected_target: dict[str, Any],
) -> dict[str, Any]:
    provider_id = selected_target["provider_id"]
    target_ref = selected_target.get("target_ref")
    if (
        not isinstance(target_ref, dict)
        or target_ref.get("authority") != "capability-manager"
        or target_ref.get("reference_id") != provider_id
    ):
        raise HTTPException(
            502,
            {"code": "unverifiable_provider_target_reference"},
        )
    try:
        response = await capability_manager_get(
            "/providers",
            params={"capability_id": capability_id, "limit": 2000},
        )
    except httpx.RequestError as error:
        raise HTTPException(
            502,
            {
                "code": "provider_inventory_unavailable",
                "message": str(error),
            },
        ) from error
    body = response_body(response)
    if response.status_code >= 400 or not isinstance(body, dict):
        raise HTTPException(
            502,
            {"code": "provider_inventory_lookup_failed"},
        )
    providers = body.get("providers")
    if not isinstance(providers, list):
        raise HTTPException(
            502,
            {"code": "invalid_provider_inventory_response"},
        )
    matches = [
        item
        for item in providers
        if isinstance(item, dict) and item.get("provider_id") == provider_id
    ]
    if len(matches) != 1:
        raise HTTPException(
            502,
            {"code": "resolved_provider_inventory_mismatch"},
        )
    provider = matches[0]
    revision = target_ref.get("revision")
    if not isinstance(revision, str) or not revision:
        raise HTTPException(
            502,
            {"code": "resolved_provider_revision_required"},
        )
    if provider.get("updated_at") != revision:
        raise HTTPException(
            502,
            {"code": "resolved_provider_revision_mismatch"},
        )
    return provider


def target_url(provider: dict[str, Any]) -> str:
    base_url = provider.get("base_url")
    execute_path = provider.get("execute_path") or "/execute"
    if not isinstance(base_url, str) or not base_url:
        raise HTTPException(
            502,
            {"code": "resolved_provider_has_no_endpoint"},
        )
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise HTTPException(
            502,
            {"code": "invalid_resolved_provider_endpoint"},
        )
    return base_url.rstrip("/") + "/" + str(execute_path).lstrip("/")


def adapter_selection(
    capability_id: str,
    selected_target: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    provider_id = selected_target["provider_id"]
    adapter_id = selected_target.get("adapter_id")
    with connect() as db:
        if adapter_id:
            row = db.execute(
                """
                SELECT * FROM provider_adapters
                WHERE adapter_id=? AND enabled=1
                  AND (capability_id IS NULL OR capability_id=?)
                  AND (provider_id IS NULL OR provider_id=?)
                """,
                (adapter_id, capability_id, provider_id),
            ).fetchone()
            if row is None:
                raise HTTPException(
                    502,
                    {"code": "resolved_adapter_unavailable"},
                )
        else:
            row = db.execute(
                """
                SELECT * FROM provider_adapters
                WHERE enabled=1
                  AND (capability_id IS NULL OR capability_id=?)
                  AND (provider_id IS NULL OR provider_id=?)
                ORDER BY
                  CASE WHEN provider_id IS NOT NULL THEN 0 ELSE 1 END,
                  CASE WHEN capability_id IS NOT NULL THEN 0 ELSE 1 END,
                  priority ASC,
                  adapter_id ASC
                LIMIT 1
                """,
                (capability_id, provider_id),
            ).fetchone()
    if row is None:
        return DEFAULT_SHAPE, {
            "adapter_id": None,
            "provider_id": provider_id,
            "metadata": {},
        }
    return row["request_shape"], {
        "adapter_id": row["adapter_id"],
        "provider_id": provider_id,
        "metadata": parse_metadata(row["metadata_json"]),
    }


def shape_payload(
    shape: str,
    execution_request: dict[str, Any],
) -> dict[str, Any]:
    if shape == "flat_input":
        return dict(execution_request["input"])
    if shape in {"canonical_envelope", "leos_execution_v1"}:
        return dict(execution_request)
    raise HTTPException(
        502,
        {
            "code": "unsupported_provider_request_shape",
            "request_shape": shape,
        },
    )


def execution_target(selected_target: dict[str, Any]) -> dict[str, Any]:
    return {
        key: selected_target[key]
        for key in ("provider_id", "provider_type", "adapter_id", "target_ref")
        if key in selected_target
    }


def resolution_reference(resolution: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority": "capability-manager",
        "reference_id": resolution["resolution_id"],
    }


def result_correlation(resolution: dict[str, Any]) -> dict[str, Any]:
    return dict(resolution["correlation"])


def empty_attempt_summary() -> dict[str, Any]:
    return {"attempt_count": 0, "attempts": []}


def non_invoked_result(
    execution_request: dict[str, Any],
    resolution: dict[str, Any],
    *,
    started_at: str,
) -> dict[str, Any]:
    status = resolution["status"]
    result: dict[str, Any] = {
        "contract_version": EXECUTION_RESULT_CONTRACT,
        "execution_id": execution_request["execution_id"],
        "status": status,
        "capability_id": execution_request["capability_id"],
        "resolution_ref": resolution_reference(resolution),
        "attempt_summary": empty_attempt_summary(),
        "correlation": result_correlation(resolution),
        "started_at": started_at,
        "completed_at": now(),
    }
    if status == "APPROVAL_PENDING":
        result["approval_requirement_ref"] = resolution[
            "approval_requirement_ref"
        ]
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        result,
        source="execution-dispatcher",
        status_code=500,
    )
    return result


def rejection_result(
    execution_request: dict[str, Any],
    resolution: dict[str, Any],
    *,
    started_at: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    result = {
        "contract_version": EXECUTION_RESULT_CONTRACT,
        "execution_id": execution_request["execution_id"],
        "status": "REJECTED",
        "capability_id": execution_request["capability_id"],
        "resolution_ref": resolution_reference(resolution),
        "attempt_summary": empty_attempt_summary(),
        "error": {
            "code": code,
            "message": message,
            "retryable_same_target": False,
            "remote_side_effect_possible": False,
        },
        "correlation": result_correlation(resolution),
        "started_at": started_at,
        "completed_at": now(),
    }
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        result,
        source="execution-dispatcher",
        status_code=500,
    )
    return result


def provider_operation_id(body: Any) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    for key in ("provider_operation_id", "operation_id"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def normalized_provider_result(
    response: httpx.Response,
    body: Any,
) -> Any:
    if not (
        isinstance(body, dict)
        and set(body) == {"content"}
        and body["content"] == response.text
    ):
        return body
    return {
        "content": response.text,
        "media_type": response.headers.get(
            "content-type",
            "text/plain",
        ).split(";", 1)[0],
    }


def retry_is_authorized(
    execution_request: dict[str, Any],
    adapter: dict[str, Any],
) -> bool:
    # Technical retry capability is not governed retry authority. No
    # execution-policy authority exists in Epic 1.2C.
    return False


async def invoke_authorized_target(
    execution_request: dict[str, Any],
    selected_target: dict[str, Any],
    provider: dict[str, Any],
    shape: str,
    adapter: dict[str, Any],
) -> tuple[
    str,
    Any,
    Optional[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    url = target_url(provider)
    payload = shape_payload(shape, execution_request)
    headers: dict[str, str] = {}
    attempts: list[dict[str, Any]] = []
    attempt_audits: list[dict[str, Any]] = []
    final_body: Any = None
    final_error: Optional[dict[str, Any]] = None
    final_status = "TRANSPORT_ERROR"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt_number in range(1, 2):
            attempt_id = str(uuid.uuid4())
            started_at = now()
            outbound = outbound_evidence(
                url,
                shape,
                payload,
                adapter,
                idempotency_key_transmitted=False,
            )
            journal_attempt_in_flight(
                execution_request["execution_id"],
                attempt_id,
                attempt_number,
                selected_target["provider_id"],
                url,
                shape,
                started_at,
                outbound,
            )
            provider_status: Optional[int] = None
            operation_id: Optional[str] = None
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                )
                provider_status = response.status_code
                body = response_body(response)
                final_body = body
                operation_id = provider_operation_id(body)
                if 200 <= response.status_code < 300:
                    final_status = "SUCCESS"
                    final_error = None
                    normalized = normalized_provider_result(response, body)
                    final_body = normalized
                else:
                    final_status = "AMBIGUOUS_OUTCOME"
                    final_error = {
                        "code": "ambiguous_provider_response",
                        "message": (
                            "The provider returned a non-success response "
                            "after transmission; remote effects are unknown."
                        ),
                        "retryable_same_target": False,
                        "remote_side_effect_possible": True,
                        "details": {
                            "provider_status": response.status_code,
                        },
                    }
                    normalized = None
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                final_status = "TRANSPORT_ERROR"
                final_body = None
                final_error = {
                    "code": "transport_error",
                    "message": str(error) or "Provider connection failed.",
                    "retryable_same_target": False,
                    "remote_side_effect_possible": False,
                }
                normalized = None
            except httpx.RequestError as error:
                final_status = "AMBIGUOUS_OUTCOME"
                final_body = None
                final_error = {
                    "code": "ambiguous_transport_outcome",
                    "message": (
                        str(error)
                        or "Provider transmission outcome is unknown."
                    ),
                    "retryable_same_target": False,
                    "remote_side_effect_possible": True,
                }
                normalized = None

            completed_at = now()
            attempt = {
                "invocation_attempt_id": attempt_id,
                "attempt_number": attempt_number,
                "status": final_status,
                "started_at": started_at,
                "completed_at": completed_at,
            }
            if operation_id:
                attempt["provider_operation_id"] = operation_id
            attempts.append(attempt)
            attempt_audits.append(
                {
                    **attempt,
                    "provider_id": selected_target["provider_id"],
                    "provider_url": url,
                    "request_shape": shape,
                    "provider_status": provider_status,
                }
            )
            finish_journal_attempt(
                attempt_id,
                final_status,
                completed_at,
                provider_status,
                operation_id,
                final_error,
            )
            break

    return (
        final_status,
        final_body,
        final_error,
        attempts,
        attempt_audits,
    )


def invoked_result(
    execution_request: dict[str, Any],
    resolution: dict[str, Any],
    *,
    started_at: str,
    status: str,
    normalized: Any,
    error: Optional[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    correlation = result_correlation(resolution)
    if attempts:
        correlation["invocation_attempt_id"] = attempts[-1][
            "invocation_attempt_id"
        ]
        operation_id = attempts[-1].get("provider_operation_id")
        if operation_id:
            correlation["provider_operation_id"] = operation_id
    summary: dict[str, Any] = {
        "attempt_count": len(attempts),
        "attempts": attempts,
    }
    idempotency_key = execution_request["policy"].get("idempotency_key")
    if idempotency_key:
        summary["idempotency_key"] = idempotency_key
    result: dict[str, Any] = {
        "contract_version": EXECUTION_RESULT_CONTRACT,
        "execution_id": execution_request["execution_id"],
        "status": status,
        "capability_id": execution_request["capability_id"],
        "resolution_ref": resolution_reference(resolution),
        "authorized_target": execution_target(
            resolution["selected_target"]
        ),
        "attempt_summary": summary,
        "correlation": correlation,
        "started_at": started_at,
        "completed_at": now(),
    }
    if status == "SUCCESS":
        result["normalized_result"] = normalized
    else:
        result["error"] = error
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        result,
        source="execution-dispatcher",
        status_code=500,
    )
    return result


def outbound_evidence(
    provider_url: str,
    shape: str,
    payload: dict[str, Any],
    adapter: dict[str, Any],
    *,
    idempotency_key_transmitted: bool,
) -> dict[str, Any]:
    return {
        "provider_url": provider_url,
        "request_shape": shape,
        "adapter_id": adapter["adapter_id"],
        "provider_id": adapter["provider_id"],
        "payload": redact_sensitive(payload),
        "idempotency_key_transmitted": idempotency_key_transmitted,
    }


def canonical_fingerprint(request: dict[str, Any]) -> str:
    encoded = json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def claim_execution(request: dict[str, Any]) -> Optional[dict[str, Any]]:
    execution_id = request["execution_id"]
    fingerprint = canonical_fingerprint(request)
    timestamp = now()
    with connect() as db:
        try:
            db.execute(
                """
                INSERT INTO execution_claims(
                    execution_id, request_fingerprint, request_json,
                    lifecycle_state, started_at, claimed_at, updated_at
                ) VALUES(?, ?, ?, 'CLAIMED', ?, ?, ?)
                """,
                (
                    execution_id,
                    fingerprint,
                    json.dumps(redact_sensitive(request), sort_keys=True),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        except sqlite3.IntegrityError as error:
            row = db.execute(
                "SELECT * FROM execution_claims WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            if row is None or row["request_fingerprint"] != fingerprint:
                raise HTTPException(
                    409, {"code": "execution_identity_conflict"}
                ) from error
            completed = db.execute(
                "SELECT result_json FROM canonical_executions "
                "WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            if completed is not None:
                result = json.loads(completed["result_json"])
                validate_or_raise(
                    EXECUTION_RESULT_CONTRACT,
                    result,
                    source="execution-dispatcher-persistence",
                    status_code=500,
                )
                return result
            if row["lifecycle_state"] == "IN_FLIGHT":
                return recover_orphaned_in_flight(db, row)
            raise HTTPException(
                409, {"code": "execution_already_active"}
            ) from error
    return None


def release_pretransmission_claim(execution_id: str) -> None:
    with connect() as db:
        db.execute(
            "DELETE FROM execution_claims "
            "WHERE execution_id=? AND lifecycle_state='CLAIMED'",
            (execution_id,),
        )


def store_claim_resolution(
    execution_id: str, resolution: dict[str, Any]
) -> None:
    with connect() as db:
        db.execute(
            "UPDATE execution_claims SET resolution_json=?, updated_at=? "
            "WHERE execution_id=? AND lifecycle_state='CLAIMED'",
            (json.dumps(resolution), now(), execution_id),
        )


def journal_attempt_in_flight(
    execution_id: str,
    attempt_id: str,
    attempt_number: int,
    provider_id: str,
    provider_url: str,
    request_shape: str,
    started_at: str,
    outbound: dict[str, Any],
) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT INTO canonical_invocation_attempts(
                invocation_attempt_id, execution_id, attempt_number,
                provider_id, provider_url, request_shape, status,
                outbound_evidence_json, started_at, completed_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'IN_FLIGHT', ?, ?, ?)
            """,
            (
                attempt_id, execution_id, attempt_number, provider_id,
                provider_url, request_shape,
                json.dumps(redact_sensitive(outbound)),
                started_at, started_at,
            ),
        )
        changed = db.execute(
            "UPDATE execution_claims SET lifecycle_state='IN_FLIGHT', "
            "updated_at=? WHERE execution_id=? "
            "AND lifecycle_state='CLAIMED'",
            (now(), execution_id),
        )
        if changed.rowcount != 1:
            raise HTTPException(409, {"code": "execution_not_owned"})


def finish_journal_attempt(
    attempt_id: str,
    status: str,
    completed_at: str,
    provider_status: Optional[int],
    operation_id: Optional[str],
    error: Optional[dict[str, Any]],
) -> None:
    with connect() as db:
        db.execute(
            """
            UPDATE canonical_invocation_attempts
            SET status=?, provider_status=?, provider_operation_id=?,
                error_evidence_json=?, completed_at=?
            WHERE invocation_attempt_id=? AND status='IN_FLIGHT'
            """,
            (
                status, provider_status, operation_id,
                json.dumps(error) if error is not None else None,
                completed_at, attempt_id,
            ),
        )


def recover_orphaned_in_flight(
    db: sqlite3.Connection, claim: sqlite3.Row
) -> dict[str, Any]:
    resolution = json.loads(claim["resolution_json"])
    request = json.loads(claim["request_json"])
    attempt_row = db.execute(
        "SELECT * FROM canonical_invocation_attempts "
        "WHERE execution_id=? ORDER BY attempt_number DESC LIMIT 1",
        (claim["execution_id"],),
    ).fetchone()
    if attempt_row is None or resolution is None:
        raise HTTPException(409, {"code": "execution_already_active"})
    completed_at = now()
    error = {
        "code": "orphaned_in_flight_attempt",
        "message": "A prior transmission may have occurred before recovery.",
        "retryable_same_target": False,
        "remote_side_effect_possible": True,
    }
    attempt = {
        "invocation_attempt_id": attempt_row["invocation_attempt_id"],
        "attempt_number": attempt_row["attempt_number"],
        "status": "AMBIGUOUS_OUTCOME",
        "started_at": attempt_row["started_at"],
        "completed_at": completed_at,
    }
    result = invoked_result(
        request,
        resolution,
        started_at=claim["started_at"],
        status="AMBIGUOUS_OUTCOME",
        normalized=None,
        error=error,
        attempts=[attempt],
    )
    db.execute(
        "UPDATE canonical_invocation_attempts SET status=?, "
        "error_evidence_json=?, completed_at=? "
        "WHERE invocation_attempt_id=?",
        (
            "AMBIGUOUS_OUTCOME", json.dumps(error), completed_at,
            attempt_row["invocation_attempt_id"],
        ),
    )
    persist_execution_in_db(
        db, request, resolution, result,
        outbound=json.loads(attempt_row["outbound_evidence_json"]),
    )
    return result


def persist_execution(
    execution_request: dict[str, Any],
    resolution: dict[str, Any],
    result: dict[str, Any],
    *,
    outbound: Optional[dict[str, Any]] = None,
    attempt_audits: Optional[list[dict[str, Any]]] = None,
    raw_provider: Any = None,
) -> None:
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        result,
        source="execution-dispatcher",
        status_code=500,
    )
    attempt_audits = attempt_audits or []
    with connect() as db:
        persist_execution_in_db(
            db,
            execution_request,
            resolution,
            result,
            outbound=outbound,
            attempt_audits=attempt_audits,
            raw_provider=raw_provider,
        )


def persist_execution_in_db(
    db: sqlite3.Connection,
    execution_request: dict[str, Any],
    resolution: dict[str, Any],
    result: dict[str, Any],
    *,
    outbound: Optional[dict[str, Any]] = None,
    attempt_audits: Optional[list[dict[str, Any]]] = None,
    raw_provider: Any = None,
) -> None:
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        result,
        source="execution-dispatcher",
        status_code=500,
    )
    attempt_audits = attempt_audits or []
    timestamp = now()
    try:
        db.execute(
                """
                INSERT INTO canonical_executions (
                    execution_id, contract_version, capability_id, status,
                    resolution_id, request_json, resolution_json,
                    authorized_target_json, outbound_evidence_json,
                    attempts_json, result_json, raw_provider_evidence_json,
                    correlation_json, started_at, completed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["execution_id"],
                    result["contract_version"],
                    result["capability_id"],
                    result["status"],
                    resolution["resolution_id"],
                    json.dumps(redact_sensitive(execution_request)),
                    json.dumps(redact_sensitive(resolution)),
                    json.dumps(result.get("authorized_target"))
                    if result.get("authorized_target")
                    else None,
                    json.dumps(redact_sensitive(outbound))
                    if outbound is not None
                    else None,
                    json.dumps(result["attempt_summary"]["attempts"]),
                    json.dumps(redact_sensitive(result)),
                    json.dumps(redact_sensitive(raw_provider))
                    if raw_provider is not None
                    else None,
                    json.dumps(result["correlation"]),
                    result["started_at"],
                    result["completed_at"],
                    timestamp,
                    timestamp,
                ),
        )
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            409,
            {"code": "execution_id_already_exists"},
        ) from error
    for attempt in attempt_audits:
        db.execute(
                """
                UPDATE canonical_invocation_attempts
                SET status=?, provider_status=?, provider_operation_id=?,
                    completed_at=?
                WHERE invocation_attempt_id=? AND execution_id=?
                """,
                (
                    attempt["status"],
                    attempt["provider_status"],
                    attempt.get("provider_operation_id"),
                    attempt["completed_at"],
                    attempt["invocation_attempt_id"],
                    result["execution_id"],
                ),
            )
    db.execute(
        "UPDATE execution_claims SET lifecycle_state='COMPLETED', "
        "updated_at=? WHERE execution_id=?",
        (timestamp, result["execution_id"]),
    )


def decode_execution(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in (
        "request_json",
        "resolution_json",
        "authorized_target_json",
        "outbound_evidence_json",
        "attempts_json",
        "result_json",
        "raw_provider_evidence_json",
        "correlation_json",
    ):
        value = item.pop(key)
        item[key.removesuffix("_json")] = json.loads(value) if value else None
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        item["result"],
        source="execution-dispatcher-persistence",
        status_code=500,
    )
    return item


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        execution_count = db.execute(
            "SELECT COUNT(*) AS count FROM canonical_executions"
        ).fetchone()["count"]
        adapter_count = db.execute(
            "SELECT COUNT(*) AS count FROM provider_adapters WHERE enabled=1"
        ).fetchone()["count"]
        legacy_present = "executions" in table_names(db)
    return {
        "ok": True,
        "service": "execution-dispatcher-service",
        "platform": "LEOS",
        "version": SERVICE_VERSION,
        "request_contract": EXECUTION_CONTRACT,
        "result_contract": EXECUTION_RESULT_CONTRACT,
        "capability_manager_url": CAPABILITY_MANAGER_URL,
        "execution_count": execution_count,
        "enabled_adapter_count": adapter_count,
        "legacy_execution_table_retained": legacy_present,
        "database": str(DB_PATH),
    }


@app.get("/contract")
def contract() -> dict[str, Any]:
    return {
        "ok": True,
        "request_contract": EXECUTION_CONTRACT,
        "resolution_request_contract": RESOLUTION_REQUEST_CONTRACT,
        "resolution_result_contract": RESOLUTION_RESULT_CONTRACT,
        "result_contract": EXECUTION_RESULT_CONTRACT,
        "request_shapes": ["flat_input", "canonical_envelope"],
        "default_request_shape": DEFAULT_SHAPE,
        "resolution_outcomes": [
            "RESOLVED",
            "APPROVAL_PENDING",
            "NO_ELIGIBLE_PROVIDER",
            "GOVERNED_ORDER_REQUIRED",
        ],
    }


@app.get("/adapters")
def adapters() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM provider_adapters ORDER BY priority, adapter_id"
        ).fetchall()
    return {
        "ok": True,
        "adapter_count": len(rows),
        "adapters": [
            {
                **dict(row),
                "enabled": bool(row["enabled"]),
                "metadata": parse_metadata(row["metadata_json"]),
            }
            for row in rows
        ],
    }


def provision_adapter(request: AdapterCreate) -> dict[str, Any]:
    """Deployment/test provisioning; intentionally not a public API route."""
    timestamp = now()
    with connect() as db:
        db.execute(
            """
            INSERT INTO provider_adapters (
                adapter_id, capability_id, provider_id, request_shape,
                enabled, priority, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(adapter_id) DO UPDATE SET
                capability_id=excluded.capability_id,
                provider_id=excluded.provider_id,
                request_shape=excluded.request_shape,
                enabled=excluded.enabled,
                priority=excluded.priority,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                request.adapter_id,
                request.capability_id,
                request.provider_id,
                request.request_shape,
                int(request.enabled),
                request.priority,
                json.dumps(request.metadata),
                timestamp,
                timestamp,
            ),
        )
    return {
        "ok": True,
        "adapter_id": request.adapter_id,
        "request_shape": request.request_shape,
    }


@app.get("/executions")
def executions(
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    where = "WHERE status=?" if status else ""
    params: list[Any] = [status, limit] if status else [limit]
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT * FROM canonical_executions
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return {
        "ok": True,
        "execution_count": len(rows),
        "executions": [decode_execution(row) for row in rows],
    }


@app.get("/executions/{execution_id}")
def execution(execution_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT * FROM canonical_executions
            WHERE execution_id=?
            """,
            (execution_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Execution not found")
    return {"ok": True, "execution": decode_execution(row)}


@app.post("/execute")
async def execute(request: dict[str, Any]) -> dict[str, Any]:
    validate_or_raise(
        EXECUTION_CONTRACT,
        request,
        source="caller",
        status_code=422,
    )
    existing = claim_execution(request)
    if existing is not None:
        return existing
    started_at = now()
    try:
        resolution_request = build_resolution_request(request)
        resolution = await resolve_capability(resolution_request)
        verify_resolution_binding(request, resolution)
        store_claim_resolution(request["execution_id"], resolution)

        if resolution["status"] != "RESOLVED":
            result = non_invoked_result(
                request,
                resolution,
                started_at=started_at,
            )
            persist_execution(request, resolution, result)
            return result

        selected_target = resolution["selected_target"]
        if "credential_ref" in selected_target:
            result = rejection_result(
                request,
                resolution,
                started_at=started_at,
                code="credential_boundary_unavailable",
                message=(
                    "The resolved target requires a governed credential "
                    "boundary that is not available in this phase."
                ),
            )
            persist_execution(request, resolution, result)
            return result

        provider = await provider_inventory_record(
            request["capability_id"],
            selected_target,
        )
        shape, adapter = adapter_selection(
            request["capability_id"],
            selected_target,
        )
        provider_url = target_url(provider)
        payload = shape_payload(shape, request)
    except HTTPException:
        release_pretransmission_claim(request["execution_id"])
        raise
    (
        status,
        normalized,
        error,
        attempts,
        attempt_audits,
    ) = await invoke_authorized_target(
        request,
        selected_target,
        provider,
        shape,
        adapter,
    )
    result = invoked_result(
        request,
        resolution,
        started_at=started_at,
        status=status,
        normalized=normalized,
        error=error,
        attempts=attempts,
    )
    persist_execution(
        request,
        resolution,
        result,
        outbound=outbound_evidence(
            provider_url,
            shape,
            payload,
            adapter,
            idempotency_key_transmitted=retry_is_authorized(
                request,
                adapter,
            ),
        ),
        attempt_audits=attempt_audits,
        raw_provider=normalized,
    )
    validate_or_raise(
        EXECUTION_RESULT_CONTRACT,
        result,
        source="execution-dispatcher",
        status_code=500,
    )
    return result
