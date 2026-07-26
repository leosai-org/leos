from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from .validation import (
    RFC3339,
    ContractValidationError,
    ValidationIssue,
    validate_contract,
)

CAPABILITY_PLUGIN_CONTRACTS = {
    "leos.capability-definition.v1",
    "leos.tool-definition.v1",
    "leos.plugin-definition.v1",
    "leos.plugin-manifest.v1",
    "leos.provider-definition.v1",
    "leos.plugin-installation.v1",
    "leos.plugin-activation.v1",
    "leos.capability-profile.v1",
    "leos.runtime-requirement.v1",
    "leos.compatibility-evidence.v1",
    "leos.permission-declaration.v1",
    "leos.plugin-revocation.v1",
    "leos.artifact-trust-evidence.v1",
}

DOMAIN_RESOURCE_TYPES = {
    "CAPABILITY",
    "TOOL",
    "PLUGIN",
    "PLUGIN_MANIFEST",
    "PROVIDER",
    "PLUGIN_INSTALLATION",
    "PLUGIN_ACTIVATION",
    "CAPABILITY_PROFILE",
    "RUNTIME_REQUIREMENT",
    "COMPATIBILITY_EVIDENCE",
    "PERMISSION_DECLARATION",
    "PLUGIN_REVOCATION",
    "ARTIFACT_TRUST_EVIDENCE",
}


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise ValueError(value)
    return datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )


def _reference_key(reference: Any) -> tuple[str, str] | None:
    if not isinstance(reference, dict):
        return None
    resource_type = reference.get("resource_type")
    resource_id = reference.get("resource_id")
    if not isinstance(resource_type, str) or not isinstance(resource_id, str):
        return None
    return resource_type, resource_id


def _semantic_version(value: str) -> tuple[int, int, int]:
    core = value.split("+", 1)[0].split("-", 1)[0]
    major, minor, patch = core.split(".")
    return int(major), int(minor), int(patch)


def _satisfies(
    version: str,
    comparators: Iterable[dict[str, str]],
) -> bool:
    candidate = _semantic_version(version)
    operations = {
        "EQ": lambda left, right: left == right,
        "GT": lambda left, right: left > right,
        "GTE": lambda left, right: left >= right,
        "LT": lambda left, right: left < right,
        "LTE": lambda left, right: left <= right,
    }
    return all(
        operations[comparator["operator"]](
            candidate,
            _semantic_version(comparator["version"]),
        )
        for comparator in comparators
    )


