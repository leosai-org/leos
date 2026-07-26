# LEOS v2 Authority Registry

## Status and purpose

This registry is the LEOS 0.2.0 Developer Preview v2 index of accepted
authority boundaries and explicitly unresolved authority gaps.

It consolidates decisions already accepted in:

- `EXECUTION_PLANE.md`
- `EXECUTION_PLANE_DECISIONS.md`
- `INTELLIGENCE_PLANE.md`
- `INTELLIGENCE_PLANE_DECISIONS.md`
- `EXECUTION_CONTRACTS.md`
- `IDENTITY_OWNERSHIP_AND_TRUST.md`
- `IDENTITY_OWNERSHIP_AND_TRUST_DECISIONS.md`
- `ORGANIZATION_DOMAIN.md`
- `ORGANIZATION_DOMAIN_DECISIONS.md`
- `CAPABILITY_PLUGIN_AND_TOOL_DOMAIN.md`
- `CAPABILITY_PLUGIN_AND_TOOL_DOMAIN_DECISIONS.md`
- `WORK_WORKFLOW_AND_ASSIGNMENT_DOMAIN.md`
- `WORK_WORKFLOW_AND_ASSIGNMENT_DOMAIN_DECISIONS.md`
- `DEV_PREVIEW_V2_BLOCKING_AUTHORITY_DECISIONS.md`
- `EFFECTIVE_RANKING_AND_MODEL_RESOLUTION.md`
- `../../roadmap/LEOS_ORGANIZATION_FIRST_ROADMAP.md`
- `../../roadmap/LEOS_DEV_PREVIEW_V2_GAP_REPORT.md`

This document does not assign an owner to a concern that the accepted
sources leave **OPEN**. It records owners only when an accepted decision names
one, and prevents an implementation from acquiring authority merely because
it is convenient, cataloged, present in Lucy, or first to persist a new
object.

If this registry conflicts with an accepted plane decision, the plane decision
governs until the conflict is corrected. A future accepted ADR may update this
registry.

## Registry states

| State | Meaning |
|---|---|
| **ACCEPTED** | The canonical responsibility and owner are established by accepted architecture. |
| **COORDINATOR ONLY** | The component may initiate or coordinate governed work but is not the continuing state authority. |
| **OPEN** | Canonical ownership or the precise boundary is not accepted. Implementation must stop before creating a new authority. |
| **PROJECTION ONLY** | The component may retain a derived view but not originate or override canonical state. |
| **TRANSPORT ONLY** | The component carries an already-authorized operation and has no selection or governance authority. |
| **DONOR EVIDENCE ONLY** | Lucy or other historical behavior may be inspected but has no v2 authority. |
| **CONFLICTING / INVESTIGATE** | A current surface overlaps accepted owners and requires explicit migration, compatibility, and retirement review. |
| **DEPRECATED / RETIRE** | The responsibility conflicts with the accepted target and must not receive new canonical behavior. |

Implementation maturity is separate from authority state. An **ACCEPTED**
authority may still be incomplete, while a working Lucy service may remain
**DONOR EVIDENCE ONLY**.

## Accepted canonical authorities

