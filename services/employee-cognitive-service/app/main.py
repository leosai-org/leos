from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from leos_contracts import ContractValidationError, validate_contract
from pydantic import BaseModel, ConfigDict, Field

SERVICE_NAME = "employee-cognitive-service"
SERVICE_VERSION = "0.2.0-dev-preview-v2"
DATA_DIR = Path(os.getenv("EMPLOYEE_COGNITIVE_DATA_DIR", "/data/employee-cognitive"))
DB_PATH = DATA_DIR / "employee-cognitive.db"
RUNTIME_URL = os.getenv(
    "PERSISTENT_EMPLOYEE_RUNTIME_URL",
    "http://persistent-employee-runtime-service:8000",
).rstrip("/")
DISPATCHER_URL = os.getenv(
    "EXECUTION_DISPATCHER_URL",
    "http://execution-dispatcher-service:8000",
).rstrip("/")
AUTO_RUN = os.getenv("EMPLOYEE_COGNITIVE_AUTO_RUN", "true").lower() == "true"
POLL_SECONDS = float(os.getenv("EMPLOYEE_COGNITIVE_POLL_SECONDS", "5"))
MAX_ATTEMPTS = int(os.getenv("EMPLOYEE_COGNITIVE_MAX_ATTEMPTS", "3"))
BACKOFF_SECONDS = float(os.getenv("EMPLOYEE_COGNITIVE_BACKOFF_SECONDS", "5"))
TIMEOUT_SECONDS = float(os.getenv("EMPLOYEE_COGNITIVE_TIMEOUT_SECONDS", "180"))
CLAIM_SECONDS = float(
    os.getenv("EMPLOYEE_COGNITIVE_CLAIM_SECONDS", str(TIMEOUT_SECONDS + 60))
)
TERMINAL_STATES = {"completed", "failed", "cancelled"}
WAITING_STATES = {"waiting", "approval_pending", "order_required", "ambiguous"}
RETRYABLE_RESULTS = {"PROVIDER_ERROR", "TRANSPORT_ERROR"}
_loop_task: Optional[asyncio.Task] = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def migrate() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS cognitive_runs(
                cognitive_run_id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL UNIQUE,
                employee_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                lease_id TEXT,
                workflow_id TEXT,
                step_id TEXT,
                capability_id TEXT NOT NULL,
                assignment_json TEXT NOT NULL,
                state TEXT NOT NULL,
                assignment_started_at TEXT,
                next_attempt_at TEXT,
                waiting_reason_json TEXT,
                terminal_transition_id TEXT,
                terminal_operation TEXT,
                terminal_request_json TEXT,
                terminal_result_json TEXT,
                terminal_conflict_json TEXT,
                claim_token TEXT,
                claim_expires_at TEXT,
                cancel_requested_at TEXT,
                cancel_reason TEXT,
                result_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_cognitive_runs_state
                ON cognitive_runs(state, updated_at);
            CREATE TABLE IF NOT EXISTS cognitive_attempts(
                cognitive_attempt_id TEXT PRIMARY KEY,
                cognitive_run_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                state TEXT NOT NULL,
                execution_id TEXT NOT NULL UNIQUE,
                execution_request_json TEXT NOT NULL,
                execution_result_json TEXT,
                result_applied_at TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(cognitive_run_id, attempt_number)
            );
            CREATE TABLE IF NOT EXISTS cognitive_observations(
                observation_id TEXT PRIMARY KEY,
                cognitive_run_id TEXT NOT NULL,
                cognitive_attempt_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def parse_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:32]
    return f"{prefix}-{digest}"


def claim_run(run_id: str) -> str:
    token = str(uuid.uuid4())
    timestamp = now()
    expires = (
        datetime.now(timezone.utc) + timedelta(seconds=CLAIM_SECONDS)
    ).isoformat()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT state, claim_token, claim_expires_at "
            "FROM cognitive_runs WHERE cognitive_run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Cognitive run not found.")
        if row["state"] in TERMINAL_STATES:
            raise HTTPException(409, "cognitive_run_terminal")
        if (
            row["claim_token"]
            and row["claim_expires_at"]
            and row["claim_expires_at"] > timestamp
        ):
            raise HTTPException(409, "cognitive_run_busy")
        db.execute(
            "UPDATE cognitive_runs SET claim_token=?, claim_expires_at=?, "
            "updated_at=? WHERE cognitive_run_id=?",
            (token, expires, timestamp, run_id),
        )
    return token


