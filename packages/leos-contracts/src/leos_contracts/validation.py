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
SUPPORTED_CONTRACTS = (
    "execution-correlation.v1.schema.json",
    "execution.v1.schema.json",
    "capability-resolution-request.v1.schema.json",
    "capability-resolution-result.v1.schema.json",
    "execution-result.v1.schema.json",
)
CONTRACT_VERSIONS = {
    "leos.execution-correlation.v1": "execution-correlation.v1.schema.json",
    "leos.execution.v1": "execution.v1.schema.json",
    "leos.capability-resolution-request.v1":
        "capability-resolution-request.v1.schema.json",
    "leos.capability-resolution-result.v1":
        "capability-resolution-result.v1.schema.json",
    "leos.execution-result.v1": "execution-result.v1.schema.json",
}
RESERVED_APPROVAL_SHORTCUTS = {
    "allow_approval_required",
    "approval_granted",
    "approved",
    "has_approval",
}
DATE_TIME_FIELDS = {
    "requested_at",
    "resolved_at",
    "valid_until",
    "started_at",
    "completed_at",
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
        name for name in SUPPORTED_CONTRACTS if not (root / name).is_file()
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
    for name in SUPPORTED_CONTRACTS:
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

    def validate_timestamps(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}.{key}"
                if key in DATE_TIME_FIELDS:
                    valid = isinstance(child, str) and bool(
                        RFC3339.fullmatch(child)
                    )
                    if valid:
                        try:
                            parsed = datetime.fromisoformat(
                                child[:-1] + "+00:00"
                                if child.endswith("Z")
                                else child
                            )
                            valid = parsed.tzinfo is not None
                        except ValueError:
                            valid = False
                    if not valid:
                        add(child_path, "must be RFC3339 date-time")
                validate_timestamps(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                validate_timestamps(child, f"{path}[{index}]")

    validate_timestamps(document)
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
