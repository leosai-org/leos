# LEOS v2 Organization, Team, and Employee Domain

## Status

This document defines the accepted Epic 5.0 Organization Domain foundation
for LEOS 0.2.0 Developer Preview v2.

It establishes logical authority, canonical resources, lifecycle vocabulary,
relationships, invariants, contracts, and migration boundaries. It does not
implement a production Organization service, authentication provider, policy
engine, Team Architect, assignment selector, UI, or runtime orchestrator.

Contract validity proves shape and deterministic invariants only. It does not
authenticate an actor, authorize a mutation, verify approval, or establish
deployed authority.

## Goals

The foundation must:

1. give Organization, Department, Team, Role, Position, Membership, Position
   Occupancy, and Employee unambiguous identities and owners;
2. establish one logical authority for organizational structure without
   duplicating Employee Registry or execution-plane state;
3. make every hierarchy and relationship revision-pinned and
   organization-scoped;
4. keep membership, occupancy, and work assignment distinct;
5. prohibit cyclic, orphaned, or cross-organization relationships;
6. preserve audit history through suspension, expiry, revocation, archive,
   and deletion tombstones;
7. ensure Team and Role never become execution or authorization authority;
8. provide deterministic reference validation without creating a production
   service or state store; and
9. preserve all user-ranking and execution-plane authority boundaries.

## Canonical authority allocation

| Concern | Canonical authority | State owned | Explicit exclusion |
|---|---|---|---|
| Organization, Department, and Team | Logical Organization Domain Authority | Definitions, revisions, lifecycle, hierarchy, ownership, policy references, audit, transition events | No scheduling, reasoning, capability resolution, invocation, policy evaluation, or knowledge/memory content |
| Role and Position | Logical Organization Domain Authority | Reusable responsibilities, concrete organizational slots, reporting-position hierarchy | Role is not authorization; Position is not Employee |
| Membership | Logical Organization Domain Authority | User/Employee membership in Organization/Team, lifecycle, effective period, issuer, role references | No capability grant, permission, assignment, or execution authority |
| Position Occupancy | Logical Organization Domain Authority | Employee occupancy of a concrete Position and its lifecycle | Not Membership, Employee identity, or work Assignment |
| Employee definition/lifecycle | Employee Registry | Employee definition, organization reference, principal binding, lifecycle, responsibilities, Role references, policy references, audit | No runtime presence, reasoning, assignment, scheduler, membership, or position state |
| Employee runtime presence/state | Persistent Employee Runtime | Mailbox, durable working state, assignment projection/transitions | No Employee definition or organization structure |
| Employee reasoning | Employee Cognitive Service | Cognitive runs, attempts, checkpoints, observations, results | No organization mutation or provider invocation |
| Jobs, leases, and admission | Scheduler | Job lifecycle, leases, resource admission/release | No employee selection or organization lifecycle |
| Employee-to-job selection | **OPEN** | None accepted | Assignment Service and identifier/score/caller-force selection remain prohibited |
| Organization policy definition/evaluation | **OPEN** | Policy references only are present in this epic | No implicit inheritance, ranking scope, permission, or authorization |
| Cross-organization collaboration | **OPEN** | None accepted | References across Organization boundaries fail closed |

The Organization Domain Authority is a logical authority boundary. Whether it
is deployed as one service or multiple modules sharing one authority protocol
remains **OPEN**. No executable service or persistence topology is established
by Epic 5.0.

## Authority classification

| Concern | Classification | Accepted boundary or unresolved question |
|---|---|---|
| Organization lifecycle | **ACCEPTED** | Logical Organization Domain Authority |
| Department lifecycle | **ACCEPTED** | Logical Organization Domain Authority |
| Team lifecycle | **ACCEPTED** | Logical Organization Domain Authority; collaboration only |
| Employee lifecycle | **ACCEPTED** | Employee Registry, not Organization Domain Authority |
| Membership authority | **ACCEPTED** | Logical Organization Domain Authority; no independent authorization |
| Role authority | **ACCEPTED** | Logical Organization Domain Authority; responsibility vocabulary only |
| Position authority | **ACCEPTED** | Logical Organization Domain Authority; structural slot only |
| Position Occupancy | **ACCEPTED** | Logical Organization Domain Authority; distinct from Membership and Assignment |
| Supervisor hierarchy | **ACCEPTED** | Acyclic Position reporting hierarchy; Employee manager views are projections |
| Team execution authority | **ACCEPTED prohibition** | Team has no execution authority |
| Employee-to-job selection | **OPEN** | No accepted proposal/selection owner or Scheduler handoff |
| Cross-organization collaboration | **OPEN** | No accepted delegation, visibility, or data-access protocol; fail closed |
| Organization policy ownership | **OPEN** | References only; no policy evaluator, inheritance, permission, or ranking scope |
| Public Assignment Service | **CONFLICTING / INVESTIGATE** | Peer job state, legacy selection, and caller-force behavior receive no v2 authority |

