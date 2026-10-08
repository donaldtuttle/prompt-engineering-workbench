"""All provider transports are synthetic; no API key, model, or tokenizer service called."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from workbench.app import ROOT, create_app
from workbench.artifacts import ArtifactStore, digest
from workbench.conditions import TOKENIZER_HASH, assemble, with_messages
from workbench.controller import Controller
from workbench.models import Message, Run, RunRequest, TokenMeasurement
from workbench.providers import ClaudeProvider, GrokProvider, OllamaProvider, OllamaRequestError
from workbench.repository import Repository
from workbench.token_parity import ProviderTokenCounter, compare_counts, measure_pair, payload_hash


def request(provider="grok", **kwargs):
    return RunRequest(
        task="same task",
        provider=provider,
        model={
            "grok": "grok-4.7",
            "claude": "claude-sonnet-4-5",
            "openai": "gpt-4o",
            "ollama": "llama3.2",
            "mock": "fixture-echo-v2",
        }[provider],
        cloud_consent=provider in ("grok", "claude", "openai"),
        **kwargs,
    )


def pair(req, texts=("one", "two")):
    runs = []
    for kind, text in zip(("FULL_INJECTOR", "NEUTRAL_LENGTH_CONTROL"), texts, strict=True):
        cond = assemble(req.task).model_copy(
            update={"condition_id": kind, "delivery_mode": req.delivery_mode}
        )
        role = "system" if req.delivery_mode == "SYSTEM_SLOT" else "user"
        cond = with_messages(cond, [Message(role=role, content=text), *cond.messages])
        runs.append(
            Run(experiment_id="fixture", probe_id="fixture", condition_id=kind, condition=cond)
        )
    return runs


class GrokCounts:
    def __init__(self, counts):
        self.counts = iter(counts)
        self.events = []
        self.closed = 0

    def factory(self, **kwargs):
        assert kwargs["api_host"] == "api.x.ai"
        assert ("grpc.enable_retries", 0) in kwargs["channel_options"]
        return self

    async def tokenize_text(self, **kwargs):
        self.events.append(("count", kwargs))
        value = next(self.counts, 7)
        if isinstance(value, Exception):
            raise value
        return list(range(value)) if type(value) is int else value

    async def sample(self, **kwargs):
        self.events.append(("sample", kwargs))
        return {"content": "fixture", "finish_reason": "REASON_STOP", "model": "grok-4.7"}

    async def close(self):
        self.closed += 1


@pytest.mark.parametrize(
    "counts,context,input_status,allowed",
    [
        ([5, 5, 9, 9], "MATCHED", "MATCHED", True),
        ([5, 6, 9, 9], "MISMATCHED", "MATCHED", False),
        ([0, 0, 9, 9], "MATCHED", "MATCHED", True),
        ([5, 5, 9, 10], "MATCHED", "MISMATCHED", False),
        ([{}, 5, 9, 9], "ERROR", "MATCHED", False),
        ([RuntimeError("PRIVATE ERROR TEXT"), 5, 9, 9], "ERROR", "MATCHED", False),
    ],
)
def test_grok_matching_mismatch_and_invalid_counts(counts, context, input_status, allowed):
    req = request()
    fake = GrokCounts(counts)
    provider = GrokProvider(req, fake.factory)
    runs = pair(req, ("Ξ\r\n", " two"))
    originals = [run.condition.model_dump() for run in runs]
    parity = asyncio.run(measure_pair(req, *runs, ProviderTokenCounter(req, provider)))
    assert (parity.context_status, parity.input_status, parity.generation_allowed) == (
        context,
        input_status,
        allowed,
    )
    assert parity.total_provider_input_parity == "NOT_ESTABLISHED"
    assert parity.injector_sha256 == digest("Ξ\r\n".encode())
    assert [r.condition.model_dump() for r in runs] == originals
    assert fake.events[0] == ("count", {"text": "Ξ\r\n", "model": "grok-4.7"})
    assert fake.events[2][1]["text"] == "system\nΞ\r\n\nuser\nsame task"
    assert all(event[0] == "count" for event in fake.events)
    assert fake.closed == 4
    assert "PRIVATE ERROR TEXT" not in parity.model_dump_json()
    assert "o200k" not in parity.model_dump_json()
    if context == "MATCHED":
        assert parity.injector_context.payload_sha256 == payload_hash("Ξ\r\n")


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4o", "MATCHED"),
        ("gpt-4.1-2025-04-14", "MATCHED"),
        ("gpt-4", "UNSUPPORTED"),
        ("gpt-4o-imaginary", "UNSUPPORTED"),
        ("unknown", "UNSUPPORTED"),
    ],
)
def test_openai_mapping_is_explicit_and_offline(model, expected, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("No download or cloud call allowed")

    monkeypatch.setattr("tiktoken.get_encoding", denied)
    req = request("openai").model_copy(update={"model": model})
    parity = asyncio.run(measure_pair(req, *pair(req), ProviderTokenCounter(req, object())))
    assert parity.context_status == expected
    assert parity.generation_allowed == (expected == "MATCHED")
    if expected == "MATCHED":
        assert parity.injector_context.tokenizer_sha256 == TOKENIZER_HASH
        assert parity.injector_context.tokenizer_version == "0.14.0"


@pytest.mark.parametrize("mode", ["SYSTEM_SLOT", "USER_PASTE", "USER_PASTE_WITH_HANDSHAKE"])
def test_claude_uses_count_endpoint_and_actual_transport_adaptation(mode):
    req = request("claude", delivery_mode=mode)
    payloads, options, closed = [], [], []

    async def count_tokens(**payload):
        payloads.append(payload)
        return {"input_tokens": 11}

    async def close():
        closed.append(True)

    def factory(**kwargs):
        options.append(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(count_tokens=count_tokens), close=close)

    runs = pair(req)
    parity = asyncio.run(
        measure_pair(req, *runs, ProviderTokenCounter(req, ClaudeProvider(req, factory)))
    )
    assert parity.generation_allowed
    assert payloads[0] == {"model": req.model, "messages": [{"role": "user", "content": "one"}]}
    if mode == "SYSTEM_SLOT":
        assert payloads[2]["system"] == "one"
        assert payloads[2]["messages"] == [{"role": "user", "content": req.task}]
    else:
        assert payloads[2]["messages"] == [{"role": "user", "content": "one\n\nsame task"}]
    assert parity.injector_context.scope == "isolated_user_message_estimate"
    assert parity.injector_input.scope == "adapted_messages_estimate"
    assert parity.injector_input.payload_sha256 == payload_hash(payloads[2])
    assert all(
        o["base_url"] == "https://api.anthropic.com" and o["max_retries"] == 0 for o in options
    )
    assert len(closed) == 4


@pytest.mark.parametrize("status", [404, 405])
def test_ollama_missing_tokenizer_is_unsupported_without_generation(status):
    req = request("ollama")
    paths = []

    def transport(path, payload, timeout):
        paths.append(path)
        assert payload["model"] == req.model
        raise OllamaRequestError(status)

    provider = OllamaProvider(req, transport)
    parity = asyncio.run(measure_pair(req, *pair(req), ProviderTokenCounter(req, provider)))
    assert parity.context_status == parity.input_status == "UNSUPPORTED"
    assert parity.injector_context.tokens is None
    assert not parity.generation_allowed
    assert paths == ["/api/tokenize"] * 4


def test_ollama_optional_tokenizer_counts_exact_text():
    req = request("ollama")
    seen = []

    def transport(path, payload, timeout):
        seen.append(payload)
        return {"tokens": [1, 2, 3]}

    provider = OllamaProvider(req, transport)
    parity = asyncio.run(measure_pair(req, *pair(req), ProviderTokenCounter(req, provider)))
    assert parity.generation_allowed
    assert seen[0]["content"] == "one"
    assert seen[2]["content"] == "one\nsame task"
    assert parity.injector_input.scope == "newline_joined_text_v1"


@pytest.mark.parametrize(
    "provider,env", [("grok", "WORKBENCH_ENABLE_GROK"), ("claude", "WORKBENCH_ENABLE_CLAUDE")]
)
def test_disabled_provider_never_opens_a_client(provider, env, monkeypatch):
    monkeypatch.delenv(env, raising=False)
    req = request(provider)
    parity = asyncio.run(measure_pair(req, *pair(req), ProviderTokenCounter(req, object())))
    assert parity.context_status == "UNSUPPORTED"
    assert not parity.generation_allowed


def test_timeout_is_evidence_and_does_not_generate():
    class SlowCounter:
        async def count(self, messages, *, context_only):
            await asyncio.sleep(1)

    req = request(timeout_seconds=0.05)
    parity = asyncio.run(measure_pair(req, *pair(req), SlowCounter()))
    assert parity.context_status == parity.input_status == "ERROR"
    assert parity.injector_context.error_type == "TimeoutError"
    assert not parity.generation_allowed


def test_frozen_handshake_does_not_exempt_a_count_error():
    req = request(delivery_mode="USER_PASTE_WITH_HANDSHAKE")
    fake = GrokCounts([5, 5, {}, 9])
    parity = asyncio.run(
        measure_pair(
            req, *pair(req), ProviderTokenCounter(req, GrokProvider(req, fake.factory)), replay=True
        )
    )
    assert parity.context_status == "MATCHED"
    assert parity.input_status == "ERROR"
    assert not parity.generation_allowed


def test_unsupported_tokenizer_blocks_context_lanes_before_generation(tmp_path):
    from workbench.models import ProviderResult

    req = request("ollama")
    generated = []

    class LocalProvider(OllamaProvider):
        async def generate(self, condition):
            generated.append(condition.condition_id)
            return ProviderResult(raw_response="fixture")

    def transport(path, payload, timeout):
        assert path == "/api/tokenize"
        raise OllamaRequestError(404)

    ctrl = Controller(
        Repository(tmp_path / "runs.db"),
        ArtifactStore(ROOT / "reference/injectors"),
        provider=LocalProvider(req, transport),
    )
    exp = ctrl.build(req)
    asyncio.run(ctrl.execute(exp))
    assert generated == ["BASELINE"]
    assert [run.status for run in exp.runs] == ["SUCCEEDED", "BLOCKED", "BLOCKED"]
    assert exp.token_parity[0].context_status == "UNSUPPORTED"
    assert ctrl.repo.get(exp.experiment_id).token_parity == exp.token_parity


def test_equal_numbers_from_different_methods_are_not_parity():
    count = TokenMeasurement(status="COUNTED", tokens=5, method="a", scope="text", uncertainty="")
    assert compare_counts(count, count.model_copy(update={"method": "b"})) == "ERROR"


def test_real_xai_sdk_tokenizer_response_shape_without_network(monkeypatch):
    from xai_sdk.aio.tokenizer import Client
    from xai_sdk.proto import tokenize_pb2

    from workbench.providers import _grok_token_count, _XaiTransport

    response = tokenize_pb2.TokenizeTextResponse(
        tokens=[tokenize_pb2.Token(token_id=4), tokenize_pb2.Token(token_id=7)]
    )
    assert _grok_token_count(response) == 2
    calls = []

    async def tokenize(payload):
        calls.append(payload)
        return response

    async def close():
        pass

    tokenizer_client = Client.__new__(Client)
    tokenizer_client._stub = SimpleNamespace(TokenizeText=tokenize)
    monkeypatch.setattr(
        "xai_sdk.AsyncClient",
        lambda **kwargs: SimpleNamespace(tokenize=tokenizer_client, close=close),
    )
    req = request()
    provider = GrokProvider(req, _XaiTransport)
    parity = asyncio.run(measure_pair(req, *pair(req), ProviderTokenCounter(req, provider)))
    assert parity.context_status == parity.input_status == "MATCHED"
    assert parity.injector_context.tokens == 2
    assert len(calls) == 4
    assert calls[0].text == "one"
    assert calls[0].model == req.model


@pytest.mark.parametrize("bad", ["tokens", b"tokens", [True], [-1], [{}], {"tokens": []}])
def test_grok_rejects_unreadable_sequences(bad):
    from workbench.providers import _grok_token_count

    with pytest.raises(ValueError, match="unreadable"):
        _grok_token_count(bad)


@pytest.mark.parametrize(
    "counts,expected", [([5, 6, 9, 9], "BLOCKED"), ([5, 5, 9, 9], "SUCCEEDED")]
)
def test_controller_checks_before_generation_and_persists_evidence(tmp_path, counts, expected):
    req = request(replicates=2)
    fake = GrokCounts(counts)
    ctrl = Controller(
        Repository(tmp_path / "runs.db"),
        ArtifactStore(ROOT / "reference/injectors"),
        provider=GrokProvider(req, fake.factory),
    )
    exp = ctrl.build(req)
    snapshots = [r.condition.model_dump() for r in exp.runs]
    asyncio.run(ctrl.execute(exp))
    stored = ctrl.repo.get(exp.experiment_id)
    assert len(stored.token_parity) == 2
    assert [r.status for r in stored.runs] == ["SUCCEEDED", expected, expected] * 2
    assert [r.condition.model_dump() for r in exp.runs] == snapshots
    assert all(r.evaluation is None for r in stored.runs)
    assert stored.resolution == "INSUFFICIENT_EVIDENCE"
    first_sample = next(i for i, (event, _) in enumerate(fake.events) if event == "sample")
    assert first_sample == 5  # Four parity counts, then the generation context-limit pre-count.
    assert stored.token_parity[0].injector_context == stored.token_parity[1].injector_context
    if expected == "BLOCKED":
        assert all(not r.calls for r in stored.runs if r.condition_id != "BASELINE")
        assert sum(event == "sample" for event, _ in fake.events) == 2


def test_old_terminal_records_unchanged_and_new_exports_contain_parity(tmp_path):
    path = tmp_path / "runs.db"
    repo = Repository(path)
    ctrl = Controller(repo, ArtifactStore(ROOT / "reference/injectors"))
    old = ctrl.build(RunRequest(task="historical"))
    old.status = "FAILED"
    repo.save(old)
    with repo.connect() as db:
        payload = json.loads(db.execute("SELECT payload FROM experiments").fetchone()[0])
        payload.pop("token_parity")
        original = json.dumps(payload)
        db.execute("UPDATE experiments SET payload=?", (original,))
    assert repo.get(old.experiment_id).token_parity is None
    with TestClient(create_app(path, test_mode=True)) as client:
        assert client.get("/health").json()["status"] == "ok"
        fresh = ctrl.build(RunRequest(task="new"))
        asyncio.run(ctrl.execute(fresh))
        for fmt in ("json", "jsonl"):
            export = client.get(
                f"/api/experiments/{fresh.experiment_id}/export?format={fmt}"
            ).json()
            evidence = export["experiment"]["token_parity"][0]
            assert evidence["context_status"] == "MATCHED"
            assert "Mock fixture only" in evidence["injector_context"]["uncertainty"]
    with repo.connect() as db:
        assert (
            db.execute(
                "SELECT payload FROM experiments WHERE id=?", (old.experiment_id,)
            ).fetchone()[0]
            == original
        )


def test_replay_recounts_and_labels_frozen_handshake_inputs(tmp_path):
    ctrl = Controller(Repository(tmp_path / "runs.db"), ArtifactStore(ROOT / "reference/injectors"))
    exp = ctrl.build(RunRequest(task="replay", delivery_mode="USER_PASTE_WITH_HANDSHAKE"))
    asyncio.run(ctrl.execute(exp))
    replay = ctrl.prepare_replay(exp.experiment_id)
    assert replay.token_parity is None
    asyncio.run(ctrl.execute(replay))
    parity = replay.token_parity[0]
    assert parity.input_phase == "FROZEN_FINAL_PROMPT"
    assert parity.injector_run_id != exp.token_parity[0].injector_run_id
    assert parity.context_status == "MATCHED"
    assert parity.total_provider_input_parity == "NOT_ESTABLISHED"
    assert replay.status == "COMPLETED"
