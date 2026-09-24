import asyncio
import base64
import os

import pytest
from fastapi.testclient import TestClient

from workbench.app import ROOT, create_app
from workbench.artifacts import ArtifactStore
from workbench.conditions import HANDSHAKE, assemble, with_messages
from workbench.controller import Controller
from workbench.models import Message, RunRequest, SamplingSettings
from workbench.providers import ClaudeProvider
from workbench.repository import Repository

MODEL = "claude-sonnet-4-5"


def controller(tmp_path):
    return Controller(Repository(tmp_path / "runs.db"), ArtifactStore(ROOT / "reference/injectors"))


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self):
        self.input_tokens = 4
        self.output_tokens = 1

    def model_dump(self):
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


class _Count:
    def __init__(self, input_tokens):
        self.input_tokens = input_tokens


class _Reply:
    def __init__(self, stop_reason):
        self.stop_reason = stop_reason
        self.content = [_Block("recorded")]
        self.usage = _Usage()
        self.id = "msg_fixture"
        self.model = "claude-returned"


class FakeMessages:
    def __init__(self, input_tokens=12, stop_reason="end_turn"):
        self.create_calls = []
        self.count_tokens_calls = []
        self.input_tokens = input_tokens
        self.stop_reason = stop_reason

    async def count_tokens(self, **kwargs):
        self.count_tokens_calls.append(kwargs)
        return _Count(self.input_tokens)

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return _Reply(self.stop_reason)


class FakeClient:
    def __init__(self, messages):
        self.messages = messages
        self.closed = False

    async def close(self):
        self.closed = True


def _factory(messages, seen, *, cleared=False):
    def factory(**kwargs):
        seen.append(kwargs)
        if cleared:
            assert os.environ.get("ANTHROPIC_BASE_URL") is None
        client = FakeClient(messages)
        factory.clients.append(client)
        return client

    factory.clients = []
    return factory


def _request(**overrides):
    values = {
        "task": "name one color",
        "provider": "claude",
        "model": MODEL,
        "cloud_consent": True,
        "artifact_id": "DEMO_OFFLINE_FIXTURE",
        "sampling": SamplingSettings(max_output_tokens=64),
    }
    values.update(overrides)
    return RunRequest(**values)


def _run(monkeypatch, request, condition, messages):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ambient.invalid")
    seen = []
    factory = _factory(messages, seen, cleared=True)
    provider = ClaudeProvider(request, client_factory=factory)
    before = condition.prompt_hash
    result = asyncio.run(provider.generate(condition))
    assert condition.prompt_hash == before
    assert seen[0]["base_url"] == "https://api.anthropic.com"
    assert seen[0]["max_retries"] == 0
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://ambient.invalid"
    assert factory.clients[0].closed
    return result, messages


def test_cloud_consent_and_seed_and_fixture_model_rejected():
    with pytest.raises(ValueError, match="cloud_consent"):
        RunRequest(task="probe", provider="claude", model=MODEL)
    with pytest.raises(ValueError, match="seed"):
        RunRequest(
            task="probe",
            provider="claude",
            model=MODEL,
            cloud_consent=True,
            sampling=SamplingSettings(seed=7),
        )
    with pytest.raises(ValueError, match="Claude model"):
        RunRequest(task="probe", provider="claude", model="fixture-echo-v2", cloud_consent=True)


def test_disabled_without_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("WORKBENCH_ENABLE_CLAUDE", raising=False)
    request = RunRequest(task="probe", provider="claude", model=MODEL, cloud_consent=True)
    with pytest.raises(RuntimeError):
        asyncio.run(ClaudeProvider(request).generate(assemble("probe")))
    monkeypatch.setenv("WORKBENCH_ENABLE_CLAUDE", "1")
    with pytest.raises(RuntimeError):
        asyncio.run(ClaudeProvider(request).generate(assemble("probe")))
    monkeypatch.delenv("WORKBENCH_ENABLE_CLAUDE")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")
    with pytest.raises(RuntimeError):
        asyncio.run(ClaudeProvider(request).generate(assemble("probe")))


def test_system_slot_injector_is_exact_and_user_only(monkeypatch):
    store = ArtifactStore(ROOT / "reference/injectors")
    snapshot = store.load("DEMO_OFFLINE_FIXTURE")
    request = _request(delivery_mode="SYSTEM_SLOT")
    condition = assemble(
        request.task, snapshot, kind="FULL_INJECTOR", delivery_mode="SYSTEM_SLOT"
    )
    messages = FakeMessages()
    result, messages = _run(monkeypatch, request, condition, messages)
    create_calls = messages.create_calls
    count_tokens = messages.count_tokens_calls
    assert len(create_calls) == 1 and len(count_tokens) == 1
    assert create_calls[0]["system"].encode() == base64.b64decode(snapshot.bytes_base64)
    assert [turn["role"] for turn in create_calls[0]["messages"]] == ["user"]
    assert "tools" not in create_calls[0] and "tools" not in count_tokens[0]
    assert count_tokens[0]["system"] == create_calls[0]["system"]
    assert count_tokens[0]["messages"] == create_calls[0]["messages"]
    gate = result.structured_response["receive_gate"]
    assert gate == {
        "model": MODEL,
        "context_floor": 200000,
        "model_context_window": 200000,
        "context_floor_source": "model",
        "budget": 200000 - 64,
        "counted_input_tokens": 12,
        "count_source": "anthropic.count_tokens",
    }
    assert result.response_status == "completed"


