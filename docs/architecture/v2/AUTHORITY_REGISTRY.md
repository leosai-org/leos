# LEOS v2 Authority Registry

## Status and purpose

This registry is the LEOS 0.2.0 Developer Preview v2 index of accepted
authority boundaries and explicitly unresolved authority gaps.

It consolidates decisions already accepted in:

- `EXECUTION_PLANE.md`
- `EXECUTION_PLANE_DECISIONS.md`
- `INTELLIGENCE_PLANE.md`
- `INTELLIGENCE_PLANE_DECISIONS.md`
- `EXECUTION_CONTRACTS.md`
- `IDENTITY_OWNERSHIP_AND_TRUST.md`
- `IDENTITY_OWNERSHIP_AND_TRUST_DECISIONS.md`
- `EFFECTIVE_RANKING_AND_MODEL_RESOLUTION.md`
- `../../roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`
- `../../roadmap/LEOS_DEV_PREVIEW_V2_GAP_REPORT.md`

This document does not assign an owner to a concern that those sources leave
**OPEN**. It prevents an implementation from acquiring authority merely
because it is convenient, cataloged, present in Lucy, or first to persist a
new object.

If this registry conflicts with an accepted plane decision, the plane decision
governs until the conflict is corrected. A future accepted ADR may update this
registry.

## Registry states

| State | Meaning |
|---|---|
| **ACCEPTED** | The canonical responsibility and owner are established by accepted architecture. |
| **COORDINATOR ONLY** | The component may initiate or coordinate governed work but is not the continuing state authority. |
| **OPEN** | Canonical ownership or the precise boundary is not accepted. Implementation must stop before creating a new authority. |
| **PROJECTION ONLY** | The component may retain a derived view but not originate or override canonical state. |
| **TRANSPORT ONLY** | The component carries an already-authorized operation and has no selection or governance authority. |
| **DONOR EVIDENCE ONLY** | Lucy or other historical behavior may be inspected but has no v2 authority. |
| **CONFLICTING / INVESTIGATE** | A current surface overlaps accepted owners and requires explicit migration, compatibility, and retirement review. |
| **DEPRECATED / RETIRE** | The responsibility conflicts with the accepted target and must not receive new canonical behavior. |

Implementation maturity is separate from authority state. An **ACCEPTED**
authority may still be incomplete, while a working Lucy service may remain
**DONOR EVIDENCE ONLY**.

## Accepted canonical authorities

