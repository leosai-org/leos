# LEOS Dev Preview v2 Integration Architecture and Delivery Plan

## Status

**Target:** LEOS 0.2.0 Developer Preview v2

**Baseline:** Epic 7.0 accepted at
`25a0f17debebf376a1c02f15b2bf92733e5f6321`

**Branch at authoring:** `feature/v2-effective-ranking-resolution`

This document is the Epic 8.0 integration planning package. It defines the
shortest correct path from the accepted v2 foundational domains to a
production-shaped, locally runnable Dev Preview v2.

It is planning and architecture only. It does not implement production code,
does not assign authority rows that remain `OPEN`, and does not make Lucy or
legacy behavior authoritative.

## Executive summary

LEOS has a strong execution and domain-contract foundation, but it is not yet
an integrated product path. The current repository contains accepted contracts
and partial production services for the execution spine, intelligence
resolution, employees, ranking, model facts, installation, first-run, operator
inspection, and security/observability. It also contains logical target
contracts for identity/trust, organization, capability/plugin/tool, and
work/workflow/assignment domains.

The shortest correct Dev Preview v2 path is not to add a new parallel
orchestrator that owns everything. The path is to accept a small number of
missing production authorities, adopt the target contracts into the existing
authoritative services, and add one governed integration layer that coordinates
work intake and workflow projection without taking scheduler, assignment,
reasoning, resolution, invocation, approval, secret, or artifact authority.

The biggest release blockers are:

- production Organization Domain service topology and storage;
- Work Request acceptance, Workflow Definition/Revision lifecycle, Task
  lifecycle, and workflow projection into Scheduler jobs;
- employee-to-job assignment decision and handoff into Scheduler/Persistent
  Runtime;
- Approval Authority durable API and fail-closed grant verification;
- Secret Authority backend, authorization, and transient injection;
- Artifact identity, linkage, result acceptance, verification, and closure;
- event outbox/replay/retention policy across authorities;
- operator/UI surfaces for the organization-first journey;
- retirement or isolation of legacy Assignment, Lucy Workflow/Planning, and
  catalog entries that conflict with accepted boundaries.

No existing code path currently satisfies the full target lifecycle from plain
language objective to Team Architect proposal, governed Work Request,
Workflow/Job/Task/Assignment, capability resolution, Dispatcher invocation,
approval wait, Result/Artifact linkage, verification, completion, closure, and
restart recovery.

## Files reviewed

Canonical architecture and roadmap:

- `AGENTS.md`
- `docs/architecture/v2/AUTHORITY_REGISTRY.md`
- `docs/architecture/v2/EXECUTION_PLANE.md`
- `docs/architecture/v2/EXECUTION_PLANE_DECISIONS.md`
- `docs/architecture/v2/EXECUTION_CONTRACTS.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE_DECISIONS.md`
- `docs/architecture/v2/IDENTITY_OWNERSHIP_AND_TRUST.md`
- `docs/architecture/v2/IDENTITY_OWNERSHIP_AND_TRUST_DECISIONS.md`
- `docs/architecture/v2/ORGANIZATION_DOMAIN.md`
- `docs/architecture/v2/ORGANIZATION_DOMAIN_DECISIONS.md`
- `docs/architecture/v2/CAPABILITY_PLUGIN_AND_TOOL_DOMAIN.md`
- `docs/architecture/v2/CAPABILITY_PLUGIN_AND_TOOL_DOMAIN_DECISIONS.md`
- `docs/architecture/v2/WORK_WORKFLOW_AND_ASSIGNMENT_DOMAIN.md`
- `docs/architecture/v2/WORK_WORKFLOW_AND_ASSIGNMENT_DOMAIN_DECISIONS.md`
- `docs/roadmap/DEV_PREVIEW_V2_SCOPE_LOCK.md`
- `docs/roadmap/DEV_PREVIEW_V2_GOALS.md`
- `docs/roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`
- `docs/roadmap/LEOS_DEV_PREVIEW_V2_GAP_REPORT.md`

Contracts and examples reviewed by reference:

- `contracts/job-definition.v1.schema.json`
- `contracts/task-definition.v1.schema.json`
- `contracts/work-request.v1.schema.json`
- `contracts/workflow-definition.v1.schema.json`
- `contracts/workflow-revision.v1.schema.json`
- `contracts/work-assignment.v1.schema.json`
- `contracts/work-delegation.v1.schema.json`
- `contracts/work-result.v1.schema.json`
- `contracts/capability-resolution-result.v1.schema.json`
- `contracts/execution-result.v1.schema.json`
- `contracts/employee-definition.v3.schema.json`
- identity/trust, organization, capability/plugin/tool, work, model, ranking,
  installer, first-run, operator, and observability contract families under
  `contracts/`
- canonical examples under `examples/`

Production and reference service surfaces:

- `services/execution-scheduler-service/app/main.py`
- `services/persistent-employee-runtime-service/app/main.py`
- `services/employee-cognitive-service/app/main.py`
- `services/execution-dispatcher-service/app/main.py`
- `services/capability-manager-service/app/main.py`
- `services/employee-registry/app.py`
- `services/model-registry-service/app/main.py`
- `services/ranking-policy-service/app/main.py`
- `services/employee-resource-profile-service/app/main.py`
- `services/employee-builder/app.py`
- `services/assignment-service/app.py`

Deployment, operator, and installer evidence:

- `config/service-catalog.json`
- `config/operator-service-catalog.json`
- `config/first-run-runtime-catalog.json`
- `tools/installer_bootstrap.py`
- `tools/first_run.py`
- `tools/operator_cli.py`
- `tools/security_observability.py`
- `deploy/reference-research-content-employee.compose.yml`

Lucy donor evidence inspected only by path discovery:

- `../lucy-runtime-reference/workflow-engine`
- `../lucy-runtime-reference/planning-engine-service`
- `../lucy-runtime-reference/runtime-execution-coordinator-service`
- `../lucy-runtime-reference/persistent-employee-runtime-service`
- `../lucy-runtime-reference/capability-manager-service`
- `../lucy-runtime-reference/plugin-platform-service`
- `../lucy-runtime-reference/plugin-registry-service`
- `../lucy-runtime-reference/approval-service`
- `../lucy-runtime-reference/leos-console-developer-preview-v0.2`
- `../lucy-runtime-reference/leos-console-employee-experience-v0.1`

Lucy remains immutable donor evidence only.

## Current-state topology

