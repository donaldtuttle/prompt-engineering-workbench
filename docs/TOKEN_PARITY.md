# Provider token parity

Status: implementation checks, not an efficacy result. Added after v0.2.0; no release
tag, historical example, reference artifact, or completed experiment is rewritten.

The neutral control still uses `repeated-stone-v1` and the pinned `o200k_base` data.
Its construction metadata describes that tokenizer only. Before a new artifact experiment
generates any responses, the controller measures the injector and the saved control using
the selected provider's count-only path. It never shortens the injector, changes the
control, or calls a generation endpoint to discover a token count.

## What is measured

Each replicate receives a `provider-token-parity-v1` entry in `experiment.token_parity`.
Two comparisons are recorded independently:

1. **Context:** the complete injector versus the complete control. For Claude this is an
   estimate using identical isolated user-message wrappers, not a raw-text token count.
2. **Assembled input:** each lane's initial input, including the task or shared readiness
   prompt, under the formatting method listed below. On replay it is the frozen final input.

| Provider | Context count | Assembled-input count | Limit |
| --- | --- | --- | --- |
| Mock | Bundled `o200k_base` | Sum of separately encoded message texts | Fixture only; no model tokenizer verified |
| OpenAI | Bundled `o200k_base`, after checking the installed tiktoken model mapping | Sum of separately encoded message texts | Only `gpt-4o`, `gpt-4.1`, and dated snapshot forms accepted; provider framing excluded |
| Grok | xAI `tokenize_text(text, model=...)` | Same endpoint on `role + newline + content`, messages joined by newline | Role-labeled text is not xAI's chat template; hidden overhead excluded |
| Claude | `messages.count_tokens` on one user message containing the exact context | Same endpoint on `_adapt_claude_messages`, including the real system field and adjacent-turn joining | Provider estimate, including formatting and possible system-added tokens; not exact billing |
| Ollama | Optional local `/api/tokenize` | Same endpoint on message contents joined by newline | No standard endpoint availability assumed; model template and tokenizer revision unverified |

The xAI response reader accepts the installed SDK's protobuf repeated token sequence as
well as test sequences. It rejects malformed values. An absent Ollama tokenizer (404/405)
is `UNSUPPORTED`. It does not fall back to OpenAI tokens or call `/api/chat` to measure parity.
An unknown OpenAI mapping is also `UNSUPPORTED`, never an inferred match.

Cloud counting retains existing provider selection, consent, credential, and endpoint
boundaries. Tokenization transmits the selected text to that provider. Tests use synthetic
transports only. No live tokenization or paid generation was used to validate this change.

## Gate and evidence

Each comparison is `MATCHED`, `MISMATCHED`, `UNSUPPORTED`, or `ERROR`.
`MATCHED` means equal nonnegative integer counts from the same recorded method, scope,
and tokenizer identity. Equality is not inferred from bytes, character length, context-window
fit, an empty-injector baseline, or generation usage.

Both comparisons must match before context lanes generate. Otherwise both context lanes
are `BLOCKED`, diagnostics and available counts are saved, and baseline remains runnable.
The saved control is intentionally not regenerated to force a pass. Revising a comparator
requires a separately declared construction method and new inputs.

Evidence records provider, requested model, timestamp, replicate and run IDs, context hashes,
assembled prompt hashes, four measurements, method/scope, and tokenizer identity. Local
counts include the tokenizer data SHA-256 and tiktoken version. Each run already records
provider SDK versions. Remote tokenizer revision/hash remains null when unavailable; a
requested model alias is not a pinned backend identity.

Each `payload_sha256` hashes compact UTF-8 JSON (`ensure_ascii=False`) of the exact count
argument: a list of separately encoded texts for local tiktoken, a string for Grok/Ollama,
or the adapted model/messages/system object for Claude. The original condition snapshots
retain the text needed to reconstruct it. No secret or raw provider error text is added.

Counts are cached only within one experiment, keyed by exact messages and measurement scope.
Identical replicates can reuse a measurement; different inputs or a replay are recounted.
The shared global limiter bounds preflight work. One timeout covers a pair's four checks,
with no automatic count retries. Available partial counts survive timeout or failure.
Generation retries retain the preflight evidence and existing per-call usage records.

## Handshake and replay

For new handshake runs, the gate covers the initial context/readiness messages. Generated
assistant replies are not constrained to equal lengths, so subsequent task inputs can differ.

Replay retains the exact stored final messages and recomputes measurement evidence under
new run IDs. Frozen handshake replay requires matched context counts and readable assembled
counts; a measured assembled-input mismatch is allowed because it preserves the differing
original replies. `input_status` still reports that mismatch and `input_phase` is
`FROZEN_FINAL_PROMPT`. Errors or unsupported assembled counts still block. This exception
does not assert matched final inputs. Previously blocked lanes remain blocked on replay.

## Reading records and evidence limits

The comparison cards show both count pairs and statuses. Expand **Token measurement method
and limits**, or inspect `token_parity` in JSON/JSONL exports. Older v2 records lacking this
optional field read as null and display "not measured". No parity is backfilled and no
terminal database payload is changed. Legacy v1 remains unchanged. No schema or release
version is bumped; the additive evidence has its own version.

`total_provider_input_parity` is always `NOT_ESTABLISHED`: text equality cannot certify hidden
chat framing; a count API estimate cannot certify exact generation usage. Generation usage
and context-window gates remain separate. Server tokenization and model aliases can change.
`semantic_neutrality` remains `NOT_ESTABLISHED`. Evaluation stays null and resolution stays
`INSUFFICIENT_EVIDENCE`. Token parity alone establishes no injector effectiveness.

## Review without provider calls

```sh
uv run --locked pytest -q tests/test_token_parity.py tests/test_grok.py
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Browser: keep Mock, load the demo, run, inspect both parity comparisons, export, reopen, and
replay. Test coverage includes equality, context mismatch, assembled-input mismatch, missing
tokenizers, malformed counts, failure/timeout, the real xAI SDK response container, transport
formatting, cache scope, blocked generation, historical preservation, exports, and replay.

Implementation contracts were checked against installed `tiktoken==0.14.0`,
`xai-sdk==1.19.0`, and `anthropic==1.8.0`, plus official references:

- [xAI tokenization API](https://docs.x.ai/developers/grpc-api-reference/tokenize)
- [xAI async tokenizer source](https://github.com/xai-org/xai-sdk-python/blob/main/xai_sdk/aio/tokenizer.py)
- [Claude token counting and estimate limits](https://platform.claude.com/docs/en/build-with-claude/token-counting)
- [OpenAI tiktoken model mapping](https://github.com/openai/tiktoken/blob/main/tiktoken/model.py)

### Verification for this change, 2026-10-08

- `uv run --locked pytest -q`: 193 passed, one existing Starlette/AnyIO deprecation warning.
- `uv run --locked ruff check .`: passed. Formatting checks pass for all changed Python files.
- `uv run --locked ruff format --check .`: six pre-existing failures, verified against the
  base commit: `glyph_report.py`, `tests/test_claude.py`, `tests/test_context_windows.py`,
  `tests/test_grok.py`, `workbench/app.py`, and `workbench/context_windows.py`. Left unchanged.
- `node --check workbench/static/app.js` and `node --check scripts/browser-smoke.cjs`: passed.
- Browser smoke started the isolated app and received `/health` HTTP 200. Browser assertions
  could not run: Chromium was absent and the attempted installation returned an invalid ZIP.
  The added browser assertions therefore remain unverified in this environment.
- No live provider tokenization or generation calls. No changes to reference artifacts,
  historical records/fixtures, license terms, dependency pins, or release tags.
