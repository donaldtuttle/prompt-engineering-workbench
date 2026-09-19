# Implementation decisions — v0.2.0

Date: 2026-09-19. Status: DEVELOP. User authorized the complete proposed v0.2.0 release.
The original AGENTS.md and PROJECT_BRIEF.md are retained. Their v0.1 milestone sections are
historical scope; this release implements the subsequently approved scope.

1. Keep FastAPI, SQLite, asyncio, a provider boundary, and plain browser assets. No new frontend
   framework, hosted service, arbitrary network target, accounts, or multi-agent workflow.
2. New records use workbench-experiment-v2 / workbench-export-v2. Preserve the complete original
   model definitions in legacy_models.py for v1 reads/exports. Do not invent legacy settings.
3. SQLite schema 2 is an admission/version guard over the same table layout. Explicit offline
   migration validates v1 payloads, makes a SQLite backup, and changes only metadata. No automatic
   startup migration. Unversioned/future databases are refused.
4. Terminal old payloads remain verbatim. Startup recovery alone changes unfinished old records
   to INTERRUPTED, still under v1. Reuse setup creates new v2 records; legacy true replay is refused.
5. Build every new artifact experiment with baseline, full context, and a length control.
   The control matches o200k_base context tokens using pinned local tokenizer bytes.
   Semantic neutrality and model-specific tokenizer equivalence remain unestablished.
6. Delivery mode is a recorded condition and run parameter. The three protocols, including exact
   shared readiness prompt, are specified in PROTOCOL.md. Never invent a handshake answer.
7. In handshake mode, both baseline and context lanes receive a preparation call; the task is
   withheld until then. Store preparation output and final message/hash independently. No automatic
   activation/conformance verdict. No cross-lane conversation sharing.
8. Replicates are bounded 1–4, indexed from zero. Sampling has temperature/top_p/seed/output cap.
   Nulls mean unknown/omitted; unsupported cloud seeds are rejected. Mock seed is a fixture input.
   Record exact requested/returned model strings; do not equate aliases with immutable snapshots.
9. Keep messages-json-v1 for the unchanged serialization algorithm. Separate initial and final
   prompt hashes. configuration_hash binds declared execution/sampling/SDK settings.
10. Replay FROZEN_FINAL_PROMPT copies stored messages after hash/configuration checks and unchanged
    SDK versions. It reuses the original handshake reply, makes only the task call, creates new IDs,
    and retains source lineage. This is input replay, not output determinism.
11. Submission reserves a slot atomically before any awaited preparation. Worker-thread preparation
    and initial saves complete before handoff to the background task. Failed/cancelled preparation
    releases capacity. Sixteen admitted experiments maximum; four global active lanes.
12. All application file/database reads and writes are either worker-thread calls or synchronous
    FastAPI routes executed in its threadpool. Ordered per-experiment saves use deep copies; cancellation
    waits for in-flight writes before recording interruption. TaskGroup owns lane cancellation.
    Shutdown recovery also covers a task cancelled before its coroutine starts.
13. D4 is deliberately still open: full experiment payloads are serialized on each transition.
    No ablation matrix ships. Artifact deduplication and per-run writes belong before that milestone.
14. UTC isoformat is the timestamp invariant. Repository writes reject noncanonical created_at
    values rather than silently mixing offsets in text ordering.
15. Implement one OpenAI Agents SDK adapter. Cloud selection requires server enablement, a key,
    explicit model, and per-request consent. Cloud replay asks for fresh consent. No key enters the UI.
16. SDK/client automatic retries, tools, handoffs, storage, truncation, and trace exports are disabled.
    Controller retries and timeout are recorded; timeout covers the whole attempt. SDK/client versions
    are pinned. A small tested internal hook captures the raw returned model before normalization.
17. Provider usage is preserved when returned; no price estimates or fabricated traces. Failed SDK
    calls can incur unknown usage. Record exception type only. No live-account smoke run was performed.
18. Preserve the restored LF injector and its original pins. Archive the v0.1.1 mixed-ending successor
    before making the v0.2.0 successor LF-only. Preserve original source/manifest and v0.1.1 provenance.
19. Add reviewer byte-identity confirmation as an attributed attestation. The build-access fact
    independent_original_LF_copy_accessed remains false. The exact transport culprit stays unknown.
20. Comparison labels remain visible; evaluation stays null and resolution INSUFFICIENT_EVIDENCE.
    No software check promotes QOFT claims, certifies activation, or establishes treatment efficacy.
21. Browser QA runs with copied references, temporary databases, cloud disabled, and no production
    data changes. Source releases contain no runtime databases, environment, cache, key, or Git internals.
22. Use official documentation and inspect the pinned SDK source for implementation contracts.
    Docs references are in OPENAI_ADAPTER.md. A paid smoke test is distinct from the mock-transport gate.