| Service or surface | Current responsibility | Authoritative records owned today | Persistence and events | APIs observed | Dependencies | Gap to Dev Preview v2 |
|---|---|---|---|---|---|---|
| Scheduler | Job lifecycle, worker leases, resource admission/release, employee eligibility recheck | `scheduler_jobs`, `scheduler_workers`, `scheduler_leases`, terminal transitions, resource history | SQLite tables; local `scheduler_events`; best-effort kernel publish through `emit()` | `/workers`, `/workers/{id}/heartbeat`, `/jobs`, `/jobs/{id}`, `/schedule/tick`, `/jobs/{id}/running`, `/complete`, `/fail`, `/cancel`, `/resources/reconcile`, `/events` | Employee Registry, Employee Resource Profile Service, kernel event endpoint | Current Job model must adopt `leos.job-definition.v1`; event reliability and replay remain incomplete; employee-to-job selection is not owned here. |
| Persistent Employee Runtime | Durable employee presence, mailbox, memory/working state, assignment projection/transitions | `employees`, `employee_messages`, `employee_memory`, `employee_assignments`, assignment terminal transitions | SQLite tables; `employee_event_outbox`; local `employee_events`; kernel event publication | `/employees`, `/messages`, `/memory`, `/scheduler/sync`, `/assignments`, `/assignments/{id}/start`, `/complete`, `/fail`, `/cancel`, `/events` | Scheduler, Employee Registry, kernel event endpoint | Assignment target contract adoption is pending; assignment decision/acceptance remains `OPEN`; memory here is working state, not canonical knowledge. |
| Employee Cognitive Service | Cognitive run lifecycle, context assembly, reason/act/observe loop, execution result handling | `cognitive_runs`, `cognitive_attempts`, `cognitive_observations` | SQLite tables; no canonical global event outbox observed | `/runs`, `/runs/{id}/execute`, `/resume`, `/cancel`, `/tick`, `/runs/{id}` | Persistent Runtime assignment APIs, Dispatcher | Good execution-spine fit; needs production context/knowledge boundaries, approval waiting integration, and target contracts for run/checkpoint evidence. |
| Execution Dispatcher | Sole governed provider/tool invocation authority, capability resolution consumption, same-target retry, result normalization | `canonical_executions`, `canonical_invocation_attempts`, `execution_claims`, provider adapters | SQLite tables; durable claims and attempts; orphan recovery | `/execute`, `/executions`, `/executions/{id}`, `/contract`, `/adapters` | Capability Manager, provider/adapters | Needs Secret Authority, approval verification, sandbox/tool catalog integration, and production adapter onboarding. |
| Capability Manager | Provider/capability inventory, provider-capability bindings, eligibility, governed resolution | `providers`, `capabilities`, `provider_capabilities`, `canonical_resolutions` | SQLite tables; local events table | `/providers`, `/capabilities`, `/bindings`, `/providers/register-bundle`, `/resolve`, `/resolutions` | Ranking Policy, Model Registry | Must adopt target Capability/Provider contracts; capability grants and permission verification remain `OPEN`; no execution allowed. |
| Model Registry | Model facts and model-provider/runtime bindings | `models`, `model_runtime_bindings`, registry events | SQLite tables and local model registry events | `/models`, `/bindings`, `/events` | Capability Manager provider verification | Must integrate production runtime/model activation; exact activation owner remains `OPEN`. |
| Ranking Policy | User-authored ranking policies and effective ranking evidence | `rankings`, `ranking_events` | SQLite tables and local events | `/rankings`, `/rankings/{id}`, `/effective`, `/events` | Capability Manager effective ranking call | Good authority fit; organization/team policy interaction remains `OPEN`; PPT/cost/health cannot reorder. |
| Employee Registry | Employee definitions, lifecycle, eligibility, resource-profile synchronization | In-process lifecycle state and persisted employee/resource behavior through local files/service storage | Best-effort event bus publish | `/employees`, `/employees/{id}`, lifecycle endpoints, `/employees/{id}/eligibility`, `/resolve`, `/import/agents` | Employee Resource Profile, Event Bus | Employee v3 adoption pending; legacy `/resolve` selects employees and remains unresolved compatibility behavior. |
| Employee Resource Profile Service | Employee resource profile, node capacity, admission evaluation, reservations | Profiles, nodes, reservations | Service-local storage via helper module | `/profiles`, `/nodes`, `/admission/evaluate`, `/reservations`, `/snapshot` | Scheduler | Fits Scheduler admission input role; should not own scheduling or model/provider selection. |
| Employee Builder | Visual/YAML employee draft and hire flow | Builder instances, generated employee definitions | File-backed `/data/employee-builder/instances.json`; no accepted v2 organization/team authority | `/ui`, `/templates`, `/instances`, `/instances/{id}/hire` | Employee Registry | Useful advanced/manual surface; not organization-first Team Architect; emits Employee v2 shape. |
| Assignment Service | Legacy/public assignment/job service | Peer jobs, assignment state, employee load | Service-local persistence and best-effort events | Legacy assignment endpoints | Employee data/event surfaces | `CONFLICTING / INVESTIGATE`; must not gain v2 authority. |
| Installer and First Run tools | Installation plan/apply evidence and first-run configuration/readiness | Installation plan, transaction, manifest, first-run session/config/result | Files under target root; guarded write paths; no production runtime activation authority | CLI tools | Release authority files, config catalogs | Good baseline; runtime/model activation and service topology remain `OPEN`. |
| Operator tools | Status, doctor, service inventory, logs, backup/update plans, security/observability reports | Inspection and plan evidence only | Reads installation/state/config; produces reports | CLI tools | Operator catalogs, source authority | Current operator service catalog is stale relative to v2 service spine; UI surfaces are missing. |
| `config/service-catalog.json` | Catalog evidence for services | Non-authoritative catalog | JSON config | N/A | N/A | Contains conflicting capability string `capabilities.execute` for Capability Manager and legacy required services; must be reconciled before production readiness. |
| `config/operator-service-catalog.json` | Operator service inventory fixture/catalog | Non-authoritative catalog | JSON config | N/A | N/A | Older/thinner than current v2 topology; still lists Runtime Coordinator as required normal service. |
| Lucy workflow/planning/plugin/approval/console surfaces | Donor implementation evidence | None in v2 | Read-only evidence | N/A | N/A | Must be promoted, adapted, or retired only after explicit v2 authority decisions. |

## Target end-to-end lifecycle

The target path is:

```text
User objective
  -> Team Architect proposal
  -> Work Request
  -> Workflow Definition and Revision selection or creation
  -> Job
  -> Task
  -> Assignment or Delegation
  -> scheduling and leasing
  -> cognitive run
  -> capability request
  -> capability resolution
  -> dispatch
  -> provider/tool execution
  -> approval wait where required
  -> Result
  -> Artifact linkage
  -> verification
  -> completion
  -> closure
```

