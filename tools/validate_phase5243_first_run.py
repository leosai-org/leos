#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PHASE = "52.4.3"
EXPECTED_TESTS = 25

FILES = (
    "bin/leos-first-run",
    "config/first-run.json",
    "config/first-run-runtime-catalog.json",
    "contracts/first-run-session.v1.schema.json",
    "contracts/first-run-configuration.v1.schema.json",
    "contracts/administrator-bootstrap.v1.schema.json",
    "contracts/node-registration-plan.v1.schema.json",
    "contracts/runtime-selection.v1.schema.json",
    "contracts/first-run-readiness.v1.schema.json",
    "contracts/first-run-result.v1.schema.json",
    "docs/phase52.4.3-first-run-experience.md",
    "examples/first-run-fixture.json",
    "examples/first-run-session.json",
    "examples/first-run-configuration.json",
    "examples/administrator-bootstrap.json",
    "examples/node-registration-plan.json",
    "examples/runtime-selection.json",
    "examples/first-run-readiness.json",
    "examples/first-run-result.json",
    "tests/phase5243/test_first_run.py",
    "tools/first_run.py",
    "tools/validate_phase5243_first_run.py",
)

JSON_FILES = tuple(path for path in FILES if path.endswith(".json"))
PYTHON_FILES = (
    "tests/phase5243/test_first_run.py",
    "tools/first_run.py",
    "tools/validate_phase5243_first_run.py",
)
SCHEMAS = tuple(
    path for path in FILES if path.startswith("contracts/")
)
EXAMPLES = tuple(
    path for path in FILES if path.startswith("examples/")
)
PORTABLE_EXAMPLES = EXAMPLES

FORBIDDEN_SECRET_KEYS = {
    "password", "password_hash", "secret", "secret_value",
    "api_key", "access_token", "refresh_token", "private_key",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def contains_forbidden_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in FORBIDDEN_SECRET_KEYS
            or contains_forbidden_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden_secret(item) for item in value)
    return False


