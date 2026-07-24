from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(
    prefix="/execution-contract",
    tags=["execution-contract"],
)

CONTRACT_VERSION = "leos.execution.v1"

DATA_DIR = Path(
    os.getenv(
        "CAPABILITY_MANAGER_DATA_DIR",
        "/data/capability-manager",
    )
)

DB_PATH = DATA_DIR / "capability-manager.db"


def now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    db = sqlite3.connect(
        DB_PATH
    )

    db.row_factory = sqlite3.Row
    db.execute(
        "PRAGMA journal_mode=WAL"
    )

    return db


def migrate() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS provider_payload_adapters (
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

            CREATE INDEX IF NOT EXISTS idx_provider_payload_adapter_lookup
                ON provider_payload_adapters (
                    capability_id,
                    provider_id,
                    enabled,
                    priority
                );
            """
        )

        timestamp = now()

        db.execute(
            """
            INSERT INTO provider_payload_adapters (
                adapter_id,
                capability_id,
                provider_id,
                request_shape,
                enabled,
                priority,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (
                'builtin-content-write-flat-input',
                'content.write',
                NULL,
                'flat_input',
                1,
                10,
                ?,
                ?,
                ?
            )
            ON CONFLICT(adapter_id)
            DO UPDATE SET
                capability_id=excluded.capability_id,
                provider_id=excluded.provider_id,
                request_shape=excluded.request_shape,
                enabled=excluded.enabled,
                priority=excluded.priority,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                json.dumps(
                    {
                        "official": True,
                        "maintainer": (
                            "Bad Tech Labs LLC"
                        ),
                        "reason": (
                            "Legacy content.write "
                            "provider accepts a flat "
                            "request body."
                        ),
                    }
                ),
                timestamp,
                timestamp,
            ),
        )


def object_value(
    value: Any,
    key: str,
    default: Any = None,
) -> Any:
    if isinstance(
        value,
        dict,
    ):
        return value.get(
            key,
            default,
        )

    return getattr(
        value,
        key,
        default,
    )


def provider_from_scope(
    scope: dict[str, Any],
) -> Any:
    preferred_names = (
        "provider",
        "selected_provider",
        "provider_record",
        "binding",
        "selected",
    )

    for name in preferred_names:
        if name in scope:
            candidate = scope[
                name
            ]

            if candidate is not None:
                return candidate

    for name, candidate in scope.items():
        if "provider" not in name.lower():
            continue

        if isinstance(
            candidate,
            (
                dict,
                sqlite3.Row,
            ),
        ):
            return candidate

    return None


def provider_identity(
    provider: Any,
) -> dict[str, Any]:
    metadata = object_value(
        provider,
        "metadata",
        None,
    )

    if metadata is None:
        metadata = object_value(
            provider,
            "metadata_json",
            {},
        )

    if isinstance(
        metadata,
        str,
    ):
        try:
            metadata = json.loads(
                metadata
            )
        except Exception:
            metadata = {}

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    return {
        "provider_id": (
            object_value(
                provider,
                "provider_id",
            )
            or object_value(
                provider,
                "id",
            )
        ),
        "provider_type": (
            object_value(
                provider,
                "provider_type",
            )
            or object_value(
                provider,
                "type",
            )
        ),
        "metadata": metadata,
    }


