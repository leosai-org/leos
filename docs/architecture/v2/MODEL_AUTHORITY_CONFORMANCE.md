# LEOS v2 Model Authority Conformance

## Scope

Epic 2.1 establishes trustworthy model facts and model-to-runtime/provider
bindings. It does not implement ranking, intelligence resolution, model
selection, fallback, execution, model installation, or runtime transport.

The promoted service-local inventory contract is explicitly provisional:
`model-registry.inventory.provisional-v1`. No shared canonical JSON Schema was
needed in this Epic.

## Authority reconciliation

| Existing component | Observed responsibility | Disposition |
|---|---|---|
| Lucy `model-registry/` | JSON-file CRUD keyed by runtime model name; provider string and availability-like status embedded in the model | **MIGRATE**: donor concept promoted and deliberately adapted |
| Lucy `provider-registry/` | Provider endpoints, models, capabilities, health, policy filters, score-based `/resolve`, and highest-score selection | **DEPRECATE**: migrate provider inventory to Capability Manager and model relationships to Model Registry; do not preserve scoring |
| v2 Capability Manager | Provider inventory, provider-capability bindings, hard provider eligibility, governed resolution | **KEEP** as sole provider authority |
| Lucy AI Router | Ollama discovery and transport plus default model, fallback model, direct model choice, retry with fallback, and Model Registry proxy mutation | **TRANSPORT-ONLY** target; selection and registry proxy behavior are legacy debt |
| v2 Employee Registry/Builder model preferences | Employee configuration and priority-shaped provider/model preferences | **FUTURE PHASE**: input evidence for governed ranking, not model facts |
| v2 Resource Profile provider preferences | Resource-admission projection containing provider/model preference-shaped values | **FUTURE PHASE**: must not become model-selection authority |
| v2 First Run runtime catalog/state | Chooses a deployment profile and writes static chat/embedding/runtime names | **MIGRATE** later into governed bootstrap coordination |
| Lucy Console provider views | Reads standalone Provider Registry for workforce and other status surfaces | **MIGRATE** later to canonical read authorities |
| Static model names and environment defaults | Installation/runtime compatibility behavior | **DEPRECATE** as selection authority; retain until governed activation migration |

## Canonical Model Registry responsibility

Model Registry owns:

- stable normalized model identity;
- descriptive and lifecycle facts;
- declared model modalities and capabilities;
- context and output limits where known;
- runtime requirements where known;
- administrative model enablement;
- explicit model-to-provider/runtime bindings;
- runtime-native model references and aliases on bindings;
- administrative binding enablement;
- reported binding availability facts;
- immutable model and binding inventory revisions;
- model-inventory audit events.

It does not own provider endpoints, provider capabilities, provider
eligibility, ranking, preference, selection, fallback, invocation, execution
history, credentials, or secret values.

## Model identity

`model_id` identifies one concrete deployable model variant supplied through a
governed registration workflow. For example, Qwen 7B Q4_K_M, Qwen 7B Q8, and
Qwen 7B FP16 require distinct model identities. The same concrete variant may
be exposed by several providers through several bindings. Identity is
independent of provider URL, deployment, process lifetime, container identity,
and runtime alias. Family remains descriptive and is not a conceptual-family
selection identity.

A model may record optional facts only when known:

- display name, family, publisher, version, and architecture;
- parameter count and quantization;
- input/output modalities and declared capabilities;
- context window and maximum output size;
- runtime requirements;
- bounded metadata.

Registration does not infer absent facts. A provider-native identifier such as
`qwen2.5:7b-instruct` belongs on a binding as `runtime_model_ref`; it does not
silently redefine normalized model identity.

Version, architecture, parameter count, and quantization are identity-bearing
facts in the current inventory. PATCH may enrich one of these facts from
unknown to known. It may not remove or change a known value; a materially
different value requires a new `model_id`. Other descriptive facts,
capabilities, modalities, limits, requirements, metadata, and administrative
enablement remain mutable.

This prevents silent variant replacement but does not claim complete artifact
identity. Artifact digests, packaging formats, and equivalence across
independently sourced artifacts remain **OPEN**.