def release_run_claim(run_id: str, token: str) -> None:
    with connect() as db:
        db.execute(
            "UPDATE cognitive_runs SET claim_token=NULL, claim_expires_at=NULL, "
            "updated_at=? WHERE cognitive_run_id=? AND claim_token=?",
            (now(), run_id, token),
        )


def require_claim(run_id: str, token: str) -> None:
    with connect() as db:
        row = db.execute(
            "SELECT claim_token FROM cognitive_runs WHERE cognitive_run_id=?",
            (run_id,),
        ).fetchone()
    if row is None or row["claim_token"] != token:
        raise HTTPException(409, "cognitive_run_claim_lost")


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment: dict[str, Any]


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = "cognitive_run_cancelled"


async def request_json(
    method: str, url: str, payload: Optional[dict[str, Any]] = None
) -> tuple[int, dict[str, Any]]:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.request(method, url, json=payload)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    return response.status_code, body


def create_run_from_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
    required = ("assignment_id", "employee_id", "job_id", "capability_id")
    if any(not assignment.get(field) for field in required):
        raise HTTPException(422, "Assignment lacks required cognitive correlation.")
    timestamp = now()
    run_id = stable_id("cognitive-run", assignment["assignment_id"])
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT * FROM cognitive_runs WHERE assignment_id=?",
            (assignment["assignment_id"],),
        ).fetchone()
        if existing:
            return dict(existing)
        try:
            db.execute(
                """
                INSERT INTO cognitive_runs(
                cognitive_run_id, assignment_id, employee_id, job_id, lease_id,
                workflow_id, step_id, capability_id, assignment_json, state,
                created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'run_created', ?, ?)
                """,
                (
                    run_id, assignment["assignment_id"], assignment["employee_id"],
                    assignment["job_id"], assignment.get("lease_id"),
                    assignment.get("workflow_id"), assignment.get("step_id"),
                    assignment["capability_id"], json.dumps(assignment),
                    timestamp, timestamp,
                ),
            )
        except sqlite3.IntegrityError:
            existing = db.execute(
                "SELECT * FROM cognitive_runs WHERE assignment_id=?",
                (assignment["assignment_id"],),
            ).fetchone()
            if existing:
                return dict(existing)
            raise HTTPException(409, "cognitive_run_identity_conflict")
    return get_run_row(run_id)


def get_run_row(run_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM cognitive_runs WHERE cognitive_run_id=?", (run_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Cognitive run not found.")
    return dict(row)


async def discover_assignments() -> dict[str, Any]:
    status, body = await request_json(
        "GET", f"{RUNTIME_URL}/assignments?state=assigned&limit=500"
    )
    if status >= 400:
        raise HTTPException(503, {"message": "Assignment discovery failed.", "response": body})
    created = 0
    for assignment in body.get("assignments", []):
        with connect() as db:
            exists = db.execute(
                "SELECT 1 FROM cognitive_runs WHERE assignment_id=?",
                (assignment.get("assignment_id"),),
            ).fetchone()
        if not exists:
            create_run_from_assignment(assignment)
            created += 1
    return {"ok": True, "discovered_count": created}


