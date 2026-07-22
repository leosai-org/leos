# RC11 Remediation Plan

Successor release: `0.1.0-dev-preview-rc11`

## Required source corrections

1. Pin every direct Python dependency.
2. Introduce governed lock files with artifact hashes.
3. Resolve and record the complete transitive dependency graph.
4. Record a digest-qualified Python base image.
5. Rebuild every public image from RC11 source.
6. Verify every copied application file against the RC11 tree.
7. Generate source and image SPDX/CycloneDX SBOMs with logical names.
8. Generate third-party notices from the governed dependency lock.
9. Generate license and vulnerability evidence per OCI image.
10. Sign release tags, image manifests, SBOMs, and provenance.

## Non-goal

RC11 is not required merely to publish the accepted RC10 source-only Developer
Preview.
