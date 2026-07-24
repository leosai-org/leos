# LEOS v2 Execution Plane Decisions

## Status and use

These architecture decision records define the adopted execution-plane
boundaries for LEOS 0.2.0 Developer Preview v2.

They are based on the RC11 versus Lucy reconciliation audit. They do not select
wire formats, databases, timeout values, or deployment topology unless stated.
Unsettled details are marked **OPEN**.

## ADR-001: Capability Manager resolves but does not execute

- **Status:** Accepted
- **Decision:** The Capability Manager owns capability and provider inventory,
  provider-capability bindings, ordered eligibility evaluation,
  first-ranked-valid selection, resolution rationale, and resolution audit.
  User-governed effective ranking establishes candidate order. Model Registry
  owns model-provider/runtime bindings, which Capability Manager consumes
  during intelligence resolution. Capability Manager does not invoke
  providers, adapt provider payloads, retry provider calls, or own execution
  attempts.
- **Context:** The Lucy implementation contains both `/resolve` and `/execute`
  and keeps a payload-adapter registry and execution history. These overlap with
  the Execution Dispatcher.
- **Consequences:** Capability Manager execution behavior is deprecated for v2.
  Callers requiring execution must use the Execution Dispatcher. A governed
  resolution contract is required.
- **OPEN:** Resolution validity, expiry, integrity, and compatibility behavior
  for the current execution endpoint.

## ADR-002: Execution Dispatcher is the sole governed invocation authority

- **Status:** Accepted
- **Decision:** The Execution Dispatcher authorizes and records every provider
  and tool invocation in the canonical execution plane. A Router or adapter may
  physically transmit an already-authorized request but may not initiate,
  redirect, retarget, escalate, substitute, or independently repeat it.
- **Context:** Lucy has provider invocation in both Capability Manager and
  Execution Dispatcher, while legacy employee execution can invoke its model
  layer directly. Multiple invocation authorities prevent consistent
  governance, retry, idempotency, normalization, and audit.
- **Consequences:** The dispatcher owns canonical execution validation,
  resolution consumption, provider request adaptation, invocation attempts,
  same-target idempotency-aware transport-retry enforcement, normalized
  results, and execution audit. Provider/model changes require a new governed
  Capability Manager resolution.
  Direct invocation by cognitive or persistent runtime services is forbidden.
- **OPEN:** The compatibility mechanism and retirement schedule for existing
  direct invocation paths.

## ADR-003: Employee Cognitive Service owns employee reasoning

- **Status:** Accepted
- **Decision:** The Employee Cognitive Service owns the employee
  reason/act/observe lifecycle, context assembly, cognitive checkpoints,
  attempts, observations, and cognitive terminal outcome.
- **Context:** Lucy's cognitive service already separates a cognitive run from
  persistent employee state, but it currently performs a single dispatch and
  has incomplete retry and restart behavior. Legacy employee runtime contains
  context and artifact behavior that must be migrated.
- **Consequences:** Cognitive behavior must not be added to the Persistent
  Employee Runtime. The cognitive service calls the dispatcher for actions and
  requests assignment transitions from the Persistent Employee Runtime.
  Per-run context may use durable working state, but Cognitive Service does not
  become a duplicate working-memory persistence authority.
- **OPEN:** Exact cognitive state names, checkpoint contract, context-provider
  boundaries, and artifact-production boundary.

## ADR-004: Persistent Employee Runtime owns assignment state, not reasoning

- **Status:** Accepted
- **Decision:** The Persistent Employee Runtime owns durable employee presence,
  mailbox, working state, assignment projection and transitions, and the
  scheduler lease/resource bridge. It does not reason, choose providers, adapt
  provider requests, or invoke providers.
- **Context:** The public RC11 implementation already provides durable employee,
  message, memory, assignment, resource-gate, and reconciliation behavior. Its
  current service contract uses the ambiguous term `assignment_execution`.
- **Consequences:** `assignment_execution` must be interpreted or revised to
  mean assignment transition and scheduler/resource bridging, not cognition or
  provider execution. Cognitive retry must not be implemented as repeated
  assignment start.
- **OPEN:** Exact assignment lifecycle, failure/cancellation endpoints, and
  scheduler/runtime terminal-transition protocol.

