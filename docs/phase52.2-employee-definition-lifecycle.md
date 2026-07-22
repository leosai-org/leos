# Phase 52.2 — Employee Definition and Lifecycle

Phase 52.2 makes `employee-registry` the canonical employee-definition and lifecycle authority.

## Canonical definition

Every employee has a durable v2 definition covering identity, role, department, capabilities, resource policy, schedule, priority, model/provider preferences, runtime, limits, permissions, memory, adapters, and metadata.

## Lifecycle

```text
draft -> validated -> active -> paused -> active
                    |         |          |
                    +-------> disabled --+
                    |                    |
                    +----------------> archived
```

`archived` is terminal. DELETE requests are implemented as auditable archive transitions.

## Execution gating

The scheduler checks `leos.employee-execution-eligibility.v1` before resource admission and rechecks it before a leased job may enter `running`. Paused and out-of-window employees remain queued. Disabled, archived, or missing employees are rejected. Registry failures are fail-closed.

## Resource integration

Activation requires successful synchronization of the employee's canonical resource profile into `employee-resource-profile-service`. Pausing, disabling, and archiving disable the profile on a best-effort basis; scheduler lifecycle enforcement remains authoritative even if the resource service is temporarily unavailable.

## Primary API

- `POST /employees/validate`
- `POST /employees`
- `POST /employees/{id}/validate`
- `POST /employees/{id}/activate`
- `POST /employees/{id}/pause`
- `POST /employees/{id}/resume`
- `POST /employees/{id}/disable`
- `POST /employees/{id}/archive`
- `PATCH /employees/{id}/assignments`
- `GET /employees/{id}/status`
- `GET /employees/{id}/history`
- `GET /employees/{id}/eligibility`
- `GET /employees/{id}/resource-profile`

Legacy `/employees/register`, heartbeat, operational patch, resolve, and agent import routes remain available.