| Concern or canonical object | Authority | State authority | Required boundary |
|---|---|---|---|
| Principal definition and lifecycle | Identity Authority | Principal identities, subject bindings, status, authentication-policy references, and revisions | Does not own domain resources, permission policy, approval, secrets, capability resolution, or execution. |
| Authenticated actor evidence | Identity Authority | Bounded Actor Context evidence after recognized authenticator verification | Contract validity or caller construction never authenticates; production authenticators remain **OPEN**. |
| Subject/action/resource authorization decision | Authorization Authority | Revisioned, evidence-backed, time-bounded allow/deny decisions, Dev Preview policy inputs, and capability permission grants | Does not authenticate, rank, resolve capabilities, issue approvals, verify work, or invoke. Advanced policy inheritance and external policy sources remain **OPEN**. |
| Common resource identity and ownership | Each accepted domain lifecycle authority | Its resource identity, exactly-one-owner evidence, revision, lifecycle transition, and audit identity | Identity Authority validates principal references; no central peer resource/ownership store. **OPEN** domain objects remain blocked. |
| Approval request, grant, and verification | Approval Authority | Requests, authenticated decisions, grant lifecycle, expiry, revocation, consumption, verification, audit, and events | Only trusted current `VERIFIED` evidence authorizes; no caller Boolean, reference existence, copied grant, or event authority. |
| Artifact trust evidence | Artifact Trust Authority | Digest, signature, provenance, trust-policy verification, and trust revocation evidence | Never publishes, installs, configures, grants, approves, or activates. Artifact Authority owns artifact lifecycle and Plugin and Tool Lifecycle Authority owns installation/activation. |
| Secret-reference identity | Secret Authority | Opaque reference identity, protected-value lifecycle, backend boundary, transient use, rotation, redaction, deletion, and audit | Reference possession never authorizes resolution; enterprise backend/federation remains **OPEN**. |
| Canonical event production | Authority that owns the represented state transition | Immutable event identity, source, producer, actor, subject revision, correlation, causation, time, schema revision, and producer outbox | Event Delivery Service owns delivery/replay infrastructure only; projections remain non-authoritative. |
| Job lifecycle | Scheduler | Jobs and scheduler-owned job transitions | Does not own employee reasoning, provider resolution, or assignment working state. |
| Job target contract | Scheduler | Organization-scoped instantiated work identity, source Work Request/Workflow revision, state, outputs, governance, and closure evidence after explicit service adoption | `leos.job-definition.v1` is a target contract; Epic 7.0 does not migrate Scheduler APIs or storage. |
| Worker lease | Scheduler | Lease identity, acquisition, renewal, and release | No workflow, runtime, or coordinator may create a peer lease authority. |
| Compute/resource admission | Scheduler | Admission decisions and resource reservations | Employee resource profiles supply governed inputs; they do not admit work. |
| Employee resource profile | Employee Resource Profile Service | Canonical employee resource requirement/profile records | Does not select models or providers and does not replace Scheduler admission. |
| Employee definition and lifecycle | Employee Registry | Employee definitions, revisions, lifecycle, execution-eligibility decisions, and assignment-policy inputs | Legacy embedded model preferences are migration input, not ranking authority; Work Coordination Service owns Dev Preview assignment decisions. |
| Organization, Department, and Team lifecycle | Organization Domain Service | Definitions, revisions, ownership, lifecycle, hierarchy, policy references, and canonical transition events | Implements the logical Organization Domain Authority with one authoritative store and outbox. Ownership transfer, recovery, inheritance, cross-Organization collaboration, and deep policy inheritance remain **OPEN**. |
| Role and Position lifecycle | Organization Domain Service | Reusable responsibility definitions, concrete organizational slots, revisions, and reporting-position hierarchy | Role is not authorization. Position is not Employee identity or work Assignment. |
| Membership lifecycle | Organization Domain Service | User/Employee Organization/Team relationships, effective periods, issuer evidence, revisions, and history | Membership and Role never independently authorize permission, capability use, assignment, or execution. |
| Position Occupancy lifecycle | Organization Domain Service | Employee-to-Position relationships, effective periods, revisions, and history | Occupancy is neither Membership nor work Assignment. |
| Durable employee presence and mailbox | Persistent Employee Runtime | Durable employee presence, mailbox, and working-state storage | No reasoning, provider invocation, or scheduler lease ownership. |
| Assignment projection and transitions | Persistent Employee Runtime | Assignment identity, durable projection, and runtime-owned transitions | Scheduler remains job/lease authority; Cognitive Service remains reasoning authority. |
| Assignment target contract | Persistent Employee Runtime | Durable accepted responsibility projection for exact Job/Task scope after explicit service adoption | Work Coordination Service owns assignment decisions; Persistent Runtime owns acceptance, projection, and runtime assignment transitions. Assignment never authorizes or executes. |
| Cognitive run | Employee Cognitive Service | Cognitive runs, attempts, checkpoints, observations, and cognitive results | No direct scheduler mutation, durable assignment ownership, or provider invocation. |
| Provider/model ranking | Ranking Policy Authority | User-authored ranking policies, scope resolution, and effective-ranking evidence | Ranking establishes order only. It does not evaluate provider eligibility or invoke targets. |
| Model facts | Model Registry | Normalized model identity, model facts, lifecycle, and revisions | No provider inventory, ranking, resolution, credentials, or invocation. |
| Model-provider/runtime binding | Model Registry | Binding identity, facts, lifecycle, and revision | Capability Manager consumes bindings; it does not copy their authority. |
| Provider inventory | Capability Manager | Provider records and revisions | Standalone Provider Registry is migration input and a retirement target. |
| Capability inventory | Capability Manager | Capability records and revisions | Capability presence does not imply a permission grant. |
| Capability definition target contract | Capability Manager | Canonical capability identity, version, contract references, risk, compatibility constraints, lifecycle, and revision after explicit service adoption | `leos.capability-definition.v1` is a target contract; Epic 6.0 does not migrate current service storage or APIs. |
| Provider definition target contract | Capability Manager | Canonical provider identity, type, capability/configuration/health references, credential-reference requirements, runtime requirements, lifecycle, and revision after explicit service adoption | `leos.provider-definition.v1` contains no raw secret or invocation endpoint; model bindings remain Model Registry authority. |
| Provider-capability binding | Capability Manager | Provider-capability bindings and revisions | Model bindings remain Model Registry authority. |
| Eligibility and capability resolution | Capability Manager | Candidate eligibility decisions, resolutions, and rationale | Consumes governed order; never invokes, adapts payloads, or silently reorders. |
| Provider/tool invocation | Execution Dispatcher | Executions, authorized targets, invocation attempts, normalized results, and execution audit | Sole normal-path invocation authority; never selects provider/model alternatives. |
| Provider protocol adaptation | Dispatcher-owned adapter or AI Router | Transport-local operational state only | **TRANSPORT ONLY**; no ranking, substitution, fallback, escalation, or independent retry authority. |
| Provider/tool local operation | Selected provider or tool | Provider-local operational state only | Performs only the selected bounded operation and owns no LEOS lifecycle decision. |
| Execution observation/await | Runtime Execution Coordinator, if retained | Observation/correlation state only | **PROJECTION ONLY**; no scheduler driving, assignment restart, lease reconciliation, or normal execution participation. |
| Initial setup coordination | First Run | First-run session, configuration, readiness, and result records within existing contracts | **COORDINATOR ONLY**; Runtime Activation Authority owns continuing runtime activation and rollback. |
| Installation planning and bootstrap | Existing installer tools within their documented scope | Installation plan, journal, transaction, and result evidence | Does not establish the future plugin/artifact publishing authority. |
| Operator inspection | LEOS operator/doctor tooling within its documented scope | Read-only status, doctor, service, log-query, backup-plan, and update-plan evidence | Backup and update plans are not execution authority. |
| Execution contract definitions | Repository-root `contracts/` | Canonical JSON Schema definitions | Runtime validation belongs to `packages/leos-contracts`; schema copies do not become authority. |
| Contract semantic validation | `packages/leos-contracts` | Canonical cross-contract semantic validation behavior | No parallel semantic validator may reinterpret the same canonical contract. |
| Source development | `leos-v2` | Writable Dev Preview v2 source | Lucy is never writable source authority. |
| Lucy donor behavior | None | None | **DONOR EVIDENCE ONLY** until deliberately promoted under canonical contracts and tests. |
| Production per Token | No runtime authority | Observational/reporting evidence only | Never selection, eligibility, ranking, resolution, fallback, retry, re-resolution, or escalation authority. |
| Phase 5.0 intelligence fixtures | None | Isolated test state only | Test/reference-only and removable; no production model, provider, ranking, health, or activation authority. |
| Work Domain reference conformance | None | Deterministic in-memory schema, reference, revision, scope, DAG, lifecycle, responsibility, and lineage checks | **DONOR/TEST EVIDENCE ONLY**; no selection, assignment, scheduling, approval, verification, persistence, or execution authority. |
| Organization Domain production topology and store | Organization Domain Service | Organization Domain resources, lifecycle transitions, and outbox records | Single production owner for Dev Preview; no peer Organization, Team, Role, Position, Membership, or Occupancy authority. |
| Work Request lifecycle | Work Coordination Service | Work Request intake, review, acceptance, rejection, conversion, and events | Work Request never authorizes, selects, approves, verifies, or becomes a Job without a governed transition. |
| Workflow Definition and Revision lifecycle | Work Coordination Service | Workflow Definition records, immutable Workflow Revisions, publication, selection, deprecation, and events | Definitions/Revisions are reusable structures, not running instances or Scheduler state. |
| Task, Dependency, Retry Intent, and Escalation Intent lifecycle | Work Coordination Service | Task records, dependency readiness, retry intents, escalation intents, projection records, and events | Tasks are work records; dependencies do not schedule; intents do not retry, reassign, select, or execute by themselves. |
| Assignment decision | Work Coordination Service | Assignment decision, rationale, assignee target, and handoff records | Persistent Runtime owns acceptance/projection after handoff; Public Assignment and Employee Registry legacy `/resolve` remain non-canonical. |
| Delegation lifecycle | Work Coordination Service | Same-Organization responsibility sub-allocation, chain, acceptance evidence, supersession, and events | Delegation cannot expand scope, cross Organizations, authorize, approve, schedule, or execute. |
| Authorization policy, capability permission grants, and authorization decisions | Authorization Authority | Dev Preview authorization policy inputs, capability permission grants, revocation, and subject/action/resource/context decisions | Does not authenticate, approve, rank, resolve, invoke, or verify work. Default deny. |
| Event delivery and replay infrastructure | Event Delivery Service | Delivery cursors, subscriptions, acknowledgements, replay requests, dead-letter records, and retention mechanics | Producing authority owns event content and outbox; delivery never becomes state authority. |
| Work Result lifecycle and acceptance | Work Coordination Service | Work Result records, producer linkage, acceptance/rejection transitions, artifact-link references, and events | Result acceptance is not verification or closure. |
| Artifact lifecycle and linkage verification | Artifact Authority | Artifact identity, versions, digest/provenance records, publication lifecycle, derivation, retention, linkage verification, and events | Artifact Trust verifies trust evidence only and does not publish, install, activate, authorize, approve, or execute. |
| Work verification and closure | Work Coordination Service | Verification requests/decisions, closure transitions, evidence links, and events | Approval is not verification; Scheduler completion is not closure. |
| Runtime activation lifecycle | Runtime Activation Authority | Desired/observed runtime state, activation attempts, health observations for activation, deactivation, rollback, and events | First Run coordinates only; Model Registry and Capability Manager retain their own registration authorities. |
| Plugin and Tool lifecycle | Plugin and Tool Lifecycle Authority | Plugin Definitions, Manifests, installations, activations, configuration, dependency locks, Tool catalog ingestion, Capability Profiles, compatibility observations, revocation, and events | Installation/activation never grants trust, permission, approval, eligibility, resolution, or execution; Dispatcher remains invocation authority. |
| Sandbox and workspace lifecycle | Sandbox Authority | Sandbox profiles, workspace identity, policy evaluation, filesystem/network/process/resource/secret/artifact boundaries, violation evidence, cleanup, attestation, and events | Sandbox establishes boundaries for separately authorized work; it does not authorize, resolve, invoke, approve, verify, or grant capability use. |
| Team Template and Team Architect apply lifecycle | Team Template Authority | Team Template definitions/versions, installed template instances, Team Architect proposal/apply/save records, validation, simulation/test-run, activation plans, upgrade/rollback records, and events | Team Architect is a governed Employee and never becomes superuser, publisher, installer, approver, secret, workflow, scheduler, dispatcher, or activation authority. |

