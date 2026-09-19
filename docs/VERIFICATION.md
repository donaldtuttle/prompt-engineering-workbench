# v0.2.0 verification record

Executed 2026-09-19 in the supplied Linux workspace. Status: DEVELOP.
Scope: software behavior and SDK wire construction; no live model or efficacy experiment.

## Results

| Check | Result |
| --- | --- |
| Locked installation | uv sync --locked passed |
| Unit/API/SDK/migration tests | **130 passed**, 1 upstream warning, 14.16 seconds |
| Ruff lint and format check | Passed |
| Node syntax checks (UI and browser script) | Passed |
| Actual Uvicorn startup, database health, shutdown | Passed |
| Playwright 1.51.1 / Chromium 134.0.6998.35 | **24 workflow checks passed** |
| Restored injector original full/scoped pins | Match; working artifact VALID |
| Successor manifest | LF-only, unchanged parsed values, new provenance hash recorded |
| Legacy history | v0.1.0 success/blocked and v0.1.1 QOFT success payloads unchanged after migration |
| Real Agents SDK with mock HTTP transport | Exact wire messages/settings, model/usage capture, retries and failures verified |
| Paid/live OpenAI request | **Not performed** |

The original 80 tests remain with changes for the new three-condition API, async submission,
schema versions, and explicit migration. Fifty additional cases include another legacy fixture,
all delivery/control combinations, SDK transport parametrization, and concurrency/replay cases.
These are actual collected pytest cases, not separate claims of scientific evidence.

Environment: Python 3.12.14; FastAPI 0.141.1; Uvicorn 0.53.0; Pydantic 2.13.5;
openai-agents 0.22.3; openai 3.16.2; tiktoken 0.14.0; pytest 9.1.1;
httpx2 2.13.0; Ruff 0.16.8. uv.lock records the full dependency graph.

## Coverage added

- Exact original context bytes in each delivery slot; deterministic message construction.
- Equal full/control context-token counts in both demo and 80 KB QOFT fixtures.
- Bundled tokenizer construction without network access.
- Replicate indices, preserved sampling settings, initial/final hashes, captured handshake output.
- Final task withheld during preparation; failed task retains successful handshake.
- Replay after current references disappear/change; frozen final hashes and one task call.
- Replay rejection for modified task, prompt, bytes, manifest, settings, request/run mismatch,
  changed SDK versions, active sources, and missing handshake inputs.
- Atomic capacity reservation before threaded preparation; preparation failure releases slots.
- Event-loop responsiveness while persistence is deliberately slowed.
- Cancellation during preparation and initial write; immediate shutdown before execution.
- Actual installed Agent/Runner/client/Responses code using a mock HTTP transport.
  Tests compare outbound message arrays with stored arrays for every delivery mode, check
  sampling parameters/output limits, empty tools, disabled storage/truncation, no previous
  conversation state, exact returned model strings, and missing-usage nulls.
- HTTP error exception-text protection and exactly recorded controller retries.
- Missing-key/cloud-consent/unsupported-seed gates; fresh cloud replay consent.
- Incomplete Responses output is failed by the SDK, not marked successful.
- Explicit migration backups, unknown/unversioned schema rejection, unchanged historical
  experiment payloads and version-correct exports, canonical UTC write validation.
- D7 changes only CRLF pairs; original provenance and reviewer attestation remain distinct.

## Browser checks

The report at browser-report.json records these 24 executed checks:

1. Page render.
2. Three isolated lanes.
3. XSS text escaping.
4. JSON download.
5. JSONL download.
6. History after reload.
7. Reuse setup.
8. Restored QOFT VALID.
9. Restored QOFT three-condition run.
10. QOFT export exact full/scoped hashes.
11. CRLF treatment blocked.
12. Baseline still succeeds.
13. 390-pixel viewport without overflow.
14. Baseline-only run.
15. No JavaScript errors.
16. No external browser requests.
17. Release source bytes unchanged.
18. Two-call handshake transcripts.
19. Replicate indices.
20. Seed settings preserved.
21. Snapshot replay after disk corruption.
22. Replay final hashes match.
23. Replay uses one task call.
24. Invalid neutral control blocked.

The script creates isolated reference copies/databases, explicitly disables cloud execution,
and shuts down its own server. No shipped artifact is corrupted by this test.
Desktop and mobile captures were visually inspected. Screenshots and refreshed mock examples
are under docs/screenshots and docs/examples. Example paths/timestamps describe QA provenance,
not installation requirements. The handshake example is a saved experiment record.

## Commands

```sh
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check workbench/static/app.js
node --check scripts/browser-smoke.cjs
node scripts/browser-smoke.cjs
```

For this workspace, the browser invocation used WORKBENCH_PLAYWRIGHT to point at the separately
installed QA package, PLAYWRIGHT_BROWSERS_PATH for its Chromium cache, and TMPDIR for scratch
browser data. These are QA configuration, not application prerequisites.

## Failures encountered and resolution

- Initial SDK tests failed when lazy tracing setup constructed an unused exporter client whose
  proxy support was unavailable. The application now initializes a disabled trace provider with
  no exporters. No extra network dependency or weakened proxy boundary was introduced.
- Initial returned-model capture wrapped the original client method, but the SDK cloned the
  client when applying retry policy. Transport tests exposed missing metadata. A pinned,
  tested response-fetch hook now captures the model/usage before normalization.
- The first queue test waited for 16 worker threads on an environment with a smaller default
  pool. It now checks all 16 reservations while preparation is blocked, without assuming
  16 simultaneous threads. The rejected seventeenth submission is awaited and inspected.
- Added handshake-failure coverage initially lacked a test import; the import was restored.
- A new incomplete-response test initially expected a returned partial result. Inspection and
  execution confirmed the SDK raises before exposing that result. The test now asserts failure
  and unavailable result, and the adapter documentation records this limitation.
- Initial lint/line-length findings and a duplicated preview label were corrected. Final checks pass.
- One unsuppressed upstream AnyIO BlockingPortal deprecation remains.

## Changes and limits

Models/conditions/controller/repository/API/provider code changed, along with UI, migration CLI,
tests, pinned dependencies, and documentation. The original v1 models are preserved as a legacy
reader. Frozen injector bytes did not change. Manifest line-ending change is separately recorded.

No live OpenAI account/model execution, live tokenizer equivalence, activation scoring, output
quality, efficacy, blind evaluation, cost calculation, streaming UI, Ollama, Windows/macOS,
other browser engines, multi-worker operation, or power-loss/storage-failure guarantee is claimed.
D4 full-payload rewriting remains open before ablations. Replicates are bounded and no
condition-order randomization or statistical analysis is implemented.

Original source attachments and accepted v0.1.x archives are unchanged. Local Git is initialized
with uncommitted changes and no remote. No push, public publication, or deployment was performed.
The source ZIP excludes runtime databases, caches, environments, credentials, and Git internals.
