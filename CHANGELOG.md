# Changelog

## 0.2.1 — 2026-09-22

- Added a loopback-only Ollama chat adapter with installed-model discovery, sampling controls,
  provider token counts, browser selection, and no API-key requirement.
- Verified real local inference with llama3.1:8b and llama3.2:latest, including a complete
  baseline/injector/neutral-control run through llama3.2:latest.

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
