# LEOS Dev Preview v2 Blocking Authority Decisions

## Status

**Target:** LEOS 0.2.0 Developer Preview v2

**Epic:** 8.1 - Blocking Authority ADR Pack

**Status:** Proposed for acceptance

This document resolves only the authority decisions that block implementation
of the accepted Dev Preview v2 integration plan in
`DEV_PREVIEW_V2_INTEGRATION_PLAN.md`.

It does not implement production code, create contracts, change schemas, alter
runtime configuration, modify Lucy, or assign authority to current legacy code
because it happens to perform an action today.

## Blocking-authority summary

| Authority | Current classification | Selected owner | Supporting services | Status after Epic 8.1 | ADR | Implementation dependency | Migration impact |
|---|---|---|---|---|---|---|---|
| Organization service topology and authoritative storage | OPEN | Organization Domain Service | Identity, Authorization, Approval, Event Delivery | ACCEPTED | ADR-DPV2-001 | Organization Domain implementation | New store; no peer org stores |
| Work Request definition and acceptance | OPEN | Work Coordination Service | Organization Domain, Authorization, Approval, Team Architect | ACCEPTED | ADR-DPV2-002 | Work Coordination implementation | New store; no Scheduler direct intake |
| Workflow Definition and Revision ownership, publication, and selection | OPEN | Work Coordination Service | Team Template Authority, Organization Domain | ACCEPTED | ADR-DPV2-002 | Work Coordination implementation | Lucy workflow remains donor only |
| Job creation request and projection | PARTLY ACCEPTED | Scheduler for Job record; Work Coordination may request creation | Work Coordination, Persistent Runtime | ACCEPTED | ADR-DPV2-002 | Scheduler target-contract adapter | No peer Job store |
| Task lifecycle | OPEN | Work Coordination Service | Scheduler, Persistent Runtime | ACCEPTED | ADR-DPV2-002 | Work Coordination implementation | New Task store |
| Assignment decision | OPEN | Work Coordination Service | Employee Registry, Organization Domain, Scheduler | ACCEPTED | ADR-DPV2-003 | Assignment handoff protocol | Public Assignment quarantined |
| Assignment acceptance and projection | OPEN/PARTLY ACCEPTED | Persistent Employee Runtime | Work Coordination, Employee Registry | ACCEPTED | ADR-DPV2-003 | Runtime assignment target adoption | Runtime store remains canonical projection |
| Delegation lifecycle | OPEN | Work Coordination Service | Persistent Runtime, Organization Domain | ACCEPTED FOR DEV PREVIEW | ADR-DPV2-003 | Work Coordination implementation | No cross-Organization delegation |
| Authorization and capability permission grants | OPEN | Authorization Authority | Organization Domain, Capability Manager, Dispatcher | ACCEPTED | ADR-DPV2-004 | Authorization service/API | New grant/decision store |
| Approval service/API | OPEN | Approval Authority | Authorization, Work Coordination, Capability Manager, Dispatcher, Cognitive Service | ACCEPTED | ADR-DPV2-005 | Approval service/API | Lucy approval not migrated as authority |
| Secret and credential-reference backend/use | OPEN | Secret Authority | Authorization, Dispatcher, Runtime Activation, Plugin/Tool Authority | ACCEPTED | ADR-DPV2-006 | Secret service/API | No raw secret migration |
| Event outbox, replay, and delivery | OPEN | Producing authority owns outbox; Event Delivery Service owns delivery/replay infrastructure | All authorities | ACCEPTED | ADR-DPV2-007 | Per-service outbox and delivery service | Existing best-effort events hardened |
| Result ownership and acceptance | OPEN | Work Coordination Service | Cognitive Service, Dispatcher, Artifact Authority | ACCEPTED | ADR-DPV2-008 | Work Coordination result APIs | New result records |
| Artifact ownership, publication, and linkage verification | OPEN | Artifact Authority | Artifact Trust Authority, Work Coordination, Plugin/Tool Authority | ACCEPTED | ADR-DPV2-009 | Artifact service/API | Service-local paths migrate to Artifact refs |
| Verification and closure | OPEN | Work Coordination Service | Human/UI, Authorization, Artifact Authority | ACCEPTED | ADR-DPV2-010 | Work Coordination verification APIs | New verification/closure records |
| Runtime activation | OPEN | Runtime Activation Authority | First Run, Model Registry, Capability Manager, Secret Authority, Operator | ACCEPTED | ADR-DPV2-011 | Runtime activation service/API | First Run remains coordinator |
| Plugin and Tool installation/lifecycle | OPEN | Plugin and Tool Lifecycle Authority | Artifact Authority, Artifact Trust, Authorization, Secret, Capability Manager, Dispatcher | ACCEPTED | ADR-DPV2-012 | Plugin/tool lifecycle service/API | Lucy plugin services donor only |
| Sandbox and workspace lifecycle | OPEN | Sandbox Authority | Dispatcher, Plugin and Tool Lifecycle Authority, Secret Authority, Artifact Authority | ACCEPTED | ADR-DPV2-014 | Sandbox/workspace service or module | Container use alone is not authority |
| Team Template ownership | OPEN | Team Template Authority | Organization Domain, Work Coordination, Plugin/Tool Authority, Approval | ACCEPTED | ADR-DPV2-013 | Team Template service/API | New template store |
| Team Architect proposal, validation, apply, test-run, and save protocol | OPEN | Team Template Authority for proposal/apply records; Team Architect remains a core Employee | Work Coordination, Organization Domain, Approval, Operator/UI | ACCEPTED | ADR-DPV2-013 | Team Architect and Team Template implementation | No superuser authority |

## ADR-DPV2-001: Organization Domain Service owns production organization topology

- **Status:** Accepted
- **Context:** Epic 5.0 accepted one logical Organization Domain Authority but
  left deployment, persistence, transaction, outbox, backup, recovery, and
  child-transition topology OPEN. No existing service in `leos-v2` owns
  Organization, Department, Team, Role, Position, Membership, and Position
  Occupancy state. Employee Registry owns Employee definitions only.
- **Decision:** Dev Preview v2 implements the logical Organization Domain
  Authority as one Organization Domain Service with one authoritative store and
  one event outbox for Organization Domain resources.
- **Authoritative owner:** Organization Domain Service.
- **Supporting actors:** Identity Authority validates Principal and Actor
  Context references. Authorization Authority decides allowed mutations.
  Approval Authority verifies grants where required. Event Delivery Service
  delivers emitted events. Operator/UI displays projections.
- **Records owned:** Organization, Department, Team, Role, Position,
  Membership, Position Occupancy, Organization Domain lifecycle transitions,
  and Organization Domain event outbox records.
- **APIs or events governed:** create/read/list/update lifecycle APIs for the
  Organization Domain resource family; canonical organization-domain
  transition events produced by this service.
- **Authorization boundary:** every mutation requires current Actor Context
  and Authorization Decision evidence. Membership and Role never authorize by
  themselves.
- **Organization boundary:** every child resource belongs to exactly one
  Organization. Cross-Organization references fail closed. Cross-Organization
  collaboration remains OPEN.