## Explicitly OPEN authorities

An **OPEN** row is an implementation stop boundary. A package may define and
seek approval for the authority; it may not silently choose one.

| Concern | What is established | What remains OPEN | Interim prohibition |
|---|---|---|---|
| Production authentication and trust bootstrap | Principal model and Actor Context owner are accepted | Human/workload authenticators, proof formats, recovery, session revocation, first-principal bootstrap, and deployment topology | Caller strings, employee IDs, development assurance, or schema-valid Actor Context documents must not become production authentication. |
| Ownership policy and transfer | Common exactly-one-owner evidence and domain-state ownership are accepted | Domain transfer, inheritance, visibility, archival, and cross-authority reconciliation policy | New services must not invent incompatible owner fields or treat ownership as authorization. |
| Long-term event evolution | Canonical envelope, producer authority, per-authority outbox ownership, and Event Delivery Service delivery/replay ownership are accepted for Dev Preview | Long-term schema evolution, cross-installation federation, and global retention policy | Event existence or receipt must not replace canonical state or transfer ownership. |
| Publishing artifact metadata | Public/private repository boundary is documented | Core publishing owner and artifact object model | Release-publication evidence must not be reused as plugin/template publishing authority. |
| Artifact version and dependency lifecycle beyond Dev Preview | Artifact Authority owns artifact lifecycle/linkage and Plugin and Tool Lifecycle Authority owns Dev Preview dependency locks | Hosted publishing, marketplace dependency policy, acquisition networks, and long-term package envelope evolution | Contract or validator output must not become a package manager or publication authority. |
| Installed artifact instance beyond Dev Preview | Plugin and Tool Lifecycle Authority owns Dev Preview install/configure/activate/update/rollback/remove lifecycle | Hosted marketplace installation topology and advanced data-ownership transfer policy | Installation and activation must not imply trust, permission, approval, eligibility, resolution, or execution. |
| Organization Domain transfer and advanced topology | Organization Domain Service production owner and store are accepted for Dev Preview | Ownership transfer, recovery, inheritance, nested Organization ownership, and cross-authority reconciliation policy | No implementation may create peer Organization, Department, Team, Role, Position, Membership, or Occupancy authorities. |
| Organization ownership transfer and recovery | A v1 Organization has one Human User owner and one Organization Principal | Transfer, recovery, inheritance, and nested Organization ownership protocol | Caller owner fields, file moves, projections, or events must not transfer ownership. |
| Cross-organization collaboration | Organization is the accepted isolation boundary | Delegation, visibility, knowledge/secret/permission access, and audit protocol | Cross-organization references fail closed until accepted. |
| Assignment optimization and workforce policy beyond Dev Preview | Work Coordination Service owns Dev Preview assignment decision records; Employee Registry owns definition, eligibility, and assignment-policy inputs | Advanced matching, optimization, scoring policy, and compatibility duration for Employee Registry legacy `/resolve` | Legacy scoring, identifier order, caller `force`, or a second job store must not become canonical assignment authority. |
| Organizational policy | Current ranking precedence remains `job > employee > capability > global` | Restriction inheritance and whether organization/team ranking scopes ever exist | Organizational policy may not silently add ranking precedence or reorder candidates. |
| Workflow lifecycle beyond Dev Preview minimum | Work Coordination Service owns Work Request, Workflow Definition/Revision, Task, Dependency, projection, retry-intent, and escalation-intent records for Dev Preview | Advanced compensation semantics, long-running workflow optimization, and cross-Organization workflow collaboration | Workflow engines must not create peer scheduler, assignment, or invocation authority. |
| Work Request lifecycle beyond Dev Preview minimum | Work Coordination Service owns Dev Preview Work Request intake, review, acceptance, rejection, conversion, and lifecycle | Advanced intake policy, external request federation, and marketplace template intake | Work Request may not select an Employee, authorize, approve, verify, or become a Job without a governed transition. |
| Workflow publication beyond Dev Preview minimum | Work Coordination Service owns Dev Preview Workflow Definition/Revision publication, selection, deprecation, persistence, and projection | Public workflow marketplace policy and cross-Organization publication | No Core or Lucy Workflow engine gains authority from contract presence. |
| Task lifecycle beyond Dev Preview minimum | Work Coordination Service owns Dev Preview Task creation, readiness, blockage, completion evidence linkage, cancellation, persistence, and events | Advanced distributed task partitioning and cross-Organization tasks | Task is neither Assignment nor execution. |
| Assignment decision and acceptance beyond Dev Preview minimum | Work Coordination Service owns assignment decisions; Persistent Runtime owns assignment acceptance/projection/lifecycle after handoff | Advanced cross-target policy, assignment optimization, and compatibility retirement timing | Public Assignment Service remains conflicting; no scoring, ranking, or implicit selection. |
| Delegation lifecycle beyond Dev Preview minimum | Work Coordination Service owns same-Organization Delegation lifecycle for Dev Preview | Cross-Organization delegation, temporary supervisory delegation, and federation | Delegation cannot expand scope, cross Organizations, authorize, approve, or execute. |
| Dependency lifecycle beyond Dev Preview minimum | Work Coordination Service owns Dev Preview dependency declaration, readiness, satisfaction, and waiver records | Advanced compensation and external dependency federation | Dependency never schedules work. |
| Work Result creation and acceptance beyond Dev Preview minimum | Work Coordination Service owns Work Result records and acceptance for Dev Preview | Advanced result reuse, delayed outcome attribution, and external outcome federation | Result does not self-verify or close work. |
| Work verification and closure beyond Dev Preview minimum | Work Coordination Service owns Dev Preview verification and closure records | Advanced outcome authority, third-party verification, and PPT numerator authority | Approval Authority remains approval-only; caller evidence never self-verifies. |
| Work retry and escalation intents beyond Dev Preview minimum | Work Coordination Service owns Dev Preview retry-intent and escalation-intent records | Advanced optimization policies for retry/escalation recommendation | Intent does not retry, reassign, select, schedule, or execute. |
| Plugin lifecycle beyond Dev Preview minimum | Plugin and Tool Lifecycle Authority owns Dev Preview definition, manifest, publishing/import, install, activation, update, rollback, removal, dependency-lock, revocation, compatibility-observation, Capability Profile, and Tool catalog lifecycle | Public marketplace, SDK governance, hosted update channels, billing, entitlement, fraud, and moderation | Lucy Plugin Platform/Registry and Module Registry are not canonical; `OPEN:` example references appoint no authority. |
| Capability declaration | Capability Manager owns canonical inventory/resolution and the target Capability Definition contract is defined | Boundary and migration among publisher declaration, installed inventory, canonical ingestion, and current Capability Manager APIs/storage | A Plugin Manifest or Capability Profile must not directly grant, rank, resolve, or authorize capability use. |
| Capability permission grants beyond Dev Preview minimum | Authorization Authority owns Dev Preview capability permission grants, revocation, and decisions | Delegated permission grants, broad policy language, and advanced inheritance | Inventory presence or employee configuration must not authorize use. |
| General authorization decisions beyond Dev Preview minimum | Authorization Authority owns Dev Preview policy inputs, grants, revocation, durable service/API, and decisions | Full policy language, external policy packs, cache/revalidation strategy, and organization/team policy inheritance | Authorization evidence does not select providers, invoke work, or become a second ranking or resolution authority. |
| Tool identity and operation catalog beyond Dev Preview minimum | Plugin and Tool Lifecycle Authority owns Dev Preview Tool catalog ingestion and lifecycle; Dispatcher is invocation authority | Public SDK governance, external tool catalog federation, and advanced operation taxonomy | Tool, Plugin, Tool Runtime, or adapter must not invoke outside Dispatcher. |
| Capability Profile lifecycle beyond Dev Preview minimum | Plugin and Tool Lifecycle Authority owns Dev Preview Capability Profile lifecycle | Advanced inheritance, policy interpretation, and cross-scope editing UX | Profiles do not grant, approve, establish candidate order, select, resolve, or invoke; ranking remains `job > employee > capability > global`. |
| Runtime compatibility evidence beyond Dev Preview minimum | Runtime Activation Authority and Plugin and Tool Lifecycle Authority own Dev Preview observations within their lifecycle scopes | Long-term freshness policy, third-party observer authority, and cross-installation reconciliation | Evidence may inform eligibility but never installs, activates, authorizes, approves, ranks, resolves, or executes. |
| Plugin ecosystem revocation beyond Dev Preview minimum | Plugin and Tool Lifecycle Authority owns Dev Preview plugin/tool revocation propagation; Artifact Authority owns artifact lifecycle revocation; Artifact Trust verifies trust evidence only | Hosted ecosystem declarers, policy packs, external transparency, and advanced in-flight treatment | Artifact Trust does not acquire general publishing, installation, activation, Tool, Provider, or execution authority. |
| Approval service implementation beyond Dev Preview minimum | Approval Authority owns durable Dev Preview request/grant/verify/consume/revoke/expire lifecycle and approver-policy evaluation | Advanced notification channels, multi-approver policy, and availability strategy | No other service may issue, mutate, or self-verify grants. |
| Secret resolution beyond Dev Preview minimum | Secret Authority owns Dev Preview backend, use authorization, transient lease/injection, rotation, redaction, deletion, backup behavior, and production implementation | Additional secret backends and enterprise recovery/federation | Raw secrets are forbidden in source, contracts, fixtures, logs, prompts, events, and memory. |
| Sandbox/workspace lifecycle beyond Dev Preview minimum | Sandbox Authority owns Dev Preview profile, workspace, filesystem, network, process, secret, artifact, cleanup, violation, and attestation lifecycle | Advanced isolation backends, remote sandboxes, and enterprise policy packs | Container use alone must not be claimed as canonical sandboxing. |
| Team Template lifecycle beyond Dev Preview minimum | Team Template Authority owns Dev Preview Team Template definitions, versions, installed instances, validation, simulation/test-run, activation plans, upgrade, and rollback | Public template marketplace and broad template ecosystem policy | A template may not grant permissions, provide secrets, approve, or self-activate. |
| Team Architect apply protocol beyond Dev Preview minimum | Team Template Authority owns Team Architect proposal/apply/save/test-run records; Team Architect is a mandatory guided employee | Advanced collaborative editing and autonomous redesign policy | Team Architect never becomes publisher, installer, approver, secret, workflow, scheduler, or activation authority. |
| Memory, knowledge, experience, and playbooks | Persistent Runtime owns only working state; reference artifacts retain bounded provenance | Canonical object distinctions, storage owners, trust/review, correction, retention, deletion, and retrieval authority | Lucy stores must not be merged or promoted without an accepted data-authority decision. |
| General artifact authority beyond Dev Preview minimum | Artifact Authority owns Dev Preview artifact identity, ownership, derivation, publication, retention, and linkage verification | Cross-Organization artifact sharing and advanced artifact marketplace rules | Service-local paths or blobs must not become global artifact identity. |
| History ingestion | Governed provenance/review pipeline is required | Import-session, consent, source, correction, retention, deletion, and connector boundary | Imported conversation or document content must not become trusted memory automatically. |
| Runtime/model activation beyond Dev Preview minimum | Runtime Activation Authority owns Dev Preview desired/observed topology, activation, registration handoff, rollback, and partial-state records | Fleet activation, high availability, and enterprise runtime policy | First Run declarations and fixture state are not activation authority. |
| Provider/runtime observations | Observations may affect eligibility under policy | Probe authority, freshness, expiry, degraded-state rules, and reconciliation | Health never becomes hidden ranking or rewrites administrative intent implicitly. |
| Budget and cost authority | Budget is a cumulative restriction concept | Reservation, accounting, issuer, scope, and exhaustion behavior | Cost or PPT must not become implicit ranking. |
| Outcome evidence | PPT requires externally grounded productive outcomes | Outcome issuer/authority, normalization, attribution, cohorts, and delayed/reused outcomes | Employees may not self-declare productive value. |
| Notification/human interaction | Approvals and operator attention require delivery | Canonical request/response identity and channel-neutral delivery boundary | A delivery channel must not decide or forge the underlying approval/action. |
| Backup, restore, and update execution | Canonical plans exist | Privileged executor, result, data ownership, migration, recovery, and rollback authority | A plan or UI confirmation is not execution authority. |