## ADR-005: Scheduler remains job, lease, and resource authority

- **Status:** Accepted
- **Decision:** The scheduler remains authoritative for job lifecycle, worker
  leases, compute/resource admission, reservations, and release.
- **Context:** Persistent runtime projects scheduler jobs into employee
  assignments and validates start/completion through the scheduler. Allowing
  another service to create independent lease or resource state would produce
  conflicting authorities.
- **Consequences:** Persistent runtime bridges assignment transitions to the
  scheduler. Cognitive and dispatcher services do not mutate scheduler state.
  Resource loss, lease expiry, cancellation, and terminal state must propagate
  through explicit contracts.
- **OPEN:** Ordering, acknowledgement, and reconciliation semantics for
  scheduler and assignment terminal transitions.

## ADR-006: Runtime Execution Coordinator is observation-only

- **Status:** Accepted
- **Decision:** The Runtime Execution Coordinator may provide durable
  correlation and await behavior for higher-level orchestration. It does not
  drive scheduler ticks, synchronize assignments, restart assignments,
  reconcile leases, or participate in provider execution.
- **Context:** The Lucy coordinator currently polls while triggering scheduler
  ticks, runtime sync, and assignment reconciliation. Those behaviors duplicate
  scheduler and Persistent Employee Runtime responsibilities.
- **Consequences:** An observation timeout does not mutate or terminate the
  underlying job. State recovery remains with the authority that owns the
  state. Coordinator callers receive observed authoritative outcomes.
- **OPEN:** Whether this remains a standalone service or is later merged into a
  higher-level orchestration service.

## ADR-007: Execution retries are idempotency-aware

- **Status:** Accepted
- **Decision:** The dispatcher may retry a concrete invocation only under a
  policy that accounts for the operation's idempotency and the ambiguity of the
  prior outcome.
- **Context:** Lucy retries exceptions and HTTP 5xx against the same provider.
  A timeout may occur after a side effect completed, making blind retry unsafe.
- **Consequences:** Executions and invocation attempts require distinct
  identifiers. Retry policy and outcomes are audited. Non-idempotent or
  unknown-idempotency actions cannot be blindly repeated. Dispatcher transport
  retry retains the same authorized target. Provider/model re-resolution,
  model escalation, and validation-triggered escalation are separate
  operations and require a new governed resolution.
- **OPEN:** Idempotency classification vocabulary, provider declaration format,
  idempotency-key transport, backoff defaults, and policy for unclassified
  operations.

## ADR-008: Assignment retry and cognitive retry are separate

- **Status:** Accepted
- **Decision:** Retrying a cognitive attempt does not restart an already-active
  assignment. Retrying or reassigning an assignment is a separate lifecycle
  decision governed by assignment and scheduler state.
- **Context:** In Lucy, a failed cognitive dispatch leaves the assignment
  running, while the next cognitive attempt calls assignment start again. The
  runtime accepts start only from assigned state, so the retry path breaks.
- **Consequences:** Cognitive attempts need their own lifecycle and identifiers.
  Assignment start is performed once per applicable assignment ownership
  period. Recovery coordinates assignment and cognition without conflating
  their states.
- **OPEN:** Rules for when scheduler retry creates a new assignment versus
  reuses an existing projection.

## ADR-009: Human approval requires an explicit verifiable grant

- **Status:** Accepted
- **Decision:** A caller-supplied Boolean is not evidence of human approval.
  Approval-required execution must carry or reference an explicit verifiable
  grant scoped to the action.
- **Context:** Lucy capability resolution uses an
  `allow_approval_required` Boolean and binding policy. Capability-level
  approval is not fully enforced, and no approval artifact is verified.
- **Consequences:** If the highest-ranked otherwise-eligible candidate lacks
  its required grant, Capability Manager returns `APPROVAL_PENDING`; it does
  not silently select a lower-ranked candidate. Only a future explicit
  governed policy may permit skipping such a candidate. Dispatcher verifies
  approval for the concrete invocation. Cognitive service may request and
  await approval but cannot self-grant it.
- **OPEN:** Approval authority, grant schema, verification mechanism, expiry,
  revocation, delegation, and action-scope comparison.

