# Authorization Authority Conformance

Epic 8.5 implements the Dev Preview v2 production Authorization Authority.

## Canonical ownership

Authorization Authority owns:

- Authorization Decision records;
- capability permission grants;
- decision verification;
- decision revocation;
- grant revocation;
- expiration handling;
- authorization decision lineage;
- Dev Preview policy evaluation over authority-owned grants;
- producer-local authorization outbox records.

Authorization Authority does not own identity, authentication, Actor Context
issuance, approval, Organization resources, Employees, Teams, Roles,
Membership, Work, Jobs, Assignments, scheduling, runtime lifecycle, Dispatcher
invocation, capability resolution, plugin/tool lifecycle, secrets, or event
delivery.

## API conformance

The service exposes:

- `POST /authorization-decisions`
- `GET /authorization-decisions`
- `GET /authorization-decisions/{decision_id}`
- `POST /authorization-decisions/{decision_id}/verify`
- `POST /authorization-decisions/{decision_id}/revoke`
- `POST /capability-permission-grants`
- `GET /capability-permission-grants`
- `GET /capability-permission-grants/{grant_id}`
- `POST /capability-permission-grants/{grant_id}/revoke`
- `GET /outbox`
- `GET /health`
- `GET /ready`
- `GET /version`

Authorization Decisions are emitted as canonical
`leos.authorization-decision.v1` records. Capability permission grants are
Dev Preview service records until a future canonical grant contract is accepted.

## Evaluation semantics

Decision creation evaluates the requested subject/action/resource/context
against active authority-owned capability permission grants.

- Missing grant: `DENY`.
- Expired grant: `DENY`.
- Revoked grant: `DENY`.
- Wrong subject, action, resource, capability, Organization, or revision:
  `DENY`.
- Exact active grant match: `ALLOW`.

Every decision is revision-pinned, time-bounded, idempotent, persisted, and
auditable. `ALLOW` decisions include grant evidence. `DENY` decisions include
explicit reasons.

## Verification semantics

Verification succeeds only for a stored Authorization Decision issued by this
service where:

- the stored decision is unexpired;
- the stored decision is not revoked;
- the supplied Organization matches the stored Organization;
- the expected scope exactly matches the stored scope;
- the expected decision matches the stored decision;
- the stored authority is the Authorization Authority.

Client-provided Authorization Decision JSON is rejected. A structurally valid
contract document is evidence shape only and never self-authorizes.

Epic 8.6.0 adds `leos.authorization-evidence-binding.v1` as the canonical
verification input shape for later consumers. The binding carries the expected
decision reference, Actor Context evidence reference, Organization reference,
scope, and expected outcome. It does not authorize by itself and does not
replace this service's live verification.

## Persistence and outbox

SQLite tables persist:

- capability permission grants;
- Authorization Decisions;
- revocations;
- idempotency keys;
- producer-local authorization outbox records.

State changes, revocation records, idempotency records, and outbox writes are
committed in the same SQLite transaction for each mutation. The outbox is
producer-local only and does not become Event Delivery authority.

## Security boundaries

The service rejects:

- caller authorization booleans;
- caller approval booleans;
- role-as-permission shortcuts;
- membership-as-permission shortcuts;
- capability-presence-as-permission shortcuts;
- plugin-installation-as-permission shortcuts;
- malformed actor references;
- malformed Organization/resource/action scope;
- raw secrets or credential values;
- client-issued Authorization Decision documents.

Roles, Membership, capability inventory, Plugin installation, Approval, and
Assignment are policy inputs or separate authority evidence only; none is
permission by itself.

## Deferred work

OPEN for later epics:

- production Identity Authority and trusted Actor Context verification;
- advanced policy language and policy-pack lifecycle;
- delegated grant policy and inheritance;
- Organization/team policy inheritance;
- consumer migration in Organization, Work Coordination, Capability Manager,
  Dispatcher, Scheduler, Runtime, and other services;
- Event Delivery ingestion of authorization outbox records.
