from __future__ import annotations

import copy
import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
EXAMPLES = ROOT / "examples"

SCHEMA_EXAMPLES = {
    "execution-correlation.v1.schema.json": "execution-correlation.v1.json",
    "execution.v1.schema.json": "execution.v1.json",
    "capability-resolution-request.v1.schema.json":
        "capability-resolution-request.v1.json",
    "capability-resolution-result.v1.schema.json":
        "capability-resolution-result.v1.json",
    "execution-result.v1.schema.json": "execution-result.v1.json",
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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_errors(schema_name: str, value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return errors

    def equal_when_present(
        left: Any,
        right: Any,
        description: str,
    ) -> None:
        if left is not None and right is not None and left != right:
            errors.append(f"{description} must match")

    def validate_timestamps(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}.{key}"
                if key in DATE_TIME_FIELDS:
                    if not isinstance(child, str) or not RFC3339.fullmatch(child):
                        errors.append(f"{child_path} must be RFC3339 date-time")
                    else:
                        try:
                            parsed = datetime.fromisoformat(
                                child[:-1] + "+00:00"
                                if child.endswith("Z")
                                else child
                            )
                            if parsed.tzinfo is None:
                                raise ValueError("timezone required")
                        except ValueError:
                            errors.append(
                                f"{child_path} must be RFC3339 date-time"
                            )
                validate_timestamps(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                validate_timestamps(child, f"{path}[{index}]")

    validate_timestamps(value)

    correlation_key = (
        "trace" if schema_name == "execution.v1.schema.json" else "correlation"
    )
    correlation = value.get(correlation_key)
    if not isinstance(correlation, dict):
        correlation = {}

    if schema_name == "execution.v1.schema.json":
        equal_when_present(
            value.get("execution_id"),
            correlation.get("execution_id"),
            "execution_id and trace.execution_id",
        )

    if schema_name == "capability-resolution-request.v1.schema.json":
        def reject_approval_shortcuts(item: Any, path: str) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in RESERVED_APPROVAL_SHORTCUTS:
                        errors.append(
                            f"{path}.{key} is not approval evidence"
                        )
                    reject_approval_shortcuts(child, f"{path}.{key}")
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    reject_approval_shortcuts(child, f"{path}[{index}]")

        reject_approval_shortcuts(value.get("constraints", {}), "$.constraints")
        reject_approval_shortcuts(value.get("policy", {}), "$.policy")

    if schema_name == "capability-resolution-result.v1.schema.json":
        equal_when_present(
            value.get("resolution_id"),
            correlation.get("resolution_id"),
            "resolution_id and correlation.resolution_id",
        )
        candidates = value.get("candidate_evaluations")
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
                    errors.append("candidate positions must be unique")
                if positions != sorted(positions):
                    errors.append(
                        "candidate evaluations must be in ascending position order"
                    )
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                if (
                    candidate.get("outcome")
                    in {"REJECTED", "APPROVAL_REQUIRED"}
                    and not candidate.get("reasons")
                ):
                    errors.append(
                        "rejected or approval-required candidates need reasons"
                    )
            if value.get("status") == "RESOLVED":
                selected = value.get("selected_target")
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
                    errors.append(
                        "selected target must appear exactly once in candidates"
                    )
                elif selected_matches[0].get("outcome") != "ELIGIBLE":
                    errors.append("selected target candidate must be eligible")
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
                    errors.append(
                        "selected target must be the first eligible candidate"
                    )

    if schema_name == "execution-result.v1.schema.json":
        equal_when_present(
            value.get("execution_id"),
            correlation.get("execution_id"),
            "execution_id and correlation.execution_id",
        )
        resolution_ref = value.get("resolution_ref")
        resolution_reference_id = (
            resolution_ref.get("reference_id")
            if isinstance(resolution_ref, dict)
            else None
        )
        equal_when_present(
            resolution_reference_id,
            correlation.get("resolution_id"),
            "resolution_ref and correlation.resolution_id",
        )
        summary = value.get("attempt_summary")
        if isinstance(summary, dict):
            attempts = summary.get("attempts")
            count = summary.get("attempt_count")
            if isinstance(attempts, list):
                if isinstance(count, int) and count != len(attempts):
                    errors.append("attempt_count must equal number of attempts")
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
                if len(attempt_ids) == len(attempts):
                    if len(set(attempt_ids)) != len(attempt_ids):
                        errors.append("invocation attempt IDs must be unique")
                if len(attempt_numbers) == len(attempts):
                    if len(set(attempt_numbers)) != len(attempt_numbers):
                        errors.append("attempt numbers must be unique")
                    if attempt_numbers != sorted(attempt_numbers):
                        errors.append(
                            "attempts must be in ascending number order"
                        )

    return errors


class ExecutionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {
            name: read_json(CONTRACTS / name)
            for name in SCHEMA_EXAMPLES
        }
        registry = Registry()
        for schema in cls.schemas.values():
            registry = registry.with_resource(
                schema["$id"],
                Resource.from_contents(schema),
            )
        cls.registry = registry

    def validator(self, schema_name: str) -> Draft202012Validator:
        return Draft202012Validator(
            self.schemas[schema_name],
            registry=self.registry,
            format_checker=FormatChecker(),
        )

    def example(self, example_name: str) -> dict[str, Any]:
        return read_json(EXAMPLES / example_name)

    def assert_valid(self, schema_name: str, value: Any) -> None:
        schema_errors = sorted(
            self.validator(schema_name).iter_errors(value),
            key=lambda error: list(error.absolute_path),
        )
        errors = [error.message for error in schema_errors]
        errors.extend(semantic_errors(schema_name, value))
        self.assertEqual([], errors, "\n".join(errors))

    def assert_invalid(self, schema_name: str, value: Any) -> None:
        schema_errors = list(self.validator(schema_name).iter_errors(value))
        self.assertTrue(schema_errors or semantic_errors(schema_name, value))

    def execution_request(self) -> dict[str, Any]:
        return self.example("execution.v1.json")

    def resolution_result(self) -> dict[str, Any]:
        return self.example("capability-resolution-result.v1.json")

    def execution_result(self) -> dict[str, Any]:
        return self.example("execution-result.v1.json")

    def error_result(self, status: str) -> dict[str, Any]:
        value = self.execution_result()
        value["status"] = status
        value.pop("normalized_result")
        value["attempt_summary"]["attempts"][0]["status"] = status
        value["error"] = {
            "code": status.lower(),
            "message": "Deterministic contract-test failure.",
            "retryable_same_target": status == "TRANSPORT_ERROR",
            "remote_side_effect_possible": status == "AMBIGUOUS_OUTCOME",
        }
        return value

    def test_valid_execution_request(self):
        self.assert_valid("execution.v1.schema.json", self.execution_request())

    def test_missing_required_execution_fields(self):
        value = self.execution_request()
        value.pop("capability_id")
        self.assert_invalid("execution.v1.schema.json", value)

    def test_valid_correlation_structure(self):
        self.assert_valid(
            "execution-correlation.v1.schema.json",
            self.example("execution-correlation.v1.json"),
        )

    def test_correlation_with_optional_ids_omitted(self):
        value = {
            "contract_version": "leos.execution-correlation.v1",
            "job_id": "job-minimal-001",
        }
        self.assert_valid("execution-correlation.v1.schema.json", value)

    def test_successful_capability_resolution(self):
        self.assert_valid(
            "capability-resolution-result.v1.schema.json",
            self.resolution_result(),
        )

    def test_no_eligible_provider_resolution(self):
        value = self.resolution_result()
        value["status"] = "NO_ELIGIBLE_PROVIDER"
        value.pop("selected_target")
        value["candidate_evaluations"] = [
            {
                "position": 1,
                "provider_id": "provider-unavailable",
                "outcome": "REJECTED",
                "reasons": ["provider_unavailable"],
            }
        ]
        value["rationale"] = {"outcome": "no_eligible_provider"}
        self.assert_valid("capability-resolution-result.v1.schema.json", value)

    def test_approval_pending_resolution(self):
        value = self.resolution_result()
        value["status"] = "APPROVAL_PENDING"
        value.pop("selected_target")
        value["candidate_evaluations"][0]["outcome"] = "APPROVAL_REQUIRED"
        value["candidate_evaluations"][0]["reasons"] = [
            "approval_grant_required"
        ]
        value["approval_requirement_ref"] = {
            "authority": "approval-authority",
            "reference_id": "approval-requirement-001",
        }
        value["rationale"] = {
            "outcome": "highest_ranked_candidate_approval_pending"
        }
        self.assert_valid("capability-resolution-result.v1.schema.json", value)

    def test_approval_pending_cannot_select_lower_candidate(self):
        value = self.resolution_result()
        value["status"] = "APPROVAL_PENDING"
        value["approval_requirement_ref"] = {
            "authority": "approval-authority",
            "reference_id": "approval-requirement-001",
        }
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_successful_execution_result(self):
        self.assert_valid(
            "execution-result.v1.schema.json",
            self.execution_result(),
        )

    def test_provider_failure_result(self):
        self.assert_valid(
            "execution-result.v1.schema.json",
            self.error_result("PROVIDER_ERROR"),
        )

    def test_transport_failure_result(self):
        self.assert_valid(
            "execution-result.v1.schema.json",
            self.error_result("TRANSPORT_ERROR"),
        )

    def test_ambiguous_outcome_result(self):
        self.assert_valid(
            "execution-result.v1.schema.json",
            self.error_result("AMBIGUOUS_OUTCOME"),
        )

    def test_rejected_execution_result(self):
        value = self.execution_result()
        value["status"] = "REJECTED"
        value.pop("normalized_result")
        value.pop("authorized_target")
        value["attempt_summary"] = {"attempt_count": 0, "attempts": []}
        value["error"] = {
            "code": "policy_denied",
            "message": "Execution was denied before invocation.",
            "retryable_same_target": False,
            "remote_side_effect_possible": False,
        }
        self.assert_valid("execution-result.v1.schema.json", value)

    def test_approval_pending_execution_result(self):
        value = self.execution_result()
        value["status"] = "APPROVAL_PENDING"
        value.pop("normalized_result")
        value.pop("authorized_target")
        value["attempt_summary"] = {"attempt_count": 0, "attempts": []}
        value["approval_requirement_ref"] = {
            "authority": "approval-authority",
            "reference_id": "approval-requirement-001",
        }
        self.assert_valid("execution-result.v1.schema.json", value)

    def test_malformed_contract_versions_are_rejected(self):
        for schema_name, example_name in SCHEMA_EXAMPLES.items():
            with self.subTest(schema=schema_name):
                value = self.example(example_name)
                value["contract_version"] = "leos.malformed.v999"
                self.assert_invalid(schema_name, value)

    def test_raw_credential_fields_are_rejected_in_governed_structures(self):
        request = self.execution_request()
        request["api_key"] = "not-a-real-secret"
        self.assert_invalid("execution.v1.schema.json", request)

        resolution = self.resolution_result()
        resolution["selected_target"]["credentials"] = {
            "token": "not-a-real-secret"
        }
        self.assert_invalid(
            "capability-resolution-result.v1.schema.json",
            resolution,
        )

    def test_secret_shaped_business_payload_names_remain_allowed(self):
        request = self.execution_request()
        request["input"] = {
            "source_field_names": ["token", "key"],
            "document": {"password_reset_requested": True},
        }
        self.assert_valid("execution.v1.schema.json", request)

    def test_opaque_credential_reference_is_allowed(self):
        resolution = self.resolution_result()
        resolution["selected_target"]["credential_ref"] = {
            "authority": "secret-authority",
            "reference_id": "credential-reference-001",
        }
        self.assert_valid(
            "capability-resolution-result.v1.schema.json",
            resolution,
        )

    def test_caller_supplied_approval_boolean_is_rejected(self):
        request = self.example("capability-resolution-request.v1.json")
        request["policy"]["allow_approval_required"] = True
        self.assert_invalid(
            "capability-resolution-request.v1.schema.json",
            request,
        )

    def test_approval_boolean_shortcuts_in_constraints_are_rejected(self):
        for name in RESERVED_APPROVAL_SHORTCUTS:
            with self.subTest(name=name):
                request = self.example("capability-resolution-request.v1.json")
                request["constraints"][name] = True
                self.assert_invalid(
                    "capability-resolution-request.v1.schema.json",
                    request,
                )

    def test_legitimate_boolean_constraint_is_allowed(self):
        request = self.example("capability-resolution-request.v1.json")
        request["constraints"]["requires_gpu"] = True
        self.assert_valid(
            "capability-resolution-request.v1.schema.json",
            request,
        )

    def test_resolved_requires_selected_target(self):
        value = self.resolution_result()
        value.pop("selected_target")
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_resolved_requires_nonempty_candidates(self):
        value = self.resolution_result()
        value["candidate_evaluations"] = []
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_resolved_requires_eligible_candidate(self):
        value = self.resolution_result()
        value["candidate_evaluations"][0]["outcome"] = "REJECTED"
        value["candidate_evaluations"][0]["reasons"] = ["unavailable"]
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_selected_target_must_appear_in_candidates(self):
        value = self.resolution_result()
        value["selected_target"]["provider_id"] = "provider-not-evaluated"
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_selected_target_candidate_must_be_eligible(self):
        value = self.resolution_result()
        value["candidate_evaluations"] = [
            {
                "position": 1,
                "provider_id": "provider-content-writer",
                "outcome": "REJECTED",
                "reasons": ["unavailable"],
            },
            {
                "position": 2,
                "provider_id": "provider-other",
                "outcome": "ELIGIBLE",
                "reasons": [],
            },
        ]
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_first_eligible_candidate_cannot_be_skipped(self):
        value = self.resolution_result()
        value["selected_target"]["provider_id"] = "provider-second"
        value["candidate_evaluations"] = [
            {
                "position": 1,
                "provider_id": "provider-first",
                "outcome": "ELIGIBLE",
                "reasons": [],
            },
            {
                "position": 2,
                "provider_id": "provider-second",
                "outcome": "ELIGIBLE",
                "reasons": [],
            },
        ]
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_candidate_positions_must_be_unique_and_ascending(self):
        value = self.resolution_result()
        value["candidate_evaluations"].append(
            {
                "position": 1,
                "provider_id": "provider-other",
                "outcome": "REJECTED",
                "reasons": ["unavailable"],
            }
        )
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

        value["candidate_evaluations"][1]["position"] = 0
        self.assert_invalid("capability-resolution-result.v1.schema.json", value)

    def test_rejected_and_approval_required_candidates_need_reasons(self):
        for outcome in ("REJECTED", "APPROVAL_REQUIRED"):
            with self.subTest(outcome=outcome):
                value = self.resolution_result()
                value["candidate_evaluations"][0]["outcome"] = outcome
                value["candidate_evaluations"][0]["reasons"] = []
                self.assert_invalid(
                    "capability-resolution-result.v1.schema.json",
                    value,
                )

    def test_approval_pending_rejects_target_attempts_and_missing_reference(self):
        base = self.resolution_result()
        base["status"] = "APPROVAL_PENDING"
        base["candidate_evaluations"][0]["outcome"] = "APPROVAL_REQUIRED"
        base["candidate_evaluations"][0]["reasons"] = ["approval_required"]

        missing_reference = copy.deepcopy(base)
        missing_reference.pop("selected_target")
        self.assert_invalid(
            "capability-resolution-result.v1.schema.json",
            missing_reference,
        )

        execution = self.execution_result()
        execution["status"] = "APPROVAL_PENDING"
        execution.pop("normalized_result")
        execution.pop("authorized_target")
        execution["approval_requirement_ref"] = {
            "authority": "approval-authority",
            "reference_id": "approval-requirement-001",
        }
        self.assert_invalid("execution-result.v1.schema.json", execution)

    def test_rejected_execution_prohibits_attempts_and_target(self):
        value = self.execution_result()
        value["status"] = "REJECTED"
        value.pop("normalized_result")
        value["error"] = {
            "code": "denied",
            "message": "Denied before invocation.",
            "retryable_same_target": False,
            "remote_side_effect_possible": False,
        }
        self.assert_invalid("execution-result.v1.schema.json", value)

    def test_ambiguous_outcome_requires_possible_remote_side_effect(self):
        value = self.error_result("AMBIGUOUS_OUTCOME")
        value["error"]["remote_side_effect_possible"] = False
        self.assert_invalid("execution-result.v1.schema.json", value)

    def test_attempt_count_and_attempt_identity_consistency(self):
        value = self.execution_result()
        value["attempt_summary"]["attempt_count"] = 2
        self.assert_invalid("execution-result.v1.schema.json", value)

        duplicate = copy.deepcopy(value["attempt_summary"]["attempts"][0])
        value = self.execution_result()
        value["attempt_summary"]["attempts"].append(duplicate)
        value["attempt_summary"]["attempt_count"] = 2
        self.assert_invalid("execution-result.v1.schema.json", value)

        value["attempt_summary"]["attempts"][1][
            "invocation_attempt_id"
        ] = "invocation-attempt-example-002"
        self.assert_invalid("execution-result.v1.schema.json", value)

    def test_failure_results_require_authorized_target(self):
        for status in (
            "PROVIDER_ERROR",
            "TRANSPORT_ERROR",
            "AMBIGUOUS_OUTCOME",
        ):
            with self.subTest(status=status):
                value = self.error_result(status)
                value.pop("authorized_target")
                self.assert_invalid("execution-result.v1.schema.json", value)

    def test_unknown_status_is_rejected(self):
        value = self.execution_result()
        value["status"] = "FELL_OVER"
        self.assert_invalid("execution-result.v1.schema.json", value)

    def test_malformed_requester_and_empty_identifiers_are_rejected(self):
        request = self.execution_request()
        request["requester"].pop("id")
        self.assert_invalid("execution.v1.schema.json", request)

        request = self.execution_request()
        request["execution_id"] = ""
        self.assert_invalid("execution.v1.schema.json", request)

    def test_parent_and_correlation_identifiers_must_match(self):
        request = self.execution_request()
        request["trace"]["execution_id"] = "execution-other"
        self.assert_invalid("execution.v1.schema.json", request)

        resolution = self.resolution_result()
        resolution["correlation"]["resolution_id"] = "resolution-other"
        self.assert_invalid(
            "capability-resolution-result.v1.schema.json",
            resolution,
        )

        result = self.execution_result()
        result["correlation"]["execution_id"] = "execution-other"
        self.assert_invalid("execution-result.v1.schema.json", result)

        result = self.execution_result()
        result["correlation"]["resolution_id"] = "resolution-other"
        self.assert_invalid("execution-result.v1.schema.json", result)

    def test_malformed_timestamps_are_rejected_semantically(self):
        resolution = self.resolution_result()
        resolution["resolved_at"] = "not-a-time"
        self.assert_invalid(
            "capability-resolution-result.v1.schema.json",
            resolution,
        )

        result = self.execution_result()
        result["attempt_summary"]["attempts"][0]["completed_at"] = "not-a-time"
        self.assert_invalid("execution-result.v1.schema.json", result)

    def test_unexpected_top_level_fields_are_rejected(self):
        request = self.execution_request()
        request["unexpected"] = True
        self.assert_invalid("execution.v1.schema.json", request)

    def test_all_canonical_examples_round_trip_and_validate(self):
        for schema_name, example_name in SCHEMA_EXAMPLES.items():
            with self.subTest(schema=schema_name):
                value = self.example(example_name)
                round_tripped = json.loads(
                    json.dumps(value, sort_keys=True, separators=(",", ":"))
                )
                self.assertEqual(value, round_tripped)
                self.assert_valid(schema_name, round_tripped)

    def test_schemas_are_valid_draft_2020_12(self):
        for schema_name, schema in self.schemas.items():
            with self.subTest(schema=schema_name):
                Draft202012Validator.check_schema(copy.deepcopy(schema))


if __name__ == "__main__":
    unittest.main()
