#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw}
        return exc.code, body


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create, validate, and activate the LEOS reference research and content employee."
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("LEOS_ROOT", str(Path.cwd())),
    )
    parser.add_argument(
        "--registry-url",
        default=os.environ.get("EMPLOYEE_REGISTRY_URL", "http://employee-registry:8000"),
    )
    parser.add_argument("--actor", default="phase52.3-bootstrap")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    definition_path = root / "config" / "reference-research-content-employee.json"
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    employee_id = definition["employee_id"]
    base = args.registry_url.rstrip("/")

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "employee_id": employee_id,
            "definition": definition,
            "registry_url": base,
        }, indent=2, sort_keys=True))
        return 0

    operations: list[dict[str, Any]] = []
    status, current = request_json("GET", f"{base}/employees/{employee_id}")
    if status == 404:
        status, body = request_json(
            "POST",
            f"{base}/employees",
            {
                "definition": definition,
                "actor": args.actor,
                "reason": "phase52.3-reference-employee-bootstrap",
            },
        )
        operations.append({"operation": "create", "status": status, "body": body})
        if status not in {200, 201}:
            raise RuntimeError(f"Employee creation failed: HTTP {status}: {body}")
        current = body.get("employee", body)
    elif status != 200:
        raise RuntimeError(f"Employee lookup failed: HTTP {status}: {current}")

    state = current.get("lifecycle_state") or current.get("state") or current.get("status")
    if state == "draft":
        status, body = request_json(
            "POST",
            f"{base}/employees/{employee_id}/validate",
            {
                "actor": args.actor,
                "reason": "phase52.3-reference-employee-validation",
                "metadata": {"phase": "52.3"},
            },
        )
        operations.append({"operation": "validate", "status": status, "body": body})
        if status != 200:
            raise RuntimeError(f"Employee validation failed: HTTP {status}: {body}")
        current = body.get("employee", body)
        state = current.get("lifecycle_state") or current.get("state") or current.get("status")

    if state == "validated":
        status, body = request_json(
            "POST",
            f"{base}/employees/{employee_id}/activate",
            {
                "actor": args.actor,
                "reason": "phase52.3-reference-employee-activation",
                "metadata": {"phase": "52.3"},
            },
        )
        operations.append({"operation": "activate", "status": status, "body": body})
        if status != 200:
            raise RuntimeError(f"Employee activation failed: HTTP {status}: {body}")
        current = body.get("employee", body)
        state = current.get("lifecycle_state") or current.get("state") or current.get("status")

    if state != "active":
        raise RuntimeError(f"Reference employee did not reach active state: {state!r}")

    eligibility_status, eligibility = request_json(
        "GET", f"{base}/employees/{employee_id}/eligibility"
    )
    if eligibility_status != 200 or eligibility.get("eligible") is not True:
        raise RuntimeError(
            f"Reference employee is not execution eligible: HTTP {eligibility_status}: {eligibility}"
        )

    print(json.dumps({
        "ok": True,
        "employee_id": employee_id,
        "state": state,
        "eligibility": eligibility,
        "operations": operations,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
