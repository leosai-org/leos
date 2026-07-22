from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from lifecycle_engine import (
    ELIGIBILITY_CONTRACT,
    EMPLOYEE_CONTRACT,
    LIFECYCLE_CONTRACT,
    EmployeeConflictError,
    EmployeeLifecycleEngine,
    EmployeeLifecycleError,
    EmployeeNotFoundError,
    legacy_manifest_to_definition,
)

SERVICE_NAME = "employee-registry"
SERVICE_VERSION = "1.0.0"
DATA_DIR = Path(os.getenv("EMPLOYEE_REGISTRY_DATA_DIR", "/data/employee-registry"))
DATABASE = Path(os.getenv("EMPLOYEE_REGISTRY_DB", str(DATA_DIR / "employee-registry.db")))
LEGACY_JSON = Path(os.getenv("EMPLOYEE_REGISTRY_LEGACY_JSON", str(DATA_DIR / "employees.json")))
RESOURCE_PROFILE_URL = os.getenv(
    "EMPLOYEE_RESOURCE_PROFILE_URL",
    "http://employee-resource-profile-service:8000",
).rstrip("/")
EVENT_BUS_URL = os.getenv("EVENT_BUS_BASE_URL", "http://event-bus:8000").rstrip("/")
AGENT_REGISTRY_URL = os.getenv(
    "AGENT_REGISTRY_BASE_URL", "http://agent-registry:8000"
).rstrip("/")
RESOURCE_TIMEOUT_SECONDS = float(
    os.getenv("EMPLOYEE_REGISTRY_RESOURCE_TIMEOUT_SECONDS", "15")
)

engine = EmployeeLifecycleEngine(DATABASE, LEGACY_JSON)
app = FastAPI(title="LEOS Employee Registry", version=SERVICE_VERSION)


class EmployeeCreateRequest(BaseModel):
    definition: dict[str, Any]
    actor: str = "system"
    reason: Optional[str] = None


class EmployeeValidateRequest(BaseModel):
    definition: dict[str, Any]


class LifecycleActionRequest(BaseModel):
    actor: str = "system"
    reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssignmentUpdateRequest(BaseModel):
    changes: dict[str, Any]
    actor: str = "system"
    reason: Optional[str] = None


class EmployeePatchRequest(BaseModel):
    status: Optional[str] = None
    operational_status: Optional[str] = None
    availability: Optional[str] = None
    current_jobs: Optional[int] = None
    health: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    status: str = "available"
    operational_status: Optional[str] = None
    availability: str = "online"
    health: str = "healthy"
    current_jobs: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmployeeRegisterRequest(BaseModel):
    manifest: dict[str, Any]
    source_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentImportRequest(BaseModel):
    overwrite: bool = False
    actor: str = "system"


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EmployeeNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EmployeeConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, EmployeeLifecycleError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


async def publish_event(
    event_type: str,
    employee_id: str,
    payload: dict[str, Any],
    actor: str = "system",
) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{EVENT_BUS_URL}/events",
                json={
                    "event_type": event_type,
                    "source": SERVICE_NAME,
                    "subject": employee_id,
                    "user_id": actor,
                    "payload": payload,
                    "metadata": {
                        "phase": "52.2",
                        "platform": "LEOS",
                        "contract_version": LIFECYCLE_CONTRACT,
                    },
                },
            )
    except Exception:
        pass


async def sync_resource_profile(
    employee_id: str,
    *,
    required: bool,
) -> dict[str, Any]:
    payload = engine.resource_profile_payload(employee_id)
    try:
        async with httpx.AsyncClient(timeout=RESOURCE_TIMEOUT_SECONDS) as client:
            response = await client.put(
                f"{RESOURCE_PROFILE_URL}/profiles/{employee_id}",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            return {
                "ok": True,
                "employee_id": employee_id,
                "required": required,
                "profile": body,
            }
    except Exception as exc:
        if required:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "resource-profile-sync-required",
                    "employee_id": employee_id,
                    "error": str(exc),
                },
            ) from exc
        return {
            "ok": False,
            "employee_id": employee_id,
            "required": required,
            "error": str(exc),
        }


