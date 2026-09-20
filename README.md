# Prompt Engineering Workbench — v0.2.0

A local browser application for running the same probe under isolated baseline,
injector, and length-control conditions, preserving the inputs, and reviewing saved runs.

**Status: DEVELOP.** Offline workflows and the real OpenAI Agents SDK through a mock
HTTP transport are verified. A real OpenAI model has not been called for this release.
Live-account compatibility, model availability, and injector effectiveness remain unverified.

This is a complete source release. Existing users: read [UPGRADE.md](UPGRADE.md) first.

## Three-Lane Probe companion

[Open the original Grok demo](https://cactus-umbra-vivid-lunar.grok.me/) — a public
DEMO-only viewport of the three-condition idea, separate from this local harness.
The [offline protocol reconstruction](examples/three_lane_probe/README.md) reproduces
its message assembly, hashes, delivery modes, and tamper checks without API keys.
**Partial / DEVELOP:** the browser UI and live Grok backend have not been ported.
See [source inspection, tests, and remaining work](docs/THREE_LANE_RECONSTRUCTION.md).

## Run locally

Install Python 3.12+ and uv, extract into a new folder, and open a terminal there:

```sh
uv sync --locked
uv run --locked python -m workbench
```

Open **http://127.0.0.1:8765** on that same computer. Keep the terminal open; Ctrl+C stops
the server. This address is your local computer, not a hosted site or an iPhone preview.
The first dependency installation needs internet access. Mock mode then works offline,
including control construction: tokenizer data is bundled and hash checked.

Load the example, keep **Mock**, choose an artifact, and click **Run experiment**.
A valid artifact creates three lanes per replicate. No artifact creates baseline only.
An invalid artifact blocks both context-dependent lanes while baseline can still run.

## New in v0.2.0

- Run/export schema v2; old v1 records retain their shape and snapshots after explicit database migration.
- BASELINE, FULL_INJECTOR, and NEUTRAL_LENGTH_CONTROL, with exact context-token matching
  in a bundled o200k_base tokenizer. The QOFT context is 14,224 tokens in that tokenizer.
- SYSTEM_SLOT, USER_PASTE, and USER_PASTE_WITH_HANDSHAKE delivery; actual handshake output
  and subsequent task input are retained. A captured handshake is not a conformance score.
- One to four replicates, zero-based replicate indices, temperature, top-p, seed support
  information, output-token limits, requested model, returned model string, and SDK versions.
- **Replay snapshot** reuses stored final messages and asserts their hashes. **Reuse setup**
  loads current files and constructs a new experiment.
- Worker-thread file/database I/O, atomic queue reservation, ordered persistence, and
  cancellation handling for both submission and execution.
- One tool-free OpenAI Agents SDK adapter with explicit cloud selection and server-side credentials.
- LF-only successor manifest, new manifest hash, and separately attributed reviewer attestation.
  Injector hashes are unchanged.

See [protocol details](docs/PROTOCOL.md), [decisions](docs/DECISIONS.md),
[verification](docs/VERIFICATION.md), and [review checklist](docs/REVIEW_CHECKLIST.md).

## Optional OpenAI execution

Mock remains the default. To enable cloud selection, set **both** environment variables in
the server's environment:

| Variable | Meaning |
| --- | --- |
| `WORKBENCH_ENABLE_OPENAI` | Set to `1` to allow the cloud adapter |
| `OPENAI_API_KEY` | Your API credential; never enter it into the probe, browser, source, or export |
| `WORKBENCH_DB` | Optional database path; default `data/workbench.sqlite3` |
| `WORKBENCH_PORT` | Optional loopback port; default `8765` |

The included `.env.example` contains names only; the app does not automatically read .env files.

For example, in Bash, enter a key without echoing it or putting its value in shell history:

```sh
read -r -s -p "OpenAI API key: " OPENAI_API_KEY
export OPENAI_API_KEY
export WORKBENCH_ENABLE_OPENAI=1
uv run --locked python -m workbench
```

Choose **OpenAI**, enter an explicit model or snapshot ID available to your account, and
check the cloud consent box. The app supplies no default cloud model. Start with the small
demo fixture and one replicate. The interface shows planned call count before retries.
Handshake delivery makes two calls per lane; each retry repeats the lane's protocol.
Cloud replay requires a fresh confirmation.

Temperature/top-p left blank are omitted from the provider request. Model-specific unsupported
settings cause a recorded failure; the adapter never silently changes them or substitutes a
different model. Responses seed is unsupported by this adapter and a non-null seed is rejected.
Mock seed is a recorded fixture input, not stochastic model evidence.

SDK traces/exporters are disabled, response storage is requested off, tools/handoffs are empty,
and truncation is disabled. Each successful response captures the returned model string and
provider-reported usage where present. A returned alias is not proof of an immutable model
snapshot. Cost and trace ID remain null. Errors retain exception type, not raw exception text.
See [provider implementation notes and official references](docs/OPENAI_ADAPTER.md).

## Reading results

Each lane shows its condition, replicate, provider, status, requested/returned model,
response, and final prompt hash. Handshake output is expandable. Export JSON/JSONL preserves
the complete input snapshots, settings, phase-call records, and results.

The comparison is **unblinded**. Evaluation remains null and resolution remains
INSUFFICIENT_EVIDENCE. No screenshot or human impression from this view is a scored outcome.
Token-length matching controls one difference; it does not make repeated text semantically
inert or establish that the chosen tokenizer equals the provider's tokenizer.

## Verify the release

```sh
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Optional browser QA, separate from application dependencies:

```sh
npm install --no-save --package-lock=false playwright@1.51.1
npx playwright install chromium --only-shell
node scripts/browser-smoke.cjs
```

Linux needs a Chromium-compatible system runtime. The script owns port 8765 temporarily
and uses isolated databases/reference copies under test-results. Stop your normal server first.
No paid model call is part of the test suite or browser smoke script.

## Data and limits

- Run one server process/worker per database. No cloud hosting, account system, or tunnel.
- Prompts, outputs, snapshots, and credentials in your own environment require your normal
  local access protections. Database/exports are plaintext.
- Stop the app before copying its entire data folder; preserve accompanying SQLite WAL/SHM files.
- Startup marks unfinished lanes INTERRUPTED and never silently resubmits them.
- History displays the newest 100 entries; older records remain retrievable by ID.
- At most 16 admitted experiments, four globally active lanes, four replicates, and 12 lanes
  per experiment. Timeouts cover a whole lane attempt, including both handshake/task phases.
- Full experiment payloads are still saved on transitions. Artifact deduplication/per-run
  storage (D4) remains required before ablation matrices.
- No blind audit, score aggregation, provider streaming UI, Ollama adapter, or efficacy claim.
- Windows/macOS and browsers other than the tested Linux Chromium run remain unverified.

Project architecture remains FastAPI → controller → provider boundary → SQLite → JSON/JSONL,
with plain HTML/CSS/JavaScript and no frontend build chain.
