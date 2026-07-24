# LEOS v2 Execution Contract Foundation

## Purpose

This package establishes the first machine-readable contracts for the LEOS
0.2.0 Developer Preview v2 execution path. It is subordinate to the execution-
and intelligence-plane architecture documents and does not change service
behavior.

The contracts cover:

- the canonical request accepted by Execution Dispatcher;
- the request and durable result of Capability Manager resolution;
- the normalized result returned and audited by Execution Dispatcher;
- reusable execution-plane correlation.

## Authority boundaries

Employee Cognitive Service creates a complete execution request but does not
select a provider. Execution Dispatcher requests resolution, authorizes and
records invocation, and normalizes the result. Capability Manager evaluates
eligibility and returns a durable resolution; it does not invoke. A Router,
adapter, or provider may physically transmit or perform only the authorized
target operation.

The normal interaction is:

```text
Cognitive Service -> Dispatcher : execution request
Dispatcher -> Capability Manager : resolution request
Capability Manager -> Dispatcher : durable resolution
Dispatcher -> Router / Adapter / Provider : authorized invocation
Dispatcher -> Cognitive Service : normalized execution result
```

## Contract inventory

| Contract ID | Schema | Authority or producer |
|---|---|---|
| `leos.execution.v1` | `contracts/execution.v1.schema.json` | Governed caller; validated by Dispatcher |
| `leos.execution-correlation.v1` | `contracts/execution-correlation.v1.schema.json` | Identifier-owning authorities |
| `leos.capability-resolution-request.v1` | `contracts/capability-resolution-request.v1.schema.json` | Dispatcher |
| `leos.capability-resolution-result.v1` | `contracts/capability-resolution-result.v1.schema.json` | Capability Manager |
| `leos.execution-result.v1` | `contracts/execution-result.v1.schema.json` | Execution Dispatcher |

All top-level objects are closed. Contract versions are exact constants.
Identifiers in the correlation object are optional except for its contract
version, so services omit unknown identifiers rather than inventing them.

## Validation levels

Canonical validation has two required levels:

1. **JSON Schema validation** checks structure, types, required fields,
   conditional fields, closed authority-bearing objects, and contract versions.
2. **Semantic contract validation** checks relationships between fields and
   ordered records that Draft 2020-12 cannot reasonably express.

An object is canonically valid only when it passes both levels. “Schema valid”
does not mean “semantically valid.” The deterministic reference checks are
implemented by the canonical runtime validator in `packages/leos-contracts/`.
Contract tests consume that shared validator. Epic 1.2 implementations must
enforce equivalent behavior at their service boundaries.

Semantic validation requires:

- parent `execution_id` and correlation `execution_id` to match when both
  exist;
- parent `resolution_id` and correlation `resolution_id` to match when both
  exist;
- execution-result resolution reference and correlation resolution ID to
  match when both exist;
- candidate positions to be unique and represented in ascending evaluation
  order;
- the selected target to appear exactly once, be `ELIGIBLE`, and be the first
  `ELIGIBLE` candidate;
- attempt count to equal the number of attempt records;
- invocation-attempt identifiers and attempt numbers to be unique, with
  attempts represented in ascending number order;
- every contract date-time to be a timezone-qualified RFC3339 value;
- reserved approval-Boolean shortcuts to be rejected throughout
  authority-bearing policy and constraint structures.

Optional correlation identifiers remain optional. Equality is enforced only
when both copies exist.

## Resolution and invocation

A resolution outcome is `RESOLVED`, `APPROVAL_PENDING`, or
`NO_ELIGIBLE_PROVIDER`. Only `RESOLVED` carries a selected target.
`APPROVAL_PENDING` carries an external approval-requirement reference and does
not silently select a lower-ranked candidate.

Candidate positions and eligibility outcomes may be recorded, but these
contracts do not define candidate ranking. User-governed effective ranking is
referenced through an extension point for a future intelligence-policy
contract. Candidate positions preserve that supplied order; they are not
scores. Rejected and approval-required candidates carry at least one reason.
For a resolved outcome, the selected provider is the first eligible candidate
in ascending evaluation order.

Dispatcher transport retry remains limited to the same authorized target.
Provider/model re-resolution, model escalation, and validation-triggered
escalation are separate and are not implemented by these schemas.

## Normalized outcomes

The execution-result statuses distinguish:

- `SUCCESS`;
- `REJECTED`;
- `PROVIDER_ERROR`;
- `TRANSPORT_ERROR`;
- `AMBIGUOUS_OUTCOME`;
- `APPROVAL_PENDING`.

Attempt records identify concrete invocation attempts. Structured errors state
whether same-target retry is potentially allowed and whether a remote side
effect may have occurred. These fields carry facts for later policy; they do
not implement retry.

`APPROVAL_PENDING` and `REJECTED` are non-invoked outcomes. They have no
authorized target, zero attempts, and no provider-operation evidence.
`APPROVAL_PENDING` additionally requires an external approval-requirement
reference. `AMBIGUOUS_OUTCOME` requires
`remote_side_effect_possible: true`; it exists only when LEOS cannot safely
prove that the remote operation did not occur.

## Deferred contracts

This foundation intentionally does not define:

- intelligence-ranking content or precedence encoding;
- approval grants, issuance, verification, revocation, or delegation;
- secret resolution or credential injection;
- resolution integrity, expiry, or revalidation rules;
- retry and escalation policy or failure taxonomy;
- provider request/response adaptation;
- raw provider audit storage.

Approval and intelligence policy are represented only by opaque governed
references. Provider credentials, when needed, are likewise represented only
by opaque references. Caller-supplied approval Booleans are never approval
evidence. The reserved compatibility names `allow_approval_required`,
`approval_granted`, `approved`, and `has_approval` are invalid in
authority-bearing policy or constraint structures.

Raw credential fields are forbidden in governed authority and configuration
structures. Arbitrary capability input, context, normalized result, and
provider-response data may legitimately contain business fields whose names
include words such as `token` or `key`; those payloads remain subject to their
capability contracts and runtime secret-redaction controls. The execution
contract does not treat such field names as credential authority.

## Lucy compatibility and migration

`leos.execution.v1` preserves the demonstrated Lucy Dispatcher envelope:
contract version, execution ID, capability ID, requester, input, context,
policy, and trace/correlation.

Migration requires adaptation for Lucy callers that use:

- separate `requester_type` and `requester_id` fields;
- `capability` instead of `capability_id`;
- direct provider selection;
- score-based resolution;
- caller-supplied approval Booleans;
- Capability Manager `/execute`;
- raw provider responses as the only result shape.

Those behaviors are evidence, not canonical v2 authority. No existing frozen
contract or executable service is changed by this package.
