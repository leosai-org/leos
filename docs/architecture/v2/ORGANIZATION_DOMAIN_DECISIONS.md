# LEOS v2 Organization Domain Decisions

## Status

These ADR-style entries establish the accepted Epic 5.0 logical domain
foundation. Production service topology, persistence, policy, cross-
organization collaboration, and existing Employee Registry migration remain
explicitly **OPEN**.

## ADR-OD-001: One logical Organization Domain Authority owns structure

- **Status:** Accepted
- **Decision:** One logical Organization Domain Authority owns Organization,
  Department, Team, Role, Position, Membership, and Position Occupancy
  definitions, revisions, lifecycle, ownership, relationships, audit, and
  canonical transition events.
- **Context:** Separate first-to-persist services would create overlapping
  hierarchy, membership, and ownership truth.
- **Consequences:** Organization Intelligence and UI remain projections.
  Employee Registry remains separate Employee authority.
- **OPEN:** One-service versus modular deployment and persistence topology.

## ADR-OD-002: Organization is the isolation boundary

- **Status:** Accepted
- **Decision:** Every Department, Team, Employee, Role, Position, Membership,
  and Position Occupancy belongs to exactly one Organization and child
  resources are owned by that Organization Principal.
- **Context:** Ambiguous or shared organization scope risks knowledge, secret,
  permission, and audit leakage.
- **Consequences:** Cross-organization references fail closed.
- **OPEN:** Explicit cross-organization collaboration and delegation.

## ADR-OD-003: A v1 Organization has one human owner

- **Status:** Accepted
- **Decision:** A v1 Organization has exactly one Human User owner and binds
  one Organization Principal. Shared control is future authorization policy,
  not co-ownership.
- **Context:** User sovereignty requires a recoverable accountable owner while
  organization-to-organization ownership policy remains unresolved.
- **Consequences:** Owner arrays and implicit parent ownership are prohibited.
- **OPEN:** Ownership transfer, recovery, inheritance, and nested ownership.

## ADR-OD-004: Employee Registry remains Employee authority

- **Status:** Accepted
- **Decision:** Employee Registry remains canonical Employee definition and
  lifecycle authority. `leos.employee-definition.v3` is its organization-aware
  target contract; Epic 5.0 creates no peer Employee store or service.
- **Context:** The existing v2 definition mixes legacy department, manager,
  permission, ranking, runtime, and memory fields.
- **Consequences:** v2 remains compatibility input until an explicit
  non-destructive migration adopts v3.
- **OPEN:** Migration order, data mapping, API window, and rollback.

## ADR-OD-005: Employee concepts remain separate

- **Status:** Accepted
- **Decision:** Employee resource, Principal, configuration, membership,
  Position Occupancy, runtime presence/state, cognitive lifecycle, work
  Assignment, and Scheduler Job are distinct resources under their accepted
  authorities.
- **Context:** A single employee record otherwise becomes a hidden registry,
  runtime, scheduler, permission, and reasoning authority.
- **Consequences:** Organization Domain contracts contain no runtime,
  assignment, cognition, lease, or provider invocation state.

## ADR-OD-006: Membership is a governed relationship, not permission

- **Status:** Accepted
- **Decision:** Membership is an Organization Domain resource for User or
  Employee belonging to Organization or Team. It records lifecycle, effective
  period, issuer, Actor Context, authorization reference, Roles, revision, and
  audit.
- **Context:** Treating membership or Role as permission would bypass
  Authorization Authority and capability governance.
- **Consequences:** Membership and Role may be future policy inputs but never
  independently authorize execution.
- **OPEN:** Policy/grant owner and Membership-to-authorization integration.

## ADR-OD-007: Position and Position Occupancy are distinct from Employee

- **Status:** Accepted
- **Decision:** Position is a concrete structural slot. Position Occupancy is
  the separately revisioned relationship between one Position and one
  Employee. Neither is Employee identity or work Assignment.
- **Context:** Conflation makes vacancies, reorganization, and history
  impossible to represent safely.
- **Consequences:** One Position has at most one active Occupancy; ended and
  revoked Occupancies remain auditable.

## ADR-OD-008: Position hierarchy owns supervision

- **Status:** Accepted
- **Decision:** Canonical supervision is the acyclic
  `reports_to_position_ref` hierarchy. Employee manager views are projections
  through current Occupancy.
- **Context:** Legacy free-form Employee `manager` strings are unauthenticated,
  ambiguous, and cannot survive vacancy or reassignment.
- **Consequences:** Projections cannot mutate Position or Employee state.
- **OPEN:** Multiple reporting relationships and temporary delegation.

