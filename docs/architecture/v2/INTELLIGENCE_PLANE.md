# LEOS v2 Intelligence Plane

## Status and scope

This document defines the provisional intelligence and model/provider
architecture for LEOS 0.2.0 Developer Preview v2. It complements
`EXECUTION_PLANE.md`; it does not replace or alter that execution-plane
architecture.

This is an authority and selection-semantics document, not an executable
implementation specification. Exact wire formats, storage schemas, service
topology, compatibility periods, and activation mechanisms remain subject to
governed contracts. Unsettled matters are marked **OPEN**.

## 1. Goals and principles

The core product principle is:

> The user defines the intelligence hierarchy. LEOS optimizes execution within
> that hierarchy.

The intelligence plane must:

1. preserve user-defined ordering across eligible intelligence choices;
2. distinguish preference order from hard eligibility restrictions;
3. establish one canonical authority for provider inventory and resolution;
4. establish one distinct canonical authority for model facts;
5. distinguish normalized model identity from provider/runtime instance
   identity;
6. support the same model through multiple provider/runtime instances;
7. treat local models as first-class providers;
8. treat cloud models as optional, explicitly permitted providers or escalation
   choices rather than a default authority;
9. preserve the Execution Dispatcher as the sole governed invocation
   authority;
10. narrow the AI Router to transport and protocol compatibility;
11. produce a durable explanation of every selection;
12. make availability, health, privacy, budget, context, and capability checks
    explicit and testable;
13. keep transport retry separate from model/provider escalation;
14. prevent raw credentials from entering intelligence metadata or execution
    records;
15. support specialized intelligence capabilities without creating a competing
    routing plane.

The canonical selection semantics are:

```text
ranking determines order
  → eligibility removes invalid candidates
  → first remaining ranked candidate wins
```

LEOS may optimize execution of the selected candidate. It may not reorder
otherwise-valid candidates based on its own assessment of quality, locality,
cost, latency, capacity, or capability strength.

## 2. Authority boundaries

| Concern | Canonical authority | Boundary |
|---|---|---|
| User/organization/employee rankings and restrictions | Governed Employee Config boundary | Normalizes scoped policy; does not invoke or observe runtime health |
| Capability and provider inventory | Capability Manager | Owns provider eligibility and governed resolution; does not execute |
| Model facts | Model Registry | Owns normalized model identity, model facts, and model-provider/runtime bindings; does not invoke |
| Provider/runtime observations | Provider/runtime observation sources, reconciled into canonical authorities | Report health, availability, locality, and capacity; do not define user ranking |
| Intelligence resolution | Capability Manager | Applies effective ranking and eligibility, records rationale |
| Invocation | Execution Dispatcher | Sole governed invocation authority; authorizes and records invocation of the resolved target; does not select |
| Protocol compatibility | AI Router or declared provider adapter | Physically transmits an already-authorized request; does not initiate, redirect, retarget, escalate, rank, or substitute |
| Installation capability | First Run | Coordinates initial capability establishment and seeds initial global ranking after governed registration; activation and registration authority remain **OPEN** |
| Provider credentials | Authorized secret authority | Authenticates and authorizes use, resolves opaque references, and performs or supplies transient credential injection |
| Specialized intelligence | Same capability/provider and model-facts principles | Embedding, reranking, OCR, vision, and speech do not create a separate routing authority |

The standalone Provider Registry is not a future peer authority. Its useful
metadata is a migration input to the Capability Manager provider inventory.

## 3. Model identity

A normalized model identity denotes the model independently of any one serving
endpoint. It must not be the same identifier as a provider/runtime instance.

The model-facts authority must be able to distinguish:

- canonical model identity;
- provider-native model name;
- family and variant where known;
- version, revision, or digest where available;
- model purpose and type;
- supported input and output modalities;
- supported capabilities and features;
- context and output limits;
- runtime and hardware compatibility;
- quantization or precision where relevant;
- licensing or use constraints;
- deprecation and lifecycle status.

