from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, HTTPException, Query
from leos_contracts import ContractValidationError, validate_contract
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DB_PATH = Path(os.getenv("RANKING_POLICY_DB", "/data/ranking-policy/rankings.db"))
RECORD_CONTRACT = "ranking-policy.record.provisional-v1"
REQUEST_CONTRACT = "leos.effective-ranking-request.v1"
RESULT_CONTRACT = "leos.effective-ranking-result.v1"
SCOPES = ("job", "employee", "capability", "global")

app = FastAPI(title="LEOS Ranking Policy Authority", version="0.2.0-dev-preview-v2")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def revision(value: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical(value).encode()).hexdigest()
    return f"sha256:{digest}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RankingWrite(StrictModel):
    dimension: Literal["provider", "model"]
    scope_type: Literal["global", "capability", "employee", "job"]
    scope_id: str | None = Field(default=None, min_length=1, max_length=256)
    ordered_ids: list[str] = Field(min_length=1)
    active: bool = True

    @field_validator("ordered_ids")
    @classmethod
    def exact_unique_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("ordered_ids entries must be non-empty identifiers")
        if len(value) != len(set(value)):
            raise ValueError("ordered_ids must not contain duplicates")
        return list(value)

    @model_validator(mode="after")
    def valid_scope(self) -> "RankingWrite":
        if self.scope_type == "global" and self.scope_id is not None:
            raise ValueError("global scope must not have scope_id")
        if self.scope_type != "global" and self.scope_id is None:
            raise ValueError("non-global scope requires scope_id")
        return self


