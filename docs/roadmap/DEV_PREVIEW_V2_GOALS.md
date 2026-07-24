# LEOS Dev Preview v2 — Session Goals and Development Direction

**Project:** LEOS — Logical Unified Cognitive Intelligence  
**Target:** LEOS 0.2.0 Developer Preview / “Dev Preview v2”  
**Status:** Planning baseline  
**Purpose:** Capture the goals, architectural decisions, priorities, and development strategy established during this session so future development can continue without reconstructing the discussion.

---

## 1. Core Direction

The next LEOS development phase should **not** be a narrow patch whose only purpose is connecting LEOS to OpenAI.

Instead, Dev Preview v2 should complete the core systems required to make LEOS a genuinely usable AI operating and workforce platform.

### Guiding transition

**RC11 / Dev Preview v1**

> Proves the LEOS architecture exists.

**Dev Preview v2**

> Proves LEOS actually works as an extensible AI workforce platform.

The goal is to move LEOS from an architecture/developer preview into a system that can:

- use local and cloud models interchangeably;
- allow users to define model/provider preference;
- give AI employees real capabilities;
- execute work safely in governed local environments;
- retain project and employee knowledge;
- measure model usage, cost, and productivity;
- allow LEOS itself to participate in developing LEOS.

---

# 2. Preserve RC11

The current RC11 source release should remain frozen as the public Developer Preview v1 baseline.

Development for v2 should occur in a new development lineage/workspace rather than modifying governed RC11 release artifacts directly.

Suggested next version:

```text
LEOS 0.2.0-dev-preview
```

Internal working name:

```text
Dev Preview v2
```

---

# 3. Dev Preview v2 Primary Theme

## From architecture preview to usable AI operating platform

Dev Preview v2 should focus primarily on completing the missing execution/runtime systems rather than cosmetic UI work.

The system should demonstrate that LEOS can:

1. select and execute against real intelligence providers;
2. use local models whenever appropriate;
3. escalate to cloud models when required;
4. safely operate tools and development environments;
5. install/discover capabilities;
6. maintain persistent structured memory;
7. measure production per token and cost;
8. allow an AI employee to perform meaningful development work.

---

# 4. Universal Intelligence Provider Runtime

This should be the **first major Dev Preview v2 epic**.

The existing Provider Registry already models providers, capabilities, locality, cost, privacy, priority, models, and provider policies. However, a real provider execution layer is still required.

Target architecture:

```text
Employee Cognitive Request
        |
        v
Provider / Model Policy
        |
        v
Provider Resolver
        |
        v
Provider Execution Runtime
        |
        +--> Local OpenAI-compatible runtime
        +--> Ollama
        +--> vLLM
        +--> llama.cpp
        +--> OpenAI
        +--> Anthropic
        +--> Gemini
        +--> Custom HTTP provider
        +--> Future providers
```

The execution layer should be generic and provider-neutral.

OpenAI should be the first major external-provider acceptance test, but the subsystem must not be designed only for OpenAI.

---

# 5. User-Controlled Model Ranking

LEOS should **not automatically choose whatever model it thinks is best without user control**.

The user should define the intelligence hierarchy.

LEOS then chooses the highest-ranked available and suitable model within that policy.

## Principle

> **The user defines the intelligence hierarchy. LEOS optimizes execution within that hierarchy.**

Example:

```yaml
model_policy:
  text.reason:
    ranking:
      - qwen2.5:7b-instruct
      - llama3.1:8b
      - openai:standard-reasoning
      - openai:advanced-reasoning

    allow_escalation: true
    max_local_attempts: 2
```

LEOS may move down the ranking when:

- a provider is offline;
- a model lacks the required capability;
- context requirements exceed the model;
- the user-defined retry/escalation policy is reached;
- a privacy rule disqualifies a provider;
- a cost ceiling disqualifies a provider.

LEOS should **not silently ignore the user's ranking simply because another model appears more capable**.

---

# 6. Ranking Scopes

Model/provider preference should be configurable at multiple scopes.

## Global ranking

Default LEOS-wide preference.

Example:

```text
1. Qwen local
2. Llama local
3. Cloud standard model
4. Cloud advanced model
```

## Capability-specific ranking

Different models may be preferred for different tasks.

Example:

```text
Coding
1. Local coding model
2. Cloud standard coding model
3. Cloud advanced reasoning model

Reasoning
1. Qwen local
2. Cloud standard reasoning model
3. Cloud advanced reasoning model

Vision
1. Local vision model
2. Cloud vision model
```

