# LEOS v2 Work, Workflow, and Assignment Domain

## Status and scope

This document defines the logical, contract-governed target Work Domain for
LEOS 0.2.0 Developer Preview v2. It defines work intake, reusable workflow
structure, instantiated Jobs and Tasks, responsibility Assignment and
Delegation, dependencies, results, lifecycle evidence, retry intent, and
escalation intent.

Epic 7.0 does not introduce a production Workflow engine, Assignment Service,
queue, worker, planner, scheduler algorithm, persistence topology, endpoint,
migration, UI, employee selection, ranking, optimization, or execution path.
The schemas and `validate_work_domain` are deterministic conformance
artifacts. They do not authenticate, authorize, approve, verify, assign,
schedule, execute, persist, or mutate.

## Architectural goals

- Keep demand, reusable definitions, instantiated work, responsibility,
  execution, results, evidence, and scheduling distinct.
- Give each resource one identity, one owner, one revision, one lifecycle
  authority reference, and complete audit lineage.
- Preserve existing Scheduler, Persistent Runtime, Organization, Employee,
  Capability Manager, Dispatcher, Authorization, Approval, Artifact Trust,
  Secret, and Model Registry boundaries.
- Fail closed on stale revisions, unknown references, invalid transitions,
  scope expansion, cycles, cross-organization linkage, and missing evidence.
- Make every unresolved production authority conspicuous rather than letting a
  reference implementation become the de facto owner.

## Canonical concepts

| Concept | Meaning | Explicitly not |
|---|---|---|
| Work Request | Governed expression of demand from a requesting principal | Employee selection, authorization, approval, Job, or execution |
| Workflow Definition | Stable reusable blueprint identity | Running instance or Scheduler Job |
| Workflow Revision | Immutable, versioned workflow structure | Mutable run state or Job |
| Job | One instantiated body of work governed by Scheduler lifecycle | Reusable definition, Assignment, worker, or invocation |
| Task | One work unit within a Job or a standalone context | Assignment, execution, or provider selection |
| Assignment | Governed responsibility relationship between work and a target | Authorization, approval, schedule, execution, or successful acceptance |
| Delegation | Governed sub-allocation or transfer of responsibility with full lineage | Scope expansion, authority creation, or erasure of the source Assignment |
| Dependency | Revision-pinned readiness/structure constraint | Scheduling action |
| Result | Immutable outcome evidence linked to work and producer | Verification, closure, Artifact Trust, or lifecycle authority |
| Artifact link | Provenance-preserving association between a Result output and Artifact | Artifact publication or trust verification |
| State Transition | Evidence produced by the subject lifecycle authority | Caller-written state or event-derived authority |
| Retry Intent | Request for a distinct later attempt preserving prior attempts | Retry execution or audit reset |
| Escalation Intent | Request for governed higher-level attention | Reassignment, selection, or execution |

Work Request, Workflow Definition, Workflow Revision, Job, Task, Assignment,
Delegation, Dependency, Approval, Verification, Execution, Result, Artifact,
Event, and Schedule are never interchangeable.

## Identity, ownership, and revision

Every Work Domain document uses `managedIdentity`:

- `resource_type` and `resource_id` form canonical identity;
- `revision` pins the material state consumed by another record;
- exactly one `owner` is required;
- `creator`, `steward`, lifecycle authority, creation Actor Context,
  authorization evidence, audit identity, and timestamps remain distinct;
- Organization-scoped resources are owned by the containing Organization
  Principal; and
- references resolve by exact type, identity, and revision.

A state-changing revision is represented by a new document revision and
authority-produced transition evidence. Mutable aliases or display names do
not replace revisions. Published Workflow Revisions are immutable.

## Authority classification

| Concern | Classification | Boundary |
|---|---|---|
| Job definition/lifecycle | **ACCEPTED — Scheduler** | Target `job-definition.v1` adoption by the existing service is a later compatibility change. |
| Scheduling, leases, resource admission/release | **ACCEPTED — Scheduler** | Dependency and Workflow records never schedule. |
| Assignment durable projection/lifecycle | **ACCEPTED — Persistent Employee Runtime** | Assignment-decision origin remains separate and OPEN. |
| Work Request definition/acceptance | **OPEN** | An `OPEN:` example reference is not production authority. |
| Workflow Definition lifecycle | **OPEN** | No Lucy or Core Workflow engine is promoted by this epic. |
| Workflow Revision publishing | **OPEN** | Publication requires a future accepted owner. |
| Task definition/lifecycle | **OPEN** | No production Workflow or Task service is introduced. |
| Assignment proposal/selection decision | **OPEN** | Persistent Runtime stores the governed projection; it does not select. |
| Assignment acceptance | **OPEN** | Acceptance evidence is distinct from lifecycle storage. |
| Delegation lifecycle | **OPEN** | Delegation does not inherit authorization from Assignment. |
| Dependency validation/lifecycle | **OPEN** | Reference conformance is non-authoritative. |
| Result creation/lifecycle | **OPEN** | Producer identity is mandatory; validation does not attest it. |
| Completion transition | Job: **Scheduler**; Task: **OPEN** | Completion requires Result evidence. |
| Verification | **OPEN** | Approval Authority does not become general work verifier. |
| Closure | **OPEN** | Closure requires explicit authority evidence. |
| Cancellation | Job: **Scheduler**; all other work: **OPEN** | Cancellation preserves history. |
| Retry intent | **OPEN** | Assignment, cognitive, and execution retry remain distinct. |
| Escalation intent | **OPEN** | Escalation cannot create Assignment. |
| Employee-to-job and Team-to-job selection | **OPEN** | No scoring, ranking, matching, or optimization is present. |
| Public Assignment Service | **CONFLICTING / INVESTIGATE** | It receives no v2 authority. |
| Workflow engines and Planning continuation | **CONFLICTING / INVESTIGATE** | Lucy is donor evidence only. |
| Artifact linkage verification | **OPEN** | Artifact Trust verifies trust evidence, not work/output linkage truth. |

