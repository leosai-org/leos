# LEOS Third-Party License Policy

## Goal

Every public source export, release archive, container image, plugin, and commercial bundle must have a reviewable chain of third-party licensing evidence.

## Required records

Each release must produce:

- SPDX and CycloneDX SBOMs;
- dependency name, version, source, license expression, and checksum;
- container base-image identity and digest;
- model, dataset, font, media, and binary-blob license records;
- `THIRD_PARTY_NOTICES` with required attribution text;
- a list of unknown, custom, noncommercial, source-available, copyleft, or restricted licenses requiring review.

## Default acceptance categories

### Generally acceptable after normal review

Permissive OSI-approved licenses such as Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, and similarly compatible terms, provided notices and conditions are preserved.

### Requires architectural and legal review

- weak copyleft licenses;
- GPL-family dependencies or tools that may affect distribution obligations;
- network copyleft licenses;
- custom licenses;
- licenses with field-of-use, noncommercial, ethical-use, or redistribution restrictions;
- model and dataset licenses;
- packages with missing or conflicting metadata;
- prebuilt binaries without corresponding source/provenance;
- fonts, icons, screenshots, sample data, and media assets.

### Prohibited until explicitly approved

- code or assets with no identifiable license;
- copied code without provenance;
- credentials, private keys, or customer content;
- dependencies whose terms cannot be satisfied by the intended distribution;
- components that falsely claim to be Apache-2.0 when upstream terms differ.

## Models are separate products

LEOS compatibility with a model does not mean the model is Apache-2.0. Every model adapter and download path must display the model provider, exact model version, governing license, commercial-use status, redistribution status, and any acceptable-use restrictions.

## Containers

A container image is a combined distribution of layers and packages. Publishing source under Apache-2.0 does not relicense the base image, operating-system packages, GPU libraries, model runtimes, or bundled dependencies. Image SBOMs and notices are mandatory.

## Marketplace

Every marketplace listing must declare:

- SPDX expression or full custom license;
- source-available/open-source/proprietary classification;
- pricing and entitlement terms;
- permissions and data access;
- supported LEOS versions;
- publisher identity and security contact;
- SBOM, signature, checksum, and update policy.

## Release gate

Unknown or incompatible licensing is a blocking failure, not a warning. Any correction after RC11 publication requires another successor release; published tags and assets are never silently replaced.


## RC11 source-only decision

RC11 refreshes source SBOM identity but does not publish OCI artifacts. Image
SBOMs, base-image digests, and signed image provenance remain blocking
requirements for a later container-bearing release.
