from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


SERVICE_NAME = "execution-scheduler-service"
SERVICE_VERSION = "0.2.0"

DATA_DIR = Path(
    os.getenv(
        "EXECUTION_SCHEDULER_DATA_DIR",
        "/data/execution-scheduler",
    )
)
DB_PATH = DATA_DIR / "execution-scheduler.db"

POLL_INTERVAL_SECONDS = float(
    os.getenv(
        "EXECUTION_SCHEDULER_POLL_INTERVAL_SECONDS",
        "3",
    )
)

DEFAULT_LEASE_SECONDS = int(
    os.getenv(
        "EXECUTION_SCHEDULER_DEFAULT_LEASE_SECONDS",
        "300",
    )
)

MAX_ASSIGNMENTS_PER_TICK = int(
    os.getenv(
        "EXECUTION_SCHEDULER_MAX_ASSIGNMENTS_PER_TICK",
        "8",
    )
)

KERNEL_URL = os.getenv(
    "LEOS_KERNEL_URL",
    "http://leos-kernel-service:8000",
).rstrip("/")

RESOURCE_PROFILE_URL = os.getenv(
    "EMPLOYEE_RESOURCE_PROFILE_URL",
    "http://employee-resource-profile-service:8000",
).rstrip("/")

EMPLOYEE_REGISTRY_URL = os.getenv(
    "EMPLOYEE_REGISTRY_URL",
    "http://employee-registry:8000",
).rstrip("/")

EMPLOYEE_LIFECYCLE_ENFORCEMENT = os.getenv(
    "EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_ENFORCEMENT",
    "true",
).lower() == "true"

EMPLOYEE_LIFECYCLE_FAIL_CLOSED = os.getenv(
    "EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_FAIL_CLOSED",
    "true",
).lower() == "true"

EMPLOYEE_LIFECYCLE_TIMEOUT_SECONDS = float(
    os.getenv(
        "EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_TIMEOUT_SECONDS",
        "10",
    )
)

RESOURCE_ENFORCEMENT_ENABLED = os.getenv(
    "EXECUTION_SCHEDULER_RESOURCE_ENFORCEMENT",
    "true",
).lower() == "true"

RESOURCE_FAIL_CLOSED = os.getenv(
    "EXECUTION_SCHEDULER_RESOURCE_FAIL_CLOSED",
    "true",
).lower() == "true"

RESOURCE_COMMIT_PREEMPTION = os.getenv(
    "EXECUTION_SCHEDULER_COMMIT_PREEMPTION",
    "true",
).lower() == "true"

RESOURCE_TIMEOUT_SECONDS = float(
    os.getenv(
        "EXECUTION_SCHEDULER_RESOURCE_TIMEOUT_SECONDS",
        "10",
    )
)

AUTO_SCHEDULE = os.getenv(
    "EXECUTION_SCHEDULER_AUTO_SCHEDULE",
    "true",
).lower() == "true"

