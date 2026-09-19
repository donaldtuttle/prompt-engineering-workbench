# v0.1.1 verification record

Executed 2026-09-19 in the supplied Linux workspace. This is a software verification
record; status remains DEVELOP. Confidence for the executed checks: ρ̂_conf_HIGH.
No live model was called and no injector-effectiveness claim follows from these checks.

## Results

| Check | Result |
| --- | --- |
| `uv lock`, `uv sync --locked` | Passed; Pydantic explicitly declared; all third-party locked versions unchanged |
| `uv run --locked pytest -q` | **80 passed**, 2 upstream deprecation warnings, 3.19 seconds |
| `uv run --locked ruff check .` | Passed |
| `uv run --locked ruff format --check .` | Passed |
| `node --check workbench/static/app.js` | Passed |
| `node --check scripts/browser-smoke.cjs` | Passed |
| Actual Uvicorn startup and `/health` | HTTP 200, version 0.1.1, database check passed |
| Chromium 134.0.6998.35 / Playwright 1.51.1 | **17 workflow checks passed** |
| Server SIGINT shutdown | Application shutdown completed |
| Restored QOFT injector | VALID, 80,140 bytes, original full-file and scoped hashes match |
| Preserved CRLF input in isolated test copy | INVALID; treatment BLOCKED; baseline still SUCCEEDED |
| v0.1.0 successful and blocked history | API/export values and raw SQLite payload unchanged after opening in v0.1.1 |
| Explicit restoration utility | Passed; rerun idempotent; original source and manifest retained |
| JavaScript errors / external browser requests | None observed during smoke workflow |

The machine-readable browser result is [browser-report.json](browser-report.json).
See [INTEGRITY_REPORT.md](INTEGRITY_REPORT.md) for exact before/after hashes and
[restoration-provenance.json](restoration-provenance.json) for the restoration record.

## Unit/API coverage

All original 48 tests remain, with negative QOFT cases using the preserved CRLF fixture
instead of the now-restored working artifact. Coverage includes source/scoped hash
validation, byte-preserving snapshots, deterministic prompt assembly, exact task whitespace,
schema/input limits, baseline-only and paired runs, null unavailable provider values,
JSON/JSONL exports, SQLite reload, interrupted-run recovery, independent lane persistence,
timeouts/retries, failed-lane isolation, global concurrency, cancellation, snapshot isolation,
path/symlink rejection, malformed manifests, invalid UTF-8/BOM/tampered/oversize inputs,
Host/origin protection, body limits, disabled providers, mock determinism, queue admission,
and the database schema-version guard.

The 32 added cases cover restored QOFT validity against fixed original pins; untouched
source/manifest hashes; exact successor metadata and provenance; restoration refusal on
unreviewed input or changed pins; generic LF/CRLF policy independently of artifact names
and content hashes; malformed policy/schema rejection; legacy manifests; direct Pydantic
declaration and lock consistency; old successful and blocked record preservation; and
a restored-QOFT API/export round trip.

Upgrade tests construct a schema-1 SQLite database directly from immutable v0.1.0 exports.
They do not generate old records through the new repository implementation. Both API/export
JSON equality and unchanged serialized database payload are asserted. Old BLOCKED treatments
remain BLOCKED; they are not relabeled by restoring the current disk artifact.

## Actual browser workflow

1. Render the desktop workspace at 1440 × 1100.
2. Run both isolated lanes with the demo fixture.
3. Render script markup as inert task/output text.
4. Download JSON and verify the task and artifact.
5. Download and parse JSONL.
6. Reload and reopen saved history.
7. Reuse setup and verify the editor contents.
8. Select the restored QOFT artifact and verify VALID.
9. Complete both restored-QOFT mock lanes.
10. Download QOFT JSON and verify exact full-file and scoped hashes.
11. Replace only an isolated QA copy with the preserved CRLF input and verify treatment BLOCKED.
12. Verify the baseline still succeeds in that partial experiment.
13. Render at 390 × 844 and assert no horizontal overflow.
14. Run baseline-only mode.
15. Assert no page JavaScript errors.
16. Assert no external browser requests.
17. Assert the shipped reference bytes were not changed by the workflow.

