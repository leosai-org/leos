# RC11 OCI Exclusion

`0.1.0-dev-preview-rc11` is a source-only Developer Preview.

## Excluded artifacts

- prebuilt OCI/container images;
- `container-images.lock.json`;
- image SBOMs;
- image/source equivalence attestations;
- signed image provenance.

Historical local images and acceptance-runtime containers are not RC11 release
artifacts and must not be labeled or redistributed as RC11.

## Reason

The public-source correction and source-authority work is separable from a
fresh reproducible container build. Publishing historical images would make an
unsupported source-equivalence claim.

## Successor requirement

A later container-bearing release must use pinned dependencies,
digest-qualified bases, fresh builds from an accepted source authority, image
SBOMs, equivalence evidence, checksums, and signed provenance.
