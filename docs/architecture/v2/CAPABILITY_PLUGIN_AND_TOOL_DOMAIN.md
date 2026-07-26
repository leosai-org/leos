# LEOS v2 Capability, Plugin, and Tool Domain

## Status and scope

This document defines the Epic 6.0 logical domain foundation for capabilities,
tools, plugins, providers, plugin manifests, installations, activations,
runtime requirements, compatibility evidence, permission declarations,
capability profiles, dependencies, and revocation.

It defines resource and evidence contracts. It does not deploy a production
plugin service, installer, package manager, marketplace, updater, runtime
supervisor, provider integration, UI, database, or migration.

Previously accepted authorities remain unchanged:

- Capability Manager owns canonical capability/provider inventory,
  provider-capability bindings, eligibility, and governed resolution.
- Execution Dispatcher is the sole governed provider/tool invocation
  authority.
- Authorization Authority decides whether a subject may perform an action.
- Approval Authority owns approval requests, grants, verification, expiry,
  revocation, scope, and consumption.
- Artifact Trust Authority verifies artifact provenance, signature, digest,
  policy, and trust-revocation evidence.
- Secret Authority owns opaque secret-reference identity and the protected
  secret lifecycle boundary.
- Model Registry owns model facts and model-provider/runtime bindings.

The production owners for plugin definition, manifest, publishing,
installation, activation, dependency resolution, plugin revocation, runtime
compatibility observation, and capability profiles remain **OPEN**. Contract
examples use visibly `OPEN:` authority references to demonstrate required
shapes. Those references are not appointments, deployable configuration, or
authority evidence.

## Domain separation

The canonical concepts are distinct:

```text
Capability
  abstract governed ability

Tool
  concrete versioned callable operation

Plugin Definition
  governed extension identity and lifecycle

Plugin Manifest
  immutable, revision-pinned package declaration

Plugin Artifact
  immutable payload governed by the future publishing lifecycle

Plugin Installation
  validated artifact presence at one target scope

Plugin Activation
  enabling one installation at one target scope

Provider
  implementation/source registered in Capability Manager inventory

Capability Profile
  scoped requirements, prohibitions, constraints, and preference references

Permission Declaration
  requested access and side-effect facts

Authorization Decision
  authoritative allow/deny decision

Approval Verification
  authoritative verification of a governed Approval Grant

Capability Resolution
  Capability Manager selection or truthful non-selection

Execution
  Dispatcher-authorized provider/tool invocation
```

Publication is not trust. Trust is not installation. Installation is not
activation. Activation is not permission, approval, eligibility, resolution,
or execution.

## Canonical resource matrix

| Resource | Definition purpose | Lifecycle owner | Authority boundary |
|---|---|---|---|
| Capability | Abstract ability, contracts, version, risk, compatibility, lifecycle | Capability Manager for canonical inventory | No provider credential, endpoint, installation, activation, ranking, permission, approval, or execution state |
| Tool | Concrete operation, schemas, capability linkage, side effects, risk, idempotency, timeout, cancellation, runtime/trust requirements | **OPEN** | Never authorizes, approves, resolves, or invokes itself |
| Plugin Definition | Extension identity, publisher, artifact/manifest linkage, declared tools/capabilities, requirements, dependencies, permission requests, provenance, trust references | **OPEN** | Definition is not manifest, artifact, installation, activation, or runtime |
| Plugin Manifest | Immutable revision-pinned package declaration | **OPEN** | Manifest declaration never registers inventory, grants, installs, activates, or executes |
| Provider Definition | Provider type, supported capabilities, configuration/health contracts, credential-reference requirements, runtime requirements, lifecycle | Capability Manager for canonical inventory | No raw secret, direct endpoint, health-based ranking, permission, or invocation |
| Plugin Installation | Evidence that one trusted compatible artifact version is present for one Organization-owned target | **OPEN** | Does not imply activation, trust, authorization, approval, eligibility, or execution |
| Plugin Activation | Evidence that one valid installation is enabled for one matching target and effective period | **OPEN** | Does not grant permission, satisfy approval, register providers, resolve, or invoke |
| Runtime Requirement | Revisioned OS, architecture, runtime, package, contract, hardware, network, and secret-reference requirements | **OPEN** | Requirement is not observed compatibility or activation |
| Compatibility Evidence | Attributable, scoped, time-bounded observation against one requirement | Observation owner **OPEN**; always non-authoritative | May inform eligibility; cannot install, activate, authorize, approve, rank, resolve, or execute |
| Permission Declaration | Requested actions, access, side effects, risk, approval-policy and sandbox references | Declaration owner **OPEN** | Declaration is never a grant or decision |
| Capability Profile | Scoped required/prohibited capabilities, allowed classes, non-ordering preferences, risk/runtime/policy references | Organization/Team/Employee/Runtime profile owners **OPEN** | Does not authorize, approve, establish ranking, select, resolve, or invoke |
| Plugin Revocation | Governed revocation declaration and required effects for a plugin ecosystem subject | Subject revocation owner **OPEN** | Artifact Trust Authority may verify artifact evidence but does not acquire declaration, install, activation, or execution authority |

