# Prompt Engineering Workbench

## Product Definition

Prompt Engineering Workbench is a local application for controlled
experimentation with prompts, injectors, models, auditors, and agent
workflows.

It converts a manual copy-and-paste process into a reproducible
engineering pipeline.

The application is intended to feel more like a professional production
tool or render queue than a conventional chat interface.

## Problem

Current prompt and agent development commonly relies on:

- manually copying text between models
- inconsistent settings
- unrecorded prompt changes
- subjective comparisons
- screenshots instead of structured records
- evaluators that know which answer is the treatment
- lost model, token, cost, and latency details
- uncontrolled model discussions
- no reliable regression history

This makes it difficult to determine whether a prompt or injector
actually improves measurable behavior.

## Core Product Workflow

The intended user workflow is:

1. Create or open a workbench project.
2. Enter a task or select a saved probe.
3. Select an injector or choose no injector.
4. Select experimental conditions.
5. Select models and providers.
6. Review the run matrix.
7. Review concurrency and budget limits.
8. Run independent lanes.
9. Preserve every raw result.
10. Blind condition identities for the auditor.
11. Run structured evaluation.
12. Reveal condition identities.
13. Compare behavior, cost, tokens, and latency.
14. Mark the outcome resolved, partially resolved, unresolved, or
    insufficient evidence.
15. Export the experiment.
16. Reuse the experiment as a regression test.

## First Scientific Target

The first defensible experimental question is:

Does the full injector change measurable model behavior on designed
probes relative to a baseline condition?

The first version does not attempt to prove that the injector changes
hidden internal reasoning.

## Version 0.1 Product Scope

Version 0.1 is a local browser application.

Required capabilities:

- localhost application
- task or probe editor
- injector file loader
- exact injector hashing
- baseline condition
- injected condition
- isolated run records
- bounded concurrency
- response panels
- SQLite storage
- experiment history
- JSON or JSONL export
- offline mock or fixture mode
- health endpoint
- basic automated tests

OpenAI and Ollama integrations are planned, but the app must first work
without credentials.

## Intended Architecture

```text
Browser UI
    ↓
FastAPI application
    ↓
Experiment Controller
    ├── Condition Builder
    ├── Provider Adapters
    ├── Concurrency Controller
    ├── Blind Auditor
    ├── Results Normalizer
    ├── SQLite Repository
    └── Export Manager

Provider boundary:

ProviderAdapter
    ├── MockProvider
    ├── OpenAIProvider
    ├── OllamaProvider
    └── Future providers

The OpenAI provider will use the OpenAI Agents SDK.

Other providers may use their native APIs or compatible local endpoints,
but their results must be normalized into the same internal run record.

Experimental Conditions

Initial required conditions:

BASELINE
Task only

FULL_INJECTOR
Exact injector plus task

Later conditions:

NEUTRAL_LENGTH_CONTROL
MINIMAL_INJECTOR
SECTION_ABLATION
COMPRESSED_INJECTOR

Condition construction must be deterministic and covered by tests.

Audit Workflow

The initial auditor should receive anonymized results:

Response A
Response B

The auditor must not know which response came from the baseline or
injector condition until after scoring.

Initial evaluation fields may include:

task correctness
scope control
unsupported claims
type or category errors
evidence discrimination
uncertainty handling
instruction compliance
confidence calibration when confidence tags are present

Scores and defects must be stored separately from raw responses.

Coordination Workflow

Multi-model coordination is a later mode.

When added, it will use:

Independent answers
    ↓
Blind audits
    ↓
Controlled exchange
    ↓
Final synthesis

Models must not simply talk until they agree.

Coordination must have:

maximum rounds
speaking order
visibility rules
stopping conditions
cost limit
timeout
unresolved outcome support
Data Integrity

Every immutable injector or prompt artifact should be identified by
SHA-256.

Every run should preserve enough information to reproduce or explain the
condition.

Unavailable provider data must be represented honestly rather than
estimated.

Privacy

The app runs locally.

Local prompts and results remain local unless the user selects a cloud
provider.

Cloud and local lanes must be visually distinguishable.

No API key may be stored in the repository or experiment export.

Initial User Interface

The first interface should prioritize function over visual polish.

Suggested layout:

Task / Probe
Injector
Conditions
Models
Run Controls

Run Queue
Response Comparison
Audit Result
Experiment Details
Export

The final visual direction may borrow from professional rendering,
animation, node, or CAD applications.

Development Phases
Phase 0: Project Foundation
governance files
Git
Python project
local server
health endpoint
test configuration
offline provider fixture
Phase 1: Offline Vertical Slice
task input
injector loading
SHA-256
baseline and injected conditions
concurrent fixture runs
SQLite records
result comparison
export
Phase 2: OpenAI Agents SDK
credential-safe configuration
one focused OpenAI agent
live OpenAI run
streaming where practical
usage and tracing capture
graceful missing-key state
Phase 3: Ollama and Concurrency
Ollama discovery
local model selection
cloud and local lanes
bounded concurrency
timeouts and retries
Phase 4: Blind Audit
anonymized responses
structured evaluator output
identity reveal
aggregate comparison
Phase 5: Controlled Coordination
proposer
counter-auditor
evidence auditor
coordinator
explicit termination rules
Phase 6: Advanced Experiments
section ablation
neutral-length controls
confidence calibration
regression suites
prompt compression research
Version 0.1 Non-Goals

Version 0.1 will not include:

public hosting
public plugin submission
GPT Store publication
user accounts
cloud database
payment system
Electron
desktop installer
unrestricted multi-agent conversation
complete ΞΣΩ simulation integration
scientific validation claims
Version 0.1 Success Criteria

The milestone succeeds when a user can:

Start the app locally.
Open it in a browser.
Enter a task.
load an injector file.
Run baseline and injected fixture conditions.
See separate results.
Confirm the stored injector hash.
Reopen the experiment from SQLite.
Export the record.
Run the automated tests successfully.