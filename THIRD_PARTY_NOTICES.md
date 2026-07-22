# Third-Party Notices

LEOS source code is distributed under Apache License 2.0.

The RC11 source tree declares the following external Python dependencies. These
packages are not vendored into the repository and are obtained separately by
the installer or container build process.

| Package | Observed versions | License |
|---|---|---|
| FastAPI | 0.116.1; 0.139.0 | MIT |
| HTTPX | 0.28.1 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| Pydantic | 2.13.4 | MIT |
| PyYAML | 6.0.3 | MIT |
| Uvicorn | 0.35.0; 0.50.2; 0.51.0 | BSD-3-Clause |

This notice identifies the dependency versions observed during the RC10-to-RC11 source audit. The
source requirements are unpinned; a later successor will introduce governed dependency locking.

No third-party models, weights, datasets, fonts, media, archives, binary
libraries, or vendored source were found in the RC11 public-source candidate.

Prebuilt container images are not included in the RC11 Developer Preview.
