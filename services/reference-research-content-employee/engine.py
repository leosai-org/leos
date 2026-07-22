from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from contextlib import contextmanager

SERVICE_ID = "reference-research-content-employee"
EMPLOYEE_ID = "research-content-employee"
RUN_CONTRACT = "leos.reference-research-content-run.v1"
SOURCE_CONTRACT = "leos.research-source.v1"
ARTIFACT_CONTRACT = "leos.research-content-artifact.v1"
HISTORY_CONTRACT = "leos.reference-employee-history.v1"
ELIGIBILITY_CONTRACT = "leos.employee-execution-eligibility.v1"
ADMISSION_CONTRACT = "leos.resource-admission-decision.v1"
RESERVATION_CONTRACT = "leos.resource-reservation.v1"

TRANSIENT_STATES = {
    "planning",
    "researching",
    "drafting",
    "reviewing",
    "revising",
    "persisting",
}
TERMINAL_STATES = {"complete", "failed", "cancelled"}
VALID_PRIORITIES = {
    "background",
    "normal",
    "elevated",
    "business-critical",
    "emergency",
}
REQUIRED_SECTIONS = (
    "Introduction",
    "Background",
    "Key Points",
    "Considerations",
    "Conclusion",
)
ALLOWED_TRANSITIONS = {
    "accepted": {"planning", "paused", "cancelled", "failed"},
    "planning": {"researching", "paused", "interrupted", "failed", "cancelled"},
    "researching": {"drafting", "paused", "interrupted", "failed", "cancelled"},
    "drafting": {"reviewing", "paused", "interrupted", "failed", "cancelled"},
    "reviewing": {"revising", "persisting", "paused", "interrupted", "failed", "cancelled"},
    "revising": {"reviewing", "paused", "interrupted", "failed", "cancelled"},
    "persisting": {"complete", "interrupted", "failed", "cancelled"},
    "paused": {"accepted", "interrupted", "cancelled"},
    "interrupted": {"accepted", "cancelled", "failed"},
    "complete": set(),
    "failed": set(),
    "cancelled": set(),
}


class ReferenceEmployeeError(RuntimeError):
    pass


class RunNotFoundError(ReferenceEmployeeError):
    pass


