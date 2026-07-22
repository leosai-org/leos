#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def contains_absolute_host_path(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("/")
    if isinstance(value, list):
        return any(
            contains_absolute_host_path(item)
            for item in value
        )
    if isinstance(value, dict):
        return any(
            contains_absolute_host_path(item)
            for item in value.values()
        )
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_json(command: list[str], cwd: Path) -> tuple[int, dict[str, Any], str]:
    process = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    try:
        value = json.loads(process.stdout)
    except Exception:
        value = {
            "ok": False,
            "parse_error": True,
            "stdout": process.stdout,
        }
    return process.returncode, value, process.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()

    required = [
        "bin/leos-install",
        "tools/installer_bootstrap.py",
        "tools/validate_phase5242_installer_bootstrap.py",
        "config/installer-bootstrap.json",
        "config/installation-layout.json",
        "contracts/installation-layout.v1.schema.json",
        "contracts/installation-transaction.v1.schema.json",
        "contracts/installation-execution-journal.v1.schema.json",
        "contracts/installation-manifest.v1.schema.json",
        "contracts/installation-result.v1.schema.json",
        "docs/phase52.4.2-idempotent-installer-bootstrap.md",
        "examples/installation-transaction.json",
        "examples/installation-execution-journal.json",
        "examples/installation-manifest.json",
        "examples/installation-result.json",
        "examples/offline-source-manifest.json",
        "examples/installer-bootstrap-fixture.json",
        "tests/phase5242/test_installer_bootstrap.py",
        "manifest.json",
        "source.lock.json",
        "contracts.lock.json",
        "checksums.sha256",
    ]
    checks: dict[str, bool] = {}

    for relative in required:
        checks[f"file:{relative}"] = (root / relative).is_file()

    json_files = [
        relative
        for relative in required
        if relative.endswith(".json")
    ]
    parsed: dict[str, Any] = {}
    for relative in json_files:
        try:
            parsed[relative] = read_json(root / relative)
            checks[f"json:{relative}"] = True
        except Exception:
            checks[f"json:{relative}"] = False

    python_files = [
        "tools/installer_bootstrap.py",
        "tools/validate_phase5242_installer_bootstrap.py",
        "tests/phase5242/test_installer_bootstrap.py",
    ]
    for relative in python_files:
        try:
            ast.parse(
                (root / relative).read_text(encoding="utf-8"),
                filename=relative,
            )
            checks[f"python-syntax:{relative}"] = True
        except Exception:
            checks[f"python-syntax:{relative}"] = False

    wrapper = root / "bin/leos-install"
    checks["wrapper-executable"] = (
        wrapper.is_file()
        and bool(stat.S_IMODE(wrapper.stat().st_mode) & 0o111)
    )
    wrapper_text = wrapper.read_text(encoding="utf-8")
    checks["wrapper-strict-shell"] = "set -euo pipefail" in wrapper_text
    checks["wrapper-targets-installer"] = (
        "tools/installer_bootstrap.py" in wrapper_text
    )

    bootstrap = parsed.get("config/installer-bootstrap.json", {})
    layout = parsed.get("config/installation-layout.json", {})
    checks["bootstrap-contract"] = (
        bootstrap.get("contract_version")
        == "leos.installer-bootstrap-config.v1"
    )
    authority = bootstrap.get("source_authority", {})
    checks["bootstrap-source-rc11"] = (
        bootstrap.get("source_release")
        == "0.1.0-dev-preview-rc11"
    )
    checks["bootstrap-source-authority"] = (
        authority.get("contract_version")
        == "leos.source-authority.v1"
        and authority.get("manifest") == "manifest.json"
        and authority.get("source_lock") == "source.lock.json"
    )
    checks["bootstrap-idempotent"] = bootstrap.get("idempotent") is True
    checks["bootstrap-rollback"] = (
        bootstrap.get("rollback_on_failure") is True
    )
    checks["bootstrap-confirmation"] = (
        bootstrap.get("requires_confirmation") is True
    )
    checks["bootstrap-no-network-default"] = (
        bootstrap.get("network_contact_default") is False
    )
    checks["bootstrap-no-daemon-default"] = (
        bootstrap.get("container_daemon_contact_default") is False
    )
    checks["bootstrap-modes"] = (
        bootstrap.get("supported_modes") == ["offline", "connected"]
    )

    checks["layout-contract"] = (
        layout.get("contract_version")
        == "leos.installation-layout.v1"
    )
    directories = layout.get("directories", [])
    checks["layout-directory-count-6"] = len(directories) == 6
    checks["layout-paths-unique"] = (
        len({item.get("path") for item in directories})
        == len(directories)
    )
    checks["layout-modes-valid"] = all(
        isinstance(item.get("mode"), str)
        and len(item["mode"]) == 4
        and item["mode"].startswith("0")
        for item in directories
    )
    checks["layout-backups-private"] = any(
        item.get("path") == "backups"
        and item.get("mode") == "0700"
        for item in directories
    )

    schema_expectations = {
        "contracts/installation-layout.v1.schema.json":
            "leos.installation-layout.v1",
        "contracts/installation-transaction.v1.schema.json":
            "leos.installation-transaction.v1",
        "contracts/installation-execution-journal.v1.schema.json":
            "leos.installation-execution-journal.v1",
        "contracts/installation-manifest.v1.schema.json":
            "leos.installation-manifest.v1",
        "contracts/installation-result.v1.schema.json":
            "leos.installation-result.v1",
    }
    for relative, contract in schema_expectations.items():
        schema = parsed.get(relative, {})
        checks[f"schema-id:{relative}"] = bool(schema.get("$id"))
        checks[f"schema-contract:{relative}"] = (
            schema.get("properties", {})
            .get("contract_version", {})
            .get("const")
            == contract
        )
        checks[f"schema-no-additional:{relative}"] = (
            schema.get("additionalProperties") is False
        )

    example_expectations = {
        "examples/installation-transaction.json":
            "leos.installation-transaction.v1",
        "examples/installation-execution-journal.json":
            "leos.installation-execution-journal.v1",
        "examples/installation-manifest.json":
            "leos.installation-manifest.v1",
        "examples/installation-result.json":
            "leos.installation-result.v1",
        "examples/offline-source-manifest.json":
            "leos.offline-source.v2",
        "examples/installer-bootstrap-fixture.json":
            "leos.installer-bootstrap-fixture.v1",
    }
    for relative, contract in example_expectations.items():
        value = parsed.get(relative, {})
        checks[f"example-contract:{relative}"] = (
            value.get("contract_version") == contract
        )

    transaction = parsed.get(
        "examples/installation-transaction.json", {}
    )
    journal = parsed.get(
        "examples/installation-execution-journal.json", {}
    )
    manifest = parsed.get(
        "examples/installation-manifest.json", {}
    )
    result_example = parsed.get(
        "examples/installation-result.json", {}
    )

    portable_examples = {
        "examples/installation-transaction.json": transaction,
        "examples/installation-execution-journal.json": journal,
        "examples/installation-manifest.json": manifest,
        "examples/installation-result.json": result_example,
    }
    for relative, value in portable_examples.items():
        checks[f"portable-paths:{relative}"] = (
            not contains_absolute_host_path(value)
        )

    checks["transaction-action-count-8"] = (
        len(transaction.get("actions", [])) == 8
    )
    checks["transaction-confirmation-required"] = (
        transaction.get("confirmation", {}).get("required") is True
    )
    checks["transaction-rollback-enabled"] = (
        transaction.get("rollback", {}).get("enabled") is True
    )
    checks["transaction-no-network"] = (
        transaction.get("network", {}).get(
            "external_network_contacted"
        )
        is False
    )
    checks["transaction-ownership-intent"] = (
        transaction.get("ownership", {}).get("apply_ownership")
        is False
    )
    checks["journal-complete"] = journal.get("state") == "complete"
    checks["journal-no-network"] = (
        journal.get("external_network_contacted") is False
    )
    checks["journal-no-daemon"] = (
        journal.get("container_daemon_contacted") is False
    )
    checks["journal-rollback-not-performed"] = (
        journal.get("rollback", {}).get("performed") is False
    )
    checks["manifest-installed"] = manifest.get("status") == "installed"
    checks["manifest-files-5"] = len(manifest.get("files", {})) == 5
    checks["manifest-source-rc11"] = (
        manifest.get("source_release")
        == "0.1.0-dev-preview-rc11"
    )
    checks["manifest-source-tree-fixture"] = (
        manifest.get("source_tree_sha256")
        == "bc2a07de0c8eb7cf3312c361c437b4fcef660853a2825654e0561e503ff53d51"
    )
    checks["manifest-ownership-intent"] = (
        manifest.get("ownership", {}).get("apply_ownership")
        is False
    )
    checks["result-example-ok"] = result_example.get("ok") is True
    checks["result-example-no-network"] = (
        result_example.get("external_network_contacted") is False
    )
    checks["result-example-no-daemon"] = (
        result_example.get("container_daemon_contacted") is False
    )
    checks["result-example-no-production-state"] = (
        result_example.get("production_state_accessed") is False
    )
    checks["result-example-no-production-network"] = (
        result_example.get("production_network_attached") is False
    )

    source_text = (
        root / "tools/installer_bootstrap.py"
    ).read_text(encoding="utf-8")
    checks["source-no-httpx"] = "import httpx" not in source_text
    checks["source-no-requests"] = "import requests" not in source_text
    checks["source-no-urllib-request"] = (
        "urllib.request" not in source_text
    )
    checks["source-no-socket"] = "import socket" not in source_text
    checks["source-no-container-create"] = (
        "docker run" not in source_text
        and "podman run" not in source_text
    )
    checks["source-no-chown"] = "os.chown" not in source_text
    checks["source-atomic-replace"] = "os.replace" in source_text
    checks["source-exclusive-lock"] = "os.O_EXCL" in source_text
    checks["source-confirmation-check"] = (
        "Confirmation token must exactly match" in source_text
    )
    checks["source-rollback-path"] = "restore_record" in source_text
    checks["source-idempotent-compare"] = (
        'before["sha256"] == after_sha' in source_text
    )
    checks["source-target-safety"] = (
        "SAFE_TARGET_FORBIDDEN" in source_text
    )
    checks["source-connected-opt-in"] = (
        "Connected mode requires --allow-network" in source_text
    )
    checks["source-authority-files"] = (
        "manifest.json" in source_text
        and "source.lock.json" in source_text
        and "rc9-release.json" not in source_text
    )

    unit = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(root / "tests/phase5242"),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    test_count = (
        unit.stdout.count(" ... ok")
        + unit.stderr.count(" ... ok")
    )
    checks["unit-tests-exit-zero"] = unit.returncode == 0
    checks["unit-tests-20"] = test_count == 20

    with tempfile.TemporaryDirectory(
        prefix="leos-phase5242-validation-"
    ) as temporary:
        temp = Path(temporary)
        source_root = temp / "source"
        source_root.mkdir()
        for authority_name in ("manifest.json", "source.lock.json"):
            (source_root / authority_name).write_bytes(
                (root / authority_name).read_bytes()
            )
        target = temp / "leos"
        plan_path = root / "examples/installation-plan.json"
        common = [
            str(root / "bin/leos-install"),
            "--bootstrap-config",
            str(root / "config/installer-bootstrap.json"),
            "--layout-config",
            str(root / "config/installation-layout.json"),
        ]
        rc, planned, _ = run_json(
            [
                *common,
                "plan",
                "--plan",
                str(plan_path),
                "--target-root",
                str(target),
                "--mode",
                "offline",
                "--source-root",
                str(source_root),
            ],
            root,
        )
        checks["accept-plan-exit-zero"] = rc == 0
        checks["accept-plan-ok"] = planned.get("ok") is True
        checks["accept-plan-non-mutating"] = (
            planned.get("mutates_host") is False
            and not target.exists()
        )

        plan_id = read_json(plan_path)["plan_id"]
        rc, first, first_stderr = run_json(
            [
                *common,
                "apply",
                "--plan",
                str(plan_path),
                "--target-root",
                str(target),
                "--mode",
                "offline",
                "--source-root",
                str(source_root),
                "--confirm",
                plan_id,
                "--desired-owner",
                "leos",
                "--desired-group",
                "leos",
            ],
            root,
        )
        checks["accept-first-exit-zero"] = rc == 0
        checks["accept-first-ok"] = first.get("ok") is True
        checks["accept-first-changed"] = first.get("changed") is True
        checks["accept-first-manifest"] = (
            first.get("manifest", {}).get("contract_version")
            == "leos.installation-manifest.v1"
        )
        checks["accept-first-journal"] = (
            first.get("journal", {}).get("contract_version")
            == "leos.installation-execution-journal.v1"
        )
        checks["accept-first-no-network"] = (
            first.get("external_network_contacted") is False
        )
        checks["accept-first-no-daemon"] = (
            first.get("container_daemon_contacted") is False
        )

        rc, second, _ = run_json(
            [
                *common,
                "apply",
                "--plan",
                str(plan_path),
                "--target-root",
                str(target),
                "--mode",
                "offline",
                "--source-root",
                str(source_root),
                "--confirm",
                plan_id,
                "--desired-owner",
                "leos",
                "--desired-group",
                "leos",
            ],
            root,
        )
        checks["accept-second-exit-zero"] = rc == 0
        checks["accept-second-ok"] = second.get("ok") is True
        checks["accept-second-idempotent"] = (
            second.get("idempotent") is True
            and second.get("changed_count") == 0
        )

        rc, inspection, _ = run_json(
            [
                *common,
                "inspect",
                "--target-root",
                str(target),
            ],
            root,
        )
        checks["accept-inspect-exit-zero"] = rc == 0
        checks["accept-inspect-installed"] = (
            inspection.get("installed") is True
        )
        checks["accept-inspect-no-drift"] = (
            inspection.get("drift_count") == 0
        )

        connected_target = temp / "connected"
        rc, connected, _ = run_json(
            [
                *common,
                "plan",
                "--plan",
                str(plan_path),
                "--target-root",
                str(connected_target),
                "--mode",
                "connected",
                "--allow-network",
            ],
            root,
        )
        checks["accept-connected-exit-zero"] = rc == 0
        checks["accept-connected-authorized"] = (
            connected.get("transaction", {})
            .get("network", {})
            .get("permission_granted")
            is True
        )
        checks["accept-connected-no-contact"] = (
            connected.get("external_network_contacted") is False
            and not connected_target.exists()
        )

        failed_target = temp / "failed"
        rc, failed, _ = run_json(
            [
                *common,
                "apply",
                "--plan",
                str(plan_path),
                "--target-root",
                str(failed_target),
                "--mode",
                "offline",
                "--source-root",
                str(source_root),
                "--confirm",
                plan_id,
                "--fail-after",
                "4",
            ],
            root,
        )
        checks["accept-failure-exit-nonzero"] = rc != 0
        checks["accept-failure-reported"] = failed.get("ok") is False
        checks["accept-failure-rolled-back"] = not (
            failed_target
            / "state/installation-manifest.json"
        ).exists()

    errors = [name for name, passed in checks.items() if not passed]
    output = {
        "ok": not errors,
        "phase": "52.4.2",
        "contract_version": (
            "leos.phase52.4.2-installer-bootstrap-validation.v1"
        ),
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
        "unit_tests": {
            "ok": unit.returncode == 0,
            "returncode": unit.returncode,
            "test_count": test_count,
            "stdout": unit.stdout,
            "stderr": unit.stderr,
        },
        "fixture_acceptance": {
            "first_changed_count": first.get("changed_count"),
            "second_changed_count": second.get("changed_count"),
            "second_idempotent": second.get("idempotent"),
            "installation_id": first.get("manifest", {}).get(
                "installation_id"
            ),
            "transaction_id": first.get("transaction", {}).get(
                "transaction_id"
            ),
            "rollback_failure_observed": failed.get("ok") is False,
        },
        "production_state_accessed": False,
        "production_network_attached": False,
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "docker_socket_mounted": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