_loop_task: Optional[asyncio.Task] = None


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def now() -> str:
    return now_dt().isoformat()


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
            CREATE TABLE IF NOT EXISTS scheduler_workers (
                worker_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                worker_type TEXT NOT NULL,
                base_url TEXT,
                status TEXT NOT NULL DEFAULT 'online',
                cpu_total REAL NOT NULL DEFAULT 0,
                cpu_available REAL NOT NULL DEFAULT 0,
                ram_mb_total INTEGER NOT NULL DEFAULT 0,
                ram_mb_available INTEGER NOT NULL DEFAULT 0,
                gpu_count INTEGER NOT NULL DEFAULT 0,
                vram_mb_total INTEGER NOT NULL DEFAULT 0,
                vram_mb_available INTEGER NOT NULL DEFAULT 0,
                max_concurrent_jobs INTEGER NOT NULL DEFAULT 1,
                active_jobs INTEGER NOT NULL DEFAULT 0,
                labels_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                last_heartbeat_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                job_id TEXT PRIMARY KEY,
                mission_id TEXT,
                workflow_id TEXT,
                step_id TEXT,
                employee_id TEXT,
                capability_id TEXT,
                job_type TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 50,
                state TEXT NOT NULL DEFAULT 'queued',
                cpu_required REAL NOT NULL DEFAULT 0,
                ram_mb_required INTEGER NOT NULL DEFAULT 0,
                gpu_required INTEGER NOT NULL DEFAULT 0,
                vram_mb_required INTEGER NOT NULL DEFAULT 0,
                required_labels_json TEXT NOT NULL DEFAULT '{}',
                payload_json TEXT NOT NULL DEFAULT '{}',
                max_attempts INTEGER NOT NULL DEFAULT 3,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                not_before TEXT,
                assigned_worker_id TEXT,
                lease_id TEXT,
                lease_expires_at TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                queued_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_queue
                ON scheduler_jobs(state, priority, queued_at);

            CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_worker
                ON scheduler_jobs(assigned_worker_id, state);

            CREATE TABLE IF NOT EXISTS scheduler_leases (
                lease_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'active',
                cpu_reserved REAL NOT NULL DEFAULT 0,
                ram_mb_reserved INTEGER NOT NULL DEFAULT 0,
                gpu_reserved INTEGER NOT NULL DEFAULT 0,
                vram_mb_reserved INTEGER NOT NULL DEFAULT 0,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                released_at TEXT,
                release_reason TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_scheduler_leases_active
                ON scheduler_leases(state, expires_at);

            CREATE TABLE IF NOT EXISTS scheduler_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                job_id TEXT,
                worker_id TEXT,
                severity TEXT NOT NULL DEFAULT 'info',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scheduler_resource_history (
                resource_event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                job_id TEXT,
                employee_id TEXT,
                reservation_id TEXT,
                decision_json TEXT NOT NULL DEFAULT '{}',
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_scheduler_resource_history_job
                ON scheduler_resource_history(job_id, created_at);
            """
        )

        job_columns = {
            "resource_decision_json": "TEXT NOT NULL DEFAULT '{}'",
            "resource_reservation_id": "TEXT",
            "resource_node_id": "TEXT",
            "resource_gpu_uuid": "TEXT",
            "resource_profile_name": "TEXT",
            "resource_state": "TEXT NOT NULL DEFAULT 'pending'",
            "resource_admitted_at": "TEXT",
            "resource_released_at": "TEXT",
            "resource_release_reason": "TEXT",
            "resource_error": "TEXT",
            "employee_decision_json": "TEXT NOT NULL DEFAULT '{}'",
            "employee_state": "TEXT NOT NULL DEFAULT 'pending'",
            "employee_checked_at": "TEXT",
            "employee_error": "TEXT",
        }
        existing_job_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(scheduler_jobs)"
            ).fetchall()
        }
        for column, definition in job_columns.items():
            if column not in existing_job_columns:
                db.execute(
                    f"ALTER TABLE scheduler_jobs ADD COLUMN {column} {definition}"
                )

        existing_lease_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(scheduler_leases)"
            ).fetchall()
        }
        if "resource_reservation_id" not in existing_lease_columns:
            db.execute(
                "ALTER TABLE scheduler_leases "
                "ADD COLUMN resource_reservation_id TEXT"
            )


def emit(
    event_type: str,
    *,
    job_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    severity: str = "info",
    details: Optional[dict[str, Any]] = None,
) -> str:
    event_id = str(uuid.uuid4())

    payload = {
        "event_type": event_type,
        "subsystem_id": "execution-scheduler",
        "severity": severity,
        "job_id": job_id,
        "worker_id": worker_id,
        "details": {
            **(details or {}),
            "scheduler_event_id": event_id,
        },
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                f"{KERNEL_URL}/events/publish",
                json=payload,
            )

        if response.status_code >= 400:
            raise RuntimeError(
                "Kernel event publish failed: "
                f"{response.status_code} {response.text}"
            )

    except Exception as exc:
        # Event publication must not break scheduling. The event can be
        # reconstructed from the scheduler's durable job/lease state.
        print(
            json.dumps(
                {
                    "level": "warning",
                    "message": "kernel_event_publish_failed",
                    "event_type": event_type,
                    "job_id": job_id,
                    "worker_id": worker_id,
                    "error": str(exc),
                }
            ),
            flush=True,
        )

    return event_id




class WorkerRegister(BaseModel):
    worker_id: str
    name: str
    worker_type: str = "runtime"
    base_url: Optional[str] = None
    status: str = "online"

    cpu_total: float = 0
    cpu_available: Optional[float] = None

    ram_mb_total: int = 0
    ram_mb_available: Optional[int] = None

    gpu_count: int = 0
    vram_mb_total: int = 0
    vram_mb_available: Optional[int] = None

    max_concurrent_jobs: int = 1

    labels: dict[str, Any] = Field(
        default_factory=dict
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class WorkerHeartbeat(BaseModel):
    status: str = "online"
    cpu_available: Optional[float] = None
    ram_mb_available: Optional[int] = None
    vram_mb_available: Optional[int] = None
    active_jobs: Optional[int] = None
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class JobCreate(BaseModel):
    job_id: Optional[str] = None

    mission_id: Optional[str] = None
    workflow_id: Optional[str] = None
    step_id: Optional[str] = None
    employee_id: Optional[str] = None
    capability_id: Optional[str] = None

    job_type: str = "workflow-step"
    priority: int = Field(
        default=50,
        ge=0,
        le=100,
    )

    cpu_required: float = 0
    ram_mb_required: int = 0
    gpu_required: int = 0
    vram_mb_required: int = 0

    required_labels: dict[str, Any] = Field(
        default_factory=dict
    )
    payload: dict[str, Any] = Field(
        default_factory=dict
    )

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
    )
    not_before: Optional[str] = None


class JobStateUpdate(BaseModel):
    worker_id: Optional[str] = None
    lease_id: Optional[str] = None
    result: dict[str, Any] = Field(
        default_factory=dict
    )
    error: Optional[str] = None
    retry_delay_seconds: int = 0


migrate()

app = FastAPI(
    title="LEOS Execution Scheduler",
    version=SERVICE_VERSION,
)


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    return {}


class ResourceEnforcementError(RuntimeError):
    """Raised when mandatory resource admission cannot be proven."""


def resource_request(
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    allow_not_found: bool = False,
) -> Optional[dict[str, Any]]:
    if not RESOURCE_ENFORCEMENT_ENABLED:
        raise ResourceEnforcementError(
            "Mandatory resource enforcement is disabled by configuration."
        )

    url = f"{RESOURCE_PROFILE_URL}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=RESOURCE_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, json=payload)
    except Exception as exc:
        raise ResourceEnforcementError(
            f"Resource service request failed: {method} {url}: {exc}"
        ) from exc

    if response.status_code == 404 and allow_not_found:
        return None

    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    if response.status_code >= 400:
        raise ResourceEnforcementError(
            "Resource service rejected request "
            f"{method} {url}: {response.status_code} {body}"
        )

    if not isinstance(body, dict):
        raise ResourceEnforcementError(
            f"Resource service returned a non-object response for {method} {url}."
        )
    return body


class EmployeeLifecycleEnforcementError(RuntimeError):
    """Raised when the employee lifecycle authority cannot prove eligibility."""


def employee_request(
    employee_id: str,
    requested_at: Optional[str] = None,
) -> dict[str, Any]:
    if not EMPLOYEE_LIFECYCLE_ENFORCEMENT:
        return {
            "ok": True,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": employee_id,
            "eligible": True,
            "decision": "eligible",
            "reasons": ["lifecycle-enforcement-disabled-for-test"],
        }
    try:
        with httpx.Client(timeout=EMPLOYEE_LIFECYCLE_TIMEOUT_SECONDS) as client:
            response = client.get(
                f"{EMPLOYEE_REGISTRY_URL}/employees/{employee_id}/eligibility",
                params={"requested_at": requested_at} if requested_at else None,
            )
        if response.status_code == 404:
            return {
                "ok": True,
                "contract_version": "leos.employee-execution-eligibility.v1",
                "employee_id": employee_id,
                "eligible": False,
                "decision": "rejected",
                "reasons": ["employee-not-found"],
            }
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise EmployeeLifecycleEnforcementError(
                "Employee registry returned a non-object eligibility response."
            )
        if body.get("contract_version") != "leos.employee-execution-eligibility.v1":
            raise EmployeeLifecycleEnforcementError(
                "Employee registry returned an unsupported eligibility contract."
            )
        return body
    except Exception as exc:
        if EMPLOYEE_LIFECYCLE_FAIL_CLOSED:
            raise EmployeeLifecycleEnforcementError(str(exc)) from exc
        return {
            "ok": False,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": employee_id,
            "eligible": False,
            "decision": "queued",
            "reasons": ["employee-lifecycle-authority-unavailable"],
            "error": str(exc),
        }


def employee_eligibility(job: sqlite3.Row) -> dict[str, Any]:
    employee_id = str(job["employee_id"] or "").strip()
    if not employee_id:
        return {
            "ok": True,
            "contract_version": "leos.employee-execution-eligibility.v1",
            "employee_id": None,
            "eligible": False,
            "decision": "rejected",
            "reasons": ["employee-id-required"],
        }
    return employee_request(employee_id)


def persist_employee_decision(
    job_id: str,
    decision: dict[str, Any],
    *,
    state: str,
    error: Optional[str] = None,
) -> None:
    with connect() as db:
        db.execute(
            """
            UPDATE scheduler_jobs
            SET employee_decision_json=?, employee_state=?,
                employee_checked_at=?, employee_error=?, updated_at=?
            WHERE job_id=?
            """,
            (json.dumps(decision), state, now(), error, now(), job_id),
        )
        emit(
            "scheduler_employee_lifecycle_checked",
            job_id=job_id,
            severity="error" if error else "info",
            details={
                "employee_id": decision.get("employee_id"),
                "eligible": decision.get("eligible"),
                "decision": decision.get("decision"),
                "reasons": decision.get("reasons", []),
                "error": error,
            },
            db=db,
        )


def worker_resource_gpus(worker: sqlite3.Row) -> list[dict[str, Any]]:
    metadata = parse_json(worker["metadata_json"])
    configured = metadata.get("gpus", [])
    result: list[dict[str, Any]] = []

    if isinstance(configured, list):
        for index, item in enumerate(configured):
            if not isinstance(item, dict):
                continue
            uuid_value = str(
                item.get("uuid")
                or item.get("gpu_uuid")
                or f"{worker['worker_id']}:gpu:{index}"
            ).strip()
            if not uuid_value:
                continue
            result.append(
                {
                    "uuid": uuid_value,
                    "name": str(item.get("name", "GPU")),
                    "vram_mb_total": int(
                        item.get(
                            "vram_mb_total",
                            item.get("memory_mb", 0),
                        )
                        or 0
                    ),
                    "enabled": bool(item.get("enabled", True)),
                }
            )

    gpu_count = max(0, int(worker["gpu_count"]))
    total_vram = max(0, int(worker["vram_mb_total"]))
    if not result and gpu_count:
        per_gpu = total_vram // gpu_count if gpu_count else 0
        result = [
            {
                "uuid": f"{worker['worker_id']}:gpu:{index}",
                "name": "Scheduler GPU",
                "vram_mb_total": per_gpu,
                "enabled": True,
            }
            for index in range(gpu_count)
        ]
    return result


def worker_resource_node(worker: sqlite3.Row) -> dict[str, Any]:
    labels = {
        str(key): str(value)
        for key, value in parse_json(worker["labels_json"]).items()
    }
    labels.setdefault("scheduler_worker_id", str(worker["worker_id"]))
    metadata = parse_json(worker["metadata_json"])
    metadata = {
        **metadata,
        "scheduler_worker_id": worker["worker_id"],
        "scheduler_managed": True,
        "worker_type": worker["worker_type"],
        "base_url": worker["base_url"],
    }
    return {
        "node_id": worker["worker_id"],
        "enabled": worker["status"] == "online",
        "status": (
            "online"
            if worker["status"] == "online"
            else "offline"
        ),
        "labels": labels,
        "cpu_cores_total": float(worker["cpu_total"]),
        "memory_mb_total": int(worker["ram_mb_total"]),
        "max_concurrent_jobs": int(worker["max_concurrent_jobs"]),
        "gpus": worker_resource_gpus(worker),
        "metadata": metadata,
    }


def sync_resource_nodes(
    workers: list[sqlite3.Row],
) -> dict[str, Any]:
    synced = 0
    errors: list[dict[str, Any]] = []
    for worker in workers:
        try:
            resource_request(
                "PUT",
                f"/nodes/{worker['worker_id']}",
                worker_resource_node(worker),
            )
            synced += 1
        except Exception as exc:
            errors.append(
                {
                    "worker_id": worker["worker_id"],
                    "error": str(exc),
                }
            )
    return {
        "ok": not errors,
        "synced": synced,
        "errors": errors,
    }


def fetch_resource_reservation(
    reservation_id: str,
) -> Optional[dict[str, Any]]:
    body = resource_request(
        "GET",
        f"/reservations/{reservation_id}",
        allow_not_found=True,
    )
    if body is None:
        return None
    reservation = body.get("reservation", body)
    return reservation if isinstance(reservation, dict) else None


def find_resource_reservation_for_job(
    job_id: str,
) -> Optional[dict[str, Any]]:
    body = resource_request(
        "GET",
        f"/reservations/by-job/{job_id}",
        allow_not_found=True,
    )
    if body is None:
        return None
    reservation = body.get("reservation", body)
    return reservation if isinstance(reservation, dict) else None


def reserve_resources(
    job: sqlite3.Row,
) -> dict[str, Any]:
    employee_id = str(job["employee_id"] or "").strip()
    if not employee_id:
        return {
            "ok": False,
            "reserved": False,
            "decision": {
                "contract_version": "leos.resource-admission-decision.v1",
                "employee_id": None,
                "job_id": job["job_id"],
                "decision": "rejected",
                "reason": "employee-id-required-for-resource-admission",
            },
            "reservation": None,
        }

    existing = find_resource_reservation_for_job(job["job_id"])
    if existing is not None and existing.get("status") == "active":
        if existing.get("employee_id") != employee_id:
            raise ResourceEnforcementError(
                "Existing resource reservation employee does not match job."
            )
        return {
            "ok": True,
            "reserved": True,
            "reused": True,
            "decision": {
                "contract_version": "leos.resource-admission-decision.v1",
                "employee_id": employee_id,
                "job_id": job["job_id"],
                "decision": "admitted",
                "reason": "existing-active-reservation-reused",
                "selected_node_id": existing.get("node_id"),
                "selected_gpu_uuid": existing.get("gpu_uuid"),
                "selected_profile": existing.get("profile_name"),
                "resources": existing.get("resources"),
                "provider_preferences": existing.get(
                    "provider_preferences", []
                ),
            },
            "reservation": existing,
        }

    body = resource_request(
        "POST",
        "/reservations",
        {
            "employee_id": employee_id,
            "job_id": job["job_id"],
            "commit_preemption": RESOURCE_COMMIT_PREEMPTION,
        },
    )
    if body is None:
        raise ResourceEnforcementError(
            "Resource service returned no reservation response."
        )
    return body


def release_resource_reservation(
    reservation_id: str,
    reason: str,
) -> dict[str, Any]:
    body = resource_request(
        "POST",
        f"/reservations/{reservation_id}/release",
        {"reason": reason},
    )
    return body or {}


def record_resource_history(
    db: sqlite3.Connection,
    *,
    event_type: str,
    job_id: Optional[str],
    employee_id: Optional[str],
    reservation_id: Optional[str] = None,
    decision: Optional[dict[str, Any]] = None,
    details: Optional[dict[str, Any]] = None,
) -> str:
    event_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO scheduler_resource_history (
            resource_event_id,
            event_type,
            job_id,
            employee_id,
            reservation_id,
            decision_json,
            details_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            job_id,
            employee_id,
            reservation_id,
            json.dumps(decision or {}),
            json.dumps(details or {}),
            now(),
        ),
    )
    return event_id


def update_resource_release_state(
    job_id: str,
    reservation_id: Optional[str],
    *,
    reason: str,
    released: bool,
    error: Optional[str] = None,
) -> None:
    with connect() as db:
        db.execute(
            """
            UPDATE scheduler_jobs
            SET
                resource_state=?,
                resource_released_at=?,
                resource_release_reason=?,
                resource_error=?,
                updated_at=?
            WHERE job_id=?
            """,
            (
                "released" if released else "release-pending",
                now() if released else None,
                reason,
                error,
                now(),
                job_id,
            ),
        )
        record_resource_history(
            db,
            event_type=(
                "resource_reservation_released"
                if released
                else "resource_release_pending"
            ),
            job_id=job_id,
            employee_id=None,
            reservation_id=reservation_id,
            details={
                "reason": reason,
                "error": error,
            },
        )


def release_job_resources(
    job_id: str,
    reservation_id: Optional[str],
    reason: str,
) -> bool:
    if not reservation_id:
        return True
    try:
        release_resource_reservation(reservation_id, reason)
        update_resource_release_state(
            job_id,
            reservation_id,
            reason=reason,
            released=True,
        )
        return True
    except Exception as exc:
        update_resource_release_state(
            job_id,
            reservation_id,
            reason=reason,
            released=False,
            error=str(exc),
        )
        return False


def validate_job_resource_reservation(
    job: sqlite3.Row,
) -> dict[str, Any]:
    reservation_id = str(
        job["resource_reservation_id"] or ""
    ).strip()
    if not reservation_id:
        raise ResourceEnforcementError(
            "Job has no resource reservation."
        )
    reservation = fetch_resource_reservation(reservation_id)
    if reservation is None:
        raise ResourceEnforcementError(
            "Resource reservation was not found."
        )
    if reservation.get("status") != "active":
        raise ResourceEnforcementError(
            "Resource reservation is not active: "
            f"{reservation.get('status')}"
        )
    if reservation.get("job_id") != job["job_id"]:
        raise ResourceEnforcementError(
            "Resource reservation job mismatch."
        )
    if reservation.get("employee_id") != job["employee_id"]:
        raise ResourceEnforcementError(
            "Resource reservation employee mismatch."
        )
    return reservation


def labels_match(
    worker_labels: dict[str, Any],
    required_labels: dict[str, Any],
) -> bool:
    for key, required in required_labels.items():
        actual = worker_labels.get(key)

        if isinstance(required, list):
            if actual not in required:
                return False
        elif actual != required:
            return False

    return True


def worker_can_run(
    worker: sqlite3.Row,
    job: sqlite3.Row,
) -> bool:
    if worker["status"] != "online":
        return False

    if worker["active_jobs"] >= worker["max_concurrent_jobs"]:
        return False

    if float(worker["cpu_available"]) < float(job["cpu_required"]):
        return False

    if int(worker["ram_mb_available"]) < int(job["ram_mb_required"]):
        return False

    if int(worker["gpu_count"]) < int(job["gpu_required"]):
        return False

    if int(worker["vram_mb_available"]) < int(job["vram_mb_required"]):
        return False

    return labels_match(
        parse_json(worker["labels_json"]),
        parse_json(job["required_labels_json"]),
    )


def worker_score(
    worker: sqlite3.Row,
    job: sqlite3.Row,
) -> tuple:
    """
    Prefer the worker that leaves the least excess VRAM, RAM, and CPU while
    still satisfying the job. This keeps larger workers available for larger
    tasks.
    """
    vram_slack = (
        int(worker["vram_mb_available"])
        - int(job["vram_mb_required"])
    )
    ram_slack = (
        int(worker["ram_mb_available"])
        - int(job["ram_mb_required"])
    )
    cpu_slack = (
        float(worker["cpu_available"])
        - float(job["cpu_required"])
    )

    utilization = (
        worker["active_jobs"]
        / max(
            1,
            worker["max_concurrent_jobs"],
        )
    )

    return (
        utilization,
        vram_slack,
        ram_slack,
        cpu_slack,
        worker["worker_id"],
    )


def reserve_worker(
    db: sqlite3.Connection,
    *,
    worker: sqlite3.Row,
    job: sqlite3.Row,
    lease_id: str,
    expires_at: str,
    resource_result: dict[str, Any],
) -> None:
    decision = resource_result.get("decision") or {}
    reservation = resource_result.get("reservation") or {}
    reservation_id = reservation.get("reservation_id")

    if not reservation_id or reservation.get("status") != "active":
        raise ResourceEnforcementError(
            "Scheduler lease requires an active resource reservation."
        )

    db.execute(
        """
        UPDATE scheduler_workers
        SET
            cpu_available=cpu_available-?,
            ram_mb_available=ram_mb_available-?,
            vram_mb_available=vram_mb_available-?,
            active_jobs=active_jobs+1,
            updated_at=?
        WHERE worker_id=?
        """,
        (
            job["cpu_required"],
            job["ram_mb_required"],
            job["vram_mb_required"],
            now(),
            worker["worker_id"],
        ),
    )

    db.execute(
        """
        INSERT INTO scheduler_leases (
            lease_id,
            job_id,
            worker_id,
            state,
            cpu_reserved,
            ram_mb_reserved,
            gpu_reserved,
            vram_mb_reserved,
            acquired_at,
            expires_at,
            released_at,
            release_reason,
            resource_reservation_id
        )
        VALUES (
            ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?,
            NULL, NULL, ?
        )
        """,
        (
            lease_id,
            job["job_id"],
            worker["worker_id"],
            job["cpu_required"],
            job["ram_mb_required"],
            job["gpu_required"],
            job["vram_mb_required"],
            now(),
            expires_at,
            reservation_id,
        ),
    )

    admitted_at = now()
    db.execute(
        """
        UPDATE scheduler_jobs
        SET
            state='leased',
            assigned_worker_id=?,
            lease_id=?,
            lease_expires_at=?,
            attempt_count=attempt_count+1,
            started_at=COALESCE(started_at, ?),
            resource_decision_json=?,
            resource_reservation_id=?,
            resource_node_id=?,
            resource_gpu_uuid=?,
            resource_profile_name=?,
            resource_state='active',
            resource_admitted_at=?,
            resource_released_at=NULL,
            resource_release_reason=NULL,
            resource_error=NULL,
            updated_at=?
        WHERE job_id=?
        """,
        (
            worker["worker_id"],
            lease_id,
            expires_at,
            admitted_at,
            json.dumps(decision),
            reservation_id,
            reservation.get("node_id"),
            reservation.get("gpu_uuid"),
            reservation.get("profile_name"),
            admitted_at,
            admitted_at,
            job["job_id"],
        ),
    )

    record_resource_history(
        db,
        event_type="resource_reservation_activated",
        job_id=job["job_id"],
        employee_id=job["employee_id"],
        reservation_id=reservation_id,
        decision=decision,
        details={
            "worker_id": worker["worker_id"],
            "node_id": reservation.get("node_id"),
            "gpu_uuid": reservation.get("gpu_uuid"),
            "profile_name": reservation.get("profile_name"),
            "lease_id": lease_id,
        },
    )


def release_lease(
    db: sqlite3.Connection,
    *,
    lease_id: str,
    reason: str,
) -> Optional[sqlite3.Row]:
    lease = db.execute(
        """
        SELECT *
        FROM scheduler_leases
        WHERE lease_id=?
        """,
        (lease_id,),
    ).fetchone()

    if lease is None or lease["state"] != "active":
        return lease

    db.execute(
        """
        UPDATE scheduler_workers
        SET
            cpu_available=MIN(
                cpu_total,
                cpu_available+?
            ),
            ram_mb_available=MIN(
                ram_mb_total,
                ram_mb_available+?
            ),
            vram_mb_available=MIN(
                vram_mb_total,
                vram_mb_available+?
            ),
            active_jobs=MAX(
                0,
                active_jobs-1
            ),
            updated_at=?
        WHERE worker_id=?
        """,
        (
            lease["cpu_reserved"],
            lease["ram_mb_reserved"],
            lease["vram_mb_reserved"],
            now(),
            lease["worker_id"],
        ),
    )

    db.execute(
        """
        UPDATE scheduler_leases
        SET
            state='released',
            released_at=?,
            release_reason=?
        WHERE lease_id=?
        """,
        (
            now(),
            reason,
            lease_id,
        ),
    )

    return lease


def expire_leases() -> int:
    timestamp = now()
    expired_count = 0
    resource_releases: list[tuple[str, Optional[str]]] = []

    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM scheduler_leases
            WHERE
                state='active'
                AND expires_at<=?
            """,
            (timestamp,),
        ).fetchall()

        for lease in rows:
            release_lease(
                db,
                lease_id=lease["lease_id"],
                reason="lease_expired",
            )

            job = db.execute(
                """
                SELECT *
                FROM scheduler_jobs
                WHERE job_id=?
                """,
                (lease["job_id"],),
            ).fetchone()

            if job is None:
                continue

            if job["attempt_count"] >= job["max_attempts"]:
                state = "failed"
                error = "Lease expired and maximum attempts were reached."
            else:
                state = "queued"
                error = "Lease expired before completion."

            reservation_id = (
                job["resource_reservation_id"]
                or lease["resource_reservation_id"]
            )
            db.execute(
                """
                UPDATE scheduler_jobs
                SET
                    state=?,
                    assigned_worker_id=NULL,
                    lease_id=NULL,
                    lease_expires_at=NULL,
                    error=?,
                    queued_at=?,
                    resource_state=?,
                    resource_release_reason='scheduler-lease-expired',
                    updated_at=?
                WHERE job_id=?
                """,
                (
                    state,
                    error,
                    now(),
                    (
                        "release-pending"
                        if reservation_id
                        else "released"
                    ),
                    now(),
                    job["job_id"],
                ),
            )

            record_resource_history(
                db,
                event_type="scheduler_lease_expired",
                job_id=job["job_id"],
                employee_id=job["employee_id"],
                reservation_id=reservation_id,
                decision=parse_json(job["resource_decision_json"]),
                details={
                    "lease_id": lease["lease_id"],
                    "new_job_state": state,
                },
            )

            emit(
                "scheduler_lease_expired",
                job_id=job["job_id"],
                worker_id=lease["worker_id"],
                severity="warning",
                details={
                    "lease_id": lease["lease_id"],
                    "new_job_state": state,
                    "resource_reservation_id": reservation_id,
                },
            )

            resource_releases.append(
                (job["job_id"], reservation_id)
            )
            expired_count += 1

    for job_id, reservation_id in resource_releases:
        release_job_resources(
            job_id,
            reservation_id,
            "scheduler-lease-expired",
        )

    return expired_count


def reconcile_resource_reservations() -> dict[str, Any]:
    checked = 0
    recovered = 0
    releases = 0
    errors: list[dict[str, Any]] = []

    try:
        resource_request("POST", "/reservations/expire", {})
    except Exception as exc:
        errors.append(
            {
                "operation": "expire-remote-reservations",
                "error": str(exc),
            }
        )

    with connect() as db:
        active_jobs = db.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE state IN ('leased', 'running')
            ORDER BY created_at
            """
        ).fetchall()

    for job in active_jobs:
        checked += 1
        try:
            validate_job_resource_reservation(job)
        except Exception as exc:
            reservation_id = job["resource_reservation_id"]
            with connect() as db:
                current = db.execute(
                    "SELECT * FROM scheduler_jobs WHERE job_id=?",
                    (job["job_id"],),
                ).fetchone()
                if current is None:
                    continue
                if current["lease_id"]:
                    release_lease(
                        db,
                        lease_id=current["lease_id"],
                        reason="resource-reservation-invalid",
                    )
                should_retry = (
                    current["attempt_count"]
                    < current["max_attempts"]
                )
                state = "queued" if should_retry else "failed"
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET
                        state=?,
                        assigned_worker_id=NULL,
                        lease_id=NULL,
                        lease_expires_at=NULL,
                        queued_at=?,
                        completed_at=?,
                        error=?,
                        resource_state='invalid',
                        resource_error=?,
                        updated_at=?
                    WHERE job_id=?
                    """,
                    (
                        state,
                        now(),
                        None if should_retry else now(),
                        "Resource reservation became invalid.",
                        str(exc),
                        now(),
                        current["job_id"],
                    ),
                )
                record_resource_history(
                    db,
                    event_type="resource_reservation_invalid",
                    job_id=current["job_id"],
                    employee_id=current["employee_id"],
                    reservation_id=reservation_id,
                    decision=parse_json(
                        current["resource_decision_json"]
                    ),
                    details={
                        "error": str(exc),
                        "new_job_state": state,
                    },
                )
            release_job_resources(
                job["job_id"],
                reservation_id,
                "resource-reservation-invalid",
            )
            recovered += 1

    with connect() as db:
        pending = db.execute(
            """
            SELECT job_id, resource_reservation_id,
                   resource_release_reason
            FROM scheduler_jobs
            WHERE resource_state='release-pending'
              AND resource_reservation_id IS NOT NULL
            ORDER BY updated_at
            """
        ).fetchall()

    for row in pending:
        if release_job_resources(
            row["job_id"],
            row["resource_reservation_id"],
            row["resource_release_reason"]
            or "scheduler-reconciliation",
        ):
            releases += 1
        else:
            errors.append(
                {
                    "operation": "release-pending",
                    "job_id": row["job_id"],
                    "reservation_id": row[
                        "resource_reservation_id"
                    ],
                }
            )

    return {
        "ok": not errors,
        "checked_active_jobs": checked,
        "recovered_invalid_jobs": recovered,
        "released_pending_reservations": releases,
        "errors": errors,
    }


def schedule_tick() -> dict[str, Any]:
    expired_count = expire_leases()
    reconciliation = reconcile_resource_reservations()
    assignments: list[dict[str, Any]] = []
    queued_by_policy = 0
    rejected_by_policy = 0
    admission_errors = 0
    queued_by_employee_policy = 0
    rejected_by_employee_policy = 0
    employee_policy_errors = 0

    with connect() as db:
        jobs = db.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE
                state='queued'
                AND (
                    not_before IS NULL
                    OR not_before<=?
                )
            ORDER BY
                priority DESC,
                queued_at ASC
            LIMIT ?
            """,
            (
                now(),
                MAX_ASSIGNMENTS_PER_TICK,
            ),
        ).fetchall()

        workers = db.execute(
            """
            SELECT *
            FROM scheduler_workers
            WHERE status='online'
            ORDER BY worker_id
            """
        ).fetchall()

    node_sync = sync_resource_nodes(workers)
    if not node_sync["ok"] and RESOURCE_FAIL_CLOSED:
        with connect() as db:
            for job in jobs:
                error = (
                    "Resource node synchronization failed; "
                    "execution is blocked fail-closed."
                )
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET resource_state='error',
                        resource_error=?,
                        updated_at=?
                    WHERE job_id=? AND state='queued'
                    """,
                    (error, now(), job["job_id"]),
                )
                record_resource_history(
                    db,
                    event_type="resource_node_sync_failed",
                    job_id=job["job_id"],
                    employee_id=job["employee_id"],
                    details={
                        "errors": node_sync["errors"],
                    },
                )
        return {
            "ok": False,
            "expired_lease_count": expired_count,
            "resource_reconciliation": reconciliation,
            "resource_node_sync": node_sync,
            "assignment_count": 0,
            "queued_by_resource_policy": len(jobs),
            "rejected_by_resource_policy": 0,
            "admission_error_count": len(jobs),
            "queued_by_employee_policy": 0,
            "rejected_by_employee_policy": 0,
            "employee_policy_error_count": 0,
            "assignments": [],
            "error": "resource-node-synchronization-failed",
        }

    for initial_job in jobs:
        with connect() as db:
            job = db.execute(
                "SELECT * FROM scheduler_jobs WHERE job_id=?",
                (initial_job["job_id"],),
            ).fetchone()
        if job is None or job["state"] != "queued":
            continue

        try:
            lifecycle_decision = employee_eligibility(job)
        except Exception as exc:
            employee_policy_errors += 1
            persist_employee_decision(
                job["job_id"],
                {
                    "contract_version": "leos.employee-execution-eligibility.v1",
                    "employee_id": job["employee_id"],
                    "eligible": False,
                    "decision": "queued",
                    "reasons": ["employee-lifecycle-authority-error"],
                },
                state="error",
                error=str(exc),
            )
            continue

        if lifecycle_decision.get("eligible") is not True:
            lifecycle_name = str(lifecycle_decision.get("decision", "queued")).lower()
            terminal = lifecycle_name == "rejected"
            with connect() as db:
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET state=?, employee_decision_json=?, employee_state=?,
                        employee_checked_at=?, employee_error=NULL,
                        completed_at=?, error=?, updated_at=?
                    WHERE job_id=? AND state='queued'
                    """,
                    (
                        "rejected" if terminal else "queued",
                        json.dumps(lifecycle_decision),
                        "rejected" if terminal else "queued",
                        now(),
                        now() if terminal else None,
                        ";".join(lifecycle_decision.get("reasons", [])) if terminal else None,
                        now(),
                        job["job_id"],
                    ),
                )
            if terminal:
                rejected_by_employee_policy += 1
            else:
                queued_by_employee_policy += 1
            emit(
                "scheduler_job_employee_rejected" if terminal else "scheduler_job_employee_queued",
                job_id=job["job_id"],
                severity="warning" if terminal else "info",
                details=lifecycle_decision,
            )
            continue

        persist_employee_decision(
            job["job_id"],
            lifecycle_decision,
            state="eligible",
        )

        try:
            resource_result = reserve_resources(job)
        except Exception as exc:
            admission_errors += 1
            with connect() as db:
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET
                        resource_state='error',
                        resource_error=?,
                        updated_at=?
                    WHERE job_id=? AND state='queued'
                    """,
                    (str(exc), now(), job["job_id"]),
                )
                record_resource_history(
                    db,
                    event_type="resource_admission_error",
                    job_id=job["job_id"],
                    employee_id=job["employee_id"],
                    details={"error": str(exc)},
                )
            emit(
                "scheduler_resource_admission_error",
                job_id=job["job_id"],
                severity="error",
                details={"error": str(exc)},
            )
            continue

        decision = resource_result.get("decision") or {}
        decision_name = str(
            decision.get("decision", "rejected")
        ).lower()
        reservation = resource_result.get("reservation")
        reservation = (
            reservation if isinstance(reservation, dict) else None
        )

        if (
            resource_result.get("reserved") is not True
            or decision_name != "admitted"
            or reservation is None
        ):
            reason = str(
                decision.get(
                    "reason",
                    "resource-admission-not-granted",
                )
            )
            terminal = decision_name == "rejected"
            with connect() as db:
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET
                        state=?,
                        resource_decision_json=?,
                        resource_state=?,
                        resource_error=NULL,
                        completed_at=?,
                        error=?,
                        updated_at=?
                    WHERE job_id=? AND state='queued'
                    """,
                    (
                        "rejected" if terminal else "queued",
                        json.dumps(decision),
                        "rejected" if terminal else "queued",
                        now() if terminal else None,
                        reason if terminal else None,
                        now(),
                        job["job_id"],
                    ),
                )
                record_resource_history(
                    db,
                    event_type=(
                        "resource_admission_rejected"
                        if terminal
                        else "resource_admission_queued"
                    ),
                    job_id=job["job_id"],
                    employee_id=job["employee_id"],
                    decision=decision,
                    details={"reason": reason},
                )
            if terminal:
                rejected_by_policy += 1
            else:
                queued_by_policy += 1
            emit(
                (
                    "scheduler_job_resource_rejected"
                    if terminal
                    else "scheduler_job_resource_queued"
                ),
                job_id=job["job_id"],
                severity="warning" if terminal else "info",
                details={
                    "decision": decision_name,
                    "reason": reason,
                },
            )
            continue

        reservation_id = reservation.get("reservation_id")
        selected_node_id = reservation.get("node_id")
        with connect() as db:
            selected = db.execute(
                """
                SELECT *
                FROM scheduler_workers
                WHERE worker_id=? AND status='online'
                """,
                (selected_node_id,),
            ).fetchone()
            current_job = db.execute(
                "SELECT * FROM scheduler_jobs WHERE job_id=?",
                (job["job_id"],),
            ).fetchone()

        if (
            selected is None
            or current_job is None
            or current_job["state"] != "queued"
            or not worker_can_run(selected, current_job)
        ):
            reason = "selected-resource-node-unavailable-to-scheduler"
            release_job_resources(
                job["job_id"],
                reservation_id,
                reason,
            )
            with connect() as db:
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET
                        resource_decision_json=?,
                        resource_reservation_id=?,
                        resource_node_id=?,
                        resource_gpu_uuid=?,
                        resource_profile_name=?,
                        resource_state='released',
                        resource_release_reason=?,
                        resource_error=?,
                        updated_at=?
                    WHERE job_id=? AND state='queued'
                    """,
                    (
                        json.dumps(decision),
                        reservation_id,
                        selected_node_id,
                        reservation.get("gpu_uuid"),
                        reservation.get("profile_name"),
                        reason,
                        reason,
                        now(),
                        job["job_id"],
                    ),
                )
                record_resource_history(
                    db,
                    event_type="resource_scheduler_node_mismatch",
                    job_id=job["job_id"],
                    employee_id=job["employee_id"],
                    reservation_id=reservation_id,
                    decision=decision,
                    details={
                        "selected_node_id": selected_node_id,
                        "worker_found": selected is not None,
                    },
                )
            queued_by_policy += 1
            continue

        lease_id = str(uuid.uuid4())
        expires_at = (
            now_dt()
            + timedelta(
                seconds=DEFAULT_LEASE_SECONDS
            )
        ).isoformat()

        try:
            with connect() as db:
                current_job = db.execute(
                    "SELECT * FROM scheduler_jobs WHERE job_id=?",
                    (job["job_id"],),
                ).fetchone()
                current_worker = db.execute(
                    "SELECT * FROM scheduler_workers WHERE worker_id=?",
                    (selected["worker_id"],),
                ).fetchone()
                if (
                    current_job is None
                    or current_job["state"] != "queued"
                    or current_worker is None
                    or not worker_can_run(
                        current_worker,
                        current_job,
                    )
                ):
                    raise ResourceEnforcementError(
                        "Worker capacity changed before lease commit."
                    )

                reserve_worker(
                    db,
                    worker=current_worker,
                    job=current_job,
                    lease_id=lease_id,
                    expires_at=expires_at,
                    resource_result=resource_result,
                )
        except Exception as exc:
            release_job_resources(
                job["job_id"],
                reservation_id,
                "scheduler-lease-commit-failed",
            )
            admission_errors += 1
            with connect() as db:
                db.execute(
                    """
                    UPDATE scheduler_jobs
                    SET resource_state='released',
                        resource_error=?,
                        updated_at=?
                    WHERE job_id=? AND state='queued'
                    """,
                    (str(exc), now(), job["job_id"]),
                )
                record_resource_history(
                    db,
                    event_type="scheduler_lease_commit_failed",
                    job_id=job["job_id"],
                    employee_id=job["employee_id"],
                    reservation_id=reservation_id,
                    decision=decision,
                    details={"error": str(exc)},
                )
            continue

        assignment = {
            "job_id": job["job_id"],
            "worker_id": selected["worker_id"],
            "lease_id": lease_id,
            "lease_expires_at": expires_at,
            "priority": job["priority"],
            "resource_reservation_id": reservation_id,
            "resource_node_id": selected_node_id,
            "resource_gpu_uuid": reservation.get("gpu_uuid"),
            "resource_profile_name": reservation.get(
                "profile_name"
            ),
        }

        assignments.append(assignment)
        emit(
            "scheduler_job_leased",
            job_id=job["job_id"],
            worker_id=selected["worker_id"],
            details=assignment,
        )

    return {
        "ok": admission_errors == 0,
        "expired_lease_count": expired_count,
        "resource_reconciliation": reconciliation,
        "resource_node_sync": node_sync,
        "assignment_count": len(assignments),
        "queued_by_resource_policy": queued_by_policy,
        "rejected_by_resource_policy": rejected_by_policy,
        "admission_error_count": admission_errors,
        "queued_by_employee_policy": queued_by_employee_policy,
        "rejected_by_employee_policy": rejected_by_employee_policy,
        "employee_policy_error_count": employee_policy_errors,
        "assignments": assignments,
    }


