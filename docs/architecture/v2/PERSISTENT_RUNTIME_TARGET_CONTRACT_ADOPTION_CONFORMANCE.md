# Persistent Runtime Target-Contract Adoption Conformance

## Status

Epic 8.4 adds an additive canonical Assignment handoff adapter to the existing
Persistent Employee Runtime. It does not replace runtime employee presence,
mailbox, working state, assignment terminal transitions, or Scheduler
terminal bridge behavior.

## Canonical handoff adapter

`POST /v2/assignment-handoffs` accepts a Work Coordination handoff that
contains a validated `leos.work-assignment.v1` document plus source lineage
and evidence. Runtime acceptance is explicit: a Work Coordination assignment
decision, Scheduler Job, Scheduler lease, caller Boolean, Team membership,
Role, capability declaration, or Employee Registry resolution is never enough
by itself.

Required evidence:

- Work Coordination assignment-handoff reference;
- source revision matching that handoff reference;
- assignment-decision evidence reference;
- source Task reference;
- Scheduler Job reference;
- Employee reference;
- Organization reference;
- Actor Context reference;
- Authorization Decision reference;
- idempotency key; and
- canonical Assignment contract version.

The adapter rejects caller-supplied authorization or approval booleans, raw
secret fields, direct runtime lifecycle/terminal state mutation, Scheduler
lease evidence as acceptance, capability-resolution evidence as permission,
Dispatcher invocation requests, scoring, ranking, force, and optimization.

## Canonical view

`GET /v2/assignments/{assignment_id}/canonical` returns a canonical Assignment
view only when the Runtime row contains complete canonical Assignment
evidence. Legacy Scheduler-sync rows are explicitly reported as non-canonical
compatibility records.

## Scheduler sync compatibility

`POST /scheduler/sync` remains a legacy compatibility path. It may still
create legacy assignment rows from legacy Scheduler Jobs. For canonical
Scheduler projection rows, it must not create a canonical Assignment from a
Scheduler row alone; it may only enrich an existing canonical handoff-created
Runtime projection with Scheduler lease/resource evidence.

## Authority boundary

Work Coordination owns assignment decisions and handoff records. Persistent
Runtime owns runtime Assignment acceptance, projection, lifecycle, and
terminal transitions after accepted handoff. Scheduler owns Job, lease,
resource, and retry timing state. Approval and Authorization remain separate.

## Compatibility and rollback

Existing assignment APIs remain compatibility paths. New storage is additive:
canonical lineage columns and a handoff idempotency table can be ignored or
removed without rewriting legacy Runtime rows.
