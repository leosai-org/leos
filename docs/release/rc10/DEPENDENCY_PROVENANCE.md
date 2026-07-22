# Dependency Provenance

## Source declarations

The clean source candidate contains seven Python requirements files. Twenty-eight
entries were parsed, representing six direct package names.

The source files are unpinned. This is recorded as an RC10 reproducibility
limitation and an RC11 correction requirement.

## Runtime evidence

Exact installed versions and license metadata were recovered from nine local
images using:

- read-only container filesystems;
- networking disabled;
- temporary containers removed;
- no changes to RC10 or the clean candidate.

Historical images are accepted only as dependency-environment evidence when
their `requirements.txt` hashes match RC10.

## Base image

The locally recorded Python base is:

```text
python@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf
platform: linux/amd64
```

This base-image evidence is retained for audit and RC11 planning. It does not
authorize publishing an RC10 container image.