async def start_assignment_once(run: dict[str, Any], claim_token: str) -> bool:
    if run["assignment_started_at"]:
        return True
    require_claim(run["cognitive_run_id"], claim_token)
    try:
        status, body = await request_json(
            "GET", f"{RUNTIME_URL}/assignments?limit=500"
        )
    except Exception:
        status, body = 503, {}
    if status >= 400:
        with connect() as db:
            db.execute(
                "UPDATE cognitive_runs SET state='waiting', "
                "waiting_reason_json=?, updated_at=? WHERE cognitive_run_id=?",
                (
                    json.dumps({
                        "status": "ASSIGNMENT_START_RECONCILIATION_REQUIRED"
                    }),
                    now(), run["cognitive_run_id"],
                ),
            )
        return False
    assignment = next(
        (
            item for item in body.get("assignments", [])
            if item.get("assignment_id") == run["assignment_id"]
        ),
        None,
    )
    if assignment is None:
        with connect() as db:
            db.execute(
                "UPDATE cognitive_runs SET state='waiting', "
                "waiting_reason_json=?, updated_at=? WHERE cognitive_run_id=?",
                (
                    json.dumps({"status": "ASSIGNMENT_STATE_UNAVAILABLE"}),
                    now(), run["cognitive_run_id"],
                ),
            )
        return False
    assignment_state = assignment.get("state")
    if assignment_state == "running":
        pass
    elif assignment_state == "assigned":
        require_claim(run["cognitive_run_id"], claim_token)
        try:
            status, body = await request_json(
                "POST",
                f"{RUNTIME_URL}/assignments/{run['assignment_id']}/start",
                {},
            )
        except Exception:
            with connect() as db:
                db.execute(
                    "UPDATE cognitive_runs SET state='run_created', "
                    "waiting_reason_json=?, updated_at=? "
                    "WHERE cognitive_run_id=?",
                    (
                        json.dumps({
                            "status": "ASSIGNMENT_START_RECONCILIATION_REQUIRED"
                        }),
                        now(), run["cognitive_run_id"],
                    ),
                )
            return False
        if status >= 400:
            raise HTTPException(
                409, {"message": "Assignment start rejected.", "response": body}
            )
    elif assignment_state in {"complete", "completed", "failed", "cancelled"}:
        cognitive_state = {
            "complete": "completed",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }[assignment_state]
        with connect() as db:
            db.execute(
                "UPDATE cognitive_runs SET state=?, completed_at=?, "
                "updated_at=? WHERE cognitive_run_id=?",
                (cognitive_state, now(), now(), run["cognitive_run_id"]),
            )
        return False
    else:
        with connect() as db:
            db.execute(
                "UPDATE cognitive_runs SET state='waiting', "
                "waiting_reason_json=?, updated_at=? WHERE cognitive_run_id=?",
                (
                    json.dumps({
                        "status": "ASSIGNMENT_STATE_UNRECOGNIZED",
                        "assignment_state": assignment_state,
                    }),
                    now(), run["cognitive_run_id"],
                ),
            )
        return False
    with connect() as db:
        db.execute(
            "UPDATE cognitive_runs SET assignment_started_at=COALESCE("
            "assignment_started_at, ?), started_at=COALESCE(started_at, ?), "
            "state='running', updated_at=? WHERE cognitive_run_id=?",
            (now(), now(), now(), run["cognitive_run_id"]),
        )
    return True


async def build_context(run: dict[str, Any]) -> dict[str, Any]:
    status, body = await request_json(
        "GET", f"{RUNTIME_URL}/employees/{run['employee_id']}"
    )
    employee = body.get("employee", {}) if status < 400 else {}
    assignment = parse_json(run.get("assignment_json"), {})
    return {
        "employee": employee,
        "assignment": assignment,
    }