| Concern or canonical object | Authority | State authority | Required boundary |
|---|---|---|---|
| Principal definition and lifecycle | Identity Authority | Principal identities, subject bindings, status, authentication-policy references, and revisions | Does not own domain resources, permission policy, approval, secrets, capability resolution, or execution. |
| Authenticated actor evidence | Identity Authority | Bounded Actor Context evidence after recognized authenticator verification | Contract validity or caller construction never authenticates; production authenticators remain **OPEN**. |
| Subject/action/resource authorization decision | Authorization Authority | Revisioned, evidence-backed, time-bounded allow/deny decisions | Does not authenticate, rank, resolve capabilities, issue approvals, or invoke. Policy/grant sources remain partly **OPEN**. |
| Common resource identity and ownership | Each accepted domain lifecycle authority | Its resource identity, exactly-one-owner evidence, revision, lifecycle transition, and audit identity | Identity Authority validates principal references; no central peer resource/ownership store. **OPEN** domain objects remain blocked. |
| Approval request, grant, and verification | Approval Authority | Requests, authenticated decisions, grant lifecycle, expiry, revocation, consumption, verification, audit, and events | Only trusted current `VERIFIED` evidence authorizes; no caller Boolean, reference existence, copied grant, or event authority. |
| Artifact trust evidence | Artifact Trust Authority | Digest, signature, provenance, trust-policy verification, and trust revocation evidence | Never publishes, installs, configures, grants, approves, or activates. Those lifecycle owners remain **OPEN**. |
| Secret-reference identity | Secret Authority | Opaque reference identity and protected-value lifecycle boundary | Reference possession never authorizes resolution; backend, transient injection, and production implementation remain **OPEN**. |
| Canonical event production | Authority that owns the represented state transition | Immutable event identity, source, producer, actor, subject revision, correlation, causation, time, and schema revision | Broker/delivery/event projections remain non-authoritative; outbox, ordering, replay, and retention remain **OPEN**. |
| Job lifecycle | Scheduler | Jobs and scheduler-owned job transitions | Does not own employee reasoning, provider resolution, or assignment working state. |
| Worker lease | Scheduler | Lease identity, acquisition, renewal, and release | No workflow, runtime, or coordinator may create a peer lease authority. |
| Compute/resource admission | Scheduler | Admission decisions and resource reservations | Employee resource profiles supply governed inputs; they do not admit work. |
| Employee resource profile | Employee Resource Profile Service | Canonical employee resource requirement/profile records | Does not select models or providers and does not replace Scheduler admission. |
| Employee definition and lifecycle | Employee Registry | Employee definitions, revisions, lifecycle, execution-eligibility decisions, and assignment-policy inputs | Legacy embedded model preferences are migration input, not ranking authority; employee-to-job selection remains **OPEN**. |
| Durable employee presence and mailbox | Persistent Employee Runtime | Durable employee presence, mailbox, and working-state storage | No reasoning, provider invocation, or scheduler lease ownership. |
| Assignment projection and transitions | Persistent Employee Runtime | Assignment identity, durable projection, and runtime-owned transitions | Scheduler remains job/lease authority; Cognitive Service remains reasoning authority. |
| Cognitive run | Employee Cognitive Service | Cognitive runs, attempts, checkpoints, observations, and cognitive results | No direct scheduler mutation, durable assignment ownership, or provider invocation. |
| Provider/model ranking | Ranking Policy Authority | User-authored ranking policies, scope resolution, and effective-ranking evidence | Ranking establishes order only. It does not evaluate provider eligibility or invoke targets. |
| Model facts | Model Registry | Normalized model identity, model facts, lifecycle, and revisions | No provider inventory, ranking, resolution, credentials, or invocation. |
| Model-provider/runtime binding | Model Registry | Binding identity, facts, lifecycle, and revision | Capability Manager consumes bindings; it does not copy their authority. |
| Provider inventory | Capability Manager | Provider records and revisions | Standalone Provider Registry is migration input and a retirement target. |
| Capability inventory | Capability Manager | Capability records and revisions | Capability presence does not imply a permission grant. |
| Provider-capability binding | Capability Manager | Provider-capability bindings and revisions | Model bindings remain Model Registry authority. |
| Eligibility and capability resolution | Capability Manager | Candidate eligibility decisions, resolutions, and rationale | Consumes governed order; never invokes, adapts payloads, or silently reorders. |
| Provider/tool invocation | Execution Dispatcher | Executions, authorized targets, invocation attempts, normalized results, and execution audit | Sole normal-path invocation authority; never selects provider/model alternatives. |
| Provider protocol adaptation | Dispatcher-owned adapter or AI Router | Transport-local operational state only | **TRANSPORT ONLY**; no ranking, substitution, fallback, escalation, or independent retry authority. |
| Provider/tool local operation | Selected provider or tool | Provider-local operational state only | Performs only the selected bounded operation and owns no LEOS lifecycle decision. |
| Execution observation/await | Runtime Execution Coordinator, if retained | Observation/correlation state only | **PROJECTION ONLY**; no scheduler driving, assignment restart, lease reconciliation, or normal execution participation. |
| Initial setup coordination | First Run | First-run session, configuration, readiness, and result records within existing contracts | **COORDINATOR ONLY**; runtime activation and continuing registry authority remain **OPEN**. |
| Installation planning and bootstrap | Existing installer tools within their documented scope | Installation plan, journal, transaction, and result evidence | Does not establish the future plugin/artifact publishing authority. |
| Operator inspection | LEOS operator/doctor tooling within its documented scope | Read-only status, doctor, service, log-query, backup-plan, and update-plan evidence | Backup and update plans are not execution authority. |
| Execution contract definitions | Repository-root `contracts/` | Canonical JSON Schema definitions | Runtime validation belongs to `packages/leos-contracts`; schema copies do not become authority. |
| Contract semantic validation | `packages/leos-contracts` | Canonical cross-contract semantic validation behavior | No parallel semantic validator may reinterpret the same canonical contract. |
| Source development | `leos-v2` | Writable Dev Preview v2 source | Lucy is never writable source authority. |
| Lucy donor behavior | None | None | **DONOR EVIDENCE ONLY** until deliberately promoted under canonical contracts and tests. |
| Production per Token | No runtime authority | Observational/reporting evidence only | Never selection, eligibility, ranking, resolution, fallback, retry, re-resolution, or escalation authority. |
| Phase 5.0 intelligence fixtures | None | Isolated test state only | Test/reference-only and removable; no production model, provider, ranking, health, or activation authority. |

