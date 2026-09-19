# OpenAI adapter — v0.2.0

The implementation uses openai-agents 0.22.3 with openai 3.16.2, pinned in pyproject/uv.lock.
It runs one Agent through Runner.run, with no tools, handoffs, hidden agent instructions,
sessions, or previous_response_id. Each invocation is one nonstreaming Responses request.

Implementation follows explicit model selection and the SDK execution boundary described in
[Models and providers](https://developers.openai.com/api/docs/guides/agents/models) and
[Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents).
Tracing is separately controlled, as discussed in
[Integrations and observability](https://developers.openai.com/api/docs/guides/agents/integrations-observability).
Exact Python signatures were checked against the installed pinned packages on 2026-09-19.

## Execution contract

- WORKBENCH_ENABLE_OPENAI=1 plus a server-side OPENAI_API_KEY are required by the public path.
- Each request must select OpenAI, specify an explicit model string, and give cloud consent.
- Endpoint is fixed to https://api.openai.com/v1; OPENAI_BASE_URL cannot silently redirect inputs.
- Store is false and truncation disabled. Unsupported settings fail instead of being omitted
  or replaced silently. Seed is not exposed by this adapter.
- Both HTTP-client and SDK retries are zero; the controller owns recorded retries/timeouts.
- Trace run config is disabled and the process trace provider has no exporters. This avoids
  initializing an unused exporter client and keeps trace_id null.
- A new client is closed after each call, including failures.
- SDK import/setup is performed off the event loop.
- Only exception types enter experiment errors, never exception messages.
- Raw structured response output is retained separately from any future evaluation.

## Returned model capture

The pinned SDK ModelResponse omits the raw response's model string. A small subclass captures
model, response ID/status, and usage at _fetch_response before SDK normalization. This is
an internal SDK hook: retain the version pin and transport-level tests when upgrading it.

A request-model alias is never silently promoted to an immutable snapshot. resolved_model is
exactly the provider-returned value, or null if unavailable. Provider cost is not inferred.
Missing usage stays null rather than being converted to fabricated zero totals.
The pinned SDK rejects incomplete/failed terminal responses before the capture hook returns.
Those calls retain ModelBehaviorError and null result/usage; partial provider output is not
available through this adapter path and must not be counted as zero-cost work.

## Verification boundary

Tests run the actual installed Agent, Runner, OpenAIResponsesModel, and AsyncOpenAI code
against httpx2.MockTransport. They inspect serialized request bodies for all delivery modes,
including both handshake phases, then verify returned identity/usage and missing-usage nulls.
Tests also cover HTTP failure isolation, exception-message redaction, explicit retries,
and incomplete response handling.

This validates local SDK integration and wire construction. It does not establish live API
acceptance, account/model access, quotas, network reliability, or model behavior. No paid
OpenAI request was made during this build. A user-selected small-fixture live smoke run remains
the next adapter verification step; scientific experiments require the separate protocol gates.
