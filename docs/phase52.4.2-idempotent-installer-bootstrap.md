# LEOS Phase 52.4.2 — Idempotent Installer and Bootstrap

Phase 52.4.2 turns the non-mutating installation plan from Phase 52.4.1 into
a governed bootstrap transaction engine. It prepares a target installation
root, generates deterministic configuration, records ownership intent, writes
a durable installation manifest, and journals every reversible action.

## Safety model

The installer never contacts an external network or a container daemon in this
phase. Connected mode only records that network access was explicitly
authorized; package acquisition remains a later installer integration. Offline
mode requires a local source root containing an RC9 release record.

`plan` is read-only. `apply` requires a confirmation token that exactly matches
the `plan_id`. Broad targets such as `/`, `/etc`, `/usr`, `/var`, and `/home`
are rejected. Managed paths are constrained beneath the selected target root.

## Idempotency

The desired bootstrap files are rendered deterministically. Before every write,
the installer compares the desired SHA-256 with the existing file. A second
application of the same plan produces zero installation-state changes and
returns `idempotent: true`.

## Rollback

Before replacing an existing managed file, the installer copies it into a
transaction-specific backup root. Any exception triggers reverse-order restore
of backups and removal of files and empty directories created by the failed
transaction. A rollback journal is written outside the failed target root so
the failure record survives complete cleanup.

## Ownership

The bootstrap records desired owner and group in
`state/ownership-intent.json`. Privileged `chown` is intentionally not executed
by default. This keeps unattended tests and developer-preview bootstrap safe
while preserving the exact ownership operation for the later privileged
installer layer.

## Commands

```bash
bin/leos-install plan \
  --plan examples/installation-plan.json \
  --target-root /opt/leos \
  --mode offline \
  --source-root release/0.1.0-dev-preview-rc9

bin/leos-install apply \
  --plan examples/installation-plan.json \
  --target-root /opt/leos \
  --mode offline \
  --source-root release/0.1.0-dev-preview-rc9 \
  --confirm plan-4ae24502f43546e5

bin/leos-install inspect --target-root /opt/leos
```

## Contracts

- `leos.installation-layout.v1`
- `leos.installation-transaction.v1`
- `leos.installation-execution-journal.v1`
- `leos.installation-manifest.v1`
- `leos.installation-result.v1`

## Phase boundary

This phase prepares installation state only. Service deployment, package
acquisition, privileged ownership application, and first-run administrator
initialization remain governed follow-on work.

## Portable example paths

The committed installation transaction, journal, manifest, and result examples
use the relative placeholder root `leos-example`. They describe contract shape
and installer behavior without embedding an absolute host filesystem path.
Runtime plans still resolve and validate an explicit operator-selected absolute
target before any installation transaction is applied.

