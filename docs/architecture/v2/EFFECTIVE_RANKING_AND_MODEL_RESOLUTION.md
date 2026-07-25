# LEOS v2 Effective Ranking and Governed Model Resolution

## Authority

Ranking Policy Authority is canonical for explicit user-authored provider and
model order, the four ranking scopes, effective-ranking derivation, revisions,
and mutation audit. It does not own inventory, eligibility, availability,
execution, endpoints, scoring, benchmarking, or fallback.

Capability Manager remains the final governed resolution authority. Model
Registry supplies model and runtime-binding facts through its API. Dispatcher
continues to invoke only a resolved target and is unchanged by this phase.

## Independent dimensions and scopes

Provider rankings contain stable provider IDs. Model rankings contain stable
model IDs. The dimensions are stored and derived independently.

For each dimension, the most-specific active defined ranking replaces every
less-specific ranking:

```text
job > employee > capability > global
```

A defined ranking is a non-empty exact list of unique IDs. Missing or inactive
records inherit. Empty lists are invalid; they mean neither inheritance nor
deny-all. Explicit deny-all requires a future distinct policy.

No lower-scope candidates are merged or appended. If a job provider ranking
exists while only an employee model ranking exists, those are the effective
provider and model rankings respectively.

## Ranking and eligibility

Ranking establishes order. Capability Manager applies hard eligibility using
canonical provider, capability, model, binding, availability-policy, and
approval facts. Eligibility may remove candidates but cannot reorder those
remaining. Defined lists exclude unlisted inventory. An undefined dimension
supplies no order and never implies alphabetical or database order.

Model-aware candidates are the combination of provider identity, model
identity, and one model-runtime binding. Provider endpoint authority remains
in Capability Manager; Model Registry does not copy or own endpoints.

## Two-dimensional ordering

For every candidate, Capability Manager determines its position in each
defined dimension. Candidate A dominates B only when A is no worse than B in
every defined dimension and strictly better in at least one.

A unique non-dominated eligible candidate resolves. Multiple non-dominated
candidates are a real missing-policy condition and produce
`GOVERNED_ORDER_REQUIRED`. LEOS does not use rank sums, weights, scores,
provider-first or model-first ordering, benchmarks, availability, locality,
metadata, timestamps, insertion order, or identifier spelling as a tie
breaker.

With no defined dimension, one eligible candidate may resolve, zero produces
the canonical no-eligible outcome, and multiple candidates require governed
order. With only one dimension, candidates tied in it remain unordered.

## Approval

Ordering is established before approval can authorize invocation. If the one
uniquely governed best candidate requires approval and no trusted verified
grant exists, the result is `APPROVAL_PENDING`; lower candidates are not
silently selected. Caller-provided approval references remain opaque audit
references and do not themselves authorize.

## Contracts and target evidence

The canonical cross-service contracts are:

- `leos.effective-ranking-request.v1`;
- `leos.effective-ranking-result.v1`;
- backward-compatible model-aware additions to capability resolution.

Ranking CRUD records use
`ranking-policy.record.provisional-v1` as a service-local representation.
No other authority consumes that complete persistence-oriented record, so it
is deliberately not a shared canonical contract.

`leos.effective-ranking-request.v1` is produced by Capability Manager and
consumed by Ranking Policy Authority. It is shared because it carries the
cross-authority scope context used to derive ordering. The corresponding
`leos.effective-ranking-result.v1` is produced by Ranking Policy Authority and
consumed by Capability Manager. It is shared because it is the governed
ordering evidence used by the separate resolution authority. Neither contract
publishes Ranking Authority storage internals.

A model-aware resolved target records provider identity and inventory
revision, model identity and revision, runtime-binding identity and revision,
runtime type, and runtime-native model reference. The resolution references
effective ranking evidence rather than copying ranking storage internals.

Ranking writes use deterministic content revisions and
`expected_revision` compare-and-swap. Identical replay causes no revision or
event churn. One record exists per dimension and scope identity.

References are syntax-validated when authored. They are deliberately not
synchronously verified against every owning service, avoiding an
all-services-online write path. Capability Manager verifies current provider,
model, and binding facts during resolution. Freshness and long-running-job
revision pinning remain **OPEN**.

Capability Manager obtains model and binding facts only through Model
Registry's HTTP API; it never reads Model Registry storage. The reads from
Ranking Authority, Model Registry, and Capability Manager inventory are not an
atomic distributed snapshot. A resolution preserves the exact provider,
model, binding, and ranking revisions actually used. A later mutation does not
rewrite that evidence. Freshness reconciliation, snapshot validity windows,
and re-resolution policy remain **OPEN**; this Epic adds no hidden retry.

## Legacy authority disposition

Lucy Provider Registry score-based selection is rejected. Its provider facts
are migration input only. Employee Registry/Builder and Resource Profile
preference-shaped data are future migration inputs, not ranking authorities.
First Run may later create governed initial records after canonical inventory
registration.

Lucy AI Router default models, fallback models, and exception-triggered
substitution remain legacy runtime debt. The Router is transport-only and is
not activated in this Epic.

## Remaining work

**OPEN:** Observation freshness policy, explicit deny-all policy, restriction
contracts, approval verification, policy pinning and integrity, First Run
registration workflow, migration adapters for legacy employee preferences,
and physical local-model transport (including Qwen/Ollama).
