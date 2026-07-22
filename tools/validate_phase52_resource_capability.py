from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "services/employee-resource-profile-service/app/resource_engine.py",
    "services/employee-resource-profile-service/app/main.py",
    "services/employee-resource-profile-service/Dockerfile",
    "services/employee-resource-profile-service/requirements.txt",
    "services/employee-resource-profile-service/service-definition.json",
    "services/employee-resource-profile-service/README.md",
    "contracts/employee-resource-profile.v1.schema.json",
    "contracts/compute-node-capacity.v1.schema.json",
    "contracts/resource-admission-decision.v1.schema.json",
    "contracts/resource-reservation.v1.schema.json",
    "config/employee-resource-profile-service.json",
    "docs/phase52-employee-resource-scheduling.md",
]
EXPECTED = {
    "employee-resource-profile.v1.schema.json": "leos.employee-resource-profile.v1",
    "compute-node-capacity.v1.schema.json": "leos.compute-node-capacity.v1",
    "resource-admission-decision.v1.schema.json": "leos.resource-admission-decision.v1",
    "resource-reservation.v1.schema.json": "leos.resource-reservation.v1",
}


def main() -> int:
    checks = {}
    errors = []

    for relative in REQUIRED:
        present = (ROOT / relative).is_file()
        checks[f"file:{relative}"] = present
        if not present:
            errors.append(f"Missing required file: {relative}")

    for relative in [
        "services/employee-resource-profile-service/app/resource_engine.py",
        "services/employee-resource-profile-service/app/main.py",
    ]:
        valid = False
        path = ROOT / relative
        if path.is_file():
            try:
                ast.parse(path.read_text(encoding="utf-8"))
                valid = True
            except SyntaxError as exc:
                errors.append(f"Python syntax error in {relative}: {exc}")
        checks[f"python-syntax:{relative}"] = valid

    for filename, contract in EXPECTED.items():
        valid = False
        path = ROOT / "contracts" / filename
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                valid = (
                    value.get("$schema")
                    == "https://json-schema.org/draft/2020-12/schema"
                    and contract in json.dumps(value)
                )
            except Exception as exc:
                errors.append(f"Invalid schema {filename}: {exc}")
        checks[f"schema:{filename}"] = valid

    definition = json.loads(
        (
            ROOT
            / "services"
            / "employee-resource-profile-service"
            / "service-definition.json"
        ).read_text(encoding="utf-8")
    )
    checks["service-definition"] = (
        definition.get("service_id")
        == "employee-resource-profile-service"
        and definition.get("port") == 8000
        and definition.get("isolation", {}).get("docker_socket_required")
        is False
        and definition.get("isolation", {}).get("production_network_required")
        is False
        and definition.get("isolation", {}).get("privileged") is False
    )

    scan_roots = [
        (
            ROOT
            / "services"
            / "employee-resource-profile-service"
        ),
        ROOT / "contracts",
        (
            ROOT
            / "config"
            / "employee-resource-profile-service.json"
        ),
        (
            ROOT
            / "docs"
            / "phase52-employee-resource-scheduling.md"
        ),
    ]

    scan_files = []

    for scan_root in scan_roots:
        if scan_root.is_file():
            scan_files.append(scan_root)
            continue

        if scan_root.is_dir():
            scan_files.extend(
                path
                for path in scan_root.rglob("*")
                if path.is_file()
                and path.stat().st_size < 2_000_000
            )

    source_text = "\n".join(
        path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        for path in sorted(
            set(scan_files),
            key=lambda item: item.as_posix(),
        )
    )
    forbidden = {
        "rc3": "0.1.0-dev-preview-" + "rc3",
        "docker-socket": "docker" + ".sock",
        "production-network": "ai-cloud" + "_default",
        "privileged": "privileged" + ": true",
    }
    for name, token in forbidden.items():
        absent = token not in source_text
        checks[f"forbidden:{name}"] = absent
        if not absent:
            errors.append(f"Forbidden token found: {token}")

    result = {
        "ok": not errors and all(checks.values()),
        "contract_version": "leos.phase52.resource-capability-validation.v1",
        "check_count": len(checks),
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
