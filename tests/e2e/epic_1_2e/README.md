# Epic 1.2E E2E Test

Run from the repository root:

```bash
docker compose \
  -f tests/e2e/epic_1_2e/compose.yaml \
  up --build --abort-on-container-exit --exit-code-from e2e-test

docker compose \
  -f tests/e2e/epic_1_2e/compose.yaml \
  down --volumes --remove-orphans
```

The stack uses isolated `tmpfs` state and actual HTTP service boundaries. The
test runner writes optional detailed evidence to
`/tmp/epic-1.2e-evidence.json` inside its disposable container and reports
assertion failures through `unittest`.

