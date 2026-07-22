# LEOS Reference Research and Content Employee

The reference employee is the first canonical Phase 52 employee implementation built on the RC8 lifecycle and runtime-resource authority.

It receives a governed goal, validates employee eligibility and an active resource reservation, creates a research plan, accepts evidence only through approved source adapters, produces a structured draft, submits that draft to an independent review-compatible gate, revises rejected output, persists a versioned artifact, and retains complete execution history.

The release implementation is provider-neutral and has no direct public-internet access. Source material is supplied in the execution request with provenance from an approved adapter such as `manual-source-input` or `company-knowledge-service`.

The deployment fragment attaches the service to the existing `ai-cloud-net` network for internal LEOS calls. It exposes no host port and does not grant public-internet research capability.

## Endpoints

- `GET /health`
- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/execute`
- `POST /runs/{run_id}/pause`
- `POST /runs/{run_id}/resume`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/recover`
- `GET /runs/{run_id}/history`
- `GET /runs/{run_id}/sources`
- `GET /artifacts/{artifact_id}`
- `POST /execute`

The `/execute` endpoint accepts the existing LEOS capability-provider envelope and returns the completed run and artifact.


## RC11 lineage

The service retains its RC8 lifecycle implementation lineage. In the RC11
source release, that historical origin is not a current release identifier; the
service is distributed and governed as part of the RC11 monorepo.