@app.get("/health")
def health() -> dict[str, Any]:
    employees = engine.list(include_archived=True)
    counts: dict[str, int] = {}
    for employee in employees:
        status = employee["lifecycle_status"]
        counts[status] = counts.get(status, 0) + 1
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "platform": "LEOS",
        "version": SERVICE_VERSION,
        "contract_version": EMPLOYEE_CONTRACT,
        "lifecycle_contract": LIFECYCLE_CONTRACT,
        "database": str(DATABASE),
        "employee_count": len(employees),
        "lifecycle_counts": counts,
    }


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "state": "ready",
        "database": str(DATABASE),
    }


@app.post("/employees/validate")
def validate_definition(request: EmployeeValidateRequest) -> dict[str, Any]:
    return engine.validate_payload(request.definition)


@app.post("/employees")
async def create_employee(request: EmployeeCreateRequest) -> dict[str, Any]:
    try:
        employee = engine.create(
            request.definition,
            actor=request.actor,
            reason=request.reason,
        )
    except Exception as exc:
        raise translate_error(exc) from exc
    await publish_event(
        "employee.created",
        employee["employee_id"],
        {
            "employee_id": employee["employee_id"],
            "revision": employee["revision"],
            "lifecycle_status": employee["lifecycle_status"],
        },
        request.actor,
    )
    return {"ok": True, "employee": employee}


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    status: Optional[str] = None,
    lifecycle_status: Optional[str] = None,
    capability: Optional[str] = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    return engine.list(
        department=department,
        lifecycle_status=lifecycle_status or status,
        capability=capability,
        include_archived=include_archived,
    )


@app.get("/employees/available")
def available_employees() -> list[dict[str, Any]]:
    return [
        employee
        for employee in engine.list()
        if engine.eligibility(employee["employee_id"])["eligible"]
    ]


@app.get("/employees/by-department/{department}")
def employees_by_department(department: str) -> list[dict[str, Any]]:
    return engine.list(department=department)


@app.get("/employees/by-capability/{capability}")
def employees_by_capability(capability: str) -> list[dict[str, Any]]:
    return engine.list(capability=capability)


@app.get("/employees/{employee_id}")
def get_employee(employee_id: str) -> dict[str, Any]:
    try:
        return engine.get(employee_id)
    except Exception as exc:
        raise translate_error(exc) from exc


@app.get("/employees/{employee_id}/status")
def get_employee_status(employee_id: str) -> dict[str, Any]:
    try:
        return engine.status(employee_id)
    except Exception as exc:
        raise translate_error(exc) from exc


@app.get("/employees/{employee_id}/history")
def get_employee_history(
    employee_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        return engine.history(employee_id, limit)
    except Exception as exc:
        raise translate_error(exc) from exc


@app.get("/employees/{employee_id}/eligibility")
def get_employee_eligibility(
    employee_id: str,
    requested_at: Optional[str] = None,
) -> dict[str, Any]:
    try:
        return engine.eligibility(employee_id, requested_at)
    except Exception as exc:
        raise translate_error(exc) from exc


@app.get("/employees/{employee_id}/resource-profile")
def get_employee_resource_profile(employee_id: str) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "employee_id": employee_id,
            "profile": engine.resource_profile_payload(employee_id),
        }
    except Exception as exc:
        raise translate_error(exc) from exc


