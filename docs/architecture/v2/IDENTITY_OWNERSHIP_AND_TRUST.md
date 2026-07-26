# LEOS v2 Identity, Ownership, and Trust Foundation

## Status and authority

This document defines the canonical identity, ownership, actor-evidence, and
trust boundaries for LEOS 0.2.0 Developer Preview v2.

It resolves the foundation questions authorized for Epic 4.0. It does not
implement a production authentication provider, secret backend, artifact
publisher, organization lifecycle, permission policy language, or deployment
topology.

The governing decisions are recorded in
`IDENTITY_OWNERSHIP_AND_TRUST_DECISIONS.md`. The canonical schemas live under
repository-root `contracts/`, and `packages/leos-contracts` remains the single
runtime schema and semantic validator.

Structural contract validity is never proof of identity, authentication,
authorization, approval, signature validity, secret access, or event truth.
Trust exists only when the recognized authority supplies current evidence over
an authenticated service boundary.

## Goals

The foundation must:

1. give every managed object one immutable resource identity;
2. give every managed object exactly one owner;
3. distinguish owner, creator, steward, and lifecycle authority;
4. make every authority-bearing action attributable to exactly one
   authenticated principal;
5. keep initiator, delegation, producer, and actor identities distinct;
6. separate authentication, authorization, capability eligibility,
   resolution, and execution;
7. define verifiable approval-grant identity and fail-closed verification;
8. define artifact trust evidence without granting publication,
   installation, or activation;
9. define opaque secret-reference identity without representing secret
   values;
10. define event producer, actor, subject, correlation, causation, time, and
    revision evidence;
11. preserve each domain service's existing canonical state authority; and
12. provide one shared contract vocabulary for later organization, plugin,
    workflow, Tool, knowledge, and onboarding epics.

## Non-goals

Epic 4.0 does not:

- implement passwords, passkeys, OAuth, OIDC, SAML, LDAP, enterprise
  federation, workload certificates, or another production authenticator;
- define Organization, Department, Team, Workflow, Plugin, Tool, Runtime,
  Artifact, Knowledge, or Memory lifecycle services where their owners remain
  **OPEN**;
- implement capability-permission grants or organization policy;
- implement approval-service persistence or endpoints;
- implement secret storage, secret leases, credential injection, or
  redaction;
- choose signature algorithms, trust roots, package formats, or publisher
  moderation;
- create a central duplicate store for every LEOS resource;
- retrofit existing service records or APIs without a service-specific
  migration; or
- make Lucy identities, tokens, approvals, event records, or filesystem
  objects canonical.

## Canonical trust authorities

These are logical authorities. A later deployment decision may colocate them,
but colocating code or storage never merges their responsibilities.

| Authority | Canonical responsibility | Explicit exclusions |
|---|---|---|
| Identity Authority | Principal definitions and lifecycle; authentication-policy bindings; validation of authenticator evidence; issuance and validation of Actor Context evidence | No domain-object lifecycle, permission policy, capability resolution, approval, secret value, provider selection, or execution |
| Authorization Authority | Subject-action-resource authorization decisions from recognized policies and grants | No authentication, ranking, capability eligibility, provider/model resolution, approval issuance, or invocation |
| Approval Authority | Approval requests, decisions, grant identity and lifecycle, revocation/consumption, and current grant verification | No caller self-approval, general permission policy, capability resolution, scheduler mutation, or invocation |
| Artifact Trust Authority | Digest/signature/provenance/trust-policy verification evidence and artifact-trust revocation status | No publication, installation, configuration, activation, capability grant, or runtime selection |
| Secret Authority | Opaque secret-reference identity and secret-value lifecycle boundary | No authorization by reference possession; no raw value in governed contracts, events, logs, prompts, memory, or normal audit |
| Domain lifecycle authority | Canonical resource identity, ownership, revision, lifecycle transition, and transition event for the objects it already owns | No global principal authentication and no lifecycle state for another domain |

The deployment topology, production authentication-provider interfaces,
authorization policy sources, artifact trust-root administration, secret
backend interface, and durable service implementations remain **OPEN**.

