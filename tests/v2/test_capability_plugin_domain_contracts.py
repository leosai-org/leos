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
    validate_capability_plugin_domain,
    validate_contract,
)

EXAMPLES = ROOT / "examples"
OBSERVED_AT = "2026-07-25T19:00:00Z"

CONTRACT_EXAMPLES = {
    "leos.capability-definition.v1": "capability-definition.v1.json",
    "leos.tool-definition.v1": "tool-definition.v1.json",
    "leos.plugin-definition.v1": "plugin-definition.v1.json",
    "leos.plugin-manifest.v1": "plugin-manifest.v1.json",
    "leos.provider-definition.v1": "provider-definition.v1.json",
    "leos.plugin-installation.v1": "plugin-installation.v1.json",
    "leos.plugin-activation.v1": "plugin-activation.v1.json",
    "leos.capability-profile.v1": "capability-profile.v1.json",
    "leos.runtime-requirement.v1": "runtime-requirement.v1.json",
    "leos.compatibility-evidence.v1": "compatibility-evidence.v1.json",
    "leos.permission-declaration.v1": "permission-declaration.v1.json",
    "leos.plugin-revocation.v1": "plugin-revocation.v1.json",
    "leos.artifact-trust-evidence.v1":
        "artifact-trust-evidence.plugin.v1.json",
}

BUNDLE_ORDER = (
    "leos.capability-definition.v1",
    "leos.runtime-requirement.v1",
    "leos.tool-definition.v1",
    "leos.permission-declaration.v1",
    "leos.plugin-definition.v1",
    "leos.plugin-manifest.v1",
    "leos.provider-definition.v1",
    "leos.artifact-trust-evidence.v1",
    "leos.compatibility-evidence.v1",
    "leos.plugin-installation.v1",
    "leos.plugin-activation.v1",
    "leos.capability-profile.v1",
    "leos.plugin-revocation.v1",
)


