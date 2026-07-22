from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


SERVICE_NAME = "persistent-employee-runtime-service"
SERVICE_VERSION = "0.2.0"
EMPLOYEE_OS_VERSION = "leos.employee.v1"

DATA_DIR = Path(
    os.getenv(
        "PERSISTENT_EMPLOYEE_RUNTIME_DATA_DIR",
        "/data/persistent-employee-runtime",
    )
)
DB_PATH = DATA_DIR / "persistent-employee-runtime.db"

KERNEL_URL = os.getenv(
    "LEOS_KERNEL_URL",
    "http://leos-kernel-service:8000",
).rstrip("/")

SCHEDULER_URL = os.getenv(
    "EXECUTION_SCHEDULER_URL",
    "http://execution-scheduler-service:8000",
).rstrip("/")

POLL_INTERVAL_SECONDS = float(
    os.getenv(
        "EMPLOYEE_RUNTIME_POLL_INTERVAL_SECONDS",
        "5",
    )
)

AUTO_POLL_SCHEDULER = os.getenv(
    "EMPLOYEE_RUNTIME_AUTO_POLL_SCHEDULER",
    "true",
).lower() == "true"

_loop_task: Optional[asyncio.Task] = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    return db


def migrate() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                employee_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT,
                manager_employee_id TEXT,
                status TEXT NOT NULL DEFAULT 'offline',
                runtime_state TEXT NOT NULL DEFAULT 'idle',
                model_id TEXT,
                profile_json TEXT NOT NULL DEFAULT '{}',
                permissions_json TEXT NOT NULL DEFAULT '{}',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                current_job_id TEXT,
                current_workflow_id TEXT,
                current_step_id TEXT,
                last_heartbeat_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_employee_status
                ON employees(status, runtime_state);

            CREATE INDEX IF NOT EXISTS idx_employee_department
                ON employees(department);

            CREATE TABLE IF NOT EXISTS employee_messages (
                message_id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                message_type TEXT NOT NULL,
                subject TEXT,
                body_json TEXT NOT NULL DEFAULT '{}',
                related_employee_id TEXT,
                mission_id TEXT,
                workflow_id TEXT,
                job_id TEXT,
                state TEXT NOT NULL DEFAULT 'unread',
                created_at TEXT NOT NULL,
                read_at TEXT,
                acknowledged_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_employee_message_inbox
                ON employee_messages(employee_id, direction, state, created_at);

            CREATE TABLE IF NOT EXISTS employee_memory (
                memory_id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'working',
                memory_key TEXT,
                content_json TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0.5,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_employee_memory_lookup
                ON employee_memory(employee_id, namespace, memory_key);

            CREATE TABLE IF NOT EXISTS employee_assignments (
                assignment_id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                workflow_id TEXT,
                step_id TEXT,
                capability_id TEXT,
                lease_id TEXT,
                state TEXT NOT NULL DEFAULT 'assigned',
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error TEXT,
                assigned_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_assignment_job
                ON employee_assignments(job_id);

            CREATE TABLE IF NOT EXISTS employee_events (
                event_id TEXT PRIMARY KEY,
                employee_id TEXT,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )

        assignment_columns = {
            "resource_reservation_id": "TEXT",
            "resource_node_id": "TEXT",
            "resource_gpu_uuid": "TEXT",
            "resource_profile_name": "TEXT",
            "resource_decision_json": "TEXT NOT NULL DEFAULT '{}'",
            "resource_state": "TEXT",
        }
        existing_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(employee_assignments)"
            ).fetchall()
        }
        for column, definition in assignment_columns.items():
            if column not in existing_columns:
                db.execute(
                    "ALTER TABLE employee_assignments "
                    f"ADD COLUMN {column} {definition}"
                )


def parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default

    return default


async def publish_kernel_event(
    event_type: str,
    *,
    employee_id: Optional[str] = None,
    severity: str = "info",
    details: Optional[dict[str, Any]] = None,
) -> None:
    payload = {
        "event_type": event_type,
        "subsystem_id": "persistent-employee-runtime",
        "severity": severity,
        "details": {
            **(details or {}),
            **(
                {"employee_id": employee_id}
                if employee_id
                else {}
            ),
        },
    }

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                f"{KERNEL_URL}/events/publish",
                json=payload,
            )
    except Exception:
        pass


