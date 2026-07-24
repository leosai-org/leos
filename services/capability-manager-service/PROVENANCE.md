# Capability Manager promotion provenance

## Authority and context

- Promotion date: 2026-07-24
- Target branch: `feature/v2-execution-conformance`
- Context: Epic 1.2A — Shared Contract Runtime + Donor Service Promotion
- Donor: `lucy-runtime-reference/capability-manager-service/`
- Target: `leos-v2/services/capability-manager-service/`

The Lucy snapshot is immutable operational evidence and is **not** source
authority. After deliberate promotion, `leos-v2` is the writable source
authority for this service. Promotion does not imply release acceptance,
architecture conformance, or approval of preserved donor behavior.

## Promoted donor files and hashes

| File | Lucy donor SHA-256 | Initial promoted SHA-256 |
|---|---|---|
| `app/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `app/execution_contract.py` | `fad499efea837776e42d3a7b46b96d978a65a18f54c0a834696be5b4fa10a3ff` | `fad499efea837776e42d3a7b46b96d978a65a18f54c0a834696be5b4fa10a3ff` |
| `app/main.py` | `01c05357cb2e398baa561868e1fd6ff59821ef0e7d470955a50863ed7a71a7fe` | `92d7acefb9a25f180023dd3bc43cfbe0e76113f96ad3c1e807b3ffee6f656e11` |
| `requirements.txt` | `01cde95c7538352ba462549e9a3b0096d40db6b2b42e2b5c305187d238a2512c` | `01cde95c7538352ba462549e9a3b0096d40db6b2b42e2b5c305187d238a2512c` |

The only intentional donor-source difference is the import proving that the
`leos_contracts` runtime dependency is available. Validation remains
behaviorally inactive in donor request and response paths during Epic 1.2A.
The Dockerfile, tests, and this provenance record are v2 promotion additions.

Excluded material includes `__pycache__`, bytecode, SQLite databases and
WAL/SHM files, logs, caches, mounted data, generated runtime state,
environment/credential files, and secret material.

## Known donor debt deliberately preserved

- direct provider invocation through `/execute`;
- Capability Manager execution persistence and history;
- the provider payload-adapter registry and adaptation behavior;
- weighted score-based resolution rather than governed candidate order;
- caller-controlled `allow_approval_required` Boolean behavior;
- incomplete explicit approval-grant verification and other governance hooks;
- execution, adapter, and event tables that overlap Dispatcher authority.

These are donor-baseline facts, not accepted v2 architecture. Later
conformance work must replace or retire them deliberately.

