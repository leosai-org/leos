from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator


SERVICE_CONTRACT = "model-registry.inventory.provisional-v1"
SCHEMA_VERSION = 1
DATA_DIR = Path(os.getenv("MODEL_REGISTRY_DATA_DIR", "/data/model-registry"))
DB_PATH = Path(os.getenv("MODEL_REGISTRY_DB", DATA_DIR / "model-registry.db"))
CAPABILITY_MANAGER_URL = os.getenv(
    "CAPABILITY_MANAGER_URL", "http://capability-manager:8000"
).rstrip("/")
RAW_CREDENTIAL_VALUE_KEYS = {
    "api_key",
    "access_token",
    "auth_token",
    "client_secret",
    "credential_value",
    "password",
    "private_key",
    "private_key_pem",
    "refresh_token",
    "secret_value",
}
IDENTITY_FIELDS = ("version", "architecture", "parameter_count", "quantization")
MAX_METADATA_BYTES = 65_536
MAX_METADATA_DEPTH = 12

app = FastAPI(title="LEOS Model Registry", version="0.2.0-dev-preview-v2")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def revision_for(kind: str, value: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        f"{kind}:{canonical_json(value)}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def reject_raw_credential_values(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if (
                normalized in RAW_CREDENTIAL_VALUE_KEYS
                and isinstance(child, (str, bytes))
                and bool(child)
            ):
                raise ValueError(
                    f"raw credential value is prohibited at {path}.{key}"
                )
            reject_raw_credential_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_raw_credential_values(child, f"{path}[{index}]")


