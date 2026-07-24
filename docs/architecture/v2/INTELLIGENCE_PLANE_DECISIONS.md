# LEOS v2 Intelligence Plane Decisions

## Status and use

These architecture decision records define the provisional intelligence-plane
boundaries for LEOS 0.2.0 Developer Preview v2. They complement the execution
plane decisions and do not change the rule that Execution Dispatcher is the
sole governed invocation authority.

The records do not define executable APIs or persistence schemas. Unsettled
details are marked **OPEN**.

## ADR-IP-001: User ranking is authoritative among eligible candidates

- **Status:** Accepted
- **Decision:** The explicit user-governed intelligence ranking determines the
  order among eligible candidates. The first ranked eligible candidate wins.
- **Context:** Lucy contains independent score, default, and fallback
  mechanisms that can choose or substitute models without preserving an
  employee or user ranking.
- **Consequences:** LEOS optimization applies after candidate order is fixed.
  Quality, cost, locality, latency, or capability estimates cannot reorder
  otherwise-valid candidates unless the user encoded that order.
- **OPEN:** Ownership and editing boundaries for global user/organization
  policy.

## ADR-IP-002: Eligibility may remove but never reorder candidates

- **Status:** Accepted
- **Decision:** Hard restrictions filter candidates. They do not assign
  comparative scores or reorder candidates that remain eligible.
- **Context:** Lucy Provider Registry adds locality, privacy, model-match, and
  other scoring bonuses. Such scoring can replace user preference with LEOS
  preference.
- **Consequences:** Every rejection has an explicit reason. The resolution
  rationale preserves original order and selected original rank. If the
  highest-ranked otherwise-eligible candidate lacks a required approval grant,
  the default result is `APPROVAL_PENDING`, not silent selection of a
  lower-ranked candidate. Only explicit future governed policy may permit
  skipping it.
- **OPEN:** Observation freshness and degraded-health eligibility rules.

## ADR-IP-003: Ranking precedence is job, employee, capability, then global

- **Status:** Accepted
- **Decision:** The most-specific defined ranking wins in this order:
  job override, employee ranking, capability-specific ranking, global ranking.
- **Context:** Existing Lucy structures contain employee preferences, arbitrary
  provider policies, defaults, and first-run declarations but no canonical
  precedence.
- **Consequences:** Resolution records the selected ranking scope and policy
  revision. Hard restrictions remain cumulative.
- **OPEN:** Restriction authority when organizational scopes conflict.

## ADR-IP-004: More-specific v2 rankings replace less-specific rankings

- **Status:** Accepted
- **Decision:** A defined more-specific ranking replaces rather than implicitly
  merges with a less-specific list.
- **Context:** Implicit merging would make authored order difficult to predict
  and audit.
- **Consequences:** A job list is evaluated as authored rather than interleaved
  with employee, capability, or global alternatives. An explicitly empty
  more-specific ranking replaces
  less-specific rankings and yields explicit resolution failure. If no ranking
  exists at any scope, resolution fails. There is no implicit emergency or
  unranked candidate pool.

## ADR-IP-005: Capability Manager is canonical provider and resolution authority

- **Status:** Accepted
- **Decision:** Capability Manager owns canonical provider inventory,
  provider-capability bindings, ordered eligibility evaluation,
  first-ranked-valid intelligence resolution, and durable rationale.
- **Context:** Lucy has overlapping Provider Registry and Capability Manager
  provider inventories and resolvers.
- **Consequences:** User-governed effective ranking establishes candidate
  order. Capability Manager performs ordered eligibility evaluation and
  first-ranked-valid selection without reordering valid candidates. It consumes
  model facts and model-provider/runtime bindings from Model Registry. It does
  not execute providers or own canonical model facts or model-provider/runtime
  bindings.
- **OPEN:** Whether effective policy is supplied by reference or retrieved
  directly.

## ADR-IP-006: Standalone Provider Registry is a migration source and retirement target

- **Status:** Accepted
- **Decision:** Useful Lucy Provider Registry metadata migrates to Capability
  Manager's canonical provider inventory and Model Registry's canonical
  model-provider/runtime bindings. Provider Registry does not remain a peer
  provider or resolution authority.
- **Context:** Provider Registry contains useful locality, privacy, cost, limit,
  model, health, and auth-reference fields, but it is disconnected from the
  adopted execution plane.
- **Consequences:** Callers and data are inventoried and migrated before
  retirement. Score-based intelligence resolution is not preserved as
  canonical selection.
- **OPEN:** Compatibility duration and any read-only facade.

## ADR-IP-007: Model Registry remains the independent model-facts authority

- **Status:** Accepted
- **Decision:** Model Registry is canonical for normalized model identity,
  model facts, lifecycle, and model-provider/runtime bindings. It remains
  distinct from Capability Manager provider inventory and provider-capability
  bindings.
