from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leos_contracts import (
    ContractRootError,
    ContractValidationError,
    validate_contract,
)
from leos_contracts import validation

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = REPOSITORY_ROOT / "examples"


class ValidationApiTests(unittest.TestCase):
    def example(self, name: str):
        return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))

    def copy_contracts(self, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        for source in (REPOSITORY_ROOT / "contracts").glob("*.schema.json"):
            shutil.copyfile(source, target / source.name)

    def test_valid_source_checkout_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                REPOSITORY_ROOT / "contracts",
                validation.contract_root(),
            )

    def test_valid_explicit_contract_root(self):
        expected = REPOSITORY_ROOT / "contracts"
        with patch.dict(os.environ, {"LEOS_CONTRACT_ROOT": str(expected)}):
            self.assertEqual(expected, validation.contract_root())

    def test_missing_configured_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            with patch.dict(
                os.environ,
                {"LEOS_CONTRACT_ROOT": str(missing)},
                clear=True,
            ):
                with self.assertRaisesRegex(
                    ContractRootError,
                    "does not exist",
                ):
                    validation.contract_root()

    def test_installed_layout_requires_explicit_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed_file = (
                Path(temporary)
                / "venv"
                / "lib"
                / "python3.12"
                / "site-packages"
                / "leos_contracts"
                / "validation.py"
            )
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(validation, "__file__", str(installed_file)),
            ):
                with self.assertRaisesRegex(
                    ContractRootError,
                    "required outside",
                ):
                    validation.contract_root()

    def test_installed_layout_rejects_unrelated_contracts_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed_file = (
                root
                / "venv"
                / "lib"
                / "python3.12"
                / "site-packages"
                / "leos_contracts"
                / "validation.py"
            )
            self.copy_contracts(root / "venv" / "contracts")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(validation, "__file__", str(installed_file)),
            ):
                with self.assertRaises(ContractRootError):
                    validation.contract_root()

    def test_incomplete_governed_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = (
                REPOSITORY_ROOT
                / "contracts"
                / "execution.v1.schema.json"
            )
            shutil.copyfile(source, root / source.name)
            with patch.dict(
                os.environ,
                {"LEOS_CONTRACT_ROOT": str(root)},
                clear=True,
            ):
                with self.assertRaisesRegex(ContractRootError, "incomplete"):
                    validation.contract_root()

    def test_malformed_schema_is_a_contract_root_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.copy_contracts(root)
            (root / "execution.v1.schema.json").write_text(
                "{malformed",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"LEOS_CONTRACT_ROOT": str(root)},
                clear=True,
            ):
                with self.assertRaisesRegex(
                    ContractRootError,
                    "invalid governed contract schema",
                ):
                    validate_contract("leos.execution.v1", {})

    def test_contract_version_and_schema_name_are_accepted(self):
        value = self.example("execution.v1.json")
        self.assertIsNone(validate_contract("leos.execution.v1", value))
        self.assertIsNone(validate_contract("execution.v1.schema.json", value))

    def test_ranking_contract_examples_validate(self):
        for contract, example in (
            (
                "leos.effective-ranking-request.v1",
                "effective-ranking-request.v1.json",
            ),
            (
                "leos.effective-ranking-result.v1",
                "effective-ranking-result.v1.json",
            ),
        ):
            self.assertIsNone(validate_contract(contract, self.example(example)))

    def test_identity_and_trust_contract_examples_validate(self):
        for contract, example in (
            ("leos.resource-identity.v1", "resource-identity.v1.json"),
            ("leos.principal.v1", "principal.v1.json"),
            ("leos.actor-context.v1", "actor-context.v1.json"),
            (
                "leos.authorization-decision.v1",
                "authorization-decision.v1.json",
            ),
            ("leos.approval-request.v1", "approval-request.v1.json"),
            ("leos.approval-grant.v1", "approval-grant.v1.json"),
            (
                "leos.approval-verification-result.v1",
                "approval-verification-result.v1.json",
            ),
            (
                "leos.artifact-trust-evidence.v1",
                "artifact-trust-evidence.v1.json",
            ),
            ("leos.secret-reference.v1", "secret-reference.v1.json"),
            ("leos.event-envelope.v1", "event-envelope.v1.json"),
        ):
            self.assertIsNone(validate_contract(contract, self.example(example)))

    def test_undefined_effective_ranking_has_no_source_authority(self):
        value = {
            "contract_version": "leos.effective-ranking-result.v1",
            "dimension": "provider",
            "status": "UNDEFINED",
            "ordered_ids": [],
            "resolved_at": "2026-07-25T12:00:00Z",
        }
        self.assertIsNone(validate_contract("leos.effective-ranking-result.v1", value))
        value["source_scope"] = "global"
        with self.assertRaises(ContractValidationError):
            validate_contract("leos.effective-ranking-result.v1", value)

    def test_validation_failure_is_structured(self):
        value = self.example("execution.v1.json")
        value["trace"]["execution_id"] = "different"
        with self.assertRaises(ContractValidationError) as raised:
            validate_contract("leos.execution.v1", value)
        self.assertTrue(raised.exception.issues)
        self.assertEqual("semantic", raised.exception.issues[0].kind)
        self.assertTrue(raised.exception.issues[0].path.startswith("$"))

    def test_execution_input_and_context_timestamp_names_are_opaque(self):
        value = self.example("execution.v1.json")
        value["input"].update(
            {
                "requested_at": "next Tuesday",
                "nested": {
                    "started_at": "business-defined-value",
                },
            }
        )
        value["context"].update(
            {
                "assignment": {
                    "started_at": None,
                    "completed_at": None,
                },
                "domain_object": {
                    "requested_at": "whenever practical",
                    "completed_at": "not-a-canonical-timestamp",
                },
            }
        )
        self.assertIsNone(validate_contract("leos.execution.v1", value))
        self.assertEqual(
            (),
            validation.validate_semantics("leos.execution.v1", value),
        )

    def test_ranking_and_model_names_in_opaque_payloads_remain_opaque(self):
        value = self.example("execution.v1.json")
        value["input"]["ranking"] = {
            "provider_order": ["invented-first"],
            "model_order": [],
        }
        value["context"]["model_id"] = "not-canonical-policy"
        value["context"]["metadata"] = {
            "provider_order": ["p9", "p1"],
            "model_order": ["m9", "m1"],
            "ranking": {"score": 999},
        }
        self.assertIsNone(validate_contract("leos.execution.v1", value))
        self.assertEqual(
            (),
            validation.validate_semantics("leos.execution.v1", value),
        )

    def test_resolution_timestamp_semantics_are_path_precise(self):
        request = self.example("capability-resolution-request.v1.json")
        request["requested_at"] = "not-a-time"
        issues = validation.validate_semantics(
            "leos.capability-resolution-request.v1",
            request,
        )
        self.assertEqual(["$.requested_at"], [issue.path for issue in issues])

        result = self.example("capability-resolution-result.v1.json")
        result["resolved_at"] = "not-a-time"
        result["valid_until"] = "also-not-a-time"
        issues = validation.validate_semantics(
            "leos.capability-resolution-result.v1",
            result,
        )
        self.assertEqual(
            ["$.resolved_at", "$.valid_until"],
            [issue.path for issue in issues],
        )

    def test_execution_result_timestamp_semantics_are_path_precise(self):
        result = self.example("execution-result.v1.json")
        result["started_at"] = "not-a-time"
        result["completed_at"] = "also-not-a-time"
        result["attempt_summary"]["attempts"][0]["started_at"] = "bad-start"
        result["attempt_summary"]["attempts"][0]["completed_at"] = "bad-end"
        issues = validation.validate_semantics(
            "leos.execution-result.v1",
            result,
        )
        self.assertEqual(
            [
                "$.started_at",
                "$.completed_at",
                "$.attempt_summary.attempts[0].started_at",
                "$.attempt_summary.attempts[0].completed_at",
            ],
            [issue.path for issue in issues],
        )

    def test_governed_order_required_needs_two_governable_candidates(self):
        value = self.example(
            "capability-resolution-result.governed-order-required.v1.json"
        )
        value["candidate_evaluations"] = value["candidate_evaluations"][:1]
        with self.assertRaises(ContractValidationError) as raised:
            validate_contract(
                "leos.capability-resolution-result.v1",
                value,
            )
        self.assertTrue(
            any(
                issue.kind == "semantic"
                and "at least two otherwise-governable" in issue.message
                for issue in raised.exception.issues
            )
        )

    def test_unsupported_contract_is_rejected(self):
        with self.assertRaises(KeyError):
            validate_contract("leos.unknown.v1", {})

    def test_common_definition_schema_is_not_a_document_contract(self):
        with self.assertRaises(KeyError):
            validate_contract("trust-common.v1.schema.json", {})


if __name__ == "__main__":
    unittest.main()
