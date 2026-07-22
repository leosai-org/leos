#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/first-run.json"
DEFAULT_RUNTIME_CATALOG = ROOT / "config/first-run-runtime-catalog.json"

CONTRACT_SESSION = "leos.first-run-session.v1"
CONTRACT_CONFIGURATION = "leos.first-run-configuration.v1"
CONTRACT_ADMIN = "leos.administrator-bootstrap.v1"
CONTRACT_NODE = "leos.node-registration-plan.v1"
CONTRACT_RUNTIME = "leos.runtime-selection.v1"
CONTRACT_READINESS = "leos.first-run-readiness.v1"
CONTRACT_RESULT = "leos.first-run-result.v1"

REQUIRED_OUTPUTS = (
    ("config/first-run.json", CONTRACT_CONFIGURATION),
    ("state/first-run-session.json", CONTRACT_SESSION),
    ("state/administrator-bootstrap.json", CONTRACT_ADMIN),
    ("state/node-registration-plan.json", CONTRACT_NODE),
    ("state/runtime-selection.json", CONTRACT_RUNTIME),
    ("state/first-run-readiness.json", CONTRACT_READINESS),
)

FORBIDDEN_SECRET_KEYS = {
    "password",
    "password_hash",
    "secret",
    "secret_value",
    "api_key",
    "access_token",
    "refresh_token",
    "private_key",
}