async def loop() -> None:
    while True:
        try:
            if AUTO_SCHEDULE:
                schedule_tick()
        except Exception:
            pass

        await asyncio.sleep(
            POLL_INTERVAL_SECONDS
        )


async def register_with_kernel() -> None:
    payload = {
        "subsystem_id": "execution-scheduler",
        "name": "Execution Scheduler",
        "category": "scheduling",
        "base_url": "http://execution-scheduler-service:8000",
        "health_path": "/health",
        "required": True,
        "enabled": True,
        "priority": 25,
        "metadata": {
            "service_version": SERVICE_VERSION,
            "scheduler": "resource-aware",
        },
    }

    try:
        async with httpx.AsyncClient(
            timeout=10
        ) as client:
            await client.post(
                f"{KERNEL_URL}/subsystems",
                json=payload,
            )
    except Exception:
        pass


@app.on_event("startup")
async def startup() -> None:
    global _loop_task

    migrate()
    await register_with_kernel()

    if AUTO_SCHEDULE and (
        _loop_task is None
        or _loop_task.done()
    ):
        _loop_task = asyncio.create_task(
            loop()
        )


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        worker_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_workers
            """
        ).fetchone()["c"]

        online_worker_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_workers
            WHERE status='online'
            """
        ).fetchone()["c"]

        queued_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_jobs
            WHERE state='queued'
            """
        ).fetchone()["c"]

        active_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_jobs
            WHERE state IN (
                'leased',
                'running'
            )
            """
        ).fetchone()["c"]

        completed_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_jobs
            WHERE state='complete'
            """
        ).fetchone()["c"]

        failed_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_jobs
            WHERE state='failed'
            """
        ).fetchone()["c"]

        rejected_count = db.execute(
            """
            SELECT COUNT(*) c
            FROM scheduler_jobs
            WHERE state='rejected'
            """
        ).fetchone()["c"]

        resource_state_counts = {
            row["resource_state"]: row["count"]
            for row in db.execute(
                """
                SELECT resource_state, COUNT(*) AS count
                FROM scheduler_jobs
                GROUP BY resource_state
                """
            ).fetchall()
        }

    return {
        "ok": True,
        "service": SERVICE_NAME,
        "platform": "LEOS",
        "version": SERVICE_VERSION,
        "auto_schedule": AUTO_SCHEDULE,
        "poll_interval_seconds": (
            POLL_INTERVAL_SECONDS
        ),
        "default_lease_seconds": (
            DEFAULT_LEASE_SECONDS
        ),
        "max_assignments_per_tick": (
            MAX_ASSIGNMENTS_PER_TICK
        ),
        "worker_count": worker_count,
        "online_worker_count": (
            online_worker_count
        ),
        "queued_count": queued_count,
        "active_count": active_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "rejected_count": rejected_count,
        "employee_lifecycle_enforcement": {
            "enabled": EMPLOYEE_LIFECYCLE_ENFORCEMENT,
            "fail_closed": EMPLOYEE_LIFECYCLE_FAIL_CLOSED,
            "registry_url": EMPLOYEE_REGISTRY_URL,
            "contract_version": "leos.employee-execution-eligibility.v1",
        },
        "resource_enforcement": {
            "mandatory": True,
            "enabled": RESOURCE_ENFORCEMENT_ENABLED,
            "fail_closed": RESOURCE_FAIL_CLOSED,
            "resource_profile_url": RESOURCE_PROFILE_URL,
            "commit_preemption": RESOURCE_COMMIT_PREEMPTION,
            "timeout_seconds": RESOURCE_TIMEOUT_SECONDS,
            "state_counts": resource_state_counts,
        },
        "database": str(DB_PATH),
    }


