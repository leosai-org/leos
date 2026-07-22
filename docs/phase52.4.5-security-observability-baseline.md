# LEOS Phase 52.4.5 — Security and Observability Baseline

Phase 52.4.5 adds an offline-first security and observability layer to the
LEOS Standard development line.

## Unified operator commands

The existing `leos` command now includes:

- `leos security` — read-only security baseline;
- `leos observe --view health|metrics|readiness` — structured operational state;
- `leos diagnostics` — a bounded, redacted diagnostics plan;
- `leos diagnostics --export ... --confirm ...` — explicitly authorized export.

## Security baseline

The baseline checks private file modes, immutable RC9 installation identity,
plaintext-secret indicators, public service bindings, and privileged runtime
intent. Secret findings contain only a path, pattern identifier, location, and
severity. Matched values are never returned.

## Observability contracts

Phase 52.4.5 defines contracts for security reports, secret and network
exposure, service health, resource metrics, structured logs, diagnostics
manifests, and observability readiness.

All probes are read-only by default. They do not contact external networks or
the container daemon. Live metrics use only local, read-only operating-system
information unless a deterministic fixture is supplied.

## Diagnostics export

Diagnostics export requires the exact confirmation token from the plan. The
output path must be portable and relative to the selected installation root.
The exporter:

1. bounds file count, individual file size, total archive size, and log lines;
2. excludes symlinks, unsupported suffixes, and secret-material filenames;
3. redacts recognized token, password, and private-key patterns;
4. writes structured reports and sanitized logs only;
5. creates a deterministic ZIP with an integrity manifest.

The exporter never copies plaintext credential files and never authorizes
repairs, service changes, network access, or daemon access.
