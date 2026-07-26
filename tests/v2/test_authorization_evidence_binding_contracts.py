from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = ROOT / "packages" / "leos-contracts" / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from leos_contracts import ContractValidationError, validate_contract

CONTRACT = "leos.authorization-evidence-binding.v1"
SCHEMA = ROOT / "contracts" / "authorization-evidence-binding.v1.schema.json"
EXAMPLES = ROOT / "examples"

VALID_EXAMPLES = (
    "authorization-evidence-binding.organization-mutation.v1.json",
    "authorization-evidence-binding.work-coordination-mutation.v1.json",
    "authorization-evidence-binding.scheduler-job-projection.v1.json",
    "authorization-evidence-binding.runtime-assignment-handoff.v1.json",
    "authorization-evidence-binding.capability-resolution.v1.json",
    "authorization-evidence-binding.dispatcher-invocation.v1.json",
)


def read_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class AuthorizationEvidenceBindingContractTests(unittest.TestCase):
    def example(self) -> dict:
        return copy.deepcopy(read_example(VALID_EXAMPLES[0]))

    def assert_valid(self, value: dict) -> None:
        try:
            validate_contract(CONTRACT, value)
        except ContractValidationError as error:
            self.fail(
                "\n".join(
                    f"{issue.kind} {issue.path}: {issue.message}"
                    for issue in error.issues
                )
            )

    def assert_invalid(self, value: dict) -> None:
        with self.assertRaises(ContractValidationError):
            validate_contract(CONTRACT, value)

    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(
            json.loads(SCHEMA.read_text(encoding="utf-8"))
        )

    def test_all_canonical_examples_validate(self):
        for example_name in VALID_EXAMPLES:
            with self.subTest(example=example_name):
                self.assert_valid(read_example(example_name))

    def test_required_fields_are_required(self):
        for field in (
            "authorization_decision_ref",
            "actor_context_ref",
            "organization_ref",
            "expected_scope",
            "expected_decision",
        ):
            value = self.example()
            value.pop(field)
            with self.subTest(field=field):
                self.assert_invalid(value)

    def test_decision_ref_must_be_authorization_decision_ref(self):
        value = self.example()
        value["authorization_decision_ref"]["resource_type"] = "APPROVAL_GRANT"
        self.assert_invalid(value)

    def test_decision_ref_must_be_revision_pinned(self):
        value = self.example()
        value["authorization_decision_ref"].pop("revision")
        self.assert_invalid(value)

    def test_actor_context_ref_must_use_actor_context_evidence_shape(self):
        value = self.example()
        value["actor_context_ref"] = {
            "resource_type": "ACTOR_CONTEXT",
            "resource_id": "actor-context:brett:session-001",
            "revision": "sha256:actor-context-brett-session-001",
        }
        self.assert_invalid(value)

    def test_actor_context_ref_must_be_revision_pinned(self):
        value = self.example()
        value["actor_context_ref"].pop("revision")
        self.assert_invalid(value)

    def test_organization_ref_is_required_and_revision_pinned(self):
        value = self.example()
        value["organization_ref"].pop("revision")
        self.assert_invalid(value)

    def test_expected_scope_resource_must_be_revision_pinned(self):
        value = self.example()
        value["expected_scope"]["resource"].pop("revision")
        self.assert_invalid(value)

    def test_expected_decision_is_bounded(self):
        value = self.example()
        value["expected_decision"] = "MAYBE"
        self.assert_invalid(value)

    def test_subject_action_resource_and_context_are_not_empty_or_ambiguous(self):
        cases = (
            ("empty subject", ("expected_scope", "subject", "principal_id"), ""),
            ("empty action", ("expected_scope", "action"), ""),
            ("empty resource", ("expected_scope", "resource", "resource_id"), ""),
            ("empty context type", ("expected_scope", "context_type"), ""),
            ("missing context digest", ("expected_scope", "context_digest"), None),
        )
        for label, path, replacement in cases:
            value = self.example()
            target = value
            for key in path[:-1]:
                target = target[key]
            if replacement is None:
                target.pop(path[-1])
            else:
                target[path[-1]] = replacement
            with self.subTest(case=label):
                self.assert_invalid(value)

    def test_caller_authorization_and_approval_booleans_are_rejected(self):
        for field in ("authorized", "is_authorized", "approved", "is_approved"):
            value = self.example()
            value[field] = True
            with self.subTest(field=field):
                self.assert_invalid(value)

    def test_raw_credentials_and_secrets_are_rejected(self):
        for field in ("api_key", "credential", "secret", "secret_value"):
            value = self.example()
            value[field] = "not-allowed"
            with self.subTest(field=field):
                self.assert_invalid(value)

    def test_embedded_authorization_decision_json_is_rejected(self):
        value = self.example()
        value["authorization_decision"] = read_example("authorization-decision.v1.json")
        self.assert_invalid(value)

    def test_embedded_actor_context_document_is_rejected(self):
        value = self.example()
        value["actor_context"] = read_example("actor-context.v1.json")
        self.assert_invalid(value)


if __name__ == "__main__":
    unittest.main()