def build_execution_request(
    run: dict[str, Any],
    attempt_id: str,
    execution_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    trace = {
        "contract_version": "leos.execution-correlation.v1",
        "job_id": run["job_id"],
        "employee_id": run["employee_id"],
        "assignment_id": run["assignment_id"],
        "cognitive_run_id": run["cognitive_run_id"],
        "cognitive_attempt_id": attempt_id,
        "execution_id": execution_id,
    }
    for field in ("lease_id", "workflow_id", "step_id"):
        if run.get(field):
            trace[field] = run[field]
    assignment = context.get("assignment", {})
    raw_input = assignment.get("payload", {})
    if not isinstance(raw_input, dict):
        raw_input = {}
    execution_input = dict(raw_input)
    if not isinstance(execution_input, dict):
        execution_input = {}
    policy = execution_input.pop("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    execution_input = {
        **execution_input,
        "assignment_id": run["assignment_id"],
    }
    request = {
        "contract_version": "leos.execution.v1",
        "execution_id": execution_id,
        "capability_id": run["capability_id"],
        "requester": {"type": "employee", "id": run["employee_id"]},
        "input": execution_input,
        "context": context,
        "policy": {**policy, "idempotency_key": execution_id},
        "trace": trace,
    }
    try:
        validate_contract("leos.execution.v1", request)
    except (ContractValidationError, KeyError) as exc:
        raise HTTPException(422, f"Canonical execution request invalid: {exc}") from exc
    return request


def next_attempt(
    run: dict[str, Any], context: dict[str, Any], claim_token: str
) -> dict[str, Any]:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        claimed = db.execute(
            "SELECT claim_token, terminal_transition_id, cancel_requested_at "
            "FROM cognitive_runs WHERE cognitive_run_id=?",
            (run["cognitive_run_id"],),
        ).fetchone()
        if claimed is None or claimed["claim_token"] != claim_token:
            raise HTTPException(409, "cognitive_run_claim_lost")
        if claimed["terminal_transition_id"] or claimed["cancel_requested_at"]:
            raise HTTPException(409, "cognitive_run_terminal_fenced")
        number = db.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) n "
            "FROM cognitive_attempts WHERE cognitive_run_id=?",
            (run["cognitive_run_id"],),
        ).fetchone()["n"] + 1
        attempt_id = stable_id(
            "cognitive-attempt", run["cognitive_run_id"], str(number)
        )
        execution_id = stable_id("execution", attempt_id, run["capability_id"])
        request = build_execution_request(
            run, attempt_id, execution_id, context
        )
        timestamp = now()
        db.execute(
            """
            INSERT INTO cognitive_attempts(
                cognitive_attempt_id, cognitive_run_id, attempt_number, state,
                execution_id, execution_request_json, created_at, updated_at
            ) VALUES(?, ?, ?, 'created', ?, ?, ?, ?)
            """,
            (
                attempt_id, run["cognitive_run_id"], number, execution_id,
                json.dumps(request), timestamp, timestamp,
            ),
        )
    return {
        "cognitive_attempt_id": attempt_id,
        "attempt_number": number,
        "execution_id": execution_id,
        "request": request,
    }


def persist_observation(
    run_id: str, attempt: dict[str, Any], result: dict[str, Any]
) -> None:
    try:
        validate_contract("leos.execution-result.v1", result)
    except (ContractValidationError, KeyError) as exc:
        raise HTTPException(502, f"Dispatcher returned invalid canonical result: {exc}") from exc
    if result["execution_id"] != attempt["execution_id"]:
        raise HTTPException(502, "Dispatcher execution identity mismatch.")
    timestamp = now()
    with connect() as db:
        db.execute(
            "UPDATE cognitive_attempts SET state='observed', "
            "execution_result_json=?, completed_at=?, updated_at=? "
            "WHERE cognitive_attempt_id=?",
            (
                json.dumps(result), timestamp, timestamp,
                attempt["cognitive_attempt_id"],
            ),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO cognitive_observations(
                observation_id, cognitive_run_id, cognitive_attempt_id,
                execution_id, status, result_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stable_id("observation", attempt["execution_id"]),
                run_id, attempt["cognitive_attempt_id"], attempt["execution_id"],
                result["status"], json.dumps(result), timestamp,
            ),
        )


async def terminal_assignment(
    run: dict[str, Any], operation: str, reason: dict[str, Any],
    claim_token: str, result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    require_claim(run["cognitive_run_id"], claim_token)
    transition_id = run.get("terminal_transition_id") or stable_id(
        "assignment-terminal", run["cognitive_run_id"], operation
    )
    existing_payload = parse_json(run.get("terminal_request_json"), None)
    payload = existing_payload or {
        "contract_version": "leos.assignment-terminal-transition.v1",
        "transition_id": transition_id,
        "cognitive_run_id": run["cognitive_run_id"],
        "reason": reason,
        "result": result or {},
    }
    if existing_payload and run.get("terminal_operation") != operation:
        raise HTTPException(409, "terminal_transition_conflict")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT claim_token, terminal_operation FROM cognitive_runs "
            "WHERE cognitive_run_id=?",
            (run["cognitive_run_id"],),
        ).fetchone()
        if current["claim_token"] != claim_token:
            raise HTTPException(409, "cognitive_run_claim_lost")
        if current["terminal_operation"] not in {None, operation}:
            raise HTTPException(409, "terminal_transition_conflict")
        db.execute(
            "UPDATE cognitive_runs SET terminal_transition_id=?, "
            "terminal_operation=?, terminal_request_json=?, updated_at=? "
            "WHERE cognitive_run_id=?",
            (
                transition_id, operation, json.dumps(payload), now(),
                run["cognitive_run_id"],
            ),
        )
    status, body = await request_json(
        "POST",
        f"{RUNTIME_URL}/assignments/{run['assignment_id']}/{operation}",
        payload,
    )
    if status >= 400:
        if status == 409:
            with connect() as db:
                db.execute(
                    "UPDATE cognitive_runs SET state='waiting', "
                    "terminal_conflict_json=?, waiting_reason_json=?, "
                    "updated_at=? WHERE cognitive_run_id=?",
                    (
                        json.dumps(body),
                        json.dumps({
                            "status": "TERMINAL_TRANSITION_CONFLICT",
                            "transition_id": transition_id,
                        }),
                        now(), run["cognitive_run_id"],
                    ),
                )
        raise HTTPException(
            409,
            {
                "message": "Persistent Runtime rejected terminal transition.",
                "transition_id": transition_id,
                "response": body,
            },
        )
    with connect() as db:
        db.execute(
            "UPDATE cognitive_runs SET terminal_result_json=?, updated_at=? "
            "WHERE cognitive_run_id=?",
            (json.dumps(body), now(), run["cognitive_run_id"]),
        )
    return body


