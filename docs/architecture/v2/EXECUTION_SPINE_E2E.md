# LEOS v2 Governed Execution Spine E2E

## Purpose

Epic 1.2E provides a disposable real-HTTP proof of the canonical execution
spine. It verifies that the independently tested execution-plane services can
complete one governed synthetic assignment without bypassing their authority
boundaries.

The proof covers execution mechanics only. It does not exercise model
selection, AI Router transport, an LLM, approval verification, production
credentials, or the Intelligence Plane.

## Services under test

The Compose stack in `tests/e2e/epic_1_2e/` runs:

- Employee Resource Profile Service;
- Execution Scheduler;
- Persistent Employee Runtime;
- Employee Cognitive Service;
- Execution Dispatcher;
- Capability Manager;
- a deterministic synthetic provider;
- a standard-library test runner.

Each stateful service uses isolated `tmpfs` storage. Automatic scheduling,
Runtime polling, and Cognitive polling are disabled so that the test can
advance each supported service boundary explicitly and deterministically.
The unavailable Kernel event sink is non-authoritative for this proof;
Scheduler lifecycle state remains durable in Scheduler storage.

## Governed path

The test bootstraps an employee and resource profile through their public
HTTP APIs, registers one synthetic capability/provider/binding bundle through
Capability Manager, and creates a Scheduler job. It then exercises:

```text
Scheduler job and resource admission
  -> Scheduler lease
  -> Persistent Runtime scheduler synchronization and assignment projection
  -> Cognitive assignment discovery, start, and context assembly
  -> canonical leos.execution.v1 request
  -> Dispatcher
  -> Capability Manager /resolve
  -> immutable authorized target revision
  -> Dispatcher invocation attempt
  -> synthetic provider
  -> canonical leos.execution-result.v1 SUCCESS
  -> Cognitive observation and saved terminal intent
  -> Persistent Runtime terminal transition
  -> Scheduler completion and resource release
```

Cognitive Service does not contact Capability Manager, Scheduler, or the
provider. Dispatcher is the only caller that resolves and invokes the
capability. The test runner never invokes the provider directly.

## Assertions

The successful-path test verifies:

- the job is `complete`, its original lease is inactive, and its reservation
  is released with reason `job-complete`;
- the assignment is `complete`, the employee is `idle`, and
  `current_assignment_id` is cleared;
- exactly one Cognitive run, Cognitive attempt, execution, resolution,
  Dispatcher invocation attempt, provider operation, and terminal transition
  exist;
- the request and result retain the Cognitive-owned execution ID;
- Capability Manager resolves the single eligible provider without adding
  ranking, scoring, failover, or substitution authority;
- Dispatcher verifies the selected provider's immutable inventory revision
  and returns canonical `SUCCESS`;
- Cognitive persists and applies one success observation and invokes only the
  Persistent Runtime completion boundary;
- the deterministic provider is invoked exactly once.

The duplicate guard then performs additional supported Scheduler ticks,
Runtime synchronizations, and Cognitive ticks. It asserts that no second
lease, assignment, Cognitive run or attempt, execution, resolution, provider
invocation, or terminal transition is created.

## Correlation evidence

The proof preserves the identifiers that are truthfully available across the
participating services:

- `job_id`;
- `lease_id`;
- `assignment_id`;
- `employee_id`;
- `cognitive_run_id`;
- `cognitive_attempt_id`;
- `execution_id`;
- `resolution_id`;
- `invocation_attempt_id`;
- `terminal_transition_id`;
- `provider_id`;
- immutable provider revision.

The disposable test runner writes its complete observed state and correlation
lineage to `/tmp/epic-1.2e-evidence.json` inside the container. This evidence
is diagnostic output, not a new authority or repository fixture.

## Running the proof

From the repository root:

```bash
docker compose \
  -f tests/e2e/epic_1_2e/compose.yaml \
  up --build --abort-on-container-exit --exit-code-from e2e-test

docker compose \
  -f tests/e2e/epic_1_2e/compose.yaml \
  down --volumes --remove-orphans
```

A determinism check requires running both commands twice. Each `up` must
follow a completed `down --volumes --remove-orphans` so no service state is
reused.

## Scope and limitations

This proof establishes that the current synthetic success path is internally
coherent. It does not establish production readiness for failure,
cancellation, approval, retry, ambiguous-outcome, multiple-provider,
provider-health, secret-resolution, model-runtime, or crash-recovery paths.
Those require their own governed scenarios and tests.