| Transition | Initiator | Authoritative owner | Input contract | Output contract | Persisted record | Event | Authorization and approval | Failure and retry | Audit evidence |
|---|---|---|---|---|---|---|---|---|---|
| User objective to Team Architect intake | Human actor through UI/operator | Identity plus Team Architect protocol owner `OPEN` | Actor Context, Organization Context, plain objective | Team Architect intake/proposal contract `MISSING` | Proposal draft `OPEN` | Proposal-created event by future owner | Authenticated actor required; no approval yet | Invalid/missing actor or organization fails closed | Actor, organization, objective digest, source channel |
| Proposal to reviewed Team configuration | Team Architect | Team Architect proposal/apply owner `OPEN`; Organization Domain for accepted resources | Proposal, Employee/Team/Capability/Workflow references | Review package `MISSING` | Review plan `OPEN` | Review-requested event by future owner | User review required for authority-bearing changes | Proposal edits invalidate affected approvals | Proposal revision, dependency plan, permission plan |
| Review to Work Request | Human or approved Team Architect apply coordinator | Work Request owner `OPEN` | `leos.work-request.v1` target plus Actor Context | Accepted Work Request transition `OPEN` | Work Request record | Work-request-accepted event | Authorization required; approval if policy requires | Rejection records reason; retry creates new transition/revision | Exact request revision and decision evidence |
| Work Request to Workflow Definition/Revision | Workflow intake/publication owner `OPEN` | Workflow Definition/Revision owner `OPEN` | Work Request, selected/published Workflow Definition, Workflow Revision | `leos.workflow-definition.v1`, `leos.workflow-revision.v1` | Definition and immutable revision | Workflow-revision-published or selected event | Authz for publish/select; approval when side effects or cost require | Invalid DAG or missing dependencies fails closed | Definition/revision IDs, dependency graph, validation evidence |
| Workflow Revision to Job | Workflow projection owner `OPEN`, calling Scheduler | Scheduler owns Job after creation | Workflow Revision, Work Request, Job target contract | Scheduler job record, target `leos.job-definition.v1` | Scheduler job row | Job-created event by Scheduler | Authz to submit job; no employee selection unless governed | Scheduler rejects invalid/duplicate job; idempotent create required | Correlation across work request, workflow, job |
| Job to Task | Task lifecycle owner `OPEN` | Task lifecycle owner `OPEN` | Workflow Revision step, Job reference | `leos.task-definition.v1` target | Task record | Task-created/ready event by future owner | Authz to materialize task | Invalid dependency blocks readiness, not Scheduler | Task/job/workflow revision lineage |
| Task to Assignment | Assignment decision owner `OPEN`; Persistent Runtime owns projection after handoff | Decision owner `OPEN`, then Persistent Runtime | Task/Job, employee candidates, Employee Registry eligibility | `leos.work-assignment.v1` target and runtime assignment projection | Assignment projection in Persistent Runtime | Assignment-created/accepted event by Persistent Runtime after adoption | Authz to assign; employee eligibility required; assignment never grants permission | Rejection or unavailable employee produces explicit transition; retry preserves history | Selection/acceptance evidence, employee revision |
| Assignment to Delegation | Employee or authorized coordinator | Delegation owner `OPEN` | Assignment scope, delegation target | `leos.work-delegation.v1` target | Delegation record | Delegation-created/accepted event | Authz and scope preservation; no cross-org unless accepted | Cycles, scope expansion, or cross-org fail closed | Full responsibility chain |
| Assignment to scheduling and lease | Persistent Runtime/Scheduler bridge | Scheduler | Assignment/Job reference and worker heartbeat | Lease and resource reservation | Scheduler lease/resource rows | Lease-acquired/resource-reserved by Scheduler | Employee eligibility and resource admission required | Lease expiry/retry under Scheduler policy; no assignment restart by coordinator | Job, lease, resource reservation IDs |
| Lease to cognitive run | Persistent Runtime and Cognitive Service | Cognitive Service owns run | Assignment projection | Cognitive run/attempt/checkpoint target `MISSING` | `cognitive_runs`, attempts, observations | Cognitive-run-started event `MISSING` | Cognitive run requires valid assignment projection | Cognitive retry is separate from assignment retry | Run, attempt, assignment, job correlation |
| Cognitive action to capability request | Cognitive Service | Cognitive Service for reasoning; Dispatcher for execution request | Context, capability request, correlation | Dispatch request using canonical execution contracts | Cognitive attempt and Dispatcher execution | Cognitive-attempt-dispatched | Authz and permission references passed, not self-verified | Cognitive retry may request another action; no direct provider call | Context digest, capability, run/attempt IDs |
| Capability resolution | Dispatcher calls Capability Manager | Capability Manager | `leos.capability-resolution-request.v1` | `leos.capability-resolution-result.v1` | Capability resolution row | Capability-resolution event by Capability Manager | Eligibility, ranking, permissions, approvals fail closed | Re-resolution is new governed resolution, not Dispatcher retry | Candidate dispositions and resolution ID |
| Dispatch and invocation | Dispatcher | Dispatcher | `leos.execution.v1` plus resolution ref | `leos.execution-result.v1` | Execution and attempt rows | Execution-started/completed event `MISSING` | Secret/approval verification required before side effects | Same-target idempotency-aware retry only | Attempt IDs, redacted payload evidence, provider operation ID |
| Approval wait | Capability Manager/Dispatcher/Cognitive Service observes pending state | Approval Authority owns grants/verifications | Approval request/grant/verification contracts | Verified grant or pending/denied result | Approval records `MISSING SERVICE` | Approval-requested/granted/verified events by Approval Authority | Explicit verified grant only | Expired/revoked/wrong-scope fail closed; resume after verified grant | Grant ID, verification result, consumed scope |
| Execution result to cognitive result | Cognitive Service | Cognitive Service | Execution result | Cognitive observation/result | Cognitive observation/result row | Observation/result event `MISSING` | No extra authority unless next action needs it | Ambiguous outcome pauses or requires governed recovery | Result status, attempt, normalized output refs |
| Cognitive result to Assignment terminal state | Cognitive Service requests runtime terminal transition | Persistent Runtime | Cognitive terminal result | Runtime assignment transition | Assignment terminal transition/outbox | Employee-assignment-completed/failed/canceled | Authz to mutate assignment; no scheduler mutation | Duplicate transition idempotent; conflicting terminal transition fails | Terminal transition ID and result ref |
| Assignment terminal to Job terminal | Persistent Runtime/Scheduler bridge | Scheduler | Assignment terminal evidence | Job completion/failure/cancellation | Scheduler terminal transition | Job-completed/failed/canceled | Authz to mutate job; resource release required | Release/reconcile on restart; no duplicate external work | Job terminal transition, resource history |
| Result and Artifact linkage | Producer and future Artifact owner | Work Result owner `OPEN`, Artifact owner `OPEN` | Execution/cognitive/assignment output refs | `leos.work-result.v1`, Artifact ref `OPEN` | Result and Artifact records | Result-created/artifact-linked events | Authz to publish/link; Artifact Trust verifies trust only | Failed artifact write preserves incomplete Result state | Digest, provenance, producer, org scope |
| Verification and closure | Human/verifier/policy authority `OPEN` | Verification and closure owner `OPEN` | Result, Artifact, external outcome evidence | Verification/closure transition `MISSING` | Verification and closure records | Verified/closed event by owner | Approval is not verification; caller evidence never self-verifies | Rework creates new work/result lineage | Verifier, criteria, evidence, outcome |

## Authority-resolution table