async def reconcile_attempt(run: dict[str, Any]) -> Optional[dict[str, Any]]:
    with connect() as db:
        attempt = db.execute(
            "SELECT * FROM cognitive_attempts WHERE cognitive_run_id=? "
            "AND execution_result_json IS NULL ORDER BY attempt_number DESC LIMIT 1",
            (run["cognitive_run_id"],),
        ).fetchone()
    if attempt is None:
        return None
    status, body = await request_json(
        "GET", f"{DISPATCHER_URL}/executions/{attempt['execution_id']}"
    )
    if status == 404:
        return {
            "_pending_reconciliation": True,
            "execution_id": attempt["execution_id"],
        }
    if status >= 400:
        raise HTTPException(503, "Dispatcher reconciliation failed.")
    execution_record = body.get("execution", body)
    result = execution_record.get("result", execution_record)
    attempt_data = {
        "cognitive_attempt_id": attempt["cognitive_attempt_id"],
        "execution_id": attempt["execution_id"],
    }
    persist_observation(run["cognitive_run_id"], attempt_data, result)
    return result


async def apply_result(
    run: dict[str, Any], attempt: dict[str, Any], result: dict[str, Any],
    claim_token: str,
) -> dict[str, Any]:
    require_claim(run["cognitive_run_id"], claim_token)
    status = result["status"]
    timestamp = now()
    if status == "SUCCESS":
        await terminal_assignment(
            run, "complete", {"code": "cognitive_run_completed"},
            claim_token,
            result=result.get("normalized_result", {}),
        )
        state, error, waiting = "completed", None, None
    elif status == "APPROVAL_PENDING":
        state, error = "approval_pending", None
        waiting = {"status": status, "approval_requirement_ref": result.get("approval_requirement_ref")}
    elif status == "GOVERNED_ORDER_REQUIRED":
        state, error = "order_required", None
        waiting = {"status": status, "resolution_ref": result["resolution_ref"]}
    elif status == "AMBIGUOUS_OUTCOME":
        state = "waiting"
        error = result.get("error")
        waiting = {"status": status, "requires_explicit_reconciliation": True}
    elif status in RETRYABLE_RESULTS:
        state = "waiting"
        error = result.get("error")
        waiting = {
            "status": "COGNITIVE_DECISION_REQUIRED",
            "execution_status": status,
            "automatic_replay": False,
        }
    else:
        await terminal_assignment(
            run, "fail",
            {
                "code": status.lower(),
                "message": "Cognitive execution reached a terminal non-success outcome.",
            },
            claim_token,
        )
        state = "failed"
        error = result.get("error") or {"code": status.lower()}
        waiting = None
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT claim_token, terminal_operation FROM cognitive_runs "
            "WHERE cognitive_run_id=?",
            (run["cognitive_run_id"],),
        ).fetchone()
        if current["claim_token"] != claim_token:
            raise HTTPException(409, "cognitive_run_claim_lost")
        expected_operation = {
            "completed": "complete",
            "failed": "fail",
        }.get(state)
        if current["terminal_operation"] not in {None, expected_operation}:
            raise HTTPException(409, "terminal_transition_conflict")
        next_attempt_at = (
            waiting.get("next_attempt_at")
            if state == "retry_wait" and waiting else None
        )
        db.execute(
            "UPDATE cognitive_runs SET state=?, waiting_reason_json=?, "
            "next_attempt_at=?, result_json=?, error_json=?, completed_at=?, updated_at=? "
            "WHERE cognitive_run_id=?",
            (
                state, json.dumps(waiting) if waiting else None,
                next_attempt_at,
                json.dumps(result),
                json.dumps(error) if error else None,
                timestamp if state in TERMINAL_STATES else None,
                timestamp, run["cognitive_run_id"],
            ),
        )
        db.execute(
            "UPDATE cognitive_attempts SET result_applied_at=?, updated_at=? "
            "WHERE cognitive_attempt_id=? AND result_applied_at IS NULL",
            (timestamp, timestamp, attempt["cognitive_attempt_id"]),
        )
    return {
        "ok": state == "completed",
        "cognitive_run_id": run["cognitive_run_id"],
        "state": state,
        "execution_id": attempt["execution_id"],
        "execution_status": status,
    }


