# LEOS Dev Preview v2 — Scope Lock

## Status

**Target:** LEOS 0.2.0 Developer Preview v2
**Scope state:** Initial architecture and must-have lock
**Evidence baseline:** `LEOS_DEV_PREVIEW_V2_GAP_REPORT.md`
**Authority index:** `../architecture/v2/AUTHORITY_REGISTRY.md`

This document fixes the minimum product and architecture outcomes required for
Dev Preview v2 planning. It does not claim that the listed systems are
implemented, and it does not assign owners that the Authority Registry marks
**OPEN**.

Adding a release blocker requires an explicit roadmap decision. Removing or
weakening a locked must-have requires an explicit architecture and product
decision; implementation convenience is not sufficient.

## Release objective

Dev Preview v2 must prove that a non-coder can create and operate a useful,
governed AI organization through a local-first installation without depending
on Lucy as an undocumented runtime authority.

The reference release journey is:

```text
Clean installation
  -> First Run and operator readiness
  -> governed local model/runtime onboarding
  -> optional explicitly permitted cloud-provider onboarding
  -> Team Architect proposal
  -> dependency, permission, secret, cloud, resource, and cost review
  -> Team Template installation
  -> side-effect-controlled simulation
  -> verifiable activation approval
  -> useful workflow and employee assignment
  -> correlated execution, artifacts, provenance, and outcome evidence
  -> restart and recovery
  -> update or rollback
```

The release is not complete if that journey requires direct Lucy APIs,
manually edited hidden authority state, caller-supplied approval, silent model
substitution, or an undocumented compatibility service.

## Locked authority invariants

Every must-have below is governed by these invariants:

1. Scheduler owns jobs, leases, and resource admission/release.
2. Persistent Employee Runtime owns durable employee/assignment state,
   mailbox, and working-state storage, but not reasoning.
3. Employee Cognitive Service owns the reasoning lifecycle and never invokes
   providers directly.
4. Ranking Policy Authority owns user-authored provider/model order.
5. Eligibility eliminates invalid candidates and never reorders survivors.
6. Capability Manager owns provider/capability inventory, eligibility,
   resolution, and rationale, but never invokes.
7. Model Registry owns model facts and model-provider/runtime bindings.
8. Execution Dispatcher is the sole governed provider/tool invocation
   authority and never selects.
9. AI Router and adapters transport an already-authorized request only.
10. Runtime Execution Coordinator, if retained, observes and awaits only.
11. Retry, re-resolution, assignment retry, cognitive retry, and escalation
    are distinct operations.
12. Human approval requires an explicit verifiable grant.
13. Raw credentials never enter governed records, prompts, events, memory,
    logs, diagnostics, source, tests, or fixtures.
14. Lucy is immutable donor evidence, never source authority.
15. Phase 5.0 fixtures are non-authoritative and leave no production state.
16. PPT is observational evidence only and never influences selection,
    eligibility, ranking, resolution, fallback, retry, re-resolution, or
    escalation.

The complete accepted and **OPEN** boundaries are indexed by
`../architecture/v2/AUTHORITY_REGISTRY.md`.

## Dev Preview v2 must-haves

### 1. Trust, ownership, and authority evidence

Required outcome:

- every authority-bearing mutation identifies a trustworthy actor;
- every managed object has unambiguous identity, revision, and ownership
  evidence appropriate to its scope;
- permission, approval, and secret use are independently verifiable;
- events, projections, observations, and audits cannot become hidden state
  authorities; and
- all still-unresolved owners remain **OPEN** until accepted decisions exist.

This locks the outcome, not a particular identity product, message broker, or
microservice topology.

### 2. Publishing and artifact lifecycle

Required outcome:

- canonical artifact identity and immutable version;
- publisher and provenance evidence;
- dependency, compatibility, license, digest, signature, and trust evidence;
- clear public Core versus private marketplace/service boundary;
- separate published artifact, installed instance, configured instance, and
  active runtime concepts; and
- governed inspect, plan, install, update, rollback, revoke, remove, and audit
  behavior.

Source-release publication is not sufficient evidence of this lifecycle.

### 3. Organization, Department, and Team domain

Required outcome:

- canonical definitions, revisions, lifecycle, membership, reporting
  relationships, policy references, ownership, and audit;
- no duplication of Employee Registry, Persistent Runtime, Scheduler, or
  Cognitive Service state;
- organization/team policy cannot silently add ranking precedence; and
- the origin and authority of employee-to-job assignment decisions is explicit
  and does not rely on legacy score, identifier order, caller `force`, or a
  peer job store; and
- cross-organization knowledge, secrets, permissions, and audit data remain
  isolated.

### 4. Workflow authority and lifecycle

Required outcome:

- versioned definition, parameters, triggers, steps, dependencies, outputs,
  artifacts, and validation;
- durable workflow-instance lifecycle, correlation, pause/resume/cancel, and
  restart recovery;
- explicit approval waits, retry versus escalation, and compensation
  semantics; and
- governed Scheduler projection without peer job, lease, assignment, or
  invocation authority.

### 5. Public Plugin layer

Required outcome:

- public manifest and SDK;
- plugin identity, version, compatibility, provenance, trust, dependencies,
  configuration, declared capabilities/tools/providers, permissions, secrets,
  isolation requirements, and data ownership;
- local install, enable, disable, update, rollback, revoke, remove, and health
  lifecycle; and
- no direct creation of grants, approvals, secrets, ranking, resolution, or
  invocation authority.

The public Plugin layer is mandatory. Hosted marketplace billing, entitlement,
fraud, and private moderation are not.

### 6. Capability grants and permissions

Required outcome:

- explicit separation of declaration, installed inventory, canonical
  inventory, permission grant, eligibility, and resolution;
- least privilege and default deny;
- subject, resource, action, scope, issuer, effective time, expiry,
  revocation, and decision evidence; and
- consistent enforcement for employee, workflow, team, plugin, tool, model,
  and cloud use.

Capability presence never implies permission.

### 7. Governed Tool operations

Required outcome:

- versioned Tool and operation identity;
- explicit input/output schemas;
- capability relationship;
- risk and side-effect classification;
- idempotency, timeout, cancellation, retry, and ambiguous-outcome semantics;
- required permissions, approvals, secrets, and sandbox profile; and
- Dispatcher invocation, result normalization, redaction, and audit.

No separate Tool Runtime may become a peer invocation authority.

### 8. Verifiable approvals

Required outcome:

- authenticated approval request and decision;
- scoped, expiring, revocable, verifiable grant;
- subject, action, resource, context/revision, issuer, and use evidence;
- fail-closed verification; and
- replay and wrong-scope rejection.

Caller Booleans and structurally valid opaque references are never authority.

### 9. Secret references and transient resolution

Required outcome:

- opaque references in governed configuration;
- authenticated and authorized resolution;
- least-privilege operation/target scope;
- transient injection;
- rotation, revocation, redaction, and audit;
- backup and diagnostic exclusion; and
- at least one safe local backend boundary.

Cloud onboarding and authenticated tools cannot be release-complete without
this outcome.

### 10. Sandbox and workspace boundary

Required outcome:

- declared filesystem, network, process, resource, secret, and artifact
  policy;
- isolated workspace identity and lifecycle;
- cleanup after completion, cancellation, failure, and restart;
- violation evidence and truthful termination; and
- no undeclared side effects during simulation.

Container execution alone is not sufficient evidence of the boundary.

### 11. Memory, knowledge, provenance, artifacts, and history foundation

Required outcome:

- explicit distinctions among working state, memory, knowledge, experience,
  playbook, artifact, source, and audit;
- ownership and organization/team/employee scopes;
- capture, provenance, trust/review, correction, supersession, retention,
  export, deletion, and retrieval-use evidence;
- protection against secret retention, cross-scope leakage, and untrusted
  instruction promotion; and
- governed history-ingestion framework.

Source-specific import connectors may be plugins and do not all belong in
public Core.

### 12. Phase 5.0 intelligence test fixture

Required development outcome:

- deterministic reference embedding/reranking behavior by default;
- optional pinned local runtime integration;
- canonical Capability Manager resolution, Dispatcher invocation, and adapter
  transport where practical;
- truthful failure, timeout, and malformed-response behavior;
- retained retrieval provenance and scope; and
- isolated temporary configuration, persistence, facts, bindings, ranking,
  and endpoints with no production residue.

It uses no cloud service, production credential, production installation path,
or production authority. Phase 6 reruns the same knowledge integration suite
through production onboarding.

### 13. Model, provider, and specialized-service onboarding

Required outcome:

- governed discover/configure, install or connect, register, activate, bind,
  observe, disable, update, rollback, and remove lifecycle;
- one complete local model/runtime acceptance path;
- one optional cloud path requiring explicit permission and authorized secret
  resolution;
- no silent substitution, fallback, emergency pool, or health-based
  reordering;
- accurate Model Registry, Ranking Policy, Capability Manager, Dispatcher, and
  adapter boundaries; and
- embedding, reranking, OCR, vision, speech-to-text, and text-to-speech through
  the same governed provider principles.

### 14. Team Template lifecycle

Required outcome:

- immutable published definition;
- employee, workflow, plugin, capability, tool, model, policy, permission,
  secret-placeholder, parameter, and validation-test references;
- dependency lock and compatibility evidence;
- separate installed instance and active Team/Organization state;
- governed install, configure, validate, simulate, approve, activate, upgrade,
  rollback, deactivate, and remove behavior; and
- no self-granted permission, secret, approval, or activation.

At least one flagship Team Template must pass clean-install acceptance.

### 15. Team Architect and core employees

Required outcome:

- Team Architect is a governed core employee using an explicit
  intent/proposal/explanation/dependency-plan/review/simulation/apply/verify
  protocol;
- Team Architect proposes and coordinates but never becomes publisher,
  installer, permission, approval, secret, Workflow, Scheduler, Dispatcher, or
  activation authority;
- plan modification invalidates prior approval where authority-bearing content
  changes; and
- LEOS Guide, System Administrator, Knowledge Curator, and Workflow Builder
  are included only under approved product scope and least privilege.

### 16. Organization-first guided experience

Required outcome:

- non-coder setup without required manual configuration editing;
- Organization, Team, Employee, Workflow, Plugin, model, permission, approval,
  knowledge, activity, cost, and health visibility;
- explicit dependency, cloud, secret, permission, resource, and cost review;
- side-effect-controlled simulation;
- resumable failure correction;
- reviewed activation; and
- audit and rollback access.

The UI composes canonical APIs and never owns canonical domain state.

### 17. Installation, operations, observability, and recovery

Required outcome:

- clean-machine installation and First Run;
- runtime, model, plugin, and Team Template activation integration;
- backup and restore;
- update, migration, failed-update rollback, and truthful irreversible-change
  reporting;
- offline/local-first operation;
- security posture, secret-safe diagnostics, and data export/deletion;
- correlated health, logs, metrics, audit, resource, token, and cost evidence;
  and
- restart recovery without duplicate external work.

Existing installer, First Run, operator, security, and observability baselines
must be extended rather than bypassed.

### 18. Outcome, cost, and PPT reporting

Required outcome:

- externally grounded outcome evidence;
- attribution to job, assignment, cognition, resolution, execution, workflow,
  Team, and Organization where applicable;
- attributable tokens, provider cost, latency, retrieval, embedding,
  reranking, revision, verification, and compute/resource costs;
- exposed underlying evidence and limitations; and
- no employee self-declaration of productive value.

PPT remains observational/reporting only and cannot influence runtime
selection, eligibility, or resolution.

## Deferred or post-v1 scope

The following do not block the minimum public Dev Preview v2 unless a later
approved decision promotes them:

- hosted marketplace billing, entitlement, fraud detection, and private
  moderation;
- official proprietary connectors and premium policy packs;
- hosted multi-tenant control plane;
- enterprise identity federation, fleet management, high availability, and
  compliance packages;
- automatic organization redesign or activation without human review;
- broad autonomous promotion of memory into trusted playbooks;
- a separate public-Core implementation for every history/SaaS connector;
- advanced predictive organization optimization;
- advanced PPT-driven recommendations beyond truthful observational reports;
- organization templates beyond the mandatory Team Template outcome unless a
  flagship acceptance journey requires them.

These are permanently prohibited rather than deferred:

- hidden provider/model scoring;
- silent fallback or substitution;
- implicit emergency or unranked candidate pools;
- caller-supplied approval authority;
- capability presence as permission;
- direct Cognitive/Persistent Runtime provider invocation;
- peer provider resolver, invocation, Scheduler, reasoning, or secret
  authorities; and
- Lucy as undocumented runtime or source authority.

## Required architecture decisions before implementation

The scope lock does not resolve the **OPEN** items in the Authority Registry.
The following decisions are prerequisites to their respective implementation
packages:

1. principal identity, authentication, and actor evidence;
2. common resource identity, ownership, and organization scope;
3. canonical event, causation, revision, replay, and delivery semantics;
4. publishing artifact and installed-instance authority;
5. Organization, Department, and Team lifecycle ownership;
6. employee-to-job assignment proposal/selection and Scheduler handoff;
7. organizational restriction and ranking interaction;
8. Workflow definition/lifecycle and Scheduler projection;
9. Plugin lifecycle and public/private publishing boundary;
10. capability declaration, grant, eligibility, and resolution split;
11. Tool identity/catalog and risk/idempotency vocabulary;
12. approval request/grant issuer and verification;
13. secret resolution and transient injection;
14. sandbox/workspace lifecycle and isolation level;
15. Team Template definition, instance, simulation, and activation;
16. memory/knowledge/artifact taxonomy and authority;
17. runtime/model activation and desired/observed topology;
18. outcome evidence and cost-attribution authority;
19. backup/restore/update execution and migration/rollback policy; and
20. repository-wide compatibility, deprecation, and event-schema evolution.

An implementation request that requires one of these decisions must stop if no
accepted document establishes it.

## Release acceptance gates

Dev Preview v2 is ready only when:

1. every required authority has an accepted owner and contract boundary;
2. the Authority Registry contains no release-blocking **OPEN** row;
3. canonical contract and semantic validation pass;
4. service unit, integration, conformance, restart, recovery, and negative
   tests pass for the release path;
5. no test fixture or Lucy state is present in production configuration or
   authority stores;
6. no secret, caller trust, silent ranking, fallback, or direct invocation
   bypass is found by adversarial review;
7. a clean installation completes the reference release journey;
8. the system restarts and resumes without duplicate external work;
9. an update and rollback or truthful irreversibility path is demonstrated;
10. artifacts, memory, outcomes, tokens, costs, and audit remain correlated;
11. a non-coder can inspect, correct, approve, activate, and recover the
    organization; and
12. no undocumented Lucy dependency remains.

## Change control

Each future epic must state:

- which locked must-have it advances;
- which Authority Registry rows it touches;
- accepted owners and forbidden overlaps;
- contracts and migrations;
- security and rollback implications;
- test and acceptance evidence; and
- any remaining **OPEN** decision.

An epic is not release-complete because its happy path works. It must satisfy
its authority, negative-test, restart/recovery, migration, documentation, and
audit obligations.
