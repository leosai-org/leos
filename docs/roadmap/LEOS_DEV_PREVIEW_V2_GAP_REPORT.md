# LEOS Dev Preview v2 — Core and Lucy Evidence Gap Report

**Target:** LEOS 0.2.0 Developer Preview v2
**Audit date:** 2026-07-25
**Status:** Evidence-based architecture and roadmap input
**Core source authority:** `leos-v2`
**Donor evidence:** `lucy-runtime-reference` (read-only; never source authority)

## 1. Purpose and method

This report audits the current LEOS Core repository against the approved
organization-first roadmap. It also records implementations found in the Lucy
runtime snapshot when they may provide donor code, behavior, or historical
evidence.

The audit is a static source review. A capability is not classified as
implemented merely because it is named in a catalog, configuration file,
roadmap, or user interface. A Lucy implementation is not treated as canonical
until it is deliberately adapted to the accepted v2 architecture, brought
under public contracts, and tested in LEOS Core.

The governing sources for this report are:

- `AGENTS.md`
- `docs/architecture/v2/EXECUTION_PLANE.md`
- `docs/architecture/v2/EXECUTION_PLANE_DECISIONS.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE_DECISIONS.md`
- `docs/roadmap/DEV_PREVIEW_V2_GOALS.md`
- `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`
- `docs/architecture/REPOSITORY_ARCHITECTURE.md`
- `docs/legal/LICENSE_BOUNDARIES.md`

### Classification vocabulary

| Classification | Meaning in this report |
|---|---|
| **Implemented** | A canonical Core implementation, governed contract or explicit authority, and meaningful tests exist for the stated scope. |
| **Partially Implemented** | Useful canonical behavior exists, but required lifecycle, authority, contract, integration, or test coverage is incomplete. |
| **Documentation Only** | Intent or boundaries are documented, but no canonical implementation exists. |
| **Missing** | No adequate canonical contract, authority, or implementation was found. |
| **Conflicting Authority** | Two or more implementations claim or imply incompatible ownership, or an implementation violates accepted v2 boundaries. |
| **Lucy Donor Evidence Only** | A real Lucy implementation exists, but it is not Core authority and cannot be assumed canonical. |
| **Post-v1** | The item should remain outside the minimum public v2/v1 core unless a later decision promotes it. |
| **Experimental** | The evidence appears exploratory, incomplete, weakly governed, or unsuitable for production adoption without substantial review. |

## 2. Executive summary

LEOS Core is not an empty architecture. It has implemented foundations for the
execution spine, governed capability resolution, provider/model ranking, model
facts, employee lifecycle, resource admission, installation planning, First
Run state, operator inspection, security checks, observability fixtures, and a
reference research employee. Those foundations should be preserved.

The organization-first product layer is not yet internally complete. Core has
no canonical Organization, Department, Team, Workflow, Plugin, Tool, Team
Template, approval-grant, secret-resolution, or sandbox lifecycle. It also
lacks a governed model activation/onboarding path, organization-first guided
console, Team Architect protocol, and unified memory/knowledge/provenance
authority. These are architecture and contract gaps, not merely missing UI.

Lucy contains substantial donor evidence:

- plugin registry, installation, runtime, and module-registry services;
- two workflow engines plus planning and orchestration services;
- tool runtime and adapter execution;
- approval and policy services;
- employee learning, memory, experience, playbook, knowledge, and artifact
  services;
- organization intelligence and a broad console;
- provider/router implementations and specialized embedding, reranking, OCR,
  vision, and speech services.

Much of that evidence is valuable, but it is not one coherent architecture.
Several Lucy services duplicate Capability Manager, Dispatcher, Ranking Policy,
Workflow, approval, memory, and persistence responsibilities. Some use caller
Booleans as approval authority, direct provider/tool invocation, score-based
selection, fallback substitution, or unverified signatures. Those behaviors
conflict with accepted v2 decisions.

The release-critical conclusion is:

> LEOS should define canonical publishing, organization, workflow, plugin,
> permission, tool, approval, secret, sandbox, template, and knowledge
> contracts before promoting donor implementations or building Team Architect.

The minimum credible organization-first v2 demonstration is a governed path
from plain-language team design through reviewed template installation and
simulation to approved activation, using the existing execution and
intelligence authorities without creating peers.

## 3. Implemented-foundations inventory

| Foundation | Classification | Current evidence | Boundary that must be preserved |
|---|---|---|---|
| Execution contracts and correlation | **Implemented** | `contracts/execution.v1.schema.json`, `contracts/execution-result.v1.schema.json`, `contracts/execution-correlation.v1.schema.json`, `tests/v2/test_execution_contracts.py` | Resolution authorizes; Dispatcher invokes; non-invoked outcomes remain truthful. |
| Execution Dispatcher | **Implemented** for current conformance scope | `services/execution-dispatcher-service/app/main.py`, `services/execution-dispatcher-service/tests/test_execution_dispatcher_conformance.py`, `docs/architecture/v2/DISPATCHER_CONFORMANCE.md` | Sole governed provider/tool invocation authority; no selection. |
| Capability resolution | **Implemented** for provider capability resolution | `services/capability-manager-service/app/main.py`, `services/capability-manager-service/tests/test_capability_manager_conformance.py`, `contracts/capability-resolution-result.v1.schema.json` | Inventory, eligibility, and first-ranked-valid resolution only; no invocation or approval self-verification. |
| Ranking Policy Authority | **Implemented** for adopted scopes | `services/ranking-policy-service/app/main.py`, `services/ranking-policy-service/tests/test_ranking_policy_conformance.py`, `contracts/effective-ranking-result.v1.schema.json` | Independent `job > employee > capability > global` order; restrictions eliminate and never reorder. |
| Model facts and bindings | **Implemented** for current registry scope | `services/model-registry-service/app/main.py`, `services/model-registry-service/tests/test_model_authority_conformance.py`, `docs/architecture/v2/MODEL_AUTHORITY_CONFORMANCE.md` | Model Registry owns facts and bindings, not ranking, resolution, activation, or transport. |
| Scheduler and resource enforcement | **Implemented** for current job/lease scope | `services/execution-scheduler-service/app/main.py`, `contracts/resource-admission-decision.v1.schema.json`, `contracts/resource-reservation.v1.schema.json` | Scheduler owns jobs, leases, and resource admission/release. |
| Durable employee runtime | **Partially Implemented** | `services/persistent-employee-runtime-service/app/main.py` and its lifecycle/resource tests | Durable employee, mailbox, working-state, and assignment projection only; no reasoning. |
| Cognitive lifecycle | **Implemented** for current synthetic/conformance scope | `services/employee-cognitive-service/app/main.py`, `services/employee-cognitive-service/tests/test_cognitive_lifecycle_conformance.py`, `docs/architecture/v2/COGNITIVE_LIFECYCLE_CONFORMANCE.md` | Owns per-run reasoning lifecycle; does not mutate scheduler state or invoke providers directly. |
| Employee definition and lifecycle | **Implemented** for individual employees | `contracts/employee-definition.v2.schema.json`, `contracts/employee-lifecycle.v1.schema.json`, `services/employee-registry/app.py`, `docs/phase52.2-employee-definition-lifecycle.md` | Employee Registry remains canonical; embedded legacy model preferences are migration input, not ranking authority. |
| Employee resource profiles | **Implemented** for current scope | `contracts/employee-resource-profile.v1.schema.json`, `services/employee-resource-profile-service/app/main.py`, `docs/phase52-employee-resource-scheduling.md` | Profiles support Scheduler admission and do not become organization policy. |
| Installer and First Run baselines | **Partially Implemented** | `tools/installation_profile.py`, `tools/installer_bootstrap.py`, `tools/first_run.py`, `docs/phase52.4.1-installation-profile-hardware-detection.md`, `docs/phase52.4.2-idempotent-installer-bootstrap.md`, `docs/phase52.4.3-first-run-experience.md` | Planning and governed local writes exist; runtime/model activation and complete recovery do not. |
| Operator, security, and observability baselines | **Partially Implemented** | `tools/operator_cli.py`, `tools/security_observability.py`, `docs/phase52.4.4-leos-cli-doctor.md`, `docs/phase52.4.5-security-observability-baseline.md` | Inspection is read-only by default; backup/update remain plans, not an execution authority. |
| Reference employee and provenance artifacts | **Partially Implemented** | `services/reference-research-content-employee/app.py`, `contracts/research-content-artifact.v1.schema.json`, `contracts/research-source.v1.schema.json`, `docs/phase52.3-reference-research-content-employee.md` | Demonstrates bounded evidence provenance, not general knowledge/memory authority. |
| Manual employee creation UI | **Partially Implemented** | `services/employee-builder/app.py`, `services/employee-builder/templates/research-content.yaml` | Useful individual-employee donor; not the required organization-first guided experience. |