@app.post("/workers")
def register_worker(
    request: WorkerRegister,
) -> dict[str, Any]:
    timestamp = now()

    cpu_available = (
        request.cpu_total
        if request.cpu_available is None
        else request.cpu_available
    )

    ram_available = (
        request.ram_mb_total
        if request.ram_mb_available is None
        else request.ram_mb_available
    )

    vram_available = (
        request.vram_mb_total
        if request.vram_mb_available is None
        else request.vram_mb_available
    )

    with connect() as db:
        db.execute(
            """
            INSERT INTO scheduler_workers (
                worker_id,
                name,
                worker_type,
                base_url,
                status,
                cpu_total,
                cpu_available,
                ram_mb_total,
                ram_mb_available,
                gpu_count,
                vram_mb_total,
                vram_mb_available,
                max_concurrent_jobs,
                active_jobs,
                labels_json,
                metadata_json,
                last_heartbeat_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            ON CONFLICT(worker_id)
            DO UPDATE SET
                name=excluded.name,
                worker_type=excluded.worker_type,
                base_url=excluded.base_url,
                status=excluded.status,
                cpu_total=excluded.cpu_total,
                cpu_available=excluded.cpu_available,
                ram_mb_total=excluded.ram_mb_total,
                ram_mb_available=excluded.ram_mb_available,
                gpu_count=excluded.gpu_count,
                vram_mb_total=excluded.vram_mb_total,
                vram_mb_available=excluded.vram_mb_available,
                max_concurrent_jobs=excluded.max_concurrent_jobs,
                labels_json=excluded.labels_json,
                metadata_json=excluded.metadata_json,
                last_heartbeat_at=excluded.last_heartbeat_at,
                updated_at=excluded.updated_at
            """,
            (
                request.worker_id,
                request.name,
                request.worker_type,
                request.base_url,
                request.status,
                request.cpu_total,
                cpu_available,
                request.ram_mb_total,
                ram_available,
                request.gpu_count,
                request.vram_mb_total,
                vram_available,
                request.max_concurrent_jobs,
                json.dumps(request.labels),
                json.dumps(request.metadata),
                timestamp,
                timestamp,
                timestamp,
            ),
        )

    emit(
        "scheduler_worker_registered",
        worker_id=request.worker_id,
        details={
            "name": request.name,
            "worker_type": request.worker_type,
            "gpu_count": request.gpu_count,
            "vram_mb_total": request.vram_mb_total,
        },
    )

    return {
        "ok": True,
        "worker_id": request.worker_id,
    }


