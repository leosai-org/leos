#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


CONTRACT = "leos.phase52.1-runtime-resource-enforcement-validation.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def service_root(root: Path, service_id: str) -> Path:
    direct = root / service_id
    if direct.is_dir():
        return direct
    return root / "services" / service_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    scheduler_root = service_root(
        root, "execution-scheduler-service"
    )
    runtime_root = service_root(
        root, "persistent-employee-runtime-service"
    )
    resource_root = service_root(
        root, "employee-resource-profile-service"
    )

    paths = {
        "scheduler": scheduler_root / "app/main.py",
        "runtime": runtime_root / "app/main.py",
        "resource_main": resource_root / "app/main.py",
        "resource_engine": resource_root / "app/resource_engine.py",
        "catalog": root / "config/service-catalog.json",
        "configuration": root
        / "config/runtime-resource-enforcement.json",
        "contract": root
        / "contracts/runtime-resource-enforcement.v1.schema.json",
        "scheduler_test": scheduler_root
        / "tests/test_phase521_resource_enforcement.py",
        "resource_test": resource_root
        / "tests/test_phase521_runtime_reservation.py",
        "runtime_test": runtime_root
        / "tests/test_phase521_runtime_resource_gate.py",
    }

    checks: dict[str, bool] = {}
    errors: list[str] = []

    for name, path in paths.items():
        checks[f"{name}_exists"] = path.is_file()
        if not path.is_file():
            errors.append(f"Missing required file: {path}")

    python_paths = [
        paths["scheduler"],
        paths["runtime"],
        paths["resource_main"],
        paths["resource_engine"],
        paths["scheduler_test"],
        paths["resource_test"],
        paths["runtime_test"],
    ]
    for path in python_paths:
        key = f"ast:{path.relative_to(root)}"
        if not path.is_file():
            checks[key] = False
            continue
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
            )
            checks[key] = True
        except Exception as exc:
            checks[key] = False
            errors.append(f"AST validation failed for {path}: {exc}")

    if all(path.is_file() for path in python_paths[:4]):
        scheduler = paths["scheduler"].read_text(encoding="utf-8")
        runtime = paths["runtime"].read_text(encoding="utf-8")
        resource_main = paths["resource_main"].read_text(
            encoding="utf-8"
        )
        resource_engine = paths["resource_engine"].read_text(
            encoding="utf-8"
        )

        scheduler_markers = [
            'SERVICE_VERSION = "0.2.0"',
            "RESOURCE_PROFILE_URL",
            "RESOURCE_FAIL_CLOSED",
            "def reserve_resources(",
            "def validate_job_resource_reservation(",
            "def reconcile_resource_reservations(",
            "resource_reservation_id",
            '@app.post("/resources/reconcile")',
            '@app.get("/jobs/{job_id}/resource")',
            '@app.get("/resource-history")',
        ]
        runtime_markers = [
            'SERVICE_VERSION = "0.2.0"',
            "resource_reservation_id",
            "resource_node_id",
            "resource_gpu_uuid",
            "Scheduler resource validation could not",
            "Scheduler completion and resource release",
        ]
        resource_markers = [
            "def active_reservation_for_job(",
            "def expire_reservations(",
            '@app.get("/reservations/by-job/{job_id}")',
            '@app.post("/reservations/expire")',
        ]

        checks["scheduler_enforcement_markers"] = all(
            marker in scheduler for marker in scheduler_markers
        )
        checks["runtime_enforcement_markers"] = all(
            marker in runtime for marker in runtime_markers
        )
        checks["resource_authority_markers"] = (
            all(
                marker in resource_engine
                for marker in resource_markers[:2]
            )
            and all(
                marker in resource_main
                for marker in resource_markers[2:]
            )
        )

    if paths["catalog"].is_file():
        catalog = read_json(paths["catalog"])
        services = {
            item.get("service_id"): item
            for item in catalog.get("services", [])
            if isinstance(item, dict)
        }
        checks["resource_service_in_catalog"] = (
            "employee-resource-profile-service" in services
        )
        scheduler_entry = services.get(
            "execution-scheduler-service", {}
        )
        checks["scheduler_depends_on_resource_authority"] = (
            "employee-resource-profile-service"
            in scheduler_entry.get("dependencies", [])
        )
        checks["scheduler_contract_current"] = (
            scheduler_entry.get("contract_version")
            == "leos.runtime-resource-enforcement.v1"
        )

    if paths["configuration"].is_file():
        config = read_json(paths["configuration"])
        checks["configuration_contract_current"] = (
            config.get("contract_version")
            == "leos.runtime-resource-enforcement.v1"
        )
        checks["configuration_mandatory"] = (
            config.get("mandatory") is True
        )
        checks["configuration_fail_closed"] = (
            config.get("fail_closed") is True
        )
        security = config.get("security", {})
        checks["configuration_no_docker_socket"] = (
            security.get("docker_socket_required") is False
        )
        checks["configuration_no_production_network"] = (
            security.get("production_network_required") is False
        )
        checks["configuration_no_production_state_write"] = (
            security.get("production_state_write_required") is False
        )

    if paths["contract"].is_file():
        contract = read_json(paths["contract"])
        checks["json_schema_current"] = (
            contract.get("$schema")
            == "https://json-schema.org/draft/2020-12/schema"
        )
        required = set(contract.get("required", []))
        checks["contract_requires_reservation"] = {
            "resource_reservation_id",
            "resource_state",
            "resource_decision",
        }.issubset(required)

    for key, ok in checks.items():
        if not ok:
            errors.append(f"Validation check failed: {key}")

    result = {
        "ok": not errors,
        "contract_version": CONTRACT,
        "phase": "52.1",
        "check_count": len(checks),
        "error_count": len(errors),
        "checks": checks,
        "errors": errors,
        "files": {
            name: {
                "path": str(path),
                "sha256": sha256(path) if path.is_file() else None,
            }
            for name, path in paths.items()
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