Every document has one canonical identity, one owner, one revision, one
lifecycle-authority reference, creation authority evidence, an audit identity,
and revision-linked state evidence. A schema-valid document cannot authenticate
its actor or prove that the referenced authority issued it.

## Capability boundary

`leos.capability-definition.v1` is the canonical target shape for Capability
Manager capability inventory. It records:

- immutable identity and semantic version;
- display name and description;
- capability class;
- input and output contract references;
- risk classification;
- runtime/compatibility constraint references;
- lifecycle status and state evidence; and
- ownership, revision, and audit identity.

It contains no endpoint, raw credential, installation, activation, grant,
approval, ranking, selected provider, or execution state.

The existing Capability Manager storage/API has not adopted this target
contract in Epic 6.0. Adoption requires a separate compatibility and migration
package.

## Tool boundary

`leos.tool-definition.v1` describes one callable operation. A Tool:

- belongs to exactly one Plugin or immutable built-in Artifact;
- provides at least one revision-pinned Capability;
- has exact input and output contract references;
- declares side-effect reach and reversibility;
- declares risk, idempotency, timeout, and cancellation behavior; and
- references runtime and artifact-trust requirements.

Tool definition authority remains **OPEN**. Dispatcher remains invocation
authority. A future Tool catalog may be implemented only after its lifecycle
owner is accepted; Tool Runtime and adapters cannot become peer invokers.

## Plugin definition, manifest, and artifact linkage

A Plugin Definition and Plugin Manifest point to each other by exact revision.
They must agree on:

- publisher;
- immutable artifact reference;
- semantic version;
- tools and capabilities;
- runtime requirements;
- dependency declarations; and
- permission declarations.

The Manifest additionally records its package digest and configuration
contract references. The Plugin Definition records category, provenance, trust
evidence, lifecycle, ownership, and audit.

The generic published Artifact contract and production publishing owner remain
**OPEN**. Epic 6.0 therefore uses a revisioned `ARTIFACT` reference and existing
`leos.artifact-trust-evidence.v1`; it does not invent a package payload schema
or publication service.

## Plugin categories

The categories are:

- `CORE_BUILT_IN`
- `BUNDLED`
- `FIRST_PARTY`
- `THIRD_PARTY`
- `LOCAL_CUSTOM`
- `DEVELOPMENT_FIXTURE`

A development fixture is non-authoritative, non-production, deterministic,
removable, and unable to publish, create production installation/activation
state, or provide trust authority. The reference validator rejects an
`INSTALLED` fixture in the production scope model.

## Provider boundary

`leos.provider-definition.v1` is the canonical target shape for Capability
Manager provider inventory. It includes:

- provider identity and type;
- supported Capability references;
- configuration and health contract references;
- declarations that opaque Secret References are required;
- runtime requirement references; and
- lifecycle, ownership, revision, and audit evidence.

It deliberately contains no direct execution endpoint or raw secret. Provider
registration does not grant use. Health and availability do not authorize or
rank. Capability Manager evaluates provider eligibility; Dispatcher invokes
only the governed resolved target.

Model-provider/runtime bindings remain Model Registry authority and are not
duplicated here.

## Installation and activation

Installation and Activation are separate resources.

