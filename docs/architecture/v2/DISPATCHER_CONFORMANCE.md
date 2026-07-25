# Execution Dispatcher v2 conformance

## Canonical authority

Execution Dispatcher is the sole governed provider and tool invocation
authority. It validates canonical execution requests, obtains and validates a
Capability Manager resolution, invokes only the resolved target, normalizes
the outcome, and owns invocation attempts and execution audit.

It does not rank, select, substitute, fail over, re-resolve, grant approval,
resolve secrets, or own provider/model inventory.

## Request boundary

`POST /execute` accepts only `leos.execution.v1`. The shared
`leos-contracts` validator runs before resolution or invocation. Malformed
requests receive an API contract-validation error; they are not converted to
canonical `REJECTED` results.

The remaining canonical read and administration surface is:

- `GET /health`;
- `GET /contract`;
- `POST /execute`;
- `GET /executions/{execution_id}`;
- `GET /executions`;
- `GET /adapters`.

Public mutable adapter administration is disabled until a trusted
control-plane authorization boundary exists. Deployment-provisioned adapters
remain transport-shaping facts and provide no ranking or resolution authority.

## Resolution handoff

Dispatcher constructs `leos.capability-resolution-request.v1` with the
capability, requester, correlation, and the policy fields that have exact
counterparts in the current resolution request contract:

- `effective_intelligence_policy_ref`;
- `approval_grant_refs`.

The execution idempotency key remains invocation policy and is not sent as a
resolution selector. The current execution request has no canonical capability
constraints field, so Dispatcher sends an empty constraints object rather
than deriving an ad hoc selector. In particular, it sends neither the donor
`provider_id` nor `preferred_provider_id`.

Capability Manager's response is validated as
`leos.capability-resolution-result.v1`. Dispatcher also verifies that its
capability, requester, and execution correlation match the submitted
execution.

For a resolved target, the provider endpoint is materialized read-only from
Capability Manager provider inventory. The inventory record must match the
exact selected provider id, target reference, and referenced revision. This
lookup does not evaluate candidates or select a provider.
For `RESOLVED`, that revision is mandatory. A missing or stale revision is a
control-plane failure, never identifier-based authority to use newer inventory
or silently re-resolve.

## Resolution-status mapping

| Resolution status | Dispatcher behavior | Execution status |
|---|---|---|
| `RESOLVED` | Materialize and invoke only the selected target | Provider outcome |
| `APPROVAL_PENDING` | Zero attempts; no target or invocation | `APPROVAL_PENDING` |
| `NO_ELIGIBLE_PROVIDER` | Zero attempts; no target or invocation | `NO_ELIGIBLE_PROVIDER` |
| `GOVERNED_ORDER_REQUIRED` | Zero attempts; no target or invocation | `GOVERNED_ORDER_REQUIRED` |

Dispatcher preserves these non-selection decisions and does not reinterpret
them.

## Invocation and adapter authority

Only `RESOLVED` reaches invocation. Dispatcher verifies the selected target,
chooses payload shaping without changing provider identity, constructs the
provider URL from the matching inventory record, records an invocation
attempt, transmits the request, and normalizes the result.

Supported request shapes are:

- `canonical_envelope` / `leos_execution_v1`;
- `flat_input`.

The donor `legacy_wrapped` shape is not part of the canonical surface. If a
resolution names an adapter, that exact enabled adapter must apply to the
resolved provider and capability. Dispatcher does not fall back to a
differently scoped adapter in that case. Without a named adapter, deterministic
adapter lookup affects shaping only; its provider id remains pinned to the
resolved target.

## Retry and idempotency

Retry, re-resolution, failover, and escalation are distinct. Dispatcher never
calls Capability Manager again during an invocation retry and never changes
the resolved provider or URL.

Automatic provider retry is disabled in Epic 1.2C because no governed
execution-policy authority evaluates `execution_policy_ref`. An idempotency
key and adapter declarations may demonstrate retry capability, but retry
capability is not retry authority. Adapter metadata cannot authorize execution
or retry. Future same-target retry requires explicit governed policy and must
not re-resolve, fail over, or escalate.

## Ambiguous outcomes and normalization

Canonical normalized results are:

- `SUCCESS` for a successful provider response;
- `TRANSPORT_ERROR` when connection failure proves transmission did not
  occur;
