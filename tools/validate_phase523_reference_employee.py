#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

EMPLOYEE_ID = "research-content-employee"
SERVICE_ID = "reference-research-content-employee"
RUN_CONTRACT = "leos.reference-research-content-run.v1"
SOURCE_CONTRACT = "leos.research-source.v1"
ARTIFACT_CONTRACT = "leos.research-content-artifact.v1"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(read(path))


def route_set(tree: ast.AST) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                result.add((decorator.func.attr.upper(), str(decorator.args[0].value)))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=os.environ.get("LEOS_ROOT", str(Path.cwd())),
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    paths = {
        "app": root / SERVICE_ID / "app.py",
        "engine": root / SERVICE_ID / "engine.py",
        "dockerfile": root / SERVICE_ID / "Dockerfile",
        "requirements": root / SERVICE_ID / "requirements.txt",
        "service_definition": root / SERVICE_ID / "service-definition.json",
        "readme": root / SERVICE_ID / "README.md",
        "tests": root / SERVICE_ID / "tests" / "test_engine.py",
        "employee_definition": root / "config" / "reference-research-content-employee.json",
        "catalog": root / "config" / "service-catalog.json",
        "run_contract": root / "contracts" / "reference-research-content-run.v1.schema.json",
        "source_contract": root / "contracts" / "research-source.v1.schema.json",
        "artifact_contract": root / "contracts" / "research-content-artifact.v1.schema.json",
        "template": root / "employee-builder" / "templates" / "research-content.yaml",
        "documentation": root / "docs" / "phase52.3-reference-research-content-employee.md",
        "compose": root / "deploy" / "reference-research-content-employee.compose.yml",
        "release_compose": root / "deploy" / "reference-research-content-employee.release.compose.yml",
        "example": root / "examples" / "reference-research-content-request.json",
        "bootstrap": root / "tools" / "bootstrap_reference_research_content_employee.py",
    }

    checks: dict[str, bool] = {
        f"file:{name}": path.is_file() for name, path in paths.items()
    }
    errors: list[str] = []

    for name in ("app", "engine", "tests", "bootstrap"):
        path = paths[name]
        if path.is_file():
            try:
                ast.parse(read(path), filename=str(path))
                checks[f"ast:{name}"] = True
            except SyntaxError as exc:
                checks[f"ast:{name}"] = False
                errors.append(f"Python syntax error in {path}: {exc}")

    json_values: dict[str, Any] = {}
    for name in (
        "service_definition",
        "employee_definition",
        "catalog",
        "run_contract",
        "source_contract",
        "artifact_contract",
        "example",
    ):
        path = paths[name]
        if not path.is_file():
            continue
        try:
            json_values[name] = load_json(path)
            checks[f"json:{name}"] = True
        except Exception as exc:
            checks[f"json:{name}"] = False
            errors.append(f"Invalid JSON in {path}: {exc}")

    requirements_text = read(paths["requirements"]) if paths["requirements"].is_file() else ""
    requirement_lines = [
        line.strip()
        for line in requirements_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    expected_requirement_lines = [
        "fastapi==0.116.1",
        "uvicorn[standard]==0.35.0",
        "pydantic==2.13.4",
    ]
    checks.update({
        "requirements_fastapi_0_116_1": "fastapi==0.116.1" in requirement_lines,
        "requirements_uvicorn_standard_0_35_0": "uvicorn[standard]==0.35.0" in requirement_lines,
        "requirements_pydantic_2_13_4": "pydantic==2.13.4" in requirement_lines,
        "requirements_exact_runtime_dependency_set": requirement_lines == expected_requirement_lines,
    })

    employee = json_values.get("employee_definition", {})
    checks.update({
        "employee_contract_v2": employee.get("contract_version") == "leos.employee-definition.v2",
        "employee_id_current": employee.get("employee_id") == EMPLOYEE_ID,
        "employee_role_present": bool(employee.get("role")),
        "employee_department_present": bool(employee.get("department")),
        "employee_priority_normal": employee.get("priority") == "normal",
        "employee_schedule_always_utc": (
            employee.get("schedule", {}).get("mode") == "always"
            and employee.get("schedule", {}).get("timezone") == "UTC"
            and employee.get("schedule", {}).get("windows") == []
        ),
        "employee_resource_profile_present": isinstance(employee.get("resource_profile"), dict),
        "employee_model_preferences_present": bool(employee.get("model_preferences")),
        "employee_internet_disabled": employee.get("permissions", {}).get("internet") is False,
        "employee_reference_metadata": employee.get("metadata", {}).get("reference_implementation") is True,
        "employee_review_required": employee.get("metadata", {}).get("independent_review_required") is True,
        "employee_human_publish_approval_required": (
            employee.get("metadata", {}).get("human_approval_required_before_external_publication") is True
        ),
    })

    required_capabilities = {
        "research.plan",
        "research.sources",
        "research.extract",
        "content.outline",
        "content.draft",
        "content.review.request",
        "content.revise",
        "artifact.persist",
        "artifact.history",
        "execution.history",
    }
    employee_capabilities = set(employee.get("capabilities", []))
    checks["employee_capabilities_complete"] = required_capabilities <= employee_capabilities

    service_definition = json_values.get("service_definition", {})
    checks.update({
        "service_id_current": service_definition.get("service_id") == SERVICE_ID,
        "service_contract_current": service_definition.get("contract_version") == RUN_CONTRACT,
        "service_employee_id_current": service_definition.get("employee_id") == EMPLOYEE_ID,
        "service_capabilities_complete": required_capabilities <= set(service_definition.get("capabilities", [])),
        "service_depends_on_registry": "employee-registry" in service_definition.get("dependencies", []),
        "service_depends_on_scheduler": "execution-scheduler-service" in service_definition.get("dependencies", []),
        "service_depends_on_resource_authority": "employee-resource-profile-service" in service_definition.get("dependencies", []),
        "service_depends_on_persistence": "leos-persistence-service" in service_definition.get("dependencies", []),
        "service_depends_on_review": "content-review-service" in service_definition.get("dependencies", []),
        "service_no_internet": service_definition.get("security", {}).get("internet_required") is False,
        "service_no_docker_socket": service_definition.get("security", {}).get("docker_socket_required") is False,
        "service_not_privileged": service_definition.get("security", {}).get("privileged") is False,
        "service_approved_adapter_only": service_definition.get("security", {}).get("approved_adapter_only") is True,
    })

    catalog = json_values.get("catalog", {})
    catalog_entries = [
        item for item in catalog.get("services", [])
        if isinstance(item, dict) and item.get("service_id") == SERVICE_ID
    ]
    checks["catalog_has_exactly_one_reference_employee"] = len(catalog_entries) == 1
    if len(catalog_entries) == 1:
        entry = catalog_entries[0]
        checks.update({
            "catalog_contract_current": entry.get("contract_version") == RUN_CONTRACT,
            "catalog_capabilities_complete": required_capabilities <= set(entry.get("capabilities", [])),
            "catalog_optional_reference_service": entry.get("required") is False,
            "catalog_health_current": entry.get("health_url") == f"http://{SERVICE_ID}:8000/health",
            "catalog_dependencies_complete": {
                "employee-registry",
                "execution-scheduler-service",
                "employee-resource-profile-service",
                "leos-persistence-service",
                "content-review-service",
            } <= set(entry.get("dependencies", [])),
        })

    contract_expectations = {
        "run_contract": (RUN_CONTRACT, ["run_id", "goal_id", "employee_id", "state", "governance"]),
        "source_contract": (SOURCE_CONTRACT, ["source_id", "run_id", "content_sha256", "provenance"]),
        "artifact_contract": (ARTIFACT_CONTRACT, ["artifact_id", "run_id", "goal_id", "employee_id", "content_sha256", "execution"]),
    }
    for name, (contract, required) in contract_expectations.items():
        value = json_values.get(name, {})
        checks[f"{name}_id_current"] = value.get("properties", {}).get("contract_version", {}).get("const") == contract
        checks[f"{name}_required_fields"] = set(required) <= set(value.get("required", []))

    app_text = read(paths["app"]) if paths["app"].is_file() else ""
    engine_text = read(paths["engine"]) if paths["engine"].is_file() else ""
    app_tree = ast.parse(app_text) if app_text else ast.Module(body=[], type_ignores=[])
    routes = route_set(app_tree)
    required_routes = {
        ("GET", "/health"),
        ("POST", "/runs"),
        ("GET", "/runs"),
        ("GET", "/runs/{run_id}"),
        ("POST", "/runs/{run_id}/execute"),
        ("POST", "/runs/{run_id}/pause"),
        ("POST", "/runs/{run_id}/resume"),
        ("POST", "/runs/{run_id}/cancel"),
        ("POST", "/runs/{run_id}/recover"),
        ("GET", "/runs/{run_id}/history"),
        ("GET", "/runs/{run_id}/sources"),
        ("GET", "/artifacts/{artifact_id}"),
        ("POST", "/execute"),
    }
    for method, route in sorted(required_routes):
        checks[f"route:{method}:{route}"] = (method, route) in routes

    engine_markers = (
        "CREATE TABLE IF NOT EXISTS runs",
        "CREATE TABLE IF NOT EXISTS run_events",
        "CREATE TABLE IF NOT EXISTS research_sources",
        "CREATE TABLE IF NOT EXISTS artifacts",
        "CREATE TABLE IF NOT EXISTS artifact_versions",
        "leos.employee-execution-eligibility.v1",
        "leos.resource-admission-decision.v1",
        "leos.resource-reservation.v1",
        "Source adapter is not approved",
        "At least one approved source is required",
        "Service restarted before run completion",
        "run.revision.started",
        "run.persistence.started",
        "run.complete",
        "human_review_required_before_external_publication",
    )
    for marker in engine_markers:
        checks[f"engine_marker:{marker}"] = marker in engine_text

    tests_text = read(paths["tests"]) if paths["tests"].is_file() else ""
    test_count = len(re.findall(r"^\s+def test_", tests_text, re.MULTILINE))
    checks["test_count_at_least_22"] = test_count >= 22
    for marker in (
        "test_ineligible_employee_is_rejected",
        "test_non_admitted_resource_decision_is_rejected",
        "test_inactive_reservation_is_rejected",
        "test_unapproved_source_adapter_is_rejected_fail_closed",
        "test_rejected_initial_draft_is_revised_and_approved",
        "test_restart_marks_inflight_run_interrupted",
        "test_recover_interrupted_run",
        "test_execution_lineage_records_governance_identifiers",
    ):
        checks[f"test_marker:{marker}"] = marker in tests_text

    docker_text = read(paths["dockerfile"]) if paths["dockerfile"].is_file() else ""
    compose_text = read(paths["compose"]) if paths["compose"].is_file() else ""
    release_compose_text = read(paths["release_compose"]) if paths["release_compose"].is_file() else ""
    socket_literal = "/" + "var/run/" + "docker" + ".sock"
    lucy_host_literal = "/" + "mnt" + "/nvme/"
    host_network_literal = "network_mode" + ": " + "host"
    checks.update({
        "docker_nonroot_user": "USER leos" in docker_text,
        "docker_no_socket": (
            socket_literal not in docker_text
            and socket_literal not in compose_text
        ),
        "compose_read_only": "read_only: true" in compose_text,
        "compose_cap_drop_all": "- ALL" in compose_text,
        "compose_no_new_privileges": "no-new-privileges:true" in compose_text,
        "compose_internal_service_network": "- ai-cloud-net" in compose_text,
        "compose_external_network_declared": (
            "ai-cloud-net:" in compose_text and "external: true" in compose_text
        ),
        "compose_no_host_network": host_network_literal not in compose_text,
        "compose_no_published_ports": "ports:" not in compose_text,
        "compose_named_volume": "reference-research-content-data:" in compose_text,
        "compose_live_context_current": "context: ../reference-research-content-employee" in compose_text,
        "release_compose_service_context_current": "context: ../services/reference-research-content-employee" in release_compose_text,
        "release_compose_image_current": "image: leos/reference-research-content-employee:0.1.0" in release_compose_text,
        "release_compose_read_only": "read_only: true" in release_compose_text,
        "release_compose_cap_drop_all": "- ALL" in release_compose_text,
        "release_compose_no_new_privileges": "no-new-privileges:true" in release_compose_text,
        "release_compose_internal_service_network": "- ai-cloud-net" in release_compose_text,
        "release_compose_external_network_declared": (
            "ai-cloud-net:" in release_compose_text and "external: true" in release_compose_text
        ),
        "release_compose_no_host_network": host_network_literal not in release_compose_text,
        "release_compose_no_published_ports": "ports:" not in release_compose_text,
        "source_has_no_lucy_host_path": lucy_host_literal not in "\n".join(
            read(path) for path in paths.values() if path.is_file()
        ),
    })

    # Validate the canonical definition with the installed RC8 lifecycle normalizer.
    lifecycle_path = root / "employee-registry" / "lifecycle_engine.py"
    checks["lifecycle_engine_present"] = lifecycle_path.is_file()
    if lifecycle_path.is_file() and employee:
        try:
            spec = importlib.util.spec_from_file_location("phase523_lifecycle", lifecycle_path)
            if spec is None or spec.loader is None:
                raise RuntimeError("Unable to load lifecycle engine.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            normalized = module.normalize_definition(employee)
            checks["canonical_definition_normalizes"] = normalized.get("employee_id") == EMPLOYEE_ID
            checks["canonical_resource_contract_current"] = normalized.get("resource_profile", {}).get("contract_version") == "leos.employee-resource-profile.v1"
            checks["canonical_schedule_current"] = normalized.get("schedule", {}).get("timezone") == "UTC"
            checks["canonical_concurrency_one"] = normalized.get("limits", {}).get("max_parallel_jobs") == 1
        except Exception as exc:
            checks["canonical_definition_normalizes"] = False
            errors.append(f"Canonical employee normalization failed: {exc}")

    failed = [name for name, passed in checks.items() if passed is not True]
    errors.extend(f"Validation check failed: {name}" for name in failed)
    result = {
        "ok": not errors,
        "phase": "52.3",
        "contract_version": "leos.phase52.3-reference-research-content-validation.v1",
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
        "test_count_detected": test_count,
        "route_count_detected": len(routes),
        "files": {name: str(path) for name, path in paths.items()},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