## Canonical resources

All resources use the Epic 4.0 managed identity:

- immutable `resource_type` and `resource_id`;
- mutable display identity;
- one material revision;
- exactly one owner, creator, steward, and lifecycle authority;
- revision-pinned creation Actor Context and authority evidence;
- audit identity; and
- creation/update timestamps.

### Organization

An Organization is the top-level isolation and ownership boundary.

- A v1 Organization has exactly one `HUMAN_USER` owner.
- It binds exactly one Organization Principal.
- Its logical lifecycle authority is the Organization Domain Authority.
- Policy references are opaque, revisioned inputs; they do not establish a
  policy owner or result.
- Nested Organization ownership and cross-organization collaboration remain
  **OPEN**.

### Department

A Department:

- belongs to exactly one Organization;
- is owned by that Organization Principal;
- may reference one parent Department in the same Organization;
- may have child Departments through their parent references; and
- cannot participate in a parent cycle.

### Team

A Team is a collaboration boundary within exactly one Organization.

- It may belong to one Department in the same Organization.
- It references Role definitions, policy evidence, Knowledge Objects, and
  Memory Objects without owning their content or lifecycle.
- Knowledge/Memory references are non-authorizing metadata. Until their
  canonical authorities can verify ownership and scope, consumers must fail
  closed rather than infer same-Organization visibility from reference
  presence.
- Membership resources determine Team membership.
- It has no scheduler, assignment, reasoning, ranking, resolution, provider,
  tool, or invocation authority.

### Employee

`leos.employee-definition.v3` is the canonical target definition contract
owned by Employee Registry. It deliberately separates:

| Concept | Authority |
|---|---|
| Employee resource and lifecycle | Employee Registry |
| Employee Principal | Identity Authority |
| Employee organization membership | Organization Domain Authority through Membership |
| Position Occupancy | Organization Domain Authority |
| Employee configuration | Existing/future governed configuration authority; exact v2 consolidation remains **OPEN** |
| Runtime presence, mailbox, working state, Assignment | Persistent Employee Runtime |
| Cognitive lifecycle | Employee Cognitive Service |
| Scheduler Job/lease/admission | Scheduler |

The Employee resource carries its one Organization reference, owner,
principal binding, status, responsibilities, Role references, policy
references, and audit identity. Team memberships are not embedded or copied;
they are defined by canonical Membership resources.

Employee definitions contain no raw secrets, provider credentials, runtime
authority, caller-generated approval, embedded authorization result, mailbox,
working state, cognitive state, assignment, or scheduler lease.

### Role

A Role is a reusable, organization-scoped responsibility definition.

- It is not a Principal, Employee, Position, permission grant, capability
  grant, authorization decision, or provider/model policy.
- A Role reference may be input to a future policy authority.
- Possession of a Role never independently authorizes action or execution.

### Position

A Position is a concrete organization-scoped slot.

- It may reference one Department, one Team, and one Role.
- It may report to one other Position in the same Organization.
- Position reporting relationships form the canonical supervisory hierarchy
  and cannot contain cycles.
- An Employee occupies a Position only through Position Occupancy.
- A Position is never an Employee identity or runtime.

Employee-to-Employee “manager” views are projections derived from current
Position Occupancy and Position reporting. They cannot mutate Position or
Employee state.

### Membership

Canonical membership kinds are:

- User to Organization;
- Employee to Organization;
- User to Team; and
- Employee to Team.

A Membership records member, container, Role references, lifecycle status,
effective period, issuer, Actor Context evidence, authorization-decision
reference, revision, and audit identity.

Membership never independently grants a capability, permission, provider,
model, tool, scheduler, assignment, or execution right. A future
Authorization Authority policy may consume current membership and Role
evidence.

An active Employee requires exactly one active Employee-to-Organization
membership matching the Employee's Organization. Duplicate active membership
for the same member/container is prohibited. Expired membership cannot be
treated as active.

