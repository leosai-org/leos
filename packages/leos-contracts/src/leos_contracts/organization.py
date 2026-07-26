from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from .validation import (
    ContractValidationError,
    ValidationIssue,
    validate_contract,
)

ORGANIZATION_RESOURCE_CONTRACTS = {
    "leos.organization.v1",
    "leos.department.v1",
    "leos.team.v1",
    "leos.role.v1",
    "leos.position.v1",
    "leos.employee-definition.v3",
    "leos.membership.v1",
    "leos.position-occupancy.v1",
}
ORGANIZATION_EVIDENCE_CONTRACTS = {
    "leos.organization-lifecycle-transition.v1",
    "leos.event-envelope.v1",
}
ORGANIZATION_DOMAIN_CONTRACTS = (
    ORGANIZATION_RESOURCE_CONTRACTS | ORGANIZATION_EVIDENCE_CONTRACTS
)
ACTIVE_ORGANIZATION_STATES = {"ACTIVE"}
ACTIVE_EMPLOYEE_STATES = {"ACTIVE"}
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise ValueError("not an RFC3339 date-time")
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is None:
        raise ValueError("not an RFC3339 date-time")
    return parsed


def validate_organization_domain(
    documents: Iterable[dict[str, Any]],
    *,
    observed_at: str,
) -> None:
    """Validate a deterministic, non-authoritative organization record set.

    This validates cross-record invariants that JSON Schema cannot express. It
    neither persists records nor authenticates, authorizes, approves, or
    performs lifecycle transitions.
    """

    issues: list[ValidationIssue] = []
    records: dict[tuple[str, str], dict[str, Any]] = {}
    paths: dict[tuple[str, str], str] = {}
    valid_documents: list[tuple[int, dict[str, Any]]] = []
    transitions: list[tuple[int, dict[str, Any]]] = []
    events: list[tuple[int, dict[str, Any]]] = []
    identities: dict[tuple[str, str], str] = {}

    try:
        observed = _timestamp(observed_at)
    except (TypeError, ValueError):
        raise ContractValidationError(
            "leos.organization-domain-conformance.v1",
            (
                ValidationIssue(
                    "semantic",
                    "$.observed_at",
                    "must be an RFC3339 date-time",
                ),
            ),
        ) from None

    def add(path: str, message: str) -> None:
        issues.append(ValidationIssue("semantic", path, message))

    for index, document in enumerate(documents):
        path = f"$[{index}]"
        contract = (
            document.get("contract_version")
            if isinstance(document, dict)
            else None
        )
        if contract not in ORGANIZATION_DOMAIN_CONTRACTS:
            add(path, "is not a supported Organization Domain record")
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
        valid_documents.append((index, document))
        identity = document["identity"]
        key = (identity["resource_type"], identity["resource_id"])
        if key in identities:
            add(path + ".identity.resource_id", "duplicates a canonical identity")
            continue
        identities[key] = path
        if contract in ORGANIZATION_RESOURCE_CONTRACTS:
            records[key] = document
            paths[key] = path
        elif contract == "leos.organization-lifecycle-transition.v1":
            transitions.append((index, document))
        else:
            events.append((index, document))

    def resolve(
        reference: Any,
        path: str,
        expected_type: str | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(reference, dict):
            return None
        resource_type = reference.get("resource_type")
        if expected_type is not None and resource_type != expected_type:
            add(path + ".resource_type", f"must reference {expected_type}")
            return None
        key = (resource_type, reference.get("resource_id"))
        target = records.get(key)
        if target is None:
            add(path, "references an orphaned Organization Domain resource")
            return None
        if reference.get("revision") != target["identity"]["revision"]:
            add(path + ".revision", "does not match the current target revision")
            return None
        return target

    organizations = {
        key[1]: value
        for key, value in records.items()
        if key[0] == "ORGANIZATION"
    }
    organization_principals: dict[str, list[str]] = defaultdict(list)
    for resource_id, organization in organizations.items():
        organization_principals[
            organization["organization_principal_ref"]["principal_id"]
        ].append(paths[("ORGANIZATION", resource_id)])
    employee_principals = {
        value["employee_principal_ref"]["principal_id"]: value
        for (resource_type, _), value in records.items()
        if resource_type == "EMPLOYEE"
    }
    employee_principal_paths: dict[str, list[str]] = defaultdict(list)
    for (resource_type, resource_id), employee in records.items():
        if resource_type == "EMPLOYEE":
            employee_principal_paths[
                employee["employee_principal_ref"]["principal_id"]
            ].append(paths[(resource_type, resource_id)])
    for binding_paths in (
        *organization_principals.values(),
        *employee_principal_paths.values(),
    ):
        if len(binding_paths) > 1:
            for path in binding_paths:
                add(
                    path,
                    "a principal may bind to only one canonical domain resource",
                )

    def organization_for(
        document: dict[str, Any],
        path: str,
    ) -> dict[str, Any] | None:
        if document["identity"]["resource_type"] == "ORGANIZATION":
            return document
        return resolve(document.get("organization_ref"), path, "ORGANIZATION")

    for index, document in valid_documents:
        if document["contract_version"] not in ORGANIZATION_RESOURCE_CONTRACTS:
            continue
        path = f"$[{index}]"
        resource_type = document["identity"]["resource_type"]
        organization = organization_for(
            document,
            path + ".organization_ref",
        )
        if organization is None:
            continue
        organization_principal = organization["organization_principal_ref"]
        owner = document["identity"]["ownership"]["owner"]
        if resource_type != "ORGANIZATION" and owner != organization_principal:
            add(
                path + ".identity.ownership.owner",
                "must be the containing Organization principal",
            )
        if resource_type not in {"ORGANIZATION", "EMPLOYEE"}:
            if (
                document["identity"]["ownership"]["lifecycle_authority"]
                != organization["identity"]["ownership"]["lifecycle_authority"]
            ):
                add(
                    path + ".identity.ownership.lifecycle_authority",
                    "must match the containing Organization Domain authority",
                )

        if resource_type == "DEPARTMENT":
            parent = document.get("parent_department_ref")
            if parent is not None:
                parent_value = resolve(
                    parent,
                    path + ".parent_department_ref",
                    "DEPARTMENT",
                )
                if (
                    parent_value is not None
                    and parent_value["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        path + ".parent_department_ref",
                        "cross-organization department parent is prohibited",
                    )

        if resource_type == "TEAM":
            department = document.get("department_ref")
            if department is not None:
                department_value = resolve(
                    department,
                    path + ".department_ref",
                    "DEPARTMENT",
                )
                if (
                    department_value is not None
                    and department_value["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        path + ".department_ref",
                        "cross-organization department reference is prohibited",
                    )
            for role_index, role in enumerate(document["role_refs"]):
                role_value = resolve(
                    role,
                    f"{path}.role_refs[{role_index}]",
                    "ROLE",
                )
                if (
                    role_value is not None
                    and role_value["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        f"{path}.role_refs[{role_index}]",
                        "cross-organization Role reference is prohibited",
                    )

        if resource_type == "EMPLOYEE":
            for role_index, role in enumerate(document["role_refs"]):
                role_value = resolve(
                    role,
                    f"{path}.role_refs[{role_index}]",
                    "ROLE",
                )
                if (
                    role_value is not None
                    and role_value["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        f"{path}.role_refs[{role_index}]",
                        "cross-organization Employee Role is prohibited",
                    )

        if resource_type == "POSITION":
            for field, expected in (
                ("department_ref", "DEPARTMENT"),
                ("team_ref", "TEAM"),
                ("role_ref", "ROLE"),
                ("reports_to_position_ref", "POSITION"),
            ):
                reference = document.get(field)
                if reference is None:
                    continue
                target = resolve(reference, f"{path}.{field}", expected)
                if (
                    target is not None
                    and target["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        f"{path}.{field}",
                        f"cross-organization {expected} reference is prohibited",
                    )

        if resource_type == "MEMBERSHIP":
            container = resolve(
                document["container_ref"],
                path + ".container_ref",
            )
            if container is not None:
                container_organization = (
                    container["identity"]["resource_id"]
                    if container["identity"]["resource_type"] == "ORGANIZATION"
                    else container["organization_ref"]["resource_id"]
                )
                if container_organization != organization["identity"]["resource_id"]:
                    add(
                        path + ".container_ref",
                        "cross-organization membership is prohibited",
                    )
            member = document["member"]
            if member["principal_type"] == "EMPLOYEE":
                employee = employee_principals.get(member["principal_id"])
                if employee is None:
                    add(
                        path + ".member",
                        "references an unknown Employee principal",
                    )
                elif (
                    employee["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        path + ".member",
                        "cross-organization Employee membership is prohibited",
                    )
            for role_index, role in enumerate(document["role_refs"]):
                role_value = resolve(
                    role,
                    f"{path}.role_refs[{role_index}]",
                    "ROLE",
                )
                if (
                    role_value is not None
                    and role_value["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        f"{path}.role_refs[{role_index}]",
                        "cross-organization membership Role is prohibited",
                    )
            if document["status"] == "ACTIVE":
                effective_from = document["effective_from"]
                if _timestamp(effective_from) > observed:
                    add(
                        path + ".status",
                        "future membership cannot be treated as ACTIVE",
                    )
                effective_until = document.get("effective_until")
                if effective_until and _timestamp(effective_until) <= observed:
                    add(
                        path + ".status",
                        "expired membership cannot be treated as ACTIVE",
                    )

        if resource_type == "POSITION_OCCUPANCY":
            position = resolve(
                document["position_ref"],
                path + ".position_ref",
                "POSITION",
            )
            employee = resolve(
                document["employee_ref"],
                path + ".employee_ref",
                "EMPLOYEE",
            )
            for field, target in (
                ("position_ref", position),
                ("employee_ref", employee),
            ):
                if (
                    target is not None
                    and target["organization_ref"]["resource_id"]
                    != organization["identity"]["resource_id"]
                ):
                    add(
                        f"{path}.{field}",
                        "cross-organization Position Occupancy is prohibited",
                    )
            if document["status"] == "ACTIVE":
                if _timestamp(document["effective_from"]) > observed:
                    add(
                        path + ".status",
                        "future Position Occupancy cannot be treated as ACTIVE",
                    )
                effective_until = document.get("effective_until")
                if effective_until and _timestamp(effective_until) <= observed:
                    add(
                        path + ".status",
                        "ended Position Occupancy cannot be treated as ACTIVE",
                    )

    def detect_cycle(
        resource_type: str,
        reference_field: str,
        label: str,
    ) -> None:
        edges: dict[str, str] = {}
        for (kind, resource_id), document in records.items():
            if kind != resource_type:
                continue
            reference = document.get(reference_field)
            if isinstance(reference, dict):
                edges[resource_id] = reference["resource_id"]
        for start in sorted(edges):
            seen: set[str] = set()
            current = start
            while current in edges:
                if current in seen:
                    add(paths[(resource_type, start)] + f".{reference_field}", label)
                    break
                seen.add(current)
                current = edges[current]

    detect_cycle(
        "DEPARTMENT",
        "parent_department_ref",
        "cyclic Department hierarchy is prohibited",
    )
    detect_cycle(
        "POSITION",
        "reports_to_position_ref",
        "cyclic supervisory Position hierarchy is prohibited",
    )

    active_memberships: dict[tuple[str, str], list[str]] = defaultdict(list)
    employee_organization_memberships: dict[str, list[str]] = defaultdict(list)
    active_occupancies: dict[str, list[str]] = defaultdict(list)
    for (resource_type, resource_id), document in records.items():
        path = paths[(resource_type, resource_id)]
        if resource_type == "MEMBERSHIP" and document["status"] == "ACTIVE":
            key = (
                document["member"]["principal_id"],
                document["container_ref"]["resource_id"],
            )
            active_memberships[key].append(path)
            if document["membership_kind"] == "EMPLOYEE_ORGANIZATION":
                employee_organization_memberships[
                    document["member"]["principal_id"]
                ].append(path)
        if (
            resource_type == "POSITION_OCCUPANCY"
            and document["status"] == "ACTIVE"
        ):
            active_occupancies[
                document["position_ref"]["resource_id"]
            ].append(path)
    for paths_for_key in active_memberships.values():
        if len(paths_for_key) > 1:
            for path in paths_for_key:
                add(path + ".status", "duplicate active membership is prohibited")
    for paths_for_position in active_occupancies.values():
        if len(paths_for_position) > 1:
            for path in paths_for_position:
                add(
                    path + ".status",
                    "a Position may have only one active occupancy",
                )
    for principal_id, employee in employee_principals.items():
        if employee["status"] != "ACTIVE":
            continue
        memberships = employee_organization_memberships.get(principal_id, [])
        if len(memberships) != 1:
            key = ("EMPLOYEE", employee["identity"]["resource_id"])
            add(
                paths[key] + ".organization_ref",
                "an ACTIVE Employee requires exactly one active "
                "Organization membership",
            )

    for (resource_type, resource_id), document in records.items():
        path = paths[(resource_type, resource_id)]
        status = document.get("status")
        if resource_type == "ORGANIZATION":
            continue
        organization = organizations.get(
            document.get("organization_ref", {}).get("resource_id")
        )
        if (
            status in ACTIVE_ORGANIZATION_STATES | ACTIVE_EMPLOYEE_STATES
            and organization is not None
            and organization["status"] not in ACTIVE_ORGANIZATION_STATES
        ):
            add(
                path + ".status",
                "an active child requires an ACTIVE Organization",
            )
        if resource_type == "TEAM" and status == "ACTIVE":
            department_ref = document.get("department_ref")
            if isinstance(department_ref, dict):
                department = records.get(
                    ("DEPARTMENT", department_ref["resource_id"])
                )
                if department is not None and department["status"] != "ACTIVE":
                    add(
                        path + ".status",
                        "an active Team requires an ACTIVE Department",
                    )
        if resource_type == "DEPARTMENT" and status == "ACTIVE":
            parent_ref = document.get("parent_department_ref")
            if isinstance(parent_ref, dict):
                parent = records.get(
                    ("DEPARTMENT", parent_ref["resource_id"])
                )
                if parent is not None and parent["status"] != "ACTIVE":
                    add(
                        path + ".status",
                        "an active Department requires an ACTIVE parent Department",
                    )
        if resource_type == "POSITION" and status == "ACTIVE":
            for field, expected in (
                ("department_ref", "DEPARTMENT"),
                ("team_ref", "TEAM"),
                ("role_ref", "ROLE"),
            ):
                reference = document.get(field)
                target = (
                    records.get((expected, reference["resource_id"]))
                    if isinstance(reference, dict)
                    else None
                )
                if target is not None and target["status"] != "ACTIVE":
                    add(
                        path + ".status",
                        f"an active Position requires an ACTIVE {expected}",
                    )
        if resource_type == "MEMBERSHIP" and status == "ACTIVE":
            container_ref = document["container_ref"]
            container = records.get(
                (
                    container_ref["resource_type"],
                    container_ref["resource_id"],
                )
            )
            if container is not None and container.get("status") != "ACTIVE":
                add(
                    path + ".status",
                    "an active Membership requires an active container",
                )
            employee = employee_principals.get(document["member"]["principal_id"])
            if employee is not None and employee["status"] != "ACTIVE":
                add(
                    path + ".status",
                    "an active Employee membership requires an ACTIVE Employee",
                )
        if resource_type == "POSITION_OCCUPANCY" and status == "ACTIVE":
            position = records.get(
                ("POSITION", document["position_ref"]["resource_id"])
            )
            employee = records.get(
                ("EMPLOYEE", document["employee_ref"]["resource_id"])
            )
            if position is not None and position["status"] != "ACTIVE":
                add(path + ".status", "active occupancy requires ACTIVE Position")
            if employee is not None and employee["status"] != "ACTIVE":
                add(path + ".status", "active occupancy requires ACTIVE Employee")

    event_records = {
        (
            event["identity"]["resource_id"],
            event["identity"]["revision"],
        ): (index, event)
        for index, event in events
    }
    referenced_events: dict[tuple[str, str], list[str]] = defaultdict(list)
    for index, transition in transitions:
        path = f"$[{index}]"
        subject_ref = transition["subject_ref"]
        subject_key = (
            subject_ref["resource_type"],
            subject_ref["resource_id"],
        )
        subject = records.get(subject_key)
        if subject is None:
            add(
                path + ".subject_ref",
                "references an orphaned Organization Domain resource",
            )
            continue
        if subject["identity"]["revision"] != transition["resulting_revision"]:
            add(
                path + ".resulting_revision",
                "must match the canonical resulting resource revision",
            )
        if subject["status"] != transition["to_status"]:
            add(
                path + ".to_status",
                "must match the canonical resulting resource status",
            )
        for field in ("owner", "lifecycle_authority"):
            if (
                transition["identity"]["ownership"][field]
                != subject["identity"]["ownership"][field]
            ):
                add(
                    f"{path}.identity.ownership.{field}",
                    f"must match the transitioned resource {field}",
                )
        authority_principal = subject["identity"]["ownership"][
            "lifecycle_authority"
        ]["principal"]
        for field in ("creator", "steward"):
            if transition["identity"]["ownership"][field] != authority_principal:
                add(
                    f"{path}.identity.ownership.{field}",
                    f"must be the transitioned resource authority principal",
                )

        event_ref = transition["resulting_event_ref"]
        event_key = (event_ref["resource_id"], event_ref["revision"])
        referenced_events[event_key].append(path)
        event_entry = event_records.get(event_key)
        if event_entry is None:
            add(
                path + ".resulting_event_ref",
                "references an absent canonical transition Event",
            )
            continue
        event_index, event = event_entry
        event_path = f"$[{event_index}]"
        expected_subject = {
            "resource_type": subject["identity"]["resource_type"],
            "resource_id": subject["identity"]["resource_id"],
            "revision": transition["resulting_revision"],
        }
        if event["subject"] != expected_subject:
            add(
                event_path + ".subject",
                "must identify the canonical resulting resource revision",
            )
        expected_creation_evidence = {
            "authority_id": transition["identity"]["ownership"][
                "lifecycle_authority"
            ]["authority_id"],
            "reference_id": transition["identity"]["resource_id"],
            "revision": transition["identity"]["revision"],
        }
        if (
            event["identity"]["creation_authority_evidence_ref"]
            != expected_creation_evidence
        ):
            add(
                event_path + ".identity.creation_authority_evidence_ref",
                "must identify the canonical lifecycle transition",
            )
        if event["actor_context_ref"] != transition["actor_context_ref"]:
            add(
                event_path + ".actor_context_ref",
                "must match the lifecycle transition Actor Context",
            )
        if (
            event["causation"]["reference_id"]
            != transition["authorization_decision_ref"]["resource_id"]
        ):
            add(
                event_path + ".causation.reference_id",
                "must identify the transition Authorization Decision",
            )
        for field in ("owner", "lifecycle_authority"):
            if (
                event["identity"]["ownership"][field]
                != subject["identity"]["ownership"][field]
            ):
                add(
                    f"{event_path}.identity.ownership.{field}",
                    f"must match the transitioned resource {field}",
                )
        for field in ("creator", "steward"):
            if event["identity"]["ownership"][field] != authority_principal:
                add(
                    f"{event_path}.identity.ownership.{field}",
                    f"must be the transitioned resource authority principal",
                )
        expected_payload = {
            "from_status": transition["from_status"],
            "to_status": transition["to_status"],
            "resulting_revision": transition["resulting_revision"],
        }
        if event["payload"] != expected_payload:
            add(
                event_path + ".payload",
                "must exactly represent the canonical lifecycle transition",
            )

    for index, event in events:
        path = f"$[{index}]"
        event_key = (
            event["identity"]["resource_id"],
            event["identity"]["revision"],
        )
        references = referenced_events.get(event_key, [])
        if not references:
            add(
                path,
                "Organization Domain Event is not linked to a lifecycle transition",
            )
        elif len(references) > 1:
            add(
                path,
                "Organization Domain Event is linked by multiple transitions",
            )

    if issues:
        raise ContractValidationError(
            "leos.organization-domain-conformance.v1",
            issues,
        )
