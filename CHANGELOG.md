# Changelog

All notable public changes to LEOS will be documented here.

The project follows semantic-versioning principles adapted for Developer
Preview and release-candidate channels.

## Unreleased

### Planned

- exact dependency locks and artifact hashes;
- digest-qualified base-image provenance;
- fresh source-equivalent OCI builds;
- signed SBOM and provenance publication;
- expanded installation and operator documentation.

## [0.1.0-dev-preview-rc10] — 2026-07-21

### Added

- initial public source Developer Preview;
- employee registry, builder, assignment, scheduling, persistent runtime, and
  resource-profile source components;
- frozen contracts and release notes;
- Apache-2.0 licensing and public governance documents;
- source SPDX and CycloneDX SBOMs;
- third-party dependency and provenance notices;
- GitHub issue and pull-request templates.

### Security

- deterministic sensitive-data scanning completed;
- four intentional or false-positive findings were accepted through exact
  path, rule, and hash allowlisting;
- no active secret finding remained in the clean source candidate.

### Known limitations

- direct Python dependencies are not pinned in RC10;
- prebuilt OCI images are excluded;
- historical runtime images are not RC10 release artifacts;
- interfaces remain subject to change before a stable release.
