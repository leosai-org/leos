# Authorization Evidence Binding Conformance

Epic 8.6.0 defines `leos.authorization-evidence-binding.v1`, the reusable
canonical input shape for later Authorization Authority consumer integration.

## What the binding is

An Authorization Evidence Binding records the exact facts a consumer expects
Authorization Authority to verify for one authorization-sensitive operation:

- the revision-pinned Authorization Decision reference;
- the canonical Actor Context evidence reference supplied to verification;
- the revision-pinned Organization reference;
- the expected subject/action/resource/context scope; and
- the expected decision outcome.

The binding lets a consumer submit a deterministic verification tuple without
retrospectively interpreting what an existing Authorization Decision meant.

## What the binding is not

The binding is not:

- an Authorization Decision;
- an approval artifact;
- identity evidence;
- authentication proof;
- a permission grant;
- a capability, provider, model, plugin, role, membership, or assignment
  shortcut;
- proof that Authorization Authority verified anything; or
- authority to continue when Authorization Authority is unavailable.

Structural validity proves only that the tuple is well-shaped. It never proves
that the referenced decision exists, was issued by Authorization Authority, is
unexpired, is unrevoked, or matches the expected scope.

## Authority boundary

Authorization Authority remains the only authority that issues Authorization
Decisions, verifies Authorization Decisions, evaluates decision outcome,
expiration, revocation, and stores authorization audit lineage.

Consumers may construct, receive, persist, and submit a binding. Consumers must
fail closed when verification fails or the authority is unavailable. Consumers
must not issue decisions, rewrite decisions, infer missing scope, or treat the
binding itself as authorization.

Identity Authority remains responsible for Actor Context issuance and
authentication-related evidence. Epic 8.6.0 does not implement Identity
Authority, authenticate principals, or claim trusted actor issuance.

Approval Authority remains separate. Approval references, grants, and
verification results cannot replace Authorization Authority verification.

## Stale revision, expiration, and revocation

The binding pins the expected Authorization Decision revision, Actor Context
evidence revision, Organization revision, resource revision, context revision,
and context digest. A consumer must compare the returned verified decision
reference to the binding's `authorization_decision_ref` and reject stale or
mismatched revisions.

Authorization Authority evaluates expiration and revocation from its own
durable state. The binding does not copy or override those facts.

## Capability and execution boundaries

Capability presence is not permission. Plugin installation is not permission.
Role or Membership is not permission. Assignment is responsibility only.

Future Epic 8.6B will allow Capability Manager and Dispatcher request
contracts to carry this binding without changing their accepted authorities:

- Capability Manager resolves capabilities and providers; it does not invoke.
- Dispatcher invokes the already resolved target; it does not select.

Future Epic 8.6A will integrate Organization Domain, Work Coordination,
Scheduler, and Persistent Runtime consumers using this binding or an explicitly
approved equivalent migration shape.

## Conformance requirements

The schema and package tests must prove:

- required references are present and revision-pinned;
- Actor Context uses `actorContextEvidenceRef`, not a generic resource ref;
- expected scope is explicit and uses canonical `actionScope`;
- unsupported expected decisions fail;
- caller authorization or approval Booleans fail;
- raw credential or secret fields fail;
- embedded Authorization Decision JSON fails;
- embedded Actor Context documents fail; and
- all six canonical consumer examples validate.

No consumer adapter, live Authorization Authority call, Capability Manager
request adoption, Dispatcher request adoption, service behavior change, or
production authority is implemented by Epic 8.6.0.