- **Approval or verification boundary:** Approval Authority grants may be
  required by policy, but Organization Domain Service cannot issue or verify
  grants by itself.
- **Failure and retry behavior:** creation and transition requests require
  idempotency keys. Stale revision, missing owner, invalid parent, cyclic
  hierarchy, unavailable authorization, or missing approval fails closed.
- **Persistence and recovery implications:** the Organization Domain store is
  recovered as a unit. Its outbox is replayed without changing canonical
  state. Projections are rebuildable.
- **Migration implications:** Employee v2 records remain Employee Registry
  compatibility input until a later migration links them to Organization
  records. Lucy organization views remain donor evidence only.
- **Rejected alternatives:** Employee Registry owning Organization state;
  Team Architect creating organization records directly; UI-local JSON as
  canonical state; separate first-to-persist services for Team, Role, and
  Membership.
- **Consequences:** Epic 8.2 can implement the Organization Domain Service
  without creating a peer Employee, Scheduler, Runtime, or policy authority.
- **Compatibility notes:** existing Employee Builder may remain an advanced
  compatibility surface but cannot create canonical Organization state.
- **Security notes:** Organization isolation becomes enforceable in a single
  lifecycle authority; cross-scope leakage fails closed.
- **Implementation prerequisites:** accepted Identity/Authorization request
  envelope, Organization Domain storage migration plan, outbox plan, and
  non-destructive Employee v3 adoption plan.
- **Validation requirements:** lifecycle, owner, revision, cross-Organization
  rejection, event/outbox, restart/recovery, stale revision, and no-role-as-
  permission tests.

## ADR-DPV2-002: Work Coordination Service owns Work Request, Workflow, Task, and projection

- **Status:** Accepted
- **Context:** Epic 7.0 created target contracts for Work Request, Workflow
  Definition, Workflow Revision, Task, Dependency, Result, Retry Intent, and
  Escalation Intent but did not assign production owners. Scheduler already
  owns Job lifecycle, leases, and resources. Current Lucy workflow/planning
  code and public catalogs are donor evidence and must not become authority by
  accident.
- **Decision:** Dev Preview v2 introduces a Work Coordination Service as the
  authoritative owner for Work Request acceptance, Workflow Definition and
  Revision publication/selection, Task lifecycle, dependency readiness,
  workflow-to-Scheduler projection requests, Retry Intent, and Escalation
  Intent. Scheduler remains the only Job lifecycle owner.
- **Authoritative owner:** Work Coordination Service for Work Requests,
  Workflow Definitions, Workflow Revisions, Tasks, Dependencies, Retry
  Intents, Escalation Intents, workflow projection records, and their events.
  Scheduler is the authoritative owner of created Jobs.
- **Supporting actors:** Organization Domain Service enforces Organization
  scope. Authorization Authority authorizes mutations. Approval Authority
  verifies required approvals. Scheduler receives idempotent job-create
  requests. Persistent Runtime receives assignment projection handoff after a
  governed assignment decision.
- **Records owned:** Work Request records, accepted-work transitions,
  Workflow Definition records, immutable Workflow Revision records, Task
  records, Dependency records, projection records, Retry Intent records, and
  Escalation Intent records.
- **APIs or events governed:** work-request intake/review/accept/reject,
  workflow publish/select/deprecate, task create/ready/block/cancel, dependency
  satisfy/waive, projection submit/status, retry-intent and escalation-intent
  APIs and events.
- **Authorization boundary:** Work Coordination Service must not treat a Work
  Request as authorization. Every authority-bearing transition requires Actor
  Context and Authorization Decision evidence.
- **Organization boundary:** all Work Domain resources are Organization-owned.
  Workflow projection cannot create cross-Organization Jobs or Tasks.
- **Approval or verification boundary:** Work Coordination may request and
  retain approval references. Only Approval Authority verifies grants. Work
  verification and closure are handled by ADR-DPV2-010.
- **Failure and retry behavior:** Work intake rejection, dependency blockage,
  Scheduler rejection, projection failure, retry intent, and escalation intent
  are distinct records. Retry preserves prior attempts and never silently
  reassigns, reroutes, or invokes.
- **Persistence and recovery implications:** Work Coordination has an
  authoritative store and outbox. On restart it reconciles its projection
  records against Scheduler state through Scheduler APIs, never by editing
  Scheduler storage.
- **Migration implications:** Lucy Workflow/Planning and cataloged
  workflow-engine behavior must be inspected for donor value and then adapted
  or retired. No Lucy workflow database is imported as authority.
- **Rejected alternatives:** Scheduler owning Workflow/Task definitions;
  Persistent Runtime owning workflow state; Team Architect directly creating
  Jobs; Lucy Workflow Engine promotion without contract adoption; a generic
  mega-orchestrator owning Scheduler or Dispatcher state.
- **Consequences:** Epic 8.3 can implement the missing work intake and
  projection layer while preserving the execution plane.
- **Compatibility notes:** existing Scheduler `/jobs` may remain for bounded
  compatibility, but the organization-first path enters through Work
  Coordination.
- **Security notes:** Work Coordination may coordinate but cannot authorize,
  approve, resolve capabilities, invoke providers, own secrets, or verify
  results by assertion.
- **Implementation prerequisites:** Organization Domain Service, idempotent
  Scheduler job-create adapter, Work Domain storage and outbox, and
  authorization/approval integration stubs that fail closed until live.
- **Validation requirements:** work intake, workflow revision immutability,
  acyclic dependencies, idempotent projection, no peer Job store, no direct
  execution, restart reconciliation, retry/escalation separation, and
  cross-Organization rejection tests.

## ADR-DPV2-003: Work Coordination decides assignments; Persistent Runtime owns acceptance projection

- **Status:** Accepted
- **Context:** The accepted architecture says Persistent Runtime owns durable
  assignment projection and lifecycle, but assignment decision and acceptance
  were OPEN. Public Assignment persists peer jobs and selects employees through
  legacy behavior. Employee Registry legacy `/resolve` also performs selection
  behavior.
- **Decision:** Work Coordination Service owns assignment-decision records for
  Dev Preview v2. Persistent Employee Runtime owns assignment acceptance,
  durable projection, runtime lifecycle transitions, and terminal assignment
  state after it accepts a governed assignment decision. Work Coordination
  owns Delegation lifecycle for Dev Preview v2, limited to same-Organization
  responsibility sub-allocation.
- **Authoritative owner:** Work Coordination Service for assignment decisions
  and delegations. Persistent Employee Runtime for assignment acceptance,
  projection, start/complete/fail/cancel transitions, and assignment terminal
  outbox records.
- **Supporting actors:** Employee Registry provides Employee definitions,
  lifecycle status, eligibility, and assignment-policy inputs. Organization
  Domain provides Team/Position/Membership scope facts. Scheduler owns Job
  lifecycle and leases.
- **Records owned:** assignment decision records, decision rationale,
  delegation records, delegation chain, and assignment handoff records by Work
  Coordination; accepted assignment projection and lifecycle records by
  Persistent Runtime.