def test_user_paste_merges_injector_and_task(monkeypatch):
    store = ArtifactStore(ROOT / "reference/injectors")
    snapshot = store.load("DEMO_OFFLINE_FIXTURE")
    request = _request(delivery_mode="USER_PASTE")
    condition = assemble(request.task, snapshot, kind="FULL_INJECTOR", delivery_mode="USER_PASTE")
    messages = FakeMessages()
    _result, messages = _run(monkeypatch, request, condition, messages)
    create_calls = messages.create_calls
    assert "system" not in create_calls[0]
    assert [turn["role"] for turn in create_calls[0]["messages"]] == ["user"]
    injector = condition.messages[0].content
    assert create_calls[0]["messages"][0]["content"] == f"{injector}\n\n{request.task}"


def test_handshake_keeps_assistant_turn_unmerged(monkeypatch):
    store = ArtifactStore(ROOT / "reference/injectors")
    snapshot = store.load("DEMO_OFFLINE_FIXTURE")
    task = "name one color"
    request = _request(task=task, delivery_mode="USER_PASTE_WITH_HANDSHAKE")
    base = assemble(task, snapshot, kind="FULL_INJECTOR", delivery_mode="USER_PASTE_WITH_HANDSHAKE")
    final = with_messages(
        base,
        [
            *base.messages,
            Message(role="assistant", content="READY"),
            Message(role="user", content=task),
        ],
    )
    messages = FakeMessages()
    _result, messages = _run(monkeypatch, request, final, messages)
    create_calls = messages.create_calls
    turns = create_calls[0]["messages"]
    assert [turn["role"] for turn in turns] == ["user", "assistant", "user"]
    assert turns[1]["content"] == "READY"
    assert "\n\nREADY" not in turns[0]["content"]
    assert turns[2]["content"] == task
    assert turns[0]["content"].endswith("\n\n" + HANDSHAKE)
    assert "system" not in create_calls[0]


def test_count_tokens_above_budget_raises_context_window(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKBENCH_CLAUDE_CONTEXT_FLOOR", "1000")
    request = _request(artifact_id=None, sampling=SamplingSettings(max_output_tokens=100))
    messages = FakeMessages(input_tokens=901)
    seen = []
    provider = ClaudeProvider(request, client_factory=_factory(messages, seen))
    with pytest.raises(ValueError, match="context window"):
        asyncio.run(provider.generate(assemble("name one color")))
    create_calls = messages.create_calls
    count_tokens = messages.count_tokens_calls
    assert count_tokens and count_tokens[0]["model"] == MODEL
    assert create_calls == []
    ctrl = controller(tmp_path)
    refused = FakeMessages(input_tokens=901)
    ctrl.provider = ClaudeProvider(request, client_factory=_factory(refused, []))
    exp = asyncio.run(_execute(ctrl, request))
    call = exp.runs[0].calls[0]
    assert exp.status == "FAILED"
    assert call.error_type == "ValueError"
    assert call.result.structured_response["receive_gate"] == {
        "model": MODEL,
        "context_floor": 1000,
        "model_context_window": 200000,
        "context_floor_source": "env_cap",
        "budget": 900,
        "counted_input_tokens": 901,
        "count_source": "anthropic.count_tokens",
    }


def test_max_tokens_stop_is_not_completed(monkeypatch, tmp_path):
    request = _request(artifact_id=None)
    messages = FakeMessages(stop_reason="max_tokens")
    result, messages = _run(monkeypatch, request, assemble(request.task), messages)
    assert messages.create_calls[0]["max_tokens"] == 64
    assert result.response_status == "max_tokens"
    ctrl = controller(tmp_path)
    stopped = FakeMessages(stop_reason="max_tokens")
    ctrl.provider = ClaudeProvider(request, client_factory=_factory(stopped, []))
    exp = asyncio.run(_execute(ctrl, request))
    assert exp.runs[0].result.response_status == "max_tokens"
    assert exp.runs[0].status == "FAILED"


def test_provider_flags_match_adapters_on_this_branch(tmp_path, monkeypatch):
    for name in (
        "WORKBENCH_ENABLE_OPENAI",
        "OPENAI_API_KEY",
        "WORKBENCH_ENABLE_CLAUDE",
        "ANTHROPIC_API_KEY",
        "WORKBENCH_ENABLE_GROK",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(tmp_path / "api.db", test_mode=True)) as client:
        body = client.get("/api/providers").json()
    assert [item["id"] for item in body] == ["mock", "openai", "ollama", "claude", "grok"]
    assert [item["enabled"] for item in body] == [True, False, True, False, False]
    assert "WORKBENCH_ENABLE_CLAUDE" in body[3]["reason"]
    assert "ANTHROPIC_API_KEY" in body[3]["reason"]
    monkeypatch.setenv("WORKBENCH_ENABLE_CLAUDE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")
    with TestClient(create_app(tmp_path / "api-on.db", test_mode=True)) as client:
        enabled = {item["id"]: item["enabled"] for item in client.get("/api/providers").json()}
    assert enabled == {"mock": True, "openai": False, "ollama": True, "claude": True, "grok": False}


def test_replay_without_cloud_consent_is_400(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_ENABLE_CLAUDE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctrl = controller(tmp_path)
    exp = ctrl.build(
        RunRequest(
            task="cloud",
            provider="claude",
            model=MODEL,
            cloud_consent=True,
            artifact_id=None,
        )
    )
    exp.status = "FAILED"
    ctrl.repo.save(exp)
    with TestClient(create_app(ctrl.repo.path, test_mode=True)) as client:
        url = f"/api/experiments/{exp.experiment_id}/replay"
        assert client.post(url, json={}).status_code == 400
        assert client.post(url, json={"cloud_consent": False}).status_code == 400
        assert client.post(url, json={"cloud_consent": True}).status_code == 409


def _execute(ctrl, request):
    async def run():
        exp = ctrl.build(request)
        await ctrl.execute(exp)
        return exp

    return run()
