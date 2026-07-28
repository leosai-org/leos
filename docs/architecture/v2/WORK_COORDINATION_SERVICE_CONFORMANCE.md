# Work Coordination Service Conformance

## Status

Epic 8.3 implements the accepted Epic 8.1 Work Coordination Service owner.
Epic 7.0 remains the historical Work Domain foundation: it introduced target
contracts and explicitly left production owners OPEN. Epic 8.1 accepted the
Dev Preview owner; Epic 8.3 implements that owner.

## Canonical ownership

Work Coordination Service owns:

- Work Request intake and lifecycle;
- Workflow Definition and immutable Workflow Revision lifecycle;
- Task, Dependency, Retry Intent, and Escalation Intent lifecycle;
- assignment decision and handoff records;
- same-Organization Delegation;
- Work Result acceptance;
- verification and closure records;
- audit history and its producer-local outbox.

It does not own Scheduler Jobs, leases, runtime Assignment projection,
Employee lifecycle, Organization lifecycle, authorization decisions, approval
grants, capability resolution, Dispatcher invocation, secrets, plugins/tools,
or event delivery.

## Required conformance

- Every authority-bearing mutation requires Actor Context evidence,
  revision-pinned Authorization Decision evidence, and a live
  Authorization Authority verification of
  `leos.authorization-evidence-binding.v1`.
- Caller-provided authorization or approval Booleans are rejected.
- Raw credentials and secret fields are rejected.
- Organization and Employee references are validated through narrow adapters
  and fail closed when evidence is unavailable.
- Scheduler projection and Persistent Runtime handoff are idempotent requests;
  neither writes foreign state directly.
- Published Workflow Revisions are immutable.
- Tasks may exist without Assignments and never schedule, invoke, approve, or
  authorize.
- Dependencies constrain readiness only.
- Assignment decisions do not authorize, execute, schedule, rank, optimize, or
  force assignee selection.
- Delegation is same-Organization only, preserves source responsibility, and
  cannot expand scope or transfer authority.
- Result acceptance is distinct from verification and closure.
- Verification is distinct from Approval.
- Closure preserves prior evidence and requires verification when required.
- Producer-local outbox records are transactional evidence, not Event Delivery
  authority.

## Authorization verification

Epic 8.6A makes structural references lineage-only for protected operations.
The canonical gate is live Authorization Authority verification of the exact
binding. Existing generic `ACTOR_CONTEXT` resource references remain accepted
only through an explicit compatibility adapter: the binding must contain the
canonical Actor Context evidence reference, and its `reference_id`/`revision`
must match the generic lineage reference.

Protected operation mappings:

| Operation | Action | Resource | Context |
| --- | --- | --- | --- |
| Create Work Domain record | `work-coordination.record.create` | created record identity and revision | `work-coordination.mutation` / `create:{resource_type}:{resource_id}` |
| Create bundle | `work-coordination.bundle.create` | Organization reference | `work-coordination.mutation` / deterministic bundle id |
| Update Work Domain record | `work-coordination.record.update` | current path identity at `expected_revision` | `work-coordination.mutation` / `update:{resource_type}:{resource_id}:{expected_revision}` |
| Lifecycle transition | `work-coordination.record.transition` | current path identity at `expected_revision` | `work-coordination.mutation` / `transition:{resource_type}:{resource_id}:{expected_revision}:{to_status}` |
| Assignment decision | `work-coordination.assignment-decision.create` | governed Work resource being assigned | `work-coordination.assignment-decision` / decision operation id |
| Runtime handoff request | `work-coordination.assignment-handoff.request` | governed Work resource from the assignment decision | `work-coordination.assignment-handoff` / handoff operation id |
| Scheduler projection request | `work-coordination.scheduler-projection.request` | source Task or Work Request | `work-coordination.scheduler-projection` / projection operation id |
| Verification record | `work-coordination.verification.create` | Work Result being verified | `work-coordination.verification` / verification operation id |
| Closure record | `work-coordination.closure.create` | Work subject being closed | `work-coordination.closure` / closure operation id |

Authorization Authority unavailability, timeout, denial, expiry, revocation,
wrong issuer, wrong Actor Context evidence, wrong action/resource/revision,
wrong Organization, wrong context, malformed response, or mismatched
verification evidence fails closed.

Work Coordination does not issue Authorization Decisions, infer subject from
Employee, requester, role, membership, assignment, or metadata, implement
Identity Authority, or implement Approval Authority.

Audit lineage is retained in record history for Work Domain records and in a
producer-local authorization verification audit table for internal operations.