A string such as `qwen2.5:7b-instruct` is evidence of a provider-native model
name. By itself it is not sufficient to identify which runtime instance serves
it or whether two nodes serve equivalent model artifacts.

**OPEN:** Canonical model identifier syntax, versioning rules, and the required
strength of artifact identity.

**OPEN:** Whether model families and exact model artifacts receive separate
identifiers.

## 4. Provider and runtime identity

A provider/runtime instance denotes an executable serving endpoint or bounded
capability provider. It is distinct from the models it can serve.

Provider/runtime facts must be able to represent:

- canonical provider instance identifier;
- provider type and protocol;
- endpoint and health-observation mechanism;
- node or deployment identity;
- locality relative to the applicable installation or organization;
- administrative enablement;
- observed availability and health;
- supported capabilities;
- served model-provider/runtime bindings;
- concurrency, rate, and capacity limits where known;
- privacy and data-handling facts;
- cost facts;
- authentication requirement and opaque credential reference;
- request-adaptation declaration;
- provider lifecycle and provenance.

Multiple local instances may serve the same normalized model. For example, a
Lucy Ollama instance and a DGX runtime must remain distinct provider/runtime
identities even when both expose the same provider-native model name.

**OPEN:** The canonical meaning and scope of `local`, including whether it is
relative to installation, organization, user, employee, or physical node.

## 5. Model-provider/runtime binding concept

A model-provider/runtime binding states that a particular provider/runtime
instance can serve a particular normalized model under declared conditions.

The binding concept must be able to carry or reference:

- normalized model identity;
- provider/runtime instance identity;
- provider-native model identifier;
- installed, discoverable, loaded, and enabled observations as applicable;
- supported modalities and capabilities for that binding;
- context and output limits as actually served;
- runtime/hardware requirements;
- request-adaptation or protocol profile;
- health and availability observations;
- cost and privacy facts that vary by provider;
- credential-reference requirement;
- evidence source and observation time.

Model facts and provider facts remain separate even though resolution consumes
both. A model may have zero, one, or many provider/runtime bindings.

**OPEN:** Which facts are intrinsic to the model, intrinsic to the provider, or
overrides on a binding requires a governed schema.

## 6. Ranking scopes

LEOS v2 supports four ranking scopes:

### Global ranking

The default ordered intelligence hierarchy for the installation or governed
scope. First Run may seed this ranking from activated runtime capability, but
First Run does not permanently own it.

### Capability-specific ranking

An ordered hierarchy for a capability, such as `code.generate`,
`text.reason`, `text.embed`, OCR, vision, or speech.

### Employee-specific ranking

An ordered hierarchy explicitly defined for an employee. It may select models
and provider/runtime choices appropriate to that employee's role and approved
operating policy.

### Job-level override

An ordered hierarchy explicitly attached to a job or assignment. It is the most
specific ranking.

Each ranking entry must identify a model, provider/runtime, or a constrained
combination with enough precision for canonical resolution. Generic words such
as `local` or `cloud` are restrictions or categories, not provider identities.

**OPEN:** Whether rankings may contain model-only entries, provider-only
entries, and exact model-provider/runtime binding entries in the same list.

## 7. Ranking precedence

The most-specific defined ranking wins:

1. job override;
2. employee ranking;
3. capability-specific ranking;
4. global ranking.

For v2, a defined more-specific ranking replaces the less-specific ranking.
LEOS does not implicitly merge or interleave ranked lists.

Hard restrictions from all applicable scopes remain cumulative. A more-specific
ranking does not erase a higher-authority restriction unless the restriction's
own governed contract explicitly permits that override.

**OPEN:** The ownership and authority ordering of restrictions when multiple
organizational scopes conflict.

## 8. Hard restrictions versus preferences

Ranking expresses preference order. Hard restrictions express eligibility.
They must not be encoded as hidden score bonuses or penalties.

Examples of ranking preferences:

- Qwen local before Llama local;
- local coding model before an approved cloud model;
- standard cloud tier before advanced cloud tier.