| Authority | Classification | Blocking for Dev Preview v2 | Decision required | Options | Evidence | Compatibility, migration, and security impact | Recommendation | ADR required |
|---|---|---|---|---|---|---|---|---|
| Scheduler Job lifecycle, leases, admission | ACCEPTED | No | None | Keep Scheduler | `AUTHORITY_REGISTRY.md`, Scheduler code | Adopt target Job contract without moving authority | Keep | No |
| Persistent Runtime assignment projection | ACCEPTED | No | None | Keep Persistent Runtime | `AUTHORITY_REGISTRY.md`, Runtime code | Adopt target Assignment contract; preserve terminal outbox | Keep | No |
| Cognitive reasoning lifecycle | ACCEPTED | No | None | Keep Cognitive Service | `EXECUTION_PLANE.md`, Cognitive code | Add contract adoption and approval wait integration | Keep | No |
| Capability resolution | ACCEPTED | No | None | Keep Capability Manager | `EXECUTION_CONTRACTS.md`, conformance tests | Adopt target Provider/Capability contracts | Keep | No |
| Dispatcher invocation | ACCEPTED | No | None | Keep Dispatcher | `EXECUTION_PLANE.md`, Dispatcher code | Add Secret/Approval/Sandbox adapters | Keep | No |
| Ranking Policy | ACCEPTED | No | None | Keep Ranking Policy | `INTELLIGENCE_PLANE.md`, service code | Org policy must not add ranking precedence silently | Keep | No |
| Model Registry | ACCEPTED | No | None | Keep Model Registry | `INTELLIGENCE_PLANE.md`, service code | Runtime activation must feed bindings through accepted owner | Keep | No |
| Organization Domain production topology | OPEN | Yes | Service/module boundary, store, transaction/outbox, ownership transfer minimum | Single Organization Domain service; modular package inside existing registry; deferred no-service target | Epic 5 contracts; Scope Lock must-have 3 | Wrong choice creates duplicate org state and cross-org leaks | Create one Organization Domain service/module with one store and outbox for v2 | Yes |
| Work Request owner | OPEN | Yes | Who accepts and transitions Work Requests | New Work Intake/Workflow Coordinator; Organization Domain extension; Scheduler direct intake | Epic 7 target contracts | Direct Scheduler intake would make Work Request a Job and lose review | New Work Intake and Workflow Coordinator that owns intake/projection only | Yes |
| Workflow Definition/Revision owner | OPEN | Yes | Publication and revision lifecycle owner | Same Work Intake/Workflow Coordinator; separate Workflow Authority; Team Template publisher | Epic 7 and roadmap | Separate generic workflow engine can steal scheduler/assignment authority | Work Intake/Workflow Coordinator owns definitions/revisions/projection only | Yes |
| Task lifecycle owner | OPEN | Yes | Task creation/state owner | Work Coordinator; Scheduler; Persistent Runtime | Epic 7 says Task is not execution or assignment | Scheduler ownership would collapse Task and Job | Work Coordinator owns Task records; Scheduler owns Job only | Yes |
| Assignment decision and acceptance | OPEN | Yes | Who proposes/selects employee and how handoff occurs | Work Coordinator from explicit assignment; Team Architect proposal; Employee Registry legacy `/resolve`; Scheduler worker match | Authority Registry row 119, legacy conflict | Legacy scoring/caller force is unsafe; Scheduler selection would mix leases with workforce policy | Dedicated assignment-decision protocol owned by Work Coordinator or accepted Assignment Authority, with Persistent Runtime projection | Yes |
| Delegation lifecycle | OPEN | Medium | Who records delegation acceptance and scope | Work Coordinator; Persistent Runtime extension | Epic 7 contracts | Premature implementation can expand scope or authorize implicitly | Defer full delegation except same-organization recorded responsibility in v2 if needed | Yes if implemented |
| Approval Authority durable service/API | OPEN | Yes | Durable request/grant/verify/consume, approver policy, notification | Promote/adapt Lucy approval; new minimal Approval service; UI-only approval | Identity/trust contracts; Lucy donor service exists | UI-only approval would reintroduce caller trust | Minimal Approval Authority service with explicit verification and consumption | Yes |
| Secret Authority backend/resolution | OPEN | Yes for cloud/tools | Backend, authorization, transient injection, redaction | Local encrypted store; OS keyring; environment-only forbidden for production | Secret Reference contracts; First Run catalogs | Bad choice leaks credentials and makes cloud unsafe | Minimal local Secret Authority with opaque refs and per-operation leases | Yes |
| Artifact lifecycle and Work Result acceptance | OPEN | Yes | Generic artifact owner, result issuer/acceptor, linkage verifier | Artifact service; Work Coordinator-owned local artifact records; Dispatcher-owned outputs | Work Result contracts, Artifact Trust boundary | Without owner, outputs cannot be audited or reopened safely | Minimal Artifact/Result Authority or Work Coordinator submodule with exact boundaries | Yes |
| Verification and closure | OPEN | Yes | Who verifies results and closes work | Human review/Work Coordinator; Approval Authority; Scheduler | Epic 7 separates completion, verification, closure | Approval Authority must not become verification authority | Work Coordinator records verification/closure decisions using external evidence | Yes |
| Event outbox/broker/replay | OPEN | Yes | Outbox, ordering, ack, replay, retention | Per-service outbox plus lightweight event bus; current best-effort; central event store | Runtime has outbox; Scheduler/Registry/Catalogs vary | Best-effort loses restart/recovery evidence | Require per-authority outbox and replayable events before release gate | Yes |
| Plugin lifecycle | OPEN | Not first vertical path unless Team Template needs install | Publish/install/activate/update/rollback owners | Defer broad plugin platform; minimal installed-core capabilities | Epic 6 contracts | Full plugin system is large; bypassing it creates future rework | Implement minimal local install/activate lifecycle before public plugin SDK | Yes |
| Tool catalog lifecycle | OPEN | Yes for real tools | Catalog owner and Dispatcher adapter ingestion | Capability Manager owns tool catalog? new Tool Registry? plugin installer feeds Dispatcher | Epic 6 separates Tool from Capability | Capability Manager must not invoke; Tool Runtime must not bypass Dispatcher | Minimal Tool Catalog authority feeding Dispatcher adapters | Yes |
| Sandbox/workspace lifecycle | OPEN | Yes for side effects | Workspace owner and isolation policy | Dispatcher-owned execution workspace; separate Sandbox Authority | Scope Lock must-have 10 | No sandbox means tools can side-effect silently | Minimal Sandbox/Workspace Authority or Dispatcher-owned bounded workspace for Dev Preview | Yes |
| Team Template lifecycle | OPEN | Yes for flagship path | Template publish/install/simulate/activate/rollback | Work/Organization coordinator; plugin/publishing authority | Roadmap mandatory Team Template | Template must not self-grant or self-activate | Minimal Team Template Authority after Org/Work/Plugin foundations | Yes |
| Team Architect apply protocol | OPEN | Yes | Proposal/apply handoff and durable coordination owner | Team Architect as Employee plus Work Coordinator; UI wizard only | Roadmap must-have 15 | AI cannot become publisher/approver/installer | Team Architect produces proposal; Work/Template/Org authorities apply after review | Yes |
| Memory/knowledge/artifact taxonomy | OPEN | Medium to high | Storage owners and retrieval authority | Defer to Phase 5/6 after work path; minimal provenance refs | Scope Lock must-have 11 | Too early can leak cross-org knowledge | Add only exact provenance refs in early work path | Yes |
| Runtime/model activation | OPEN | Yes for install-first path | Desired/observed topology and rollback owner | First Run coordinator plus Model Registry; new Runtime Activation service | First Run is coordinator-only | First Run cannot own ongoing activation | Minimal Runtime Activation Authority before production model onboarding | Yes |
| Budget/cost/PPT authority | OPEN / observational | Not initial blocker | Cost accounting owner and outcome evidence | Observability module; Work Coordinator reporting | ADR-IP-022/023 and Scope Lock | PPT cannot influence selection/retry | Defer PPT selection; add cost evidence fields only after result/outcome owners | Yes when implemented |
| Public Assignment Service | CONFLICTING | Yes if kept in path | Retire, adapter, or quarantine | Retire; compatibility facade; migration adapter | Authority Registry conflict | Keeping it risks peer job/assignment authority | Quarantine then retire; no new v2 behavior | Yes |
| Lucy Workflow/Planning/Coordinator | DONOR EVIDENCE / CONFLICTING where overlapping | No if isolated | Promote, adapt, or retire | Inspect per future epic | Lucy paths exist | Blind promotion imports conflicts | Use as donor evidence only after accepted owner decisions | No for this plan; yes for promotion |

