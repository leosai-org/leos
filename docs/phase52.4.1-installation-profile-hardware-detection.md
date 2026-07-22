# LEOS Phase 52.4.1 — Installation Profile and Hardware Detection

Phase 52.4.1 adds a read-only host capability probe and a deterministic
installation-profile planner for the LEOS Standard developer preview.

## Commands

```bash
bin/leos-install-profile detect
bin/leos-install-profile recommend
bin/leos-install-profile plan
bin/leos-install-profile all
```

Every command emits JSON. Use `--output FILE` to write a document and
`--fixture FILE` for deterministic acceptance testing.

The default probe is safe and local:

- CPU topology and instruction flags
- total and available memory
- capacity of the selected installation path
- operating system, architecture, and Python runtime
- Docker or Podman binary presence
- NVIDIA driver, GPU, VRAM, CUDA, and container-runtime integration
- local interfaces and default-route presence
- service-manager, virtualization, and current-user context

The default probe does not contact an external network and does not contact
the container service. Add `--contact-container-daemon` only when a local
runtime-access check is required.

## Standard profiles

The catalog intentionally remains focused on LEOS Standard:

- `leos-standard-large-nvidia`
- `leos-standard-nvidia`
- `leos-standard-cpu`
- `leos-standard-minimum`

The minimum profile is marked degraded and is intended for evaluation. It is
not a separate LEOS Lite product.

## Outputs

`leos.host-capability-inventory.v1`
: Normalized host facts and probe provenance.

`leos.installation-profile-recommendation.v1`
: Selected profile, readiness, blockers, warnings, runtime mode, and employee
  concurrency budget.

`leos.installation-plan.v1`
: A non-mutating plan for the idempotent installer developed in Phase 52.4.2.
  The plan includes a `leos.compute-node-capacity.v1` projection so runtime
  scheduling can use the same resource vocabulary.

Phase 52.4.1 never installs packages, changes services, creates containers, or
modifies host configuration. All installation actions are represented as
planned records requiring confirmation.