## Employee-specific ranking

Employees may have specialized model preferences.

Example:

```text
LEOS Developer
1. Local coding model
2. Cloud standard coding/reasoning model
3. Cloud advanced reasoning model
```

## Job-level override

A user should be able to override the normal hierarchy for a single job without permanently changing the employee.

Example:

```text
Use the advanced cloud model first for this assignment.
```

---

# 7. Provider Ranking

Model preference and provider preference should be distinct.

A model may eventually be available from multiple runtimes or machines.

Example:

```text
Model ranking:
1. Qwen 14B
2. GPT-class cloud model

Provider ranking:
1. Lucy local
2. Alice local
3. DGX node
4. Cloud API
```

LEOS resolves the desired model against available providers while respecting:

- user ranking;
- health;
- capability;
- privacy;
- budget;
- locality;
- availability.

---

# 8. Local Models First — Cloud as Escalation

LEOS should take advantage of existing local models rather than calling OpenAI for every reasoning step.

Desired pattern:

```text
Request
   |
   v
LEOS classifies requirement
   |
   +--> trivial/repetitive --> local model
   |
   +--> ordinary reasoning --> local model
   |
   +--> specialized local capability --> local service/model
   |
   +--> complex architecture/debugging --> cloud model
   |
   +--> sensitive/local-only --> local model only
```

Potential workload examples:

```text
Summarize test logs
    -> local

Extract failed services
    -> local

Search project memory
    -> local embeddings/search

Generate boilerplate tests
    -> local

Routine code review
    -> local first

Distributed architecture failure
    -> cloud escalation

Critical architectural design
    -> cloud advanced model
```

---

# 9. Escalation Policy

LEOS should support controlled escalation rather than static provider selection.

Example:

```text
Local model attempts task
        |
        v
Validation / confidence / tests
        |
      success?
      /     \
    yes      no
     |        |
 continue   next ranked model
```

Possible policy:

```yaml
provider_policy:
  prefer_local: true
  allow_cloud: true

  escalation:
    max_local_attempts: 2
    cloud_on_test_failure: true
    cloud_on_timeout: true
    cloud_on_low_confidence: true

  privacy:
    sensitive_data: local_only

  budget:
    cloud_cost_per_job_limit: 1.00
```

The user remains authoritative.

---

# 10. Model and Provider Management UI

Dev Preview v2 should expose model/provider management in Settings.

Suggested experience:

```text
Settings
  -> Models & Intelligence
```

Example UI:

```text
Reasoning Priority

[drag] Qwen 2.5 7B          Local      #1
[drag] Llama 3.1 8B         Local      #2
[drag] Cloud Standard       Cloud      #3
[drag] Cloud Advanced       Cloud      #4
```

Each model/provider should expose controls such as:

```text
Enabled
Local only
Allowed capabilities
Max cost
Context limit
Use for coding
Use for reasoning
Use for vision
Fallback allowed
```

Advanced routing:

```text
Fallback after failures
Escalate on timeout
Escalate on low confidence
Allow cloud
Sensitive data local-only
```

The model router should be transparent rather than mysterious.

---

# 11. OpenAI Inside LEOS

OpenAI should be used as an **intelligence provider inside LEOS**, not as the system that owns the entire workflow.

Desired architecture:

```text
LEOS Employee
     |
     +--> memory
     +--> project context
     +--> provider policy
     +--> tools
     +--> approvals
     |
     v
Provider Runtime
     |
     +--> local model
     |
     +--> OpenAI API
```

LEOS remains authoritative for:

- memory;
- state;
- employee configuration;
- project knowledge;
- tool access;
- approvals;
- workflows;
- execution history;
- context assembly.

Only the relevant reasoning package should be sent to an external provider.

---

# 12. Production-per-Token Hypothesis

A major research and product goal for v2 is measuring whether LEOS increases useful output per model token.

Instead of repeatedly transmitting huge conversation histories, LEOS should retrieve only relevant context.

Traditional long-session pattern:

```text
Entire conversation
architecture history
logs
old decisions
current task
code
corrections
    |
    v
MODEL
```

Target LEOS pattern:

```text
Project Memory
      |
Relevant Decisions
      |
Current Files
      |
Current Failure
      |
Current Task
      |
      v
Focused Context Package
      |
      v
Model
```