## Known conflicting or legacy public surfaces

These source surfaces are present in `leos-v2` but do not receive authority
from their presence. Their migration or retirement is future reviewed work.

| Surface | Conflicting behavior | Registry disposition |
|---|---|---|
| `services/assignment-service/app.py` | Persists a peer job lifecycle, selects employees through legacy resolution/score behavior, accepts caller `force`, mutates employee load, and publishes best-effort events | **CONFLICTING / INVESTIGATE**. It is outside the canonical execution path and must receive no new v2 authority. Caller/data migration, compatibility, and retirement remain **OPEN**. |
| Employee Registry legacy `/resolve` | Returns a selected employee using legacy assignment-resolution behavior within the otherwise canonical Employee Registry | Definition, lifecycle, eligibility, assignment-policy inputs, and resource-profile synchronization remain canonical. Workforce assignment-selection authority and compatibility duration remain **OPEN**. |

## Canonical object vocabulary

These terms are normative even where the final contract is **OPEN**.

| Term | Meaning | Authority rule |
|---|---|---|
| Definition | A durable declarative description of an object | Owned by the object's accepted definition authority; not proof of installation or activity. |
| Revision | Immutable identity for the material state used in a decision | Mutable display names, timestamps, or endpoint aliases do not substitute for revision evidence. |
| Policy | User- or authority-authored rules and restrictions | Policy is not a provider resolution or execution result. |
| Plan | Proposed operations and declared effects | A plan never proves authorization or completion. |
| Decision | An authority's governed determination from referenced inputs | A decision does not perform the external operation unless that authority explicitly owns it. |
| Ranking | User-governed candidate order | Ranking does not imply eligibility, availability, approval, or invocation. |
| Eligibility result | Candidate survival or rejection under cumulative restrictions and facts | Eligibility may remove but never reorder. |
| Resolution | Capability Manager's governed authorization of a selected target, or truthful non-selection outcome | Resolution is not provider execution. |
| Execution | Dispatcher's durable invocation lifecycle for one governed request | Execution never invents a target or silently changes it. |
| Attempt | One same-target invocation attempt within an execution | Attempt identity and retry never imply re-resolution. |
| Observation | Time-bounded reported fact about another object | An observation is not administrative state or source authority. |
| Projection | Derived local view of another authority's state | A projection is rebuildable and cannot override its source. |
| Published artifact | Immutable distributable definition and evidence | Not an installed, configured, enabled, or active instance. |
| Installed instance | Local realization of one published artifact version | Installation does not imply permission, approval, enablement, or activation. |
| Configured instance | Installed instance with local non-secret configuration and opaque references | Configuration does not imply readiness or activity. |
| Active runtime | Governed running realization with desired/observed state | Runtime Activation Authority owns desired/observed activation for Dev Preview. |
| Capability | A governed kind of work that may be resolved to an eligible provider | Capability presence is not a grant and is not a Tool operation. |
| Tool | Versioned bounded operation with explicit schemas and side-effect/idempotency declarations | Plugin and Tool Lifecycle Authority owns Tool catalog lifecycle; invocation remains Dispatcher authority. |
| Plugin | Installable extension package declaring integrations, capabilities, tools, requirements, and configuration | Declaration does not grant, register, approve, or activate by itself. |
| Employee | Governed worker definition and lifecycle identity | Employee Registry owns definition; runtime and cognition own separate operational state. |
| Work Request | Governed expression of demand | Not selection, authorization, approval, Job, or execution. |
| Workflow Definition | Stable reusable work-blueprint identity | Not a running instance or Job. |
| Workflow Revision | Immutable versioned workflow structure | Not mutable run state or Job. |
| Job | One instantiated body of work | Scheduler owns lifecycle; not a reusable definition, Assignment, or execution runtime. |
| Task | One work unit within a Job or standalone context | May exist without Assignment; not execution. |
| Assignment | Durable responsibility projection for exact Job/Task scope | Work Coordination Service owns the assignment decision; Persistent Runtime owns acceptance/projection; no authorization or execution. |
| Delegation | Governed responsibility sub-allocation preserving source Assignment and full chain | Never scope expansion, authority transfer, or execution. |
| Dependency | Revision-pinned structural/readiness constraint | Never scheduling authority. |
| Work Result | Immutable producer-linked outcome evidence | Not verification, closure, Artifact Trust, or lifecycle authority. |
| Workflow | Collective domain term for Definition/Revision and separately instantiated governed work | No generic running instance may absorb Scheduler or Dispatcher authority. |
| Team Template | Immutable publishable organization blueprint | Separate from its installed instance, created Team, and active organization. |
| Approval request | Request for an authorized human/authority decision | Not a grant. |
| Approval grant | Explicit verifiable scoped authorization | Approval Authority owns lifecycle and verification; caller-provided evidence is not self-verifying. |
| Secret reference | Opaque identifier for protected material | Secret Authority owns identity; the reference never contains or implies authorization to retrieve the secret value. |
| Artifact | Durable output with identity, ownership, provenance, and derivation | Artifact Authority owns Dev Preview artifact lifecycle and linkage verification. |
| Memory/knowledge item | Governed retained information with scope, provenance, trust, and lifecycle | Exact taxonomy and authority remain **OPEN**. |
| Outcome evidence | Externally grounded evidence of productive value | Observational input to reporting only; not selection authority. |
| Event | Immutable fact published by the authority that owns the represented transition | Event delivery does not create state authority. |
| Audit record | Durable evidence that an authority evaluated or performed an operation | Audit evidence does not replace the canonical object or grant authority. |