## Explicitly OPEN authorities

An **OPEN** row is an implementation stop boundary. A package may define and
seek approval for the authority; it may not silently choose one.

| Concern | What is established | What remains OPEN | Interim prohibition |
|---|---|---|---|
| Production authentication and trust bootstrap | Principal model and Actor Context owner are accepted | Human/workload authenticators, proof formats, recovery, session revocation, first-principal bootstrap, and deployment topology | Caller strings, employee IDs, development assurance, or schema-valid Actor Context documents must not become production authentication. |
| Ownership policy and transfer | Common exactly-one-owner evidence and domain-state ownership are accepted | Domain transfer, inheritance, visibility, archival, and cross-authority reconciliation policy | New services must not invent incompatible owner fields or treat ownership as authorization. |
| Event delivery and evolution | Canonical envelope and producer authority are accepted | Outbox, broker, ordering, acknowledgement, replay, retention, schema evolution, and global event-store topology | Event existence or receipt must not replace canonical state or transfer ownership. |
| Publishing artifact metadata | Public/private repository boundary is documented | Core publishing owner and artifact object model | Release-publication evidence must not be reused as plugin/template publishing authority. |
| Artifact version and dependency lifecycle | Immutable versioning and provenance are required | Package, signature, compatibility, dependency, deprecation, and revocation contracts | No ad hoc package format may become canonical by implementation. |
| Installed artifact instance | Published definition and installed instance must differ | Install, configure, enable, update, rollback, remove, and data-ownership authority | Installation must not imply activation or permission. |
| Organization lifecycle | Organization-first hierarchy is accepted product direction | Definition, revision, lifecycle, membership, and persistence owner | Organization Intelligence or filesystem layout must not become definition authority. |
| Department lifecycle | Department is a first-class organizational concept | Definition, revision, lifecycle, membership, and persistence owner | Lucy department YAML is donor evidence only. |
| Team lifecycle | Team is a first-class organizational concept | Definition, revision, lifecycle, membership, and persistence owner | Team Template installation must not invent an implicit Team authority. |
| Employee-to-job assignment decision | Scheduler accepts a job identifying an employee; Employee Registry owns definition, eligibility, and assignment-policy inputs | Who proposes/selects the employee for a job, applicable policy, and the governed handoff into Scheduler | Legacy scoring, identifier order, caller `force`, or a second job store must not become canonical assignment authority. |
| Organizational policy | Current ranking precedence remains `job > employee > capability > global` | Restriction inheritance and whether organization/team ranking scopes ever exist | Organizational policy may not silently add ranking precedence or reorder candidates. |
| Workflow definition and lifecycle | Workflow correlation fields exist; Workflow submits governed work | Definition, validation, lifecycle, compensation, projection, and persistence owner | Workflow engines must not create peer scheduler, assignment, or invocation authority. |
| Plugin lifecycle | Public Plugin SDK/manifest direction is required | Manifest, trust, dependency, install-instance, update, rollback, removal, and isolation owner | Lucy Plugin Platform and Module Registry are not canonical. |
| Capability declaration | Capability Manager owns canonical inventory/resolution | Boundary among publisher declaration, installed inventory, and canonical ingestion | A plugin manifest must not directly grant or resolve capability use. |
| Capability permission grants | Capability presence and eligibility are distinct | Grant issuer, subject/scope/action model, expiry, revocation, delegation, and verifier | Inventory presence or employee configuration must not authorize use. |
| General authorization decisions | Authorization Authority owns the canonical subject/action/resource decision interface; restrictions are cumulative and may eliminate but not reorder | Policy definition, policy issuer, grant sources, durable service/API, and enforcement integration outside current resolution facts | Authorization evidence does not select providers, invoke work, or become a second ranking or resolution authority. |
| Tool identity and operation catalog | Dispatcher is invocation authority | Tool identity, schema, risk, side-effect, idempotency, and catalog owner | Tool Runtime or adapters must not invoke outside Dispatcher. |
| Approval service implementation and approver policy | Approval Authority, contracts, lifecycle boundary, and verifier outcomes are accepted | Durable service/API, approver-policy source, notification, atomic verification/consumption, and availability strategy | No other service may issue, mutate, or self-verify grants. |
| Secret resolution | Secret Authority and opaque Secret Reference identity are accepted | Backend interface, use authorization, transient lease/injection, rotation, redaction, deletion, and production implementation | Raw secrets are forbidden in source, contracts, fixtures, logs, prompts, events, and memory. |
| Sandbox/workspace lifecycle | Side-effecting work requires governed isolation | Profile, workspace, filesystem, network, process, secret, artifact, cleanup, and attestation owner | Container use alone must not be claimed as canonical sandboxing. |
| Team Template lifecycle | Team Templates are mandatory publishing objects | Definition, validation, published version, installed instance, simulation, activation, upgrade, and rollback authority | A template may not grant permissions, provide secrets, approve, or self-activate. |
| Team Architect apply protocol | Team Architect is a mandatory guided employee | Proposal/apply handoff contract and any durable coordination owner | Team Architect never becomes publisher, installer, approver, secret, workflow, scheduler, or activation authority. |
| Memory, knowledge, experience, and playbooks | Persistent Runtime owns only working state; reference artifacts retain bounded provenance | Canonical object distinctions, storage owners, trust/review, correction, retention, deletion, and retrieval authority | Lucy stores must not be merged or promoted without an accepted data-authority decision. |
| General artifact authority | Execution and research flows can produce artifacts | Cross-service artifact identity, ownership, derivation, retention, and lifecycle owner | Service-local paths or blobs must not become global artifact identity. |
| History ingestion | Governed provenance/review pipeline is required | Import-session, consent, source, correction, retention, deletion, and connector boundary | Imported conversation or document content must not become trusted memory automatically. |
| Runtime/model activation | First Run may coordinate future work | Installation, activation, desired/observed topology, registration, rollback, and partial-state owner | First Run declarations and fixture state are not activation authority. |
| Provider/runtime observations | Observations may affect eligibility under policy | Probe authority, freshness, expiry, degraded-state rules, and reconciliation | Health never becomes hidden ranking or rewrites administrative intent implicitly. |
| Budget and cost authority | Budget is a cumulative restriction concept | Reservation, accounting, issuer, scope, and exhaustion behavior | Cost or PPT must not become implicit ranking. |
| Outcome evidence | PPT requires externally grounded productive outcomes | Outcome issuer/authority, normalization, attribution, cohorts, and delayed/reused outcomes | Employees may not self-declare productive value. |
| Notification/human interaction | Approvals and operator attention require delivery | Canonical request/response identity and channel-neutral delivery boundary | A delivery channel must not decide or forge the underlying approval/action. |
| Backup, restore, and update execution | Canonical plans exist | Privileged executor, result, data ownership, migration, recovery, and rollback authority | A plan or UI confirmation is not execution authority. |

