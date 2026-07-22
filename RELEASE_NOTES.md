# LEOS 0.1.0 Developer Preview RC1

This release candidate freezes the first verified governed autonomous employee
execution path after native core consolidation and canonical lineage repair.

## Verified behavior

- Goal-to-mission planning and workflow materialization
- Scheduler and Persistent Employee Runtime execution
- Capability dispatch through the canonical execution envelope
- Artifact persistence and versioning
- Independent content review
- Autonomous revision after `revision_required`
- Approved artifact closeout
- Canonical KPI and success-criterion evidence
- Goal completion with integrity verification
- Runtime lease reconciliation
- Exact lineage correlation across planning, workflow, dispatch, runtime,
  artifact, review, and goal completion
- Kernel and Developer Preview release-gate readiness

## Consolidation

Canonical production modules:

- `app.runtime_reconciliation`
- `app.goal_integrity`

Compatibility shims remain for older imports.

## Lineage

The Autonomous Execution Chain now exposes:

```text
leos.execution-lineage.v1
```

The E2E harness uses the chain's exact proposal, mission, workflow, scheduler
job, dispatcher execution, final runtime job, artifact, and review identifiers.
It no longer re-correlates records by broad goal-level searches.

## Release state

`0.1.0-dev-preview-rc1` is a release candidate for migration formalization,
isolated clean-install testing, rollback testing, and installer development.

## Phase 51.1.3 Image Lock

Every critical RC1 service is now locked to the immutable Docker image ID observed from its running container. The authoritative image inventory is `container-images.lock.json`. Release metadata records Phase 51.1.3 as the final RC1 freeze-cleanup phase.

## Phase 51.2.1 Schema Authority

RC2 introduces a canonical schema-authority registry for eight core services.
SQLite-backed authorities were backed up before migration history was installed.
Application schema hashes were unchanged, migration apply/rollback/reapply was
tested on disposable clones, live drift detection passed, and the governed E2E
acceptance chain passed 17 of 17 stages.

## Phase 51.2.2 PostgreSQL Authority

RC3 brings `leos-persistence-service` under PostgreSQL migration authority.
Persistence-owned tables were discovered from the live connection and service
source, backed up in custom PostgreSQL format, fingerprinted, and registered
under transactional migration history protected by a PostgreSQL advisory lock.
Apply, rollback, and reapply passed in a temporary database, production schema
and data fingerprints remained unchanged, drift remained clean, and governed
E2E acceptance passed 17 of 17 stages.

## PostgreSQL Drift Semantics

`leos.postgresql-drift.v2` separates release-blocking schema or migration
authority drift from normal application data activity. Persistence documents,
events, and key/value records are mutable runtime data. Their fingerprint is
retained as observational evidence but does not invalidate a release when the
canonical schema and migration-history authority remain valid.

## Phase 51.3.2 Isolated Acceptance Runtime

RC4 introduces a disposable Docker Compose acceptance runtime built entirely
from RC3 image locks and Phase 51.3.1 cloned state. The runtime exposes no host
ports, uses an internal-only project network, mounts no production named
volumes, restores PostgreSQL into a project-scoped volume, and confines all
writable SQLite state to the workspace. Governed E2E passed 17 of 17 stages in
the isolated runtime. Production SQLite and PostgreSQL logical fingerprints
were identical before and after execution, and all isolated containers,
networks, and volumes were removed.
