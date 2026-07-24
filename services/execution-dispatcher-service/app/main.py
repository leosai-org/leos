from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from leos_contracts import validate_contract as validate_governed_contract
from pydantic import BaseModel, Field

SERVICE_VERSION = "0.1.0"
CONTRACT_VERSION = "leos.execution.v1"
DATA_DIR = Path(os.getenv("EXECUTION_DISPATCHER_DATA_DIR", "/data/execution-dispatcher"))
DB_PATH = DATA_DIR / "execution-dispatcher.db"
CAPABILITY_MANAGER_URL = os.getenv("CAPABILITY_MANAGER_URL", "http://capability-manager-service:8000").rstrip("/")
TIMEOUT = float(os.getenv("EXECUTION_DISPATCHER_TIMEOUT_SECONDS", "120"))
MAX_RETRIES = int(os.getenv("EXECUTION_DISPATCHER_MAX_PROVIDER_RETRIES", "1"))
DEFAULT_SHAPE = os.getenv("EXECUTION_DISPATCHER_DEFAULT_REQUEST_SHAPE", "legacy_wrapped")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def migrate() -> None:
    with connect() as db:
        db.executescript("""
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
        CREATE TABLE IF NOT EXISTS executions (
            execution_id TEXT PRIMARY KEY,
            contract_version TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            requester_type TEXT,
            requester_id TEXT,
            provider_id TEXT,
            request_shape TEXT,
            provider_url TEXT,
            state TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            envelope_json TEXT NOT NULL,
            provider_payload_json TEXT,
            provider_response_json TEXT,
            provider_status INTEGER,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        );
        """)
        ts = now()
        db.execute("""
        INSERT INTO provider_adapters (
            adapter_id, capability_id, provider_id, request_shape,
            enabled, priority, metadata_json, created_at, updated_at
        ) VALUES (?, ?, NULL, ?, 1, 10, ?, ?, ?)
        ON CONFLICT(adapter_id) DO UPDATE SET
            capability_id=excluded.capability_id,
            request_shape=excluded.request_shape,
            enabled=1,
            priority=10,
            metadata_json=excluded.metadata_json,
            updated_at=excluded.updated_at
        """, (
            "builtin-content-write-flat-input",
            "content.write",
            "flat_input",
            json.dumps({"official": True, "maintainer": "Bad Tech Labs LLC"}),
            ts,
            ts,
        ))


class ExecuteRequest(BaseModel):
    capability_id: Optional[str] = None
    capability: Optional[str] = None
    requester_type: str = "system"
    requester_id: str = "leos"
    input: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    provider_id: Optional[str] = None
    execution_id: Optional[str] = None
    contract_version: str = CONTRACT_VERSION


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


def envelope(req: ExecuteRequest) -> dict[str, Any]:
    capability_id = req.capability_id or req.capability
    if not capability_id:
        raise HTTPException(422, "capability_id or capability is required")
    return {
        "contract_version": req.contract_version or CONTRACT_VERSION,
        "execution_id": req.execution_id or str(uuid.uuid4()),
        "capability_id": capability_id,
        "input": dict(req.input),
        "requester": {"type": req.requester_type, "id": req.requester_id},
        "context": dict(req.context),
        "policy": dict(req.policy),
        "trace": dict(req.trace),
    }