def normalize_execution_envelope(
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(
        payload,
        dict,
    ):
        payload = {
            "input": payload,
        }

    capability_id = (
        payload.get(
            "capability_id"
        )
        or payload.get(
            "capability"
        )
    )

    request_input = payload.get(
        "input",
        {},
    )

    if not isinstance(
        request_input,
        dict,
    ):
        request_input = {
            "value": request_input,
        }

    requester = payload.get(
        "requester",
        {},
    )

    if not isinstance(
        requester,
        dict,
    ):
        requester = {
            "id": str(
                requester
            ),
        }

    context = payload.get(
        "context",
        {},
    )

    if not isinstance(
        context,
        dict,
    ):
        context = {}

    policy = payload.get(
        "policy",
        {},
    )

    if not isinstance(
        policy,
        dict,
    ):
        policy = {}

    trace = payload.get(
        "trace",
        {},
    )

    if not isinstance(
        trace,
        dict,
    ):
        trace = {}

    return {
        "contract_version": (
            payload.get(
                "contract_version"
            )
            or CONTRACT_VERSION
        ),
        "execution_id": (
            payload.get(
                "execution_id"
            )
            or str(
                uuid.uuid4()
            )
        ),
        "capability_id": (
            capability_id
        ),
        "input": request_input,
        "requester": requester,
        "context": context,
        "policy": policy,
        "trace": trace,
    }


def adapter_rows(
    *,
    capability_id: str | None,
    provider_id: str | None,
) -> list[sqlite3.Row]:
    migrate()

    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM provider_payload_adapters
            WHERE
                enabled=1
                AND (
                    capability_id IS NULL
                    OR capability_id=?
                )
                AND (
                    provider_id IS NULL
                    OR provider_id=?
                )
            ORDER BY
                CASE
                    WHEN provider_id IS NOT NULL
                    THEN 0
                    ELSE 1
                END,
                priority ASC,
                created_at ASC
            """,
            (
                capability_id,
                provider_id,
            ),
        ).fetchall()

    return rows


def select_request_shape(
    *,
    envelope: dict[str, Any],
    provider: Any,
) -> tuple[str, dict[str, Any]]:
    identity = provider_identity(
        provider
    )

    provider_id = identity[
        "provider_id"
    ]

    metadata = identity[
        "metadata"
    ]

    explicit_shape = (
        metadata.get(
            "request_shape"
        )
        or metadata.get(
            "payload_shape"
        )
        or metadata.get(
            "execution_request_shape"
        )
    )

    if explicit_shape:
        return (
            str(
                explicit_shape
            ),
            {
                "source": (
                    "provider_metadata"
                ),
                "provider_id": (
                    provider_id
                ),
            },
        )

    rows = adapter_rows(
        capability_id=envelope.get(
            "capability_id"
        ),
        provider_id=provider_id,
    )

    if rows:
        row = rows[0]

        return (
            row[
                "request_shape"
            ],
            {
                "source": (
                    "adapter_registry"
                ),
                "adapter_id": (
                    row[
                        "adapter_id"
                    ]
                ),
                "provider_id": (
                    provider_id
                ),
            },
        )

    return (
        "legacy_wrapped",
        {
            "source": "default",
            "provider_id": (
                provider_id
            ),
        },
    )


def shape_provider_payload(
    *,
    shape: str,
    envelope: dict[str, Any],
    original_payload: dict[str, Any],
) -> dict[str, Any]:
    if shape in {
        "flat_input",
        "raw_input",
    }:
        return dict(
            envelope[
                "input"
            ]
        )

    if shape in {
        "canonical_envelope",
        "leos_execution_v1",
    }:
        return envelope

    if shape == "legacy_wrapped":
        return {
            "capability": (
                envelope[
                    "capability_id"
                ]
            ),
            "input": (
                envelope[
                    "input"
                ]
            ),
            "requester": (
                envelope[
                    "requester"
                ]
            ),
        }

    if shape == "original":
        return original_payload

    return {
        "capability": (
            envelope[
                "capability_id"
            ]
        ),
        "input": (
            envelope[
                "input"
            ]
        ),
        "requester": (
            envelope[
                "requester"
            ]
        ),
    }


def adapt_provider_payload(
    scope: dict[str, Any],
    payload: Any,
) -> dict[str, Any]:
    original_payload = (
        payload
        if isinstance(
            payload,
            dict,
        )
        else {
            "input": payload,
        }
    )

    envelope = (
        normalize_execution_envelope(
            original_payload
        )
    )

    provider = provider_from_scope(
        scope
    )

    shape, selection = (
        select_request_shape(
            envelope=envelope,
            provider=provider,
        )
    )

    adapted = shape_provider_payload(
        shape=shape,
        envelope=envelope,
        original_payload=(
            original_payload
        ),
    )

    return adapted


class AdapterCreate(BaseModel):
    adapter_id: str
    capability_id: str | None = None
    provider_id: str | None = None
    request_shape: str
    enabled: bool = True
    priority: int = 100
    metadata: dict[str, Any] = {}


@router.get("")
def contract() -> dict[str, Any]:
    return {
        "ok": True,
        "contract_version": (
            CONTRACT_VERSION
        ),
        "required_fields": [
            "contract_version",
            "execution_id",
            "capability_id",
            "input",
            "requester",
            "context",
            "policy",
            "trace",
        ],
        "request_shapes": [
            "legacy_wrapped",
            "flat_input",
            "canonical_envelope",
            "original",
        ],
        "default_request_shape": (
            "legacy_wrapped"
        ),
    }


@router.get("/adapters")
def list_adapters() -> dict[str, Any]:
    migrate()

    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM provider_payload_adapters
            ORDER BY priority, created_at
            """
        ).fetchall()

    return {
        "ok": True,
        "adapter_count": len(
            rows
        ),
        "adapters": [
            {
                **dict(row),
                "enabled": bool(
                    row[
                        "enabled"
                    ]
                ),
                "metadata": (
                    json.loads(
                        row[
                            "metadata_json"
                        ]
                    )
                    if row[
                        "metadata_json"
                    ]
                    else {}
                ),
            }
            for row in rows
        ],
    }


@router.post("/adapters")
def create_adapter(
    request: AdapterCreate,
) -> dict[str, Any]:
    migrate()

    timestamp = now()

    with connect() as db:
        db.execute(
            """
            INSERT INTO provider_payload_adapters (
                adapter_id,
                capability_id,
                provider_id,
                request_shape,
                enabled,
                priority,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(adapter_id)
            DO UPDATE SET
                capability_id=excluded.capability_id,
                provider_id=excluded.provider_id,
                request_shape=excluded.request_shape,
                enabled=excluded.enabled,
                priority=excluded.priority,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                request.adapter_id,
                request.capability_id,
                request.provider_id,
                request.request_shape,
                int(
                    request.enabled
                ),
                request.priority,
                json.dumps(
                    request.metadata
                ),
                timestamp,
                timestamp,
            ),
        )

    return {
        "ok": True,
        "adapter_id": (
            request.adapter_id
        ),
        "request_shape": (
            request.request_shape
        ),
    }


migrate()