- **APIs or events governed:** assignment propose/decide/handoff APIs in Work
  Coordination; assignment accept/start/terminal APIs and events in Persistent
  Runtime.
- **Authorization boundary:** assignment decision requires Actor Context and
  Authorization Decision evidence. Assignment does not grant permission,
  capability use, approval, scheduling, or execution.
- **Organization boundary:** assigned work, assignee target, source Task/Job,
  and Delegation target must share one Organization. Cross-Organization
  delegation remains OPEN and fails closed.
- **Approval or verification boundary:** assignment may require approval, but
  only Approval Authority verifies. Assignment acceptance is not work
  verification.
- **Failure and retry behavior:** unavailable employees, ineligible lifecycle
  state, stale Employee revision, rejected handoff, or cross-scope target
  creates explicit failure evidence. Reassignment requires a new assignment
  decision and preserves the previous assignment. Delegation cycles and scope
  expansion fail closed.
- **Persistence and recovery implications:** Work Coordination persists the
  decision and can replay handoff. Persistent Runtime persists accepted
  projection and terminal transitions. Neither edits the other's store.
- **Migration implications:** Public Assignment remains `CONFLICTING /
  INVESTIGATE` and receives no new v2 authority. Employee Registry `/resolve`
  becomes compatibility/donor behavior and is not used by the canonical
  Dev Preview path until explicitly retired or adapted.
- **Rejected alternatives:** Public Assignment as canonical owner; Employee
  Registry selecting employees; Scheduler selecting workforce targets;
  Team/Role/Position hierarchy selecting by implication; Persistent Runtime
  inventing assignments without a decision record.
- **Consequences:** assignment policy becomes explicit and auditable while
  Persistent Runtime keeps its accepted durable assignment boundary.
- **Compatibility notes:** legacy assignment data can be read only for
  migration analysis. It must not feed canonical decisions without a reviewed
  import.
- **Security notes:** assignment responsibility cannot be confused with
  authorization or provider/tool permission.
- **Implementation prerequisites:** Work Coordination decision API, Employee
  Registry eligibility API compatibility, Persistent Runtime assignment target
  adoption, and explicit retirement plan for conflicting paths.
- **Validation requirements:** no score/identifier/caller-force selection,
  exact decision-to-projection linkage, same-Organization checks, employee
  eligibility, delegation chain, retry/reassignment history, and restart
  handoff tests.

## ADR-DPV2-004: Authorization Authority owns capability permission grants and decisions

- **Status:** Accepted
- **Context:** Identity/trust decisions established Authorization Authority
  for subject/action/resource/context decisions but left policy and grant
  sources partly OPEN. Capability presence is explicitly not permission.
  Dev Preview v2 cannot safely run plugin/tool/model operations without a
  concrete permission-grant owner.
- **Decision:** For Dev Preview v2, Authorization Authority owns durable
  authorization policy inputs, capability permission grants, revocation, and
  Authorization Decision records used by Organization, Work, Capability,
  Dispatcher, Plugin/Tool, Secret, Artifact, and Team Template flows.
- **Authoritative owner:** Authorization Authority.
- **Supporting actors:** Organization Domain supplies scope facts. Capability
  Manager consumes verified permission/authorization evidence for eligibility.
  Dispatcher consumes invocation authorization evidence. Approval Authority
  remains separate.
- **Records owned:** capability permission grants, authorization policy
  records within Dev Preview scope, revocation records, decision records, and
  authorization event outbox records.
- **APIs or events governed:** grant/revoke/list/decision APIs; authorization
  decision and grant lifecycle events.
- **Authorization boundary:** Authorization Authority does not authenticate,
  rank, resolve, invoke, approve, verify work results, or own Organization
  resources. Its own mutations require Actor Context and prior administrative
  authorization.
- **Organization boundary:** every grant and decision is scoped to an
  Organization, resource, action, subject, and revision where applicable.
  Cross-Organization grants are invalid until collaboration policy is
  accepted.
- **Approval or verification boundary:** Approval Authority may be required to
  approve a grant or decision path, but Approval Authority does not replace
  Authorization Authority.
- **Failure and retry behavior:** missing, expired, revoked, stale,
  unavailable, or wrong-scope grants fail closed. Decision retries must use
  the same input revisions unless a new decision is requested.
- **Persistence and recovery implications:** grant and decision state is
  durable, revisioned, and replayable from Authorization Authority state and
  outbox.
- **Migration implications:** roles, membership, plugin declarations, and
  employee config become policy inputs only after explicit mapping. They are
  not automatically grants.
- **Rejected alternatives:** Capability Manager issuing grants; Plugin
  installation granting permission; Team membership granting permission;
  caller-provided permission Booleans; approval grants doubling as
  authorization.
- **Consequences:** Capability Manager and Dispatcher can fail closed against
  an explicit decision source.
- **Compatibility notes:** existing permission-like fields remain
  compatibility data until imported through Authorization Authority.
- **Security notes:** default deny is enforceable and permission revocation is
  not hidden in capability inventory.
- **Implementation prerequisites:** minimal Authorization service/API,
  resource/action vocabulary for Dev Preview, revocation behavior, and
  integration points for Capability Manager and Dispatcher.
- **Validation requirements:** grant issue/revoke/expire, deny reasons,
  wrong-scope rejection, no role-as-permission, no plugin-install permission,
  no provider selection, and replay/restart tests.

## ADR-DPV2-005: Approval Authority owns durable approval service behavior

- **Status:** Accepted
- **Context:** Approval contracts exist and Approval Authority already owns
  grants and verification conceptually, but durable service/API, approver
  policy, notification, and atomic verification/consumption were OPEN. Current
  v2 services must not treat caller approval references as authority.
- **Decision:** Dev Preview v2 implements Approval Authority as the sole owner
  of approval requests, decisions, grants, verification, consumption, expiry,
  revocation, approver policy evaluation, notification records, and approval
  events.
- **Authoritative owner:** Approval Authority.
- **Supporting actors:** Authorization Authority authorizes approval-related
  mutations. Work Coordination, Capability Manager, Dispatcher, Cognitive
  Service, Team Template Authority, and Organization Domain request or consume
  verification results.
- **Records owned:** approval requests, decision records, approval grants,
  verification results, consumption records, revocations, notification state,
  and approval outbox records.
- **APIs or events governed:** request/decide/verify/consume/revoke/list APIs;
  approval-requested, grant-issued, verification-completed, consumed, expired,
  and revoked events.
- **Authorization boundary:** approver eligibility is authorization/policy
  input, not caller assertion. Approval does not authorize unrelated action
  outside its exact scope.
- **Organization boundary:** approval scope includes Organization, subject,
  action, resource, expected revision, and context digest. Cross-Organization
  approval is invalid without accepted collaboration policy.
- **Approval or verification boundary:** only current `VERIFIED` evidence from
  Approval Authority authorizes an approval-gated path. References, copied
  grants, events, UI state, and schema-valid grants do not self-verify.
