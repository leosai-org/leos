from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from engine import (
    ARTIFACT_CONTRACT,
    EMPLOYEE_ID,
    HISTORY_CONTRACT,
    RUN_CONTRACT,
    SERVICE_ID,
    GovernanceError,
    ReferenceEmployeeError,
    ReferenceResearchContentEngine,
    RunNotFoundError,
)

DATA_DIR = Path(
    os.getenv(
        "LEOS_REFERENCE_RESEARCH_CONTENT_DATA_DIR",
        "/data/reference-research-content-employee",
    )
)
DB_PATH = DATA_DIR / "reference-research-content.db"


class SourceInput(BaseModel):
    source_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    content: str
    adapter_id: str = "manual-source-input"
    provenance: dict[str, Any] = Field(default_factory=dict)


class ReferenceRunRequest(BaseModel):
    goal_id: str
    goal: str
    title: Optional[str] = None
    requested_by: str = "operator"
    sources: list[SourceInput] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    approved_adapters: list[str] = Field(
        default_factory=lambda: [
            "manual-source-input",
            "company-knowledge-service",
        ]
    )
    governance: dict[str, Any]
    initial_draft: Optional[str] = None
    minimum_words: int = Field(default=220, ge=120, le=5000)
    max_revision_attempts: int = Field(default=2, ge=0, le=5)
    run_id: Optional[str] = None
    artifact_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecuteEnvelope(BaseModel):
    capability: str = "research-content.execute"
    input: dict[str, Any] = Field(default_factory=dict)
    requester: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    reason: str = "operator-request"


engine = ReferenceResearchContentEngine(DB_PATH)
app = FastAPI(
    title="LEOS Reference Research and Content Employee",
    version="0.1.0",
)


def error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, RunNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, GovernanceError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ReferenceEmployeeError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def request_dict(request: ReferenceRunRequest) -> dict[str, Any]:
    return request.model_dump(exclude_none=True)


@app.get("/health")
def health() -> dict[str, Any]:
    runs = engine.list_runs(limit=1000)
    counts: dict[str, int] = {}
    for run in runs:
        counts[run["state"]] = counts.get(run["state"], 0) + 1
    return {
        "ok": True,
        "service": SERVICE_ID,
        "employee_id": EMPLOYEE_ID,
        "platform": "LEOS",
        "version": "0.1.0",
        "contract_version": RUN_CONTRACT,
        "artifact_contract": ARTIFACT_CONTRACT,
        "history_contract": HISTORY_CONTRACT,
        "capabilities": [
            "research.plan",
            "research.sources",
            "research.extract",
            "content.outline",
            "content.draft",
            "content.review.request",
            "content.revise",
            "artifact.persist",
            "artifact.history",
            "execution.history",
        ],
        "state_counts": counts,
        "database": str(DB_PATH),
        "internet_access": False,
        "approved_adapter_only": True,
    }


@app.post("/runs", status_code=201)
def create_run(request: ReferenceRunRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.create_run(request_dict(request))}
    except Exception as exc:
        raise error_response(exc) from exc


@app.get("/runs")
def list_runs(
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    runs = engine.list_runs(limit=limit)
    return {"ok": True, "count": len(runs), "runs": runs}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.get_run(run_id)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.post("/runs/{run_id}/execute")
def execute_run(run_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.execute(run_id)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.post("/runs/{run_id}/pause")
def pause_run(run_id: str, request: ActionRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.pause(run_id, request.reason)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str, request: ActionRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.resume(run_id, request.reason)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: ActionRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.cancel(run_id, request.reason)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.post("/runs/{run_id}/recover")
def recover_run(run_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "run": engine.recover(run_id)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.get("/runs/{run_id}/history")
def run_history(run_id: str) -> dict[str, Any]:
    try:
        return engine.history(run_id)
    except Exception as exc:
        raise error_response(exc) from exc


@app.get("/runs/{run_id}/sources")
def run_sources(run_id: str) -> dict[str, Any]:
    try:
        sources = engine.sources(run_id)
        return {"ok": True, "count": len(sources), "sources": sources}
    except Exception as exc:
        raise error_response(exc) from exc


@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "artifact": engine.get_artifact(artifact_id)}
    except Exception as exc:
        raise error_response(exc) from exc


@app.post("/execute")
def execute_compatibility(request: ExecuteEnvelope) -> dict[str, Any]:
    if request.capability not in {
        "research-content.execute",
        "research.plan",
        "research.sources",
        "research.extract",
        "content.draft",
        "content.revise",
        "artifact.persist",
    }:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported capability: {request.capability}",
        )
    payload = dict(request.input)
    payload.setdefault(
        "requested_by",
        request.requester.get("employee_id")
        or request.requester.get("user_id")
        or "scheduler",
    )
    payload.setdefault("metadata", {})
    payload["metadata"] = {
        **payload["metadata"],
        **request.metadata,
        "requested_capability": request.capability,
    }
    try:
        created = engine.create_run(payload)
        completed = engine.execute(created["run_id"])
        artifact = engine.get_artifact(completed["artifact_id"])
        return {
            "ok": True,
            "status": completed["state"],
            "run_id": completed["run_id"],
            "artifact_id": completed["artifact_id"],
            "result": completed["result"],
            "artifact": artifact,
            "error": None,
        }
    except Exception as exc:
        raise error_response(exc) from exc