Examples of hard restrictions:

- provider or model administratively disabled;
- missing capability or modality;
- insufficient context window;
- unavailable runtime or model;
- unacceptable health state;
- locality prohibition;
- privacy or data-retention mismatch;
- cloud execution not permitted;
- budget ceiling exceeded;
- credential unavailable;
- required approval grant absent;
- provider/model explicitly denied;
- runtime or hardware incompatibility.

A restriction may remove a candidate. It may not move a lower-ranked valid
candidate above another valid candidate.

Quality, benchmark, latency, locality, and cost observations may participate in
eligibility only where governed policy defines a hard threshold. They do not
become implicit reordering signals.

## 9. Effective-ranking construction

For a resolution request, the effective ranking is constructed as follows:

1. identify all applicable hard restrictions;
2. locate an explicitly defined job ranking;
3. otherwise locate an explicitly defined employee ranking;
4. otherwise locate an explicitly defined ranking for the requested
   capability;
5. otherwise use the global ranking;
6. preserve the selected list's explicit order without implicit merging;
7. attach ranking scope, policy revision, owner, and provenance to the
   resolution input.

An explicitly defined empty ranking is a defined more-specific ranking and
therefore replaces less-specific rankings. It yields explicit resolution
failure; it does not fall back.

If no ranking exists at job, employee, capability, or global scope,
intelligence resolution fails explicitly. There is no implicit emergency or
unranked candidate pool, and LEOS must not invent a provider/model choice.
First Run normally seeds an initial global ranking after successful governed
runtime/model registration.

**OPEN:** How policy revisions are pinned for long-running jobs.

## 10. Eligibility filtering

The Capability Manager evaluates each ranked candidate in order against all
applicable restrictions and canonical facts.

Eligibility must consider, where applicable:

- requested capability;
- requested modality;
- required model features;
- model-provider/runtime binding existence;
- model and provider administrative status;
- observed provider and model availability;
- health policy;
- runtime/node availability;
- context and output requirements;
- locality restrictions;
- privacy and data-handling restrictions;
- cloud permission;
- cost and budget limits;
- credential-reference availability;
- approval-grant requirements;
- explicit allow/deny policy;
- runtime/hardware compatibility;
- applicable provider limits.

Filtering produces an eligibility result for every considered ranked candidate.
The result records valid or invalid status and explicit reasons. Eligibility
does not assign a comparative score.

**OPEN:** Staleness limits for health, availability, capacity, price, and
credential observations.

## 11. First-ranked-valid selection rule

The first candidate in effective-ranking order that passes all eligibility
checks wins.

If the ordered candidates are:

1. local Qwen;
2. local Llama;
3. approved cloud standard;
4. approved cloud advanced;

and candidates 1 and 2 are unavailable while candidate 3 is eligible, candidate
3 wins. If candidate 1 is eligible, candidate 1 wins even if LEOS considers
candidate 2 faster, cheaper, healthier above a configured threshold, or more
capable.

If no candidate is eligible, resolution fails or returns a governed
non-selection outcome. It does not select an unranked model. There is no
implicit emergency or unranked candidate pool in v2.

If the highest-ranked otherwise-eligible candidate requires an approval grant
that is not present, resolution returns `APPROVAL_PENDING`. Lower-ranked
candidates are not silently selected. A future explicit governed policy may
permit skipping unapproved candidates, but that behavior must never be
implicit.

## 12. Resolution rationale and audit

Every resolution must durably record:

- resolution identifier;
- requester and correlation identifiers;
- requested capability, modality, context, and required features;
- ranking scope and policy revision;
- complete effective ranking as evaluated;
- applicable hard restrictions and their provenance;
- model, provider, and model-provider/runtime binding fact revisions or
  observation references;
- candidate order;
- eligibility outcome and reason for each candidate considered;
- selected candidate and its original rank;
- approval and cloud-permission evidence where applicable;
- budget decision where applicable;
- resolution time and validity period;
- whether no candidate was selected.