def read_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class CapabilityPluginDomainContractTests(unittest.TestCase):
    def example(self, contract: str) -> dict[str, Any]:
        return copy.deepcopy(read_example(CONTRACT_EXAMPLES[contract]))

    def bundle(self) -> list[dict[str, Any]]:
        return [self.example(contract) for contract in BUNDLE_ORDER]

    def by_type(
        self,
        bundle: list[dict[str, Any]],
        resource_type: str,
    ) -> dict[str, Any]:
        return next(
            item
            for item in bundle
            if item["identity"]["resource_type"] == resource_type
        )

    def assert_bundle_invalid(self, bundle: list[dict[str, Any]]) -> None:
        with self.assertRaises(ContractValidationError):
            validate_capability_plugin_domain(
                bundle,
                observed_at=OBSERVED_AT,
            )

    def assert_contract_invalid(self, contract: str, value: Any) -> None:
        with self.assertRaises(ContractValidationError):
            validate_contract(contract, value)

    def add_dependency_plugin(
        self,
        bundle: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        source_plugin = self.by_type(bundle, "PLUGIN")
        source_manifest = self.by_type(bundle, "PLUGIN_MANIFEST")
        source_permission = self.by_type(bundle, "PERMISSION_DECLARATION")

        dependency_plugin = copy.deepcopy(source_plugin)
        dependency_plugin["identity"]["resource_id"] = "plugin:acme:helper"
        dependency_plugin["identity"]["revision"] = "sha256:plugin-acme-helper-v1"
        dependency_plugin["identity"]["audit_id"] = "audit:plugin:acme:helper:v1"
        dependency_plugin["manifest_ref"] = {
            "resource_type": "PLUGIN_MANIFEST",
            "resource_id": "plugin-manifest:acme:helper:1.0.0",
            "revision": "sha256:plugin-manifest-acme-helper-v1",
        }
        dependency_plugin["provided_tool_refs"] = []
        dependency_plugin["permission_declaration_refs"] = [{
            "resource_type": "PERMISSION_DECLARATION",
            "resource_id": "permission-declaration:acme:helper",
            "revision": "sha256:permission-declaration-acme-helper-v1",
        }]

        dependency_manifest = copy.deepcopy(source_manifest)
        dependency_manifest["identity"]["resource_id"] = (
            "plugin-manifest:acme:helper:1.0.0"
        )
        dependency_manifest["identity"]["revision"] = (
            "sha256:plugin-manifest-acme-helper-v1"
        )
        dependency_manifest["identity"]["audit_id"] = (
            "audit:plugin-manifest:acme:helper:v1"
        )
        dependency_manifest["plugin_ref"] = {
            "resource_type": "PLUGIN",
            "resource_id": "plugin:acme:helper",
            "revision": "sha256:plugin-acme-helper-v1",
        }
        dependency_manifest["tool_refs"] = []
        dependency_manifest["permission_declaration_refs"] = copy.deepcopy(
            dependency_plugin["permission_declaration_refs"]
        )

        dependency_permission = copy.deepcopy(source_permission)
        dependency_permission["identity"]["resource_id"] = (
            "permission-declaration:acme:helper"
        )
        dependency_permission["identity"]["revision"] = (
            "sha256:permission-declaration-acme-helper-v1"
        )
        dependency_permission["identity"]["audit_id"] = (
            "audit:permission-declaration:acme:helper:v1"
        )
        dependency_permission["declaring_plugin_ref"] = copy.deepcopy(
            dependency_manifest["plugin_ref"]
        )
        dependency_permission["actions"] = ["filesystem.read"]
        dependency_permission["side_effects"] = {
            "effect": "READ_ONLY",
            "reach": "LOCAL",
            "reversibility": "NOT_APPLICABLE",
            "accesses": ["FILESYSTEM"],
            "risk_justification": "The helper reads local files.",
        }

        bundle.extend(
            [
                dependency_plugin,
                dependency_manifest,
                dependency_permission,
            ]
        )
        return (
            dependency_plugin,
            dependency_manifest,
            dependency_permission,
        )

    def test_all_examples_and_complete_bundle_validate(self):
        for contract in CONTRACT_EXAMPLES:
            with self.subTest(contract=contract):
                validate_contract(contract, self.example(contract))
        validate_capability_plugin_domain(
            self.bundle(),
            observed_at=OBSERVED_AT,
        )

    def test_schemas_are_draft_2020_12_and_identifiers_are_unique(self):
        names = [
            "capability-plugin-common.v1.schema.json",
            *(
                contract.removeprefix("leos.") + ".schema.json"
                for contract in CONTRACT_EXAMPLES
                if contract != "leos.artifact-trust-evidence.v1"
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

    def test_tool_requires_a_capability(self):
        value = self.example("leos.tool-definition.v1")
        value["provided_capability_refs"] = []
        self.assert_contract_invalid("leos.tool-definition.v1", value)

    def test_tool_cannot_claim_undeclared_capability(self):
        bundle = self.bundle()
        capability = self.by_type(bundle, "CAPABILITY")
        other = copy.deepcopy(capability)
        other["identity"]["resource_id"] = "capability:file.convert"
        other["identity"]["revision"] = "sha256:capability-file-convert-v1"
        other["identity"]["audit_id"] = "audit:capability:file-convert:v1"
        bundle.append(other)
        self.by_type(bundle, "TOOL")["provided_capability_refs"].append({
            "resource_type": "CAPABILITY",
            "resource_id": "capability:file.convert",
            "revision": "sha256:capability-file-convert-v1",
        })
        self.assert_bundle_invalid(bundle)

    def test_duplicate_plugin_tool_identity_is_rejected(self):
        value = self.example("leos.plugin-definition.v1")
        value["provided_tool_refs"].append(
            copy.deepcopy(value["provided_tool_refs"][0])
        )
        self.assert_contract_invalid("leos.plugin-definition.v1", value)

    def test_plugin_and_manifest_publisher_mismatch_is_rejected(self):
        bundle = self.bundle()
        self.by_type(bundle, "PLUGIN_MANIFEST")["publisher"] = {
            "principal_id": "principal:publisher:other",
            "principal_type": "PUBLISHER",
        }
        self.assert_bundle_invalid(bundle)

    def test_plugin_and_manifest_artifact_mismatch_is_rejected(self):
        bundle = self.bundle()
        self.by_type(bundle, "PLUGIN_MANIFEST")["artifact_ref"][
            "resource_id"
        ] = "artifact:plugin:other"
        self.assert_bundle_invalid(bundle)

    def test_untrusted_or_mismatched_artifact_evidence_is_rejected(self):
        for mutation in ("outcome", "artifact"):
            bundle = self.bundle()
            trust = self.by_type(bundle, "ARTIFACT_TRUST_EVIDENCE")
            if mutation == "outcome":
                trust["outcome"] = "UNTRUSTED"
                trust["reasons"] = ["Signature verification failed."]
                trust["signatures"] = []
            else:
                trust["artifact_ref"]["resource_id"] = "artifact:plugin:other"
            with self.subTest(mutation=mutation):
                self.assert_bundle_invalid(bundle)

    def test_raw_credentials_are_rejected(self):
        for contract, field in (
            ("leos.plugin-definition.v1", "api_key"),
            ("leos.provider-definition.v1", "access_token"),
            ("leos.permission-declaration.v1", "secret_value"),
        ):
            value = self.example(contract)
            value[field] = True
            with self.subTest(contract=contract):
                self.assert_contract_invalid(contract, value)

    def test_activation_requires_installation(self):
        bundle = [
            item
            for item in self.bundle()
            if item["identity"]["resource_type"] != "PLUGIN_INSTALLATION"
        ]
        self.assert_bundle_invalid(bundle)

    def test_cross_organization_installation_and_activation_are_rejected(self):
        for resource_type in ("PLUGIN_INSTALLATION", "PLUGIN_ACTIVATION"):
            bundle = self.bundle()
            target = self.by_type(bundle, resource_type)
            target["organization_ref"] = {
                "resource_type": "ORGANIZATION",
                "resource_id": "organization:other",
                "revision": "sha256:organization-other-v1",
            }
            with self.subTest(resource_type=resource_type):
                self.assert_bundle_invalid(bundle)

    def test_scoped_resources_require_organization_ownership(self):
        for resource_type in (
            "PLUGIN_INSTALLATION",
            "PLUGIN_ACTIVATION",
            "CAPABILITY_PROFILE",
            "COMPATIBILITY_EVIDENCE",
        ):
            bundle = self.bundle()
            target = self.by_type(bundle, resource_type)
            target["identity"]["ownership"]["owner"] = {
                "principal_id": "principal:publisher:acme-labs",
                "principal_type": "PUBLISHER",
            }
            with self.subTest(resource_type=resource_type):
                self.assert_bundle_invalid(bundle)

    def test_active_revocation_blocks_installation_and_activation(self):
        bundle = self.bundle()
        revocation = self.by_type(bundle, "PLUGIN_REVOCATION")
        installation = self.by_type(bundle, "PLUGIN_INSTALLATION")
        revocation["subject_ref"] = copy.deepcopy(installation["artifact_ref"])
        revocation["status"] = "ACTIVE"
        self.assert_bundle_invalid(bundle)

    def test_active_activation_must_be_current(self):
        for field, value in (
            ("effective_from", "2026-07-26T19:00:00Z"),
            ("effective_until", "2026-07-25T18:30:00Z"),
        ):
            bundle = self.bundle()
            self.by_type(bundle, "PLUGIN_ACTIVATION")[field] = value
            with self.subTest(field=field):
                self.assert_bundle_invalid(bundle)

    def test_activation_is_not_authorization_or_approval(self):
        for field, value in (
            ("authorized", True),
            ("approved", True),
            ("grants_permission", True),
        ):
            activation = self.example("leos.plugin-activation.v1")
            activation[field] = value
            with self.subTest(field=field):
                self.assert_contract_invalid(
                    "leos.plugin-activation.v1",
                    activation,
                )

    def test_incompatible_runtime_facts_are_rejected(self):
        mutations = (
            ("operating_system", "WINDOWS"),
            ("cpu_architecture", "ARMV7"),
            ("ram_bytes", 1),
        )
        for field, value in mutations:
            bundle = self.bundle()
            evidence = self.by_type(bundle, "COMPATIBILITY_EVIDENCE")
            evidence["observed_facts"][field] = value
            with self.subTest(field=field):
                self.assert_bundle_invalid(bundle)

    def test_unresolved_required_dependency_is_rejected(self):
        bundle = self.bundle()
        plugin = self.by_type(bundle, "PLUGIN")
        dependency = {
            "dependency_type": "PLUGIN",
            "target_ref": {
                "resource_type": "PLUGIN",
                "resource_id": "plugin:missing",
                "revision": "sha256:plugin-missing-v1",
            },
            "requirement": "REQUIRED",
            "version_constraints": [{"operator": "GTE", "version": "1.0.0"}],
            "provenance_ref": copy.deepcopy(plugin["provenance_refs"][0]),
        }
        plugin["dependencies"] = [dependency]
        self.by_type(bundle, "PLUGIN_MANIFEST")["dependencies"] = [
            copy.deepcopy(dependency)
        ]
        self.assert_bundle_invalid(bundle)

    def test_dependency_cycle_is_rejected(self):
        bundle = self.bundle()
        plugin = self.by_type(bundle, "PLUGIN")
        dependency = {
            "dependency_type": "PLUGIN",
            "target_ref": {
                "resource_type": "PLUGIN",
                "resource_id": plugin["identity"]["resource_id"],
                "revision": plugin["identity"]["revision"],
            },
            "requirement": "REQUIRED",
            "version_constraints": [{"operator": "EQ", "version": "1.0.0"}],
            "provenance_ref": copy.deepcopy(plugin["provenance_refs"][0]),
        }
        plugin["dependencies"] = [dependency]
        self.by_type(bundle, "PLUGIN_MANIFEST")["dependencies"] = [
            copy.deepcopy(dependency)
        ]
        self.assert_bundle_invalid(bundle)

    def test_incompatible_dependency_version_is_rejected(self):
        bundle = self.bundle()
        dependency_plugin, _, dependency_permission = (
            self.add_dependency_plugin(bundle)
        )
        plugin = next(
            item
            for item in bundle
            if item["identity"]["resource_id"] == "plugin:acme:web-search"
        )
        plugin["permission_declaration_refs"].append({
            "resource_type": "PERMISSION_DECLARATION",
            "resource_id": dependency_permission["identity"]["resource_id"],
            "revision": dependency_permission["identity"]["revision"],
        })
        manifest = self.by_type(bundle, "PLUGIN_MANIFEST")
        manifest["permission_declaration_refs"] = copy.deepcopy(
            plugin["permission_declaration_refs"]
        )
        dependency = {
            "dependency_type": "PLUGIN",
            "target_ref": {
                "resource_type": "PLUGIN",
                "resource_id": dependency_plugin["identity"]["resource_id"],
                "revision": dependency_plugin["identity"]["revision"],
            },
            "requirement": "REQUIRED",
            "version_constraints": [{"operator": "GTE", "version": "2.0.0"}],
            "provenance_ref": copy.deepcopy(plugin["provenance_refs"][0]),
        }
        plugin["dependencies"] = [dependency]
        manifest["dependencies"] = [copy.deepcopy(dependency)]
        self.assert_bundle_invalid(bundle)

    def test_hidden_transitive_permission_escalation_is_rejected(self):
        bundle = self.bundle()
        dependency_plugin, _, _ = self.add_dependency_plugin(bundle)
        plugin = next(
            item
            for item in bundle
            if item["identity"]["resource_id"] == "plugin:acme:web-search"
        )
        dependency = {
            "dependency_type": "PLUGIN",
            "target_ref": {
                "resource_type": "PLUGIN",
                "resource_id": dependency_plugin["identity"]["resource_id"],
                "revision": dependency_plugin["identity"]["revision"],
            },
            "requirement": "REQUIRED",
            "version_constraints": [{"operator": "EQ", "version": "1.0.0"}],
            "provenance_ref": copy.deepcopy(plugin["provenance_refs"][0]),
        }
        plugin["dependencies"] = [dependency]
        self.by_type(bundle, "PLUGIN_MANIFEST")["dependencies"] = [
            copy.deepcopy(dependency)
        ]
        self.assert_bundle_invalid(bundle)

    def test_dependency_on_revoked_plugin_is_rejected(self):
        bundle = self.bundle()
        dependency_plugin, _, dependency_permission = (
            self.add_dependency_plugin(bundle)
        )
        plugin = next(
            item
            for item in bundle
            if item["identity"]["resource_id"] == "plugin:acme:web-search"
        )
        plugin["permission_declaration_refs"].append({
            "resource_type": "PERMISSION_DECLARATION",
            "resource_id": dependency_permission["identity"]["resource_id"],
            "revision": dependency_permission["identity"]["revision"],
        })
        manifest = self.by_type(bundle, "PLUGIN_MANIFEST")
        manifest["permission_declaration_refs"] = copy.deepcopy(
            plugin["permission_declaration_refs"]
        )
        dependency = {
            "dependency_type": "PLUGIN",
            "target_ref": {
                "resource_type": "PLUGIN",
                "resource_id": dependency_plugin["identity"]["resource_id"],
                "revision": dependency_plugin["identity"]["revision"],
            },
            "requirement": "REQUIRED",
            "version_constraints": [{"operator": "EQ", "version": "1.0.0"}],
            "provenance_ref": copy.deepcopy(plugin["provenance_refs"][0]),
        }
        plugin["dependencies"] = [dependency]
        manifest["dependencies"] = [copy.deepcopy(dependency)]
        revocation = self.by_type(bundle, "PLUGIN_REVOCATION")
        revocation["subject_ref"] = copy.deepcopy(dependency["target_ref"])
        revocation["status"] = "ACTIVE"
        self.assert_bundle_invalid(bundle)

    def test_required_secret_access_must_be_declared(self):
        bundle = self.bundle()
        requirement = self.by_type(bundle, "RUNTIME_REQUIREMENT")
        requirement["requirements"]["required_secret_reference_ids"] = [
            "secret-ref:web-search-api"
        ]
        self.assert_bundle_invalid(bundle)

    def test_unsupported_contract_version_is_rejected(self):
        value = self.example("leos.plugin-manifest.v1")
        value["contract_version"] = "leos.plugin-manifest.v2"
        self.assert_contract_invalid("leos.plugin-manifest.v1", value)

    def test_capability_profile_cannot_authorize_or_select(self):
        for field, value in (
            ("authorization_grant", {"allowed": True}),
            ("selected_provider_ref", {
                "resource_type": "PROVIDER",
                "resource_id": "provider:acme:web-search",
                "revision": "sha256:provider-acme-web-search-v1",
            }),
        ):
            profile = self.example("leos.capability-profile.v1")
            profile[field] = value
            with self.subTest(field=field):
                self.assert_contract_invalid(
                    "leos.capability-profile.v1",
                    profile,
                )

    def test_inconsistent_risk_and_side_effect_claims_are_rejected(self):
        cases = (
            {
                "effect": "DESTRUCTIVE",
                "reach": "LOCAL",
                "reversibility": "COMPENSATABLE",
                "accesses": ["FILESYSTEM"],
                "risk_justification": "Deletes files.",
                "risk": "LOW",
            },
            {
                "effect": "READ_ONLY",
                "reach": "LOCAL",
                "reversibility": "REVERSIBLE",
                "accesses": ["FILESYSTEM"],
                "rollback_expectation": "Restore the file.",
                "risk": "MODERATE",
            },
            {
                "effect": "DESTRUCTIVE",
                "reach": "LOCAL",
                "reversibility": "REVERSIBLE",
                "accesses": ["FILESYSTEM"],
                "risk_justification": "Deletes files.",
                "risk": "HIGH",
            },
        )
        for case in cases:
            tool = self.example("leos.tool-definition.v1")
            tool["side_effects"] = {
                key: value
                for key, value in case.items()
                if key != "risk"
            }
            tool["risk_classification"] = case["risk"]
            with self.subTest(case=case):
                self.assert_contract_invalid("leos.tool-definition.v1", tool)

    def test_external_network_effect_cannot_be_declared_local_only(self):
        tool = self.example("leos.tool-definition.v1")
        tool["side_effects"]["reach"] = "LOCAL"
        self.assert_contract_invalid("leos.tool-definition.v1", tool)

    def test_stale_manifest_and_resource_revisions_are_rejected(self):
        for resource_type, field in (
            ("PLUGIN", "manifest_ref"),
            ("TOOL", "provided_capability_refs"),
        ):
            bundle = self.bundle()
            value = self.by_type(bundle, resource_type)
            reference = value[field]
            if isinstance(reference, list):
                reference = reference[0]
            reference["revision"] = "sha256:stale"
            with self.subTest(resource_type=resource_type):
                self.assert_bundle_invalid(bundle)

    def test_duplicate_active_installation_and_activation_are_rejected(self):
        for resource_type in ("PLUGIN_INSTALLATION", "PLUGIN_ACTIVATION"):
            bundle = self.bundle()
            duplicate = copy.deepcopy(self.by_type(bundle, resource_type))
            duplicate["identity"]["resource_id"] += ":duplicate"
            duplicate["identity"]["revision"] += ":duplicate"
            duplicate["identity"]["audit_id"] += ":duplicate"
            bundle.append(duplicate)
            with self.subTest(resource_type=resource_type):
                self.assert_bundle_invalid(bundle)

    def test_fixture_cannot_install_into_production_scope(self):
        bundle = self.bundle()
        self.by_type(bundle, "PLUGIN")["category"] = "DEVELOPMENT_FIXTURE"
        self.assert_bundle_invalid(bundle)

    def test_bypass_and_false_authority_fields_are_rejected(self):
        cases = (
            ("leos.provider-definition.v1", "invoke_endpoint"),
            ("leos.tool-definition.v1", "direct_dispatch"),
            ("leos.plugin-installation.v1", "trusted"),
            ("leos.plugin-installation.v1", "caller_installed"),
            ("leos.plugin-activation.v1", "caller_activated"),
        )
        for contract, field in cases:
            value = self.example(contract)
            value[field] = True
            with self.subTest(contract=contract, field=field):
                self.assert_contract_invalid(contract, value)

    def test_plugin_cannot_bypass_artifact_trust(self):
        value = self.example("leos.plugin-definition.v1")
        value["artifact_trust_evidence_refs"] = []
        self.assert_contract_invalid("leos.plugin-definition.v1", value)

    def test_compatibility_evidence_cannot_claim_authority(self):
        value = self.example("leos.compatibility-evidence.v1")
        value["authoritative"] = True
        self.assert_contract_invalid("leos.compatibility-evidence.v1", value)

    def test_state_and_lifecycle_authority_must_match(self):
        value = self.example("leos.plugin-installation.v1")
        value["state_evidence"]["transition_authority"][
            "authority_id"
        ] = "caller-controlled-authority"
        self.assert_contract_invalid("leos.plugin-installation.v1", value)


if __name__ == "__main__":
    unittest.main()
