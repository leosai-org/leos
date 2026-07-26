# LEOS v2 Capability, Plugin, and Tool Domain Decisions

## Status

These ADR-style entries establish the Epic 6.0 logical contract foundation.
They do not assign production owners that were previously **OPEN**.

## ADR-CPT-001: Capability, Tool, Plugin, Provider, and execution are distinct

- **Status:** Accepted
- **Decision:** Capability, Tool, Plugin Definition, Plugin Manifest, Artifact,
  Installation, Activation, Provider, Permission, Approval, Authorization,
  Capability Resolution, and Execution remain distinct resources or
  authorities.
- **Consequences:** No document silently absorbs another lifecycle or grants
  itself use.

## ADR-CPT-002: Capability Manager remains capability/provider authority

- **Status:** Accepted
- **Decision:** Capability Manager remains canonical for capability/provider
  inventory, provider-capability bindings, eligibility, and governed
  resolution. `leos.capability-definition.v1` and
  `leos.provider-definition.v1` are target inventory contracts.
- **Consequences:** Epic 6.0 changes no service behavior. Target-contract
  adoption requires an explicit compatibility package.

## ADR-CPT-003: Dispatcher remains sole invocation authority

- **Status:** Accepted
- **Decision:** Tools, Plugins, Providers, runtimes, adapters, and future plugin
  managers may not invoke outside Execution Dispatcher.
- **Consequences:** Tool Runtime and Adapter Manager donor behavior cannot
  migrate as peer invocation authority.

## ADR-CPT-004: Plugin Definition, Manifest, Artifact, Installation, and Activation are separate

- **Status:** Accepted
- **Decision:** Plugin Definition governs extension identity; Manifest is an
  immutable revision-pinned declaration; Artifact is the immutable payload;
  Installation records validated presence; Activation records scoped
  enablement.
- **Consequences:** Publication is not installation, and installation is not
  activation.
- **OPEN:** Production lifecycle owners and topology for all five resources.

## ADR-CPT-005: Artifact Trust verifies but does not publish or install

- **Status:** Accepted
- **Decision:** Artifact Trust Authority verifies digest, signature,
  provenance, trust policy, and artifact revocation evidence.
- **Consequences:** Trust evidence cannot publish, acquire, install, activate,
  authorize, approve, register, resolve, or execute an artifact.
- **OPEN:** Generic Artifact and publishing authority.

## ADR-CPT-006: Installation and Activation never imply permission

- **Status:** Accepted
- **Decision:** Installation and Activation require external Actor Context and
  Authorization Decision evidence and applicable Approval Verification
  references, but never create grants or decisions.
- **Consequences:** Use remains default-deny until Authorization Authority
  permits the exact action/resource/scope and other eligibility checks pass.

## ADR-CPT-007: Compatibility Evidence is explicitly non-authoritative

- **Status:** Accepted
- **Decision:** Compatibility Evidence is revision-pinned, attributable,
  scoped, time-bounded, and explicitly `authoritative: false`.
- **Consequences:** It may inform eligibility but cannot install, activate,
  authorize, approve, rank, resolve, or execute.
- **OPEN:** Observer authority, freshness, runtime target ownership, and
  reconciliation.

## ADR-CPT-008: Permission Declarations are requests, not grants

- **Status:** Accepted
- **Decision:** Permission Declarations record requested actions, access,
  side effects, risk, Approval policy references, and sandbox references.
- **Consequences:** Declaration presence, publisher authorship, manifest
  inclusion, installation, or activation never authorizes use.
- **OPEN:** Capability permission grant source and policy integration.

## ADR-CPT-009: Risk and side effects must be explicit and consistent

- **Status:** Accepted
- **Decision:** Tool and Permission declarations distinguish no effect,
  read-only, mutating, and destructive behavior; local/external reach;
  reversibility; and network/filesystem/secret/data/process/code access.
- **Consequences:** Contradictory low-risk, local-only, read-only, reversible,
  and rollback claims fail validation.

## ADR-CPT-010: Dependencies are exact, versioned, provenance-linked, and fail closed

- **Status:** Accepted
- **Decision:** Dependencies identify exact revisions, required versus
  optional status, semantic-version comparators, and provenance.
- **Consequences:** Unresolved required dependencies, version mismatch,
  cycles, revoked revisions, and hidden transitive permission escalation fail
  conformance.
- **OPEN:** Production resolver, lock, acquisition, update, and rollback
  authority.