- **Failure and retry behavior:** missing, expired, revoked, consumed, stale,
  wrong-scope, unavailable, or conflicting approval outcomes fail closed.
  Repeated verification is idempotent only for the same grant revision and
  context; consumption is atomic.
- **Persistence and recovery implications:** approval waits survive restart.
  Notification delivery is replayable and never substitutes for the grant.
- **Migration implications:** Lucy approval records may inform behavior but
  are not migrated as verified grants.
- **Rejected alternatives:** UI-only approval; caller Boolean approval;
  Capability Manager or Dispatcher issuing grants; event-bus approval;
  copying Lucy approval state into v2 authority.
- **Consequences:** approval gates can be implemented without weakening the
  Capability Manager and Dispatcher authority boundaries.
- **Compatibility notes:** legacy approval-like fields are audit hints only.
- **Security notes:** approval is fail-closed and revision-pinned.
- **Implementation prerequisites:** Approval service/API, approver policy
  source, notification channel boundary, and atomic verify/consume semantics.
- **Validation requirements:** approval pending, grant issue, verify, consume,
  expiry, revocation, wrong-scope, replay, outage, and no caller-approval
  tests.

## ADR-DPV2-006: Secret Authority owns local secret backend and transient use

- **Status:** Accepted
- **Context:** Secret Reference identity is accepted, but backend, use
  authorization, transient lease/injection, rotation, redaction, deletion,
  backup behavior, and production implementation were OPEN. Cloud and tool
  operations cannot be release-ready without this boundary.
- **Decision:** Dev Preview v2 implements Secret Authority as the sole owner
  of protected secret values, opaque references, secret lifecycle, use
  authorization checks, transient use leases or injection records, rotation,
  revocation, deletion, redaction policy, and secret-use audit.
- **Authoritative owner:** Secret Authority.
- **Supporting actors:** Authorization Authority authorizes secret use.
  Dispatcher requests per-invocation secret use. Runtime Activation and
  Plugin/Tool Lifecycle Authority register requirements and opaque
  references. Operator surfaces manage setup without displaying values.
- **Records owned:** secret references, protected values, value versions,
  secret use leases, injection records, revocations, rotation records, and
  redacted audit events.
- **APIs or events governed:** create/reference/rotate/revoke/delete,
  authorize-use, lease/inject, and redacted audit APIs/events.
- **Authorization boundary:** possession of a secret reference never
  authorizes use. Secret Authority does not decide provider eligibility,
  select models, invoke tools, approve operations, or grant capability use.
- **Organization boundary:** secrets are scoped to one owner and Organization
  unless a future collaboration policy exists. Cross-Organization use fails
  closed.
- **Approval or verification boundary:** high-risk secret use may require a
  verified Approval grant, but Approval Authority remains separate.
- **Failure and retry behavior:** missing, unavailable, expired, revoked,
  wrong-scope, unauthorized, or injection-failed secret use fails closed.
  Lease retry must not duplicate side effects or expose values.
- **Persistence and recovery implications:** raw secret values never enter
  governed records, events, logs, prompts, memory, diagnostics, examples, or
  source. Backup/restore behavior must preserve protected value semantics and
  truthful irreversibility when applicable.
- **Migration implications:** no raw secret migration from environment,
  config, Lucy, tests, or fixtures. Existing opaque references can be
  registered only after user-authorized import.
- **Rejected alternatives:** environment variables as production authority;
  provider records storing encrypted values; Dispatcher owning secrets;
  plugin activation granting secret use.
- **Consequences:** Dispatcher and cloud/provider onboarding can use secrets
  without leaking or broadening authority.
- **Compatibility notes:** local-first Dev Preview may use one local backend,
  but the Secret Authority API must preserve future backend independence.
- **Security notes:** least-privilege, redaction, and fail-closed behavior are
  release gates.
- **Implementation prerequisites:** local backend decision, use-lease contract
  if needed, redaction tests, backup policy, and Dispatcher integration.
- **Validation requirements:** no raw secret persistence, wrong-scope
  rejection, revocation, rotation, redaction, backup exclusion, crash/restart,
  and cloud-use tests.

## ADR-DPV2-007: Producers own event outboxes; Event Delivery Service owns delivery

- **Status:** Accepted
- **Context:** Existing services vary: Persistent Runtime has an
  `employee_event_outbox`, Scheduler has local `scheduler_events` plus
  best-effort kernel publication, and registries often use local events.
  Identity/trust decisions say the state authority produces canonical events
  but left outbox, broker, replay, retention, and schema evolution OPEN.
- **Decision:** Each state authority owns its own canonical event production
  and outbox records for transitions it owns. A separate Event Delivery
  Service owns delivery, acknowledgement, replay cursors, subscriber state,
  and broker retention mechanics. Event Delivery Service never owns the
  canonical transition fact.
- **Authoritative owner:** producing authority for event content and outbox;
  Event Delivery Service for delivery infrastructure records only.
- **Supporting actors:** all services publish through their own outbox.
  Consumers build projections and never mutate source state from delivered
  events alone.
- **Records owned:** per-service outbox records by each producer; delivery
  cursor, acknowledgement, subscription, retry, and retention records by Event
  Delivery Service.
- **APIs or events governed:** outbox append/drain/retry APIs per authority;
  subscribe, replay, acknowledge, dead-letter, and retention APIs in Event
  Delivery Service.
- **Authorization boundary:** event delivery does not authorize actions.
  Consumers require their own Actor Context and Authorization Decision for
  follow-on mutations.
- **Organization boundary:** events carry Organization scope where applicable.
  delivery filters must not leak cross-Organization data.
- **Approval or verification boundary:** event presence never verifies
  approval, trust, authorization, or work completion.
- **Failure and retry behavior:** duplicate delivery is expected and must be
  idempotent. Outbox replay does not re-run state transitions. Dead-letter
  records are operator evidence only.
- **Persistence and recovery implications:** each authority recovers outbox
  with canonical state. Event Delivery Service can rebuild delivery views from
  producer outboxes where retention permits.
- **Migration implications:** best-effort event publishers migrate to outbox
  delivery without changing state ownership.
- **Rejected alternatives:** central event bus as state authority; events as
  permission or approval; consumers inferring state from delivery; one global
  event table that owns all transitions.
- **Consequences:** restart and replay can be made reliable without a mega
  state service.
- **Compatibility notes:** existing local event endpoints may remain read-only
  diagnostics during migration.
- **Security notes:** events must not carry raw secrets or unnecessary prompt,
  memory, or private artifact content.
- **Implementation prerequisites:** event envelope adoption, producer outbox
  pattern, delivery service, retention policy, and projection rebuild tests.
- **Validation requirements:** producer-only event assertions, duplicate
  delivery idempotency, replay, ordering scope, retention, dead-letter,
  cross-Organization filtering, and no-event-authority tests.

## ADR-DPV2-008: Work Coordination Service owns Work Results and acceptance

- **Status:** Accepted
- **Context:** Work Result contracts exist, but production result issuer,
  acceptor, artifact-link verification, and persistence owners were OPEN.
  Results must connect Assignment, execution, Artifact, and verification
  without self-verifying completion.
