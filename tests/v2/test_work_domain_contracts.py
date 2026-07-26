from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = ROOT / "packages" / "leos-contracts" / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from leos_contracts import (  # noqa: E402
    ContractValidationError,
    validate_contract,
    validate_work_domain,
)

EXAMPLES = ROOT / "examples"
WORK_EXAMPLES = (
    "work-request",
    "workflow-definition",
    "workflow-revision",
    "job-definition",
    "task-definition",
    "work-assignment",
    "work-delegation",
    "work-dependency",
    "work-result",
    "work-state-transition",
    "retry-intent",
    "escalation-intent",
)


def read_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class WorkDomainContractTests(unittest.TestCase):
    def example(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(read_example(f"{name}.v1.json"))

    def assert_contract_invalid(self, document: dict[str, Any]) -> None:
        with self.assertRaises(ContractValidationError):
            validate_contract(document["contract_version"], document)

    def assert_bundle_invalid(self, documents: list[dict[str, Any]]) -> None:
        with self.assertRaises(ContractValidationError):
            validate_work_domain(documents)

    def request_acceptance_transition(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        transition = self.example("work-state-transition")
        transition["identity"]["resource_id"] = (
            "work-transition:acme:market-brief:accepted"
        )
        transition["identity"]["display_name"] = (
            "Market brief request accepted"
        )
        transition["identity"]["revision"] = (
            "sha256:work-transition-acme-market-brief-accepted-v1"
        )
        transition["identity"]["audit_id"] = (
            "audit:work-transition:acme:market-brief:accepted:v1"
        )
        authority = request["identity"]["ownership"]["lifecycle_authority"]
        transition["identity"]["ownership"]["lifecycle_authority"] = authority
        transition["identity"]["ownership"]["creator"] = authority["principal"]
        transition["identity"]["ownership"]["steward"] = authority["principal"]
        transition["state_evidence"]["transition_authority"] = authority
        transition["subject_ref"] = {
            "resource_type": "WORK_REQUEST",
            "resource_id": request["identity"]["resource_id"],
            "revision": request["identity"]["revision"],
        }
        transition["from_state"] = "UNDER_REVIEW"
        transition["to_state"] = "ACCEPTED"
        transition["expected_revision"] = (
            "sha256:work-request-acme-market-brief-v0"
        )
        transition["resulting_revision"] = request["identity"]["revision"]
        transition["reason"] = "The governed request was accepted."
        return transition

    def bundle(self) -> list[dict[str, Any]]:
        request = self.example("work-request")
        request["status"] = "ACCEPTED"
        transition = self.request_acceptance_transition(request)
        request["acceptance_transition_ref"] = {
            "resource_type": "WORK_STATE_TRANSITION",
            "resource_id": transition["identity"]["resource_id"],
            "revision": transition["identity"]["revision"],
        }
        return [
            read_example("organization.v1.json"),
            read_example("team.v1.json"),
            read_example("position.v1.json"),
            read_example("employee-definition.v3.json"),
            request,
            transition,
            self.example("workflow-definition"),
            self.example("workflow-revision"),
            self.example("job-definition"),
            self.example("task-definition"),
            self.example("work-assignment"),
            self.example("work-delegation"),
            self.example("work-result"),
            self.example("work-state-transition"),
            self.example("retry-intent"),
            self.example("escalation-intent"),
        ]

    def test_all_canonical_examples_validate(self):
        for name in WORK_EXAMPLES:
            with self.subTest(name=name):
                document = self.example(name)
                validate_contract(document["contract_version"], document)

    def test_all_schemas_are_valid_and_identifiers_are_unique(self):
        names = ["work-common.v1.schema.json"] + [
            f"{name}.v1.schema.json" for name in WORK_EXAMPLES
        ]
        identifiers = []
        for name in names:
            schema = json.loads(
                (ROOT / "contracts" / name).read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(schema)
            identifiers.append(schema["$id"])
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_complete_reference_bundle_validates(self):
        validate_work_domain(self.bundle())

    def test_work_request_cannot_select_employee_or_self_authorize(self):
        for field, value in (
            (
                "selected_employee_ref",
                {
                    "resource_type": "EMPLOYEE",
                    "resource_id": "employee:acme:researcher",
                    "revision": "sha256:employee-acme-researcher-v3",
                },
            ),
            ("authorization_granted", True),
            ("execute_now", True),
        ):
            request = self.example("work-request")
            request[field] = value
            with self.subTest(field=field):
                self.assert_contract_invalid(request)

    def test_accepted_request_requires_governed_transition(self):
        request = self.example("work-request")
        request["status"] = "ACCEPTED"
        self.assert_contract_invalid(request)

    def test_request_acceptance_transition_must_match_exact_request(self):
        bundle = self.bundle()
        bundle[5]["subject_ref"]["resource_id"] = "work-request:other"
        self.assert_bundle_invalid(bundle)

    def test_workflow_definition_is_not_a_running_instance(self):
        definition = self.example("workflow-definition")
        definition["running_instance_id"] = "workflow-run:1"
        self.assert_contract_invalid(definition)

    def test_published_workflow_revision_is_immutable(self):
        revision = self.example("workflow-revision")
        revision["immutable"] = False
        self.assert_contract_invalid(revision)

    def test_workflow_step_dependency_unknown_self_and_cycles_fail(self):
        for mutation in ("unknown", "self", "cycle"):
            bundle = self.bundle()
            revision = bundle[7]
            if mutation == "unknown":
                revision["dependencies"][0]["depends_on_step_id"] = "unknown"
            elif mutation == "self":
                revision["dependencies"][0]["depends_on_step_id"] = "review"
            else:
                revision["dependencies"].append(
                    {
                        "source_step_id": "research",
                        "depends_on_step_id": "review",
                        "relationship": "FINISH_TO_START",
                        "join": "REQUIRED",
                    }
                )
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_workflow_version_and_governance_declarations_are_exact(self):
        for mutation in ("version", "approval", "verification"):
            bundle = self.bundle()
            if mutation == "version":
                bundle[6]["semantic_version"] = "2.0.0"
            elif mutation == "approval":
                bundle[7]["steps"][0]["governance"][
                    "approval_required"
                ] = True
            else:
                bundle[7]["steps"][0]["governance"][
                    "verification_required"
                ] = True
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_job_requires_organization_scope_and_cannot_invoke_tool(self):
        job = self.example("job-definition")
        job.pop("organization_ref")
        self.assert_contract_invalid(job)
        job = self.example("job-definition")
        job["tool_invocation"] = {"tool_id": "tool:unsafe"}
        self.assert_contract_invalid(job)

    def test_job_responsible_scope_must_resolve_in_same_organization(self):
        bundle = self.bundle()
        bundle[8]["responsible_scope"]["resource_id"] = "organization:other"
        self.assert_bundle_invalid(bundle)

    def test_job_requires_accepted_request_and_published_exact_workflow(self):
        for mutation in ("request", "revision-status", "stale-revision"):
            bundle = self.bundle()
            if mutation == "request":
                bundle[4]["status"] = "SUBMITTED"
                bundle[4].pop("acceptance_transition_ref")
            elif mutation == "revision-status":
                bundle[7]["status"] = "DRAFT"
            else:
                bundle[8]["source_workflow_revision_ref"]["revision"] = (
                    "sha256:stale"
                )
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_task_is_not_assignment_execution_or_provider_selection(self):
        for field, value in (
            ("assignee", {"target_type": "EMPLOYEE"}),
            ("execution_request", {}),
            ("selected_provider_id", "provider:cheap"),
            ("ranked_employee_ids", ["employee:a", "employee:b"]),
        ):
            task = self.example("task-definition")
            task[field] = value
            with self.subTest(field=field):
                self.assert_contract_invalid(task)

    def test_task_completion_requires_result(self):
        task = self.example("task-definition")
        task["status"] = "COMPLETED"
        self.assert_contract_invalid(task)

    def test_task_closure_requires_verification_and_closure_evidence(self):
        task = self.example("task-definition")
        task["status"] = "CLOSED"
        task["governance"]["verification_required"] = True
        task["result_refs"] = [
            {
                "resource_type": "WORK_RESULT",
                "resource_id": "result:x",
                "revision": "sha256:result-x",
            }
        ]
        self.assert_contract_invalid(task)

    def test_task_workflow_step_and_parent_are_exact_and_known(self):
        for field, value in (
            ("source_workflow_step_id", "unknown"),
            ("parent_job_ref", {
                "resource_type": "SCHEDULER_JOB",
                "resource_id": "job:unknown",
                "revision": "sha256:unknown",
            }),
        ):
            bundle = self.bundle()
            bundle[9][field] = value
            with self.subTest(field=field):
                self.assert_bundle_invalid(bundle)

    def test_assignment_requires_work_and_valid_target_type(self):
        assignment = self.example("work-assignment")
        assignment.pop("work_ref")
        self.assert_contract_invalid(assignment)
        assignment = self.example("work-assignment")
        assignment["assignee"] = {
            "target_type": "RUNTIME",
            "resource": {
                "resource_type": "RUNTIME",
                "resource_id": "runtime:local",
                "revision": "sha256:runtime-local",
            },
        }
        self.assert_contract_invalid(assignment)

    def test_assignment_is_not_authorization_approval_or_execution(self):
        for field in (
            "authorized",
            "approval_granted",
            "execution_id",
            "provider_id",
            "tool_id",
        ):
            assignment = self.example("work-assignment")
            assignment[field] = True
            with self.subTest(field=field):
                self.assert_contract_invalid(assignment)

    def test_assignment_target_must_be_allowed_and_same_organization(self):
        for mutation in ("disallowed", "cross-org"):
            bundle = self.bundle()
            assignment = bundle[10]
            if mutation == "disallowed":
                assignment["assignee"] = {
                    "target_type": "POSITION",
                    "resource": copy.deepcopy(bundle[2]["identity"]),
                }
                assignment["assignee"]["resource"].pop("display_name")
                assignment["assignee"]["resource"].pop("ownership")
                assignment["assignee"]["resource"].pop(
                    "creation_actor_context_ref"
                )
                assignment["assignee"]["resource"].pop(
                    "creation_authority_evidence_ref"
                )
                assignment["assignee"]["resource"].pop("audit_id")
                assignment["assignee"]["resource"].pop("created_at")
                assignment["assignee"]["resource"].pop("updated_at")
            else:
                assignment["assignee"]["resource"]["resource_id"] = (
                    "employee:other:researcher"
                )
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_duplicate_active_exclusive_assignment_fails(self):
        bundle = self.bundle()
        duplicate = copy.deepcopy(bundle[10])
        duplicate["identity"]["resource_id"] = "assignment:duplicate"
        duplicate["identity"]["revision"] = "sha256:assignment-duplicate"
        duplicate["identity"]["audit_id"] = "audit:assignment:duplicate"
        bundle.append(duplicate)
        self.assert_bundle_invalid(bundle)

    def test_reassignment_preserves_prior_assignment(self):
        bundle = self.bundle()
        assignment = bundle[10]
        assignment["assignment_reason"] = "REASSIGNMENT"
        self.assert_bundle_invalid(bundle)

    def test_assignment_accepted_scope_cannot_expand_or_be_unresolved(self):
        bundle = self.bundle()
        bundle[10]["accepted_scope_refs"].append(
            {
                "resource_type": "TASK",
                "resource_id": "task:unknown",
                "revision": "sha256:task-unknown",
            }
        )
        self.assert_bundle_invalid(bundle)

    def test_delegation_requires_source_assignment_and_preserves_source(self):
        delegation = self.example("work-delegation")
        delegation.pop("source_assignment_ref")
        self.assert_contract_invalid(delegation)
        delegation = self.example("work-delegation")
        delegation["source_responsibility_preserved"] = False
        self.assert_contract_invalid(delegation)

    def test_delegation_cannot_create_authority_or_execution(self):
        for field in (
            "authorization_decision",
            "approval_granted",
            "execute_now",
            "provider_id",
        ):
            delegation = self.example("work-delegation")
            delegation[field] = True
            with self.subTest(field=field):
                self.assert_contract_invalid(delegation)

    def test_delegation_scope_cannot_expand_assignment(self):
        bundle = self.bundle()
        bundle[11]["delegated_scope_refs"][0]["resource_id"] = "task:other"
        self.assert_bundle_invalid(bundle)

    def test_root_delegator_must_be_source_assignee(self):
        bundle = self.bundle()
        bundle[11]["delegating_target"] = copy.deepcopy(
            bundle[11]["delegate_target"]
        )
        self.assert_bundle_invalid(bundle)

    def test_delegation_target_and_parent_cycles_fail(self):
        bundle = self.bundle()
        second = copy.deepcopy(bundle[11])
        second["identity"]["resource_id"] = "delegation:second"
        second["identity"]["revision"] = "sha256:delegation-second"
        second["identity"]["audit_id"] = "audit:delegation:second"
        second["parent_delegation_ref"] = {
            "resource_type": "WORK_DELEGATION",
            "resource_id": bundle[11]["identity"]["resource_id"],
            "revision": bundle[11]["identity"]["revision"],
        }
        second["delegating_target"] = copy.deepcopy(
            bundle[11]["delegate_target"]
        )
        second["delegate_target"] = copy.deepcopy(
            bundle[11]["delegating_target"]
        )
        bundle.append(second)
        self.assert_bundle_invalid(bundle)

    def dependency_bundle(self) -> list[dict[str, Any]]:
        bundle = self.bundle()
        review = copy.deepcopy(bundle[9])
        review["identity"]["resource_id"] = "task:acme:market-brief:review"
        review["identity"]["revision"] = (
            "sha256:task-acme-market-brief-review-v1"
        )
        review["identity"]["audit_id"] = (
            "audit:task:acme:market-brief:review:v1"
        )
        review["source_workflow_step_id"] = "review"
        review["status"] = "BLOCKED"
        dependency = self.example("work-dependency")
        review["dependency_refs"] = [
            {
                "resource_type": "WORK_DEPENDENCY",
                "resource_id": dependency["identity"]["resource_id"],
                "revision": dependency["identity"]["revision"],
            }
        ]
        bundle.extend((review, dependency))
        return bundle

    def test_dependency_reference_is_exact_known_and_same_organization(self):
        for mutation in ("unknown", "stale", "cross-org"):
            bundle = self.dependency_bundle()
            dependency = bundle[-1]
            if mutation == "unknown":
                dependency["depends_on_work_ref"]["resource_id"] = "task:unknown"
            elif mutation == "stale":
                dependency["depends_on_work_ref"]["revision"] = "sha256:stale"
            else:
                dependency["organization_ref"]["resource_id"] = (
                    "organization:other"
                )
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_task_dependency_cycle_fails(self):
        bundle = self.dependency_bundle()
        reverse = copy.deepcopy(bundle[-1])
        reverse["identity"]["resource_id"] = "dependency:reverse"
        reverse["identity"]["revision"] = "sha256:dependency-reverse"
        reverse["identity"]["audit_id"] = "audit:dependency:reverse"
        reverse["source_work_ref"], reverse["depends_on_work_ref"] = (
            reverse["depends_on_work_ref"],
            reverse["source_work_ref"],
        )
        bundle.append(reverse)
        self.assert_bundle_invalid(bundle)

    def test_conditional_and_satisfied_dependency_requires_evidence(self):
        for mutation in ("condition", "satisfaction"):
            bundle = self.dependency_bundle()
            dependency = bundle[-1]
            if mutation == "condition":
                dependency["relationship"] = "CONDITIONAL"
            else:
                dependency["status"] = "SATISFIED"
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_impossible_ready_state_with_unsatisfied_dependency_fails(self):
        bundle = self.dependency_bundle()
        bundle[-2]["status"] = "READY"
        self.assert_bundle_invalid(bundle)

    def test_result_requires_producer_and_exact_assignment_scope(self):
        result = self.example("work-result")
        result.pop("producing_principal")
        self.assert_contract_invalid(result)
        bundle = self.bundle()
        bundle[12]["work_ref"]["resource_id"] = "task:other"
        self.assert_bundle_invalid(bundle)

    def test_result_required_output_and_artifact_lineage_are_enforced(self):
        for mutation in ("output", "organization", "producer", "artifact"):
            bundle = self.bundle()
            result = bundle[12]
            if mutation == "output":
                result["deliverables"] = []
            elif mutation == "organization":
                result["artifact_links"][0]["organization_ref"][
                    "resource_id"
                ] = "organization:other"
            else:
                if mutation == "producer":
                    result["artifact_links"][0]["producer_ref"] = {
                        "principal_id": "principal:user:other",
                        "principal_type": "HUMAN_USER",
                    }
                else:
                    result["artifact_links"][0]["artifact_ref"][
                        "resource_id"
                    ] = "artifact:other"
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_invalid_lifecycle_transition_and_stale_revision_fail(self):
        for mutation in ("invalid", "stale", "authority", "caller-complete"):
            bundle = self.bundle()
            transition = bundle[13]
            if mutation == "invalid":
                transition["from_state"] = "CLOSED"
            elif mutation == "stale":
                transition["resulting_revision"] = "sha256:stale"
            elif mutation == "authority":
                transition["identity"]["ownership"]["lifecycle_authority"][
                    "authority_id"
                ] = "caller"
            else:
                transition["to_state"] = "COMPLETED"
                transition["result_refs"] = []
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_state_evidence_must_match_lifecycle_authority(self):
        task = self.example("task-definition")
        task["state_evidence"]["transition_authority"]["authority_id"] = (
            "caller"
        )
        self.assert_contract_invalid(task)

    def test_retry_preserves_history_and_uses_new_attempt_identity(self):
        retry = self.example("retry-intent")
        retry["preserves_history"] = False
        self.assert_contract_invalid(retry)
        retry = self.example("retry-intent")
        retry["requested_attempt_ref"] = copy.deepcopy(
            retry["prior_attempt_refs"][0]
        )
        self.assert_contract_invalid(retry)

    def test_cancellation_transition_preserves_history(self):
        transition = self.example("work-state-transition")
        transition["to_state"] = "CANCELLED"
        transition["history_refs"] = []
        self.assert_contract_invalid(transition)

    def test_escalation_cannot_create_or_silently_change_assignment(self):
        escalation = self.example("escalation-intent")
        escalation["creates_assignment"] = True
        self.assert_contract_invalid(escalation)
        escalation = self.example("escalation-intent")
        escalation["replacement_assignment_ref"] = escalation[
            "source_assignment_ref"
        ]
        self.assert_contract_invalid(escalation)

    def test_team_target_never_becomes_execution_authority(self):
        assignment = self.example("work-assignment")
        assignment["assignee"] = {
            "target_type": "TEAM",
            "resource": {
                "resource_type": "TEAM",
                "resource_id": "team:acme:market-research",
                "revision": "sha256:team-acme-market-research-v1",
            },
        }
        assignment["team_executes"] = True
        self.assert_contract_invalid(assignment)

    def test_capability_requirement_cannot_select_or_authorize(self):
        task = self.example("task-definition")
        task["required_capability_refs"] = [
            {
                "resource_type": "CAPABILITY",
                "resource_id": "capability:research",
                "revision": "sha256:capability-research-v1",
                "selected_provider_id": "provider:one",
            }
        ]
        self.assert_contract_invalid(task)

    def test_fixture_cannot_claim_production_authority(self):
        request = self.example("work-request")
        request["record_mode"] = {
            "kind": "DEVELOPMENT_FIXTURE",
            "authoritative": False,
            "production_eligible": True,
        }
        self.assert_contract_invalid(request)

    def test_public_assignment_service_is_not_a_contract_authority(self):
        assignment = self.example("work-assignment")
        assignment["identity"]["ownership"]["lifecycle_authority"][
            "authority_id"
        ] = "public-assignment-service"
        assignment["state_evidence"]["transition_authority"] = copy.deepcopy(
            assignment["identity"]["ownership"]["lifecycle_authority"]
        )
        bundle = self.bundle()
        bundle[10] = assignment
        # Lifecycle projection remains accepted only for Persistent Runtime.
        self.assert_bundle_invalid(bundle)

    def test_raw_secret_and_credential_fields_are_rejected(self):
        for field in ("password", "api_key", "credential", "secret_value"):
            task = self.example("task-definition")
            task[field] = "forbidden"
            with self.subTest(field=field):
                self.assert_contract_invalid(task)

    def test_unknown_contract_is_rejected_by_reference_validator(self):
        document = self.example("task-definition")
        document["contract_version"] = "leos.assignment-service.v1"
        self.assert_bundle_invalid([document])


if __name__ == "__main__":
    unittest.main()
