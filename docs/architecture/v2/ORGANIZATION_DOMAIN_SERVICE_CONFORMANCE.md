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

## Deferred integrations

- Production Identity, Authorization, and Approval verification services are
  not implemented by this epic.
- Employee Registry v3 adoption is deferred. Employee references are checked
  through a narrow adapter and fail closed when unavailable.
- Event Delivery Service is not implemented. The service persists a local
  producer outbox only.
- Ownership transfer, recovery, cross-Organization collaboration, and deep
  Organization policy inheritance remain OPEN.
