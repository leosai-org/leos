# Phase 52.1 — Runtime Resource Enforcement

## Status

Phase 52.1 makes the employee resource-profile service a mandatory runtime
authority. A scheduler job cannot receive a scheduler lease or transition to
`running` unless it has an active resource reservation for the same job and
employee.

## Enforced lifecycle

```text
queued job
→ employee resource profile
→ compute-node capacity synchronization
→ admission decision
→ resource reservation
→ scheduler lease
→ runtime start validation
→ execution
→ completion or failure
→ resource release
→ durable lifecycle history
```

## Fail-closed behavior

The scheduler does not execute a job when:

- the job has no `employee_id`;
- the resource authority is unavailable;
- compute-node synchronization fails;
- the admission decision is `queued`, `rejected`, or `preemption-required`;
- the selected resource node is not an available scheduler worker;
- the resource reservation is missing, expired, preempted, or released;
- the reservation belongs to a different job or employee.

Queued jobs remain unexecuted. Rejected decisions become terminal
`scheduler_jobs.state = rejected`.

## Durable state

The execution scheduler persists:

- admission decision;
- resource reservation ID;
- node ID;
- GPU UUID;
- selected profile;
- resource lifecycle state;
- admitted and released timestamps;
- release reason;
- enforcement errors;
- append-only resource lifecycle events.

The persistent employee runtime copies these fields into assignment history.

## Release and recovery

Resource reservations are released on:

- successful completion;
- job failure;
- scheduler lease expiration;
- scheduler lease commit failure;
- selected-node mismatch;
- invalid reservation reconciliation.

Each scheduling tick expires stale reservations, validates active jobs, recovers
jobs whose resource reservations are no longer active, and retries pending
releases. SQLite migrations are additive and idempotent, so resource lifecycle
state survives service restarts.

## API additions

Employee Resource Profile Service:

```text
GET  /reservations/by-job/{job_id}
POST /reservations/expire
```

Execution Scheduler:

```text
POST /resources/reconcile
GET  /jobs/{job_id}/resource
GET  /resource-history
```

## Security invariants

Phase 52.1 does not require:

- Docker socket access;
- privileged containers;
- host networking;
- production-network attachment during acceptance;
- direct production-state writes from development or acceptance tooling.
