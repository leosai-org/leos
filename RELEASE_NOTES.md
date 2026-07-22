# LEOS 0.1.0 Developer Preview RC11

RC11 is the corrected public-source successor to the immutable RC10 root
publication. It preserves RC10 history while fixing current-facing release
identity, repository ownership, installer authority, operator diagnostics, and
source provenance.

## Corrected public release surface

- current release documentation now identifies RC11;
- provisional `leos-ai-platform` CODEOWNERS handles are replaced by the
  verified maintainer account pending creation of visible organization teams;
- operator and security tooling load release identity from public authority
  files instead of compiled RC9 constants;
- installer bootstrap validates `manifest.json` and `source.lock.json`;
- installation and diagnostic examples identify RC11 without pretending their
  fixture hashes are the release payload hash;
- SPDX and CycloneDX source SBOM metadata identifies RC11;
- RC10 publication evidence remains byte-identical under `docs/release/rc10/`.

## Public source authority

The RC11 source distribution contains:

- `manifest.json` — release identity, channel, predecessor, license, and OCI
  exclusion;
- `contracts.lock.json` — SHA-256 records for tracked contracts;
- `source.lock.json` — deterministic payload-tree hash and file inventory;
- `checksums.sha256` — release-file checksums excluding the checksum file
  itself.

The payload-tree algorithm excludes the four authority files, preventing a
self-referential hash cycle. See `docs/release/rc11/SOURCE_AUTHORITY.md`.

## Source-only distribution

RC11 does not publish prebuilt OCI images or `container-images.lock.json`.
Historical images are not RC11 artifacts. See
`docs/release/rc11/OCI_EXCLUSION.md`.

## Compatibility and lineage

RC11 retains the service contracts and Phase 52 implementation lineage present
in RC10. Historical RC1-RC10 references remain only where they describe prior
phases, predecessor evidence, or immutable release history.

## Known limitations

- direct Python requirements remain unpinned;
- no source-equivalent OCI images are published;
- interfaces may change before stable `0.1.0`;
- the temporary CODEOWNER is `@bd3691` until governed organization teams are
  created and granted write access.

## Publication state

RC11 is a Developer Preview source candidate. A signed RC11 commit and tag,
remote publication, GitHub Release, and public announcement require the
remaining governed acceptance gates.
