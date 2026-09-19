\# AGENTS.md



\## Project Identity



Project name: Prompt Engineering Workbench



The project is a local, browser-based Python application for designing,

running, auditing, comparing, storing, and exporting controlled LLM

experiments.



The initial product is an engineering workbench, not a QOFT proof,

consciousness claim, hosted SaaS product, GPT Store listing, or public

ChatGPT plugin.



\## Current Milestone



Build a small, verified local vertical slice before expanding the system.



The first milestone must demonstrate:



1\. A local browser interface.

2\. A task or probe editor.

3\. Exact loading of an injector file.

4\. Baseline and injected conditions.

5\. Isolated experiment runs.

6\. Structured run records.

7\. SQLite persistence.

8\. A usable comparison view.

9\. JSON or JSONL export.

10\. An offline fixture or mock mode that requires no API key.



Do not attempt the complete multi-provider, multi-agent product in one

development pass.



\## Authority Order



When instructions conflict, use this order:



1\. The user's latest explicit instruction.

2\. This AGENTS.md.

3\. PROJECT\_BRIEF.md.

4\. docs/DECISIONS.md.

5\. Current tests and verified behavior.

6\. Exact reference artifacts.

7\. Historical conversations and exploratory notes.



For a frozen artifact, the actual file bytes outrank any paraphrase of

that artifact.



Report conflicts instead of silently choosing a convenient interpretation.



\## User Collaboration



The user is a highly experienced 3D artist and production-pipeline

designer.



Use clear, concrete explanations.



When reporting work, explain:



\- what changed

\- where it changed

\- why it changed

\- what was tested

\- what failed

\- what remains unverified

\- the exact command or click path for review



Avoid unnecessary computer-science jargon.



Use spatial, pipeline, node, rendering, queue, layer, and pass analogies

when they improve understanding.



Do not use the user's lack of formal software-engineering training as a

reason to simplify functionality or make decisions without explanation.



\## Preservation Rules



Never silently rewrite, normalize, compress, reformat, or correct:



\- frozen injectors

\- experiment prompts

\- probe wording

\- intentional redundancy

\- glyphs

\- QOFT terminology

\- formulas

\- thresholds

\- schema field names

\- output labels

\- test fixtures designated immutable



Read frozen artifacts as bytes when computing hashes.



Do not change line endings or encoding in immutable source artifacts.



When copying an immutable artifact into an experiment record, record:



\- source path

\- byte length

\- SHA-256

\- encoding when known

\- load timestamp

\- experiment condition



Do not treat historical QOFT or ΞΣΩ claims as experimentally validated

merely because they appear in a document.



\## Experimental Integrity



The primary first-stage hypothesis is behavioral:



Does the injector change measurable model behavior on designed probes?



Do not claim that observed output differences prove changes in hidden

reasoning computation.



Use controlled experimental conditions.



At minimum, support:



\- baseline: task without injector

\- treatment: task with full injector



Later conditions may include:



\- neutral length control

\- compressed injector

\- section ablation

\- model comparison

\- repeated trials



Keep condition assembly deterministic and testable.



Independent model responses must be captured before models see one

another's responses.



Evaluation order:



1\. Independent generation.

2\. Blind auditing.

3\. Identity reveal.

4\. Controlled coordination when requested.

5\. Final synthesis or unresolved report.



Do not force agreement.



Supported resolution states:



\- RESOLVED

\- PARTIALLY\_RESOLVED

\- UNRESOLVED

\- INSUFFICIENT\_EVIDENCE



Illustrative scores from planning documents are not experiment results.



\## Technical Defaults



Preferred language: Python.



Preferred package manager: uv.



Preferred local architecture:



\- FastAPI backend

\- simple server-rendered browser UI or minimal JavaScript

\- SQLite persistence

\- asyncio-based orchestration

\- explicit provider adapters

\- typed internal schemas

\- pytest tests



Use the OpenAI Agents SDK for the OpenAI agent path.



Start with one focused agent and add specialists only after the single

agent path works.



Use a provider-neutral application boundary so non-OpenAI providers do

not leak provider-specific structures into experiment records.



Suggested provider boundary:



\- MockProvider

\- OpenAIProvider

\- OllamaProvider

\- future provider adapters



Do not create a large frontend build system during the first milestone.