- **Decision:** Work Coordination Service owns Work Result records and Result
  acceptance for Dev Preview v2. Producers submit result evidence; Work
  Coordination validates lineage, Organization scope, producer authority,
  artifact references, and expected revisions before accepting the Result.
- **Authoritative owner:** Work Coordination Service.
- **Supporting actors:** Cognitive Service and Dispatcher provide producer
  evidence. Persistent Runtime provides Assignment state. Artifact Authority
  verifies Artifact references and ownership. Authorization Authority
  authorizes acceptance.
- **Records owned:** Work Result records, result acceptance transitions,
  producer linkage, artifact-link references, result revision history, and
  result event outbox records.
- **APIs or events governed:** submit-result, accept-result, reject-result,
  list/result-read APIs; result-submitted, result-accepted, result-rejected
  events.
- **Authorization boundary:** result submission and acceptance require Actor
  Context and Authorization Decision evidence. A Result never authorizes a
  new action.
- **Organization boundary:** Result, work item, Assignment, producer, and
  Artifact refs must be in the same Organization unless future collaboration
  policy exists.
- **Approval or verification boundary:** Result acceptance is not approval and
  not verification. Verification and closure are governed by ADR-DPV2-010.
- **Failure and retry behavior:** malformed evidence, missing execution,
  missing Assignment, wrong Organization, stale revision, or bad artifact link
  produces rejection evidence. Resubmission creates new result evidence and
  preserves history.
- **Persistence and recovery implications:** Result records are immutable
  after acceptance except lifecycle transitions that preserve prior revisions.
  Artifact writes can be incomplete without self-closing work.
- **Migration implications:** service-local output paths migrate to Artifact
  references only after Artifact Authority adoption.
- **Rejected alternatives:** Dispatcher owning Work Results; Cognitive Service
  self-closing work; Artifact Trust verifying work; Scheduler accepting
  Results; caller-submitted completion flags.
- **Consequences:** work outputs become auditable without collapsing
  verification or closure.
- **Compatibility notes:** existing execution results remain execution audit,
  not Work Result records, until linked by Work Coordination.
- **Security notes:** Result records must retain provenance without embedding
  raw secrets or excessive prompt/memory content.
- **Implementation prerequisites:** Work Coordination store, Artifact
  Authority linkage API, producer evidence vocabulary, and redaction policy.
- **Validation requirements:** exact lineage, wrong-scope rejection, duplicate
  submission idempotency, artifact-link checks, no self-verification, and
  restart tests.

## ADR-DPV2-009: Artifact Authority owns artifact lifecycle and linkage verification

- **Status:** Accepted
- **Context:** Artifact Trust Authority verifies trust evidence but does not
  publish, install, activate, or own artifact lifecycle. Generic artifact
  identity, ownership, derivation, retention, publication, and linkage
  verification were OPEN.
- **Decision:** Dev Preview v2 introduces Artifact Authority as the owner of
  artifact identity, ownership, content-address/digest records, provenance,
  derivation, publication state, retention, redacted metadata, and linkage
  verification for Work Results, Team Templates, Plugins, diagnostics, and
  other durable outputs.
- **Authoritative owner:** Artifact Authority.
- **Supporting actors:** Artifact Trust Authority verifies signatures,
  provenance, trust policy, and revocation evidence. Work Coordination,
  Plugin/Tool Lifecycle Authority, Team Template Authority, Dispatcher, and
  Operator tools create or reference artifacts through Artifact Authority.
- **Records owned:** Artifact records, artifact versions, digest/provenance
  records, publication lifecycle records, derivation links, retention state,
  linkage-verification records, and artifact outbox records.
- **APIs or events governed:** create/register, publish/deprecate/revoke,
  link/unlink/verify-link, retention, read metadata, and artifact lifecycle
  events.
- **Authorization boundary:** Artifact Authority does not authorize use of the
  artifact's contents, install plugins, activate runtimes, approve work, or
  invoke tools.
- **Organization boundary:** Artifact ownership and visibility are
  Organization-scoped unless public release/public marketplace policy is
  explicitly accepted. Cross-Organization linking fails closed.
- **Approval or verification boundary:** Artifact Trust evidence and Work
  verification are separate. Trust does not prove productive correctness.
- **Failure and retry behavior:** digest mismatch, missing producer, stale
  source revision, unauthorized publication, or wrong-scope linkage fails
  closed. Re-publication uses a new version/revision, not mutation of history.
- **Persistence and recovery implications:** artifacts require durable metadata
  and content-location records; missing content after restart is a recoverable
  degraded state with truthful evidence.
- **Migration implications:** existing service-local files or paths are not
  artifact IDs. They must be registered with digest/provenance evidence.
- **Rejected alternatives:** Artifact Trust Authority owning publication;
  Work Coordination owning all artifacts; plugin installer owning generic
  artifacts; filesystem path as canonical identity.
- **Consequences:** outputs and packages can share a common artifact boundary
  without giving trust or installer services extra authority.
- **Compatibility notes:** source-release authority files remain frozen and
  separate from Dev Preview artifact publication unless explicitly authorized.
- **Security notes:** artifact metadata must not reveal secrets; retention and
  deletion must be auditable.
- **Implementation prerequisites:** artifact contract/API if existing target
  contracts are insufficient, storage strategy, trust integration, retention
  policy, and redaction controls.
- **Validation requirements:** digest/provenance, publication, linkage,
  revocation/deprecation, wrong-scope rejection, missing-content recovery, and
  no-trust-as-install tests.

## ADR-DPV2-010: Work Coordination Service owns verification and closure

- **Status:** Accepted
- **Context:** Epic 7.0 separated completion, verification, and closure but
  left production verification and closure owners OPEN. Approval Authority is
  approval-only. Scheduler completion is not work verification.
- **Decision:** Work Coordination Service owns work verification and closure
  records for Dev Preview v2. Verification records externally grounded
  evidence against Work Results and criteria. Closure records the final
  lifecycle disposition of Work Requests, Workflow runs/projections, Tasks,
  and related Results after required verification and terminal states exist.
- **Authoritative owner:** Work Coordination Service.
- **Supporting actors:** human reviewers, Operator/UI, Artifact Authority,
  Persistent Runtime, Scheduler, Cognitive Service, Dispatcher, Authorization
  Authority, and Approval Authority.
- **Records owned:** verification requests, verification decisions, closure
  transitions, closure rationale, linked evidence, and verification/closure
  events.
- **APIs or events governed:** request-verification, verify, reject, request
  rework, close, reopen-if-policy-allows, and closure event APIs.
- **Authorization boundary:** verification and closure require Actor Context
  and Authorization Decision evidence. Employees cannot self-declare
  productive value or close their own work unless explicitly authorized.
- **Organization boundary:** all work, results, artifacts, reviewers, and
  criteria must share one Organization unless collaboration policy is
  accepted.
