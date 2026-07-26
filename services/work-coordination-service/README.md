# LEOS Work Coordination Service

The Work Coordination Service is the Dev Preview v2 production owner for the
Work Domain records assigned by Epic 8.1: Work Requests, Workflow
Definitions/Revisions, Tasks, Dependencies, assignment decisions,
same-Organization Delegation, Work Results, verification, closure, Retry
Intents, Escalation Intents, audit lineage, and its producer-local outbox.

It coordinates work; it does not schedule, lease, accept runtime assignment
projection, authorize, approve, resolve capabilities, invoke providers/tools,
own Employees or Organizations, hold secrets, or deliver events.

## Local development

```bash
docker build -f services/work-coordination-service/Dockerfile -t leos-work-coordination-service:test .
docker run --rm -p 8118:8118 leos-work-coordination-service:test
```

The default production adapters fail closed when Organization, Employee,
Scheduler, or Persistent Runtime evidence is unavailable. Tests inject
deterministic adapters; those adapters are not production authorities.