## Principal model

A principal is an identity that can be authenticated and can be the subject of
authorization. Principal identity is not a display name, user-entered string,
service URL, employee ID, plugin ID, process ID, container ID, or API token.

Canonical principal types are:

| Principal type | Meaning |
|---|---|
| `HUMAN_USER` | A person represented by a governed User resource |
| `SERVICE` | A LEOS service or authority workload |
| `ORGANIZATION` | An organization acting as an owning or policy subject |
| `DEPARTMENT` | A department acting within future governed organization policy |
| `TEAM` | A team acting as an owning or policy subject |
| `EMPLOYEE` | The governed acting identity bound to an Employee definition |
| `RUNTIME` | A governed active runtime identity, once runtime activation authority exists |
| `PLUGIN` | A governed installed plugin identity, once plugin lifecycle authority exists |
| `PUBLISHER` | A governed publisher identity, distinct from an artifact or signing key |

Operator, approver, administrator, installer, steward, and reviewer are roles
or authorized actions. They are not additional principal types.

Non-human principals require a governed subject resource. Organization, Team,
Employee, Runtime, and Plugin principals cannot exist before their subject
resource has a canonical lifecycle authority. A human principal binds to one
User resource.

Principal status is `ACTIVE`, `SUSPENDED`, `REVOKED`, or `ARCHIVED`.
Authentication and authorization fail closed for a principal that is not
active.

## One actor per action

Every authority-bearing request or transition has exactly one actor principal.
An Actor Context binds that actor to authentication evidence issued by the
Identity Authority.

When one principal initiates work performed by another:

- `actor` is the principal performing the immediate action;
- `initiator` identifies the earlier principal whose request caused it; and
- `delegation_ref` is mandatory when `initiator` is present.

Initiator or delegation never turns two principals into joint actors.
Correlation and causation preserve the chain.

An Actor Context contains no credential, token, signature value, or secret.
The contract names the authentication method and assurance class as evidence;
it does not implement or prove that method. Only a trusted Identity Authority
boundary can issue usable Actor Context evidence.

The `DEVELOPMENT` assurance class is explicitly non-production. It supports
deterministic conformance fixtures only and must not be accepted by a
production deployment.

## Managed resource identity and ownership

Every persisted managed resource has:

- `resource_type`;
- immutable `resource_id`;
- mutable `display_name`;
- material `revision`;
- exactly one `owner`;
- exactly one `creator`;
- exactly one current `steward`;
- exactly one `lifecycle_authority`;
- revision-pinned creation Actor Context and authority-evidence references;
- `audit_id`;
- creation and update timestamps.

The singular owner requirement prohibits owner arrays, owner sets, and
implicit shared ownership. Shared control is expressed through authorization
policy, not multiple canonical owners.

The roles mean:

| Role | Meaning |
|---|---|
| Owner | Principal accountable for and exercising governed ownership rights over the resource |
| Creator | Actor principal whose authorized action created the resource |
| Steward | Principal currently responsible for administration or care; stewardship does not transfer ownership |
| Lifecycle authority | Recognized domain authority that alone may assert canonical resource revisions and lifecycle transitions |

Ownership is not authorization by itself. The Authorization Authority must
evaluate applicable owner rights and restrictions for the exact action and
resource revision.

Ownership transfer is a lifecycle transition performed by the resource's
domain authority. It requires authenticated actor evidence, an authorization
decision, a new material revision and audit identity, and an authority-produced
event. A transfer cannot be inferred from an event, UI update, file move,
database copy, or caller-supplied owner field.

No separate global ownership database becomes a peer state authority. Each
domain authority persists the canonical identity and ownership of its own
resource atomically with the resource revision. The Identity Authority
validates principal references; it does not own the domain resource.

For user- or service-requested domain mutations, creation authority evidence
is the applicable Authorization Decision. For evidence emitted as the normal
function of a recognized authority—such as an Actor Context, Authorization
Decision, verification result, or canonical event—it references that
authority's accepted mandate or the governed decision that caused the
transition. This avoids an infinite chain in which an Authorization Decision
would require another Authorization Decision merely to exist. It does not
create a bootstrap exception: the producing service is still one
authenticated actor, and production trust bootstrap remains **OPEN**.

