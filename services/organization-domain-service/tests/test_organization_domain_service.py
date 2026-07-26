from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "services" / "organization-domain-service"
PACKAGE_SRC = ROOT / "packages" / "leos-contracts" / "src"
EXAMPLES = ROOT / "examples"

TEST_DATA = tempfile.TemporaryDirectory()
os.environ["LEOS_ORGANIZATION_DOMAIN_DATA_DIR"] = TEST_DATA.name
os.environ["LEOS_ORGANIZATION_DOMAIN_DB"] = str(Path(TEST_DATA.name) / "organization-domain.db")
os.environ["LEOS_CONTRACT_ROOT"] = str(ROOT / "contracts")
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(PACKAGE_SRC))

from app import main  # noqa: E402
from app.domain import (  # noqa: E402
    OrganizationDomainStore,
    StaticEmployeeReferenceAdapter,
    revision_for,
)


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def auth_ref(record: dict) -> dict:
    evidence = record["identity"]["creation_authority_evidence_ref"]
    return {
        "resource_type": "AUTHORIZATION_DECISION",
        "resource_id": evidence["reference_id"],
        "revision": evidence["revision"],
    }


def actor_evidence_ref(record: dict) -> dict:
    actor = record["identity"]["creation_actor_context_ref"]
    return {
        "evidence_type": "ACTOR_CONTEXT",
        "authority": {
            "authority_id": "identity-authority",
            "principal": {
                "principal_id": "principal:service:identity-authority",
                "principal_type": "SERVICE",
            },
            "authority_revision": "sha256:identity-authority-v1",
        },
        "reference_id": actor["resource_id"],
        "revision": actor["revision"],
    }


def envelope(record: dict, *, key: str | None = None) -> dict:
    return {
        "record": record,
        "actor_context_ref": actor_evidence_ref(record),
        "authorization_decision_ref": auth_ref(record),
        "idempotency_key": key,
        "correlation_id": f"correlation:{record['identity']['resource_id']}",
    }


class OrganizationDomainServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        TEST_DATA.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "organization-domain.db"
        self.employee = example("employee-definition.v3.json")
        self.store = OrganizationDomainStore(
            self.database,
            employee_adapter=StaticEmployeeReferenceAdapter([self.employee]),
        )
        main.store = self.store
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create(self, filename: str, collection: str) -> dict:
        record = example(filename)
        response = self.client.post(
            f"/{collection}",
            json=envelope(record, key=f"create:{record['identity']['resource_id']}"),
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["record"]

    def bootstrap_structure(self) -> dict[str, dict]:
        records = {
            "organization": self.create("organization.v1.json", "organizations"),
            "department": self.create("department.v1.json", "departments"),
            "role": self.create("role.v1.json", "roles"),
            "team": self.create("team.v1.json", "teams"),
            "position": self.create("position.v1.json", "positions"),
        }
        return records

    def bootstrap_all(self) -> dict[str, dict]:
        records = self.bootstrap_structure()
        organization_membership = example("membership.v1.json")
        organization_membership["identity"]["resource_id"] = (
            "membership:acme:researcher:organization"
        )
        organization_membership["identity"]["display_name"] = (
            "Researcher membership in Acme Research"
        )
        organization_membership["identity"]["revision"] = (
            "sha256:membership-acme-researcher-organization-v1"
        )
        organization_membership["identity"]["audit_id"] = (
            "audit:membership:acme:researcher:organization:v1"
        )
        organization_membership["membership_kind"] = "EMPLOYEE_ORGANIZATION"
        organization_membership["container_ref"] = {
            "resource_type": "ORGANIZATION",
            "resource_id": "organization:acme",
            "revision": "sha256:organization-acme-v1",
        }
        records["organization_membership"] = self.client.post(
            "/memberships",
            json=envelope(organization_membership, key="create:org-membership"),
        ).json()["record"]
        records["team_membership"] = self.create("membership.v1.json", "memberships")
        records["occupancy"] = self.create(
            "position-occupancy.v1.json",
            "position-occupancies",
        )
        return records

    def test_health_ready_and_version(self):
        self.assertEqual(200, self.client.get("/health").status_code)
        self.assertEqual("ready", self.client.get("/ready").json()["state"])
        self.assertEqual(
            "organization-domain-service",
            self.client.get("/version").json()["service"],
        )

    def test_create_read_and_scoped_list_all_record_types(self):
        self.bootstrap_all()
        response = self.client.get(
            "/teams/team:acme:market-research",
            params={"organization_id": "organization:acme"},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("TEAM", response.json()["record"]["identity"]["resource_type"])

        listed = self.client.get(
            "/memberships",
            params={"organization_id": "organization:acme"},
        ).json()
        self.assertEqual(2, listed["count"])

    def test_create_is_idempotent_and_conflicting_duplicate_rejected(self):
        record = example("organization.v1.json")
        request = envelope(record, key="idempotent-create")
        first = self.client.post("/organizations", json=request)
        second = self.client.post("/organizations", json=request)
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(first.json(), second.json())

        changed = copy.deepcopy(record)
        changed["description"] = "Different organization description."
        response = self.client.post("/organizations", json=envelope(changed))
        self.assertEqual(409, response.status_code)
        self.assertEqual("duplicate_resource_identity", response.json()["detail"]["code"])

    def test_update_requires_stale_write_protection_and_preserves_history(self):
        before = self.create("organization.v1.json", "organizations")
        after = copy.deepcopy(before)
        after["description"] = "Updated through the Organization Domain Service."
        after["identity"]["updated_at"] = "2026-07-25T18:00:00Z"
        after["identity"]["revision"] = revision_for(after)
        request = envelope(after, key="update-organization")
        request["expected_revision"] = before["identity"]["revision"]

        response = self.client.patch(
            f"/organizations/{before['identity']['resource_id']}",
            json=request,
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertNotEqual(
            before["identity"]["revision"],
            response.json()["record"]["identity"]["revision"],
        )
        audit = self.client.get(
            f"/audit/ORGANIZATION/{before['identity']['resource_id']}"
        ).json()
        self.assertEqual(["CREATE", "UPDATE"], [row["operation"] for row in audit["audit"]])

        stale_request = copy.deepcopy(request)
        stale_request["idempotency_key"] = "stale-update-organization"
        stale = self.client.patch(
            f"/organizations/{before['identity']['resource_id']}",
            json=stale_request,
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("stale_revision", stale.json()["detail"]["code"])

    def test_status_change_requires_lifecycle_transition(self):
        before = self.create("organization.v1.json", "organizations")
        updated = copy.deepcopy(before)
        updated["status"] = "SUSPENDED"
        updated["identity"]["revision"] = "sha256:attempted-status-update"
        request = envelope(updated)
        request["expected_revision"] = before["identity"]["revision"]
        response = self.client.patch(
            f"/organizations/{before['identity']['resource_id']}",
            json=request,
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual("illegal_lifecycle_transition", response.json()["detail"]["code"])

    def test_lifecycle_transition_updates_record_outbox_and_transition_log_atomically(self):
        before = self.create("organization.v1.json", "organizations")
        request = {
            "expected_revision": before["identity"]["revision"],
            "to_status": "SUSPENDED",
            "actor_context_ref": actor_evidence_ref(before),
            "authorization_decision_ref": auth_ref(before),
            "idempotency_key": "transition-org-suspend",
            "correlation_id": "correlation:transition-org-suspend",
        }
        response = self.client.post(
            f"/organizations/{before['identity']['resource_id']}/transition",
            json=request,
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("SUSPENDED", body["record"]["status"])
        self.assertEqual(
            body["record"]["identity"]["revision"],
            body["transition"]["resulting_revision"],
        )
        self.assertEqual(2, self.client.get("/outbox").json()["count"])
        self.assertEqual(1, self.client.get("/transitions").json()["count"])

        reopened = OrganizationDomainStore(
            self.database,
            employee_adapter=StaticEmployeeReferenceAdapter([self.employee]),
        )
        self.assertEqual(
            "SUSPENDED",
            reopened.get("ORGANIZATION", "organization:acme")["record"]["status"],
        )

    def test_illegal_lifecycle_transition_is_rejected(self):
        before = self.create("organization.v1.json", "organizations")
        response = self.client.post(
            f"/organizations/{before['identity']['resource_id']}/transition",
            json={
                "expected_revision": before["identity"]["revision"],
                "to_status": "DELETED",
                "actor_context_ref": actor_evidence_ref(before),
                "authorization_decision_ref": auth_ref(before),
            },
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual("illegal_lifecycle_transition", response.json()["detail"]["code"])

    def test_cross_organization_reference_fails_closed(self):
        self.bootstrap_structure()
        other = copy.deepcopy(example("organization.v1.json"))
        other["identity"]["resource_id"] = "organization:other"
        other["identity"]["revision"] = "sha256:organization-other-v1"
        other["identity"]["audit_id"] = "audit:organization:other:v1"
        other["organization_principal_ref"]["principal_id"] = "principal:organization:other"
        self.assertEqual(200, self.client.post("/organizations", json=envelope(other)).status_code)

        team = copy.deepcopy(example("team.v1.json"))
        team["identity"]["resource_id"] = "team:other:leaky"
        team["identity"]["revision"] = "sha256:team-other-leaky-v1"
        team["identity"]["audit_id"] = "audit:team:other:leaky:v1"
        team["organization_ref"] = {
            "resource_type": "ORGANIZATION",
            "resource_id": "organization:other",
            "revision": "sha256:organization-other-v1",
        }
        response = self.client.post("/teams", json=envelope(team))
        self.assertEqual(422, response.status_code)
        self.assertEqual("validation_failure", response.json()["detail"]["code"])

    def test_wrong_organization_context_cannot_fetch_record(self):
        self.bootstrap_structure()
        response = self.client.get(
            "/teams/team:acme:market-research",
            params={"organization_id": "organization:other"},
        )
        self.assertEqual(404, response.status_code)

    def test_duplicate_active_membership_is_rejected(self):
        records = self.bootstrap_all()
        duplicate = copy.deepcopy(records["team_membership"])
        duplicate["identity"]["resource_id"] = "membership:duplicate"
        duplicate["identity"]["revision"] = "sha256:membership-duplicate-v1"
        duplicate["identity"]["audit_id"] = "audit:membership:duplicate:v1"
        response = self.client.post("/memberships", json=envelope(duplicate))
        self.assertEqual(422, response.status_code)

    def test_duplicate_active_occupancy_is_rejected(self):
        records = self.bootstrap_all()
        duplicate = copy.deepcopy(records["occupancy"])
        duplicate["identity"]["resource_id"] = "position-occupancy:duplicate"
        duplicate["identity"]["revision"] = "sha256:position-occupancy-duplicate-v1"
        duplicate["identity"]["audit_id"] = "audit:position-occupancy:duplicate:v1"
        response = self.client.post("/position-occupancies", json=envelope(duplicate))
        self.assertEqual(422, response.status_code)

    def test_employee_registry_unavailable_fails_closed_for_employee_relationships(self):
        self.store = OrganizationDomainStore(self.database)
        main.store = self.store
        self.client = TestClient(main.app)
        self.bootstrap_structure()
        response = self.client.post(
            "/memberships",
            json=envelope(example("membership.v1.json")),
        )
        self.assertEqual(503, response.status_code)
        self.assertEqual("dependency_unavailable", response.json()["detail"]["code"])

    def test_missing_actor_or_authorization_evidence_fails_closed(self):
        record = example("organization.v1.json")
        for removed, expected_code in (
            ("actor_context_ref", "missing_actor_context"),
            ("authorization_decision_ref", "missing_authorization_evidence"),
        ):
            request = envelope(record)
            request.pop(removed)
            with self.subTest(removed=removed):
                response = self.client.post("/organizations", json=request)
                self.assertIn(response.status_code, {401, 403})
                self.assertEqual(expected_code, response.json()["detail"]["code"])

    def test_caller_authority_boolean_is_rejected(self):
        request = envelope(example("organization.v1.json"))
        request["authorized"] = True
        response = self.client.post("/organizations", json=request)
        self.assertEqual(403, response.status_code)
        self.assertEqual("caller_authority_claim_rejected", response.json()["detail"]["code"])

    def test_raw_credentials_or_secrets_are_rejected(self):
        request = envelope(example("organization.v1.json"))
        request["record"]["metadata"]["labels"]["api_key"] = "not-allowed"
        response = self.client.post("/organizations", json=request)
        self.assertEqual(422, response.status_code)
        self.assertEqual("raw_secret_prohibited", response.json()["detail"]["code"])

    def test_failed_mutation_rolls_back_state_and_outbox(self):
        self.create("organization.v1.json", "organizations")
        bad_department = copy.deepcopy(example("department.v1.json"))
        bad_department["parent_department_ref"] = {
            "resource_type": "DEPARTMENT",
            "resource_id": "department:missing",
            "revision": "sha256:missing",
        }
        response = self.client.post("/departments", json=envelope(bad_department))
        self.assertEqual(422, response.status_code)

        with sqlite3.connect(self.database) as db:
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM organization_records WHERE resource_type = 'DEPARTMENT'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1,
                db.execute("SELECT COUNT(*) FROM organization_outbox").fetchone()[0],
            )


if __name__ == "__main__":
    unittest.main()