The rationale must make it possible to prove that LEOS did not reorder valid
user choices.

The audit must not contain raw credentials, prompt content not required for
resolution, or secret values.

## 13. Capability Manager integration

Capability Manager is the canonical provider inventory and governed resolution
authority.

For intelligence resolution it:

- receives the effective ordered ranking or an authoritative reference to it;
- consumes canonical model facts and model-provider/runtime bindings from Model
  Registry;
- evaluates provider-capability bindings, model-provider/runtime binding facts,
  and capability eligibility;
- applies hard restrictions without reordering;
- verifies required governance evidence;
- selects the first ranked valid candidate;
- records durable resolution rationale;
- returns a governed resolution for Dispatcher consumption.

It does not:

- invoke providers;
- adapt provider payloads;
- retry transport calls;
- silently replace the selected model;
- own canonical model facts;
- invent a ranking based on provider priority or quality scoring.

Existing provider or binding priorities may remain useful for non-intelligence
capabilities or migration, but they must not reorder an explicit intelligence
ranking.

The Persistent Employee Runtime remains the authority for durable employee
working-state storage. Employee Cognitive Service owns per-run context
assembly, which may consume durable working memory, employee configuration,
assignment data, knowledge, long-term memory, and execution results. Cognitive
Service must not become a duplicate working-memory persistence authority.

**OPEN:** Whether Capability Manager retrieves effective policy directly or the
request carries a signed/versioned effective-ranking reference.

## 14. Model Registry responsibility

Model Registry remains distinct from Capability Manager provider inventory.

It is authoritative for:

- normalized model identities;
- model metadata and lifecycle;
- modalities, capabilities, features, and limits;
- model/runtime compatibility facts;
- model-provider/runtime bindings;
- declared and observed model availability evidence;
- provenance and revisions of model facts.

It does not:

- own user ranking;
- resolve a provider independently of Capability Manager;
- invoke models;
- store raw credentials;
- treat a provider-native name as a globally unique identity.

The existing CRUD-only Lucy implementation is a migration starting point, not
a complete v2 authority.

**OPEN:** Whether runtime observations are written into Model Registry or
referenced from a separate observation authority.

## 15. Provider Registry migration

The Lucy Provider Registry contains useful metadata:

- locality;
- capabilities;
- served models;
- privacy;
- cost;
- limits;
- authentication references;
- endpoint and health metadata.

That metadata must be reconciled into Capability Manager's canonical provider
inventory and the appropriate model-provider/runtime bindings.

During migration:

1. inventory all Provider Registry callers;
2. define field mappings and provenance;
3. normalize provider identities and types;
4. separate model facts from provider facts;
5. replace score-based intelligence resolution with ordered eligibility;
6. migrate health and auth-reference behavior to canonical boundaries;
7. move callers to Capability Manager or other canonical APIs;
8. retain read compatibility only where required;
9. retire standalone Provider Registry after dependency and data migration.

Provider Registry must not remain a peer resolution authority.

**OPEN:** Compatibility duration and whether a read-only facade remains after
retirement.

## 16. Execution Dispatcher boundary

The Execution Dispatcher remains the sole governed provider/tool invocation
authority under `EXECUTION_PLANE.md`. It authorizes and records an invocation;
a Router or adapter may physically transmit the already-authorized request.

For intelligence execution it:

- receives a complete execution request from Cognitive Service, including the
  applicable effective intelligence policy or ranking;
- requests a governed resolution from Capability Manager and receives its
  durable resolution record or reference;
- verifies that the resolved model-provider/runtime binding is valid for the
  execution;
- adapts the canonical request to the declared provider protocol;
- requests authorized credential use or injection from the secret authority;
- invokes the exact resolved provider/runtime and model;
- applies transport retry consistent with idempotency and resolution policy;
- records attempts;
- normalizes usage, result, error, and ambiguous outcome;
- returns the normalized execution result.

It must not:

- build or reorder rankings;
- independently choose a different model or provider;
- treat transport failure as permission to escalate;
- invoke an unranked candidate;
- retain raw resolved credentials.