## Work Request

`leos.work-request.v1` records requesting and submitting principals, desired
outcome, requested deliverables, constraints, urgency, due window, policy and
capability requirements, optional source evidence, state, and audit identity.
Acceptance and conversion require explicit transition evidence; conversion
also pins the resulting Job. The request cannot identify an Employee, select
a capability implementation, authorize, approve, verify, or execute itself.

## Workflow Definition and immutable Revision

The Definition carries stable identity, description, semantic version,
current exact Revision, policy references, and definition lifecycle.

The Revision carries immutable versioned structure:

- step identities and task-template evidence;
- required capabilities and expected outputs;
- approval and verification declarations;
- retry and cancellation constraints;
- branch-condition evidence;
- revision-pinned definition linkage;
- dependency edges and join declarations;
- entry and completion criteria;
- parallelism declaration; and
- compensation policy references.

Step identifiers are unique. Non-informational dependencies form an acyclic
graph and may reference only steps in that exact Revision. A published
Revision never becomes a running instance.

## Job and Task

The Scheduler-owned Job target records an optional accepted Work Request,
optional exact Workflow Definition/Revision pair, objective, responsible
Organization scope, priority, due window, policies, capability requirements,
expected outputs, governance, assignment constraints, Result references,
verification evidence, and closure evidence.

A Task records its optional parent Job and exact workflow step, objective,
inputs, outputs, dependencies, capability requirements, assignment
constraints, governance, retry limit, escalation policy, Results,
verification evidence, and closure evidence. A Task may exist without an
Assignment. Neither Job nor Task performs capability resolution or execution.

## Assignment and participation

`leos.work-assignment.v1` gives responsibility for one exact Job or Task
revision to a Principal, Employee, Team, or Position target. Runtime is not an
accepted target in v1. The record separates:

- assigning principal;
- externally governed assignment-decision evidence;
- assignment reason;
- optional Role and Position context;
- exact accepted work scope;
- effective period;
- lifecycle state;
- acceptance requirement/state/evidence;
- exclusive-assignment constraint; and
- superseded Assignment lineage.

The target type must be allowed by the work definition. Active exclusive
responsibility cannot have multiple active assignees. Reassignment and
replacement preserve the prior Assignment. Assignment does not grant
permission, approval, capability eligibility, schedule, lease, provider/tool
selection, or execution.

Requested by, submitted by, created by, owned by, stewarded by, assigned by,
assigned to, delegated by, delegated to, accepted by, performed by, completed
by, approved by, verified by, closed by, cancelled by, and escalated by are
different relationships. Position hierarchy remains the supervisory
hierarchy. A Team is a collaboration/responsibility target, never an
execution authority.

## Delegation

Delegation pins the source Assignment, delegating and delegate targets, exact
delegated work scope, reason, kind, retained responsibility, effective period,
acceptance, lifecycle, parent chain, and supersession.

Root delegation begins with the source assignee. Child delegation begins with
the parent delegate and preserves the same source Assignment. Delegated scope
must be a subset of accepted Assignment scope. Cross-organization delegation,
scope expansion, target cycles, parent cycles, and source responsibility
erasure fail closed. Delegation cannot create authorization, approval,
capability eligibility, or execution authority.

## Dependency and readiness

Workflow-step and Work Dependency edges support finish-to-start,
start-to-start, finish-to-finish, blocking, informational, and conditional
relationships plus required/optional joins. Edges are revision-pinned,
same-Organization, known, non-self-referential, and acyclic. Informational
edges do not block readiness. A Task cannot truthfully be `READY` while an
active required predecessor remains unsatisfied.

Dependencies constrain declared structure/readiness only. Scheduler alone
owns Job scheduling and resource admission.

## Lifecycle rules

The schemas define minimum coherent state vocabularies. The deterministic
validator checks allowed transitions against the exact resulting subject
revision and lifecycle authority.

- Work Request: `DRAFT → SUBMITTED → UNDER_REVIEW → ACCEPTED/REJECTED`,
  with governed withdrawal, conversion, and closure paths.
- Workflow Definition: `DRAFT → ACTIVE → DEPRECATED/RETIRED`.
- Workflow Revision: `DRAFT → PUBLISHED → SUPERSEDED/REVOKED`.
- Job/Task: draft, ready, active, blocked, paused, completed, failed,
  cancelled, awaiting verification, verified, and closed.