## Identity and lifecycle matrix

An **OPEN** lifecycle row is an implementation stop boundary. The common
identity contract can describe the future object, but no canonical instance
may be persisted until an accepted authority owns its lifecycle.

| Object | Immutable identity | Display identity | Canonical owner | Creator/steward | Lifecycle authority | Authentication and authorization | Version/audit | Persistence |
|---|---|---|---|---|---|---|---|---|
| User | `USER` resource ID and bound human principal ID | User-controlled display name | The human principal; bootstrap exceptions require governed evidence | Authenticated bootstrap/administrator actor; designated steward | Identity Authority for the foundation scope | Identity Authority authenticates; Authorization Authority decides actions | Material revision and audit ID | Identity Authority store |
| Organization | Organization resource ID and bound Organization Principal | Organization name | Exactly one Human User principal in v1 | Authenticated creator and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; approval policy remains **OPEN** | Material revision and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Department | Department resource ID | Department name | Containing Organization Principal | Authenticated creator and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; cross-organization references fail closed | Material revision and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Team | Team resource ID | Team name | Containing Organization Principal | Authenticated creator and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; Team has no execution authority | Material revision and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Role | Role resource ID | Role name | Containing Organization Principal | Authenticated creator and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; Role never independently authorizes | Material revision and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Position | Position resource ID | Position name/code | Containing Organization Principal | Authenticated creator and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; Position is not Employee | Material revision and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Membership | Membership resource ID | Relationship description | Containing Organization Principal | Authenticated issuer and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; membership never independently authorizes | Material revision, effective period, and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Position Occupancy | Position Occupancy resource ID | Relationship description | Containing Organization Principal | Authenticated issuer and governed steward | Logical Organization Domain Authority | Actor Context and Authorization Decision; occupancy is not Assignment | Material revision, effective period, and audit ID | Logical Organization Domain Authority; production topology **OPEN** |
| Employee | Employee resource ID and bound Employee principal | Employee name | Containing Organization Principal in the v3 target contract | Authenticated creator; Employee Registry steward | Employee Registry | Actor Context and Authorization Decision; capability use remains separately governed | Employee definition revision and audit | Employee Registry |
| Workflow | Workflow resource ID | Workflow name | Accepted user/organization/team principal | Authenticated creator and governed steward | **OPEN** Workflow authority | Actor Context and future workflow policy | Required before instance creation | Future Workflow authority store |
| Plugin | Plugin resource ID; installed instance remains separate | Plugin name | Publisher for published definition; local owner for installed instance | Authenticated publisher/installer and governed steward | **OPEN** publishing and installed-instance authorities | Publisher/installer Actor Context and separate authorization/trust evidence | Immutable published version plus instance revision | Future publishing and installation stores |
| Capability | Capability resource ID | Capability name | User or organization principal under later policy | Authenticated creator; Capability Manager steward | Capability Manager | Declaration/inventory is not a grant; Authorization Decision precedes resolution where required | Capability revision and audit | Capability Manager |
| Tool | Tool and operation IDs | Tool/operation names | Publisher or local owner under future Tool policy | Authenticated creator and governed steward | **OPEN** Tool catalog authority | Actor Context, permission, approval, secret, sandbox, resolution, and Dispatcher execution as applicable | Required before instance creation | Future Tool catalog |
| Provider | Provider resource ID | Provider name | User or Organization principal | Authenticated creator; Capability Manager steward | Capability Manager | Actor Context and Authorization Decision for mutation/use; Capability Manager separately resolves | Provider revision and audit | Capability Manager |
| Model | Model resource ID | Model name | User or Organization principal | Authenticated creator; Model Registry steward | Model Registry | Actor Context and Authorization Decision for mutation/use; ranking/resolution remain separate | Model revision and audit | Model Registry |
| Runtime | Runtime resource ID and later Runtime principal | Runtime name | User or Organization principal | Authenticated creator and governed steward | **OPEN** runtime activation authority | Actor Context and future activation authorization | Required before active instance creation | Future runtime authority store |
| Artifact | Artifact resource ID plus immutable published version/content digest where applicable | Artifact name | User, Organization, Team, or Publisher principal | Authenticated creator/publisher and steward | General lifecycle remains **OPEN**; Artifact Trust Authority owns only trust evidence | Separate publish/install/activate authorizations and trust verification | Artifact revision/version/digest and audit | Future artifact authority; trust evidence in Artifact Trust Authority |
| Approval Grant | Approval Grant resource ID | Human-readable scoped purpose | Principal accountable for the approved action | Approval Authority creates/stewards from authenticated decision | Approval Authority | Current trusted verification for exact subject/action/resource/context | Grant revision, status, use, revocation, audit | Approval Authority |
| Secret Reference | Secret Reference resource ID | Non-secret label | User or Organization principal | Authenticated creator; Secret Authority steward | Secret Authority | Separate authorization for each resolution/use; possession is never authority | Reference revision/version/status and audit | Secret Authority; value remains in backend boundary |
| Event Source | Event Source resource ID bound to the producing domain authority | Source name | Resource owner represented by the source authority | Domain authority creates/stewards | The state authority represented by the source | Producer authenticates as its service principal | Source revision and audit | Producing authority |
| Event | Event resource ID | Event type/display description | Subject resource owner | State authority produces/stewards immutable evidence | Authority that owns the asserted transition | Producer and actor evidence required; event is not authorization | Event revision, subject revision, audit | Producing authority/outbox; delivery store is a projection |
| Scheduler Job | Scheduler Job ID | Job description | Accepted user/organization/team owner under later submission policy | Authenticated creator; Scheduler steward | Scheduler | Actor Context and submission Authorization Decision | Job revision/state audit | Scheduler |
| Knowledge Object | Knowledge resource ID | Knowledge title | User/Organization/Team/Employee owner under future data policy | Authenticated creator and curator | **OPEN** Knowledge authority | Actor Context plus scope/trust/retrieval authorization | Required before canonical persistence | Future Knowledge authority |
| Memory Object | Memory resource ID | Memory description | User/Organization/Team/Employee owner under future data policy | Authenticated creator and curator | **OPEN** Memory authority | Actor Context plus scope/trust/retrieval authorization | Required before canonical persistence | Future Memory authority |