## 4. Audit-area summary matrix

| # | Capability or subsystem | Core classification | Lucy evidence classification | Release conclusion |
|---|---|---|---|---|
| 1 | Publishing authority and artifact lifecycle | **Partially Implemented / Documentation Only** | **Lucy Donor Evidence Only / Conflicting Authority** | Define public artifact and lifecycle authority before further publishing implementation. |
| 2 | Organization, Department, and Team lifecycle | **Missing** | **Lucy Donor Evidence Only / Experimental** | Canonical definitions and lifecycle authority are prerequisite. |
| 3 | Organizational policy with ranking/restrictions | **Documentation Only / Missing** | **Conflicting Authority** | Keep current ranking precedence until an explicit architecture decision adds organizational restrictions or scopes. |
| 4 | Workflow definition and lifecycle | **Missing** | **Lucy Donor Evidence Only / Conflicting Authority** | Select one canonical workflow authority and projection boundary. |
| 5 | Plugin manifest, SDK, trust, lifecycle, isolation | **Documentation Only / Missing** | **Lucy Donor Evidence Only / Conflicting Authority** | Public plugin layer is a v2 must-have but Lucy cannot be copied unchanged. |
| 6 | Capability grants, permissions, revocation, audit | **Missing** | **Lucy Donor Evidence Only / Conflicting Authority** | Distinguish declarations, inventory, grants, policy, and resolution. |
| 7 | Tool identity, schemas, side effects, idempotency, dispatch | **Missing** | **Lucy Donor Evidence Only / Conflicting Authority** | Define Tool contract; retain Dispatcher as invocation authority. |
| 8 | Approval verification authority | **Missing** | **Lucy Donor Evidence Only / Experimental** | A verifiable scoped grant is a v2 security prerequisite. |
| 9 | Secrets and credential resolution | **Missing** | **Lucy Donor Evidence Only / Experimental** | Define opaque references and transient resolution before cloud/plugin activation. |
| 10 | Sandboxing and execution boundaries | **Missing** | **Experimental** | Required before arbitrary tools or development employees perform side effects. |
| 11 | Team Template lifecycle | **Missing** | **Missing** | First-class immutable definition and installed-instance contracts are required. |
| 12 | Team Architect plan/review/apply | **Missing** | **Missing** | Required core employee and guided setup protocol; must not become an authority service. |
| 13 | Memory, knowledge, provenance, artifacts, history | **Partially Implemented** | **Lucy Donor Evidence Only / Conflicting Authority** | Unify authority and provenance before recursive learning or imports. |
| 14 | Model and service onboarding | **Partially Implemented** | **Lucy Donor Evidence Only / Conflicting Authority** | Complete activation and transport registration without restoring Router selection. |
| 15 | Installer, First Run, operator UX, security, observability, recovery, cost | **Partially Implemented** | **Lucy Donor Evidence Only** | Extend existing baselines; do not replace them with console-only flows. |
| 16 | Core employees and organization-first guided UI | **Partially Implemented** | **Lucy Donor Evidence Only / Experimental** | Build Team Architect and guided organization UX over canonical APIs. |

## 5. Detailed capability and gap records

### G-01 — Publishing authority and artifact lifecycle

- **Classification:** **Partially Implemented**, **Documentation Only**, and
  **Lucy Donor Evidence Only / Conflicting Authority**.
- **Current evidence:** Core has source-release publication boundaries and a
  release publication report, but no canonical distributable-object model for
  plugins, employees, workflows, or Team Templates. Public/private repository
  boundaries are recorded in `docs/architecture/REPOSITORY_ARCHITECTURE.md`
  and `docs/legal/LICENSE_BOUNDARIES.md`.
- **Authoritative files:** `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`,
  `docs/architecture/REPOSITORY_ARCHITECTURE.md`,
  `docs/legal/LICENSE_BOUNDARIES.md`, and
  `contracts/release-publication-report.v1.schema.json`. The last contract is
  release-engineering evidence; it is not a general publishing artifact
  contract.
- **Lucy donor evidence:** `../lucy-runtime-reference/plugin-registry-service/app/main.py`
  implements publishers, tokens, plugin versions, submissions, moderation,
  advisories, and downloads. `../lucy-runtime-reference/plugin-platform-service/app/registry_routes.py`
  inspects and installs packages. `../lucy-runtime-reference/marketplace/README.md`
  is documentation evidence only.
- **Missing contracts:** Artifact identity and type; immutable version;
  publisher identity; dependencies; compatibility; content digest; signature
  and trust evidence; provenance/SBOM/license; publication state; installation
  instance; upgrade, rollback, removal, and revocation.
- **Missing services:** A public publishing protocol/validation layer and local
  artifact lifecycle authority. Hosted billing, entitlement, fraud, and
  private moderation remain outside Core.
- **Missing tests:** Reproducible package build; signature verification;
  malicious archive handling; dependency resolution; compatibility;
  immutable-version enforcement; install/update/rollback/remove; revoked
  artifact behavior; offline installation; public/private boundary tests.
- **Dependencies:** Plugin, Workflow, Employee, Team Template, permission,
  secret, approval, sandbox, installation, and provenance decisions.
- **Security implications:** Unverified publishers or signatures, unsafe
  archive extraction, mutable versions, dependency confusion, and rollback to
  vulnerable artifacts could turn publishing into remote code execution.
- **Recommended epic:** **P0 — Publishing Authority and Artifact Contracts**,
  followed by **P0 — Local Artifact Lifecycle and Verification**.
- **Recommended priority:** **P0 / release blocker** because every installable
  organization-first object depends on it.
- **Migration or compatibility concerns:** Preserve public SDK/manifest and
  private marketplace-service boundaries. Treat Lucy databases, token formats,
  package layouts, and `present_unverified` signature states as donor data,
  not compatibility commitments.

### G-02 — Organization, Department, and Team contracts and lifecycle

- **Classification:** **Missing** in Core; **Lucy Donor Evidence Only /
  Experimental**.
- **Current evidence:** The roadmap defines the product hierarchy, but no
  Organization, Department, or Team schema, lifecycle authority, service, or
  conformance suite exists.
- **Authoritative files:** `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`.
  Individual employee authority remains in
  `contracts/employee-definition.v2.schema.json`,
  `contracts/employee-lifecycle.v1.schema.json`, and
  `services/employee-registry/app.py`.
- **Lucy donor evidence:** `../lucy-runtime-reference/companies/default-company/company.yaml`
  and `../lucy-runtime-reference/departments/communications/department.yaml`
  show configuration shapes.
  `../lucy-runtime-reference/organization-intelligence-service/app/main.py`
  builds organization snapshots, graphs, insights, and review state, but acts
  as analytics/projection rather than a proven lifecycle authority.
- **Missing contracts:** Definition, stable identity, revision, lifecycle,
  membership, reporting relations, policy references, knowledge references,
  ownership, deletion/archive, import/export, and event/correlation contracts
  for all three object types.
- **Missing services:** Canonical organization structure authority, or an
  explicitly accepted allocation of Organization/Department/Team storage to a
  smaller set of authorities.
- **Missing tests:** Revision concurrency; lifecycle transitions; membership
  integrity; employee archival effects; cross-team membership; policy
  inheritance; deletion safety; audit history; tenant/organization isolation.
- **Dependencies:** Publishing identity, employee references, Workflow,
  permissions, policy, knowledge, Team Templates, and activation.
- **Security implications:** Undefined organization boundaries can leak
  knowledge, credentials, capabilities, or audit data between teams and can
  allow unauthorized membership or policy changes.
- **Recommended epic:** **P0 — Organization Domain Authority and Contracts**.
- **Recommended priority:** **P0** before Team Architect or Team Template
  activation.
- **Migration or compatibility concerns:** Lucy YAML and graph IDs should be
  imported through explicit migration, not made canonical by path layout.
  Organization intelligence should consume authoritative projections later,
  not own the definitions.

### G-03 — Organizational policy interaction with ranking and restrictions

- **Classification:** **Documentation Only / Missing** in Core;
  **Conflicting Authority** in Lucy evidence.
