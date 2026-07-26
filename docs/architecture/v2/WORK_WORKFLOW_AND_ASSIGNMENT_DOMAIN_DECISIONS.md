# LEOS v2 Work, Workflow, and Assignment Domain Decisions

## ADR-WWAD-001: Work concepts remain distinct

- **Status:** Accepted
- **Decision:** Work Request, Workflow Definition, Workflow Revision, Job,
  Task, Assignment, Delegation, Dependency, Approval, Verification, Execution,
  Result, Artifact, Event, and Schedule are distinct objects and authorities.
- **Consequences:** No convenient field, service, event, or projection may
  absorb another concept's lifecycle.

## ADR-WWAD-002: Epic 7.0 is logical and contract-governed only

- **Status:** Accepted
- **Decision:** Epic 7.0 introduces canonical target schemas, examples,
  documentation, and deterministic reference conformance only.
- **Consequences:** No production Workflow engine, Assignment Service,
  persistence, API, queue, scheduler algorithm, worker, planner, UI, selection,
  or execution path is introduced.

## ADR-WWAD-003: Work resources are Organization-owned

- **Status:** Accepted
- **Decision:** Every Work Domain resource has one canonical identity, exact
  revision, one containing Organization, and that Organization Principal as
  owner.
- **Consequences:** Cross-Organization references fail closed. Transfer and
  collaboration policy remain OPEN.

## ADR-WWAD-004: Workflow Definitions are reusable identities

- **Status:** Accepted
- **Decision:** A Workflow Definition is a stable blueprint identity and never
  a running instance.
- **Consequences:** Runtime state belongs to instantiated Job/Task records and
  their accepted lifecycle authorities.

## ADR-WWAD-005: Workflow Revisions are immutable

- **Status:** Accepted
- **Decision:** Published Workflow Revisions are immutable, exact-revision
  structures with unique steps and acyclic dependencies.
- **Consequences:** Modification creates a new revision. Publication authority
  remains OPEN.

## ADR-WWAD-006: Scheduler remains Job authority

- **Status:** Accepted
- **Decision:** Scheduler owns Job identity/lifecycle and retains lease and
  resource-admission authority.
- **Consequences:** `job-definition.v1` is a target contract. Epic 7.0 does
  not migrate Scheduler APIs or storage, and Workflow/Task records do not
  schedule.

## ADR-WWAD-007: Tasks are work records, not execution

- **Status:** Accepted
- **Decision:** A Task is an Organization-scoped work unit that may exist
  without Assignment and cannot invoke providers/tools.
- **Consequences:** Task lifecycle authority remains OPEN. Capability
  requirements are declarations only.

## ADR-WWAD-008: Persistent Runtime stores Assignment projection

- **Status:** Accepted
- **Decision:** Persistent Employee Runtime retains accepted durable
  Assignment projection/lifecycle responsibility.
- **Consequences:** Assignment-decision origin and acceptance remain OPEN.
  Public Assignment Service remains CONFLICTING / INVESTIGATE.

## ADR-WWAD-009: Assignment grants responsibility only

- **Status:** Accepted
- **Decision:** Assignment records responsibility for exact work scope and a
  governed decision reference.
- **Consequences:** Assignment never grants authorization, approval,
  capability eligibility, scheduling, provider/tool selection, or execution.

## ADR-WWAD-010: Assignment targets exclude Runtime in v1

- **Status:** Accepted
- **Decision:** v1 targets are Principal, Employee, Team, or Position, subject
  to the work's assignment constraints.
- **Consequences:** Runtime targeting requires future accepted architecture.
  A Team remains collaboration/responsibility scope only.

## ADR-WWAD-011: Selection authority remains OPEN

- **Status:** Accepted
- **Decision:** Employee-to-job, Team-to-job, and other assignee selection,
  matching, ranking, scoring, and optimization remain OPEN.
- **Consequences:** Neither the schemas nor reference validator select targets.
  Capability Profiles do not become assignment policy.

## ADR-WWAD-012: Delegation preserves responsibility lineage

- **Status:** Accepted
- **Decision:** Delegation pins the source Assignment and may only delegate a
  subset of accepted scope while retaining prior responsibility records.
- **Consequences:** Delegation cannot create authority, bypass governance,
  erase its source, cross Organizations, or form a cycle. Production
  Delegation authority remains OPEN.

## ADR-WWAD-013: Dependencies constrain readiness, not scheduling

