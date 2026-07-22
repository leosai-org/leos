# GitHub Ruleset Requirements

Use repository rulesets rather than relying only on informal maintainer practice.
Rulesets may layer with branch protections; the most restrictive applicable rule
should control.

## Ruleset: `leos-main-protection`

Target: default branch

Required:

- block deletion;
- block force pushes;
- require pull requests;
- require one approval;
- require CODEOWNER review;
- dismiss stale approvals when new commits are pushed;
- require all conversations resolved;
- require linear history;
- require status checks;
- require branch to be current before merge;
- restrict bypass to owners and audited release managers.

Initial required checks:

- `policy`
- `unit-tests`
- `integration-tests`
- `secret-scan`
- `dependency-review`
- `license-scan`
- `public-export-check`

Activate signed-commit enforcement only after a contributor rehearsal confirms
that GitHub squash merges, bot commits, and maintainer workflows remain usable.
Until then, use DCO as the mandatory contributor attestation and require signed
release tags.

## Ruleset: `leos-release-branches`

Target: `release/**/*`

- require two approvals;
- require release-manager review;
- require all main checks plus release verification;
- block force pushes and deletion;
- block direct pushes except the release automation identity;
- require signed commits after rehearsal.

## Ruleset: `leos-release-tags`

Target: `v*`

- restrict creation, update, and deletion to release managers or the release app;
- prevent tag movement;
- require a signed annotated tag;
- require the tag to identify a verified release commit.

## Workflow safeguards

Release workflows must:

- pin third-party actions to immutable commit SHAs;
- use least-privilege job permissions;
- publish through a protected environment;
- require human approval;
- emit checksums, SBOM, provenance, and immutable OCI digests;
- fail closed if any required artifact is missing.
