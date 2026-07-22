# Source SBOM Decision

Syft creates a package for the scanned directory in addition to packages
identified from dependency manifests.

For this release:

- the directory package is LEOS itself;
- its generated name is a local filesystem path;
- its `NOASSERTION` value is not a third-party license gap;
- the publication overlay assigns the logical name `LEOS`;
- the overlay records version `0.1.0-dev-preview-rc10`;
- the governing license is `Apache-2.0`.

The original scanner-produced SBOM remains preserved as audit evidence. A
publication-normalized copy is created without changing the evidence original.