## Contract adoption matrix

| Service | Canonical target contract | Current internal model | Compatibility status | Adapter or migration | Adapter owner | Dual-read/write | Deprecation path | Target conformance tests |
|---|---|---|---|---|---|---|---|---|
| Scheduler | `leos.job-definition.v1`, state transition evidence, event envelope | `scheduler_jobs`, legacy request fields, terminal transitions | Partial | Request/response adapter mapping Job target fields into current tables; idempotent job create | Scheduler | Temporary read adapter; avoid dual-write to peer Job store | Remove legacy fields after v2 clients migrate | Job create/list/get/terminal/resource/restart tests |
| Persistent Runtime | `leos.work-assignment.v1`, terminal transition evidence, working-state refs | `employee_assignments`, terminal transitions, messages, memory | Partial | Assignment projection adapter from canonical Assignment into runtime table | Persistent Runtime | Temporary projection read; no peer Assignment authority | Retire non-canonical assignment fields after migration | Assignment start/terminal/outbox/restart tests |
| Cognitive Service | Cognitive run/checkpoint/result target contracts `MISSING`; consumes `leos.execution-result.v1` | `cognitive_runs`, attempts, observations | Partial | Add explicit run/attempt/checkpoint envelopes and correlation | Cognitive Service | No dual-write needed if additive columns/docs | Retire implicit context/result shapes | Reason/act/observe, approval wait, restart tests |
| Execution Dispatcher | `leos.execution.v1`, `leos.execution-result.v1` | Canonical executions and attempts | Mostly aligned | Add Secret/Approval/Sandbox integration adapters | Dispatcher | No dual-write | Retire donor adapter shortcuts after plugin/tool onboarding | Same-target retry, no selection, secret redaction, approval verification |
| Capability Manager | `leos.capability-definition.v1`, `leos.provider-definition.v1`, `leos.capability-resolution-result.v1` | `providers`, `capabilities`, bindings, resolutions | Partial | Ingest target Provider/Capability contracts into current inventory | Capability Manager | Temporary import adapter; no parallel registry | Retire legacy provider/binding shape | First-ranked-valid, no unranked selection, approval pending, no execution |
| Model Registry | model facts, model runtime bindings | `models`, `model_runtime_bindings` | Mostly aligned | Runtime activation writes accepted bindings through Model Registry API | Model Registry and Runtime Activation owner | No dual-write | Retire activation fixture bindings | Model/binding lifecycle and no credential tests |
| Ranking Policy | effective ranking contract | `rankings`, effective response | Aligned for current scope | Organization policy integration must preserve precedence | Ranking Policy plus Org Policy owner | No dual-write | N/A | job > employee > capability > global, no PPT/health reordering |
| Employee Registry | `leos.employee-definition.v3` target | Employee v2 lifecycle plus legacy fields | Partial | v2-to-v3 migration and organization principal refs | Employee Registry | Limited dual-read v2/v3; single lifecycle store | Retire v2 creation once v3 adoption complete | Existing compatibility plus v3 org membership tests |
| Organization Domain | Organization, Department, Team, Role, Position, Membership, Occupancy contracts | No production service | Missing | Create production service/module after ADR | Organization Domain owner | No dual-write because no existing authority | N/A | Lifecycle, cross-org fail closed, owner/revision/event tests |
| Work Intake/Workflow Coordinator | Work Request, Workflow Definition/Revision, Task, Dependency, Result, Retry/Escalation intent | No production service; Lucy donor only | Missing | Create production coordinator with narrow projection role | Work/Workflow owner accepted by ADR | No permanent parallel models | Quarantine Lucy/Public Assignment paths | Intake/projection/restart/approval wait/result/closure tests |
| Approval Authority | approval request, grant, verification result | Contracts only; Lucy donor approval exists | Missing | Minimal durable API for request, decision, verify, consume | Approval Authority | No dual-write from caller refs | Reject caller booleans/opaque self-verification | Scope/expiry/revocation/replay/consumption tests |
| Secret Authority | secret reference and future use-lease/injection contracts | Secret Reference contract only | Missing | Minimal local backend and use authorization | Secret Authority | No raw secret migration | N/A | No secret persistence, redaction, authorization, rotation tests |
| Artifact/Result Authority | Artifact object `MISSING`, Work Result target | Work Result contract only; service-local paths | Missing | Add generic Artifact contract/service or Work-owned artifact module | Artifact owner accepted by ADR | No global path-as-ID dual-write | Migrate service-local artifacts into refs | Digest/provenance/linkage/verification tests |
| Installer/First Run | installer/first-run contracts | CLI tools and files | Partial | Feed accepted Runtime Activation, Secret, Model Registry, Organization bootstrap APIs | First Run coordinator plus target authorities | No first-run authority store | Keep coordinator-only evidence | Clean install/restart/rollback/no secret tests |
| Operator/UI | status/doctor/operator contracts | CLI; employee-builder UI; no organization-first UI | Partial/missing | Add operator API/UI consuming canonical services only | Operator surface | Read projections only | Retire stale catalog entries | UI journey, audit, health, failure correction tests |

## Persistence and event design

Dev Preview v2 must use one authoritative store owner per record type:

| Record type | Authoritative storage owner |
|---|---|
| Principal, Actor Context issuance, subject bindings | Identity Authority |
| Organization, Department, Team, Role, Position, Membership, Occupancy | Organization Domain Authority |
| Employee definitions and lifecycle | Employee Registry |
| Employee presence, mailbox, working state, assignment projection | Persistent Employee Runtime |
| Work Request, Workflow Definition/Revision, Task, Dependency, retry/escalation intent | Work Intake/Workflow Coordinator after ADR |
| Job, lease, resource admission, resource release | Scheduler |
| Cognitive run, attempt, checkpoint, observation | Employee Cognitive Service |
| Capability, Provider, provider-capability binding, resolution | Capability Manager |
| Model facts and model-runtime/provider binding | Model Registry |
| Ranking policy and effective ranking evidence | Ranking Policy Authority |
| Execution, invocation attempt, normalized result | Execution Dispatcher |
| Approval request/grant/verification/consumption | Approval Authority |
| Secret reference and protected value lifecycle | Secret Authority |
| Artifact identity, digest, provenance, retention, linkage | Artifact owner `OPEN` |
| Verification and closure | Work verification/closure owner `OPEN` |