- **Approval or verification boundary:** approval may allow a risky operation;
  it does not verify outcome quality. Verification may cite approval evidence
  but cannot issue approval grants.
- **Failure and retry behavior:** failed verification may request rework,
  retry intent, or escalation intent while preserving history. Closure fails
  if required terminal states, Results, Artifacts, or verification evidence
  are missing or stale.
- **Persistence and recovery implications:** verification and closure
  transitions are durable and replayable. Restart cannot infer closure from
  terminal Jobs alone.
- **Migration implications:** existing job completion and assignment terminal
  state remain lower-level evidence and do not become closure records.
- **Rejected alternatives:** Scheduler closing work; Approval Authority
  verifying outcomes; Cognitive Service self-verifying; Result acceptance as
  closure; UI checkbox as verification.
- **Consequences:** Dev Preview can expose honest lifecycle state: completed,
  verified, and closed mean different things.
- **Compatibility notes:** prior completed Jobs may be shown as unverified
  legacy evidence until reviewed.
- **Security notes:** outcome evidence must be externally grounded where used
  for productivity/PPT reporting.
- **Implementation prerequisites:** verification criteria model, Artifact
  linkage, Work Result acceptance, and UI/operator review flow.
- **Validation requirements:** no self-verification, failed verification,
  rework, closure prerequisites, stale evidence, cross-Organization rejection,
  and restart tests.

## ADR-DPV2-011: Runtime Activation Authority owns desired and observed runtime activation

- **Status:** Accepted
- **Context:** First Run coordinates setup and seeds defaults but is not
  continuing runtime/model activation authority. Model Registry owns model
  facts and model-runtime bindings. Capability Manager owns provider
  inventory. No accepted service owns desired/observed runtime activation,
  rollback, and partial activation state.
- **Decision:** Dev Preview v2 introduces Runtime Activation Authority as the
  owner of local runtime/provider activation plans, desired state, observed
  state, activation attempts, rollback/deactivation, runtime health
  observations, and activation events. First Run coordinates initial calls;
  Model Registry and Capability Manager receive canonical registrations under
  their own authority.
- **Authoritative owner:** Runtime Activation Authority.
- **Supporting actors:** First Run, Operator tools, Model Registry, Capability
  Manager, Secret Authority, Authorization Authority, Event Delivery Service,
  and provider/runtime adapters.
- **Records owned:** runtime activation records, desired state, observed state,
  activation attempts, deactivation/rollback records, health observation
  records for activation, and activation outbox records.
- **APIs or events governed:** plan/activate/deactivate/rollback/observe/list
  APIs and runtime-activation lifecycle events.
- **Authorization boundary:** activation requires Actor Context,
  Authorization Decision evidence, and secret-use authorization where needed.
  Activation does not grant permission or ranking.
- **Organization boundary:** runtime/provider availability and visibility are
  scoped to installation and Organization as configured. Cross-Organization
  use fails closed without accepted sharing policy.
- **Approval or verification boundary:** activation may require approval, but
  only Approval Authority verifies grants.
- **Failure and retry behavior:** partial activation, failed health,
  unavailable secrets, or registration failure records degraded activation
  evidence and rollback state. Retry is an activation retry, not provider
  invocation retry or capability re-resolution.
- **Persistence and recovery implications:** desired and observed state
  survive restart. Observations can expire and never become hidden ranking.
- **Migration implications:** First Run runtime fixture declarations and
  existing catalog state are coordinator evidence only and must be imported
  through Runtime Activation Authority before production use.
- **Rejected alternatives:** First Run owning ongoing activation; Model
  Registry activating runtimes; Capability Manager activating providers;
  service catalog entries as activation; health observations as ranking.
- **Consequences:** local and optional cloud onboarding can be implemented
  without weakening Model Registry or Capability Manager boundaries.
- **Compatibility notes:** one local runtime path may be implemented first;
  optional cloud remains explicit and secret-gated.
- **Security notes:** activation must not expose credentials or silently
  enable cloud execution.
- **Implementation prerequisites:** activation API, desired/observed schema or
  record shape, rollback policy, Model Registry/Capability Manager
  registration handoff, and Operator visibility.
- **Validation requirements:** local activation, failed activation, rollback,
  restart reconciliation, no ranking by health, no first-run authority, and
  cloud permission/secret tests.

## ADR-DPV2-012: Plugin and Tool Lifecycle Authority owns installation, activation, and tool catalog ingestion

- **Status:** Accepted
- **Context:** Epic 6.0 defined Plugin, Tool, Installation, Activation,
  Runtime Requirement, Permission Declaration, Compatibility Evidence,
  Capability Profile, dependency, and revocation target contracts but left
  production lifecycle owners OPEN. Capability Manager must not install
  plugins or invoke tools. Dispatcher invokes only an authorized target.
- **Decision:** Dev Preview v2 introduces Plugin and Tool Lifecycle Authority
  as the owner of Plugin Definition/Manifest lifecycle, plugin package
  installation, configuration without raw secrets, activation/deactivation,
  update, rollback, removal, dependency locking, compatibility-observation
  ingestion, revocation propagation, Capability Profile lifecycle, and Tool
  catalog ingestion. It registers canonical capability/provider inventory with
  Capability Manager and adapter/tool invocation metadata with Dispatcher
  without becoming an invocation authority.
- **Authoritative owner:** Plugin and Tool Lifecycle Authority.
- **Supporting actors:** Artifact Authority stores packages. Artifact Trust
  Authority verifies trust evidence. Authorization Authority authorizes
  install/activate/use policy. Secret Authority owns secret references.
  Capability Manager owns capability/provider inventory and resolution.
  Dispatcher owns invocation. Event Delivery Service delivers events.
- **Records owned:** plugin definitions/manifests, installed instances,
  activations, configuration records, dependency locks, compatibility
  observations accepted for lifecycle use, Capability Profiles, Tool catalog
  records, revocation records, and plugin/tool outbox records.
- **APIs or events governed:** inspect/plan/install/configure/activate/
  deactivate/update/rollback/remove/revoke, dependency-lock, tool-ingest, and
  lifecycle events.
- **Authorization boundary:** installation and activation require Actor
  Context and Authorization Decision evidence. Installation/activation never
  grants permission, approval, trust, eligibility, resolution, or execution.
- **Organization boundary:** installed and activated instances are scoped to
  installation, Organization, Team, Employee, or runtime scope as declared.
  Cross-Organization use fails closed.
- **Approval or verification boundary:** high-risk installation or activation
  may require Approval Authority verification. Artifact Trust verifies trust
  but cannot install or activate.
- **Failure and retry behavior:** dependency mismatch, revoked artifact,
  failed compatibility, missing secret reference, or failed rollback records a
  lifecycle failure. Retry preserves prior attempts and cannot invoke tools.
- **Persistence and recovery implications:** installed and active state is
  durable and recoverable. Runtime observations expire and cannot silently
  reorder or select providers.
- **Migration implications:** Lucy Plugin Platform, Plugin Registry, Module
  Registry, Capability Registry, Tool Runtime, and Adapter Manager remain
  donor evidence until deliberately mapped.