## Lifecycle vocabulary and separation

Lifecycle families must not be collapsed.

| Lifecycle family | Accepted or required separation |
|---|---|
| Employee definition lifecycle | Employee Registry is canonical. Existing employee lifecycle contracts govern the implemented scope. |
| Job lifecycle | Scheduler owns it independently of assignment, cognition, workflow, and execution. |
| Lease/resource lifecycle | Scheduler owns acquisition/admission/release; terminal job state and resource release require truthful reconciliation. |
| Assignment lifecycle | Work Coordination Service owns assignment decisions; Persistent Runtime owns acceptance, durable projection, and runtime transitions. |
| Cognitive lifecycle | Cognitive Service owns runs, attempts, checkpoints, observations, and results. Cognitive retry is not assignment retry. |
| Resolution lifecycle | Capability Manager owns resolution and non-selection outcomes. Re-resolution is not Dispatcher retry. |
| Execution lifecycle | Dispatcher owns execution and same-target attempts. Provider failure, transport failure, and ambiguous outcome remain distinct. |
| Artifact publication lifecycle | Draft/validation/publication/deprecation/revocation semantics require future contracts. Publication is never installation. |
| Installed-instance lifecycle | Inspect/plan/install/configure/enable/update/rollback/remove semantics require future contracts. Installation is never activation. |
| Runtime lifecycle | Runtime Activation Authority owns desired/observed activation, health observations for activation, deactivation, and rollback. |
| Organization Domain lifecycle | Organization Domain Service owns Organization, Department, Team, Role, Position, Membership, and Position Occupancy definitions and lifecycle. Ownership transfer, recovery, inheritance, and cross-Organization collaboration remain **OPEN**. |
| Workflow lifecycle | Work Coordination Service owns Work Requests, Workflow Definitions/Revisions, Tasks, Dependencies, projection records, retry intents, and escalation intents. |
| Work Request lifecycle | Work Coordination Service owns Dev Preview intake, review, acceptance, rejection, conversion, and lifecycle. |
| Task lifecycle | Work Coordination Service owns Dev Preview Task states and evidence linkage. |
| Delegation lifecycle | Work Coordination Service owns same-Organization Delegation lifecycle for Dev Preview; cross-Organization delegation remains **OPEN**. |
| Work Result lifecycle | Work Coordination Service owns Dev Preview Result creation and acceptance. |
| Permission lifecycle | Authorization Authority owns Dev Preview capability permission grants, authorization decisions, expiry, and revocation; advanced delegation remains **OPEN**. |
| Approval lifecycle | Approval Authority owns request/decision/grant/verify/consume/expire/revoke and approver-policy evaluation for Dev Preview. |
| Memory/knowledge lifecycle | Capture/review/trust/correct/supersede/deprecate/delete semantics remain **OPEN**. |