Required persistence rules:

- Every managed record has immutable identity, exactly one owner, revision
  evidence, Organization scope where applicable, and actor/correlation
  evidence for authority-bearing mutations.
- Mutable records use revisioned state transitions. Previous revisions remain
  audit-addressable and are not overwritten as if history did not exist.
- Create and transition APIs accept idempotency keys for externally initiated
  operations. Idempotency keys are scoped to actor, Organization, resource,
  operation, and request fingerprint.
- Events are emitted by the authority that owns the represented transition.
  Events are notifications and replay material, not canonical state.
- Every authority that publishes release-path events needs an outbox or
  equivalent durable publish/retry mechanism. Persistent Runtime already has
  `employee_event_outbox`; Scheduler and several registry services currently
  rely on local events or best-effort publication and need hardening.
- Event ordering is guaranteed only per source authority and resource unless a
  future event-broker ADR accepts stronger ordering.
- Consumers build projections that can be rebuilt from canonical state and
  replayed events.
- Restart recovery must reconcile in-flight Scheduler leases, resource
  reservations, Persistent Runtime terminal transitions, Cognitive claims,
  Dispatcher in-flight attempts, approval waits, secret leases, sandbox
  workspaces, and artifact writes.
- Organization isolation is enforced at write time and read time. Cross-
  Organization references fail closed unless a future collaboration protocol is
  accepted.
- Retention policy must distinguish canonical state, audit evidence, logs,
  secret-use evidence without secret values, artifacts, memory/knowledge,
  diagnostic bundles, and test fixtures.

No implementation technology is selected here beyond repository evidence that
current services use SQLite-backed FastAPI stores. SQLite remains acceptable
for bounded local Dev Preview services if each authority owns its own schema,
has migration/recovery tests, and can later migrate without changing authority
semantics. A central database may be introduced only by an ADR that preserves
per-authority ownership boundaries.

## Security and governance flow

Required end-to-end controls:

- Actor Context is issued by Identity Authority and verified by each
  authority-bearing service. A caller string or schema-valid Actor Context is
  not authentication.
- Organization Context is required for Organization-scoped resources and must
  be checked against resource ownership and membership evidence.
- Authorization Authority produces subject/action/resource/context decisions.
  Authorization does not rank, resolve, invoke, approve, or authenticate.
- Capability grants are distinct from Capability inventory. Capability Manager
  may consider verified permission/authorization evidence during eligibility,
  but inventory presence never grants use.
- Tool/model/cloud permissions are checked before resolution or invocation as
  appropriate. Cloud use requires explicit permission and a valid secret-use
  path.
- Secret records carry opaque references only. Secret values are resolved at
  invocation time through Secret Authority and are never written to source,
  fixtures, tests, events, logs, memory, prompts, execution results, or audits.
- Approval gates use Approval Authority. Caller booleans, opaque reference
  existence, copied grant JSON, and UI state do not authorize.
- Cancellation is scoped: Work cancellation, Job cancellation, Assignment
  cancellation, cognitive cancellation, execution cancellation, and sandbox
  cleanup are separate transitions with correlation.
- Retry is scoped and idempotency-aware. Assignment retry, cognitive retry,
  Dispatcher same-target retry, Capability Manager re-resolution, and
  escalation are distinct.
- Artifact publication/linkage requires a future Artifact owner. Artifact
  Trust Authority verifies trust evidence only and cannot publish, install,
  activate, grant, or execute.
- Audit records expose decisions, inputs, revisions, and limitations. They do
  not replace canonical state.

Known bypass risks to close:

- `services/assignment-service/app.py` can act as a peer job/assignment store
  and selection surface.
- Employee Registry legacy `/resolve` can select an employee through legacy
  assignment behavior.
- `config/service-catalog.json` currently describes Capability Manager with
  `capabilities.execute`, which contradicts the accepted no-execution
  boundary.
- Runtime Coordinator catalog capabilities include execute/submit/lease
  reconcile behavior that is forbidden for its v2 observation-only role.
- Employee Builder can hire Employee v2 definitions without the future
  Organization/Team/Team Architect review path.
- Current operator catalogs do not reflect the complete accepted v2 spine and
  still imply older required services.

## Team Architect integration plan

The first production-shaped Team Architect is a governed core Employee plus an
apply protocol, not a super-service.

Required Dev Preview v2 capabilities:

- accept a plain-language outcome within an Organization;
- propose Employee roles, Team structure, capability needs, model/tool
  requirements, memory scope, schedules, approval gates, and estimated cost;
- explain dependencies, permissions, cloud/network use, secrets, resource
  needs, sandbox requirements, and risks in human language;
- produce a reviewable, revisioned proposal using canonical Organization,
  Employee, Team, Capability, Tool, Work, approval, and governance structures;
- run deterministic validation and side-effect-controlled simulation;
- save accepted output as a reusable Team Template;
- hand off apply operations to the relevant authorities after explicit user
  review and verified approvals.

Team Architect must not:

- publish, install, activate, approve, verify, authorize, issue secrets,
  resolve providers, invoke tools/models, mutate Scheduler jobs, own
  assignments, or close work;
- self-declare productive value or use PPT as ranking/resolution input;
- keep authority after its proposal is accepted.

Dev Preview v2 minimum:

- one local-first Team Architect proposal flow;
- one Team Template produced and saved from that flow;
- one deterministic simulation path with no undeclared side effects;
- one human review/apply path that creates Organization, Team, Employees,
  Workflow Definition/Revision, Work Request, Job/Task/Assignment, and
  approval gates through accepted authorities.

Deferrable without architectural rework:

- marketplace publishing;
- broad template library;
- automatic organization redesign;
- autonomous activation without human review;
- advanced cost/PPT optimization.

## Operator experience topology

Minimum Dev Preview v2 surfaces:

| Surface | Existing extendable surface | Missing production surface |
|---|---|---|
| Organization selection/create | None | Organization Domain UI/API client |
| Employee management | Employee Builder, Employee Registry APIs | v3 organization-aware editor and lifecycle UI |
| Team management | Organization Domain contracts only | Team/member/role/position management UI |
| Team Architect | None | Outcome intake, proposal review, simulation, apply |
| Work submission | Scheduler `/jobs` only; Work contracts | Work Request UI/API |
| Work lifecycle | Scheduler, Persistent Runtime, Cognitive, Dispatcher APIs | Unified projection across Work Request, Workflow, Job, Task, Assignment, Execution |
| Approvals | Contracts only; Lucy donor approval | Approval request/grant/verification UI |
| Results and Artifacts | Work Result contract; service-local outputs | Artifact/Result browser and verifier |
| Errors and audit history | Service-local events/logs; operator CLI | Cross-authority correlation view |
| System health | Operator CLI, security/observability tools | Updated v2 service catalog and UI |