The public Assignment Service remains **CONFLICTING / INVESTIGATE** and does
not gain an identity, ownership, or job authority from this foundation.
Employee-to-job selection authority remains **OPEN**.

## Authentication boundary

Authentication answers: “Which principal proved control of an accepted
credential or workload identity at a recognized boundary?”

The boundary is:

```text
credential or workload proof
  -> authenticator adapter
  -> Identity Authority verification
  -> bounded Actor Context
```

Authenticator adapters are evidence providers, not principal or authorization
authorities. They cannot create principals, assign owners, grant permissions,
issue approvals, select capabilities, or invoke providers.

Production authenticator selection, proof formats, key rotation, session
revocation, workload identity, and recovery remain **OPEN**. Epic 4.0 provides
no production-ready authentication claim.

## Authorization boundary

Authorization answers: “May this authenticated subject perform this exact
action against this exact resource revision in this exact context?”

The canonical separation is:

```text
Authentication
  -> Actor Context
Authorization
  -> subject/action/resource/context decision
Capability governance
  -> eligibility and governed target resolution
Execution
  -> exact authorized invocation
```

An `ALLOW` Authorization Decision requires recognized, revisioned authority
evidence. A `DENY` decision requires reasons. The decision has a bounded
validity window and never selects a provider/model or implies capability
eligibility.

The policy and grant sources that the Authorization Authority may consume
remain partly **OPEN**. Capability permission grants and organizational policy
are later epics. Until they exist, their absence fails closed.

## Approval Grant authority

Approval is a specific authorization prerequisite, not general authentication
or permission.

The Approval Authority owns:

- Approval Request identity and lifecycle;
- authenticated approval decision evidence;
- Approval Grant identity, subject, recipient, action, resource revision,
  context revision/digest, validity, use policy, and lifecycle;
