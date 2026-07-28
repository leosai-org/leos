# Scheduler Target-Contract Adoption Conformance

## Status

Epic 8.4 adds an additive canonical adapter to the existing Execution
Scheduler. It does not replace Scheduler storage, queues, leases, resource
admission, retry timing, or terminal-transition behavior.

## Canonical adapter

`POST /v2/job-projections` accepts a Work Coordination scheduler projection
that contains a validated `leos.job-definition.v1` document plus source
lineage and evidence. The adapter creates exactly one Scheduler-owned Job for
one accepted idempotency scope.

Required evidence:

- Work Coordination scheduler-projection reference;
- source revision matching that projection reference;
- source Task reference;
- Organization reference;
- Actor Context reference;
- Authorization Decision reference;
- verified `leos.authorization-evidence-binding.v1`;
- idempotency key; and
- canonical Job contract version.

The adapter rejects caller-supplied authorization or approval booleans, raw
secret fields, direct Scheduler lifecycle mutation, lease-state mutation,
attempt-count mutation, direct not-before mutation, score/ranking/selection
fields, and Retry Intent requests that attempt to set Scheduler retry timing.

## Canonical view

`GET /v2/jobs/{job_id}/canonical` returns a canonical Job view only when the
Scheduler row contains complete canonical Job evidence. Legacy Scheduler rows
are returned as non-canonical compatibility records and are not mislabeled.

## Authority boundary

Work Coordination may request a projection; Scheduler alone owns the Job row,
queue state, lease state, resource admission/release, retry timing, attempt
count, and terminal Job transitions.

Resource-fit ordering is Scheduler worker/resource placement only. It is not
employee selection, ranking, or optimization authority.

## Authorization verification

Epic 8.6A requires `POST /v2/job-projections` to verify the supplied
Authorization Evidence Binding before accepting a canonical Job projection.
The protected operation mapping is:

- action: `scheduler.job-projection.accept`;
- resource: canonical `SCHEDULER_JOB` identity and revision;
- context type: `scheduler.job-projection`;
- context id: projection id;
- context revision: source projection revision; and
- context digest: deterministic digest over the operation, Organization ref,
  Scheduler Job ref, and source Scheduler projection ref.

The existing generic `ACTOR_CONTEXT` resource reference is compatibility
lineage only. The binding must contain canonical Actor Context evidence whose
`reference_id` and `revision` match that lineage reference.

Authorization Authority unavailability, timeout, denial, expiry, revocation,
wrong issuer, wrong Actor Context evidence, wrong action/resource/revision,
wrong Organization, wrong context, malformed response, or mismatched
verification evidence fails closed. The Scheduler does not issue decisions,
reinterpret Work Coordination's assignment decision, implement Approval, or
change Job/resource/lease authority.

## Compatibility and rollback

Existing `/jobs` APIs remain compatibility paths. New storage is additive:
canonical lineage columns and a projection idempotency table can be ignored or
removed without rewriting legacy Scheduler rows.
