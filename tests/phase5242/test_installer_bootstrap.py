from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/installer_bootstrap.py"

spec = importlib.util.spec_from_file_location(
    "leos_installer_bootstrap",
    MODULE_PATH,
)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.target = self.root / "install-root"
        self.source = self.root / "offline-source"
        self.source.mkdir()
        (self.source / "manifest.json").write_text(
            json.dumps(
                {
                    "contract_version": "leos.release-manifest.v1",
                    "release_version": "0.1.0-dev-preview-rc11",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.source / "source.lock.json").write_text(
            json.dumps(
                {
                    "contract_version": "leos.source-lock.v1",
                    "release_version": "0.1.0-dev-preview-rc11",
                    "payload_tree_sha256": (
                        "bc2a07de0c8eb7cf3312c361c437b4fcef660853a2825654e0561e503ff53d51"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.plan = json.loads(
            (ROOT / "examples/installation-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.bootstrap = json.loads(
            (ROOT / "config/installer-bootstrap.json").read_text(
                encoding="utf-8"
            )
        )
        self.layout = json.loads(
            (ROOT / "config/installation-layout.json").read_text(
                encoding="utf-8"
            )
        )
        self.source_record = installer.resolve_source(
            mode="offline",
            source_root=str(self.source),
            allow_network=False,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def transaction(self):
        return installer.build_transaction(
            plan=self.plan,
            target_root=self.target,
            mode="offline",
            source=self.source_record,
            bootstrap_config=self.bootstrap,
            layout_config=self.layout,
            desired_owner="leos",
            desired_group="leos",
        )

    def apply(self, **kwargs):
        return installer.apply_installation(
            plan=self.plan,
            target_root=self.target,
            mode="offline",
            source=self.source_record,
            bootstrap_config=self.bootstrap,
            layout_config=self.layout,
            confirmation=self.plan["plan_id"],
            desired_owner="leos",
            desired_group="leos",
            **kwargs,
        )

    def test_transaction_is_deterministic(self):
        self.assertEqual(self.transaction(), self.transaction())

    def test_transaction_contract(self):
        value = self.transaction()
        self.assertEqual(
            value["contract_version"],
            "leos.installation-transaction.v1",
        )
        self.assertEqual(value["state"], "planned")
        self.assertEqual(len(value["actions"]), 8)

    def test_confirmation_is_required(self):
        with self.assertRaises(installer.InstallerError):
            installer.apply_installation(
                plan=self.plan,
                target_root=self.target,
                mode="offline",
                source=self.source_record,
                bootstrap_config=self.bootstrap,
                layout_config=self.layout,
                confirmation="wrong-token",
                desired_owner="leos",
                desired_group="leos",
            )
        self.assertFalse(self.target.exists())

    def test_offline_mode_requires_source_root(self):
        with self.assertRaises(installer.InstallerError):
            installer.resolve_source(
                mode="offline",
                source_root=None,
                allow_network=False,
            )

    def test_connected_mode_requires_permission(self):
        with self.assertRaises(installer.InstallerError):
            installer.resolve_source(
                mode="connected",
                source_root=None,
                allow_network=False,
            )

    def test_connected_mode_does_not_contact_network(self):
        value = installer.resolve_source(
            mode="connected",
            source_root=None,
            allow_network=True,
        )
        self.assertFalse(value["external_network_contacted"])
        self.assertTrue(value["network_permission_granted"])

    def test_plan_command_does_not_mutate_target(self):
        command = [
            sys.executable,
            "-B",
            str(MODULE_PATH),
            "--bootstrap-config",
            str(ROOT / "config/installer-bootstrap.json"),
            "--layout-config",
            str(ROOT / "config/installation-layout.json"),
            "plan",
            "--plan",
            str(ROOT / "examples/installation-plan.json"),
            "--target-root",
            str(self.target),
            "--mode",
            "offline",
            "--source-root",
            str(self.source),
        ]
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["mutates_host"])
        self.assertFalse(self.target.exists())

    def test_apply_creates_layout(self):
        result = self.apply()
        self.assertTrue(result["ok"])
        for entry in self.layout["directories"]:
            self.assertTrue(
                (self.target / entry["path"]).is_dir()
            )

    def test_apply_creates_manifest_and_journal(self):
        result = self.apply()
        self.assertEqual(
            result["manifest"]["contract_version"],
            "leos.installation-manifest.v1",
        )
        self.assertEqual(
            result["journal"]["contract_version"],
            "leos.installation-execution-journal.v1",
        )
        self.assertTrue(Path(result["manifest_path"]).is_file())
        self.assertTrue(Path(result["journal_path"]).is_file())

    def test_generated_environment_is_sorted(self):
        self.apply()
        lines = (
            self.target / "config/leos.env"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, sorted(lines))

    def test_apply_is_idempotent(self):
        first = self.apply()
        second = self.apply()
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["changed_count"], 0)

    def test_manifest_detects_drift(self):
        self.apply()
        (self.target / "config/leos.env").write_text(
            "BROKEN=1\n",
            encoding="utf-8",
        )
        inspection = installer.inspect_installation(self.target)
        self.assertFalse(inspection["ok"])
        self.assertEqual(inspection["drift_count"], 1)

    def test_inspect_uninstalled_target(self):
        result = installer.inspect_installation(self.target)
        self.assertTrue(result["ok"])
        self.assertFalse(result["installed"])

    def test_existing_plan_mismatch_requires_upgrade(self):
        self.apply()
        modified = json.loads(json.dumps(self.plan))
        modified["plan_id"] = "plan-different"
        with self.assertRaises(installer.InstallerError):
            installer.apply_installation(
                plan=modified,
                target_root=self.target,
                mode="offline",
                source=self.source_record,
                bootstrap_config=self.bootstrap,
                layout_config=self.layout,
                confirmation="plan-different",
                desired_owner="leos",
                desired_group="leos",
            )

    def test_lock_blocks_concurrent_apply(self):
        lock = self.target.parent / (
            f".{self.target.name}.leos-install.lock"
        )
        lock.write_text("held\n", encoding="utf-8")
        with self.assertRaises(installer.InstallerError):
            self.apply()

    def test_injected_failure_rolls_back_new_install(self):
        with self.assertRaises(installer.InstallerError) as context:
            self.apply(fail_after=4)
        self.assertIn("rolled back", str(context.exception))
        self.assertFalse(
            (
                self.target
                / "state/installation-manifest.json"
            ).exists()
        )

    def test_injected_failure_restores_existing_file(self):
        self.target.mkdir(parents=True)
        config = self.target / "config"
        config.mkdir()
        existing = config / "leos.env"
        existing.write_text("ORIGINAL=1\n", encoding="utf-8")
        with self.assertRaises(installer.InstallerError):
            self.apply(fail_after=3)
        self.assertEqual(
            existing.read_text(encoding="utf-8"),
            "ORIGINAL=1\n",
        )

    def test_ownership_is_intent_only(self):
        result = self.apply()
        ownership = result["manifest"]["ownership"]
        self.assertEqual(ownership["desired_owner"], "leos")
        self.assertFalse(ownership["apply_ownership"])

    def test_unsafe_target_is_blocked(self):
        with self.assertRaises(installer.InstallerError):
            installer.normalize_target("/")

    def test_cli_output_file(self):
        output = self.root / "transaction.json"
        command = [
            str(ROOT / "bin/leos-install"),
            "--output",
            str(output),
            "plan",
            "--plan",
            str(ROOT / "examples/installation-plan.json"),
            "--target-root",
            str(self.target),
            "--mode",
            "offline",
            "--source-root",
            str(self.source),
        ]
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(output.read_text(encoding="utf-8")),
            json.loads(result.stdout),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
