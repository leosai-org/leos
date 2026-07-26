# LEOS Authorization Authority

Production Dev Preview v2 service for issuing and verifying Authorization
Decision evidence and capability permission grants.

The service is intentionally narrow:

- owns Authorization Decision records;
- owns capability permission grants and revocations;
- performs deterministic default-deny policy evaluation over its own grants;
- persists audit lineage and a producer-local outbox;
- validates generated `leos.authorization-decision.v1` records.

It does not authenticate users, issue Actor Context evidence, approve actions,
resolve capabilities, schedule work, select employees, rank providers, invoke
tools, dispatch executions, manage secrets, or deliver events.

## Local run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8119
```

By default the service stores SQLite state under
`/data/authorization/authorization-authority.db`. For tests or local runs, set
`LEOS_AUTHORIZATION_AUTHORITY_DB` to a writable SQLite path.

## API surface

- `GET /health`
- `GET /ready`
- `GET /version`
- `GET /outbox`
- `POST /authorization-decisions`
- `GET /authorization-decisions`
- `GET /authorization-decisions/{decision_id}`
- `POST /authorization-decisions/{decision_id}/verify`
- `POST /authorization-decisions/{decision_id}/revoke`
- `POST /capability-permission-grants`
- `GET /capability-permission-grants`
- `GET /capability-permission-grants/{grant_id}`
- `POST /capability-permission-grants/{grant_id}/revoke`

Caller-supplied authorization booleans, approval booleans, role-as-permission,
membership-as-permission, plugin-installation-as-permission, raw secrets, and
client-issued Authorization Decision JSON are rejected.