def emit_local(
    event_type: str,
    *,
    employee_id: Optional[str] = None,
    severity: str = "info",
    details: Optional[dict[str, Any]] = None,
) -> str:
    event_id = str(uuid.uuid4())

    with connect() as db:
        db.execute(
            """
            INSERT INTO employee_events (
                event_id,
                employee_id,
                event_type,
                severity,
                details_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                employee_id,
                event_type,
                severity,
                json.dumps(details or {}),
                now(),
            ),
        )

    return event_id


class EmployeeCreate(BaseModel):
    employee_id: str
    name: str
    role: str
    department: Optional[str] = None
    manager_employee_id: Optional[str] = None
    status: str = "online"
    runtime_state: str = "idle"
    model_id: Optional[str] = None
    profile: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmployeeHeartbeat(BaseModel):
    status: str = "online"
    runtime_state: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCreate(BaseModel):
    direction: str = "inbox"
    message_type: str = "task"
    subject: Optional[str] = None
    body: dict[str, Any] = Field(default_factory=dict)
    related_employee_id: Optional[str] = None
    mission_id: Optional[str] = None
    workflow_id: Optional[str] = None
    job_id: Optional[str] = None


class MemoryCreate(BaseModel):
    namespace: str = "working"
    memory_key: Optional[str] = None
    content: dict[str, Any]
    importance: float = 0.5
    expires_at: Optional[str] = None


class AssignmentStateUpdate(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


migrate()

app = FastAPI(
    title="LEOS Persistent Employee Runtime",
    version=SERVICE_VERSION,
)


def employee_or_404(
    employee_id: str,
) -> sqlite3.Row:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM employees
            WHERE employee_id=?
            """,
            (employee_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found.",
        )

    return row


def employee_to_dict(
    row: sqlite3.Row,
) -> dict[str, Any]:
    item = dict(row)

    item["profile"] = parse_json(
        item.pop("profile_json"),
        {},
    )

    item["permissions"] = parse_json(
        item.pop("permissions_json"),
        {},
    )

    item["capabilities"] = parse_json(
        item.pop("capabilities_json"),
        [],
    )

    item["metadata"] = parse_json(
        item.pop("metadata_json"),
        {},
    )

    return item


async def register_with_kernel() -> None:
    payload = {
        "subsystem_id": "persistent-employee-runtime",
        "name": "Persistent Employee Runtime",
        "category": "employee",
        "base_url": (
            "http://persistent-employee-runtime-service:8000"
        ),
        "health_path": "/health",
        "required": True,
        "enabled": True,
        "priority": 35,
        "metadata": {
            "service_version": SERVICE_VERSION,
            "employee_os_version": EMPLOYEE_OS_VERSION,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{KERNEL_URL}/subsystems",
                json=payload,
            )
    except Exception:
        pass


async def register_scheduler_worker() -> None:
    payload = {
        "worker_id": "persistent-employee-runtime",
        "name": "LEOS Persistent Employee Runtime",
        "worker_type": "employee-runtime",
        "base_url": (
            "http://persistent-employee-runtime-service:8000"
        ),
        "status": "online",
        "cpu_total": 4,
        "ram_mb_total": 8192,
        "gpu_count": 0,
        "vram_mb_total": 0,
        "max_concurrent_jobs": 16,
        "labels": {
            "runtime": "persistent-employee",
            "platform": "leos",
        },
        "metadata": {
            "service_version": SERVICE_VERSION,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{SCHEDULER_URL}/workers",
                json=payload,
            )
    except Exception:
        pass


async def import_scheduler_assignments() -> dict[str, Any]:
    imported = 0
    skipped = 0

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{SCHEDULER_URL}/jobs?limit=500"
            )

        if response.status_code >= 400:
            return {
                "ok": False,
                "imported": 0,
                "skipped": 0,
                "error": response.text,
            }

        body = response.json()
        jobs = body.get("jobs", [])

    except Exception as exc:
        return {
            "ok": False,
            "imported": 0,
            "skipped": 0,
            "error": str(exc),
        }

    with connect() as db:
        for job in jobs:
            employee_id = job.get("employee_id")

            if (
                not employee_id
                or job.get("state")
                not in {"leased", "running"}
            ):
                skipped += 1
                continue

            employee = db.execute(
                """
                SELECT employee_id
                FROM employees
                WHERE employee_id=?
                """,
                (employee_id,),
            ).fetchone()

            if employee is None:
                skipped += 1
                continue

            existing = db.execute(
                """
                SELECT assignment_id
                FROM employee_assignments
                WHERE job_id=?
                """,
                (job["job_id"],),
            ).fetchone()

            if existing is not None:
                skipped += 1
                continue

            assignment_id = str(uuid.uuid4())

            db.execute(
                """
                INSERT INTO employee_assignments (
                    assignment_id,
                    employee_id,
                    job_id,
                    workflow_id,
                    step_id,
                    capability_id,
                    lease_id,
                    state,
                    payload_json,
                    result_json,
                    error,
                    assigned_at,
                    started_at,
                    completed_at,
                    updated_at,
                    resource_reservation_id,
                    resource_node_id,
                    resource_gpu_uuid,
                    resource_profile_name,
                    resource_decision_json,
                    resource_state
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, 'assigned', ?,
                    NULL, NULL, ?, NULL, NULL, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    assignment_id,
                    employee_id,
                    job["job_id"],
                    job.get("workflow_id"),
                    job.get("step_id"),
                    job.get("capability_id"),
                    job.get("lease_id"),
                    json.dumps(
                        job.get("payload", {})
                    ),
                    now(),
                    now(),
                    job.get("resource_reservation_id"),
                    job.get("resource_node_id"),
                    job.get("resource_gpu_uuid"),
                    job.get("resource_profile_name"),
                    json.dumps(
                        job.get("resource_decision", {})
                    ),
                    job.get("resource_state"),
                ),
            )

            db.execute(
                """
                UPDATE employees
                SET
                    runtime_state='assigned',
                    current_job_id=?,
                    current_workflow_id=?,
                    current_step_id=?,
                    updated_at=?
                WHERE employee_id=?
                """,
                (
                    job["job_id"],
                    job.get("workflow_id"),
                    job.get("step_id"),
                    now(),
                    employee_id,
                ),
            )

            message_id = str(uuid.uuid4())

            db.execute(
                """
                INSERT INTO employee_messages (
                    message_id,
                    employee_id,
                    direction,
                    message_type,
                    subject,
                    body_json,
                    related_employee_id,
                    mission_id,
                    workflow_id,
                    job_id,
                    state,
                    created_at,
                    read_at,
                    acknowledged_at
                )
                VALUES (
                    ?, ?, 'inbox', 'assignment', ?,
                    ?, NULL, ?, ?, ?, 'unread', ?,
                    NULL, NULL
                )
                """,
                (
                    message_id,
                    employee_id,
                    (
                        f"New assignment: "
                        f"{job.get('capability_id') or job.get('job_type')}"
                    ),
                    json.dumps(job),
                    job.get("mission_id"),
                    job.get("workflow_id"),
                    job["job_id"],
                    now(),
                ),
            )

            imported += 1

    if imported:
        emit_local(
            "employee_assignments_imported",
            details={
                "imported_count": imported,
            },
        )

        await publish_kernel_event(
            "employee_assignments_imported",
            details={
                "imported_count": imported,
            },
        )

    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
    }


async def poll_loop() -> None:
    while True:
        try:
            if AUTO_POLL_SCHEDULER:
                await import_scheduler_assignments()
        except Exception:
            pass

        await asyncio.sleep(
            POLL_INTERVAL_SECONDS
        )


@app.on_event("startup")
async def startup() -> None:
    global _loop_task

    migrate()
    await register_with_kernel()
    await register_scheduler_worker()

    if AUTO_POLL_SCHEDULER and (
        _loop_task is None
        or _loop_task.done()
    ):
        _loop_task = asyncio.create_task(
            poll_loop()
        )


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        employee_count = db.execute(
            "SELECT COUNT(*) c FROM employees"
        ).fetchone()["c"]

        online_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM employees
            WHERE status='online'
            """
        ).fetchone()["c"]

        active_assignment_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM employee_assignments
            WHERE state IN ('assigned', 'running')
            """
        ).fetchone()["c"]

        unread_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM employee_messages
            WHERE direction='inbox'
              AND state='unread'
            """
        ).fetchone()["c"]

        resource_assignment_counts = {
            row["resource_state"]: row["count"]
            for row in db.execute(
                """
                SELECT resource_state, COUNT(*) AS count
                FROM employee_assignments
                GROUP BY resource_state
                """
            ).fetchall()
        }

    return {
        "ok": True,
        "service": SERVICE_NAME,
        "platform": "LEOS",
        "version": SERVICE_VERSION,
        "employee_os_version": EMPLOYEE_OS_VERSION,
        "employee_count": employee_count,
        "online_count": online_count,
        "active_assignment_count": (
            active_assignment_count
        ),
        "unread_message_count": unread_count,
        "scheduler_url": SCHEDULER_URL,
        "resource_enforcement": {
            "mandatory": True,
            "assignment_state_counts": resource_assignment_counts,
        },
        "kernel_url": KERNEL_URL,
        "auto_poll_scheduler": AUTO_POLL_SCHEDULER,
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "database": str(DB_PATH),
    }


@app.post("/employees")
async def create_employee(
    request: EmployeeCreate,
) -> dict[str, Any]:
    timestamp = now()

    with connect() as db:
        db.execute(
            """
            INSERT INTO employees (
                employee_id,
                name,
                role,
                department,
                manager_employee_id,
                status,
                runtime_state,
                model_id,
                profile_json,
                permissions_json,
                capabilities_json,
                metadata_json,
                current_job_id,
                current_workflow_id,
                current_step_id,
                last_heartbeat_at,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                NULL, NULL, NULL, ?, ?, ?
            )
            ON CONFLICT(employee_id)
            DO UPDATE SET
                name=excluded.name,
                role=excluded.role,
                department=excluded.department,
                manager_employee_id=excluded.manager_employee_id,
                status=excluded.status,
                runtime_state=excluded.runtime_state,
                model_id=excluded.model_id,
                profile_json=excluded.profile_json,
                permissions_json=excluded.permissions_json,
                capabilities_json=excluded.capabilities_json,
                metadata_json=excluded.metadata_json,
                last_heartbeat_at=excluded.last_heartbeat_at,
                updated_at=excluded.updated_at
            """,
            (
                request.employee_id,
                request.name,
                request.role,
                request.department,
                request.manager_employee_id,
                request.status,
                request.runtime_state,
                request.model_id,
                json.dumps(request.profile),
                json.dumps(request.permissions),
                json.dumps(request.capabilities),
                json.dumps(request.metadata),
                timestamp,
                timestamp,
                timestamp,
            ),
        )

    emit_local(
        "employee_registered",
        employee_id=request.employee_id,
        details={
            "name": request.name,
            "role": request.role,
            "department": request.department,
        },
    )

    await publish_kernel_event(
        "employee_registered",
        employee_id=request.employee_id,
        details={
            "name": request.name,
            "role": request.role,
            "department": request.department,
        },
    )

    return {
        "ok": True,
        "employee_id": request.employee_id,
    }


@app.get("/employees")
def list_employees(
    status: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []

    if status:
        clauses.append("status=?")
        params.append(status)

    if department:
        clauses.append("department=?")
        params.append(department)

    where = (
        "WHERE " + " AND ".join(clauses)
        if clauses
        else ""
    )

    params.append(limit)

    with connect() as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM employees
            {where}
            ORDER BY department, role, name
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "ok": True,
        "employee_count": len(rows),
        "employees": [
            employee_to_dict(row)
            for row in rows
        ],
    }


@app.get("/employees/{employee_id}")
def get_employee(
    employee_id: str,
) -> dict[str, Any]:
    row = employee_or_404(employee_id)

    with connect() as db:
        assignments = db.execute(
            """
            SELECT *
            FROM employee_assignments
            WHERE employee_id=?
            ORDER BY assigned_at DESC
            LIMIT 100
            """,
            (employee_id,),
        ).fetchall()

        unread_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM employee_messages
            WHERE employee_id=?
              AND direction='inbox'
              AND state='unread'
            """,
            (employee_id,),
        ).fetchone()["c"]

    return {
        "ok": True,
        "employee": employee_to_dict(row),
        "unread_message_count": unread_count,
        "assignments": [
            {
                **dict(item),
                "payload": parse_json(
                    item["payload_json"],
                    {},
                ),
                "result": parse_json(
                    item["result_json"],
                    {},
                ),
            }
            for item in assignments
        ],
    }


@app.put("/employees/{employee_id}/heartbeat")
def heartbeat(
    employee_id: str,
    request: EmployeeHeartbeat,
) -> dict[str, Any]:
    row = employee_or_404(employee_id)

    metadata = parse_json(
        row["metadata_json"],
        {},
    )
    metadata.update(request.metadata)

    with connect() as db:
        db.execute(
            """
            UPDATE employees
            SET
                status=?,
                runtime_state=?,
                metadata_json=?,
                last_heartbeat_at=?,
                updated_at=?
            WHERE employee_id=?
            """,
            (
                request.status,
                (
                    request.runtime_state
                    or row["runtime_state"]
                ),
                json.dumps(metadata),
                now(),
                now(),
                employee_id,
            ),
        )

    return {
        "ok": True,
        "employee_id": employee_id,
        "status": request.status,
        "runtime_state": (
            request.runtime_state
            or row["runtime_state"]
        ),
    }


@app.post("/employees/{employee_id}/messages")
async def create_message(
    employee_id: str,
    request: MessageCreate,
) -> dict[str, Any]:
    employee_or_404(employee_id)

    if request.direction not in {"inbox", "outbox"}:
        raise HTTPException(
            status_code=422,
            detail="direction must be inbox or outbox.",
        )

    message_id = str(uuid.uuid4())

    with connect() as db:
        db.execute(
            """
            INSERT INTO employee_messages (
                message_id,
                employee_id,
                direction,
                message_type,
                subject,
                body_json,
                related_employee_id,
                mission_id,
                workflow_id,
                job_id,
                state,
                created_at,
                read_at,
                acknowledged_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                NULL, NULL
            )
            """,
            (
                message_id,
                employee_id,
                request.direction,
                request.message_type,
                request.subject,
                json.dumps(request.body),
                request.related_employee_id,
                request.mission_id,
                request.workflow_id,
                request.job_id,
                (
                    "unread"
                    if request.direction == "inbox"
                    else "sent"
                ),
                now(),
            ),
        )

    emit_local(
        "employee_message_created",
        employee_id=employee_id,
        details={
            "message_id": message_id,
            "direction": request.direction,
            "message_type": request.message_type,
        },
    )

    return {
        "ok": True,
        "message_id": message_id,
        "employee_id": employee_id,
        "direction": request.direction,
    }


@app.get("/employees/{employee_id}/messages")
def list_messages(
    employee_id: str,
    direction: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    employee_or_404(employee_id)

    clauses = ["employee_id=?"]
    params: list[Any] = [employee_id]

    if direction:
        clauses.append("direction=?")
        params.append(direction)

    if state:
        clauses.append("state=?")
        params.append(state)

    params.append(limit)

    with connect() as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM employee_messages
            WHERE {" AND ".join(clauses)}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "ok": True,
        "message_count": len(rows),
        "messages": [
            {
                **dict(row),
                "body": parse_json(
                    row["body_json"],
                    {},
                ),
            }
            for row in rows
        ],
    }


@app.post("/messages/{message_id}/acknowledge")
def acknowledge_message(
    message_id: str,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM employee_messages
            WHERE message_id=?
            """,
            (message_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Message not found.",
            )

        db.execute(
            """
            UPDATE employee_messages
            SET
                state='acknowledged',
                read_at=COALESCE(read_at, ?),
                acknowledged_at=?
            WHERE message_id=?
            """,
            (
                now(),
                now(),
                message_id,
            ),
        )

    return {
        "ok": True,
        "message_id": message_id,
        "state": "acknowledged",
    }


@app.post("/employees/{employee_id}/memory")
def create_memory(
    employee_id: str,
    request: MemoryCreate,
) -> dict[str, Any]:
    employee_or_404(employee_id)

    memory_id = str(uuid.uuid4())
    timestamp = now()

    with connect() as db:
        if request.memory_key:
            existing = db.execute(
                """
                SELECT memory_id
                FROM employee_memory
                WHERE employee_id=?
                  AND namespace=?
                  AND memory_key=?
                """,
                (
                    employee_id,
                    request.namespace,
                    request.memory_key,
                ),
            ).fetchone()
        else:
            existing = None

        if existing:
            memory_id = existing["memory_id"]

            db.execute(
                """
                UPDATE employee_memory
                SET
                    content_json=?,
                    importance=?,
                    expires_at=?,
                    updated_at=?
                WHERE memory_id=?
                """,
                (
                    json.dumps(request.content),
                    request.importance,
                    request.expires_at,
                    timestamp,
                    memory_id,
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO employee_memory (
                    memory_id,
                    employee_id,
                    namespace,
                    memory_key,
                    content_json,
                    importance,
                    expires_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    employee_id,
                    request.namespace,
                    request.memory_key,
                    json.dumps(request.content),
                    request.importance,
                    request.expires_at,
                    timestamp,
                    timestamp,
                ),
            )

    return {
        "ok": True,
        "memory_id": memory_id,
        "employee_id": employee_id,
        "namespace": request.namespace,
    }


@app.get("/employees/{employee_id}/memory")
def list_memory(
    employee_id: str,
    namespace: Optional[str] = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    employee_or_404(employee_id)

    clauses = ["employee_id=?"]
    params: list[Any] = [employee_id]

    if namespace:
        clauses.append("namespace=?")
        params.append(namespace)

    params.append(limit)

    with connect() as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM employee_memory
            WHERE {" AND ".join(clauses)}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "ok": True,
        "memory_count": len(rows),
        "memories": [
            {
                **dict(row),
                "content": parse_json(
                    row["content_json"],
                    {},
                ),
            }
            for row in rows
        ],
    }


@app.post("/scheduler/sync")
async def scheduler_sync() -> dict[str, Any]:
    return await import_scheduler_assignments()


@app.get("/assignments")
def list_assignments(
    state: Optional[str] = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    where = ""
    params: list[Any] = []

    if state:
        where = "WHERE state=?"
        params.append(state)

    params.append(limit)

    with connect() as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM employee_assignments
            {where}
            ORDER BY assigned_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "ok": True,
        "assignment_count": len(rows),
        "assignments": [
            {
                **dict(row),
                "payload": parse_json(
                    row["payload_json"],
                    {},
                ),
                "result": parse_json(
                    row["result_json"],
                    {},
                ),
                "resource_decision": parse_json(
                    row["resource_decision_json"],
                    {},
                ),
            }
            for row in rows
        ],
    }


@app.post("/assignments/{assignment_id}/start")
async def start_assignment(
    assignment_id: str,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM employee_assignments
            WHERE assignment_id=?
            """,
            (assignment_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found.",
        )

    if row["state"] != "assigned":
        raise HTTPException(
            status_code=409,
            detail="Assignment is not assigned.",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            scheduler_response = await client.post(
                f"{SCHEDULER_URL}/jobs/{row['job_id']}/running",
                json={
                    "worker_id": (
                        "persistent-employee-runtime"
                    ),
                    "lease_id": row["lease_id"],
                },
            )
        try:
            scheduler_body = scheduler_response.json()
        except Exception:
            scheduler_body = {
                "raw": scheduler_response.text,
            }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Scheduler resource validation could not "
                    "be completed."
                ),
                "error": str(exc),
                "job_id": row["job_id"],
                "resource_reservation_id": row[
                    "resource_reservation_id"
                ],
            },
        ) from exc

    if scheduler_response.status_code >= 400:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Assignment start was blocked because the "
                    "scheduler did not validate an active "
                    "resource reservation."
                ),
                "scheduler_status": scheduler_response.status_code,
                "scheduler_response": scheduler_body,
                "job_id": row["job_id"],
                "resource_reservation_id": row[
                    "resource_reservation_id"
                ],
            },
        )

    with connect() as db:
        current = db.execute(
            """
            SELECT *
            FROM employee_assignments
            WHERE assignment_id=?
            """,
            (assignment_id,),
        ).fetchone()
        if current is None or current["state"] != "assigned":
            raise HTTPException(
                status_code=409,
                detail="Assignment state changed before start.",
            )

        db.execute(
            """
            UPDATE employee_assignments
            SET state='running',
                resource_state='active',
                started_at=?,
                updated_at=?
            WHERE assignment_id=?
            """,
            (
                now(),
                now(),
                assignment_id,
            ),
        )

        db.execute(
            """
            UPDATE employees
            SET runtime_state='working', updated_at=?
            WHERE employee_id=?
            """,
            (
                now(),
                row["employee_id"],
            ),
        )

    await publish_kernel_event(
        "employee_assignment_started",
        employee_id=row["employee_id"],
        details={
            "assignment_id": assignment_id,
            "job_id": row["job_id"],
            "resource_reservation_id": row[
                "resource_reservation_id"
            ],
            "resource_node_id": row["resource_node_id"],
            "resource_gpu_uuid": row["resource_gpu_uuid"],
        },
    )

    return {
        "ok": True,
        "assignment_id": assignment_id,
        "state": "running",
        "resource_reservation_id": row[
            "resource_reservation_id"
        ],
        "resource_node_id": row["resource_node_id"],
        "resource_gpu_uuid": row["resource_gpu_uuid"],
    }


@app.post("/assignments/{assignment_id}/complete")
async def complete_assignment(
    assignment_id: str,
    request: AssignmentStateUpdate,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM employee_assignments
            WHERE assignment_id=?
            """,
            (assignment_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found.",
        )

    if row["state"] not in {"assigned", "running"}:
        raise HTTPException(
            status_code=409,
            detail="Assignment is not active.",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            scheduler_response = await client.post(
                f"{SCHEDULER_URL}/jobs/{row['job_id']}/complete",
                json={
                    "worker_id": (
                        "persistent-employee-runtime"
                    ),
                    "lease_id": row["lease_id"],
                    "result": request.result,
                },
            )
        try:
            scheduler_body = scheduler_response.json()
        except Exception:
            scheduler_body = {
                "raw": scheduler_response.text,
            }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Scheduler completion and resource release "
                    "could not be completed."
                ),
                "error": str(exc),
                "job_id": row["job_id"],
                "resource_reservation_id": row[
                    "resource_reservation_id"
                ],
            },
        ) from exc

    if scheduler_response.status_code >= 400:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Scheduler rejected assignment completion."
                ),
                "scheduler_status": scheduler_response.status_code,
                "scheduler_response": scheduler_body,
                "job_id": row["job_id"],
                "resource_reservation_id": row[
                    "resource_reservation_id"
                ],
            },
        )

    with connect() as db:
        current = db.execute(
            """
            SELECT *
            FROM employee_assignments
            WHERE assignment_id=?
            """,
            (assignment_id,),
        ).fetchone()
        if current is None or current["state"] not in {
            "assigned",
            "running",
        }:
            raise HTTPException(
                status_code=409,
                detail="Assignment state changed before completion.",
            )

        db.execute(
            """
            UPDATE employee_assignments
            SET
                state='complete',
                result_json=?,
                error=NULL,
                resource_state='released',
                completed_at=?,
                updated_at=?
            WHERE assignment_id=?
            """,
            (
                json.dumps(request.result),
                now(),
                now(),
                assignment_id,
            ),
        )

        db.execute(
            """
            UPDATE employees
            SET
                runtime_state='idle',
                current_job_id=NULL,
                current_workflow_id=NULL,
                current_step_id=NULL,
                updated_at=?
            WHERE employee_id=?
            """,
            (
                now(),
                row["employee_id"],
            ),
        )

    await publish_kernel_event(
        "employee_assignment_completed",
        employee_id=row["employee_id"],
        details={
            "assignment_id": assignment_id,
            "job_id": row["job_id"],
            "result": request.result,
            "resource_reservation_id": row[
                "resource_reservation_id"
            ],
            "resource_released": scheduler_body.get(
                "resource_released"
            ),
        },
    )

    return {
        "ok": True,
        "assignment_id": assignment_id,
        "state": "complete",
        "resource_reservation_id": row[
            "resource_reservation_id"
        ],
        "resource_released": scheduler_body.get(
            "resource_released"
        ),
    }


@app.get("/events")
def list_events(
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM employee_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return {
        "ok": True,
        "event_count": len(rows),
        "events": [
            {
                **dict(row),
                "details": parse_json(
                    row["details_json"],
                    {},
                ),
            }
            for row in rows
        ],
    }

# Phase 49.2: lease-aware recovery extension
from app.runtime_reconciliation import router as runtime_reconciliation_router
app.include_router(runtime_reconciliation_router)
