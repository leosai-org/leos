# LEOS v2 Execution Plane

## Status and scope

This document defines the target execution-plane architecture for the LEOS
0.2.0 Developer Preview v2 development tree.

It is an architecture boundary document, not an implementation specification.
It records the responsibilities and sequencing established by the RC11 versus
Lucy reconciliation audit. Exact wire formats, state enumerations, persistence
schemas, timeout values, and compatibility windows remain subject to explicit
contracts. Items that the audit did not settle are marked **OPEN**.

The canonical employee path is:

```text
Scheduler
  -> Persistent Employee Runtime
  -> Employee Cognitive Service
  -> Execution Dispatcher
```

Resolution and invocation are separate interactions:

```text
Execution Dispatcher -> Capability Manager : resolve
Capability Manager -> Execution Dispatcher : resolution record
Execution Dispatcher -> Router / Adapter / Provider : invoke resolved target
```

The Execution Dispatcher is the sole governed invocation authority: it
authorizes and records the invocation. A Router or adapter may physically
transmit the already-authorized request, but the Capability Manager does not
invoke the selected provider or tool.

The Runtime Execution Coordinator is not part of this normal execution path. It
is an optional observation and await facade for higher-level orchestration.

## 1. Architectural goals

The v2 execution plane must:

1. establish one authority for each material state transition;
2. separate employee reasoning from durable employee and assignment state;
3. separate governed capability resolution from provider invocation;
4. preserve scheduler authority over jobs, leases, compute admission, and
   resource release;
5. provide end-to-end correlation across planning, assignment, cognition,
   resolution, dispatch, and provider execution;
6. make retry behavior safe for side-effecting and non-idempotent operations;
7. represent approval as a verifiable governance artifact rather than a
   caller assertion;
8. propagate failure and cancellation to every authority that owns affected
   state or resources;
9. make restart and reconciliation behavior explicit and testable;
10. permit higher-level systems to observe and await execution without creating
    another execution control plane;
11. preserve required behavior from the current Lucy implementation while
    removing duplicated responsibilities;
12. allow contracts and tests to govern promotion into the public v2 source.

## 2. Canonical service responsibility matrix

| Service | Canonical responsibility | Must not own | Primary state authority |
|---|---|---|---|
| Execution Scheduler | Job lifecycle, worker leases, compute/resource admission, and resource release | Employee reasoning, provider selection, provider invocation, employee mailbox or memory | Jobs, leases, admission decisions, reservations, and resource release |
| Persistent Employee Runtime | Durable employee presence, mailbox, working state, assignment projection and assignment transitions, and the scheduler lease/resource bridge | Reasoning, capability resolution, provider payload adaptation, or provider invocation | Employee runtime state, employee messages, working memory, and projected assignments |
| Employee Cognitive Service | Employee reasoning lifecycle, context assembly, reason/act/observe behavior, cognitive checkpoints, and cognitive attempts | Direct scheduler mutation, durable assignment authority, capability/provider inventory, or direct provider invocation | Cognitive runs, attempts, checkpoints, observations, and cognitive results |
| Capability Manager | Capability inventory, provider inventory, provider-capability bindings, ordered eligibility evaluation, first-ranked-valid selection, governance-aware resolution, and resolution audit | Establishment or reordering of candidate order, model-provider/runtime binding authority, provider invocation, provider payload adaptation, execution retry, or execution-result ownership | Capabilities, providers, provider-capability bindings, eligibility decisions, and resolutions |
| Execution Dispatcher | Sole governed provider/tool invocation authority, acquisition and consumption of governed resolutions, request adaptation, same-target idempotency-aware transport retry, result normalization, and execution audit | Employee reasoning, assignment lifecycle, scheduler leases, capability inventory authority, provider/model selection, or provider/model failover | Dispatch executions, invocation attempts, adapted requests, normalized results, and execution errors |
| Runtime Execution Coordinator | Optional durable observation/await facade and correlation for higher-level orchestration | Scheduler driving, assignment restart, lease reconciliation, provider invocation, or normal execution participation | Observation subscriptions or coordination records only |
| Provider / Tool | Perform the selected bounded capability under the supplied execution and governance context | LEOS assignment, cognition, resolution, or scheduler authority | Provider-local operational state only |

### Responsibility interpretation

“Authority” means that other services may request or observe a transition, but
must not independently create a conflicting authoritative transition.

The Persistent Employee Runtime is the durable employee-facing projection of a
scheduler job. The scheduler remains authoritative for the job, lease, and
resource reservation. Their contracts must define how the projection is
created, acknowledged, reconciled, and made terminal.

