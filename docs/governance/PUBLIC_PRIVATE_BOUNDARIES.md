# Public and Private Repository Boundaries

## Public by default

The public project should contain the source, contracts, schemas, examples,
documentation, tests, governance, release notes, SBOMs, and issue history needed
to understand, build, review, and contribute to the open-source platform.

## Private by default

Private repositories may contain credentials, production configuration,
customer or employee data, security reports under embargo, hosted-service
operations, commercial extensions, contracts, internal financial material, and
infrastructure-specific deployment details.

## Publication rules

A file may enter the public repository only after it passes:

1. source-authority and release-identity verification;
2. public/private classification;
3. sensitive-data scanning;
4. third-party license and provenance review;
5. public-document review;
6. final assembly and checksum verification.

Private material must not be sanitized in place and silently mixed into a public
release. Publication should flow one way—from an immutable internal authority
through a governed export into a fresh public assembly tree.

## Independence of licensing

Private or commercial repositories do not change the Apache-2.0 license of the
public LEOS source. Public and private components must communicate through
documented interfaces without misrepresenting private code as part of the open
release.
