# Execution Dispatcher promotion provenance

## Authority and context

- Promotion date: 2026-07-24
- Target branch: `feature/v2-execution-conformance`
- Context: Epic 1.2A — Shared Contract Runtime + Donor Service Promotion
- Donor: `lucy-runtime-reference/execution-dispatcher-service/`
- Target: `leos-v2/services/execution-dispatcher-service/`

The Lucy snapshot is immutable operational evidence and is **not** source
authority. After deliberate promotion, `leos-v2` is the writable source
authority for this service. Promotion does not imply release acceptance,
architecture conformance, or approval of preserved donor behavior.

## Promoted donor files and hashes

| File | Lucy donor SHA-256 | Initial promoted SHA-256 |
|---|---|---|
| `app/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `app/main.py` | `1da55c947bf2087805b4abd34074aea4c103b120f5a35adbdbf7bd9c6de3dd5b` | `f077cf609a3854b4c8f65c4b7719a1f8a0beecfabf7c350d4cfbafeb9ee86d85` |
| `requirements.txt` | `01cde95c7538352ba462549e9a3b0096d40db6b2b42e2b5c305187d238a2512c` | `01cde95c7538352ba462549e9a3b0096d40db6b2b42e2b5c305187d238a2512c` |

The only intentional donor-source difference is the import proving that the
`leos_contracts` runtime dependency is available. Validation remains
behaviorally inactive in donor request and response paths during Epic 1.2A.
The Dockerfile, tests, and this provenance record are v2 promotion additions.

Excluded material includes `__pycache__`, bytecode, SQLite databases and
WAL/SHM files, logs, caches, mounted data, generated runtime state,
environment/credential files, and secret material.

## Known donor debt deliberately preserved

- Dispatcher sends `provider_id` while Capability Manager accepts
  `preferred_provider_id`;
- legacy/raw provider result shape rather than canonical normalized output;
- current exception/HTTP-status retry semantics;
- no canonical execution-output validation;
- incomplete governance enforcement and idempotency classification;
- provider adapter and execution schemas that require later conformance.

These are donor-baseline facts, not accepted v2 architecture. Later
conformance work must replace or retire them deliberately.