The Dispatcher does not perform provider/model failover. Any provider/model
change requires a new governed resolution from Capability Manager. Dispatcher
may retry only the same authorized target and only when retry policy,
idempotency semantics, and failure classification permit a transport retry.

## 17. AI Router transport-only role

AI Router is narrowed to intelligence transport and protocol compatibility.

Useful behavior to preserve includes:

- Ollama request/response compatibility;
- OpenAI-compatible facade behavior where contractually supported;
- dynamic runtime model discovery as an observation;
- specialized protocol adaptation where it remains the declared adapter.

AI Router does not:

- initiate another invocation independently;
- redirect an invocation;
- change provider or model;
- retry using another provider or model;
- escalate;
- rank models or providers;
- own default or fallback policy;
- silently substitute a model;
- consult its own independent routing hierarchy;
- override a governed resolution;
- act as a competing provider or model registry.

An explicitly resolved request identifies the provider/runtime and model to
execute. Dispatcher authorizes and records the invocation; Router or an adapter
may physically transmit it. If transmission or execution fails, Router reports
the failure. Escalation is a separate governed operation requiring a new
Capability Manager resolution.

Existing hard-coded Qwen/Llama fallback is prohibited in the v2 target
architecture.

**OPEN:** Whether AI Router remains one service, becomes protocol-specific
adapters, or is partially absorbed into provider implementations.

## 18. Local model execution

Local models are first-class intelligence candidates. They are not implicit
defaults merely because they are local, and they are not downgraded merely
because a cloud model appears more capable.

Local execution must be representable through:

- provider/runtime instance identity;
- node and locality facts;
- normalized model-provider/runtime binding;
- protocol profile such as Ollama, vLLM, llama.cpp, or another supported
  interface;
- health and model availability observations;
- context, modality, and feature compatibility;
- capacity and applicable hardware facts;
- no-auth or credential-reference declaration;
- governed request adaptation.

Multiple local runtimes and nodes may coexist. Model identity cannot assume one
global Ollama instance.

The current Lucy `ollama-core` path is evidence of one local runtime
implementation. It is not the permanent topology authority.

**OPEN:** How scheduler resource admission and live model-runtime capacity
participate in eligibility without reordering valid candidates.

## 19. Cloud provider execution

Cloud providers are optional candidates and require explicit permission.

Cloud eligibility must require, as applicable:

- the cloud provider/model appears in the effective ranking;
- explicit cloud permission at an applicable scope;
- privacy and data-handling compatibility;
- external-network permission;
- budget and cost eligibility;
- required approval grant;
- valid model-provider/runtime binding;
- health and availability;
- authorized credential reference;
- permitted request data classification.

Cloud credentials are resolved only for the selected governed invocation.
Credentials must not be stored in provider/model records, resolution records,
execution records, logs, prompts, events, or employee memory.

A local failure does not itself authorize cloud escalation. The next cloud
candidate may be considered only under the effective ranking and explicit
escalation conditions.

## 20. Specialized model services

Embedding, reranking, OCR, vision, and speech remain capability providers under
the same authority principles.

They:

- register provider/runtime identity and capabilities with Capability Manager;
- expose model/runtime facts and model-provider/runtime bindings through Model
  Registry where a model is involved;
- participate in ordered ranking when multiple eligible alternatives exist;
- use Dispatcher for invocation;
- use declared transport/request adaptation;
- obey privacy, cloud, budget, approval, health, and secret requirements.

They do not require a separate competing routing architecture.

The current Lucy implementations are evidence of useful provider
implementations. Existing OCR and speech Router/service contract mismatches must
be resolved during migration rather than preserved as authority.

**OPEN:** How non-model OCR engines or compound pipelines are represented in
Model Registry versus capability/provider inventory.

## 21. Health and availability observations

Administrative enablement, runtime health, model availability, capacity, and
validation are distinct facts.

Observations must identify:

- subject: provider/runtime, model-provider/runtime binding, or endpoint;
- observation type;
- observed state;
- source;
- observation time;
- expiry or freshness;
- diagnostic details safe for audit;
- relationship to administrative state.

An observation may make a ranked candidate ineligible under policy. It may not
reorder otherwise-valid candidates.

One failed probe must not silently rewrite an administrator's intended provider
configuration without an explicit lifecycle rule.

**OPEN:** Observation authorities, probe scheduling, freshness defaults, and
degraded-state eligibility.

## 22. Privacy, cloud, and budget constraints

These are hard restrictions when applicable.

Privacy constraints may include:

- locality or data-boundary requirements;
- retention restrictions;
- provider training-use restrictions;
- organization or tenant restrictions;
- approved data classifications;
- required redaction or minimization.

Cloud constraints include:

- explicit allow/deny;
- permitted providers or models;
- external-network permission;
- escalation conditions;
- approval requirements.

Budget constraints may include:

- maximum cost for an execution;
- maximum unit cost;
- remaining governed budget;
- permitted billing tier;
- usage-accounting availability.

Cost or locality does not reorder valid candidates unless the user explicitly
encoded that order. A cost ceiling or locality prohibition may make a candidate
ineligible.

**OPEN:** Budget authority, reservation/accounting protocol, and behavior when
current pricing is unavailable.

## 23. Escalation versus retry

Transport retry repeats the same resolved operation against the same resolved
provider/model under idempotency-aware policy.

Escalation considers a later ranked candidate only after the current candidate
becomes ineligible under a governed observation or an explicit escalation
policy authorizes the change. Escalation requires a new governed resolution.

These concepts are separate:

- transport retry;
- provider/model re-resolution;
- model escalation;
- validation-triggered escalation;
- user-authorized cloud escalation;
- cognitive retry;
- assignment retry;
- capability failure;
- validation-triggered reconsideration.

The existing Lucy Router behavior that catches any first-call error and silently
changes from Qwen to Llama conflates transport retry and model escalation. It is
prohibited in the target architecture.

**OPEN:** Which failure classes permit automatic re-resolution and which
require user, cognitive, or operator action.

Re-resolution does not automatically make a failed candidate invalid. A
candidate may be excluded from a subsequent resolution only when a governed
eligibility observation or escalation policy makes it invalid for the relevant
scope. Examples include provider or model unavailability, context
incompatibility, rate limiting, a governed health failure, or explicitly
authorized validation-triggered escalation. Without a changed eligibility fact
or explicit escalation authorization, re-resolution may select the same
first-ranked candidate again.

## 24. Secret-reference requirements

Provider and model-provider/runtime binding records may store only opaque
credential references and non-secret authentication metadata.

The dedicated secret authority must:

1. authenticate the calling Dispatcher;
2. authorize access for the specific provider, execution, organization,
   employee, and capability as applicable;
3. resolve credentials only at invocation time;
4. support provider-specific authentication mechanisms;
5. expose validity, expiry, rotation, and revocation state;
6. prevent credential persistence in execution or resolution audit;
7. redact secret values from logs, errors, traces, events, prompts, and memory;
8. audit access without recording the secret;
9. fail closed when a credential is absent, invalid, unauthorized, or revoked.

Dispatcher requests authorized credential use or injection; it does not own
secret resolution. Dispatcher, Router, adapters, and providers may transiently
consume authorized credential material as required, but must never persist it
in governed execution records, prompts, memory, events, or normal logs.

**OPEN:** Secret authority service boundary, credential-injection mechanism,
and whether the Dispatcher receives or delegates use of credential material.

## 25. First-run activation relationship

First Run coordinates initial installation capability establishment. It may
initiate governed workflows that result in:

- runtime activation or verification;
- provider/runtime registration;
- model registration;
- model-provider/runtime binding registration;
- record network and credential prerequisites without storing credentials;
- an initial global ranking seeded only after successful governed registration;
- produce an activation/registration outcome.

