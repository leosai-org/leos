from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


PROFILE_CONTRACT = "leos.employee-resource-profile.v1"
NODE_CONTRACT = "leos.compute-node-capacity.v1"
DECISION_CONTRACT = "leos.resource-admission-decision.v1"
RESERVATION_CONTRACT = "leos.resource-reservation.v1"

PRIORITY_WEIGHTS = {
    "background": 10,
    "normal": 50,
    "elevated": 70,
    "business-critical": 90,
    "emergency": 100,
}


class ResourcePolicyError(RuntimeError):
    pass


class ResourceNotFoundError(ResourcePolicyError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def nonempty(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ResourcePolicyError(f"{field} must be a non-empty string.")
    return text


def number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResourcePolicyError(f"{field} must be numeric.") from exc
    if result < 0:
        raise ResourcePolicyError(f"{field} must be non-negative.")
    return result


def integer(value: Any, field: str) -> int:
    result = number(value, field)
    if int(result) != result:
        raise ResourcePolicyError(f"{field} must be an integer.")
    return int(result)


def normalize_resources(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    gpu_required = bool(raw.get("gpu_required", False))
    vram = integer(raw.get("vram_mb_min", 0), "vram_mb_min")
    if vram > 0:
        gpu_required = True
    preferences = raw.get("gpu_uuid_preferences", [])
    if not isinstance(preferences, list):
        raise ResourcePolicyError("gpu_uuid_preferences must be a list.")
    return {
        "cpu_cores_min": number(raw.get("cpu_cores_min", 1), "cpu_cores_min"),
        "memory_mb_min": integer(raw.get("memory_mb_min", 512), "memory_mb_min"),
        "gpu_required": gpu_required,
        "vram_mb_min": vram,
        "gpu_uuid_preferences": [nonempty(item, "gpu uuid") for item in preferences],
    }


def normalize_policy(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    concurrency = integer(raw.get("max_concurrent_jobs", 1), "max_concurrent_jobs")
    ttl = integer(raw.get("reservation_ttl_seconds", 3600), "reservation_ttl_seconds")
    if concurrency < 1:
        raise ResourcePolicyError("max_concurrent_jobs must be at least 1.")
    if ttl < 30:
        raise ResourcePolicyError("reservation_ttl_seconds must be at least 30.")
    return {
        "max_concurrent_jobs": concurrency,
        "preemptible": bool(raw.get("preemptible", True)),
        "allow_preemption": bool(raw.get("allow_preemption", False)),
        "queue_when_unavailable": bool(raw.get("queue_when_unavailable", True)),
        "reservation_ttl_seconds": ttl,
    }


def normalize_affinity(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    required = raw.get("required_labels", {})
    preferred = raw.get("preferred_labels", {})
    if not isinstance(required, dict) or not isinstance(preferred, dict):
        raise ResourcePolicyError("Affinity labels must be objects.")
    return {
        "required_labels": {str(k): str(v) for k, v in required.items()},
        "preferred_labels": {str(k): str(v) for k, v in preferred.items()},
    }


def normalize_windows(value: Any) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ResourcePolicyError("allowed_execution_windows must be a list.")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ResourcePolicyError("Execution windows must be objects.")
        weekdays = item.get("weekdays", list(range(7)))
        if not isinstance(weekdays, list) or not weekdays:
            raise ResourcePolicyError("Execution-window weekdays are required.")
        days = [integer(day, "weekday") for day in weekdays]
        if any(day > 6 for day in days):
            raise ResourcePolicyError("Weekdays use Monday=0 through Sunday=6.")
        start = nonempty(item.get("start", "00:00"), "window start")
        end = nonempty(item.get("end", "23:59"), "window end")
        time.fromisoformat(start)
        time.fromisoformat(end)
        if item.get("timezone", "UTC") != "UTC":
            raise ResourcePolicyError("Phase 52.0 supports UTC windows only.")
        result.append({"weekdays": sorted(set(days)), "start": start, "end": end, "timezone": "UTC"})
    return result


def normalize_providers(value: Any) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ResourcePolicyError("provider_preferences must be a list.")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ResourcePolicyError("Provider preferences must be objects.")
        result.append({
            "provider": nonempty(item.get("provider"), "provider"),
            "model": nonempty(item.get("model"), "model"),
            "priority": integer(item.get("priority", index + 1), "provider priority"),
        })
    return sorted(result, key=lambda item: (item["priority"], item["provider"], item["model"]))


def normalize_profile(payload: dict[str, Any], override: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ResourcePolicyError("Profile payload must be an object.")
    employee_id = nonempty(override or payload.get("employee_id"), "employee_id")
    priority_class = str(payload.get("priority_class", "normal"))
    if priority_class not in PRIORITY_WEIGHTS:
        raise ResourcePolicyError("Unknown priority_class.")
    weight = integer(payload.get("priority_weight", PRIORITY_WEIGHTS[priority_class]), "priority_weight")
    if weight > 100:
        raise ResourcePolicyError("priority_weight cannot exceed 100.")
    fallbacks = payload.get("fallback_profiles", [])
    if not isinstance(fallbacks, list):
        raise ResourcePolicyError("fallback_profiles must be a list.")
    normalized_fallbacks = []
    for index, item in enumerate(fallbacks):
        if not isinstance(item, dict):
            raise ResourcePolicyError("Fallback profiles must be objects.")
        normalized_fallbacks.append({
            "name": nonempty(item.get("name", f"fallback-{index + 1}"), "fallback name"),
            "resource_profile": normalize_resources(item.get("resource_profile")),
            "provider_preferences": normalize_providers(item.get("provider_preferences", [])),
        })
    return {
        "contract_version": PROFILE_CONTRACT,
        "employee_id": employee_id,
        "enabled": bool(payload.get("enabled", True)),
        "priority_class": priority_class,
        "priority_weight": weight,
        "resource_profile": normalize_resources(payload.get("resource_profile")),
        "execution_policy": normalize_policy(payload.get("execution_policy")),
        "provider_preferences": normalize_providers(payload.get("provider_preferences", [])),
        "node_affinity": normalize_affinity(payload.get("node_affinity")),
        "allowed_execution_windows": normalize_windows(payload.get("allowed_execution_windows", [])),
        "fallback_profiles": normalized_fallbacks,
        "metadata": payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {},
    }


def normalize_node(payload: dict[str, Any], override: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ResourcePolicyError("Node payload must be an object.")
    status = str(payload.get("status", "online"))
    if status not in {"online", "offline", "draining"}:
        raise ResourcePolicyError("Node status must be online, offline, or draining.")
    labels = payload.get("labels", {})
    gpus = payload.get("gpus", [])
    if not isinstance(labels, dict) or not isinstance(gpus, list):
        raise ResourcePolicyError("Node labels must be an object and gpus a list.")
    normalized_gpus = []
    for index, gpu in enumerate(gpus):
        if not isinstance(gpu, dict):
            raise ResourcePolicyError(f"gpus[{index}] must be an object.")
        normalized_gpus.append({
            "uuid": nonempty(gpu.get("uuid"), "gpu uuid"),
            "name": str(gpu.get("name", "GPU")),
            "vram_mb_total": integer(gpu.get("vram_mb_total", 0), "gpu vram"),
            "enabled": bool(gpu.get("enabled", True)),
        })
    max_jobs = integer(payload.get("max_concurrent_jobs", 16), "node max_concurrent_jobs")
    if max_jobs < 1:
        raise ResourcePolicyError("Node max_concurrent_jobs must be at least 1.")
    return {
        "contract_version": NODE_CONTRACT,
        "node_id": nonempty(override or payload.get("node_id"), "node_id"),
        "enabled": bool(payload.get("enabled", True)),
        "status": status,
        "labels": {str(k): str(v) for k, v in labels.items()},
        "cpu_cores_total": number(payload.get("cpu_cores_total", 1), "cpu_cores_total"),
        "memory_mb_total": integer(payload.get("memory_mb_total", 1024), "memory_mb_total"),
        "max_concurrent_jobs": max_jobs,
        "gpus": normalized_gpus,
        "metadata": payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {},
    }


def in_window(windows: list[dict[str, Any]], requested: datetime) -> bool:
    if not windows:
        return True
    current = requested.astimezone(timezone.utc)
    current_time = current.time().replace(tzinfo=None)
    for window in windows:
        if current.weekday() not in window["weekdays"]:
            continue
        start = time.fromisoformat(window["start"])
        end = time.fromisoformat(window["end"])
        if start <= end and start <= current_time <= end:
            return True
        if start > end and (current_time >= start or current_time <= end):
            return True
    return False


class ResourceEngine:
    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

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
            connection.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                employee_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                employee_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                priority_weight INTEGER NOT NULL,
                preemptible INTEGER NOT NULL,
                resources TEXT NOT NULL,
                gpu_uuid TEXT,
                profile_name TEXT NOT NULL,
                providers TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                released_at TEXT,
                release_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_reservation_node_status ON reservations(node_id, status);
            CREATE INDEX IF NOT EXISTS idx_reservation_employee_status ON reservations(employee_id, status);
            """)

    def upsert_profile(self, payload: dict[str, Any], employee_id: str | None = None) -> dict[str, Any]:
        profile = normalize_profile(payload, employee_id)
        now = utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT version, created_at FROM profiles WHERE employee_id=?", (profile["employee_id"],)).fetchone()
            version = int(existing["version"]) + 1 if existing else 1
            created = existing["created_at"] if existing else now
            connection.execute(
                "INSERT INTO profiles VALUES(?,?,?,?,?) ON CONFLICT(employee_id) DO UPDATE SET data=excluded.data, version=excluded.version, updated_at=excluded.updated_at",
                (profile["employee_id"], canonical_json(profile), version, created, now),
            )
            connection.execute("COMMIT")
        return {**profile, "version": version, "created_at": created, "updated_at": now}

    def get_profile(self, employee_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM profiles WHERE employee_id=?", (employee_id,)).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"Employee resource profile not found: {employee_id}")
        return {**json.loads(row["data"]), "version": row["version"], "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_profiles(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT employee_id FROM profiles ORDER BY employee_id").fetchall()
        return [self.get_profile(row["employee_id"]) for row in rows]

    def register_node(self, payload: dict[str, Any], node_id: str | None = None) -> dict[str, Any]:
        node = normalize_node(payload, node_id)
        now = utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT created_at FROM nodes WHERE node_id=?", (node["node_id"],)).fetchone()
            created = existing["created_at"] if existing else now
            connection.execute(
                "INSERT INTO nodes VALUES(?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (node["node_id"], canonical_json(node), created, now),
            )
            connection.execute("COMMIT")
        return {**node, "created_at": created, "updated_at": now}

    def get_node(self, node_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"Compute node not found: {node_id}")
        return {**json.loads(row["data"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_nodes(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT node_id FROM nodes ORDER BY node_id").fetchall()
        return [self.get_node(row["node_id"]) for row in rows]

    def _expire(self, connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            "UPDATE reservations SET status='expired', released_at=?, release_reason='reservation-ttl-expired' WHERE status='active' AND expires_at<=?",
            (now.isoformat(), now.isoformat()),
        )

    def _profile(self, connection: sqlite3.Connection, employee_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT data, version FROM profiles WHERE employee_id=?", (employee_id,)).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"Employee resource profile not found: {employee_id}")
        return {**json.loads(row["data"]), "version": row["version"]}

    def _active(self, connection: sqlite3.Connection, node_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM reservations WHERE status='active'"
        params: tuple[Any, ...] = ()
        if node_id is not None:
            query += " AND node_id=?"
            params = (node_id,)
        query += " ORDER BY priority_weight ASC, created_at ASC"
        return [dict(row) for row in connection.execute(query, params).fetchall()]

    def _usage(self, reservations: list[dict[str, Any]]) -> dict[str, Any]:
        gpu: dict[str, int] = {}
        for reservation in reservations:
            if reservation["gpu_uuid"]:
                requirements = json.loads(reservation["resources"])
                gpu[reservation["gpu_uuid"]] = gpu.get(reservation["gpu_uuid"], 0) + int(requirements["vram_mb_min"])
        return {
            "cpu": sum(float(json.loads(item["resources"])["cpu_cores_min"]) for item in reservations),
            "memory": sum(int(json.loads(item["resources"])["memory_mb_min"]) for item in reservations),
            "gpu": gpu,
            "jobs": len(reservations),
        }

    def _choose_gpu(self, node: dict[str, Any], usage: dict[str, Any], requirements: dict[str, Any]) -> str | None:
        if not requirements["gpu_required"]:
            return None
        candidates = []
        for gpu in node["gpus"]:
            if not gpu["enabled"]:
                continue
            available = gpu["vram_mb_total"] - usage["gpu"].get(gpu["uuid"], 0)
            if available < requirements["vram_mb_min"]:
                continue
            preferred = gpu["uuid"] in requirements["gpu_uuid_preferences"]
            rank = requirements["gpu_uuid_preferences"].index(gpu["uuid"]) if preferred else 9999
            candidates.append((0 if preferred else 1, rank, -available, gpu["uuid"]))
        return sorted(candidates)[0][3] if candidates else None

    def _fits(self, node: dict[str, Any], reservations: list[dict[str, Any]], requirements: dict[str, Any]) -> tuple[bool, str | None]:
        usage = self._usage(reservations)
        if usage["jobs"] >= node["max_concurrent_jobs"]:
            return False, None
        if node["cpu_cores_total"] - usage["cpu"] < requirements["cpu_cores_min"]:
            return False, None
        if node["memory_mb_total"] - usage["memory"] < requirements["memory_mb_min"]:
            return False, None
        gpu_uuid = self._choose_gpu(node, usage, requirements)
        if requirements["gpu_required"] and gpu_uuid is None:
            return False, None
        return True, gpu_uuid

    def _preemption_plan(self, node: dict[str, Any], reservations: list[dict[str, Any]], requirements: dict[str, Any], requester_priority: int) -> tuple[list[str], str | None]:
        remaining = list(reservations)
        removed = []
        for candidate in reservations:
            if not bool(candidate["preemptible"]) or int(candidate["priority_weight"]) >= requester_priority:
                continue
            removed.append(candidate["reservation_id"])
            remaining = [item for item in remaining if item["reservation_id"] != candidate["reservation_id"]]
            fits, gpu_uuid = self._fits(node, remaining, requirements)
            if fits:
                return removed, gpu_uuid
        return [], None

    def _evaluate(self, connection: sqlite3.Connection, employee_id: str, job_id: str, requested: datetime) -> dict[str, Any]:
        profile = self._profile(connection, employee_id)
        base = {
            "contract_version": DECISION_CONTRACT,
            "decision_id": str(uuid.uuid4()),
            "employee_id": employee_id,
            "job_id": job_id,
            "priority_class": profile["priority_class"],
            "priority_weight": profile["priority_weight"],
            "requested_at": requested.isoformat(),
            "selected_node_id": None,
            "selected_gpu_uuid": None,
            "selected_profile": None,
            "resources": None,
            "provider_preferences": [],
            "preemption_candidates": [],
        }
        if not profile["enabled"]:
            return {**base, "decision": "rejected", "reason": "employee-resource-profile-disabled"}
        if not in_window(profile["allowed_execution_windows"], requested):
            decision = "queued" if profile["execution_policy"]["queue_when_unavailable"] else "rejected"
            return {**base, "decision": decision, "reason": "outside-allowed-execution-window"}
        active_employee = connection.execute("SELECT COUNT(*) AS count FROM reservations WHERE employee_id=? AND status='active'", (employee_id,)).fetchone()["count"]
        if active_employee >= profile["execution_policy"]["max_concurrent_jobs"]:
            decision = "queued" if profile["execution_policy"]["queue_when_unavailable"] else "rejected"
            return {**base, "decision": decision, "reason": "employee-concurrency-limit-reached"}

        profiles = [{"name": "primary", "resource_profile": profile["resource_profile"], "provider_preferences": profile["provider_preferences"]}] + profile["fallback_profiles"]
        direct = []
        preempt = []
        for row in connection.execute("SELECT data FROM nodes ORDER BY node_id").fetchall():
            node = json.loads(row["data"])
            if not node["enabled"] or node["status"] != "online":
                continue
            required_labels = profile["node_affinity"]["required_labels"]
            if any(node["labels"].get(k) != v for k, v in required_labels.items()):
                continue
            reservations = self._active(connection, node["node_id"])
            preferred_matches = sum(1 for k, v in profile["node_affinity"]["preferred_labels"].items() if node["labels"].get(k) == v)
            for candidate in profiles:
                requirements = candidate["resource_profile"]
                fits, gpu_uuid = self._fits(node, reservations, requirements)
                usage = self._usage(reservations)
                score = preferred_matches * 10000 + (node["cpu_cores_total"] - usage["cpu"]) * 10 + (node["memory_mb_total"] - usage["memory"]) / 1024
                record = (score, node["node_id"], candidate["name"], requirements, candidate["provider_preferences"], gpu_uuid)
                if fits:
                    direct.append(record)
                elif profile["execution_policy"]["allow_preemption"]:
                    plan, planned_gpu = self._preemption_plan(node, reservations, requirements, profile["priority_weight"])
                    if plan:
                        preempt.append((*record[:-1], planned_gpu, plan))

        if direct:
            score, node_id, name, requirements, providers, gpu_uuid = sorted(direct, reverse=True)[0]
            return {**base, "decision": "admitted", "reason": "resources-available", "selected_node_id": node_id, "selected_gpu_uuid": gpu_uuid, "selected_profile": name, "resources": requirements, "provider_preferences": providers}
        if preempt:
            score, node_id, name, requirements, providers, gpu_uuid, plan = sorted(preempt, reverse=True)[0]
            return {**base, "decision": "preemption-required", "reason": "lower-priority-preemptible-reservations-found", "selected_node_id": node_id, "selected_gpu_uuid": gpu_uuid, "selected_profile": name, "resources": requirements, "provider_preferences": providers, "preemption_candidates": plan}
        decision = "queued" if profile["execution_policy"]["queue_when_unavailable"] else "rejected"
        return {**base, "decision": decision, "reason": "no-node-satisfies-resource-policy"}

    def evaluate(self, employee_id: str, job_id: str, requested_at: str | None = None) -> dict[str, Any]:
        requested = parse_timestamp(requested_at)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire(connection, requested)
            decision = self._evaluate(connection, nonempty(employee_id, "employee_id"), nonempty(job_id, "job_id"), requested)
            connection.execute("COMMIT")
        return decision

    def reserve(self, employee_id: str, job_id: str, requested_at: str | None = None, commit_preemption: bool = False) -> dict[str, Any]:
        requested = parse_timestamp(requested_at)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._expire(connection, requested)
            if connection.execute("SELECT 1 FROM reservations WHERE job_id=? AND status='active'", (job_id,)).fetchone():
                connection.execute("ROLLBACK")
                raise ResourcePolicyError(f"Job already has an active reservation: {job_id}")
            decision = self._evaluate(connection, nonempty(employee_id, "employee_id"), nonempty(job_id, "job_id"), requested)
            if decision["decision"] == "preemption-required":
                if not commit_preemption:
                    connection.execute("COMMIT")
                    return {"ok": False, "reserved": False, "decision": decision, "reservation": None}
                for reservation_id in decision["preemption_candidates"]:
                    connection.execute("UPDATE reservations SET status='preempted', released_at=?, release_reason=? WHERE reservation_id=? AND status='active'", (requested.isoformat(), f"preempted-by:{employee_id}:{job_id}", reservation_id))
                decision = {**decision, "decision": "admitted", "reason": "resources-admitted-after-preemption"}
            if decision["decision"] != "admitted":
                connection.execute("COMMIT")
                return {"ok": False, "reserved": False, "decision": decision, "reservation": None}
            profile = self._profile(connection, employee_id)
            reservation_id = str(uuid.uuid4())
            expires = requested + timedelta(seconds=profile["execution_policy"]["reservation_ttl_seconds"])
            connection.execute(
                "INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    reservation_id,
                    employee_id,
                    job_id,
                    decision["selected_node_id"],
                    "active",
                    profile["priority_weight"],
                    1 if profile["execution_policy"]["preemptible"] else 0,
                    canonical_json(decision["resources"]),
                    decision["selected_gpu_uuid"],
                    decision["selected_profile"],
                    canonical_json(decision["provider_preferences"]),
                    requested.isoformat(),
                    expires.isoformat(),
                    None,
                    None,
                ),
            )
            connection.execute("COMMIT")
        return {"ok": True, "reserved": True, "decision": decision, "reservation": self.get_reservation(reservation_id)}

    def _reservation(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "contract_version": RESERVATION_CONTRACT,
            "reservation_id": row["reservation_id"],
            "employee_id": row["employee_id"],
            "job_id": row["job_id"],
            "node_id": row["node_id"],
            "status": row["status"],
            "priority_weight": row["priority_weight"],
            "preemptible": bool(row["preemptible"]),
            "resources": json.loads(row["resources"]),
            "gpu_uuid": row["gpu_uuid"],
            "profile_name": row["profile_name"],
            "provider_preferences": json.loads(row["providers"]),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "released_at": row["released_at"],
            "release_reason": row["release_reason"],
        }

    def get_reservation(self, reservation_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
        if row is None:
            raise ResourceNotFoundError(f"Reservation not found: {reservation_id}")
        return self._reservation(row)

    def list_reservations(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM reservations"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY created_at, reservation_id"
        with self.connection() as connection:
            now = datetime.now(timezone.utc)
            connection.execute("BEGIN IMMEDIATE")
            self._expire(connection, now)
            rows = connection.execute(query, params).fetchall()
            connection.execute("COMMIT")
        return [self._reservation(row) for row in rows]

    def active_reservation_for_job(self, job_id: str) -> dict[str, Any]:
        normalized_job_id = nonempty(job_id, "job_id")
        with self.connection() as connection:
            requested = datetime.now(timezone.utc)
            connection.execute("BEGIN IMMEDIATE")
            self._expire(connection, requested)
            row = connection.execute(
                """
                SELECT *
                FROM reservations
                WHERE job_id=? AND status='active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized_job_id,),
            ).fetchone()
            connection.execute("COMMIT")
        if row is None:
            raise ResourceNotFoundError(
                f"Active reservation not found for job: {normalized_job_id}"
            )
        return self._reservation(row)

    def expire_reservations(self) -> dict[str, Any]:
        requested = datetime.now(timezone.utc)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            before = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM reservations
                WHERE status='active' AND expires_at<=?
                """,
                (requested.isoformat(),),
            ).fetchone()["count"]
            self._expire(connection, requested)
            connection.execute("COMMIT")
        return {
            "ok": True,
            "contract_version": "leos.resource-reservation-expiration.v1",
            "expired_count": int(before),
            "expired_at": requested.isoformat(),
        }

    def release(self, reservation_id: str, reason: str = "released") -> dict[str, Any]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise ResourceNotFoundError(f"Reservation not found: {reservation_id}")
            if row["status"] == "active":
                connection.execute("UPDATE reservations SET status='released', released_at=?, release_reason=? WHERE reservation_id=?", (utc_now(), str(reason), reservation_id))
            connection.execute("COMMIT")
        return self.get_reservation(reservation_id)

    def snapshot(self) -> dict[str, Any]:
        profiles = self.list_profiles()
        nodes = self.list_nodes()
        reservations = self.list_reservations()
        return {
            "ok": True,
            "service": "employee-resource-profile-service",
            "contract_version": "leos.resource-policy-snapshot.v1",
            "profile_count": len(profiles),
            "node_count": len(nodes),
            "active_reservation_count": sum(1 for item in reservations if item["status"] == "active"),
            "profiles": profiles,
            "nodes": nodes,
            "reservations": reservations,
            "generated_at": utc_now(),
        }