## ADR-010: Resolution and invocation use separate audit authorities

- **Status:** Accepted
- **Decision:** Capability Manager is authoritative for why a provider was
  selected. Execution Dispatcher is authoritative for how and whether that
  provider was invoked and what outcome was observed.
- **Context:** Lucy stores execution records in both services, making it unclear
  which record governs invocation history.
- **Consequences:** Dispatcher records reference the governing resolution ID.
  Capability Manager does not keep a competing invocation record. Correlation
  links the two audits.
- **OPEN:** Retention, event publication, and cross-service integrity rules.

## ADR-011: Failure and cancellation follow authority boundaries

- **Status:** Accepted
- **Decision:** Provider outcomes flow through dispatcher normalization and
  cognitive interpretation before assignment and scheduler terminal
  transitions. Scheduler cancellation, lease expiry, and resource loss flow
  back through persistent assignment state to cognition.
- **Context:** Lucy lacks an explicit persistent-runtime assignment failure
  endpoint, and terminal cognitive failure can leave the assignment and
  scheduler job active.
- **Consequences:** Explicit failure and cancellation contracts are required.
  Every terminal path must release or explicitly account for scheduler
  resources. No service may independently mark state owned by another service.
- **OPEN:** Compensation for completed external side effects and the precise
  terminal acknowledgement protocol.

## ADR-012: Correlation is preserved end to end

- **Status:** Accepted
- **Decision:** Applicable mission, workflow, step, job, lease, resource,
  employee, assignment, cognitive run, cognitive attempt, resolution,
  execution, invocation attempt, approval grant, and provider operation
  identifiers remain correlatable across the execution plane.
- **Context:** Lucy's dispatcher retains rich context in its envelope, but
  legacy payload adaptation can omit it from provider requests and several
  identifiers are nested rather than first-class.
- **Consequences:** Canonical contracts define identifier origin and
  propagation. Provider adaptation may omit fields only if the dispatcher
  retains an authoritative mapping.
- **OPEN:** Requiredness, field names, and integrity rules.

## ADR-013: Legacy employee-runtime behavior is migrated before retirement

- **Status:** Accepted
- **Decision:** The legacy employee runtime is not retired until required
  context, configuration, memory, knowledge, artifact, review, work-result, and
  audit behavior has a canonical v2 owner and equivalent tests.
- **Context:** The audited modern chain does not yet reproduce all useful
  legacy employee-runtime behavior.
- **Consequences:** Migration is capability-based, not directory-based.
  Provider invocation moves to dispatcher; reasoning context moves toward the
  cognitive boundary; assignment state remains in persistent runtime.
- **OPEN:** Artifact authority, company-knowledge boundary, long-term learned
  memory boundary, and compatibility duration.

## ADR-014: The Lucy runtime tree is evidence, not source authority

- **Status:** Accepted
- **Decision:** `lucy-runtime-reference` remains read-only evidence. The
  governed `leos-v2` repository is the only development target for Developer
  Preview v2.
- **Context:** Lucy contains real implementations that were absent from public
  RC11, but it also contains historical copies, live overlays, and duplicated
  responsibilities.
- **Consequences:** Implementations are promoted through reviewed changes and
  contract conformance in `leos-v2`; they are not developed in place on Lucy.
  Provenance and persisted-state migration require explicit review.
- **OPEN:** Promotion packaging, compatibility evidence, and operational data
  migration procedure.

## Consolidated open decisions

The following require later decisions or contracts:

1. assignment lifecycle states and transition protocol;
2. scheduler/runtime terminal acknowledgement and reconciliation;
3. cognitive-run states, checkpoints, and restart recovery;
4. event versus polling delivery for assignment availability;
5. resolution issuance, integrity, expiry, and revalidation;
6. approval authority and grant verification;
7. idempotency classification and provider idempotency-key support;
8. provider result and ambiguous-outcome normalization;
9. artifact, company-knowledge, and learned-memory authorities;
10. event-store authority and retention;
11. coordinator standalone versus merged deployment;
12. compatibility periods for deprecated Lucy behavior;
13. persisted Lucy state migration and provenance procedure.