No lifecycle transition may be inferred solely from:

- an API call returning successfully;
- an event being emitted;
- a UI state change;
- a caller-provided Boolean;
- an opaque reference existing;
- an artifact being downloaded;
- a plugin being installed;
- a service health observation; or
- a test fixture record.

## Event, correlation, and causation boundaries

1. The authority that owns a state transition is the only producer that may
   assert the canonical transition fact.
2. Events are immutable evidence and notification. Canonical state remains in
   the authority's governed store unless an accepted decision explicitly says
   otherwise.
3. Consumers may build projections, initiate separately authorized work, or
   report observations. They may not reinterpret an event as permission,
   approval, selection, or state ownership.
4. Duplicate delivery must not duplicate authority-bearing work. Exact event
   idempotency, ordering, acknowledgement, replay, and outbox rules remain
   **OPEN**.
5. Correlation identifies related work but does not authorize it. The current
   execution contracts govern the implemented correlation envelope.
6. Causation distinguishes the actor/request that caused a transition from the
   producer that recorded it under `leos.event-envelope.v1`.
7. Events, logs, diagnostics, and audit records must not carry raw secrets or
   unnecessary prompt/memory content.
8. Service-local event formats are not automatically public contracts.

Established correlation ownership includes:

| Identifier | Authority |
|---|---|
| `job_id`, `lease_id`, `resource_reservation_id` | Scheduler |
| `employee_id` | Employee definition authority |
| `assignment_id` | Persistent Employee Runtime |
| `cognitive_run_id`, `cognitive_attempt_id` | Employee Cognitive Service |
| `resolution_id` | Capability Manager |
| `execution_id`, invocation attempt identity | Execution Dispatcher |
| `model_id`, model-binding revision | Model Registry |
| effective-ranking identity/revision | Ranking Policy Authority |
| `workflow_id`, `step_id` | Work Coordination Service |
| `approval_grant_id` | Approval Authority |