- expiry, revocation, and single-use consumption;
- current read and fail-closed verification; and
- approval audit and authority-produced events.

The verification path is:

```text
caller supplies opaque grant reference
  -> trusted Approval Authority retrieves current grant
  -> compares subject, action, resource, revision, context, status, expiry,
     revocation, and use
  -> returns VERIFIED or a non-authorizing outcome
```

Only `VERIFIED` from the trusted Approval Authority may become eligibility or
pre-invocation evidence. Schema validity, a Boolean, an opaque reference, a
copied grant, a stale revision, an Approval Request, or an event never
authorizes.

Capability Manager may consume verified grant eligibility facts. Dispatcher
must verify approval for the concrete invocation as required by
`EXECUTION_PLANE_DECISIONS.md`. Neither service issues or mutates the grant.

## Artifact trust boundary

Artifact trust evidence binds:

- exact Artifact identity and revision;
- immutable artifact version;
- content digest;
- Publisher principal;
- one or more signer principals and detached signature references;
- provenance evidence;
- trust-policy revision;
- Artifact Trust Authority identity;
- outcome, reasons, verification time, validity, and revocation evidence.

`TRUSTED` means only that the Artifact Trust Authority verified the stated
evidence under the stated policy revision. It does not mean:

- published;
- compatible;
- installed;
- configured;
- permissioned;
- approved;
- activated; or
- safe for every context.

The actor that signs, the publisher that publishes, the installer that
installs, the runtime authority that activates, and the authority that revokes
are independently authenticated principals. Their operations require separate
authorization and lifecycle evidence. Publishing, installation, and runtime
activation owners remain **OPEN** for their later epics.

Signature algorithms, signature containers, trust-root administration,
transparency evidence, package formats, dependency policy, and offline
revocation freshness remain **OPEN**.

## Secret Reference identity

A Secret Reference is a managed resource owned by one principal and governed
by the Secret Authority. It contains:

- opaque reference identity;
- opaque backend reference;
- opaque value-version reference;
- non-secret class;
- lifecycle status and timestamps; and
- normal ownership, revision, authority, and audit evidence.

It never contains the protected value, an encrypted value pretending to be a
reference, a bearer token, an API key, a password, a private key, or enough
backend locator detail to bypass the Secret Authority.

Possession, configuration, installation, or validation of a Secret Reference
does not authorize resolution. The Secret Authority must later authenticate
the requester and authorize the exact operation, provider/tool target,
organization, employee, execution, and capability as applicable.

Secret backend support, transient lease/injection contract, rotation protocol,
redaction implementation, and production service remain **OPEN**.

## Canonical event identity

Every canonical event contains:

- immutable Event identity and material revision;
- event type and event-schema revision;
- governed Event Source identity and revision;
- producer service principal;
- actor principal and Actor Context reference;
- revisioned subject resource;
- correlation ID;
- explicit root-action or parent-event causation;
- occurrence and recording timestamps; and
- payload.

The producer must be the service principal of the lifecycle authority that
owns the asserted transition. A generic bus may deliver, retain, or project
the event, but may not become its producer or the subject's state authority.

Payload fields cannot override envelope identity, actor, producer, subject,
revision, correlation, or causation.

Outbox, ordering, acknowledgement, replay, retention, global event-store
topology, and schema-evolution protocol remain **OPEN**. Duplicate delivery
must not duplicate authority-bearing work.

## Contract inventory

| Contract | Purpose |
|---|---|
| `trust-common.v1.schema.json` | Reusable closed definitions; not a standalone authority document |
| `leos.resource-identity.v1` | Common managed identity and ownership evidence |
| `leos.principal.v1` | Principal definition and lifecycle evidence |
| `leos.actor-context.v1` | Bounded authenticated actor evidence |
| `leos.authorization-decision.v1` | Subject-action-resource-context authorization decision |
| `leos.approval-request.v1` | Non-authorizing approval request |
| `leos.approval-grant.v1` | Scoped Approval Authority grant lifecycle record |
| `leos.approval-verification-result.v1` | Fail-closed current grant verification outcome |
| `leos.artifact-trust-evidence.v1` | Digest, signature, provenance, trust, and revocation evidence |
| `leos.secret-reference.v1` | Opaque secret-reference identity |
| `leos.event-envelope.v1` | Canonical authority-produced event evidence |