- **Rejected alternatives:** Capability Manager as plugin installer; Dispatcher
  as tool catalog owner; Tool Runtime as peer invocation authority; plugin
  installation creating grants; service catalog entries as installed state.
- **Consequences:** public plugin and tool onboarding can start without
  collapsing capability resolution or dispatch authority.
- **Compatibility notes:** Dev Preview can begin with Core/bundled/local
  plugins only; hosted marketplace remains post-v1 unless later promoted.
- **Security notes:** no raw credentials in manifests, configs, fixtures, logs,
  or tool catalog records.
- **Implementation prerequisites:** lifecycle service/API, Artifact Authority,
  trust verification, secret references, dependency locking, Capability
  Manager ingestion adapter, and Dispatcher adapter metadata handoff.
- **Validation requirements:** install/activate separation, no permission
  implication, rollback, revocation, dependency failure, no direct invocation,
  secret redaction, cross-scope rejection, and restart tests.

## ADR-DPV2-013: Team Template Authority owns templates and Team Architect apply records

- **Status:** Accepted
- **Context:** The organization-first roadmap requires Team Templates and Team
  Architect. Prior architecture says Team Architect is a guided employee and
  never becomes publisher, installer, approver, secret, workflow, scheduler,
  Dispatcher, or activation authority. Template lifecycle and apply protocol
  were OPEN.
- **Decision:** Dev Preview v2 introduces Team Template Authority as the owner
  of Team Template definitions, published template versions, installed
  template instances, template validation records, simulation/test-run
  records, activation plans, upgrade/rollback records, and Team Architect
  proposal/apply/save-as-template records. Team Architect remains a governed
  core Employee that proposes content; it does not own the template or apply
  authority.
- **Authoritative owner:** Team Template Authority.
- **Supporting actors:** Team Architect Employee, Organization Domain Service,
  Work Coordination Service, Employee Registry, Plugin and Tool Lifecycle
  Authority, Authorization Authority, Approval Authority, Secret Authority,
  Runtime Activation Authority, Artifact Authority, Operator/UI.
- **Records owned:** template definitions, template versions, installed
  template instances, proposal records, validation records, simulation/test-run
  records, apply plans, activation plans, upgrade/rollback records, and
  template outbox records.
- **APIs or events governed:** propose-template-intake record APIs, validate,
  simulate/test-run, save-template, install-template, apply-plan, activate,
  upgrade, rollback, deactivate, and template lifecycle events.
- **Authorization boundary:** proposal is not authorization. Applying a
  template calls each target authority with Actor Context and Authorization
  Decision evidence. Team Template Authority cannot grant capability use,
  approve, issue secrets, resolve providers, invoke tools, or mutate target
  resources directly outside accepted APIs.
- **Organization boundary:** a template instance applies to exactly one
  Organization. Cross-Organization templates are publishable artifacts only
  until installed into a target Organization under accepted authority.
- **Approval or verification boundary:** template activation and risky apply
  operations require verified Approval grants where policy requires. Team
  Architect cannot self-approve.
- **Failure and retry behavior:** proposal edits invalidate affected approvals.
  Failed validation, simulation, installation, apply, or activation preserves
  an explicit failed attempt. Retry uses a new apply attempt and preserves
  history.
- **Persistence and recovery implications:** proposal/apply/test-run state
  survives restart. Target resources remain owned by their target authorities.
  Apply records reconcile by querying target authorities, not by editing their
  stores.
- **Migration implications:** Employee Builder templates are donor/advanced
  inputs only. Lucy console/team concepts require deliberate mapping.
- **Rejected alternatives:** Team Architect as superuser; Work Coordination
  owning templates; Organization Domain owning template publication; Plugin
  installer owning Team Templates; UI state as applied template authority.
- **Consequences:** the non-coder organization-first path can be implemented
  without giving an AI employee unchecked system power.
- **Compatibility notes:** Dev Preview requires one flagship reusable Team
  Template; broad marketplace publishing is deferred.
- **Security notes:** templates may declare requirements and placeholders but
  cannot contain secret values, self-grant permissions, or self-activate.
- **Implementation prerequisites:** Organization Domain Service, Work
  Coordination Service, Approval Authority, Secret Authority, Artifact
  Authority, minimal Plugin/Tool lifecycle, and Operator/UI review flow.
- **Validation requirements:** proposal invalidation, deterministic
  validation, side-effect-controlled simulation, apply handoff, no direct
  target-store mutation, approval gating, secret placeholders, rollback, and
  restart tests.

## ADR-DPV2-014: Sandbox Authority owns execution workspace lifecycle

- **Status:** Accepted
- **Context:** Dev Preview v2 needs governed side-effect boundaries for tool,
  plugin, model-runtime, simulation, and artifact-producing work. Existing
  container use, filesystem paths, and test fixtures do not prove sandbox
  authority or cleanup behavior.
- **Decision:** Dev Preview v2 introduces Sandbox Authority as the owner of
  sandbox profiles, workspace identity, declared filesystem/network/process/
  resource/secret/artifact access, workspace lifecycle, violation evidence,
  cleanup, and sandbox attestation records. Dispatcher and Plugin/Tool
  Lifecycle Authority consume sandbox decisions for execution and activation.
- **Authoritative owner:** Sandbox Authority.
- **Supporting actors:** Dispatcher, Plugin and Tool Lifecycle Authority,
  Secret Authority, Artifact Authority, Runtime Activation Authority,
  Authorization Authority, Approval Authority, and Operator/UI.
- **Records owned:** sandbox profiles, workspace records, policy evaluations,
  cleanup records, violation records, attestations, and sandbox outbox records.
- **APIs or events governed:** evaluate-sandbox, create-workspace, attach-
  policy, record-violation, cleanup, attest, and sandbox lifecycle events.
- **Authorization boundary:** sandbox approval does not authorize the work
  itself, grant capability permission, resolve providers, or invoke tools.
  It only establishes the allowed boundary for separately authorized work.
- **Organization boundary:** workspaces are scoped to one Organization,
  work/execution context, and authorized actor. Cross-Organization filesystem,
  network, secret, or artifact access fails closed unless future policy
  explicitly accepts it.
- **Approval or verification boundary:** high-risk workspace policies may
  require Approval Authority verification. Sandbox attestation is not outcome
  verification.
- **Failure and retry behavior:** missing profile, undeclared side effect,
  policy violation, cleanup failure, or attestation mismatch produces truthful
  failure evidence. Retrying a sandboxed operation must not reuse dirty
  workspace state unless a policy explicitly permits it.
- **Persistence and recovery implications:** workspace state, cleanup status,
  and violations survive restart. Orphaned workspaces are reconciled and
  cleaned or quarantined with audit evidence.
- **Migration implications:** existing service-local temporary paths and
  container invocations are implementation details until registered through
  Sandbox Authority.
- **Rejected alternatives:** Dispatcher owning all sandbox policy; plugin
  manifests self-enforcing isolation; container runtime presence as
  authority; UI simulation state as sandbox evidence.
