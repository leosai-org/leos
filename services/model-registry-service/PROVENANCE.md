# Model Registry promotion provenance

The implementation concept was promoted from the immutable Lucy evidence at:

`lucy-runtime-reference/model-registry/`

Donor hashes:

| File | SHA-256 |
|---|---|
| `app.py` | `a687f66f8fa96a4c1a68419ea5634062aba7c412b6f1e12e3d0e5446294a6bba` |
| `Dockerfile` | `b0aa488c00d3dc4422aea38c2e17700d683fb39d1329ec463a30c5d0cdb582bd` |
| `requirements.txt` | `ba560a3c64a98d7beaa959974c33de69b938fce9678958b093e1ada5cf9dd87a` |

Promotion context: LEOS 0.2.0 Developer Preview v2, Epic 2.1, 2026-07-25.
The Lucy tree remains evidence only. This directory in `leos-v2` is the
writable source authority.

Intentional differences include stable `model_id`, explicit model-runtime
bindings, Capability Manager provider references, SQLite persistence,
content-addressed inventory revisions, non-destructive schema migration,
administrative enablement and availability facts, and audit events.

The donor's provider string, status-as-selection implication, overwrite CRUD,
model-name identity, and delete endpoint were not preserved. Runtime JSON
state, databases, logs, caches, secrets, and generated files were excluded.
Legacy donor JSON import remains deferred and must be governed before use.