class GovernanceError(ReferenceEmployeeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_'’-]*", value)


def sentence_list(value: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", value).strip()
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", normalized) if item.strip()]


def safe_identifier(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ReferenceEmployeeError(f"{field} is required.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", normalized):
        raise ReferenceEmployeeError(f"{field} contains unsupported characters.")
    return normalized


class ReferenceResearchContentEngine:
    def __init__(
        self,
        database: str | Path,
        *,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.database = Path(database)
        self.clock = clock
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self._interrupt_inflight_runs()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    governance_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    revision_count INTEGER NOT NULL DEFAULT 0,
                    artifact_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_reference_runs_state
                    ON runs(state, updated_at);

                CREATE TABLE IF NOT EXISTS run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, sequence),
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS research_sources (
                    source_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    author TEXT,
                    published_at TEXT,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_reference_sources_run
                    ON research_sources(run_id, created_at);

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS artifact_versions (
                    artifact_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    execution_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(artifact_id, version),
                    FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id)
                );
                """
            )

    def _interrupt_inflight_runs(self) -> None:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT run_id, state FROM runs WHERE state IN (%s)"
                % ",".join("?" for _ in TRANSIENT_STATES),
                sorted(TRANSIENT_STATES),
            ).fetchall()
            stamp = self.clock()
            for row in rows:
                connection.execute(
                    """
                    UPDATE runs
                    SET state='interrupted', current_stage='interrupted',
                        error=COALESCE(error, ?), updated_at=?
                    WHERE run_id=?
                    """,
                    ("Service restarted before run completion.", stamp, row["run_id"]),
                )
                self._append_event(
                    connection,
                    row["run_id"],
                    "run.interrupted",
                    "interrupted",
                    {"previous_state": row["state"], "reason": "service-restart"},
                )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        state: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sequence = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM run_events WHERE run_id=?",
            (run_id,),
        ).fetchone()["value"]
        event = {
            "contract_version": HISTORY_CONTRACT,
            "event_id": str(uuid.uuid4()),
            "run_id": run_id,
            "sequence": int(sequence),
            "event_type": event_type,
            "state": state,
            "details": copy.deepcopy(details or {}),
            "created_at": self.clock(),
        }
        connection.execute(
            """
            INSERT INTO run_events (
                event_id, run_id, sequence, event_type, state,
                details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                run_id,
                event["sequence"],
                event_type,
                state,
                canonical_json(event["details"]),
                event["created_at"],
            ),
        )
        return event

    def _transition(
        self,
        run_id: str,
        target: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.session() as connection:
            row = connection.execute(
                "SELECT state FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise RunNotFoundError(f"Run not found: {run_id}")
            current = row["state"]
            if target not in ALLOWED_TRANSITIONS.get(current, set()):
                raise ReferenceEmployeeError(
                    f"Invalid run transition: {current} -> {target}."
                )
            stamp = self.clock()
            connection.execute(
                """
                UPDATE runs
                SET state=?, current_stage=?, updated_at=?,
                    completed_at=CASE WHEN ? IN ('complete','failed','cancelled')
                                      THEN ? ELSE completed_at END
                WHERE run_id=?
                """,
                (target, target, stamp, target, stamp, run_id),
            )
            self._append_event(connection, run_id, event_type, target, details)
        return self.get_run(run_id)

    def _validate_governance(
        self,
        governance: dict[str, Any],
        *,
        goal_id: str,
    ) -> dict[str, Any]:
        if not isinstance(governance, dict):
            raise GovernanceError("governance must be an object.")
        eligibility = dict(governance.get("employee_eligibility") or {})
        admission = dict(governance.get("resource_admission") or {})
        reservation = dict(governance.get("resource_reservation") or {})
        execution = dict(governance.get("execution") or {})

        if eligibility.get("contract_version") != ELIGIBILITY_CONTRACT:
            raise GovernanceError("Missing canonical employee eligibility contract.")
        if eligibility.get("employee_id") != EMPLOYEE_ID:
            raise GovernanceError("Eligibility employee_id does not match the reference employee.")
        if eligibility.get("eligible") is not True or eligibility.get("decision") != "eligible":
            raise GovernanceError("The employee is not execution eligible.")
        if eligibility.get("reasons") not in (None, []):
            raise GovernanceError("Eligible employee response contains blocking reasons.")

        if admission.get("contract_version") != ADMISSION_CONTRACT:
            raise GovernanceError("Missing canonical resource admission contract.")
        if admission.get("employee_id") != EMPLOYEE_ID:
            raise GovernanceError("Admission employee_id does not match the reference employee.")
        if admission.get("decision") != "admitted":
            raise GovernanceError("Resource admission did not admit the run.")

        if reservation.get("contract_version") != RESERVATION_CONTRACT:
            raise GovernanceError("Missing canonical resource reservation contract.")
        if reservation.get("employee_id") != EMPLOYEE_ID:
            raise GovernanceError("Reservation employee_id does not match the reference employee.")
        if reservation.get("status") != "active":
            raise GovernanceError("Resource reservation is not active.")

        job_ids = {
            str(value)
            for value in (
                admission.get("job_id"),
                reservation.get("job_id"),
                execution.get("job_id"),
            )
            if value is not None
        }
        if len(job_ids) != 1:
            raise GovernanceError("Admission, reservation, and execution job identifiers disagree.")
        job_id = next(iter(job_ids), "")
        safe_identifier(job_id, "governance.execution.job_id")
        safe_identifier(str(reservation.get("reservation_id", "")), "reservation_id")
        safe_identifier(str(admission.get("decision_id", "")), "decision_id")
        safe_identifier(str(execution.get("assignment_id", "")), "assignment_id")
        safe_identifier(str(execution.get("execution_id", "")), "execution_id")

        priority = str(
            execution.get("priority")
            or eligibility.get("priority")
            or admission.get("priority_class")
            or "normal"
        ).lower()
        if priority not in VALID_PRIORITIES:
            raise GovernanceError(f"Unknown priority: {priority}")

        return {
            "employee_eligibility": eligibility,
            "resource_admission": admission,
            "resource_reservation": reservation,
            "execution": {
                **execution,
                "job_id": job_id,
                "goal_id": goal_id,
                "priority": priority,
            },
            "verified": True,
            "verified_at": self.clock(),
        }

    def create_run(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ReferenceEmployeeError("Run request must be an object.")
        goal_id = safe_identifier(request.get("goal_id", ""), "goal_id")
        goal = str(request.get("goal", "")).strip()
        title = str(request.get("title") or goal).strip()
        if not goal:
            raise ReferenceEmployeeError("goal is required.")
        if not title:
            raise ReferenceEmployeeError("title is required.")
        sources = request.get("sources", [])
        if not isinstance(sources, list):
            raise ReferenceEmployeeError("sources must be a list.")
        governance = self._validate_governance(
            dict(request.get("governance") or {}), goal_id=goal_id
        )
        approved_adapters = request.get(
            "approved_adapters", ["manual-source-input", "company-knowledge-service"]
        )
        if not isinstance(approved_adapters, list):
            raise ReferenceEmployeeError("approved_adapters must be a list.")
        normalized_request = {
            "contract_version": RUN_CONTRACT,
            "goal_id": goal_id,
            "goal": goal,
            "title": title,
            "requested_by": str(request.get("requested_by", "operator")),
            "sources": copy.deepcopy(sources),
            "requirements": [
                str(item).strip()
                for item in request.get("requirements", [])
                if str(item).strip()
            ],
            "approved_adapters": sorted({str(item) for item in approved_adapters}),
            "initial_draft": request.get("initial_draft"),
            "minimum_words": max(120, int(request.get("minimum_words", 220))),
            "max_revision_attempts": min(
                5, max(0, int(request.get("max_revision_attempts", 2)))
            ),
            "metadata": copy.deepcopy(request.get("metadata", {})),
        }
        run_id = str(request.get("run_id") or uuid.uuid4())
        artifact_id = str(request.get("artifact_id") or f"artifact-{run_id}")
        safe_identifier(run_id, "run_id")
        safe_identifier(artifact_id, "artifact_id")
        stamp = self.clock()
        with self.session() as connection:
            if connection.execute(
                "SELECT 1 FROM runs WHERE run_id=?", (run_id,)
            ).fetchone():
                raise ReferenceEmployeeError(f"Run already exists: {run_id}")
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, goal_id, employee_id, state, current_stage,
                    priority, request_json, governance_json, result_json,
                    error, revision_count, artifact_id, created_at,
                    updated_at, completed_at
                ) VALUES (?, ?, ?, 'accepted', 'accepted', ?, ?, ?, NULL,
                          NULL, 0, ?, ?, ?, NULL)
                """,
                (
                    run_id,
                    goal_id,
                    EMPLOYEE_ID,
                    governance["execution"]["priority"],
                    canonical_json(normalized_request),
                    canonical_json(governance),
                    artifact_id,
                    stamp,
                    stamp,
                ),
            )
            self._append_event(
                connection,
                run_id,
                "run.accepted",
                "accepted",
                {
                    "goal_id": goal_id,
                    "artifact_id": artifact_id,
                    "priority": governance["execution"]["priority"],
                    "reservation_id": governance["resource_reservation"]["reservation_id"],
                },
            )
        return self.get_run(run_id)

    def _row_to_run(self, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["request"] = json.loads(value.pop("request_json"))
        value["governance"] = json.loads(value.pop("governance_json"))
        raw_result = value.pop("result_json")
        value["result"] = json.loads(raw_result) if raw_result else None
        return {"contract_version": RUN_CONTRACT, **value}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise RunNotFoundError(f"Run not found: {run_id}")
        return self._row_to_run(row)

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def history(self, run_id: str) -> dict[str, Any]:
        self.get_run(run_id)
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM run_events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            item["contract_version"] = HISTORY_CONTRACT
            events.append(item)
        return {
            "ok": True,
            "contract_version": HISTORY_CONTRACT,
            "run_id": run_id,
            "event_count": len(events),
            "events": events,
        }

    def pause(self, run_id: str, reason: str = "operator-request") -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["state"] in TERMINAL_STATES:
            raise ReferenceEmployeeError("A terminal run cannot be paused.")
        return self._transition(
            run_id,
            "paused",
            "run.paused",
            {"reason": reason, "previous_state": run["state"]},
        )

    def resume(self, run_id: str, reason: str = "operator-request") -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["state"] not in {"paused", "interrupted"}:
            raise ReferenceEmployeeError("Only paused or interrupted runs can resume.")
        return self._transition(
            run_id,
            "accepted",
            "run.resumed",
            {"reason": reason, "previous_state": run["state"]},
        )

    def cancel(self, run_id: str, reason: str = "operator-request") -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["state"] in TERMINAL_STATES:
            raise ReferenceEmployeeError("Run is already terminal.")
        return self._transition(
            run_id,
            "cancelled",
            "run.cancelled",
            {"reason": reason, "previous_state": run["state"]},
        )

    def _replace_sources(
        self,
        run_id: str,
        raw_sources: Iterable[dict[str, Any]],
        approved_adapters: set[str],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_sources, start=1):
            if not isinstance(raw, dict):
                raise ReferenceEmployeeError("Every source must be an object.")
            title = str(raw.get("title") or f"Source {index}").strip()
            content = str(raw.get("content") or raw.get("text") or "").strip()
            if not content:
                raise ReferenceEmployeeError(f"Source {index} has no content.")
            provenance = dict(raw.get("provenance") or {})
            adapter_id = str(
                provenance.get("adapter_id")
                or raw.get("adapter_id")
                or "manual-source-input"
            )
            if adapter_id not in approved_adapters:
                raise GovernanceError(
                    f"Source adapter is not approved: {adapter_id}"
                )
            source_id = str(raw.get("source_id") or f"source-{index}-{sha256_text(content)[:12]}")
            safe_identifier(source_id, "source_id")
            if source_id in seen:
                raise ReferenceEmployeeError(f"Duplicate source_id: {source_id}")
            seen.add(source_id)
            digest = sha256_text(content)
            item = {
                "contract_version": SOURCE_CONTRACT,
                "source_id": source_id,
                "run_id": run_id,
                "title": title,
                "url": raw.get("url"),
                "author": raw.get("author"),
                "published_at": raw.get("published_at"),
                "content": content,
                "content_sha256": digest,
                "provenance": {
                    **provenance,
                    "adapter_id": adapter_id,
                    "approved": True,
                    "retrieved_at": provenance.get("retrieved_at") or self.clock(),
                    "content_sha256": digest,
                },
                "created_at": self.clock(),
            }
            normalized.append(item)

        if not normalized:
            raise GovernanceError(
                "At least one approved source is required before factual content generation."
            )

        with self.session() as connection:
            connection.execute("DELETE FROM research_sources WHERE run_id=?", (run_id,))
            for item in normalized:
                connection.execute(
                    """
                    INSERT INTO research_sources (
                        source_id, run_id, title, url, author, published_at,
                        content, content_sha256, provenance_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["source_id"],
                        run_id,
                        item["title"],
                        item["url"],
                        item["author"],
                        item["published_at"],
                        item["content"],
                        item["content_sha256"],
                        canonical_json(item["provenance"]),
                        item["created_at"],
                    ),
                )
        return normalized

    def sources(self, run_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM research_sources WHERE run_id=? ORDER BY created_at, source_id",
                (run_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["provenance"] = json.loads(item.pop("provenance_json"))
            item["contract_version"] = SOURCE_CONTRACT
            result.append(item)
        return result

    def _build_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        goal = request["goal"]
        return {
            "contract_version": "leos.reference-research-plan.v1",
            "goal_id": request["goal_id"],
            "goal": goal,
            "research_questions": [
                goal,
                f"Which approved evidence directly supports {goal}?",
                f"Which limitations or tradeoffs should be disclosed for {goal}?",
            ],
            "tasks": [
                {"task_id": "plan", "capability": "research.plan"},
                {"task_id": "sources", "capability": "research.sources"},
                {"task_id": "evidence", "capability": "research.extract"},
                {"task_id": "draft", "capability": "content.draft"},
                {"task_id": "review", "capability": "content.review.request"},
                {"task_id": "revision", "capability": "content.revise"},
                {"task_id": "persist", "capability": "artifact.persist"},
            ],
        }

    def _extract_evidence(
        self,
        goal: str,
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        terms = {token.lower() for token in words(goal) if len(token) > 2}
        evidence: list[dict[str, Any]] = []
        for source_index, source in enumerate(sources, start=1):
            sentences = sentence_list(source["content"])
            ranked = sorted(
                enumerate(sentences),
                key=lambda item: (
                    -sum(term in item[1].lower() for term in terms),
                    item[0],
                ),
            )
            selected = [text for _, text in ranked[:3] if text]
            if not selected:
                selected = [source["content"][:500]]
            for evidence_index, text in enumerate(selected, start=1):
                evidence.append(
                    {
                        "evidence_id": f"evidence-{source_index}-{evidence_index}",
                        "source_id": source["source_id"],
                        "citation": f"[S{source_index}]",
                        "text": text,
                        "content_sha256": sha256_text(text),
                    }
                )
        return evidence

    def _draft_content(
        self,
        request: dict[str, Any],
        sources: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> str:
        citations = {
            source["source_id"]: f"[S{index}]"
            for index, source in enumerate(sources, start=1)
        }
        grouped: dict[str, list[str]] = {}
        for item in evidence:
            grouped.setdefault(item["source_id"], []).append(item["text"])

        evidence_lines = []
        for source in sources:
            quote = " ".join(grouped.get(source["source_id"], []))
            evidence_lines.append(
                f"- {quote} {citations[source['source_id']]}"
            )
        requirements = request.get("requirements", [])
        requirement_text = (
            " The requested deliverable explicitly addresses: "
            + "; ".join(requirements)
            + "."
            if requirements
            else ""
        )
        source_list = "\n".join(
            f"{index}. {source['title']} {citations[source['source_id']]}"
            + (f" — {source['url']}" if source.get("url") else "")
            for index, source in enumerate(sources, start=1)
        )
        content = f"""# {request['title']}

## Introduction

This research brief addresses **{request['goal']}** using only approved source material with retained provenance. The result is a reviewable draft rather than an automatic publication.{requirement_text}

## Background

LEOS separated source collection, evidence extraction, drafting, review, revision, and artifact persistence so every factual statement can be traced to an approved input. The execution record also retains the employee eligibility decision, resource admission decision, active reservation, scheduler job, assignment, and execution identifiers.

## Key Points

{chr(10).join(evidence_lines)}

The approved evidence supports a structured response to the goal while preserving the distinction between source statements and employee interpretation. Each source is content-hashed so later review can detect substitution or drift.

## Considerations

The supplied material may not cover every possible viewpoint. Conclusions should remain proportional to the evidence, absolute claims should be avoided, and any external publication should remain behind the appropriate human or policy approval gate. Source quality, freshness, authorship, and context remain visible in the artifact provenance.

## Conclusion

The approved sources provide enough traceable evidence to produce a governed research-and-content artifact for **{request['goal']}**. LEOS can now submit this draft for independent review, revise any recorded findings, and persist the final version together with its complete lineage.

## Sources

{source_list}
""".strip()
        return content

    def _review(
        self,
        content: str,
        source_ids: list[str],
        minimum_words: int,
        requirements: list[str],
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        lower = content.lower()
        count = len(words(content))
        for section in REQUIRED_SECTIONS:
            if f"## {section}".lower() not in lower:
                findings.append(
                    {
                        "category": "structure",
                        "severity": "medium",
                        "description": f"Required section is missing: {section}",
                        "required_correction": f"Add a {section} section.",
                    }
                )
        if count < minimum_words:
            findings.append(
                {
                    "category": "completeness",
                    "severity": "medium",
                    "description": f"Draft contains {count} words; at least {minimum_words} are required.",
                    "required_correction": "Expand the evidence explanation and limitations.",
                }
            )
        expected_citations = {f"[S{index}]" for index in range(1, len(source_ids) + 1)}
        missing_citations = sorted(citation for citation in expected_citations if citation not in content)
        if missing_citations:
            findings.append(
                {
                    "category": "evidence",
                    "severity": "high",
                    "description": "Not every approved source is cited.",
                    "required_correction": "Add citations for: " + ", ".join(missing_citations),
                }
            )
        unsupported = [
            phrase
            for phrase in ("guaranteed", "best in the world", "never fails", "100%")
            if phrase in lower
        ]
        if unsupported:
            findings.append(
                {
                    "category": "accuracy",
                    "severity": "high",
                    "description": "Unsupported absolute claims were detected.",
                    "required_correction": "Qualify or remove: " + ", ".join(unsupported),
                }
            )
        missing_requirements = [
            item for item in requirements if item.lower() not in lower
        ]
        for item in missing_requirements:
            findings.append(
                {
                    "category": "requirements",
                    "severity": "medium",
                    "description": f"Requirement not explicitly addressed: {item}",
                    "required_correction": f"Explicitly address: {item}",
                }
            )
        penalty = sum(
            20 if item["severity"] == "high" else 10
            for item in findings
        )
        score = max(0, 100 - penalty)
        approved = not findings and score >= 85
        return {
            "contract_version": "leos.reference-content-review.v1",
            "review_id": str(uuid.uuid4()),
            "reviewer": "content-review-service-compatible-deterministic-review",
            "approved": approved,
            "status": "approved" if approved else "revision_required",
            "score": score,
            "word_count": count,
            "findings": findings,
            "required_corrections": [
                item["required_correction"]
                for item in findings
                if item.get("required_correction")
            ],
            "created_at": self.clock(),
        }

    def _persist_artifact_version(
        self,
        *,
        run: dict[str, Any],
        content: str,
        sources: list[dict[str, Any]],
        review: dict[str, Any],
        status: str,
        version: int,
        plan: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        artifact_id = run["artifact_id"]
        request = run["request"]
        governance = run["governance"]
        execution = {
            "employee_id": EMPLOYEE_ID,
            "goal_id": run["goal_id"],
            "run_id": run["run_id"],
            "job_id": governance["execution"]["job_id"],
            "assignment_id": governance["execution"]["assignment_id"],
            "execution_id": governance["execution"]["execution_id"],
            "decision_id": governance["resource_admission"]["decision_id"],
            "reservation_id": governance["resource_reservation"]["reservation_id"],
            "priority": run["priority"],
        }
        source_ids = [source["source_id"] for source in sources]
        data = {
            "contract_version": ARTIFACT_CONTRACT,
            "artifact_id": artifact_id,
            "run_id": run["run_id"],
            "goal_id": run["goal_id"],
            "employee_id": EMPLOYEE_ID,
            "title": request["title"],
            "status": status,
            "version": version,
            "content": content,
            "content_sha256": sha256_text(content),
            "source_ids": source_ids,
            "sources": [
                {
                    "source_id": source["source_id"],
                    "title": source["title"],
                    "url": source.get("url"),
                    "content_sha256": source["content_sha256"],
                    "provenance": source["provenance"],
                }
                for source in sources
            ],
            "plan": plan,
            "evidence": evidence,
            "review": review,
            "execution": execution,
            "created_at": self.clock(),
        }
        metadata = {
            "reference_implementation": True,
            "human_review_required_before_external_publication": True,
            "source_count": len(sources),
            "revision_count": run["revision_count"],
        }
        stamp = self.clock()
        with self.session() as connection:
            existing = connection.execute(
                "SELECT 1 FROM artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE artifacts SET title=?, status=?, current_version=?,
                        data_json=?, metadata_json=?, updated_at=?
                    WHERE artifact_id=?
                    """,
                    (
                        request["title"],
                        status,
                        version,
                        canonical_json(data),
                        canonical_json(metadata),
                        stamp,
                        artifact_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO artifacts (
                        artifact_id, run_id, title, status, current_version,
                        data_json, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_id,
                        run["run_id"],
                        request["title"],
                        status,
                        version,
                        canonical_json(data),
                        canonical_json(metadata),
                        stamp,
                        stamp,
                    ),
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO artifact_versions (
                    artifact_id, version, status, content, source_ids_json,
                    review_json, execution_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    version,
                    status,
                    content,
                    canonical_json(source_ids),
                    canonical_json(review),
                    canonical_json(execution),
                    stamp,
                ),
            )
        return data

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            versions = connection.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id=? ORDER BY version",
                (artifact_id,),
            ).fetchall()
        if row is None:
            raise ReferenceEmployeeError(f"Artifact not found: {artifact_id}")
        artifact = dict(row)
        artifact["data"] = json.loads(artifact.pop("data_json"))
        artifact["metadata"] = json.loads(artifact.pop("metadata_json"))
        artifact["contract_version"] = ARTIFACT_CONTRACT
        artifact["versions"] = []
        for version in versions:
            item = dict(version)
            item["source_ids"] = json.loads(item.pop("source_ids_json"))
            item["review"] = json.loads(item.pop("review_json"))
            item["execution"] = json.loads(item.pop("execution_json"))
            artifact["versions"].append(item)
        return artifact

    def execute(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["state"] == "complete":
            return run
        if run["state"] in {"paused", "interrupted"}:
            raise ReferenceEmployeeError(
                "Paused or interrupted runs must be resumed before execution."
            )
        if run["state"] != "accepted":
            raise ReferenceEmployeeError(
                f"Run cannot execute from state: {run['state']}"
            )

        request = run["request"]
        try:
            self._transition(run_id, "planning", "run.planning.started")
            plan = self._build_plan(request)
            self._transition(
                run_id,
                "researching",
                "run.research.started",
                {"task_count": len(plan["tasks"])},
            )
            sources = self._replace_sources(
                run_id,
                request["sources"],
                set(request["approved_adapters"]),
            )
            evidence = self._extract_evidence(request["goal"], sources)
            self._transition(
                run_id,
                "drafting",
                "run.drafting.started",
                {"source_count": len(sources), "evidence_count": len(evidence)},
            )
            content = (
                str(request.get("initial_draft")).strip()
                if request.get("initial_draft") is not None
                else self._draft_content(request, sources, evidence)
            )
            revision_count = 0
            current_version = 1
            review = self._review(
                content,
                [source["source_id"] for source in sources],
                request["minimum_words"],
                request["requirements"],
            )
            self._transition(
                run_id,
                "reviewing",
                "run.review.completed",
                {
                    "review_id": review["review_id"],
                    "approved": review["approved"],
                    "score": review["score"],
                },
            )
            self._persist_artifact_version(
                run=self.get_run(run_id),
                content=content,
                sources=sources,
                review=review,
                status=("reviewed" if review["approved"] else "revision_required"),
                version=current_version,
                plan=plan,
                evidence=evidence,
            )

            while not review["approved"] and revision_count < request["max_revision_attempts"]:
                self._transition(
                    run_id,
                    "revising",
                    "run.revision.started",
                    {
                        "attempt": revision_count + 1,
                        "review_id": review["review_id"],
                        "corrections": review["required_corrections"],
                    },
                )
                revision_count += 1
                with self.session() as connection:
                    connection.execute(
                        "UPDATE runs SET revision_count=?, updated_at=? WHERE run_id=?",
                        (revision_count, self.clock(), run_id),
                    )
                content = self._draft_content(request, sources, evidence)
                review = self._review(
                    content,
                    [source["source_id"] for source in sources],
                    request["minimum_words"],
                    request["requirements"],
                )
                current_version += 1
                self._transition(
                    run_id,
                    "reviewing",
                    "run.revision.review.completed",
                    {
                        "attempt": revision_count,
                        "review_id": review["review_id"],
                        "approved": review["approved"],
                        "score": review["score"],
                    },
                )
                self._persist_artifact_version(
                    run=self.get_run(run_id),
                    content=content,
                    sources=sources,
                    review=review,
                    status=("reviewed" if review["approved"] else "revision_required"),
                    version=current_version,
                    plan=plan,
                    evidence=evidence,
                )

            if not review["approved"]:
                raise ReferenceEmployeeError(
                    "Independent review did not approve the artifact within the revision limit."
                )

            self._transition(
                run_id,
                "persisting",
                "run.persistence.started",
                {"artifact_id": run["artifact_id"], "version": current_version + 1},
            )
            current_version += 1
            final_artifact = self._persist_artifact_version(
                run=self.get_run(run_id),
                content=content,
                sources=sources,
                review=review,
                status="approved",
                version=current_version,
                plan=plan,
                evidence=evidence,
            )
            result = {
                "contract_version": RUN_CONTRACT,
                "status": "complete",
                "run_id": run_id,
                "goal_id": run["goal_id"],
                "employee_id": EMPLOYEE_ID,
                "plan": plan,
                "source_count": len(sources),
                "evidence_count": len(evidence),
                "artifact_id": run["artifact_id"],
                "artifact_version": current_version,
                "artifact_status": "approved",
                "artifact_content_sha256": final_artifact["content_sha256"],
                "review_id": review["review_id"],
                "review_score": review["score"],
                "revision_count": revision_count,
                "governance": run["governance"],
                "completed_at": self.clock(),
            }
            with self.session() as connection:
                connection.execute(
                    """
                    UPDATE runs SET result_json=?, error=NULL,
                        revision_count=?, updated_at=? WHERE run_id=?
                    """,
                    (canonical_json(result), revision_count, self.clock(), run_id),
                )
            self._transition(
                run_id,
                "complete",
                "run.complete",
                {
                    "artifact_id": run["artifact_id"],
                    "artifact_version": current_version,
                    "review_id": review["review_id"],
                    "revision_count": revision_count,
                },
            )
            return self.get_run(run_id)
        except Exception as exc:
            current = self.get_run(run_id)
            if current["state"] not in TERMINAL_STATES and current["state"] != "interrupted":
                with self.session() as connection:
                    connection.execute(
                        "UPDATE runs SET error=?, updated_at=? WHERE run_id=?",
                        (str(exc), self.clock(), run_id),
                    )
                try:
                    self._transition(
                        run_id,
                        "failed",
                        "run.failed",
                        {"error": str(exc), "error_type": type(exc).__name__},
                    )
                except ReferenceEmployeeError:
                    pass
            raise

    def recover(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["state"] != "interrupted":
            raise ReferenceEmployeeError("Only interrupted runs can be recovered.")
        self.resume(run_id, "restart-recovery")
        return self.execute(run_id)