## Model-runtime binding

A binding relates exactly one normalized `model_id` to exactly one canonical
Capability Manager `provider_id`. It records:

- stable `binding_id`;
- `model_id`;
- `provider_id`;
- an exact Capability Manager provider reference and revision;
- provider-native `runtime_model_ref`;
- optional runtime type;
- administrative enablement;
- availability observation;
- binding-specific runtime requirements and bounded metadata;
- binding revision and timestamps.

One model may have several provider bindings. One provider may expose several
models. Model Registry stores no provider URL, health URL, adapter endpoint, or
provider credential.

A logical runtime target is unique by `provider_id`, normalized
`runtime_type`, and normalized `runtime_model_ref`. A target cannot be bound
twice or identify two canonical models simultaneously. The same model and
provider may use distinct aliases where those are genuine runtime targets, and
the same alias text may be used by different providers. Runtime type is
lower-cased and trimmed; runtime-native references are trimmed but retain case.

## Capability Manager relationship

Capability Manager remains the canonical provider authority. Before accepting
a binding, Model Registry verifies the supplied provider reference through
Capability Manager's public provider-inventory API and requires the exact
provider revision. This creates referential integrity without reading or
mutating Capability Manager storage and without copying endpoint authority.

The binding retains the verified reference as evidence. Provider mutation can
make that evidence stale; continuous reconciliation and staleness policy are
future work. A binding or declared model capability never independently
authorizes execution.

Verification distinguishes authority unavailability, malformed responses,
valid absence, and exact revision mismatch. It establishes only that provider
revision R was current when Capability Manager answered. It is not an atomic
cross-service snapshot.

Capability Manager currently provides neither exact provider lookup nor
pagination beyond its 2,000-record list limit. If a full page omits the target,
Model Registry reports incomplete lookup rather than falsely claiming absence.

## Capability, availability, and enablement semantics

Provider capability means that a provider is registered and bound to perform
a governed capability. Model capability is only a declared fact about a
model. Capability Manager must later evaluate both through governed
resolution.

Availability means that an observation source reported a binding as
`unknown`, `available`, or `unavailable`. It is not eligibility or preference.
Likewise, `enabled: true` is administrative inventory state, not a preferred
or selected position. Model Registry query filters return matching facts; they
never select a winner.

Provider preference and model preference remain separate future policy
concepts. The inventory can represent independent provider and model
identities without combining them into a score.

## Revision semantics

Model and binding revisions are SHA-256 content identities over their
canonical material facts, prefixed with `sha256:`. Created/updated timestamps
and audit event identities are excluded.

- identical registration or update preserves revision and timestamps;
- a material fact change produces a new revision;
- mutable display text is covered by revision but is never itself revision
  identity;
- a runtime alias change changes only the binding revision, not `model_id`;
- a provider reference revision is material binding evidence.
- capabilities and modalities are deduplicated and sorted because they are
  set-like facts rather than preference order;
- arbitrary metadata arrays retain authored order;
- availability observations and administrative enablement are material
  binding facts and therefore change binding revision.

This provides deterministic revision evidence without treating wall-clock time
or mutable names as authority.

Model and binding PATCH require `expected_revision`. Mutation begins a
serialized local write transaction, compares the current revision, and
atomically persists state and event. A stale writer receives
`revision_conflict`. Provider verification happens before a binding write
transaction; the expected local binding revision is then checked.

Registration uses the same serialized write discipline. Concurrent identical
registration is idempotent, while conflicting identity or logical-target
registration returns a deterministic conflict.

## Persistence and migration

The service uses SQLite tables for:

- schema migration metadata;
- models;
- model-runtime bindings;
- inventory audit events.

Startup creates missing objects with `CREATE IF NOT EXISTS`; it does not drop
or rewrite unknown/donor tables. Model foreign keys protect local model
references. Provider integrity uses the Capability Manager API rather than a
cross-service database foreign key.

The logical runtime-target unique index is established non-destructively and
repeated startup preserves populated v1 rows. Mutation and its event commit in
one transaction. Events record previous and new revision evidence, but do not
store complete historical documents and cannot reconstruct old state. Current
inventory tables—not the event stream—remain state authority.

