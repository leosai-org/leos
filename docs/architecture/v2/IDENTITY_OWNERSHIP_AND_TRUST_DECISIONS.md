# LEOS v2 Identity, Ownership, and Trust Decisions

## Status and use

These ADR-style entries establish the accepted Epic 4.0 foundation for LEOS
0.2.0 Developer Preview v2. They do not claim that production authenticators,
durable trust services, secret backends, artifact publishing, or downstream
service migrations are implemented.

Unresolved implementation and domain-lifecycle choices are explicitly
**OPEN**.

## ADR-IT-001: Identity Authority owns principals and Actor Context evidence

- **Status:** Accepted
- **Decision:** Identity Authority owns canonical Principal records,
  authentication-policy bindings, validation of evidence from recognized
  authenticator adapters, and issuance/validation of bounded Actor Context
  evidence.
- **Context:** Caller strings, employee IDs, service names, URLs, process
  identity, and bearer-token possession are not authenticated principal
  authority.
- **Consequences:** Authenticator adapters cannot create principals, assign
  ownership, authorize actions, issue approvals, or invoke. Contract validity
  never authenticates a principal.
- **OPEN:** Production authenticators, proof formats, workload identity,
  credential recovery, session revocation, and deployment topology.

## ADR-IT-002: Every authority-bearing action has exactly one actor

- **Status:** Accepted
- **Decision:** Every authority-bearing request and state transition identifies
  one Actor Principal through one current Actor Context. Initiator, delegated
  authority, producer, approver, and subject identities are separate evidence.
- **Context:** “On behalf of” chains otherwise create ambiguous shared
  responsibility or let a service borrow a user's authority silently.
- **Consequences:** An initiator requires an explicit delegation reference.
  Correlation or causation never authorizes. A service performing an action is
  the actor even when a human initiated the larger workflow.
- **OPEN:** Delegation grant schema and policy.

## ADR-IT-003: Managed resources have one identity and one owner

- **Status:** Accepted
- **Decision:** Every persisted managed resource has one immutable resource ID,
  one current material revision, exactly one owner, one creator, one steward,
  one lifecycle authority, revision-pinned creation Actor Context and
  authority-evidence references, and one audit identity.
- **Context:** Service-local owner fields, filesystem paths, names, and arrays
  of co-owners cannot support deterministic policy or migration.
- **Consequences:** Shared control is authorization policy, not multiple
  canonical owners. A resource with unknown identity, owner, or lifecycle
  authority cannot enter canonical state.
- **OPEN:** Domain-specific ownership-transfer and inheritance policies.

## ADR-IT-004: Domain authorities retain resource and ownership state

- **Status:** Accepted
- **Decision:** The accepted domain lifecycle authority persists its resource's
  identity and ownership atomically with canonical state. Identity Authority
  validates principal references but does not create a duplicate global
  resource or ownership store.
- **Context:** A central object store would compete with Scheduler, Employee
  Registry, Capability Manager, Model Registry, Persistent Runtime, and future
  domain authorities.
- **Consequences:** Ownership changes are domain lifecycle transitions with a
  new revision, audit identity, authorization evidence, and canonical event.
  Projections remain non-authoritative.
- **OPEN:** Cross-authority transaction and reconciliation protocol.

## ADR-IT-005: Authentication, authorization, capability governance, and execution are separate

- **Status:** Accepted
- **Decision:** Authentication establishes actor evidence. Authorization
  decides subject/action/resource/context permission. Capability Manager
  evaluates capability eligibility and resolution. Dispatcher invokes the
  exact resolved target.
- **Context:** Conflating these layers lets authentication imply permission,
  capability presence imply grants, or an authorization engine become a
  second provider selector.
- **Consequences:** Authorization cannot rank, resolve, substitute, retry,
  escalate, or invoke. Capability Manager and Dispatcher retain all accepted
  boundaries.
- **OPEN:** Authorization policy language and permission-grant sources.

## ADR-IT-006: Authorization Decisions are revisioned, evidence-backed, and bounded

- **Status:** Accepted
- **Decision:** Authorization Authority produces a revisioned
  subject-action-resource-context decision from recognized authority evidence.
  `ALLOW` requires evidence references. `DENY` requires reasons. Decisions are
  time-bounded.
- **Context:** Caller Booleans, roles supplied in request payloads, or stale
  policy snapshots cannot be trusted.
- **Consequences:** A structurally valid decision is usable only when received
  from the recognized authority over an authenticated boundary and its
  evidence/revision remains current.
- **OPEN:** Policy owners, role and group model, cache/revalidation, and
  revocation propagation.

## ADR-IT-007: Approval Authority exclusively owns Approval Grants and verification

- **Status:** Accepted
- **Decision:** Approval Authority owns requests, authenticated decisions,
  grants, expiry, revocation, consumption, current reads, verification, audit,
  and grant lifecycle events. Verification compares the exact subject, action,
  resource revision, context revision/digest, status, time, and use.
- **Context:** Lucy accepts caller `decided_by` strings and mutates peer job
  state. Existing v2 services correctly refuse to authorize from opaque
  reference existence.
- **Consequences:** Only a `VERIFIED` outcome from trusted Approval Authority
  may become eligibility or invocation evidence. Capability Manager and
  Dispatcher consume but never issue or mutate grants. Requests, Booleans,
  references, copied grants, events, and schema validity do not authorize.
- **OPEN:** Durable service/API, approver-policy source, notification,
  concurrent decisions, and verification availability strategy.

## ADR-IT-008: Approval Grant use is fail-closed and revision-pinned