def validate_capability_plugin_domain(
    documents: Iterable[dict[str, Any]],
    *,
    observed_at: str,
) -> None:
    """Validate one deterministic, non-authoritative domain snapshot."""

    documents = list(documents)
    issues: list[ValidationIssue] = []
    records: dict[tuple[str, str], dict[str, Any]] = {}
    paths: dict[tuple[str, str], str] = {}
    valid_records: list[tuple[int, dict[str, Any]]] = []

    try:
        observed = _timestamp(observed_at)
    except (TypeError, ValueError):
        raise ContractValidationError(
            "leos.capability-plugin-domain-conformance.v1",
            (
                ValidationIssue(
                    "semantic",
                    "$.observed_at",
                    "must be an RFC3339 date-time",
                ),
            ),
        ) from None

    def add(path: str, message: str) -> None:
        issues.append(ValidationIssue("semantic", path, message))

    for index, document in enumerate(documents):
        path = f"$[{index}]"
        contract = (
            document.get("contract_version")
            if isinstance(document, dict)
            else None
        )
        if contract not in CAPABILITY_PLUGIN_CONTRACTS:
            add(path, "is not a supported Capability/Plugin Domain record")
            continue
        try:
            validate_contract(contract, document)
        except ContractValidationError as error:
            issues.extend(
                ValidationIssue(
                    issue.kind,
                    path + issue.path.removeprefix("$"),
                    issue.message,
                )
                for issue in error.issues
            )
            continue
        identity = document["identity"]
        key = (identity["resource_type"], identity["resource_id"])
        if key in records:
            add(path + ".identity.resource_id", "duplicates a canonical identity")
            continue
        records[key] = document
        paths[key] = path
        valid_records.append((index, document))

    def resolve(
        reference: Any,
        path: str,
        *,
        required: bool = True,
    ) -> dict[str, Any] | None:
        key = _reference_key(reference)
        if key is None:
            return None
        target = records.get(key)
        if target is None:
            if required and key[0] in DOMAIN_RESOURCE_TYPES:
                add(path, "references an unresolved required domain resource")
            return None
        if reference.get("revision") != target["identity"]["revision"]:
            add(path + ".revision", "does not match the current target revision")
            return None
        return target

    def same_refs(left: Any, right: Any) -> bool:
        return left == right

    plugins = {
        key[1]: document
        for key, document in records.items()
        if key[0] == "PLUGIN"
    }

    for index, document in valid_records:
        path = f"$[{index}]"
        resource_type = document["identity"]["resource_type"]

        if resource_type in {
            "PLUGIN_INSTALLATION",
            "PLUGIN_ACTIVATION",
            "CAPABILITY_PROFILE",
            "COMPATIBILITY_EVIDENCE",
        }:
            organization_ref = document["organization_ref"]
            owner = document["identity"]["ownership"]["owner"]
            if owner["principal_type"] != "ORGANIZATION":
                add(
                    path + ".identity.ownership.owner",
                    "Organization-scoped resources require an Organization owner",
                )
            if (
                document.get("target_scope", document.get("profile_scope", {}))
                .get("resource_type") == "ORGANIZATION"
                and document.get(
                    "target_scope",
                    document.get("profile_scope"),
                ) != organization_ref
            ):
                add(
                    path + ".organization_ref",
                    "Organization target scope must match organization_ref",
                )

        if resource_type == "CAPABILITY":
            for ref_index, reference in enumerate(
                document["compatibility_constraint_refs"]
            ):
                resolve(
                    reference,
                    f"{path}.compatibility_constraint_refs[{ref_index}]",
                )

        if resource_type == "TOOL":
            owner = document["package_owner_ref"]
            plugin = (
                resolve(owner, path + ".package_owner_ref")
                if owner["resource_type"] == "PLUGIN"
                else None
            )
            for capability_index, reference in enumerate(
                document["provided_capability_refs"]
            ):
                resolve(
                    reference,
                    f"{path}.provided_capability_refs[{capability_index}]",
                )
                if (
                    plugin is not None
                    and reference not in plugin["declared_capability_refs"]
                ):
                    add(
                        f"{path}.provided_capability_refs[{capability_index}]",
                        "tool claims a capability not declared by its plugin",
                    )
            for requirement_index, reference in enumerate(
                document["runtime_requirement_refs"]
            ):
                resolve(
                    reference,
                    f"{path}.runtime_requirement_refs[{requirement_index}]",
                )

        if resource_type == "PLUGIN":
            publisher = document["publisher"]
            if document["identity"]["ownership"]["owner"] != publisher:
                add(
                    path + ".publisher",
                    "plugin publisher must be the plugin definition owner",
                )
            manifest = resolve(document["manifest_ref"], path + ".manifest_ref")
            tool_ids = [
                reference["resource_id"]
                for reference in document["provided_tool_refs"]
            ]
            if len(tool_ids) != len(set(tool_ids)):
                add(
                    path + ".provided_tool_refs",
                    "plugin contains duplicate tool identities",
                )
            for field in (
                "provided_tool_refs",
                "declared_capability_refs",
                "runtime_requirement_refs",
                "permission_declaration_refs",
                "artifact_trust_evidence_refs",
                "installation_compatibility_refs",
            ):
                for ref_index, reference in enumerate(document[field]):
                    resolve(reference, f"{path}.{field}[{ref_index}]")
            required_secret_ids: set[str] = set()
            for reference in document["runtime_requirement_refs"]:
                requirement = resolve(
                    reference,
                    path + ".runtime_requirement_refs",
                )
                if requirement is not None:
                    required_secret_ids.update(
                        requirement["requirements"][
                            "required_secret_reference_ids"
                        ]
                    )
            if required_secret_ids:
                declares_secret_access = False
                for reference in document["permission_declaration_refs"]:
                    declaration = resolve(
                        reference,
                        path + ".permission_declaration_refs",
                    )
                    if (
                        declaration is not None
                        and "SECRET" in declaration["side_effects"]["accesses"]
                    ):
                        declares_secret_access = True
                if not declares_secret_access:
                    add(
                        path + ".permission_declaration_refs",
                        "runtime secret requirements require an explicit "
                        "SECRET access declaration",
                    )
            if manifest is not None:
                comparisons = (
                    ("publisher", "publisher"),
                    ("artifact_ref", "artifact_ref"),
                    ("semantic_version", "plugin_version"),
                    ("provided_tool_refs", "tool_refs"),
                    ("declared_capability_refs", "capability_refs"),
                    ("runtime_requirement_refs", "runtime_requirement_refs"),
                    ("dependencies", "dependencies"),
                    ("permission_declaration_refs",
                     "permission_declaration_refs"),
                )
                for plugin_field, manifest_field in comparisons:
                    if not same_refs(
                        document[plugin_field],
                        manifest[manifest_field],
                    ):
                        add(
                            path + f".{plugin_field}",
                            "does not match the pinned plugin manifest",
                        )
                if manifest["plugin_ref"] != {
                    "resource_type": "PLUGIN",
                    "resource_id": document["identity"]["resource_id"],
                    "revision": document["identity"]["revision"],
                }:
                    add(
                        path + ".manifest_ref",
                        "manifest does not point back to this plugin revision",
                    )

        if resource_type == "PLUGIN_MANIFEST":
            plugin = resolve(document["plugin_ref"], path + ".plugin_ref")
            if document["identity"]["ownership"]["owner"] != document["publisher"]:
                add(
                    path + ".publisher",
                    "manifest publisher must be the manifest owner",
                )
            if plugin is not None and plugin["publisher"] != document["publisher"]:
                add(path + ".publisher", "manifest publisher does not match plugin")
            for field in (
                "tool_refs",
                "capability_refs",
                "runtime_requirement_refs",
                "permission_declaration_refs",
            ):
                for ref_index, reference in enumerate(document[field]):
                    resolve(reference, f"{path}.{field}[{ref_index}]")

        if resource_type == "PROVIDER":
            for ref_index, reference in enumerate(
                document["supported_capability_refs"]
            ):
                resolve(
                    reference,
                    f"{path}.supported_capability_refs[{ref_index}]",
                )
            for ref_index, reference in enumerate(
                document["runtime_requirement_refs"]
            ):
                resolve(
                    reference,
                    f"{path}.runtime_requirement_refs[{ref_index}]",
                )

        if resource_type == "PERMISSION_DECLARATION":
            resolve(
                document["declaring_plugin_ref"],
                path + ".declaring_plugin_ref",
            )

        if resource_type == "COMPATIBILITY_EVIDENCE":
            requirement = resolve(
                document["requirement_ref"],
                path + ".requirement_ref",
            )
            if document["observer"] != document["identity"]["ownership"][
                "lifecycle_authority"
            ]:
                add(
                    path + ".observer",
                    "observer must match the evidence lifecycle authority",
                )
            if requirement is not None:
                expected = requirement["requirements"]
                facts = document["observed_facts"]
                mismatches = []
                if facts["operating_system"] not in expected["operating_systems"]:
                    mismatches.append("operating system")
                if facts["cpu_architecture"] not in expected["cpu_architectures"]:
                    mismatches.append("CPU architecture")
                if (
                    expected["runtime_types"]
                    and not set(expected["runtime_types"])
                    .intersection(facts["runtime_types"])
                ):
                    mismatches.append("runtime type")
                hardware = expected["minimum_hardware"]
                for fact_name, requirement_name in (
                    ("cpu_cores", "cpu_cores"),
                    ("ram_bytes", "ram_bytes"),
                    ("storage_bytes", "storage_bytes"),
                    ("gpu_memory_bytes", "gpu_memory_bytes"),
                ):
                    if facts[fact_name] < hardware[requirement_name]:
                        mismatches.append(requirement_name)
                if hardware["gpu_required"] and not facts["gpu_present"]:
                    mismatches.append("GPU")
                if (
                    expected["network_requirement"] == "REQUIRED"
                    and not facts["network_available"]
                ):
                    mismatches.append("network")
                if not set(expected["required_secret_reference_ids"]).issubset(
                    facts["available_secret_reference_ids"]
                ):
                    mismatches.append("secret-reference availability")
                if document["outcome"] == "COMPATIBLE" and mismatches:
                    add(
                        path + ".outcome",
                        "COMPATIBLE contradicts observed " + ", ".join(mismatches),
                    )

        if resource_type == "PLUGIN_INSTALLATION":
            plugin = resolve(document["plugin_ref"], path + ".plugin_ref")
            manifest = resolve(document["manifest_ref"], path + ".manifest_ref")
            if plugin is not None:
                if plugin["status"] != "PUBLISHED":
                    add(
                        path + ".plugin_ref",
                        "installation requires a PUBLISHED plugin definition",
                    )
                if document["installed_version"] != plugin["semantic_version"]:
                    add(
                        path + ".installed_version",
                        "does not match the pinned plugin definition",
                    )
                if document["manifest_ref"] != plugin["manifest_ref"]:
                    add(
                        path + ".manifest_ref",
                        "does not match the plugin's current pinned manifest",
                    )
                if document["artifact_ref"] != plugin["artifact_ref"]:
                    add(
                        path + ".artifact_ref",
                        "does not match the plugin's immutable artifact",
                    )
                if (
                    plugin["category"] == "DEVELOPMENT_FIXTURE"
                    and document["status"] == "INSTALLED"
                ):
                    add(
                        path + ".status",
                        "development fixtures cannot install into production scope",
                    )
            if (
                manifest is not None
                and document["artifact_ref"] != manifest["artifact_ref"]
            ):
                add(path + ".artifact_ref", "does not match the manifest artifact")
            if manifest is not None and manifest["status"] != "DECLARED":
                add(
                    path + ".manifest_ref",
                    "installation requires a current DECLARED manifest",
                )
            for field in (
                "compatibility_evidence_refs",
                "artifact_trust_evidence_refs",
            ):
                for ref_index, reference in enumerate(document[field]):
                    evidence = resolve(reference, f"{path}.{field}[{ref_index}]")
                    if evidence is None:
                        continue
                    if field == "compatibility_evidence_refs":
                        if evidence["organization_ref"] != document["organization_ref"]:
                            add(
                                f"{path}.{field}[{ref_index}]",
                                "cross-organization compatibility evidence is prohibited",
                            )
                        if evidence["target_scope"] != document["target_scope"]:
                            add(
                                f"{path}.{field}[{ref_index}]",
                                "compatibility evidence targets another scope",
                            )
                        if (
                            evidence["outcome"] != "COMPATIBLE"
                            or _timestamp(evidence["valid_until"]) <= observed
                        ):
                            add(
                                f"{path}.{field}[{ref_index}]",
                                "installation requires current COMPATIBLE evidence",
                            )
                    else:
                        if evidence["artifact_ref"] != document["artifact_ref"]:
                            add(
                                f"{path}.{field}[{ref_index}]",
                                "trust evidence describes another artifact",
                            )
                        if evidence["outcome"] != "TRUSTED":
                            add(
                                f"{path}.{field}[{ref_index}]",
                                "installation requires TRUSTED artifact evidence",
                            )
                        if _timestamp(evidence["valid_until"]) <= observed:
                            add(
                                f"{path}.{field}[{ref_index}]",
                                "artifact trust evidence is expired",
                            )

        if resource_type == "PLUGIN_ACTIVATION":
            installation = resolve(
                document["installation_ref"],
                path + ".installation_ref",
            )
            if installation is not None:
                if installation["status"] != "INSTALLED":
                    add(
                        path + ".installation_ref",
                        "activation requires an installed plugin",
                    )
                if document["organization_ref"] != installation["organization_ref"]:
                    add(
                        path + ".organization_ref",
                        "cross-organization activation is prohibited",
                    )
                if document["target_scope"] != installation["target_scope"]:
                    add(
                        path + ".target_scope",
                        "activation target must match installation target",
                    )
            if document["status"] == "ACTIVE":
                if _timestamp(document["effective_from"]) > observed:
                    add(
                        path + ".effective_from",
                        "ACTIVE activation cannot begin in the future",
                    )
                if (
                    "effective_until" in document
                    and _timestamp(document["effective_until"]) <= observed
                ):
                    add(
                        path + ".effective_until",
                        "ACTIVE activation cannot be expired",
                    )
            for ref_index, reference in enumerate(
                document["compatibility_evidence_refs"]
            ):
                evidence = resolve(
                    reference,
                    f"{path}.compatibility_evidence_refs[{ref_index}]",
                )
                if evidence is None:
                    continue
                if evidence["organization_ref"] != document["organization_ref"]:
                    add(
                        f"{path}.compatibility_evidence_refs[{ref_index}]",
                        "cross-organization compatibility evidence is prohibited",
                    )
                if evidence["target_scope"] != document["target_scope"]:
                    add(
                        f"{path}.compatibility_evidence_refs[{ref_index}]",
                        "compatibility evidence targets another scope",
                    )
                if (
                    evidence["outcome"] != "COMPATIBLE"
                    or _timestamp(evidence["valid_until"]) <= observed
                ):
                    add(
                        f"{path}.compatibility_evidence_refs[{ref_index}]",
                        "activation requires current COMPATIBLE evidence",
                    )

        if resource_type == "CAPABILITY_PROFILE":
            required = set(
                reference["resource_id"]
                for reference in document["required_capability_refs"]
            )
            prohibited = set(
                reference["resource_id"]
                for reference in document["prohibited_capability_refs"]
            )
            if required.intersection(prohibited):
                add(
                    path,
                    "a capability cannot be both required and prohibited",
                )
            for field in (
                "required_capability_refs",
                "prohibited_capability_refs",
                "preferred_implementation_refs",
                "preferred_provider_refs",
                "runtime_constraint_refs",
            ):
                for ref_index, reference in enumerate(document[field]):
                    resolve(reference, f"{path}.{field}[{ref_index}]")

        if resource_type == "PLUGIN_REVOCATION":
            resolve(document["subject_ref"], path + ".subject_ref")
            if document["declaring_authority"] != document["identity"][
                "ownership"
            ]["lifecycle_authority"]:
                add(
                    path + ".declaring_authority",
                    "revocation must be produced by its lifecycle authority",
                )

    for plugin_id, plugin in plugins.items():
        plugin_path = paths[("PLUGIN", plugin_id)]
        for dependency_index, dependency in enumerate(plugin["dependencies"]):
            reference = dependency["target_ref"]
            target = resolve(
                reference,
                f"{plugin_path}.dependencies[{dependency_index}].target_ref",
                required=dependency["requirement"] == "REQUIRED",
            )
            if target is None:
                continue
            expected_type = dependency["dependency_type"]
            if reference["resource_type"] != expected_type:
                add(
                    f"{plugin_path}.dependencies[{dependency_index}].dependency_type",
                    "does not match dependency target type",
                )
            target_version = target.get("semantic_version")
            if (
                target_version is None
                or not _satisfies(
                    target_version,
                    dependency["version_constraints"],
                )
            ):
                add(
                    f"{plugin_path}.dependencies[{dependency_index}].version_constraints",
                    "dependency version is incompatible",
                )
            if reference["resource_type"] == "PLUGIN":
                parent_permissions = set(
                    item["resource_id"]
                    for item in plugin["permission_declaration_refs"]
                )
                dependency_permissions = set(
                    item["resource_id"]
                    for item in target["permission_declaration_refs"]
                )
                if not dependency_permissions.issubset(parent_permissions):
                    add(
                        f"{plugin_path}.dependencies[{dependency_index}]",
                        "required dependency introduces undeclared transitive permissions",
                    )

    graph: dict[str, set[str]] = defaultdict(set)
    for plugin_id, plugin in plugins.items():
        for dependency in plugin["dependencies"]:
            reference = dependency["target_ref"]
            if (
                dependency["requirement"] == "REQUIRED"
                and reference["resource_type"] == "PLUGIN"
                and reference["resource_id"] in plugins
            ):
                graph[plugin_id].add(reference["resource_id"])

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(plugin_id: str) -> None:
        if plugin_id in visiting:
            add(paths[("PLUGIN", plugin_id)] + ".dependencies", "dependency cycle")
            return
        if plugin_id in visited:
            return
        visiting.add(plugin_id)
        for dependency_id in graph[plugin_id]:
            visit(dependency_id)
        visiting.remove(plugin_id)
        visited.add(plugin_id)

    for plugin_id in plugins:
        visit(plugin_id)

    active_revocations = {
        (
            document["subject_ref"]["resource_type"],
            document["subject_ref"]["resource_id"],
            document["subject_ref"]["revision"],
        )
        for _, document in valid_records
        if (
            document["identity"]["resource_type"] == "PLUGIN_REVOCATION"
            and document["status"] == "ACTIVE"
            and _timestamp(document["effective_at"]) <= observed
        )
    }

    for plugin_id, plugin in plugins.items():
        plugin_path = paths[("PLUGIN", plugin_id)]
        for dependency_index, dependency in enumerate(plugin["dependencies"]):
            reference = dependency["target_ref"]
            if (
                reference["resource_type"],
                reference["resource_id"],
                reference["revision"],
            ) in active_revocations:
                add(
                    f"{plugin_path}.dependencies[{dependency_index}]",
                    "dependency targets a revoked resource revision",
                )

    active_installations: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    active_activations: dict[tuple[str, str], list[str]] = defaultdict(list)
    for index, document in valid_records:
        path = f"$[{index}]"
        resource_type = document["identity"]["resource_type"]
        if resource_type == "PLUGIN_INSTALLATION" and document["status"] == "INSTALLED":
            plugin_ref = document["plugin_ref"]
            artifact_ref = document["artifact_ref"]
            for reference in (plugin_ref, artifact_ref):
                if (
                    reference["resource_type"],
                    reference["resource_id"],
                    reference["revision"],
                ) in active_revocations:
                    add(path + ".status", "revoked content cannot remain installed")
            plugin = resolve(plugin_ref, path + ".plugin_ref")
            if plugin is not None:
                for reference in plugin["provided_tool_refs"]:
                    tool = resolve(reference, path + ".plugin_ref")
                    if (
                        tool is not None
                        and tool["status"] == "REVOKED"
                    ) or (
                        reference["resource_type"],
                        reference["resource_id"],
                        reference["revision"],
                    ) in active_revocations:
                        add(
                            path + ".status",
                            "plugin contains a revoked Tool revision",
                        )
            key = (
                plugin_ref["resource_id"],
                document["target_scope"]["resource_id"],
                document["organization_ref"]["resource_id"],
            )
            active_installations[key].append(path)
        if resource_type == "PLUGIN_ACTIVATION" and document["status"] == "ACTIVE":
            installation = resolve(
                document["installation_ref"],
                path + ".installation_ref",
            )
            if installation is not None:
                for reference in (
                    installation["plugin_ref"],
                    installation["artifact_ref"],
                    document["installation_ref"],
                ):
                    if (
                        reference["resource_type"],
                        reference["resource_id"],
                        reference["revision"],
                    ) in active_revocations:
                        add(path + ".status", "revoked content cannot be active")
            key = (
                document["installation_ref"]["resource_id"],
                document["target_scope"]["resource_id"],
            )
            active_activations[key].append(path)

    for duplicate_paths in (
        *active_installations.values(),
        *active_activations.values(),
    ):
        if len(duplicate_paths) > 1:
            for path in duplicate_paths:
                add(path, "duplicates an active installation or activation")

    if issues:
        raise ContractValidationError(
            "leos.capability-plugin-domain-conformance.v1",
            issues,
        )
