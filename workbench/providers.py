"""Provider-neutral, explicitly selected local/cloud execution."""

import asyncio
import json
import os
from functools import lru_cache
from importlib.metadata import version
from typing import Protocol

from .models import Condition, ProviderResult, RunRequest


class ProviderAdapter(Protocol):
    async def generate(self, condition: Condition) -> ProviderResult: ...


@lru_cache(maxsize=1)
def prepare_sdk():
    # This standalone app owns SDK tracing: install no exporters or background clients.
    from agents import set_trace_provider
    from agents.tracing.provider import DefaultTraceProvider

    provider = DefaultTraceProvider()
    provider.set_disabled(True)
    set_trace_provider(provider)


def provider_versions(provider):
    packages = {
        "openai": ("openai-agents", "openai"),
        "claude": ("anthropic",),
    }.get(provider, ())
    return {name: version(name) for name in packages}


def cloud_available():
    return os.getenv("WORKBENCH_ENABLE_OPENAI") == "1" and bool(os.getenv("OPENAI_API_KEY"))


def claude_available():
    return os.getenv("WORKBENCH_ENABLE_CLAUDE") == "1" and bool(os.getenv("ANTHROPIC_API_KEY"))


def any_cloud_available():
    return cloud_available() or claude_available()


def claude_context_floor() -> int:
    raw = os.getenv("WORKBENCH_CLAUDE_CONTEXT_FLOOR", "200000")
    try:
        floor = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("WORKBENCH_CLAUDE_CONTEXT_FLOOR must be an integer") from exc
    if floor < 1:
        raise RuntimeError("WORKBENCH_CLAUDE_CONTEXT_FLOOR must be positive")
    return floor


def provider_catalog():
    return [
        {
            "id": "mock",
            "model": "fixture-echo-v2",
            "enabled": True,
            "execution": "local-offline",
        },
        {
            "id": "openai",
            "enabled": cloud_available(),
            "execution": "cloud",
            "reason": "Requires WORKBENCH_ENABLE_OPENAI=1 and server-side OPENAI_API_KEY",
            "seed_supported": False,
        },
        {
            "id": "ollama",
            "enabled": False,
            "reason": "Not implemented; no local model requests",
        },
        {
            "id": "claude",
            "enabled": claude_available(),
            "execution": "cloud",
            "reason": "Requires WORKBENCH_ENABLE_CLAUDE=1 and server-side ANTHROPIC_API_KEY",
            "seed_supported": False,
        },
    ]


class MockProvider:
    def __init__(self, request=None):
        self.request = request or RunRequest(task="fixture")

    async def generate(self, condition: Condition) -> ProviderResult:
        await asyncio.sleep(0.15)
        receipt = {
            "kind": "OFFLINE_FIXTURE",
            "notice": "Synthetic acknowledgement. No model answered or evaluated this task.",
            "task_received": condition.messages[-1].content,
            "message_count": len(condition.messages),
            "injector_present": condition.injector is not None,
            "assembled_prompt_sha256": condition.prompt_hash,
            "fixture_seed": self.request.sampling.seed,
        }
        return ProviderResult(
            raw_response=json.dumps(receipt, ensure_ascii=False, indent=2),
            structured_response=receipt,
            resolved_model="fixture-echo-v2",
            response_status="completed",
        )


class OpenAIProvider:
    """One tool-free Agents SDK agent, one Responses request per generate call."""

    def __init__(self, request, client_factory=None):
        self.request, self.client_factory = request, client_factory

    async def generate(self, condition: Condition) -> ProviderResult:
        if not self.client_factory and not cloud_available():
            raise RuntimeError("OpenAI is disabled or OPENAI_API_KEY is missing")
        await asyncio.to_thread(prepare_sdk)
        from agents import Agent, ModelSettings, RunConfig, Runner
        from agents.models.openai_responses import OpenAIResponsesModel
        from agents.retry import ModelRetrySettings
        from openai import AsyncOpenAI

        # Explicit endpoint prevents accidental redirection by ambient OPENAI_BASE_URL.
        factory = self.client_factory or AsyncOpenAI
        client = factory(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url="https://api.openai.com/v1",
            max_retries=0,
            timeout=self.request.timeout_seconds,
        )
        captured = {}

        class CapturingModel(OpenAIResponsesModel):
            # SDK 0.22.3 ModelResponse omits the returned model string. Capture it
            # before normalization; this pinned internal hook has transport-level tests.
            async def _fetch_response(self, *args, **kwargs):
                response = await super()._fetch_response(*args, **kwargs)
                captured.update(
                    model=response.model,
                    response_id=response.id,
                    status=response.status,
                    usage=response.usage.model_dump() if response.usage else None,
                )
                return response

        sampling = self.request.sampling
        settings = ModelSettings(
            temperature=sampling.temperature,
            top_p=sampling.top_p,
            max_tokens=sampling.max_output_tokens,
            store=False,
            truncation="disabled",
            retry=ModelRetrySettings(max_retries=0),
        )
        agent = Agent(
            name="Workbench",
            instructions=None,
            tools=[],
            handoffs=[],
            model=CapturingModel(model=self.request.model, openai_client=client),
            model_settings=settings,
        )
        try:
            result = await Runner.run(
                agent,
                input=[m.model_dump() for m in condition.messages],
                max_turns=1,
                run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
            )
            usage = captured.get("usage")
            counts = (
                {
                    k: usage[k]
                    for k in ("input_tokens", "output_tokens", "total_tokens")
                    if type(usage.get(k)) is int
                }
                if usage is not None
                else None
            )
            return ProviderResult(
                raw_response=str(result.final_output),
                structured_response={
                    "output": [
                        item.model_dump(mode="json")
                        for response in result.raw_responses
                        for item in response.output
                    ]
                },
                token_usage=counts,
                resolved_model=captured.get("model"),
                response_id=captured.get("response_id"),
                response_status=captured.get("status"),
            )
        finally:
            await client.close()