An Installation pins one Plugin Definition, Manifest, Artifact, installed
version, Organization, target scope, current compatibility evidence, current
Artifact Trust evidence, Actor Context, Authorization Decision, status, and
state evidence.

An Activation pins one Installation, the same Organization and target scope,
an effective period, current compatibility evidence, Actor Context,
Authorization Decision, applicable Approval Verification references, status,
and state evidence.

The reference validator fails closed when:

- installation, manifest, plugin, artifact, or version linkage is stale;
- trust evidence is missing, untrusted, revoked, expired, or for another
  artifact;
- compatibility evidence is missing, incompatible, expired, cross-
  organization, or for another target;
- activation has no current `INSTALLED` record;
- Organization or target scope differs;
- an applicable Plugin, Artifact, Installation, or Activation is revoked; or
- a duplicate active installation or activation would exist.

Approval references are evidence only. Production activation must verify them
through Approval Authority. The production installer and activation owner
remain **OPEN**.

## Capability profiles

A Capability Profile may be scoped to an Organization, Team, Employee, or
Runtime. It may declare:

- required and prohibited capabilities;
- allowed capability classes;
- set-like preferred implementation/provider references;
- maximum risk;
- runtime constraints; and
- policy references.

Preference arrays in v1 do not establish candidate ordering. They are
declarative inputs whose future interpretation requires accepted policy.
Organization and Team ranking scopes remain **OPEN**. Canonical ranking
precedence remains:

```text
job > employee > capability > global
```

The profile cannot contain an Authorization Grant, Approval Grant, selected
implementation, final provider, or execution authority.

## Runtime requirements and compatibility evidence

Runtime Requirements express supported OS and CPU architecture, runtime types,
minimum CPU/RAM/storage/GPU, network requirements, package/version
constraints, contract references, and opaque Secret Reference requirements.

Compatibility Evidence records observed target facts, observer, Organization,
target, outcome, reasons, observation time, and expiry. It is explicitly
`authoritative: false`.

The deterministic validator checks that `COMPATIBLE` is truthful for declared
OS, architecture, runtime, hardware, network, and Secret Reference
availability. Passing that check never installs, activates, authorizes,
approves, ranks, resolves, or executes anything.

Probe authority, freshness policy, runtime ownership, and production evidence
ingestion remain **OPEN**.

## Permission, risk, and side-effect declarations

Permission Declarations express requested actions, accesses, side effects,
risk, approval policy references, and sandbox profile references. They inform
Authorization and Approval authorities; they replace neither.

The schemas and semantic validator reject contradictions including:

- access declared with no side effect;
- mutating/destructive behavior with no reach;
- network access declared local-only;
- destructive behavior below `HIGH` risk;
- destructive behavior claiming full reversibility;
- irreversible behavior claiming rollback; and
- a Plugin needing Secret References without declaring `SECRET` access.

The declaration cannot carry raw Secret values. A future Authorization
Decision must use authenticated actor, subject, action, resource, scope,
current policy, and grant evidence. Activation or installation never satisfies
that decision.

## Dependencies and versions

Dependencies identify Plugin, Capability, or Tool resources by exact revision,
mark them `REQUIRED` or `OPTIONAL`, carry explicit semantic-version
comparators, and retain provenance.

The reference validator rejects:

- unresolved required dependencies;
- incompatible versions;
- required dependency cycles;
- dependencies on actively revoked revisions; and
- transitive permission requirements not explicitly repeated by the dependent
  Plugin.

Optional absence is representable and is not silently upgraded to required.
Production dependency resolution, package acquisition, lock generation,
rollback, and update authority remain **OPEN**.

## Revocation

`leos.plugin-revocation.v1` may address Plugin, Artifact, Installation,
Activation, Provider, or Tool revisions. It records:

- declaring authority and authenticated/authorized evidence;
- effective time and reason;
- required prohibition of new installation and activation;
- explicit existing-activation and in-flight-execution treatment;
- rollback expectation;
- Artifact Trust verification references where applicable; and
- lifecycle, revision, Event, and audit evidence.

Artifact Trust Authority verifies artifact trust/revocation evidence. It does
not declare all subject revocations or gain publishing, installation,
activation, provider, Tool, or execution authority. Exact subject revocation
owners and production propagation remain **OPEN**.