- `AMBIGUOUS_OUTCOME` when LEOS cannot prove whether the remote operation
  occurred;
- `REJECTED` for a governed post-resolution pre-invocation refusal.

`AMBIGUOUS_OUTCOME` always records
`remote_side_effect_possible: true` and is not automatically retried.
Absent an authoritative provider-operation profile, every non-2xx response is
ambiguous because HTTP status cannot prove the absence of remote effects.
`PROVIDER_ERROR` remains canonical but generic transport handling does not emit
it in this phase. Only HTTPX `ConnectError` and `ConnectTimeout` are treated as
conclusively pre-transmission; other request failures are ambiguous.
Non-JSON provider success is normalized to content plus media type rather than
returned as the donor raw-result envelope.

## Approval and secrets

Dispatcher neither grants nor verifies approval. A Capability Manager
`APPROVAL_PENDING` result is preserved with zero attempts.

Secret Manager and governed credential injection are deferred. A selected
target carrying a credential reference is returned as a pre-invocation
`REJECTED` result with `credential_boundary_unavailable`; Dispatcher does not
invent environment-variable or inline-secret authentication. Persisted
request, outbound, result, and raw-provider audit documents are recursively
redacted for unambiguous credential-bearing keys. Generic business fields
named `token`, `key`, or `secret` are preserved as capability evidence and do
not become execution authority; adapter configuration continues to prohibit
those names because it is an authority-bearing control-plane structure.

## Persistence transition

The canonical schema adds:

- `dispatcher_schema`, recording migration state;
- `canonical_executions`, containing canonical request, resolution, selected
  target, safe outbound evidence, attempts, canonical result, safe provider
  evidence, timestamps, and correlation;
- `execution_claims`, containing the request fingerprint and `CLAIMED`,
  `IN_FLIGHT`, or `COMPLETED` lifecycle;
- `canonical_invocation_attempts`, containing one durable journal row per
  concrete attempt.

Persistence is validated before writing, and canonical results are validated
again when read.
The claim, safe outbound evidence, and `IN_FLIGHT` attempt are committed before
transmission. An orphaned `IN_FLIGHT` attempt recovers conservatively as
`AMBIGUOUS_OUTCOME` and is never retransmitted automatically. A completed
duplicate with the same fingerprint returns its canonical result; a different
fingerprint conflicts; an active duplicate never starts another invocation.
Separate Dispatcher databases do not share execution identity authority.

Pre-transmission control-plane failures release a `CLAIMED` execution for safe
resubmission. They remain API failures rather than canonical `REJECTED`.

Existing donor state is non-destructive:

| Donor state | Classification |
|---|---|
| `provider_adapters` | Retained canonical transport-adaptation state |
| `executions` | Legacy read-only |
| donor envelope/result columns | Superseded |
| legacy table after a governed retention window | Future-removal candidate |

Startup never drops or rewrites donor execution rows.

## Donor behavior removed

Epic 1.2C removes:

- optional `capability` in place of `capability_id`;
- split `requester_type` / `requester_id`;
- optional generated execution identifiers;
- caller-selected `provider_id`;
- the `provider_id` / `preferred_provider_id` resolution mismatch;
- unvalidated donor resolution and provider envelopes;
- raw provider output as the canonical API result;
- unconditional retry of exceptions and HTTP 5xx;
- the `legacy_wrapped` default;
- writes to the donor `executions` table.

Git history and the Epic 1.2A baseline tests remain the donor evidence.

## Remaining debt

- A governed provider endpoint/transport-profile contract should replace the
  current exact provider-inventory materialization step.
- Adapter and idempotency declarations need canonical contracts and revisions.
- Governed execution-policy evaluation is required before retry can return.
- Trusted authorization is required before mutable adapter administration can
  return.
- Provider-operation profiles are required before generic non-2xx responses
  can be conclusively classified as `PROVIDER_ERROR`.
- Resolution integrity, expiry, and revalidation remain open.
- Secret Manager integration and credential injection remain deferred.
- Cancellation and provider-operation reconciliation are not implemented.
- Resolution transport failure currently produces an API failure because no
  canonical execution result can truthfully carry a missing resolution
  reference.
- Retention and removal policy for legacy Dispatcher rows remains open.