- **Current evidence:** Ranking Policy currently owns independent precedence
  `job > employee > capability > global`; eligibility removes candidates and
  never reorders them. The roadmap explicitly leaves organization/team
  ranking scopes open.
- **Authoritative files:** `docs/architecture/v2/INTELLIGENCE_PLANE.md`,
  `docs/architecture/v2/INTELLIGENCE_PLANE_DECISIONS.md`,
  `docs/architecture/v2/EFFECTIVE_RANKING_AND_MODEL_RESOLUTION.md`,
  `services/ranking-policy-service/app/main.py`, and
  `contracts/effective-ranking-result.v1.schema.json`.
- **Lucy donor evidence:** `../lucy-runtime-reference/policy-engine/app.py`
  evaluates policy separately, while
  `../lucy-runtime-reference/provider-registry/app.py` contains
  priority/scoring behavior. Neither is accepted ranking authority.
- **Missing contracts:** Organizational restriction inputs, provenance,
  precedence, conflict reporting, immutable decision evidence, and rules for
  whether future organization/team ranking scopes are allowed.
- **Missing services:** No new service is necessarily required; the missing
  item is an accepted policy-to-Ranking/Capability Manager contract and clear
  persistence authority.
- **Missing tests:** Cumulative restrictions; non-reordering; conflicting
  restrictions; organization/team membership changes; exact scope
  provenance; user override constraints; cross-organization isolation.
- **Dependencies:** Organization domain, Ranking Policy, Capability Manager,
  permission grants, cloud permission, and approval.
- **Security implications:** Implicit inheritance can silently reorder user
  preferences or weaken restrictions. A second policy resolver could bypass
  first-ranked-valid semantics.
- **Recommended epic:** **P0 — Organizational Policy and Ranking Boundary
  Decision**, then contract conformance.
- **Recommended priority:** **P0** before organization activation.
- **Migration or compatibility concerns:** Do not infer precedence from Lucy
  priority or score fields. Existing employee `model_preferences` must remain
  migration input rather than a peer authority.

### G-04 — Workflow definition and lifecycle authority

- **Classification:** **Missing** in Core; **Lucy Donor Evidence Only /
  Conflicting Authority**.
- **Current evidence:** `config/service-catalog.json` names a workflow engine,
  and execution correlation can carry workflow identifiers, but no canonical
  workflow definition, state machine, scheduler projection, or compensation
  contract exists.
- **Authoritative files:** `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`,
  `docs/architecture/v2/EXECUTION_PLANE.md`, and
  `contracts/execution-correlation.v1.schema.json`.
- **Lucy donor evidence:** `../lucy-runtime-reference/workflow-engine/app.py`
  is a small JSON-backed engine.
  `../lucy-runtime-reference/workflow-engine-service/app/main.py` contains
  richer SQLite templates, workflows, steps, events, artifacts, run controls,
  and approval endpoints.
  `../lucy-runtime-reference/planning-engine-service/app/main.py`,
  `../lucy-runtime-reference/planning-engine-service/app/lifecycle.py`, and
  `../lucy-runtime-reference/planning-engine-service/app/autonomous_continuation.py`
  also control workflow/plan lifecycle and continuation.
- **Missing contracts:** Immutable workflow definition/revision; parameters;
  step identity; dependencies; triggers; outputs/artifacts; state machine;
  scheduler job projection; approval wait; retry versus compensation;
  cancellation; simulation; resumability; correlation; version migration.
- **Missing services:** One canonical Workflow authority and, only if needed,
  a projection/orchestration worker that submits jobs to Scheduler without
  owning leases or execution.
- **Missing tests:** DAG validation; cycles; deterministic projection;
  restart/resume; duplicate events; approval waits; cancellation;
  compensation; assignment correlation; version upgrades; cross-team access.
  No directly scoped first-party tests were found alongside the examined Lucy
  workflow services.
- **Dependencies:** Organization/Team, Scheduler, assignments, approval,
  permissions, tools, artifacts, publishing, and Team Templates.
- **Security implications:** Direct step execution or caller-supplied approval
  can bypass Dispatcher and approval verification. Competing lifecycle owners
  can duplicate work after restart.
- **Recommended epic:** **P0 — Canonical Workflow Definition, Lifecycle, and
  Scheduler Projection**.
- **Recommended priority:** **P0** for any useful Team Template.
- **Migration or compatibility concerns:** Preserve useful Lucy step,
  dependency, artifact, and event concepts only after mapping them to one
  state machine. Do not preserve duplicate run/continuation authorities.

### G-05 — Plugin manifest, SDK, trust, dependencies, lifecycle, and isolation

- **Classification:** **Documentation Only / Missing** in Core;
  **Lucy Donor Evidence Only / Conflicting Authority**.
- **Current evidence:** Repository and license documents require a public
  plugin/adapter SDK and manifest direction, but no canonical Core plugin
  contract or SDK is present.
- **Authoritative files:** `docs/architecture/REPOSITORY_ARCHITECTURE.md`,
  `docs/legal/LICENSE_BOUNDARIES.md`, and
  `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`.
- **Lucy donor evidence:** `../lucy-runtime-reference/plugin-platform-service/app/main.py`
  manages installed plugin state and container runtime operations;
  `../lucy-runtime-reference/plugin-platform-service/app/registry_routes.py`
  inspects, installs, and removes packages;
  `../lucy-runtime-reference/plugin-platform-service/catalog/plugin-manifest.schema.json`
  is a donor manifest;
  `../lucy-runtime-reference/module-registry/app.py` independently registers,
  scans, enables, disables, and removes modules.
- **Missing contracts:** Manifest and package envelope; plugin/runtime
  identity; declared capabilities/tools/providers; configuration schema;
  required secrets and permissions; dependencies; compatibility; trust and
  signature verification; installed instance; enabled state; health;
  update/rollback/remove; data ownership; isolation profile.
- **Missing services:** Canonical local Plugin Manager/installer and public
  SDK validation tooling. A hosted marketplace backend is not required in
  Core.
- **Missing tests:** Manifest compatibility; cryptographic verification;
  dependency graph and cycles; archive safety; least-privilege install;
  enable/disable; failed update rollback; data retention/removal; offline
  behavior; runtime isolation; capability registration/revocation.
- **Dependencies:** Publishing, capability declarations, grants, Tool
  contracts, secrets, approval, sandbox, installer, Model Registry, and
  Dispatcher adapters.
- **Security implications:** Plugins are executable supply-chain artifacts.
  Lucy records signatures as present/unverified in some paths and performs
  runtime/container and registry mutations without a canonical trust grant.
- **Recommended epic:** **P0 — Public Plugin Contract and SDK**, followed by
  **P0 — Governed Plugin Installation and Runtime Isolation**.
- **Recommended priority:** **P0 / explicit v2 must-have**.
- **Migration or compatibility concerns:** Lucy has at least plugin-platform,
  plugin-registry, and module-registry identities. Choose one canonical model
  and migrate records. Do not allow installation to create a second
  capability/provider registry.

### G-06 — Capability grants, permissions, revocation, and audit

- **Classification:** Capability inventory/resolution is **Implemented**;
  grants and permissions are **Missing**; Lucy is **Conflicting Authority**.
- **Current evidence:** Capability Manager governs provider inventory,
  bindings, eligibility, and resolution. Employee definitions contain
  permission-shaped data, but no canonical subject/resource/action grant
  lifecycle or verifier exists.
- **Authoritative files:** `docs/architecture/v2/CAPABILITY_MANAGER_CONFORMANCE.md`,
  `services/capability-manager-service/app/main.py`,
  `contracts/capability-resolution-request.v1.schema.json`,
  `contracts/capability-resolution-result.v1.schema.json`, and
  `contracts/employee-definition.v2.schema.json`.
- **Lucy donor evidence:** `../lucy-runtime-reference/capability-registry/app.py`,
  `../lucy-runtime-reference/module-registry/app.py`, and
  `../lucy-runtime-reference/tool-runtime-service/app/main.py` each derive or
  expose capability state. Plugin installation also registers capabilities
  into multiple registries.
- **Missing contracts:** Capability declaration versus runtime inventory;
  grant subject/scope/action; issuer; policy and approval references;
  effective time and expiry; revocation; delegation; decision evidence;
  employee/workflow/team binding; audit events.
- **Missing services:** Canonical permission/grant authority and verification
  interface. Capability Manager should consume governed eligibility facts,
  not own all identity or permission persistence by implication.
