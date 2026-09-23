import asyncio

import pytest

from workbench.conditions import assemble
from workbench.context_windows import claude_model_window, ollama_context, openai_model_window
from workbench.models import RunRequest, SamplingSettings
from workbench.providers import (
    OllamaProvider,
    OllamaRequestError,
    OpenAIProvider,
    ollama_base_url,
)


def test_claude_windows_follow_confirmed_model_ids():
    assert claude_model_window("claude-sonnet-4-5") == 200_000
    assert claude_model_window("claude-haiku-4-5-20251001") == 200_000
    assert claude_model_window("claude-sonnet-5") == 1_000_000
    assert claude_model_window("claude-sonnet-4-6") == 1_000_000
    assert claude_model_window("claude-opus-4-6-20260205") == 1_000_000
    with pytest.raises(ValueError, match="pinned context window"):
        claude_model_window("gpt-4o")


def test_openai_windows_do_not_guess_unlisted_ids():
    assert openai_model_window("gpt-4o") == 128_000
    assert openai_model_window("gpt-4o-2024-11-20") == 128_000
    assert openai_model_window("gpt-4.1") == 1_047_576
    assert openai_model_window("gpt-4.1-2025-04-14") == 1_047_576
    assert openai_model_window("gpt-4.1-mini") is None
    assert openai_model_window("requested-snapshot") is None


def test_env_cap_cannot_raise_a_model_window(monkeypatch):
    from workbench.context_windows import capped_window

    monkeypatch.setenv("WORKBENCH_OPENAI_CONTEXT_FLOOR", "999999999")
    assert capped_window(128_000, "WORKBENCH_OPENAI_CONTEXT_FLOOR") == (128_000, "model")
    monkeypatch.setenv("WORKBENCH_CLAUDE_CONTEXT_FLOOR", "1000")
    assert capped_window(1_000_000, "WORKBENCH_CLAUDE_CONTEXT_FLOOR") == (1000, "env_cap")
    monkeypatch.setenv("WORKBENCH_OLLAMA_CONTEXT_CAP", "nope")
    with pytest.raises(RuntimeError, match="integer"):
        capped_window(8192, "WORKBENCH_OLLAMA_CONTEXT_CAP")


def test_openai_pinned_window_refuses_before_the_client(monkeypatch):
    monkeypatch.setenv("WORKBENCH_OPENAI_CONTEXT_FLOOR", "32")
    request = RunRequest(
        task="word " * 40,
        provider="openai",
        model="gpt-4o",
        cloud_consent=True,
        artifact_id=None,
        sampling=SamplingSettings(max_output_tokens=16),
    )

    def factory(**kwargs):
        raise AssertionError("over-budget call must not construct a client")

    provider = OpenAIProvider(request, client_factory=factory)
    with pytest.raises(ValueError, match="context window") as caught:
        asyncio.run(provider.generate(assemble(request.task)))
    gate = caught.value.receive_gate
    assert gate["model_context_window"] == 128_000
    assert gate["context_floor"] == 32
    assert gate["context_floor_source"] == "env_cap"
    assert gate["budget"] == 16
    assert gate["counted_input_tokens"] > 16


def test_unpinned_openai_model_is_refused(monkeypatch):
    request = RunRequest(
        task="short",
        provider="openai",
        model="requested-snapshot",
        cloud_consent=True,
        artifact_id=None,
    )

    def factory(**kwargs):
        raise AssertionError("unpinned model must not construct a client")

    provider = OpenAIProvider(request, client_factory=factory)
    with pytest.raises(ValueError, match="refusing rather than guessing") as caught:
        asyncio.run(provider.generate(assemble("short")))
    assert caught.value.receive_gate["context_floor_source"] == "unpinned"


def test_ollama_show_uses_architecture_length_not_modelfile_default():
    show = {
        "parameters": "num_ctx 2048\nstop END",
        "model_info": {
            "general.architecture": "llama",
            "llama.context_length": 131072,
            "gemma.context_length": 8192,
        },
    }
    assert ollama_context(show) == {
        "model_context_length": 131072,
        "modelfile_num_ctx": 2048,
        "source": "model_info:llama.context_length",
    }
    with pytest.raises(ValueError, match="ambiguous"):
        ollama_context({"model_info": {"llama.context_length": 8, "gemma.context_length": 4}})


def _ollama_request(**overrides):
    values = {
        "task": "name one color",
        "provider": "ollama",
        "model": "llama3.1:8b",
        "artifact_id": None,
        "sampling": SamplingSettings(max_output_tokens=64, seed=7),
    }
    values.update(overrides)
    return RunRequest(**values)


def _show():
    return {
        "parameters": "num_ctx 2048",
        "model_info": {"general.architecture": "llama", "llama.context_length": 8192},
    }


def test_ollama_sends_model_num_ctx_and_records_the_gate():
    calls = []

    def transport(path, payload, timeout):
        calls.append((path, payload, timeout))
        if path == "/api/show":
            return _show()
        if path == "/api/tokenize":
            return {"tokens": [1, 2, 3]}
        assert payload["options"]["num_ctx"] == 8192
        assert payload["options"]["num_predict"] == 64
        assert payload["options"]["seed"] == 7
        assert payload["stream"] is False
        return {
            "done": True,
            "done_reason": "stop",
            "model": "llama3.1:8b",
            "message": {"role": "assistant", "content": "blue"},
            "prompt_eval_count": 30,
            "eval_count": 1,
        }

    request = _ollama_request()
    result = asyncio.run(
        OllamaProvider(request, transport).generate(assemble(request.task))
    )
    assert [path for path, _, _ in calls] == ["/api/show", "/api/tokenize", "/api/chat"]
    gate = result.structured_response["receive_gate"]
    assert gate["model_context_window"] == 8192
    assert gate["context_floor"] == 8192
    assert gate["num_ctx"] == 8192
    assert gate["modelfile_num_ctx"] == 2048
    assert gate["counted_input_tokens"] == 30
    assert gate["tokenize_input_tokens"] == 3
    assert result.response_status == "completed"


def test_ollama_tokenize_over_budget_does_not_chat():
    calls = []

    def transport(path, payload, timeout):
        calls.append(path)
        if path == "/api/show":
            return _show()
        if path == "/api/tokenize":
            return {"tokens": list(range(9000))}
        raise AssertionError("chat must not run")

    request = _ollama_request()
    with pytest.raises(ValueError, match="context window") as caught:
        asyncio.run(OllamaProvider(request, transport).generate(assemble(request.task)))
    assert calls == ["/api/show", "/api/tokenize"]
    assert caught.value.receive_gate["count_source"] == "ollama.tokenize"
    assert caught.value.receive_gate["budget"] == 8192 - 64


def test_ollama_full_window_count_is_refused_as_truncation():
    def transport(path, payload, timeout):
        if path == "/api/show":
            return _show()
        if path == "/api/tokenize":
            raise OllamaRequestError(404)
        return {
            "done": True,
            "message": {"role": "assistant", "content": "clipped"},
            "prompt_eval_count": 8192 - 64,
            "eval_count": 64,
        }

    request = _ollama_request()
    with pytest.raises(ValueError, match="context window"):
        asyncio.run(OllamaProvider(request, transport).generate(assemble(request.task)))


def test_ollama_base_url_rejects_non_loopback(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://example.com")
    with pytest.raises(ValueError, match="loopback"):
        ollama_base_url()