## Known conflicting or legacy public surfaces

These source surfaces are present in `leos-v2` but do not receive authority
from their presence. Their migration or retirement is future reviewed work.

| Surface | Conflicting behavior | Registry disposition |
|---|---|---|
| `services/assignment-service/app.py` | Persists a peer job lifecycle, selects employees through legacy resolution/score behavior, accepts caller `force`, mutates employee load, and publishes best-effort events | **CONFLICTING / INVESTIGATE**. It is outside the canonical execution path and must receive no new v2 authority. Caller/data migration, compatibility, and retirement remain **OPEN**. |
| Employee Registry legacy `/resolve` | Returns a selected employee using legacy assignment-resolution behavior within the otherwise canonical Employee Registry | Definition, lifecycle, eligibility, assignment-policy inputs, and resource-profile synchronization remain canonical. Workforce assignment-selection authority and compatibility duration remain **OPEN**. |

## Canonical object vocabulary

These terms are normative even where the final contract is **OPEN**.

| Term | Meaning | Authority rule |
|---|---|---|
| Definition | A durable declarative description of an object | Owned by the object's accepted definition authority; not proof of installation or activity. |
| Revision | Immutable identity for the material state used in a decision | Mutable display names, timestamps, or endpoint aliases do not substitute for revision evidence. |
| Policy | User- or authority-authored rules and restrictions | Policy is not a provider resolution or execution result. |
| Plan | Proposed operations and declared effects | A plan never proves authorization or completion. |
| Decision | An authority's governed determination from referenced inputs | A decision does not perform the external operation unless that authority explicitly owns it. |
| Ranking | User-governed candidate order | Ranking does not imply eligibility, availability, approval, or invocation. |
| Eligibility result | Candidate survival or rejection under cumulative restrictions and facts | Eligibility may remove but never reorder. |
| Resolution | Capability Manager's governed authorization of a selected target, or truthful non-selection outcome | Resolution is not provider execution. |
| Execution | Dispatcher's durable invocation lifecycle for one governed request | Execution never invents a target or silently changes it. |
| Attempt | One same-target invocation attempt within an execution | Attempt identity and retry never imply re-resolution. |
| Observation | Time-bounded reported fact about another object | An observation is not administrative state or source authority. |
| Projection | Derived local view of another authority's state | A projection is rebuildable and cannot override its source. |
| Published artifact | Immutable distributable definition and evidence | Not an installed, configured, enabled, or active instance. |
| Installed instance | Local realization of one published artifact version | Installation does not imply permission, approval, enablement, or activation. |
| Configured instance | Installed instance with local non-secret configuration and opaque references | Configuration does not imply readiness or activity. |
| Active runtime | Governed running realization with desired/observed state | Runtime activation authority remains **OPEN**. |
| Capability | A governed kind of work that may be resolved to an eligible provider | Capability presence is not a grant and is not a Tool operation. |
| Tool | Versioned bounded operation with explicit schemas and side-effect/idempotency declarations | Tool identity/catalog authority remains **OPEN**; invocation remains Dispatcher authority. |
| Plugin | Installable extension package declaring integrations, capabilities, tools, requirements, and configuration | Declaration does not grant, register, approve, or activate by itself. |
| Employee | Governed worker definition and lifecycle identity | Employee Registry owns definition; runtime and cognition own separate operational state. |
| Assignment | Durable projection of employee work associated with a scheduler job | Persistent Runtime owns assignment state; it does not own the job lease. |
| Workflow | Versioned process definition and instance coordinating governed work | Workflow authority remains **OPEN** and cannot absorb Scheduler or Dispatcher. |
| Team Template | Immutable publishable organization blueprint | Separate from its installed instance, created Team, and active organization. |
| Approval request | Request for an authorized human/authority decision | Not a grant. |
| Approval grant | Explicit verifiable scoped authorization | Approval Authority owns lifecycle and verification; caller-provided evidence is not self-verifying. |
| Secret reference | Opaque identifier for protected material | Secret Authority owns identity; the reference never contains or implies authorization to retrieve the secret value. |
| Artifact | Durable output with identity, ownership, provenance, and derivation | General artifact authority remains **OPEN**. |
| Memory/knowledge item | Governed retained information with scope, provenance, trust, and lifecycle | Exact taxonomy and authority remain **OPEN**. |
| Outcome evidence | Externally grounded evidence of productive value | Observational input to reporting only; not selection authority. |
| Event | Immutable fact published by the authority that owns the represented transition | Event delivery does not create state authority. |
| Audit record | Durable evidence that an authority evaluated or performed an operation | Audit evidence does not replace the canonical object or grant authority. |

