# Frozen Contracts — LEOS 0.1.0 Developer Preview RC1

Authoritative machine-readable locks:

- `manifest.json`
- `contracts.lock.json`
- `source.lock.json`
- `checksums.sha256`

Core frozen contracts include:

- `leos.execution.v1`
- `leos.execution-lineage.v1`
- `leos.acceptance.e2e.v1.1`
- `leos.runtime-coordination.v2.2`
- `leos.runtime-reconciliation.v3.1`
- `leos.goal-finalization.v2.1`
- `leos.goal-integrity.v1.1`
- the live review/revision contracts detected from source
- `dev-preview-e2e-scenario` version `1.8.0`

A change to a frozen contract, source hash, critical image identity,
configuration checksum, or acceptance lineage requires a new release candidate
and a complete governed acceptance run.

## Container Image Lock

The immutable runtime image authority is `container-images.lock.json` using contract `leos.image-lock.v1`. Every critical service must have a non-null `sha256:` image ID, and the live RC1 container must resolve to that same image ID.

## Schema and Migration Authority

The authoritative registry is `migrations/registry.json` using
`leos.schema-authority.registry.v1`. Managed migrations use
`leos.database-migration.v1`; clone-based migration verification uses
`leos.migration-test.v1`. A managed SQLite authority must preserve its recorded
application-schema hash unless a new ordered migration explicitly changes it.

## PostgreSQL Migration Authority

`leos.postgresql-authority.v1` governs the PostgreSQL authority for
`leos-persistence-service`. Migration execution uses
`leos.database-migration.v1`, PostgreSQL advisory transaction locks, custom
format backups, isolated temporary-database testing, and schema/data drift
fingerprints. Test evidence uses `leos.postgresql-migration-test.v1`.

## PostgreSQL Drift Contract

`leos.postgresql-drift.v2` treats `schema_drift` and an invalid canonical
migration row as release blockers. `data_activity_observed` is informational
under the `observational` data-fingerprint policy and is not schema drift.

## Isolated Acceptance Runtime

`leos.isolated-acceptance-runtime.v1` governs disposable acceptance execution.
`leos.acceptance-network-isolation.v1` requires an internal-only Docker
network, zero host ports, no production container names, and no production
named volumes. `leos.production-state-proof.v1` requires exact logical
fingerprint equality for all seven production SQLite authorities and the
PostgreSQL persistence authority. `leos.acceptance-runtime-teardown.v1`
requires zero remaining project containers, networks, and volumes.
