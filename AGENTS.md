# LEOS Development

Current development target: LEOS 0.2.0 Developer Preview v2

## Authoritative v2 architecture

Read before implementation:

- `docs/architecture/v2/EXECUTION_PLANE.md`
- `docs/architecture/v2/EXECUTION_PLANE_DECISIONS.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE_DECISIONS.md`
- `docs/roadmap/DEV_PREVIEW_V2_GOALS.md` when present

If an implementation request conflicts with these documents, stop and report
the conflict. Do not silently change the architecture.

## Core principles

- User sovereignty.
- Local-first operation.
- Model/provider independence.
- User ranking is authoritative.
- Ranking establishes candidate order.
- Eligibility removes invalid candidates.
- The first remaining ranked candidate wins.
- Hard restrictions may eliminate but never reorder candidates.
- No silent provider/model substitution.
- No implicit emergency provider/model pool.
- Cloud execution requires explicit permission.
- Retry, re-resolution, and escalation are distinct operations.
- Real work occurs through governed capabilities and execution boundaries.

## Canonical responsibilities

- **Scheduler:** jobs, leases, and resource admission and release.
- **Persistent Employee Runtime:** durable employee and assignment state,
  mailbox, and durable working-state storage.
- **Employee Cognitive Service:** reasoning lifecycle, per-run context
  assembly, and reason/act/observe behavior.
- **Capability Manager:** canonical provider inventory, provider-capability
  bindings, eligibility evaluation, and first-ranked-valid resolution; no
  provider invocation.
- **Model Registry:** canonical model facts and model-provider/runtime
  bindings.
- **Execution Dispatcher:** sole governed invocation authority, execution
  audit, and same-target safe retry; no provider/model selection.
- **AI Router / adapters:** physical transport and protocol compatibility only;
  no ranking, substitution, or independent escalation.
- **Runtime Execution Coordinator:** observation and await only.

## Source authority

`leos-v2` is the sole writable v2 source authority.

`lucy-runtime-reference` is immutable evidence and implementation donor
material. Never modify Lucy reference files.

Existing Lucy implementations must be inspected and deliberately promoted,
adapted, or retired rather than blindly copied or rewritten.

## Development rules

- Inspect existing implementation before creating a new service.
- Do not create parallel authorities.
- Prefer canonical implementation over duplication.
- Do not introduce temporary compatibility hacks unless explicitly approved.
- Make contract changes explicit.
- Add or update tests for behavioral changes.
- Prefer deterministic behavior.
- Make retries idempotency-aware.
- Never place credentials or secret values in source, fixtures, tests,
  documentation, logs, prompts, events, or memory.
- Preserve correlation and auditability across service boundaries.
- Do not modify public/release authority merely to make development easier.

## Frozen/public release authority

Do not modify RC11 release authority unless explicitly instructed, including:

- `manifest.json`
- `source.lock.json`
- `contracts.lock.json`
- `checksums.sha256`
- RC11 release/governance artifacts

## Before completing implementation work

Always:

- run relevant tests;
- run `git diff --check`;
- report files changed;
- report API/contract changes;
- report migrations;
- report unresolved issues;
- show `git diff --stat`.

Do not commit unless explicitly instructed.
