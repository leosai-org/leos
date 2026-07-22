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
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOOTSTRAP_CONFIG = ROOT / "config/installer-bootstrap.json"
DEFAULT_LAYOUT_CONFIG = ROOT / "config/installation-layout.json"

CONTRACT_TRANSACTION = "leos.installation-transaction.v1"
CONTRACT_JOURNAL = "leos.installation-execution-journal.v1"
CONTRACT_MANIFEST = "leos.installation-manifest.v1"
CONTRACT_RESULT = "leos.installation-result.v1"
CONTRACT_LAYOUT = "leos.installation-layout.v1"

SAFE_TARGET_FORBIDDEN = {
    Path("/"),
    Path("/bin"),
    Path("/boot"),
    Path("/dev"),
    Path("/etc"),
    Path("/home"),
    Path("/lib"),
    Path("/lib64"),
    Path("/proc"),
    Path("/root"),
    Path("/run"),
    Path("/sbin"),
    Path("/sys"),
    Path("/usr"),
    Path("/var"),
}


class InstallerError(RuntimeError):
    pass


class InjectedFailure(InstallerError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def stable_id(prefix: str, value: Any, length: int = 16) -> str:
    digest = hashlib.sha256(canonical_json(value)).hexdigest()
    return f"{prefix}-{digest[:length]}"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InstallerError(f"Unable to read JSON: {path}") from exc


def read_config(path: Path, expected_contract: str) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise InstallerError(f"Expected JSON object: {path}")
    if value.get("contract_version") != expected_contract:
        raise InstallerError(
            f"Unexpected contract in {path}: {value.get('contract_version')}"
        )
    return value


def validate_plan(plan: dict[str, Any]) -> None:
    required = (
        "contract_version",
        "plan_id",
        "node_id",
        "selected_profile",
        "resource_budget",
        "compute_node_capacity",
        "environment",
        "execution",
    )
    missing = [key for key in required if key not in plan]
    if missing:
        raise InstallerError(f"Installation plan is missing: {missing}")
    if plan.get("contract_version") != "leos.installation-plan.v1":
        raise InstallerError("Unsupported installation-plan contract.")
    if not plan.get("execution", {}).get("requires_confirmation"):
        raise InstallerError("Installation plan must require confirmation.")
    if plan.get("execution", {}).get("mutates_host") is not False:
        raise InstallerError(
            "Phase 52.4.1 plan must remain non-mutating before apply."
        )


def normalize_target(path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    if target in SAFE_TARGET_FORBIDDEN:
        raise InstallerError(f"Unsafe installation target: {target}")
    if len(target.parts) < 3:
        raise InstallerError(
            f"Installation target is too broad: {target}"
        )
    return target


def ensure_subpath(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise InstallerError(
            f"Path escapes installation root: {path}"
        ) from exc


def mode_from_text(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0"):
        raise InstallerError(f"Invalid mode: {value!r}")
    return int(value, 8)


def source_release_record(source_root: Path) -> dict[str, Any]:
    manifest_path = source_root / "manifest.json"
    source_lock_path = source_root / "source.lock.json"
    if not manifest_path.is_file() or not source_lock_path.is_file():
        raise InstallerError(
            "Source authority requires manifest.json and source.lock.json."
        )

    manifest = read_json(manifest_path)
    source_lock = read_json(source_lock_path)
    if not isinstance(manifest, dict) or not isinstance(source_lock, dict):
        raise InstallerError("Source authority files must be JSON objects.")
    if manifest.get("contract_version") != "leos.release-manifest.v1":
        raise InstallerError("Unsupported release-manifest contract.")
    if source_lock.get("contract_version") != "leos.source-lock.v1":
        raise InstallerError("Unsupported source-lock contract.")

    release = str(manifest.get("release_version", ""))
    if not release or source_lock.get("release_version") != release:
        raise InstallerError("Release manifest and source lock disagree.")
    payload = str(source_lock.get("payload_tree_sha256", ""))
    if not re.fullmatch(r"[a-f0-9]{64}", payload):
        raise InstallerError("Source lock payload hash is invalid.")

    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "source_lock_path": str(source_lock_path),
        "source_lock_sha256": sha256_file(source_lock_path),
        "release": release,
        "payload_tree_sha256": payload,
        "record": manifest,
    }


def resolve_source(
    *,
    mode: str,
    source_root: str | None,
    allow_network: bool,
) -> dict[str, Any]:
    if mode not in {"offline", "connected"}:
        raise InstallerError(f"Unsupported installation mode: {mode}")

    if mode == "offline":
        if not source_root:
            raise InstallerError(
                "Offline mode requires --source-root."
            )
        root = Path(source_root).expanduser().resolve()
        if not root.is_dir():
            raise InstallerError(
                f"Offline source root is missing: {root}"
            )
        release = source_release_record(root)
        return {
            "mode": "offline",
            "source_root": str(root),
            "source_record": release,
            "external_network_contacted": False,
            "network_permission_granted": False,
            "acquisition_status": "local-source-verified",
        }

    if not allow_network:
        raise InstallerError(
            "Connected mode requires --allow-network."
        )
    release = source_release_record(ROOT)
    return {
        "mode": "connected",
        "source_root": None,
        "source_record": release,
        "external_network_contacted": False,
        "network_permission_granted": True,
        "acquisition_status": "network-acquisition-authorized-not-executed",
    }


def build_transaction(
    *,
    plan: dict[str, Any],
    target_root: Path,
    mode: str,
    source: dict[str, Any],
    bootstrap_config: dict[str, Any],
    layout_config: dict[str, Any],
    desired_owner: str,
    desired_group: str,
) -> dict[str, Any]:
    validate_plan(plan)
    target_root = normalize_target(target_root)
    authority = source.get("source_record")
    if not isinstance(authority, dict):
        raise InstallerError("Resolved source authority is missing.")
    source_release = str(authority["release"])
    source_tree_sha256 = str(authority["payload_tree_sha256"])

    transaction_seed = {
        "plan_id": plan["plan_id"],
        "target_root": str(target_root),
        "mode": mode,
        "source_root": source.get("source_root"),
        "selected_profile": plan["selected_profile"],
        "source_release": source_release,
        "layout_version": layout_config["layout_version"],
        "desired_owner": desired_owner,
        "desired_group": desired_group,
    }
    transaction_id = stable_id("install-tx", transaction_seed)
    actions = [
        {
            "sequence": 1,
            "action_id": "acquire-install-lock",
            "action_type": "lock",
            "reversible": True,
        },
        {
            "sequence": 2,
            "action_id": "prepare-directory-layout",
            "action_type": "filesystem",
            "reversible": True,
        },
        {
            "sequence": 3,
            "action_id": "write-installation-plan",
            "action_type": "configuration",
            "reversible": True,
        },
        {
            "sequence": 4,
            "action_id": "write-runtime-environment",
            "action_type": "configuration",
            "reversible": True,
        },
        {
            "sequence": 5,
            "action_id": "write-compute-node-capacity",
            "action_type": "configuration",
            "reversible": True,
        },
        {
            "sequence": 6,
            "action_id": "write-ownership-intent",
            "action_type": "ownership",
            "reversible": True,
        },
        {
            "sequence": 7,
            "action_id": "write-installation-manifest",
            "action_type": "manifest",
            "reversible": True,
        },
        {
            "sequence": 8,
            "action_id": "finalize-execution-journal",
            "action_type": "journal",
            "reversible": False,
        },
    ]
    return {
        "contract_version": CONTRACT_TRANSACTION,
        "transaction_id": transaction_id,
        "plan_id": plan["plan_id"],
        "node_id": plan["node_id"],
        "selected_profile": plan["selected_profile"],
        "source_release": source_release,
        "source_tree_sha256": source_tree_sha256,
        "target_root": str(target_root),
        "mode": mode,
        "state": "planned",
        "confirmation": {
            "required": True,
            "token": plan["plan_id"],
        },
        "network": {
            "permission_granted": source[
                "network_permission_granted"
            ],
            "external_network_contacted": False,
            "acquisition_status": source["acquisition_status"],
        },
        "ownership": {
            "desired_owner": desired_owner,
            "desired_group": desired_group,
            "apply_ownership": False,
        },
        "rollback": {
            "enabled": True,
            "automatic_on_failure": True,
            "backup_directory": str(
                target_root / "backups" / transaction_id
            ),
        },
        "actions": actions,
    }


def desired_files(
    *,
    plan: dict[str, Any],
    transaction: dict[str, Any],
    bootstrap_config: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, bytes]:
    env = {
        **plan.get("environment", {}),
        "LEOS_INSTALL_ROOT": transaction["target_root"],
        "LEOS_SOURCE_RELEASE": transaction["source_release"],
        "LEOS_SOURCE_TREE_SHA256": transaction[
            "source_tree_sha256"
        ],
        "LEOS_INSTALL_MODE": transaction["mode"],
    }
    env_text = "".join(
        f"{key}={env[key]}\n"
        for key in sorted(env)
    ).encode("utf-8")

    owner_intent = {
        "contract_version": "leos.ownership-intent.v1",
        "target_root": transaction["target_root"],
        "desired_owner": transaction["ownership"][
            "desired_owner"
        ],
        "desired_group": transaction["ownership"][
            "desired_group"
        ],
        "apply_ownership": False,
        "reason": (
            "Phase 52.4.2 prepares explicit ownership intent. "
            "Privileged ownership application remains opt-in."
        ),
    }

    source_record = source.get("source_record")
    source_summary = {
        "mode": source["mode"],
        "source_root": source.get("source_root"),
        "manifest_path": (
            source_record.get("manifest_path")
            if isinstance(source_record, dict)
            else None
        ),
        "manifest_sha256": (
            source_record.get("manifest_sha256")
            if isinstance(source_record, dict)
            else None
        ),
        "source_lock_path": (
            source_record.get("source_lock_path")
            if isinstance(source_record, dict)
            else None
        ),
        "source_lock_sha256": (
            source_record.get("source_lock_sha256")
            if isinstance(source_record, dict)
            else None
        ),
        "authority_contract": "leos.source-authority.v1",
        "external_network_contacted": False,
    }

    install_config = {
        "contract_version": "leos.bootstrap-configuration.v1",
        "plan_id": plan["plan_id"],
        "node_id": plan["node_id"],
        "selected_profile": plan["selected_profile"],
        "resource_budget": plan["resource_budget"],
        "compute_node_capacity": plan["compute_node_capacity"],
        "source": source_summary,
        "installer": {
            "transaction_id": transaction["transaction_id"],
            "mode": transaction["mode"],
            "idempotent": True,
            "rollback_enabled": True,
        },
    }

    return {
        "config/leos.env": env_text,
        "config/installation.json": canonical_json(
            install_config
        ),
        "state/installation-plan.json": canonical_json(plan),
        "state/compute-node-capacity.json": canonical_json(
            plan["compute_node_capacity"]
        ),
        "state/ownership-intent.json": canonical_json(
            owner_intent
        ),
    }


def file_state(path: Path) -> dict[str, Any]:
    if not path.exists() and not path.is_symlink():
        return {
            "exists": False,
            "sha256": None,
            "mode": None,
            "size_bytes": None,
        }
    if not path.is_file() or path.is_symlink():
        raise InstallerError(
            f"Installer only manages regular files: {path}"
        )
    return {
        "exists": True,
        "sha256": sha256_file(path),
        "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        "size_bytes": path.stat().st_size,
    }


def atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}"
    )
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def backup_path(
    *,
    target_root: Path,
    backup_root: Path,
    managed_path: Path,
) -> Path:
    relative = managed_path.relative_to(target_root)
    destination = backup_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def backup_existing(
    *,
    target_root: Path,
    backup_root: Path,
    path: Path,
) -> dict[str, Any]:
    state = file_state(path)
    record = {
        "path": str(path),
        "relative_path": path.relative_to(target_root).as_posix(),
        "before": state,
        "backup_path": None,
        "created_by_transaction": not state["exists"],
    }
    if state["exists"]:
        destination = backup_path(
            target_root=target_root,
            backup_root=backup_root,
            managed_path=path,
        )
        shutil.copy2(path, destination)
        record["backup_path"] = str(destination)
    return record


def restore_record(record: dict[str, Any]) -> None:
    path = Path(record["path"])
    backup = record.get("backup_path")
    if backup:
        source = Path(backup)
        if not source.is_file():
            raise InstallerError(
                f"Rollback backup is missing: {source}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
        return
    if record.get("created_by_transaction") and path.exists():
        path.unlink()


def managed_directory_records(
    target_root: Path,
    layout_config: dict[str, Any],
) -> list[dict[str, Any]]:
    records = []
    for entry in layout_config["directories"]:
        relative = entry["path"]
        path = target_root / relative
        ensure_subpath(target_root, path)
        records.append(
            {
                "relative_path": relative,
                "path": str(path),
                "mode": entry["mode"],
            }
        )
    return records


def prepare_directories(
    target_root: Path,
    layout_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path]]:
    states = []
    created = []
    target_root_preexisting = target_root.exists()
    target_root.mkdir(parents=True, exist_ok=True)
    if not target_root_preexisting:
        created.append(target_root)

    for record in managed_directory_records(
        target_root,
        layout_config,
    ):
        path = Path(record["path"])
        before_exists = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        mode = mode_from_text(record["mode"])
        os.chmod(path, mode)
        if not before_exists:
            created.append(path)
        states.append(
            {
                **record,
                "created": not before_exists,
                "exists": path.is_dir(),
                "actual_mode": oct(
                    stat.S_IMODE(path.stat().st_mode)
                ),
            }
        )
    return states, created


def rollback_directories(created: Iterable[Path]) -> None:
    for path in sorted(
        created,
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        try:
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


@contextmanager
def installation_lock(target_root: Path):
    target_root.parent.mkdir(parents=True, exist_ok=True)
    lock = target_root.parent / (
        f".{target_root.name}.leos-install.lock"
    )
    try:
        descriptor = os.open(
            lock,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise InstallerError(
            f"Another installation transaction holds: {lock}"
        ) from exc

    try:
        os.write(
            descriptor,
            canonical_json(
                {
                    "contract_version": "leos.install-lock.v1",
                    "target_root": str(target_root),
                    "pid": os.getpid(),
                }
            ),
        )
        os.close(descriptor)
        yield lock
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        if lock.exists():
            lock.unlink()


def build_manifest(
    *,
    plan: dict[str, Any],
    transaction: dict[str, Any],
    target_root: Path,
    desired: dict[str, bytes],
    directories: list[dict[str, Any]],
    previous_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    file_records = {}
    for relative in sorted(desired):
        path = target_root / relative
        file_records[relative] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        }

    installation_seed = {
        "target_root": str(target_root),
        "source_release": transaction["source_release"],
        "source_tree_sha256": transaction[
            "source_tree_sha256"
        ],
        "plan_id": plan["plan_id"],
        "selected_profile": plan["selected_profile"],
    }
    installation_id = (
        previous_manifest.get("installation_id")
        if previous_manifest
        else stable_id("installation", installation_seed)
    )
    installed_at = (
        previous_manifest.get("installed_at")
        if previous_manifest
        else plan.get("created_at", "1970-01-01T00:00:00+00:00")
    )

    return {
        "contract_version": CONTRACT_MANIFEST,
        "installation_id": installation_id,
        "transaction_id": transaction["transaction_id"],
        "plan_id": plan["plan_id"],
        "node_id": plan["node_id"],
        "selected_profile": plan["selected_profile"],
        "source_release": transaction["source_release"],
        "source_tree_sha256": transaction[
            "source_tree_sha256"
        ],
        "target_root": str(target_root),
        "mode": transaction["mode"],
        "installed_at": installed_at,
        "layout_version": "1",
        "directories": directories,
        "files": file_records,
        "ownership": transaction["ownership"],
        "status": "installed",
    }


def existing_manifest(target_root: Path) -> dict[str, Any] | None:
    path = target_root / "state/installation-manifest.json"
    if not path.is_file():
        return None
    value = read_json(path)
    if not isinstance(value, dict):
        raise InstallerError(
            f"Installation manifest is invalid: {path}"
        )
    if value.get("contract_version") != CONTRACT_MANIFEST:
        raise InstallerError(
            f"Unsupported installation manifest: {path}"
        )
    return value


def compatibility_check(
    previous: dict[str, Any] | None,
    transaction: dict[str, Any],
) -> None:
    if not previous:
        return
    mismatches = []
    for key in (
        "plan_id",
        "source_release",
        "source_tree_sha256",
        "selected_profile",
    ):
        if previous.get(key) != transaction.get(key):
            mismatches.append(
                {
                    "field": key,
                    "existing": previous.get(key),
                    "requested": transaction.get(key),
                }
            )
    if mismatches:
        raise InstallerError(
            "Existing installation requires an explicit upgrade "
            f"workflow: {mismatches}"
        )


def apply_installation(
    *,
    plan: dict[str, Any],
    target_root: Path,
    mode: str,
    source: dict[str, Any],
    bootstrap_config: dict[str, Any],
    layout_config: dict[str, Any],
    confirmation: str | None,
    desired_owner: str,
    desired_group: str,
    fail_after: int | None = None,
) -> dict[str, Any]:
    transaction = build_transaction(
        plan=plan,
        target_root=target_root,
        mode=mode,
        source=source,
        bootstrap_config=bootstrap_config,
        layout_config=layout_config,
        desired_owner=desired_owner,
        desired_group=desired_group,
    )
    if confirmation != transaction["confirmation"]["token"]:
        raise InstallerError(
            "Confirmation token must exactly match the plan_id."
        )

    target_root = Path(transaction["target_root"])
    previous = existing_manifest(target_root)
    compatibility_check(previous, transaction)
    desired = desired_files(
        plan=plan,
        transaction=transaction,
        bootstrap_config=bootstrap_config,
        source=source,
    )
    backup_root = Path(
        transaction["rollback"]["backup_directory"]
    )
    journal_entries: list[dict[str, Any]] = []
    backups: list[dict[str, Any]] = []
    created_directories: list[Path] = []
    changed_paths: list[str] = []
    unchanged_paths: list[str] = []
    action_counter = 0
    rolled_back = False

    def event(
        action_id: str,
        status: str,
        **extra: Any,
    ) -> None:
        journal_entries.append(
            {
                "sequence": len(journal_entries) + 1,
                "action_id": action_id,
                "status": status,
                **extra,
            }
        )

    def checkpoint(action_id: str) -> None:
        nonlocal action_counter
        action_counter += 1
        if (
            fail_after is not None
            and action_counter >= fail_after
        ):
            raise InjectedFailure(
                f"Injected failure after action {action_id}"
            )

    try:
        with installation_lock(target_root) as lock:
            event(
                "acquire-install-lock",
                "complete",
                path=str(lock),
            )
            checkpoint("acquire-install-lock")

            directories, created_directories = (
                prepare_directories(
                    target_root,
                    layout_config,
                )
            )
            event(
                "prepare-directory-layout",
                "complete",
                directory_count=len(directories),
                created_count=sum(
                    1 for item in directories if item["created"]
                ),
            )
            checkpoint("prepare-directory-layout")

            desired_modes = bootstrap_config["file_modes"]
            for relative, content in sorted(desired.items()):
                path = target_root / relative
                ensure_subpath(target_root, path)
                before = file_state(path)
                after_sha = sha256_bytes(content)
                if (
                    before["exists"]
                    and before["sha256"] == after_sha
                ):
                    unchanged_paths.append(relative)
                    event(
                        f"write:{relative}",
                        "unchanged",
                        path=str(path),
                        before_sha256=before["sha256"],
                        after_sha256=after_sha,
                    )
                    continue

                backup = backup_existing(
                    target_root=target_root,
                    backup_root=backup_root,
                    path=path,
                )
                backups.append(backup)
                atomic_write(
                    path,
                    content,
                    mode_from_text(
                        desired_modes.get(relative, "0640")
                    ),
                )
                changed_paths.append(relative)
                event(
                    f"write:{relative}",
                    "complete",
                    path=str(path),
                    before_sha256=before["sha256"],
                    after_sha256=sha256_file(path),
                    backup_path=backup.get("backup_path"),
                )
                checkpoint(f"write:{relative}")

            manifest_path = (
                target_root
                / "state"
                / "installation-manifest.json"
            )
            provisional_directories = (
                managed_directory_records(
                    target_root,
                    layout_config,
                )
            )
            manifest = build_manifest(
                plan=plan,
                transaction=transaction,
                target_root=target_root,
                desired=desired,
                directories=provisional_directories,
                previous_manifest=previous,
            )
            manifest_content = canonical_json(manifest)
            before_manifest = file_state(manifest_path)
            if (
                before_manifest["exists"]
                and before_manifest["sha256"]
                == sha256_bytes(manifest_content)
            ):
                unchanged_paths.append(
                    "state/installation-manifest.json"
                )
                event(
                    "write-installation-manifest",
                    "unchanged",
                    path=str(manifest_path),
                )
            else:
                backup = backup_existing(
                    target_root=target_root,
                    backup_root=backup_root,
                    path=manifest_path,
                )
                backups.append(backup)
                atomic_write(
                    manifest_path,
                    manifest_content,
                    mode_from_text(
                        desired_modes.get(
                            "state/installation-manifest.json",
                            "0640",
                        )
                    ),
                )
                changed_paths.append(
                    "state/installation-manifest.json"
                )
                event(
                    "write-installation-manifest",
                    "complete",
                    path=str(manifest_path),
                    before_sha256=before_manifest["sha256"],
                    after_sha256=sha256_file(manifest_path),
                    backup_path=backup.get("backup_path"),
                )
                checkpoint("write-installation-manifest")

            journal = {
                "contract_version": CONTRACT_JOURNAL,
                "transaction_id": transaction["transaction_id"],
                "plan_id": plan["plan_id"],
                "target_root": str(target_root),
                "state": "complete",
                "entries": journal_entries,
                "changed_paths": sorted(changed_paths),
                "unchanged_paths": sorted(unchanged_paths),
                "rollback": {
                    "performed": False,
                    "backup_root": str(backup_root),
                    "backup_count": len(backups),
                },
                "external_network_contacted": False,
                "container_daemon_contacted": False,
            }
            journal_path = (
                target_root
                / "journal"
                / f"{transaction['transaction_id']}.json"
            )
            atomic_write(
                journal_path,
                canonical_json(journal),
                0o640,
            )

            transaction["state"] = "complete"
            result = {
                "ok": True,
                "contract_version": CONTRACT_RESULT,
                "state": "complete",
                "changed": bool(changed_paths),
                "changed_count": len(changed_paths),
                "unchanged_count": len(unchanged_paths),
                "idempotent": not changed_paths,
                "transaction": transaction,
                "journal": journal,
                "journal_path": str(journal_path),
                "manifest": manifest,
                "manifest_path": str(manifest_path),
                "external_network_contacted": False,
                "container_daemon_contacted": False,
                "production_state_accessed": False,
                "production_network_attached": False,
            }
            return result
    except Exception as exc:
        rollback_errors = []
        for record in reversed(backups):
            try:
                restore_record(record)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        rollback_directories(created_directories)
        rolled_back = True

        failed_journal = {
            "contract_version": CONTRACT_JOURNAL,
            "transaction_id": transaction["transaction_id"],
            "plan_id": plan["plan_id"],
            "target_root": str(target_root),
            "state": "rolled-back",
            "entries": [
                *journal_entries,
                {
                    "sequence": len(journal_entries) + 1,
                    "action_id": "automatic-rollback",
                    "status": (
                        "complete"
                        if not rollback_errors
                        else "failed"
                    ),
                    "reason": str(exc),
                    "rollback_errors": rollback_errors,
                },
            ],
            "changed_paths": sorted(changed_paths),
            "unchanged_paths": sorted(unchanged_paths),
            "rollback": {
                "performed": True,
                "backup_root": str(backup_root),
                "backup_count": len(backups),
                "errors": rollback_errors,
            },
            "external_network_contacted": False,
            "container_daemon_contacted": False,
        }
        rollback_journal_root = (
            target_root.parent
            / f".{target_root.name}-rollback-journals"
        )
        rollback_journal_root.mkdir(
            parents=True,
            exist_ok=True,
        )
        failed_path = (
            rollback_journal_root
            / f"{transaction['transaction_id']}.json"
        )
        atomic_write(
            failed_path,
            canonical_json(failed_journal),
            0o600,
        )
        if rollback_errors:
            raise InstallerError(
                f"Install failed and rollback was incomplete: "
                f"{exc}; {rollback_errors}"
            ) from exc
        raise InstallerError(
            f"Install failed and was rolled back: {exc}; "
            f"journal={failed_path}; rolled_back={rolled_back}"
        ) from exc


def inspect_installation(target_root: Path) -> dict[str, Any]:
    target_root = normalize_target(target_root)
    manifest_path = (
        target_root / "state/installation-manifest.json"
    )
    if not manifest_path.is_file():
        return {
            "ok": True,
            "installed": False,
            "target_root": str(target_root),
            "manifest": None,
            "drift": [],
        }

    manifest = read_json(manifest_path)
    drift = []
    for relative, expected in manifest.get("files", {}).items():
        path = target_root / relative
        actual = file_state(path)
        if (
            not actual["exists"]
            or actual["sha256"] != expected["sha256"]
        ):
            drift.append(
                {
                    "path": relative,
                    "expected_sha256": expected["sha256"],
                    "actual_sha256": actual["sha256"],
                    "exists": actual["exists"],
                }
            )
    return {
        "ok": not drift,
        "installed": True,
        "target_root": str(target_root),
        "manifest": manifest,
        "drift": drift,
        "drift_count": len(drift),
    }


def explicit_rollback(
    *,
    target_root: Path,
    transaction_id: str,
) -> dict[str, Any]:
    target_root = normalize_target(target_root)
    backup_root = target_root / "backups" / transaction_id
    if not backup_root.is_dir():
        raise InstallerError(
            f"Backup transaction does not exist: {backup_root}"
        )

    restored = []
    for backup in sorted(backup_root.rglob("*")):
        if not backup.is_file():
            continue
        relative = backup.relative_to(backup_root)
        destination = target_root / relative
        ensure_subpath(target_root, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, destination)
        restored.append(relative.as_posix())

    return {
        "ok": True,
        "contract_version": "leos.installation-rollback-result.v1",
        "transaction_id": transaction_id,
        "target_root": str(target_root),
        "restored_count": len(restored),
        "restored_paths": restored,
        "external_network_contacted": False,
        "container_daemon_contacted": False,
    }


def load_inputs(args: argparse.Namespace) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    plan = read_json(Path(args.plan))
    if not isinstance(plan, dict):
        raise InstallerError("Installation plan must be a JSON object.")
    validate_plan(plan)
    bootstrap = read_config(
        Path(args.bootstrap_config),
        "leos.installer-bootstrap-config.v1",
    )
    layout = read_config(
        Path(args.layout_config),
        CONTRACT_LAYOUT,
    )
    return plan, bootstrap, layout


def emit(value: dict[str, Any], output: str | None) -> None:
    content = canonical_json(value)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, content, 0o640)
    sys.stdout.buffer.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "LEOS idempotent installer and bootstrap transaction engine."
        )
    )
    parser.add_argument(
        "--bootstrap-config",
        default=str(DEFAULT_BOOTSTRAP_CONFIG),
    )
    parser.add_argument(
        "--layout-config",
        default=str(DEFAULT_LAYOUT_CONFIG),
    )
    parser.add_argument("--output")

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Create a deterministic installation transaction.",
    )
    plan_parser.add_argument("--plan", required=True)
    plan_parser.add_argument("--target-root", required=True)
    plan_parser.add_argument(
        "--mode",
        choices=("offline", "connected"),
        required=True,
    )
    plan_parser.add_argument("--source-root")
    plan_parser.add_argument(
        "--allow-network",
        action="store_true",
    )
    plan_parser.add_argument(
        "--desired-owner",
        default=os.environ.get("USER", "leos"),
    )
    plan_parser.add_argument(
        "--desired-group",
        default=os.environ.get("USER", "leos"),
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply an installation transaction.",
    )
    apply_parser.add_argument("--plan", required=True)
    apply_parser.add_argument("--target-root", required=True)
    apply_parser.add_argument(
        "--mode",
        choices=("offline", "connected"),
        required=True,
    )
    apply_parser.add_argument("--source-root")
    apply_parser.add_argument(
        "--allow-network",
        action="store_true",
    )
    apply_parser.add_argument("--confirm", required=True)
    apply_parser.add_argument(
        "--desired-owner",
        default=os.environ.get("USER", "leos"),
    )
    apply_parser.add_argument(
        "--desired-group",
        default=os.environ.get("USER", "leos"),
    )
    apply_parser.add_argument(
        "--fail-after",
        type=int,
        help="Test-only deterministic failure injection.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect an installation manifest and drift.",
    )
    inspect_parser.add_argument("--target-root", required=True)

    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Restore files from a transaction backup.",
    )
    rollback_parser.add_argument("--target-root", required=True)
    rollback_parser.add_argument(
        "--transaction-id",
        required=True,
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.command == "inspect":
            result = inspect_installation(
                Path(args.target_root)
            )
        elif args.command == "rollback":
            result = explicit_rollback(
                target_root=Path(args.target_root),
                transaction_id=args.transaction_id,
            )
        else:
            plan, bootstrap, layout = load_inputs(args)
            source = resolve_source(
                mode=args.mode,
                source_root=args.source_root,
                allow_network=args.allow_network,
            )
            if args.command == "plan":
                transaction = build_transaction(
                    plan=plan,
                    target_root=Path(args.target_root),
                    mode=args.mode,
                    source=source,
                    bootstrap_config=bootstrap,
                    layout_config=layout,
                    desired_owner=args.desired_owner,
                    desired_group=args.desired_group,
                )
                result = {
                    "ok": True,
                    "contract_version": (
                        "leos.installation-transaction-plan.v1"
                    ),
                    "transaction": transaction,
                    "mutates_host": False,
                    "external_network_contacted": False,
                    "container_daemon_contacted": False,
                }
            else:
                result = apply_installation(
                    plan=plan,
                    target_root=Path(args.target_root),
                    mode=args.mode,
                    source=source,
                    bootstrap_config=bootstrap,
                    layout_config=layout,
                    confirmation=args.confirm,
                    desired_owner=args.desired_owner,
                    desired_group=args.desired_group,
                    fail_after=args.fail_after,
                )
    except InstallerError as exc:
        result = {
            "ok": False,
            "contract_version": "leos.installer-error.v1",
            "error": str(exc),
            "external_network_contacted": False,
            "container_daemon_contacted": False,
            "production_state_accessed": False,
            "production_network_attached": False,
        }
        emit(result, args.output)
        return 1

    emit(result, args.output)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
