# Phase 52.3 — Reference Research and Content Employee

Phase 52.3 provides the first complete canonical employee built on the RC8 employee lifecycle and runtime-resource authority.

## Governed flow

```text
Goal and approved sources
  ↓
Active employee eligibility
  ↓
Admitted resource decision and active reservation
  ↓
Research plan and evidence extraction
  ↓
Structured content draft
  ↓
Independent review-compatible gate
  ↓
Bounded revision when rejected
  ↓
Versioned approved artifact
  ↓
Persistent execution and artifact history
```

## Contracts

- `leos.reference-research-content-run.v1`
- `leos.research-source.v1`
- `leos.research-content-artifact.v1`
- `leos.reference-employee-history.v1`

The execution request embeds the canonical RC8 employee eligibility, resource admission, resource reservation, scheduler job, assignment, and execution identifiers. Mismatched or non-active governance records fail closed before source processing.

## Research boundary

The reference employee does not browse the public internet directly. It accepts source material only when the source provenance identifies an adapter listed in the employee's approved-adapter policy. The reference configuration approves manual source input and the local Company Knowledge Service.

Every source is content-hashed and retained with its adapter provenance. The final artifact includes visible citations, source hashes, review findings, artifact versions, and runtime lineage.

## Draft and review

The default output is a reviewable Markdown brief with Introduction, Background, Key Points, Considerations, Conclusion, and Sources sections. The deterministic release reviewer checks structure, evidence citations, word count, requirements, and unsupported absolute claims. A rejected draft enters a bounded revision loop and remains unapproved when the retry limit is exhausted.

External publication is not a capability of this employee and remains behind a separate human or policy approval gate.

## Service-network boundary

The employee joins the existing `ai-cloud-net` service network so the scheduler, registry, review, and persistence services can call its internal HTTP API. It publishes no host ports, does not use host networking, and does not perform public-internet research. The network is used only for governed LEOS service-to-service traffic.

## Restart recovery

Runs in planning, research, drafting, review, revision, or persistence states are marked `interrupted` when the service restarts. An interrupted run can be recovered from its stored request and governance envelope without losing its prior history.

## Deployment layouts

LEOS keeps separate Compose entry points for the writable project tree and immutable release trees because their canonical service paths differ:

- `deploy/reference-research-content-employee.compose.yml` builds from `../reference-research-content-employee` in the live project tree.
- `deploy/reference-research-content-employee.release.compose.yml` builds from `../services/reference-research-content-employee` inside a published release.

Both definitions preserve the same read-only root filesystem, dropped capabilities, no-new-privileges policy, named data volume, internal service network, and zero published host ports.

## Runtime dependency closure

The reference employee runtime is locked to the dependency set used by the
offline RC9 candidate image:

- `fastapi==0.116.1`
- `uvicorn[standard]==0.35.0`
- `pydantic==2.13.4`

Release validation requires the image metadata to match these exact versions.
The RC9 publication path may reuse the content-addressable RC8 dependency image
only after confirming the dependency versions, source hashes, routes, and
ephemeral SQLite initialization with networking disabled. A requirements file
and runtime image version mismatch is a release blocker rather than a warning.