class RankingPatch(StrictModel):
    expected_revision: str = Field(min_length=1)
    ordered_ids: list[str] | None = Field(default=None, min_length=1)
    active: bool | None = None

    @field_validator("ordered_ids")
    @classmethod
    def exact_unique_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("ordered_ids entries must be non-empty identifiers")
        if len(value) != len(set(value)):
            raise ValueError("ordered_ids must not contain duplicates")
        return list(value)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def migrate() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS rankings(
              ranking_id TEXT PRIMARY KEY,
              dimension TEXT NOT NULL,
              scope_type TEXT NOT NULL,
              scope_key TEXT NOT NULL,
              document_json TEXT NOT NULL,
              revision TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(dimension, scope_type, scope_key)
            );
            CREATE TABLE IF NOT EXISTS ranking_events(
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              ranking_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              previous_revision TEXT,
              new_revision TEXT NOT NULL,
              occurred_at TEXT NOT NULL
            );
            """
        )


def material(write: RankingWrite) -> dict[str, Any]:
    value = write.model_dump(exclude_none=True)
    return value


def document(row: sqlite3.Row) -> dict[str, Any]:
    value = json.loads(row["document_json"])
    return {
        "contract_version": RECORD_CONTRACT,
        "ranking_id": row["ranking_id"],
        **value,
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def validate(contract: str, value: dict[str, Any]) -> None:
    try:
        validate_contract(contract, value)
    except ContractValidationError as error:
        raise HTTPException(
            500,
            detail={
                "code": "canonical_contract_failure",
                "contract": contract,
                "issues": [issue.message for issue in error.issues],
            },
        ) from error


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        count = db.execute("SELECT COUNT(*) FROM rankings").fetchone()[0]
    return {"ok": True, "service": "ranking-policy-service", "ranking_count": count}


@app.post("/rankings")
def create_ranking(write: RankingWrite) -> dict[str, Any]:
    value = material(write)
    scope_key = value.get("scope_id", "")
    new_revision = revision(value)
    timestamp = now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM rankings WHERE dimension=? AND scope_type=? AND scope_key=?",
            (write.dimension, write.scope_type, scope_key),
        ).fetchone()
        if row is not None:
            current = document(row)
            if row["revision"] == new_revision:
                return {"ok": True, "changed": False, "ranking": current}
            raise HTTPException(
                409,
                detail={
                    "code": "ranking_scope_conflict",
                    "ranking_id": row["ranking_id"],
                    "current_revision": row["revision"],
                },
            )
        ranking_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO rankings VALUES(?,?,?,?,?,?,?,?)",
            (
                ranking_id, write.dimension, write.scope_type, scope_key,
                canonical(value), new_revision, timestamp, timestamp,
            ),
        )
        db.execute(
            "INSERT INTO ranking_events(ranking_id,event_type,new_revision,occurred_at) VALUES(?,?,?,?)",
            (ranking_id, "created", new_revision, timestamp),
        )
        result = {
            "contract_version": RECORD_CONTRACT, "ranking_id": ranking_id,
            **value, "revision": new_revision,
            "created_at": timestamp, "updated_at": timestamp,
        }
    return {"ok": True, "changed": True, "ranking": result}


@app.get("/rankings")
def list_rankings(
    dimension: str | None = None,
    active: bool | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    clauses, values = [], []
    if dimension is not None:
        clauses.append("dimension=?")
        values.append(dimension)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as db:
        rows = db.execute(
            f"SELECT * FROM rankings{where} ORDER BY dimension,scope_type,scope_key LIMIT ?",
            (*values, limit),
        ).fetchall()
    items = [document(row) for row in rows]
    if active is not None:
        items = [item for item in items if item["active"] is active]
    return {"rankings": items, "count": len(items)}


@app.get("/rankings/{ranking_id}")
def get_ranking(ranking_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM rankings WHERE ranking_id=?", (ranking_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, detail="ranking not found")
    return {"ranking": document(row)}


@app.patch("/rankings/{ranking_id}")
def patch_ranking(ranking_id: str, patch: RankingPatch) -> dict[str, Any]:
    updates = patch.model_dump(exclude_unset=True)
    expected = updates.pop("expected_revision")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM rankings WHERE ranking_id=?", (ranking_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, detail="ranking not found")
        if row["revision"] != expected:
            raise HTTPException(
                409,
                detail={"code": "revision_conflict", "current_revision": row["revision"]},
            )
        value = json.loads(row["document_json"])
        value.update(updates)
        new_revision = revision(value)
        if new_revision == row["revision"]:
            return {"ok": True, "changed": False, "ranking": document(row)}
        timestamp = now()
        db.execute(
            "UPDATE rankings SET document_json=?,revision=?,updated_at=? WHERE ranking_id=?",
            (canonical(value), new_revision, timestamp, ranking_id),
        )
        db.execute(
            "INSERT INTO ranking_events(ranking_id,event_type,previous_revision,new_revision,occurred_at) VALUES(?,?,?,?,?)",
            (ranking_id, "updated", row["revision"], new_revision, timestamp),
        )
        updated = db.execute(
            "SELECT * FROM rankings WHERE ranking_id=?", (ranking_id,)
        ).fetchone()
    result = document(updated)
    return {"ok": True, "changed": True, "ranking": result}


@app.post("/effective")
def effective(request: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_contract(REQUEST_CONTRACT, request)
    except ContractValidationError as error:
        raise HTTPException(
            422,
            detail={"code": "invalid_contract", "issues": [i.message for i in error.issues]},
        ) from error
    dimension = request["dimension"]
    chosen = None
    with connect() as db:
        for scope in SCOPES:
            scope_id = "" if scope == "global" else request.get(f"{scope}_id")
            if scope != "global" and scope_id is None:
                continue
            row = db.execute(
                """
                SELECT * FROM rankings
                WHERE dimension=? AND scope_type=? AND scope_key=?
                """,
                (dimension, scope, scope_id),
            ).fetchone()
            if row is not None and json.loads(row["document_json"])["active"]:
                chosen = document(row)
                break
    result: dict[str, Any] = {
        "contract_version": RESULT_CONTRACT,
        "dimension": dimension,
        "status": "UNDEFINED",
        "ordered_ids": [],
        "resolved_at": now(),
    }
    if chosen:
        result.update(
            status="DEFINED",
            ordered_ids=chosen["ordered_ids"],
            source_scope=chosen["scope_type"],
            ranking_ref={
                "authority": "ranking-policy-authority",
                "reference_id": chosen["ranking_id"],
                "revision": chosen["revision"],
            },
        )
        if chosen["scope_type"] != "global":
            result["source_scope_id"] = chosen["scope_id"]
    validate(RESULT_CONTRACT, result)
    return result


@app.get("/events")
def events(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM ranking_events ORDER BY event_id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"events": [dict(row) for row in rows]}


migrate()