## ADR-CPT-011: Capability Profiles constrain configuration but do not select

- **Status:** Accepted
- **Decision:** Capability Profiles may declare scoped requirements,
  prohibitions, allowed classes, set-like implementation/provider
  preferences, risk limits, runtime constraints, and policy references.
- **Consequences:** Profile arrays do not establish candidate order or change
  `job > employee > capability > global`. Profiles cannot authorize, approve,
  select, resolve, or invoke.
- **OPEN:** Organization, Team, Employee, and Runtime profile owners and policy
  interpretation.

## ADR-CPT-012: Provider definitions carry requirements, never credentials

- **Status:** Accepted
- **Decision:** Provider Definitions contain configuration/health contract
  references and opaque credential-reference requirements, never raw secret
  material or direct execution endpoints.
- **Consequences:** Secret reference possession does not authorize resolution;
  Dispatcher remains invocation authority.

## ADR-CPT-013: Model bindings remain Model Registry authority

- **Status:** Accepted
- **Decision:** Provider Definition may declare supported capabilities and
  runtime requirements but does not contain or own model-provider/runtime
  bindings.
- **Consequences:** Model Registry and Capability Manager responsibilities do
  not collapse.

## ADR-CPT-014: Plugin categories include isolated Development Fixtures

- **Status:** Accepted
- **Decision:** Categories distinguish Core built-in, bundled, first-party,
  third-party, local custom, and development fixture Plugins.
- **Consequences:** Development fixtures are deterministic, removable,
  non-authoritative, non-production, and prohibited from production
  installation/activation.

## ADR-CPT-015: Revocation effects are explicit and do not transfer authority

- **Status:** Accepted
- **Decision:** Revocation records exact subjects and revisions, evidence,
  effective time, new-install/new-activation prohibition, existing-activation
  treatment, in-flight treatment, and rollback expectations.
- **Consequences:** Artifact Trust verification does not grant general
  revocation, installation, activation, or execution authority. In-flight
  cancellation follows existing execution authorities.
- **OPEN:** Subject-specific revocation declarers and production propagation.

## ADR-CPT-016: State evidence cannot self-authenticate

- **Status:** Accepted
- **Decision:** Managed resources carry lifecycle-authority, Actor Context,
  Authorization Decision, applicable Approval Verification, Event, revision,
  and audit references.
- **Consequences:** Schema validity, reference existence, caller construction,
  examples, or Events do not prove those authorities issued or verified the
  evidence.

## ADR-CPT-017: The Epic 6.0 validator is reference-only

- **Status:** Accepted
- **Decision:** `validate_capability_plugin_domain` deterministically validates
  an in-memory record set at an explicit observation time.
- **Consequences:** It has no production storage, mutation, authentication,
  trust verification, installation, activation, resolution, or invocation
  authority and is removable without migration.

## ADR-CPT-018: Lucy extension services are donor evidence only

- **Status:** Accepted
- **Decision:** Lucy Plugin Registry, Plugin Platform, Module Registry,
  Capability Registry, Tool Runtime, and Adapter Manager provide donor
  concepts only.
- **Consequences:** Lucy data, tokens, manifests, installed state, runtime
  containers, and direct invocation do not become v2 authority without
  explicit promotion, migration, and conformance.

## ADR-CPT-019: Production lifecycle owners remain OPEN

- **Status:** Accepted
- **Decision:** Epic 6.0 does not silently appoint plugin definition,
  manifest, publishing, installation, activation, dependency, revocation,
  compatibility-observation, capability-profile, marketplace, or automatic-
  update authorities.
- **Consequences:** `OPEN:` references in examples are conspicuous
  placeholders only. Production implementation must stop for an accepted ADR.

## Consolidated OPEN questions

1. Who owns generic Artifact publication and package metadata?
2. Who owns Plugin Definition and Manifest lifecycle?
3. Who installs, activates, updates, rolls back, revokes, and removes Plugins?
4. Who resolves dependency graphs and produces locks?
5. Who owns Tool catalog persistence and ingestion?
6. Who owns Capability Profiles at each scope?
7. Who observes runtime compatibility and governs freshness?
8. Who issues and verifies capability permission grants?
9. Who owns sandbox profiles and enforcement?
10. Who declares each revocation class and coordinates in-flight effects?
11. How does Capability Manager migrate to the target Capability/Provider
    contracts?
12. What public Core versus private marketplace boundaries apply?