The UI composes canonical APIs and projections. It owns no canonical domain
state. It may cache and display read models that are rebuildable from
authoritative services.

## Migration and compatibility plan

Recommended order:

1. Freeze legacy conflicting paths from receiving new v2 behavior. Keep Lucy
   and Public Assignment isolated.
2. Accept ADRs for Organization service topology, Work/Workflow owner,
   Assignment decision handoff, Approval service, Secret backend, Event
   outbox, Artifact/Result owner, Runtime Activation, and Team Architect apply
   protocol.
3. Implement Organization Domain production service/module and migrate
   Employee Registry toward `leos.employee-definition.v3` references.
4. Implement Work Intake/Workflow Coordinator with Work Request,
   Workflow Definition/Revision, Task, Dependency, Result, verification, and
   closure records. It submits jobs to Scheduler but owns no leases.
5. Adopt Scheduler Job target contract and Persistent Runtime Assignment
   target contract through adapters and migration tests.
6. Implement Approval Authority and integrate Capability Manager/Dispatcher/
   Cognitive waits with verified grants.
7. Implement Secret Authority and integrate Dispatcher with transient secret
   use.
8. Implement minimal Artifact/Result authority and sandbox/workspace boundary.
9. Implement Team Template lifecycle and Team Architect proposal/apply flow.
10. Update First Run, operator catalogs, local deployment topology, and UI to
    exercise the end-to-end path.
11. Run restart/recovery, migration/rollback, adversarial, and clean-install
    release gates.
12. Retire or quarantine legacy Assignment, old Runtime Coordinator behaviors,
    stale catalog capabilities, and Lucy-derived duplicates.

Backward compatibility:

- Maintain read compatibility for existing Employee v2 definitions during
  Employee v3 adoption.
- Expose Scheduler/Persistent Runtime adapters rather than parallel Job or
  Assignment stores.
- Use feature flags only to disable incomplete v2 flows, not to change
  authority semantics.
- Legacy APIs may remain as compatibility shims only when they cannot create
  or mutate canonical v2 state outside the accepted owner.

Rollback checkpoints:

- after each authority ADR and before code;
- after each new service schema migration;
- after each target-contract adapter;
- before enabling approval-gated or secret-backed side effects;
- before replacing operator/first-run catalogs;
- before retiring legacy/Public Assignment paths.

Removal conditions for legacy paths:

- canonical service exposes equivalent accepted functionality;
- migrations have exact source and target evidence;
- read-only compatibility window is documented;
- adversarial tests prove no peer authority remains;
- rollback or irreversible-change warning exists.

## Delivery roadmap

| Epic | Objective | Decisions required beforehand | Services affected | Contract changes | Production code changes | Migrations | Tests | Documentation | Acceptance criteria | Rollback point | Dependencies | Model tier | Effort |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8.1 Authority ADR pack | Accept blocking Dev Preview owners and forbidden overlaps | None | None | No schema changes unless ADR discovers defect | None | None | ADR uniqueness/docs refs | Authority Registry, decisions | No release-blocking owner is silently assigned; all blockers have accepted or deferred status | Source rollback | Epic 8.0 | Standard reasoning | M |
| 8.2 Organization Domain service | Implement logical Organization Domain Authority | Org topology, storage, events | New org service/module, Employee Registry references | Possibly no new schemas; adopt Epic 5 contracts | Service, persistence, API, outbox | New local store | Lifecycle, cross-org fail closed, ownership, restart | Service conformance | Org/Team/Role/Position/Membership/Occupancy lifecycle works locally | DB migration rollback | 8.1 | Strong coding | L |
| 8.3 Work Intake and Workflow Coordinator | Accept Work Requests, own Workflow/Task/Result projection, submit Scheduler jobs | Work owner, Task owner, assignment handoff, event outbox | New work coordinator, Scheduler adapter, Persistent Runtime adapter | Maybe transition/event contracts | Service, persistence, API | New store | Intake, DAG, idempotent submit, restart, no peer leases | Work integration docs | Work Request to Job/Task/Assignment projection works without stealing authority | Migration rollback | 8.1, 8.2 | Strong coding | XL |
| 8.4 Job and Assignment target adoption | Map Scheduler and Runtime to v2 target contracts | Contract adoption accepted in 8.1/8.3 | Scheduler, Persistent Runtime | Narrow adapter/example updates if needed | API adapters and storage migration | Existing store migration | Contract, terminal, resource, restart tests | Adoption guide | Existing spine emits/serves canonical Job and Assignment views | Reversible schema migration | 8.3 | Strong coding | L |
| 8.5 Approval Authority | Durable approval request/grant/verify/consume | Approval API, approver policy, notification minimum | New Approval service, Capability Manager, Dispatcher, Cognitive | Maybe no new schemas; use Epic 4 contracts | Service and integration | New store | Expiry, revocation, wrong scope, replay, pending/resume | Approval flow docs | Approval-required work pauses and resumes only with verified grant | Disable approval-gated flows | 8.1, 8.3 | Strong coding | L |
| 8.6 Secret Authority and sandbox | Local secret backend and bounded workspace for side effects | Secret backend, use lease, sandbox owner | New Secret service, Dispatcher, adapters/tools | Likely secret-use lease/sandbox contracts | Service, Dispatcher integration | New secure store/workspaces | Redaction, no secret persistence, cleanup, restart | Secret/sandbox docs | One local and one optional cloud provider path use explicit secret permission | Disable cloud/tool side effects | 8.1, 8.5 | Strong coding/security | XL |
| 8.7 Tool/Plugin minimum install path | Minimal local plugin/tool lifecycle feeding Capability Manager/Dispatcher | Plugin lifecycle, tool catalog, install/activation | Plugin/tool authority, Capability Manager, Dispatcher | May adopt Epic 6 target contracts | Install/activate APIs and adapter ingestion | New store | Install/activate/revoke/no permission implication | Plugin minimum docs | One governed tool installs, activates, resolves, dispatches safely | Disable plugin activation | 8.6 | Strong coding | XL |
| 8.8 Artifact/Result/verification | Store outputs, artifacts, result acceptance, verification, closure | Artifact owner, verification/closure owner | Work Coordinator, Artifact service/module, Dispatcher/Cognitive refs | Artifact contract may be needed | Service/module and API | New store | Digest, provenance, linkage, closure distinct | Artifact/result docs | Result/Artifact linked to work and verifiable without self-verification | Disable closure path | 8.3, 8.6 | Strong coding | L |
| 8.9 Team Template and Team Architect | First reusable Team Template and proposal/apply flow | Team Template and Architect apply protocol | Org, Work, Employee Registry, Capability, Approval, UI | Proposal/template contracts likely needed | Team Architect employee/config, template service/module, UI/API | New store | Proposal invalidation, simulation, apply, activation approval | Guided UX docs | Non-coder can create a team template and apply it locally | Disable apply; keep draft templates | 8.2-8.8 | Frontier coding/reasoning | XL |
| 8.10 Operator/UI and clean-install release path | Local guided UI/operator journey and deployment topology | Event/outbox, runtime activation final | UI/operator, First Run, installer, deployment | Operator catalog updates | UI/API composition, catalog/deploy updates | Config migration | Clean install, restart, recovery, update/rollback, audit | Release runbook | Reference journey passes without Lucy or manual hidden state | Revert catalogs/deploy | 8.2-8.9 | Strong coding/frontend | XL |