Expected potential benefits:

- reduced prompt size;
- lower API cost;
- faster model calls;
- less irrelevant context;
- better task focus;
- easier long-running development;
- model interchangeability.

This must be measured rather than assumed.

---

# 13. Token, Cost, and Productivity Telemetry

Dev Preview v2 should record model execution telemetry.

Per invocation:

```text
Provider
Model
Employee
Job
Capability
Input tokens
Cached input tokens
Output tokens
Cost
Latency
Success/failure
Retries
Escalations
Outcome
```

Organization Intelligence should eventually calculate metrics such as:

```text
Tokens consumed
API spend
Tasks completed
Successful outputs
Cost per completed task
Tokens per completed task
Local/cloud ratio
Escalation frequency
```

A key future KPI:

```text
Production per token
```

Potential comparison:

```text
Direct-model workflow:
18,400 tokens / completed task

LEOS workflow:
3,200 tokens / completed task
```

Any marketing claim should be based on actual measured results.

---

# 14. Coding Sandbox

After provider execution works, the **coding sandbox should be the next bootstrap feature**.

Once LEOS has a provider runtime plus a sandbox, it can begin helping build the rest of Dev Preview v2.

The sandbox should be isolated from the host.

Example:

```text
/mnt/nvme/leos-workspaces/
    jobs/
      <execution-id>/
        repo/
        artifacts/
        logs/
        results/
```

Typical workflow:

```text
create isolated workspace
        |
checkout/copy governed source
        |
create working branch
        |
inspect code
        |
edit
        |
run tests
        |
inspect failures
        |
revise
        |
rerun tests
        |
generate diff
        |
request approval
```

---

# 15. Sandbox Security and Permissions

The model should never receive unrestricted Lucy host access.

Suggested permission defaults:

```text
filesystem.read        automatic
filesystem.write       sandbox only
code.search            automatic
shell.execute          sandbox only
tests.execute          automatic
git.diff               automatic
git.branch             automatic

git.commit             approval
git.push               approval
production.modify      approval
host.execute           prohibited or approval
secret.read            prohibited
destructive.delete     approval
```

This should integrate with LEOS governance and approval systems.

---

# 16. Capability Store

Capability Store should become a core v2 subsystem.

It should be distinct from Plugin Store.

## Relationship

```text
Plugin
   |
   v
registers one or more
Capabilities
   |
   v
assigned to
Employees
```

Examples:

```text
coding.python
coding.javascript
code.search
filesystem.workspace
git.read
git.diff
git.commit
docker.inspect
docker.build
testing.pytest
testing.integration
web.search
browser.navigate
document.read
document.convert
ocr.extract
email.read
calendar.read
gis.query
```

An employee should consume a capability without needing to know whether it is implemented by:

- Python;
- shell;
- HTTP;
- Docker;
- MCP;
- a local service;
- a plugin;
- a remote API.

---

# 17. Capability Marketplace / Store UX

The user should eventually be able to browse capabilities similarly to an app store.

Example:

```text
Capability Store

Coding
  Python Development
  Git
  Docker
  Test Runner

Research
  Web Search
  Browser
  Document Retrieval

Business
  Email
  Calendar
  CRM
  Accounting

Specialized
  GIS
  Vision
  OCR
  Speech
```

Installation should:

1. install/enable the implementing plugin/service;
2. register provided capabilities;
3. expose them to compatible employees;
4. apply permission defaults;
5. make them assignable from employee configuration.

---

# 18. Secret / Credential Manager

The Provider Registry already anticipates secret references.

Dev Preview v2 should implement a real local secret-resolution system.

Example:

```text
providers/openai/api-key
github/developer/token
wordpress/site/password
gmail/account/oauth
```

Employees should not receive raw secrets unless absolutely required.

Preferred path:

```text
Employee requests capability
        |
        v
Tool / Provider Runtime
        |
        v
Secret Manager
        |
inject credential at execution time
```

Secrets should:

- remain local;
- never be committed;
- never appear in normal logs;
- never be stored in employee memory;
- support rotation;
- support per-plugin/provider scope.

---

# 19. Memory Contract v2

A contract drift was discovered during this session between the Core Intelligence Adapter and the Memory Service.

Dev Preview v2 must establish one canonical memory contract.

Memory should become a stable core API.

Suggested scopes:

```text
User memory
Employee memory
Project memory
Company memory
Job memory
Experience memory
System memory
```

