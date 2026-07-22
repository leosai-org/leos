from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import security_observability as so


def load_operator():
    spec = importlib.util.spec_from_file_location(
        "operator_cli_phase5245", TOOLS / "operator_cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SecurityObservabilityTests(unittest.TestCase):
    NOW = "2026-07-21T00:00:00+00:00"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="leos-phase5245-test-")
        self.target = Path(self.temp.name) / "leos-installation"
        for name in ("config", "state", "journal", "logs"):
            (self.target / name).mkdir(parents=True, exist_ok=True)
        self._write_json(
            "state/installation-manifest.json",
            {
                "contract_version": "leos.installation-manifest.v1",
                "installation_id": "installation-test",
                "selected_profile": "leos-standard-nvidia",
                "source_release": so.SOURCE_RELEASE,
                "source_tree_sha256": so.SOURCE_TREE,
                "status": "installed",
            },
            0o600,
        )
        self._write_json(
            "state/administrator-bootstrap.json",
            {
                "contract_version": "leos.administrator-bootstrap.v1",
                "activation_required": True,
                "username": "operator",
            },
            0o600,
        )
        self._write_json(
            "state/runtime-selection.json",
            {
                "contract_version": "leos.runtime-selection.v1",
                "runtime_id": "local-nvidia",
                "network_authorized": False,
            },
            0o600,
        )
        self._write_json(
            "config/first-run.json",
            {
                "contract_version": "leos.first-run-configuration.v1",
                "first_run_complete": True,
            },
            0o644,
        )
        (self.target / "logs/ai-router.log").write_text(
            "INFO router ready correlation_id=test\n",
            encoding="utf-8",
        )
        self.config = so.load_object(
            ROOT / "config/security-observability.json",
            "leos.security-observability-config.v1",
        )
        self.catalog = so.load_object(
            ROOT / "config/operator-service-catalog.json",
            "leos.operator-service-catalog.v1",
        )
        self.fixture = so.load_fixture(
            str(ROOT / "examples/security-observability-fixture.json")
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_json(self, relative: str, value: dict, mode: int) -> None:
        path = self.target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        path.chmod(mode)

    def reports(self, fixture=None):
        return so.build_reports(
            self.target,
            self.config,
            self.catalog,
            self.fixture if fixture is None else fixture,
            self.NOW,
        )

    def test_security_report_pass(self):
        self.assertEqual(self.reports()["security-baseline"]["status"], "pass")

    def test_security_report_contract(self):
        self.assertEqual(
            self.reports()["security-baseline"]["contract_version"],
            so.CONTRACT_SECURITY,
        )

    def test_secret_report_pass(self):
        self.assertEqual(self.reports()["secret-exposure"]["status"], "pass")

    def test_secret_json_key_detected_without_value(self):
        self._write_json("config/unsafe.json", {"api_key": "TOP-SECRET-VALUE"}, 0o600)
        report = self.reports()["secret-exposure"]
        self.assertEqual(report["status"], "fail")
        rendered = json.dumps(report)
        self.assertNotIn("TOP-SECRET-VALUE", rendered)
        self.assertTrue(all(item["value_redacted"] for item in report["findings"]))

    def test_secret_text_pattern_detected_without_value(self):
        (self.target / "logs/unsafe.log").write_text(
            "password=TOP-SECRET-VALUE\n", encoding="utf-8"
        )
        report = self.reports()["secret-exposure"]
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("TOP-SECRET-VALUE", json.dumps(report))

    def test_secret_material_filename_skipped(self):
        (self.target / "config/client-secret.json").write_text(
            '{"value":"ignored"}\n', encoding="utf-8"
        )
        report = self.reports()["secret-exposure"]
        self.assertTrue(
            any(item["reason"] == "secret-material-name" for item in report["skipped"])
        )

    def test_network_report_pass(self):
        self.assertEqual(self.reports()["network-exposure"]["status"], "pass")

    def test_network_public_required_binding_fails(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["services"]["ai-router"]["bindings"] = ["0.0.0.0:8000"]
        report = self.reports(fixture)["network-exposure"]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["counts"]["public_bindings"], 1)

    def test_network_no_contact(self):
        report = self.reports()["network-exposure"]
        self.assertFalse(report["external_network_contacted"])
        self.assertFalse(report["container_daemon_contacted"])

    def test_health_all_required_healthy(self):
        report = self.reports()["health-aggregate"]
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["required_unhealthy"], 0)

    def test_health_required_unhealthy_fails(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["services"]["ai-router"]["health"] = "unhealthy"
        report = self.reports(fixture)["health-aggregate"]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["required_unhealthy"], 1)

    def test_metrics_fixture(self):
        report = self.reports()["metrics-snapshot"]
        self.assertEqual(report["source"], "fixture")
        self.assertEqual(report["metrics"]["nvidia_gpu_count"], 1)

    def test_metrics_local_read_only(self):
        report = so.metrics_snapshot(self.target, {}, self.NOW)
        self.assertEqual(report["source"], "local-read-only")
        self.assertGreater(report["metrics"]["storage_total_gb"], 0)

    def test_private_mode_violation_fails(self):
        path = self.target / "state/runtime-selection.json"
        path.chmod(0o644)
        report = self.reports()["security-baseline"]
        self.assertEqual(report["status"], "fail")

    def test_release_mismatch_fails(self):
        manifest = json.loads((self.target / "state/installation-manifest.json").read_text())
        manifest["source_release"] = "wrong-release"
        self._write_json("state/installation-manifest.json", manifest, 0o600)
        report = self.reports()["security-baseline"]
        self.assertEqual(report["status"], "fail")

    def test_runtime_privileged_fails(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["runtime"]["privileged"] = True
        self.assertEqual(self.reports(fixture)["security-baseline"]["status"], "fail")

    def test_readiness_ready(self):
        self.assertEqual(self.reports()["observability-readiness"]["status"], "ready")

    def test_readiness_blocked_on_low_storage(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["metrics"]["storage_free_gb"] = 0.1
        report = self.reports(fixture)["observability-readiness"]
        self.assertEqual(report["status"], "blocked")
        self.assertIn("diagnostic-storage", report["blockers"])

    def test_structured_log_redacts_message(self):
        record = so.structured_log_record(
            "ai-router", "info", "password=TOP-SECRET-VALUE", {}, None, self.NOW
        )
        self.assertIn("[REDACTED]", record["message"])
        self.assertNotIn("TOP-SECRET-VALUE", json.dumps(record))

    def test_structured_log_redacts_attribute_key(self):
        record = so.structured_log_record(
            "ai-router", "info", "ready", {"api_key": "TOP-SECRET-VALUE"}, None, self.NOW
        )
        self.assertEqual(record["attributes"]["api_key"], "[REDACTED]")
        self.assertFalse(record["plaintext_secret_exposed"])

    def test_structured_log_deterministic(self):
        a = so.structured_log_record("ai-router", "info", "ready", {}, "c-1", self.NOW)
        b = so.structured_log_record("ai-router", "info", "ready", {}, "c-1", self.NOW)
        self.assertEqual(a, b)

    def test_diagnostics_plan_requires_confirmation(self):
        plan = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        self.assertTrue(plan["requires_confirmation"])
        self.assertFalse(plan["execution_authorized"])

    def test_diagnostics_plan_is_deterministic(self):
        a = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        b = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        self.assertEqual(a, b)

    def test_diagnostics_export_rejects_bad_confirmation(self):
        plan = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        with self.assertRaises(so.SecurityObservabilityError):
            so.export_diagnostics(
                self.target, self.config, plan, self.reports(),
                "diagnostics/test.zip", "wrong", self.NOW
            )

    def test_diagnostics_export_rejects_absolute_output(self):
        plan = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        with self.assertRaises(so.SecurityObservabilityError):
            so.export_diagnostics(
                self.target, self.config, plan, self.reports(),
                str(Path(os.sep) / "tmp" / "test.zip"),
                plan["confirmation_token"], self.NOW
            )

    def test_diagnostics_export_creates_zip(self):
        plan = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        result = so.export_diagnostics(
            self.target, self.config, plan, self.reports(),
            "diagnostics/test.zip", plan["confirmation_token"], self.NOW
        )
        archive = self.target / "diagnostics/test.zip"
        self.assertTrue(archive.is_file())
        self.assertEqual(result["status"], "exported")
        self.assertLessEqual(result["archive_size_bytes"], self.config["diagnostics"]["max_bundle_bytes"])

    def test_diagnostics_export_contains_manifest(self):
        plan = so.diagnostics_plan(self.target, self.config, self.reports(), self.NOW)
        so.export_diagnostics(
            self.target, self.config, plan, self.reports(),
            "diagnostics/test.zip", plan["confirmation_token"], self.NOW
        )
        with zipfile.ZipFile(self.target / "diagnostics/test.zip") as archive:
            self.assertIn("manifest.json", archive.namelist())

    def test_diagnostics_export_redacts_log(self):
        (self.target / "logs/unsafe.log").write_text(
            "token=TOP-SECRET-VALUE\n", encoding="utf-8"
        )
        reports = self.reports()
        plan = so.diagnostics_plan(self.target, self.config, reports, self.NOW)
        so.export_diagnostics(
            self.target, self.config, plan, reports,
            "diagnostics/test.zip", plan["confirmation_token"], self.NOW
        )
        with zipfile.ZipFile(self.target / "diagnostics/test.zip") as archive:
            content = archive.read("logs/logs/unsafe.log").decode()
        self.assertIn("[REDACTED]", content)
        self.assertNotIn("TOP-SECRET-VALUE", content)

    def test_diagnostics_does_not_copy_secret_named_file(self):
        (self.target / "logs/credential.txt").write_text("TOP-SECRET-VALUE\n")
        reports = self.reports()
        plan = so.diagnostics_plan(self.target, self.config, reports, self.NOW)
        so.export_diagnostics(
            self.target, self.config, plan, reports,
            "diagnostics/test.zip", plan["confirmation_token"], self.NOW
        )
        with zipfile.ZipFile(self.target / "diagnostics/test.zip") as archive:
            names = archive.namelist()
        self.assertFalse(any("credential.txt" in name for name in names))

    def test_safe_target_blocks_root(self):
        with self.assertRaises(so.SecurityObservabilityError):
            so.safe_target(Path(os.sep))

    def test_portable_output_blocks_parent_escape(self):
        with self.assertRaises(so.SecurityObservabilityError):
            so.portable_output("../outside.zip")

    def test_standalone_cli_security(self):
        process = subprocess.run(
            [
                sys.executable, "-B", str(TOOLS / "security_observability.py"),
                "--target-root", str(self.target),
                "--fixture", str(ROOT / "examples/security-observability-fixture.json"),
                "--now", self.NOW,
                "security",
            ],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        value = json.loads(process.stdout)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(value["payload_contract"], so.CONTRACT_SECURITY)

    def test_standalone_cli_output_file(self):
        output = Path(self.temp.name) / "result.json"
        process = subprocess.run(
            [
                sys.executable, "-B", str(TOOLS / "security_observability.py"),
                "--target-root", str(self.target),
                "--fixture", str(ROOT / "examples/security-observability-fixture.json"),
                "--now", self.NOW, "--output", str(output),
                "metrics",
            ],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self.assertEqual(process.returncode, 0)
        self.assertEqual(json.loads(output.read_text())["payload_contract"], so.CONTRACT_METRICS)

    def test_operator_cli_security_command(self):
        operator = load_operator()
        operator_fixture = json.loads((ROOT / "examples/operator-fixture.json").read_text())
        operator_fixture["metrics"] = self.fixture["metrics"]
        fixture_path = Path(self.temp.name) / "operator-fixture.json"
        fixture_path.write_text(json.dumps(operator_fixture))
        output = Path(self.temp.name) / "operator-security.json"
        code = operator.main([
            "--target-root", str(self.target), "--fixture", str(fixture_path),
            "--now", self.NOW, "--output", str(output), "security"
        ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read_text())["payload_contract"], so.CONTRACT_SECURITY)

    def test_operator_cli_observe_command(self):
        operator = load_operator()
        fixture_path = Path(self.temp.name) / "operator-fixture.json"
        fixture = json.loads((ROOT / "examples/operator-fixture.json").read_text())
        fixture["metrics"] = self.fixture["metrics"]
        fixture_path.write_text(json.dumps(fixture))
        output = Path(self.temp.name) / "observe.json"
        operator.main([
            "--target-root", str(self.target), "--fixture", str(fixture_path),
            "--now", self.NOW, "--output", str(output),
            "observe", "--view", "health"
        ])
        self.assertEqual(json.loads(output.read_text())["payload_contract"], so.CONTRACT_HEALTH)

    def test_operator_cli_diagnostics_plan(self):
        operator = load_operator()
        fixture_path = Path(self.temp.name) / "operator-fixture.json"
        fixture = json.loads((ROOT / "examples/operator-fixture.json").read_text())
        fixture["metrics"] = self.fixture["metrics"]
        fixture_path.write_text(json.dumps(fixture))
        output = Path(self.temp.name) / "diagnostics.json"
        operator.main([
            "--target-root", str(self.target), "--fixture", str(fixture_path),
            "--now", self.NOW, "--output", str(output), "diagnostics"
        ])
        value = json.loads(output.read_text())
        self.assertEqual(value["payload_contract"], so.CONTRACT_DIAGNOSTICS)
        self.assertTrue(value["payload"]["requires_confirmation"])

    def test_operator_cli_diagnostics_export_marks_mutation(self):
        operator = load_operator()
        fixture_path = Path(self.temp.name) / "operator-fixture-export.json"
        fixture = json.loads((ROOT / "examples/operator-fixture.json").read_text())
        fixture["metrics"] = self.fixture["metrics"]
        fixture_path.write_text(json.dumps(fixture))
        plan_output = Path(self.temp.name) / "operator-plan.json"
        operator.main([
            "--target-root", str(self.target), "--fixture", str(fixture_path),
            "--now", self.NOW, "--output", str(plan_output), "diagnostics"
        ])
        token = json.loads(plan_output.read_text())["payload"]["confirmation_token"]
        export_output = Path(self.temp.name) / "operator-export.json"
        operator.main([
            "--target-root", str(self.target), "--fixture", str(fixture_path),
            "--now", self.NOW, "--output", str(export_output),
            "diagnostics", "--export", "--output-relative", "diagnostics/operator.zip",
            "--confirm", token
        ])
        value = json.loads(export_output.read_text())
        self.assertFalse(value["safety"]["read_only"])
        self.assertEqual(value["payload"]["status"], "exported")

    def test_operator_version_matches_release_identity(self):
        operator = load_operator()
        output = Path(self.temp.name) / "version.json"
        operator.main([
            "--target-root", str(self.target), "--output", str(output), "version"
        ])
        payload = json.loads(output.read_text())["payload"]
        self.assertEqual(payload["release"], operator.release_identity()["release"])
        self.assertEqual(payload["phase"], operator.release_identity()["phase"])
        self.assertEqual(payload["source_release"], operator.SOURCE_RELEASE)


if __name__ == "__main__":
    unittest.main()