@app.put("/workers/{worker_id}/heartbeat")
def worker_heartbeat(
    worker_id: str,
    request: WorkerHeartbeat,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM scheduler_workers
            WHERE worker_id=?
            """,
            (worker_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Worker not found.",
            )

        db.execute(
            """
            UPDATE scheduler_workers
            SET
                status=?,
                cpu_available=?,
                ram_mb_available=?,
                vram_mb_available=?,
                active_jobs=?,
                metadata_json=?,
                last_heartbeat_at=?,
                updated_at=?
            WHERE worker_id=?
            """,
            (
                request.status,
                (
                    row["cpu_available"]
                    if request.cpu_available is None
                    else request.cpu_available
                ),
                (
                    row["ram_mb_available"]
                    if request.ram_mb_available is None
                    else request.ram_mb_available
                ),
                (
                    row["vram_mb_available"]
                    if request.vram_mb_available is None
                    else request.vram_mb_available
                ),
                (
                    row["active_jobs"]
                    if request.active_jobs is None
                    else request.active_jobs
                ),
                json.dumps(request.metadata),
                now(),
                now(),
                worker_id,
            ),
        )

    return {
        "ok": True,
        "worker_id": worker_id,
        "status": request.status,
    }


@app.get("/workers")
def list_workers() -> dict[str, Any]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM scheduler_workers
            ORDER BY worker_id
            """
        ).fetchall()

    return {
        "ok": True,
        "worker_count": len(rows),
        "workers": [
            {
                **dict(row),
                "labels": parse_json(
                    row["labels_json"]
                ),
                "metadata": parse_json(
                    row["metadata_json"]
                ),
            }
            for row in rows
        ],
    }


