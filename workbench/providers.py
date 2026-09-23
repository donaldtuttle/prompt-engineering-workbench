"""Provider-neutral, explicitly selected local/cloud execution."""

import asyncio
import json
import os
from functools import lru_cache
from importlib.metadata import version
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .conditions import tokenizer
from .context_windows import (
    capped_window,
    claude_model_window,
    context_window_error,
    ollama_context,
    openai_model_window,
    receive_gate,
)
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
            "enabled": True,
            "execution": "local",
            "reason": "Loopback only. The context window is that model's reported context length.",
            "seed_supported": True,
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
        gate = _openai_gate(self.request, condition)
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
                    "receive_gate": gate,
                    "output": [
                        item.model_dump(mode="json")
                        for response in result.raw_responses
                        for item in response.output
                    ],
                },
                token_usage=counts,
                resolved_model=captured.get("model"),
                response_id=captured.get("response_id"),
                response_status=captured.get("status"),
            )
        except Exception as exc:
            exc.receive_gate = gate
            raise
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


def _openai_gate(request, condition):
    documented = openai_model_window(request.model)
    if documented is None:
        err = ValueError(
            "No pinned context window for this OpenAI model; refusing rather than guessing"
        )
        err.receive_gate = receive_gate(
            model=request.model,
            documented=None,
            floor=None,
            source="unpinned",
            budget=None,
            counted=None,
            count_source="not_counted",
        )
        raise err
    floor, source = capped_window(documented, "WORKBENCH_OPENAI_CONTEXT_FLOOR")
    counted = sum(len(tokenizer().encode(message.content)) for message in condition.messages)
    budget = floor - request.sampling.max_output_tokens
    gate = receive_gate(
        model=request.model,
        documented=documented,
        floor=floor,
        source=source,
        budget=budget,
        counted=counted,
        count_source="workbench-o200k-base message text; excludes provider framing",
    )
    if budget < 1 or counted > budget:
        raise context_window_error("OpenAI", gate)
    return gate


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
        documented = claude_model_window(self.request.model)
        floor, source = capped_window(documented, "WORKBENCH_CLAUDE_CONTEXT_FLOOR")
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
            gate = receive_gate(
                model=self.request.model,
                documented=documented,
                floor=floor,
                source=source,
                budget=budget,
                counted=counted_tokens,
                count_source="anthropic.count_tokens",
            )
            if budget < 1 or counted_tokens > budget:
                raise context_window_error("Claude", gate)
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


class OllamaRequestError(RuntimeError):
    def __init__(self, status=None):
        super().__init__("Local Ollama request failed")
        self.status = status


def ollama_base_url():
    value = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("OLLAMA_BASE_URL must be a loopback-only HTTP origin")
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _ollama_json(path, payload=None, timeout=2.0):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{ollama_base_url()}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    try:
        # Ignore ambient proxies and refuse redirects so a local service cannot
        # bounce prompts to a non-loopback endpoint.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise OllamaRequestError(exc.code) from exc
    except (URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise OllamaRequestError() from exc
    if not isinstance(result, dict):
        raise ValueError("Ollama returned a non-object response")
    return result


def _ollama_status(stop_reason):
    if stop_reason in (None, "stop"):
        return "completed"
    if isinstance(stop_reason, str) and stop_reason:
        return stop_reason
    return "unknown"


class OllamaProvider:
    """Loopback chat adapter. num_ctx is that model's reported context length."""

    def __init__(self, request=None, transport=None):
        self.request = request or RunRequest(
            task="fixture", provider="ollama", model="llama3.2:latest"
        )
        self.transport = transport or _ollama_json

    async def generate(self, condition: Condition) -> ProviderResult:
        sampling = self.request.sampling
        timeout = self.request.timeout_seconds
        show = await asyncio.to_thread(
            self.transport, "/api/show", {"model": self.request.model}, timeout
        )
        discovered = ollama_context(show)
        documented = discovered["model_context_length"]
        floor, source = capped_window(documented, "WORKBENCH_OLLAMA_CONTEXT_CAP")
        budget = floor - sampling.max_output_tokens
        extra = {
            "num_ctx": floor,
            "modelfile_num_ctx": discovered["modelfile_num_ctx"],
            "context_length_source": discovered["source"],
        }
        text = "\n".join(message.content for message in condition.messages)
        tokenize_count = await self._tokenize(text, timeout)
        if tokenize_count is not None and (budget < 1 or tokenize_count >= budget):
            raise context_window_error(
                "Ollama",
                receive_gate(
                    model=self.request.model,
                    documented=documented,
                    floor=floor,
                    source=source,
                    budget=budget,
                    counted=tokenize_count,
                    count_source="ollama.tokenize",
                    extra=extra,
                ),
            )
        options = {"num_predict": sampling.max_output_tokens, "num_ctx": floor}
        for name, value in (
            ("temperature", sampling.temperature),
            ("top_p", sampling.top_p),
            ("seed", sampling.seed),
        ):
            if value is not None:
                options[name] = value
        payload = {
            "model": self.request.model,
            "messages": [message.model_dump() for message in condition.messages],
            "stream": False,
            "options": options,
        }
        response = await asyncio.to_thread(self.transport, "/api/chat", payload, timeout)
        message = response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("Ollama response lacks assistant message content")
        if response.get("done") is not True:
            raise ValueError("Ollama response is incomplete")
        evaluated = response.get("prompt_eval_count")
        if type(evaluated) is not int:
            raise ValueError(
                "Ollama response did not include prompt_eval_count; context gate cannot be proven"
            )
        gate = receive_gate(
            model=self.request.model,
            documented=documented,
            floor=floor,
            source=source,
            budget=budget,
            counted=evaluated,
            count_source="ollama.prompt_eval_count",
            extra={**extra, "tokenize_input_tokens": tokenize_count},
        )
        # Filling the window matches Ollama's silent truncation count, so it is refused.
        if budget < 1 or evaluated >= budget:
            raise context_window_error("Ollama", gate)
        counts = {"input_tokens": evaluated}
        if type(response.get("eval_count")) is int:
            counts["output_tokens"] = response["eval_count"]
            counts["total_tokens"] = counts["input_tokens"] + counts["output_tokens"]
        return ProviderResult(
            raw_response=message["content"],
            structured_response={"receive_gate": gate},
            token_usage=counts,
            resolved_model=_optional_str(response.get("model")),
            response_status=_ollama_status(response.get("done_reason")),
        )

    async def _tokenize(self, text, timeout):
        try:
            counted = await asyncio.to_thread(
                self.transport,
                "/api/tokenize",
                {"model": self.request.model, "content": text},
                timeout,
            )
        except OllamaRequestError as exc:
            if exc.status in (404, 405):
                return None
            raise
        tokens = counted.get("tokens") if isinstance(counted, dict) else None
        if not isinstance(tokens, list) or any(type(item) is not int for item in tokens):
            raise ValueError("Ollama token count was unreadable")
        return len(tokens)
