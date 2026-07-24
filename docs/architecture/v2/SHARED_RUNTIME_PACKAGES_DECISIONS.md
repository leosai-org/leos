# Shared Runtime Packages Decisions

## ADR: Canonical shared runtime package location

**Status:** Accepted

Reusable v2 runtime libraries live under `packages/`. The initial library is
the independently packageable `packages/leos-contracts/` distribution, with
the `leos_contracts` Python namespace. It provides schema loading and runtime
schema/semantic validation for governed LEOS contracts. It must not accumulate
routing, discovery, persistence, approval, secret, or unrelated SDK behavior.

## ADR: Contract definition authority remains at repository root

**Status:** Accepted

Canonical JSON Schemas remain in `contracts/`; documented semantic invariants
complete their authority. `leos-contracts` enforces that authority and embeds
no schema copies. Development resolves the repository `contracts/` directory
only from a positively identified LEOS source checkout, with
`LEOS_CONTRACT_ROOT` as the explicit runtime authority. Installed packages
outside that verified layout require the environment setting. Container
deployments must copy the governed artifacts and set that variable.

## ADR: Root-context v2 service builds

**Status:** Accepted

Services consuming shared LEOS packages use the repository root as Docker
build context while retaining service-owned Dockerfiles at
`services/<service>/Dockerfile`. This permits an image to copy its service,
`packages/leos-contracts/`, and `contracts/` without duplication.

This convention applies prospectively to v2 shared-package consumers. It does
not rewrite RC11 packaging or unrelated service builds.

Shared-package consumer images use the governed `constraints/v2-runtime.txt`
dependency set and an immutable Python base-image digest. The root
`.dockerignore` limits transmitted build context; service Dockerfiles continue
to copy only their required service, package, contract, and constraint inputs.
