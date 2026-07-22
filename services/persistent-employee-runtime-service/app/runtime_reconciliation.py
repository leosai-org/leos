from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter()
CONTRACT_VERSION = "leos.runtime-reconciliation.v3.1"
SCHEDULER_URL = os.getenv(
    "LEOS_EXECUTION_SCHEDULER_URL",
    "http://execution-scheduler-service:8000",
).rstrip("/")

REQUIRED_COLUMNS = {
    "assignment_id",
    "job_id",
    "state",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def candidate_paths() -> list[Path]:
    values: list[Path] = []

    try:
        from app import main as runtime_main

        for name, value in vars(runtime_main).items():
            upper = name.upper()

            if any(
                token in upper
                for token in (
                    "DB",
                    "DATABASE",
                    "SQLITE",
                    "DATA",
                )
            ):
                if isinstance(value, Path):
                    values.append(value)
                elif isinstance(value, str):
                    text = value.strip()

                    if text.startswith("sqlite:///"):
                        text = text[10:]
                    elif text.startswith("sqlite://"):
                        text = text[9:]

                    if text and text != ":memory:":
                        values.append(Path(text))

            if isinstance(value, sqlite3.Connection):
                try:
                    for row in value.execute(
                        "PRAGMA database_list"
                    ).fetchall():
                        if row[2]:
                            values.append(
                                Path(str(row[2]))
                            )
                except Exception:
                    pass
    except Exception:
        pass

    for name, value in os.environ.items():
        if not any(
            token in name.upper()
            for token in (
                "DB",
                "DATABASE",
                "SQLITE",
                "DATA",
            )
        ):
            continue

        text = value.strip()

        if text.startswith("sqlite:///"):
            text = text[10:]
        elif text.startswith("sqlite://"):
            text = text[9:]

        if text and text != ":memory:":
            values.append(Path(text))

    for base in (
        Path("/data"),
        Path("/app"),
        Path("/tmp"),
    ):
        if not base.exists():
            continue

        for current_root, directories, files in os.walk(base):
            relative = Path(current_root).relative_to(base)

            if len(relative.parts) >= 6:
                directories[:] = []

            for filename in files:
                if filename.lower().endswith(
                    (
                        ".db",
                        ".sqlite",
                        ".sqlite3",
                    )
                ):
                    values.append(
                        Path(current_root) / filename
                    )

    values.extend(
        [
            Path(
                "/data/persistent-employee-runtime/"
                "persistent-employee-runtime.db"
            ),
            Path(
                "/data/persistent-employee-runtime/"
                "employees.db"
            ),
            Path(
                "/data/persistent-employee-runtime/"
                "runtime.db"
            ),
            Path(
                "/data/persistent-employee-runtime.db"
            ),
            Path("/data/employees.db"),
            Path("/data/runtime.db"),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()

    for value in values:
        key = str(value)

        if key not in seen:
            seen.add(key)
            unique.append(value)

    return unique


def inspect_database(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "tables": [],
        "assignment_tables": [],
        "error": None,
    }

    if not path.exists() or not path.is_file():
        return result

    try:
        connection = sqlite3.connect(
            path,
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(
            "PRAGMA busy_timeout=10000"
        )

        table_rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()

        for row in table_rows:
            table_name = row["name"]
            columns = sorted(
                column["name"]
                for column in connection.execute(
                    f"PRAGMA table_info({q(table_name)})"
                ).fetchall()
            )

            record = {
                "table": table_name,
                "columns": columns,
            }
            result["tables"].append(record)

            if REQUIRED_COLUMNS.issubset(
                set(columns)
            ):
                result[
                    "assignment_tables"
                ].append(record)

        connection.close()

    except Exception as exc:
        result["error"] = {
            "type": exc.__class__.__name__,
            "message": str(exc) or repr(exc),
        }

    return result


def resolve_store() -> dict[str, Any]:
    inspections: list[dict[str, Any]] = []

    preferred = {
        "assignments": 0,
        "employee_assignments": 1,
        "runtime_assignments": 2,
        "assignment_records": 3,
    }

    for path in candidate_paths():
        inspection = inspect_database(path)
        inspections.append(inspection)
        matches = inspection[
            "assignment_tables"
        ]

        if not matches:
            continue

        chosen = sorted(
            matches,
            key=lambda item: (
                preferred.get(
                    item["table"].lower(),
                    100,
                ),
                item["table"],
            ),
        )[0]

        return {
            "database": path,
            "table": chosen["table"],
            "columns": set(
                chosen["columns"]
            ),
            "inspection": inspection,
            "inspections": inspections,
        }

    raise RuntimeError(
        "No SQLite table containing "
        "assignment_id, job_id, and state "
        "was found."
    )


def connect_store() -> tuple[
    sqlite3.Connection,
    str,
    set[str],
]:
    store = resolve_store()
    connection = sqlite3.connect(
        store["database"],
        timeout=10,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA busy_timeout=10000"
    )

    return (
        connection,
        store["table"],
        store["columns"],
    )


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers: dict[str, str] = {}

    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = (
            "application/json"
        )

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            raw = response.read().decode()

            try:
                body = (
                    json.loads(raw)
                    if raw
                    else {}
                )
            except Exception:
                body = {"raw": raw}

            return response.status, body

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()

        try:
            body = (
                json.loads(raw)
                if raw
                else {}
            )
        except Exception:
            body = {"raw": raw}

        return exc.code, body

    except Exception as exc:
        return 0, {
            "ok": False,
            "connection_error": (
                str(exc)
                or exc.__class__.__name__
            ),
        }


def unwrap_job(
    body: dict[str, Any],
) -> dict[str, Any]:
    job = body.get("job")

    return (
        job
        if isinstance(job, dict)
        else body
    )


def age_seconds(
    value: str | None,
) -> float | None:
    if not value:
        return None

    try:
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except Exception:
        return None

    return max(
        0.0,
        (
            datetime.now(timezone.utc)
            - timestamp
        ).total_seconds(),
    )


def order_clause(
    columns: set[str],
) -> str:
    available = [
        column
        for column in (
            "updated_at",
            "completed_at",
            "started_at",
            "assigned_at",
            "created_at",
        )
        if column in columns
    ]

    if not available:
        return ""

    return (
        " ORDER BY COALESCE("
        + ", ".join(
            q(column)
            for column in available
        )
        + ") DESC"
    )


class ReconcileRequest(BaseModel):
    job_id: str
    requested_by: str
    watchdog_seconds: int = Field(
        default=30,
        ge=5,
        le=240,
    )


@router.get(
    "/assignments/reconcile/health"
)
def reconcile_health() -> dict[str, Any]:
    try:
        store = resolve_store()

        return {
            "ok": True,
            "extension": (
                "phase50.1.1-schema-aware-store"
            ),
            "contract_version": (
                CONTRACT_VERSION
            ),
            "database": str(
                store["database"]
            ),
            "assignment_table": (
                store["table"]
            ),
            "assignment_columns": sorted(
                store["columns"]
            ),
            "inspection": (
                store["inspection"]
            ),
            "candidate_count": len(
                candidate_paths()
            ),
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "extension": (
                "phase50.1.1-schema-aware-store"
            ),
            "contract_version": (
                CONTRACT_VERSION
            ),
            "database": None,
            "assignment_table": None,
            "inspections": [
                inspect_database(path)
                for path in candidate_paths()
            ],
            "error_type": (
                exc.__class__.__name__
            ),
            "error": (
                str(exc)
                or repr(exc)
            ),
        }


@router.post(
    "/assignments/reconcile"
)
def reconcile_assignment(
    request: ReconcileRequest,
) -> dict[str, Any]:
    try:
        store = resolve_store()
        database = store["database"]
        table = store["table"]
        table_columns = store["columns"]
        quoted_table = q(table)

        scheduler_status, scheduler_body = (
            request_json(
                "GET",
                (
                    f"{SCHEDULER_URL}/jobs/"
                    f"{request.job_id}"
                ),
            )
        )

        if scheduler_status != 200:
            return {
                "ok": False,
                "action": (
                    "scheduler-job-unavailable"
                ),
                "job_id": request.job_id,
                "scheduler_status": (
                    scheduler_status
                ),
                "scheduler_response": (
                    scheduler_body
                ),
                "database": str(database),
                "assignment_table": table,
                "contract_version": (
                    CONTRACT_VERSION
                ),
            }

        job = unwrap_job(
            scheduler_body
        )

        connection, _, _ = connect_store()
        assignment = connection.execute(
            (
                f"SELECT * FROM {quoted_table} "
                "WHERE job_id=?"
                + order_clause(
                    table_columns
                )
                + " LIMIT 1"
            ),
            (request.job_id,),
        ).fetchone()
        connection.close()

        if assignment is None:
            return {
                "ok": True,
                "action": (
                    "assignment-not-created-yet"
                ),
                "job_id": request.job_id,
                "scheduler_state": (
                    job.get("state")
                ),
                "scheduler_lease_id": (
                    job.get("lease_id")
                ),
                "database": str(database),
                "assignment_table": table,
                "contract_version": (
                    CONTRACT_VERSION
                ),
            }

        assignment = dict(assignment)
        assignment_state = str(
            assignment.get("state", "")
        ).lower()
        scheduler_state = str(
            job.get("state", "")
        ).lower()

        scheduler_lease = job.get(
            "lease_id"
        )
        assignment_lease = (
            assignment.get("lease_id")
        )
        running_age = age_seconds(
            assignment.get("started_at")
            or assignment.get(
                "updated_at"
            )
        )

        common = {
            "assignment_id": (
                assignment[
                    "assignment_id"
                ]
            ),
            "job_id": request.job_id,
            "database": str(database),
            "assignment_table": table,
            "contract_version": (
                CONTRACT_VERSION
            ),
        }

        if assignment_state in {
            "complete",
            "completed",
        }:
            return {
                "ok": True,
                "action": (
                    "assignment-already-complete"
                ),
                "assignment_state": (
                    assignment_state
                ),
                "scheduler_state": (
                    scheduler_state
                ),
                "lease_match": (
                    not scheduler_lease
                    or scheduler_lease
                    == assignment_lease
                ),
                **common,
            }

        if scheduler_state in {
            "complete",
            "completed",
        }:
            sets = [
                f"{q('state')}=?"
            ]
            values: list[Any] = [
                "complete"
            ]

            if (
                "result_json"
                in table_columns
            ):
                sets.append(
                    f"{q('result_json')}=?"
                )
                values.append(
                    json.dumps(
                        job.get("result")
                        if isinstance(
                            job.get("result"),
                            dict,
                        )
                        else {}
                    )
                )

            if "error" in table_columns:
                sets.append(
                    f"{q('error')}=NULL"
                )

            if (
                "completed_at"
                in table_columns
            ):
                sets.append(
                    f"{q('completed_at')}="
                    f"COALESCE("
                    f"{q('completed_at')}, ?)"
                )
                values.append(now())

            if (
                "updated_at"
                in table_columns
            ):
                sets.append(
                    f"{q('updated_at')}=?"
                )
                values.append(now())

            values.append(
                assignment[
                    "assignment_id"
                ]
            )

            connection, _, _ = (
                connect_store()
            )
            connection.execute(
                (
                    f"UPDATE {quoted_table} "
                    f"SET {', '.join(sets)} "
                    "WHERE assignment_id=?"
                ),
                values,
            )
            connection.commit()
            connection.close()

            return {
                "ok": True,
                "action": (
                    "assignment-completed-"
                    "from-scheduler"
                ),
                **common,
            }

        if scheduler_state in {
            "failed",
            "cancelled",
            "canceled",
        }:
            sets = [
                f"{q('state')}=?"
            ]
            values = [
                scheduler_state
            ]

            if "error" in table_columns:
                sets.append(
                    f"{q('error')}=?"
                )
                values.append(
                    job.get("error")
                )

            if (
                "completed_at"
                in table_columns
            ):
                sets.append(
                    f"{q('completed_at')}="
                    f"COALESCE("
                    f"{q('completed_at')}, ?)"
                )
                values.append(now())

            if (
                "updated_at"
                in table_columns
            ):
                sets.append(
                    f"{q('updated_at')}=?"
                )
                values.append(now())

            values.append(
                assignment[
                    "assignment_id"
                ]
            )

            connection, _, _ = (
                connect_store()
            )
            connection.execute(
                (
                    f"UPDATE {quoted_table} "
                    f"SET {', '.join(sets)} "
                    "WHERE assignment_id=?"
                ),
                values,
            )
            connection.commit()
            connection.close()

            return {
                "ok": True,
                "action": (
                    "assignment-terminal-"
                    "from-scheduler"
                ),
                "state": scheduler_state,
                **common,
            }

        lease_mismatch = bool(
            scheduler_lease
            and assignment_lease
            and scheduler_lease
            != assignment_lease
        )

        stale_running = bool(
            assignment_state == "running"
            and running_age is not None
            and running_age
            >= request.watchdog_seconds
        )

        should_restart = bool(
            scheduler_state
            in {
                "leased",
                "running",
            }
            and (
                lease_mismatch
                or stale_running
            )
        )

        if not should_restart:
            return {
                "ok": True,
                "action": (
                    "no-recovery-required"
                ),
                "assignment_state": (
                    assignment_state
                ),
                "scheduler_state": (
                    scheduler_state
                ),
                "assignment_lease_id": (
                    assignment_lease
                ),
                "scheduler_lease_id": (
                    scheduler_lease
                ),
                "lease_mismatch": (
                    lease_mismatch
                ),
                "stale_running": (
                    stale_running
                ),
                "running_age_seconds": (
                    running_age
                ),
                **common,
            }

        sets = [
            f"{q('state')}=?"
        ]
        values = [
            "assigned"
        ]

        if "lease_id" in table_columns:
            sets.insert(
                0,
                f"{q('lease_id')}=?",
            )
            values.insert(
                0,
                scheduler_lease,
            )

        for column in (
            "result_json",
            "error",
            "started_at",
            "completed_at",
        ):
            if column in table_columns:
                sets.append(
                    f"{q(column)}=NULL"
                )

        if (
            "updated_at"
            in table_columns
        ):
            sets.append(
                f"{q('updated_at')}=?"
            )
            values.append(now())

        values.append(
            assignment[
                "assignment_id"
            ]
        )

        connection, _, _ = (
            connect_store()
        )
        connection.execute(
            (
                f"UPDATE {quoted_table} "
                f"SET {', '.join(sets)} "
                "WHERE assignment_id=?"
            ),
            values,
        )
        connection.commit()
        connection.close()

        start_status, start_body = (
            request_json(
                "POST",
                (
                    "http://127.0.0.1:8000"
                    f"/assignments/"
                    f"{assignment['assignment_id']}"
                    "/start"
                ),
            )
        )

        start_ok = (
            start_status
            in {
                200,
                201,
                202,
                204,
                409,
            }
        )

        return {
            "ok": start_ok,
            "action": (
                "assignment-restarted"
                if start_ok
                else (
                    "assignment-restart-failed"
                )
            ),
            "previous_assignment_state": (
                assignment_state
            ),
            "previous_assignment_lease_id": (
                assignment_lease
            ),
            "scheduler_lease_id": (
                scheduler_lease
            ),
            "lease_mismatch": (
                lease_mismatch
            ),
            "stale_running": (
                stale_running
            ),
            "running_age_seconds": (
                running_age
            ),
            "start_status": start_status,
            "start_response": start_body,
            **common,
        }

    except Exception as exc:
        return {
            "ok": False,
            "action": (
                "reconciliation-exception"
            ),
            "job_id": request.job_id,
            "error_type": (
                exc.__class__.__name__
            ),
            "error": (
                str(exc)
                or repr(exc)
            ),
            "inspections": [
                inspect_database(path)
                for path
                in candidate_paths()
            ],
            "contract_version": (
                CONTRACT_VERSION
            ),
        }
