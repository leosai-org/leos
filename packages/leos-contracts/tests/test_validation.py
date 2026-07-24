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

    def test_validation_failure_is_structured(self):
        value = self.example("execution.v1.json")
        value["trace"]["execution_id"] = "different"
        with self.assertRaises(ContractValidationError) as raised:
            validate_contract("leos.execution.v1", value)
        self.assertTrue(raised.exception.issues)
        self.assertEqual("semantic", raised.exception.issues[0].kind)
        self.assertTrue(raised.exception.issues[0].path.startswith("$"))

    def test_unsupported_contract_is_rejected(self):
        with self.assertRaises(KeyError):
            validate_contract("leos.unknown.v1", {})


if __name__ == "__main__":
    unittest.main()
