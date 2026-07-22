# LEOS Licensing

## Community/Core license

Unless a file or component clearly states otherwise, the public LEOS Community/Core source distribution is licensed under the **Apache License, Version 2.0**. The SPDX identifier is:

```text
Apache-2.0
```

The complete license is in [`LICENSE`](../../LICENSE).

Apache-2.0 permits use, modification, distribution, and commercial use subject to its conditions. Recipients must preserve required copyright, license, attribution, and NOTICE information; modified files must carry prominent notices of modification; and the license includes an express patent grant with a patent-litigation termination provision.

## What commercial licensing means for LEOS

Commercial LEOS products do **not** take away rights already granted under Apache-2.0. A customer never needs a commercial license merely to use, modify, host, or sell services based on Apache-licensed LEOS Community/Core.

Commercial licenses apply only to separately identified offerings, such as:

- LEOS Enterprise proprietary modules;
- official premium plugins, connectors, policy packs, and management tools;
- marketplace access, billing, certification, signing, and distribution services;
- hosted or managed LEOS services;
- enterprise support, warranties, indemnities, service-level commitments, training, and consulting;
- commercial redistribution bundles containing proprietary LEOS components.

## Public repository rule

A public repository must contain a top-level `LICENSE` file and must identify its license in repository metadata as `Apache-2.0`. New source files created for RC11 and later should normally carry a concise SPDX header appropriate to the file type:

```text
SPDX-License-Identifier: Apache-2.0
```

RC10 files are immutable. SPDX headers are **not** backfilled into RC10 source files. The RC10 public export is licensed through the publication envelope, top-level license, NOTICE, and a hash-audited license manifest. RC11 begins successor normalization without rewriting immutable RC10 evidence.

## Files not covered by Apache-2.0

The following are excluded unless explicitly licensed otherwise:

- LEOS names, logos, employee glyphs, trade dress, and other brand assets;
- proprietary Enterprise source and binaries;
- proprietary official plugins or third-party marketplace products;
- cloud service, marketplace, support, and commercial contract terms;
- model weights, datasets, fonts, media, and third-party dependencies governed by their own licenses;
- credentials, signing keys, private infrastructure, internal evidence, customer data, and secrets.

## Forks and downstream distributions

Forks may use the Apache-licensed code according to Apache-2.0. They may accurately state that they are based on LEOS, but they may not imply official status, certification, sponsorship, or endorsement. Downstream projects should choose a distinct product name and branding unless written trademark permission is granted.

## No Apache Foundation affiliation

“Apache-2.0” names the license. LEOS is not an Apache Software Foundation project and must never be marketed as “Apache LEOS.”

## References

- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- Apache licensing FAQ: https://www.apache.org/foundation/license-faq.html
- SPDX license information: https://spdx.org/licenses/Apache-2.0.html
- SPDX identifier guidance: https://spdx.dev/learn/handling-license-info/


## RC11 source-authority files

`manifest.json`, `contracts.lock.json`, `source.lock.json`, and
`checksums.sha256` are part of the Apache-2.0 public-source distribution or
factual release metadata. They do not alter third-party license terms.