First Run does not permanently own per-request routing. Later global,
capability, employee, and job rankings are governed intelligence policy.
First Run is not declared the canonical runtime/model activation or
registration authority; that owner remains **OPEN**.

The current runtime-selection document is declarative evidence only; it does
not activate an Ollama/runtime instance or register models.

**OPEN:** Activation ownership, rollback, partial activation states, and when a
seeded global ranking becomes governed editable policy.

## 26. Required contracts

The v2 intelligence plane requires governed contracts for:

1. normalized model identity and model facts;
2. provider/runtime identity and provider facts;
3. model-provider/runtime binding;
4. provider/runtime/model observations;
5. scoped ordered ranking;
6. ranking provenance, precedence, and replacement semantics;
7. cumulative hard restrictions;
8. effective-ranking construction;
9. intelligence resolution request;
10. candidate eligibility result and rejection reasons;
11. governed resolution and rationale;
12. resolution validity, integrity, expiry, and revalidation;
13. intelligence execution request extending the canonical execution envelope;
14. provider protocol/request-adaptation declaration;
15. normalized intelligence result, usage, error, and ambiguous outcome;
16. transport retry, provider/model re-resolution, model escalation, and
    validation-triggered escalation policy;
17. cloud permission and privacy constraints;
18. budget eligibility and usage accounting;
19. credential reference, authorization, and resolution;
20. runtime activation and provider/model registration;
21. specialized embedding, reranking, OCR, vision, and speech provider
    contracts;
22. end-to-end intelligence correlation.

Existing Lucy schemas and metadata are migration evidence, not complete v2
contract authority.

## 27. Required tests

### Ranking semantics

- global ranking selection;
- capability ranking replacing global ranking;
- employee ranking replacing capability ranking;
- job ranking replacing employee ranking;
- no implicit list merging;
- explicit empty ranking and entirely absent ranking both fail;
- stable preservation of authored order.

### Eligibility

- capability and modality compatibility;
- context and feature requirements;
- availability and health;
- locality and privacy restrictions;
- cloud permission;
- budget ceiling;
- approval grant and default approval-pending behavior;
- credential availability;
- explicit allow/deny;
- runtime/hardware compatibility.

### Selection invariants

- first ranked valid candidate always wins;
- invalid candidates are removed with reasons;
- valid candidates are never reordered by score, quality, cost, locality,
  latency, or capacity;
- no unranked candidate is selected;
- complete rationale reproduces the decision.

### Identity and binding

- the same normalized model on multiple provider/runtime instances;
- provider-native name collisions;
- model revision/digest differences;
- model-provider/runtime binding availability and staleness;
- multiple local nodes and protocols.

### Execution boundaries

- Capability Manager resolves but does not invoke;
- Dispatcher invokes exact governed model/provider;
- Dispatcher never independently selects;
- Dispatcher never performs provider/model failover;
- Router/adapter transport cannot independently initiate or retarget;
- AI Router never substitutes;
- protocol adaptation preserves resolved identity and correlation.

### Retry and escalation

- idempotent transport retry;
- ambiguous timeout without blind side-effect replay;
- re-resolution does not itself invalidate the failed candidate;
- model escalation only under governed conditions;
- cloud escalation only when ranked and permitted;
- cognitive and assignment retry remain separate.

### Cloud and secrets

- explicit cloud denial;
- privacy and budget denial;
- credential resolution authorization;
- absent, expired, revoked, and rotated credential;
- no secret in persistence, logs, errors, prompts, events, or memory.

### Activation and observations

- First Run coordination of activation and registration;
- activation failure and rollback;
- runtime discovery reconciliation;
- stale health and availability;
- administrative state distinct from observed state.

### Specialized intelligence

- embedding and reranking contract conformance;
- OCR and speech corrected contract conformance;
- vision path and runtime requirements;
- specialized provider ranking and eligibility.

### End to end

- employee cognitive request through ranking, resolution, dispatch, local model,
  normalized result, and audit;
