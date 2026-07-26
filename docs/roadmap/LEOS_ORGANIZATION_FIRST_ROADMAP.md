# LEOS Architecture Update
## Roadmap Revision — Organization-First Development

**Status:** APPROVED

**Date:** 2026-07-25

**Audience:** Kepler, LEOS contributors, architecture reviewers, release planners

**Architecture reconciliation:** 2026-07-25, after Epic 2.2 commit `877c9f0`

---

# 1. Purpose

This document records the updated architectural direction, roadmap, and required features for LEOS.

It supersedes prior planning assumptions that treated manual employee creation as the primary user workflow.

This is the authoritative product direction for organization-first development.
It does not supersede the accepted authority boundaries or contract semantics in:

- `docs/architecture/v2/EXECUTION_PLANE.md`
- `docs/architecture/v2/EXECUTION_PLANE_DECISIONS.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE.md`
- `docs/architecture/v2/INTELLIGENCE_PLANE_DECISIONS.md`

Those documents and the canonical contracts govern current implementation.
Future concepts introduced here require explicit architecture, contracts, and
authority assignments before they become executable behavior. Where this
roadmap and an accepted v2 decision appear to conflict, implementation must
stop for reconciliation rather than silently changing either direction.

The new direction is **organization-first development**:

> The user describes what they want accomplished. LEOS designs, explains, configures, validates, and deploys the AI organization required to accomplish it.

Manual employee creation remains available for advanced users, but it is no longer the default onboarding or setup path.

---

# 2. Product Vision

LEOS is not merely a chatbot, agent launcher, or employee editor.

LEOS is an **AI Organization Operating System**.

Its purpose is to help users create, operate, govern, and improve complete AI organizations composed of:

- organizations
- departments
- teams
- employees
- workflows
- plugins
- capabilities
- tools
- models
- memory
- policies
- schedules
- approval gates
- knowledge sources
- automation

The primary experience should be understandable to a non-technical user.

A user should be able to say:

> “I want a team that monitors markets, researches companies, tracks my portfolio, and gives me a daily briefing.”

LEOS should determine and explain:

- which employees are required
- what each employee does
- how they report to one another
- which plugins and capabilities are needed
- which tools and data sources are required
- which model/provider options are suitable and what governed ranking the user
  may approve
- what permissions are necessary
- what information each employee may access
- how often each employee runs
- where human approval is required
- what the estimated resource and API cost will be
- how the team will be tested before activation

---

# 3. Foundational Design Principle

## Previous default

```text
User manually creates employees
        ↓
User manually assigns tools and models
        ↓
User manually creates workflows
        ↓
User manually configures permissions
        ↓
User manually tests the team
```

## New default

```text
User describes desired outcome
        ↓
LEOS designs the organization
        ↓
LEOS explains the proposal
        ↓
User reviews and answers setup questions
        ↓
LEOS presents dependency, permission, and activation plans
        ↓
User authorizes governed installation/configuration actions
        ↓
LEOS configures the organization
        ↓
LEOS validates and simulates it
        ↓
User approves activation
```

This principle must influence future work across:

- schemas
- APIs
- publishing
- plugin architecture
- capabilities
- employee definitions
- team definitions
- workflow orchestration
- permissions
- user interface
- onboarding
- model management
- testing
- templates
- marketplace behavior

---

# 4. Core Architectural Concepts

LEOS must preserve clear separation between the following concepts.

## Plugin

A deployable software package that provides one or more integrations, services, tools, or runtime extensions.

Examples:

- GitHub plugin
- Gmail plugin
- Slack plugin
- market-data plugin
- browser plugin
- coding-sandbox plugin

## Capability

A governed ability that may be granted to an employee or workflow.

Examples:

- read repositories
- create pull requests
- read email
- send email
- access market data
- execute code
- search the web

Capabilities are permission-bearing abstractions and must not be treated as identical to plugins.

## Tool

A callable operation exposed through a capability.

Example:

```text
GitHub Plugin
├── Capability: Repository Read
│   ├── Tool: Search code
│   ├── Tool: Read file
│   └── Tool: Inspect pull request
└── Capability: Repository Write
    ├── Tool: Create branch
    ├── Tool: Commit changes
    └── Tool: Open pull request
```

## Employee

A governed AI worker definition composed of:

- identity
- role
- responsibilities
- instructions
- memory
- assigned capabilities
- model policy
- permissions
- schedules
- escalation rules
- reporting relationships
- operational boundaries

## Team

A collection of employees and workflows working toward a shared purpose.

## Team Template

A reusable, publishable organization blueprint containing employees, workflows, dependencies, policies, and validation tests.

## Workflow

An automation or process connecting employees, tools, events, schedules, approvals, and outputs.

## Organization

The top-level operating structure containing departments, teams, employees, policies, knowledge, shared services, and governance.

These concepts must remain independently versioned and composable.

---

## Current authority alignment

The following boundaries apply while this roadmap is implemented:

| Roadmap concept | Current authority or status | Required interpretation |
|---|---|---|
| Employee definition and lifecycle | Employee Registry; current v2 compatibility contract and organization-aware `leos.employee-definition.v3` target | Existing `model_preferences` data is migration input; canonical provider/model order belongs to Ranking Policy Authority. v3 adoption requires an explicit migration. |
| Durable employee/assignment state | Persistent Employee Runtime | Team or organization services must not duplicate mailbox, working-state, or assignment authority. |
| Employee reasoning | Employee Cognitive Service | Team Architect may propose work and configurations but does not become a second cognitive runtime. |
| Capability/provider resolution | Capability Manager | A future Capability Store is publishing/discovery UX over canonical capability records and plugin declarations, not a peer runtime registry or resolver. |
| Provider/model ranking | Ranking Policy Authority | Recommendations become authority only after governed user acceptance; user ranking remains authoritative. |
| Model facts and runtime bindings | Model Registry | Plugins and templates reference governed model facts; they do not copy or own model inventory. |
| Invocation | Execution Dispatcher | Tools, plugin operations, and Team Architect actions that perform real work use the governed execution boundary. |
| Transport | AI Router or declared adapters | No roadmap feature may restore Router ranking, fallback, or substitution authority. |
| Scheduling and resources | Scheduler | Workflow, Team, and Organization layers submit governed work; they do not create peer lease or admission authorities. |
| Principal, actor, and resource ownership evidence | Identity Authority plus each domain lifecycle authority | Follow `../architecture/v2/IDENTITY_OWNERSHIP_AND_TRUST.md`; contract validity and caller strings never authenticate. |
| Authorization decisions | Authorization Authority | Subject/action/resource/context decisions do not rank, resolve, or invoke; policy and grant sources remain partly **OPEN**. |
| Approval grants | Approval Authority | Team Architect and templates may request approval but cannot manufacture or self-verify grants; only trusted current `VERIFIED` evidence authorizes. |
| Artifact trust | Artifact Trust Authority | Trust verification never publishes, installs, grants permissions for, or activates an artifact. |
| Secrets | Secret Authority for opaque reference identity; backend and transient resolution remain **OPEN** | Roadmap objects carry opaque requirements or references only, never credential values. |
| Workflow lifecycle | **OPEN** | `workflow-engine-service` is cataloged, and workflow correlation exists, but no canonical workflow definition/lifecycle authority is established in this repository. |
| Organization, Department, Team, Role, Position, Membership, and Position Occupancy lifecycle | Logical Organization Domain Authority | Epic 5.0 accepts one logical authority and canonical contracts. Production service/module topology, persistence, ownership transfer, cross-organization collaboration, and child-transition protocol remain **OPEN**. |
| Plugin and Tool lifecycle | **OPEN** | Repository licensing anticipates a public plugin SDK/manifest, but canonical package, install, grant, tool, and runtime contracts are not yet established. |
| Team Template publishing | **OPEN** | Team Templates are mandatory first-class future publishing objects, but their package, install, instance, upgrade, rollback, and activation contracts remain to be defined. |

The organization-first direction does not authorize parallel authorities. New
services must compose the authorities above through explicit contracts.

### Already implemented foundations

The repository already contains foundations that this roadmap must reuse:

- the canonical scheduler-to-runtime-to-cognition-to-dispatch execution spine;
- governed capability resolution with Capability Manager separated from
  invocation;
- Model Registry model facts and model-provider/runtime bindings;
- independent effective provider/model ranking with exact-list,
  first-ranked-valid, and `GOVERNED_ORDER_REQUIRED` semantics;
- employee-definition and lifecycle authority;
- employee resource profiles and scheduler eligibility/resource enforcement;
- installer, First Run, operator, security, and observability baselines;
- execution, resolution, correlation, lifecycle, and ranking contracts and
  conformance tests.

