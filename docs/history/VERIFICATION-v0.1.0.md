# v0.1.0 verification record

Executed 2026-09-19 in the supplied Linux workspace. This is a software verification
record; the status remains DEVELOP. Confidence for the executed checks: ρ̂_conf_HIGH.

## Results

| Check | Result |
| --- | --- |
| `uv sync` | Installed locked dependencies in a local virtual environment |
| `uv run --locked pytest -q` | **48 passed**, 2 dependency deprecation warnings, 2.97 seconds |
| `uv run --locked ruff check .` | Passed |
| `uv run --locked ruff format --check .` | Passed |
| `node --check workbench/static/app.js` | Passed |
| `node --check scripts/browser-smoke.cjs` | Passed |
| Actual Uvicorn server startup and `/health` | HTTP 200; database check passed |
| Browser smoke, Chromium 134.0.6998.35 / Playwright 1.51.1 | **13 workflow checks passed** |
| Browser shutdown / server SIGINT | Uvicorn logged application shutdown complete |
| Supplied QOFT injector verification | Correctly INVALID, treatment BLOCKED |
| Demo fixture verification | VALID; baseline/treatment software runs completed |

## Unit/API coverage

Frozen expected hashes, byte-preserving source loads, source mismatch rejection, valid
and invalid scoped hashes, deterministic message assembly, exact API task whitespace,
schema/input limits, baseline-only and paired runs, null unavailable provider values,
JSON/JSONL round-trips, SQLite reload, interrupted-run recovery, per-lane persistence,
timeouts/retries, failed-lane isolation, global concurrency across experiments, cancellation,
artifact snapshot isolation from later disk edits, traversal/symlink rejection, malformed
manifests, invalid UTF-8/BOM/tampered/oversize bytes, local Host/origin protection, request
body limits, unknown IDs, disabled providers, deterministic mock output, queue admission,
and database schema-version guard.

## Actual browser workflow

1. Render desktop workspace at 1440 × 1100.
2. Run both isolated lanes with the demo fixture.
3. Render literal script markup as inert task/output text (XSS test).
4. Download JSON and verify exact submitted task plus artifact identity.
5. Download JSONL and parse one experiment on one line.
6. Reload the page and reopen the same saved experiment from history.
7. Reuse the stored setup and verify exact editor content.
8. Select the supplied QOFT artifact and verify treatment BLOCKED.
9. Verify the baseline still succeeds, with experiment status PARTIAL.
10. Render a 390 × 844 viewport and assert no horizontal overflow.
11. Run baseline-only mode and verify exactly one result lane.
12. Assert no page JavaScript errors.
13. Assert no external browser page requests.

The health check and server run occur inside the smoke script's subprocess lifecycle.
The UI screenshots were visually inspected. Full-page captures are provided under
`docs/screenshots/`; a generated fixture export is under `docs/examples/`.

## Environment and commands

Python 3.12.14; FastAPI 0.141.1; Uvicorn 0.53.0; Pydantic 2.13.5;
pytest 9.1.1; httpx 0.28.1; Ruff 0.16.8. `uv.lock` records all exact dependencies.

```sh
uv sync
uv run --locked ruff format .
uv run --locked ruff check .
uv run --locked pytest -q
uv run --locked ruff format --check .
node --check workbench/static/app.js
node --check scripts/browser-smoke.cjs
node scripts/browser-smoke.cjs
```

For this workspace's browser invocation, `WORKBENCH_PLAYWRIGHT` pointed at its separately
installed Playwright package, `PLAYWRIGHT_BROWSERS_PATH` at the downloaded QA browser cache,
and `TMPDIR` at a scratch QA directory. These are test-environment settings, not required
application configuration. The smoke script supplies its own test database path.

## Failures encountered and disposition

- Initial lint pass found overlong Python lines: formatting and a shorter local filename
  variable resolved them; final lint/format checks passed.
- The preinstalled newer Playwright package could not obtain its browser from the CDN.
  A QA-only pinned Playwright 1.51.1 installation downloaded Chromium using its advertised
  fallback endpoint. This does not change application dependencies.
- An initial browser wait used a function evaluation incompatible with the restrictive CSP.
  The test now waits on rendered status elements. The application's CSP was not weakened.
- Two upstream test-client deprecations remain (httpx integration and AnyIO's BlockingPortal
  alias). They do not fail the tests; warnings were not suppressed.
- Frozen QOFT checks still fail, intentionally and visibly. No repair or canonical promotion.

## Unverified / deliberately absent

Live OpenAI/Ollama execution, API credentials, API token/cost capture, model quality,
injector effectiveness, activation handshake behavior, blinded auditing, scoring,
multi-agent coordination, cross-platform browser/OS behavior beyond this Linux Chromium
run, multi-worker service operation, hostile-local-user security, and scientific validity.

The software tests do not constitute a behavioral experiment on an LLM. The next
discriminating step is an authorized resolution of the frozen injector and a separately
specified live-provider milestone before any baseline/treatment efficacy trial.

## Source-control state at handoff

Local Git initialized on `main`. New implementation/documentation/reference files are
uncommitted. No remote configured, no push, no publication, and no original attachment
was changed. Runtime databases, caches, credentials, and QA environments are excluded
from the deliverable. The ZIP includes the source, lockfile, tests, docs, and frozen copies.