In-flight cancellation remains a request to the current execution authority.
Revocation does not let a plugin manager mutate Dispatcher execution history
or impersonate Scheduler/Cognitive/Persistent Runtime cancellation authority.

## Lifecycle and rollback

Each resource has an explicit status vocabulary. Terminal or revoked records
remain auditable and are not silently overwritten. Update and rollback create
new governed revisions; they do not mutate old artifacts or manifests.

Before production adoption, rollback is a source revert. After adoption,
rollback must preserve:

- immutable Artifact and Manifest revisions;
- installation/activation/revocation history;
- permissions requested and decisions issued;
- compatibility/trust evidence used;
- canonical state transition Events; and
- dependency and target-scope correlation.

No production migration is included in Epic 6.0.

## Reference validator

`validate_capability_plugin_domain` validates a caller-supplied in-memory
snapshot at an explicit observation time. It checks schemas, identity
uniqueness, revision pinning, linkage, trust, compatibility, scope,
dependencies, version constraints, cycles, permission escalation, revocation,
and active-instance uniqueness.

It has no storage, API, clock, authenticator, authority configuration, network,
installer, package acquisition, activation, provider registration, resolution,
or invocation capability. It is deterministic and non-authoritative. Passing
conformance creates no resource and confers no permission, approval, trust,
eligibility, or execution authority.

## Lucy donor evidence

Lucy Plugin Registry, Plugin Platform, Module Registry, Capability Registry,
Tool Runtime, and Adapter Manager are donor evidence only.

Useful donor concepts include manifest inspection, checksums, package
quarantine, installed-instance records, enable/disable history, dependency
metadata, runtime requirements, event vocabulary, and provider/capability
registration intent.

The following Lucy behaviors are not promoted:

- publisher tokens or caller strings as v2 authentication;
- checksum equality as complete Artifact Trust;
- installation directly registering grants or authorizing use;
- activation starting runtime containers and self-registering providers as one
  atomic hidden authority;
- Tool Runtime or adapters invoking outside Dispatcher;
- Capability Registry or Module Registry acting as peer inventory/resolution
  authorities;
- raw environment credential injection as governed Secret resolution; and
- physical deletion as revocation or audit erasure.

## Remaining OPEN and conflicting decisions

1. Generic Artifact definition, publication owner, package envelope, and
   public/private publishing boundary.
2. Plugin Definition and Manifest lifecycle owner and production persistence.
3. Production installer, installation owner, activation owner, transaction,
   event/outbox, backup, recovery, and rollback topology.
4. Dependency resolution, lock generation, package acquisition, and update
   authority.
5. Plugin/Artifact/Installation/Activation/Provider/Tool revocation declarers,
   verification, propagation, and in-flight policy.
6. Tool catalog owner and production ingestion into Capability Manager.
7. Capability and Provider target-contract adoption by Capability Manager.
8. Organization, Team, Employee, and Runtime Capability Profile owners and
   policy interpretation.
9. Runtime compatibility observer, freshness, reconciliation, and runtime
   target authority.
10. Capability permission grant issuer, policy/grant sources, revocation,
    delegation, and verifier.
11. Sandbox profile authority and production isolation level.
12. Secret backend, authorized resolution, transient injection, and redaction.
13. Marketplace and automatic update authorities.
14. Plugin runtime-instance definition and process-supervisor topology.

Lucy Plugin Platform, Module Registry, Capability Registry, Tool Runtime, and
Adapter Manager remain **CONFLICTING / INVESTIGATE** wherever their running
behavior overlaps these accepted boundaries.

## Work Domain integration

Jobs, Tasks, and Workflow steps may declare exact capability requirements.
Those declarations do not identify a provider or Tool, establish candidate
order, grant permission, activate a Plugin, satisfy approval, or authorize
execution. Assignment and Delegation do not change capability eligibility.

Capability Manager remains the resolution authority and Dispatcher remains
the sole invocation authority. Work Results may link execution and Artifact
evidence, but neither Work Domain contracts nor their reference validator may
invoke Capability Manager, Dispatcher, a Tool, or a provider.