These are foundations, not proof that the Organization Domain production
service, Workflow, Plugin, Tool, Team Template, approval, secret, sandbox,
memory/knowledge, or publishing lifecycles are complete.

### Missing prerequisite architecture

Before Team Architect can safely deploy organizations, LEOS needs explicit
authority and contracts for:

1. production deployment/persistence, ownership transfer, migration, and
   child-transition protocol for the accepted Organization Domain contracts;
2. organization/team policy interaction with the existing
   `job > employee > capability > global` ranking scopes and cumulative hard
   restrictions;
3. Workflow definition, validation, lifecycle, scheduling projection,
   compensation, and correlation;
4. Plugin package identity, manifest, provenance, signature/trust,
   dependencies, compatibility, install/enable/update/rollback/remove
   lifecycle, and runtime isolation;
5. Capability declaration versus runtime inventory, employee/workflow grant,
   permission evaluation, revocation, and audit;
6. Tool identity, input/output schemas, capability exposure, idempotency,
   side-effect classification, adaptation, and Dispatcher invocation;
7. publishing artifact identity, versioning, dependencies, signatures,
   compatibility, installation instances, upgrades, rollback, removal, and
   provenance;
8. Team Template definition, composition, parameterization, validation,
   simulation, installed-instance, activation, upgrade, and rollback;
9. a plan/review/apply protocol so Team Architect proposals cannot become
   installation, permission, secret, cloud, or activation authority;
10. verifiable approvals, secret-reference resolution, sandboxing,
    memory/knowledge provenance, artifact authority, telemetry, and cost
    accounting.

---

# 5. Updated Development Roadmap

## Phase 1 — Define and Complete the Publishing Baseline

Finish the current Publishing Platform direction before expanding
implementation into the new roadmap.

The public repository currently establishes repository and licensing boundaries
for publishing, including a public plugin SDK/manifest direction and a private
marketplace-service boundary. It does not yet contain an authoritative
Publishing Platform architecture, artifact contract set, or complete remaining
epic plan. Those artifacts are a prerequisite for claiming end-to-end
publishing completion. The exact pre-existing publishing epic scope is
**OPEN** until its source and authority are recorded in this repository.

Immediate sequence:

1. Preserve Epic 2.2 as the completed governed ranking/resolution foundation
   (`877c9f0`).
2. Record the Publishing Platform authority, object model, lifecycle, and
   public/private boundary.
3. Define canonical publishing artifact and dependency contracts.
4. Review and approve the remaining publishing epic plan.
5. Complete the approved publishing epics.
6. Verify end-to-end publishing, installation, upgrade, rollback, and removal
   behavior.

Current work must not be discarded or prematurely redirected.

---

## Phase 2 — Full LEOS Core Audit

Perform a complete evidence-based audit of LEOS Core and Lucy donor implementations.

The audit must identify:

- what is implemented
- what is partially implemented
- what exists only in documentation
- duplicated or conflicting authority
- missing core services
- remaining Lucy dependencies
- incomplete contracts
- missing tests
- missing onboarding paths
- missing security controls
- missing installation and upgrade behavior
- missing model-service support
- missing sandbox and plugin infrastructure
- missing observability and recovery behavior

### Required output

`LEOS_DEV_PREVIEW_V2_GAP_REPORT.md`

Each gap must be classified as one of:

- Core Runtime
- Core Employee
- Plugin
- Capability
- Tooling
- Infrastructure
- Marketplace
- Security
- User Experience
- Post-v1
- Experimental
- Documentation Only
- Already Implemented

---

## Phase 3 — Lock Dev Preview v2.0 Must-Haves

Using the gap report, define and approve the Dev Preview v2.0 scope.

The Phase 3 lock artifacts are:

- `../architecture/v2/AUTHORITY_REGISTRY.md`, which records accepted owners,
  explicitly **OPEN** authorities, canonical vocabulary, event boundaries,
  forbidden overlaps, and compatibility/versioning rules; and
- `DEV_PREVIEW_V2_SCOPE_LOCK.md`, which records locked release outcomes,
  deferred scope, required architecture decisions, and release acceptance
  gates.

Neither artifact assigns an owner to an **OPEN** concern. The applicable
authority decision must be accepted before implementation begins.

The must-have scope should include, at minimum:

### Core runtime

- employee lifecycle
- team lifecycle
- organization lifecycle
- orchestration
- task scheduling
- workflow execution
- capability management
- governed model/provider resolution and transport
- memory and knowledge access
- permission enforcement
- approval gates
- audit logging
- observability
- failure handling
- retry and recovery
- sandbox execution

### Model and service setup

- local model registration
- cloud provider registration
- hardware detection
- required default models or services
- embeddings
- OCR
- speech-to-text
- text-to-speech
- vision
- governed provider/model re-resolution and escalation with no implicit
  fallback or substitution
- cost awareness
- resource awareness
- model installation
- model replacement
- model updates

Any required bootstrap model or service must be selected and registered through
governed setup and ranking. “Required default” does not authorize an implicit
provider/model default, emergency pool, or silent substitution.
Model installation, replacement, and update are administrative lifecycle
operations; they do not authorize changing the target of an active invocation.

### Publishing

- employees
- plugins
- capabilities
- workflows
- team templates
- organization templates where appropriate
- dependency declarations
- versioning
- compatibility
- trust and signatures
- installation
- upgrades
- rollback
- removal

### User experience

- guided onboarding
- Team Architect
- plugin setup
- model setup
- team visualization
- workflow visualization
- permission review
- approval review
- testing and simulation
- system health
- activity history
- cost visibility

## Phase 4 — Identity, Ownership, and Trust Foundation

Epic 4.0 establishes the common trust vocabulary required by every later
organization-first subsystem.

Canonical outputs are:

- `../architecture/v2/IDENTITY_OWNERSHIP_AND_TRUST.md`;
- `../architecture/v2/IDENTITY_OWNERSHIP_AND_TRUST_DECISIONS.md`;
- common Principal, Actor Context, resource identity, authorization decision,
  Approval Grant/verification, Artifact Trust, Secret Reference, and Event
  Envelope contracts under `../../contracts/`; and
- canonical semantic validation and negative conformance tests.

Phase 4 establishes logical authorities and contract boundaries. It does not
implement production authenticators, durable trust services, secret backends,
artifact publishing, organization lifecycle, or migrations into existing
services.

Every later epic must:

- identify the authenticated actor at each mutation;
- persist one canonical owner with the domain object;
- preserve creator, steward, lifecycle-authority, revision, and audit
  evidence;
- obtain authorization, approval, artifact trust, and secret use only from
  their recognized authorities;
- publish canonical transition events only from the state owner; and
- fail closed when trust evidence is absent, stale, revoked, mismatched, or
  unavailable.

Workflow, Plugin, Tool, Runtime, Artifact, Knowledge, and Memory lifecycle
owners that remain **OPEN** are not silently assigned by Phase 4. Organization
Domain ownership is assigned only by the later accepted Epic 5.0 decisions.

## Epic 5.0 — Organization, Team, and Employee Domain Foundation

Epic 5.0 establishes one logical Organization Domain Authority for
Organization, Department, Team, Role, Position, Membership, and Position
Occupancy, while Employee Registry remains Employee definition/lifecycle
authority.

Canonical outputs are:

- `../architecture/v2/ORGANIZATION_DOMAIN.md`;
- `../architecture/v2/ORGANIZATION_DOMAIN_DECISIONS.md`;
- organization-domain contracts and examples under `../../contracts/` and
  `../../examples/`; and
- deterministic, non-authoritative cross-record conformance validation.

The epic separates Membership, Position Occupancy, and work Assignment;
establishes Position hierarchy as canonical supervision; rejects cyclic,
orphaned, stale-revision, and unauthorized cross-organization relationships;
and preserves Team as collaboration only.

It does not implement a production Organization service, persistence
migration, policy engine, Team Architect, Assignment Service, runtime
orchestration, authentication provider, billing, or UI. Production topology,
organizational policy, ownership transfer/recovery, cross-organization
collaboration, Employee v2-to-v3 migration, and employee-to-job selection
remain **OPEN**. The Public Assignment Service remains
**CONFLICTING / INVESTIGATE**.

## Phase 5.0 — Non-authoritative Intelligence Test Fixture

The detailed implementation roadmap established after the Phase 3 scope lock
must place knowledge, memory, provenance, retrieval, and data-governance work
in Phase 5 before the production model/provider/runtime onboarding work in
Phase 6.