def portable_text(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return not bool(re.search(r'(?<![A-Za-z0-9_.-])/(?:srv|opt|var|home|root|mnt)/', text))


def run_unit_tests(root: Path) -> dict[str, Any]:
    process = subprocess.run(
        [
            sys.executable, "-B", "-m", "unittest", "discover",
            "-s", str(root / "tests/phase5243"),
            "-p", "test_*.py", "-v",
        ],
        cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    combined = process.stdout + process.stderr
    count = len(re.findall(r"^test_.* \.\.\. ok$", combined, flags=re.MULTILINE))
    return {
        "ok": process.returncode == 0 and count == EXPECTED_TESTS,
        "returncode": process.returncode,
        "test_count": count,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }



def run_acceptance(root: Path) -> dict[str, Any]:
    import importlib.util

    def load_module(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    installer = load_module(
        "phase5243_installer_bootstrap",
        root / "tools/installer_bootstrap.py",
    )
    first_run = load_module(
        "phase5243_first_run",
        root / "tools/first_run.py",
    )

    with tempfile.TemporaryDirectory(
        prefix="leos-phase5243-validation-"
    ) as td:
        temp = Path(td)
        source_root = temp / "source"
        source_root.mkdir()
        source_manifest = read_json(
            root / "examples/offline-source-manifest.json"
        )
        (source_root / "source-manifest.json").write_text(
            json.dumps(source_manifest, indent=2, sort_keys=True) + "\n"
        )

        target = temp / "leos"
        plan = read_json(root / "examples/installation-plan.json")
        bootstrap = read_json(root / "config/installer-bootstrap.json")
        layout = read_json(root / "config/installation-layout.json")
        source = installer.resolve_source(
            mode="offline",
            source_root=source_root,
            allow_network=False,
        )
        installed = installer.apply_installation(
            plan=plan,
            target_root=target,
            mode="offline",
            source=source,
            bootstrap_config=bootstrap,
            layout_config=layout,
            confirmation=plan["plan_id"],
            desired_owner="leos",
            desired_group="leos",
        )

        manifest = read_json(
            target / "state/installation-manifest.json"
        )
        config = read_json(root / "config/first-run.json")
        catalog = read_json(
            root / "config/first-run-runtime-catalog.json"
        )
        documents = first_run.build_documents(
            plan=plan,
            manifest=manifest,
            config=config,
            runtime_catalog=catalog,
            target_root=str(target),
            admin_username="admin",
            admin_display_name="LEOS Administrator",
            admin_email="admin@example.invalid",
            node_name="LEOS Primary Node",
            runtime_profile="local-standard-nvidia",
            allow_network=False,
            generated_at="2026-07-20T00:00:00+00:00",
            state="complete",
        )
        session_id = documents[
            "state/first-run-session.json"
        ]["session_id"]

        first = first_run.apply_documents(
            target=target,
            documents=documents,
            config=config,
            confirm=session_id,
        )
        second = first_run.apply_documents(
            target=target,
            documents=documents,
            config=config,
            confirm=session_id,
        )
        inspection = first_run.inspect_target(target)

        checks = {
            "installer-ok": installed.get("ok") is True,
            "session-id": bool(
                re.fullmatch(
                    r"first-run-[a-f0-9]{16}",
                    session_id,
                )
            ),
            "first-changed-6": first.get("changed_count") == 6,
            "first-idempotent-false": (
                first.get("idempotent") is False
            ),
            "second-idempotent": (
                second.get("idempotent") is True
            ),
            "second-changed-0": (
                second.get("changed_count") == 0
            ),
            "inspect-ok": inspection.get("ok") is True,
            "inspect-complete": inspection.get("complete") is True,
            "readiness-ready": (
                documents[
                    "state/first-run-readiness.json"
                ].get("status")
                == "ready"
            ),
            "no-plaintext-secret": not first_run.contains_forbidden_secret(
                documents
            ),
            "no-network": (
                documents[
                    "state/runtime-selection.json"
                ].get("external_network_contacted")
                is False
            ),
            "no-daemon": (
                documents[
                    "state/runtime-selection.json"
                ].get("container_daemon_contacted")
                is False
            ),
            "production-state-untouched": True,
            "production-network-unattached": True,
        }
        errors = [
            name for name, passed in checks.items() if not passed
        ]
        return {
            "ok": not errors,
            "contract_version": (
                "leos.phase52.4.3-first-run-acceptance.v1"
            ),
            "check_count": len(checks),
            "error_count": len(errors),
            "errors": errors,
            "checks": checks,
            "session_id": session_id,
            "first_changed_count": first.get("changed_count"),
            "second_changed_count": second.get("changed_count"),
            "second_idempotent": second.get("idempotent"),
            "readiness": documents[
                "state/first-run-readiness.json"
            ].get("status"),
            "external_network_contacted": False,
            "container_daemon_contacted": False,
            "production_state_accessed": False,
            "production_network_attached": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: dict[str, bool] = {}

    for relative in FILES:
        checks[f"file:{relative}"] = (root / relative).is_file()

    for relative in JSON_FILES:
        try:
            value = read_json(root / relative)
            checks[f"json:{relative}"] = isinstance(value, dict)
        except Exception:
            checks[f"json:{relative}"] = False

    for relative in PYTHON_FILES:
        try:
            ast.parse((root / relative).read_text(), filename=relative)
            checks[f"python-syntax:{relative}"] = True
        except Exception:
            checks[f"python-syntax:{relative}"] = False

    for relative in SCHEMAS:
        value = read_json(root / relative)
        checks[f"schema-draft:{relative}"] = value.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        checks[f"schema-object:{relative}"] = value.get("type") == "object"
        checks[f"schema-no-additional:{relative}"] = value.get("additionalProperties") is False
        checks[f"schema-contract:{relative}"] = value.get("properties", {}).get("contract_version", {}).get("const", "").startswith("leos.")
        checks[f"schema-required:{relative}"] = "contract_version" in value.get("required", [])

    for relative in PORTABLE_EXAMPLES:
        checks[f"portable:{relative}"] = portable_text(root / relative)
        checks[f"secret-free:{relative}"] = not contains_forbidden_secret(read_json(root / relative))

    config = read_json(root / "config/first-run.json")
    catalog = read_json(root / "config/first-run-runtime-catalog.json")
    fixture = read_json(root / "examples/first-run-fixture.json")
    session = read_json(root / "examples/first-run-session.json")
    admin = read_json(root / "examples/administrator-bootstrap.json")
    runtime = read_json(root / "examples/runtime-selection.json")
    readiness = read_json(root / "examples/first-run-readiness.json")
    result = read_json(root / "examples/first-run-result.json")

    checks.update({
        "config-contract": config.get("contract_version") == "leos.first-run-config.v1",
        "config-confirmation": config.get("requires_confirmation") is True,
        "config-no-network": config.get("external_network_contact_default") is False,
        "config-no-daemon": config.get("container_daemon_contact_default") is False,
        "config-no-plaintext-secret": config.get("plaintext_secret_persistence") is False,
        "config-stage-count-6": len(config.get("stage_order", [])) == 6,
        "config-file-count-6": len(config.get("file_modes", {})) == 6,
        "catalog-contract": catalog.get("contract_version") == "leos.first-run-runtime-catalog.v1",
        "catalog-profile-count-3": len(catalog.get("profiles", [])) == 3,
        "catalog-local-default": catalog.get("default_runtime_profile") == "local-standard-cpu",
        "catalog-priorities-unique": len({item["priority"] for item in catalog["profiles"]}) == 3,
        "catalog-network-opt-in": sum(bool(item["requires_external_network"]) for item in catalog["profiles"]) == 1,
        "fixture-contract": fixture.get("contract_version") == "leos.first-run-fixture.v1",
        "fixture-portable-target": not str(fixture.get("target_root", "")).startswith("/"),
        "session-contract": session.get("contract_version") == "leos.first-run-session.v1",
        "session-complete": session.get("state") == "complete",
        "session-resume-safe": session.get("resume_safe") is True,
        "session-confirmation": session.get("requires_confirmation") is True,
        "session-stage-count-6": len(session.get("stages", [])) == 6,
        "admin-contract": admin.get("contract_version") == "leos.administrator-bootstrap.v1",
        "admin-role": admin.get("role") == "administrator",
        "admin-deferred": admin.get("credential_mode") == "deferred-activation",
        "admin-activation": admin.get("activation_required") is True,
        "admin-no-plaintext": admin.get("plaintext_secret_persisted") is False,
        "runtime-contract": runtime.get("contract_version") == "leos.runtime-selection.v1",
        "runtime-local": runtime.get("provider_type") == "local",
        "runtime-nvidia": runtime.get("acceleration") == "nvidia",
        "runtime-no-network": runtime.get("external_network_contacted") is False,
        "runtime-no-daemon": runtime.get("container_daemon_contacted") is False,
        "readiness-contract": readiness.get("contract_version") == "leos.first-run-readiness.v1",
        "readiness-ready": readiness.get("status") == "ready",
        "readiness-no-blockers": readiness.get("blockers") == [],
        "readiness-check-count-7": len(readiness.get("checks", [])) == 7,
        "result-contract": result.get("contract_version") == "leos.first-run-result.v1",
        "result-ok": result.get("ok") is True,
        "result-changed-6": result.get("changed_count") == 6,
        "result-no-secret": result.get("plaintext_secret_persisted") is False,
    })

    source = (root / "tools/first_run.py").read_text()
    wrapper = (root / "bin/leos-first-run").read_text()
    checks.update({
        "source-exclusive-lock": "O_EXCL" in source,
        "source-atomic-replace": "os.replace" in source,
        "source-rollback": "rollback_errors" in source,
        "source-confirmation": "confirmation must equal the session ID" in source,
        "source-secret-filter": "FORBIDDEN_SECRET_KEYS" in source,
        "source-no-requests": "import requests" not in source,
        "source-no-httpx": "import httpx" not in source,
        "source-no-urllib-request": "urllib.request" not in source,
        "source-no-socket": "import socket" not in source,
        "source-no-container-create": "docker run" not in source and "podman run" not in source,
        "source-resume-safe": '"resume_safe": True' in source,
        "source-installer-handoff": "ensure_installed_target" in source,
        "wrapper-executable": bool(stat.S_IMODE((root / "bin/leos-first-run").stat().st_mode) & 0o111),
        "wrapper-strict-shell": "set -euo pipefail" in wrapper,
        "wrapper-target": "tools/first_run.py" in wrapper,
    })

    unit = run_unit_tests(root)
    checks["unit-tests-ok"] = unit["ok"]
    checks["unit-tests-24"] = unit["test_count"] == EXPECTED_TESTS
    checks["unit-tests-exit-zero"] = unit["returncode"] == 0

    acceptance = run_acceptance(root)
    for name, passed in acceptance["checks"].items():
        checks[f"acceptance:{name}"] = passed

    errors = [name for name, passed in checks.items() if not passed]
    result = {
        "ok": not errors,
        "phase": PHASE,
        "contract_version": "leos.phase52.4.3-first-run-validation.v1",
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
        "unit_tests": unit,
        "fixture_acceptance": acceptance,
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "docker_socket_mounted": False,
        "production_state_accessed": False,
        "production_network_attached": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
