from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACT_ROOT_ENV = "LEOS_CONTRACT_ROOT"
SCHEMA_RESOURCES = (
    "trust-common.v1.schema.json",
    "organization-common.v1.schema.json",
    "capability-plugin-common.v1.schema.json",
    "work-common.v1.schema.json",
)
SUPPORTED_CONTRACTS = (
    "resource-identity.v1.schema.json",
    "principal.v1.schema.json",
    "actor-context.v1.schema.json",
    "authorization-decision.v1.schema.json",
    "approval-request.v1.schema.json",
    "approval-grant.v1.schema.json",
    "approval-verification-result.v1.schema.json",
    "artifact-trust-evidence.v1.schema.json",
    "secret-reference.v1.schema.json",
    "event-envelope.v1.schema.json",
    "organization.v1.schema.json",
    "department.v1.schema.json",
    "team.v1.schema.json",
    "role.v1.schema.json",
    "position.v1.schema.json",
    "employee-definition.v3.schema.json",
    "membership.v1.schema.json",
    "position-occupancy.v1.schema.json",
    "organization-lifecycle-transition.v1.schema.json",
    "capability-definition.v1.schema.json",
    "tool-definition.v1.schema.json",
    "plugin-definition.v1.schema.json",
    "plugin-manifest.v1.schema.json",
    "provider-definition.v1.schema.json",
    "plugin-installation.v1.schema.json",
    "plugin-activation.v1.schema.json",
    "capability-profile.v1.schema.json",
    "runtime-requirement.v1.schema.json",
    "compatibility-evidence.v1.schema.json",
    "permission-declaration.v1.schema.json",
    "plugin-revocation.v1.schema.json",
    "execution-correlation.v1.schema.json",
    "execution.v1.schema.json",
    "capability-resolution-request.v1.schema.json",
    "capability-resolution-result.v1.schema.json",
    "execution-result.v1.schema.json",
    "effective-ranking-request.v1.schema.json",
    "effective-ranking-result.v1.schema.json",
    "work-request.v1.schema.json",
    "workflow-definition.v1.schema.json",
    "workflow-revision.v1.schema.json",
    "job-definition.v1.schema.json",
    "task-definition.v1.schema.json",
    "work-assignment.v1.schema.json",
    "work-delegation.v1.schema.json",
    "work-dependency.v1.schema.json",
    "work-result.v1.schema.json",
    "work-state-transition.v1.schema.json",
    "retry-intent.v1.schema.json",
    "escalation-intent.v1.schema.json",
)
CONTRACT_VERSIONS = {
    "leos.resource-identity.v1": "resource-identity.v1.schema.json",
    "leos.principal.v1": "principal.v1.schema.json",
    "leos.actor-context.v1": "actor-context.v1.schema.json",
    "leos.authorization-decision.v1":
        "authorization-decision.v1.schema.json",
    "leos.approval-request.v1": "approval-request.v1.schema.json",
    "leos.approval-grant.v1": "approval-grant.v1.schema.json",
    "leos.approval-verification-result.v1":
        "approval-verification-result.v1.schema.json",
    "leos.artifact-trust-evidence.v1":
        "artifact-trust-evidence.v1.schema.json",
    "leos.secret-reference.v1": "secret-reference.v1.schema.json",
    "leos.event-envelope.v1": "event-envelope.v1.schema.json",
    "leos.organization.v1": "organization.v1.schema.json",
    "leos.department.v1": "department.v1.schema.json",
    "leos.team.v1": "team.v1.schema.json",
    "leos.role.v1": "role.v1.schema.json",
    "leos.position.v1": "position.v1.schema.json",
    "leos.employee-definition.v3": "employee-definition.v3.schema.json",
    "leos.membership.v1": "membership.v1.schema.json",
    "leos.position-occupancy.v1": "position-occupancy.v1.schema.json",
    "leos.organization-lifecycle-transition.v1":
        "organization-lifecycle-transition.v1.schema.json",
    "leos.capability-definition.v1":
        "capability-definition.v1.schema.json",
    "leos.tool-definition.v1": "tool-definition.v1.schema.json",
    "leos.plugin-definition.v1": "plugin-definition.v1.schema.json",
    "leos.plugin-manifest.v1": "plugin-manifest.v1.schema.json",
    "leos.provider-definition.v1": "provider-definition.v1.schema.json",
    "leos.plugin-installation.v1": "plugin-installation.v1.schema.json",
    "leos.plugin-activation.v1": "plugin-activation.v1.schema.json",
    "leos.capability-profile.v1": "capability-profile.v1.schema.json",
    "leos.runtime-requirement.v1": "runtime-requirement.v1.schema.json",
    "leos.compatibility-evidence.v1":
        "compatibility-evidence.v1.schema.json",
    "leos.permission-declaration.v1":
        "permission-declaration.v1.schema.json",
    "leos.plugin-revocation.v1": "plugin-revocation.v1.schema.json",
    "leos.execution-correlation.v1": "execution-correlation.v1.schema.json",
    "leos.execution.v1": "execution.v1.schema.json",
    "leos.capability-resolution-request.v1":
        "capability-resolution-request.v1.schema.json",
    "leos.capability-resolution-result.v1":
        "capability-resolution-result.v1.schema.json",
    "leos.execution-result.v1": "execution-result.v1.schema.json",
    "leos.effective-ranking-request.v1":
        "effective-ranking-request.v1.schema.json",
    "leos.effective-ranking-result.v1":
        "effective-ranking-result.v1.schema.json",
    "leos.work-request.v1": "work-request.v1.schema.json",
    "leos.workflow-definition.v1": "workflow-definition.v1.schema.json",
    "leos.workflow-revision.v1": "workflow-revision.v1.schema.json",
    "leos.job-definition.v1": "job-definition.v1.schema.json",
    "leos.task-definition.v1": "task-definition.v1.schema.json",
    "leos.work-assignment.v1": "work-assignment.v1.schema.json",
    "leos.work-delegation.v1": "work-delegation.v1.schema.json",
    "leos.work-dependency.v1": "work-dependency.v1.schema.json",
    "leos.work-result.v1": "work-result.v1.schema.json",
    "leos.work-state-transition.v1":
        "work-state-transition.v1.schema.json",
    "leos.retry-intent.v1": "retry-intent.v1.schema.json",
    "leos.escalation-intent.v1": "escalation-intent.v1.schema.json",
}
RESERVED_APPROVAL_SHORTCUTS = {
    "allow_approval_required",
    "approval_granted",
    "approved",
    "has_approval",
}
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


