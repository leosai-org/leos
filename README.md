# LEOS

LEOS is an open-source orchestration platform for defining, coordinating, and
governing AI employees, services, tools, schedules, approvals, and persistent
workflows.

This repository contains the **source-only `0.1.0-dev-preview-rc11` Developer Preview**. It
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
- deterministic public source-authority files;
- preserved RC10 publication evidence and RC11 successor documentation.

## Source authority

RC11 introduces a non-self-referential public source authority:

- `manifest.json` records release identity and source-only status;
- `contracts.lock.json` fingerprints every tracked contract;
- `source.lock.json` fingerprints the governed source payload while excluding
  the four authority files themselves;
- `checksums.sha256` fingerprints every tracked release file except itself.

See `docs/release/rc11/SOURCE_AUTHORITY.md`.

## What is not included

This preview does not publish prebuilt OCI/container images. Historical images
were not rebuilt from the accepted RC11 source payload and are not release
artifacts. See `docs/release/rc11/OCI_EXCLUSION.md`.

Models, model weights, private deployment configuration, credentials,
commercial extensions, hosted infrastructure, and private operational data are
not part of this source release.

## Start here

1. Read `RELEASE_NOTES.md`.
2. Review `FROZEN_CONTRACTS.md`.
3. Review `docs/architecture/REPOSITORY_ARCHITECTURE.md`.
4. Inspect `manifest.json`, `source.lock.json`, and `contracts.lock.json`.
5. Read `CONTRIBUTING.md` before proposing changes.

Dependencies remain declared but not fully pinned in RC11. Exact observed
versions are documented in `THIRD_PARTY_NOTICES.md` and the source SBOMs.
Dependency locking and source-equivalent OCI publication remain later work.

## Release identity

```text
Release: 0.1.0-dev-preview-rc11
Release ordinal: 11
Source release: governed
OCI release: excluded
License: Apache-2.0
```

## Project resources

- Website: `https://leosai.org`
- Public repository: `https://github.com/leosai-org/leos`
- Security: `SECURITY.md`
- Support: `SUPPORT.md`
- Governance: `GOVERNANCE.md`
- License: `LICENSE`
- Third-party notices: `THIRD_PARTY_NOTICES.md`

## Status and roadmap

RC11 corrects public release identity, replaces provisional repository
ownership, and introduces deterministic source authority. A later successor
will focus on exact dependency locks, digest-qualified base images, fresh
source-equivalent OCI builds, image SBOMs, and signed provenance.

LEOS is stewarded by Bad Tech Labs LLC with an open contribution and governance
model described in this repository.