@app.post("/employees/{employee_id}/validate")
async def validate_employee(
    employee_id: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    try:
        employee = engine.validate_existing(
            employee_id,
            actor=request.actor,
            reason=request.reason,
        )
    except Exception as exc:
        raise translate_error(exc) from exc
    await publish_event(
        "employee.validated",
        employee_id,
        {"employee_id": employee_id, "revision": employee["revision"]},
        request.actor,
    )
    return {"ok": True, "employee": employee}


async def transition_employee(
    employee_id: str,
    target: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    if target == "active":
        try:
            current = engine.get(employee_id)
            if current["validation_state"] != "valid":
                current = engine.validate_existing(
                    employee_id,
                    actor=request.actor,
                    reason="activation-validation",
                )
        except Exception as exc:
            raise translate_error(exc) from exc
        # Activation is fail-closed: Phase 52.1 cannot dispatch the employee
        # unless the authoritative resource service has the matching profile.
        provisional_profile = engine.resource_profile_payload(employee_id)
        provisional_profile["enabled"] = True
        try:
            async with httpx.AsyncClient(timeout=RESOURCE_TIMEOUT_SECONDS) as client:
                response = await client.put(
                    f"{RESOURCE_PROFILE_URL}/profiles/{employee_id}",
                    json=provisional_profile,
                )
                response.raise_for_status()
                sync_result = {
                    "ok": True,
                    "employee_id": employee_id,
                    "required": True,
                    "profile": response.json(),
                }
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "resource-profile-sync-required",
                    "employee_id": employee_id,
                    "error": str(exc),
                },
            ) from exc
    else:
        sync_result = None

    try:
        employee = engine.transition(
            employee_id,
            target,
            actor=request.actor,
            reason=request.reason,
            payload=request.metadata,
        )
    except Exception as exc:
        raise translate_error(exc) from exc

    if target != "active":
        sync_result = await sync_resource_profile(employee_id, required=False)

    await publish_event(
        f"employee.{target}",
        employee_id,
        {
            "employee_id": employee_id,
            "lifecycle_status": employee["lifecycle_status"],
            "revision": employee["revision"],
            "resource_profile_sync": sync_result,
        },
        request.actor,
    )
    return {
        "ok": True,
        "employee": employee,
        "resource_profile_sync": sync_result,
    }