@dataclass(frozen=True)
class ValidationIssue:
    kind: str
    path: str
    message: str


class ContractValidationError(ValueError):
    def __init__(self, contract_id: str, issues: Iterable[ValidationIssue]):
        self.contract_id = contract_id
        self.issues = tuple(issues)
        super().__init__(
            f"{contract_id} failed validation with {len(self.issues)} issue(s)"
        )


class ContractRootError(RuntimeError):
    """The governed contract authority is unavailable or invalid."""


def _validate_contract_root(root: Path) -> Path:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ContractRootError(f"LEOS contract root does not exist: {root}")
    missing = [
        name
        for name in (*SCHEMA_RESOURCES, *SUPPORTED_CONTRACTS)
        if not (root / name).is_file()
    ]
    if missing:
        raise ContractRootError(
            f"LEOS contract root is incomplete: {root}; "
            f"missing {', '.join(missing)}"
        )
    return root


def _source_checkout_root(module_file: Path) -> Path | None:
    module_file = module_file.resolve()
    try:
        repository_root = module_file.parents[4]
    except IndexError:
        return None
    expected_package = (
        repository_root
        / "packages"
        / "leos-contracts"
        / "src"
        / "leos_contracts"
    )
    if module_file.parent != expected_package:
        return None
    if not (repository_root / "AGENTS.md").is_file():
        return None
    if not (repository_root / "docs" / "architecture" / "v2").is_dir():
        return None
    if not (repository_root / "contracts").is_dir():
        return None
    return repository_root


def contract_root() -> Path:
    configured = os.getenv(CONTRACT_ROOT_ENV)
    if configured:
        return _validate_contract_root(Path(configured))
    repository_root = _source_checkout_root(Path(__file__))
    if repository_root is None:
        raise ContractRootError(
            "LEOS_CONTRACT_ROOT is required outside a positively identified "
            "LEOS source checkout"
        )
    return _validate_contract_root(repository_root / "contracts")


def _schema_name(contract_id: str) -> str:
    if contract_id in SUPPORTED_CONTRACTS:
        return contract_id
    if contract_id in CONTRACT_VERSIONS:
        return CONTRACT_VERSIONS[contract_id]
    suffix = contract_id.rsplit("/", 1)[-1]
    if suffix in SUPPORTED_CONTRACTS:
        return suffix
    raise KeyError(f"unsupported LEOS contract: {contract_id}")