- **Missing tests:** Least privilege; default deny; scope inheritance;
  revocation during queued/running work; expiry; issuer verification;
  duplicate grants; audit completeness; organization isolation.
- **Dependencies:** Organization identity, Employee, Workflow, Plugin, Tool,
  approval, secrets, policy, and Dispatcher.
- **Security implications:** Capability presence must never imply permission.
  Multiple registries can leave stale grants after plugin disable or employee
  changes.
- **Recommended epic:** **P0 — Capability Declaration and Permission Grant
  Authority**.
- **Recommended priority:** **P0** before plugins or Team Templates activate.
- **Migration or compatibility concerns:** Import Lucy capability records as
  declarations/inventory candidates only. Keep canonical resolution in
  Capability Manager and retire peer resolvers.

### G-07 — Tool identity, schemas, side effects, idempotency, and dispatch

- **Classification:** **Missing** in Core; **Lucy Donor Evidence Only /
  Conflicting Authority**.
- **Current evidence:** Canonical execution contracts can carry governed
  invocations, and Dispatcher is the sole invocation authority, but no
  first-class Tool definition or operation contract was found.
- **Authoritative files:** `docs/architecture/v2/EXECUTION_PLANE.md`,
  `docs/architecture/v2/EXECUTION_PLANE_DECISIONS.md`,
  `contracts/execution.v1.schema.json`, and
  `services/execution-dispatcher-service/app/main.py`.
- **Lucy donor evidence:** `../lucy-runtime-reference/tool-runtime-service/app/main.py`
  has a tool catalog, employee manifests, invocation persistence, approval
  checks, adapter discovery, and direct `/execute` calls.
  `../lucy-runtime-reference/adapter-manager/app.py` is another direct
  invocation layer.
- **Missing contracts:** Tool and operation identity; version; input/output
  JSON Schemas; capability link; side-effect/risk class; idempotency support;
  timeout/cancellation; required permissions/secrets; provider adaptation;
  normalized result and error mapping; audit/redaction policy.
- **Missing services:** Tool catalog/declaration authority and Dispatcher
  adapters. A separate normal-path Tool Runtime must not become a second
  invocation authority.
- **Missing tests:** Schema rejection; permission and approval gates;
  same-target retry; unsafe/non-idempotent retry; ambiguous outcome;
  cancellation; timeout; secret redaction; side-effect audit; adapter
  normalization.
- **Dependencies:** Plugin manifest, capability grants, approval, secret
  resolver, sandbox, Dispatcher, and artifacts.
- **Security implications:** Lucy accepts a caller-provided
  `approval_granted` Boolean and invokes adapters directly. That is explicitly
  incompatible with verifiable grants and Dispatcher authority.
- **Recommended epic:** **P0 — Tool Contract, Risk Model, and Dispatcher
  Adapter Boundary**.
- **Recommended priority:** **P0** before productive plugin use.
- **Migration or compatibility concerns:** Preserve useful catalog and
  invocation-audit fields, but route all real work through Dispatcher and
  eliminate caller Boolean authority.

### G-08 — Approval verification authority

- **Classification:** **Missing** in Core; **Lucy Donor Evidence Only /
  Experimental**.
- **Current evidence:** Execution architecture requires an explicit verifiable
  grant. Capability Manager preserves opaque approval references but does not
  treat them as authority. `APPROVAL_PENDING` is a canonical non-invoked
  outcome.
- **Authoritative files:** `docs/architecture/v2/EXECUTION_PLANE_DECISIONS.md`,
  `docs/architecture/v2/EXECUTION_CONTRACTS.md`,
  `contracts/capability-resolution-result.v1.schema.json`, and
  `contracts/execution-result.v1.schema.json`.
- **Lucy donor evidence:** `../lucy-runtime-reference/approval-service/app.py`
  creates, lists, approves, denies, and records approval history.
  `../lucy-runtime-reference/workflow-engine-service/app/main.py` also stores
  step approvals.
- **Missing contracts:** Approval request; immutable decision; verifiable
  grant; subject/action/resource scope; approver identity and authority;
  issued/expiry times; one-time versus reusable use; revocation; consumed
  state; challenge/context digest; verification result.
- **Missing services:** Authenticated Approval Authority and read-only
  verification endpoint usable by eligibility and execution boundaries.
- **Missing tests:** Forged references; caller Boolean rejection; expired,
  revoked, wrong-scope, wrong-subject, replayed, and modified grants;
  concurrent decisions; audit provenance; fail-closed verifier outage.
- **Dependencies:** Identity/authentication, policy, organization roles,
  capability grants, Tool risk, cloud permission, secrets, Workflow, and
  Dispatcher.
- **Security implications:** A structurally valid reference or unverified
  `decided_by` field must never authorize an action. Approval data can contain
  sensitive intent and requires access control and tamper evidence.
- **Recommended epic:** **P0 — Verifiable Approval Grant Authority**.
- **Recommended priority:** **P0 / security blocker**.
- **Migration or compatibility concerns:** Lucy approval records may be
  historical audit input, but cannot be converted to v2 grants without an
  explicit trust and identity migration.

### G-09 — Secrets and credential resolution

- **Classification:** **Missing** in Core; **Lucy Donor Evidence Only /
  Experimental**.
- **Current evidence:** Architecture forbids secret values in definitions,
  logs, prompts, events, and memory. First Run and security tooling can report
  posture, but no canonical secret reference, grant, resolver, or rotation
  lifecycle exists.
- **Authoritative files:** `AGENTS.md`,
  `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`,
  `contracts/secret-exposure-report.v1.schema.json`, and
  `tools/security_observability.py`.
- **Lucy donor evidence:** `../lucy-runtime-reference/kernel-variable-resolution-service/app/main.py`
  resolves and validates variables, while
  `../lucy-runtime-reference/config-service/app.py` stores configuration.
  Several runtime services read broad environment API keys. These are
  implementation clues, not a secret authority.
- **Missing contracts:** Opaque secret reference; provider/backend; requesting
  subject; allowed operation/target; scope; lease/expiry; rotation/version;
  resolution audit; redaction; unavailable/revoked result; deletion.
- **Missing services:** Secret Authority adapter layer supporting at least a
  safe local backend and transient injection into governed invocations.
- **Missing tests:** No plaintext persistence; log/prompt/event/memory
  redaction; wrong-subject denial; expiry/revocation; rotation; plugin
  uninstall; backup/diagnostic exclusion; crash cleanup; fail-closed outage.
- **Dependencies:** Identity, grants, approval, Plugin/Tool definitions,
  Dispatcher, installer, backup, diagnostics, and cloud providers.
- **Security implications:** Environment-wide keys and configuration CRUD can
  overgrant plugins, leak into diagnostics, and persist in invocation records.
- **Recommended epic:** **P0 — Secret References, Authority, and Transient
  Resolution**.
- **Recommended priority:** **P0** before cloud or authenticated tool use.
- **Migration or compatibility concerns:** Migrate reference names, never
  credential values. Existing Lucy environment names must not become public
  API or appear in examples.

### G-10 — Sandboxing and execution boundaries

- **Classification:** **Missing** in Core; Lucy evidence is **Experimental**.
- **Current evidence:** Dispatcher governs invocation and installation tooling
  avoids unauthorized host/container contact in acceptance tests, but there is
  no canonical sandbox profile, workspace lifecycle, filesystem/network
  policy, or isolation attestation for arbitrary tools.
- **Authoritative files:** `docs/architecture/v2/EXECUTION_PLANE.md`,
  `services/execution-dispatcher-service/app/main.py`,
  `docs/phase52.4.2-idempotent-installer-bootstrap.md`, and
  `docs/phase52.4.5-security-observability-baseline.md`.
- **Lucy donor evidence:** `../lucy-runtime-reference/plugin-platform-service/app/main.py`
  starts plugin containers, while
  `../lucy-runtime-reference/tool-runtime-service/app/main.py` and
  `../lucy-runtime-reference/adapter-manager/app.py` call service endpoints.
  Container use alone does not prove least privilege or isolation.
- **Missing contracts:** Sandbox profile; filesystem roots; network policy;
  process/resource limits; secret mounts; workspace identity; artifact
  ingress/egress; cleanup; attestation; violation and termination result.
- **Missing services:** Governed sandbox/workspace manager or a clearly
  bounded adapter to an external runtime.
