from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "authorization-authority"))
sys.path.insert(0, str(ROOT / "packages" / "leos-contracts" / "src"))

from app.domain import (  # noqa: E402
    AUTHORITY_REF,
    AuthorizationAuthorityError,
    AuthorizationStore,
)
from leos_contracts import validate_contract  # noqa: E402

try:  # noqa: E402
    from fastapi.testclient import TestClient  # type: ignore
    from app import main  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised on lean hosts
    TestClient = None
    main = None


class DirectResponse:
    def __init__(
        self,
        status_code: int,
        body: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = text or json.dumps(self._body)

    def json(self) -> dict[str, Any]:
        return self._body


class DirectClient:
    """Host-compatible client when FastAPI is unavailable."""

    def __init__(self, store: AuthorizationStore) -> None:
        self.store = store

    def _call(self, operation) -> DirectResponse:
        try:
            return DirectResponse(200, operation())
        except AuthorizationAuthorityError as exc:
            return DirectResponse(exc.status_code, {"detail": exc.as_detail()})

    def get(self, path: str) -> DirectResponse:
        if path == "/health":
            return self._call(self.store.health)
        if path == "/ready":
            return self._call(self.store.ready)
        if path == "/version":
            return DirectResponse(200, {"ok": True, "service": "authorization-authority"})
        if path == "/outbox":
            return self._call(self.store.outbox)
        if path.startswith("/authorization-decisions/"):
            decision_id = path.removeprefix("/authorization-decisions/")
            return self._call(lambda: self.store.get_authorization_decision(decision_id))
        if path == "/authorization-decisions":
            return self._call(self.store.list_authorization_decisions)
        if path.startswith("/capability-permission-grants/"):
            grant_id = path.removeprefix("/capability-permission-grants/")
            return self._call(lambda: self.store.get_capability_grant(grant_id))
        if path == "/capability-permission-grants":
            return self._call(self.store.list_capability_grants)
        return DirectResponse(404, {"detail": {"code": "not_found"}})

    def post(self, path: str, json: dict[str, Any]) -> DirectResponse:
        if path == "/authorization-decisions":
            return self._call(lambda: self.store.create_authorization_decision(json))
        if path.endswith("/verify") and path.startswith("/authorization-decisions/"):
            decision_id = path.removeprefix("/authorization-decisions/").removesuffix("/verify")
            return self._call(lambda: self.store.verify_authorization_decision(decision_id, json))
        if path.endswith("/revoke") and path.startswith("/authorization-decisions/"):
            decision_id = path.removeprefix("/authorization-decisions/").removesuffix("/revoke")
            return self._call(lambda: self.store.revoke_authorization_decision(decision_id, json))
        if path == "/capability-permission-grants":
            return self._call(lambda: self.store.issue_capability_grant(json))
        if path.endswith("/revoke") and path.startswith("/capability-permission-grants/"):
            grant_id = path.removeprefix("/capability-permission-grants/").removesuffix("/revoke")
            return self._call(lambda: self.store.revoke_capability_grant(grant_id, json))
        return DirectResponse(404, {"detail": {"code": "not_found"}})

    def delete(self, path: str) -> DirectResponse:
        return DirectResponse(405, {"detail": {"code": "method_not_allowed"}})


def actor_context_ref() -> dict[str, Any]:
    return {
        "evidence_type": "ACTOR_CONTEXT",
        "authority": {
            "authority_id": "identity-authority",
            "principal": {
                "principal_id": "principal:service:identity-authority",
                "principal_type": "SERVICE",
            },
            "authority_revision": "sha256:identity-authority-policy-v1",
        },
        "reference_id": "actor-context:brett:session-001",
        "revision": "sha256:actor-context-brett-session-001",
    }


def organization_ref(revision: str = "sha256:organization-acme-v1") -> dict[str, str]:
    return {
        "resource_type": "ORGANIZATION",
        "resource_id": "organization:acme",
        "revision": revision,
    }


def subject() -> dict[str, str]:
    return {
        "principal_id": "principal:user:brett",
        "principal_type": "HUMAN_USER",
    }


def resource() -> dict[str, str]:
    return {
        "resource_type": "PROVIDER",
        "resource_id": "provider:local:synthetic",
        "revision": "sha256:provider-local-synthetic-v1",
    }


def capability_ref() -> dict[str, str]:
    return {
        "resource_type": "CAPABILITY",
        "resource_id": "capability:model.chat",
        "revision": "sha256:capability-model-chat-v1",
    }


def context() -> dict[str, str]:
    return {
        "context_type": "execution",
        "context_id": "execution:synthetic:001",
        "context_revision": "sha256:execution-synthetic-request-v1",
        "context_digest": "sha256:" + "a" * 64,
    }


def grant_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "idempotency_key": "idem:grant:1",
        "grant_id": "capability-permission-grant:acme:brett:provider-invoke",
        "actor_context_ref": actor_context_ref(),
        "organization_ref": organization_ref(),
        "subject": subject(),
        "action": "provider.invoke",
        "resource": resource(),
        "capability_ref": capability_ref(),
        "policy_version": "dev-preview-v2-minimum",
        "issued_at": "2026-07-26T12:00:00Z",
        "valid_from": "2026-07-26T12:00:00Z",
        "valid_until": "2099-07-26T13:00:00Z",
        "grant_basis_refs": [
            {
                "authority": AUTHORITY_REF,
                "reference_id": "authority-mandate:authorization-grant-issuance",
                "revision": "sha256:authorization-grant-issuance-v1",
            }
        ],
    }
    payload.update(overrides)
    return payload


