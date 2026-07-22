#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INVENTORY_CONTRACT = "leos.host-capability-inventory.v1"
RECOMMENDATION_CONTRACT = "leos.installation-profile-recommendation.v1"
PLAN_CONTRACT = "leos.installation-plan.v1"
PROFILE_CATALOG_CONTRACT = "leos.installation-profile-catalog.v1"
COMPUTE_NODE_CONTRACT = "leos.compute-node-capacity.v1"

SUPPORTED_SYSTEMS = {"linux"}
SUPPORTED_ARCHITECTURES = {
    "x86_64",
    "amd64",
    "aarch64",
    "arm64",
}


class InstallationProfileError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InstallationProfileError(
            f"Unable to read JSON document: {path}"
        ) from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def nonnegative_int(value: Any, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise InstallationProfileError(
            f"{field} must be an integer."
        ) from exc
    if result < 0:
        raise InstallationProfileError(
            f"{field} must be non-negative."
        )
    return result


def positive_int(value: Any, field: str) -> int:
    result = nonnegative_int(value, field)
    if result < 1:
        raise InstallationProfileError(
            f"{field} must be at least 1."
        )
    return result


def text(value: Any, field: str, default: str = "") -> str:
    result = str(value if value is not None else default).strip()
    if not result and not default:
        raise InstallationProfileError(
            f"{field} must be a non-empty string."
        )
    return result or default


def normalize_architecture(value: str) -> str:
    lowered = value.strip().lower()
    aliases = {
        "x64": "x86_64",
        "x86-64": "x86_64",
        "arm64": "aarch64",
    }
    return aliases.get(lowered, lowered)


def command_result(
    command: list[str],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    try:
        process = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env={
                **os.environ,
                "LC_ALL": "C",
                "LANG": "C",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }

    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }


def parse_meminfo(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    if not path.is_file():
        return values
    for line in path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        match = re.search(r"(\d+)", raw)
        if match:
            values[key.strip()] = int(match.group(1))
    return values


def detect_cpu() -> dict[str, Any]:
    logical = os.cpu_count() or 1
    model = platform.processor().strip()
    flags: set[str] = set()
    physical_pairs: set[tuple[str, str]] = set()

    cpuinfo = Path(os.sep) / "proc" / "cpuinfo"
    if cpuinfo.is_file():
        blocks = cpuinfo.read_text(
            encoding="utf-8",
            errors="replace",
        ).split("\n\n")
        for block in blocks:
            fields: dict[str, str] = {}
            for line in block.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip().lower()] = value.strip()
            if not model:
                model = (
                    fields.get("model name")
                    or fields.get("hardware")
                    or fields.get("processor")
                    or ""
                )
            flag_value = fields.get("flags") or fields.get("features")
            if flag_value:
                flags.update(flag_value.split())
            physical_id = fields.get("physical id")
            core_id = fields.get("core id")
            if physical_id is not None and core_id is not None:
                physical_pairs.add((physical_id, core_id))

    physical = len(physical_pairs) if physical_pairs else logical
    return {
        "logical_cores": logical,
        "physical_cores": physical,
        "model": model or "unknown",
        "flags": sorted(flags),
    }


def detect_memory() -> dict[str, Any]:
    info = parse_meminfo(Path(os.sep) / "proc" / "meminfo")
    total_kib = info.get("MemTotal", 0)
    available_kib = info.get(
        "MemAvailable",
        info.get("MemFree", 0),
    )
    return {
        "total_mb": total_kib // 1024,
        "available_mb": available_kib // 1024,
    }


def detect_storage(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    try:
        usage = shutil.disk_usage(resolved)
    except OSError as exc:
        raise InstallationProfileError(
            f"Unable to inspect storage path {resolved}: {exc}"
        ) from exc

    divisor = 1024 ** 3
    return {
        "path": str(resolved),
        "total_gb": int(usage.total // divisor),
        "free_gb": int(usage.free // divisor),
    }


def runtime_probe(
    binary: str,
    *,
    contact_daemon: bool,
) -> dict[str, Any]:
    executable = shutil.which(binary)
    if not executable:
        return {
            "present": False,
            "binary": None,
            "version": None,
            "daemon_accessible": False,
            "daemon_probe_performed": False,
        }

    version_result = command_result([executable, "--version"])
    version = (
        version_result["stdout"]
        or version_result["stderr"]
        or "unknown"
    )

    daemon_accessible = False
    daemon_probe_performed = False
    if contact_daemon:
        daemon_probe_performed = True
        if binary == "docker":
            result = command_result(
                [executable, "info", "--format", "{{json .ServerVersion}}"],
                timeout=8.0,
            )
        else:
            result = command_result(
                [executable, "info", "--format", "json"],
                timeout=8.0,
            )
        daemon_accessible = result["ok"]

    return {
        "present": True,
        "binary": executable,
        "version": version,
        "daemon_accessible": daemon_accessible,
        "daemon_probe_performed": daemon_probe_performed,
    }


def parse_csv_line(value: str) -> list[str]:
    return [item.strip() for item in value.split(",")]


def detect_nvidia() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {
            "driver_present": False,
            "driver_version": None,
            "cuda_version": None,
            "gpus": [],
            "nvidia_container_runtime_present": (
                shutil.which("nvidia-container-runtime") is not None
            ),
        }

    query = command_result(
        [
            executable,
            "--query-gpu=index,uuid,name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=10.0,
    )
    gpus: list[dict[str, Any]] = []
    driver_version: str | None = None

    if query["ok"] and query["stdout"]:
        for line in query["stdout"].splitlines():
            fields = parse_csv_line(line)
            if len(fields) != 5:
                continue
            index, uuid, name, memory, driver = fields
            try:
                memory_mb = int(float(memory))
            except ValueError:
                memory_mb = 0
            driver_version = driver_version or driver
            gpus.append(
                {
                    "index": nonnegative_int(index, "gpu.index"),
                    "uuid": uuid,
                    "name": name,
                    "memory_mb": memory_mb,
                    "compute_capability": None,
                }
            )

    capability = command_result(
        [
            executable,
            "--query-gpu=index,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        timeout=10.0,
    )
    if capability["ok"]:
        capability_by_index = {}
        for line in capability["stdout"].splitlines():
            fields = parse_csv_line(line)
            if len(fields) == 2:
                capability_by_index[fields[0]] = fields[1]
        for gpu in gpus:
            gpu["compute_capability"] = capability_by_index.get(
                str(gpu["index"])
            )

    header = command_result([executable], timeout=10.0)
    cuda_version = None
    match = re.search(
        r"CUDA Version:\s*([0-9.]+)",
        header["stdout"],
    )
    if match:
        cuda_version = match.group(1)

    return {
        "driver_present": bool(gpus),
        "driver_version": driver_version,
        "cuda_version": cuda_version,
        "gpus": gpus,
        "nvidia_container_runtime_present": (
            shutil.which("nvidia-container-runtime") is not None
        ),
    }


def detect_network() -> dict[str, Any]:
    interface_root = Path(os.sep) / "sys" / "class" / "net"
    interfaces = []
    if interface_root.is_dir():
        for path in sorted(interface_root.iterdir()):
            name = path.name
            state_path = path / "operstate"
            state = (
                state_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).strip()
                if state_path.is_file()
                else "unknown"
            )
            interfaces.append(
                {
                    "name": name,
                    "state": state,
                    "loopback": name == "lo",
                }
            )

    default_route = False
    route_path = Path(os.sep) / "proc" / "net" / "route"
    if route_path.is_file():
        for line in route_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 4 and fields[1] == "00000000":
                default_route = True
                break

    return {
        "hostname": socket.gethostname(),
        "interfaces": interfaces,
        "default_route_present": default_route,
    }


def detect_privileges() -> dict[str, Any]:
    effective_uid = os.geteuid() if hasattr(os, "geteuid") else None
    group_names = []
    if hasattr(os, "getgroups"):
        for group_id in os.getgroups():
            try:
                group_names.append(grp.getgrgid(group_id).gr_name)
            except KeyError:
                group_names.append(str(group_id))
    return {
        "effective_uid": effective_uid,
        "is_root": effective_uid == 0 if effective_uid is not None else False,
        "groups": sorted(set(group_names)),
    }


def detect_runtime(
    *,
    contact_container_daemon: bool,
) -> dict[str, Any]:
    virtualization = None
    detector = shutil.which("systemd-detect-virt")
    if detector:
        result = command_result([detector], timeout=3.0)
        if result["stdout"] and result["stdout"] != "none":
            virtualization = result["stdout"]

    return {
        "python_version": platform.python_version(),
        "systemd_present": shutil.which("systemctl") is not None,
        "virtualization": virtualization,
        "docker": runtime_probe(
            "docker",
            contact_daemon=contact_container_daemon,
        ),
        "podman": runtime_probe(
            "podman",
            contact_daemon=contact_container_daemon,
        ),
    }


def fixture_inventory(
    fixture: dict[str, Any],
    *,
    node_id: str,
    storage_path: Path,
) -> dict[str, Any]:
    platform_value = dict(fixture.get("platform", {}))
    cpu = dict(fixture.get("cpu", {}))
    memory = dict(fixture.get("memory", {}))
    storage = dict(fixture.get("storage", {}))
    runtime = dict(fixture.get("runtime", {}))
    nvidia = dict(fixture.get("nvidia", {}))
    network = dict(fixture.get("network", {}))
    privileges = dict(fixture.get("privileges", {}))

    if not platform_value or not cpu or not memory or not storage:
        raise InstallationProfileError(
            "Fixture requires platform, cpu, memory, and storage."
        )

    docker = dict(runtime.get("docker", {}))
    podman = dict(runtime.get("podman", {}))

    normalized_gpus = []
    for index, raw_gpu in enumerate(nvidia.get("gpus", [])):
        gpu = dict(raw_gpu)
        normalized_gpus.append(
            {
                "index": nonnegative_int(
                    gpu.get("index", index),
                    "gpu.index",
                ),
                "uuid": text(
                    gpu.get("uuid", f"GPU-FIXTURE-{index}"),
                    "gpu.uuid",
                ),
                "name": text(
                    gpu.get("name", "Fixture GPU"),
                    "gpu.name",
                ),
                "memory_mb": nonnegative_int(
                    gpu.get("memory_mb", 0),
                    "gpu.memory_mb",
                ),
                "compute_capability": (
                    str(gpu["compute_capability"])
                    if gpu.get("compute_capability") is not None
                    else None
                ),
            }
        )

    collected_at = str(
        fixture.get("collected_at")
        or "2026-01-01T00:00:00+00:00"
    )

    return {
        "contract_version": INVENTORY_CONTRACT,
        "inventory_id": "",
        "collected_at": collected_at,
        "node_id": node_id,
        "platform": {
            "system": text(
                platform_value.get("system", "Linux"),
                "platform.system",
            ),
            "release": text(
                platform_value.get("release", "fixture"),
                "platform.release",
            ),
            "architecture": normalize_architecture(
                text(
                    platform_value.get(
                        "architecture",
                        platform_value.get("machine", "x86_64"),
                    ),
                    "platform.architecture",
                )
            ),
            "machine": text(
                platform_value.get(
                    "machine",
                    platform_value.get("architecture", "x86_64"),
                ),
                "platform.machine",
            ),
        },
        "cpu": {
            "logical_cores": positive_int(
                cpu.get("logical_cores"),
                "cpu.logical_cores",
            ),
            "physical_cores": positive_int(
                cpu.get(
                    "physical_cores",
                    cpu.get("logical_cores"),
                ),
                "cpu.physical_cores",
            ),
            "model": text(
                cpu.get("model", "Fixture CPU"),
                "cpu.model",
            ),
            "flags": sorted(
                str(item) for item in cpu.get("flags", [])
            ),
        },
        "memory": {
            "total_mb": nonnegative_int(
                memory.get("total_mb"),
                "memory.total_mb",
            ),
            "available_mb": nonnegative_int(
                memory.get(
                    "available_mb",
                    memory.get("total_mb"),
                ),
                "memory.available_mb",
            ),
        },
        "storage": {
            "path": str(
                storage.get("path")
                or storage_path.expanduser().resolve()
            ),
            "total_gb": nonnegative_int(
                storage.get("total_gb"),
                "storage.total_gb",
            ),
            "free_gb": nonnegative_int(
                storage.get("free_gb"),
                "storage.free_gb",
            ),
        },
        "runtime": {
            "python_version": text(
                runtime.get("python_version", "3.12.0"),
                "runtime.python_version",
            ),
            "systemd_present": bool(
                runtime.get("systemd_present", True)
            ),
            "virtualization": runtime.get("virtualization"),
            "docker": {
                "present": bool(docker.get("present", False)),
                "binary": docker.get("binary"),
                "version": docker.get("version"),
                "daemon_accessible": bool(
                    docker.get("daemon_accessible", False)
                ),
                "daemon_probe_performed": bool(
                    docker.get(
                        "daemon_probe_performed",
                        docker.get("present", False),
                    )
                ),
            },
            "podman": {
                "present": bool(podman.get("present", False)),
                "binary": podman.get("binary"),
                "version": podman.get("version"),
                "daemon_accessible": bool(
                    podman.get("daemon_accessible", False)
                ),
                "daemon_probe_performed": bool(
                    podman.get(
                        "daemon_probe_performed",
                        podman.get("present", False),
                    )
                ),
            },
        },
        "nvidia": {
            "driver_present": bool(
                nvidia.get("driver_present", bool(normalized_gpus))
            ),
            "driver_version": nvidia.get("driver_version"),
            "cuda_version": nvidia.get("cuda_version"),
            "gpus": normalized_gpus,
            "nvidia_container_runtime_present": bool(
                nvidia.get(
                    "nvidia_container_runtime_present",
                    False,
                )
            ),
        },
        "network": {
            "hostname": text(
                network.get("hostname", "fixture-host"),
                "network.hostname",
            ),
            "interfaces": [
                {
                    "name": text(
                        item.get("name"),
                        "network.interface.name",
                    ),
                    "state": text(
                        item.get("state", "unknown"),
                        "network.interface.state",
                    ),
                    "loopback": bool(
                        item.get(
                            "loopback",
                            item.get("name") == "lo",
                        )
                    ),
                }
                for item in network.get("interfaces", [])
            ],
            "default_route_present": bool(
                network.get("default_route_present", True)
            ),
        },
        "privileges": {
            "effective_uid": privileges.get("effective_uid"),
            "is_root": bool(privileges.get("is_root", False)),
            "groups": sorted(
                str(item) for item in privileges.get("groups", [])
            ),
        },
        "probe": {
            "mode": "fixture",
            "container_daemon_contacted": False,
            "external_network_contacted": False,
        },
    }


def collect_inventory(
    *,
    node_id: str,
    storage_path: Path,
    fixture: dict[str, Any] | None = None,
    contact_container_daemon: bool = False,
) -> dict[str, Any]:
    if fixture is not None:
        inventory = fixture_inventory(
            fixture,
            node_id=node_id,
            storage_path=storage_path,
        )
    else:
        inventory = {
            "contract_version": INVENTORY_CONTRACT,
            "inventory_id": "",
            "collected_at": utc_now(),
            "node_id": node_id,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "architecture": normalize_architecture(
                    platform.machine()
                ),
                "machine": platform.machine(),
            },
            "cpu": detect_cpu(),
            "memory": detect_memory(),
            "storage": detect_storage(storage_path),
            "runtime": detect_runtime(
                contact_container_daemon=(
                    contact_container_daemon
                ),
            ),
            "nvidia": detect_nvidia(),
            "network": detect_network(),
            "privileges": detect_privileges(),
            "probe": {
                "mode": "live",
                "container_daemon_contacted": (
                    contact_container_daemon
                ),
                "external_network_contacted": False,
            },
        }

    material = dict(inventory)
    material["inventory_id"] = ""
    inventory["inventory_id"] = (
        "inventory-" + canonical_sha256(material)[:16]
    )
    validate_inventory(inventory)
    return inventory


def validate_inventory(inventory: dict[str, Any]) -> None:
    if inventory.get("contract_version") != INVENTORY_CONTRACT:
        raise InstallationProfileError(
            "Inventory contract_version is invalid."
        )
    positive_int(
        inventory.get("cpu", {}).get("logical_cores"),
        "cpu.logical_cores",
    )
    nonnegative_int(
        inventory.get("memory", {}).get("total_mb"),
        "memory.total_mb",
    )
    nonnegative_int(
        inventory.get("storage", {}).get("free_gb"),
        "storage.free_gb",
    )
    text(inventory.get("node_id"), "node_id")
    architecture = normalize_architecture(
        text(
            inventory.get("platform", {}).get("architecture"),
            "platform.architecture",
        )
    )
    inventory["platform"]["architecture"] = architecture


def load_profile_catalog(path: Path) -> dict[str, Any]:
    catalog = read_json(path)
    if (
        catalog.get("contract_version")
        != PROFILE_CATALOG_CONTRACT
    ):
        raise InstallationProfileError(
            "Installation profile catalog contract is invalid."
        )
    profiles = catalog.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise InstallationProfileError(
            "Installation profile catalog contains no profiles."
        )
    seen = set()
    for profile in profiles:
        profile_id = text(
            profile.get("profile_id"),
            "profile.profile_id",
        )
        if profile_id in seen:
            raise InstallationProfileError(
                f"Duplicate profile_id: {profile_id}"
            )
        seen.add(profile_id)
        positive_int(profile.get("priority"), "profile.priority")
    return catalog


def container_state(
    inventory: dict[str, Any],
) -> dict[str, Any]:
    runtime = inventory.get("runtime", {})
    docker = runtime.get("docker", {})
    podman = runtime.get("podman", {})
    selected = None
    if docker.get("present"):
        selected = "docker"
    elif podman.get("present"):
        selected = "podman"

    daemon_accessible = False
    probe_performed = False
    if selected:
        selected_value = runtime.get(selected, {})
        daemon_accessible = bool(
            selected_value.get("daemon_accessible", False)
        )
        probe_performed = bool(
            selected_value.get(
                "daemon_probe_performed",
                False,
            )
        )

    return {
        "selected": selected,
        "present": selected is not None,
        "daemon_accessible": daemon_accessible,
        "daemon_probe_performed": probe_performed,
    }


def largest_gpu_memory(inventory: dict[str, Any]) -> int:
    return max(
        (
            nonnegative_int(
                gpu.get("memory_mb", 0),
                "gpu.memory_mb",
            )
            for gpu in inventory.get("nvidia", {}).get(
                "gpus",
                [],
            )
        ),
        default=0,
    )


def evaluate_profile(
    inventory: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    requirements = dict(profile.get("requirements", {}))
    system = str(
        inventory.get("platform", {}).get("system", "")
    ).lower()
    architecture = normalize_architecture(
        str(
            inventory.get("platform", {}).get(
                "architecture",
                "",
            )
        )
    )
    cpu = nonnegative_int(
        inventory.get("cpu", {}).get("logical_cores", 0),
        "cpu.logical_cores",
    )
    memory = nonnegative_int(
        inventory.get("memory", {}).get("total_mb", 0),
        "memory.total_mb",
    )
    storage = nonnegative_int(
        inventory.get("storage", {}).get("free_gb", 0),
        "storage.free_gb",
    )
    gpu_memory = largest_gpu_memory(inventory)

    criteria = {
        "system_supported": (
            system in {
                str(item).lower()
                for item in requirements.get(
                    "systems",
                    sorted(SUPPORTED_SYSTEMS),
                )
            }
        ),
        "architecture_supported": (
            architecture in {
                normalize_architecture(str(item))
                for item in requirements.get(
                    "architectures",
                    sorted(SUPPORTED_ARCHITECTURES),
                )
            }
        ),
        "cpu_cores": cpu >= int(
            requirements.get("cpu_cores_min", 0)
        ),
        "memory_mb": memory >= int(
            requirements.get("memory_mb_min", 0)
        ),
        "storage_free_gb": storage >= int(
            requirements.get("storage_free_gb_min", 0)
        ),
        "gpu_memory_mb": (
            gpu_memory
            >= int(requirements.get("gpu_memory_mb_min", 0))
        ),
    }

    return {
        "profile_id": profile.get("profile_id"),
        "priority": profile.get("priority"),
        "eligible": all(criteria.values()),
        "criteria": criteria,
        "observed": {
            "system": system,
            "architecture": architecture,
            "cpu_cores": cpu,
            "memory_mb": memory,
            "storage_free_gb": storage,
            "largest_gpu_memory_mb": gpu_memory,
        },
        "required": requirements,
    }


def resource_budget(
    inventory: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    cpu_total = positive_int(
        inventory.get("cpu", {}).get("logical_cores"),
        "cpu.logical_cores",
    )
    memory_total = nonnegative_int(
        inventory.get("memory", {}).get("total_mb"),
        "memory.total_mb",
    )

    defaults = dict(profile.get("defaults", {}))
    cpu_reserve = min(
        cpu_total,
        int(defaults.get("cpu_cores_reserve", 1)),
    )
    memory_reserve = min(
        memory_total,
        int(defaults.get("memory_mb_reserve", 2048)),
    )
    employee_cpu = max(
        1,
        int(defaults.get("employee_cpu_cores", 2)),
    )
    employee_memory = max(
        256,
        int(defaults.get("employee_memory_mb", 2048)),
    )
    profile_cap = max(
        1,
        int(defaults.get("max_concurrent_employees", 1)),
    )

    cpu_capacity = max(
        1,
        (cpu_total - cpu_reserve) // employee_cpu,
    )
    memory_capacity = max(
        1,
        (memory_total - memory_reserve) // employee_memory,
    )
    concurrency = max(
        1,
        min(profile_cap, cpu_capacity, memory_capacity),
    )

    return {
        "cpu_cores_total": cpu_total,
        "cpu_cores_reserved": cpu_reserve,
        "memory_mb_total": memory_total,
        "memory_mb_reserved": memory_reserve,
        "employee_cpu_cores_default": employee_cpu,
        "employee_memory_mb_default": employee_memory,
        "max_concurrent_employees": concurrency,
    }


def recommend_profile(
    inventory: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    validate_inventory(inventory)
    profiles = sorted(
        catalog["profiles"],
        key=lambda item: int(item["priority"]),
        reverse=True,
    )
    evaluations = [
        evaluate_profile(inventory, profile)
        for profile in profiles
    ]
    eligible = [
        profile
        for profile, evaluation in zip(
            profiles,
            evaluations,
            strict=True,
        )
        if evaluation["eligible"]
    ]

    blockers = []
    warnings = []

    system = str(
        inventory.get("platform", {}).get("system", "")
    ).lower()
    architecture = normalize_architecture(
        str(
            inventory.get("platform", {}).get(
                "architecture",
                "",
            )
        )
    )
    if system not in SUPPORTED_SYSTEMS:
        blockers.append(
            {
                "code": "unsupported-operating-system",
                "message": (
                    "The current developer preview requires a Linux host."
                ),
            }
        )
    if architecture not in SUPPORTED_ARCHITECTURES:
        blockers.append(
            {
                "code": "unsupported-architecture",
                "message": (
                    "The detected architecture is not supported by "
                    "the current developer preview."
                ),
            }
        )

    selected = eligible[0] if eligible else None
    if selected is None:
        blockers.append(
            {
                "code": "insufficient-host-capacity",
                "message": (
                    "The host does not satisfy the minimum standard "
                    "installation profile."
                ),
            }
        )

    container = container_state(inventory)
    if not container["present"]:
        warnings.append(
            {
                "code": "container-runtime-missing",
                "message": (
                    "A supported container runtime must be installed "
                    "before deployment."
                ),
            }
        )
    elif (
        container["daemon_probe_performed"]
        and not container["daemon_accessible"]
    ):
        warnings.append(
            {
                "code": "container-runtime-unavailable",
                "message": (
                    "The selected container runtime is installed but "
                    "the current user cannot reach its service."
                ),
            }
        )

    if not inventory.get("runtime", {}).get(
        "systemd_present",
        False,
    ):
        warnings.append(
            {
                "code": "service-manager-not-detected",
                "message": (
                    "Automatic service startup may require a manual "
                    "integration on this host."
                ),
            }
        )

    if not inventory.get("network", {}).get(
        "default_route_present",
        False,
    ):
        warnings.append(
            {
                "code": "default-route-not-detected",
                "message": (
                    "Connected installation and remote model providers "
                    "may be unavailable."
                ),
            }
        )

    selected_profile_id = (
        selected.get("profile_id")
        if selected
        else "unsupported"
    )
    selected_evaluation = next(
        (
            item
            for item in evaluations
            if item["profile_id"] == selected_profile_id
        ),
        None,
    )

    if blockers:
        suitability = "unsupported"
        readiness = "unsupported"
        budget = {
            "cpu_cores_total": inventory["cpu"]["logical_cores"],
            "cpu_cores_reserved": 0,
            "memory_mb_total": inventory["memory"]["total_mb"],
            "memory_mb_reserved": 0,
            "employee_cpu_cores_default": 0,
            "employee_memory_mb_default": 0,
            "max_concurrent_employees": 0,
        }
        defaults = {}
    else:
        defaults = dict(selected.get("defaults", {}))
        suitability = str(
            selected.get("suitability", "supported")
        )
        readiness = (
            "ready"
            if not warnings
            else "action-required"
        )
        budget = resource_budget(inventory, selected)

    generated_at = inventory["collected_at"]
    recommendation = {
        "contract_version": RECOMMENDATION_CONTRACT,
        "recommendation_id": "",
        "generated_at": generated_at,
        "inventory_id": inventory["inventory_id"],
        "node_id": inventory["node_id"],
        "selected_profile": selected_profile_id,
        "suitability": suitability,
        "readiness": readiness,
        "blockers": blockers,
        "warnings": warnings,
        "profile_evaluations": evaluations,
        "selected_profile_evaluation": selected_evaluation,
        "runtime": {
            "container_runtime": container,
            "gpu_mode": (
                "nvidia"
                if inventory.get("nvidia", {}).get("gpus")
                else "cpu"
            ),
            "embedding_runtime": defaults.get(
                "embedding_runtime",
                "cpu",
            ),
            "model_runtime": defaults.get(
                "model_runtime",
                "external-or-cpu",
            ),
        },
        "resource_budget": budget,
    }
    material = dict(recommendation)
    material["recommendation_id"] = ""
    recommendation["recommendation_id"] = (
        "recommendation-" + canonical_sha256(material)[:16]
    )
    validate_recommendation(recommendation)
    return recommendation


def validate_recommendation(
    recommendation: dict[str, Any],
) -> None:
    if (
        recommendation.get("contract_version")
        != RECOMMENDATION_CONTRACT
    ):
        raise InstallationProfileError(
            "Recommendation contract_version is invalid."
        )
    if recommendation.get("suitability") not in {
        "supported",
        "degraded",
        "unsupported",
    }:
        raise InstallationProfileError(
            "Recommendation suitability is invalid."
        )
    if recommendation.get("readiness") not in {
        "ready",
        "action-required",
        "unsupported",
    }:
        raise InstallationProfileError(
            "Recommendation readiness is invalid."
        )


def build_installation_plan(
    inventory: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    validate_inventory(inventory)
    validate_recommendation(recommendation)
    if (
        recommendation.get("inventory_id")
        != inventory.get("inventory_id")
    ):
        raise InstallationProfileError(
            "Recommendation does not reference the supplied inventory."
        )

    runtime = recommendation.get("runtime", {})
    container = runtime.get("container_runtime", {})
    nvidia = inventory.get("nvidia", {})
    budget = recommendation.get("resource_budget", {})

    actions = [
        {
            "action_id": "prepare-installation-directories",
            "action_type": "filesystem",
            "required": True,
            "status": "planned",
            "reason": (
                "Create portable LEOS configuration, state, and log roots."
            ),
        },
        {
            "action_id": "verify-python-runtime",
            "action_type": "runtime",
            "required": True,
            "status": "satisfied",
            "reason": (
                "The hardware detector is already running on Python."
            ),
        },
        {
            "action_id": "install-container-runtime",
            "action_type": "container-runtime",
            "required": not container.get("present", False),
            "status": (
                "planned"
                if not container.get("present", False)
                else "satisfied"
            ),
            "reason": (
                "LEOS services are deployed as isolated containers."
            ),
        },
        {
            "action_id": "verify-container-service-access",
            "action_type": "container-runtime",
            "required": bool(
                container.get("daemon_probe_performed")
                and not container.get("daemon_accessible")
            ),
            "status": (
                "planned"
                if container.get("daemon_probe_performed")
                and not container.get("daemon_accessible")
                else "satisfied"
            ),
            "reason": (
                "The installer must be able to create and inspect "
                "isolated service containers."
            ),
        },
        {
            "action_id": "configure-nvidia-container-runtime",
            "action_type": "gpu-runtime",
            "required": bool(
                nvidia.get("gpus")
                and not nvidia.get(
                    "nvidia_container_runtime_present",
                    False,
                )
            ),
            "status": (
                "planned"
                if nvidia.get("gpus")
                and not nvidia.get(
                    "nvidia_container_runtime_present",
                    False,
                )
                else "satisfied"
            ),
            "reason": (
                "NVIDIA-backed profiles require a compatible container "
                "runtime integration."
            ),
        },
        {
            "action_id": "write-installation-profile",
            "action_type": "configuration",
            "required": True,
            "status": "planned",
            "reason": (
                "Persist the selected profile and resource budget."
            ),
        },
        {
            "action_id": "deploy-core-services",
            "action_type": "deployment",
            "required": (
                recommendation.get("suitability") != "unsupported"
            ),
            "status": (
                "planned"
                if recommendation.get("suitability") != "unsupported"
                else "blocked"
            ),
            "reason": (
                "Deploy the governed LEOS core after all blockers are "
                "resolved."
            ),
        },
        {
            "action_id": "run-first-start-doctor",
            "action_type": "verification",
            "required": (
                recommendation.get("suitability") != "unsupported"
            ),
            "status": (
                "planned"
                if recommendation.get("suitability") != "unsupported"
                else "blocked"
            ),
            "reason": (
                "Verify service health, permissions, resource capacity, "
                "and configuration after deployment."
            ),
        },
    ]

    gpus = [
        {
            "uuid": gpu["uuid"],
            "name": gpu["name"],
            "memory_mb_total": gpu["memory_mb"],
            "enabled": True,
        }
        for gpu in nvidia.get("gpus", [])
    ]
    compute_capacity = {
        "contract_version": COMPUTE_NODE_CONTRACT,
        "node_id": inventory["node_id"],
        "status": (
            "online"
            if recommendation.get("suitability") != "unsupported"
            else "offline"
        ),
        "cpu_cores_total": inventory["cpu"]["logical_cores"],
        "memory_mb_total": inventory["memory"]["total_mb"],
        "gpus": gpus,
        "enabled": (
            recommendation.get("suitability") != "unsupported"
        ),
        "max_concurrent_jobs": max(
            1,
            int(budget.get("max_concurrent_employees", 0) or 1),
        ),
        "labels": {
            "installation_profile": recommendation[
                "selected_profile"
            ],
            "architecture": inventory["platform"]["architecture"],
            "gpu_mode": runtime.get("gpu_mode", "cpu"),
        },
    }

    plan = {
        "contract_version": PLAN_CONTRACT,
        "plan_id": "",
        "created_at": recommendation["generated_at"],
        "inventory_id": inventory["inventory_id"],
        "recommendation_id": recommendation[
            "recommendation_id"
        ],
        "node_id": inventory["node_id"],
        "selected_profile": recommendation[
            "selected_profile"
        ],
        "readiness": recommendation["readiness"],
        "actions": actions,
        "environment": {
            "LEOS_INSTALL_PROFILE": recommendation[
                "selected_profile"
            ],
            "LEOS_GPU_MODE": runtime.get("gpu_mode", "cpu"),
            "LEOS_CONTAINER_RUNTIME": (
                container.get("selected") or "unselected"
            ),
            "LEOS_MAX_CONCURRENT_EMPLOYEES": str(
                budget.get("max_concurrent_employees", 0)
            ),
        },
        "resource_budget": budget,
        "compute_node_capacity": compute_capacity,
        "execution": {
            "mutates_host": False,
            "requires_confirmation": True,
            "external_network_contacted": False,
        },
    }
    material = dict(plan)
    material["plan_id"] = ""
    plan["plan_id"] = "plan-" + canonical_sha256(material)[:16]
    validate_plan(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("contract_version") != PLAN_CONTRACT:
        raise InstallationProfileError(
            "Installation plan contract_version is invalid."
        )
    if not isinstance(plan.get("actions"), list):
        raise InstallationProfileError(
            "Installation plan actions must be a list."
        )
    if plan.get("execution", {}).get("mutates_host") is not False:
        raise InstallationProfileError(
            "Phase 52.4.1 plans must not mutate the host."
        )


def default_catalog_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "config" / "installation-profiles.json"


def load_fixture(path: Path | None) -> dict[str, Any] | None:
    return read_json(path) if path else None


def inventory_from_path(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise InstallationProfileError(
            "Inventory file must contain a JSON object."
        )
    validate_inventory(value)
    return value


def recommendation_from_path(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise InstallationProfileError(
            "Recommendation file must contain a JSON object."
        )
    validate_recommendation(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect LEOS host capabilities and build a standard "
            "installation profile recommendation."
        )
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=default_catalog_path(),
        help="Installation profile catalog JSON.",
    )
    parser.add_argument(
        "--node-id",
        default=socket.gethostname(),
        help="Compute node identifier.",
    )
    parser.add_argument(
        "--storage-path",
        type=Path,
        default=Path.cwd(),
        help="Target storage path to inspect.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Deterministic hardware fixture used for tests.",
    )
    parser.add_argument(
        "--contact-container-daemon",
        action="store_true",
        help=(
            "Probe local container-service accessibility. "
            "No external network traffic is generated."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of standard output.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )
    subparsers.add_parser("detect")
    recommend = subparsers.add_parser("recommend")
    recommend.add_argument(
        "--inventory",
        type=Path,
        help="Existing host inventory JSON.",
    )
    plan = subparsers.add_parser("plan")
    plan.add_argument(
        "--inventory",
        type=Path,
        help="Existing host inventory JSON.",
    )
    plan.add_argument(
        "--recommendation",
        type=Path,
        help="Existing recommendation JSON.",
    )
    subparsers.add_parser("all")
    return parser


def emit(value: Any, output: Path | None) -> None:
    if output:
        write_json(output, value)
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    fixture = load_fixture(args.fixture)
    catalog = load_profile_catalog(args.catalog)

    if args.command == "detect":
        inventory = collect_inventory(
            node_id=args.node_id,
            storage_path=args.storage_path,
            fixture=fixture,
            contact_container_daemon=(
                args.contact_container_daemon
            ),
        )
        emit(inventory, args.output)
        return 0

    inventory_path = getattr(args, "inventory", None)
    inventory = (
        inventory_from_path(inventory_path)
        if inventory_path
        else collect_inventory(
            node_id=args.node_id,
            storage_path=args.storage_path,
            fixture=fixture,
            contact_container_daemon=(
                args.contact_container_daemon
            ),
        )
    )
    recommendation = recommend_profile(inventory, catalog)

    if args.command == "recommend":
        emit(recommendation, args.output)
        return 0

    recommendation_path = getattr(
        args,
        "recommendation",
        None,
    )
    if recommendation_path:
        recommendation = recommendation_from_path(
            recommendation_path
        )

    plan = build_installation_plan(
        inventory,
        recommendation,
    )

    if args.command == "plan":
        emit(plan, args.output)
        return 0

    emit(
        {
            "ok": True,
            "contract_version": "leos.installation-profile-bundle.v1",
            "inventory": inventory,
            "recommendation": recommendation,
            "plan": plan,
        },
        args.output,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallationProfileError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
