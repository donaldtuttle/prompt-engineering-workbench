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
    packages = ["openai-agents", "openai"] if provider == "openai" else []
    return {name: version(name) for name in packages}


def cloud_available():
    return os.getenv("WORKBENCH_ENABLE_OPENAI") == "1" and bool(os.getenv("OPENAI_API_KEY"))


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


class OllamaProvider:
    async def generate(self, condition: Condition) -> ProviderResult:
        raise NotImplementedError("Ollama is not implemented in v0.2.0")