@app.post("/jobs")
def create_job(
    request: JobCreate,
) -> dict[str, Any]:
    job_id = (
        request.job_id
        or str(uuid.uuid4())
    )

    timestamp = now()

    with connect() as db:
        existing = db.execute(
            """
            SELECT job_id
            FROM scheduler_jobs
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()

        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="Job already exists.",
            )

        db.execute(
            """
            INSERT INTO scheduler_jobs (
                job_id,
                mission_id,
                workflow_id,
                step_id,
                employee_id,
                capability_id,
                job_type,
                priority,
                state,
                cpu_required,
                ram_mb_required,
                gpu_required,
                vram_mb_required,
                required_labels_json,
                payload_json,
                max_attempts,
                attempt_count,
                not_before,
                assigned_worker_id,
                lease_id,
                lease_expires_at,
                result_json,
                error,
                created_at,
                queued_at,
                started_at,
                completed_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, 'queued',
                ?, ?, ?, ?, ?, ?, ?, 0, ?,
                NULL, NULL, NULL, NULL, NULL,
                ?, ?, NULL, NULL, ?
            )
            """,
            (
                job_id,
                request.mission_id,
                request.workflow_id,
                request.step_id,
                request.employee_id,
                request.capability_id,
                request.job_type,
                request.priority,
                request.cpu_required,
                request.ram_mb_required,
                request.gpu_required,
                request.vram_mb_required,
                json.dumps(
                    request.required_labels
                ),
                json.dumps(request.payload),
                request.max_attempts,
                request.not_before,
                timestamp,
                timestamp,
                timestamp,
            ),
        )

    emit(
        "scheduler_job_queued",
        job_id=job_id,
        details={
            "priority": request.priority,
            "employee_id": request.employee_id,
            "capability_id": request.capability_id,
            "cpu_required": request.cpu_required,
            "ram_mb_required": request.ram_mb_required,
            "gpu_required": request.gpu_required,
            "vram_mb_required": request.vram_mb_required,
        },
    )

    return {
        "ok": True,
        "job_id": job_id,
        "state": "queued",
    }


@app.get("/jobs")
def list_jobs(
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
            FROM scheduler_jobs
            {where}
            ORDER BY priority DESC, queued_at
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "ok": True,
        "job_count": len(rows),
        "jobs": [
            {
                **dict(row),
                "required_labels": parse_json(
                    row["required_labels_json"]
                ),
                "payload": parse_json(
                    row["payload_json"]
                ),
                "result": parse_json(
                    row["result_json"]
                ),
                "resource_decision": parse_json(
                    row["resource_decision_json"]
                ),
            }
            for row in rows
        ],
    }


@app.get("/jobs/{job_id}")
def get_job(
    job_id: str,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    return {
        "ok": True,
        "job": {
            **dict(row),
            "required_labels": parse_json(
                row["required_labels_json"]
            ),
            "payload": parse_json(
                row["payload_json"]
            ),
            "result": parse_json(
                row["result_json"]
            ),
            "resource_decision": parse_json(
                row["resource_decision_json"]
            ),
            "employee_decision": parse_json(
                row["employee_decision_json"]
            ),
        },
    }


@app.post("/schedule/tick")
def manual_schedule_tick() -> dict[str, Any]:
    return schedule_tick()


@app.post("/jobs/{job_id}/running")
def mark_job_running(
    job_id: str,
    request: JobStateUpdate,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    if row["state"] != "leased":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only leased jobs may "
                "transition to running."
            ),
        )

    if request.lease_id and (
        request.lease_id
        != row["lease_id"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Lease mismatch.",
        )

    try:
        lifecycle_decision = employee_eligibility(row)
    except Exception as exc:
        persist_employee_decision(
            job_id,
            {
                "contract_version": "leos.employee-execution-eligibility.v1",
                "employee_id": row["employee_id"],
                "eligible": False,
                "decision": "queued",
                "reasons": ["employee-lifecycle-authority-error"],
            },
            state="error",
            error=str(exc),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Job cannot start without current employee lifecycle eligibility.",
                "error": str(exc),
            },
        ) from exc
    if lifecycle_decision.get("eligible") is not True:
        persist_employee_decision(
            job_id,
            lifecycle_decision,
            state=str(lifecycle_decision.get("decision", "queued")),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Job cannot start because the employee is not eligible.",
                "employee_decision": lifecycle_decision,
            },
        )
    persist_employee_decision(job_id, lifecycle_decision, state="eligible")

    try:
        reservation = validate_job_resource_reservation(row)
    except Exception as exc:
        with connect() as db:
            record_resource_history(
                db,
                event_type="resource_start_validation_failed",
                job_id=row["job_id"],
                employee_id=row["employee_id"],
                reservation_id=row["resource_reservation_id"],
                decision=parse_json(row["resource_decision_json"]),
                details={"error": str(exc)},
            )
            db.execute(
                """
                UPDATE scheduler_jobs
                SET resource_state='invalid',
                    resource_error=?,
                    updated_at=?
                WHERE job_id=?
                """,
                (str(exc), now(), job_id),
            )
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Job cannot start without an active "
                    "resource reservation."
                ),
                "error": str(exc),
                "resource_reservation_id": row[
                    "resource_reservation_id"
                ],
            },
        ) from exc

    with connect() as db:
        current = db.execute(
            "SELECT * FROM scheduler_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if current is None or current["state"] != "leased":
            raise HTTPException(
                status_code=409,
                detail="Job state changed before start.",
            )
        db.execute(
            """
            UPDATE scheduler_jobs
            SET state='running',
                resource_state='active',
                resource_error=NULL,
                updated_at=?
            WHERE job_id=?
            """,
            (now(), job_id),
        )
        record_resource_history(
            db,
            event_type="resource_reservation_start_validated",
            job_id=row["job_id"],
            employee_id=row["employee_id"],
            reservation_id=row["resource_reservation_id"],
            decision=parse_json(row["resource_decision_json"]),
            details={
                "lease_id": row["lease_id"],
                "node_id": reservation.get("node_id"),
                "gpu_uuid": reservation.get("gpu_uuid"),
            },
        )

    emit(
        "scheduler_job_running",
        job_id=job_id,
        worker_id=row["assigned_worker_id"],
        details={
            "lease_id": row["lease_id"],
            "resource_reservation_id": row[
                "resource_reservation_id"
            ],
            "resource_node_id": reservation.get("node_id"),
            "resource_gpu_uuid": reservation.get("gpu_uuid"),
        },
    )

    return {
        "ok": True,
        "job_id": job_id,
        "state": "running",
        "resource_reservation_id": row[
            "resource_reservation_id"
        ],
        "resource_node_id": reservation.get("node_id"),
        "resource_gpu_uuid": reservation.get("gpu_uuid"),
    }


@app.post("/jobs/{job_id}/complete")
def complete_job(
    job_id: str,
    request: JobStateUpdate,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Job not found.",
            )

        if row["state"] not in {
            "leased",
            "running",
        }:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Job is not active."
                ),
            )

        if request.lease_id and (
            request.lease_id
            != row["lease_id"]
        ):
            raise HTTPException(
                status_code=409,
                detail="Lease mismatch.",
            )

        if row["lease_id"]:
            release_lease(
                db,
                lease_id=row["lease_id"],
                reason="job_complete",
            )

        db.execute(
            """
            UPDATE scheduler_jobs
            SET
                state='complete',
                result_json=?,
                error=NULL,
                completed_at=?,
                resource_state=?,
                resource_release_reason='job-complete',
                updated_at=?
            WHERE job_id=?
            """,
            (
                json.dumps(request.result),
                now(),
                (
                    "release-pending"
                    if row["resource_reservation_id"]
                    else "released"
                ),
                now(),
                job_id,
            ),
        )
        record_resource_history(
            db,
            event_type="job_complete_resource_release_requested",
            job_id=row["job_id"],
            employee_id=row["employee_id"],
            reservation_id=row["resource_reservation_id"],
            decision=parse_json(row["resource_decision_json"]),
            details={"lease_id": row["lease_id"]},
        )

    resource_released = release_job_resources(
        job_id,
        row["resource_reservation_id"],
        "job-complete",
    )

    emit(
        "scheduler_job_complete",
        job_id=job_id,
        worker_id=row["assigned_worker_id"],
        details={
            "result": request.result,
            "resource_reservation_id": row[
                "resource_reservation_id"
            ],
            "resource_released": resource_released,
        },
    )

    return {
        "ok": True,
        "job_id": job_id,
        "state": "complete",
        "resource_reservation_id": row[
            "resource_reservation_id"
        ],
        "resource_released": resource_released,
    }


@app.post("/jobs/{job_id}/fail")
def fail_job(
    job_id: str,
    request: JobStateUpdate,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            """
            SELECT *
            FROM scheduler_jobs
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Job not found.",
            )

        if row["lease_id"]:
            release_lease(
                db,
                lease_id=row["lease_id"],
                reason="job_failed",
            )

        should_retry = (
            row["attempt_count"]
            < row["max_attempts"]
        )

        new_state = (
            "queued"
            if should_retry
            else "failed"
        )

        not_before = (
            (
                now_dt()
                + timedelta(
                    seconds=max(
                        0,
                        request.retry_delay_seconds,
                    )
                )
            ).isoformat()
            if should_retry
            else None
        )

        db.execute(
            """
            UPDATE scheduler_jobs
            SET
                state=?,
                assigned_worker_id=NULL,
                lease_id=NULL,
                lease_expires_at=NULL,
                error=?,
                not_before=?,
                queued_at=?,
                completed_at=?,
                resource_state=?,
                resource_release_reason='job-failed',
                updated_at=?
            WHERE job_id=?
            """,
            (
                new_state,
                request.error,
                not_before,
                now(),
                (
                    None
                    if should_retry
                    else now()
                ),
                (
                    "release-pending"
                    if row["resource_reservation_id"]
                    else "released"
                ),
                now(),
                job_id,
            ),
        )
        record_resource_history(
            db,
            event_type="job_failed_resource_release_requested",
            job_id=row["job_id"],
            employee_id=row["employee_id"],
            reservation_id=row["resource_reservation_id"],
            decision=parse_json(row["resource_decision_json"]),
            details={
                "retry": should_retry,
                "new_state": new_state,
                "error": request.error,
            },
        )

    resource_released = release_job_resources(
        job_id,
        row["resource_reservation_id"],
        "job-failed",
    )

    emit(
        "scheduler_job_failed",
        job_id=job_id,
        worker_id=row["assigned_worker_id"],
        severity=(
            "warning"
            if should_retry
            else "error"
        ),
        details={
            "error": request.error,
            "retry": should_retry,
            "new_state": new_state,
            "attempt_count": (
                row["attempt_count"]
            ),
            "max_attempts": (
                row["max_attempts"]
            ),
            "resource_reservation_id": row[
                "resource_reservation_id"
            ],
            "resource_released": resource_released,
        },
    )

    return {
        "ok": True,
        "job_id": job_id,
        "state": new_state,
        "retry": should_retry,
        "resource_reservation_id": row[
            "resource_reservation_id"
        ],
        "resource_released": resource_released,
    }


