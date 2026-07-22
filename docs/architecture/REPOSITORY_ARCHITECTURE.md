# LEOS Repository Architecture

## Launch architecture

### Public repositories

| Repository | Purpose | Initial authority |
|---|---|---|
| `.github` | Organization profile, shared issue templates, contribution links, default community-health files | Community governance |
| `leos` | Clean public export of the LEOS core monorepo, releases, discussions, primary issue tracker | Public source |
| `leos-docs` | Documentation site source and publication guides for leosai.org | Documentation |
| `leos-examples` | Curated examples, demos, sample employees, and integration recipes | Examples |

### Private repositories

| Repository | Purpose |
|---|---|
| `leos-publication` | Clean-export policy, embargoed staging, release evidence, manifests, publication automation |
| `leos-enterprise` | Proprietary Enterprise modules |
| `leos-marketplace-service` | App Store billing, entitlement, fraud, and private moderation |
| `leos-premium-plugins` | Official proprietary plugins and connectors |
| `leos-cloud` | Hosted and managed service control plane |
| `leos-security-private` | Embargoed vulnerability coordination and private security evidence |
| `leos-website` | leosai.org implementation until a later decision makes it public |
| `leos-internal-ops` | Internal infrastructure, customer operations, and release administration |

Secrets belong in a secret manager, never in a repository.

## Why the core starts as a monorepo

RC11 contains tightly coordinated services, contracts, deployment definitions,
tests, and release verification. Publishing those components in one repository
preserves atomic changes and prevents incompatible cross-repository releases.

A component may be extracted only when all of these are true:

1. it has an explicitly documented public API or artifact contract;
2. it can be tested independently;
3. it has named maintainers;
4. it can follow an independent release cadence;
5. its dependency direction is clear;
6. splitting it does not make the community edition incomplete;
7. migration and compatibility plans are approved.

## Deferred candidate repositories

These are names, not launch requirements:

- `leos-plugin-sdk`
- `leos-contracts`
- `leos-installer`
- `leos-operator`
- `leos-rfcs`
- `leos-brand`

Until the extraction criteria are met, these capabilities remain in `leos` or
their appropriate existing publication repository.


## RC11 publication lineage

The public source authority is `leosai-org/leos`. RC10 remains the immutable
predecessor root publication; RC11 is the current source-only successor. Private
publication evidence remains outside the public monorepo.