Membership records are retained after expiry or revocation. Removal means a
governed terminal lifecycle transition, not erasure of audit history.

### Position Occupancy

Position Occupancy records one Employee occupying one Position for an
effective period.

- It is separate from Organization/Team Membership.
- It is separate from work Assignment.
- One Position may have at most one active Occupancy.
- Both Position and Employee must belong to the same Organization.
- Active Occupancy requires active Position and Employee records.
- Ended or revoked Occupancy remains auditable.

## Lifecycle

Organization, Department, Team, Role, and Position use:

```text
DRAFT -> ACTIVE -> SUSPENDED -> ACTIVE
   |        |          |
   +--------+----------+-> ARCHIVED -> DELETED
```

Employee keeps the established Employee Registry lifecycle in normalized
form:

```text
DRAFT -> VALIDATED -> ACTIVE -> PAUSED -> ACTIVE
   |          |          |       |
   +----------+----------+-------+-> DISABLED -> ACTIVE
   +-------------------------------------------> ARCHIVED
```

`ARCHIVED` is terminal for Employee. The production mapping from existing
lowercase Employee Registry states to v3 remains a future compatibility
package.

Membership uses:

```text
PENDING -> ACTIVE -> SUSPENDED -> ACTIVE
    |         |          |
    +---------+----------+-> EXPIRED
    +---------+----------+-> REVOKED
```

Position Occupancy uses:

```text
PENDING -> ACTIVE -> ENDED
    |         |
    +---------+-> REVOKED
```

Expired, revoked, ended, archived, and deleted records remain immutable
history/tombstone evidence. They are not silently reactivated.

## Transition authority and evidence

`leos.organization-lifecycle-transition.v1` records a completed,
revision-conditional transition for Organization Domain resources. It
requires:

- the expected subject revision;
- from/to status;
- a different resulting revision;
- exactly one Actor Context;
- a revision-pinned Authorization Decision;
- current verified Approval evidence when applicable;
- resulting canonical Event reference;
- explicit rollback behavior;
- explicit child-resource behavior; and
- transition timestamp.

The contract cannot authorize itself. Production consumers must verify the
Actor Context, authorization decision, and any Approval verification through
their recognized authorities.

Approval policy remains **OPEN**. Therefore production code may not infer that
approval is unnecessary from a caller field or example. The transition
authority determines applicable policy and fails closed when policy or
verification is unavailable.

A transition to `DELETED` is terminal and uses
`TERMINAL_NO_ROLLBACK`. Other rollback is a separately authenticated and
authorized compensating transition; no record is mutated backward.

Parent suspension, archive, or deletion never implies an invisible cascade.
The transition must explicitly block on a child plan, reference separately
authorized child transitions, or retain children under an accepted
restriction. The exact production child-plan protocol remains **OPEN**.

## Organizational invariants

The canonical validator enforces, for a deterministic record set and explicit
observation time:

1. unique resource identity and one-to-one Organization/Employee Principal
   bindings;
2. exactly one owner and lifecycle authority per resource;
3. Organization Principal ownership for child resources;
4. one Organization per Department, Team, Employee, Role, Position,
   Membership, and Occupancy;
5. revision-current references and no orphaned local resources;
6. no cross-organization Department, Team, Role, Position, Membership,
   Employee, or Occupancy references;
7. no Department-parent cycles;
8. no supervisory Position cycles;
9. no duplicate active Membership;
10. exactly one active Organization Membership for each active Employee;
11. no future or expired Membership treated as active;
12. at most one active Occupancy per Position and no future or ended
    Occupancy treated as active;
13. no active child beneath an inactive required structural parent and no
    active Occupancy with an inactive Position or Employee;
14. Role never serving as authorization; and
15. Position never serving as Employee identity; and
16. completed transition evidence matching the resulting canonical resource
    revision, status, owner, lifecycle authority, and exactly one canonical
    Event.

The validator is deterministic reference validation only. It has no storage,
API, authenticator, authority configuration, clock, or mutation capability.

## Event boundary

The authority owning the transition produces its canonical
`leos.event-envelope.v1` event.

Organization Domain events preserve:

- event identity and revision;
- producing authority and authenticated actor;
- revisioned subject;
- correlation and causation;
- occurrence/recording times; and
- minimal transition payload.

Events, organization-intelligence snapshots, graphs, UI state, indexes, logs,
and audits are non-authoritative evidence or projections. They cannot mutate
canonical organizational state, grant membership, authorize, assign work, or
create lifecycle transitions.

