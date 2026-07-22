# Frozen Contracts — LEOS 0.1.0 Developer Preview RC11

## Machine-readable source authority

- `manifest.json`
- `contracts.lock.json`
- `source.lock.json`
- `checksums.sha256`

`source.lock.json` uses contract `leos.source-lock.v1` and payload-tree contract
`leos.payload-tree.v1`. Its deterministic hash excludes the four authority
files listed above. `contracts.lock.json` uses `leos.contracts-lock.v1`.

## Core frozen contracts

Core contracts include:

- `leos.execution.v1`
- `leos.execution-lineage.v1`
- `leos.acceptance.e2e.v1.1`
- `leos.runtime-coordination.v2.2`
- `leos.runtime-reconciliation.v3.1`
- `leos.goal-finalization.v2.1`
- `leos.goal-integrity.v1.1`
- the review and revision contracts present in `contracts/`;
- `dev-preview-e2e-scenario` version `1.8.0`.

A change to a frozen contract, source-authority algorithm, governed
configuration, or acceptance lineage requires a successor release and a new
acceptance run.

## Container images

RC11 is source-only. It has no `container-images.lock.json` and makes no claim
that historical local images are source-equivalent RC11 artifacts. The
controlling exclusion is `docs/release/rc11/OCI_EXCLUSION.md`.

## Schema and migration authority

The migration registry remains `migrations/registry.json` using
`leos.schema-authority.registry.v1`. Managed migrations use
`leos.database-migration.v1`; clone-based verification uses
`leos.migration-test.v1`.

## PostgreSQL authority

`leos.postgresql-authority.v1` governs PostgreSQL migration authority for
`leos-persistence-service`. `leos.postgresql-drift.v2` treats schema drift and
invalid canonical migration history as release blockers while normal
application data remains observational.

## Isolated acceptance runtime

`leos.isolated-acceptance-runtime.v1` governs disposable acceptance execution.
Network isolation, production-state proof, and teardown contracts remain part
of the predecessor implementation lineage. RC11 does not publish the
historical acceptance containers as release artifacts.