Project memory is especially important for software-development continuity and production-per-token testing.

---

# 20. Context Assembly

LEOS should not send all stored memory to a model.

A Context Assembly layer should retrieve and package only information relevant to the current task.

Potential sources:

```text
employee identity
employee instructions
current job
project memory
recent decisions
relevant source files
relevant tests
recent failures
capability results
organization policies
```

Context assembly should be observable so the user can inspect what LEOS sent to a model.

---

# 21. LEOS Core Developer Employee

Once Provider Runtime and Coding Sandbox exist, create an early internal employee:

```text
LEOS Core Developer
```

Suggested role:

```text
Role:
LEOS Core Developer

Primary intelligence:
user-ranked local/cloud provider hierarchy

Memory:
LEOS architecture
project history
roadmap
decisions
release history
known bugs
development outcomes

Capabilities:
code.read
code.write
code.search
filesystem.workspace
shell.sandbox
git.status
git.diff
git.branch
tests.run
docker.inspect
documentation.search
memory.search

Approvals:
commit
push
production modification
destructive operations
```

---

# 22. Bootstrap Strategy — LEOS Builds LEOS

The v2 development strategy should become progressively recursive.

## Stage 1

```text
Brett + ChatGPT
    |
build Provider Runtime
```

## Stage 2

```text
Brett + ChatGPT
    |
build Coding Sandbox
```

## Stage 3

```text
LEOS Developer
    |
local models + OpenAI
    |
sandbox
    |
helps build:
  Memory v2
  Capability Store
  Secret Manager
  telemetry
  model management
```

## Stage 4

LEOS performs a meaningful LEOS development task from diagnosis through tested patch generation.

---

# 23. LEOS-Develops-LEOS Acceptance Test

A major Dev Preview v2 acceptance gate should be:

> **LEOS must successfully use an AI employee, persistent project knowledge, ranked provider routing, capabilities, and an isolated coding environment to modify and test LEOS itself.**

Example acceptance job:

```text
Audit the current Memory Service and Core Intelligence Adapter.

Identify the contract drift responsible for pending memory.store records.

Implement the correction in an isolated development workspace.

Run relevant tests.

Present the patch and evidence for human review.
```

Expected execution:

```text
retrieve project knowledge
        |
identify relevant source
        |
select ranked provider
        |
reason
        |
edit sandbox source
        |
run tests
        |
inspect failures
        |
revise
        |
pass tests
        |
generate diff
        |
request approval
```

---

# 24. ChatGPT's Role During v2 Development

ChatGPT remains valuable as:

```text
Architect
Technical reviewer
Planning partner
Release reviewer
Debugging partner
Design critic
Research assistant
```

Long development work should be separated into focused chats/epics instead of one extremely long thread.

Suggested structure:

```text
LEOS Dev Preview v2 — Master Architecture
LEOS v2 — Provider Runtime
LEOS v2 — Coding Sandbox
LEOS v2 — Memory
LEOS v2 — Capability Store
LEOS v2 — Secret Manager
LEOS v2 — Telemetry
LEOS v2 — Acceptance / Release
```

Each epic should end with a handoff document containing:

- current state;
- decisions;
- modified files;
- tests;
- known issues;
- next steps.

---

# 25. MCP Position

MCP is **not required for LEOS to develop itself** once:

```text
Provider Runtime
+
Coding Sandbox
```

are working.

LEOS can then perform everything locally except cloud model inference.

MCP remains useful as an optional interoperability layer for external clients such as ChatGPT, Claude, IDEs, or other platforms.

Therefore MCP should not block the core Dev Preview v2 roadmap.

Priority:

```text
Provider Runtime
    |
Coding Sandbox
    |
Memory / Capability / Secrets / Telemetry
    |
LEOS Developer
    |
Optional MCP interoperability
```

---

# 26. Local-First / Sovereign Design

LEOS should continue supporting the principle that external cloud intelligence is optional.

A complete deployment should be capable of:

```text
LEOS
 + local chat model
 + local embedding model
 + local OCR
 + local speech
 + local vision
 + local reranker
 + local tools
```

Cloud providers should enhance the system, not define it.

The user should always be able to set:

```text
Cloud providers disabled
```

for employees, projects, capabilities, or the entire installation.

---

# 27. Suggested Dev Preview v2 Epic Order

## Bootstrap Layer

