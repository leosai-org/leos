# RC10 OCI Exclusion

No prebuilt container image may be published, tagged, or represented as an RC10
release artifact under this decision.

## Reason

Three historical/running service images contain exact RC10 requirements files
but differ from the RC10 application payload:

- assignment-service;
- employee-builder;
- employee-registry.

Other inspected images supply dependency, license, and base-image evidence but
have not been accepted as complete public RC10 OCI artifacts.

## Forbidden operations

Until RC11 is built and accepted:

- do not push any local LEOS image as RC10;
- do not retag historical images as `0.1.0`, `rc10`, or equivalent;
- do not attach historical image SBOMs as though they describe an RC10 image;
- do not advertise prebuilt containers as part of the RC10 Developer Preview.

## RC11 requirements

RC11 must include:

- exact Python dependency pins;
- digest-qualified base-image provenance;
- fresh builds from the accepted source;
- image/source payload equivalence checks;
- SPDX and CycloneDX SBOMs for each image;
- license and vulnerability reports;
- immutable registry digests and signed provenance.
