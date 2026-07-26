# LEOS Organization Domain Service

Production owner for Dev Preview v2 Organization Domain resources.

The service persists canonical Organization, Department, Team, Role,
Position, Membership, Position Occupancy, lifecycle transition, audit, and
local producer-outbox records. It does not own Employee lifecycle,
authorization, approval, work assignment, scheduling, execution, model/provider
selection, secrets, plugins, or event delivery.

## Boundaries

- Employee references are validated through a narrow Employee Registry adapter.
  The service stores no Employee definitions.
- Authorization evidence is required as revision-pinned
  `AUTHORIZATION_DECISION` evidence. Until Authorization Authority is live,
  this is a compatibility boundary and not self-verifying authority.
- Actor Context evidence is required for every mutation.
- Events are persisted in a local producer outbox. Event Delivery Service will
  own delivery/replay later.
- Hard deletion is not exposed. Terminal states remain auditable.

## Local test

```bash
PYTHONPATH=services/organization-domain-service:packages/leos-contracts/src \
  python3 -m unittest discover services/organization-domain-service/tests
```

## Rollback

Before production migration, rollback is source removal plus deleting the
service-local SQLite database. After production migration, exported canonical
records, history, transitions, and outbox entries must be preserved before any
rollback.
