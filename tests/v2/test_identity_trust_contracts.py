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

from leos_contracts import ContractValidationError, validate_contract

EXAMPLES = ROOT / "examples"

CONTRACT_EXAMPLES = {
    "leos.resource-identity.v1": "resource-identity.v1.json",
    "leos.principal.v1": "principal.v1.json",
    "leos.actor-context.v1": "actor-context.v1.json",
    "leos.authorization-decision.v1": "authorization-decision.v1.json",
    "leos.approval-request.v1": "approval-request.v1.json",
    "leos.approval-grant.v1": "approval-grant.v1.json",
    "leos.approval-verification-result.v1":
        "approval-verification-result.v1.json",
    "leos.artifact-trust-evidence.v1": "artifact-trust-evidence.v1.json",
    "leos.secret-reference.v1": "secret-reference.v1.json",
    "leos.event-envelope.v1": "event-envelope.v1.json",
}


def read_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class IdentityTrustContractTests(unittest.TestCase):
    def example(self, contract: str) -> dict[str, Any]:
        return copy.deepcopy(read_example(CONTRACT_EXAMPLES[contract]))

    def assert_valid(self, contract: str, value: Any) -> None:
        try:
            validate_contract(contract, value)
        except ContractValidationError as error:
            self.fail(
                "\n".join(
                    f"{issue.kind} {issue.path}: {issue.message}"
                    for issue in error.issues
                )
            )

    def assert_invalid(self, contract: str, value: Any) -> None:
        with self.assertRaises(ContractValidationError):
            validate_contract(contract, value)

    def test_all_canonical_examples_validate(self):
        for contract in CONTRACT_EXAMPLES:
            with self.subTest(contract=contract):
                self.assert_valid(contract, self.example(contract))

    def test_all_foundation_schemas_are_valid_draft_2020_12(self):
        schema_names = [
            "trust-common.v1.schema.json",
            *(name.replace("leos.", "") + ".schema.json"
              for name in CONTRACT_EXAMPLES),
        ]
        schema_ids = []
        for schema_name in schema_names:
            with self.subTest(schema=schema_name):
                schema = json.loads(
                    (ROOT / "contracts" / schema_name).read_text(
                        encoding="utf-8"
                    )
                )
                Draft202012Validator.check_schema(schema)
                schema_ids.append(schema["$id"])
        self.assertEqual(len(schema_ids), len(set(schema_ids)))

    def test_example_resource_identities_are_unique(self):
        identities = [
            self.example(contract)["identity"]["resource_id"]
            for contract in CONTRACT_EXAMPLES
        ]
        self.assertEqual(len(identities), len(set(identities)))

    def test_every_example_has_exactly_one_owner(self):
        for contract in CONTRACT_EXAMPLES:
            with self.subTest(contract=contract):
                ownership = self.example(contract)["identity"]["ownership"]
                self.assertIsInstance(ownership["owner"], dict)
                self.assertNotIsInstance(ownership["owner"], list)

    def test_managed_identity_requires_owner_creator_steward_and_authority(self):
        for field in ("owner", "creator", "steward", "lifecycle_authority"):
            value = self.example("leos.resource-identity.v1")
            value["identity"]["ownership"].pop(field)
            with self.subTest(field=field):
                self.assert_invalid("leos.resource-identity.v1", value)

    def test_managed_identity_rejects_multiple_owner_shape(self):
        value = self.example("leos.resource-identity.v1")
        value["identity"]["ownership"]["owner"] = [
            value["identity"]["ownership"]["owner"],
            value["identity"]["ownership"]["owner"],
        ]
        self.assert_invalid("leos.resource-identity.v1", value)

    def test_managed_identity_requires_revision_and_audit_identity(self):
        for field in ("revision", "audit_id"):
            value = self.example("leos.resource-identity.v1")
            value["identity"].pop(field)
            with self.subTest(field=field):
                self.assert_invalid("leos.resource-identity.v1", value)

    def test_managed_identity_requires_creation_authentication_and_authority_evidence(self):
        for field in (
            "creation_actor_context_ref",
            "creation_authority_evidence_ref",
        ):
            value = self.example("leos.resource-identity.v1")
            value["identity"].pop(field)
            with self.subTest(field=field):
                self.assert_invalid("leos.resource-identity.v1", value)

    def test_creation_evidence_types_are_fixed(self):
        value = self.example("leos.resource-identity.v1")
        value["identity"]["creation_actor_context_ref"]["resource_type"] = (
            "AUTHORIZATION_DECISION"
        )
        self.assert_invalid("leos.resource-identity.v1", value)

        value = self.example("leos.resource-identity.v1")
        value["identity"]["creation_authority_evidence_ref"].pop("revision")
        self.assert_invalid("leos.resource-identity.v1", value)

    def test_managed_identity_rejects_update_before_creation(self):
        value = self.example("leos.resource-identity.v1")
        value["identity"]["updated_at"] = "2026-07-25T11:59:59Z"
        self.assert_invalid("leos.resource-identity.v1", value)

    def test_principal_identity_type_is_fixed(self):
        value = self.example("leos.principal.v1")
        value["identity"]["resource_type"] = "USER"
        self.assert_invalid("leos.principal.v1", value)

    def test_non_human_principal_requires_governed_subject(self):
        value = self.example("leos.principal.v1")
        value["principal_type"] = "SERVICE"
        value.pop("subject_ref")
        self.assert_invalid("leos.principal.v1", value)

    def test_human_principal_subject_must_be_user(self):
        value = self.example("leos.principal.v1")
        value["subject_ref"]["resource_type"] = "EMPLOYEE"
        self.assert_invalid("leos.principal.v1", value)

    def test_human_principal_requires_governed_subject(self):
        value = self.example("leos.principal.v1")
        value.pop("subject_ref")
        self.assert_invalid("leos.principal.v1", value)

    def test_actor_must_match_authenticated_subject(self):
        value = self.example("leos.actor-context.v1")
        value["authentication"]["subject"]["principal_id"] = (
            "principal:user:someone-else"
        )
        self.assert_invalid("leos.actor-context.v1", value)

    def test_actor_context_expiry_must_follow_issue(self):
        value = self.example("leos.actor-context.v1")
        value["expires_at"] = value["issued_at"]
        self.assert_invalid("leos.actor-context.v1", value)

    def test_actor_context_issuer_must_be_lifecycle_authority(self):
        value = self.example("leos.actor-context.v1")
        value["authentication"]["issuer"]["authority_id"] = "caller"
        self.assert_invalid("leos.actor-context.v1", value)

    def test_initiator_requires_explicit_delegation(self):
        value = self.example("leos.actor-context.v1")
        value["initiator"] = {
            "principal_id": "principal:user:brett",
            "principal_type": "HUMAN_USER",
        }
        self.assert_invalid("leos.actor-context.v1", value)

    def test_caller_authentication_boolean_is_not_actor_evidence(self):
        value = self.example("leos.actor-context.v1")
        value["authenticated"] = True
        self.assert_invalid("leos.actor-context.v1", value)

    def test_allow_authorization_requires_authority_evidence(self):
        value = self.example("leos.authorization-decision.v1")
        value["authority_evidence_refs"] = []
        self.assert_invalid("leos.authorization-decision.v1", value)

    def test_authorization_authority_must_be_lifecycle_authority(self):
        value = self.example("leos.authorization-decision.v1")
        value["authority"]["authority_id"] = "caller"
        self.assert_invalid("leos.authorization-decision.v1", value)

    def test_deny_authorization_requires_reason(self):
        value = self.example("leos.authorization-decision.v1")
        value["decision"] = "DENY"
        value["authority_evidence_refs"] = []
        value["reasons"] = []
        self.assert_invalid("leos.authorization-decision.v1", value)

    def test_authorization_does_not_accept_selected_provider_shortcut(self):
        value = self.example("leos.authorization-decision.v1")
        value["selected_provider_id"] = "provider:other"
        self.assert_invalid("leos.authorization-decision.v1", value)

    def test_actor_evidence_references_are_explicitly_typed(self):
        cases = (
            ("leos.authorization-decision.v1", ("actor_context_ref",)),
            ("leos.approval-request.v1", ("requested_by_actor_ref",)),
            ("leos.approval-grant.v1", ("approved_by_actor_ref",)),
            ("leos.event-envelope.v1", ("actor_context_ref",)),
        )
        for contract, path in cases:
            value = self.example(contract)
            ref = value
            for field in path:
                ref = ref[field]
            ref["evidence_type"] = "AUTHORIZATION_DECISION"
            with self.subTest(contract=contract):
                self.assert_invalid(contract, value)

    def test_approval_request_is_closed_and_cannot_claim_approval(self):
        value = self.example("leos.approval-request.v1")
        value["approved"] = True
        self.assert_invalid("leos.approval-request.v1", value)

    def test_approval_request_expiry_must_follow_request(self):
        value = self.example("leos.approval-request.v1")
        value["expires_at"] = value["requested_at"]
        self.assert_invalid("leos.approval-request.v1", value)

    def test_approval_grant_must_reference_request(self):
        value = self.example("leos.approval-grant.v1")
        value["request_ref"]["resource_type"] = "SCHEDULER_JOB"
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_approval_recipient_must_match_scoped_subject(self):
        value = self.example("leos.approval-grant.v1")
        value["recipient"]["principal_id"] = "principal:employee:other"
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_approval_issuer_must_be_lifecycle_authority(self):
        value = self.example("leos.approval-grant.v1")
        value["issuer"]["authority_id"] = "caller"
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_caller_boolean_is_not_approval_grant_authority(self):
        value = self.example("leos.approval-grant.v1")
        value["approval_granted"] = True
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_revoked_grant_requires_revocation_evidence(self):
        value = self.example("leos.approval-grant.v1")
        value["status"] = "REVOKED"
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_active_grant_prohibits_revocation_evidence(self):
        value = self.example("leos.approval-grant.v1")
        value["revocation"] = {
            "revoked_at": "2026-07-25T12:24:00Z",
            "revoked_by_actor_ref": value["approved_by_actor_ref"],
            "reason": "test",
        }
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_grant_revocation_cannot_predate_issue(self):
        value = self.example("leos.approval-grant.v1")
        value["status"] = "REVOKED"
        value["revocation"] = {
            "revoked_at": "2026-07-25T12:21:59Z",
            "revoked_by_actor_ref": value["approved_by_actor_ref"],
            "reason": "test",
        }
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_consumed_grant_requires_use_evidence(self):
        value = self.example("leos.approval-grant.v1")
        value["status"] = "CONSUMED"
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_grant_expiry_must_follow_validity_start(self):
        value = self.example("leos.approval-grant.v1")
        value["expires_at"] = value["valid_from"]
        self.assert_invalid("leos.approval-grant.v1", value)

    def test_verified_approval_requires_revision_use_and_expiry(self):
        for field in ("verified_grant_revision", "use_ref", "valid_until"):
            value = self.example("leos.approval-verification-result.v1")
            value.pop(field)
            with self.subTest(field=field):
                self.assert_invalid(
                    "leos.approval-verification-result.v1",
                    value,
                )

    def test_verified_approval_pins_exact_grant_revision(self):
        value = self.example("leos.approval-verification-result.v1")
        value["verified_grant_revision"] = "sha256:different-grant-revision"
        self.assert_invalid("leos.approval-verification-result.v1", value)

    def test_approval_verifier_must_be_lifecycle_authority(self):
        value = self.example("leos.approval-verification-result.v1")
        value["authority"]["authority_id"] = "caller"
        self.assert_invalid("leos.approval-verification-result.v1", value)

    def test_nonverified_approval_cannot_carry_authorizing_evidence(self):
        value = self.example("leos.approval-verification-result.v1")
        value["outcome"] = "REVOKED"
        value["reasons"] = ["grant_revoked"]
        self.assert_invalid("leos.approval-verification-result.v1", value)

    def test_arbitrary_opaque_reference_is_not_verification(self):
        value = {
            "contract_version": "leos.approval-verification-result.v1",
            "grant_ref": {
                "resource_type": "APPROVAL_GRANT",
                "resource_id": "arbitrary",
            },
            "outcome": "VERIFIED",
        }
        self.assert_invalid("leos.approval-verification-result.v1", value)

    def test_trusted_artifact_requires_signature_evidence(self):
        value = self.example("leos.artifact-trust-evidence.v1")
        value["signatures"] = []
        self.assert_invalid("leos.artifact-trust-evidence.v1", value)

    def test_artifact_publisher_must_be_publisher_principal(self):
        value = self.example("leos.artifact-trust-evidence.v1")
        value["publisher"]["principal_type"] = "SERVICE"
        self.assert_invalid("leos.artifact-trust-evidence.v1", value)

    def test_artifact_verifier_must_be_lifecycle_authority(self):
        value = self.example("leos.artifact-trust-evidence.v1")
        value["verifier"]["authority_id"] = "caller"
        self.assert_invalid("leos.artifact-trust-evidence.v1", value)

    def test_revoked_artifact_requires_revocation_evidence(self):
        value = self.example("leos.artifact-trust-evidence.v1")
        value["outcome"] = "REVOKED"
        value["reasons"] = ["publisher_revocation"]
        self.assert_invalid("leos.artifact-trust-evidence.v1", value)

    def test_artifact_trust_does_not_accept_install_or_activation_claims(self):
        for field in ("installed", "active"):
            value = self.example("leos.artifact-trust-evidence.v1")
            value[field] = True
            with self.subTest(field=field):
                self.assert_invalid(
                    "leos.artifact-trust-evidence.v1",
                    value,
                )

    def test_secret_reference_rejects_secret_value_fields(self):
        for field in ("secret_value", "api_key", "password"):
            value = self.example("leos.secret-reference.v1")
            value[field] = None
            with self.subTest(field=field):
                self.assert_invalid("leos.secret-reference.v1", value)

    def test_secret_authority_must_be_lifecycle_authority(self):
        value = self.example("leos.secret-reference.v1")
        value["secret_authority"]["authority_id"] = "caller"
        self.assert_invalid("leos.secret-reference.v1", value)

    def test_secret_reference_possession_does_not_encode_authorization(self):
        value = self.example("leos.secret-reference.v1")
        value["authorized"] = True
        self.assert_invalid("leos.secret-reference.v1", value)

    def test_secret_reference_lifecycle_evidence_is_status_bound(self):
        value = self.example("leos.secret-reference.v1")
        value["revoked_at"] = "2026-07-25T12:36:00Z"
        self.assert_invalid("leos.secret-reference.v1", value)

        value = self.example("leos.secret-reference.v1")
        value["status"] = "DELETED"
        self.assert_invalid("leos.secret-reference.v1", value)

    def test_secret_lifecycle_timestamp_cannot_predate_creation(self):
        value = self.example("leos.secret-reference.v1")
        value["status"] = "REVOKED"
        value["revoked_at"] = "2026-07-25T12:34:59Z"
        self.assert_invalid("leos.secret-reference.v1", value)

    def test_event_source_must_be_explicit_event_source(self):
        value = self.example("leos.event-envelope.v1")
        value["source"]["resource_type"] = "SERVICE"
        self.assert_invalid("leos.event-envelope.v1", value)

    def test_event_producer_must_match_event_lifecycle_authority(self):
        value = self.example("leos.event-envelope.v1")
        value["producer"]["principal_id"] = "principal:service:event-bus"
        self.assert_invalid("leos.event-envelope.v1", value)

    def test_event_requires_actor_correlation_causation_and_revision(self):
        for field in (
            "actor",
            "actor_context_ref",
            "correlation_id",
            "causation",
            "event_revision",
        ):
            value = self.example("leos.event-envelope.v1")
            value.pop(field)
            with self.subTest(field=field):
                self.assert_invalid("leos.event-envelope.v1", value)

    def test_event_recording_cannot_precede_occurrence(self):
        value = self.example("leos.event-envelope.v1")
        value["recorded_at"] = "2026-07-25T12:39:59Z"
        self.assert_invalid("leos.event-envelope.v1", value)

    def test_event_payload_cannot_override_envelope_identity(self):
        value = self.example("leos.event-envelope.v1")
        value["payload"]["event_id"] = "event:forged"
        self.assert_valid("leos.event-envelope.v1", value)
        self.assertNotEqual(
            value["payload"]["event_id"],
            value["identity"]["resource_id"],
        )


if __name__ == "__main__":
    unittest.main()