Do not add React, Electron, Docker, Redis, PostgreSQL, Celery, Kubernetes,

or cloud infrastructure unless the user explicitly approves the change

after a demonstrated need.



\## Application Boundaries



Everything should run locally by default.



The browser interface should bind to localhost unless the user explicitly

requests network access.



No prompt, injector, result, or trace leaves the machine except when the

user chooses a cloud model provider.



The application must clearly label:



\- local execution

\- cloud execution

\- estimated or actual cost

\- provider

\- model

\- missing credentials

\- failed requests

\- retries



A missing API key must disable the affected provider gracefully. It must

not prevent the application from starting.



\## Secrets and Credentials



Never request that an API key be pasted into a prompt, source file, issue,

README, test fixture, or committed configuration file.



Use environment variables or an approved local secret mechanism.



Create `.env.example` with variable names only.



Ensure `.env` is ignored by Git.



Never print, log, summarize, export, or commit secret values.



Likely variables include:



\- OPENAI\_API\_KEY

\- OLLAMA\_BASE\_URL



Add other provider variables only when the corresponding provider is

implemented.



\## Data and Tracing



Every primary run should be able to record:



\- experiment ID

\- probe ID

\- condition ID

\- provider

\- model

\- model settings

\- injector path

\- injector SHA-256

\- prompt hash

\- start timestamp

\- end timestamp

\- latency

\- status

\- raw response

\- structured response when available

\- token usage when available

\- cost when available

\- errors

\- retries

\- trace ID when available



Do not invent unavailable token, cost, trace, or confidence values.



Use null or an explicit unavailable state.



Keep raw model output separate from evaluator interpretation.



\## Concurrency



Use bounded concurrency.



Do not launch unbounded API or local-model jobs.



Use separate limits for:



\- cloud model runs

\- local model runs

\- auditor runs



Make timeout, retry, and concurrency limits configurable.



A failed lane must not corrupt successful lanes.



Preserve partial experiment results.



\## Development Process



Before significant implementation:



1\. Read AGENTS.md.

2\. Read PROJECT\_BRIEF.md.

3\. Inspect docs/DECISIONS.md.

4\. Inspect relevant reference artifacts.

5\. Inspect the current Git status.

6\. State the current milestone.

7\. Produce a focused implementation plan.



Work in small vertical slices.



Do not rewrite unrelated code.



Do not change behavior merely to make code look cleaner.



Add or update tests with behavior changes.



After implementation:



1\. Run tests.

2\. Run lint or static checks configured by the repository.

3\. Start the application.

4\. Verify the health endpoint.

5\. Verify the affected browser workflow.

6\. Report exact commands and results.

7\. Report unverified behavior honestly.

8\. Show the changed-file summary.



Do not claim success from code inspection alone when the behavior can be

run and checked.



\## Git Rules



Initialize Git if the directory is not already a repository.



Do not push to a remote without explicit permission.



Do not publish the injector or private QOFT material.



Keep generated runtime data, secrets, caches, local databases, and logs

out of source control unless a specific fixture is intentionally added.



Prefer small commits aligned to verified milestones.



Do not rewrite Git history without explicit permission.



\## Documentation



Maintain:



\- README.md for setup and use

\- PROJECT\_BRIEF.md for product scope

\- docs/DECISIONS.md for accepted decisions

\- docs/PRODUCT\_WORKFLOW.md for the user workflow

\- tests for executable expectations



Historical conversation files are provenance only.



Do not use historical conversation text as authority when a current

specification exists.



\## Out of Scope for the First Milestone



Do not build these yet:



\- four-agent ΞΣΩ simulation mode

\- uncontrolled model debate

\- Claude or Gemini provider integration

\- public hosting

\- user accounts

\- team collaboration

\- GPT Store publication

\- ChatGPT plugin submission

\- desktop EXE packaging

\- Electron shell

\- billing

\- automatic patent claims

\- complete injector compression

\- complete ablation search

\- automatic prompt optimization



Create extension points where appropriate, but do not implement these

features prematurely.



\## Novelty Flags



When a milestone reveals a potentially distinctive method, report it

separately as one of:



\- Productizable Engineering Pattern

\- Publishable Experimental Method Candidate

\- Patent-Screen Candidate



Do not state that something is novel, patentable, validated, or proven

without the required search, comparison, or experiment.

