# Employee Cognitive Service promotion provenance

## Authority and context

- Promotion date: 2026-07-24
- Target branch: `feature/v2-cognitive-lifecycle`
- Context: Epic 1.2D — Employee Cognitive Lifecycle Conformance
- Donor: `lucy-runtime-reference/employee-cognitive-service/`
- Target: `leos-v2/services/employee-cognitive-service/`

Lucy is immutable operational evidence, not source authority. The promoted and
conformed implementation in `leos-v2` is the writable v2 source authority.

## Donor hashes

| Donor file | Lucy SHA-256 |
|---|---|
| `app/main.py` | `0c859181985284f3fffbeaad6024995c01e1fe93247f8dc8beb76906a6d1daf9` |
| `app/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `requirements.txt` | `01cde95c7538352ba462549e9a3b0096d40db6b2b42e2b5c305187d238a2512c` |
| `Dockerfile` | `f3222565c90d5ae30b548560046b890cdcab7fd0377e49ac37d4ac2bd81893ae` |

The service shell, assignment discovery, context assembly, persistence concept,
and polling concept were donor inputs. Lifecycle and execution behavior were
deliberately conformed rather than copied verbatim.

Excluded material includes bytecode and `__pycache__`, SQLite/WAL/SHM files,
logs, caches, mounted data, environment files, credentials, secret material,
and historical runtime snapshots.

## Donor behavior removed

- assignment `/start` on every cognitive retry;
- noncanonical Dispatcher requests and legacy result interpretation;
- direct writes that made Cognitive Service a second working-memory authority;
- treating every Dispatcher response as success;
- absence of durable attempts, observations, waiting states, and terminal
  transition reconciliation;
- automatic retry after undifferentiated failures.

## Known remaining debt

- The reason/act/observe policy is intentionally minimal in this phase.
- Approval and governed-order resume require an explicit external decision.
- The Persistent Runtime terminal body remains provisional and service-local.
- Durable cognitive event publication is not introduced by this epic.