## Contract, revision, and compatibility rules

1. JSON Schema files under repository-root `contracts/` are the canonical
   shared schema definitions. Runtime schema copies are prohibited.
2. `packages/leos-contracts` is the canonical semantic-validation
   implementation for governed shared contracts.
3. JSON Schema validation and semantic validation are both required where the
   canonical validator defines semantic invariants.
4. Contract version, object revision, artifact version, service version, model
   identity, binding revision, and installed-instance version are different
   concepts.
5. A revision used for a governed decision must identify the material facts
   evaluated. Mutable names, identifier spelling, timestamps, health probes, or
   list position must not become hidden policy.
6. Compatibility is explicit. It may preserve a validated read or transport
   surface, but it must not preserve conflicting selection, invocation,
   approval, secret, or lifecycle authority.
7. Lucy behavior has no compatibility entitlement merely because it is
   running. Compatibility duration and retirement require explicit decisions
   and tests.
8. Pre-release v2 contracts may be completed in their existing version only
   when the governing architecture and contract-specific versioning decision
   permit it.
9. Published artifact versions are expected to be immutable. Artifact
   Authority owns Dev Preview artifact lifecycle; long-term public artifact
   compatibility rules remain **OPEN**.
10. Irreversible migrations require explicit review. Until then, prefer
    non-destructive schema additions, revisioned imports, rebuildable
    projections, and truthful rollback limitations.