async def execute_run(run_id: str) -> dict[str, Any]:
    existing = get_run_row(run_id)
    if existing["state"] in TERMINAL_STATES:
        return {
            "ok": True,
            "cognitive_run_id": run_id,
            "state": existing["state"],
            "changed": False,
        }
    token = claim_run(run_id)
    try:
        return await execute_claimed_run(run_id, token)
    finally:
        release_run_claim(run_id, token)


def finalize_terminal_acknowledgement(
    run: dict[str, Any], claim_token: str
) -> dict[str, Any]:
    require_claim(run["cognitive_run_id"], claim_token)
    operation = run["terminal_operation"]
    terminal_state = {
        "complete": "completed",
        "fail": "failed",
        "cancel": "cancelled",
    }.get(operation)
    if terminal_state is None:
        raise HTTPException(409, "terminal_acknowledgement_invalid")
    timestamp = now()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute(
            "SELECT claim_token FROM cognitive_runs WHERE cognitive_run_id=?",
            (run["cognitive_run_id"],),
        ).fetchone()
        if current["claim_token"] != claim_token:
            raise HTTPException(409, "cognitive_run_claim_lost")
        db.execute(
            "UPDATE cognitive_runs SET state=?, completed_at=COALESCE("
            "completed_at, ?), updated_at=? WHERE cognitive_run_id=?",
            (
                terminal_state, timestamp, timestamp,
                run["cognitive_run_id"],
            ),
        )
        db.execute(
            "UPDATE cognitive_attempts SET result_applied_at=COALESCE("
            "result_applied_at, ?), updated_at=? WHERE cognitive_attempt_id=("
            "SELECT cognitive_attempt_id FROM cognitive_attempts "
            "WHERE cognitive_run_id=? AND execution_result_json IS NOT NULL "
            "ORDER BY attempt_number DESC LIMIT 1)",
            (timestamp, timestamp, run["cognitive_run_id"]),
        )
    return {
        "ok": terminal_state == "completed",
        "cognitive_run_id": run["cognitive_run_id"],
        "state": terminal_state,
        "changed": True,
    }


