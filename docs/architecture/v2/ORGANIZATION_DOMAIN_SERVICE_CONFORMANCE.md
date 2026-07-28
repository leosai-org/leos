# LEOS v2 Organization Domain Service Conformance

## Status

Epic 8.2 implements the accepted Organization Domain Service authority from
ADR-DPV2-001.

## Authority boundary

The service is the single Dev Preview v2 production owner for:

- Organization, Department, Team, Role, Position, Membership, and Position
  Occupancy records;
- Organization Domain lifecycle transitions;
- Organization Domain revision lineage and append-only audit records; and
- Organization Domain producer outbox records.

It does not own Employee lifecycle, Authorization, Approval, Work,
Assignment, Scheduler, Runtime, Capability, Dispatcher, Secret, Artifact,
Plugin, Tool, Team Template, or Event Delivery authority.

## Contract adoption

The API accepts and returns canonical Organization Domain contracts at its
resource boundaries. Service-local persistence stores canonical JSON records
and does not introduce a permanent parallel resource model. Cross-record
validation reuses `validate_organization_domain`.

## Authorization verification

Epic 8.6A replaces structural Authorization Decision reference acceptance on
protected mutations with live Authorization Authority verification of
`leos.authorization-evidence-binding.v1`.

Protected operation mappings:

| Operation | Action | Resource | Context |
| --- | --- | --- | --- |
| Create Organization Domain record | `organization-domain.record.create` | created record identity and revision | `organization-domain.mutation` / `create:{resource_type}:{resource_id}` |
| Update Organization Domain record | `organization-domain.record.update` | current path identity at `expected_revision` | `organization-domain.mutation` / `update:{resource_type}:{resource_id}:{expected_revision}` |
| Lifecycle transition | `organization-domain.record.transition` | current path identity at `expected_revision` | `organization-domain.mutation` / `transition:{resource_type}:{resource_id}:{expected_revision}:{to_status}` |

The service verifies the exact Actor Context evidence reference,
Authorization Decision reference, Organization reference, action, resource,
resource revision, context identifier, context revision, context digest, and
expected `ALLOW` outcome. Authorization Authority unavailability, timeout,
malformed response, denial, expiry, revocation, wrong issuer, or mismatched
verification response fails closed.

The service does not issue Authorization Decisions, infer permissions from
roles or memberships, implement Identity Authority, or implement Approval
Authority. Existing Actor Context and Authorization Decision references remain
lineage fields only; the verified binding is the operation gate.

Audit history stores the binding and normalized verification evidence beside
the prior Actor Context and Authorization Decision lineage.

## Deferred integrations

- Production Identity and Approval verification services are not implemented
  by this epic.
- Employee Registry v3 adoption is deferred. Employee references are checked
  through a narrow adapter and fail closed when unavailable.
- Event Delivery Service is not implemented. The service persists a local
  producer outbox only.
- Ownership transfer, recovery, cross-Organization collaboration, and deep
  Organization policy inheritance remain OPEN.