- **Consequences:** side-effecting tools can be introduced without silent file,
  process, network, secret, or artifact access.
- **Compatibility notes:** Dev Preview can start with a minimal local
  workspace implementation as long as the authority boundary is stable.
- **Security notes:** sandbox records must not include secret values or
  unnecessary prompt/memory content.
- **Implementation prerequisites:** minimal sandbox profile vocabulary,
  workspace store, Dispatcher integration, Plugin/Tool activation integration,
  and cleanup/restart policy.
- **Validation requirements:** allowed/denied filesystem and network access,
  secret/artifact scope, violation evidence, cleanup after completion/failure/
  cancellation/restart, no sandbox-as-authorization, and no fixture state in
  production tests.

## Implementation-readiness matrix

| Implementation epic | Readiness after Epic 8.1 | Remaining dependency |
|---|---|---|
| Epic 8.2 Organization Domain Service | READY | Identity/Authorization integration may begin with fail-closed stubs if live services are not yet implemented. |
| Epic 8.3 Work Coordination Service | PARTIALLY READY | Requires Organization Domain Service and idempotent Scheduler/Persistent Runtime adapters. |
| Epic 8.4 Job and Assignment target adoption | PARTIALLY READY | Requires Work Coordination handoff contract and Scheduler/Persistent Runtime migration plan. |
| Epic 8.5 Authorization and capability permission grants | READY | Requires resource/action vocabulary scoped to Dev Preview. |
| Epic 8.6 Approval Authority | READY | Requires notification boundary decision inside implementation scope. |
| Epic 8.7 Secret Authority | READY | Requires local backend choice and use-lease/injection record shape. |
| Epic 8.8 Event Delivery and outbox hardening | READY | Requires event envelope adoption plan per service. |
| Epic 8.9 Runtime Activation Authority | PARTIALLY READY | Requires Secret Authority for cloud paths; local-only path can begin first. |
| Epic 8.10 Artifact Authority and Work Result linkage | READY | Artifact schema gap may be discovered and must be handled in that epic. |
| Epic 8.11 Sandbox Authority | READY | Requires minimal profile vocabulary and Dispatcher integration boundary. |
| Epic 8.12 Plugin and Tool Lifecycle Authority | PARTIALLY READY | Requires Artifact Authority, Secret Authority, and Sandbox Authority for side-effecting or credentialed plugins. |
| Epic 8.13 Team Template and Team Architect | BLOCKED | Requires Organization, Work Coordination, Approval, Secret, Artifact, Sandbox, and minimal Plugin/Tool lifecycle. |
| Epic 8.14 Operator/UI clean-install journey | BLOCKED | Requires enough canonical APIs from the earlier epics to avoid UI-owned state. |

## Remaining OPEN decisions

These decisions remain OPEN because they do not block the first production
implementation epic or require broader product/security review:

1. production authenticator adapters, proof formats, workload identity,
   session revocation, first-principal recovery, and trust bootstrap;
2. Organization ownership transfer, recovery, nested Organization ownership,
   inheritance, and cross-Organization collaboration;
3. deep Organization policy inheritance and whether organization/team ranking
   scopes are later introduced;
4. full public marketplace, hosted publishing, billing, entitlement, and
   moderation boundaries;
5. memory, knowledge, experience, playbook, and history-ingestion authorities;
6. Budget/cost reservation and outcome/PPT evidence authority;
7. long-term event schema evolution, global retention policy, and cross-
   installation federation;
8. full sandbox profile taxonomy beyond the minimum Dispatcher/tool workspace
   boundary;
9. broad connector catalog and public SDK governance beyond the first local
   Plugin/Tool lifecycle.

## Remaining CONFLICTING decisions

These surfaces remain CONFLICTING / INVESTIGATE until a later migration or
retirement epic resolves them:

1. `services/assignment-service/app.py` as a peer job/assignment and legacy
   selection surface.
2. Employee Registry legacy `/resolve` assignment-selection behavior.
3. Lucy Workflow/Planning/Runtime Coordinator behavior that overlaps Work
   Coordination, Scheduler, Persistent Runtime, or Dispatcher authority.
4. Lucy Plugin Platform, Plugin Registry, Module Registry, Capability
   Registry, Tool Runtime, and Adapter Manager where they overlap accepted
   Plugin/Tool, Capability Manager, or Dispatcher boundaries.
5. Current service catalog entries that imply Capability Manager execution or
   Runtime Coordinator lease/execute authority.

## Proposed Epic 8.2

**Epic name:** Epic 8.2 - Organization Domain Service

**Objective:** Implement the production Organization Domain Service as the
single authoritative owner for Organization, Department, Team, Role, Position,
Membership, Position Occupancy, and Organization Domain lifecycle transition
records.

**Exact services:** add `services/organization-domain-service`; integrate only
read/reference calls to Identity, Authorization, Approval, and Event Delivery
interfaces as fail-closed stubs or adapters if those production services are
not yet live.

**Authoritative records:** Organization, Department, Team, Role, Position,
Membership, Position Occupancy, lifecycle transition, and Organization Domain
event outbox records.

**Contracts adopted:** existing Epic 5.0 Organization Domain contracts:
`organization.v1`, `department.v1`, `team.v1`, `role.v1`, `position.v1`,
`membership.v1`, `position-occupancy.v1`,
`organization-lifecycle-transition.v1`, and shared identity/trust evidence
references.

**APIs and events:** create/read/list/update lifecycle APIs for each
Organization Domain resource; transition APIs with expected revision; local
event/outbox APIs for Organization Domain transitions.

**Persistence changes:** new Organization Domain store only. No migrations to
Employee Registry, Scheduler, Persistent Runtime, Dispatcher, Capability
Manager, or Lucy.

**Migrations:** none in the initial implementation. Employee v2-to-v3 and
Employee Registry linkage are later compatibility work.

**Tests:** schema and semantic conformance, lifecycle transitions, owner and
revision checks, cross-Organization fail-closed checks, Role/Membership not
permission checks, Position hierarchy acyclicity, outbox/replay, restart,
negative stale-revision tests, and no service-code authority overlap tests.

**File-scope estimate:** one new service directory, focused service tests,
possibly one architecture conformance document update. No contract/schema
changes unless a blocking defect is discovered and explicitly scoped.

**Explicit exclusions:** no Work Coordination, no Scheduler changes, no
Persistent Runtime changes, no Employee Registry migration, no UI, no
deployment config, no Public Assignment, no Lucy, no plugin/tool lifecycle,
no secret/approval production service.

**Rollback boundary:** remove the new Organization Domain Service directory
and its tests before adoption; after persistence migration, rollback requires
export or destructive migration review.

**Acceptance criteria:** Organization Domain Service is the only production
Organization Domain state owner; all resource lifecycles are revisioned and
Organization-scoped; cross-Organization references fail closed; events are
producer-owned; no Role/Membership permission shortcut exists; no existing
service gains Organization authority; tests and documentation pass.

**Recommended model tier:** strong coding model with architecture-awareness;
frontier review for adversarial pre-commit.