- **Missing tests:** Path traversal; host mount denial; network egress;
  process escape; resource exhaustion; secret access; cleanup after crash;
  concurrent isolation; artifact quarantine; cancellation and audit.
- **Dependencies:** Tool risk model, Plugin runtime, permissions, approval,
  secrets, Scheduler resources, Dispatcher, and artifacts.
- **Security implications:** Productive employees can perform arbitrary side
  effects. Without isolation, a compromised model or plugin can access the
  host, network, other teams, or credentials.
- **Recommended epic:** **P0 — Governed Sandbox and Workspace Boundary**.
- **Recommended priority:** **P0 / security blocker** for development tools
  and third-party plugins.
- **Migration or compatibility concerns:** Lucy container names, networks,
  mounts, and direct HTTP layouts are operational donor details, not a stable
  sandbox contract.

### G-11 — Team Template lifecycle

- **Classification:** **Missing** in both Core and the inspected Lucy evidence.
- **Current evidence:** The roadmap makes Team Templates mandatory first-class
  publishing objects and separates immutable published definitions from
  installed/running instances.
- **Authoritative files:** `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`.
- **Lucy donor evidence:** Lucy workflow templates and employee packs provide
  content-shape ideas, but no complete Team Template definition, package,
  instance, simulation, activation, upgrade, or rollback authority was found.
- **Missing contracts:** Template definition/version; contained employees and
  workflows; dependencies; required plugins/capabilities/tools/models/secrets;
  parameters; policies; tests; compatibility; publication; install plan;
  installed instance; simulation report; activation grant; upgrade/rollback.
- **Missing services:** Template validation/composition, installation planner,
  simulation coordinator, and instance lifecycle authority, allocated without
  duplicating underlying Employee, Workflow, Plugin, Ranking, or Scheduler
  authorities.
- **Missing tests:** Deterministic composition; dependency lock; missing
  capability; secret placeholders; simulation without side effects; partial
  installation rollback; activation approval; immutable versions; instance
  upgrade/data migration; rollback; uninstall.
- **Dependencies:** All G-01 through G-10, plus Organization/Team authority and
  operator recovery.
- **Security implications:** A Team Template aggregates code, permissions,
  secrets, cloud use, schedules, and workflows. It must not self-authorize
  installation or activation.
- **Recommended epic:** **P1 — Team Template Contract and Validation**, then
  **P1 — Governed Template Install/Simulate/Activate Lifecycle**.
- **Recommended priority:** **P1**, after its P0 authorities; mandatory for
  organization-first v2.
- **Migration or compatibility concerns:** Existing Lucy employee packs and
  workflow templates require conversion and explicit dependency manifests.
  Filesystem grouping must not imply a trusted published package.

### G-12 — Team Architect plan/review/apply protocol

- **Classification:** **Missing** in Core and the inspected Lucy evidence.
- **Current evidence:** The roadmap defines Team Architect as a required core
  employee and guided user experience, but explicitly not as publishing,
  permission, approval, secret, workflow, scheduling, or activation authority.
- **Authoritative files:** `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`,
  `docs/architecture/v2/EXECUTION_PLANE.md`, and
  `docs/architecture/v2/INTELLIGENCE_PLANE.md`.
- **Lucy donor evidence:** `../lucy-runtime-reference/leos-console/app.py`
  supplies broad setup and workforce UX ideas, and Lucy employee packs supply
  examples. No canonical Team Architect employee or plan/review/apply protocol
  was found.
- **Missing contracts:** User intent; architecture proposal; alternatives and
  rationale; dependency plan; permission/secret/cloud requirements; cost and
  resource estimate; validation/simulation; review decision; approved apply
  plan; operation results; resumable correction.
- **Missing services:** Prefer a core Employee definition and guided UI
  composing existing authorities. A small proposal/apply coordinator may be
  justified only if its durable responsibility cannot fit Workflow/Template
  lifecycle.
- **Missing tests:** Natural-language ambiguity; no-action-before-review;
  permission and secret escalation; dependency failure; simulation;
  cancellation; partial apply rollback; plan tampering; repeatability; audit
  and correlation.
- **Dependencies:** Team Template, Organization/Team, Workflow, Plugin, grants,
  approval, secrets, sandbox, models, cost/resource inventory, and publishing.
- **Security implications:** Team Architect is a high-leverage confused-deputy
  risk. It must propose and request; verified authorities must apply.
- **Recommended epic:** **P1 — Team Architect Plan/Review/Apply Contract and
  Reference Employee**.
- **Recommended priority:** **P1**, after P0 dependencies and Team Template
  definition.
- **Migration or compatibility concerns:** Do not implement Team Architect as
  a privileged monolith or teach it Lucy’s direct service mutations.

### G-13 — Memory, knowledge, provenance, artifacts, and history ingestion

- **Classification:** **Partially Implemented** in Core; **Lucy Donor Evidence
  Only / Conflicting Authority**.
- **Current evidence:** Persistent Runtime stores durable working state, while
  the reference research employee has bounded source/artifact provenance.
  There is no canonical cross-employee knowledge, episodic memory, learned
  procedure, retention, correction, or imported-history authority.
- **Authoritative files:** `docs/architecture/v2/EXECUTION_PLANE.md`,
  `services/persistent-employee-runtime-service/app/main.py`,
  `contracts/research-content-artifact.v1.schema.json`,
  `contracts/research-source.v1.schema.json`, and
  `docs/phase52.3-reference-research-content-employee.md`.
- **Lucy donor evidence:** `../lucy-runtime-reference/memory-service/app.py`
  provides simple memory CRUD/search;
  `../lucy-runtime-reference/employee-learning-service/app/main.py` stores job
  artifacts, memories, review state, retrieval events, corrections, and
  profiles;
  `../lucy-runtime-reference/experience-engine-service/app/main.py` separately
  owns experiences and playbooks;
  `../lucy-runtime-reference/company-knowledge-service/app.py` owns another
  knowledge store; and
  `../lucy-runtime-reference/leos-persistence-service/app/main.py` provides
  additional generic persistence.
- **Missing contracts:** Memory classes and scopes; source/provenance;
  artifact identity; derivation; confidence; trust/review state; correction
  and supersession; retention/deletion; retrieval evidence; prompt-use audit;
  team/organization knowledge; import session and consent; source connector.
- **Missing services:** Canonical knowledge/artifact authority and bounded
  retrieval interface. The architecture must decide whether learning,
  experience, playbook, and knowledge are projections or separate object
  types under one authority.
- **Missing tests:** Provenance preservation; prompt-injection isolation;
  deduplication; correction/supersession; deletion propagation; access scope;
  untrusted versus approved retrieval; retention; export; history-import
  consent; audit; deterministic intelligence-fixture conformance; optional
  pinned local embedding/reranking integration; truthful fixture failure and
  malformed-response handling; absence of fixture state from production; and
  deterministic evaluation of production-per-token effects.
- **Dependencies:** Organization scope, identity, permissions, approval,
  secrets, artifacts, Workflow, Cognitive Service context assembly, embedding,
  reranking, and data portability.
- **Security implications:** Memory can retain secrets, poisoned instructions,
  personal data, copyrighted material, or cross-team data. Recursive learning
  without review and provenance can amplify errors.
- **Recommended epic:** **P0 — Knowledge, Artifact, Memory, and Provenance
  Authority**, followed by **P2 — Governed History Ingestion Framework**.
- **Recommended priority:** **P0** for safe persistent learning; source-specific
  import connectors can be **P2 or post-v1**.
- **Migration or compatibility concerns:** Lucy has competing stores and IDs.
  Define a migration envelope and provenance mapping before importing. Do not
  make raw Lucy databases or embeddings canonical.

### G-14 — Model and specialized-service onboarding

- **Classification:** **Partially Implemented** in Core; **Lucy Donor Evidence
  Only / Conflicting Authority**.
- **Current evidence:** Model Registry owns facts/bindings, Ranking Policy owns
  order, Capability Manager resolves, Dispatcher invokes, and Router/adapters
  transport. Core lacks a complete discover/install/activate/health/register
  path for local and cloud runtimes or specialized model services.
- **Authoritative files:** `docs/architecture/v2/INTELLIGENCE_PLANE.md`,
  `docs/architecture/v2/INTELLIGENCE_PLANE_DECISIONS.md`,
  `services/model-registry-service/app/main.py`,
  `services/ranking-policy-service/app/main.py`,
  `services/capability-manager-service/app/main.py`, and
  `services/execution-dispatcher-service/app/main.py`.