Phase 5 may use a narrowly scoped intelligence fixture so its contracts and
behavior can be tested without prematurely implementing or authorizing the
Phase 6 production onboarding system.

The fixture is:

- test/reference-only;
- deterministic by default;
- optionally backed by a pinned local embedding or reranking runtime for
  integration testing;
- prohibited from using cloud services or production credentials;
- not a production installation, activation, discovery, or onboarding path;
- not an authority over models, providers, ranking, health, or runtime
  activation;
- prohibited from creating a direct knowledge-plane or Cognitive Service
  model-invocation path;
- expected to use the canonical Capability Manager to Dispatcher to adapter
  path where practical;
- isolated from production configuration, persistence, and authority state;
- limited to temporary fixture-owned facts, bindings, rankings, and endpoint
  records when the canonical path requires them; and
- removable without production migration or compatibility obligations.

The deterministic fixture is the conformance default. An optional pinned local
runtime may prove real embedding or reranking integration, but its model,
runtime, package, and configuration choices do not become production
authority.

Phase 5 acceptance must prove:

1. deterministic fixture conformance;
2. optional real local embedding/reranking integration when the required
   runtime is available;
3. truthful failure, timeout, and malformed-response handling;
4. retained provenance and access scope through retrieval and context use;
5. no direct model invocation by the knowledge plane or Cognitive Service;
6. no cloud contact or production credential use; and
7. no fixture state in production authority stores or production
   configuration.

Phase 6 must rerun the same knowledge integration suite through the production
model/provider/runtime onboarding and activation path. Passing against the
Phase 5.0 fixture does not establish production onboarding conformance.

### Production per Token authority boundary

Production per Token (PPT) is observational and reporting evidence only. It is
never provider/model selection, eligibility, ranking, resolution, fallback,
retry, re-resolution, or escalation authority.

PPT must not:

- create hidden provider or model scores;
- automatically change or override user ranking;
- treat technical completion or low token use as productive value; or
- accept an employee's self-declaration that its output was productive.

The numerator must use externally grounded outcome evidence. Attribution must
include applicable retrieval, embedding, reranking, revision, verification,
token, provider, latency, and compute/resource costs. Reports must expose the
underlying outcome and cost evidence rather than only a composite number.

---

# 6. Plugin Layer — Required Prerequisite

The plugin layer is a **Dev Preview v2.0 must-have** and a prerequisite for the complete Team Architect experience.

Without a plugin layer, Team Architect can recommend organizations but cannot reliably equip or deploy them.

The plugin layer is core public infrastructure. Marketplace billing,
entitlement, fraud handling, and private moderation are not public-core runtime
responsibilities; the repository architecture assigns those concerns to a
separate private service. Premium and third-party plugins are optional
packages, not dependencies of a complete open-source core.

The public-core requirement includes plugin manifest/SDK contracts,
validation, a governed installation lifecycle, capability/tool registration
interfaces, permission declarations, isolation policy, health, audit, and
local package support. It does not require any particular proprietary
connector, hosted marketplace, billing system, third-party model weight, or
cloud service.

## Required plugin functions

The plugin system must support:

- plugin manifests
- stable plugin identifiers
- semantic versioning
- dependency declarations
- dependency resolution
- compatibility checks
- installation
- enable
- disable
- update
- rollback
- uninstall
- capability registration
- tool schema registration
- permission declarations
- secret and credential requirements
- sandbox policy
- filesystem access policy
- network access policy
- device access policy
- health checks
- diagnostics
- structured logging
- audit events
- test definitions
- validation
- signatures
- trust levels
- marketplace metadata
- deprecation
- migration behavior

## Plugin trust and permission model

A plugin must never implicitly grant all of its capabilities to an employee.

Employees receive only explicitly approved capabilities and tools.

Example:

```text
Plugin installed: GitHub

Employee A:
- Repository Read
- Pull Request Review

Employee B:
- Repository Read
- Repository Write
- Pull Request Creation

Employee C:
- No GitHub access
```

Least privilege is mandatory.

Installing a plugin registers what it can provide. It does not grant every
declared capability or tool to any employee, workflow, team, or organization.
Capability grants require a separate governed permission decision and remain
revocable.

## Team Architect dependency behavior

When designing a team, Team Architect must determine:

- which capabilities are required
- which installed plugins provide them
- which plugins are missing
- whether compatible alternatives exist
- whether local alternatives exist
- which credentials are required
- what permissions will be requested
- whether the plugin is trusted
- whether the plugin can run safely in the available environment
- estimated cost or resource impact

Example response:

> “This team requires repository access, issue tracking, a coding sandbox, and web research. GitHub and sandbox capabilities are installed. Jira support is missing. You may install the Jira plugin, choose another issue tracker, or continue without issue-tracker integration.”

---

# 7. Team Architect — New Core Employee

## Status

**CORE EMPLOYEE**

**MANDATORY**

**NOT OPTIONAL**

Team Architect is the primary guided setup experience for creating AI organizations.

“Core Employee” describes a required governed employee definition and user
experience. It does not make Team Architect a service authority. Team Architect
must operate through the canonical Employee Registry, Ranking Policy Authority,
Capability Manager, Model Registry, Dispatcher, Scheduler, and future
publishing, workflow, permission, approval, secret, and activation authorities.

## Purpose

Translate plain-language objectives into complete, governed, testable AI organizations.

## Primary responsibilities

Team Architect must be able to:

1. Understand the user's desired outcome.
2. Identify required work functions.
3. Propose employees and reporting relationships.
4. Recommend team structure.
5. Identify required plugins, capabilities, and tools.
6. Recommend models and execution policies for governed user acceptance.
7. Propose memory scopes and knowledge access.
8. Propose permissions, capability grants, and approval gates.
9. Propose schedules, triggers, and workflows.
10. Estimate operating cost and resource requirements.
11. Explain risks, limitations, and missing dependencies.
12. Ask only the setup questions needed to complete the design.
13. Generate a versioned organization proposal and configuration plan.
14. Validate dependencies and permissions.
15. Run a simulation or test scenario.
16. Present results to the user.
17. Request governed team activation only after approval.
18. Save the result as a reusable Team Template.
19. Reassess and improve existing teams later.

## Authority limits

Team Architect must not:

- silently install, update, enable, disable, roll back, or remove a plugin;
- grant permissions, capabilities, cloud access, or approval to itself or
  another employee;
- treat a caller Boolean or unverified reference as approval;
- write secret values into a proposal, template, prompt, event, log, or memory;
- override user provider/model ranking or invent fallback order;
- invoke a provider or tool outside Execution Dispatcher;
- mutate scheduler leases or resource admission;
- activate a Team or Organization by writing another authority's state;
- publish or install a Team Template without the governed review/apply path.

It proposes, explains, validates, simulates, and requests actions. The
appropriate canonical authority verifies and applies each approved action.

## Example interaction

### User

> “I want an investment research team.”

### Team Architect proposal

```text
Investment Research Team
├── Market Monitor
├── Company Researcher
├── Portfolio Analyst
├── Risk Reviewer
└── Research Manager
```

### Follow-up questions

- Which markets do you follow?
- Which data sources or brokerage services do you use?
- Do you want real-time alerts, scheduled reports, or both?
- Should the team provide research only, or prepare actions for approval?
- Which local or cloud models are allowed?
- What is the maximum acceptable operating cost?
- What risk rules should the team observe?
- Which information may be stored in long-term memory?

### Result

Team Architect proposes:

- employee definitions
- capability-grant requests
- plugin dependencies
- workflows
- schedules
- memory scopes
- reporting structure
- permission requests
- approval gates
- test scenarios
- activation checklist
- reusable Team Template

## Existing-team improvement

Team Architect should later support:

- detecting duplicated responsibilities
- identifying missing roles
- finding bottlenecks
- identifying excessive permissions
- proposing cheaper model-policy alternatives without changing user ranking
- identifying unused plugins
- detecting ineffective workflows
- recommending reviewers or approval gates
- testing proposed changes before application

---

# 8. Team Templates — First-Class Publishing Object

The Publishing Platform must support complete Team Templates, not only individual employees.

## A Team Template must be able to contain

- template identity
- purpose
- version
- required employees
- optional employees
- reporting structure
- workflows
- capability requirements
- plugin dependencies
- tool requirements
- model recommendations for governed user acceptance
- model constraints
- shared memory definitions
- employee memory boundaries
- knowledge-source requirements
- schedules
- triggers
- approval gates
- permissions
- opaque secret and credential requirements or references, never values
- cost guidance
- hardware guidance
- setup questions
- validation checks
- simulation scenarios
- expected outputs
- upgrade behavior
- rollback behavior