def decision_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "idempotency_key": "idem:decision:1",
        "decision_id": "authorization-decision:acme:provider-invoke:1",
        "actor_context_ref": actor_context_ref(),
        "organization_ref": organization_ref(),
        "subject": subject(),
        "action": "provider.invoke",
        "resource": resource(),
        "capability_ref": capability_ref(),
        "context": context(),
        "policy_version": "dev-preview-v2-minimum",
        "evaluation_timestamp": "2026-07-26T12:05:00Z",
        "valid_until": "2099-07-26T12:10:00Z",
    }
    payload.update(overrides)
    return payload


class AuthorizationAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AuthorizationStore(Path(self.tmp.name) / "authorization.db")
        if TestClient is not None and main is not None:
            main.store = self.store
            self.client = TestClient(main.app)
        else:
            self.client = DirectClient(self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def issue_grant(self, **overrides: Any) -> dict[str, Any]:
        response = self.client.post(
            "/capability-permission-grants",
            json=grant_payload(**overrides),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["grant"]

    def create_decision(self, **overrides: Any) -> dict[str, Any]:
        response = self.client.post("/authorization-decisions", json=decision_payload(**overrides))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["authorization_decision"]

    def test_health_ready_version(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 200)
        version = self.client.get("/version")
        self.assertEqual(version.status_code, 200)
        self.assertEqual(version.json()["service"], "authorization-authority")

    def test_default_deny_without_grant(self) -> None:
        decision = self.create_decision()
        self.assertEqual(decision["decision"], "DENY")
        self.assertEqual(decision["authority_evidence_refs"], [])
        self.assertEqual(decision["reasons"], ["no_active_capability_permission_grant"])
        validate_contract("leos.authorization-decision.v1", decision)

    def test_exact_active_grant_allows_authorization_decision(self) -> None:
        grant = self.issue_grant()
        decision = self.create_decision()
        self.assertEqual(decision["decision"], "ALLOW")
        self.assertEqual(decision["authority_evidence_refs"][0]["reference_id"], grant["grant_id"])
        self.assertEqual(decision["authority"], AUTHORITY_REF)
        validate_contract("leos.authorization-decision.v1", decision)

    def test_wrong_organization_grant_does_not_authorize(self) -> None:
        self.issue_grant()
        decision = self.create_decision(
            idempotency_key="idem:decision:wrong-org",
            decision_id="authorization-decision:acme:provider-invoke:wrong-org",
            organization_ref=organization_ref("sha256:organization-acme-v2"),
        )
        self.assertEqual(decision["decision"], "DENY")

    def test_wrong_capability_grant_does_not_authorize(self) -> None:
        self.issue_grant(
            capability_ref={
                "resource_type": "CAPABILITY",
                "resource_id": "capability:ocr",
                "revision": "sha256:capability-ocr-v1",
            }
        )
        decision = self.create_decision()
        self.assertEqual(decision["decision"], "DENY")

    def test_revoked_grant_causes_later_denial(self) -> None:
        self.issue_grant()
        revoke = self.client.post(
            "/capability-permission-grants/capability-permission-grant:acme:brett:provider-invoke/revoke",
            json={
                "actor_context_ref": actor_context_ref(),
                "reason": "operator revoked",
                "revoked_at": "2026-07-26T12:03:00Z",
                "idempotency_key": "idem:grant-revoke:1",
            },
        )
        self.assertEqual(revoke.status_code, 200, revoke.text)
        decision = self.create_decision()
        self.assertEqual(decision["decision"], "DENY")

    def test_expired_grant_causes_denial(self) -> None:
        self.issue_grant(valid_until="2026-07-26T12:02:00Z")
        decision = self.create_decision()
        self.assertEqual(decision["decision"], "DENY")

    def test_verification_accepts_stored_current_decision(self) -> None:
        self.issue_grant()
        decision = self.create_decision()
        response = self.client.post(
            "/authorization-decisions/authorization-decision:acme:provider-invoke:1/verify",
            json={
                "actor_context_ref": actor_context_ref(),
                "organization_ref": organization_ref(),
                "scope": decision["scope"],
                "expected_decision": "ALLOW",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["verification_status"], "VERIFIED")

    def test_verification_rejects_scope_mismatch(self) -> None:
        self.issue_grant()
        decision = self.create_decision()
        mismatched_scope = dict(decision["scope"])
        mismatched_scope["context_id"] = "execution:synthetic:other"
        response = self.client.post(
            "/authorization-decisions/authorization-decision:acme:provider-invoke:1/verify",
            json={
                "actor_context_ref": actor_context_ref(),
                "organization_ref": organization_ref(),
                "scope": mismatched_scope,
                "expected_decision": "ALLOW",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["verification_status"], "DENIED")
        self.assertIn("scope_mismatch", response.json()["reasons"])

    def test_verification_rejects_cross_organization_scope(self) -> None:
        self.issue_grant()
        decision = self.create_decision()
        response = self.client.post(
            "/authorization-decisions/authorization-decision:acme:provider-invoke:1/verify",
            json={
                "actor_context_ref": actor_context_ref(),
                "organization_ref": {
                    "resource_type": "ORGANIZATION",
                    "resource_id": "organization:other",
                    "revision": "sha256:organization-other-v1",
                },
                "scope": decision["scope"],
                "expected_decision": "ALLOW",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["verification_status"], "DENIED")
        self.assertIn("organization_scope_mismatch", response.json()["reasons"])

    def test_revoked_decision_fails_verification(self) -> None:
        self.issue_grant()
        decision = self.create_decision()
        revoke = self.client.post(
            "/authorization-decisions/authorization-decision:acme:provider-invoke:1/revoke",
            json={
                "actor_context_ref": actor_context_ref(),
                "reason": "operator revoked",
                "revoked_at": "2026-07-26T12:06:00Z",
                "idempotency_key": "idem:decision-revoke:1",
            },
        )
        self.assertEqual(revoke.status_code, 200, revoke.text)
        response = self.client.post(
            "/authorization-decisions/authorization-decision:acme:provider-invoke:1/verify",
            json={
                "actor_context_ref": actor_context_ref(),
                "organization_ref": organization_ref(),
                "scope": decision["scope"],
                "expected_decision": "ALLOW",
            },
        )
        self.assertEqual(response.json()["verification_status"], "DENIED")
        self.assertIn("authorization_decision_revoked", response.json()["reasons"])

    def test_expired_decision_fails_verification(self) -> None:
        self.issue_grant()
        decision = self.create_decision(valid_until="2026-07-26T12:05:01Z")
        response = self.client.post(
            "/authorization-decisions/authorization-decision:acme:provider-invoke:1/verify",
            json={
                "actor_context_ref": actor_context_ref(),
                "organization_ref": organization_ref(),
                "scope": decision["scope"],
                "expected_decision": "ALLOW",
            },
        )
        self.assertEqual(response.json()["verification_status"], "DENIED")
        self.assertIn("authorization_decision_expired", response.json()["reasons"])

    def test_idempotency_replays_same_response_and_rejects_conflict(self) -> None:
        payload = grant_payload()
        first = self.client.post("/capability-permission-grants", json=payload)
        second = self.client.post("/capability-permission-grants", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json(), second.json())
        changed = dict(payload)
        changed["action"] = "provider.read"
        conflict = self.client.post("/capability-permission-grants", json=changed)
        self.assertEqual(conflict.status_code, 409)

    def test_caller_authorization_boolean_is_rejected(self) -> None:
        response = self.client.post(
            "/authorization-decisions",
            json=decision_payload(authorized=True),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "caller_authority_boolean_rejected")

    def test_caller_approval_boolean_is_rejected(self) -> None:
        response = self.client.post(
            "/capability-permission-grants",
            json=grant_payload(approved=True),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "caller_authority_boolean_rejected")

    def test_role_membership_capability_and_plugin_shortcuts_are_rejected(self) -> None:
        for key in (
            "role_ref",
            "membership_ref",
            "capability_present",
            "plugin_installation_ref",
        ):
            with self.subTest(key=key):
                response = self.client.post(
                    "/authorization-decisions",
                    json=decision_payload(idempotency_key=f"idem:shortcut:{key}", **{key: "fake"}),
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "permission_shortcut_rejected",
                )

    def test_client_issued_authorization_decision_json_is_rejected(self) -> None:
        response = self.client.post(
            "/authorization-decisions/authorization-decision:fake/verify",
            json={
                "actor_context_ref": actor_context_ref(),
                "organization_ref": organization_ref(),
                "scope": {
                    "subject": subject(),
                    "action": "provider.invoke",
                    "resource": resource(),
                    **context(),
                },
                "authorization_decision": {
                    "contract_version": "leos.authorization-decision.v1",
                    "decision": "ALLOW",
                },
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "client_authorization_decision_rejected",
        )

    def test_malformed_actor_context_ref_is_rejected(self) -> None:
        bad_actor = actor_context_ref()
        bad_actor["evidence_type"] = "NOT_ACTOR_CONTEXT"
        response = self.client.post(
            "/authorization-decisions",
            json=decision_payload(actor_context_ref=bad_actor),
        )
        self.assertEqual(response.status_code, 422)

    def test_malformed_resource_is_rejected(self) -> None:
        bad_resource = resource()
        bad_resource.pop("revision")
        response = self.client.post(
            "/authorization-decisions",
            json=decision_payload(resource=bad_resource),
        )
        self.assertEqual(response.status_code, 422)

    def test_raw_secret_is_rejected(self) -> None:
        response = self.client.post(
            "/capability-permission-grants",
            json=grant_payload(api_key=True),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "raw_secret_prohibited")

    def test_outbox_records_are_producer_local(self) -> None:
        self.issue_grant()
        self.create_decision()
        events = self.client.get("/outbox").json()["events"]
        self.assertEqual([event["event_type"] for event in events], [
            "authorization.capability_grant.issued",
            "authorization.decision.created",
        ])
        self.assertTrue(all(event["authority"] == AUTHORITY_REF for event in events))

    def test_no_hard_delete_path(self) -> None:
        response = self.client.delete(
            "/capability-permission-grants/capability-permission-grant:acme:brett:provider-invoke"
        )
        self.assertEqual(response.status_code, 405)

    def test_no_dispatch_or_capability_resolution_endpoints_exist(self) -> None:
        self.assertEqual(self.client.get("/capability-resolution").status_code, 404)
        self.assertEqual(self.client.get("/dispatch").status_code, 404)

    def test_state_history_idempotency_and_outbox_are_atomic(self) -> None:
        self.issue_grant()
        with sqlite3.connect(Path(self.tmp.name) / "authorization.db") as connection:
            grant_count = connection.execute(
                "SELECT COUNT(*) FROM capability_permission_grants"
            ).fetchone()[0]
            idempotency_count = connection.execute(
                "SELECT COUNT(*) FROM idempotency_keys"
            ).fetchone()[0]
            outbox_count = connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        self.assertEqual(grant_count, 1)
        self.assertEqual(idempotency_count, 1)
        self.assertEqual(outbox_count, 1)


if __name__ == "__main__":
    unittest.main()