- Assignment/Delegation: proposed, active, suspended where applicable,
  completed, superseded, revoked, expired, or cancelled. Acceptance is a
  separate nested state.

Terminal states do not silently reopen. Reopening, if later required, needs an
accepted authority decision and new contract semantics. Cancellation,
supersession, reassignment, retry, and delegation preserve prior identities
and history.

## Approval, verification, completion, and closure

Work may declare approval and verification requirements. Approval Authority
remains the only issuer/verifier of approval grants. References or caller
Booleans cannot satisfy approval.

Completion requires Result evidence. Verification is a later governed
confirmation and its production authority remains OPEN. Closure is later
still and requires explicit closure-authority evidence. A completed object can
therefore remain unverified; a verified object can remain unclosed.

## Results and Artifacts

`leos.work-result.v1` requires an immutable identity, exact work revision,
producing principal, optional producing Assignment, optional execution
reference, outcome, summary, deliverables, Artifact links, evidence, and
completion time.

A successful Result must account for every required output. When an Employee
Assignment is referenced, the producing principal must match that Employee.
Artifact links preserve Artifact identity/revision, Organization, output,
producer, and provenance. They do not publish an Artifact or attest trust.
Artifact Trust Authority retains only its accepted trust-verification
boundary; generic Artifact lifecycle and work-link verification remain OPEN.

## Retry, escalation, failure, and cancellation

Retry Intent identifies the work, retry class, reason, prior attempt
identities, distinct requested attempt identity, policies, and status.
`preserves_history` is mandatory. It does not perform a retry.

Escalation Intent identifies work, optional source Assignment, escalating
principal, target, reason, policies, and status. `creates_assignment` is
always false. A separately authorized assignment decision is required to
change responsibility.

Failure, cancellation, pause, resume, blocking, partial completion,
supersession, and abandonment are lifecycle facts written only by the owning
authority. They never erase Results, attempts, Assignments, Delegations, or
transition history.

## Capability and execution boundaries

Work declares capability requirements only:

1. a governed reasoning or orchestration owner decides to act;
2. Capability Manager evaluates inventory, bindings, eligibility, and
   first-ranked-valid resolution;
3. Dispatcher alone invokes the resolved provider/tool target;
4. adapters transport without selection; and
5. Result records the governed work outcome and lineage.

Work, Assignment, Delegation, Team, Workflow, and the reference validator do
not rank providers, select implementations, authorize capability use, invoke
Dispatcher, or bypass Capability Manager.

## Reference validator boundary

`validate_work_domain` accepts an in-memory snapshot and checks schema and
cross-object consistency. It is deterministic, side-effect free,
non-authoritative, non-production, and removable without migration. It has no
network, persistence, credential, scheduling, selection, approval,
verification, execution, or mutation path. `DEVELOPMENT_FIXTURE` records must
declare `authoritative: false` and `production_eligible: false`.

## Lucy donor evidence and migration

Lucy Workflow Engine variants, Planning Engine, Task Dispatcher, Job
Execution Bridge, Assignment Service, and related continuations contain donor
concepts such as templates, steps, dependencies, artifacts, retry counters,
and correlation. They also overlap accepted Scheduler, Persistent Runtime,
Capability Manager, Dispatcher, and Approval boundaries.

No Lucy service, database, event, caller Boolean, score, token, or runtime
state is authoritative. A future production epic must inventory callers and
data, select accepted OPEN authorities, adopt target contracts deliberately,
migrate exact identities/revisions/history, run compatibility tests, and
retire conflicting surfaces. Public Assignment Service remains
CONFLICTING / INVESTIGATE.

## Compatibility and future adoption

Existing Scheduler and Persistent Runtime APIs/storage are unchanged. The Job
and Assignment schemas are target contracts, not claims that those services
already emit them. Adoption requires explicit mapping and compatibility
epics. No database migration or release-authority artifact is part of Epic
7.0.

## Security properties

- Cross-Organization references fail closed.
- No raw secret or credential field is accepted.
- Evidence references are revision-pinned but never self-verifying.
- Assignment and Delegation never imply authorization or approval.
- Caller-generated state, completion, verification, closure, or selection is
  rejected.
- Full lineage is retained across cancellation, retry, reassignment,
  supersession, and delegation.

## OPEN questions

1. Which authority owns Work Request definition and acceptance?
2. Which authority owns Workflow Definitions and publishes immutable
   Revisions?
3. Which authority owns Task definition and lifecycle?
4. Which authority produces employee/team Assignment decisions?
5. Which authority owns Assignment acceptance and Delegation?
6. Which authority validates dependencies in production?
7. Which authority accepts Results and writes Task completion?
8. Which authority verifies and closes work?
9. Which authority creates Retry and Escalation intents?
10. How will Scheduler and Persistent Runtime adopt the target contracts?
11. What is the generic Artifact lifecycle and linkage-verification authority?
12. What migration/retirement path applies to Public Assignment Service and
    Lucy Workflow/Planning execution behavior?
