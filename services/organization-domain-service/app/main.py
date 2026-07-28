from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .domain import (
    COLLECTION_TO_RESOURCE_TYPE,
    HttpAuthorizationVerifier,
    RESOURCE_TYPE_TO_COLLECTION,
    SERVICE_CONTRACT,
    SERVICE_ID,
    SERVICE_VERSION,
    OrganizationDomainError,
    OrganizationDomainStore,
)


DATA_DIR = Path(os.getenv("LEOS_ORGANIZATION_DOMAIN_DATA_DIR", "/data/organization-domain"))
DATABASE = Path(
    os.getenv(
        "LEOS_ORGANIZATION_DOMAIN_DB",
        DATA_DIR / "organization-domain.db",
    )
)
AUTHORIZATION_AUTHORITY_URL = os.getenv(
    "LEOS_AUTHORIZATION_AUTHORITY_URL",
    "http://authorization-authority:8000",
)
AUTHORIZATION_AUTHORITY_TIMEOUT_SECONDS = float(
    os.getenv("LEOS_AUTHORIZATION_AUTHORITY_TIMEOUT_SECONDS", "5")
)

store = OrganizationDomainStore(
    DATABASE,
    authorization_verifier=HttpAuthorizationVerifier(
        AUTHORIZATION_AUTHORITY_URL,
        timeout=AUTHORIZATION_AUTHORITY_TIMEOUT_SECONDS,
    ),
)
logging.basicConfig(level=os.getenv("LEOS_LOG_LEVEL", "INFO"))
logger = logging.getLogger(SERVICE_ID)

app = FastAPI(
    title="LEOS Organization Domain Service",
    version=SERVICE_VERSION,
)


@app.on_event("startup")
def startup() -> None:
    logger.info(
        '{"event":"organization_domain_startup","service":"%s","database":"%s"}',
        SERVICE_ID,
        DATABASE,
    )
    store.ready()


@app.on_event("shutdown")
def shutdown() -> None:
    logger.info(
        '{"event":"organization_domain_shutdown","service":"%s"}',
        SERVICE_ID,
    )


def call(operation):
    try:
        return operation()
    except OrganizationDomainError as exc:
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


@app.get("/audit/{resource_type}/{resource_id:path}")
def audit(resource_type: str, resource_id: str) -> dict[str, Any]:
    normalized = resource_type.upper().replace("-", "_")
    if normalized not in RESOURCE_TYPE_TO_COLLECTION:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "unknown resource type"},
        )
    return call(lambda: store.audit(normalized, resource_id))


@app.get("/outbox")
def outbox(organization_id: str | None = Query(default=None)) -> dict[str, Any]:
    return call(lambda: store.outbox(organization_id=organization_id))


@app.get("/transitions")
def transitions(organization_id: str | None = Query(default=None)) -> dict[str, Any]:
    return call(lambda: store.transitions(organization_id=organization_id))


@app.post("/{collection}")
def create_record(collection: str, payload: dict[str, Any]) -> dict[str, Any]:
    resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
    if resource_type is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "unknown collection"},
        )
    record = payload.get("record") if isinstance(payload, dict) else None
    if isinstance(record, dict) and record.get("identity", {}).get("resource_type") != resource_type:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "validation_failure",
                "message": "record resource_type does not match collection",
            },
        )
    return call(lambda: store.create(payload))


@app.get("/{collection}")
def list_records(
    collection: str,
    organization_id: str | None = Query(default=None),
) -> dict[str, Any]:
    resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
    if resource_type is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "unknown collection"},
        )
    return call(lambda: store.list_records(resource_type, organization_id=organization_id))


@app.get("/{collection}/{resource_id:path}")
def get_record(
    collection: str,
    resource_id: str,
    organization_id: str | None = Query(default=None),
) -> dict[str, Any]:
    resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
    if resource_type is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "unknown collection"},
        )
    return call(lambda: store.get(resource_type, resource_id, organization_id=organization_id))


@app.patch("/{collection}/{resource_id:path}")
def update_record(collection: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
    if resource_type is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "unknown collection"},
        )
    return call(lambda: store.update(resource_type, resource_id, payload))


@app.post("/{collection}/{resource_id:path}/transition")
def transition_record(collection: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    resource_type = COLLECTION_TO_RESOURCE_TYPE.get(collection)
    if resource_type is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "unknown collection"},
        )
    return call(lambda: store.transition(resource_type, resource_id, payload))
