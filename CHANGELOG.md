# Changelog

## Unreleased

Later-slice Claude adapter. Not enabled by default. No model-efficacy claim; resolution stays
INSUFFICIENT_EVIDENCE.

- Added an opt-in Claude Messages adapter. It runs only when `WORKBENCH_ENABLE_CLAUDE=1` and
  `ANTHROPIC_API_KEY` are both set. The endpoint is explicit `https://api.anthropic.com`, retries
  are off, and each `generate()` is one tool-free call.
- Added a receive-gate: `messages.count_tokens` runs before `create`. Input above the context floor
  minus max output tokens is refused. The default floor is 200000 (`WORKBENCH_CLAUDE_CONTEXT_FLOOR`).
- Replay of a Claude experiment requires fresh `cloud_consent`, the same rule as OpenAI.

- Context windows are per model. Confirmed Claude 1M ids use 1,000,000 tokens; other
  `claude-*` ids stay at 200,000. `gpt-4o` snapshots use 128,000 and `gpt-4.1` snapshots
  use 1,047,576. Unlisted OpenAI ids are refused. `WORKBENCH_CLAUDE_CONTEXT_FLOOR` and
  `WORKBENCH_OPENAI_CONTEXT_FLOOR` can only lower those windows.
- Ollama is a loopback chat adapter. It sends `num_ctx` from that model's reported
  architecture context length, not the 2048 Modelfile default. A prompt that fills or
  exceeds the window is refused. `WORKBENCH_OLLAMA_CONTEXT_CAP` can only lower it.

## 0.2.0 — 2026-09-19

Complete experimental-control and adapter release. Status DEVELOP; live OpenAI smoke unverified.

- Added v2 run/export records, legacy v1 readers, explicit backed-up database admission migration.
- Added neutral token-length control, bundled hash-checked tokenizer, and three delivery protocols.
- Added bounded replicates, sampling settings, requested/returned model identity, SDK capture, and
  configuration hashes. Handshake/task calls are separately recorded.
- Added stored final-prompt replay with input/configuration validation and source lineage.
- Moved file/database I/O off the event loop; reserved queue slots before preparation; ordered saves
  and made cancellation/shutdown wait for in-flight persistence.
- Added one tool-free OpenAI Agents SDK adapter with explicit cloud opt-in, no hidden retries,
  no trace exporter, disabled response storage, and requested truncation disabled.
- Normalized the successor manifest to LF, retaining original and v0.1.1 copies. Injector hash
  pins remain unchanged. Added separately attributed reviewer attestation.
- Expanded interface controls, browser coverage, SDK mock-transport tests, and upgrade documentation.
- D4 ablation-storage redesign, blind audit, efficacy protocols, Ollama, streaming UI, and actual
  live-account execution remain open.

## 0.1.1 — 2026-09-19

Restored the LF injector against original full/scoped pins; preserved CRLF source and original
manifest; declared Pydantic directly; added generic manifest line-ending policy. Offline-only.
80 tests and 17 browser checks passed at that release.

## 0.1.0 — 2026-09-19

Initial offline vertical slice: task editor, two-condition mock runs, integrity gate, SQLite,
comparison view, JSON/JSONL export. 48 tests and 13 browser checks passed at that release.
The supplied CRLF QOFT input correctly blocked its treatment.
