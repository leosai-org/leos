# Branching, Pull Request, and Merge Policy

## Default model

LEOS uses protected trunk-based development:

- `main` is always releasable;
- changes use short-lived branches;
- pull requests are mandatory;
- squash merge is the default;
- direct pushes, force pushes, and branch deletion are blocked.

Do not create a permanent `develop` branch.

## Branch names

- `feature/<issue>-<slug>`
- `fix/<issue>-<slug>`
- `docs/<issue>-<slug>`
- `security/<private-id>-<slug>` in private security workflows
- `release/<version>`
- `hotfix/<version>-<slug>` after a stable release

## Pull request requirements

All pull requests must:

1. reference an issue or approved maintenance task;
2. include DCO sign-off on commits;
3. pass required tests, linting, secret scanning, dependency review, and export checks;
4. update tests and documentation when behavior changes;
5. receive at least one approving review;
6. receive CODEOWNER approval for owned paths;
7. resolve all review conversations;
8. be current with the target branch before merge.

Require two approvals for:

- release engineering;
- licensing and trademark policy;
- security-sensitive paths;
- compatibility contracts;
- organization workflows that can publish artifacts;
- proprietary/public boundary changes.

## Merge method

Enable squash merging for normal pull requests. Disable merge commits and rebase
merging on `main` unless a later ADR establishes a justified exception.

The squash commit title follows:

```text
<type>(<scope>): <summary> (#<pull-request>)
```

Allowed types include `feat`, `fix`, `docs`, `test`, `build`, `ci`, `refactor`,
`perf`, `security`, `release`, and `chore`.

## Release branches

Create a release branch only when stabilization requires parallel work. Release
branches accept fixes, documentation corrections, packaging changes, and
security work approved for that release. New feature development stays on
`main` for a later release.

## Public-to-internal contribution flow

The public repository is not the authority for immutable RC10. Accepted public
changes are recorded and applied to the active successor workspace through a
reviewed integration process. The successor release then produces the next clean
public export.
