from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query
from leos_contracts import (
    ContractRootError,
    ContractValidationError,
    validate_contract,
)
from pydantic import BaseModel, Field

SERVICE_VERSION = "0.2.0-dev-preview-v2"
DATA_DIR = Path(os.getenv("CAPABILITY_MANAGER_DATA_DIR", "/data/capability-manager"))
DB_PATH = DATA_DIR / "capability-manager.db"
REQUEST_CONTRACT = "leos.capability-resolution-request.v1"
RESULT_CONTRACT = "leos.capability-resolution-result.v1"
CORRELATION_CONTRACT = "leos.execution-correlation.v1"
PROVIDER_ORDER_CONSTRAINT = "provider_preference_order"
RAW_CREDENTIAL_KEYS = {
    "access_token",
    "api_key",
    "api_token",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "secret",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def migrate() -> None:
    """Apply the non-destructive v2 schema transition."""
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS providers (
                provider_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                source_id TEXT,
                adapter_name TEXT,
                base_url TEXT,
                execute_path TEXT NOT NULL DEFAULT '/execute',
                health_url TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                health_state TEXT NOT NULL DEFAULT 'unknown',
                priority INTEGER NOT NULL DEFAULT 100,
                trust_level TEXT NOT NULL DEFAULT 'community',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS capabilities (
                capability_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                risk_level TEXT NOT NULL DEFAULT 'low',
                approval_required INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS provider_capabilities (
                provider_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                provider_priority INTEGER,
                approval_policy TEXT NOT NULL DEFAULT 'allowed',
                permissions_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (provider_id, capability_id),
                FOREIGN KEY (provider_id)
                    REFERENCES providers(provider_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (capability_id)
                    REFERENCES capabilities(capability_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                provider_id TEXT,
                capability_id TEXT,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS canonical_resolutions (
                resolution_id TEXT PRIMARY KEY,
                contract_version TEXT NOT NULL,
                status TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                requester_type TEXT NOT NULL,
                requester_id TEXT NOT NULL,
                correlation_json TEXT NOT NULL,
                candidate_evaluations_json TEXT NOT NULL,
                selected_provider_id TEXT,
                rationale_json TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                resolved_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS capability_manager_schema (
                component TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                migrated_at TEXT NOT NULL
            );
            """
        )
        db.execute(
            """
            INSERT INTO capability_manager_schema (
                component, schema_version, migrated_at
            ) VALUES ('capability-manager', 2, ?)
            ON CONFLICT(component) DO UPDATE SET
                schema_version=excluded.schema_version,
                migrated_at=excluded.migrated_at
            """,
            (now(),),
        )


def decode(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    for key in tuple(value):
        if key.endswith("_json"):
            target = key[:-5]
            try:
                value[target] = json.loads(value.pop(key))
            except Exception:
                value[target] = value.pop(key)
    for key in ("enabled", "approval_required"):
        if key in value:
            value[key] = bool(value[key])
    return value


def emit(
    event_type: str,
    provider_id: Optional[str] = None,
    capability_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                event_type,
                provider_id,
                capability_id,
                json.dumps(details or {}),
                now(),
            ),
        )


def contains_raw_credentials(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in RAW_CREDENTIAL_KEYS
            or contains_raw_credentials(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_raw_credentials(child) for child in value)
    return False


def reject_raw_credentials(value: Any, location: str) -> None:
    if contains_raw_credentials(value):
        raise HTTPException(
            422,
            {
                "code": "raw_credentials_forbidden",
                "location": location,
            },
        )


class Provider(BaseModel):
    provider_id: str
    name: str
    provider_type: str = Field(
        pattern="^(plugin|employee|service|adapter|builtin)$"
    )
    source_id: Optional[str] = None
    adapter_name: Optional[str] = None
    base_url: Optional[str] = None
    execute_path: str = "/execute"
    health_url: Optional[str] = None
    status: str = "active"
    priority: int = 100
    trust_level: str = "community"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Capability(BaseModel):
    capability_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    risk_level: str = "low"
    approval_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Binding(BaseModel):
    provider_id: str
    capability_id: str
    enabled: bool = True
    provider_priority: Optional[int] = None
    approval_policy: str = "allowed"
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Bundle(BaseModel):
    provider: Provider
    capabilities: list[Capability]
    bindings: list[Binding] = Field(default_factory=list)


migrate()
app = FastAPI(title="LEOS Capability Manager", version=SERVICE_VERSION)


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        providers = db.execute("SELECT COUNT(*) c FROM providers").fetchone()["c"]
        capabilities = db.execute(
            "SELECT COUNT(*) c FROM capabilities"
        ).fetchone()["c"]
        resolutions = db.execute(
            "SELECT COUNT(*) c FROM canonical_resolutions"
        ).fetchone()["c"]
    return {
        "ok": True,
        "service": "capability-manager-service",
        "platform": "LEOS",
        "version": SERVICE_VERSION,
        "release_channel": "developer-preview",
        "provider_count": providers,
        "capability_count": capabilities,
        "canonical_resolution_count": resolutions,
        "database": str(DB_PATH),
    }


@app.post("/providers")
def register_provider(request: Provider) -> dict[str, Any]:
    reject_raw_credentials(request.metadata, "provider.metadata")
    parsed_base_url = urlsplit(request.base_url) if request.base_url else None
    if parsed_base_url and (
        parsed_base_url.username is not None
        or parsed_base_url.password is not None
    ):
        raise HTTPException(
            422,
            {
                "code": "raw_credentials_forbidden",
                "location": "provider.base_url",
            },
        )
    timestamp = now()
    with connect() as db:
        db.execute(
            """
            INSERT INTO providers (
                provider_id, name, provider_type, source_id, adapter_name,
                base_url, execute_path, health_url, status, health_state,
                priority, trust_level, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                name=excluded.name,
                provider_type=excluded.provider_type,
                source_id=excluded.source_id,
                adapter_name=excluded.adapter_name,
                base_url=excluded.base_url,
                execute_path=excluded.execute_path,
                health_url=excluded.health_url,
                status=excluded.status,
                priority=excluded.priority,
                trust_level=excluded.trust_level,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                request.provider_id,
                request.name,
                request.provider_type,
                request.source_id,
                request.adapter_name,
                request.base_url,
                request.execute_path,
                request.health_url,
                request.status,
                request.priority,
                request.trust_level,
                json.dumps(request.metadata),
                timestamp,
                timestamp,
            ),
        )
    emit("provider_registered", request.provider_id)
    return {"ok": True, "provider_id": request.provider_id}


@app.post("/capabilities")
def register_capability(request: Capability) -> dict[str, Any]:
    reject_raw_credentials(request.metadata, "capability.metadata")
    timestamp = now()
    with connect() as db:
        db.execute(
            """
            INSERT INTO capabilities (
                capability_id, name, description, category, risk_level,
                approval_required, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(capability_id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                category=excluded.category,
                risk_level=excluded.risk_level,
                approval_required=excluded.approval_required,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                request.capability_id,
                request.name or request.capability_id,
                request.description,
                request.category,
                request.risk_level,
                int(request.approval_required),
                json.dumps(request.metadata),
                timestamp,
                timestamp,
            ),
        )
    emit("capability_registered", capability_id=request.capability_id)
    return {"ok": True, "capability_id": request.capability_id}


@app.post("/bindings")
def register_binding(request: Binding) -> dict[str, Any]:
    reject_raw_credentials(request.metadata, "binding.metadata")
    timestamp = now()
    with connect() as db:
        if db.execute(
            "SELECT 1 FROM providers WHERE provider_id=?",
            (request.provider_id,),
        ).fetchone() is None:
            raise HTTPException(404, "Provider not found.")
        if db.execute(
            "SELECT 1 FROM capabilities WHERE capability_id=?",
            (request.capability_id,),
        ).fetchone() is None:
            raise HTTPException(404, "Capability not found.")
        db.execute(
            """
            INSERT INTO provider_capabilities (
                provider_id, capability_id, enabled, provider_priority,
                approval_policy, permissions_json, metadata_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id, capability_id) DO UPDATE SET
                enabled=excluded.enabled,
                provider_priority=excluded.provider_priority,
                approval_policy=excluded.approval_policy,
                permissions_json=excluded.permissions_json,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                request.provider_id,
                request.capability_id,
                int(request.enabled),
                request.provider_priority,
                request.approval_policy,
                json.dumps(request.permissions),
                json.dumps(request.metadata),
                timestamp,
                timestamp,
            ),
        )
    emit(
        "provider_capability_bound",
        request.provider_id,
        request.capability_id,
    )
    return {
        "ok": True,
        "provider_id": request.provider_id,
        "capability_id": request.capability_id,
    }


@app.post("/providers/register-bundle")
def register_bundle(request: Bundle) -> dict[str, Any]:
    register_provider(request.provider)
    for capability in request.capabilities:
        register_capability(capability)
    bindings = request.bindings or [
        Binding(
            provider_id=request.provider.provider_id,
            capability_id=capability.capability_id,
        )
        for capability in request.capabilities
    ]
    for binding in bindings:
        register_binding(binding)
    return {
        "ok": True,
        "provider_id": request.provider.provider_id,
        "capabilities": [
            capability.capability_id for capability in request.capabilities
        ],
        "binding_count": len(bindings),
    }


@app.get("/providers")
def providers(
    capability_id: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    params: list[Any] = []
    join = ""
    where = ""
    if capability_id:
        join = (
            "JOIN provider_capabilities pc "
            "ON pc.provider_id=providers.provider_id"
        )
        where = "WHERE pc.capability_id=?"
        params.append(capability_id)
    params.append(limit)
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT DISTINCT providers.*
            FROM providers
            {join}
            {where}
            ORDER BY provider_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return {
        "ok": True,
        "provider_count": len(rows),
        "providers": [decode(row) for row in rows],
    }


@app.get("/capabilities")
def capabilities(
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT capabilities.*,
                   (
                     SELECT COUNT(*)
                     FROM provider_capabilities pc
                     WHERE pc.capability_id=capabilities.capability_id
                       AND pc.enabled=1
                   ) AS provider_count
            FROM capabilities
            ORDER BY capability_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {
        "ok": True,
        "capability_count": len(rows),
        "capabilities": [decode(row) for row in rows],
    }


def validation_error(error: ContractValidationError) -> HTTPException:
    return HTTPException(
        422,
        {
            "code": "invalid_contract",
            "contract_id": error.contract_id,
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


def validate_resolution_request(request: dict[str, Any]) -> None:
    try:
        validate_contract(REQUEST_CONTRACT, request)
    except ContractValidationError as error:
        raise validation_error(error) from error
    except ContractRootError as error:
        raise HTTPException(
            500,
            {"code": "contract_authority_unavailable"},
        ) from error
    reject_raw_credentials(request.get("constraints", {}), "constraints")


def candidate_rows(capability_id: str) -> dict[str, sqlite3.Row]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT p.*, pc.enabled, pc.provider_priority,
                   pc.approval_policy, pc.permissions_json,
                   pc.metadata_json AS binding_metadata_json,
                   c.risk_level, c.approval_required
            FROM provider_capabilities pc
            JOIN providers p ON p.provider_id=pc.provider_id
            JOIN capabilities c ON c.capability_id=pc.capability_id
            WHERE pc.capability_id=?
            """,
            (capability_id,),
        ).fetchall()
    return {row["provider_id"]: row for row in rows}


def ordered_provider_ids(
    request: dict[str, Any],
    rows: dict[str, sqlite3.Row],
) -> tuple[list[str], bool]:
    supplied = request["constraints"].get(PROVIDER_ORDER_CONSTRAINT)
    if supplied is None:
        return sorted(rows), False
    if (
        not isinstance(supplied, list)
        or any(not isinstance(item, str) or not item for item in supplied)
        or len(set(supplied)) != len(supplied)
    ):
        raise HTTPException(
            422,
            {
                "code": "invalid_provider_preference_order",
                "location": (
                    f"constraints.{PROVIDER_ORDER_CONSTRAINT}"
                ),
            },
        )
    return list(supplied), True


def candidate_disposition(
    row: Optional[sqlite3.Row],
) -> tuple[str, list[str]]:
    if row is None:
        return "REJECTED", ["provider_not_bound"]
    if not bool(row["enabled"]):
        return "REJECTED", ["binding_disabled"]
    if row["status"] != "active":
        return "REJECTED", ["provider_disabled"]
    if row["health_state"] == "unhealthy":
        return "REJECTED", ["provider_unhealthy"]
    if row["approval_policy"] == "denied":
        return "REJECTED", ["binding_policy_denied"]
    approval_required = (
        bool(row["approval_required"])
        or row["approval_policy"] == "approval_required"
    )
    if approval_required:
        return "APPROVAL_REQUIRED", ["approval_grant_required"]
    return "ELIGIBLE", []


def provider_target(row: sqlite3.Row) -> dict[str, Any]:
    target: dict[str, Any] = {
        "provider_id": row["provider_id"],
        "provider_type": row["provider_type"],
        "target_ref": {
            "authority": "capability-manager",
            "reference_id": row["provider_id"],
            "revision": row["updated_at"],
        },
    }
    if row["adapter_name"]:
        target["adapter_id"] = row["adapter_name"]
    return target


def persist_resolution(
    request: dict[str, Any],
    result: dict[str, Any],
) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT INTO canonical_resolutions (
                resolution_id, contract_version, status, capability_id,
                requester_type, requester_id, correlation_json,
                candidate_evaluations_json, selected_provider_id,
                rationale_json, request_json, result_json, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["resolution_id"],
                result["contract_version"],
                result["status"],
                result["capability_id"],
                result["requester"]["type"],
                result["requester"]["id"],
                json.dumps(result["correlation"]),
                json.dumps(result["candidate_evaluations"]),
                (
                    result.get("selected_target", {}).get("provider_id")
                    or None
                ),
                json.dumps(result["rationale"]),
                json.dumps(request),
                json.dumps(result),
                result["resolved_at"],
            ),
        )


@app.post("/resolve")
def resolve(request: dict[str, Any]) -> dict[str, Any]:
    validate_resolution_request(request)
    resolution_id = str(uuid.uuid4())
    correlation = dict(request["correlation"])
    correlation["resolution_id"] = resolution_id
    rows = candidate_rows(request["capability_id"])
    ordered_ids, governed_order_supplied = ordered_provider_ids(request, rows)
    evaluations: list[dict[str, Any]] = []
    selected: Optional[sqlite3.Row] = None
    approval_provider_id: Optional[str] = None
    governed_order_required = False

    for position, provider_id in enumerate(ordered_ids, start=1):
        row = rows.get(provider_id)
        outcome, reasons = candidate_disposition(row)
        evaluations.append(
            {
                "position": position,
                "provider_id": provider_id,
                "outcome": outcome,
                "reasons": reasons,
            }
        )
        if governed_order_supplied:
            if outcome == "APPROVAL_REQUIRED":
                approval_provider_id = provider_id
                break
            if outcome == "ELIGIBLE":
                selected = row
                break

    if not governed_order_supplied:
        eligible = [
            evaluation
            for evaluation in evaluations
            if evaluation["outcome"] == "ELIGIBLE"
        ]
        approval_required = [
            evaluation
            for evaluation in evaluations
            if evaluation["outcome"] == "APPROVAL_REQUIRED"
        ]
        if len(eligible) == 1:
            selected = rows[eligible[0]["provider_id"]]
        elif len(eligible) > 1:
            governed_order_required = True
        elif len(approval_required) == 1:
            approval_provider_id = approval_required[0]["provider_id"]
        elif len(approval_required) > 1:
            for evaluation in approval_required:
                evaluation["outcome"] = "REJECTED"
                evaluation["reasons"] = ["governed_order_required"]

    timestamp = now()
    result: dict[str, Any] = {
        "contract_version": RESULT_CONTRACT,
        "resolution_id": resolution_id,
        "status": "NO_ELIGIBLE_PROVIDER",
        "capability_id": request["capability_id"],
        "requester": dict(request["requester"]),
        "candidate_evaluations": evaluations,
        "rationale": {
            "selection_rule": "first-ranked-valid",
            "provider_order_source": (
                f"constraints.{PROVIDER_ORDER_CONSTRAINT}"
                if governed_order_supplied
                else "none"
            ),
            "outcome": "no_eligible_provider",
        },
        "correlation": correlation,
        "resolved_at": timestamp,
    }

    if governed_order_required:
        result["status"] = "GOVERNED_ORDER_REQUIRED"
        result["rationale"]["outcome"] = "governed_order_required"
        result["rationale"]["eligible_candidate_count"] = sum(
            1
            for item in evaluations
            if item["outcome"] == "ELIGIBLE"
        )
    elif approval_provider_id is not None:
        result["status"] = "APPROVAL_PENDING"
        result["approval_requirement_ref"] = {
            "authority": "capability-manager",
            "reference_id": (
                f"{resolution_id}:{approval_provider_id}:approval"
            ),
        }
        result["rationale"]["outcome"] = "approval_pending"
        result["rationale"]["blocked_position"] = len(evaluations)
    elif selected is not None:
        result["status"] = "RESOLVED"
        result["selected_target"] = provider_target(selected)
        result["rationale"]["outcome"] = "selected"
        result["rationale"]["selected_position"] = next(
            item["position"]
            for item in evaluations
            if item["provider_id"] == selected["provider_id"]
        )
    elif (
        not governed_order_supplied
        and any(
            "governed_order_required" in item["reasons"]
            for item in evaluations
        )
    ):
        result["rationale"]["outcome"] = (
            "governed_order_required_for_multiple_candidates"
        )

    try:
        validate_contract(RESULT_CONTRACT, result)
    except ContractValidationError as error:
        raise HTTPException(
            500,
            {
                "code": "invalid_canonical_resolution",
                "issues": [
                    {
                        "kind": issue.kind,
                        "path": issue.path,
                        "message": issue.message,
                    }
                    for issue in error.issues
                ],
            },
        ) from error
    persist_resolution(request, result)
    emit(
        "capability_resolved",
        result.get("selected_target", {}).get("provider_id"),
        request["capability_id"],
        {
            "resolution_id": resolution_id,
            "status": result["status"],
        },
    )
    return result


@app.get("/resolutions/{resolution_id}")
def resolution(resolution_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            "SELECT result_json FROM canonical_resolutions "
            "WHERE resolution_id=?",
            (resolution_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Resolution not found.")
    result = json.loads(row["result_json"])
    try:
        validate_contract(RESULT_CONTRACT, result)
    except ContractValidationError as error:
        raise HTTPException(
            500,
            {"code": "persisted_resolution_invalid"},
        ) from error
    return result


@app.get("/resolutions")
def resolutions(
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            "SELECT result_json FROM canonical_resolutions "
            "ORDER BY resolved_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {
        "ok": True,
        "resolution_count": len(rows),
        "resolutions": [json.loads(row["result_json"]) for row in rows],
    }