- **Lucy donor evidence:** `../lucy-runtime-reference/model-registry/app.py`
  and `../lucy-runtime-reference/provider-registry/app.py` provide older model
  and provider stores. `../lucy-runtime-reference/router/app.py` supplies
  transport donor code but contains fallback/substitution behavior.
  Specialized donors are `../lucy-runtime-reference/embed-service/app.py`,
  `../lucy-runtime-reference/rerank-service/app.py`,
  `../lucy-runtime-reference/ocr-service/app.py`,
  `../lucy-runtime-reference/vision-service/app.py`, and
  `../lucy-runtime-reference/speech-service/app.py`.
- **Missing contracts:** Runtime/provider onboarding plan; model artifact and
  license; hardware compatibility; install/activation; health/readiness;
  capability declaration; endpoint binding; secret requirement; unload;
  rollback; specialized request/result schemas; usage and cost evidence.
- **Missing services:** Governed onboarding/activation workflow and transport
  adapters for at least one local model path and one explicit-permission cloud
  path. Specialized services should be provider implementations, not new
  selection authorities.
- **Missing tests:** Model discovery/import; license/provenance; capacity;
  activation failure/rollback; health changes without reordering; exact-list
  selection; no silent substitution; local/cloud permission; specialized
  normalization; unload/resource release.
- **Dependencies:** Plugin/publishing, secrets, Scheduler resources, Model
  Registry, Ranking Policy, Capability Manager, Dispatcher, Router/adapters,
  observability, and cost accounting.
- **Security implications:** Model artifacts and runtimes are supply-chain and
  resource risks. Cloud onboarding can leak data without explicit permission.
  Router fallback can violate user sovereignty.
- **Recommended epic:** **P1 — Governed Model/Provider Onboarding and
  Activation**, followed by **P1 — Specialized Intelligence Provider
  Promotion**.
- **Recommended priority:** **P1**, required for a productive release after
  security authorities exist.
- **Migration or compatibility concerns:** Migrate model/provider facts into
  canonical registries. Remove score/priority authority and fallback from
  donor Router logic; preserve only protocol compatibility.

### G-15 — Installer, First Run, operations, recovery, and cost

- **Classification:** **Partially Implemented**; Lucy is **Donor Evidence
  Only**.
- **Current evidence:** Hardware/profile recommendation, idempotent installation
  planning and journaling, First Run configuration/readiness, CLI/doctor,
  security posture, health, metrics fixtures, and diagnostic bundles have
  contracts and tests. First Run is not a complete runtime/model/plugin/team
  activation experience. Backup/update are non-executing plans, and canonical
  production-per-token/cost accounting is absent.
- **Authoritative files:** `contracts/installation-plan.v1.schema.json`,
  `contracts/installation-transaction.v1.schema.json`,
  `contracts/first-run-session.v1.schema.json`,
  `contracts/first-run-result.v1.schema.json`,
  `contracts/backup-plan.v1.schema.json`,
  `contracts/update-plan.v1.schema.json`,
  `contracts/metrics-snapshot.v1.schema.json`,
  `tools/installer_bootstrap.py`, `tools/first_run.py`,
  `tools/operator_cli.py`, and `tools/security_observability.py`.
- **Lucy donor evidence:** `../lucy-runtime-reference/leos-console/app.py`
  contains setup, operations, workforce, model, plugin, workflow, and
  observability routes. Lucy also retains matching phase tests under
  `../lucy-runtime-reference/tests/phase5241/test_installation_profile.py`,
  `../lucy-runtime-reference/tests/phase5242/test_installer_bootstrap.py`, and
  `../lucy-runtime-reference/tests/phase5243/test_first_run.py`.
- **Missing contracts:** Full rollback result if it remains a public outcome;
  runtime/model/plugin activation plan; backup execution/result and restore;
  update execution/result; recovery point; service-data ownership; usage
  ledger; token/cost/latency/energy attribution; production outcome linkage.
- **Missing services:** Governed backup/restore and update executors; runtime
  activation integration; durable telemetry/usage collection; cost and
  production-per-token reporting.
- **Missing tests:** Clean-machine end to end; interrupted install recovery;
  backup/restore integrity; failed update rollback; offline mode; migration
  compatibility; credential exclusion; multi-service telemetry correlation;
  token/cost attribution; degraded-service UX.
- **Dependencies:** All installable object lifecycles, secrets, publishing,
  model activation, service data ownership, observability, and operator
  authorization.
- **Security implications:** Recovery bundles and diagnostics can leak secrets
  or personal data. Update and restore are privileged supply-chain actions.
  Cost data requires accurate identity/correlation and tamper resistance.
- **Recommended epic:** **P1 — Guided First Run and Activation Integration**,
  **P1 — Backup/Restore and Update Execution**, and **P2 — Usage, Cost, and
  Production-per-Token Accounting**.
- **Recommended priority:** **P1** for release operability; advanced
  optimization is **P2**.
- **Migration or compatibility concerns:** Extend the tested Core tools rather
  than replacing them with Lucy console calls. Preserve plan/apply separation
  and offline-safe behavior.

### G-16 — Core LEOS employees and organization-first guided UI

- **Classification:** **Partially Implemented** in Core; **Lucy Donor Evidence
  Only / Experimental**.
- **Current evidence:** Core includes a manual Employee Builder and a reference
  research-content employee. It does not include the mandatory Team Architect
  or a guided Organization/Department/Team/Workflow/Template console.
- **Authoritative files:** `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`,
  `services/employee-builder/app.py`,
  `services/employee-builder/templates/research-content.yaml`, and
  `services/reference-research-content-employee/app.py`.
- **Lucy donor evidence:** `../lucy-runtime-reference/leos-console/app.py`
  provides extensive operations, workforce, organization intelligence,
  plugins, planning, workflow, memory, and setup UI donor routes.
  `../lucy-runtime-reference/employee-packs/sam-communications/pack.yaml`,
  `../lucy-runtime-reference/employees/research-employee/employee.yaml`, and
  `../lucy-runtime-reference/employees/writer-employee/employee.yaml` provide
  content examples, but the console and packs are tightly coupled to Lucy
  service contracts and duplicated authorities.
- **Missing contracts:** Guided setup session; organization proposal; Team
  Architect plan/review/apply; dependency and permission presentation;
  simulation result; activation handoff; resumability; accessibility and
  operator error outcomes.
- **Missing services:** Team Architect reference employee and an
  organization-first console/BFF that composes canonical services without
  owning their state.
- **Missing tests:** Non-coder happy path; accessibility; incomplete
  dependencies; denied cloud/secrets/permissions; no mutation before apply;
  restart/resume; simulation; activation approval; error recovery; audit
  drill-down; clean installation acceptance.
- **Dependencies:** G-01 through G-15, particularly Team Templates,
  permissions, Workflow, approval, secrets, sandbox, model onboarding, and
  recovery.
- **Security implications:** A convenient UI can conceal privileged actions or
  authority changes. Every proposed mutation must expose dependencies,
  permissions, cloud use, cost, and approval state.
- **Recommended epic:** **P1 — Core Employees**, then **P1 — Organization-First
  Guided Console**, with Team Architect as the flagship acceptance path.
- **Recommended priority:** **P1 / required product outcome**, after underlying
  P0 authorities.
- **Migration or compatibility concerns:** Reuse Lucy information architecture
  and interaction ideas selectively. Do not preserve its direct calls to
  obsolete or competing registries as compatibility requirements.

Core-role status is therefore:

| Core role | Classification | Audit result |
|---|---|---|
| Team Architect | **Missing** | Mandatory v2 role; blocked on Team Template and governance prerequisites. |
| LEOS Guide | **Documentation Only** | Candidate role named by the roadmap; no governed definition or acceptance tests found. |
| System Administrator | **Documentation Only** | Candidate role named by the roadmap; must remain least-privilege and cannot become an ambient superuser. |
| Knowledge Curator | **Documentation Only** | Candidate role named by the roadmap; blocked on canonical knowledge/provenance authority. |
| Workflow Builder | **Documentation Only** | Candidate role named by the roadmap; blocked on canonical Workflow authority. |
| Reference Research Content Employee | **Partially Implemented** | Real bounded reference employee and provenance artifacts exist, but it is not an organization-management employee. |

## 6. Authority-conflict inventory

