from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from .resource_engine import (
    ResourceEngine,
    ResourceNotFoundError,
    ResourcePolicyError,
)


DATABASE = Path(
    os.getenv(
        "LEOS_RESOURCE_PROFILE_DB",
        "/data/employee-resource-profile/resource-policy.db",
    )
)
engine = ResourceEngine(DATABASE)

app = FastAPI(
    title="LEOS Employee Resource Profile Service",
    version="0.2.0",
)


def call(operation):
    try:
        return operation()
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResourcePolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    snapshot = engine.snapshot()
    return {
        "ok": True,
        "service": "employee-resource-profile-service",
        "platform": "LEOS",
        "version": "0.2.0",
        "contract_version": "leos.employee-resource-profile.v1",
        "database": str(DATABASE),
        "profile_count": snapshot["profile_count"],
        "node_count": snapshot["node_count"],
        "active_reservation_count": snapshot[
            "active_reservation_count"
        ],
    }


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "employee-resource-profile-service",
        "state": "ready",
        "database": str(DATABASE),
    }


@app.post("/profiles")
def create_profile(payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: engine.upsert_profile(payload))


@app.put("/profiles/{employee_id}")
def upsert_profile(
    employee_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return call(lambda: engine.upsert_profile(payload, employee_id))


@app.get("/profiles")
def list_profiles() -> dict[str, Any]:
    profiles = engine.list_profiles()
    return {"ok": True, "count": len(profiles), "profiles": profiles}


@app.get("/profiles/{employee_id}")
def get_profile(employee_id: str) -> dict[str, Any]:
    return call(lambda: engine.get_profile(employee_id))


@app.post("/nodes")
def create_node(payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: engine.register_node(payload))


@app.put("/nodes/{node_id}")
def upsert_node(
    node_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return call(lambda: engine.register_node(payload, node_id))


@app.get("/nodes")
def list_nodes() -> dict[str, Any]:
    nodes = engine.list_nodes()
    return {"ok": True, "count": len(nodes), "nodes": nodes}


@app.get("/nodes/{node_id}")
def get_node(node_id: str) -> dict[str, Any]:
    return call(lambda: engine.get_node(node_id))


@app.post("/admission/evaluate")
def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    return call(
        lambda: engine.evaluate(
            payload.get("employee_id"),
            payload.get("job_id"),
            payload.get("requested_at"),
        )
    )


@app.post("/reservations")
def reserve(payload: dict[str, Any]) -> dict[str, Any]:
    return call(
        lambda: engine.reserve(
            payload.get("employee_id"),
            payload.get("job_id"),
            payload.get("requested_at"),
            bool(payload.get("commit_preemption", False)),
        )
    )


@app.get("/reservations")
def list_reservations(status: str | None = None) -> dict[str, Any]:
    reservations = engine.list_reservations(status)
    return {
        "ok": True,
        "count": len(reservations),
        "reservations": reservations,
    }


@app.get("/reservations/by-job/{job_id}")
def get_reservation_by_job(job_id: str) -> dict[str, Any]:
    return call(
        lambda: engine.active_reservation_for_job(job_id)
    )


@app.post("/reservations/expire")
def expire_reservations() -> dict[str, Any]:
    return call(engine.expire_reservations)


@app.get("/reservations/{reservation_id}")
def get_reservation(reservation_id: str) -> dict[str, Any]:
    return call(
        lambda: engine.get_reservation(reservation_id)
    )


@app.post("/reservations/{reservation_id}/release")
def release(
    reservation_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = payload or {}
    return call(
        lambda: engine.release(
            reservation_id,
            str(body.get("reason", "released")),
        )
    )


@app.get("/snapshot")
def snapshot() -> dict[str, Any]:
    return engine.snapshot()
