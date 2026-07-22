# Versioning and Release Channels

## Baseline

RC10 retains its exact established identity:

```text
0.1.0-dev-preview-rc10
```

Public Git tag:

```text
v0.1.0-dev-preview-rc10
```

No retroactive rename is allowed.

## Versioning rule

LEOS follows Semantic Versioning for its declared public APIs. Major version zero
is initial development, so compatibility may still change, but every intentional
breaking change must be documented.

## Developer-preview lineage

The existing developer-preview names use this legacy form:

```text
0.1.0-dev-preview-rc<N>
```

This syntax is valid as a prerelease identifier, but the embedded numeric suffix
does not provide reliable numeric SemVer ordering between values such as `rc9`
and `rc10`. Therefore:

- preserve all existing names exactly;
- use the explicit integer `release_ordinal` in release manifests;
- do not let automation select the newest developer preview by lexical or SemVer
  sorting alone;
- use exact tags or signed release manifests.

Successor identity:

```text
0.1.0-dev-preview-rc11
release_ordinal: 11
```

## Formal channels

| Channel | Version form | Audience |
|---|---|---|
| Internal development | Unreleased commit plus build metadata | Maintainers |
| Closed developer preview | `0.1.0-dev-preview-rc<N>` | Approved testers |
| Public developer preview | Same verified RC identifier | Public technical users |
| Final 0.1 release candidate | `0.1.0-rc.<N>` | Broad stabilization |
| Stable 0.1 | `0.1.0` | Supported initial release |
| Post-stable | Standard `MAJOR.MINOR.PATCH` with dotted prereleases | General users |

Because `rc` sorts after the current `dev-...` identifier, the move to
`0.1.0-rc.1` is the clean transition into canonical final-release candidates.

## Release immutability

Once published, a version and tag never move. Corrections require a new version.
Assets may not be silently replaced. If a publication asset is defective, mark
the release accordingly and publish a successor.

## Artifact identity

Every release manifest must record:

- software version;
- release ordinal where applicable;
- source/export commit;
- immutable RC source tree identity;
- public-export tree identity;
- container digest;
- checksums;
- SBOM identities;
- provenance identity;
- signing identity;
- build timestamp and builder.

## Support labels

Use explicit labels instead of vague terms:

- `developer-preview`
- `closed-preview`
- `public-preview`
- `release-candidate`
- `stable`
- `deprecated`
- `unsupported`


## Current public-preview successor

```text
0.1.0-dev-preview-rc11
release_ordinal: 11
expected tag: v0.1.0-dev-preview-rc11
```

RC11 corrects the public release surface and introduces deterministic source
authority. RC10 remains a preserved predecessor and its tag must not move.