## Lifecycle vocabulary and separation

Lifecycle families must not be collapsed.

| Lifecycle family | Accepted or required separation |
|---|---|
| Employee definition lifecycle | Employee Registry is canonical. Existing employee lifecycle contracts govern the implemented scope. |
| Job lifecycle | Scheduler owns it independently of assignment, cognition, workflow, and execution. |
| Lease/resource lifecycle | Scheduler owns acquisition/admission/release; terminal job state and resource release require truthful reconciliation. |
| Assignment lifecycle | Persistent Runtime owns the durable projection. Complete shared state vocabulary and publication remain partly **OPEN**. |
| Cognitive lifecycle | Cognitive Service owns runs, attempts, checkpoints, observations, and results. Cognitive retry is not assignment retry. |
| Resolution lifecycle | Capability Manager owns resolution and non-selection outcomes. Re-resolution is not Dispatcher retry. |
| Execution lifecycle | Dispatcher owns execution and same-target attempts. Provider failure, transport failure, and ambiguous outcome remain distinct. |
| Artifact publication lifecycle | Draft/validation/publication/deprecation/revocation semantics require future contracts. Publication is never installation. |
| Installed-instance lifecycle | Inspect/plan/install/configure/enable/update/rollback/remove semantics require future contracts. Installation is never activation. |
| Runtime lifecycle | Desired/observed activation, health, placement, and rollback authority remain **OPEN**. |
| Organization/Department/Team lifecycle | Definitions, revisions, membership, activation, archive, and deletion remain **OPEN**. |
| Workflow lifecycle | Definition revision and workflow-instance state are separate from projected Scheduler jobs; exact states remain **OPEN**. |
| Permission lifecycle | Request/grant/verify/expire/revoke semantics remain **OPEN** and separate from capability inventory. |
| Approval lifecycle | Approval Authority owns request/decision/grant/verify/consume/expire/revoke; durable implementation and approver-policy integration remain **OPEN**. |
| Memory/knowledge lifecycle | Capture/review/trust/correct/supersede/deprecate/delete semantics remain **OPEN**. |