- **Context:** Models may be served through multiple provider/runtime
  instances. Lucy Model Registry currently stores only limited CRUD metadata
  and does not affect execution.
- **Consequences:** Model Registry does not rank, resolve providers
  independently, invoke models, or store credentials.
- **OPEN:** Runtime-observation ingestion and exact model artifact identity.

## ADR-IP-008: Models and provider/runtime instances have separate identities

- **Status:** Accepted
- **Decision:** A normalized model identity is not a provider/runtime identity.
  Their executable relationship is represented by a model-provider/runtime
  binding.
- **Context:** Lucy mixes `provider: ollama`, `provider_id: ollama-local`,
  locality words such as `local`, and native model names.
- **Consequences:** The same model may bind to Lucy, Alice, DGX, vLLM,
  llama.cpp, cloud, or other instances without identity collision.
- **OPEN:** Identifier syntax and family/artifact distinction.

## ADR-IP-009: Dispatcher never selects intelligence

- **Status:** Accepted
- **Decision:** Cognitive Service sends Dispatcher a complete execution request,
  including applicable effective intelligence policy or ranking. Dispatcher
  requests a governed resolution from Capability Manager, receives the durable
  resolution record or reference, and invokes only the resolved
  provider/runtime and model. It does not construct ranking or choose
  alternatives independently.
- **Context:** Dispatcher is already the sole governed invocation authority
  under the execution-plane architecture.
- **Consequences:** Any provider/model change requires a new governed
  Capability Manager resolution. Dispatcher owns authorization, adaptation,
  invocation recording, same-target idempotency-aware transport retry,
  normalization, and execution audit.
- **OPEN:** Resolution delivery, validity, integrity, and revalidation
  mechanism.

## ADR-IP-010: AI Router is transport and protocol compatibility only

- **Status:** Accepted
- **Decision:** AI Router is narrowed to physical transport and protocol
  compatibility for an already-authorized, explicitly resolved intelligence
  request.
- **Context:** Lucy Router combines Ollama invocation, hard-coded
  default/fallback selection, OpenAI facade behavior, specialized proxies, and
  unrelated foundation APIs.
- **Consequences:** Useful Ollama and OpenAI compatibility may be preserved.
  Router does not own ranking, provider inventory, model facts, or independent
  routing policy. It may not independently initiate, redirect, retarget,
  repeat against another target, escalate, or substitute an invocation.
- **OPEN:** Standalone Router versus protocol-specific adapters.

## ADR-IP-011: Silent Router fallback and model substitution are prohibited

- **Status:** Accepted
- **Decision:** A Router or transport adapter must report failure for the
  explicitly resolved model. It may not silently substitute another model.
- **Context:** Lucy Router changes from the requested/default model to a
  hard-coded Llama fallback after any exception.
- **Consequences:** Model escalation is handled through governed resolution.
  Explicit model identity remains accurate in audit and results.
- **OPEN:** Compatibility treatment for existing direct Router callers.

## ADR-IP-012: First Run coordinates capability establishment and seeds defaults

- **Status:** Accepted
- **Decision:** First Run coordinates initial installation capability
  establishment. It may initiate workflows resulting in runtime activation,
  provider registration, model registration, and model-provider/runtime
  binding registration. It seeds the initial global ranking only after
  successful governed registration and does not permanently control
  per-request selection.
- **Context:** Current first-run runtime selection writes declarations but does
  not activate runtimes or register models.
- **Consequences:** Later governed ranking at global, capability, employee, and
  job scopes controls resolution. First Run is not declared the canonical
  runtime/model activation or registration authority.
- **OPEN:** Activation owner, rollback, partial state, and transition from seed
  to editable governed policy.

## ADR-IP-013: Cloud execution requires explicit cloud permission

- **Status:** Accepted
- **Decision:** A cloud candidate is ineligible without explicit applicable
  cloud permission, even if it is ranked.
- **Context:** Lucy contains `allow_cloud` declarations, but the canonical
  execution path does not enforce them.
- **Consequences:** Local failure alone never authorizes cloud use. Privacy,
  network, budget, approval, and credential requirements remain cumulative.
- **OPEN:** Cloud-permission issuer, scope, expiry, and revocation.

## ADR-IP-014: Cloud credentials require authorized secret-reference resolution

- **Status:** Accepted
- **Decision:** Provider and model-provider/runtime binding records store only
  opaque credential references. Dispatcher requests authorized credential use
  or injection. A dedicated secret authority authenticates and authorizes the
  request, resolves the reference, performs or supplies transient injection,
  and audits use without exposing credential material.
- **Context:** Lucy demonstrates `secret_ref` metadata and environment API keys
  but has no provider-secret resolution authority in the audited path.
