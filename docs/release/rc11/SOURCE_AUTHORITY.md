# RC11 Source Authority

## Release identity

```text
Release: 0.1.0-dev-preview-rc11
Expected tag: v0.1.0-dev-preview-rc11
Distribution: source-only
```

## Authority files

- `manifest.json` records release identity, predecessor evidence, license, and
  OCI status.
- `contracts.lock.json` records SHA-256 and size for every tracked contract.
- `source.lock.json` records the deterministic source payload inventory and
  payload-tree hash.
- `checksums.sha256` records every tracked release file except itself.

## Payload-tree algorithm

The `leos.payload-tree.v1` digest is calculated over payload files sorted by
UTF-8 path. For each file, the digest input is:

```text
path + NUL + lowercase SHA-256 + NUL
```

The following files are excluded to avoid self-reference:

```text
manifest.json
contracts.lock.json
source.lock.json
checksums.sha256
```

All other tracked files, including the RC11 documentation and source SBOMs, are
included.

## Runtime consumption

The installer, operator CLI, and security-observability tooling read
`manifest.json` and `source.lock.json`. Release and payload identity are no
longer compiled as RC9 constants.

## Git authority

The signed Git commit and signed annotated tag remain the primary distribution
authority. The files above provide portable source verification before and
after archive extraction.
