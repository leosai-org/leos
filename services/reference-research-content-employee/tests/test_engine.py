from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import (  # noqa: E402
    ADMISSION_CONTRACT,
    ARTIFACT_CONTRACT,
    ELIGIBILITY_CONTRACT,
    EMPLOYEE_ID,
    RESERVATION_CONTRACT,
    GovernanceError,
    ReferenceEmployeeError,
    ReferenceResearchContentEngine,
)


def governance(
    *,
    eligible: bool = True,
    admission: str = "admitted",
    reservation: str = "active",
    job_id: str = "job-1",
    reservation_job_id: str | None = None,
    execution_job_id: str | None = None,
    priority: str = "normal",
) -> dict:
    return {
        "employee_eligibility": {
            "contract_version": ELIGIBILITY_CONTRACT,
            "employee_id": EMPLOYEE_ID,
            "eligible": eligible,
            "decision": "eligible" if eligible else "queued",
            "reasons": [] if eligible else ["employee-paused"],
            "priority": priority,
        },
        "resource_admission": {
            "contract_version": ADMISSION_CONTRACT,
            "decision_id": "decision-1",
            "employee_id": EMPLOYEE_ID,
            "job_id": job_id,
            "decision": admission,
            "priority_class": priority,
            "priority_weight": 50,
            "reason": "capacity-available",
        },
        "resource_reservation": {
            "contract_version": RESERVATION_CONTRACT,
            "reservation_id": "reservation-1",
            "employee_id": EMPLOYEE_ID,
            "job_id": reservation_job_id or job_id,
            "node_id": "node-1",
            "status": reservation,
            "resources": {"cpu_cores": 1, "memory_mb": 512},
            "created_at": "2026-07-20T00:00:00+00:00",
            "expires_at": "2026-07-20T01:00:00+00:00",
        },
        "execution": {
            "job_id": execution_job_id or job_id,
            "assignment_id": "assignment-1",
            "execution_id": "execution-1",
            "priority": priority,
        },
    }


def source(
    *,
    source_id: str = "source-1",
    adapter_id: str = "manual-source-input",
    content: str | None = None,
) -> dict:
    return {
        "source_id": source_id,
        "title": "LEOS Architecture Notes",
        "url": "https://example.invalid/leos",
        "content": content
        or (
            "LEOS schedules employees only after lifecycle eligibility and resource admission. "
            "An active reservation is required before runtime execution begins. "
            "Artifacts retain source provenance, review findings, and execution lineage."
        ),
        "adapter_id": adapter_id,
        "provenance": {"adapter_id": adapter_id, "collection_id": "collection-1"},
    }


class ReferenceResearchContentEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "reference.db"
        self.engine = ReferenceResearchContentEngine(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def request(self, **overrides):
        value = {
            "run_id": "run-1",
            "artifact_id": "artifact-1",
            "goal_id": "goal-1",
            "goal": "Explain governed LEOS employee execution",
            "title": "Governed LEOS Employee Execution",
            "requested_by": "test-suite",
            "sources": [source()],
            "requirements": ["resource admission", "artifact lineage"],
            "approved_adapters": [
                "manual-source-input",
                "company-knowledge-service",
            ],
            "governance": governance(),
            "minimum_words": 180,
            "max_revision_attempts": 2,
        }
        value.update(overrides)
        return value

    def test_create_run_starts_accepted(self):
        run = self.engine.create_run(self.request())
        self.assertEqual(run["state"], "accepted")
        self.assertEqual(run["employee_id"], EMPLOYEE_ID)
        self.assertEqual(run["priority"], "normal")

    def test_ineligible_employee_is_rejected(self):
        with self.assertRaises(GovernanceError):
            self.engine.create_run(self.request(governance=governance(eligible=False)))

    def test_non_admitted_resource_decision_is_rejected(self):
        with self.assertRaises(GovernanceError):
            self.engine.create_run(self.request(governance=governance(admission="queued")))

    def test_inactive_reservation_is_rejected(self):
        with self.assertRaises(GovernanceError):
            self.engine.create_run(self.request(governance=governance(reservation="released")))

    def test_governance_job_identifiers_must_match(self):
        with self.assertRaises(GovernanceError):
            self.engine.create_run(
                self.request(
                    governance=governance(
                        reservation_job_id="job-2",
                        execution_job_id="job-3",
                    )
                )
            )

    def test_unknown_priority_is_rejected(self):
        with self.assertRaises(GovernanceError):
            self.engine.create_run(self.request(governance=governance(priority="urgent")))

    def test_unapproved_source_adapter_is_rejected_fail_closed(self):
        self.engine.create_run(
            self.request(sources=[source(adapter_id="public-web")])
        )
        with self.assertRaises(GovernanceError):
            self.engine.execute("run-1")
        self.assertEqual(self.engine.get_run("run-1")["state"], "failed")

    def test_empty_sources_are_rejected_before_drafting(self):
        self.engine.create_run(self.request(sources=[]))
        with self.assertRaises(GovernanceError):
            self.engine.execute("run-1")
        self.assertEqual(self.engine.get_run("run-1")["state"], "failed")

    def test_complete_execution_persists_approved_artifact(self):
        self.engine.create_run(self.request())
        run = self.engine.execute("run-1")
        self.assertEqual(run["state"], "complete")
        self.assertEqual(run["result"]["artifact_status"], "approved")
        artifact = self.engine.get_artifact("artifact-1")
        self.assertEqual(artifact["contract_version"], ARTIFACT_CONTRACT)
        self.assertEqual(artifact["status"], "approved")
        self.assertGreaterEqual(len(artifact["versions"]), 2)

    def test_source_provenance_and_content_hash_are_retained(self):
        self.engine.create_run(self.request())
        self.engine.execute("run-1")
        stored = self.engine.sources("run-1")[0]
        self.assertTrue(stored["provenance"]["approved"])
        self.assertEqual(
            stored["content_sha256"],
            stored["provenance"]["content_sha256"],
        )
        self.assertEqual(stored["provenance"]["adapter_id"], "manual-source-input")

    def test_execution_lineage_records_governance_identifiers(self):
        self.engine.create_run(self.request())
        self.engine.execute("run-1")
        artifact = self.engine.get_artifact("artifact-1")
        execution = artifact["data"]["execution"]
        self.assertEqual(execution["job_id"], "job-1")
        self.assertEqual(execution["assignment_id"], "assignment-1")
        self.assertEqual(execution["execution_id"], "execution-1")
        self.assertEqual(execution["reservation_id"], "reservation-1")

    def test_rejected_initial_draft_is_revised_and_approved(self):
        self.engine.create_run(
            self.request(initial_draft="Too short and guaranteed.")
        )
        run = self.engine.execute("run-1")
        self.assertEqual(run["state"], "complete")
        self.assertEqual(run["revision_count"], 1)
        artifact = self.engine.get_artifact("artifact-1")
        statuses = [item["status"] for item in artifact["versions"]]
        self.assertIn("revision_required", statuses)
        self.assertEqual(statuses[-1], "approved")

    def test_revision_limit_failure_is_terminal(self):
        self.engine.create_run(
            self.request(
                initial_draft="Too short and guaranteed.",
                max_revision_attempts=0,
            )
        )
        with self.assertRaises(ReferenceEmployeeError):
            self.engine.execute("run-1")
        self.assertEqual(self.engine.get_run("run-1")["state"], "failed")

    def test_history_records_governed_pipeline_stages(self):
        self.engine.create_run(self.request())
        self.engine.execute("run-1")
        history = self.engine.history("run-1")
        event_types = [item["event_type"] for item in history["events"]]
        for required in (
            "run.accepted",
            "run.planning.started",
            "run.research.started",
            "run.drafting.started",
            "run.review.completed",
            "run.persistence.started",
            "run.complete",
        ):
            self.assertIn(required, event_types)
        self.assertEqual(
            [item["sequence"] for item in history["events"]],
            list(range(1, history["event_count"] + 1)),
        )

    def test_pause_and_resume_before_execution(self):
        self.engine.create_run(self.request())
        paused = self.engine.pause("run-1", "maintenance")
        self.assertEqual(paused["state"], "paused")
        with self.assertRaises(ReferenceEmployeeError):
            self.engine.execute("run-1")
        resumed = self.engine.resume("run-1", "maintenance-complete")
        self.assertEqual(resumed["state"], "accepted")
        self.assertEqual(self.engine.execute("run-1")["state"], "complete")

    def test_cancel_is_terminal(self):
        self.engine.create_run(self.request())
        cancelled = self.engine.cancel("run-1", "operator-cancelled")
        self.assertEqual(cancelled["state"], "cancelled")
        with self.assertRaises(ReferenceEmployeeError):
            self.engine.execute("run-1")

    def test_restart_marks_inflight_run_interrupted(self):
        self.engine.create_run(self.request())
        with self.engine.session() as connection:
            connection.execute(
                "UPDATE runs SET state='researching', current_stage='researching' WHERE run_id='run-1'"
            )
        restarted = ReferenceResearchContentEngine(self.database)
        self.assertEqual(restarted.get_run("run-1")["state"], "interrupted")
        self.assertIn(
            "run.interrupted",
            [item["event_type"] for item in restarted.history("run-1")["events"]],
        )

    def test_recover_interrupted_run(self):
        self.engine.create_run(self.request())
        with self.engine.session() as connection:
            connection.execute(
                "UPDATE runs SET state='drafting', current_stage='drafting' WHERE run_id='run-1'"
            )
        restarted = ReferenceResearchContentEngine(self.database)
        recovered = restarted.recover("run-1")
        self.assertEqual(recovered["state"], "complete")

    def test_duplicate_run_id_is_rejected(self):
        self.engine.create_run(self.request())
        with self.assertRaises(ReferenceEmployeeError):
            self.engine.create_run(self.request())

    def test_requirements_are_present_in_final_content(self):
        self.engine.create_run(self.request())
        self.engine.execute("run-1")
        content = self.engine.get_artifact("artifact-1")["data"]["content"].lower()
        self.assertIn("resource admission", content)
        self.assertIn("artifact lineage", content)

    def test_all_sources_have_visible_citations(self):
        self.engine.create_run(
            self.request(
                sources=[
                    source(source_id="source-1"),
                    source(
                        source_id="source-2",
                        content=(
                            "Independent review separates content generation from approval. "
                            "Revision findings remain attached to artifact history."
                        ),
                    ),
                ]
            )
        )
        self.engine.execute("run-1")
        content = self.engine.get_artifact("artifact-1")["data"]["content"]
        self.assertIn("[S1]", content)
        self.assertIn("[S2]", content)

    def test_completed_execute_is_idempotent(self):
        self.engine.create_run(self.request())
        first = self.engine.execute("run-1")
        second = self.engine.execute("run-1")
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(
            len(self.engine.get_artifact("artifact-1")["versions"]),
            len(self.engine.get_artifact("artifact-1")["versions"]),
        )


if __name__ == "__main__":
    unittest.main()
