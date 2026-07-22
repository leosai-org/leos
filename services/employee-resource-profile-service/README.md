# LEOS Employee Resource Profile Service

This service gives LEOS a resource-policy authority for AI employees.

It stores employee resource profiles, registers compute-node capacity,
evaluates priority-aware admission requests, creates reservations, returns
preemption plans for higher-priority work, and releases or expires capacity.

## Endpoints

```text
GET  /health
GET  /ready
POST /profiles
PUT  /profiles/{employee_id}
GET  /profiles
GET  /profiles/{employee_id}
POST /nodes
PUT  /nodes/{node_id}
GET  /nodes
GET  /nodes/{node_id}
POST /admission/evaluate
POST /reservations
GET  /reservations
GET  /reservations/{reservation_id}
POST /reservations/{reservation_id}/release
GET  /snapshot
```

## Scheduler sequence

1. The scheduler requests an admission decision.
2. The service evaluates CPU, RAM, GPU, VRAM, affinity, execution windows,
   concurrency, priority, and fallback profiles.
3. The scheduler creates an atomic reservation.
4. The runtime releases that reservation after completion.
5. Higher-priority work may request a preemption plan, but preemption is only
   committed when `commit_preemption=true` is explicitly supplied.

## Core tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