SAFE_TARGET_FORBIDDEN_NAMES = {
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


class FirstRunError(RuntimeError):
    pass


class InjectedFailure(FirstRunError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        raise FirstRunError(f"Unable to read JSON document: {path}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def load_object(path: Path, contract: str | None = None) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise FirstRunError(f"Expected a JSON object: {path}")
    if contract is not None and value.get("contract_version") != contract:
        raise FirstRunError(
            f"Unexpected contract in {path}: {value.get('contract_version')!r}"
        )
    return value


def mode_from_text(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0[0-7]{3}", value):
        raise FirstRunError(f"Invalid file mode: {value!r}")
    return int(value, 8)


def normalize_target(value: str | Path) -> Path:
    target = Path(value).expanduser().resolve()
    if len(target.parts) < 3:
        raise FirstRunError(f"First-run target is too broad: {target}")
    if target.name.lower() in SAFE_TARGET_FORBIDDEN_NAMES:
        raise FirstRunError(f"Unsafe first-run target: {target}")
    return target


def ensure_installed_target(target: Path) -> dict[str, Any]:
    manifest_path = target / "state/installation-manifest.json"
    if not manifest_path.is_file():
        raise FirstRunError(
            "The target does not contain an installation manifest."
        )
    manifest = load_object(
        manifest_path,
        "leos.installation-manifest.v1",
    )
    if manifest.get("status") != "installed":
        raise FirstRunError("The installation manifest is not installed.")
    manifest_target = Path(str(manifest.get("target_root", "")))
    if manifest_target.is_absolute() and manifest_target.resolve() != target:
        raise FirstRunError("Installation manifest target does not match.")
    return manifest


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("contract_version") != "leos.installation-plan.v1":
        raise FirstRunError("Unsupported installation-plan contract.")
    for key in (
        "plan_id",
        "node_id",
        "selected_profile",
        "resource_budget",
        "compute_node_capacity",
        "execution",
    ):
        if key not in plan:
            raise FirstRunError(f"Installation plan is missing {key}.")
    if plan.get("execution", {}).get("requires_confirmation") is not True:
        raise FirstRunError("Installation plan must require confirmation.")


def validate_manifest_against_plan(
    manifest: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    pairs = (
        ("plan_id", "plan_id"),
        ("node_id", "node_id"),
        ("selected_profile", "selected_profile"),
    )
    mismatches = [
        left
        for left, right in pairs
        if manifest.get(left) != plan.get(right)
    ]
    if mismatches:
        raise FirstRunError(
            "Installation manifest and plan disagree: "
            + ", ".join(mismatches)
        )


def validate_admin_username(value: str) -> str:
    username = value.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,31}", username):
        raise FirstRunError(
            "Administrator username must be 3-32 lowercase characters."
        )
    return username


def validate_node_name(value: str) -> str:
    node_name = " ".join(value.strip().split())
    if not 3 <= len(node_name) <= 80:
        raise FirstRunError("Node name must be 3-80 characters.")
    return node_name


def contains_forbidden_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_SECRET_KEYS:
                return True
            if contains_forbidden_secret(item):
                return True
    elif isinstance(value, list):
        return any(contains_forbidden_secret(item) for item in value)
    return False


def load_runtime_profile(
    catalog: dict[str, Any],
    installation_profile: str,
    requested: str | None,
    allow_network: bool,
) -> dict[str, Any]:
    profiles = catalog.get("profiles", [])
    if not isinstance(profiles, list) or not profiles:
        raise FirstRunError("Runtime catalog has no profiles.")

    candidates = []
    for profile in profiles:
        if installation_profile not in profile.get(
            "supported_installation_profiles",
            [],
        ):
            continue
        if requested and profile.get("profile_id") != requested:
            continue
        candidates.append(profile)

    if not candidates:
        raise FirstRunError(
            f"No runtime profile supports {installation_profile!r}."
        )

    candidates.sort(
        key=lambda item: (
            int(item.get("priority", 0)),
            str(item.get("profile_id", "")),
        ),
        reverse=True,
    )
    selected = dict(candidates[0])

    if selected.get("requires_external_network") and not allow_network:
        raise FirstRunError(
            "The selected runtime profile requires explicit network permission."
        )

    selected["network_permission_granted"] = bool(
        allow_network and selected.get("requires_external_network")
    )
    selected["external_network_contacted"] = False
    selected["container_daemon_contacted"] = False
    return selected


def build_documents(
    *,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    config: dict[str, Any],
    runtime_catalog: dict[str, Any],
    target_root: str,
    admin_username: str,
    admin_display_name: str,
    admin_email: str,
    node_name: str,
    runtime_profile: str | None,
    allow_network: bool,
    generated_at: str,
    state: str,
) -> dict[str, dict[str, Any]]:
    validate_plan(plan)
    validate_manifest_against_plan(manifest, plan)

    username = validate_admin_username(admin_username)
    display_name = " ".join(admin_display_name.strip().split())
    if not 1 <= len(display_name) <= 120:
        raise FirstRunError("Administrator display name is invalid.")
    email = admin_email.strip().lower()
    if email and not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        email,
    ):
        raise FirstRunError("Administrator email is invalid.")
    normalized_node_name = validate_node_name(node_name)

    runtime = load_runtime_profile(
        runtime_catalog,
        str(plan["selected_profile"]),
        runtime_profile,
        allow_network,
    )

    session_basis = {
        "installation_id": manifest["installation_id"],
        "plan_id": plan["plan_id"],
        "node_id": plan["node_id"],
        "administrator_username": username,
        "node_name": normalized_node_name,
        "runtime_profile": runtime["profile_id"],
        "target_root": str(target_root),
    }
    session_id = stable_id("first-run", session_basis)

    administrator = {
        "contract_version": CONTRACT_ADMIN,
        "session_id": session_id,
        "username": username,
        "display_name": display_name,
        "email": email or None,
        "role": "administrator",
        "credential_mode": config["administrator_credential_mode"],
        "credential_reference": f"operator-activation:{username}",
        "activation_required": True,
        "plaintext_secret_persisted": False,
        "created_at": generated_at,
    }

    node = {
        "contract_version": CONTRACT_NODE,
        "session_id": session_id,
        "node_id": plan["node_id"],
        "node_name": normalized_node_name,
        "node_role": "primary",
        "registration_mode": "local-bootstrap",
        "registration_state": "planned",
        "runtime_endpoint": "local-router",
        "external_network_required": False,
        "compute_node_capacity": plan["compute_node_capacity"],
        "created_at": generated_at,
    }

    runtime_selection = {
        "contract_version": CONTRACT_RUNTIME,
        "session_id": session_id,
        "profile_id": runtime["profile_id"],
        "provider_type": runtime["provider_type"],
        "acceleration": runtime["acceleration"],
        "model_runtime": runtime["model_runtime"],
        "chat_model": runtime["chat_model"],
        "embedding_model": runtime["embedding_model"],
        "speech_runtime": runtime["speech_runtime"],
        "network_permission_granted": runtime[
            "network_permission_granted"
        ],
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "created_at": generated_at,
    }

    configuration = {
        "contract_version": CONTRACT_CONFIGURATION,
        "session_id": session_id,
        "installation_id": manifest["installation_id"],
        "plan_id": plan["plan_id"],
        "node_id": plan["node_id"],
        "selected_profile": plan["selected_profile"],
        "administrator_username": username,
        "runtime_profile": runtime["profile_id"],
        "first_run_complete": state == "complete",
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "generated_at": generated_at,
    }

    readiness_checks = [
        {
            "check_id": "installation-manifest-present",
            "ok": True,
            "required": True,
        },
        {
            "check_id": "installation-plan-matches",
            "ok": True,
            "required": True,
        },
        {
            "check_id": "administrator-activation-deferred",
            "ok": administrator["activation_required"],
            "required": True,
        },
        {
            "check_id": "plaintext-secret-not-persisted",
            "ok": administrator["plaintext_secret_persisted"] is False,
            "required": True,
        },
        {
            "check_id": "node-registration-planned",
            "ok": node["registration_state"] == "planned",
            "required": True,
        },
        {
            "check_id": "runtime-selected",
            "ok": bool(runtime_selection["profile_id"]),
            "required": True,
        },
        {
            "check_id": "network-permission-consistent",
            "ok": (
                runtime["requires_external_network"]
                is False
                or runtime["network_permission_granted"] is True
            ),
            "required": True,
        },
    ]
    blockers = [
        item["check_id"]
        for item in readiness_checks
        if item["required"] and not item["ok"]
    ]

    readiness = {
        "contract_version": CONTRACT_READINESS,
        "session_id": session_id,
        "status": "ready" if not blockers else "blocked",
        "checks": readiness_checks,
        "blockers": blockers,
        "installer_handoff": {
            "installation_id": manifest["installation_id"],
            "plan_id": plan["plan_id"],
            "manifest_status": manifest["status"],
            "confirmation_required": True,
        },
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "generated_at": generated_at,
    }

    stages = []
    for sequence, stage_id in enumerate(config["stage_order"], start=1):
        if stage_id == "complete":
            stage_state = "complete" if state == "complete" else "pending"
        else:
            stage_state = "complete"
        stages.append(
            {
                "sequence": sequence,
                "stage_id": stage_id,
                "state": stage_state,
            }
        )

    session = {
        "contract_version": CONTRACT_SESSION,
        "session_id": session_id,
        "installation_id": manifest["installation_id"],
        "plan_id": plan["plan_id"],
        "node_id": plan["node_id"],
        "state": state,
        "current_stage": "complete" if state == "complete" else "readiness",
        "stages": stages,
        "resume_safe": True,
        "requires_confirmation": True,
        "confirmation_token": session_id,
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "created_at": generated_at,
        "updated_at": generated_at,
    }

    documents = {
        "config/first-run.json": configuration,
        "state/first-run-session.json": session,
        "state/administrator-bootstrap.json": administrator,
        "state/node-registration-plan.json": node,
        "state/runtime-selection.json": runtime_selection,
        "state/first-run-readiness.json": readiness,
    }
    if any(contains_forbidden_secret(value) for value in documents.values()):
        raise FirstRunError("Generated first-run documents contain secrets.")
    return documents


def atomic_replace(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{hashlib.sha256(content).hexdigest()[:8]}"
    )
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def exclusive_lock(path: Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise FirstRunError("A first-run operation is already active.") from exc
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def apply_documents(
    *,
    target: Path,
    documents: dict[str, dict[str, Any]],
    config: dict[str, Any],
    confirm: str,
    fail_after: int | None = None,
) -> dict[str, Any]:
    session = documents["state/first-run-session.json"]
    if confirm != session["session_id"]:
        raise FirstRunError(
            "First-run confirmation must equal the session ID."
        )

    snapshots: dict[str, tuple[bytes, int] | None] = {}
    changed: list[str] = []
    unchanged: list[str] = []
    lock_path = target / "runtime/first-run.lock"

    with exclusive_lock(lock_path):
        try:
            for sequence, (relative, document) in enumerate(
                documents.items(),
                start=1,
            ):
                path = target / relative
                desired = canonical_json(document)
                desired_mode = mode_from_text(
                    config["file_modes"][relative]
                )

                if path.is_file():
                    existing = path.read_bytes()
                    existing_mode = stat.S_IMODE(path.stat().st_mode)
                    if existing == desired and existing_mode == desired_mode:
                        unchanged.append(relative)
                        continue
                    snapshots[relative] = (existing, existing_mode)
                else:
                    snapshots[relative] = None

                atomic_replace(path, desired, desired_mode)
                changed.append(relative)

                if fail_after is not None and sequence >= fail_after:
                    raise InjectedFailure(
                        f"Injected first-run failure after {sequence} writes."
                    )
        except Exception:
            rollback_errors = []
            for relative in reversed(changed):
                path = target / relative
                snapshot = snapshots[relative]
                try:
                    if snapshot is None:
                        if path.exists():
                            path.unlink()
                    else:
                        atomic_replace(path, snapshot[0], snapshot[1])
                except Exception as exc:
                    rollback_errors.append(f"{relative}:{exc}")
            if rollback_errors:
                raise FirstRunError(
                    "First-run rollback failed: " + "; ".join(rollback_errors)
                )
            raise

    return {
        "changed_paths": changed,
        "unchanged_paths": unchanged,
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "idempotent": len(changed) == 0,
        "rollback_performed": False,
    }


def inspect_target(target: Path) -> dict[str, Any]:
    records = []
    errors = []
    for relative, contract in REQUIRED_OUTPUTS:
        path = target / relative
        if not path.is_file():
            records.append(
                {
                    "path": relative,
                    "exists": False,
                    "contract": None,
                    "ok": False,
                }
            )
            errors.append(f"missing:{relative}")
            continue
        try:
            value = load_object(path)
            contract_ok = value.get("contract_version") == contract
            secret_free = not contains_forbidden_secret(value)
            record_ok = contract_ok and secret_free
            records.append(
                {
                    "path": relative,
                    "exists": True,
                    "contract": value.get("contract_version"),
                    "sha256": sha256_file(path),
                    "secret_free": secret_free,
                    "ok": record_ok,
                }
            )
            if not record_ok:
                errors.append(f"invalid:{relative}")
        except Exception as exc:
            records.append(
                {
                    "path": relative,
                    "exists": True,
                    "ok": False,
                    "error": str(exc),
                }
            )
            errors.append(f"unreadable:{relative}")

    session_path = target / "state/first-run-session.json"
    session = load_object(session_path) if session_path.is_file() else {}
    readiness_path = target / "state/first-run-readiness.json"
    readiness = load_object(readiness_path) if readiness_path.is_file() else {}

    complete = (
        not errors
        and session.get("state") == "complete"
        and readiness.get("status") == "ready"
    )
    return {
        "ok": not errors,
        "contract_version": "leos.first-run-inspection.v1",
        "installed": (target / "state/installation-manifest.json").is_file(),
        "complete": complete,
        "session_id": session.get("session_id"),
        "readiness": readiness.get("status"),
        "record_count": len(records),
        "records": records,
        "error_count": len(errors),
        "errors": errors,
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "production_state_accessed": False,
        "production_network_attached": False,
    }


def common_inputs(args: argparse.Namespace) -> tuple[
    Path,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    target = normalize_target(args.target_root)
    config = load_object(
        Path(args.config),
        "leos.first-run-config.v1",
    )
    catalog = load_object(
        Path(args.runtime_catalog),
        "leos.first-run-runtime-catalog.v1",
    )
    plan_path = (
        Path(args.installation_plan)
        if args.installation_plan
        else target / "state/installation-plan.json"
    )
    plan = load_object(plan_path, "leos.installation-plan.v1")
    manifest = ensure_installed_target(target)
    return target, config, catalog, plan, manifest


def render_result(
    *,
    command: str,
    target: Path,
    documents: dict[str, dict[str, Any]],
    apply_record: dict[str, Any] | None,
) -> dict[str, Any]:
    session = documents["state/first-run-session.json"]
    readiness = documents["state/first-run-readiness.json"]
    return {
        "ok": True,
        "contract_version": CONTRACT_RESULT,
        "command": command,
        "state": (
            "complete"
            if command == "apply"
            else "planned"
        ),
        "session_id": session["session_id"],
        "confirmation_required": True,
        "confirmation_token": session["session_id"],
        "target_root": str(target),
        "readiness": readiness,
        "documents": documents,
        "changed": (
            bool(apply_record["changed_count"])
            if apply_record is not None
            else False
        ),
        "changed_count": (
            apply_record["changed_count"]
            if apply_record is not None
            else 0
        ),
        "unchanged_count": (
            apply_record["unchanged_count"]
            if apply_record is not None
            else 0
        ),
        "idempotent": (
            apply_record["idempotent"]
            if apply_record is not None
            else False
        ),
        "external_network_contacted": False,
        "container_daemon_contacted": False,
        "production_state_accessed": False,
        "production_network_attached": False,
        "plaintext_secret_persisted": False,
    }


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--installation-plan")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument(
        "--admin-display-name",
        default="LEOS Administrator",
    )
    parser.add_argument("--admin-email", default="")
    parser.add_argument(
        "--node-name",
        default="LEOS Primary Node",
    )
    parser.add_argument("--runtime-profile")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--generated-at")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
    )
    parser.add_argument(
        "--runtime-catalog",
        default=str(DEFAULT_RUNTIME_CATALOG),
    )
    parser.add_argument("--output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LEOS first-run initialization."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    planned = subparsers.add_parser(
        "plan",
        help="Build a non-mutating first-run plan.",
    )
    add_common_arguments(planned)

    apply = subparsers.add_parser(
        "apply",
        help="Apply a confirmed first-run plan.",
    )
    add_common_arguments(apply)
    apply.add_argument("--confirm", required=True)
    apply.add_argument("--fail-after", type=int)

    inspect = subparsers.add_parser(
        "inspect",
        help="Inspect first-run state.",
    )
    inspect.add_argument("--target-root", required=True)
    inspect.add_argument("--output")

    return parser


def emit(value: dict[str, Any], output: str | None) -> None:
    if output:
        write_json(Path(output), value)
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            target = normalize_target(args.target_root)
            result = inspect_target(target)
            emit(result, args.output)
            return 0 if result["ok"] else 1

        target, config, catalog, plan, manifest = common_inputs(args)
        generated_at = args.generated_at or utc_now()
        state = "complete" if args.command == "apply" else "planned"
        documents = build_documents(
            plan=plan,
            manifest=manifest,
            config=config,
            runtime_catalog=catalog,
            target_root=str(target),
            admin_username=args.admin_username,
            admin_display_name=args.admin_display_name,
            admin_email=args.admin_email,
            node_name=args.node_name,
            runtime_profile=args.runtime_profile,
            allow_network=args.allow_network,
            generated_at=generated_at,
            state=state,
        )

        apply_record = None
        if args.command == "apply":
            apply_record = apply_documents(
                target=target,
                documents=documents,
                config=config,
                confirm=args.confirm,
                fail_after=args.fail_after,
            )

        result = render_result(
            command=args.command,
            target=target,
            documents=documents,
            apply_record=apply_record,
        )
        emit(result, args.output)
        return 0
    except Exception as exc:
        failure = {
            "ok": False,
            "contract_version": "leos.first-run-error.v1",
            "command": args.command,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "external_network_contacted": False,
            "container_daemon_contacted": False,
            "production_state_accessed": False,
            "production_network_attached": False,
            "plaintext_secret_persisted": False,
        }
        emit(failure, getattr(args, "output", None))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
