# LEOS License Boundary Matrix

This matrix is the default publication rule. A component-specific license file may override it only after review.

| Asset or capability | Default status | Default license/terms | Repository class |
|---|---|---|---|
| LEOS runtime kernel and orchestration contracts | Public | Apache-2.0 | Public core |
| Employee lifecycle, scheduling, resource enforcement | Public | Apache-2.0 | Public core |
| Public API schemas and compatibility contracts | Public | Apache-2.0 | Public core/contracts |
| CLI, installer, first-run, doctor, rollback foundations | Public | Apache-2.0 | Public core or installer |
| Plugin/adapter SDK and manifest schema | Public | Apache-2.0 | Public SDK |
| Reference employees, plugins, and examples | Public | Apache-2.0 | Public examples/plugins |
| Baseline local security and observability | Public | Apache-2.0 | Public core |
| Public documentation in source repositories | Public | Apache-2.0 unless marked | Public docs |
| RC11 public-source metadata, manifests, checksums | Public | Apache-2.0 or factual data | Public release engineering |
| Enterprise identity, fleet, HA, compliance, advanced governance | Private/commercial | LEOS Enterprise agreement | Private enterprise |
| Proprietary admin experiences and policy packs | Private/commercial | LEOS Enterprise agreement | Private enterprise |
| Official premium connectors/plugins | Commercial | Premium Plugin License | Private plugin repo/package |
| Marketplace client protocol and validation tools | Public | Apache-2.0 | Public marketplace SDK |
| Marketplace billing, entitlement, fraud, private moderation | Service/private | Marketplace/service terms | Private service |
| Third-party marketplace plugins | Varies | Publisher-selected declared license | Publisher repo/package |
| LEOS hosted control plane and managed operations | Service/private | Cloud terms | Private service |
| Customer configurations, data, secrets, support records | Private | Contract/privacy terms | Never public |
| Internal release evidence and infrastructure details | Private | Confidential | Internal release engineering |
| Signing keys, credentials, tokens, internal endpoints | Secret | Never distributed | Secret management only |
| LEOS word marks, logos, glyphs, and trade dress | Publicly viewable, controlled use | Trademark policy, not Apache-2.0 | Brand repository/CDN |
| Third-party model weights and datasets | Varies | Upstream license | External/cache, never assumed Apache |
| Third-party libraries and images | Varies | Upstream license and notices | Dependency/package |

## Interface rule

Where practical, proprietary modules should integrate through public, stable interfaces rather than private forks of the core. If an enterprise feature requires a core hook, the generic hook should normally be contributed to the Apache-licensed core, while the proprietary implementation remains private.

## Combined distributions

A commercial LEOS distribution may bundle Apache-licensed core and proprietary components. The bundle must:

1. preserve the Apache-2.0 `LICENSE`, required notices, and source-offer obligations imposed by any third-party licenses;
2. clearly identify which components are Apache-2.0, proprietary, or third-party;
3. avoid implying that the commercial agreement overrides Apache-2.0 rights in the core;
4. include an SBOM and third-party notices;
5. use separate entitlement checks only for proprietary components.


## RC11 lineage note

RC10 license and publication evidence remains historical. RC11 adds corrected
public-source metadata and authority files under the same Apache-2.0 community
boundary; brand assets and proprietary modules remain outside that grant.