## 3. Canonical execution sequence

The canonical sequence is:

1. The scheduler admits a job, reserves required resources, and leases the job
   to an eligible employee runtime worker.
2. The Persistent Employee Runtime projects the leased job as an employee
   assignment and records the employee's working-state correlation.
3. The Employee Cognitive Service discovers or receives the available
   assignment and atomically establishes a cognitive run and attempt.
4. The Employee Cognitive Service requests that the Persistent Employee
   Runtime transition the assignment into its active state.
5. The Persistent Employee Runtime validates the scheduler lease and resource
   state through its scheduler bridge and records the assignment transition.
6. The Employee Cognitive Service assembles the permitted employee, assignment,
   memory, knowledge, configuration, policy, and prior-observation context.
7. The cognitive loop decides on a bounded capability action.
8. The Employee Cognitive Service sends a complete canonical execution request,
   including the applicable effective intelligence policy or ranking, to the
   Execution Dispatcher. It does not select or call a provider directly.
9. The Execution Dispatcher asks the Capability Manager for a governed
   resolution.
10. The Capability Manager evaluates capability existence,
    provider-capability bindings, applicable model-provider/runtime binding
    facts, eligibility, health/trust inputs, permission requirements, approval
    state, and applicable constraints. It preserves the user-governed candidate
    order, performs first-ranked-valid selection, and records and returns the
    durable resolution record or reference. It does not invoke the provider.
11. The Execution Dispatcher validates the returned resolution, adapts the
    canonical request to the selected provider contract, and applies
    idempotency-aware invocation policy.
12. The Execution Dispatcher invokes the selected provider or tool and records
    every attempt.
13. The Execution Dispatcher normalizes the provider response or error and
    returns it to the Employee Cognitive Service.
14. The Employee Cognitive Service observes the result and either continues
    reasoning, checkpoints, waits for approval, retries a cognitive action, or
    reaches a terminal cognitive result.
15. On terminal success, failure, or cancellation, the Employee Cognitive
    Service requests the corresponding assignment transition from the
    Persistent Employee Runtime.
16. The Persistent Employee Runtime bridges that transition to the scheduler so
    the scheduler can complete, fail, or cancel the job and release resources.
17. The Runtime Execution Coordinator, when used, observes these authoritative
    states and reports them to higher-level orchestration without driving them.

**OPEN:** Whether assignment availability is delivered by an event, polling, or
both is not yet decided.

**OPEN:** The exact ordering and atomicity protocol between scheduler terminal
state and Persistent Employee Runtime terminal state requires a contract.

## 4. Assignment lifecycle

An assignment is the Persistent Employee Runtime's durable employee-facing
projection of a scheduler job and lease.

The lifecycle must distinguish at least:

- availability before cognitive ownership;
- active execution;
- successful completion;
- failure;
- cancellation;
- any governed waiting state needed to prevent resource or lease ambiguity.

The exact state names and transition table are **OPEN**. They must be defined by
an authoritative assignment lifecycle contract rather than inferred from
service-local strings.

The lifecycle must satisfy these rules:

1. A scheduler job identifier maps unambiguously to its projected assignment.
2. An assignment records the applicable employee, lease, workflow, step,
   capability, and resource correlations.
3. Starting an assignment is distinct from starting or retrying a cognitive
   attempt.
4. A cognitive retry must not attempt to start an already-active assignment
   again.
5. Assignment transitions are conditional and concurrency-safe.
6. Terminal cognitive failure or cancellation must be representable as a
   terminal assignment transition.
7. Scheduler rejection of start or completion must not be hidden.
8. Scheduler success followed by local persistence failure must be
   reconcilable.
9. Lease mismatch, expiry, or resource loss must propagate to cognition rather
   than silently restart reasoning.
10. Reconciliation must consider both assignment and cognitive state.

The Persistent Employee Runtime may reconcile its projection with scheduler
authority. It must not independently restart cognition as part of that
reconciliation.

The Persistent Employee Runtime owns durable employee working-state storage.
The Employee Cognitive Service may read that state as an input to per-run
context assembly, but it must not become a duplicate working-memory persistence
authority.

## 5. Cognitive-run lifecycle

A cognitive run represents the reasoning lifecycle for one assignment. A
cognitive attempt represents one bounded attempt within that lifecycle.

The lifecycle must support:

- atomic claim of an available assignment;
- context assembly;
- reasoning;
- action request;
- observation of a normalized execution result;
- durable checkpointing;
- a separate subsequent cognitive attempt when permitted;
- waiting for explicit human approval;
- successful completion;
- failure;
- cancellation;
- restart recovery.

Exact state names, checkpoint format, and the relationship between one
cognitive run and multiple dispatcher executions are **OPEN**.

The following boundaries are fixed:

1. The cognitive service owns reasoning and cognitive attempts.
2. It does not mutate scheduler jobs directly.
3. It does not invoke providers or tools directly.
4. It may request assignment transitions from the Persistent Employee Runtime.
5. It may submit multiple bounded execution requests during a reason/act/observe
   loop.
6. Every dispatcher execution must correlate to the cognitive run and attempt.
7. Cognitive retry and assignment retry are separate concepts.
8. Restart recovery must not leave a durable run indefinitely marked active
   without an owner.

## 6. Execution and resolution boundaries

### Capability Manager boundary

The Capability Manager answers:

> Given this capability request, requester, governance context, and constraints,
> which provider or tool is eligible and selected, and why?

It owns:

- capability definitions;
- provider inventory;
- provider-capability bindings;
- eligibility inputs and evaluation;
- governance constraints used during resolution;
- ordered eligibility evaluation against the user-governed effective ranking;
- first-ranked-valid selection;
- the selected provider;
- a durable resolution record and rationale.

User-governed effective ranking establishes candidate order. The Capability
Manager may eliminate candidates through governed eligibility rules but may
not reorder otherwise-valid candidates. Model Registry owns
model-provider/runtime bindings; Capability Manager consumes those binding
facts during intelligence resolution.

It does not:

- adapt provider payloads;
- invoke a provider;
- retry an invocation;
- normalize a provider result;
- own execution attempt history.

### Execution Dispatcher boundary

The Execution Dispatcher answers:

> Given a canonical execution request and a governed resolution, how is this
> request safely invoked and what was the normalized outcome?

It owns:

- canonical execution-envelope validation;
- acquisition and validation of a governed resolution;
- provider request adaptation;
- invocation;
- attempt history;
- same-target idempotency-aware transport-retry enforcement;
- normalized result and error production;
- execution audit.

The canonical normal path is that the Cognitive Service supplies a complete
execution request, including applicable effective intelligence policy or
ranking, and the Dispatcher requests a governed resolution from Capability
Manager. Capability Manager returns a durable resolution record or reference;
the Dispatcher invokes only that resolved target.

The Dispatcher does not perform provider/model failover. It may retry the same
authorized target only when retry policy, idempotency semantics, and the
failure class permit a transport retry. Any provider/model change requires a
new governed resolution from Capability Manager.

**OPEN:** Resolution expiry, integrity protection, and revalidation rules are
not decided.

## 7. Approval and governance boundaries

Human approval must be represented by an explicit, verifiable grant. A Boolean
such as `allow_approval_required=true` is not evidence that approval occurred.

The governance boundary must:

1. identify the action, requester, capability, provider constraints, and scope
   covered by the approval;
2. identify who or what granted approval;
3. be verifiable by the resolution and/or dispatch authority;
4. have defined validity, expiry, and revocation semantics;
5. prevent reuse for a materially different action;
6. be correlated with the assignment, cognitive run, resolution, and execution;
7. be retained in the relevant audit records.

If the highest-ranked otherwise-eligible candidate requires an approval grant
that is not present, Capability Manager returns `APPROVAL_PENDING`. It does not
silently select a lower-ranked candidate. A future explicit governed policy may
permit skipping unapproved candidates, but that behavior must never be
implicit.

The Execution Dispatcher must verify that the resolution and approval evidence
authorize the concrete invocation before invoking a side-effecting provider or
tool.

The Persistent Employee Runtime may project a waiting state, but it does not
decide whether an action is approved. The Employee Cognitive Service may
request approval and wait for it, but it does not self-grant approval.

**OPEN:** The service that issues and revokes approval grants is outside this
document's settled scope.

**OPEN:** The approval grant schema and cryptographic or registry-based
verification mechanism remain to be defined.

## 8. Retry and idempotency principles

Retries are owned at the layer that can determine what is being retried:

- scheduler retry concerns a job or lease;
- assignment retry concerns assignment ownership or lifecycle;
- cognitive retry concerns reasoning or selection of a next action;
- dispatcher retry concerns a concrete provider invocation.

These retries must not be treated as interchangeable.

Dispatcher retry rules:

1. Every execution has a stable execution identifier.
2. Every invocation attempt has a distinct attempt identifier.
3. A provider operation must have a known idempotency classification before
   automatic retry.
4. A side-effecting or unknown-idempotency operation must not be blindly
   repeated after a timeout or ambiguous transport failure.
5. When supported, an idempotency key must be passed to the provider in its
   declared contract.
6. Retry policy, backoff, attempt limits, and retry decisions must be recorded.
7. A transport retry must retain the same authorized provider/model target.
8. A normalized result must distinguish definitive failure from an ambiguous
   outcome where the provider may have completed the action.

Transport retry, provider/model re-resolution, model escalation, and
validation-triggered escalation are separate operations. Re-resolution does
not automatically make a failed candidate invalid. A subsequent resolution
may exclude it only when a governed eligibility observation or escalation
policy makes it invalid for the relevant scope. Without a changed eligibility
fact or explicit escalation authorization, re-resolution may select the same
first-ranked candidate again.

**OPEN:** The idempotency classification vocabulary and default behavior for an
unclassified provider are not yet defined.

**OPEN:** The exact failure taxonomy for transport retry, provider/model
re-resolution, model escalation, and validation-triggered escalation is not
yet defined.

## 9. Failure and cancellation propagation

Failure and cancellation must propagate through explicit transitions:

```text
Provider/Tool
  -> Execution Dispatcher
  -> Employee Cognitive Service
  -> Persistent Employee Runtime
  -> Scheduler
```

The reverse direction carries scheduler lease expiry, resource loss, operator
cancellation, or job cancellation back toward cognition.

Required principles:

1. Provider failure becomes a normalized dispatcher outcome.
2. Dispatcher exhaustion does not directly mutate an assignment.
3. Cognitive service decides whether the outcome permits another cognitive
   action or makes the cognitive run terminal.
4. A terminal cognitive outcome is submitted to the Persistent Employee
   Runtime.
5. Persistent Employee Runtime bridges terminal assignment state to scheduler
   job state and resource release.
6. Scheduler cancellation or lease/resource loss is projected into the
   assignment and communicated to cognition.
7. Cancellation is not reported complete until authorities that own affected
   resources have acknowledged it or the contract explicitly records a pending
   cleanup state.
8. Partial writes and uncertain remote outcomes must be visible, not collapsed
   into generic failure.

**OPEN:** Compensation behavior for completed external side effects is
provider- and capability-specific and is not defined here.

## 10. Correlation identifiers

The execution plane must preserve applicable identifiers end to end:

| Identifier | Authority or origin | Purpose |
|---|---|---|
| `mission_id` | Higher-level planning/orchestration | Correlates execution to a mission |
| `workflow_id` | Workflow authority | Correlates the workflow instance |
| `step_id` | Workflow authority | Identifies the workflow step |
| `job_id` | Scheduler | Identifies scheduler job lifecycle |
| `lease_id` | Scheduler | Identifies worker lease authority |
| `resource_reservation_id` | Scheduler/resource authority | Identifies admitted compute resources |
| `employee_id` | Employee authority | Identifies the assigned employee |
| `assignment_id` | Persistent Employee Runtime | Identifies employee-facing assignment projection |
| `cognitive_run_id` | Employee Cognitive Service | Identifies the reasoning lifecycle |
| `cognitive_attempt_id` | Employee Cognitive Service | Identifies a bounded cognitive attempt |
| `resolution_id` | Capability Manager | Identifies the governed provider resolution |
| `execution_id` | Execution Dispatcher | Identifies canonical execution |
| `invocation_attempt_id` | Execution Dispatcher | Identifies one provider invocation attempt |
| `approval_grant_id` | **OPEN** approval authority | Identifies verifiable approval evidence |
| `provider_operation_id` | Provider, when supplied | Correlates provider-local execution |

Not every job originates in a mission or workflow, so higher-level identifiers
may be absent. Once present, identifiers must not be silently discarded by
request adaptation. Provider-specific payloads may omit identifiers only when
the dispatcher retains a complete authoritative correlation record.

**OPEN:** Field requiredness and propagation rules belong in the canonical
contracts.

## 11. Runtime Execution Coordinator observation-only role

The Runtime Execution Coordinator is optional. It provides a durable interface
for higher-level systems that need to submit or register interest in a job and
later await its authoritative outcome.

It may:

- persist an observation or await record;
- correlate a job with its assignment, cognitive run, resolution, and
  execution when those identifiers become available;