All top-level contracts and authority-bearing nested objects are closed.
Canonical examples are under `examples/`.

`packages/leos-contracts` validates schema and deterministic cross-field
semantics. It does not authenticate, authorize, verify signatures, verify a
grant against live state, resolve a secret, or operate an event bus.

## Persistence, integrity, and audit

Canonical domain state remains in the recognized authority's governed store.
Identity/ownership evidence must be committed atomically with the domain
revision it describes. Audit records and events may reference the revision but
cannot reconstruct or replace it unless a later accepted event-sourcing
decision explicitly establishes that model.

Authority evidence is revision-pinned and time-bounded where staleness could
change the result. Consumers fail closed when the issuer is unknown, evidence
is malformed, a revision is stale, an actor context is expired, a grant is not
verified, artifact trust is indeterminate, or Secret Authority is unavailable.

No contract contains raw credential or secret values.

## Compatibility, migration, and rollback

This foundation is additive and pre-release:

- no existing v2 service contract is rewritten in Epic 4.0;
- no service behavior or persistence is changed;
- existing strings such as `requested_by`, `user_id`, `employee_id`,
  `decided_by`, and `source` remain compatibility data, not authenticated
  principal evidence;
- later service epics must add explicit Actor Context and resource identity
  migrations at their mutation boundaries;
- existing records remain readable until their service-specific migration and
  compatibility policy is accepted;
- migrations must create revisioned principal/resource mappings without
  treating display strings as proof;
- Lucy approval records, publisher tokens, event-bus records, environment
  variable names, and filesystem identifiers are donor evidence only; and
- removal of these additive contracts and examples is source rollback because
  no production state is created.

There is no automatic conversion of Lucy or legacy approvals into Approval
Grants. There is no migration of secret values. There is no automatic
principal creation from historical actor strings.

## Required conformance

The foundation requires tests for:

- closed contracts and canonical examples;
- unique canonical example identities;
- exactly one owner and required creator/steward/lifecycle authority;
- required revision and audit identity;
- principal/subject binding;
- authenticated actor/subject equality;
- explicit delegation;
- bounded timestamp chronology;
- evidence-backed authorization decisions;
- caller Boolean and unknown-field rejection;
- Approval Request versus Grant separation;
- grant issuer, recipient, subject, scope, expiry, revocation, and use;
- non-authorizing verification outcomes;
- artifact signature and revocation evidence;
- no install/activation implication from trust;
- no secret-value or reference-possession authority;
- Event Source, producer, actor, correlation, causation, subject revision, and
  chronology; and
- payload inability to override the event envelope.

Service integrations must later add live-authority, persistence, concurrency,
revocation, outage, restart, replay, migration, and adversarial tests.

## Remaining OPEN decisions

Epic 4.0 intentionally left these decisions **OPEN**. Epic 5.0 subsequently
accepted the logical Organization Domain boundary in
`ORGANIZATION_DOMAIN.md`; the remaining list is:

1. production human and workload authenticators;
2. Identity, Authorization, Approval, Artifact Trust, and Secret deployment
   topology and durable stores;
3. authorization policy language, permission-grant issuer, role model, and
   organization-policy inheritance;
4. Organization Domain production topology/persistence, ownership transfer,
   and migration, plus workflow, plugin, Tool, runtime, artifact, knowledge,
   and memory lifecycle authorities;
5. employee-to-job selection authority;
6. publisher protocol, package format, signature algorithms, key lifecycle,
   trust roots, and transparency evidence;
7. secret backends, transient lease/injection, rotation, and redaction;
8. event outbox, ordering, replay, retention, broker, and schema evolution;
9. general persisted-data migration and compatibility window; and
10. bootstrap recovery after the initial human principal exists.

No implementation may fill these gaps by caller convention, fixture state,
identifier spelling, Lucy behavior, or the first component that persists a
record.
