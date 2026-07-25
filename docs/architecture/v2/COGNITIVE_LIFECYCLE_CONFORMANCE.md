# Cognitive lifecycle conformance

## Authority

Employee Cognitive Service owns cognitive runs, attempts, ephemeral per-run
context, observations, retry decisions, waiting conditions, and cognitive
terminal outcomes. It does not own assignments, employee working projection,
provider selection, invocation, Scheduler jobs, leases, or resources.

The canonical path is:

```text
Persistent Runtime assignment
  -> Employee Cognitive Service
  -> Execution Dispatcher
  -> Employee Cognitive Service observation
  -> Persistent Runtime terminal transition
```

There is no direct Cognitive Service path to Scheduler, Capability Manager,
AI Router, a provider, or a model runtime.

## Run and attempt lifecycle

Durable run meanings are:

- `run_created`: assignment discovered and run established;
- `running`: assignment started and cognition active;
- `retry_wait`: cognitive policy permits another cognitive attempt after the
  recorded time;
- `waiting`: explicit reconciliation or review is required;
- `approval_pending`: verified approval is required;
- `order_required`: governed ordering is required;
- `completed`, `failed`, `cancelled`: immutable cognitive terminal outcomes.

Attempts are ordered children of one run. Each attempt has its own stable
cognitive-attempt and execution identifiers. Creating another attempt never
creates or restarts an assignment.

For Epic 1.2D a run performs at most **one successful governed action**.
`SUCCESS` therefore intentionally means that the constrained cognitive
objective is complete and the assignment is completed through Persistent
Runtime. General multi-action reason/act/observe/reason loops remain future
work.

## Run claiming and concurrency

A durable SQLite claim token and expiry fence one run mutation owner at a
time. Claims use `BEGIN IMMEDIATE`. Assignment start and reconciliation,
attempt numbering, Dispatcher submission, observation application, terminal
transition work, cancellation, and recovery all require the current claim.
Attempt numbers use the claimed run's maximum persisted sequence rather than
an unprotected row count.

Cancellation first writes a durable cancellation fence. If a Dispatcher
execution is already in flight, its known execution identity is reconciled and
no further execution is created. The eventual canonical result is retained
even though assignment cancellation remains the requested terminal outcome.

## Assignment start

Persistent Runtime assignment `/start` occurs once per cognitive run's
assignment execution period. Cognitive retry reuses the running assignment.
A later Scheduler retry appears as a new assignment identity and therefore
creates a new cognitive run.

When local start acknowledgement is absent, Cognitive Service first reads the
exact assignment from Persistent Runtime. `running` is recorded locally,
`assigned` permits `/start`, terminal state finalizes cognition, and unavailable
or unknown state enters safe reconciliation. A lost `/start` response is never
treated as success; the next recovery reads Runtime truth before acting.

## Canonical execution

Every action is validated as `leos.execution.v1` before submission to
Dispatcher. Correlation includes the employee, assignment, job, lease when
available, workflow, step, cognitive run, cognitive attempt, and execution.
Ephemeral context remains cognitive state; durable employee working state
remains owned by Persistent Runtime.

## Result mapping

| Dispatcher result | Cognitive state/action |
|---|---|
| `SUCCESS` | Observe result and complete through Persistent Runtime |
| `APPROVAL_PENDING` | `approval_pending`; no automatic retry |
| `GOVERNED_ORDER_REQUIRED` | `order_required`; no automatic retry |
| `NO_ELIGIBLE_PROVIDER` | Terminal cognitive failure |
| `REJECTED` | Terminal governed refusal/failure |
| `PROVIDER_ERROR` | Stable cognitive-decision wait |
| `TRANSPORT_ERROR` | Stable cognitive-decision wait |
| `AMBIGUOUS_OUTCOME` | `waiting`; never automatically replay |

Automatic cognitive action replay is disabled in Epic 1.2D.
`PROVIDER_ERROR` and `TRANSPORT_ERROR` persist their canonical observation and
enter a stable `COGNITIVE_DECISION_REQUIRED` wait. A future governed
retry/reasoning policy must authorize and construct any later action.

## Terminal bridge and recovery

Completion, failure, and cancellation are requested only through Persistent
Runtime. Before the request, Cognitive Service durably stores the stable
transition identity and exact provisional service-local request. Response-loss
or restart reconciliation reuses that identical request and identity.

If a dispatched execution has no local observation after restart, Cognitive
Service retrieves the execution by its existing ID from Dispatcher before it
can consider another action. It never generates a replacement execution ID to
bypass duplicate protection.

Recovery gives durable evidence strict precedence before new work:

1. apply a persisted terminal acknowledgement;
2. apply an observed but unapplied canonical result;
3. reconcile an existing dispatched execution by the same execution ID;
4. replay a persisted terminal request with the same transition ID and body;
5. only then consider creating an attempt.

Observation rows have an explicit result-applied marker. Run state and that
marker advance together for nonterminal results. Terminal acknowledgement
finalization advances the cognitive terminal state before normal execution can
resume.

## Waiting and ambiguous outcomes

Approval and ordering waits are excluded from automatic polling selection.
They resume only through the explicit run resume endpoint after the governing
condition is resolved externally.

An ambiguous result records that explicit reconciliation is required. The
potentially side-effecting operation is not automatically submitted again,
under either the original or a fresh execution ID.

Generic resume is prohibited for ambiguous, approval-pending, order-required,
and execution-reconciliation waits. Approval and ordering require future
governed evidence contracts; ambiguity requires future authoritative
reconciliation or operator/governed policy.

## Donor behavior removed and remaining debt

The Lucy donor's repeated assignment start, noncanonical Dispatcher envelope,
generic exception retry, direct working-memory write, and success-only result
handling are removed.

OPEN:

- canonical shared cognitive-run and attempt contracts;
- governed approval/order resume evidence;
- richer multi-action reason/act/observe policy and checkpoints;
- durable cognitive event/outbox contract;
- operator reconciliation policy for ambiguous external side effects.
