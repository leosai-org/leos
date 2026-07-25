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
    "execution-correlation.v1.schema.json",
    "execution.v1.schema.json",
    "capability-resolution-request.v1.schema.json",
    "capability-resolution-result.v1.schema.json",
    "execution-result.v1.schema.json",
    "effective-ranking-request.v1.schema.json",
    "effective-ranking-result.v1.schema.json",
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
    return tuple(errors)


def validate_contract(contract_id: str, document: Any) -> None:
    issues = (
        *validate_schema(contract_id, document),
        *validate_semantics(contract_id, document),
    )
    if issues:
        raise ContractValidationError(contract_id, issues)