| Conflict | Accepted authority | Conflicting donor behavior | Required disposition |
|---|---|---|---|
| Capability inventory and resolution | Capability Manager | Lucy capability-registry, module-registry, plugin-platform registration, provider-registry resolver | Migrate facts to Capability Manager; retire peer resolvers and implicit registration authority. |
| Provider/model order | Ranking Policy Authority | Provider score/priority and Router fallback/defaults | Remove selection semantics from donors; keep only facts or transport code. |
| Invocation | Execution Dispatcher | Tool Runtime and Adapter Manager directly execute operations; Router may substitute | Route all governed operations through Dispatcher; adapters transport only. |
| Approval | Future authenticated Approval Authority | Caller Boolean, opaque reference existence, workflow-local approval state | Define verifiable scoped grants; local workflow state may only reference them. |
| Workflow lifecycle | **OPEN**, one future canonical authority | Two workflow engines plus Planning lifecycle and autonomous continuation | Select one state machine; make planning produce definitions/plans rather than run authority. |
| Plugin/module lifecycle | **OPEN**, one future canonical local authority | Plugin Platform and Module Registry both install/register/state-change/remove | Define one object and installed-instance model; migrate or retire duplicates. |
| Memory/experience/knowledge/artifacts | **OPEN** | Memory Service, Employee Learning, Experience Engine, Company Knowledge, generic persistence | Define object boundaries and one source of truth; treat derived indexes/playbooks as projections where possible. |
| Organization structure | **OPEN** | Lucy configuration paths and Organization Intelligence graph/snapshots | Establish canonical definitions; Organization Intelligence becomes a consumer/projection. |
| Secrets | Future Secret Authority | Environment variables, Config Service, kernel-variable resolution | Use opaque references and transient authorized resolution; never promote raw values. |
| Scheduling and resource control | Scheduler | Workflow/planning/autonomous services may drive continuation directly | Workflow submits governed jobs; Scheduler alone owns leases/admission/release. |
| Employee reasoning and durable state | Cognitive Service / Persistent Runtime | Legacy orchestration services may blend planning, continuation, and employee state | Migrate only necessary behavior into the accepted split; retire restart/reasoning peers. |
| Release publishing versus product publishing | Release engineering versus future Publishing Authority | Source publication report can be mistaken for plugin/template publishing | Keep separate terms and contracts: source release, published artifact, installed instance, active runtime. |

## 7. Prerequisite dependency graph

The graph shows authority prerequisites, not necessarily one epic per box.

```text
Publishing authority + artifact identity
├── Plugin manifest/SDK/trust/lifecycle
│   ├── Capability declarations and grants
│   ├── Tool contracts
│   │   ├── Verifiable approval grants
│   │   ├── Secret resolution
│   │   └── Sandbox/workspace boundary
│   └── Model/provider and specialized-service onboarding
│
Organization/Department/Team authority
├── Organizational policy boundary
├── Workflow definition/lifecycle
│   ├── Scheduler projection
│   └── Artifact and approval waits
└── Knowledge/memory/provenance scope

Publishing + Organization + Workflow + Plugin/Tool governance
└── Team Template definition and installed-instance lifecycle
    ├── simulation
    ├── reviewed activation
    └── upgrade/rollback

Team Template + all governed dependencies
└── Team Architect plan/review/apply
    └── Organization-first guided UI and flagship templates

Installer/First Run + recovery + observability/cost
└── supports every install, activation, update, and operator path above
```

Existing execution and intelligence authorities underlay the whole graph:

```text
Scheduler -> Persistent Runtime -> Cognitive Service -> Dispatcher
                                                       |
                                                       v
                                            Capability Manager
                                                       |
                          Ranking Policy + Model Registry facts
                                                       |
                                                       v
                                            Provider/tool adapter
```

Organization-first work must compose this spine; it must not insert a second
reasoner, resolver, invoker, scheduler, or transport selector.

## 8. Recommended formal epic sequence

### Foundation lock and publishing

1. **Epic 3.0 — Architecture Lock and Authority Registry**
   - Record canonical owners, object vocabulary, lifecycle vocabulary, event
     boundaries, and compatibility/versioning rules.
2. **Epic 3.1 — Publishing Authority and Artifact Contracts**
   - Define artifact, version, publisher, dependency, provenance, signature,
     compatibility, and public/private protocol boundaries.
3. **Epic 3.2 — Local Artifact Verification and Lifecycle**
   - Implement later, after contract review: inspect, install, update,
     rollback, revoke, remove, and evidence.

### Organization and work definition

4. **Epic 3.3 — Organization, Department, and Team Domain**
   - Definitions, revisions, lifecycle, membership, policy references, and
     audit.
5. **Epic 3.4 — Organizational Policy Boundary**
   - Decide restriction inheritance and whether any new ranking scope is
     allowed; preserve current precedence until accepted.
6. **Epic 3.5 — Workflow Definition and Lifecycle**
   - Definition, validation, scheduler projection, correlation, approval wait,
     cancellation, compensation, and resume.

### Extension and governance plane

7. **Epic 3.6 — Plugin Contract and Public SDK**
   - Manifest, declarations, configuration, compatibility, trust,
     dependencies, and validation.
8. **Epic 3.7 — Capability Grants and Permission Authority**
   - Separate declaration/inventory/grant/eligibility/resolution.
9. **Epic 3.8 — Tool Contract and Dispatcher Adapter Boundary**
   - Tool operations, schemas, side effects, idempotency, results, and audit.
10. **Epic 3.9 — Verifiable Approval Authority**
    - Authenticated scoped grants, verification, expiry, revocation, and use.
11. **Epic 3.10 — Secret Authority and Transient Resolution**
    - Opaque references, least-privilege resolution, rotation, redaction.
12. **Epic 3.11 — Sandbox and Workspace Authority**
    - Filesystem, network, process, resource, secret, artifact, and cleanup
      boundaries.
13. **Epic 3.12 — Governed Plugin Installation and Isolation**
    - Implement only after Epics 3.6 through 3.11 define the safety envelope.

### Knowledge and intelligence onboarding

**Phase 5.0 — Non-authoritative Intelligence Test Fixture**

- Establish deterministic test/reference embedding and reranking behavior
  before knowledge-plane conformance.
- Permit an optional pinned local runtime for integration testing.
- Use no cloud service, production credential, production onboarding path, or
  production authority state.
- Exercise Capability Manager resolution, Dispatcher invocation, and adapter
  transport where practical; do not create direct knowledge-plane or Cognitive
  Service model invocation.
- Keep configuration, persistence, and temporary authority records isolated
  and removable without production migration obligations.

14. **Epic 3.13 — Knowledge, Artifact, Memory, and Provenance Authority**
    - Define canonical objects, review/trust, retention, retrieval, correction,
      and scope. Acceptance includes deterministic fixture conformance,
      optional real local embedding/reranking integration, truthful failure
      behavior, retained provenance/scope, and no fixture state in production.
15. **Epic 3.14 — Model/Provider Onboarding and Activation**
    - Complete local and explicit-permission cloud paths using existing
      ranking, registry, resolution, dispatch, and transport authorities, then
      rerun the same Phase 5 knowledge integration suite through this
      production onboarding path.
16. **Epic 3.15 — Specialized Intelligence Providers**
    - Deliberately promote embedding and reranking first, then OCR, vision, and
      speech according to product acceptance needs.

### Organization-first product

17. **Epic 3.16 — Team Template Contract and Validation**
    - Immutable definitions, dependencies, parameters, policies, tests, and
      compatibility.
18. **Epic 3.17 — Team Template Install, Simulate, Activate, Upgrade, Rollback**
    - Separate published definition from installed and active instances.
19. **Epic 3.18 — Team Architect Plan/Review/Apply**
    - Core employee plus explicit proposal and approved-apply handoff.
20. **Epic 3.19 — Guided Organization-First Console and Core Employees**
    - Non-coder onboarding, dependency disclosure, simulation, approvals,
      activation, audit, and recovery.

### Release operability

21. **Epic 3.20 — First Run Activation and Recovery**
    - Join installation, runtime/model/plugin onboarding, backup/restore, and
      update rollback.
22. **Epic 3.21 — Usage, Cost, and Production-per-Token Accounting**
    - Correlate tokens, provider cost, latency, resources, and accepted
      externally grounded production outcomes. PPT is observational reporting
      only, never selection, eligibility, ranking, fallback, retry,
      re-resolution, or escalation authority. Attribution includes retrieval,
      embedding, reranking, revision, verification, and resources, and reports
      expose underlying evidence rather than only a composite.