### Epic 1 — Universal Provider Execution Runtime
- execute local providers;
- execute external providers;
- OpenAI integration;
- provider health;
- common request/response normalization;
- provider failure handling.

### Epic 2 — User Model/Provider Ranking and Escalation
- global ranking;
- capability-specific ranking;
- employee ranking;
- job override;
- controlled escalation;
- privacy and budget constraints.

### Epic 3 — Coding Sandbox
- isolated workspaces;
- filesystem capability;
- shell capability;
- Git capability;
- test capability;
- artifacts;
- approval boundaries.

## Core Completion Layer

### Epic 4 — Memory Contract v2
- repair current drift;
- canonical contract;
- memory scopes;
- project memory;
- context retrieval.

### Epic 5 — Capability Store
- capability registry;
- implementation mapping;
- capability installation;
- employee assignment;
- store UI.

### Epic 6 — Secret Manager
- secret references;
- local encrypted storage;
- runtime injection;
- scoped access;
- no logging/memory leakage.

### Epic 7 — Usage and Productivity Telemetry
- tokens;
- API cost;
- latency;
- provider;
- model;
- job;
- success;
- local/cloud ratio;
- production-per-token metrics.

### Epic 8 — Model Management UI
- provider configuration;
- ranking;
- capability mapping;
- model status;
- cost;
- privacy;
- routing visualization.

## Dogfooding Layer

### Epic 9 — LEOS Core Developer Employee
- development employee;
- sandbox integration;
- project memory;
- provider routing;
- capability manifest.

### Epic 10 — LEOS-Develops-LEOS Acceptance
- real defect/feature;
- autonomous local workflow;
- governed escalation;
- tests;
- patch;
- approval;
- measurable token/cost telemetry.

---

# 28. Long-Term Interaction Model

Today:

```text
Brett
  |
ChatGPT
  |
Terminal
  |
LEOS
```

Early v2:

```text
Brett
  |
LEOS
  |
LEOS Developer
  |
Provider Runtime
  +--> local models
  +--> OpenAI
  |
Coding Sandbox
```

Later:

```text
Brett
  |
LEOS Manager
  |
LEOS Developer
  |
specialized employees
  |
capabilities
  |
ranked intelligence providers
  |
governed execution
```

Ultimate experience:

```text
Brett:
"Build this."

LEOS:
plans
delegates
retrieves knowledge
selects intelligence
executes
tests
reviews
learns
requests approval where required
```

---

# 29. Core Product Philosophy Reinforced by This Session

Dev Preview v2 should reinforce the following principles.

## User sovereignty

The user controls:

- provider availability;
- model ranking;
- cloud permission;
- budgets;
- employee permissions;
- approvals;
- data locality.

## Model independence

LEOS is not tied to one model vendor.

## Local-first operation

Cloud intelligence is optional.

## Capability-driven employees

Employees are defined by what they can do, not merely by prompts/personas.

## Governed execution

Real work occurs through controlled capabilities and sandboxes rather than unrestricted model access.

## Persistent organizational memory

Knowledge belongs to LEOS, not to a temporary chat session.

## Efficient intelligence

Use the least expensive/sensitive intelligence capable of completing the task successfully.

## Observable automation

Users should be able to see:

- what model ran;
- why it was selected;
- what context it received;
- what capabilities were invoked;
- what it cost;
- what changed;
- what requires approval.

---

# 30. Proposed Dev Preview v2 Success Statement

A successful LEOS Dev Preview v2 should allow the following statement to be true:

> **LEOS can operate an AI workforce using user-ranked local and cloud intelligence providers, persistent structured memory, installable capabilities, governed local execution environments, and measurable routing/cost policies. LEOS can use these systems to perform and validate real work—including contributing to its own development—without requiring a cloud model for every task.**

---

# 31. Immediate Next Step

Before beginning implementation:

1. freeze/preserve RC11;
2. establish the clean Dev Preview v2 development baseline;
3. perform a focused core audit for existing implementations and contract drift;
4. define the v2 architecture/contracts for Provider Runtime and model ranking;
5. begin **Epic 1 — Universal Provider Execution Runtime**.

The objective is not to bolt OpenAI onto LEOS.

The objective is to create the missing intelligence execution layer that allows **any approved model provider** to participate in LEOS under user-defined policy.

Once that exists, OpenAI becomes one provider in the hierarchy—and LEOS can begin helping build the rest of itself.