- read scheduler and Persistent Employee Runtime status;
- return completed, failed, cancelled, blocked, interrupted, or still-pending
  observations as defined by its contract;
- apply an observer timeout without changing the underlying execution.

It must not:

- trigger scheduler ticks;
- create or renew leases;
- import assignments;
- start or restart assignments;
- perform lease reconciliation;
- call the cognitive service to force execution;
- resolve capabilities;
- invoke providers;
- mark the underlying job or assignment terminal.

An observer timeout means only that the observation did not finish within its
window. It does not mean the underlying job was cancelled or stopped.

**OPEN:** Whether this observation role remains a standalone service or is
eventually merged into a higher-level orchestration service is not decided.

## 12. Legacy responsibilities that must be migrated

The current Lucy legacy employee runtime contains behavior that is not supplied
by the audited modern chain and must not be lost during migration:

- accepted-work discovery where work does not yet enter through the canonical
  scheduler assignment flow;
- effective employee configuration retrieval;
- approved employee-learning memory retrieval;
- company-knowledge retrieval;
- context and professional prompt construction;
- interpretation of assignment objectives, capabilities, and expected
  artifacts;
- production and durable reference of work artifacts;
- updates to the originating work record;
- representation of review-required outcomes;
- result summaries and execution history;
- normalization of legacy provider responses;
- prompt, context, response, and artifact auditability;
- explicit failure updates to the originating work record.

These responsibilities must be assigned deliberately:

- reasoning-context responsibilities belong with the Employee Cognitive
  Service or a canonical context dependency;
- provider invocation belongs with the Execution Dispatcher;
- assignment state belongs with the Persistent Employee Runtime;
- scheduler state belongs with the scheduler;
- durable artifact storage belongs with the applicable persistence/artifact
  authority.

**OPEN:** The canonical artifact authority and the final boundary for company
knowledge and long-term learned memory are not settled by this document.

## 13. Deprecated and forbidden responsibility overlaps

The following overlaps are architecturally deprecated for v2:

1. Capability Manager direct provider execution.
2. Capability Manager provider payload adaptation.
3. Separate payload-adapter registries in Capability Manager and Execution
   Dispatcher.
4. Employee Cognitive Service direct provider or tool invocation.
5. Employee Cognitive Service direct scheduler state mutation.
6. Persistent Employee Runtime reasoning or prompt execution.
7. Persistent Employee Runtime provider invocation.
8. Runtime Execution Coordinator scheduler driving.
9. Runtime Execution Coordinator assignment restart or lease reconciliation.
10. Runtime Execution Coordinator participation in normal provider execution.
11. Caller-supplied approval Booleans treated as approval evidence.
12. Blind retry of operations with unknown or non-idempotent effects.
13. Treating cognitive retry as assignment restart.
14. Independent services creating conflicting terminal states for the same job
    or assignment.
15. Dropping correlation, policy, or approval information during provider
    request adaptation without retaining it in the canonical audit record.

Deprecated endpoints may require a compatibility period. Compatibility behavior
must delegate to the canonical authority and must not preserve two independent
authorities.

**OPEN:** Compatibility duration and removal release are not yet decided.

## 14. Required contracts

The following governed contracts are required before the execution plane is
considered internally complete:

1. canonical execution request and normalized result/error;
2. capability-resolution request and response;
3. provider inventory and provider-capability binding records;
4. model-provider/runtime binding facts consumed from Model Registry;
5. resolution integrity, validity, expiry, and revalidation;
6. provider request-adaptation declaration;
7. provider execution result and ambiguous-outcome representation;
8. assignment lifecycle and conditional transitions;
9. scheduler-to-assignment projection and reconciliation;
10. cognitive-run, cognitive-attempt, and checkpoint lifecycle;
11. transport retry, re-resolution, escalation, and idempotency classification;
12. approval request, approval-pending result, and verifiable approval grant;
13. permission/eligibility evaluation result;
14. cancellation and failure propagation;
15. end-to-end correlation identifiers;
16. execution-plane event envelope and event authority;
17. Runtime Execution Coordinator observation/await request and outcome;
18. artifact reference and work-result update, if those remain execution-plane
    outputs.

Existing code-level labels such as `leos.execution.v1`,
`leos.cognition.v1`, `leos.employee-runtime-resource-lifecycle.v1`, and
`leos.runtime-coordination.v2.2` are evidence of intended contracts. Their
presence does not by itself establish complete v2 contract authority.

## 15. Required test categories

Promotion requires tests in these categories:

### Contract tests

