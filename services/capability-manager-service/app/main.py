from __future__ import annotations
from app.execution_contract import adapt_provider_payload, router as execution_contract_router

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

DATA_DIR = Path(os.getenv("CAPABILITY_MANAGER_DATA_DIR", "/data/capability-manager"))
DB_PATH = DATA_DIR / "capability-manager.db"
ADAPTER_MANAGER_URL = os.getenv(
    "ADAPTER_MANAGER_URL",
    "http://adapter-manager:8000",
).rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("CAPABILITY_REQUEST_TIMEOUT_SECONDS", "60"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db() -> None:
    with connect() as db:
        db.executescript(
            '''
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

            CREATE TABLE IF NOT EXISTS resolutions (
                resolution_id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL,
                selected_provider_id TEXT,
                requester_type TEXT,
                requester_id TEXT,
                candidates_json TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                resolution_id TEXT,
                capability_id TEXT NOT NULL,
                provider_id TEXT,
                requester_type TEXT,
                requester_id TEXT,
                request_json TEXT NOT NULL,
                response_json TEXT,
                status TEXT NOT NULL,
                status_code INTEGER,
                error TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                provider_id TEXT,
                capability_id TEXT,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            '''
        )


def decode(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in list(item):
        if key.endswith("_json"):
            raw = item.pop(key)
            item[key[:-5]] = json.loads(raw) if raw else {}
    for key in ("enabled", "approval_required"):
        if key in item:
            item[key] = bool(item[key])
    return item


def emit(
    event_type: str,
    provider_id: Optional[str] = None,
    capability_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    with connect() as db:
        db.execute(
            '''
            INSERT INTO events
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                str(uuid.uuid4()),
                event_type,
                provider_id,
                capability_id,
                json.dumps(details or {}),
                now(),
            ),
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
    metadata: dict[str, Any] = {}


class Capability(BaseModel):
    capability_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    risk_level: str = "low"
    approval_required: bool = False
    metadata: dict[str, Any] = {}


class Binding(BaseModel):
    provider_id: str
    capability_id: str
    enabled: bool = True
    provider_priority: Optional[int] = None
    approval_policy: str = "allowed"
    permissions: list[str] = []
    metadata: dict[str, Any] = {}


class Bundle(BaseModel):
    provider: Provider
    capabilities: list[Capability]
    bindings: list[Binding] = []


class ResolveRequest(BaseModel):
    capability_id: str
    requester_type: str = "system"
    requester_id: Optional[str] = None
    preferred_provider_id: Optional[str] = None
    allow_unhealthy: bool = False
    allow_approval_required: bool = False


class ExecuteRequest(BaseModel):
    capability_id: str
    input: dict[str, Any] = {}
    requester_type: str = "system"
    requester_id: Optional[str] = None
    preferred_provider_id: Optional[str] = None
    allow_approval_required: bool = False


init_db()
app = FastAPI(title="LEOS Capability Manager", version="0.1.0")
app.include_router(execution_contract_router)


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        providers = db.execute("SELECT COUNT(*) c FROM providers").fetchone()["c"]
        capabilities = db.execute("SELECT COUNT(*) c FROM capabilities").fetchone()["c"]
        executions = db.execute("SELECT COUNT(*) c FROM executions").fetchone()["c"]
    return {
        "ok": True,
        "service": "capability-manager-service",
        "platform": "LEOS",
        "version": "0.1.0",
        "release_channel": "developer-preview",
        "provider_count": providers,
        "capability_count": capabilities,
        "execution_count": executions,
        "adapter_manager_url": ADAPTER_MANAGER_URL,
        "database": str(DB_PATH),
    }


@app.post("/providers")
def register_provider(request: Provider) -> dict[str, Any]:
    timestamp = now()
    with connect() as db:
        db.execute(
            '''
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
            ''',
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
    emit("provider_registered", request.provider_id, details=request.model_dump())
    return {"ok": True, "provider_id": request.provider_id}


@app.post("/capabilities")
def register_capability(request: Capability) -> dict[str, Any]:
    timestamp = now()
    with connect() as db:
        db.execute(
            '''
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
            ''',
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
    emit(
        "capability_registered",
        capability_id=request.capability_id,
        details=request.model_dump(),
    )
    return {"ok": True, "capability_id": request.capability_id}


@app.post("/bindings")
def register_binding(request: Binding) -> dict[str, Any]:
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
            '''
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
            ''',
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
        request.model_dump(),
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
            capability_id=item.capability_id,
        )
        for item in request.capabilities
    ]

    for binding in bindings:
        register_binding(binding)

    return {
        "ok": True,
        "provider_id": request.provider.provider_id,
        "capabilities": [item.capability_id for item in request.capabilities],
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
            f'''
            SELECT DISTINCT providers.*
            FROM providers
            {join}
            {where}
            ORDER BY priority, name
            LIMIT ?
            ''',
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
            '''
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
            ''',
            (limit,),
        ).fetchall()
    return {
        "ok": True,
        "capability_count": len(rows),
        "capabilities": [decode(row) for row in rows],
    }


def select_candidates(request: ResolveRequest) -> list[dict[str, Any]]:
    clauses = [
        "pc.capability_id=?",
        "pc.enabled=1",
        "p.status='active'",
        "pc.approval_policy!='denied'",
    ]
    params: list[Any] = [request.capability_id]

    if not request.allow_unhealthy:
        clauses.append("p.health_state IN ('healthy','unknown')")
    if not request.allow_approval_required:
        clauses.append("pc.approval_policy!='approval_required'")

    with connect() as db:
        rows = db.execute(
            f'''
            SELECT p.*, pc.provider_priority, pc.approval_policy,
                   pc.permissions_json AS binding_permissions_json,
                   c.risk_level, c.approval_required
            FROM provider_capabilities pc
            JOIN providers p ON p.provider_id=pc.provider_id
            JOIN capabilities c ON c.capability_id=pc.capability_id
            WHERE {" AND ".join(clauses)}
            ''',
            params,
        ).fetchall()

    trust = {"builtin": 0, "verified": 10, "community": 30, "untrusted": 100}
    health = {"healthy": 0, "unknown": 10, "degraded": 30, "unhealthy": 100}
    result = []

    for row in rows:
        item = decode(row)
        effective = (
            item["provider_priority"]
            if item.get("provider_priority") is not None
            else item["priority"]
        )
        score = effective + trust.get(item["trust_level"], 50) + health.get(
            item["health_state"],
            50,
        )
        if request.preferred_provider_id == item["provider_id"]:
            score -= 10000
        item["resolution_score"] = score
        result.append(item)

    result.sort(key=lambda item: (item["resolution_score"], item["provider_id"]))
    return result


@app.post("/resolve")
def resolve(request: ResolveRequest) -> dict[str, Any]:
    with connect() as db:
        capability = db.execute(
            "SELECT * FROM capabilities WHERE capability_id=?",
            (request.capability_id,),
        ).fetchone()
    if capability is None:
        raise HTTPException(404, "Capability not registered.")

    candidates = select_candidates(request)
    if not candidates:
        raise HTTPException(404, "No eligible provider.")

    selected = candidates[0]
    resolution_id = str(uuid.uuid4())

    with connect() as db:
        db.execute(
            '''
            INSERT INTO resolutions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                resolution_id,
                request.capability_id,
                selected["provider_id"],
                request.requester_type,
                request.requester_id,
                json.dumps(candidates),
                "lowest_weighted_score",
                now(),
            ),
        )

    emit(
        "capability_resolved",
        selected["provider_id"],
        request.capability_id,
        {
            "resolution_id": resolution_id,
            "candidate_count": len(candidates),
        },
    )

    return {
        "ok": True,
        "resolution_id": resolution_id,
        "capability": decode(capability),
        "provider": selected,
        "candidates": candidates,
        "reason": "lowest_weighted_score",
    }


@app.post("/execute")
async def execute(request: ExecuteRequest) -> dict[str, Any]:
    resolution = resolve(
        ResolveRequest(
            capability_id=request.capability_id,
            requester_type=request.requester_type,
            requester_id=request.requester_id,
            preferred_provider_id=request.preferred_provider_id,
            allow_approval_required=request.allow_approval_required,
        )
    )

    provider = resolution["provider"]
    target = None

    if provider.get("base_url"):
        target = provider["base_url"].rstrip("/") + provider.get(
            "execute_path",
            "/execute",
        )
    elif provider.get("adapter_name"):
        target = (
            f"{ADAPTER_MANAGER_URL}/adapters/"
            f"{provider['adapter_name']}/execute"
        )

    if not target:
        raise HTTPException(409, "Provider has no execution target.")

    execution_id = str(uuid.uuid4())
    started = now()

    with connect() as db:
        db.execute(
            '''
            INSERT INTO executions (
                execution_id, resolution_id, capability_id, provider_id,
                requester_type, requester_id, request_json, status, started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            ''',
            (
                execution_id,
                resolution["resolution_id"],
                request.capability_id,
                provider["provider_id"],
                request.requester_type,
                request.requester_id,
                json.dumps(request.model_dump()),
                started,
            ),
        )

    payload = {
        "capability": request.capability_id,
        "input": request.input,
        "requester": {
            "type": request.requester_type,
            "id": request.requester_id,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(target, json=adapt_provider_payload(locals(), payload))

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        status = "complete" if response.status_code < 400 else "failed"

        with connect() as db:
            db.execute(
                '''
                UPDATE executions
                SET response_json=?, status=?, status_code=?, completed_at=?
                WHERE execution_id=?
                ''',
                (
                    json.dumps(body),
                    status,
                    response.status_code,
                    now(),
                    execution_id,
                ),
            )

        if response.status_code >= 400:
            raise HTTPException(
                502,
                {
                    "message": "Provider execution failed.",
                    "provider_status": response.status_code,
                    "provider_response": body,
                },
            )

        return {
            "ok": True,
            "execution_id": execution_id,
            "resolution": resolution,
            "provider_response": body,
        }

    except HTTPException:
        raise
    except Exception as exc:
        with connect() as db:
            db.execute(
                '''
                UPDATE executions
                SET status='failed', error=?, completed_at=?
                WHERE execution_id=?
                ''',
                (str(exc), now(), execution_id),
            )
        raise HTTPException(
            502,
            {
                "message": "Provider execution failed.",
                "error": str(exc),
                "target": target,
            },
        ) from exc


@app.post("/sync/adapters")
async def sync_adapters() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{ADAPTER_MANAGER_URL}/adapters")
    if response.status_code >= 400:
        raise HTTPException(502, response.text[:2000])

    payload = response.json()
    adapters = payload.get("adapters", payload) if isinstance(payload, dict) else payload

    if isinstance(adapters, dict):
        items = [
            {**value, "name": value.get("name", key)}
            for key, value in adapters.items()
        ]
    elif isinstance(adapters, list):
        items = adapters
    else:
        raise HTTPException(502, "Unexpected Adapter Manager response.")

    registered = []

    for adapter in items:
        name = adapter.get("name")
        if not name:
            continue

        provider_id = f"adapter:{name}"
        register_provider(
            Provider(
                provider_id=provider_id,
                name=name,
                provider_type="adapter",
                source_id=name,
                adapter_name=name,
                base_url=adapter.get("entrypoint"),
                execute_path=adapter.get("execute_path", "/execute"),
                status=adapter.get("status", "active"),
                trust_level=(
                    "builtin"
                    if name in {
                        "music-adapter",
                        "gis-adapter",
                        "research-employee-adapter",
                        "writer-employee-adapter",
                    }
                    else "community"
                ),
                metadata={"adapter": adapter, "sync_source": "adapter-manager"},
            )
        )

        caps = []
        for capability_id in adapter.get("capabilities", []):
            register_capability(
                Capability(
                    capability_id=capability_id,
                    name=capability_id,
                    category=capability_id.split(".", 1)[0],
                    metadata={"sync_source": "adapter-manager"},
                )
            )
            register_binding(
                Binding(
                    provider_id=provider_id,
                    capability_id=capability_id,
                    metadata={"adapter_name": name},
                )
            )
            caps.append(capability_id)

        registered.append(
            {
                "provider_id": provider_id,
                "adapter_name": name,
                "capabilities": caps,
            }
        )

    return {
        "ok": True,
        "adapter_count": len(items),
        "registered_count": len(registered),
        "providers": registered,
    }


@app.get("/executions")
def executions(limit: int = Query(default=200, ge=1, le=2000)):
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM executions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"ok": True, "executions": [decode(row) for row in rows]}


@app.get("/events")
def events(limit: int = Query(default=500, ge=1, le=2000)):
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"ok": True, "events": [decode(row) for row in rows]}