@app.post("/employees/{employee_id}/activate")
async def activate_employee(
    employee_id: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    return await transition_employee(employee_id, "active", request)


@app.post("/employees/{employee_id}/pause")
async def pause_employee(
    employee_id: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    return await transition_employee(employee_id, "paused", request)


@app.post("/employees/{employee_id}/resume")
async def resume_employee(
    employee_id: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    return await transition_employee(employee_id, "active", request)


@app.post("/employees/{employee_id}/disable")
async def disable_employee(
    employee_id: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    return await transition_employee(employee_id, "disabled", request)


@app.post("/employees/{employee_id}/archive")
async def archive_employee(
    employee_id: str,
    request: LifecycleActionRequest,
) -> dict[str, Any]:
    return await transition_employee(employee_id, "archived", request)


@app.delete("/employees/{employee_id}")
async def delete_employee(employee_id: str) -> dict[str, Any]:
    # Dev-preview deletion is intentionally soft and auditable.
    return await transition_employee(
        employee_id,
        "archived",
        LifecycleActionRequest(actor="system", reason="delete-requested"),
    )


@app.patch("/employees/{employee_id}/assignments")
async def update_employee_assignments(
    employee_id: str,
    request: AssignmentUpdateRequest,
) -> dict[str, Any]:
    try:
        employee = engine.update_assignments(
            employee_id,
            request.changes,
            actor=request.actor,
            reason=request.reason,
        )
    except Exception as exc:
        raise translate_error(exc) from exc
    sync_result = None
    if employee["lifecycle_status"] == "active":
        sync_result = await sync_resource_profile(employee_id, required=True)
    await publish_event(
        "employee.assignments-updated",
        employee_id,
        {
            "employee_id": employee_id,
            "revision": employee["revision"],
            "changed_fields": sorted(request.changes),
        },
        request.actor,
    )
    return {
        "ok": True,
        "employee": employee,
        "resource_profile_sync": sync_result,
    }


@app.patch("/employees/{employee_id}")
async def patch_employee(
    employee_id: str,
    request: EmployeePatchRequest,
) -> dict[str, Any]:
    try:
        employee = engine.operational_patch(
            employee_id,
            request.model_dump(exclude_none=True),
        )
    except Exception as exc:
        raise translate_error(exc) from exc
    await publish_event(
        "employee.operational-updated",
        employee_id,
        {
            "employee_id": employee_id,
            "operational_status": employee["operational_status"],
            "health": employee["health"],
            "availability": employee["availability"],
            "current_jobs": employee["current_jobs"],
        },
    )
    return {"ok": True, "employee": employee}


@app.post("/employees/{employee_id}/heartbeat")
async def heartbeat(
    employee_id: str,
    request: HeartbeatRequest,
) -> dict[str, Any]:
    try:
        employee = engine.heartbeat(
            employee_id,
            operational_status=request.operational_status or request.status,
            availability=request.availability,
            health=request.health,
            current_jobs=request.current_jobs,
            metadata={**request.metadata, "metrics": request.metrics},
        )
    except Exception as exc:
        raise translate_error(exc) from exc
    await publish_event(
        "employee.heartbeat",
        employee_id,
        {
            "employee_id": employee_id,
            "operational_status": employee["operational_status"],
            "health": employee["health"],
            "current_jobs": employee["current_jobs"],
        },
    )
    return {"ok": True, "employee": employee}


@app.post("/resolve")
def resolve_employee(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        capabilities = [str(item) for item in payload]
        requested_at = None
    elif isinstance(payload, dict):
        capabilities = [str(item) for item in payload.get("required_capabilities", [])]
        requested_at = payload.get("requested_at")
    else:
        raise HTTPException(status_code=422, detail="Invalid resolve payload.")
    return engine.resolve(capabilities, requested_at)


@app.post("/employees/register")
async def register_legacy_employee(
    request: EmployeeRegisterRequest,
) -> dict[str, Any]:
    converted = legacy_manifest_to_definition(request.manifest)
    definition = converted["definition"]
    definition.setdefault("metadata", {}).update(request.metadata)
    if request.source_path:
        definition["metadata"]["source_path"] = request.source_path
    employee_id = definition["employee_id"]
    try:
        try:
            current = engine.get(employee_id)
        except EmployeeNotFoundError:
            current = engine.create(
                definition,
                actor="legacy-register",
                reason="legacy-manifest-registration",
            )
        current = engine.validate_existing(
            employee_id,
            actor="legacy-register",
            reason="legacy-manifest-validation",
        )
        desired = converted["lifecycle_status"]
        if desired == "active" and current["lifecycle_status"] != "active":
            # Preserve legacy registration without silently bypassing the
            # resource authority. Legacy records remain validated until an
            # explicit activation succeeds.
            desired = "validated"
        if desired != current["lifecycle_status"]:
            current = engine.transition(
                employee_id,
                desired,
                actor="legacy-register",
                reason="legacy-manifest-status",
            )
    except Exception as exc:
        raise translate_error(exc) from exc
    await publish_event(
        "employee.registered",
        employee_id,
        {
            "employee_id": employee_id,
            "legacy": True,
            "lifecycle_status": current["lifecycle_status"],
        },
    )
    return {"ok": True, "employee": current}


@app.post("/import/agents")
async def import_agents(request: AgentImportRequest) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{AGENT_REGISTRY_URL}/agents")
        response.raise_for_status()
        agents = response.json()
    imported: list[str] = []
    skipped: list[Any] = []
    for agent_name, agent in agents.items():
        employee_id = agent_name.replace("_", "-").replace("agent", "employee")
        definition = {
            "employee_id": employee_id,
            "name": employee_id.replace("-", " ").title(),
            "description": agent.get("description", ""),
            "role": employee_id.replace("-", " ").title(),
            "department": agent.get("metadata", {}).get("category", "general"),
            "capabilities": agent.get("capabilities", []) or ["general.execute"],
            "runtime": {
                "type": "http",
                "endpoint": agent.get("entrypoint"),
                "execute_path": "/execute",
                "health_path": "/health",
                "timeout_seconds": 300,
            },
            "model_preferences": [],
            "resource_profile": {},
            "schedule": {"mode": "always"},
            "metadata": {
                "source": "agent-registry-import",
                "legacy_agent_name": agent_name,
            },
        }
        try:
            try:
                engine.get(employee_id)
                if not request.overwrite:
                    skipped.append(employee_id)
                    continue
                employee = engine.update_assignments(
                    employee_id,
                    {
                        key: value
                        for key, value in definition.items()
                        if key
                        in {
                            "role",
                            "department",
                            "capabilities",
                            "runtime",
                            "model_preferences",
                            "resource_profile",
                            "schedule",
                            "metadata",
                        }
                    },
                    actor=request.actor,
                    reason="agent-registry-reimport",
                )
            except EmployeeNotFoundError:
                employee = engine.create(
                    definition,
                    actor=request.actor,
                    reason="agent-registry-import",
                )
            engine.validate_existing(
                employee_id,
                actor=request.actor,
                reason="agent-registry-import-validation",
            )
            imported.append(employee_id)
        except Exception as exc:
            skipped.append({"employee_id": employee_id, "error": str(exc)})
    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "employee_count": len(engine.list(include_archived=True)),
    }
