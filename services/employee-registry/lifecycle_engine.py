from __future__ import annotations

import copy
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Iterator

EMPLOYEE_CONTRACT = "leos.employee-definition.v2"
LIFECYCLE_CONTRACT = "leos.employee-lifecycle.v1"
HISTORY_CONTRACT = "leos.employee-lifecycle-history.v1"
ELIGIBILITY_CONTRACT = "leos.employee-execution-eligibility.v1"
RESOURCE_PROFILE_CONTRACT = "leos.employee-resource-profile.v1"

PRIORITY_WEIGHTS = {
    "background": 10,
    "normal": 50,
    "elevated": 70,
    "business-critical": 90,
    "emergency": 100,
}

LIFECYCLE_STATES = {
    "draft",
    "validated",
    "active",
    "paused",
    "disabled",
    "archived",
}

TRANSITIONS = {
    "draft": {"validated", "archived"},
    "validated": {"active", "disabled", "archived"},
    "active": {"paused", "disabled", "archived"},
    "paused": {"active", "disabled", "archived"},
    "disabled": {"active", "archived"},
    "archived": set(),
}

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CAPABILITY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class EmployeeLifecycleError(RuntimeError):
    pass


class EmployeeNotFoundError(EmployeeLifecycleError):
    pass


class EmployeeConflictError(EmployeeLifecycleError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def nonempty(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EmployeeLifecycleError(f"{field} must be a non-empty string.")
    return text


def integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EmployeeLifecycleError(f"{field} must be an integer.") from exc
    if minimum is not None and result < minimum:
        raise EmployeeLifecycleError(f"{field} must be at least {minimum}.")
    return result


def number(value: Any, field: str, *, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EmployeeLifecycleError(f"{field} must be numeric.") from exc
    if minimum is not None and result < minimum:
        raise EmployeeLifecycleError(f"{field} must be at least {minimum}.")
    return result


def normalize_capabilities(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise EmployeeLifecycleError("capabilities must be a list.")
    result: list[str] = []
    for item in value:
        capability = nonempty(item, "capability").lower()
        if not CAPABILITY_PATTERN.fullmatch(capability):
            raise EmployeeLifecycleError(
                f"Invalid capability identifier: {capability}"
            )
        if capability not in result:
            result.append(capability)
    if not result:
        raise EmployeeLifecycleError("At least one capability is required.")
    return result


def normalize_windows(value: Any) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise EmployeeLifecycleError("schedule.windows must be a list.")
    result = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise EmployeeLifecycleError(
                f"schedule.windows[{index}] must be an object."
            )
        weekdays = raw.get("weekdays", list(range(7)))
        if not isinstance(weekdays, list) or not weekdays:
            raise EmployeeLifecycleError(
                f"schedule.windows[{index}].weekdays must be a non-empty list."
            )
        days = sorted({integer(item, "weekday", minimum=0) for item in weekdays})
        if any(day > 6 for day in days):
            raise EmployeeLifecycleError(
                "Schedule weekdays use Monday=0 through Sunday=6."
            )
        start = nonempty(raw.get("start", "00:00"), "schedule window start")
        end = nonempty(raw.get("end", "23:59"), "schedule window end")
        try:
            time.fromisoformat(start)
            time.fromisoformat(end)
        except ValueError as exc:
            raise EmployeeLifecycleError(
                "Schedule window start and end must be ISO local times."
            ) from exc
        timezone_name = str(raw.get("timezone", "UTC"))
        if timezone_name != "UTC":
            raise EmployeeLifecycleError(
                "Phase 52.2 supports UTC schedule windows only."
            )
        result.append(
            {
                "weekdays": days,
                "start": start,
                "end": end,
                "timezone": "UTC",
            }
        )
    return result


def normalize_schedule(value: Any) -> dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, dict) else {}
    mode = str(raw.get("mode", "always")).lower()
    if mode not in {"always", "windows", "disabled"}:
        raise EmployeeLifecycleError(
            "schedule.mode must be always, windows, or disabled."
        )
    timezone_name = str(raw.get("timezone", "UTC"))
    if timezone_name != "UTC":
        raise EmployeeLifecycleError("Phase 52.2 supports UTC schedules only.")
    windows = normalize_windows(raw.get("windows", []))
    if mode == "windows" and not windows:
        raise EmployeeLifecycleError(
            "A windows schedule requires at least one execution window."
        )
    return {
        "mode": mode,
        "timezone": "UTC",
        "windows": windows,
    }


def normalize_model_preferences(value: Any) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise EmployeeLifecycleError("model_preferences must be a list.")
    result = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            provider = "local"
            model = nonempty(item, "model")
            priority = index + 1
        elif isinstance(item, dict):
            provider = nonempty(item.get("provider", "local"), "provider")
            model = nonempty(item.get("model"), "model")
            priority = integer(
                item.get("priority", index + 1),
                "model preference priority",
                minimum=1,
            )
        else:
            raise EmployeeLifecycleError(
                "model_preferences entries must be strings or objects."
            )
        result.append(
            {
                "provider": provider,
                "model": model,
                "priority": priority,
            }
        )
    return sorted(
        result,
        key=lambda item: (item["priority"], item["provider"], item["model"]),
    )


def normalize_resource_profile(
    value: Any,
    *,
    priority_class: str,
    model_preferences: list[dict[str, Any]],
    schedule: dict[str, Any],
) -> dict[str, Any]:
    raw = dict(value or {}) if isinstance(value, dict) else {}
    resources = raw.get("resource_profile", raw.get("resources", {}))
    resources = dict(resources or {}) if isinstance(resources, dict) else {}
    execution = raw.get("execution_policy", {})
    execution = dict(execution or {}) if isinstance(execution, dict) else {}
    affinity = raw.get("node_affinity", {})
    affinity = dict(affinity or {}) if isinstance(affinity, dict) else {}
    fallbacks = raw.get("fallback_profiles", [])
    if not isinstance(fallbacks, list):
        raise EmployeeLifecycleError("fallback_profiles must be a list.")

    normalized_fallbacks = []
    for index, item in enumerate(fallbacks):
        if not isinstance(item, dict):
            raise EmployeeLifecycleError("Fallback profiles must be objects.")
        fallback_resources = dict(item.get("resource_profile", {}) or {})
        normalized_fallbacks.append(
            {
                "name": nonempty(
                    item.get("name", f"fallback-{index + 1}"),
                    "fallback name",
                ),
                "resource_profile": {
                    "cpu_cores_min": number(
                        fallback_resources.get("cpu_cores_min", 1),
                        "fallback cpu_cores_min",
                        minimum=0,
                    ),
                    "memory_mb_min": integer(
                        fallback_resources.get("memory_mb_min", 512),
                        "fallback memory_mb_min",
                        minimum=0,
                    ),
                    "gpu_required": bool(
                        fallback_resources.get("gpu_required", False)
                    ),
                    "vram_mb_min": integer(
                        fallback_resources.get("vram_mb_min", 0),
                        "fallback vram_mb_min",
                        minimum=0,
                    ),
                    "gpu_uuid_preferences": [
                        nonempty(item, "gpu uuid")
                        for item in fallback_resources.get(
                            "gpu_uuid_preferences", []
                        )
                    ],
                },
                "provider_preferences": normalize_model_preferences(
                    item.get("provider_preferences", [])
                ),
            }
        )

    gpu_preferences = resources.get("gpu_uuid_preferences", [])
    if not isinstance(gpu_preferences, list):
        raise EmployeeLifecycleError(
            "resource_profile.gpu_uuid_preferences must be a list."
        )
    required_labels = affinity.get("required_labels", {})
    preferred_labels = affinity.get("preferred_labels", {})
    if not isinstance(required_labels, dict) or not isinstance(
        preferred_labels, dict
    ):
        raise EmployeeLifecycleError("node_affinity labels must be objects.")

    vram = integer(
        resources.get("vram_mb_min", 0),
        "resource_profile.vram_mb_min",
        minimum=0,
    )
    gpu_required = bool(resources.get("gpu_required", False) or vram > 0)

    return {
        "contract_version": RESOURCE_PROFILE_CONTRACT,
        "enabled": bool(raw.get("enabled", True)),
        "priority_class": priority_class,
        "priority_weight": integer(
            raw.get("priority_weight", PRIORITY_WEIGHTS[priority_class]),
            "priority_weight",
            minimum=0,
        ),
        "resource_profile": {
            "cpu_cores_min": number(
                resources.get("cpu_cores_min", 1),
                "resource_profile.cpu_cores_min",
                minimum=0,
            ),
            "memory_mb_min": integer(
                resources.get("memory_mb_min", 512),
                "resource_profile.memory_mb_min",
                minimum=0,
            ),
            "gpu_required": gpu_required,
            "vram_mb_min": vram,
            "gpu_uuid_preferences": [
                nonempty(item, "gpu uuid") for item in gpu_preferences
            ],
        },
        "execution_policy": {
            "max_concurrent_jobs": integer(
                execution.get("max_concurrent_jobs", 1),
                "execution_policy.max_concurrent_jobs",
                minimum=1,
            ),
            "preemptible": bool(execution.get("preemptible", True)),
            "allow_preemption": bool(
                execution.get("allow_preemption", False)
            ),
            "queue_when_unavailable": bool(
                execution.get("queue_when_unavailable", True)
            ),
            "reservation_ttl_seconds": integer(
                execution.get("reservation_ttl_seconds", 3600),
                "execution_policy.reservation_ttl_seconds",
                minimum=30,
            ),
        },
        "provider_preferences": copy.deepcopy(model_preferences),
        "node_affinity": {
            "required_labels": {
                str(key): str(value) for key, value in required_labels.items()
            },
            "preferred_labels": {
                str(key): str(value) for key, value in preferred_labels.items()
            },
        },
        "allowed_execution_windows": (
            copy.deepcopy(schedule["windows"])
            if schedule["mode"] == "windows"
            else []
        ),
        "fallback_profiles": normalized_fallbacks,
        "metadata": (
            copy.deepcopy(raw.get("metadata", {}))
            if isinstance(raw.get("metadata", {}), dict)
            else {}
        ),
    }


def normalize_definition(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EmployeeLifecycleError("Employee definition must be an object.")
    employee_id = nonempty(payload.get("employee_id"), "employee_id").lower()
    if not ID_PATTERN.fullmatch(employee_id):
        raise EmployeeLifecycleError(
            "employee_id must be lowercase kebab-case."
        )
    priority_class = str(payload.get("priority", "normal")).lower()
    if priority_class not in PRIORITY_WEIGHTS:
        raise EmployeeLifecycleError("Unknown employee priority class.")
    model_preferences = normalize_model_preferences(
        payload.get("model_preferences", payload.get("models", []))
    )
    schedule = normalize_schedule(payload.get("schedule"))
    resource_profile = normalize_resource_profile(
        payload.get("resource_profile"),
        priority_class=priority_class,
        model_preferences=model_preferences,
        schedule=schedule,
    )
    limits = payload.get("limits", {})
    limits = dict(limits or {}) if isinstance(limits, dict) else {}
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise EmployeeLifecycleError("metadata must be an object.")
    runtime = payload.get("runtime", {})
    if not isinstance(runtime, dict):
        raise EmployeeLifecycleError("runtime must be an object.")
    permissions = payload.get("permissions", {})
    if not isinstance(permissions, dict):
        raise EmployeeLifecycleError("permissions must be an object.")

    return {
        "contract_version": EMPLOYEE_CONTRACT,
        "employee_id": employee_id,
        "name": nonempty(payload.get("name"), "name"),
        "description": str(payload.get("description", "")),
        "role": nonempty(payload.get("role"), "role"),
        "department": nonempty(payload.get("department", "general"), "department"),
        "manager": payload.get("manager"),
        "version": str(payload.get("version", "1.0.0")),
        "vendor": str(payload.get("vendor", "")),
        "license": str(payload.get("license", "")),
        "capabilities": normalize_capabilities(payload.get("capabilities", [])),
        "resource_profile": resource_profile,
        "schedule": schedule,
        "priority": priority_class,
        "priority_weight": PRIORITY_WEIGHTS[priority_class],
        "model_preferences": model_preferences,
        "provider_preferences": copy.deepcopy(model_preferences),
        "runtime": copy.deepcopy(runtime),
        "limits": {
            "max_parallel_jobs": integer(
                limits.get(
                    "max_parallel_jobs",
                    resource_profile["execution_policy"]["max_concurrent_jobs"],
                ),
                "limits.max_parallel_jobs",
                minimum=1,
            ),
            "max_runtime_seconds": integer(
                limits.get("max_runtime_seconds", 300),
                "limits.max_runtime_seconds",
                minimum=1,
            ),
            "max_retries": integer(
                limits.get("max_retries", 2),
                "limits.max_retries",
                minimum=0,
            ),
        },
        "permissions": copy.deepcopy(permissions),
        "memory": copy.deepcopy(payload.get("memory", {}))
        if isinstance(payload.get("memory", {}), dict)
        else {},
        "adapters": copy.deepcopy(payload.get("adapters", {}))
        if isinstance(payload.get("adapters", {}), dict)
        else {},
        "metadata": copy.deepcopy(metadata),
    }


def legacy_manifest_to_definition(manifest: dict[str, Any]) -> dict[str, Any]:
    employee = manifest.get("employee", {})
    organization = manifest.get("organization", {})
    models = manifest.get("models", {})
    preferred_models = models.get("preferred", []) if isinstance(models, dict) else []
    limits = manifest.get("limits", {})
    default_status = manifest.get("status", {}).get("default", "available")
    lifecycle = {
        "available": "active",
        "busy": "active",
        "offline": "validated",
        "paused": "paused",
        "disabled": "disabled",
        "training": "paused",
        "updating": "paused",
        "retired": "archived",
    }.get(default_status, "validated")
    max_jobs = int(limits.get("max_parallel_jobs", 1)) if isinstance(limits, dict) else 1
    return {
        "definition": {
            "employee_id": employee.get("id"),
            "name": employee.get("name"),
            "version": employee.get("version", "1.0.0"),
            "description": employee.get("description", ""),
            "vendor": employee.get("vendor", ""),
            "license": employee.get("license", ""),
            "department": organization.get("department", "general"),
            "manager": organization.get("manager"),
            "role": organization.get("role"),
            "capabilities": manifest.get("capabilities", []),
            "runtime": manifest.get("runtime", {}),
            "limits": limits,
            "model_preferences": preferred_models,
            "adapters": manifest.get("adapters", {}),
            "memory": manifest.get("memory", {}),
            "permissions": manifest.get("permissions", {}),
            "schedule": manifest.get("metadata", {}).get(
                "schedule", {"mode": "always"}
            ),
            "priority": manifest.get("metadata", {}).get("priority", "normal"),
            "resource_profile": {
                "execution_policy": {"max_concurrent_jobs": max_jobs},
            },
            "metadata": {
                **manifest.get("metadata", {}),
                "legacy_manifest": manifest,
                "plugin": manifest.get("plugin", {}),
                "compatibility": manifest.get("compatibility", {}),
                "dependencies": manifest.get("dependencies", []),
            },
        },
        "lifecycle_status": lifecycle,
        "operational_status": default_status,
    }


def schedule_allows(schedule: dict[str, Any], requested: datetime) -> bool:
    mode = schedule.get("mode", "always")
    if mode == "disabled":
        return False
    if mode == "always":
        return True
    current = requested.astimezone(timezone.utc)
    current_time = current.time().replace(tzinfo=None)
    for window in schedule.get("windows", []):
        if current.weekday() not in window["weekdays"]:
            continue
        start = time.fromisoformat(window["start"])
        end = time.fromisoformat(window["end"])
        if start <= end and start <= current_time <= end:
            return True
        if start > end and (current_time >= start or current_time <= end):
            return True
    return False


class EmployeeLifecycleEngine:
    def __init__(
        self,
        database: str | Path,
        legacy_json: str | Path | None = None,
    ):
        self.database = Path(database)
        self.legacy_json = Path(legacy_json) if legacy_json else None
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._import_legacy_once()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS employees (
                    employee_id TEXT PRIMARY KEY,
                    lifecycle_status TEXT NOT NULL,
                    operational_status TEXT NOT NULL,
                    health TEXT NOT NULL,
                    availability TEXT NOT NULL,
                    current_jobs INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    validation_state TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    validated_at TEXT,
                    activated_at TEXT,
                    paused_at TEXT,
                    disabled_at TEXT,
                    archived_at TEXT,
                    last_heartbeat_at TEXT
                );
                CREATE TABLE IF NOT EXISTS employee_history (
                    event_id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    actor TEXT NOT NULL,
                    reason TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_employee_history_employee
                    ON employee_history(employee_id, created_at, event_id);
                CREATE TABLE IF NOT EXISTS registry_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def _import_legacy_once(self) -> None:
        if self.legacy_json is None or not self.legacy_json.is_file():
            return
        with self.connection() as connection:
            imported = connection.execute(
                "SELECT value FROM registry_metadata WHERE key='legacy-json-imported'"
            ).fetchone()
            if imported is not None:
                return
        try:
            legacy = json.loads(self.legacy_json.read_text(encoding="utf-8"))
        except Exception:
            legacy = {}
        if isinstance(legacy, dict):
            for employee_id, record in legacy.items():
                try:
                    if isinstance(record, dict) and isinstance(record.get("manifest"), dict):
                        converted = legacy_manifest_to_definition(record["manifest"])
                    else:
                        converted = {
                            "definition": {
                                "employee_id": record.get("employee_id", employee_id),
                                "name": record.get("name", employee_id),
                                "description": record.get("description", ""),
                                "role": record.get("role", "employee"),
                                "department": record.get("department", "general"),
                                "manager": record.get("manager"),
                                "version": record.get("version", "1.0.0"),
                                "vendor": record.get("vendor", ""),
                                "license": record.get("license", ""),
                                "capabilities": record.get("capabilities", ["general.execute"]),
                                "resource_profile": {
                                    "execution_policy": {
                                        "max_concurrent_jobs": record.get("limits", {}).get("max_parallel_jobs", 1)
                                    }
                                },
                                "schedule": record.get("metadata", {}).get("schedule", {"mode": "always"}),
                                "priority": record.get("metadata", {}).get("priority", "normal"),
                                "model_preferences": record.get("models", {}).get("preferred", []),
                                "runtime": record.get("runtime", {}),
                                "limits": record.get("limits", {}),
                                "permissions": record.get("permissions", {}),
                                "memory": record.get("memory", {}),
                                "adapters": record.get("adapters", {}),
                                "metadata": {**record.get("metadata", {}), "legacy_record": record},
                            },
                            "lifecycle_status": {
                                "available": "active",
                                "busy": "active",
                                "paused": "paused",
                                "disabled": "disabled",
                                "retired": "archived",
                            }.get(record.get("status"), "validated"),
                            "operational_status": record.get("status", "unknown"),
                        }
                    self._insert_imported(converted, record)
                except Exception:
                    continue
        with self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO registry_metadata(key,value) VALUES('legacy-json-imported',?)",
                (utc_now(),),
            )

    def _insert_imported(
        self,
        converted: dict[str, Any],
        legacy_record: dict[str, Any],
    ) -> None:
        definition = normalize_definition(converted["definition"])
        employee_id = definition["employee_id"]
        with self.connection() as connection:
            if connection.execute(
                "SELECT 1 FROM employees WHERE employee_id=?", (employee_id,)
            ).fetchone():
                return
            timestamp = utc_now()
            lifecycle = converted.get("lifecycle_status", "validated")
            if lifecycle not in LIFECYCLE_STATES:
                lifecycle = "validated"
            connection.execute(
                """
                INSERT INTO employees VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    employee_id,
                    lifecycle,
                    converted.get("operational_status", "unknown"),
                    legacy_record.get("health", "unknown"),
                    legacy_record.get("availability", "unknown"),
                    max(0, int(legacy_record.get("current_jobs", 0))),
                    1,
                    "valid",
                    canonical_json(definition),
                    legacy_record.get("registered_at", timestamp),
                    timestamp,
                    timestamp,
                    timestamp if lifecycle == "active" else None,
                    timestamp if lifecycle == "paused" else None,
                    timestamp if lifecycle == "disabled" else None,
                    timestamp if lifecycle == "archived" else None,
                    legacy_record.get("last_heartbeat_at"),
                ),
            )
            self._history(
                connection,
                employee_id=employee_id,
                revision=1,
                event_type="employee.legacy-imported",
                from_status=None,
                to_status=lifecycle,
                actor="system",
                reason="legacy-json-migration",
                payload={"source": str(self.legacy_json)},
            )

    def _history(
        self,
        connection: sqlite3.Connection,
        *,
        employee_id: str,
        revision: int,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor: str,
        reason: str | None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO employee_history VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                employee_id,
                revision,
                event_type,
                from_status,
                to_status,
                actor,
                reason,
                canonical_json(payload or {}),
                utc_now(),
            ),
        )
        return event_id

    def validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            definition = normalize_definition(payload)
            return {
                "ok": True,
                "valid": True,
                "contract_version": EMPLOYEE_CONTRACT,
                "errors": [],
                "definition": definition,
            }
        except EmployeeLifecycleError as exc:
            return {
                "ok": True,
                "valid": False,
                "contract_version": EMPLOYEE_CONTRACT,
                "errors": [{"path": "", "message": str(exc)}],
                "definition": None,
            }

    def create(
        self,
        payload: dict[str, Any],
        *,
        actor: str = "system",
        reason: str | None = None,
    ) -> dict[str, Any]:
        definition = normalize_definition(payload)
        employee_id = definition["employee_id"]
        timestamp = utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM employees WHERE employee_id=?", (employee_id,)
            ).fetchone():
                connection.execute("ROLLBACK")
                raise EmployeeConflictError(f"Employee already exists: {employee_id}")
            connection.execute(
                """
                INSERT INTO employees VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    employee_id,
                    "draft",
                    "offline",
                    "unknown",
                    "offline",
                    0,
                    1,
                    "pending",
                    canonical_json(definition),
                    timestamp,
                    timestamp,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            self._history(
                connection,
                employee_id=employee_id,
                revision=1,
                event_type="employee.created",
                from_status=None,
                to_status="draft",
                actor=actor,
                reason=reason,
                payload={"definition": definition},
            )
            connection.execute("COMMIT")
        return self.get(employee_id)

    def _row(self, employee_id: str) -> sqlite3.Row:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM employees WHERE employee_id=?", (employee_id,)
            ).fetchone()
        if row is None:
            raise EmployeeNotFoundError(f"Employee not found: {employee_id}")
        return row

    def _record(self, row: sqlite3.Row) -> dict[str, Any]:
        definition = json.loads(row["definition_json"])
        return {
            **definition,
            "lifecycle_contract": LIFECYCLE_CONTRACT,
            "lifecycle_status": row["lifecycle_status"],
            "status": row["lifecycle_status"],
            "operational_status": row["operational_status"],
            "availability": row["availability"],
            "health": row["health"],
            "current_jobs": row["current_jobs"],
            "revision": row["revision"],
            "validation_state": row["validation_state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "validated_at": row["validated_at"],
            "activated_at": row["activated_at"],
            "paused_at": row["paused_at"],
            "disabled_at": row["disabled_at"],
            "archived_at": row["archived_at"],
            "last_heartbeat_at": row["last_heartbeat_at"],
        }

    def get(self, employee_id: str) -> dict[str, Any]:
        return self._record(self._row(employee_id))

    def list(
        self,
        *,
        department: str | None = None,
        lifecycle_status: str | None = None,
        capability: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM employees ORDER BY employee_id"
            ).fetchall()
        records = [self._record(row) for row in rows]
        if not include_archived:
            records = [
                item for item in records if item["lifecycle_status"] != "archived"
            ]
        if department:
            records = [item for item in records if item["department"] == department]
        if lifecycle_status:
            records = [
                item
                for item in records
                if item["lifecycle_status"] == lifecycle_status
            ]
        if capability:
            records = [
                item for item in records if capability in item["capabilities"]
            ]
        return records

    def validate_existing(
        self,
        employee_id: str,
        *,
        actor: str = "system",
        reason: str | None = None,
    ) -> dict[str, Any]:
        row = self._row(employee_id)
        definition = normalize_definition(json.loads(row["definition_json"]))
        current = row["lifecycle_status"]
        target = "validated" if current == "draft" else current
        timestamp = utc_now()
        revision = int(row["revision"]) + 1
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE employees
                SET lifecycle_status=?, validation_state='valid', definition_json=?,
                    revision=?, validated_at=?, updated_at=?
                WHERE employee_id=?
                """,
                (
                    target,
                    canonical_json(definition),
                    revision,
                    timestamp,
                    timestamp,
                    employee_id,
                ),
            )
            self._history(
                connection,
                employee_id=employee_id,
                revision=revision,
                event_type="employee.validated",
                from_status=current,
                to_status=target,
                actor=actor,
                reason=reason,
                payload={"contract_version": EMPLOYEE_CONTRACT},
            )
            connection.execute("COMMIT")
        return self.get(employee_id)

    def transition(
        self,
        employee_id: str,
        target: str,
        *,
        actor: str = "system",
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = str(target).lower()
        if target not in LIFECYCLE_STATES:
            raise EmployeeLifecycleError(f"Unknown lifecycle state: {target}")
        row = self._row(employee_id)
        current = row["lifecycle_status"]
        if target == current:
            return self._record(row)
        if target not in TRANSITIONS[current]:
            raise EmployeeConflictError(
                f"Invalid employee lifecycle transition: {current} -> {target}"
            )
        if target == "active" and row["validation_state"] != "valid":
            raise EmployeeConflictError(
                "Employee must be validated before activation."
            )
        revision = int(row["revision"]) + 1
        timestamp = utc_now()
        timestamp_column = {
            "active": "activated_at",
            "paused": "paused_at",
            "disabled": "disabled_at",
            "archived": "archived_at",
        }.get(target)
        operational_status = {
            "active": "available",
            "paused": "paused",
            "disabled": "disabled",
            "archived": "offline",
            "validated": "offline",
            "draft": "offline",
        }[target]
        availability = "online" if target == "active" else "offline"
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if timestamp_column:
                connection.execute(
                    f"""
                    UPDATE employees
                    SET lifecycle_status=?, operational_status=?, availability=?,
                        revision=?, updated_at=?, {timestamp_column}=?
                    WHERE employee_id=?
                    """,
                    (
                        target,
                        operational_status,
                        availability,
                        revision,
                        timestamp,
                        timestamp,
                        employee_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE employees
                    SET lifecycle_status=?, operational_status=?, availability=?,
                        revision=?, updated_at=?
                    WHERE employee_id=?
                    """,
                    (
                        target,
                        operational_status,
                        availability,
                        revision,
                        timestamp,
                        employee_id,
                    ),
                )
            self._history(
                connection,
                employee_id=employee_id,
                revision=revision,
                event_type=f"employee.{target}",
                from_status=current,
                to_status=target,
                actor=actor,
                reason=reason,
                payload=payload,
            )
            connection.execute("COMMIT")
        return self.get(employee_id)

    def update_assignments(
        self,
        employee_id: str,
        changes: dict[str, Any],
        *,
        actor: str = "system",
        reason: str | None = None,
    ) -> dict[str, Any]:
        row = self._row(employee_id)
        if row["lifecycle_status"] == "archived":
            raise EmployeeConflictError("Archived employees cannot be modified.")
        definition = json.loads(row["definition_json"])
        allowed = {
            "role",
            "department",
            "manager",
            "capabilities",
            "resource_profile",
            "schedule",
            "priority",
            "model_preferences",
            "runtime",
            "limits",
            "permissions",
            "memory",
            "adapters",
            "metadata",
        }
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise EmployeeLifecycleError(
                f"Unsupported employee assignment fields: {unknown}"
            )
        for key, value in changes.items():
            if key == "metadata":
                definition.setdefault("metadata", {}).update(value or {})
            else:
                definition[key] = value
        normalized = normalize_definition(definition)
        revision = int(row["revision"]) + 1
        timestamp = utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE employees
                SET definition_json=?, validation_state='valid', revision=?,
                    validated_at=?, updated_at=?
                WHERE employee_id=?
                """,
                (
                    canonical_json(normalized),
                    revision,
                    timestamp,
                    timestamp,
                    employee_id,
                ),
            )
            self._history(
                connection,
                employee_id=employee_id,
                revision=revision,
                event_type="employee.assignments-updated",
                from_status=row["lifecycle_status"],
                to_status=row["lifecycle_status"],
                actor=actor,
                reason=reason,
                payload={"changes": changes},
            )
            connection.execute("COMMIT")
        return self.get(employee_id)

    def heartbeat(
        self,
        employee_id: str,
        *,
        operational_status: str = "available",
        availability: str = "online",
        health: str = "healthy",
        current_jobs: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self._row(employee_id)
        timestamp = utc_now()
        definition = json.loads(row["definition_json"])
        if metadata:
            definition.setdefault("metadata", {}).update(metadata)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE employees
                SET operational_status=?, availability=?, health=?, current_jobs=?,
                    definition_json=?, last_heartbeat_at=?, updated_at=?
                WHERE employee_id=?
                """,
                (
                    operational_status,
                    availability,
                    health,
                    max(0, int(current_jobs)),
                    canonical_json(definition),
                    timestamp,
                    timestamp,
                    employee_id,
                ),
            )
            connection.execute("COMMIT")
        return self.get(employee_id)

    def operational_patch(
        self,
        employee_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        current = self.get(employee_id)
        return self.heartbeat(
            employee_id,
            operational_status=changes.get(
                "operational_status", changes.get("status", current["operational_status"])
            ),
            availability=changes.get("availability", current["availability"]),
            health=changes.get("health", current["health"]),
            current_jobs=changes.get("current_jobs", current["current_jobs"]),
            metadata=changes.get("metadata", {}),
        )

    def eligibility(
        self,
        employee_id: str,
        requested_at: str | None = None,
    ) -> dict[str, Any]:
        record = self.get(employee_id)
        requested = (
            datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
            if requested_at
            else datetime.now(timezone.utc)
        )
        if requested.tzinfo is None:
            requested = requested.replace(tzinfo=timezone.utc)
        reasons: list[str] = []
        if record["lifecycle_status"] != "active":
            reasons.append(f"employee-lifecycle-{record['lifecycle_status']}")
        if record["validation_state"] != "valid":
            reasons.append("employee-definition-not-validated")
        if not schedule_allows(record["schedule"], requested):
            reasons.append("employee-outside-schedule")
        if record["health"] == "unhealthy":
            reasons.append("employee-unhealthy")
        if record["availability"] == "offline":
            reasons.append("employee-offline")
        if record["current_jobs"] >= record["limits"]["max_parallel_jobs"]:
            reasons.append("employee-concurrency-limit-reached")
        eligible = not reasons
        terminal = record["lifecycle_status"] in {"disabled", "archived"}
        return {
            "ok": True,
            "contract_version": ELIGIBILITY_CONTRACT,
            "employee_id": employee_id,
            "eligible": eligible,
            "decision": "eligible" if eligible else ("rejected" if terminal else "queued"),
            "reasons": reasons,
            "lifecycle_status": record["lifecycle_status"],
            "operational_status": record["operational_status"],
            "health": record["health"],
            "availability": record["availability"],
            "schedule": record["schedule"],
            "priority": record["priority"],
            "capabilities": record["capabilities"],
            "resource_profile": self.resource_profile_payload(employee_id),
            "requested_at": requested.astimezone(timezone.utc).isoformat(),
        }

    def resolve(
        self,
        required_capabilities: list[str],
        requested_at: str | None = None,
    ) -> dict[str, Any]:
        required = {str(item) for item in required_capabilities}
        matches = []
        for employee in self.list():
            eligibility = self.eligibility(employee["employee_id"], requested_at)
            employee_capabilities = set(employee["capabilities"])
            matched = sorted(required & employee_capabilities)
            missing = sorted(required - employee_capabilities)
            score = (
                len(matched) * 20
                - len(missing) * 25
                + employee["priority_weight"]
                - employee["current_jobs"] * 5
            )
            if not eligibility["eligible"]:
                score -= 1000
            matches.append(
                {
                    "employee_id": employee["employee_id"],
                    "name": employee["name"],
                    "score": score,
                    "eligible": eligibility["eligible"],
                    "eligibility": eligibility,
                    "matched_capabilities": matched,
                    "missing_capabilities": missing,
                }
            )
        matches.sort(key=lambda item: (item["score"], item["employee_id"]), reverse=True)
        selected_match = next(
            (
                item
                for item in matches
                if item["eligible"] and not item["missing_capabilities"]
            ),
            None,
        )
        selected = self.get(selected_match["employee_id"]) if selected_match else None
        return {
            "ok": True,
            "required_capabilities": sorted(required),
            "matches": matches,
            "selected_match": selected_match,
            "selected_employee": selected,
            "resolution": {
                "selected_employee_id": selected_match["employee_id"] if selected_match else None,
                "score": selected_match["score"] if selected_match else None,
                "matched_capabilities": selected_match["matched_capabilities"] if selected_match else [],
                "missing_capabilities": selected_match["missing_capabilities"] if selected_match else sorted(required),
            },
        }

    def history(self, employee_id: str, limit: int = 200) -> dict[str, Any]:
        self._row(employee_id)
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM employee_history
                WHERE employee_id=?
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                """,
                (employee_id, max(1, min(int(limit), 2000))),
            ).fetchall()
        events = [
            {
                **dict(row),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
        for event in events:
            event.pop("payload_json", None)
        return {
            "ok": True,
            "contract_version": HISTORY_CONTRACT,
            "employee_id": employee_id,
            "event_count": len(events),
            "events": events,
        }

    def status(self, employee_id: str) -> dict[str, Any]:
        record = self.get(employee_id)
        eligibility = self.eligibility(employee_id)
        return {
            "ok": True,
            "contract_version": LIFECYCLE_CONTRACT,
            "employee_id": employee_id,
            "lifecycle_status": record["lifecycle_status"],
            "operational_status": record["operational_status"],
            "health": record["health"],
            "availability": record["availability"],
            "current_jobs": record["current_jobs"],
            "revision": record["revision"],
            "validation_state": record["validation_state"],
            "eligible": eligibility["eligible"],
            "eligibility_reasons": eligibility["reasons"],
            "updated_at": record["updated_at"],
        }

    def resource_profile_payload(self, employee_id: str) -> dict[str, Any]:
        record = self.get(employee_id)
        profile = copy.deepcopy(record["resource_profile"])
        profile["contract_version"] = RESOURCE_PROFILE_CONTRACT
        profile["employee_id"] = employee_id
        profile["enabled"] = (
            record["lifecycle_status"] == "active"
            and record["schedule"]["mode"] != "disabled"
        )
        profile["priority_class"] = record["priority"]
        profile["priority_weight"] = record["priority_weight"]
        profile["provider_preferences"] = copy.deepcopy(record["model_preferences"])
        profile["allowed_execution_windows"] = (
            copy.deepcopy(record["schedule"]["windows"])
            if record["schedule"]["mode"] == "windows"
            else []
        )
        profile.setdefault("metadata", {}).update(
            {
                "source": "employee-registry",
                "employee_revision": record["revision"],
                "lifecycle_status": record["lifecycle_status"],
            }
        )
        return profile
