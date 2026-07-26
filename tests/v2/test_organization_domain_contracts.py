from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = ROOT / "packages" / "leos-contracts" / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from leos_contracts import (  # noqa: E402
    ContractValidationError,
    validate_contract,
    validate_organization_domain,
)

EXAMPLES = ROOT / "examples"
OBSERVED_AT = "2026-07-25T17:00:00Z"

CONTRACT_EXAMPLES = {
    "leos.organization.v1": "organization.v1.json",
    "leos.department.v1": "department.v1.json",
    "leos.team.v1": "team.v1.json",
    "leos.role.v1": "role.v1.json",
    "leos.position.v1": "position.v1.json",
    "leos.employee-definition.v3": "employee-definition.v3.json",
    "leos.membership.v1": "membership.v1.json",
    "leos.position-occupancy.v1": "position-occupancy.v1.json",
    "leos.organization-lifecycle-transition.v1":
        "organization-lifecycle-transition.v1.json",
}


def read_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class OrganizationDomainContractTests(unittest.TestCase):
    def example(self, contract: str) -> dict[str, Any]:
        return copy.deepcopy(read_example(CONTRACT_EXAMPLES[contract]))

    def assert_invalid(self, contract: str, value: Any) -> None:
        with self.assertRaises(ContractValidationError):
            validate_contract(contract, value)

    def organization_membership(self) -> dict[str, Any]:
        value = self.example("leos.membership.v1")
        value["identity"]["resource_id"] = (
            "membership:acme:researcher:organization"
        )
        value["identity"]["display_name"] = (
            "Researcher membership in Acme Research"
        )
        value["identity"]["revision"] = (
            "sha256:membership-acme-researcher-organization-v1"
        )
        value["identity"]["audit_id"] = (
            "audit:membership:acme:researcher:organization:v1"
        )
        value["membership_kind"] = "EMPLOYEE_ORGANIZATION"
        value["container_ref"] = {
            "resource_type": "ORGANIZATION",
            "resource_id": "organization:acme",
            "revision": "sha256:organization-acme-v1",
        }
        return value

    def bundle(self) -> list[dict[str, Any]]:
        return [
            self.example("leos.organization.v1"),
            self.example("leos.department.v1"),
            self.example("leos.role.v1"),
            self.example("leos.team.v1"),
            self.example("leos.position.v1"),
            self.example("leos.employee-definition.v3"),
            self.organization_membership(),
            self.example("leos.membership.v1"),
            self.example("leos.position-occupancy.v1"),
            self.example("leos.organization-lifecycle-transition.v1"),
            read_example("organization-event-envelope.v1.json"),
        ]

    def assert_bundle_invalid(self, value: list[dict[str, Any]]) -> None:
        with self.assertRaises(ContractValidationError):
            validate_organization_domain(value, observed_at=OBSERVED_AT)

    def test_all_examples_validate(self):
        for contract in CONTRACT_EXAMPLES:
            with self.subTest(contract=contract):
                validate_contract(contract, self.example(contract))
        validate_contract(
            "leos.event-envelope.v1",
            read_example("organization-event-envelope.v1.json"),
        )

    def test_all_schemas_are_draft_2020_12_and_unique(self):
        names = [
            "organization-common.v1.schema.json",
            *(
                contract.removeprefix("leos.") + ".schema.json"
                for contract in CONTRACT_EXAMPLES
            ),
        ]
        identifiers = []
        for name in names:
            schema = json.loads(
                (ROOT / "contracts" / name).read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(schema)
            identifiers.append(schema["$id"])
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_complete_reference_bundle_validates(self):
        validate_organization_domain(self.bundle(), observed_at=OBSERVED_AT)

    def test_team_without_organization_is_rejected(self):
        value = self.example("leos.team.v1")
        value.pop("organization_ref")
        self.assert_invalid("leos.team.v1", value)

    def test_employee_without_owner_is_rejected(self):
        value = self.example("leos.employee-definition.v3")
        value["identity"]["ownership"].pop("owner")
        self.assert_invalid("leos.employee-definition.v3", value)

    def test_multiple_organization_ownership_is_rejected(self):
        value = self.example("leos.organization.v1")
        value["identity"]["ownership"]["owner"] = [
            value["identity"]["ownership"]["owner"],
            value["identity"]["ownership"]["owner"],
        ]
        self.assert_invalid("leos.organization.v1", value)

    def test_child_owner_must_be_organization_principal(self):
        value = self.bundle()
        value[1]["identity"]["ownership"]["owner"] = {
            "principal_id": "principal:user:brett",
            "principal_type": "HUMAN_USER",
        }
        self.assert_bundle_invalid(value)

    def test_orphan_creation_is_rejected(self):
        value = self.bundle()
        value.pop(0)
        self.assert_bundle_invalid(value)

    def test_stale_revision_reference_is_rejected(self):
        value = self.bundle()
        value[3]["department_ref"]["revision"] = "sha256:stale"
        self.assert_bundle_invalid(value)

    def test_transition_result_must_match_canonical_revision_and_status(self):
        for field, replacement in (
            ("resulting_revision", "sha256:not-the-current-revision"),
            ("to_status", "SUSPENDED"),
        ):
            value = self.bundle()
            value[9][field] = replacement
            with self.subTest(field=field):
                self.assert_bundle_invalid(value)

    def test_transition_and_event_owner_must_match_subject_owner(self):
        for index in (9, 10):
            value = self.bundle()
            value[index]["identity"]["ownership"]["owner"] = {
                "principal_id": "principal:organization:acme",
                "principal_type": "ORGANIZATION",
            }
            with self.subTest(index=index):
                self.assert_bundle_invalid(value)

    def test_transition_and_event_authority_must_match_subject_authority(self):
        for index in (9, 10):
            value = self.bundle()
            value[index]["identity"]["ownership"]["lifecycle_authority"][
                "authority_id"
            ] = "peer-organization-authority"
            with self.subTest(index=index):
                self.assert_bundle_invalid(value)

    def test_transition_and_event_are_produced_by_subject_authority(self):
        for index in (9, 10):
            for field in ("creator", "steward"):
                value = self.bundle()
                value[index]["identity"]["ownership"][field] = {
                    "principal_id": "principal:user:brett",
                    "principal_type": "HUMAN_USER",
                }
                with self.subTest(index=index, field=field):
                    self.assert_bundle_invalid(value)

    def test_transition_event_must_be_present_and_exact(self):
        value = self.bundle()
        value.pop(10)
        self.assert_bundle_invalid(value)

        value = self.bundle()
        value[10]["payload"]["to_status"] = "SUSPENDED"
        self.assert_bundle_invalid(value)

    def test_transition_event_authority_evidence_is_linked(self):
        mutations = (
            (
                ("identity", "creation_authority_evidence_ref", "reference_id"),
                "organization-transition:other",
            ),
            (
                ("actor_context_ref", "reference_id"),
                "actor-context:other",
            ),
            (
                ("causation", "reference_id"),
                "authorization-decision:other",
            ),
        )
        for path, replacement in mutations:
            value = self.bundle()
            target = value[10]
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = replacement
            with self.subTest(path=path):
                self.assert_bundle_invalid(value)

    def test_department_hierarchy_cycle_is_rejected(self):
        value = self.bundle()
        parent = value[1]
        child = copy.deepcopy(parent)
        child["identity"]["resource_id"] = "department:acme:analysis"
        child["identity"]["revision"] = "sha256:department-acme-analysis-v1"
        child["identity"]["audit_id"] = "audit:department:acme:analysis:v1"
        child["parent_department_ref"] = {
            "resource_type": "DEPARTMENT",
            "resource_id": parent["identity"]["resource_id"],
            "revision": parent["identity"]["revision"],
        }
        parent["parent_department_ref"] = {
            "resource_type": "DEPARTMENT",
            "resource_id": child["identity"]["resource_id"],
            "revision": child["identity"]["revision"],
        }
        value.append(child)
        self.assert_bundle_invalid(value)

    def test_supervisory_position_cycle_is_rejected(self):
        value = self.bundle()
        first = value[4]
        second = copy.deepcopy(first)
        second["identity"]["resource_id"] = "position:acme:research-lead"
        second["identity"]["revision"] = "sha256:position-acme-lead-v1"
        second["identity"]["audit_id"] = "audit:position:acme:lead:v1"
        second["position_code"] = "research-lead"
        first["reports_to_position_ref"] = {
            "resource_type": "POSITION",
            "resource_id": second["identity"]["resource_id"],
            "revision": second["identity"]["revision"],
        }
        second["reports_to_position_ref"] = {
            "resource_type": "POSITION",
            "resource_id": first["identity"]["resource_id"],
            "revision": first["identity"]["revision"],
        }
        value.append(second)
        self.assert_bundle_invalid(value)

    def test_cross_organization_reference_is_rejected(self):
        value = self.bundle()
        other = copy.deepcopy(value[0])
        other["identity"]["resource_id"] = "organization:other"
        other["identity"]["revision"] = "sha256:organization-other-v1"
        other["identity"]["audit_id"] = "audit:organization:other:v1"
        other["organization_principal_ref"]["principal_id"] = (
            "principal:organization:other"
        )
        value.append(other)
        value[3]["organization_ref"] = {
            "resource_type": "ORGANIZATION",
            "resource_id": "organization:other",
            "revision": "sha256:organization-other-v1",
        }
        self.assert_bundle_invalid(value)

    def test_organization_principal_cannot_bind_two_organizations(self):
        value = self.bundle()
        other = copy.deepcopy(value[0])
        other["identity"]["resource_id"] = "organization:other"
        other["identity"]["revision"] = "sha256:organization-other-v1"
        other["identity"]["audit_id"] = "audit:organization:other:v1"
        value.append(other)
        self.assert_bundle_invalid(value)

    def test_employee_principal_cannot_bind_two_employees(self):
        value = self.bundle()
        other = copy.deepcopy(value[5])
        other["identity"]["resource_id"] = "employee:acme:other"
        other["identity"]["revision"] = "sha256:employee-acme-other-v3"
        other["identity"]["audit_id"] = "audit:employee:acme:other:v3"
        other["status"] = "DRAFT"
        value.append(other)
        self.assert_bundle_invalid(value)

    def test_duplicate_active_membership_is_rejected(self):
        value = self.bundle()
        duplicate = copy.deepcopy(value[7])
        duplicate["identity"]["resource_id"] = "membership:duplicate"
        duplicate["identity"]["revision"] = "sha256:membership-duplicate-v1"
        duplicate["identity"]["audit_id"] = "audit:membership:duplicate:v1"
        value.append(duplicate)
        self.assert_bundle_invalid(value)

    def test_expired_membership_cannot_remain_active(self):
        value = self.bundle()
        value[7]["effective_until"] = "2026-07-25T16:59:59Z"
        self.assert_bundle_invalid(value)

    def test_future_membership_cannot_be_active(self):
        value = self.bundle()
        value[7]["effective_from"] = "2026-07-25T17:00:01Z"
        self.assert_bundle_invalid(value)

    def test_active_employee_requires_one_organization_membership(self):
        value = self.bundle()
        value.pop(6)
        self.assert_bundle_invalid(value)

    def test_duplicate_active_position_occupancy_is_rejected(self):
        value = self.bundle()
        duplicate = copy.deepcopy(value[8])
        duplicate["identity"]["resource_id"] = "position-occupancy:duplicate"
        duplicate["identity"]["revision"] = "sha256:occupancy-duplicate-v1"
        duplicate["identity"]["audit_id"] = "audit:occupancy:duplicate:v1"
        value.append(duplicate)
        self.assert_bundle_invalid(value)

    def test_future_or_ended_position_occupancy_cannot_be_active(self):
        for field, timestamp in (
            ("effective_from", "2026-07-25T17:00:01Z"),
            ("effective_until", "2026-07-25T16:59:59Z"),
        ):
            value = self.bundle()
            value[8][field] = timestamp
            with self.subTest(field=field):
                self.assert_bundle_invalid(value)

    def test_suspended_parent_cannot_have_active_child(self):
        value = self.bundle()
        value[0]["status"] = "SUSPENDED"
        self.assert_bundle_invalid(value)

    def test_suspended_department_cannot_have_active_department_child(self):
        value = self.bundle()
        parent = value[1]
        parent["status"] = "SUSPENDED"
        child = copy.deepcopy(parent)
        child["identity"]["resource_id"] = "department:acme:analysis"
        child["identity"]["revision"] = "sha256:department-acme-analysis-v1"
        child["identity"]["audit_id"] = "audit:department:acme:analysis:v1"
        child["status"] = "ACTIVE"
        child["parent_department_ref"] = {
            "resource_type": "DEPARTMENT",
            "resource_id": parent["identity"]["resource_id"],
            "revision": parent["identity"]["revision"],
        }
        value.append(child)
        self.assert_bundle_invalid(value)

    def test_membership_kinds_enforce_member_and_container_types(self):
        cases = (
            ("USER_ORGANIZATION", "HUMAN_USER", "ORGANIZATION"),
            ("EMPLOYEE_ORGANIZATION", "EMPLOYEE", "ORGANIZATION"),
            ("USER_TEAM", "HUMAN_USER", "TEAM"),
            ("EMPLOYEE_TEAM", "EMPLOYEE", "TEAM"),
        )
        for kind, member_type, container_type in cases:
            value = self.example("leos.membership.v1")
            value["membership_kind"] = kind
            value["member"]["principal_type"] = member_type
            value["container_ref"] = (
                {
                    "resource_type": "ORGANIZATION",
                    "resource_id": "organization:acme",
                    "revision": "sha256:organization-acme-v1",
                }
                if container_type == "ORGANIZATION"
                else {
                    "resource_type": "TEAM",
                    "resource_id": "team:acme:market-research",
                    "revision": "sha256:team-acme-market-research-v1",
                }
            )
            with self.subTest(kind=kind):
                validate_contract("leos.membership.v1", value)

    def test_role_cannot_claim_authorization(self):
        value = self.example("leos.role.v1")
        value["permissions"] = ["provider.invoke"]
        self.assert_invalid("leos.role.v1", value)

    def test_position_cannot_embed_employee_identity(self):
        value = self.example("leos.position.v1")
        value["employee_ref"] = {
            "resource_type": "EMPLOYEE",
            "resource_id": "employee:acme:researcher",
            "revision": "sha256:employee-acme-researcher-v3",
        }
        self.assert_invalid("leos.position.v1", value)

    def test_team_cannot_claim_execution_authority(self):
        for field in ("schedule", "execution", "provider_id", "assignment_id"):
            value = self.example("leos.team.v1")
            value[field] = {}
            with self.subTest(field=field):
                self.assert_invalid("leos.team.v1", value)

    def test_employee_cannot_embed_runtime_secrets_or_assignment(self):
        for field in (
            "runtime",
            "secret_value",
            "provider_credentials",
            "approval_granted",
            "assignment",
        ):
            value = self.example("leos.employee-definition.v3")
            value[field] = {}
            with self.subTest(field=field):
                self.assert_invalid("leos.employee-definition.v3", value)

    def test_projection_fields_cannot_mutate_canonical_state(self):
        value = self.example("leos.organization.v1")
        value["snapshot_id"] = "lucy-snapshot"
        self.assert_invalid("leos.organization.v1", value)

    def test_invalid_lifecycle_transition_is_rejected(self):
        value = self.example("leos.organization-lifecycle-transition.v1")
        value["from_status"] = "DRAFT"
        value["to_status"] = "DELETED"
        self.assert_invalid(
            "leos.organization-lifecycle-transition.v1",
            value,
        )

    def test_non_deleted_transition_requires_compensating_rollback(self):
        value = self.example("leos.organization-lifecycle-transition.v1")
        value["rollback_behavior"] = "TERMINAL_NO_ROLLBACK"
        self.assert_invalid(
            "leos.organization-lifecycle-transition.v1",
            value,
        )

    def test_transition_requires_new_revision(self):
        value = self.example("leos.organization-lifecycle-transition.v1")
        value["resulting_revision"] = value["subject_ref"]["revision"]
        self.assert_invalid(
            "leos.organization-lifecycle-transition.v1",
            value,
        )

    def test_transition_approval_is_fail_closed(self):
        value = self.example("leos.organization-lifecycle-transition.v1")
        value["approval_requirement"] = "VERIFIED"
        self.assert_invalid(
            "leos.organization-lifecycle-transition.v1",
            value,
        )

    def test_terminal_relationship_status_requires_effective_end(self):
        for contract, status in (
            ("leos.membership.v1", "EXPIRED"),
            ("leos.position-occupancy.v1", "ENDED"),
        ):
            value = self.example(contract)
            value["status"] = status
            value.pop("effective_until", None)
            with self.subTest(contract=contract):
                self.assert_invalid(contract, value)

    def test_incorrect_organization_event_producer_is_rejected(self):
        value = read_example("organization-event-envelope.v1.json")
        value["producer"]["principal_id"] = "principal:service:event-bus"
        self.assert_invalid("leos.event-envelope.v1", value)

    def test_observation_time_is_explicit_and_validated(self):
        for observed_at in (
            "system-clock-now",
            "2026-07-25",
            "2026-07-25T17:00:00",
        ):
            with self.subTest(observed_at=observed_at):
                with self.assertRaises(ContractValidationError):
                    validate_organization_domain(
                        self.bundle(),
                        observed_at=observed_at,
                    )


if __name__ == "__main__":
    unittest.main()