def _adapt_claude_messages(messages):
    """Transport-only. Does not alter stored messages or prompt_hash."""
    system_parts = []
    turns = []
    for message in messages:
        if message.role == "system":
            if turns:
                raise ValueError("Claude transport cannot place a system message after a turn")
            system_parts.append(message.content)
            continue
        if turns and turns[-1]["role"] == message.role:
            turns[-1]["content"] = f"{turns[-1]['content']}\n\n{message.content}"
        else:
            turns.append({"role": message.role, "content": message.content})
    if not turns:
        raise ValueError("Claude transport requires a user or assistant turn")
    system = None
    if len(system_parts) == 1:
        system = system_parts[0]
    elif system_parts:
        system = "\n\n".join(system_parts)
    return system, turns


def _claude_input_tokens(counted):
    if isinstance(counted, dict):
        value = counted.get("input_tokens")
    else:
        value = getattr(counted, "input_tokens", None)
    return value if type(value) is int else None


def _claude_stop_status(stop_reason):
    if stop_reason in ("end_turn", "stop_sequence"):
        return "completed"
    if isinstance(stop_reason, str) and stop_reason:
        return stop_reason
    return "unknown"


def _claude_text(message):
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    parts = []
    for block in content or []:
        if isinstance(block, dict):
            kind, text = block.get("type"), block.get("text")
        else:
            kind, text = getattr(block, "type", None), getattr(block, "text", None)
        if kind == "text" and isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def _claude_usage(message):
    if isinstance(message, dict):
        usage = message.get("usage")
    else:
        usage = getattr(message, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        raw = usage.model_dump()
    elif isinstance(usage, dict):
        raw = usage
    else:
        raw = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
    counts = {key: value for key, value in raw.items() if type(value) is int}
    return counts or None


def _optional_str(value):
    return value if isinstance(value, str) and value else None


def _context_window_error(floor, budget, counted):
    err = ValueError(
        f"Claude input exceeds the context window ({counted} input tokens > {budget} token budget)"
    )
    err.receive_gate = {
        "context_floor": floor,
        "budget": budget,
        "counted_input_tokens": counted,
    }
    return err


class ClaudeProvider:
    """One tool-free Messages API call per generate(). Tokens are counted before create."""

    def __init__(self, request, client_factory=None):
        self.request, self.client_factory = request, client_factory

    async def generate(self, condition: Condition) -> ProviderResult:
        if not self.client_factory and not claude_available():
            raise RuntimeError("Claude is disabled or ANTHROPIC_API_KEY is missing")
        from anthropic import AsyncAnthropic

        system, turns = _adapt_claude_messages(condition.messages)
        payload = {"model": self.request.model, "messages": turns}
        if system is not None:
            payload["system"] = system
        sampling = self.request.sampling
        create_payload = {**payload, "max_tokens": sampling.max_output_tokens}
        extra = {}
        if sampling.temperature is not None:
            extra["temperature"] = sampling.temperature
        if sampling.top_p is not None:
            extra["top_p"] = sampling.top_p
        if extra:
            # SDK 1.8 has no typed temperature/top_p arguments; extra_body is the request body.
            create_payload["extra_body"] = extra
        floor = claude_context_floor()
        budget = floor - sampling.max_output_tokens
        factory = self.client_factory or AsyncAnthropic
        ambient = os.environ.pop("ANTHROPIC_BASE_URL", None)
        client = None
        try:
            client = factory(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                base_url="https://api.anthropic.com",
                max_retries=0,
                timeout=self.request.timeout_seconds,
            )
            counted = await client.messages.count_tokens(**payload)
            counted_tokens = _claude_input_tokens(counted)
            if counted_tokens is None:
                raise ValueError("Claude token count did not include input_tokens")
            gate = {
                "context_floor": floor,
                "budget": budget,
                "counted_input_tokens": counted_tokens,
            }
            if counted_tokens > budget:
                raise _context_window_error(floor, budget, counted_tokens)
            try:
                message = await client.messages.create(**create_payload)
            except Exception as exc:
                exc.receive_gate = gate
                raise
        finally:
            if ambient is not None:
                os.environ["ANTHROPIC_BASE_URL"] = ambient
            if client is not None:
                await client.close()
        stop_reason = (
            message.get("stop_reason")
            if isinstance(message, dict)
            else getattr(message, "stop_reason", None)
        )
        structured = {"receive_gate": gate}
        if isinstance(stop_reason, str):
            structured["stop_reason"] = stop_reason
        if isinstance(message, dict):
            resolved, response_id = message.get("model"), message.get("id")
        else:
            resolved = getattr(message, "model", None)
            response_id = getattr(message, "id", None)
        return ProviderResult(
            raw_response=_claude_text(message),
            structured_response=structured,
            token_usage=_claude_usage(message),
            resolved_model=_optional_str(resolved),
            response_id=_optional_str(response_id),
            response_status=_claude_stop_status(stop_reason),
        )


class OllamaProvider:
    async def generate(self, condition: Condition) -> ProviderResult:
        raise NotImplementedError("Ollama is not implemented in v0.2.0")