Lucy runtime JSON, databases, logs, caches, and generated state were not
copied. Import of donor model data requires a future governed migration that
separates normalized identity from provider-native aliases.

## API surface

The minimum service-local API is:

- `GET /health`;
- `POST /models`;
- `GET /models`;
- `GET /models/{model_id}`;
- `PATCH /models/{model_id}`;
- `POST /bindings`;
- `GET /bindings`;
- `GET /bindings/{binding_id}`;
- `PATCH /bindings/{binding_id}`;
- `GET /events`.

There is intentionally no delete, best-model, select, recommend, route,
resolve, fallback, invoke, or execute endpoint. Registration conflicts require
an explicit update rather than implicit overwrite.

PATCH bodies require `expected_revision`; a stale value returns HTTP 409 with
`revision_conflict`.

## Provider Registry disposition

Lucy Provider Registry is donor evidence and a retirement target, not a v2
peer authority. Its useful provider facts belong in Capability Manager; its
model lists become governed Model Registry bindings. Its health observations
may later feed canonical availability. Its priority, locality bonuses,
privacy bonuses, model-match bonuses, degraded penalty, highest-score
selection, and `/resolve` authority must not migrate.

Lucy Console callers must move to canonical read APIs before the standalone
Provider Registry can be retired. Compatibility duration remains **OPEN**.

## AI Router legacy behavior

The Lucy Router currently:

- defaults missing model requests to `OLLAMA_MODEL`;
- retries failed Ollama calls using `OLLAMA_FALLBACK_MODEL`;
- accepts a caller model string as direct runtime selection;
- exposes Ollama tags as its own model inventory;
- proxies Model Registry reads and writes;
- routes specialized model services through static endpoints.

Defaults, fallback substitution, direct selection, and registry mutation
violate the v2 authority boundary. Ollama tag discovery remains useful
availability evidence, and protocol translation remains useful transport
behavior. Router refactoring is intentionally deferred.

## First Run future role

Current First Run chooses one static runtime profile and persists provider
type, runtime type, chat model, embedding model, and external-network
permission. It does not register canonical providers, models, or bindings.

Future First Run should coordinate, in order:

1. provider registration through Capability Manager;
2. normalized model registration through Model Registry;
3. verified model-runtime binding registration;
4. availability observation;
5. separately governed initial ranking creation and activation.

First Run is a bootstrap coordinator, not the continuing authority for any of
those records. Exact activation authority remains **OPEN**.

## Security boundary

Model Registry applies a narrow value-aware guard against obvious raw
credential storage. It rejects non-empty scalar secret material under explicit
credential-value fields such as `api_key`, `access_token`, `refresh_token`,
`client_secret`, `password`, `private_key`, `private_key_pem`,
`secret_value`, and `credential_value`. Boolean declarations are not secret
values. Descriptive fields such as `token`, `tokenizer`, `secret_name`,
`api_key_required`, `private_key_support`, and `credential_type` are allowed.

This guard is not general DLP and does not assert that arbitrary metadata is
secret-free. Model Registry stores no provider authentication configuration,
and it neither resolves nor introduces secret references in this Epic.

Metadata, runtime requirements, and availability details are bounded to 64 KiB
and twelve nested levels per object. Nested metadata is source evidence only:
names such as `model_id`, `provider_id`, `revision`, `enabled`, and
`capabilities` never override canonical top-level fields.

## Remaining Intelligence Plane work

- canonical model identifier syntax and artifact-strength rules;
- governed model/provider ranking contracts and precedence implementation;
- Capability Manager consumption of model and binding facts;
- provider-reference staleness and reconciliation policy;
- availability observation authentication, freshness, and reconciliation;
- model discovery normalization for Ollama and other runtimes;
- First Run registration and activation workflow;
- Provider Registry caller migration and retirement;
- AI Router transport-only refactor;
- governed model installation/download lifecycle;
- Secret Authority integration;
- model/runtime resolution and full Intelligence Plane E2E.