## Critical path

Shortest correct path:

1. Epic 8.1: accept the blocking authority ADRs.
2. Epic 8.2: production Organization Domain service.
3. Epic 8.3: Work Intake/Workflow Coordinator.
4. Epic 8.4: Scheduler/Persistent Runtime target-contract adoption.
5. Epic 8.5: Approval Authority.
6. Epic 8.6: Secret Authority and sandbox.
7. Epic 8.8: Artifact/Result/verification.
8. Epic 8.9: Team Template and Team Architect.
9. Epic 8.10: UI/operator/clean-install release path.

Parallelizable work:

- Operator catalog reconciliation can start after 8.1 but should not become
  release authority.
- Employee Registry v3 migration can run alongside Organization service once
  Organization references are live.
- Dispatcher adapter hardening can run alongside Secret/Sandbox work after
  authority decisions.
- Lucy donor inspections for approval, workflow, plugin, and console can run
  in parallel as read-only evidence.

High-risk integration points:

- Work Coordinator must not become a peer Scheduler, Runtime, Dispatcher, or
  Approval Authority.
- Assignment decision must not reuse legacy score/order/caller-force behavior.
- Approval resume must not rely on caller-provided grant refs.
- Secret injection must not persist credential material.
- Plugin/tool activation must not imply permissions or capability eligibility.
- Restart recovery must not duplicate provider side effects.
- Catalog updates must not reintroduce Capability Manager execution or Runtime
  Coordinator lease behavior.

Safely deferrable:

- hosted marketplace and billing;
- broad plugin ecosystem;
- cross-Organization collaboration;
- advanced PPT analytics;
- many Team Templates beyond one flagship;
- enterprise auth/federation;
- advanced memory/knowledge promotion.

Cannot defer without debt:

- accepted owners for blocking `OPEN` rows;
- Organization isolation;
- Work Request/Workflow/Task/Assignment handoff;
- approval verification;
- secret resolution for cloud/tools;
- artifact/result lineage;
- outbox/restart recovery;
- operator visibility into lifecycle/errors/audit.

## Deferred findings

- `config/service-catalog.json` still contains Capability Manager
  `capabilities.execute`, which contradicts the accepted no-execution
  boundary. This should be fixed in a catalog reconciliation epic, not in this
  planning epic.
- Runtime Execution Coordinator catalog capabilities still imply
  execute/submit/lease reconcile behavior. v2 limits it to observation/await.
- `config/operator-service-catalog.json` is stale and does not represent the
  current v2 execution/intelligence spine.
- Employee Builder is useful donor/advanced UI but creates Employee v2 records
  and does not implement the organization-first path.
- Public Assignment Service and Employee Registry legacy `/resolve` need a
  retirement or compatibility ADR before any Dev Preview v2 work uses them.
- Lucy console/workflow/planning/plugin/approval implementations may contain
  valuable donor code, but none are accepted source authority.

## Validation results

This plan was validated by repository inspection, not by production
execution. Required checks for this documentation package are:

- all cited repository paths exist;
- no lifecycle in this plan gives hidden selection, execution,
  authorization, verification, ranking, fallback, retry, or escalation
  authority to a non-owner;
- cross-Organization references remain fail-closed;
- restart and recovery are explicitly required;
- Team Architect uses canonical Employee, Team, Capability, Work, approval,
  and governance structures;
- no permanent duplicate models or stores are proposed;
- `git diff --check` passes.

## Remaining blockers

Dev Preview v2 implementation should not begin until at least these blockers
are resolved by accepted ADRs or scoped decisions:

1. Organization Domain service/module topology and persistence.
2. Work Intake/Workflow Coordinator ownership and exact forbidden overlaps.
3. Assignment decision/acceptance owner and Scheduler/Persistent Runtime
   handoff.
4. Approval Authority durable service/API and approver policy.
5. Secret Authority backend/use authorization/transient injection.
6. Event outbox/broker/replay/retention policy.
7. Artifact/Result owner and verification/closure authority.
8. Runtime/model activation owner.
9. Tool catalog/plugin installation/activation minimum lifecycle.
10. Team Template and Team Architect apply protocol.

## Proposed next epic

**Epic 8.1 - Dev Preview v2 Blocking Authority ADR Pack**

Objective:

Accept the minimum set of architecture decisions needed before implementation
can safely begin on the integration path.

Strict scope:

- `docs/architecture/v2/*_DECISIONS.md`
- `docs/architecture/v2/AUTHORITY_REGISTRY.md`
- `docs/roadmap/DEV_PREVIEW_V2_SCOPE_LOCK.md` only if a release-gate wording
  correction is required
- this integration plan only if accepted decisions change it

Likely files added or modified:

- new ADR entries for Organization topology, Work/Workflow owner, Assignment
  handoff, Approval service, Secret service, Event outbox, Artifact/Result
  owner, Runtime Activation, Plugin/Tool minimum lifecycle, and Team Architect
  apply protocol;
- `AUTHORITY_REGISTRY.md` rows changed only where an ADR explicitly accepts an
  owner or changes a blocker classification.

Explicit exclusions:

- no service code;
- no contracts/schemas unless an ADR exposes a blocking schema contradiction;
- no tests except documentation/ADR validation helpers if already present;
- no runtime configuration or deployment changes;
- no Lucy changes;
- no Public Assignment changes.

Required tests:

- documentation reference validation;
- ADR identifier uniqueness;
- authority registry consistency checks where available;
- credential-pattern scan;
- `git diff --check`.

Acceptance criteria:

- every decision needed by Epic 8.2 and Epic 8.3 is either accepted or
  explicitly deferred without blocking the shortest correct Dev Preview path;
- no previously `OPEN` authority is assigned without an ADR;
- all forbidden overlaps from Epics 3-7 remain forbidden;
- Public Assignment remains `CONFLICTING / INVESTIGATE` unless a dedicated ADR
  changes it;
- Lucy remains donor evidence only.

Rollback criteria:

- any ADR creates a duplicate Scheduler, Assignment, Dispatcher, Capability
  Manager, Approval, Secret, Organization, Artifact, or Workflow authority;
- any ADR permits hidden ranking, silent substitution, caller approval,
  capability-as-permission, or direct provider invocation by non-Dispatcher
  services;
- any registry row is changed without a traceable decision.

Recommended model tier:

- strong reasoning model for architecture review;
- frontier coding/reasoning model only if the ADR pack includes automated
  consistency validators.

## Proposed commit message

```text
docs(architecture): define dev preview v2 integration plan
```

## Exact staging command

```bash
git add docs/architecture/v2/DEV_PREVIEW_V2_INTEGRATION_PLAN.md
```