No lifecycle transition may be inferred solely from:

- an API call returning successfully;
- an event being emitted;
- a UI state change;
- a caller-provided Boolean;
- an opaque reference existing;
- an artifact being downloaded;
- a plugin being installed;
- a service health observation; or
- a test fixture record.

## Event, correlation, and causation boundaries

1. The authority that owns a state transition is the only producer that may
   assert the canonical transition fact.
2. Events are immutable evidence and notification. Canonical state remains in
   the authority's governed store unless an accepted decision explicitly says
   otherwise.
3. Consumers may build projections, initiate separately authorized work, or
   report observations. They may not reinterpret an event as permission,
   approval, selection, or state ownership.
4. Duplicate delivery must not duplicate authority-bearing work. Exact event
   idempotency, ordering, acknowledgement, replay, and outbox rules remain
   **OPEN**.
5. Correlation identifies related work but does not authorize it. The current
   execution contracts govern the implemented correlation envelope.
6. Causation distinguishes the actor/request that caused a transition from the
   producer that recorded it under `leos.event-envelope.v1`.
7. Events, logs, diagnostics, and audit records must not carry raw secrets or
   unnecessary prompt/memory content.
8. Service-local event formats are not automatically public contracts.

Established correlation ownership includes:

| Identifier | Authority |
|---|---|
| `job_id`, `lease_id`, `resource_reservation_id` | Scheduler |
| `employee_id` | Employee definition authority |
| `assignment_id` | Persistent Employee Runtime |
| `cognitive_run_id`, `cognitive_attempt_id` | Employee Cognitive Service |
| `resolution_id` | Capability Manager |
| `execution_id`, invocation attempt identity | Execution Dispatcher |
| `model_id`, model-binding revision | Model Registry |
| effective-ranking identity/revision | Ranking Policy Authority |
| `workflow_id`, `step_id` | **OPEN** Workflow authority |
| `approval_grant_id` | Approval Authority |

