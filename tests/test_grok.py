import asyncio

import pytest
from fastapi.testclient import TestClient

from workbench.app import create_app
from workbench.conditions import assemble
from workbench.context_windows import grok_model_window
from workbench.controller import Controller
from workbench.models import RunRequest, SamplingSettings
from workbench.providers import GrokProvider, _XaiTransport, grok_client_kwargs
from workbench.repository import Repository


class _Usage:
    prompt_tokens = 9
    completion_tokens = 2
    total_tokens = 11
    reasoning_tokens = 0


class _Reply:
    content = "recorded"
    finish_reason = "REASON_STOP"
    usage = _Usage()
    id = "resp_fixture"
    model = "grok-4.7"
    encrypted_content = ""
    cost_usd = None


class FakeGrok:
    def __init__(self, tokens=4, reply=None):
        self.tokens = tokens
        self.reply = reply or _Reply()
        self.tokenize_calls = []
        self.sample_calls = []
        self.closed = False

    async def tokenize_text(self, *, text, model):
        self.tokenize_calls.append({"text": text, "model": model})
        return list(range(self.tokens))

    async def sample(self, **kwargs):
        self.sample_calls.append(kwargs)
        return self.reply

    async def close(self):
        self.closed = True


def _factory(client, seen):
    def factory(**kwargs):
        seen.append(kwargs)
        return client

    return factory


def _request(**overrides):
    values = {
        "task": "name one color",
        "provider": "grok",
        "model": "grok-4.7",
        "cloud_consent": True,
        "artifact_id": None,
        "sampling": SamplingSettings(max_output_tokens=64, seed=3),
    }
    values.update(overrides)
    return RunRequest(**values)


def test_pinned_windows_are_exact_ids():
    assert grok_model_window("grok-4.7") == 500_000
    assert grok_model_window("grok-4.6") == 500_000
    assert grok_model_window("grok-4.5-latest") == 500_000
    assert grok_model_window("grok-4") == 256_000
    assert grok_model_window("grok-4-0709") == 256_000
    with pytest.raises(ValueError, match="pinned context window"):
        grok_model_window("grok-4.7-latest")
    with pytest.raises(ValueError, match="pinned context window"):
        grok_model_window("grok-4-fast")


def test_client_kwargs_pin_host_and_disable_retries(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "synthetic-test-key")
    kwargs = grok_client_kwargs(12)
    assert kwargs["api_host"] == "api.x.ai"
    assert kwargs["api_key"] == "synthetic-test-key"
    assert kwargs["timeout"] == 12
    assert ("grpc.enable_retries", 0) in kwargs["channel_options"]


def test_transport_refuses_a_different_host_before_connecting():
    with pytest.raises(RuntimeError, match="api.x.ai"):
        _XaiTransport(api_host="example.com", channel_options=[("grpc.enable_retries", 0)])
    with pytest.raises(RuntimeError, match="retries"):
        _XaiTransport(api_host="api.x.ai", channel_options=[])


def test_consent_fixture_model_rejected():
    with pytest.raises(ValueError, match="cloud_consent"):
        RunRequest(task="probe", provider="grok", model="grok-4.7")
    with pytest.raises(ValueError, match="explicit Grok"):
        RunRequest(
            task="probe", provider="grok", model="fixture-echo-v2", cloud_consent=True
        )


def test_sample_follows_tokenize_and_records_the_model_window():
    seen = []
    client = FakeGrok()
    request = _request()
    result = asyncio.run(
        GrokProvider(request, _factory(client, seen)).generate(assemble(request.task))
    )
    assert seen[0]["api_host"] == "api.x.ai"
    assert ("grpc.enable_retries", 0) in seen[0]["channel_options"]
    assert client.tokenize_calls[0]["model"] == "grok-4.7"
    assert "name one color" in client.tokenize_calls[0]["text"]
    assert client.sample_calls[0]["seed"] == 3
    assert client.sample_calls[0]["max_tokens"] == 64
    assert client.sample_calls[0]["messages"][-1]["content"] == request.task
    assert client.closed
    gate = result.structured_response["receive_gate"]
    assert gate["model_context_window"] == 500_000
    assert gate["context_floor"] == 500_000
    assert gate["budget"] == 500_000 - 64
    assert gate["counted_input_tokens"] == 4
    assert gate["count_source"].startswith("xai.tokenize")
    assert "o200k" not in gate["count_source"]
    assert result.response_status == "completed"
    assert result.token_usage["input_tokens"] == 9
    assert result.cost_usd is None


def test_over_budget_does_not_sample(monkeypatch):
    monkeypatch.setenv("WORKBENCH_GROK_CONTEXT_FLOOR", "1000")
    seen = []
    client = FakeGrok(tokens=901)
    request = _request(sampling=SamplingSettings(max_output_tokens=100))
    with pytest.raises(ValueError, match="context window") as caught:
        asyncio.run(GrokProvider(request, _factory(client, seen)).generate(assemble(request.task)))
    assert client.sample_calls == []
    gate = caught.value.receive_gate
    assert gate["context_floor"] == 1000
    assert gate["model_context_window"] == 500_000
    assert gate["context_floor_source"] == "env_cap"
    assert gate["budget"] == 900
    assert client.closed


def test_unpinned_model_does_not_open_a_client():
    request = _request(model="grok-2")

    def factory(**kwargs):
        raise AssertionError("unpinned model must not construct a client")

    with pytest.raises(ValueError, match="pinned context window") as caught:
        asyncio.run(GrokProvider(request, factory).generate(assemble("name one color")))
    assert caught.value.receive_gate["context_floor_source"] == "unpinned"


def test_max_context_finish_is_not_completed():
    reply = _Reply()
    reply.finish_reason = "REASON_MAX_CONTEXT"
    client = FakeGrok(reply=reply)
    request = _request()
    result = asyncio.run(
        GrokProvider(request, _factory(client, [])).generate(assemble(request.task))
    )
    assert result.response_status == "REASON_MAX_CONTEXT"


def test_server_prompt_tokens_over_budget_fail_the_call():
    reply = _Reply()
    reply.usage = _Usage()
    reply.usage.prompt_tokens = 500_000
    client = FakeGrok(tokens=4, reply=reply)
    request = _request(sampling=SamplingSettings(max_output_tokens=64))
    with pytest.raises(ValueError, match="context window") as caught:
        asyncio.run(GrokProvider(request, _factory(client, [])).generate(assemble(request.task)))
    assert client.sample_calls
    assert caught.value.receive_gate["count_source"] == "xai.usage.prompt_tokens"
    assert caught.value.receive_gate["counted_input_tokens"] == 500_000


def test_replay_requires_fresh_consent(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_ENABLE_GROK", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    from workbench.app import ROOT
    from workbench.artifacts import ArtifactStore

    ctrl = Controller(
        Repository(tmp_path / "runs.db"), ArtifactStore(ROOT / "reference/injectors")
    )
    exp = ctrl.build(_request())
    exp.status = "FAILED"
    ctrl.repo.save(exp)
    with TestClient(create_app(ctrl.repo.path, test_mode=True)) as client:
        url = f"/api/experiments/{exp.experiment_id}/replay"
        assert client.post(url, json={}).status_code == 400
        assert client.post(url, json={"cloud_consent": True}).status_code == 409