- schema validation for every boundary;
- backwards-compatibility behavior where explicitly retained;
- required correlation propagation;
- normalized error and ambiguous-outcome behavior.

### Responsibility-boundary tests

- Capability Manager resolves but cannot invoke;
- dispatcher is the only provider invocation path;
- cognitive service cannot mutate scheduler state directly;
- Persistent Employee Runtime does not reason or invoke;
- coordinator is observation-only.

### Lifecycle tests

- assignment projection, start, completion, failure, and cancellation;
- cognitive claim, checkpoints, attempts, restart recovery, and terminal state;
- scheduler lease expiry and resource loss propagation;
- reconciliation after partial persistence failures.

### Resolution and governance tests

- provider eligibility, provider-capability binding, model-provider/runtime
  binding facts, trust, health, and deterministic ordered evaluation;
- permissions and approval-required exclusion;
- valid, expired, revoked, or mismatched approval grants;
- resolution integrity and expiry.

### Dispatch tests

- request adaptation for supported provider contracts;
- success, client error, server error, timeout, and malformed response;
- idempotent retry;
- prohibited retry for non-idempotent or unknown operations;
- same-target governed transport retry;
- provider/model change only after a new governed resolution;
- execution and attempt audit.

### Concurrency and recovery tests

- atomic assignment and cognitive-run claims;
- duplicate delivery;
- concurrent transition attempts;
- service restart at every non-terminal state;
- scheduler success followed by runtime persistence failure;
- provider completion followed by response loss.

### End-to-end tests

- assignment through normalized provider result and scheduler completion;
- terminal provider failure through resource release;
- human approval request, grant verification, resume, and completion;
- cancellation initiated at scheduler and higher-level orchestration;
- correlation across all participating authorities;
- coordinator observation without mutation.

## 16. Migration strategy from the current Lucy implementation

The Lucy tree is evidence and reference only. It is not a writable source of
truth. Migration into v2 must occur through reviewed changes to the governed
public source tree.

### Phase 1: Freeze boundaries and capture behavior

1. Adopt this responsibility model and the accompanying decision record.
2. Inventory the exact current Lucy endpoints and persisted states for the five
   audited services.
3. Capture compatibility requirements and live dependency callers.
4. Record unresolved items as explicit design work rather than inferring
   authority from existing code.

### Phase 2: Establish contracts and tests

1. Define the required execution, resolution, assignment, cognition,
   governance, retry, correlation, and observation contracts.
2. Add contract conformance tests and responsibility-boundary tests.
3. Build end-to-end fixtures for happy path, failure, cancellation, approval,
   restart, and ambiguous provider outcome.
4. Decide compatibility and versioning policy. **OPEN**

### Phase 3: Promote canonical service implementations

1. Preserve the existing public Persistent Employee Runtime as the starting
   assignment-state implementation because it is already in the governed tree.
2. Promote reviewed implementations of the Employee Cognitive Service,
   Execution Dispatcher, Capability Manager, and, if retained, Runtime
   Execution Coordinator.
3. Ensure promoted implementations conform to the new contracts rather than
   copying Lucy's duplicated authority unchanged.
4. Add migration handling for persisted Lucy state only after its required
   compatibility and provenance are separately approved. **OPEN**

### Phase 4: Remove overlaps

1. Move provider execution and payload adaptation out of Capability Manager.
2. Make Execution Dispatcher the sole governed invocation authority and limit
   Router/adapter behavior to physical transmission of an already-authorized
   request.
3. Separate cognitive retry from assignment transitions.
4. Add explicit assignment failure and cancellation propagation.
5. Remove scheduler driving, restart, and lease reconciliation from Runtime
   Execution Coordinator.
6. Consolidate event and correlation authority.

### Phase 5: Migrate required legacy behavior

1. Move effective configuration, memory, company knowledge, prompt/context,
   artifact, review, work-result, and audit behavior to their canonical v2
   owners.
2. Prove equivalent required outcomes through tests.
3. Deprecate legacy execution paths only after all live callers have migrated.
4. Preserve read compatibility or historical data access where required.
   **OPEN**

### Phase 6: Acceptance and retirement

1. Run contract, lifecycle, governance, retry, recovery, and end-to-end suites.
2. Verify that only the dispatcher can invoke providers.
3. Verify that every terminal path releases or explicitly accounts for
   scheduler resources.
4. Verify complete correlation and auditable approval evidence.
5. Retire compatibility execution paths according to the approved policy.

No phase authorizes modification of the Lucy reference tree.