- **Consequences:** Raw credentials are forbidden in provider/model records,
  resolutions, executions, normal logs, prompts, events, and employee memory.
  Dispatcher, Router, adapters, and providers may consume authorized credential
  material transiently but never persist it in governed records.
- **OPEN:** Secret-service implementation, credential-injection mechanism, and
  access scope.

## ADR-IP-015: Specialized intelligence follows the same authority principles

- **Status:** Accepted
- **Decision:** Embedding, reranking, OCR, vision, and speech are capability
  providers governed by the same provider inventory, model-facts, ranking,
  eligibility, dispatch, health, privacy, and credential principles.
- **Context:** Lucy Router currently exposes specialized hard-wired routes, with
  contract mismatches for OCR and speech.
- **Consequences:** Specialized intelligence does not create a competing
  routing architecture. Provider-specific transport remains declarative and
  auditable.
- **OPEN:** Representation of non-model engines and compound pipelines.

## ADR-IP-016: Retry and model escalation are separate concepts

- **Status:** Accepted
- **Decision:** Transport retry repeats the same resolved operation against the
  same authorized target under idempotency-aware policy. Provider/model
  re-resolution, model escalation, and validation-triggered escalation are
  separate operations. Every provider/model change requires a new governed
  Capability Manager resolution.
- **Context:** Lucy Router conflates any request failure with model fallback.
- **Consequences:** Retry does not change model identity. Escalation requires
  policy-defined conditions and must preserve ranked order and hard
  restrictions. Re-resolution does not itself invalidate a failed candidate;
  without a changed governed eligibility fact or explicit escalation
  authorization, the same first-ranked candidate may be selected again.
- **OPEN:** Failure classes that permit automatic re-resolution.

## ADR-IP-017: Hard restrictions are cumulative

- **Status:** Accepted
- **Decision:** A more-specific ranking replaces a less-specific ranking, but
  applicable hard restrictions remain cumulative.
- **Context:** Ranking precedence must not allow a job preference to bypass
  organization privacy, cloud, budget, approval, or denial policy.
- **Consequences:** Resolution records restriction provenance and the reason a
  candidate is disqualified.
- **OPEN:** Explicit override authority for restrictions, if any.

## ADR-IP-018: Resolution rationale proves ranking preservation

- **Status:** Accepted
- **Decision:** Every intelligence resolution records effective ranking,
  original candidate order, eligibility outcomes, rejection reasons, selected
  original rank, governing facts, and policy provenance.
- **Context:** The product principle must be auditable rather than inferred from
  the selected result.
- **Consequences:** Tests can prove that LEOS filtered but did not reorder.
  Secret values and unnecessary prompt data are excluded.
- **OPEN:** Retention, integrity protection, and cross-service audit linkage.

## ADR-IP-019: Health observations do not become hidden ranking scores

- **Status:** Accepted
- **Decision:** Health and availability may make a candidate eligible or
  ineligible according to policy. They do not reorder candidates that remain
  valid.
- **Context:** Lucy Provider Registry applies health and locality score
  adjustments and rewrites provider administrative status after a probe.
- **Consequences:** Administrative enablement and observed state are distinct.
  Observation freshness and policy determine eligibility.
- **OPEN:** Probe authority, freshness, and degraded-state rules.

## ADR-IP-020: Lucy is migration evidence, not intelligence source authority

- **Status:** Accepted
- **Decision:** `lucy-runtime-reference` remains immutable evidence. All v2
  implementation and contract work occurs through reviewed changes to
  `leos-v2`.
- **Context:** Lucy contains useful implementations and metadata alongside
  duplicated authorities and historical behavior.
- **Consequences:** Provider/model data migration preserves provenance and
  excludes raw credentials. Existing behavior is not canonical merely because
  it runs on Lucy.
- **OPEN:** Operational data extraction, provenance packaging, and compatibility
  acceptance procedure.

## Consolidated OPEN questions

1. Policy delivery to Capability Manager: retrieval or governed reference.
2. Canonical model and provider/runtime identifier syntax.
3. Model family versus exact artifact identity.
4. Intrinsic versus binding-level model/provider facts.
5. Meaning and scope of locality.
6. Permitted ranking-entry forms.
7. Restriction conflict and override authority.
8. Policy and fact revision pinning.
9. Health, availability, price, and capacity observation freshness.
10. Scheduler capacity interaction without hidden reordering.
11. Approval, cloud-permission, and budget authorities.
12. Secret-service implementation and credential injection.
13. Automatic re-resolution and validation-triggered escalation failure
    classes.
14. AI Router deployment boundary.
15. Non-model and compound specialized-provider representation.
16. Runtime/model activation, registration, and rollback authority coordinated
    by First Run.
17. Provider Registry and Router compatibility periods.
18. Lucy operational data migration and provenance.