- **Status:** Accepted
- **Decision:** Revision-pinned, acyclic dependency graphs express structural
  and readiness constraints.
- **Consequences:** Scheduler remains the only scheduling/lease/resource
  authority.

## ADR-WWAD-014: Completion, verification, and closure are separate

- **Status:** Accepted
- **Decision:** Completion requires Result evidence; verification requires
  separately governed evidence; closure requires explicit authority evidence.
- **Consequences:** Approval Authority remains approval-only. Work
  verification and closure authorities remain OPEN.

## ADR-WWAD-015: Results preserve producer and Artifact lineage

- **Status:** Accepted
- **Decision:** Results pin work, producer, optional Assignment/execution,
  deliverables, Artifact Organization/producer/provenance, and completion time.
- **Consequences:** Result does not verify work or establish Artifact trust.
  Generic Artifact lifecycle/linkage verification remains OPEN.

## ADR-WWAD-016: Retry is intent with immutable history

- **Status:** Accepted
- **Decision:** Retry Intent points to prior attempts and a distinct requested
  attempt and always preserves history.
- **Consequences:** Assignment, cognitive, execution, and other retry scopes
  remain distinct; intent does not execute retry.

## ADR-WWAD-017: Escalation never silently assigns

- **Status:** Accepted
- **Decision:** Escalation Intent records a target and reason with
  `creates_assignment: false`.
- **Consequences:** Any responsibility change requires a separate governed
  Assignment decision and preserves previous Assignment.

## ADR-WWAD-018: Lifecycle state requires owner-produced evidence

- **Status:** Accepted
- **Decision:** The subject lifecycle authority produces state transitions
  against an expected revision and resulting revision.
- **Consequences:** Callers, Events, examples, schema validity, and projections
  cannot self-declare completion, verification, closure, or cancellation.

## ADR-WWAD-019: Approval remains external and verifiable

- **Status:** Accepted
- **Decision:** Work may declare approval requirements and retain verification
  references, but only Approval Authority can issue/verify grants.
- **Consequences:** Reference existence and caller Booleans never satisfy an
  approval gate.

## ADR-WWAD-020: Capability and execution authorities remain unchanged

- **Status:** Accepted
- **Decision:** Work declares capability needs; Capability Manager resolves;
  Dispatcher invokes; adapters transport.
- **Consequences:** Work, Workflow, Assignment, Delegation, Team, and the
  validator cannot select providers/tools, authorize execution, or invoke.

## ADR-WWAD-021: Reference conformance is non-authoritative

- **Status:** Accepted
- **Decision:** `validate_work_domain` deterministically checks a caller-
  supplied in-memory snapshot.
- **Consequences:** It has no persistence, mutation, authentication,
  authorization, approval verification, scheduling, selection, or execution
  authority and is removable without migration.

## ADR-WWAD-022: OPEN production authorities remain OPEN

- **Status:** Accepted
- **Decision:** Work intake, Workflow definition/publication, Task lifecycle,
  Assignment decision/acceptance, Delegation, Dependency, Result acceptance,
  Verification, Closure, retry-intent, and escalation-intent production owners
  are not assigned by Epic 7.0.
- **Consequences:** `OPEN:` example references are conspicuous placeholders,
  never authority. Implementation must stop for an accepted ADR.

## ADR-WWAD-023: Lucy and Public Assignment behavior are donor evidence

- **Status:** Accepted
- **Decision:** Lucy Workflow/Planning/Task/Assignment implementations and the
  public Assignment Service provide evidence only.
- **Consequences:** Their databases, APIs, tokens, scores, caller Booleans,
  direct execution, and continuation behavior receive no v2 authority.

## ADR-WWAD-024: Target contracts require explicit service adoption

- **Status:** Accepted
- **Decision:** Job and Assignment target schemas do not claim that Scheduler
  or Persistent Runtime currently expose those exact contracts.
- **Consequences:** API/storage mapping, data migration, compatibility, and
  retirement require later reviewed epics.

## Consolidated OPEN questions

1. Work Request definition and acceptance owner.
2. Workflow Definition and Revision publication owner.
3. Task definition and lifecycle owner.
4. Assignment decision, acceptance, and Delegation owners.
5. Dependency validation and Result acceptance owners.
6. Work verification, closure, retry-intent, and escalation-intent owners.
7. Scheduler/Persistent Runtime target-contract adoption.
8. Generic Artifact lifecycle and linkage verification.
9. Public Assignment Service and Lucy Workflow/Planning migration/retirement.