- job override using an explicitly approved cloud model;
- local failure with prohibited cloud escalation;
- local failure with authorized next-ranked escalation;
- complete correlation across job, employee, assignment, cognition, resolution,
  execution, attempt, provider, and model.

## 28. Migration strategy from Lucy

Lucy remains immutable evidence and is not a writable source authority.
Migration occurs through reviewed changes to `leos-v2`.

### Phase 1: Capture and normalize evidence

1. Inventory live callers of AI Router, Provider Registry, Model Registry,
   Employee Config Engine, Capability Manager, and Dispatcher.
2. Capture provider, model, preference, runtime, health, privacy, cost, and auth
   field mappings without copying raw credentials.
3. Identify provider/model records that represent the same runtime or model.
4. Record unresolved provenance and live-state questions as **OPEN**.

### Phase 2: Establish contracts and invariants

1. Define the required identity, model-provider/runtime binding, ranking,
   restriction, observation, resolution, execution, escalation, and
   secret-reference contracts.
2. Add tests proving the first-ranked-valid invariant.
3. Add responsibility-boundary and no-silent-substitution tests.
4. Define compatibility policy. **OPEN**

### Phase 3: Establish canonical authorities

1. Promote and narrow Capability Manager as canonical provider/resolution
   authority.
2. Promote and expand Model Registry as canonical independent model-facts
   authority.
3. Normalize Employee Config ranking and restrictions.
4. Extend canonical execution input with governed intelligence requirements and
   resolution.
5. Establish secret-reference resolution before enabling cloud execution.

### Phase 4: Migrate provider metadata

1. Map useful Provider Registry metadata into Capability Manager provider facts
   and Model Registry model-provider/runtime bindings.
2. Migrate callers.
3. Disable Provider Registry resolution as a peer authority.
4. Retire the standalone service only after dependency and data migration.

### Phase 5: Narrow transport

1. Remove ranking/default/fallback authority from AI Router.
2. Preserve validated Ollama/OpenAI protocol compatibility.
3. Prohibit silent model substitution.
4. Correct OCR and speech transport contracts.
5. Route all invocation through Dispatcher.

### Phase 6: Activate installation capability

1. Connect First Run declarations to governed runtime activation or
   verification.
2. Have the still-**OPEN** activation and registration authority register
   runtime/provider instances, models, and installed model-provider/runtime
   bindings.
3. Have First Run seed an initial global ranking only after successful governed
   registration.
4. Preserve operator network and cloud permission requirements.

### Phase 7: Acceptance and retirement

1. Run ranking, eligibility, identity, secret, retry/escalation, specialized,
   and end-to-end tests.
2. Verify no peer provider authority remains.
3. Verify Dispatcher is the only governed invocation authority.
4. Verify Router cannot select or substitute.
5. Verify every cloud call has explicit permission and authorized credentials.
6. Retire compatibility paths according to approved policy.

## 29. Unresolved questions

1. Does Capability Manager retrieve effective policy, or consume a
   versioned/signed effective-ranking reference?
2. What are the canonical model and provider/runtime identifier formats?
3. Are exact model artifacts and model families separately identified?
4. Which model-provider binding facts override intrinsic model or provider
   facts?
5. How is `local` scoped?
6. Are model-only, provider-only, and exact-binding ranking entries all
   permitted?
7. How are hard-restriction conflicts resolved across organization, user,
   employee, and job scopes?
8. How are policy and fact revisions pinned for long-running work?
9. What observation freshness and degraded-health rules apply?
10. How does scheduler admission interact with model capacity without
    reordering valid candidates?
11. Who owns approval grants, cloud permission, and budget authority?
12. What service implements secret resolution and credential injection?
13. Which failure classes permit automatic re-resolution or
    validation-triggered escalation?
14. Does AI Router remain one service or become protocol-specific adapters?
15. Where do non-model engines and compound specialized pipelines belong?
16. What authority activates and registers runtimes/models and handles
    rollback when First Run coordinates establishment?
17. How long do Provider Registry and Router compatibility surfaces remain?
18. How are Lucy persisted provider/model facts migrated with provenance?