## Contract, revision, and compatibility rules

1. JSON Schema files under repository-root `contracts/` are the canonical
   shared schema definitions. Runtime schema copies are prohibited.
2. `packages/leos-contracts` is the canonical semantic-validation
   implementation for governed shared contracts.
3. JSON Schema validation and semantic validation are both required where the
   canonical validator defines semantic invariants.
4. Contract version, object revision, artifact version, service version, model
   identity, binding revision, and installed-instance version are different
   concepts.
5. A revision used for a governed decision must identify the material facts
   evaluated. Mutable names, identifier spelling, timestamps, health probes, or
   list position must not become hidden policy.
6. Compatibility is explicit. It may preserve a validated read or transport
   surface, but it must not preserve conflicting selection, invocation,
   approval, secret, or lifecycle authority.
7. Lucy behavior has no compatibility entitlement merely because it is
   running. Compatibility duration and retirement require explicit decisions
   and tests.
8. Pre-release v2 contracts may be completed in their existing version only
   when the governing architecture and contract-specific versioning decision
   permit it.
9. Published artifact versions are expected to be immutable; the exact
   artifact contract and compatibility rules remain **OPEN**.
10. Irreversible migrations require explicit review. Until then, prefer
    non-destructive schema additions, revisioned imports, rebuildable
    projections, and truthful rollback limitations.
11. Test/reference fixtures have no production compatibility or migration
    obligation and must leave no production authority/configuration state.
12. RC11 release authority remains frozen unless explicitly authorized.

The repository-wide compatibility window, deprecation duration, event-schema
evolution protocol, artifact-version syntax, and stored-data migration policy
remain **OPEN**.

## Forbidden authority overlaps

The following are prohibited unless an accepted later ADR explicitly changes
the boundary:

- Capability Manager invoking a provider or adapting provider payloads.
- Dispatcher, Router, adapters, or providers selecting or substituting a
  provider/model.
- Router fallback, emergency provider pools, identifier ordering, score-based
  selection, or unranked candidate append.
- Cognitive Service or Persistent Runtime invoking providers directly.
- Persistent Runtime owning reasoning or Scheduler leases.
- Assignment Service or any other peer owning Scheduler jobs, Persistent
  Runtime assignments, or employee-selection policy by implementation
  accident.
- Workflow, planning, Team Architect, or Runtime Coordinator driving leases or
  restarting assignments.
- Plugin installation directly granting capabilities, permissions, approvals,
  secrets, or activation.
- Capability presence being treated as permission.
- Caller Booleans or opaque approval-reference existence authorizing action.
- Tool Runtime or Adapter Manager becoming a peer invocation authority.
- First Run or Phase 5.0 fixtures becoming continuing model/provider/runtime
  authority.
- Health, price, cost, benchmark, locality, trust, or PPT metrics silently
  reordering user-ranked candidates.
- Organization or Team policy adding ranking precedence before an accepted
  intelligence-plane decision.
- Events, projections, caches, UI state, logs, or audits becoming canonical
  state authority.
- Lucy files, databases, endpoints, or behavior becoming authority without
  deliberate promotion into `leos-v2`.

## Change control

An implementation package that touches an **ACCEPTED** row must:

1. cite the governing authority document;
2. preserve the owner and forbidden overlaps;
3. update explicit contracts and tests for behavioral changes;
4. retain correlation, audit, idempotency, secret, and failure semantics; and
5. report migrations and compatibility behavior.

An implementation package that touches an **OPEN** row must first obtain an
accepted architecture decision. Creating a table, endpoint, schema, fixture,
or service does not resolve an **OPEN** authority.

This registry must be updated whenever an accepted decision:

- establishes a new canonical owner;
- changes a responsibility boundary;
- defines a previously open lifecycle;
- adds or removes a compatibility surface; or
- retires a donor or duplicated authority.
