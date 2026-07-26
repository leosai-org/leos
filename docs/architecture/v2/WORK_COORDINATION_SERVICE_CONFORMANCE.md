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

- Every mutation requires Actor Context evidence and revision-pinned
  Authorization Decision evidence.
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
