#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
from typing import Any


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=os.environ.get("LEOS_ROOT", str(Path.cwd())),
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    files = {
        "registry_app": root / "employee-registry" / "app.py",
        "lifecycle_engine": root / "employee-registry" / "lifecycle_engine.py",
        "registry_test": root / "employee-registry" / "tests" / "test_lifecycle_engine.py",
        "scheduler": root / "execution-scheduler-service" / "app" / "main.py",
        "scheduler_test": root / "execution-scheduler-service" / "tests" / "test_phase522_employee_lifecycle.py",
        "assignment": root / "assignment-service" / "app.py",
        "builder": root / "employee-builder" / "app.py",
        "definition_contract": root / "contracts" / "employee-definition.v2.schema.json",
        "lifecycle_contract": root / "contracts" / "employee-lifecycle.v1.schema.json",
        "configuration": root / "config" / "employee-lifecycle.json",
        "catalog": root / "config" / "service-catalog.json",
        "documentation": root / "docs" / "phase52.2-employee-definition-lifecycle.md",
    }

    checks: dict[str, bool] = {}
    errors: list[str] = []
    for name, path in files.items():
        checks[f"file:{name}"] = path.is_file()

    python_names = (
        "registry_app",
        "lifecycle_engine",
        "registry_test",
        "scheduler",
        "scheduler_test",
        "assignment",
        "builder",
    )
    texts: dict[str, str] = {}
    for name, path in files.items():
        if path.is_file():
            texts[name] = read(path)
    for name in python_names:
        try:
            ast.parse(texts.get(name, ""), filename=str(files[name]))
            checks[f"ast:{name}"] = True
        except Exception as exc:
            checks[f"ast:{name}"] = False
            errors.append(f"ast:{name}:{exc}")

    try:
        definition = json.loads(read(files["definition_contract"]))
        checks["definition_contract_v2"] = (
            definition.get("properties", {}).get("contract_version", {}).get("const")
            == "leos.employee-definition.v2"
        )
        checks["definition_requires_capabilities"] = "capabilities" in definition.get("required", [])
        checks["definition_requires_resource_profile"] = "resource_profile" in definition.get("required", [])
        checks["definition_requires_schedule"] = "schedule" in definition.get("required", [])
    except Exception as exc:
        errors.append(f"definition-contract:{exc}")
        checks["definition_contract_v2"] = False
        checks["definition_requires_capabilities"] = False
        checks["definition_requires_resource_profile"] = False
        checks["definition_requires_schedule"] = False

    try:
        lifecycle = json.loads(read(files["lifecycle_contract"]))
        enum = lifecycle.get("properties", {}).get("lifecycle_status", {}).get("enum", [])
        checks["lifecycle_contract_v1"] = (
            lifecycle.get("properties", {}).get("lifecycle_contract", {}).get("const")
            == "leos.employee-lifecycle.v1"
        )
        checks["lifecycle_states_complete"] = set(enum) == {
            "draft", "validated", "active", "paused", "disabled", "archived"
        }
    except Exception as exc:
        errors.append(f"lifecycle-contract:{exc}")
        checks["lifecycle_contract_v1"] = False
        checks["lifecycle_states_complete"] = False

    try:
        config = json.loads(read(files["configuration"]))
        checks["configuration_contract_current"] = config.get("contract_version") == "leos.employee-lifecycle-policy.v1"
        checks["configuration_fail_closed"] = config.get("fail_closed") is True
        checks["configuration_pre_resource_admission"] = config.get("mandatory_before_resource_admission") is True
        checks["configuration_pre_running"] = config.get("mandatory_before_running") is True
        checks["configuration_resource_sync"] = config.get("resource_profile_sync_required_for_activation") is True
        checks["configuration_no_docker_socket"] = config.get("docker_socket_mount_allowed") is False
        checks["configuration_no_production_network"] = config.get("production_network_attachment_allowed") is False
        checks["configuration_no_production_state"] = config.get("production_state_write_allowed_during_acceptance") is False
    except Exception as exc:
        errors.append(f"configuration:{exc}")
        for key in (
            "configuration_contract_current",
            "configuration_fail_closed",
            "configuration_pre_resource_admission",
            "configuration_pre_running",
            "configuration_resource_sync",
            "configuration_no_docker_socket",
            "configuration_no_production_network",
            "configuration_no_production_state",
        ):
            checks[key] = False

    registry = texts.get("registry_app", "")
    engine = texts.get("lifecycle_engine", "")
    scheduler = texts.get("scheduler", "")
    assignment = texts.get("assignment", "")
    builder = texts.get("builder", "")

    for marker in (
        '@app.post("/employees")',
        '@app.post("/employees/validate")',
        '@app.post("/employees/{employee_id}/validate")',
        '@app.post("/employees/{employee_id}/activate")',
        '@app.post("/employees/{employee_id}/pause")',
        '@app.post("/employees/{employee_id}/resume")',
        '@app.post("/employees/{employee_id}/disable")',
        '@app.post("/employees/{employee_id}/archive")',
        '@app.patch("/employees/{employee_id}/assignments")',
        '@app.get("/employees/{employee_id}/status")',
        '@app.get("/employees/{employee_id}/history")',
        '@app.get("/employees/{employee_id}/eligibility")',
    ):
        checks[f"registry_route:{marker}"] = marker in registry

    for marker in (
        "CREATE TABLE IF NOT EXISTS employees",
        "CREATE TABLE IF NOT EXISTS employee_history",
        "legacy-json-imported",
        "Invalid employee lifecycle transition",
        "employee.assignments-updated",
        "employee-concurrency-limit-reached",
        "employee-outside-schedule",
        "resource_profile_payload",
    ):
        checks[f"engine_marker:{marker}"] = marker in engine

    for marker in (
        "EMPLOYEE_REGISTRY_URL",
        "EXECUTION_SCHEDULER_EMPLOYEE_LIFECYCLE_ENFORCEMENT",
        "leos.employee-execution-eligibility.v1",
        "queued_by_employee_policy",
        "rejected_by_employee_policy",
        "Job cannot start because the employee is not eligible",
    ):
        checks[f"scheduler_marker:{marker}"] = marker in scheduler

    checks["assignment_uses_eligibility"] = "/eligibility" in assignment
    checks["assignment_updates_operational_status"] = "operational_status" in assignment
    checks["builder_uses_canonical_create"] = 'f"{EMPLOYEE_REGISTRY_URL}/employees"' in builder
    checks["builder_validates_employee"] = "/validate" in builder
    checks["builder_activates_employee"] = "/activate" in builder

    try:
        catalog = json.loads(read(files["catalog"]))
        services = {item.get("service_id"): item for item in catalog.get("services", [])}
        registry_record = services.get("employee-registry", {})
        scheduler_record = services.get("execution-scheduler-service", {})
        checks["catalog_employee_registry_present"] = bool(registry_record)
        checks["catalog_employee_contract_v2"] = registry_record.get("contract_version") == "leos.employee-definition.v2"
        checks["catalog_scheduler_depends_on_registry"] = "employee-registry" in scheduler_record.get("dependencies", [])
        checks["catalog_scheduler_lifecycle_capability"] = "employee-lifecycle.enforce" in scheduler_record.get("capabilities", [])
    except Exception as exc:
        errors.append(f"catalog:{exc}")
        checks["catalog_employee_registry_present"] = False
        checks["catalog_employee_contract_v2"] = False
        checks["catalog_scheduler_depends_on_registry"] = False
        checks["catalog_scheduler_lifecycle_capability"] = False

    for name, value in checks.items():
        if not value and not any(error.startswith(name) for error in errors):
            errors.append(name)

    result: dict[str, Any] = {
        "ok": not errors,
        "phase": "52.2",
        "contract_version": "leos.phase52.2-employee-lifecycle-validation.v1",
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
        "files": {name: str(path) for name, path in files.items()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
