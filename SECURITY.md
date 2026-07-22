# Security Policy

## Supported versions

The current Developer Preview is supported for coordinated vulnerability
reporting only.

| Version | Security reporting |
|---|---|
| 0.1.0-dev-preview-rc11 | Supported |
| 0.1.0-dev-preview-rc10 | Historical predecessor; not supported |
| Earlier internal candidates | Not supported |

## Reporting a vulnerability

Do not report suspected vulnerabilities in a public issue, discussion, pull
request, or social-media post.

Use the repository's private **Security → Report a vulnerability** workflow.
When that workflow is unavailable, use the security contact method published at
`https://leosai.org`.

Include:

- affected component and version;
- impact and realistic attack scenario;
- reproduction steps or proof of concept;
- relevant logs with credentials and personal data removed;
- suggested mitigation, when known;
- whether the issue is already public.

## Response process

Maintainers will acknowledge a valid private report, assess scope and severity,
coordinate remediation, and publish an advisory when disclosure is appropriate.
Response timing depends on impact, reproducibility, and maintainer availability.

## Scope

Security reports may cover source code, service boundaries, authentication and
authorization behavior, secret handling, dependency risk, unsafe defaults,
release provenance, or documentation that could cause insecure deployment.

The RC11 source release does not include supported prebuilt container images.
Reports concerning historical local images should identify the exact image
digest and must not assume those images are RC11 artifacts.

## Safe harbor

Good-faith research that avoids privacy violations, service disruption,
destructive actions, data exfiltration, and unnecessary access will not be
treated as malicious by the project. This statement does not authorize testing
systems you do not own or have permission to test.