async def execute_claimed_run(
    run_id: str, claim_token: str
) -> dict[str, Any]:
    run = get_run_row(run_id)
    if run["terminal_result_json"]:
        return finalize_terminal_acknowledgement(run, claim_token)
    if run["terminal_conflict_json"]:
        return {
            "ok": False,
            "cognitive_run_id": run_id,
            "state": "waiting",
            "changed": False,
            "reason": "TERMINAL_TRANSITION_CONFLICT",
        }
    if run["cancel_requested_at"]:
        reconciled = await reconcile_attempt(run)
        if (
            reconciled is not None
            and reconciled.get("_pending_reconciliation")
        ):
            with connect() as db:
                db.execute(
                    "UPDATE cognitive_runs SET state='waiting', "
                    "waiting_reason_json=?, updated_at=? "
                    "WHERE cognitive_run_id=?",
                    (
                        json.dumps({
                            "status": "CANCELLATION_EXECUTION_RECONCILIATION",
                            "execution_id": reconciled["execution_id"],
                        }),
                        now(), run_id,
                    ),
                )
            return {
                "ok": True,
                "cognitive_run_id": run_id,
                "state": "cancellation_pending",
                "execution_id": reconciled["execution_id"],
            }
        await terminal_assignment(
            run,
            "cancel",
            {
                "code": "cognitive_run_cancelled",
                "message": run["cancel_reason"] or "cancelled",
            },
            claim_token,
        )
        return finalize_terminal_acknowledgement(
            get_run_row(run_id), claim_token
        )

    with connect() as db:
        observed = db.execute(
            "SELECT * FROM cognitive_attempts WHERE cognitive_run_id=? "
            "AND execution_result_json IS NOT NULL "
            "AND result_applied_at IS NULL "
            "ORDER BY attempt_number LIMIT 1",
            (run_id,),
        ).fetchone()
    if observed is not None:
        result = parse_json(observed["execution_result_json"], {})
        return await apply_result(
            run, dict(observed), result, claim_token
        )

    if run["terminal_transition_id"]:
        operation = run["terminal_operation"]
        await terminal_assignment(
            run, operation, {"code": f"reconcile_{operation}"},
            claim_token,
        )
        return finalize_terminal_acknowledgement(
            get_run_row(run_id), claim_token
        )
    reconciled = await reconcile_attempt(run)
    if reconciled is not None:
        if reconciled.get("_pending_reconciliation"):
            with connect() as db:
                db.execute(
                    "UPDATE cognitive_runs SET state='waiting', "
                    "waiting_reason_json=?, updated_at=? "
                    "WHERE cognitive_run_id=?",
                    (
                        json.dumps({
                            "status": "EXECUTION_RECONCILIATION_REQUIRED",
                            "execution_id": reconciled["execution_id"],
                        }),
                        now(), run_id,
                    ),
                )
            return {
                "ok": False,
                "cognitive_run_id": run_id,
                "state": "waiting",
                "changed": True,
                "execution_id": reconciled["execution_id"],
            }
        with connect() as db:
            attempt_row = db.execute(
                "SELECT * FROM cognitive_attempts WHERE execution_id=?",
                (reconciled["execution_id"],),
            ).fetchone()
        return await apply_result(
            run, dict(attempt_row), reconciled, claim_token
        )
    if run["state"] in TERMINAL_STATES | WAITING_STATES:
        return {
            "ok": True,
            "cognitive_run_id": run_id,
            "state": run["state"],
            "changed": False,
        }
    started = await start_assignment_once(run, claim_token)
    if not started:
        current = get_run_row(run_id)
        return {
            "ok": current["state"] in TERMINAL_STATES,
            "cognitive_run_id": run_id,
            "state": current["state"],
            "changed": True,
        }
    run = get_run_row(run_id)
    context = await build_context(run)
    attempt = next_attempt(run, context, claim_token)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute(
            "UPDATE cognitive_attempts SET state='dispatched', updated_at=? "
            "WHERE cognitive_attempt_id=? AND EXISTS("
            "SELECT 1 FROM cognitive_runs WHERE cognitive_run_id=? "
            "AND claim_token=? AND cancel_requested_at IS NULL "
            "AND terminal_transition_id IS NULL)",
            (
                now(), attempt["cognitive_attempt_id"], run_id, claim_token,
            ),
        )
    if cursor.rowcount != 1:
        current = get_run_row(run_id)
        if current["cancel_requested_at"]:
            await terminal_assignment(
                current,
                "cancel",
                {
                    "code": "cognitive_run_cancelled",
                    "message": current["cancel_reason"] or "cancelled",
                },
                claim_token,
            )
            return finalize_terminal_acknowledgement(
                get_run_row(run_id), claim_token
            )
        raise HTTPException(409, "cognitive_run_terminal_fenced")
    status, result = await request_json(
        "POST", f"{DISPATCHER_URL}/execute", attempt["request"]
    )
    if status >= 400:
        raise HTTPException(502, {"message": "Dispatcher request failed.", "response": result})
    persist_observation(run_id, attempt, result)
    current = get_run_row(run_id)
    if current["cancel_requested_at"]:
        await terminal_assignment(
            current,
            "cancel",
            {
                "code": "cognitive_run_cancelled",
                "message": current["cancel_reason"] or "cancelled",
            },
            claim_token,
        )
        return finalize_terminal_acknowledgement(
            get_run_row(run_id), claim_token
        )
    return await apply_result(run, attempt, result, claim_token)