def _load_schemas() -> dict[str, dict[str, Any]]:
    root = contract_root()
    schemas = {}
    for name in (*SCHEMA_RESOURCES, *SUPPORTED_CONTRACTS):
        try:
            schemas[name] = json.loads(
                (root / name).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise ContractRootError(
                f"invalid governed contract schema {root / name}: {error}"
            ) from error
    return schemas


def validate_schema(contract_id: str, document: Any) -> tuple[ValidationIssue, ...]:
    name = _schema_name(contract_id)
    schemas = _load_schemas()
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(
            schema["$id"],
            Resource.from_contents(schema),
        )
    validator = Draft202012Validator(
        schemas[name],
        registry=registry,
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    return tuple(
        ValidationIssue(
            kind="schema",
            path="$" + "".join(
                f"[{part}]" if isinstance(part, int) else f".{part}"
                for part in error.absolute_path
            ),
            message=error.message,
        )
        for error in errors
    )


def validate_semantics(
    contract_id: str,
    document: Any,
) -> tuple[ValidationIssue, ...]:
    name = _schema_name(contract_id)
    errors: list[ValidationIssue] = []
    if not isinstance(document, dict):
        return ()

    def add(path: str, message: str) -> None:
        errors.append(ValidationIssue("semantic", path, message))

    def equal_when_present(
        left: Any,
        right: Any,
        path: str,
        description: str,
    ) -> None:
        if left is not None and right is not None and left != right:
            add(path, f"{description} must match")

    def validate_timestamp(value: Any, path: str) -> None:
        valid = isinstance(value, str) and bool(RFC3339.fullmatch(value))
        if valid:
            try:
                parsed = datetime.fromisoformat(
                    value[:-1] + "+00:00"
                    if value.endswith("Z")
                    else value
                )
                valid = parsed.tzinfo is not None
            except ValueError:
                valid = False
        if not valid:
            add(path, "must be RFC3339 date-time")

    def parsed_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not RFC3339.fullmatch(value):
            return None
        try:
            parsed = datetime.fromisoformat(
                value[:-1] + "+00:00"
                if value.endswith("Z")
                else value
            )
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None

    def require_chronology(
        earlier: Any,
        later: Any,
        path: str,
        description: str,
        *,
        allow_equal: bool = True,
    ) -> None:
        earlier_value = parsed_timestamp(earlier)
        later_value = parsed_timestamp(later)
        if earlier_value is None or later_value is None:
            return
        valid = (
            earlier_value <= later_value
            if allow_equal
            else earlier_value < later_value
        )
        if not valid:
            add(path, description)

    foundation_identity_types = {
        "principal.v1.schema.json": "PRINCIPAL",
        "actor-context.v1.schema.json": "ACTOR_CONTEXT",
        "authorization-decision.v1.schema.json": "AUTHORIZATION_DECISION",
        "approval-request.v1.schema.json": "APPROVAL_REQUEST",
        "approval-grant.v1.schema.json": "APPROVAL_GRANT",
        "approval-verification-result.v1.schema.json":
            "APPROVAL_VERIFICATION",
        "artifact-trust-evidence.v1.schema.json":
            "ARTIFACT_TRUST_EVIDENCE",
        "secret-reference.v1.schema.json": "SECRET_REFERENCE",
        "event-envelope.v1.schema.json": "EVENT",
        "organization.v1.schema.json": "ORGANIZATION",
        "department.v1.schema.json": "DEPARTMENT",
        "team.v1.schema.json": "TEAM",
        "role.v1.schema.json": "ROLE",
        "position.v1.schema.json": "POSITION",
        "employee-definition.v3.schema.json": "EMPLOYEE",
        "membership.v1.schema.json": "MEMBERSHIP",
        "position-occupancy.v1.schema.json": "POSITION_OCCUPANCY",
        "organization-lifecycle-transition.v1.schema.json":
            "ORGANIZATION_TRANSITION",
        "capability-definition.v1.schema.json": "CAPABILITY",
        "tool-definition.v1.schema.json": "TOOL",
        "plugin-definition.v1.schema.json": "PLUGIN",
        "plugin-manifest.v1.schema.json": "PLUGIN_MANIFEST",
        "provider-definition.v1.schema.json": "PROVIDER",
        "plugin-installation.v1.schema.json": "PLUGIN_INSTALLATION",
        "plugin-activation.v1.schema.json": "PLUGIN_ACTIVATION",
        "capability-profile.v1.schema.json": "CAPABILITY_PROFILE",
        "runtime-requirement.v1.schema.json": "RUNTIME_REQUIREMENT",
        "compatibility-evidence.v1.schema.json":
            "COMPATIBILITY_EVIDENCE",
        "permission-declaration.v1.schema.json":
            "PERMISSION_DECLARATION",
        "plugin-revocation.v1.schema.json": "PLUGIN_REVOCATION",
        "work-request.v1.schema.json": "WORK_REQUEST",
        "workflow-definition.v1.schema.json": "WORKFLOW_DEFINITION",
        "workflow-revision.v1.schema.json": "WORKFLOW_REVISION",
        "job-definition.v1.schema.json": "SCHEDULER_JOB",
        "task-definition.v1.schema.json": "TASK",
        "work-assignment.v1.schema.json": "WORK_ASSIGNMENT",
        "work-delegation.v1.schema.json": "WORK_DELEGATION",
        "work-dependency.v1.schema.json": "WORK_DEPENDENCY",
        "work-result.v1.schema.json": "WORK_RESULT",
        "work-state-transition.v1.schema.json": "WORK_STATE_TRANSITION",
        "retry-intent.v1.schema.json": "RETRY_INTENT",
        "escalation-intent.v1.schema.json": "ESCALATION_INTENT",
    }
    foundation_contracts = {
        "resource-identity.v1.schema.json",
        *foundation_identity_types,
    }
    if name in foundation_contracts:
        identity = document.get("identity")
        if isinstance(identity, dict):
            expected_type = foundation_identity_types.get(name)
            if (
                expected_type is not None
                and identity.get("resource_type") != expected_type
            ):
                add(
                    "$.identity.resource_type",
                    f"must be {expected_type} for this contract",
                )
            for field in ("created_at", "updated_at"):
                if field in identity:
                    validate_timestamp(
                        identity[field],
                        f"$.identity.{field}",
                    )
            require_chronology(
                identity.get("created_at"),
                identity.get("updated_at"),
                "$.identity.updated_at",
                "updated_at must not precede created_at",
            )
            creation_actor = identity.get("creation_actor_context_ref")
            if (
                isinstance(creation_actor, dict)
                and creation_actor.get("resource_type") != "ACTOR_CONTEXT"
            ):
                add(
                    "$.identity.creation_actor_context_ref.resource_type",
                    "must reference an ACTOR_CONTEXT",
                )

    if name == "principal.v1.schema.json":
        principal_type = document.get("principal_type")
        subject = document.get("subject_ref")
        expected_subject_types = {
            "HUMAN_USER": "USER",
            "SERVICE": "SERVICE",
            "ORGANIZATION": "ORGANIZATION",
            "DEPARTMENT": "DEPARTMENT",
            "TEAM": "TEAM",
            "EMPLOYEE": "EMPLOYEE",
            "RUNTIME": "RUNTIME",
            "PLUGIN": "PLUGIN",
            "PUBLISHER": "PUBLISHER",
        }
        if isinstance(subject, dict):
            expected_subject_type = expected_subject_types.get(principal_type)
            if (
                expected_subject_type is not None
                and subject.get("resource_type") != expected_subject_type
            ):
                add(
                    "$.subject_ref.resource_type",
                    f"a {principal_type} principal subject must be "
                    f"{expected_subject_type}",
                )
        elif principal_type != "HUMAN_USER":
            add(
                "$.subject_ref",
                "non-human principals require a governed subject resource",
            )

    if name == "actor-context.v1.schema.json":
        authentication = document.get("authentication")
        if isinstance(authentication, dict):
            equal_when_present(
                document.get("actor"),
                authentication.get("subject"),
                "$.authentication.subject",
                "actor and authenticated subject",
            )
            identity = document.get("identity")
            ownership = (
                identity.get("ownership")
                if isinstance(identity, dict)
                else None
            )
            if isinstance(ownership, dict):
                equal_when_present(
                    authentication.get("issuer"),
                    ownership.get("lifecycle_authority"),
                    "$.authentication.issuer",
                    "authentication issuer and Actor Context "
                    "lifecycle authority",
                )
            if "authenticated_at" in authentication:
                validate_timestamp(
                    authentication["authenticated_at"],
                    "$.authentication.authenticated_at",
                )
            require_chronology(
                authentication.get("authenticated_at"),
                document.get("issued_at"),
                "$.issued_at",
                "issued_at must not precede authentication",
            )
        for field in ("issued_at", "expires_at"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("issued_at"),
            document.get("expires_at"),
            "$.expires_at",
            "expires_at must be later than issued_at",
            allow_equal=False,
        )

    if name == "authorization-decision.v1.schema.json":
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("authority"),
                ownership.get("lifecycle_authority"),
                "$.authority",
                "decision authority and lifecycle authority",
            )
        for field in ("decided_at", "valid_until"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("decided_at"),
            document.get("valid_until"),
            "$.valid_until",
            "valid_until must be later than decided_at",
            allow_equal=False,
        )

    if name == "approval-request.v1.schema.json":
        for field in ("requested_at", "expires_at"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("requested_at"),
            document.get("expires_at"),
            "$.expires_at",
            "expires_at must be later than requested_at",
            allow_equal=False,
        )

    if name == "approval-grant.v1.schema.json":
        request_ref = document.get("request_ref")
        if (
            isinstance(request_ref, dict)
            and request_ref.get("resource_type") != "APPROVAL_REQUEST"
        ):
            add(
                "$.request_ref.resource_type",
                "must reference an APPROVAL_REQUEST",
            )
        scope = document.get("scope")
        if isinstance(scope, dict):
            equal_when_present(
                document.get("recipient"),
                scope.get("subject"),
                "$.scope.subject",
                "recipient and approval subject",
            )
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("issuer"),
                ownership.get("lifecycle_authority"),
                "$.issuer",
                "issuer and grant lifecycle authority",
            )
        for field in ("issued_at", "valid_from", "expires_at"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("issued_at"),
            document.get("valid_from"),
            "$.valid_from",
            "valid_from must not precede issued_at",
        )
        require_chronology(
            document.get("valid_from"),
            document.get("expires_at"),
            "$.expires_at",
            "expires_at must be later than valid_from",
            allow_equal=False,
        )
        revocation = document.get("revocation")
        if isinstance(revocation, dict) and "revoked_at" in revocation:
            validate_timestamp(
                revocation["revoked_at"],
                "$.revocation.revoked_at",
            )
            require_chronology(
                document.get("issued_at"),
                revocation.get("revoked_at"),
                "$.revocation.revoked_at",
                "revoked_at must not precede issued_at",
            )

    if name == "approval-verification-result.v1.schema.json":
        grant_ref = document.get("grant_ref")
        if (
            isinstance(grant_ref, dict)
            and grant_ref.get("resource_type") != "APPROVAL_GRANT"
        ):
            add(
                "$.grant_ref.resource_type",
                "must reference an APPROVAL_GRANT",
            )
        if document.get("outcome") == "VERIFIED":
            equal_when_present(
                grant_ref.get("revision")
                if isinstance(grant_ref, dict)
                else None,
                document.get("verified_grant_revision"),
                "$.verified_grant_revision",
                "grant_ref revision and verified grant revision",
            )
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("authority"),
                ownership.get("lifecycle_authority"),
                "$.authority",
                "verification authority and lifecycle authority",
            )
        for field in ("verified_at", "valid_until"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("verified_at"),
            document.get("valid_until"),
            "$.valid_until",
            "valid_until must be later than verified_at",
            allow_equal=False,
        )

    if name == "artifact-trust-evidence.v1.schema.json":
        artifact_ref = document.get("artifact_ref")
        if (
            isinstance(artifact_ref, dict)
            and artifact_ref.get("resource_type") != "ARTIFACT"
        ):
            add(
                "$.artifact_ref.resource_type",
                "must reference an ARTIFACT",
            )
        publisher = document.get("publisher")
        if (
            isinstance(publisher, dict)
            and publisher.get("principal_type") != "PUBLISHER"
        ):
            add(
                "$.publisher.principal_type",
                "artifact publisher must be a PUBLISHER principal",
            )
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("verifier"),
                ownership.get("lifecycle_authority"),
                "$.verifier",
                "artifact verifier and lifecycle authority",
            )
        for field in ("verified_at", "valid_until"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("verified_at"),
            document.get("valid_until"),
            "$.valid_until",
            "valid_until must be later than verified_at",
            allow_equal=False,
        )

    if name == "secret-reference.v1.schema.json":
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("secret_authority"),
                ownership.get("lifecycle_authority"),
                "$.secret_authority",
                "Secret Authority and lifecycle authority",
            )
        for field in (
            "created_at",
            "rotated_at",
            "revoked_at",
            "deleted_at",
        ):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        for field in ("rotated_at", "revoked_at", "deleted_at"):
            if field in document:
                require_chronology(
                    document.get("created_at"),
                    document.get(field),
                    f"$.{field}",
                    f"{field} must not precede created_at",
                )

    if name == "event-envelope.v1.schema.json":
        source = document.get("source")
        if (
            isinstance(source, dict)
            and source.get("resource_type") != "EVENT_SOURCE"
        ):
            add(
                "$.source.resource_type",
                "must reference an EVENT_SOURCE",
            )
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        lifecycle_authority = (
            ownership.get("lifecycle_authority")
            if isinstance(ownership, dict)
            else None
        )
        if isinstance(lifecycle_authority, dict):
            equal_when_present(
                document.get("producer"),
                lifecycle_authority.get("principal"),
                "$.producer",
                "producer and event lifecycle-authority principal",
            )
        for field in ("occurred_at", "recorded_at"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("occurred_at"),
            document.get("recorded_at"),
            "$.recorded_at",
            "recorded_at must not precede occurred_at",
        )

    organization_domain_names = {
        "organization.v1.schema.json",
        "department.v1.schema.json",
        "team.v1.schema.json",
        "role.v1.schema.json",
        "position.v1.schema.json",
        "employee-definition.v3.schema.json",
        "membership.v1.schema.json",
        "position-occupancy.v1.schema.json",
        "organization-lifecycle-transition.v1.schema.json",
    }
    if name in organization_domain_names:
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        organization_ref = document.get("organization_ref")
        if (
            name != "organization.v1.schema.json"
            and name != "organization-lifecycle-transition.v1.schema.json"
            and isinstance(organization_ref, dict)
            and organization_ref.get("resource_type") != "ORGANIZATION"
        ):
            add(
                "$.organization_ref.resource_type",
                "must reference an ORGANIZATION",
            )
        if name == "organization.v1.schema.json":
            organization_principal = document.get(
                "organization_principal_ref"
            )
            if (
                isinstance(organization_principal, dict)
                and organization_principal.get("principal_type")
                != "ORGANIZATION"
            ):
                add(
                    "$.organization_principal_ref.principal_type",
                    "must be an ORGANIZATION principal",
                )
            owner = (
                ownership.get("owner")
                if isinstance(ownership, dict)
                else None
            )
            if (
                isinstance(owner, dict)
                and owner.get("principal_type") != "HUMAN_USER"
            ):
                add(
                    "$.identity.ownership.owner.principal_type",
                    "a v1 Organization must have one HUMAN_USER owner",
                )

    if name == "employee-definition.v3.schema.json":
        employee_principal = document.get("employee_principal_ref")
        if (
            isinstance(employee_principal, dict)
            and employee_principal.get("principal_type") != "EMPLOYEE"
        ):
            add(
                "$.employee_principal_ref.principal_type",
                "must be an EMPLOYEE principal",
            )

    if name == "team.v1.schema.json":
        for field, expected in (
            ("knowledge_refs", "KNOWLEDGE_OBJECT"),
            ("memory_refs", "MEMORY_OBJECT"),
        ):
            refs = document.get(field)
            if isinstance(refs, list):
                for index, reference in enumerate(refs):
                    if (
                        isinstance(reference, dict)
                        and reference.get("resource_type") != expected
                    ):
                        add(
                            f"$.{field}[{index}].resource_type",
                            f"must reference {expected}",
                        )

    if name in {
        "membership.v1.schema.json",
        "position-occupancy.v1.schema.json",
    }:
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("issuer"),
                ownership.get("lifecycle_authority"),
                "$.issuer",
                "issuer and lifecycle authority",
            )
        for field in ("effective_from", "effective_until"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("effective_from"),
            document.get("effective_until"),
            "$.effective_until",
            "effective_until must be later than effective_from",
            allow_equal=False,
        )

    if name == "membership.v1.schema.json":
        member = document.get("member")
        container = document.get("container_ref")
        kind = document.get("membership_kind")
        expected = {
            "USER_ORGANIZATION": ("HUMAN_USER", "ORGANIZATION"),
            "EMPLOYEE_ORGANIZATION": ("EMPLOYEE", "ORGANIZATION"),
            "USER_TEAM": ("HUMAN_USER", "TEAM"),
            "EMPLOYEE_TEAM": ("EMPLOYEE", "TEAM"),
        }.get(kind)
        if expected and isinstance(member, dict) and isinstance(
            container, dict
        ):
            if member.get("principal_type") != expected[0]:
                add(
                    "$.member.principal_type",
                    f"{kind} requires a {expected[0]} member",
                )
            if container.get("resource_type") != expected[1]:
                add(
                    "$.container_ref.resource_type",
                    f"{kind} requires a {expected[1]} container",
                )
        if (
            document.get("status") == "EXPIRED"
            and "effective_until" not in document
        ):
            add(
                "$.effective_until",
                "EXPIRED membership requires an effective end",
            )

    if (
        name == "position-occupancy.v1.schema.json"
        and document.get("status") == "ENDED"
        and "effective_until" not in document
    ):
        add(
            "$.effective_until",
            "ENDED Position Occupancy requires an effective end",
        )

    if name == "organization-lifecycle-transition.v1.schema.json":
        for field in ("transitioned_at",):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        subject = document.get("subject_ref")
        subject_type = (
            subject.get("resource_type")
            if isinstance(subject, dict)
            else None
        )
        transitions = {
            "ORGANIZATION": {
                "DRAFT": {"ACTIVE", "ARCHIVED"},
                "ACTIVE": {"SUSPENDED", "ARCHIVED"},
                "SUSPENDED": {"ACTIVE", "ARCHIVED"},
                "ARCHIVED": {"DELETED"},
                "DELETED": set(),
            },
            "DEPARTMENT": {
                "DRAFT": {"ACTIVE", "ARCHIVED"},
                "ACTIVE": {"SUSPENDED", "ARCHIVED"},
                "SUSPENDED": {"ACTIVE", "ARCHIVED"},
                "ARCHIVED": {"DELETED"},
                "DELETED": set(),
            },
            "TEAM": {
                "DRAFT": {"ACTIVE", "ARCHIVED"},
                "ACTIVE": {"SUSPENDED", "ARCHIVED"},
                "SUSPENDED": {"ACTIVE", "ARCHIVED"},
                "ARCHIVED": {"DELETED"},
                "DELETED": set(),
            },
            "ROLE": {
                "DRAFT": {"ACTIVE", "ARCHIVED"},
                "ACTIVE": {"SUSPENDED", "ARCHIVED"},
                "SUSPENDED": {"ACTIVE", "ARCHIVED"},
                "ARCHIVED": {"DELETED"},
                "DELETED": set(),
            },
            "POSITION": {
                "DRAFT": {"ACTIVE", "ARCHIVED"},
                "ACTIVE": {"SUSPENDED", "ARCHIVED"},
                "SUSPENDED": {"ACTIVE", "ARCHIVED"},
                "ARCHIVED": {"DELETED"},
                "DELETED": set(),
            },
            "MEMBERSHIP": {
                "PENDING": {"ACTIVE", "REVOKED"},
                "ACTIVE": {"SUSPENDED", "EXPIRED", "REVOKED"},
                "SUSPENDED": {"ACTIVE", "EXPIRED", "REVOKED"},
                "EXPIRED": set(),
                "REVOKED": set(),
            },
            "POSITION_OCCUPANCY": {
                "PENDING": {"ACTIVE", "REVOKED"},
                "ACTIVE": {"ENDED", "REVOKED"},
                "ENDED": set(),
                "REVOKED": set(),
            },
        }
        allowed = transitions.get(subject_type, {}).get(
            document.get("from_status"),
            set(),
        )
        if document.get("to_status") not in allowed:
            add(
                "$.to_status",
                "is not an allowed lifecycle transition for the subject",
            )
        if (
            isinstance(subject, dict)
            and subject.get("revision") == document.get("resulting_revision")
        ):
            add(
                "$.resulting_revision",
                "must differ from the subject's expected revision",
            )
        if (
            document.get("to_status") == "DELETED"
            and document.get("rollback_behavior")
            != "TERMINAL_NO_ROLLBACK"
        ):
            add(
                "$.rollback_behavior",
                "DELETED transitions are terminal",
            )
        if (
            document.get("to_status") != "DELETED"
            and document.get("rollback_behavior")
            != "COMPENSATING_TRANSITION_REQUIRED"
        ):
            add(
                "$.rollback_behavior",
                "non-DELETED rollback requires a governed compensating transition",
            )

    capability_plugin_names = {
        "capability-definition.v1.schema.json",
        "tool-definition.v1.schema.json",
        "plugin-definition.v1.schema.json",
        "plugin-manifest.v1.schema.json",
        "provider-definition.v1.schema.json",
        "plugin-installation.v1.schema.json",
        "plugin-activation.v1.schema.json",
        "capability-profile.v1.schema.json",
        "runtime-requirement.v1.schema.json",
        "compatibility-evidence.v1.schema.json",
        "permission-declaration.v1.schema.json",
        "plugin-revocation.v1.schema.json",
    }
    if name in capability_plugin_names:
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        state_evidence = document.get("state_evidence")
        if isinstance(ownership, dict) and isinstance(state_evidence, dict):
            equal_when_present(
                state_evidence.get("transition_authority"),
                ownership.get("lifecycle_authority"),
                "$.state_evidence.transition_authority",
                "state transition authority and lifecycle authority",
            )
            for field, evidence_field in (
                ("installer_actor_context_ref", "actor_context_ref"),
                ("activating_actor_context_ref", "actor_context_ref"),
                ("actor_context_ref", "actor_context_ref"),
                ("authorization_decision_ref",
                 "authorization_decision_ref"),
                ("approval_verification_refs",
                 "approval_verification_refs"),
            ):
                if field in document:
                    equal_when_present(
                        document.get(field),
                        state_evidence.get(evidence_field),
                        f"$.{field}",
                        f"{field} and state evidence",
                    )
        if isinstance(state_evidence, dict):
            if "transitioned_at" in state_evidence:
                validate_timestamp(
                    state_evidence["transitioned_at"],
                    "$.state_evidence.transitioned_at",
                )
            updated_at = (
                identity.get("updated_at")
                if isinstance(identity, dict)
                else None
            )
            require_chronology(
                updated_at,
                state_evidence.get("transitioned_at"),
                "$.state_evidence.transitioned_at",
                "state transition must not precede the resource revision",
            )

    if name in {
        "tool-definition.v1.schema.json",
        "permission-declaration.v1.schema.json",
    }:
        side_effects = document.get("side_effects")
        risk = document.get("risk_classification")
        if isinstance(side_effects, dict):
            effect = side_effects.get("effect")
            reach = side_effects.get("reach")
            reversibility = side_effects.get("reversibility")
            accesses = side_effects.get("accesses")
            if effect in {"NONE", "READ_ONLY"}:
                if reversibility != "NOT_APPLICABLE":
                    add(
                        "$.side_effects.reversibility",
                        "non-mutating operations require NOT_APPLICABLE",
                    )
                if "rollback_expectation" in side_effects:
                    add(
                        "$.side_effects.rollback_expectation",
                        "non-mutating operations must not claim rollback",
                    )
            if effect == "NONE":
                if reach != "NONE":
                    add(
                        "$.side_effects.reach",
                        "an operation with no side effect must have NONE reach",
                    )
                if accesses:
                    add(
                        "$.side_effects.accesses",
                        "an operation with no side effect must declare no access",
                    )
            if effect in {"MUTATING", "DESTRUCTIVE"} and reach == "NONE":
                add(
                    "$.side_effects.reach",
                    "mutating operations must declare their side-effect reach",
                )
            if effect == "DESTRUCTIVE":
                if risk not in {"HIGH", "CRITICAL"}:
                    add(
                        "$.risk_classification",
                        "destructive operations must be HIGH or CRITICAL risk",
                    )
                if reversibility == "REVERSIBLE":
                    add(
                        "$.side_effects.reversibility",
                        "destructive operations cannot claim full reversibility",
                    )
                if not side_effects.get("risk_justification"):
                    add(
                        "$.side_effects.risk_justification",
                        "destructive operations require risk justification",
                    )
            if (
                isinstance(accesses, list)
                and "NETWORK" in accesses
                and reach not in {"EXTERNAL", "LOCAL_AND_EXTERNAL"}
            ):
                add(
                    "$.side_effects.reach",
                    "network access requires external side-effect reach",
                )
            if (
                reversibility == "IRREVERSIBLE"
                and "rollback_expectation" in side_effects
            ):
                add(
                    "$.side_effects.rollback_expectation",
                    "irreversible operations cannot claim rollback",
                )

    if name == "plugin-definition.v1.schema.json":
        publisher = document.get("publisher")
        if (
            isinstance(publisher, dict)
            and publisher.get("principal_type") != "PUBLISHER"
        ):
            add(
                "$.publisher.principal_type",
                "plugin publisher must be a PUBLISHER principal",
            )

    if name == "plugin-manifest.v1.schema.json":
        publisher = document.get("publisher")
        if (
            isinstance(publisher, dict)
            and publisher.get("principal_type") != "PUBLISHER"
        ):
            add(
                "$.publisher.principal_type",
                "manifest publisher must be a PUBLISHER principal",
            )

    if name == "plugin-activation.v1.schema.json":
        for field in ("effective_from", "effective_until"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("effective_from"),
            document.get("effective_until"),
            "$.effective_until",
            "effective_until must be later than effective_from",
            allow_equal=False,
        )

    if name == "compatibility-evidence.v1.schema.json":
        for field in ("observed_at", "valid_until"):
            if field in document:
                validate_timestamp(document[field], f"$.{field}")
        require_chronology(
            document.get("observed_at"),
            document.get("valid_until"),
            "$.valid_until",
            "valid_until must be later than observed_at",
            allow_equal=False,
        )
        reasons = document.get("reasons")
        if (
            document.get("outcome") != "COMPATIBLE"
            and isinstance(reasons, list)
            and not reasons
        ):
            add(
                "$.reasons",
                "non-compatible evidence requires reasons",
            )

    if name == "plugin-revocation.v1.schema.json":
        if "effective_at" in document:
            validate_timestamp(document["effective_at"], "$.effective_at")
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        if isinstance(ownership, dict):
            equal_when_present(
                document.get("declaring_authority"),
                ownership.get("lifecycle_authority"),
                "$.declaring_authority",
                "revocation declaring authority and lifecycle authority",
            )

    if name == "capability-resolution-request.v1.schema.json":
        if "requested_at" in document:
            validate_timestamp(document["requested_at"], "$.requested_at")

    if name == "effective-ranking-request.v1.schema.json":
        if "requested_at" in document:
            validate_timestamp(document["requested_at"], "$.requested_at")

    if name == "effective-ranking-result.v1.schema.json":
        if "resolved_at" in document:
            validate_timestamp(document["resolved_at"], "$.resolved_at")

    if name == "capability-resolution-result.v1.schema.json":
        if "resolved_at" in document:
            validate_timestamp(document["resolved_at"], "$.resolved_at")
        if "valid_until" in document:
            validate_timestamp(document["valid_until"], "$.valid_until")

    if name == "execution-result.v1.schema.json":
        if "started_at" in document:
            validate_timestamp(document["started_at"], "$.started_at")
        if "completed_at" in document:
            validate_timestamp(document["completed_at"], "$.completed_at")
        summary = document.get("attempt_summary")
        attempts = (
            summary.get("attempts")
            if isinstance(summary, dict)
            else None
        )
        if isinstance(attempts, list):
            for index, attempt in enumerate(attempts):
                if not isinstance(attempt, dict):
                    continue
                if "started_at" in attempt:
                    validate_timestamp(
                        attempt["started_at"],
                        f"$.attempt_summary.attempts[{index}].started_at",
                    )
                if "completed_at" in attempt:
                    validate_timestamp(
                        attempt["completed_at"],
                        f"$.attempt_summary.attempts[{index}].completed_at",
                    )

    correlation_key = "trace" if name == "execution.v1.schema.json" else "correlation"
    correlation = document.get(correlation_key)
    if not isinstance(correlation, dict):
        correlation = {}

    if name == "execution.v1.schema.json":
        equal_when_present(
            document.get("execution_id"),
            correlation.get("execution_id"),
            "$.trace.execution_id",
            "execution_id and trace.execution_id",
        )

    if name == "capability-resolution-request.v1.schema.json":
        def reject_approval_shortcuts(item: Any, path: str) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    child_path = f"{path}.{key}"
                    if key in RESERVED_APPROVAL_SHORTCUTS:
                        add(child_path, "is not approval evidence")
                    reject_approval_shortcuts(child, child_path)
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    reject_approval_shortcuts(child, f"{path}[{index}]")

        reject_approval_shortcuts(document.get("constraints", {}), "$.constraints")
        reject_approval_shortcuts(document.get("policy", {}), "$.policy")

    if name == "capability-resolution-result.v1.schema.json":
        equal_when_present(
            document.get("resolution_id"),
            correlation.get("resolution_id"),
            "$.correlation.resolution_id",
            "resolution_id and correlation.resolution_id",
        )
        candidates = document.get("candidate_evaluations")
        if isinstance(candidates, list):
            positions = [
                candidate.get("position")
                for candidate in candidates
                if isinstance(candidate, dict)
                and isinstance(candidate.get("position"), int)
                and not isinstance(candidate.get("position"), bool)
            ]
            if len(positions) == len(candidates):
                if len(set(positions)) != len(positions):
                    add("$.candidate_evaluations", "candidate positions must be unique")
                if positions != sorted(positions):
                    add(
                        "$.candidate_evaluations",
                        "candidate evaluations must be in ascending position order",
                    )
            for index, candidate in enumerate(candidates):
                if not isinstance(candidate, dict):
                    continue
                if (
                    candidate.get("outcome") in {"REJECTED", "APPROVAL_REQUIRED"}
                    and not candidate.get("reasons")
                ):
                    add(
                        f"$.candidate_evaluations[{index}].reasons",
                        "rejected or approval-required candidates need reasons",
                    )
            if document.get("status") == "RESOLVED":
                selected = document.get("selected_target")
                selected_id = (
                    selected.get("provider_id")
                    if isinstance(selected, dict)
                    else None
                )
                selected_matches = [
                    candidate
                    for candidate in candidates
                    if isinstance(candidate, dict)
                    and candidate.get("provider_id") == selected_id
                    and (
                        not isinstance(selected, dict)
                        or not selected.get("model_id")
                        or (
                            candidate.get("model_id") == selected.get("model_id")
                            and candidate.get("runtime_binding_id")
                            == selected.get("runtime_binding_id")
                        )
                    )
                ]
                if len(selected_matches) != 1:
                    add(
                        "$.selected_target.provider_id",
                        "selected target must appear exactly once in candidates",
                    )
                elif selected_matches[0].get("outcome") != "ELIGIBLE":
                    add(
                        "$.selected_target.provider_id",
                        "selected target candidate must be eligible",
                    )
                if not isinstance(selected, dict) or "model_id" not in selected:
                    first_eligible = next(
                        (
                            candidate.get("provider_id")
                            for candidate in candidates
                            if isinstance(candidate, dict)
                            and candidate.get("outcome") == "ELIGIBLE"
                        ),
                        None,
                    )
                    if selected_id is not None and selected_id != first_eligible:
                        add(
                            "$.selected_target.provider_id",
                            "selected target must be the first eligible candidate",
                        )
            if document.get("status") == "NO_ELIGIBLE_PROVIDER":
                eligible_count = sum(
                    1
                    for candidate in candidates
                    if isinstance(candidate, dict)
                    and candidate.get("outcome") == "ELIGIBLE"
                )
                if eligible_count:
                    add(
                        "$.candidate_evaluations",
                        "NO_ELIGIBLE_PROVIDER must not contain eligible candidates",
                    )
            if document.get("status") == "GOVERNED_ORDER_REQUIRED":
                governable_count = sum(
                    1
                    for candidate in candidates
                    if isinstance(candidate, dict)
                    and candidate.get("outcome")
                    in {"ELIGIBLE", "APPROVAL_REQUIRED"}
                )
                if governable_count < 2:
                    add(
                        "$.candidate_evaluations",
                        "GOVERNED_ORDER_REQUIRED needs at least two "
                        "otherwise-governable candidates",
                    )
                rationale = document.get("rationale")
                if not isinstance(rationale, dict) or not rationale:
                    add(
                        "$.rationale",
                        "GOVERNED_ORDER_REQUIRED needs nonempty rationale",
                    )

    if name == "execution-result.v1.schema.json":
        equal_when_present(
            document.get("execution_id"),
            correlation.get("execution_id"),
            "$.correlation.execution_id",
            "execution_id and correlation.execution_id",
        )
        resolution_ref = document.get("resolution_ref")
        reference_id = (
            resolution_ref.get("reference_id")
            if isinstance(resolution_ref, dict)
            else None
        )
        equal_when_present(
            reference_id,
            correlation.get("resolution_id"),
            "$.resolution_ref.reference_id",
            "resolution_ref and correlation.resolution_id",
        )
        summary = document.get("attempt_summary")
        if isinstance(summary, dict):
            attempts = summary.get("attempts")
            count = summary.get("attempt_count")
            if isinstance(attempts, list):
                if isinstance(count, int) and count != len(attempts):
                    add(
                        "$.attempt_summary.attempt_count",
                        "attempt_count must equal number of attempts",
                    )
                attempt_ids = [
                    attempt.get("invocation_attempt_id")
                    for attempt in attempts
                    if isinstance(attempt, dict)
                    and isinstance(attempt.get("invocation_attempt_id"), str)
                ]
                attempt_numbers = [
                    attempt.get("attempt_number")
                    for attempt in attempts
                    if isinstance(attempt, dict)
                    and isinstance(attempt.get("attempt_number"), int)
                    and not isinstance(attempt.get("attempt_number"), bool)
                ]
                if (
                    len(attempt_ids) == len(attempts)
                    and len(set(attempt_ids)) != len(attempt_ids)
                ):
                    add(
                        "$.attempt_summary.attempts",
                        "invocation attempt IDs must be unique",
                    )
                if len(attempt_numbers) == len(attempts):
                    if len(set(attempt_numbers)) != len(attempt_numbers):
                        add(
                            "$.attempt_summary.attempts",
                            "attempt numbers must be unique",
                        )
                    if attempt_numbers != sorted(attempt_numbers):
                        add(
                            "$.attempt_summary.attempts",
                            "attempts must be in ascending number order",
                        )

    work_domain_names = {
        "work-request.v1.schema.json",
        "workflow-definition.v1.schema.json",
        "workflow-revision.v1.schema.json",
        "job-definition.v1.schema.json",
        "task-definition.v1.schema.json",
        "work-assignment.v1.schema.json",
        "work-delegation.v1.schema.json",
        "work-dependency.v1.schema.json",
        "work-result.v1.schema.json",
        "work-state-transition.v1.schema.json",
        "retry-intent.v1.schema.json",
        "escalation-intent.v1.schema.json",
    }
    if name in work_domain_names:
        identity = document.get("identity")
        ownership = (
            identity.get("ownership")
            if isinstance(identity, dict)
            else None
        )
        lifecycle_authority = (
            ownership.get("lifecycle_authority")
            if isinstance(ownership, dict)
            else None
        )
        state_evidence = document.get("state_evidence")
        if isinstance(state_evidence, dict):
            equal_when_present(
                lifecycle_authority,
                state_evidence.get("transition_authority"),
                "$.state_evidence.transition_authority",
                "state transition and lifecycle authority",
            )
            if "transitioned_at" in state_evidence:
                validate_timestamp(
                    state_evidence["transitioned_at"],
                    "$.state_evidence.transitioned_at",
                )
        if isinstance(identity, dict):
            require_chronology(
                identity.get("created_at"),
                identity.get("updated_at"),
                "$.identity.updated_at",
                "updated_at must not precede created_at",
            )
            require_chronology(
                identity.get("created_at"),
                (
                    state_evidence.get("transitioned_at")
                    if isinstance(state_evidence, dict)
                    else None
                ),
                "$.state_evidence.transitioned_at",
                "transitioned_at must not precede resource creation",
            )
        due_window = (
            document.get("requested_due_window")
            if name == "work-request.v1.schema.json"
            else document.get("due_window")
        )
        if isinstance(due_window, dict):
            require_chronology(
                due_window.get("not_before"),
                due_window.get("due_at"),
                "$.due_window.due_at",
                "due_at must not precede not_before",
            )
        effective_period = document.get("effective_period")
        if isinstance(effective_period, dict):
            require_chronology(
                effective_period.get("effective_from"),
                effective_period.get("effective_until"),
                "$.effective_period.effective_until",
                "effective_until must be later than effective_from",
                allow_equal=False,
            )

    if name in {
        "job-definition.v1.schema.json",
        "task-definition.v1.schema.json",
    }:
        status = document.get("status")
        result_refs = document.get("result_refs")
        if (
            status in {
                "COMPLETED",
                "AWAITING_VERIFICATION",
                "VERIFIED",
                "CLOSED",
            }
            and isinstance(result_refs, list)
            and not result_refs
        ):
            add(
                "$.result_refs",
                "completed or later work state requires result evidence",
            )
        governance = document.get("governance")
        verification_refs = document.get("verification_evidence_refs")
        if (
            isinstance(governance, dict)
            and governance.get("verification_required") is True
            and status in {"VERIFIED", "CLOSED"}
            and isinstance(verification_refs, list)
            and not verification_refs
        ):
            add(
                "$.verification_evidence_refs",
                "verified or closed work requires verification evidence",
            )
        if status == "CLOSED" and "closure_transition_ref" not in document:
            add(
                "$.closure_transition_ref",
                "closed work requires governed closure evidence",
            )

    if name in {
        "work-assignment.v1.schema.json",
        "work-delegation.v1.schema.json",
    }:
        acceptance = document.get("acceptance")
        status = document.get("status")
        if isinstance(acceptance, dict):
            required = acceptance.get("required")
            state = acceptance.get("state")
            if required is False and state != "NOT_REQUIRED":
                add(
                    "$.acceptance.state",
                    "non-required acceptance must be NOT_REQUIRED",
                )
            if required is True and state == "NOT_REQUIRED":
                add(
                    "$.acceptance.state",
                    "required acceptance cannot be NOT_REQUIRED",
                )
            if (
                status == "ACTIVE"
                and required is True
                and state != "ACCEPTED"
            ):
                add(
                    "$.acceptance.state",
                    "active responsibility requires accepted evidence",
                )
            if state == "ACCEPTED" and "evidence_ref" not in acceptance:
                add(
                    "$.acceptance.evidence_ref",
                    "accepted responsibility requires evidence",
                )

    if name == "work-result.v1.schema.json":
        if "completed_at" in document:
            validate_timestamp(document["completed_at"], "$.completed_at")
        producing_principal = document.get("producing_principal")
        for index, link in enumerate(document.get("artifact_links", [])):
            if isinstance(link, dict):
                equal_when_present(
                    producing_principal,
                    link.get("producer_ref"),
                    f"$.artifact_links[{index}].producer_ref",
                    "result and Artifact producer",
                )

    if name == "work-state-transition.v1.schema.json":
        if "occurred_at" in document:
            validate_timestamp(document["occurred_at"], "$.occurred_at")
        if document.get("expected_revision") == document.get(
            "resulting_revision"
        ):
            add(
                "$.resulting_revision",
                "state transition must produce a new revision",
            )
        if document.get("from_state") == document.get("to_state"):
            add("$.to_state", "state transition must change state")

    if name == "retry-intent.v1.schema.json":
        requested = document.get("requested_attempt_ref")
        if requested in document.get("prior_attempt_refs", []):
            add(
                "$.requested_attempt_ref",
                "requested attempt must not reuse prior attempt identity",
            )
    return tuple(errors)


def validate_contract(contract_id: str, document: Any) -> None:
    issues = (
        *validate_schema(contract_id, document),
        *validate_semantics(contract_id, document),
    )
    if issues:
        raise ContractValidationError(contract_id, issues)