async def resolve_provider(env: dict[str, Any], provider_id: Optional[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "capability_id": env["capability_id"],
        "requester_type": env["requester"]["type"],
        "requester_id": env["requester"]["id"],
    }
    if provider_id:
        payload["provider_id"] = provider_id
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(f"{CAPABILITY_MANAGER_URL}/resolve", json=payload)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    if response.status_code >= 400:
        raise HTTPException(502, {"message": "Capability resolution failed", "status": response.status_code, "response": body})
    provider = body.get("provider") or body.get("resolution", {}).get("provider")
    if not isinstance(provider, dict):
        raise HTTPException(502, {"message": "Capability Manager returned no provider", "response": body})
    return body, provider


def parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return {}


def request_shape(capability_id: str, provider: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    provider_id = provider.get("provider_id")
    metadata = parse_metadata(provider.get("metadata"))
    explicit = metadata.get("request_shape") or metadata.get("payload_shape") or metadata.get("execution_request_shape")
    if explicit:
        return str(explicit), {"source": "provider_metadata", "provider_id": provider_id}
    with connect() as db:
        row = db.execute("""
        SELECT * FROM provider_adapters
        WHERE enabled=1
          AND (capability_id IS NULL OR capability_id=?)
          AND (provider_id IS NULL OR provider_id=?)
        ORDER BY CASE WHEN provider_id IS NOT NULL THEN 0 ELSE 1 END,
                 priority ASC, created_at ASC
        LIMIT 1
        """, (capability_id, provider_id)).fetchone()
    if row:
        return row["request_shape"], {"source": "adapter_registry", "adapter_id": row["adapter_id"], "provider_id": provider_id}
    return DEFAULT_SHAPE, {"source": "default", "provider_id": provider_id}


def shape_payload(shape: str, env: dict[str, Any]) -> dict[str, Any]:
    if shape in {"flat_input", "raw_input"}:
        return dict(env["input"])
    if shape in {"canonical_envelope", "leos_execution_v1"}:
        return dict(env)
    if shape == "legacy_wrapped":
        return {"capability": env["capability_id"], "input": dict(env["input"]), "requester": dict(env["requester"])}
    raise HTTPException(500, {"message": "Unsupported request shape", "request_shape": shape})


def target_url(provider: dict[str, Any]) -> str:
    base_url = provider.get("base_url")
    execute_path = provider.get("execute_path") or "/execute"
    if not base_url:
        raise HTTPException(502, {"message": "Selected provider has no base_url", "provider": provider})
    return base_url.rstrip("/") + "/" + execute_path.lstrip("/")


def insert_execution(env: dict[str, Any], req: ExecuteRequest) -> None:
    ts = now()
    with connect() as db:
        db.execute("""
        INSERT INTO executions (
            execution_id, contract_version, capability_id, requester_type,
            requester_id, state, envelope_json, created_at, started_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'resolving', ?, ?, ?, ?)
        """, (
            env["execution_id"], env["contract_version"], env["capability_id"],
            req.requester_type, req.requester_id, json.dumps(env), ts, ts, ts,
        ))


def update_execution(execution_id: str, **values: Any) -> None:
    allowed = {
        "provider_id", "request_shape", "provider_url", "state", "attempt_count",
        "provider_payload_json", "provider_response_json", "provider_status",
        "error", "completed_at",
    }
    clean = {k: v for k, v in values.items() if k in allowed}
    if not clean:
        return
    clean["updated_at"] = now()
    assignments = ", ".join(f"{key}=?" for key in clean)
    with connect() as db:
        db.execute(f"UPDATE executions SET {assignments} WHERE execution_id=?", [*clean.values(), execution_id])


async def invoke(url: str, payload: dict[str, Any]) -> tuple[int, Any, int]:
    attempts = MAX_RETRIES + 1
    last_status = 0
    last_body: Any = None
    last_error: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.post(url, json=payload)
                last_status = response.status_code
                try:
                    last_body = response.json()
                except Exception:
                    last_body = {"raw": response.text}
                if response.status_code < 500:
                    return last_status, last_body, attempt
            except Exception as exc:
                last_error = exc
    if last_error and not last_status:
        raise last_error
    return last_status, last_body, attempts


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        execution_count = db.execute("SELECT COUNT(*) c FROM executions").fetchone()["c"]
        failed_count = db.execute("SELECT COUNT(*) c FROM executions WHERE state='failed'").fetchone()["c"]
        adapter_count = db.execute("SELECT COUNT(*) c FROM provider_adapters WHERE enabled=1").fetchone()["c"]
    return {
        "ok": True,
        "service": "execution-dispatcher-service",
        "platform": "LEOS",
        "version": SERVICE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "capability_manager_url": CAPABILITY_MANAGER_URL,
        "execution_count": execution_count,
        "failed_count": failed_count,
        "enabled_adapter_count": adapter_count,
        "default_request_shape": DEFAULT_SHAPE,
        "database": str(DB_PATH),
    }


@app.get("/contract")
def contract() -> dict[str, Any]:
    return {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "required_fields": ["contract_version", "execution_id", "capability_id", "input", "requester", "context", "policy", "trace"],
        "request_shapes": ["legacy_wrapped", "flat_input", "canonical_envelope"],
        "default_request_shape": DEFAULT_SHAPE,
    }


@app.get("/adapters")
def adapters() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute("SELECT * FROM provider_adapters ORDER BY priority, created_at").fetchall()
    return {
        "ok": True,
        "adapter_count": len(rows),
        "adapters": [{**dict(row), "enabled": bool(row["enabled"]), "metadata": parse_metadata(row["metadata_json"])} for row in rows],
    }


@app.post("/adapters")
def create_adapter(req: AdapterCreate) -> dict[str, Any]:
    ts = now()
    with connect() as db:
        db.execute("""
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
        """, (
            req.adapter_id, req.capability_id, req.provider_id, req.request_shape,
            int(req.enabled), req.priority, json.dumps(req.metadata), ts, ts,
        ))
    return {"ok": True, "adapter_id": req.adapter_id, "request_shape": req.request_shape}


@app.get("/executions")
def executions(state: Optional[str] = None, limit: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
    where = "WHERE state=?" if state else ""
    params: list[Any] = [state, limit] if state else [limit]
    with connect() as db:
        rows = db.execute(f"SELECT * FROM executions {where} ORDER BY created_at DESC LIMIT ?", params).fetchall()
    return {"ok": True, "execution_count": len(rows), "executions": [dict(row) for row in rows]}


@app.get("/executions/{execution_id}")
def execution(execution_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT * FROM executions WHERE execution_id=?", (execution_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Execution not found")
    item = dict(row)
    for source, target in (("envelope_json", "envelope"), ("provider_payload_json", "provider_payload"), ("provider_response_json", "provider_response")):
        value = item.pop(source)
        item[target] = json.loads(value) if value else None
    return {"ok": True, "execution": item}


@app.post("/execute")
async def execute(req: ExecuteRequest) -> dict[str, Any]:
    env = envelope(req)
    execution_id = env["execution_id"]
    insert_execution(env, req)
    try:
        resolution, provider = await resolve_provider(env, req.provider_id)
        shape, adapter_selection = request_shape(env["capability_id"], provider)
        payload = shape_payload(shape, env)
        url = target_url(provider)
        update_execution(
            execution_id,
            provider_id=provider.get("provider_id"),
            request_shape=shape,
            provider_url=url,
            state="running",
            provider_payload_json=json.dumps(payload),
        )
        status_code, body, attempts = await invoke(url, payload)
        if status_code >= 400:
            update_execution(
                execution_id,
                state="failed",
                attempt_count=attempts,
                provider_response_json=json.dumps(body),
                provider_status=status_code,
                error="Provider execution failed",
                completed_at=now(),
            )
            raise HTTPException(502, {
                "message": "Provider execution failed",
                "execution_id": execution_id,
                "provider_id": provider.get("provider_id"),
                "request_shape": shape,
                "provider_status": status_code,
                "provider_response": body,
            })
        update_execution(
            execution_id,
            state="complete",
            attempt_count=attempts,
            provider_response_json=json.dumps(body),
            provider_status=status_code,
            completed_at=now(),
        )
        return {
            "ok": True,
            "execution_id": execution_id,
            "contract_version": env["contract_version"],
            "capability_id": env["capability_id"],
            "resolution": resolution,
            "provider": {
                "provider_id": provider.get("provider_id"),
                "provider_type": provider.get("provider_type"),
                "request_shape": shape,
                "adapter_selection": adapter_selection,
                "url": url,
                "status_code": status_code,
                "attempt_count": attempts,
            },
            "provider_response": body,
        }
    except HTTPException:
        raise
    except Exception as exc:
        update_execution(execution_id, state="failed", error=str(exc), completed_at=now())
        raise HTTPException(502, {"message": "Execution dispatcher failed", "execution_id": execution_id, "error": str(exc)}) from exc