The script starts and stops its own server, using a temporary database and copied references
under `test-results/run-*/`. Fresh captures are in `docs/screenshots/`; the restored-QOFT
desktop and mobile captures were visually inspected. Example downloads are in
`docs/examples/`. These are deterministic mock records, not observed language-model answers.
Paths inside example exports/report identify the QA run's local copies, not required
installation paths. Temporary databases, browser caches, and runtime logs are not shipped.

## Environment and reproduction

Python 3.12.14; FastAPI 0.141.1; Uvicorn 0.53.0; Pydantic 2.13.5;
pytest 9.1.1; httpx 0.28.1; Ruff 0.16.8. The lockfile records exact versions.

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest -q
uv run --locked ruff format --check .
node --check workbench/static/app.js
node --check scripts/browser-smoke.cjs
node scripts/browser-smoke.cjs
```

For this workspace's browser run, `WORKBENCH_PLAYWRIGHT` pointed to the separate Playwright
1.51.1 QA package, `PLAYWRIGHT_BROWSERS_PATH` to the Chromium cache, and `TMPDIR` to a scratch
QA directory. These are QA environment settings, not application requirements. See the
README for optional browser-tool installation. The restoration utility is release tooling,
not a normal installation step, and is never called by the runtime loader.

## Failures encountered and disposition

- Two new upgrade tests initially compared a Python-mode tuple with a JSON-mode list.
  API/export equality and raw database payload preservation already passed. Changing the
  final comparison to `model_dump(mode="json")` resolved the test representation mismatch;
  no production migration or repository behavior changed.
- Two upstream test-client warnings remain: the Starlette/httpx integration deprecation
  and AnyIO BlockingPortal alias deprecation. Warnings were not suppressed.
- CRLF rejection is an intentional negative test, not a remaining release-integrity defect.
  The shipped working QOFT pair is VALID.
- Historical v0.1.0 verification and its earlier failures are retained separately under
  `docs/history/`; they are not the current release result.

## Changed-file summary

- Runtime: generic manifest line-ending/schema validation; version and UI copy updates.
- Packaging: direct Pydantic dependency, refreshed lock metadata, reference/fixture byte protection.
- References: restored LF working input, original rejected CRLF and manifest preserved,
  versioned successor manifest with unchanged injector pins.
- Tests/tooling: release-restoration utility, 32 new cases, immutable legacy exports,
  isolated-reference browser smoke and additional QOFT/export checks.
- Documentation: README, upgrade guide, changelog, decisions/workflow, provenance,
  integrity/verification reports, fresh screenshots and example exports.

The controller, repository, models, API routing/security, and provider implementation files
are byte-identical to v0.1.0. Database schema remains 1; experiment/export schemas remain v1.
The artifact-manifest v2 label does not mean an experiment-schema migration.

## Unverified / deliberately deferred

Windows/macOS execution, browsers other than this Linux Chromium run, live OpenAI/Ollama
execution, credentials, model settings/replicates, token/cost capture, model quality,
injector effectiveness, handshake delivery, length controls, snapshot replay, blinded
auditing, scoring, multi-agent coordination, multi-worker operation, hostile-local-user
security, and scientific validity remain unverified or unimplemented.

Review items D3/D5 (blocking I/O and atomic queue admission), D4 (artifact deduplication),
and Phase 2 experimental-design gates remain open. UTC timestamp consistency remains
an invariant, not a redesigned persistence format. Do not use this offline milestone as
evidence that any model treatment works.

## Source-control and delivery state

Local Git initialized on main; changes are uncommitted. No remote, push, or public
publication. Original attachments and the v0.1.0 release were not changed. The replacement
ZIP contains complete source, lockfile, tests, documentation, and reference/provenance
copies; it excludes environments, caches, databases, credentials, and Git internals.
