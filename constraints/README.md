# V2 runtime constraints

`v2-runtime.txt` is the governed, complete Python dependency constraint set
for v2 service images that currently share the Epic 1.2A runtime.

The initial versions were captured with `pip freeze` from the successfully
built Capability Manager image on 2026-07-24. The pinned Python base digest
fixes the bundled Python and pip versions. The package build backend version
was resolved from that base and then verified by rebuilding both images.

To update the constraints, start from an intentionally selected immutable
Python base, install the donor requirements and local LEOS package, capture
the complete transitive environment, review every version change, and rerun
the package, contract, service, regression, and image-build checks. Do not
update individual transitive pins opportunistically.