async def cancel_run(run_id: str, reason: str) -> dict[str, Any]:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        run = db.execute(
            "SELECT * FROM cognitive_runs WHERE cognitive_run_id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise HTTPException(404, "Cognitive run not found.")
        if run["state"] in TERMINAL_STATES:
            raise HTTPException(409, "Cognitive run is already terminal.")
        if run["terminal_operation"] not in {None, "cancel"}:
            raise HTTPException(409, "terminal_transition_conflict")
        db.execute(
            "UPDATE cognitive_runs SET cancel_requested_at=COALESCE("
            "cancel_requested_at, ?), cancel_reason=COALESCE(cancel_reason, ?), "
            "updated_at=? WHERE cognitive_run_id=?",
            (now(), reason, now(), run_id),
        )
    try:
        token = claim_run(run_id)
    except HTTPException as exc:
        if exc.detail == "cognitive_run_busy":
            return {
                "ok": True,
                "cognitive_run_id": run_id,
                "state": "cancellation_pending",
            }
        raise
    try:
        return await execute_claimed_run(run_id, token)
    finally:
        release_run_claim(run_id, token)


async def tick() -> dict[str, Any]:
    discovery = await discover_assignments()
    with connect() as db:
        rows = db.execute(
            "SELECT cognitive_run_id FROM cognitive_runs "
            "WHERE state IN ('run_created', 'retry_wait') "
            "OR (cancel_requested_at IS NOT NULL "
            "AND state NOT IN ('completed', 'failed', 'cancelled')) "
            "ORDER BY created_at"
        ).fetchall()
    results = []
    for row in rows:
        results.append(await execute_run(row["cognitive_run_id"]))
    return {"ok": True, "discovery": discovery, "selected_count": len(rows), "results": results}


async def loop() -> None:
    while True:
        try:
            if AUTO_RUN:
                await tick()
        except Exception:
            pass
        await asyncio.sleep(POLL_SECONDS)


migrate()
app = FastAPI(title="LEOS Employee Cognitive Service", version=SERVICE_VERSION)


@app.on_event("startup")
async def startup() -> None:
    global _loop_task
    migrate()
    if AUTO_RUN and (_loop_task is None or _loop_task.done()):
        _loop_task = asyncio.create_task(loop())


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as db:
        counts = {
            row["state"]: row["count"]
            for row in db.execute(
                "SELECT state, COUNT(*) count FROM cognitive_runs GROUP BY state"
            )
        }
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "states": counts,
        "dispatcher_url": DISPATCHER_URL,
        "persistent_runtime_url": RUNTIME_URL,
    }


@app.post("/runs")
def create_run(request: RunCreate) -> dict[str, Any]:
    return {"ok": True, "run": create_run_from_assignment(request.assignment)}


@app.post("/runs/{run_id}/execute")
async def manual_execute(run_id: str) -> dict[str, Any]:
    return await execute_run(run_id)


@app.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, request: ResumeRequest) -> dict[str, Any]:
    run = get_run_row(run_id)
    if run["state"] not in {"approval_pending", "order_required", "waiting"}:
        raise HTTPException(409, "Cognitive run is not waiting.")
    raise HTTPException(
        409,
        {
            "code": "governed_resume_evidence_required",
            "state": run["state"],
            "message": (
                "This waiting state cannot be resumed from a caller reason. "
                "A future governed evidence contract is required."
            ),
        },
    )


@app.post("/runs/{run_id}/cancel")
async def manual_cancel(run_id: str, request: CancelRequest) -> dict[str, Any]:
    return await cancel_run(run_id, request.reason)


@app.post("/tick")
async def manual_tick() -> dict[str, Any]:
    return await tick()


@app.get("/runs")
def list_runs(
    state: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    params: list[Any] = []
    where = ""
    if state:
        where = "WHERE state=?"
        params.append(state)
    params.append(limit)
    with connect() as db:
        rows = db.execute(
            f"SELECT * FROM cognitive_runs {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
    return {"ok": True, "runs": [dict(row) for row in rows]}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = get_run_row(run_id)
    with connect() as db:
        attempts = db.execute(
            "SELECT * FROM cognitive_attempts WHERE cognitive_run_id=? "
            "ORDER BY attempt_number",
            (run_id,),
        ).fetchall()
    return {
        "ok": True,
        "run": run,
        "attempts": [dict(row) for row in attempts],
    }