A published Team Template is an immutable versioned definition, not a running
Team and not proof of installation or activation. Installation creates a
separately identified configured instance. Activation is a later governed
transition. Template recommendations never override user ranking, hard
restrictions, permissions, cloud policy, or approval requirements.

## Example Team Templates

- Software Development Team
- Market Research Team
- Small Business Operations Team
- Customer Support Team
- Content and Marketing Team
- Personal Knowledge Team
- Home Automation Team

## Target installation flow

```text
Select Team Template version
        ↓
Review provenance, compatibility, dependencies, plugins, and permissions
        ↓
Answer setup questions
        ↓
Create governed installation plan
        ↓
Authorize installation actions and connect opaque credential references
        ↓
Select models and cost limits
        ↓
Run validation
        ↓
Run simulation
        ↓
Approve activation
```

This flow is central to the measurable product target of a useful AI
organization in approximately 30 minutes. It is not a release or marketing
guarantee until demonstrated by acceptance testing.

---

# 9. Core LEOS Employees

Every standard LEOS installation should include governed definitions or
templates for the following LEOS-operating employees. Inclusion does not grant
capabilities, credentials, approval, or automatic activation.

Team Architect is the mandatory core employee and primary organization-first
experience. LEOS Guide, System Administrator, Knowledge Curator, and Workflow
Builder are bundled core-role candidates whose activation and permissions
remain subject to product-scope approval and least privilege.

## Team Architect

Designs, proposes configuration for, validates, and coordinates governed
deployment of teams and organizations.

## LEOS Guide

Explains LEOS concepts, navigation, setup, and common workflows.

## System Administrator

May be granted governed capabilities to manage:

- system health
- models
- providers
- storage
- plugins
- services
- updates
- diagnostics
- backups
- operational alerts

## Knowledge Curator

Manages:

- imports
- classification
- indexing
- deduplication
- provenance
- confidence
- retention
- archival
- knowledge hygiene
- memory review

## Workflow Builder

Turns repeated work into governed workflows and automations.

These core employees operate LEOS itself. They are distinct from user-created business teams.

No employee persona replaces the canonical service that owns the state it
manages. In particular, System Administrator is not an ambient superuser, and
Knowledge Curator is not itself the memory or provenance storage authority.

---

# 10. History and Knowledge Import

History import is a required future core feature once memory and knowledge ingestion are stable.

The core requirement is a governed ingestion, provenance, classification,
review, correction, retention, and deletion pipeline. Source-specific
connectors such as Gmail, Slack, Teams, or commercial conversation platforms
should normally be plugins and are not individually required parts of the
public core.

## Target import sources

- ChatGPT exports
- Claude exports
- Gemini exports
- documents
- repositories
- email
- calendars
- notes
- Slack
- Teams
- other supported conversation archives

## Import requirements

LEOS must separate:

- raw imported history
- extracted facts
- preferences
- decisions
- tasks
- project references
- temporary context
- sensitive information
- uncertain or conflicting claims

Extracted knowledge should include:

- provenance
- confidence
- source references
- timestamps
- last-confirmed date
- review status
- retention policy
- sensitivity classification

The Knowledge Curator should process imported data.

Team Architect may use approved imported knowledge to make better recommendations.

Example:

> “Your imported history shows frequent use of Docker, Ubuntu, GitHub, and local servers. I recommend including a Linux Operations employee and Repository Reviewer in your development organization.”

Imported history must not be treated as unquestioned truth.

Users must be able to review, correct, reject, expire, or restrict extracted profile items.

---

# 11. Flagship Demonstration Teams

Before broad public release, LEOS should include polished demonstration templates.

Priority templates:

1. Small Business Operations Team
2. Software Development Team
3. Market Research Team
4. Customer Support Team
5. Content and Marketing Team
6. Personal Knowledge and Research Team

The market-research demonstration should focus on:

- monitoring
- research
- analysis
- alerts
- summaries
- scenarios
- decision support

It should not imply guaranteed results or uncontrolled autonomous trading.

Flagship Team Templates are reference content and acceptance fixtures. They are
important release deliverables, but their individual business domains are not
new core runtime authorities.

---

# 12. Success Criteria

A non-technical user should be able to create a useful AI organization in approximately 30 minutes.

The user should not need to understand the implementation details of:

- models
- embeddings
- vector databases
- tool schemas
- orchestration
- plugin manifests
- capability bindings
- workflow internals
- sandbox policies

unless the user chooses advanced configuration.

## Product-level success experience

The user should be able to say:

> “Build me a customer support team.”

LEOS should:

- propose the team
- explain the design
- present and, after authorization, apply governed dependency plans
- request permissions
- connect data sources
- configure employees
- test the result
- request governed activation after explicit approval
- continue improving it over time

---

# 13. Guidance for Future Development

When evaluating implementation options, prefer designs that support:

- organization-first workflows
- plain-language setup
- guided configuration
- composable employees
- reusable Team Templates
- explicit plugins
- explicit capabilities
- least privilege
- human approval
- simulation before activation
- provenance
- auditability
- model portability
- local-first deployment
- cloud optionality
- recoverability
- long-term maintainability
- marketplace distribution
- clear upgrade paths

Avoid designs that:

- require manual employee setup as the default
- collapse plugin, capability, and tool concepts
- grant broad permissions implicitly
- hide dependencies
- bypass user approval
- bind teams permanently to one model provider
- make imported memory unauditable
- make templates impossible to test or validate
- depend on Lucy as an undocumented runtime authority

---

# 14. Current Priority Order

```text
Preserve completed Epic 2.2 baseline (877c9f0)
        ↓
Define Publishing Platform authority and contracts
        ↓
Finish approved Publishing Dev Preview epics
        ↓
Perform Full Core and Lucy Evidence Audit
        ↓
Produce Dev Preview v2.0 Gap Report
        ↓
Lock v2.0 Architecture and Must-Haves
        ↓
Implement Core Runtime Gaps
        ↓
Implement Plugin Layer
        ↓
Stabilize Capability Registry and Permission Model
        ↓
Implement Knowledge, Memory, Provenance, and Data-Governance Contracts
        ↓
Establish Phase 5.0 Non-authoritative Intelligence Test Fixture
        ↓
Pass Phase 5 Knowledge Conformance and Optional Local Integration
        ↓
Complete Phase 6 Production Model/Provider/Runtime Onboarding
        ↓
Rerun the Phase 5 Knowledge Integration Suite Through Phase 6
        ↓
Define Team Template Contract
        ↓
Implement Team Architect v1
        ↓
Implement Core LEOS Employees
        ↓
Implement Guided Installation and Organization Setup
        ↓
Implement History and Knowledge Import
        ↓
Build Flagship Team Templates
        ↓
Release Public Dev Preview v2.0
        ↓
Harden Toward LEOS v1.0
```

---

# 15. Architectural Direction

The correct hierarchy for future planning is:

```text
User
└── Organization
    ├── Departments
    │   ├── Teams
    │   │   ├── Employees
    │   │   └── Workflows
    │   └── Shared Knowledge
    ├── Plugins
    ├── Capabilities
    ├── Tools
    ├── Models
    ├── Memory
    ├── Policies
    ├── Approvals
    └── Automation
```

LEOS is evolving from an AI Employee Operating System into an **AI Organization Operating System**.

Employees remain fundamental, but they are one component of the larger system.

This hierarchy is a product composition model, not a declaration that every
node already has a canonical service or persistence owner. Epic 5.0 accepts
one logical Organization Domain Authority for Organization, Department, Team,
Role, Position, Membership, and Position Occupancy, but its production
topology and persistence remain **OPEN**. Workflow and Automation authorities
remain **OPEN** until their architecture and contracts are accepted.
Organization or Team policy must not silently add ranking precedence ahead of
the currently adopted independent
`job > employee > capability > global` provider/model scopes.
Future organizational policy may add cumulative restrictions or new ranking
scopes only through an explicit intelligence-plane decision and governed
migration.

---

# 16. Instruction to Kepler

Use this document as approved roadmap and architecture guidance.

For current in-progress work:

- finish the existing scoped task
- do not introduce unrelated implementation changes
- do not commit unless explicitly instructed
- record conflicts between current contracts and this direction
- preserve evidence and provenance
- identify where current schemas or architecture will block the roadmap
- propose follow-up epics instead of silently expanding scope

Future planning and architecture work must account for:

- the plugin layer
- capabilities and tools
- Team Templates
- Team Architect
- organization-first onboarding
- core LEOS employees
- guided deployment
- history import
- testable and reusable organizations

This document represents the current approved direction for LEOS.
