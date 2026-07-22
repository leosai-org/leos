# LEOS Canonical Database Migrations

This directory is generated and governed by Phase 51.2.

## Authorities

`registry.json` classifies storage for eight core LEOS services. SQLite-backed
services are managed directly in Phase 51.2.1. External database services are
recorded as `classified-pending-adapter`; stateless services are recorded as
`classified-no-database`.

## Baselines

Each managed SQLite authority has:

```text
authorities/<service>/1.0.0/baseline.json
```

The baseline records the canonical application schema and hash. The internal
`leos_schema_migrations` table is excluded from application-schema drift
calculations.

## Evidence

- `baseline-application-evidence.json`
- `migration-test-evidence.json`
- `drift-report.json`

Backups are intentionally stored outside this directory under the deployment
backup path.
## PostgreSQL Authority

`leos-persistence-service` is governed by
`leos.postgresql-authority.v1`.

The authority uses:

- custom-format `pg_dump` backups
- schema-only SQL backups
- canonical schema hashes
- deterministic per-table data fingerprints
- PostgreSQL advisory transaction locks
- migration history in `leos_migrations.schema_migrations`
- isolated temporary-database apply, rollback, and reapply tests
- live schema and data drift detection
