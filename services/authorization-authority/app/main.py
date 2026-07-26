from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .domain import (
    AuthorizationAuthorityError,
    AuthorizationStore,
    SERVICE_CONTRACT,
    SERVICE_ID,
    SERVICE_VERSION,
)


DATA_DIR = Path(os.getenv("LEOS_AUTHORIZATION_AUTHORITY_DATA_DIR", "/data/authorization"))
DATABASE = Path(
    os.getenv(
        "LEOS_AUTHORIZATION_AUTHORITY_DB",
        DATA_DIR / "authorization-authority.db",
    )
)

store = AuthorizationStore(DATABASE)
logging.basicConfig(level=os.getenv("LEOS_LOG_LEVEL", "INFO"))
logger = logging.getLogger(SERVICE_ID)

app = FastAPI(title="LEOS Authorization Authority", version=SERVICE_VERSION)


@app.on_event("startup")
def startup() -> None:
    logger.info(
        '{"event":"authorization_authority_startup","service":"%s","database":"%s"}',
        SERVICE_ID,
        DATABASE,
    )
    store.ready()


@app.on_event("shutdown")
def shutdown() -> None:
    logger.info('{"event":"authorization_authority_shutdown","service":"%s"}', SERVICE_ID)


def call(operation):
    try:
        return operation()
    except AuthorizationAuthorityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return store.health()


@app.get("/ready")
def ready() -> dict[str, Any]:
    return store.ready()


@app.get("/version")
def version() -> dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_ID,
        "version": SERVICE_VERSION,
        "service_contract": SERVICE_CONTRACT,
    }


@app.get("/outbox")
def outbox(organization_id: str | None = Query(default=None)) -> dict[str, Any]:
    return call(lambda: store.outbox(organization_id=organization_id))


@app.post("/authorization-decisions")
def create_authorization_decision(payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: store.create_authorization_decision(payload))


@app.get("/authorization-decisions")
def list_authorization_decisions(
    organization_id: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return call(
        lambda: store.list_authorization_decisions(
            organization_id=organization_id,
            subject_id=subject_id,
        )
    )


@app.get("/authorization-decisions/{decision_id:path}")
def get_authorization_decision(decision_id: str) -> dict[str, Any]:
    return call(lambda: store.get_authorization_decision(decision_id))


@app.post("/authorization-decisions/{decision_id:path}/verify")
def verify_authorization_decision(decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: store.verify_authorization_decision(decision_id, payload))


@app.post("/authorization-decisions/{decision_id:path}/revoke")
def revoke_authorization_decision(decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: store.revoke_authorization_decision(decision_id, payload))


@app.post("/capability-permission-grants")
def issue_capability_grant(payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: store.issue_capability_grant(payload))


@app.get("/capability-permission-grants")
def list_capability_grants(
    organization_id: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return call(
        lambda: store.list_capability_grants(
            organization_id=organization_id,
            subject_id=subject_id,
        )
    )


@app.get("/capability-permission-grants/{grant_id:path}")
def get_capability_grant(grant_id: str) -> dict[str, Any]:
    return call(lambda: store.get_capability_grant(grant_id))


@app.post("/capability-permission-grants/{grant_id:path}/revoke")
def revoke_capability_grant(grant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return call(lambda: store.revoke_capability_grant(grant_id, payload))
