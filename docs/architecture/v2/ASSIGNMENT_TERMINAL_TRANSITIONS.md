# Assignment terminal transitions

## Purpose

This prerequisite completes the authority bridge required by Employee
Cognitive Service. Cognitive Service reports terminal outcomes to Persistent
Employee Runtime; it never mutates Scheduler state directly.

## Authority path

```text
Employee Cognitive Service
  -> Persistent Employee Runtime assignment transition
  -> Execution Scheduler job transition and resource release
  -> Persistent Employee Runtime assignment projection
```

Persistent Runtime exposes:

- `POST /assignments/{assignment_id}/complete`;
- `POST /assignments/{assignment_id}/fail`;
- `POST /assignments/{assignment_id}/cancel`.

Scheduler exposes:

- `POST /jobs/{job_id}/complete`;
- `POST /jobs/{job_id}/fail`;
- `POST /jobs/{job_id}/cancel`.

## Transition identity and recovery

Every completion, failure, or cancellation carries a stable `transition_id`. Repeating the
same transition returns its existing result. Reusing an identifier for a
different assignment, job, target state, or request is a conflict.

Persistent Runtime journals `requested`, `scheduler_acknowledged`, and
`local_committed`. It commits the request before calling Scheduler. If Scheduler
acknowledges but the local projection is not committed, replay uses the same
transition identity and Scheduler returns the prior result. This permits local
completion without repeating the authoritative terminal transition.

Scheduler journals its terminal transition before changing job, lease, or
resource state. Cancellation is terminal and never becomes failure or retry.
Failure retains existing Scheduler retry policy: the job may become `queued`
or `failed`.

Completion and failure are scoped to the exact Scheduler lease/execution
attempt. A stale transition for an earlier lease cannot mutate a later attempt.
Cancellation is a whole-job terminal transition.

## Assignment retry boundary

A failed assignment remains immutable terminal history. If Scheduler requeues
the job and later creates a new lease, Persistent Runtime creates a new
assignment identity. It never restarts the failed assignment.

## Resource and employee projection

After Scheduler acknowledgement, Persistent Runtime marks the assignment
terminal. It clears the employee's work correlation only when
`current_assignment_id` still identifies that exact assignment. Resource state
is `released` only when
Scheduler reports successful release; otherwise it remains
`release-pending` for authority-owned reconciliation.

The local projection transaction also writes a durable terminal event intent.
Its stable identifier is `assignment-terminal:<transition_id>`. Delivery is
at-least-once and replay retains the same identifier so consumers can
deduplicate.

## Current contract form

The request body is the **provisional, service-local** contract
`leos.assignment-terminal-transition.v1` and contains:

- `transition_id`;
- optional cognitive run, cognitive attempt, and execution identifiers;
- a structured reason;
- optional failure retry delay.

This identifier is not canonical shared-contract authority. Consumers must not
independently freeze duplicate implementations of it. Exact shared JSON Schema
publication remains OPEN and should be completed with
the broader assignment-lifecycle contract. This prerequisite does not claim
that the complete assignment lifecycle vocabulary is finalized.
