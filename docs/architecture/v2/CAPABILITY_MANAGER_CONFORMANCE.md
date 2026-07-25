# Capability Manager v2 conformance

## Canonical responsibility

Capability Manager is authoritative for provider and capability inventory,
provider-capability bindings, governed eligibility evaluation,
first-ranked-valid selection, and canonical resolution audit.

It does not invoke providers, adapt payloads, own execution history, or own
model-provider/runtime bindings.

## Canonical API

Inventory APIs remain:

- `GET /health`
- `POST /providers`
- `GET /providers`
- `POST /capabilities`
- `GET /capabilities`
- `POST /bindings`
- `POST /providers/register-bundle`

Resolution APIs are:

- `POST /resolve`, accepting
  `leos.capability-resolution-request.v1` and returning
  `leos.capability-resolution-result.v1`;
- `GET /resolutions/{resolution_id}`;
- `GET /resolutions`.

Input is validated before resolution. Output is validated before persistence
and return. Persisted results are validated when retrieved.

The following donor APIs were removed rather than retained as compatibility
authorities:

- `POST /execute`;
- execution-history APIs;
- payload-adapter and execution-contract APIs.

The current Dispatcher still emits its donor resolution request shape. Its
canonical request integration is deferred to Epic 1.2C; Capability Manager
does not weaken `/resolve` to conceal that incompatibility.

## Candidate ordering and eligibility

The optional canonical constraint
`constraints.provider_preference_order` carries ordered generic provider IDs
for this phase. It is not the future intelligence-ranking contract. Supplied
IDs are evaluated in their exact order. Providers omitted from an explicit
list are not appended or considered implicitly.

Without governed ordering, Capability Manager evaluates bound providers for
eligibility but does not use provider identifier spelling as policy. Exactly
one eligible provider may be selected. Zero eligible providers produces
`NO_ELIGIBLE_PROVIDER`. If multiple providers remain eligible, Capability
Manager returns `GOVERNED_ORDER_REQUIRED`, keeps those candidates marked
`ELIGIBLE`, returns no selected target, and authorizes no invocation.
Provider-ID ordering may be used only to make audit presentation
deterministic; it never selects a target.

Provider priority, trust, and health are not combined into a score. Candidate
order is never changed by eligibility.

Current hard eligibility facts are:

- provider administrative `status` must be `active`;
- binding `enabled` must be true;
- observed provider health must not be `unhealthy`;
- binding approval policy must not be `denied`;
- approval-required candidates need at least one governed approval-grant
  reference.

Unknown and degraded health remain eligible in this phase because the
repository has no adopted health freshness or degraded-state policy.
Permissions, trust level, risk level, and other metadata are retained facts
but do not create invented permission or governance behavior.

If the highest-ranked otherwise-eligible candidate requires approval and the
request has no governed approval reference, the result is
`APPROVAL_PENDING`; lower candidates are not evaluated. Caller-supplied
approval Booleans are rejected. Caller-supplied grant references are accepted
as opaque correlation and audit evidence, but their existence does not
authorize a candidate. Because no trusted approval verifier exists in this
phase, an approval-required candidate remains `APPROVAL_PENDING` even when
such references are supplied. Future approval integration may convert a grant
into eligibility only after trusted verification, scope matching, validity,
expiry, and revocation checks.

## Non-destructive database transition

V2 creates `canonical_resolutions` for complete validated request/result audit
and `capability_manager_schema` for migration state. Provider, capability,
binding, and inventory-event tables remain canonical service state.

Existing donor databases are migrated non-destructively. If present, these
legacy tables are retained without canonical APIs or new writes:

- `resolutions`;
- `executions`;
- `provider_payload_adapters`.

Fresh v2 databases do not create those legacy tables. They may be removed only
by a later explicit destructive migration after retention and rollback policy
is approved.

Canonical resolution rows retain request identity, capability, requester,
correlation, evaluated candidates, selected provider where applicable,
rationale, status, and timestamps. Raw credential-shaped fields are rejected
from governed resolution constraints and inventory metadata before
persistence.

## Dispatcher and model boundaries

Dispatcher consumes the canonical resolution, adapts and invokes the selected
target, and owns execution attempts and results. Capability Manager target
records contain opaque provider target references, not invocation behavior.

Future intelligence resolution may supply an effective ranking policy and
consume Model Registry facts. Capability Manager does not implement that
policy or absorb Model Registry authority in this phase.