## Persistence boundary

The logical Organization Domain Authority persists its resources and
ownership atomically with each revision. The production data model, API,
transaction/outbox implementation, deployment topology, backup, and recovery
remain **OPEN**.

Employee Registry remains the Employee persistence authority. Epic 5.0 does
not create a second Employee store.

## Assignment and execution boundaries

Membership, Position Occupancy, and work Assignment are distinct:

```text
Membership
  -> organizational belonging only
Position Occupancy
  -> structural slot only
Work Assignment
  -> Persistent Employee Runtime projection of Scheduler work
```

Organization and Team layers may later submit governed work. They do not
select an Employee, create Scheduler leases, own Persistent Runtime
Assignments, reason, resolve providers, invoke tools/models, or restart work.

The Public Assignment Service remains **CONFLICTING / INVESTIGATE**.
Employee-to-job proposal/selection and the governed Scheduler handoff remain
**OPEN**.

## Policy and ranking boundary

Organization objects carry revisioned policy references only.

Epic 5.0 does not establish:

- organization/team ranking scopes;
- policy inheritance or conflict precedence;
- permission grants;
- Role-to-permission mapping;
- capability grants;
- cloud permission; or
- budget authority.

Epic 6.0 adds an Organization-scoped Capability Profile target contract, but
does not resolve these policy questions. Organization, Team, Employee, and
Runtime profiles retain separate exact scope and Organization references.
They express requirements, prohibitions, set-like preferences, risk limits,
runtime constraints, and policy references only. They do not grant
permission, satisfy approval, establish a new ranking scope, select a
provider, resolve a capability, activate a Plugin, or invoke work.

The accepted ranking precedence remains:

```text
job > employee > capability > global
```

Future organizational restrictions may eliminate candidates only under an
accepted policy decision. They cannot reorder candidates or add ranking scope
implicitly.

## Compatibility and migration

- Existing `leos.employee-definition.v2` and
  `leos.employee-lifecycle.v1` remain current Employee Registry compatibility
  contracts.
- `leos.employee-definition.v3` is the accepted organization-aware target.
- Adoption requires an explicit Employee Registry migration package, stored
  data mapping, Actor Context integration, concurrency tests, and rollback
  plan.
- No v2 record is automatically assigned an Organization, owner, Principal,
  Role, Membership, or Position.
- Legacy `department`, `role`, `manager`, `permissions`,
  `model_preferences`, runtime, memory, and adapter fields are migration input
  only. They do not become canonical organization, authorization, ranking,
  runtime, or memory authority.
- Lucy company/department YAML is donor evidence only.
- Lucy Organization Intelligence remains a projection/analytics donor. Its
  snapshots, graph nodes, edges, insights, review fields, and caller actor
  strings are not lifecycle authority.

No database migration, production configuration, or service implementation is
part of Epic 5.0. Before adoption, rollback is a source revert. After adoption,
rollback must preserve v3 revisions and relationship audit history rather
than reconstructing legacy strings.

## Canonical contracts

| Contract | Purpose |
|---|---|
| `leos.organization.v1` | Top-level organization boundary |
| `leos.department.v1` | Department and optional parent |
| `leos.team.v1` | Collaboration boundary |
| `leos.employee-definition.v3` | Organization-aware Employee target |
| `leos.role.v1` | Reusable responsibility definition |
| `leos.position.v1` | Concrete organizational slot and reporting hierarchy |
| `leos.membership.v1` | User/Employee Organization/Team relationship |
| `leos.position-occupancy.v1` | Employee-to-Position relationship |
| `leos.organization-lifecycle-transition.v1` | Completed governed transition evidence |
| `leos.event-envelope.v1` | Authority-produced transition event |

`organization-common.v1.schema.json` contains reusable definitions and is not
a document contract.

## Remaining OPEN decisions

1. Production Organization Domain service/module topology and persistence.
2. Organization policy owner, language, inheritance, and conflict behavior.
3. Cross-organization collaboration, delegation, visibility, and data access.
4. Ownership transfer and organization recovery.
5. Child transition plan and cross-authority transaction protocol.
6. Organization event outbox, delivery, replay, and schema evolution.
7. Employee Registry v2-to-v3 migration and compatibility duration.
8. Production Role/Membership inputs to Authorization Authority.
9. Employee-to-job selection and Scheduler handoff.
10. Team Template installation and organization activation protocol.
11. Knowledge/Memory reference scope verification and removal behavior.
