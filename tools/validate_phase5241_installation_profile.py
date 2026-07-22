#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "bin/leos-install-profile",
    "tools/installation_profile.py",
    "tools/validate_phase5241_installation_profile.py",
    "contracts/host-capability-inventory.v1.schema.json",
    "contracts/installation-profile-recommendation.v1.schema.json",
    "contracts/installation-plan.v1.schema.json",
    "config/installation-profiles.json",
    "docs/phase52.4.1-installation-profile-hardware-detection.md",
    "examples/installation-profile-fixture.json",
    "examples/host-capability-inventory.json",
    "examples/installation-profile-recommendation.json",
    "examples/installation-plan.json",
    "tests/phase5241/test_installation_profile.py",
]

EXPECTED_SCHEMA_CONTRACTS = {
    "host-capability-inventory.v1.schema.json":
        "leos.host-capability-inventory.v1",
    "installation-profile-recommendation.v1.schema.json":
        "leos.installation-profile-recommendation.v1",
    "installation-plan.v1.schema.json":
        "leos.installation-plan.v1",
}

EXPECTED_PROFILE_IDS = [
    "leos-standard-large-nvidia",
    "leos-standard-nvidia",
    "leos-standard-cpu",
    "leos-standard-minimum",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(
        "leos_phase5241_validator_module",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    root = args.root.resolve()

    checks: dict[str, bool] = {}
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        present = (root / relative).is_file()
        checks[f"file:{relative}"] = present
        if not present:
            errors.append(f"missing:{relative}")

    python_files = [
        "tools/installation_profile.py",
        "tools/validate_phase5241_installation_profile.py",
        "tests/phase5241/test_installation_profile.py",
    ]
    for relative in python_files:
        valid = False
        path = root / relative
        if path.is_file():
            try:
                ast.parse(
                    path.read_text(encoding="utf-8"),
                    filename=str(path),
                )
                valid = True
            except SyntaxError as exc:
                errors.append(f"python:{relative}:{exc}")
        checks[f"python-syntax:{relative}"] = valid

    json_files = [
        "contracts/host-capability-inventory.v1.schema.json",
        "contracts/installation-profile-recommendation.v1.schema.json",
        "contracts/installation-plan.v1.schema.json",
        "config/installation-profiles.json",
        "examples/installation-profile-fixture.json",
        "examples/host-capability-inventory.json",
        "examples/installation-profile-recommendation.json",
        "examples/installation-plan.json",
    ]
    json_values = {}
    for relative in json_files:
        valid = False
        path = root / relative
        if path.is_file():
            try:
                json_values[relative] = read_json(path)
                valid = True
            except Exception as exc:
                errors.append(f"json:{relative}:{exc}")
        checks[f"json:{relative}"] = valid

    for filename, contract in EXPECTED_SCHEMA_CONTRACTS.items():
        schema = json_values.get(f"contracts/{filename}", {})
        valid = (
            schema.get("$schema")
            == "https://json-schema.org/draft/2020-12/schema"
            and schema.get("type") == "object"
            and contract in json.dumps(schema, sort_keys=True)
        )
        checks[f"schema-contract:{filename}"] = valid

    catalog = json_values.get(
        "config/installation-profiles.json",
        {},
    )
    profiles = catalog.get("profiles", [])
    profile_ids = [
        item.get("profile_id")
        for item in profiles
        if isinstance(item, dict)
    ]
    priorities = [
        item.get("priority")
        for item in profiles
        if isinstance(item, dict)
    ]

    catalog_checks = {
        "catalog-contract": (
            catalog.get("contract_version")
            == "leos.installation-profile-catalog.v1"
        ),
        "catalog-profile-count-4": len(profiles) == 4,
        "catalog-profile-order": profile_ids == EXPECTED_PROFILE_IDS,
        "catalog-priorities-unique": (
            len(priorities) == len(set(priorities))
        ),
        "catalog-priorities-descending": priorities == sorted(
            priorities,
            reverse=True,
        ),
        "catalog-standard-only": all(
            str(profile_id).startswith("leos-standard-")
            for profile_id in profile_ids
        ),
        "catalog-minimum-degraded": (
            profiles[-1].get("suitability") == "degraded"
            if profiles
            else False
        ),
    }
    checks.update(catalog_checks)

    wrapper = root / "bin/leos-install-profile"
    wrapper_text = (
        wrapper.read_text(encoding="utf-8")
        if wrapper.is_file()
        else ""
    )
    checks.update(
        {
            "wrapper-executable": (
                wrapper.is_file()
                and bool(
                    stat.S_IMODE(wrapper.stat().st_mode)
                    & stat.S_IXUSR
                )
            ),
            "wrapper-strict-shell": "set -euo pipefail" in wrapper_text,
            "wrapper-targets-installation-profile": (
                "tools/installation_profile.py" in wrapper_text
            ),
        }
    )

    tool_path = root / "tools/installation_profile.py"
    module = load_module(tool_path)
    fixture = json_values.get(
        "examples/installation-profile-fixture.json",
        {},
    )
    inventory = module.collect_inventory(
        node_id="node-example",
        storage_path=Path("."),
        fixture=fixture,
        contact_container_daemon=False,
    )
    profile_catalog = module.load_profile_catalog(
        root / "config/installation-profiles.json"
    )
    recommendation = module.recommend_profile(
        inventory,
        profile_catalog,
    )
    plan = module.build_installation_plan(
        inventory,
        recommendation,
    )

    inventory_example = json_values.get(
        "examples/host-capability-inventory.json",
        {},
    )
    recommendation_example = json_values.get(
        "examples/installation-profile-recommendation.json",
        {},
    )
    plan_example = json_values.get(
        "examples/installation-plan.json",
        {},
    )

    semantic_checks = {
        "inventory-contract": (
            inventory.get("contract_version")
            == "leos.host-capability-inventory.v1"
        ),
        "inventory-example-deterministic": inventory == inventory_example,
        "inventory-no-external-network": (
            inventory.get("probe", {}).get(
                "external_network_contacted"
            )
            is False
        ),
        "inventory-no-daemon-contact": (
            inventory.get("probe", {}).get(
                "container_daemon_contacted"
            )
            is False
        ),
        "recommendation-contract": (
            recommendation.get("contract_version")
            == "leos.installation-profile-recommendation.v1"
        ),
        "recommendation-example-deterministic": (
            recommendation == recommendation_example
        ),
        "recommendation-standard-nvidia": (
            recommendation.get("selected_profile")
            == "leos-standard-nvidia"
        ),
        "recommendation-ready": (
            recommendation.get("readiness") == "ready"
        ),
        "recommendation-no-blockers": (
            recommendation.get("blockers") == []
        ),
        "recommendation-concurrency-positive": (
            recommendation.get("resource_budget", {}).get(
                "max_concurrent_employees",
                0,
            )
            >= 1
        ),
        "plan-contract": (
            plan.get("contract_version")
            == "leos.installation-plan.v1"
        ),
        "plan-example-deterministic": plan == plan_example,
        "plan-does-not-mutate-host": (
            plan.get("execution", {}).get("mutates_host")
            is False
        ),
        "plan-requires-confirmation": (
            plan.get("execution", {}).get(
                "requires_confirmation"
            )
            is True
        ),
        "plan-no-external-network": (
            plan.get("execution", {}).get(
                "external_network_contacted"
            )
            is False
        ),
        "plan-compute-capacity-contract": (
            plan.get("compute_node_capacity", {}).get(
                "contract_version"
            )
            == "leos.compute-node-capacity.v1"
        ),
        "plan-action-count-8": len(plan.get("actions", [])) == 8,
        "plan-gpu-mode-nvidia": (
            plan.get("environment", {}).get("LEOS_GPU_MODE")
            == "nvidia"
        ),
    }
    checks.update(semantic_checks)

    tool_text = (
        tool_path.read_text(encoding="utf-8")
        if tool_path.is_file()
        else ""
    )
    source_policy_checks = {
        "source-no-http-client-import": all(
            token not in tool_text
            for token in (
                "import requests",
                "from urllib.request",
                "import httpx",
            )
        ),
        "source-no-container-create": all(
            token not in tool_text
            for token in (
                '"run", "-d"',
                '"compose", "up"',
                '"container", "create"',
            )
        ),
        "source-fixture-mode": "--fixture" in tool_text,
        "source-daemon-probe-opt-in": (
            "--contact-container-daemon" in tool_text
        ),
        "source-external-network-false": (
            '"external_network_contacted": False'
            in tool_text
        ),
        "source-compute-node-projection": (
            "leos.compute-node-capacity.v1" in tool_text
        ),
    }
    checks.update(source_policy_checks)

    cli = command(
        [
            sys.executable,
            "-B",
            str(tool_path),
            "--catalog",
            str(root / "config/installation-profiles.json"),
            "--node-id",
            "node-example",
            "--fixture",
            str(
                root
                / "examples/installation-profile-fixture.json"
            ),
            "all",
        ],
        cwd=root,
    )
    cli_value = {}
    if cli.returncode == 0 and cli.stdout.strip():
        try:
            cli_value = json.loads(cli.stdout)
        except Exception as exc:
            errors.append(f"cli-json:{exc}")

    checks.update(
        {
            "cli-exit-zero": cli.returncode == 0,
            "cli-json-object": isinstance(cli_value, dict),
            "cli-ok": cli_value.get("ok") is True,
            "cli-inventory-match": (
                cli_value.get("inventory") == inventory_example
            ),
            "cli-recommendation-match": (
                cli_value.get("recommendation")
                == recommendation_example
            ),
            "cli-plan-match": (
                cli_value.get("plan") == plan_example
            ),
        }
    )

    unit = command(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            str(root / "tests/phase5241"),
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=root,
        timeout=300,
    )
    unit_count = (
        unit.stderr.count(" ... ok")
        + unit.stdout.count(" ... ok")
    )
    checks.update(
        {
            "unit-tests-exit-zero": unit.returncode == 0,
            "unit-tests-14": unit_count == 14,
            "unit-tests-summary-ok": (
                "OK" in unit.stderr or "OK" in unit.stdout
            ),
        }
    )

    for name, passed in checks.items():
        if not passed and name not in errors:
            errors.append(name)

    output = {
        "ok": not errors,
        "phase": "52.4.1",
        "contract_version": (
            "leos.phase52.4.1-installation-profile-validation.v1"
        ),
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
        "unit_tests": {
            "ok": unit.returncode == 0,
            "test_count": unit_count,
            "returncode": unit.returncode,
            "stdout": unit.stdout,
            "stderr": unit.stderr,
        },
        "fixture_acceptance": {
            "inventory_id": inventory.get("inventory_id"),
            "recommendation_id": recommendation.get(
                "recommendation_id"
            ),
            "plan_id": plan.get("plan_id"),
            "selected_profile": recommendation.get(
                "selected_profile"
            ),
            "readiness": recommendation.get("readiness"),
            "max_concurrent_employees": recommendation.get(
                "resource_budget",
                {},
            ).get("max_concurrent_employees"),
        },
        "production_state_accessed": False,
        "production_network_attached": False,
        "external_network_contacted": False,
        "docker_socket_mounted": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
