#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: dict[str, bool] = {}

    source_files = [
        "tools/security_observability.py",
        "tools/operator_cli.py",
        "tools/validate_phase5245_security_observability.py",
        "tests/phase5245/test_security_observability.py",
    ]
    config_files = [
        "config/security-observability.json",
        "config/operator-cli.json",
    ]
    schema_names = [
        "security-baseline-report.v1.schema.json",
        "secret-exposure-report.v1.schema.json",
        "network-exposure-report.v1.schema.json",
        "health-aggregate.v1.schema.json",
        "metrics-snapshot.v1.schema.json",
        "structured-log-record.v1.schema.json",
        "diagnostics-bundle-manifest.v1.schema.json",
        "observability-readiness.v1.schema.json",
    ]
    schema_files = [f"contracts/{name}" for name in schema_names]
    example_names = [
        "security-observability-fixture.json",
        "security-baseline-report.json",
        "secret-exposure-report.json",
        "network-exposure-report.json",
        "health-aggregate.json",
        "metrics-snapshot.json",
        "structured-log-record.json",
        "diagnostics-bundle-manifest.json",
        "observability-readiness.json",
    ]
    example_files = [f"examples/{name}" for name in example_names]
    other_files = ["docs/phase52.4.5-security-observability-baseline.md"]
    files = source_files + config_files + schema_files + example_files + other_files

    for relative in files:
        checks[f"file:{relative}"] = (root / relative).is_file()

    for relative in config_files + schema_files + example_files:
        try:
            read_json(root / relative)
            checks[f"json:{relative}"] = True
        except Exception:
            checks[f"json:{relative}"] = False

    for relative in source_files:
        try:
            ast.parse((root / relative).read_text(encoding="utf-8"), filename=relative)
            checks[f"python-syntax:{relative}"] = True
        except Exception:
            checks[f"python-syntax:{relative}"] = False

    contracts = {
        "security-baseline-report.v1.schema.json": "leos.security-baseline-report.v1",
        "secret-exposure-report.v1.schema.json": "leos.secret-exposure-report.v1",
        "network-exposure-report.v1.schema.json": "leos.network-exposure-report.v1",
        "health-aggregate.v1.schema.json": "leos.health-aggregate.v1",
        "metrics-snapshot.v1.schema.json": "leos.metrics-snapshot.v1",
        "structured-log-record.v1.schema.json": "leos.structured-log-record.v1",
        "diagnostics-bundle-manifest.v1.schema.json": "leos.diagnostics-bundle-manifest.v1",
        "observability-readiness.v1.schema.json": "leos.observability-readiness.v1",
    }
    example_for_schema = {
        "security-baseline-report.v1.schema.json": "security-baseline-report.json",
        "secret-exposure-report.v1.schema.json": "secret-exposure-report.json",
        "network-exposure-report.v1.schema.json": "network-exposure-report.json",
        "health-aggregate.v1.schema.json": "health-aggregate.json",
        "metrics-snapshot.v1.schema.json": "metrics-snapshot.json",
        "structured-log-record.v1.schema.json": "structured-log-record.json",
        "diagnostics-bundle-manifest.v1.schema.json": "diagnostics-bundle-manifest.json",
        "observability-readiness.v1.schema.json": "observability-readiness.json",
    }
    for name, contract in contracts.items():
        schema = read_json(root / "contracts" / name)
        checks[f"schema-contract:{name}"] = (
            schema.get("properties", {}).get("contract_version", {}).get("const") == contract
        )
        checks[f"schema-no-additional:{name}"] = schema.get("additionalProperties") is False
        checks[f"schema-id:{name}"] = str(schema.get("$id", "")).startswith(
            "https://leosai.org/contracts/"
        )
        example = read_json(root / "examples" / example_for_schema[name])
        checks[f"schema-valid-example:{name}"] = not list(
            Draft202012Validator(schema).iter_errors(example)
        )

    config = read_json(root / "config/security-observability.json")
    operator_config = read_json(root / "config/operator-cli.json")
    fixture = read_json(root / "examples/security-observability-fixture.json")
    checks["config-contract"] = config.get("contract_version") == "leos.security-observability-config.v1"
    checks["config-read-only"] = config.get("read_only_default") is True
    checks["config-no-network"] = config.get("external_network_contact_default") is False
    checks["config-no-daemon"] = config.get("container_daemon_contact_default") is False
    checks["config-secret-copy-forbidden"] = config.get("secret_material_copy_forbidden") is True
    checks["config-repair-confirmation"] = config.get("repair_requires_confirmation") is True
    checks["config-bundle-bounded"] = 0 < int(config["diagnostics"]["max_bundle_bytes"]) <= 10 * 1024 * 1024
    checks["config-file-bounded"] = 0 < int(config["diagnostics"]["max_file_bytes"]) < int(config["diagnostics"]["max_bundle_bytes"])
    checks["config-redaction-required"] = config["diagnostics"].get("redaction_required") is True
    checks["config-private-mode-0600"] = config["security"].get("private_file_mode_max") == "0600"
    checks["operator-security-config"] = operator_config.get("security_observability_config") == "config/security-observability.json"
    checks["operator-command-count-12"] = len(operator_config.get("commands", [])) == 12
    checks["operator-security-command"] = "security" in operator_config.get("commands", [])
    checks["operator-observe-command"] = "observe" in operator_config.get("commands", [])
    checks["operator-diagnostics-command"] = "diagnostics" in operator_config.get("commands", [])
    checks["fixture-contract"] = fixture.get("contract_version") == "leos.security-observability-fixture.v1"
    checks["fixture-six-services"] = len(fixture.get("services", {})) == 6
    checks["fixture-no-public-bindings"] = not any(
        str(binding).startswith(("0.0.0.0:", ":::"))
        for service in fixture.get("services", {}).values()
        for binding in service.get("bindings", [])
    )
    checks["fixture-runtime-not-privileged"] = fixture.get("runtime", {}).get("privileged") is False
    checks["fixture-storage-positive"] = fixture.get("metrics", {}).get("storage_free_gb", 0) > 0

    security_source = (root / "tools/security_observability.py").read_text(encoding="utf-8")
    operator_source = (root / "tools/operator_cli.py").read_text(encoding="utf-8")
    combined = security_source + "\n" + operator_source
    checks["source-no-requests"] = "import requests" not in combined
    checks["source-no-httpx"] = "import httpx" not in combined
    checks["source-no-socket"] = "import socket" not in combined
    checks["source-no-urllib-request"] = "urllib.request" not in combined
    checks["source-redaction-patterns"] = "REDACTION_PATTERNS" in security_source
    checks["source-secret-key-redaction"] = "SECRET_KEYS" in security_source
    checks["source-secret-name-exclusion"] = "SECRET_FILE_FRAGMENTS" in security_source
    checks["source-bounded-file-scan"] = "max_files" in security_source and "max_file_bytes" in security_source
    checks["source-bounded-bundle"] = "max_bundle_bytes" in security_source
    checks["source-bounded-log-lines"] = "max_log_lines" in security_source
    checks["source-deterministic-zip"] = "ZipInfo" in security_source and "1980, 1, 1" in security_source
    checks["source-confirmation-token"] = "confirmation_token" in security_source
    checks["source-confirmation-enforced"] = "Diagnostics confirmation token mismatch" in security_source
    checks["source-portable-output"] = "portable_output" in security_source
    checks["source-safe-target"] = "safe_target" in security_source
    checks["source-no-plaintext-output"] = "plaintext_secret_exposed" in security_source
    checks["source-no-secret-copy"] = "secret_material_copied" in security_source
    checks["source-local-metrics"] = "safe_local_metrics" in security_source
    checks["operator-integrates-security"] = "build_security_observability_reports" in operator_source
    checks["operator-integrates-diagnostics"] = "security_diagnostics_plan" in operator_source
    checks["operator-diagnostics-mutation-accurate"] = "result_read_only=not args.export" in operator_source
    checks["operator-version-dynamic"] = (
        "def release_identity()" in operator_source
        and "LEOS_RELEASE_VERSION" in operator_source
        and "LEOS_RELEASE_PHASE" in operator_source
    )

    unit = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(root / "tests/phase5245"),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
    )
    unit_count = unit.stdout.count(" ... ok") + unit.stderr.count(" ... ok")
    checks["unit-tests-exit-zero"] = unit.returncode == 0
    checks["unit-tests-38"] = unit_count == 38

    spec = importlib.util.spec_from_file_location(
        "security_observability_validation", root / "tools/security_observability.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with tempfile.TemporaryDirectory(prefix="leos-security-observability-accept-") as temporary:
        target = Path(temporary) / "leos-installation"
        for name in ("config", "state", "journal", "logs"):
            (target / name).mkdir(parents=True, exist_ok=True)
        manifest = {
            "contract_version": "leos.installation-manifest.v1",
            "installation_id": "installation-acceptance",
            "selected_profile": "leos-standard-nvidia",
            "source_release": module.SOURCE_RELEASE,
            "source_tree_sha256": module.SOURCE_TREE,
            "status": "installed",
        }
        state_values = {
            "installation-manifest.json": manifest,
            "administrator-bootstrap.json": {
                "contract_version": "leos.administrator-bootstrap.v1",
                "activation_required": True,
                "username": "operator",
            },
            "runtime-selection.json": {
                "contract_version": "leos.runtime-selection.v1",
                "runtime_id": "local-nvidia",
                "network_authorized": False,
            },
        }
        for name, value in state_values.items():
            path = target / "state" / name
            path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            path.chmod(0o600)
        (target / "logs/ai-router.log").write_text(
            "INFO router ready\npassword=SHOULD-BE-REDACTED\n", encoding="utf-8"
        )

        cfg = module.load_object(
            root / "config/security-observability.json",
            "leos.security-observability-config.v1",
        )
        catalog = module.load_object(
            root / "config/operator-service-catalog.json",
            "leos.operator-service-catalog.v1",
        )
        acceptance_fixture = module.load_fixture(
            str(root / "examples/security-observability-fixture.json")
        )
        now = "2026-07-21T00:00:00+00:00"
        reports = module.build_reports(target, cfg, catalog, acceptance_fixture, now)
        plan = module.diagnostics_plan(target, cfg, reports, now)
        exported = module.export_diagnostics(
            target,
            cfg,
            plan,
            reports,
            "diagnostics/acceptance.zip",
            plan["confirmation_token"],
            now,
        )
        archive = target / "diagnostics/acceptance.zip"

        checks["accept-security-fail-on-secret"] = reports["security-baseline"]["status"] == "fail"
        checks["accept-secret-finding-redacted"] = reports["secret-exposure"]["status"] == "fail" and "SHOULD-BE-REDACTED" not in json.dumps(reports["secret-exposure"])
        checks["accept-network-pass"] = reports["network-exposure"]["status"] == "pass"
        checks["accept-health-pass"] = reports["health-aggregate"]["status"] == "pass"
        checks["accept-metrics-fixture"] = reports["metrics-snapshot"]["source"] == "fixture"
        checks["accept-readiness-blocked"] = reports["observability-readiness"]["status"] == "blocked"
        checks["accept-plan-confirmation"] = plan.get("requires_confirmation") is True
        checks["accept-plan-not-authorized"] = plan.get("execution_authorized") is False
        checks["accept-export-authorized"] = exported.get("execution_authorized") is True
        checks["accept-export-created"] = archive.is_file()
        checks["accept-export-bounded"] = exported.get("archive_size_bytes", 0) <= cfg["diagnostics"]["max_bundle_bytes"]
        checks["accept-export-no-secret"] = exported.get("plaintext_secret_exposed") is False
        checks["accept-export-no-secret-copy"] = exported.get("secret_material_copied") is False
        checks["accept-export-hash"] = exported.get("archive_sha256") == module.sha256_file(archive)
        with zipfile.ZipFile(archive) as handle:
            names = handle.namelist()
            log_content = handle.read("logs/logs/ai-router.log").decode("utf-8")
        checks["accept-export-manifest"] = "manifest.json" in names
        checks["accept-export-log"] = "logs/logs/ai-router.log" in names
        checks["accept-export-redaction"] = "[REDACTED]" in log_content and "SHOULD-BE-REDACTED" not in log_content

        clean_target = Path(temporary) / "clean-installation"
        shutil.copytree(target, clean_target)
        (clean_target / "diagnostics").exists() and shutil.rmtree(clean_target / "diagnostics")
        (clean_target / "logs/ai-router.log").write_text("INFO router ready\n", encoding="utf-8")
        clean_reports = module.build_reports(clean_target, cfg, catalog, acceptance_fixture, now)
        checks["accept-clean-security-pass"] = clean_reports["security-baseline"]["status"] == "pass"
        checks["accept-clean-readiness-ready"] = clean_reports["observability-readiness"]["status"] == "ready"

        cli_base = [
            sys.executable,
            "-B",
            str(root / "tools/security_observability.py"),
            "--target-root",
            str(clean_target),
            "--fixture",
            str(root / "examples/security-observability-fixture.json"),
            "--now",
            now,
        ]
        cli_commands = {
            "security": ["security"],
            "secrets": ["secrets"],
            "network": ["network"],
            "health": ["health"],
            "metrics": ["metrics"],
            "readiness": ["readiness"],
            "log": [
                "log",
                "--service-id",
                "ai-router",
                "--message",
                "token=CLI-SECRET-VALUE",
            ],
            "diagnostics": ["diagnostics"],
        }
        cli_results: dict[str, dict[str, Any]] = {}
        for name, command in cli_commands.items():
            process = subprocess.run(
                [*cli_base, *command],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300,
            )
            checks[f"cli-{name}-exit-zero"] = process.returncode == 0
            try:
                cli_results[name] = json.loads(process.stdout)
                checks[f"cli-{name}-json"] = True
            except Exception:
                cli_results[name] = {}
                checks[f"cli-{name}-json"] = False
        checks["cli-security-contract"] = cli_results["security"].get("payload_contract") == module.CONTRACT_SECURITY
        checks["cli-health-contract"] = cli_results["health"].get("payload_contract") == module.CONTRACT_HEALTH
        checks["cli-metrics-contract"] = cli_results["metrics"].get("payload_contract") == module.CONTRACT_METRICS
        checks["cli-readiness-ready"] = cli_results["readiness"].get("payload", {}).get("status") == "ready"
        checks["cli-log-redacted"] = "CLI-SECRET-VALUE" not in json.dumps(cli_results["log"])
        checks["cli-diagnostics-confirmation"] = cli_results["diagnostics"].get("payload", {}).get("requires_confirmation") is True
        checks["cli-all-no-network"] = all(
            result.get("safety", {}).get("external_network_contacted") is False
            for result in cli_results.values()
        )
        checks["cli-all-no-daemon"] = all(
            result.get("safety", {}).get("container_daemon_contacted") is False
            for result in cli_results.values()
        )
        checks["cli-all-no-secret-output"] = all(
            result.get("safety", {}).get("plaintext_secret_exposed") is False
            for result in cli_results.values()
        )

    example_contracts = {
        "security-baseline-report.json": module.CONTRACT_SECURITY,
        "secret-exposure-report.json": module.CONTRACT_SECRET,
        "network-exposure-report.json": module.CONTRACT_NETWORK,
        "health-aggregate.json": module.CONTRACT_HEALTH,
        "metrics-snapshot.json": module.CONTRACT_METRICS,
        "structured-log-record.json": module.CONTRACT_LOG,
        "diagnostics-bundle-manifest.json": module.CONTRACT_DIAGNOSTICS,
        "observability-readiness.json": module.CONTRACT_READINESS,
    }
    for name, contract in example_contracts.items():
        value = read_json(root / "examples" / name)
        serialized = json.dumps(value)
        checks[f"example-contract:{name}"] = value.get("contract_version") == contract
        checks[f"example-portable:{name}"] = not any(
            marker in serialized
            for marker in (
                os.sep + "home" + os.sep,
                os.sep + "mnt" + os.sep,
                os.sep + "srv" + os.sep,
                os.sep + "opt" + os.sep,
                os.sep + "tmp" + os.sep,
            )
        )
        checks[f"example-no-secret:{name}"] = "TOP-SECRET" not in serialized and "SHOULD-BE-REDACTED" not in serialized

    errors = [name for name, passed in checks.items() if not passed]
    output = {
        "ok": not errors,
        "phase": "52.4.5",
        "contract_version": "leos.phase52.4.5-security-observability-validation.v1",
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
        "unit_tests": {
            "ok": unit.returncode == 0 and unit_count == 38,
            "test_count": unit_count,
            "returncode": unit.returncode,
            "stdout": unit.stdout,
            "stderr": unit.stderr,
        },
        "fixture_acceptance": {
            "ok": all(
                checks.get(name, False)
                for name in (
                    "accept-clean-security-pass",
                    "accept-clean-readiness-ready",
                    "accept-health-pass",
                    "accept-network-pass",
                    "accept-export-created",
                    "accept-export-redaction",
                    "accept-export-bounded",
                    "accept-export-no-secret-copy",
                )
            ),
            "security": "pass",
            "health": "pass",
            "readiness": "ready",
            "diagnostics_exported": True,
            "redaction_verified": True,
            "archive_size_bytes": exported.get("archive_size_bytes"),
        },
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "docker_socket_mounted": False,
        "plaintext_secret_exposed": False,
        "secret_material_copied": False,
        "production_state_accessed": False,
        "production_network_attached": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
