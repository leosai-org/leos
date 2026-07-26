"""Deterministic, non-authoritative Work Domain conformance validation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .validation import ContractValidationError, ValidationIssue, validate_contract

WORK_DOMAIN_CONTRACTS = {
    "leos.work-request.v1",
    "leos.workflow-definition.v1",
    "leos.workflow-revision.v1",
    "leos.job-definition.v1",
    "leos.task-definition.v1",
    "leos.work-assignment.v1",
    "leos.work-delegation.v1",
    "leos.work-dependency.v1",
    "leos.work-result.v1",
    "leos.work-state-transition.v1",
    "leos.retry-intent.v1",
    "leos.escalation-intent.v1",
}
ORGANIZATION_REFERENCE_CONTRACTS = {
    "leos.organization.v1",
    "leos.department.v1",
    "leos.team.v1",
    "leos.role.v1",
    "leos.position.v1",
    "leos.employee-definition.v3",
    "leos.membership.v1",
    "leos.position-occupancy.v1",
}
WORK_TYPES = {
    "SCHEDULER_JOB",
    "TASK",
}
ACTIVE_RESPONSIBILITY_STATES = {"ACTIVE", "ACCEPTED"}
TERMINAL_WORK_STATES = {
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "VERIFIED",
    "CLOSED",
}
SATISFIED_DEPENDENCY_STATES = {"COMPLETED", "VERIFIED", "CLOSED"}

TRANSITIONS = {
    "WORK_REQUEST": {
        "DRAFT": {"SUBMITTED", "WITHDRAWN"},
        "SUBMITTED": {"UNDER_REVIEW", "WITHDRAWN"},
        "UNDER_REVIEW": {"ACCEPTED", "REJECTED", "WITHDRAWN"},
        "ACCEPTED": {"CONVERTED", "CLOSED"},
        "REJECTED": {"CLOSED"},
        "WITHDRAWN": {"CLOSED"},
        "CONVERTED": {"CLOSED"},
        "CLOSED": set(),
    },
    "WORKFLOW_DEFINITION": {
        "DRAFT": {"ACTIVE", "RETIRED"},
        "ACTIVE": {"DEPRECATED", "RETIRED"},
        "DEPRECATED": {"ACTIVE", "RETIRED"},
        "RETIRED": set(),
    },
    "WORKFLOW_REVISION": {
        "DRAFT": {"PUBLISHED", "REVOKED"},
        "PUBLISHED": {"SUPERSEDED", "REVOKED"},
        "SUPERSEDED": set(),
        "REVOKED": set(),
    },
    "SCHEDULER_JOB": {
        "DRAFT": {"READY", "CANCELLED"},
        "READY": {"ACTIVE", "BLOCKED", "PAUSED", "CANCELLED"},
        "ACTIVE": {
            "BLOCKED",
            "PAUSED",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "AWAITING_VERIFICATION",
        },
        "BLOCKED": {"READY", "ACTIVE", "PAUSED", "FAILED", "CANCELLED"},
        "PAUSED": {"READY", "ACTIVE", "CANCELLED"},
        "COMPLETED": {"AWAITING_VERIFICATION", "CLOSED"},
        "AWAITING_VERIFICATION": {"VERIFIED", "FAILED", "CANCELLED"},
        "VERIFIED": {"CLOSED"},
        "FAILED": set(),
        "CANCELLED": set(),
        "CLOSED": set(),
    },
    "TASK": {
        "DRAFT": {"READY", "CANCELLED"},
        "READY": {"ACTIVE", "BLOCKED", "PAUSED", "CANCELLED"},
        "ACTIVE": {
            "BLOCKED",
            "PAUSED",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "AWAITING_VERIFICATION",
        },
        "BLOCKED": {"READY", "ACTIVE", "PAUSED", "FAILED", "CANCELLED"},
        "PAUSED": {"READY", "ACTIVE", "CANCELLED"},
        "COMPLETED": {"AWAITING_VERIFICATION", "CLOSED"},
        "AWAITING_VERIFICATION": {"VERIFIED", "FAILED", "CANCELLED"},
        "VERIFIED": {"CLOSED"},
        "FAILED": set(),
        "CANCELLED": set(),
        "CLOSED": set(),
    },
    "WORK_ASSIGNMENT": {
        "PROPOSED": {"ACTIVE", "SUSPENDED", "REVOKED", "CANCELLED"},
        "ACTIVE": {
            "SUSPENDED",
            "COMPLETED",
            "SUPERSEDED",
            "REVOKED",
            "EXPIRED",
            "CANCELLED",
        },
        "SUSPENDED": {"ACTIVE", "REVOKED", "EXPIRED", "CANCELLED"},
        "COMPLETED": set(),
        "SUPERSEDED": set(),
        "REVOKED": set(),
        "EXPIRED": set(),
        "CANCELLED": set(),
    },
    "WORK_DELEGATION": {
        "PROPOSED": {"ACTIVE", "REVOKED", "CANCELLED"},
        "ACTIVE": {
            "COMPLETED",
            "SUPERSEDED",
            "REVOKED",
            "EXPIRED",
            "CANCELLED",
        },
        "COMPLETED": set(),
        "SUPERSEDED": set(),
        "REVOKED": set(),
        "EXPIRED": set(),
        "CANCELLED": set(),
    },
}


def _key(reference: Any) -> tuple[str, str] | None:
    if not isinstance(reference, dict):
        return None
    resource_type = reference.get("resource_type")
    resource_id = reference.get("resource_id")
    if isinstance(resource_type, str) and isinstance(resource_id, str):
        return resource_type, resource_id
    return None


def _target_key(target: Any) -> tuple[str, str] | None:
    if not isinstance(target, dict):
        return None
    target_type = target.get("target_type")
    if target_type == "PRINCIPAL":
        principal = target.get("principal")
        if isinstance(principal, dict):
            return "PRINCIPAL", principal.get("principal_id")
        return None
    return _key(target.get("resource"))


def _cycle_nodes(graph: dict[str, set[str]]) -> set[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            cycles.update(visiting)
            return
        if node in visited:
            return
        visiting.add(node)
        for child in graph.get(node, set()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return cycles


def validate_work_domain(documents: Iterable[dict[str, Any]]) -> None:
    """Validate a caller-supplied snapshot without granting domain authority.

    The validator has no storage, actor authentication, policy evaluation,
    selection, scheduling, invocation, approval verification, or lifecycle
    mutation behavior.
    """

    documents = list(documents)
    issues: list[ValidationIssue] = []
    records: dict[tuple[str, str], dict[str, Any]] = {}
    paths: dict[tuple[str, str], str] = {}
    valid: list[tuple[int, dict[str, Any]]] = []

    def add(path: str, message: str) -> None:
        issues.append(ValidationIssue("semantic", path, message))

    for index, document in enumerate(documents):
        path = f"$[{index}]"
        contract = (
            document.get("contract_version")
            if isinstance(document, dict)
            else None
        )
        if contract not in WORK_DOMAIN_CONTRACTS | ORGANIZATION_REFERENCE_CONTRACTS:
            add(path, "is not a supported Work Domain snapshot record")
            continue
        try:
            validate_contract(contract, document)
        except ContractValidationError as error:
            issues.extend(
                ValidationIssue(
                    issue.kind,
                    path + issue.path.removeprefix("$"),
                    issue.message,
                )
                for issue in error.issues
            )
            continue
        key = _key(document["identity"])
        if key in records:
            add(path + ".identity.resource_id", "duplicates a canonical identity")
            continue
        records[key] = document
        paths[key] = path
        valid.append((index, document))

    def resolve(
        reference: Any,
        path: str,
        expected: str | None = None,
    ) -> dict[str, Any] | None:
        key = _key(reference)
        if key is None:
            return None
        if expected is not None and key[0] != expected:
            add(path + ".resource_type", f"must reference {expected}")
            return None
        target = records.get(key)
        if target is None:
            add(path, "references an unresolved required snapshot resource")
            return None
        if reference.get("revision") != target["identity"]["revision"]:
            add(path + ".revision", "does not match the exact target revision")
            return None
        return target

    organizations = {
        key[1]: value
        for key, value in records.items()
        if key[0] == "ORGANIZATION"
    }

    def organization_id(document: dict[str, Any]) -> str | None:
        if document.get("identity", {}).get("resource_type") == "ORGANIZATION":
            return document["identity"].get("resource_id")
        reference = document.get("organization_ref")
        if isinstance(reference, dict):
            return reference.get("resource_id")
        return None

    def require_same_organization(
        source: dict[str, Any],
        target: dict[str, Any],
        path: str,
    ) -> None:
        if organization_id(source) != organization_id(target):
            add(path, "cross-organization Work Domain reference is prohibited")

    def resolve_target(
        source: dict[str, Any],
        target: dict[str, Any],
        path: str,
    ) -> dict[str, Any] | None:
        target_type = target.get("target_type")
        if target_type == "PRINCIPAL":
            principal = target.get("principal", {})
            if principal.get("principal_type") not in {
                "HUMAN_USER",
                "EMPLOYEE",
                "TEAM",
                "ORGANIZATION",
            }:
                add(path, "principal target type is not accepted for work responsibility")
            return None
        resource = resolve(target.get("resource"), path + ".resource", target_type)
        if resource is not None:
            require_same_organization(source, resource, path)
        return resource

    for index, document in valid:
        if document["contract_version"] not in WORK_DOMAIN_CONTRACTS:
            continue
        path = f"$[{index}]"
        identity = document["identity"]
        resource_type = identity["resource_type"]
        lifecycle_authority_id = identity["ownership"][
            "lifecycle_authority"
        ]["authority_id"]
        accepted_lifecycle_authorities = {
            "SCHEDULER_JOB": "execution-scheduler-service",
            "WORK_ASSIGNMENT": "persistent-employee-runtime-service",
        }
        expected_lifecycle_authority = accepted_lifecycle_authorities.get(
            resource_type
        )
        if (
            expected_lifecycle_authority is not None
            and lifecycle_authority_id != expected_lifecycle_authority
        ):
            add(
                path + ".identity.ownership.lifecycle_authority.authority_id",
                f"must remain {expected_lifecycle_authority}; no parallel "
                "lifecycle authority is accepted",
            )
        organization = resolve(
            document["organization_ref"],
            path + ".organization_ref",
            "ORGANIZATION",
        )
        if organization is not None:
            owner = identity["ownership"]["owner"]
            expected_owner = organization["organization_principal_ref"]
            if owner != expected_owner:
                add(
                    path + ".identity.ownership.owner",
                    "must be the containing Organization principal",
                )

        if resource_type == "WORK_REQUEST":
            if document["status"] in {"ACCEPTED", "CONVERTED"}:
                acceptance_transition = resolve(
                    document.get("acceptance_transition_ref"),
                    path + ".acceptance_transition_ref",
                    "WORK_STATE_TRANSITION",
                )
                if (
                    acceptance_transition is not None
                    and acceptance_transition["subject_ref"]
                    != {
                        "resource_type": "WORK_REQUEST",
                        "resource_id": identity["resource_id"],
                        "revision": identity["revision"],
                    }
                ):
                    add(
                        path + ".acceptance_transition_ref",
                        "acceptance transition must reference this exact "
                        "Work Request revision",
                    )
            if document["status"] == "CONVERTED":
                job = resolve(
                    document.get("conversion_job_ref"),
                    path + ".conversion_job_ref",
                    "SCHEDULER_JOB",
                )
                if job is not None:
                    require_same_organization(document, job, path + ".conversion_job_ref")

        elif resource_type == "WORKFLOW_DEFINITION":
            revision = resolve(
                document["current_revision_ref"],
                path + ".current_revision_ref",
                "WORKFLOW_REVISION",
            )
            if revision is not None:
                require_same_organization(document, revision, path + ".current_revision_ref")
                if revision["workflow_definition_ref"] != {
                    "resource_type": "WORKFLOW_DEFINITION",
                    "resource_id": identity["resource_id"],
                    "revision": identity["revision"],
                }:
                    add(
                        path + ".current_revision_ref",
                        "current revision must link back to this exact definition",
                    )
                if document["status"] == "ACTIVE" and revision["status"] != "PUBLISHED":
                    add(
                        path + ".current_revision_ref",
                        "active definition requires a published revision",
                    )
                if document["semantic_version"] != revision["semantic_version"]:
                    add(
                        path + ".semantic_version",
                        "definition and current revision semantic versions must match",
                    )

        elif resource_type == "WORKFLOW_REVISION":
            definition = resolve(
                document["workflow_definition_ref"],
                path + ".workflow_definition_ref",
                "WORKFLOW_DEFINITION",
            )
            if definition is not None:
                require_same_organization(document, definition, path + ".workflow_definition_ref")
            step_ids = [step["step_id"] for step in document["steps"]]
            if len(step_ids) != len(set(step_ids)):
                add(path + ".steps", "workflow step identities must be unique")
            step_set = set(step_ids)
            graph: dict[str, set[str]] = defaultdict(set)
            for edge_index, edge in enumerate(document["dependencies"]):
                edge_path = f"{path}.dependencies[{edge_index}]"
                source = edge["source_step_id"]
                dependency = edge["depends_on_step_id"]
                if source not in step_set or dependency not in step_set:
                    add(edge_path, "references an unknown workflow step")
                if source == dependency:
                    add(edge_path, "workflow step cannot depend on itself")
                if edge["relationship"] != "INFORMATIONAL":
                    graph[source].add(dependency)
                if (
                    edge["relationship"] == "CONDITIONAL"
                    and "condition_ref" not in edge
                ):
                    add(
                        edge_path + ".condition_ref",
                        "conditional dependency requires governed condition "
                        "evidence",
                    )
            for step_index, step in enumerate(document["steps"]):
                governance = step["governance"]
                if (
                    governance["approval_required"]
                    and not governance["approval_policy_refs"]
                ):
                    add(
                        f"{path}.steps[{step_index}].governance.approval_policy_refs",
                        "approval-required step must declare an approval policy",
                    )
                if (
                    governance["verification_required"]
                    and not governance["verification_criteria_refs"]
                ):
                    add(
                        f"{path}.steps[{step_index}].governance.verification_criteria_refs",
                        "verification-required step must declare criteria",
                    )
            for node in _cycle_nodes(graph):
                add(path + ".dependencies", f"workflow dependency cycle includes {node}")

        elif resource_type == "SCHEDULER_JOB":
            responsible_scope = resolve(
                document["responsible_scope"],
                path + ".responsible_scope",
            )
            if responsible_scope is not None:
                require_same_organization(
                    document,
                    responsible_scope,
                    path + ".responsible_scope",
                )
            request_ref = document.get("source_work_request_ref")
            if request_ref is not None:
                request = resolve(request_ref, path + ".source_work_request_ref", "WORK_REQUEST")
                if request is not None:
                    require_same_organization(document, request, path + ".source_work_request_ref")
                    if request["status"] not in {"ACCEPTED", "CONVERTED"}:
                        add(
                            path + ".source_work_request_ref",
                            "job requires an accepted Work Request",
                        )
            definition_ref = document.get("source_workflow_definition_ref")
            revision_ref = document.get("source_workflow_revision_ref")
            if (definition_ref is None) != (revision_ref is None):
                add(path, "workflow definition and revision references must appear together")
            if definition_ref is not None and revision_ref is not None:
                definition = resolve(
                    definition_ref,
                    path + ".source_workflow_definition_ref",
                    "WORKFLOW_DEFINITION",
                )
                revision = resolve(
                    revision_ref,
                    path + ".source_workflow_revision_ref",
                    "WORKFLOW_REVISION",
                )
                if definition is not None and revision is not None:
                    require_same_organization(
                        document,
                        definition,
                        path + ".source_workflow_definition_ref",
                    )
                    require_same_organization(
                        document,
                        revision,
                        path + ".source_workflow_revision_ref",
                    )
                    if revision["workflow_definition_ref"] != definition_ref:
                        add(
                            path + ".source_workflow_revision_ref",
                            "revision does not belong to source definition",
                        )
                    if revision["status"] != "PUBLISHED":
                        add(
                            path + ".source_workflow_revision_ref",
                            "job requires a published workflow revision",
                        )

        elif resource_type == "TASK":
            parent = document.get("parent_job_ref")
            if parent is not None:
                job = resolve(parent, path + ".parent_job_ref", "SCHEDULER_JOB")
                if job is not None:
                    require_same_organization(document, job, path + ".parent_job_ref")
            workflow_ref = document.get("source_workflow_revision_ref")
            step_id = document.get("source_workflow_step_id")
            if (workflow_ref is None) != (step_id is None):
                add(path, "workflow revision and step identity must appear together")
            if workflow_ref is not None:
                revision = resolve(
                    workflow_ref,
                    path + ".source_workflow_revision_ref",
                    "WORKFLOW_REVISION",
                )
                if revision is not None:
                    require_same_organization(
                        document,
                        revision,
                        path + ".source_workflow_revision_ref",
                    )
                    if revision["status"] != "PUBLISHED":
                        add(
                            path + ".source_workflow_revision_ref",
                            "task requires a published workflow revision",
                        )
                    if step_id not in {step["step_id"] for step in revision["steps"]}:
                        add(
                            path + ".source_workflow_step_id",
                            "references an unknown workflow step",
                        )
            for ref_index, reference in enumerate(document["dependency_refs"]):
                dependency = resolve(
                    reference,
                    f"{path}.dependency_refs[{ref_index}]",
                    "WORK_DEPENDENCY",
                )
                if dependency is not None and dependency["source_work_ref"] != {
                    "resource_type": "TASK",
                    "resource_id": identity["resource_id"],
                    "revision": identity["revision"],
                }:
                    add(
                        f"{path}.dependency_refs[{ref_index}]",
                        "dependency source must be this exact Task revision",
                    )

        if resource_type in WORK_TYPES:
            governance = document["governance"]
            if (
                governance["approval_required"]
                and not governance["approval_policy_refs"]
            ):
                add(
                    path + ".governance.approval_policy_refs",
                    "approval-required work must declare an approval policy",
                )
            if (
                governance["verification_required"]
                and not governance["verification_criteria_refs"]
            ):
                add(
                    path + ".governance.verification_criteria_refs",
                    "verification-required work must declare criteria",
                )
            work_reference = {
                "resource_type": resource_type,
                "resource_id": identity["resource_id"],
                "revision": identity["revision"],
            }
            for result_index, reference in enumerate(document["result_refs"]):
                result = resolve(
                    reference,
                    f"{path}.result_refs[{result_index}]",
                    "WORK_RESULT",
                )
                if result is not None and result["work_ref"] != work_reference:
                    add(
                        f"{path}.result_refs[{result_index}]",
                        "Result must reference this exact work revision",
                    )
            closure_ref = document.get("closure_transition_ref")
            if closure_ref is not None:
                closure = resolve(
                    closure_ref,
                    path + ".closure_transition_ref",
                    "WORK_STATE_TRANSITION",
                )
                if closure is not None and closure["subject_ref"] != work_reference:
                    add(
                        path + ".closure_transition_ref",
                        "closure transition must reference this exact work revision",
                    )

        if resource_type == "WORK_ASSIGNMENT":
            work = resolve(document["work_ref"], path + ".work_ref")
            if work is not None:
                require_same_organization(document, work, path + ".work_ref")
                constraints = work["assignment_constraints"]
                if document["assignee"]["target_type"] not in constraints["allowed_target_types"]:
                    add(path + ".assignee", "target type is not allowed by the work definition")
                if document["exclusive"] != constraints["exclusive_assignment"]:
                    add(path + ".exclusive", "must match the work assignment constraint")
            resolve_target(document, document["assignee"], path + ".assignee")
            scopes = {
                _key(reference)
                for reference in document["accepted_scope_refs"]
            }
            if _key(document["work_ref"]) not in scopes:
                add(path + ".accepted_scope_refs", "must include the assigned work")
            for scope_index, reference in enumerate(
                document["accepted_scope_refs"]
            ):
                scope = resolve(
                    reference,
                    f"{path}.accepted_scope_refs[{scope_index}]",
                )
                if scope is None:
                    continue
                require_same_organization(
                    document,
                    scope,
                    f"{path}.accepted_scope_refs[{scope_index}]",
                )
                if (
                    _key(reference) != _key(document["work_ref"])
                    and document["work_ref"]["resource_type"]
                    == "SCHEDULER_JOB"
                    and scope.get("parent_job_ref") != document["work_ref"]
                ):
                    add(
                        f"{path}.accepted_scope_refs[{scope_index}]",
                        "additional Assignment scope must be a Task of the assigned Job",
                    )
                elif (
                    _key(reference) != _key(document["work_ref"])
                    and document["work_ref"]["resource_type"] == "TASK"
                ):
                    add(
                        f"{path}.accepted_scope_refs[{scope_index}]",
                        "Task Assignment cannot expand to other work",
                    )
            for context_field, context_type in (
                ("role_context_ref", "ROLE"),
                ("position_context_ref", "POSITION"),
            ):
                context_ref = document.get(context_field)
                if context_ref is not None:
                    context = resolve(
                        context_ref,
                        f"{path}.{context_field}",
                        context_type,
                    )
                    if context is not None:
                        require_same_organization(
                            document,
                            context,
                            f"{path}.{context_field}",
                        )
            if document["assignment_reason"] in {"REASSIGNMENT", "REPLACEMENT"}:
                previous = resolve(
                    document.get("supersedes_assignment_ref"),
                    path + ".supersedes_assignment_ref",
                    "WORK_ASSIGNMENT",
                )
                if previous is None:
                    add(
                        path + ".supersedes_assignment_ref",
                        "reassignment must preserve the prior Assignment",
                    )

        elif resource_type == "WORK_DELEGATION":
            assignment = resolve(
                document["source_assignment_ref"],
                path + ".source_assignment_ref",
                "WORK_ASSIGNMENT",
            )
            if assignment is not None:
                require_same_organization(document, assignment, path + ".source_assignment_ref")
                if _target_key(document["delegating_target"]) != _target_key(
                    assignment["assignee"]
                ):
                    parent_ref = document.get("parent_delegation_ref")
                    if parent_ref is None:
                        add(
                            path + ".delegating_target",
                            "root delegator must be the source assignee",
                        )
                allowed_scope = {
                    _key(reference)
                    for reference in assignment["accepted_scope_refs"]
                }
                for scope_index, reference in enumerate(document["delegated_scope_refs"]):
                    if _key(reference) not in allowed_scope:
                        add(
                            f"{path}.delegated_scope_refs[{scope_index}]",
                            "delegation cannot expand source Assignment scope",
                        )
            resolve_target(document, document["delegating_target"], path + ".delegating_target")
            resolve_target(document, document["delegate_target"], path + ".delegate_target")
            parent_ref = document.get("parent_delegation_ref")
            if parent_ref is not None:
                parent = resolve(parent_ref, path + ".parent_delegation_ref", "WORK_DELEGATION")
                if parent is not None:
                    if parent["source_assignment_ref"] != document["source_assignment_ref"]:
                        add(
                            path + ".parent_delegation_ref",
                            "child delegation must preserve source Assignment",
                        )
                    if _target_key(parent["delegate_target"]) != _target_key(
                        document["delegating_target"]
                    ):
                        add(
                            path + ".delegating_target",
                            "child delegator must be the parent delegate",
                        )

        elif resource_type == "WORK_DEPENDENCY":
            source = resolve(document["source_work_ref"], path + ".source_work_ref")
            dependency = resolve(document["depends_on_work_ref"], path + ".depends_on_work_ref")
            if source is not None:
                require_same_organization(document, source, path + ".source_work_ref")
            if dependency is not None:
                require_same_organization(document, dependency, path + ".depends_on_work_ref")
            if _key(document["source_work_ref"]) == _key(document["depends_on_work_ref"]):
                add(path, "work cannot depend on itself")
            if (
                document["relationship"] == "CONDITIONAL"
                and "condition_ref" not in document
            ):
                add(
                    path + ".condition_ref",
                    "conditional dependency requires governed condition "
                    "evidence",
                )
            if (
                document["status"] in {"SATISFIED", "WAIVED"}
                and not document["satisfaction_evidence_refs"]
            ):
                add(
                    path + ".satisfaction_evidence_refs",
                    "satisfied or waived dependency requires evidence",
                )

        elif resource_type == "WORK_RESULT":
            work = resolve(document["work_ref"], path + ".work_ref")
            if work is not None:
                require_same_organization(document, work, path + ".work_ref")
                expected = {
                    output["output_id"]
                    for output in work["expected_outputs"]
                    if output["required"]
                }
                produced = {
                    output["output_id"]
                    for output in document["deliverables"]
                    if output["status"] == "PRODUCED"
                }
                if document["outcome"] == "SUCCEEDED" and not expected <= produced:
                    add(path + ".deliverables", "successful result omits a required output")
            assignment_ref = document.get("producing_assignment_ref")
            if assignment_ref is not None:
                assignment = resolve(
                    assignment_ref,
                    path + ".producing_assignment_ref",
                    "WORK_ASSIGNMENT",
                )
                if assignment is not None:
                    if assignment["work_ref"] != document["work_ref"]:
                        add(
                            path + ".producing_assignment_ref",
                            "result is outside Assignment scope",
                        )
                    assignee = assignment["assignee"]
                    if assignee["target_type"] == "EMPLOYEE":
                        employee = resolve(
                            assignee["resource"],
                            path + ".producing_assignment_ref.assignee",
                            "EMPLOYEE",
                        )
                        if (
                            employee is not None
                            and employee["employee_principal_ref"]
                            != document["producing_principal"]
                        ):
                            add(
                                path + ".producing_principal",
                                "producer does not match assigned Employee",
                            )
            for link_index, link in enumerate(document["artifact_links"]):
                if link["organization_ref"] != document["organization_ref"]:
                    add(
                        f"{path}.artifact_links[{link_index}]"
                        ".organization_ref",
                        "Artifact organization scope must match work",
                    )
            linked_outputs = {
                (
                    link["output_id"],
                    _key(link["artifact_ref"]),
                    link["artifact_ref"]["revision"],
                )
                for link in document["artifact_links"]
            }
            for deliverable_index, deliverable in enumerate(
                document["deliverables"]
            ):
                for artifact_index, artifact_ref in enumerate(
                    deliverable["artifact_refs"]
                ):
                    if (
                        deliverable["output_id"],
                        _key(artifact_ref),
                        artifact_ref["revision"],
                    ) not in linked_outputs:
                        add(
                            f"{path}.deliverables[{deliverable_index}]"
                            f".artifact_refs[{artifact_index}]",
                            "Artifact must have matching Organization and "
                            "producer provenance linkage",
                        )

        elif resource_type == "WORK_STATE_TRANSITION":
            subject = resolve(document["subject_ref"], path + ".subject_ref")
            if subject is not None:
                require_same_organization(document, subject, path + ".subject_ref")
                subject_authority = subject["identity"]["ownership"]["lifecycle_authority"]
                transition_authority = identity["ownership"]["lifecycle_authority"]
                if transition_authority != subject_authority:
                    add(
                        path + ".identity.ownership.lifecycle_authority",
                        "transition must be owned by subject lifecycle "
                        "authority",
                    )
                if document["resulting_revision"] != subject["identity"]["revision"]:
                    add(path + ".resulting_revision", "must match resulting subject revision")
                if document["to_state"] != subject["status"]:
                    add(path + ".to_state", "must match resulting subject state")
                allowed = TRANSITIONS.get(
                    subject["identity"]["resource_type"],
                    {},
                ).get(document["from_state"], set())
                if document["to_state"] not in allowed:
                    add(path + ".to_state", "is not a valid lifecycle transition")
                if (
                    document["to_state"]
                    in {
                        "COMPLETED",
                        "AWAITING_VERIFICATION",
                        "VERIFIED",
                        "CLOSED",
                    }
                    and not document["result_refs"]
                ):
                    add(
                        path + ".result_refs",
                        "completion transition requires Result evidence",
                    )
                if (
                    document["to_state"] in {"VERIFIED", "CLOSED"}
                    and subject.get("governance", {}).get(
                        "verification_required"
                    )
                    and not document["verification_evidence_refs"]
                ):
                    add(
                        path + ".verification_evidence_refs",
                        "verification-required transition lacks verification "
                        "evidence",
                    )
                if (
                    document["to_state"] == "CLOSED"
                    and "closure_authority_evidence_ref" not in document
                ):
                    add(
                        path + ".closure_authority_evidence_ref",
                        "closure requires authority evidence",
                    )
                for result_index, reference in enumerate(
                    document["result_refs"]
                ):
                    result = resolve(
                        reference,
                        f"{path}.result_refs[{result_index}]",
                        "WORK_RESULT",
                    )
                    if result is not None and result["work_ref"] != document["subject_ref"]:
                        add(
                            f"{path}.result_refs[{result_index}]",
                            "transition Result must reference the exact subject revision",
                        )

        elif resource_type == "RETRY_INTENT":
            work = resolve(document["work_ref"], path + ".work_ref")
            if work is not None:
                require_same_organization(document, work, path + ".work_ref")

        elif resource_type == "ESCALATION_INTENT":
            work = resolve(document["work_ref"], path + ".work_ref")
            if work is not None:
                require_same_organization(document, work, path + ".work_ref")
            assignment_ref = document.get("source_assignment_ref")
            if assignment_ref is not None:
                assignment = resolve(
                    assignment_ref,
                    path + ".source_assignment_ref",
                    "WORK_ASSIGNMENT",
                )
                if assignment is not None and assignment["work_ref"] != document["work_ref"]:
                    add(
                        path + ".source_assignment_ref",
                        "escalation Assignment must cover the same work",
                    )
            resolve_target(document, document["escalation_target"], path + ".escalation_target")

    assignment_groups: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    dependency_graph: dict[str, set[str]] = defaultdict(set)
    delegation_graph: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    delegation_parent_graph: dict[str, set[str]] = defaultdict(set)
    for index, document in valid:
        resource_type = document["identity"]["resource_type"]
        if (
            resource_type == "WORK_ASSIGNMENT"
            and document["status"] in ACTIVE_RESPONSIBILITY_STATES
        ):
            assignment_groups[_key(document["work_ref"])].append((index, document))
        elif (
            resource_type == "WORK_DEPENDENCY"
            and document["status"] == "ACTIVE"
            and document["relationship"] != "INFORMATIONAL"
        ):
            dependency_graph[document["source_work_ref"]["resource_id"]].add(
                document["depends_on_work_ref"]["resource_id"]
            )
        elif resource_type == "WORK_DELEGATION" and document["status"] == "ACTIVE":
            source = _target_key(document["delegating_target"])
            target = _target_key(document["delegate_target"])
            if source is not None and target is not None:
                delegation_graph[source].add(target)
            parent = document.get("parent_delegation_ref")
            if parent is not None:
                delegation_parent_graph[
                    document["identity"]["resource_id"]
                ].add(parent["resource_id"])

    for assignments in assignment_groups.values():
        if len(assignments) > 1 and any(document["exclusive"] for _, document in assignments):
            for index, _ in assignments:
                add(f"$[{index}]", "conflicting active exclusive Assignments are prohibited")
    for node in _cycle_nodes(dependency_graph):
        add("$", f"Task dependency cycle includes {node}")
    target_graph = {
        f"{source[0]}:{source[1]}": {f"{target[0]}:{target[1]}" for target in targets}
        for source, targets in delegation_graph.items()
    }
    for node in _cycle_nodes(target_graph):
        add("$", f"delegation responsibility cycle includes {node}")
    for node in _cycle_nodes(delegation_parent_graph):
        add("$", f"delegation parent cycle includes {node}")

    for index, document in valid:
        if document["identity"]["resource_type"] != "TASK" or document["status"] != "READY":
            continue
        for reference in document["dependency_refs"]:
            dependency = records.get(_key(reference))
            if (
                dependency is None
                or dependency["status"] != "ACTIVE"
                or dependency["relationship"] == "INFORMATIONAL"
            ):
                continue
            predecessor = records.get(_key(dependency["depends_on_work_ref"]))
            if predecessor is None or predecessor["status"] not in SATISFIED_DEPENDENCY_STATES:
                add(
                    f"$[{index}].status",
                    "READY is impossible while a required dependency is unsatisfied",
                )

    if issues:
        raise ContractValidationError(
            "leos.work-domain-conformance.v1",
            issues,
        )