23. **Epic 3.22 — Dev Preview v2 Organization Acceptance**
    - Clean-machine install to a simulated and approved active flagship team,
      with audit, recovery, and no Lucy runtime dependency.

The numbering is proposed and must not overwrite already assigned project
numbers without release-management review.

## 9. Explicit Dev Preview v2.0 must-haves

The following are required to support the approved organization-first promise:

1. One documented source of authority for every new object and lifecycle.
2. Canonical publication artifact, immutable version, dependency, provenance,
   compatibility, and signature/trust contracts.
3. Public Plugin manifest/SDK and a governed local install/update/rollback/
   removal path.
4. Canonical Organization, Department, Team, and Workflow definitions with
   lifecycle and audit.
5. Explicit capability declarations, least-privilege grants, revocation, and
   eligibility integration.
6. First-class Tool operations with schemas, side-effect classification, and
   idempotency semantics, invoked only through Dispatcher.
7. Verifiable approval grants; no caller Boolean or opaque reference
   authorization.
8. Opaque secret references and authorized transient resolution.
9. A governed sandbox/workspace boundary for side-effecting tools and
   third-party plugins.
10. Canonical knowledge/memory/artifact provenance sufficient for safe
    context reuse, correction, deletion, and audit.
11. A complete model/provider onboarding and activation path with at least one
    local runtime acceptance path and one explicitly authorized cloud path.
12. Embedding and reranking available through governed provider onboarding if
    they are used to support the release’s production-per-token claim.
13. Team Template definition, dependency validation, installation,
    side-effect-free simulation, reviewed activation, upgrade, and rollback.
14. Team Architect as a core employee using plan/review/apply rather than
    privileged direct mutation.
15. Organization-first guided UI that a non-coder can use to create, inspect,
    test, activate, and recover a useful team.
16. Installer/First Run integration, backup/restore, failed-update rollback,
    security posture, correlated observability, and usage/cost evidence.
17. At least one flagship Team Template proven from a clean installation with
    no undocumented Lucy runtime dependency.

## 10. Items that should remain post-v1 or outside public Core

These items should not block the minimum open Core unless a later approved
decision changes scope:

- hosted marketplace billing, entitlement, fraud detection, and private
  moderation;
- official proprietary connectors and premium policy packs;
- hosted multi-tenant control-plane operations;
- enterprise identity federation, fleet management, high availability, and
  compliance packages;
- automatic organization redesign or self-activation without human review;
- broad autonomous promotion of memories into trusted playbooks;
- source-specific import connectors for every chat, drive, email, or SaaS
  provider (the safe import/provenance framework belongs in Core);
- advanced organization-intelligence optimization and predictive workforce
  analytics;
- opaque “best model” scoring, automatic provider substitution, or emergency
  model pools; these are not deferred features but rejected authority models;
- a second marketplace, resolver, invoker, scheduler, cognitive runtime, or
  secret store inside Core.

Embedding and reranking are not automatically post-v1: they are release
dependencies if the v2 acceptance claims rely on them. OCR, vision, and speech
may follow as later provider plugins unless a flagship Team Template requires
them.

## 11. Unresolved architecture decisions

The following questions must remain **OPEN** until explicit decisions and
contracts are accepted:

1. What public Core component owns publishing artifact metadata, and which
   responsibilities remain only in private publication/marketplace systems?
2. Is Organization/Department/Team lifecycle one authority or several
   authorities sharing a revision/event protocol?
3. Can organization or team policy add ranking scopes, or may it only add
   cumulative hard restrictions? If scopes are added, where do they sit
   relative to `job > employee > capability > global`?
4. Which single service owns Workflow definitions and lifecycle, and how are
   workflow state and Scheduler job/lease state projected without dual writes?
5. Are plugin, adapter, model-provider package, employee package, workflow
   package, and Team Template variants of one artifact envelope?
6. What is the canonical split among capability declaration, live inventory,
   permission grant, eligibility facts, and resolution?
7. Does Tool catalog persistence belong to Plugin authority, Capability
   Manager, Dispatcher, or a dedicated declaration authority?
8. What identity and authentication authority issues and verifies approval
   grants, publisher signatures, operator actions, and organization roles?
9. Which secret backends must the open Core support, and which component owns
   short-lived secret leases and redaction policy?
10. Is the sandbox implemented by a Core service, a runtime adapter contract,
    or both? What isolation level is acceptable for Dev Preview v2?
11. What are the canonical differences among working state, episodic memory,
    knowledge, experience, playbook, artifact, and audit event?
12. Which data can Cognitive Service assemble automatically, and which
    knowledge requires user review or an explicit trust grant?
13. What is the authoritative source for externally grounded production
    outcome evidence, and how are production value, attribution, comparison
    cohorts, and delayed or reused outcomes normalized for PPT reporting?
14. How is a published Team Template instance revised when its employees,
    workflows, plugins, models, or policies have independent versions?
15. Which actions Team Architect may apply after one reviewed plan, and which
    require separate installation, permission, secret, cloud, or activation
    grants?
16. What release acceptance threshold distinguishes a guided development
    preview from a production security claim?

## 12. Lucy preservation, promotion, and retirement guidance

### Highest-value donor candidates for deliberate inspection

1. `../lucy-runtime-reference/plugin-registry-service/app/main.py` for package,
   moderation, advisory, and publisher workflow concepts.
2. `../lucy-runtime-reference/plugin-platform-service/app/main.py` and
   `../lucy-runtime-reference/plugin-platform-service/app/registry_routes.py`
   for installed-instance and runtime lifecycle behavior.
3. `../lucy-runtime-reference/workflow-engine-service/app/main.py` for step,
   dependency, artifact, event, and durable resume concepts.
4. `../lucy-runtime-reference/employee-learning-service/app/main.py` for
   provenance, review, correction, retrieval audit, and job-artifact concepts.
5. `../lucy-runtime-reference/leos-console/app.py` for navigation, operator
   vocabulary, and organization-first UX research.
6. Specialized service donors for protocol and model-loading behavior, led by
   embedding and reranking.

### Responsibilities likely to retire rather than promote

- Lucy provider scoring/priority and Router fallback or substitution.
- Capability Registry as a peer resolver to Capability Manager.
- Direct normal-path invocation by Tool Runtime or Adapter Manager.
- Caller-provided approval Booleans and locally self-verified approval state.
- Multiple plugin/module installation and registry authorities.
- Multiple workflow lifecycle/continuation authorities.
- Memory, experience, playbook, knowledge, and generic persistence stores all
  acting as independent sources of truth.
- Organization Intelligence acting as definition/lifecycle authority.

Retirement does not imply deleting evidence. Lucy remains immutable donor
evidence until migration decisions and acceptance tests are complete.

## 13. Recommended deeper-inspection order

1. Publishing Registry and Plugin Platform package/trust/install behavior.
2. Module Registry and Capability Registry overlap with Capability Manager.
3. Tool Runtime, Adapter Manager, Approval Service, and Policy Engine as one
   governance/invocation cluster.
4. Both Workflow Engines plus Planning lifecycle/continuation as one authority
   reconciliation.
5. Organization configuration and Organization Intelligence projections.
6. Employee Learning, Experience Engine, Memory Service, Company Knowledge,
   and Persistence as one data-authority reconciliation.
7. Provider Registry, Router, model runtime activation, then specialized
   embedding/reranking/OCR/vision/speech donors.
8. Lucy Console only after canonical APIs are chosen, using it as UX evidence
   rather than service authority.

For each donor cluster, the next review should capture APIs, persistence,
dependencies, security assumptions, direct callers, test coverage, data
migration needs, and the exact portions to preserve or retire.

## 14. Audit conclusion

LEOS Core can support the organization-first direction without discarding its
completed execution and intelligence work. The safe path is additive at the
product layer and conservative at authority boundaries:

- keep Scheduler, Persistent Runtime, Cognitive Service, Dispatcher,
  Capability Manager, Ranking Policy, Model Registry, and Employee Registry in
  their accepted roles;
- define the missing artifact, organization, workflow, extension, permission,
  approval, secret, sandbox, template, and knowledge authorities;
- promote Lucy code only after contract and security reconciliation;
- make Team Architect a governed planner and guided employee, never a hidden
  superuser;
- prove the release through a clean, reversible, auditable Team Template
  lifecycle.

Until those prerequisites are complete, LEOS has a credible technical
foundation but not yet a complete organization operating system.
