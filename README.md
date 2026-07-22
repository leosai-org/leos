# LEOS

LEOS is an open-source orchestration platform for defining, coordinating, and
governing AI employees, services, tools, schedules, approvals, and persistent
workflows.

This repository contains the **source-only `0.1.0-dev-preview-rc10` Developer Preview**. It
is intended for architecture review, local development, testing, and early
community contribution.

> **Developer Preview:** interfaces, service boundaries, schemas, and
> deployment behavior may change before a stable release.

## What is included

- employee definitions, registries, runtime services, and scheduling;
- resource-profile and assignment services;
- service contracts, schemas, tools, and examples;
- governance, licensing, security, and contribution policies;
- SPDX and CycloneDX source SBOMs;
- release evidence for the RC10 source publication.

## What is not included

This preview does not publish prebuilt OCI/container images. Historical local
images did not establish complete RC10 source equivalence and are explicitly
excluded. See `docs/release/rc10/OCI_EXCLUSION.md`.

Models, model weights, private deployment configuration, credentials,
commercial extensions, hosted infrastructure, and private operational data are
not part of this source release.

## Start here

1. Read `RELEASE_NOTES.md`.
2. Review `FROZEN_CONTRACTS.md`.
3. Review `docs/architecture/REPOSITORY_ARCHITECTURE.md`.
4. Inspect the service directories and their local `requirements.txt` and
   Dockerfiles.
5. Read `CONTRIBUTING.md` before proposing changes.

RC10 dependencies are declared but not yet pinned. Exact observed versions and
the RC11 remediation plan are documented under `docs/release/rc10/`.

## Release identity

```text
Release: 0.1.0-dev-preview-rc10
Source release: accepted
OCI release: excluded
License: Apache-2.0
```

## Project resources

- Website: `https://leosai.org`
- Security: `SECURITY.md`
- Support: `SUPPORT.md`
- Governance: `GOVERNANCE.md`
- License: `LICENSE`
- Third-party notices: `THIRD_PARTY_NOTICES.md`

## Status and roadmap

RC11 will focus on reproducibility and container publication readiness,
including exact dependency locks, digest-qualified bases, fresh image builds,
image/source equivalence, and signed image provenance.

LEOS is stewarded by Bad Tech Labs LLC with an open contribution and governance
model described in this repository.