- **Status:** Accepted
- **Decision:** Grant verification returns a current grant revision and use
  reference only for `VERIFIED`. Expired, revoked, consumed, stale,
  wrong-subject, wrong-scope, missing, or unavailable outcomes authorize
  nothing.
- **Context:** A once-valid Approval Grant can become invalid before an
  invocation.
- **Consequences:** Single-use grants require consumption evidence. A
  nonverified outcome cannot carry fields that imply authority.
- **OPEN:** Atomic verification/consumption protocol and bounded caching.

## ADR-IT-009: Artifact Trust Authority verifies but does not publish, install, or activate

- **Status:** Accepted
- **Decision:** Artifact Trust Authority owns digest/signature/provenance/
  policy verification evidence and trust revocation status. Publisher, signer,
  installer, activator, and revoker are separately authenticated principals
  acting through their respective lifecycle authorities.
- **Context:** A verified digest or publisher signature does not prove
  compatibility, installation, permission, approval, configuration, or
  activation.
- **Consequences:** `TRUSTED` is bounded evidence under one trust-policy
  revision. Artifact trust cannot create installed instances, grants,
  capabilities, or runtimes.
- **OPEN:** Publishing, installation, and runtime activation owners; signature
  formats and algorithms; trust roots; key lifecycle; transparency; offline
  revocation.

## ADR-IT-010: Secret Reference identity is distinct from secret value and use authority

- **Status:** Accepted
- **Decision:** Secret Authority owns opaque Secret Reference identity and the
  protected-value lifecycle boundary. Governed contracts carry only opaque
  backend and value-version references plus non-secret lifecycle evidence.
- **Context:** Environment-wide keys, configuration CRUD, and “encrypted
  value” fields can leak or bypass least privilege.
- **Consequences:** Reference possession, installation, configuration, or
  structural validity never authorizes resolution. No raw value is permitted
  in governed contracts, source, fixtures, tests, logs, events, prompts,
  memory, or normal audit.
- **OPEN:** Backend interface, transient lease/injection, rotation, redaction,
  deletion, backup behavior, and production implementation.

## ADR-IT-011: The state authority produces the canonical event

- **Status:** Accepted
- **Decision:** Only the authority that owns a state transition may produce
  the canonical event asserting it. Event identity records source, producer,
  actor, Actor Context reference, revisioned subject, correlation, causation,
  timestamps, schema revision, and payload.
- **Context:** Lucy's generic event bus assigns event identity after accepting
  unverified source and user strings. That is delivery behavior, not canonical
  transition authority.
- **Consequences:** A broker can deliver or project but cannot replace the
  producer or domain store. Payload fields never override the envelope.
  Duplicate delivery cannot duplicate authority-bearing work.
- **OPEN:** Outbox, broker, ordering, acknowledgment, replay, retention,
  global event-store topology, and event-schema evolution.

## ADR-IT-012: Evidence and fixtures never become authority

- **Status:** Accepted
- **Decision:** Events, projections, observations, plans, audits, logs,
  examples, conformance fixtures, and Lucy donor records remain
  non-authoritative. Structural validation establishes shape and deterministic
  invariants only.
- **Context:** Reference examples necessarily name illustrative principals and
  authorities, but those names do not create deployed identities or services.
- **Consequences:** Production consumers require authenticated issuer
  identity, current revision, applicable scope, and recognized authority.
  Development assurance and example state are forbidden from production
  authority/configuration stores.
- **OPEN:** Production trust bootstrap and fixture-isolation mechanism.

## ADR-IT-013: Existing services migrate explicitly and non-destructively

- **Status:** Accepted
- **Decision:** Epic 4.0 adds contracts and reference validation without
  rewriting current service APIs or persistence. Each service later adopts
  Actor Context and resource identity through an explicit compatibility,
  migration, and negative-test package.
- **Context:** Existing fields such as `requested_by`, `user_id`, `decided_by`,
  employee IDs, and event `source` are not authenticated evidence, but changing
  all services atomically would create unsafe implicit migrations.
- **Consequences:** Legacy strings remain compatibility data only. No
  historical string is promoted automatically to a Principal. No Lucy
  approval becomes a Grant and no secret value is migrated.
- **OPEN:** Service order, compatibility window, stored-data mapping, and
  production rollback procedure.

## ADR-IT-014: Identity syntax does not become policy

- **Status:** Accepted
- **Decision:** Canonical identifiers are opaque, bounded, and stable. Their
  spelling, prefix, lexical order, display name, or storage path has no
  authorization, ranking, ownership, trust, or selection meaning.
- **Context:** Identifier-derived policy recreates hidden ranking and makes
  renames or migrations change authority.
- **Consequences:** Policy uses explicit principal/resource references and
  revisioned evidence. Sorting by ID is presentation-only.
- **OPEN:** Long-term namespace allocation and public identifier syntax.

## Consolidated OPEN questions

1. Which production authenticators and workload-identity mechanisms are
   required for the Dev Preview?
2. Are the logical trust authorities separate deployments or colocated
   modules with isolated state and APIs?
3. Which authorities issue capability permissions, organization roles, and
   general policy?
4. How are delegation, ownership transfer, and cross-authority transactions
   represented?
5. Which signature algorithms, trust roots, transparency mechanisms, and
   revocation channels are acceptable?
6. Which local secret backend, lease/injection protocol, rotation behavior,
   and redaction boundary satisfy release acceptance?
7. What event outbox, delivery, replay, retention, and schema-evolution model
   is canonical?
8. What is the migration order and compatibility window for current service
   actor/owner/source strings?
9. What bootstrap and recovery process creates or restores the first trusted
   human principal without circular self-authorization?