11. Test/reference fixtures have no production compatibility or migration
    obligation and must leave no production authority/configuration state.
12. RC11 release authority remains frozen unless explicitly authorized.

The repository-wide compatibility window, deprecation duration, long-term
event-schema evolution protocol, artifact-version syntax, and stored-data
migration policy remain **OPEN**.

## Forbidden authority overlaps

The following are prohibited unless an accepted later ADR explicitly changes
the boundary:

- Capability Manager invoking a provider or adapting provider payloads.
- Dispatcher, Router, adapters, or providers selecting or substituting a
  provider/model.
- Router fallback, emergency provider pools, identifier ordering, score-based
  selection, or unranked candidate append.
- Cognitive Service or Persistent Runtime invoking providers directly.
- Persistent Runtime owning reasoning or Scheduler leases.
- Assignment Service or any other peer owning Scheduler jobs, Persistent
  Runtime assignments, or employee-selection policy by implementation
  accident.
- Workflow, planning, Team Architect, or Runtime Coordinator driving leases or
  restarting assignments.
- Plugin installation directly granting capabilities, permissions, approvals,
  secrets, or activation.
- Capability presence being treated as permission.
- Caller Booleans or opaque approval-reference existence authorizing action.
- Tool Runtime or Adapter Manager becoming a peer invocation authority.
- First Run or Phase 5.0 fixtures becoming continuing model/provider/runtime
  authority.
- Health, price, cost, benchmark, locality, trust, or PPT metrics silently
  reordering user-ranked candidates.
- Organization or Team policy adding ranking precedence before an accepted
  intelligence-plane decision.
- Events, projections, caches, UI state, logs, or audits becoming canonical
  state authority.
- Lucy files, databases, endpoints, or behavior becoming authority without
  deliberate promotion into `leos-v2`.

## Change control

An implementation package that touches an **ACCEPTED** row must:

1. cite the governing authority document;
2. preserve the owner and forbidden overlaps;
3. update explicit contracts and tests for behavioral changes;
4. retain correlation, audit, idempotency, secret, and failure semantics; and
5. report migrations and compatibility behavior.

An implementation package that touches an **OPEN** row must first obtain an
accepted architecture decision. Creating a table, endpoint, schema, fixture,
or service does not resolve an **OPEN** authority.

This registry must be updated whenever an accepted decision:

- establishes a new canonical owner;
- changes a responsibility boundary;
- defines a previously open lifecycle;
- adds or removes a compatibility surface; or
- retires a donor or duplicated authority.