## ADR-OD-009: Organizational lifecycles are explicit and tombstoned

- **Status:** Accepted
- **Decision:** Organization structural resources use explicit draft, active,
  suspended, archived, and deleted states. Membership and Occupancy use their
  own explicit relationship lifecycles. Terminal records remain as audit
  history/tombstones.
- **Context:** Physical deletion or event-only state loses ownership,
  revocation, and causation evidence.
- **Consequences:** No implicit reactivation, cascade, or audit erasure.

## ADR-OD-010: Lifecycle transitions require external authority evidence

- **Status:** Accepted
- **Decision:** A completed transition records one Actor Context, a current
  Authorization Decision, verified Approval evidence when applicable,
  expected/resulting revision, canonical Event, rollback behavior, and child
  behavior.
- **Context:** A caller transition request, Boolean, Role, Membership, or
  schema-valid record cannot authorize itself.
- **Consequences:** Stale revision and unavailable authority fail closed.
- **OPEN:** Approval policy and atomic production transition protocol.

## ADR-OD-011: Team is collaboration only

- **Status:** Accepted
- **Decision:** Team owns no scheduling, assignment, reasoning, ranking,
  resolution, provider/tool, invocation, approval, secret, or policy
  authority.
- **Context:** Organization-first UX must not create a parallel execution
  plane.
- **Consequences:** Team layers later submit separately governed work through
  canonical authorities.

## ADR-OD-012: Organization policy references do not establish policy

- **Status:** Accepted
- **Decision:** Organization Domain resources may retain revisioned policy
  references, but Epic 5.0 does not assign policy ownership, inheritance,
  permission, or ranking scope.
- **Context:** Organizational policy is still an explicit architecture gap.
- **Consequences:** Existing ranking remains
  `job > employee > capability > global`; restrictions cannot reorder.
- **OPEN:** Policy authority, language, inheritance, conflict, and enforcement
  integration.

## ADR-OD-013: Cross-organization references fail closed

- **Status:** Accepted
- **Decision:** Department, Team, Employee, Role, Position, Membership, and
  Occupancy references must remain inside one Organization.
- **Context:** No accepted cross-organization collaboration or access policy
  exists.
- **Consequences:** Cross-organization linking is rejected rather than
  interpreted as delegation. External Knowledge, Memory, and policy reference
  presence grants no visibility or access; their future authorities must
  verify scope and fail closed.
- **OPEN:** Federated collaboration and data-isolation protocol.

## ADR-OD-014: Organization projections never mutate canonical state

- **Status:** Accepted
- **Decision:** Organization Intelligence snapshots, graphs, insights, UI
  state, event delivery, logs, and audits are non-authoritative projections or
  evidence.
- **Context:** Lucy Organization Intelligence derives nodes and edges and
  accepts caller actor strings, but does not prove lifecycle authority.
- **Consequences:** Only the state owner may create a canonical revision and
  event.

## ADR-OD-015: Employee selection and Assignment Service remain unresolved

- **Status:** Accepted
- **Decision:** Membership, Role, Position, Occupancy, or hierarchy never
  selects an Employee for a Scheduler Job. Employee-to-job selection remains
  **OPEN** and the Public Assignment Service remains
  **CONFLICTING / INVESTIGATE**.
- **Context:** Legacy score, identifier order, and caller `force` conflict
  with accepted Scheduler and Persistent Runtime authorities.
- **Consequences:** Epic 5.0 adds no assignment or selection contract.

## ADR-OD-016: Reference validation is non-authoritative

- **Status:** Accepted
- **Decision:** `validate_organization_domain` deterministically validates
  canonical documents, revisions, hierarchy, scope, lifecycle relationships,
  completed transition/Event linkage, and an explicit observation time
  without persistence or mutation.
- **Context:** JSON Schema cannot detect cycles, duplicate active
  relationships, or cross-record stale revisions.
- **Consequences:** Passing conformance does not create an Organization,
  authority, membership, permission, or transition. The validator is
  removable without production migration.

## Consolidated OPEN questions

1. How is the logical Organization Domain Authority deployed and persisted?
2. Who owns organizational policy and permission grants?
3. How are cross-organization collaboration and delegation represented?
4. What is the ownership transfer and recovery protocol?
5. How are child transition plans and cross-authority transactions committed?
6. How does Employee Registry migrate v2 records to v3?
7. How do current Membership/Role facts reach Authorization Authority?
8. Who proposes/selects an Employee for a Scheduler Job?
9. What event outbox, delivery, replay, and evolution protocol is used?
10. How do Team Templates create inactive structure and request activation?