@app.post("/resources/reconcile")
def reconcile_resources() -> dict[str, Any]:
    result = reconcile_resource_reservations()
    return {
        "ok": result.get("ok") is True,
        "contract_version": "leos.runtime-resource-reconciliation.v1",
        **result,
    }


@app.get("/jobs/{job_id}/resource")
def get_job_resource(
    job_id: str,
) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM scheduler_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    reservation = None
    reservation_error = None
    if row["resource_reservation_id"]:
        try:
            reservation = fetch_resource_reservation(
                row["resource_reservation_id"]
            )
        except Exception as exc:
            reservation_error = str(exc)

    return {
        "ok": True,
        "contract_version": "leos.job-resource-lifecycle.v1",
        "job_id": row["job_id"],
        "employee_id": row["employee_id"],
        "job_state": row["state"],
        "resource_state": row["resource_state"],
        "resource_decision": parse_json(
            row["resource_decision_json"]
        ),
        "resource_reservation_id": row[
            "resource_reservation_id"
        ],
        "resource_node_id": row["resource_node_id"],
        "resource_gpu_uuid": row["resource_gpu_uuid"],
        "resource_profile_name": row[
            "resource_profile_name"
        ],
        "resource_admitted_at": row[
            "resource_admitted_at"
        ],
        "resource_released_at": row[
            "resource_released_at"
        ],
        "resource_release_reason": row[
            "resource_release_reason"
        ],
        "resource_error": row["resource_error"],
        "reservation": reservation,
        "reservation_error": reservation_error,
    }


@app.get("/resource-history")
def list_resource_history(
    job_id: Optional[str] = None,
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
    ),
) -> dict[str, Any]:
    where = ""
    params: list[Any] = []
    if job_id:
        where = "WHERE job_id=?"
        params.append(job_id)
    params.append(limit)

    with connect() as db:
        rows = db.execute(
            f"""
            SELECT *
            FROM scheduler_resource_history
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "ok": True,
        "contract_version": "leos.resource-lifecycle-history.v1",
        "event_count": len(rows),
        "events": [
            {
                **dict(row),
                "decision": parse_json(
                    row["decision_json"]
                ),
                "details": parse_json(
                    row["details_json"]
                ),
            }
            for row in rows
        ],
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
            FROM scheduler_events
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
                    row["details_json"]
                ),
            }
            for row in rows
        ],
    }
