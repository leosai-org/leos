# leos-contracts

`leos-contracts` is the runtime validator for governed LEOS JSON contracts.
It does not define or embed schemas.

The contract root is resolved deterministically:

1. `LEOS_CONTRACT_ROOT`, when set; otherwise
2. the repository's canonical `contracts/` directory only when the package
   positively identifies the expected LEOS source-checkout structure.

Containers must set `LEOS_CONTRACT_ROOT` to the copied canonical contract
artifacts (the promoted v2 services use `/opt/leos/contracts`).

An installed package outside that verified source layout must set
`LEOS_CONTRACT_ROOT`; it never falls back to a nearby environment or virtual
environment `contracts/` directory. Missing, incomplete, or malformed
governed roots raise `ContractRootError`.

The validator supports the canonical execution, effective-ranking, Epic 4.0
identity/trust, Epic 5.0 Organization Domain, and Epic 6.0 Capability/Plugin/
Tool Domain contracts. It validates schemas and deterministic cross-field
invariants only.

`validate_organization_domain` additionally validates a caller-supplied,
in-memory record set for reference integrity, revision pinning, organization
scope, active relationship periods, duplicate active relationships, and
Department/Position hierarchy cycles. When transition and Event evidence are
present, it also checks their resulting revision, status, owner, lifecycle
authority, subject, and payload linkage. Its explicit `observed_at` input
makes time-dependent conformance deterministic. It does not persist or mutate
records and is not a production Organization Domain Authority.

`validate_capability_plugin_domain` validates a caller-supplied in-memory
snapshot for identity uniqueness, exact revision linkage, Plugin/Manifest/
Artifact consistency, Tool/Capability linkage, runtime compatibility,
Artifact Trust linkage, Organization/target scope, semantic-version
dependencies, cycles, transitive permission declarations, revocation, and
active Installation/Activation uniqueness at an explicit observation time.
It does not publish, install, activate, authorize, approve, resolve, invoke,
or mutate records and is not a production lifecycle authority.

The package does not authenticate principals, authorize actions, verify a
live Approval Grant or artifact signature, resolve a secret, or establish
event truth. Those operations require the recognized authority over an
authenticated boundary.
