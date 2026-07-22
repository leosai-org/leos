#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/security-observability.json"
DEFAULT_SERVICE_CATALOG = ROOT / "config/operator-service-catalog.json"
SOURCE_RELEASE = "0.1.0-dev-preview-rc9"
SOURCE_TREE = "64ba7c60c8c4e18ac9349edaa7ac96a7ae52242f8eba06e4d99b298cd3d2c7da"

CONTRACT_SECURITY = "leos.security-baseline-report.v1"
CONTRACT_SECRET = "leos.secret-exposure-report.v1"
CONTRACT_NETWORK = "leos.network-exposure-report.v1"
CONTRACT_HEALTH = "leos.health-aggregate.v1"
CONTRACT_METRICS = "leos.metrics-snapshot.v1"
CONTRACT_LOG = "leos.structured-log-record.v1"
CONTRACT_DIAGNOSTICS = "leos.diagnostics-bundle-manifest.v1"
CONTRACT_READINESS = "leos.observability-readiness.v1"
CONTRACT_RESULT = "leos.security-observability-result.v1"

SECRET_KEYS = {
    "password",
    "password_hash",
    "secret",
    "secret_value",
    "api_key",
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
    "authorization",
}
SECRET_FILE_FRAGMENTS = (
    ".env",
    "secret",
    "credential",
    "private-key",
    "id_rsa",
)
TEXT_SECRET_PATTERNS = (
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("key-assignment", re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]{4,}")),
    ("private-key-marker", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
REDACTION_PATTERNS = tuple(pattern for _, pattern in TEXT_SECRET_PATTERNS)


class SecurityObservabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def stable_id(prefix: str, value: Any, length: int = 16) -> str:
    return f"{prefix}-{hashlib.sha256(canonical_json(value)).hexdigest()[:length]}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    temporary.write_bytes(canonical_json(value))
    temporary.chmod(mode)
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SecurityObservabilityError(f"Unable to read JSON: {path}") from exc


def load_object(path: Path, contract: str | None = None) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise SecurityObservabilityError(f"Expected JSON object: {path}")
    if contract and value.get("contract_version") != contract:
        raise SecurityObservabilityError(f"Unexpected contract in {path}")
    return value


def safe_target(value: str | Path) -> Path:
    target = Path(value).expanduser().resolve()
    blocked = {
        "",
        ".",
        "..",
        "bin",
        "boot",
        "dev",
        "etc",
        "home",
        "lib",
        "lib64",
        "proc",
        "root",
        "run",
        "sbin",
        "sys",
        "usr",
        "var",
    }
    if len(target.parts) < 3 or target.name.lower() in blocked:
        raise SecurityObservabilityError(f"Unsafe target root: {target}")
    return target


def portable_output(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SecurityObservabilityError(
            "Diagnostics output must be a portable relative path."
        )
    return path


def safety(read_only: bool = True) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "plaintext_secret_exposed": False,
        "secret_material_copied": False,
        "production_state_accessed": False,
        "production_network_attached": False,
    }


def load_fixture(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    value = load_object(Path(path))
    if value.get("contract_version") != "leos.security-observability-fixture.v1":
        raise SecurityObservabilityError("Unsupported security fixture contract.")
    return value


def iter_bounded_files(
    target: Path,
    roots: Iterable[str],
    *,
    allowed_suffixes: set[str],
    max_files: int,
    max_file_bytes: int,
) -> tuple[list[Path], list[dict[str, Any]]]:
    selected: list[Path] = []
    skipped: list[dict[str, Any]] = []
    for relative_root in roots:
        root = target / relative_root
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(root.rglob("*"))
        for path in candidates:
            if len(selected) >= max_files:
                skipped.append({"path": relative_root, "reason": "file-limit"})
                return selected, skipped
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(target).as_posix()
            lowered = path.name.lower()
            if any(fragment in lowered for fragment in SECRET_FILE_FRAGMENTS):
                skipped.append({"path": relative, "reason": "secret-material-name"})
                continue
            if path.suffix.lower() not in allowed_suffixes:
                skipped.append({"path": relative, "reason": "suffix-not-allowed"})
                continue
            size = path.stat().st_size
            if size > max_file_bytes:
                skipped.append({"path": relative, "reason": "file-too-large"})
                continue
            selected.append(path)
    return selected, skipped


def secret_findings_from_json(value: Any, pointer: str = "") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{str(key).replace('~', '~0').replace('/', '~1')}"
            if str(key).lower() in SECRET_KEYS and child not in (None, "", [], {}):
                findings.append(
                    {
                        "pattern_id": "forbidden-secret-key",
                        "location": child_pointer,
                        "severity": "fail",
                        "value_redacted": True,
                    }
                )
            findings.extend(secret_findings_from_json(child, child_pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(secret_findings_from_json(child, f"{pointer}/{index}"))
    return findings


def secret_exposure_report(
    target: Path,
    config: dict[str, Any],
    fixture: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    scan = config["secret_scan"]
    files, skipped = iter_bounded_files(
        target,
        scan["roots"],
        allowed_suffixes=set(scan["allowed_suffixes"]),
        max_files=int(scan["max_files"]),
        max_file_bytes=int(scan["max_file_bytes"]),
    )
    findings: list[dict[str, Any]] = []
    scanned_bytes = 0
    for path in files:
        relative = path.relative_to(target).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        scanned_bytes += len(content.encode("utf-8"))
        if path.suffix.lower() == ".json":
            try:
                value = json.loads(content)
            except json.JSONDecodeError:
                findings.append(
                    {
                        "path": relative,
                        "pattern_id": "invalid-json",
                        "location": None,
                        "line": None,
                        "severity": "warn",
                        "value_redacted": True,
                    }
                )
            else:
                for item in secret_findings_from_json(value):
                    findings.append({"path": relative, "line": None, **item})
        for line_number, line in enumerate(content.splitlines(), 1):
            for pattern_id, pattern in TEXT_SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "path": relative,
                            "pattern_id": pattern_id,
                            "location": None,
                            "line": line_number,
                            "severity": "fail",
                            "value_redacted": True,
                        }
                    )
    for injected in fixture.get("secret_findings", []):
        findings.append(
            {
                "path": str(injected.get("path", "fixture")),
                "pattern_id": str(injected.get("pattern_id", "fixture-secret")),
                "location": injected.get("location"),
                "line": injected.get("line"),
                "severity": str(injected.get("severity", "fail")),
                "value_redacted": True,
            }
        )
    fail_count = sum(1 for item in findings if item["severity"] == "fail")
    warn_count = sum(1 for item in findings if item["severity"] == "warn")
    status = "fail" if fail_count else "warn" if warn_count else "pass"
    body = {
        "target_root": target.as_posix(),
        "files_scanned": len(files),
        "findings": findings,
    }
    return {
        "contract_version": CONTRACT_SECRET,
        "report_id": stable_id("secret-report", body),
        "status": status,
        "target_root": target.as_posix(),
        "files_scanned": len(files),
        "bytes_scanned": scanned_bytes,
        "skipped": skipped,
        "findings": findings,
        "counts": {
            "total": len(findings),
            "fail": fail_count,
            "warn": warn_count,
        },
        "plaintext_secret_exposed": False,
        "generated_at": now,
        "safety": safety(True),
    }


def network_exposure_report(
    catalog: dict[str, Any],
    fixture: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    fixture_services = fixture.get("services", {})
    services: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for spec in catalog.get("services", []):
        observed = fixture_services.get(spec["service_id"], {})
        bindings = list(observed.get("bindings", []))
        services.append(
            {
                "service_id": spec["service_id"],
                "required": bool(spec.get("required")),
                "bindings": bindings,
            }
        )
        for binding in bindings:
            text = str(binding)
            if text.startswith(("0.0.0.0:", ":::")):
                findings.append(
                    {
                        "service_id": spec["service_id"],
                        "binding": text,
                        "exposure": "public",
                        "severity": "fail" if spec.get("required") else "warn",
                    }
                )
    public_count = len(findings)
    fail_count = sum(1 for item in findings if item["severity"] == "fail")
    status = "fail" if fail_count else "warn" if public_count else "pass"
    body = {"services": services, "findings": findings}
    return {
        "contract_version": CONTRACT_NETWORK,
        "report_id": stable_id("network-report", body),
        "status": status,
        "services": services,
        "findings": findings,
        "counts": {
            "services": len(services),
            "public_bindings": public_count,
            "fail": fail_count,
            "warn": public_count - fail_count,
        },
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "generated_at": now,
        "safety": safety(True),
    }


def health_aggregate(
    catalog: dict[str, Any],
    fixture: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    fixture_services = fixture.get("services", {})
    services: list[dict[str, Any]] = []
    for spec in catalog.get("services", []):
        observed = fixture_services.get(spec["service_id"], {})
        state = str(observed.get("state", "unknown"))
        health = str(observed.get("health", "unknown"))
        services.append(
            {
                "service_id": spec["service_id"],
                "display_name": spec.get("display_name", spec["service_id"]),
                "required": bool(spec.get("required")),
                "state": state,
                "health": health,
                "latency_ms": observed.get("latency_ms"),
                "source": "fixture" if fixture_services else "catalog",
            }
        )
    healthy = sum(1 for item in services if item["health"] == "healthy")
    unhealthy = sum(1 for item in services if item["health"] == "unhealthy")
    unknown = len(services) - healthy - unhealthy
    required_unhealthy = sum(
        1
        for item in services
        if item["required"] and item["health"] != "healthy"
    )
    status = "fail" if required_unhealthy else "warn" if unhealthy or unknown else "pass"
    body = {"services": services, "status": status}
    return {
        "contract_version": CONTRACT_HEALTH,
        "aggregate_id": stable_id("health", body),
        "status": status,
        "services": services,
        "summary": {
            "total": len(services),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "unknown": unknown,
            "required_unhealthy": required_unhealthy,
        },
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "generated_at": now,
        "safety": safety(True),
    }


def safe_local_metrics(target: Path) -> dict[str, Any]:
    cpu_count = os.cpu_count()
    load = None
    try:
        load = list(os.getloadavg())
    except OSError:
        pass
    memory_total_mb = None
    memory_available_mb = None
    meminfo = Path(os.sep) / "proc" / "meminfo"
    if meminfo.is_file():
        parsed: dict[str, int] = {}
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            token = raw.strip().split()[0]
            if token.isdigit():
                parsed[key] = int(token)
        if "MemTotal" in parsed:
            memory_total_mb = round(parsed["MemTotal"] / 1024, 2)
        if "MemAvailable" in parsed:
            memory_available_mb = round(parsed["MemAvailable"] / 1024, 2)
    disk = shutil.disk_usage(target if target.exists() else target.parent)
    return {
        "cpu_cores": cpu_count,
        "load_average": load,
        "memory_total_mb": memory_total_mb,
        "memory_available_mb": memory_available_mb,
        "storage_total_gb": round(disk.total / (1024**3), 2),
        "storage_free_gb": round(disk.free / (1024**3), 2),
        "nvidia_gpu_count": None,
        "nvidia_vram_total_mb": None,
    }


def metrics_snapshot(
    target: Path,
    fixture: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    metrics = dict(fixture.get("metrics", {})) or safe_local_metrics(target)
    body = {"target_root": target.as_posix(), "metrics": metrics}
    return {
        "contract_version": CONTRACT_METRICS,
        "snapshot_id": stable_id("metrics", body),
        "target_root": target.as_posix(),
        "metrics": metrics,
        "source": "fixture" if fixture.get("metrics") else "local-read-only",
        "generated_at": now,
        "safety": safety(True),
    }


def file_mode_checks(target: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    private_max = int(config["security"]["private_file_mode_max"], 8)
    for relative in config["security"]["private_files"]:
        path = target / relative
        exists = path.is_file()
        actual_mode = stat.S_IMODE(path.stat().st_mode) if exists else None
        ok = exists and actual_mode is not None and (actual_mode & ~private_max) == 0
        checks.append(
            {
                "check_id": "private-mode-" + relative.replace("/", "-"),
                "domain": "filesystem-permissions",
                "status": "pass" if ok else "fail",
                "message": "Private file exists with bounded permissions.",
                "path": relative,
                "actual_mode": oct(actual_mode) if actual_mode is not None else None,
                "expected_mode_max": oct(private_max),
                "remediation": None if ok else "Restore the file and restrict group/other permissions.",
            }
        )
    return checks


def security_baseline_report(
    target: Path,
    config: dict[str, Any],
    catalog: dict[str, Any],
    fixture: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    secret = secret_exposure_report(target, config, fixture, now)
    network = network_exposure_report(catalog, fixture, now)
    checks = file_mode_checks(target, config)
    manifest_path = target / "state/installation-manifest.json"
    manifest = load_object(manifest_path) if manifest_path.is_file() else {}
    checks.extend(
        [
            {
                "check_id": "release-source",
                "domain": "release-integrity",
                "status": "pass" if manifest.get("source_release") == SOURCE_RELEASE else "fail",
                "message": "Installation source release matches RC9.",
                "path": "state/installation-manifest.json",
                "actual_mode": None,
                "expected_mode_max": None,
                "remediation": None if manifest.get("source_release") == SOURCE_RELEASE else "Restore the governed installation manifest.",
            },
            {
                "check_id": "release-tree",
                "domain": "release-integrity",
                "status": "pass" if manifest.get("source_tree_sha256") == SOURCE_TREE else "fail",
                "message": "Installation source tree matches the immutable RC9 tree.",
                "path": "state/installation-manifest.json",
                "actual_mode": None,
                "expected_mode_max": None,
                "remediation": None if manifest.get("source_tree_sha256") == SOURCE_TREE else "Reinstall from the exact RC9 source tree.",
            },
            {
                "check_id": "secret-exposure",
                "domain": "secret-exposure",
                "status": secret["status"],
                "message": "No plaintext secret indicators were emitted or persisted.",
                "path": None,
                "actual_mode": None,
                "expected_mode_max": None,
                "remediation": None if secret["status"] == "pass" else "Remove plaintext secret material and rotate affected credentials.",
            },
            {
                "check_id": "network-exposure",
                "domain": "network-exposure",
                "status": network["status"],
                "message": "Required services are not publicly bound.",
                "path": None,
                "actual_mode": None,
                "expected_mode_max": None,
                "remediation": None if network["status"] == "pass" else "Bind services to loopback or a governed private interface.",
            },
            {
                "check_id": "runtime-hardening",
                "domain": "runtime-hardening",
                "status": "pass" if fixture.get("runtime", {}).get("privileged") is not True else "fail",
                "message": "No privileged runtime mode is declared.",
                "path": None,
                "actual_mode": None,
                "expected_mode_max": None,
                "remediation": None if fixture.get("runtime", {}).get("privileged") is not True else "Disable privileged runtime execution.",
            },
        ]
    )
    fail = sum(1 for item in checks if item["status"] == "fail")
    warn = sum(1 for item in checks if item["status"] == "warn")
    status = "fail" if fail else "warn" if warn else "pass"
    body = {"target_root": target.as_posix(), "checks": checks}
    return {
        "contract_version": CONTRACT_SECURITY,
        "report_id": stable_id("security", body),
        "status": status,
        "target_root": target.as_posix(),
        "source_release": SOURCE_RELEASE,
        "source_tree_sha256": SOURCE_TREE,
        "checks": checks,
        "counts": {
            "total": len(checks),
            "pass": len(checks) - fail - warn,
            "warn": warn,
            "fail": fail,
        },
        "component_reports": {
            "secret_exposure_report_id": secret["report_id"],
            "network_exposure_report_id": network["report_id"],
        },
        "repair_requires_confirmation": True,
        "generated_at": now,
        "safety": safety(True),
    }


def redact_text(value: str) -> tuple[str, int]:
    redacted = value
    count = 0
    for pattern in REDACTION_PATTERNS:
        redacted, replaced = pattern.subn("[REDACTED]", redacted)
        count += replaced
    return redacted, count


def structured_log_record(
    service_id: str,
    level: str,
    message: str,
    attributes: dict[str, Any],
    correlation_id: str | None,
    now: str,
) -> dict[str, Any]:
    clean_message, message_redactions = redact_text(message)
    clean_attributes: dict[str, Any] = {}
    attribute_redactions = 0
    for key, value in sorted(attributes.items()):
        if key.lower() in SECRET_KEYS:
            clean_attributes[key] = "[REDACTED]"
            attribute_redactions += 1
        elif isinstance(value, str):
            clean_attributes[key], replaced = redact_text(value)
            attribute_redactions += replaced
        else:
            clean_attributes[key] = value
    basis = {
        "service_id": service_id,
        "level": level,
        "message": clean_message,
        "attributes": clean_attributes,
        "timestamp": now,
    }
    return {
        "contract_version": CONTRACT_LOG,
        "record_id": stable_id("log", basis),
        "timestamp": now,
        "service_id": service_id,
        "level": level,
        "message": clean_message,
        "attributes": clean_attributes,
        "correlation_id": correlation_id or stable_id("correlation", basis),
        "redaction_count": message_redactions + attribute_redactions,
        "plaintext_secret_exposed": False,
    }


def observability_readiness(
    security: dict[str, Any],
    health: dict[str, Any],
    metrics: dict[str, Any],
    config: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    free_gb = metrics.get("metrics", {}).get("storage_free_gb")
    storage_ok = free_gb is None or float(free_gb) >= float(config["observability"]["minimum_free_storage_gb"])
    checks = [
        {"check_id": "security-baseline", "ok": security["status"] != "fail", "status": security["status"]},
        {"check_id": "required-service-health", "ok": health["summary"]["required_unhealthy"] == 0, "status": health["status"]},
        {"check_id": "diagnostic-storage", "ok": storage_ok, "status": "pass" if storage_ok else "fail"},
        {"check_id": "bounded-diagnostics", "ok": int(config["diagnostics"]["max_bundle_bytes"]) > 0, "status": "pass"},
        {"check_id": "secret-redaction", "ok": config["diagnostics"]["redaction_required"] is True, "status": "pass"},
    ]
    blockers = [item["check_id"] for item in checks if not item["ok"]]
    status = "ready" if not blockers else "blocked"
    body = {"checks": checks, "status": status}
    return {
        "contract_version": CONTRACT_READINESS,
        "readiness_id": stable_id("observability", body),
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "generated_at": now,
        "safety": safety(True),
    }


def diagnostic_candidates(target: Path, config: dict[str, Any]) -> tuple[list[Path], list[dict[str, Any]]]:
    diagnostics = config["diagnostics"]
    return iter_bounded_files(
        target,
        diagnostics["roots"],
        allowed_suffixes=set(diagnostics["allowed_suffixes"]),
        max_files=int(diagnostics["max_files"]),
        max_file_bytes=int(diagnostics["max_file_bytes"]),
    )


def diagnostics_plan(
    target: Path,
    config: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    now: str,
) -> dict[str, Any]:
    candidates, skipped = diagnostic_candidates(target, config)
    entries = [
        {
            "source_path": path.relative_to(target).as_posix(),
            "bundle_path": f"logs/{path.relative_to(target).as_posix()}",
            "source_size_bytes": path.stat().st_size,
            "redaction_required": True,
        }
        for path in candidates
    ]
    report_entries = [
        {
            "source_path": None,
            "bundle_path": f"reports/{name}.json",
            "source_size_bytes": len(canonical_json(value)),
            "redaction_required": False,
        }
        for name, value in sorted(reports.items())
    ]
    body = {
        "target_root": target.as_posix(),
        "entries": entries + report_entries,
        "limits": config["diagnostics"],
    }
    bundle_id = stable_id("diagnostics", body)
    return {
        "contract_version": CONTRACT_DIAGNOSTICS,
        "bundle_id": bundle_id,
        "target_root": target.as_posix(),
        "status": "planned",
        "entries": entries + report_entries,
        "skipped": skipped,
        "limits": {
            "max_files": int(config["diagnostics"]["max_files"]),
            "max_file_bytes": int(config["diagnostics"]["max_file_bytes"]),
            "max_bundle_bytes": int(config["diagnostics"]["max_bundle_bytes"]),
            "max_log_lines": int(config["diagnostics"]["max_log_lines"]),
        },
        "requires_confirmation": True,
        "confirmation_token": stable_id("diagnostics-confirm", body),
        "execution_authorized": False,
        "redaction_required": True,
        "plaintext_secret_exposed": False,
        "secret_material_copied": False,
        "generated_at": now,
        "safety": safety(True),
    }


def deterministic_zip(directory: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            info = zipfile.ZipInfo(relative)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IMODE(path.stat().st_mode) & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())


def export_diagnostics(
    target: Path,
    config: dict[str, Any],
    plan: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    output_relative: str,
    confirmation: str | None,
    now: str,
) -> dict[str, Any]:
    if confirmation != plan["confirmation_token"]:
        raise SecurityObservabilityError("Diagnostics confirmation token mismatch.")
    relative = portable_output(output_relative)
    output = target / relative
    if output.suffix.lower() != ".zip":
        raise SecurityObservabilityError("Diagnostics output must end in .zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SecurityObservabilityError(f"Diagnostics output already exists: {output}")

    with tempfile.TemporaryDirectory(prefix="leos-diagnostics-") as temporary:
        bundle = Path(temporary) / "bundle"
        bundle.mkdir()
        total = 0
        exported: list[dict[str, Any]] = []
        redactions = 0
        max_bundle = int(config["diagnostics"]["max_bundle_bytes"])
        max_lines = int(config["diagnostics"]["max_log_lines"])

        for name, value in sorted(reports.items()):
            path = bundle / "reports" / f"{name}.json"
            write_json(path, value)
            size = path.stat().st_size
            total += size
            exported.append(
                {
                    "bundle_path": path.relative_to(bundle).as_posix(),
                    "size_bytes": size,
                    "sha256": sha256_file(path),
                    "redaction_count": 0,
                }
            )

        candidates, _ = diagnostic_candidates(target, config)
        for source in candidates:
            relative_source = source.relative_to(target).as_posix()
            raw_lines = source.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines]
            clean_lines: list[str] = []
            file_redactions = 0
            for line in raw_lines:
                clean, count = redact_text(line)
                clean_lines.append(clean)
                file_redactions += count
            content = ("\n".join(clean_lines) + ("\n" if clean_lines else "")).encode("utf-8")
            if total + len(content) > max_bundle:
                continue
            destination = bundle / "logs" / relative_source
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destination.chmod(0o600)
            total += len(content)
            redactions += file_redactions
            exported.append(
                {
                    "bundle_path": destination.relative_to(bundle).as_posix(),
                    "size_bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "redaction_count": file_redactions,
                }
            )

        manifest = {
            **plan,
            "status": "exported",
            "entries": exported,
            "total_bytes": total,
            "redaction_count": redactions,
            "execution_authorized": True,
            "archive_path": relative.as_posix(),
            "archive_sha256": None,
            "generated_at": now,
            "safety": safety(False),
        }
        write_json(bundle / "manifest.json", manifest)
        temporary_zip = output.parent / f".{output.name}.tmp-{os.getpid()}"
        deterministic_zip(bundle, temporary_zip)
        if temporary_zip.stat().st_size > max_bundle:
            temporary_zip.unlink()
            raise SecurityObservabilityError("Diagnostics bundle exceeds configured size limit.")
        archive_sha = sha256_file(temporary_zip)
        os.replace(temporary_zip, output)

    return {
        **manifest,
        "archive_sha256": archive_sha,
        "archive_size_bytes": output.stat().st_size,
        "plaintext_secret_exposed": False,
        "secret_material_copied": False,
    }


def build_reports(
    target: Path,
    config: dict[str, Any],
    catalog: dict[str, Any],
    fixture: dict[str, Any],
    now: str,
) -> dict[str, dict[str, Any]]:
    secret = secret_exposure_report(target, config, fixture, now)
    network = network_exposure_report(catalog, fixture, now)
    health = health_aggregate(catalog, fixture, now)
    metrics = metrics_snapshot(target, fixture, now)
    security = security_baseline_report(target, config, catalog, fixture, now)
    readiness = observability_readiness(security, health, metrics, config, now)
    return {
        "security-baseline": security,
        "secret-exposure": secret,
        "network-exposure": network,
        "health-aggregate": health,
        "metrics-snapshot": metrics,
        "observability-readiness": readiness,
    }


def result(command: str, payload: dict[str, Any], now: str, read_only: bool) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_RESULT,
        "command": command,
        "ok": True,
        "generated_at": now,
        "payload_contract": payload.get("contract_version", "leos.unknown.v1"),
        "payload": payload,
        "safety": safety(read_only),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LEOS security and observability baseline")
    parser.add_argument("--target-root", default=os.environ.get("LEOS_TARGET_ROOT", "leos-installation"))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--service-catalog", default=str(DEFAULT_SERVICE_CATALOG))
    parser.add_argument("--fixture")
    parser.add_argument("--now")
    parser.add_argument("--output")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("security")
    sub.add_parser("secrets")
    sub.add_parser("network")
    sub.add_parser("health")
    sub.add_parser("metrics")
    sub.add_parser("readiness")
    log_parser = sub.add_parser("log")
    log_parser.add_argument("--service-id", required=True)
    log_parser.add_argument("--level", default="info", choices=["debug", "info", "warning", "error", "critical"])
    log_parser.add_argument("--message", required=True)
    log_parser.add_argument("--attributes-json", default="{}")
    log_parser.add_argument("--correlation-id")
    diag = sub.add_parser("diagnostics")
    diag.add_argument("--export", action="store_true")
    diag.add_argument("--output-relative", default="diagnostics/leos-diagnostics.zip")
    diag.add_argument("--confirm")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = args.now or utc_now()
    target = safe_target(args.target_root)
    config = load_object(Path(args.config), "leos.security-observability-config.v1")
    catalog = load_object(Path(args.service_catalog), "leos.operator-service-catalog.v1")
    fixture = load_fixture(args.fixture)
    reports = build_reports(target, config, catalog, fixture, now)

    if args.command == "security":
        payload = reports["security-baseline"]
        read_only = True
    elif args.command == "secrets":
        payload = reports["secret-exposure"]
        read_only = True
    elif args.command == "network":
        payload = reports["network-exposure"]
        read_only = True
    elif args.command == "health":
        payload = reports["health-aggregate"]
        read_only = True
    elif args.command == "metrics":
        payload = reports["metrics-snapshot"]
        read_only = True
    elif args.command == "readiness":
        payload = reports["observability-readiness"]
        read_only = True
    elif args.command == "log":
        try:
            attributes = json.loads(args.attributes_json)
        except json.JSONDecodeError as exc:
            raise SecurityObservabilityError("Invalid attributes JSON.") from exc
        if not isinstance(attributes, dict):
            raise SecurityObservabilityError("Log attributes must be a JSON object.")
        payload = structured_log_record(
            args.service_id,
            args.level,
            args.message,
            attributes,
            args.correlation_id,
            now,
        )
        read_only = True
    elif args.command == "diagnostics":
        plan = diagnostics_plan(target, config, reports, now)
        if args.export:
            payload = export_diagnostics(
                target,
                config,
                plan,
                reports,
                args.output_relative,
                args.confirm,
                now,
            )
            read_only = False
        else:
            payload = plan
            read_only = True
    else:
        raise SecurityObservabilityError(f"Unsupported command: {args.command}")

    output = result(args.command, payload, now, read_only)
    text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SecurityObservabilityError as exc:
        output = {
            "contract_version": CONTRACT_RESULT,
            "command": "error",
            "ok": False,
            "generated_at": utc_now(),
            "payload_contract": "leos.security-observability-error.v1",
            "payload": {
                "contract_version": "leos.security-observability-error.v1",
                "error": str(exc),
            },
            "safety": safety(True),
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        raise SystemExit(2)