def validate_bounded_object(
    value: dict[str, Any],
    *,
    field: str,
    depth: int = 0,
) -> dict[str, Any]:
    if len(canonical_json(value).encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError(f"{field} exceeds {MAX_METADATA_BYTES} bytes")

    def check_depth(item: Any, current: int) -> None:
        if current > MAX_METADATA_DEPTH:
            raise ValueError(f"{field} exceeds nesting depth {MAX_METADATA_DEPTH}")
        if isinstance(item, dict):
            for child in item.values():
                check_depth(child, current + 1)
        elif isinstance(item, list):
            for child in item:
                check_depth(child, current + 1)

    check_depth(value, depth)
    reject_raw_credential_values(value)
    return value


def nonempty_strings(values: list[str], field: str) -> list[str]:
    normalized = []
    for value in values:
        item = value.strip()
        if not item:
            raise ValueError(f"{field} entries must be non-empty")
        if item not in normalized:
            normalized.append(item)
    return sorted(normalized)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelWrite(StrictModel):
    model_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    family: str | None = None
    publisher: str | None = None
    version: str | None = None
    architecture: str | None = None
    parameter_count: int | None = Field(default=None, ge=0)
    quantization: str | None = None
    modalities: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    context_window_tokens: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    runtime_requirements: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_id", "display_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must be non-empty")
        return value

    @field_validator("modalities", "capabilities")
    @classmethod
    def validate_string_lists(cls, value: list[str], info: Any) -> list[str]:
        return nonempty_strings(value, info.field_name)

    @field_validator("runtime_requirements", "metadata")
    @classmethod
    def validate_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_bounded_object(value, field="model inventory object")


class ModelUpdate(StrictModel):
    expected_revision: str = Field(min_length=1)
    display_name: str | None = Field(default=None, min_length=1)
    family: str | None = None
    publisher: str | None = None
    version: str | None = None
    architecture: str | None = None
    parameter_count: int | None = Field(default=None, ge=0)
    quantization: str | None = None
    modalities: list[str] | None = None
    capabilities: list[str] | None = None
    context_window_tokens: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    runtime_requirements: dict[str, Any] | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("modalities", "capabilities")
    @classmethod
    def validate_string_lists(
        cls, value: list[str] | None, info: Any
    ) -> list[str] | None:
        return None if value is None else nonempty_strings(value, info.field_name)

    @field_validator("runtime_requirements", "metadata")
    @classmethod
    def validate_no_secrets(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is not None:
            return validate_bounded_object(value, field="model inventory object")
        return None


class ProviderReference(StrictModel):
    authority: Literal["capability-manager"]
    reference_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class Availability(StrictModel):
    state: Literal["unknown", "available", "unavailable"] = "unknown"
    observed_at: datetime | None = None
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def validate_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_bounded_object(value, field="availability details")


class BindingWrite(StrictModel):
    binding_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_ref: ProviderReference
    runtime_model_ref: str = Field(min_length=1)
    runtime_type: str = ""
    enabled: bool = True
    availability: Availability = Field(default_factory=Availability)
    runtime_requirements: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runtime_requirements", "metadata")
    @classmethod
    def validate_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_bounded_object(value, field="binding inventory object")

    @field_validator("runtime_model_ref")
    @classmethod
    def normalize_runtime_model_ref(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("runtime_model_ref must be non-empty")
        return value

    @field_validator("runtime_type")
    @classmethod
    def normalize_runtime_type(cls, value: str | None) -> str:
        return (value or "").strip().lower()

    @field_validator("provider_ref")
    @classmethod
    def validate_provider_identity(
        cls, value: ProviderReference, info: Any
    ) -> ProviderReference:
        provider_id = info.data.get("provider_id")
        if provider_id and value.reference_id != provider_id:
            raise ValueError("provider_ref.reference_id must equal provider_id")
        return value


class BindingUpdate(StrictModel):
    expected_revision: str = Field(min_length=1)
    provider_ref: ProviderReference | None = None
    runtime_model_ref: str | None = Field(default=None, min_length=1)
    runtime_type: str | None = None
    enabled: bool | None = None
    availability: Availability | None = None
    runtime_requirements: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("runtime_requirements", "metadata")
    @classmethod
    def validate_no_secrets(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if value is not None:
            return validate_bounded_object(value, field="binding inventory object")
        return None

    @field_validator("runtime_model_ref")
    @classmethod
    def normalize_runtime_model_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("runtime_model_ref must be non-empty")
        return value

    @field_validator("runtime_type")
    @classmethod
    def normalize_runtime_type(cls, value: str | None) -> str:
        return (value or "").strip().lower()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 30000")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def migrate() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS model_registry_schema (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS models (
                model_id TEXT PRIMARY KEY,
                document_json TEXT NOT NULL,
                revision TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS model_runtime_bindings (
                binding_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                runtime_type TEXT NOT NULL,
                runtime_model_ref TEXT NOT NULL,
                document_json TEXT NOT NULL,
                revision TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (model_id) REFERENCES models(model_id)
            );
            CREATE INDEX IF NOT EXISTS idx_model_bindings_model
                ON model_runtime_bindings(model_id);
            CREATE INDEX IF NOT EXISTS idx_model_bindings_provider
                ON model_runtime_bindings(provider_id);
            CREATE TABLE IF NOT EXISTS model_registry_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                previous_revision TEXT,
                new_revision TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
            """
        )
        binding_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(model_runtime_bindings)")
        }
        if "runtime_type" not in binding_columns:
            db.execute(
                "ALTER TABLE model_runtime_bindings ADD COLUMN runtime_type TEXT"
            )
        if "runtime_model_ref" not in binding_columns:
            db.execute(
                "ALTER TABLE model_runtime_bindings "
                "ADD COLUMN runtime_model_ref TEXT"
            )
        rows = db.execute(
            """
            SELECT binding_id, document_json
            FROM model_runtime_bindings
            WHERE runtime_type IS NULL OR runtime_model_ref IS NULL
            """
        ).fetchall()
        for row in rows:
            document = json.loads(row["document_json"])
            db.execute(
                """
                UPDATE model_runtime_bindings
                SET runtime_type = ?, runtime_model_ref = ?
                WHERE binding_id = ?
                """,
                (
                    str(document.get("runtime_type") or "").strip().lower(),
                    str(document.get("runtime_model_ref") or "").strip(),
                    row["binding_id"],
                ),
            )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_model_binding_runtime_target
            ON model_runtime_bindings(
                provider_id, runtime_type, runtime_model_ref
            )
            """
        )
        event_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(model_registry_events)")
        }
        if "previous_revision" not in event_columns:
            db.execute(
                "ALTER TABLE model_registry_events "
                "ADD COLUMN previous_revision TEXT"
            )
        if "new_revision" not in event_columns:
            db.execute(
                "ALTER TABLE model_registry_events ADD COLUMN new_revision TEXT"
            )
            if "revision" in event_columns:
                db.execute(
                    "UPDATE model_registry_events "
                    "SET new_revision = revision WHERE new_revision IS NULL"
                )
        db.execute(
            """
            INSERT OR IGNORE INTO model_registry_schema(version, applied_at)
            VALUES (?, ?)
            """,
            (SCHEMA_VERSION, utc_now()),
        )


def material_model(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in ModelWrite.model_fields}


def material_binding(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in BindingWrite.model_fields}


def stored_document(row: sqlite3.Row) -> dict[str, Any]:
    result = json.loads(row["document_json"])
    result.update(
        revision=row["revision"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
    return result


def record_event(
    db: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    event_type: str,
    new_revision: str,
    occurred_at: str,
    previous_revision: str | None = None,
) -> None:
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(model_registry_events)")
    }
    if "revision" in columns:
        db.execute(
            """
            INSERT INTO model_registry_events(
                entity_type, entity_id, event_type, revision,
                previous_revision, new_revision, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                event_type,
                new_revision,
                previous_revision,
                new_revision,
                occurred_at,
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO model_registry_events(
                entity_type, entity_id, event_type, previous_revision,
                new_revision, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                entity_id,
                event_type,
                previous_revision,
                new_revision,
                occurred_at,
            ),
        )


async def verify_provider_reference(reference: ProviderReference) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{CAPABILITY_MANAGER_URL}/providers",
                params={"limit": 2000},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "provider_authority_unavailable",
                "message": str(error),
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "provider_authority_invalid_response",
                "message": "Capability Manager returned malformed JSON.",
            },
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail={"code": "provider_authority_invalid_response"},
        )
    providers = payload.get("providers")
    if not isinstance(providers, list):
        raise HTTPException(
            status_code=502,
            detail={"code": "provider_authority_invalid_response"},
        )
    for provider in providers:
        if not isinstance(provider, dict):
            raise HTTPException(
                status_code=502,
                detail={"code": "provider_authority_invalid_response"},
            )
        provider_id = provider.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise HTTPException(
                status_code=502,
                detail={"code": "provider_authority_invalid_response"},
            )
        if provider_id != reference.reference_id:
            continue
        provider_revision = provider.get("updated_at")
        if not isinstance(provider_revision, str) or not provider_revision.strip():
            raise HTTPException(
                status_code=502,
                detail={"code": "provider_authority_invalid_response"},
            )
        if provider_revision != reference.revision:
            raise HTTPException(
                status_code=409,
                detail={"code": "provider_revision_mismatch"},
            )
        return
    if len(providers) >= 2000:
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_lookup_incomplete"},
        )
    raise HTTPException(status_code=422, detail={"code": "unknown_provider"})


@app.on_event("startup")
def startup() -> None:
    migrate()


@app.get("/health")
def health() -> dict[str, Any]:
    migrate()
    with connect() as db:
        model_count = db.execute("SELECT COUNT(*) FROM models").fetchone()[0]
        binding_count = db.execute(
            "SELECT COUNT(*) FROM model_runtime_bindings"
        ).fetchone()[0]
    return {
        "ok": True,
        "service": "model-registry-service",
        "service_contract": SERVICE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "model_count": model_count,
        "binding_count": binding_count,
    }


@app.post("/models")
def register_model(request: ModelWrite) -> dict[str, Any]:
    material = material_model(request.model_dump(mode="json"))
    revision = revision_for("model", material)
    now = utc_now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM models WHERE model_id = ?", (request.model_id,)
        ).fetchone()
        if existing:
            current = stored_document(existing)
            if existing["revision"] != revision:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "model_already_exists"},
                )
            return {"ok": True, "changed": False, "model": current}
        db.execute(
            """
            INSERT INTO models(
                model_id, document_json, revision, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (request.model_id, canonical_json(material), revision, now, now),
        )
        record_event(db, "model", request.model_id, "registered", revision, now)
    return {
        "ok": True,
        "changed": True,
        "model": {**material, "revision": revision, "created_at": now, "updated_at": now},
    }


@app.get("/models")
def list_models(
    enabled: bool | None = None,
    capability: str | None = None,
    modality: str | None = None,
) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute("SELECT * FROM models ORDER BY model_id").fetchall()
    models = [stored_document(row) for row in rows]
    if enabled is not None:
        models = [item for item in models if item["enabled"] is enabled]
    if capability:
        models = [item for item in models if capability in item["capabilities"]]
    if modality:
        models = [item for item in models if modality in item["modalities"]]
    return {"models": models, "count": len(models)}


@app.get("/models/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM models WHERE model_id = ?", (model_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="model not found")
    return {"model": stored_document(row)}


@app.patch("/models/{model_id}")
def update_model(model_id: str, request: ModelUpdate) -> dict[str, Any]:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM models WHERE model_id = ?", (model_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="model not found")
        if row["revision"] != request.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "revision_conflict",
                    "current_revision": row["revision"],
                },
            )
        current = stored_document(row)
        material = material_model(current)
        updates = request.model_dump(exclude_unset=True, mode="json")
        updates.pop("expected_revision")
        for field in IDENTITY_FIELDS:
            if field not in updates:
                continue
            previous = material[field]
            proposed = updates[field]
            if previous is not None and proposed != previous:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "model_identity_conflict",
                        "field": field,
                    },
                )
        material.update(updates)
        material["model_id"] = model_id
        revision = revision_for("model", material)
        if revision == row["revision"]:
            return {"ok": True, "changed": False, "model": current}
        now = utc_now()
        db.execute(
            """
            UPDATE models SET document_json = ?, revision = ?, updated_at = ?
            WHERE model_id = ?
            """,
            (canonical_json(material), revision, now, model_id),
        )
        record_event(
            db,
            "model",
            model_id,
            "updated",
            revision,
            now,
            previous_revision=row["revision"],
        )
    return {
        "ok": True,
        "changed": True,
        "model": {
            **material,
            "revision": revision,
            "created_at": current["created_at"],
            "updated_at": now,
        },
    }


@app.post("/bindings")
async def register_binding(request: BindingWrite) -> dict[str, Any]:
    await verify_provider_reference(request.provider_ref)
    material = material_binding(request.model_dump(mode="json"))
    revision = revision_for("model-runtime-binding", material)
    now = utc_now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(
            "SELECT 1 FROM models WHERE model_id = ?", (request.model_id,)
        ).fetchone() is None:
            raise HTTPException(status_code=422, detail={"code": "unknown_model"})
        existing = db.execute(
            "SELECT * FROM model_runtime_bindings WHERE binding_id = ?",
            (request.binding_id,),
        ).fetchone()
        if existing:
            current = stored_document(existing)
            if existing["revision"] != revision:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "binding_already_exists"},
                )
            return {"ok": True, "changed": False, "binding": current}
        logical = db.execute(
            """
            SELECT binding_id
            FROM model_runtime_bindings
            WHERE provider_id = ? AND runtime_type = ?
              AND runtime_model_ref = ?
            """,
            (
                request.provider_id,
                request.runtime_type,
                request.runtime_model_ref,
            ),
        ).fetchone()
        if logical is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "binding_target_conflict",
                    "binding_id": logical["binding_id"],
                },
            )
        db.execute(
            """
            INSERT INTO model_runtime_bindings(
                binding_id, model_id, provider_id, runtime_type,
                runtime_model_ref, document_json, revision, created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.binding_id,
                request.model_id,
                request.provider_id,
                request.runtime_type,
                request.runtime_model_ref,
                canonical_json(material),
                revision,
                now,
                now,
            ),
        )
        record_event(
            db, "binding", request.binding_id, "registered", revision, now
        )
    return {
        "ok": True,
        "changed": True,
        "binding": {
            **material,
            "revision": revision,
            "created_at": now,
            "updated_at": now,
        },
    }


@app.get("/bindings")
def list_bindings(
    model_id: str | None = None,
    provider_id: str | None = None,
    enabled: bool | None = None,
    availability: Literal["unknown", "available", "unavailable"] | None = None,
) -> dict[str, Any]:
    clauses: list[str] = []
    values: list[Any] = []
    if model_id:
        clauses.append("model_id = ?")
        values.append(model_id)
    if provider_id:
        clauses.append("provider_id = ?")
        values.append(provider_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as db:
        rows = db.execute(
            f"SELECT * FROM model_runtime_bindings{where} ORDER BY binding_id",
            values,
        ).fetchall()
    bindings = [stored_document(row) for row in rows]
    if enabled is not None:
        bindings = [item for item in bindings if item["enabled"] is enabled]
    if availability:
        bindings = [
            item
            for item in bindings
            if item["availability"]["state"] == availability
        ]
    return {"bindings": bindings, "count": len(bindings)}


@app.get("/bindings/{binding_id}")
def get_binding(binding_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM model_runtime_bindings WHERE binding_id = ?",
            (binding_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="binding not found")
    return {"binding": stored_document(row)}


@app.patch("/bindings/{binding_id}")
async def update_binding(
    binding_id: str, request: BindingUpdate
) -> dict[str, Any]:
    updates = request.model_dump(exclude_unset=True, mode="json")
    expected_revision = updates.pop("expected_revision")
    if "provider_ref" in updates:
        reference = ProviderReference.model_validate(updates["provider_ref"])
        await verify_provider_reference(reference)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM model_runtime_bindings WHERE binding_id = ?",
            (binding_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="binding not found")
        if row["revision"] != expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "revision_conflict",
                    "current_revision": row["revision"],
                },
            )
        current = stored_document(row)
        material = material_binding(current)
        if (
            "provider_ref" in updates
            and updates["provider_ref"]["reference_id"] != material["provider_id"]
        ):
            raise HTTPException(
                status_code=422,
                detail={"code": "provider_reference_mismatch"},
            )
        material.update(updates)
        revision = revision_for("model-runtime-binding", material)
        if revision == row["revision"]:
            return {"ok": True, "changed": False, "binding": current}
        logical = db.execute(
            """
            SELECT binding_id
            FROM model_runtime_bindings
            WHERE provider_id = ? AND runtime_type = ?
              AND runtime_model_ref = ? AND binding_id <> ?
            """,
            (
                material["provider_id"],
                material["runtime_type"],
                material["runtime_model_ref"],
                binding_id,
            ),
        ).fetchone()
        if logical is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "binding_target_conflict",
                    "binding_id": logical["binding_id"],
                },
            )
        now = utc_now()
        db.execute(
            """
            UPDATE model_runtime_bindings
            SET document_json = ?, revision = ?, updated_at = ?
                , runtime_type = ?, runtime_model_ref = ?
            WHERE binding_id = ?
            """,
            (
                canonical_json(material),
                revision,
                now,
                material["runtime_type"],
                material["runtime_model_ref"],
                binding_id,
            ),
        )
        record_event(
            db,
            "binding",
            binding_id,
            "updated",
            revision,
            now,
            previous_revision=row["revision"],
        )
    return {
        "ok": True,
        "changed": True,
        "binding": {
            **material,
            "revision": revision,
            "created_at": current["created_at"],
            "updated_at": now,
        },
    }


@app.get("/events")
def list_events(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT * FROM model_registry_events
            ORDER BY event_id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


migrate()
