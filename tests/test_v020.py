import asyncio
import base64
import json
import sqlite3
import threading
import time

import httpx2
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from workbench.app import ROOT, create_app
from workbench.artifacts import ArtifactStore, digest
from workbench.conditions import HANDSHAKE, assemble, tokenizer, verify_condition
from workbench.controller import Controller, configuration_hash
from workbench.migrate import migrate
from workbench.models import Message, RunRequest, SamplingSettings
from workbench.providers import MockProvider, OpenAIProvider
from workbench.repository import Repository

MODES = ["SYSTEM_SLOT", "USER_PASTE", "USER_PASTE_WITH_HANDSHAKE"]


def controller(tmp_path):
    return Controller(Repository(tmp_path / "runs.db"), ArtifactStore(ROOT / "reference/injectors"))


def completed(ctrl, request):
    exp = ctrl.build(request)
    asyncio.run(ctrl.execute(exp))
    return exp


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("artifact", ["DEMO_OFFLINE_FIXTURE", "QOFT_XI_HEX_STANDALONE_v1.1"])
def test_exact_context_and_token_length_control(tmp_path, mode, artifact):
    ctrl = controller(tmp_path)
    exp = ctrl.build(RunRequest(task="  exact\r\n ", artifact_id=artifact, delivery_mode=mode))
    baseline, full, neutral = [r.condition for r in exp.runs]
    assert full.messages[0].content.encode() == base64.b64decode(exp.artifact.bytes_base64)
    assert full.messages[0].role == ("system" if mode == "SYSTEM_SLOT" else "user")
    assert len(tokenizer().encode(full.messages[0].content)) == len(
        tokenizer().encode(neutral.messages[0].content)
    )
    assert baseline.messages[-1].content == (
        HANDSHAKE if mode.endswith("HANDSHAKE") else exp.request.task
    )
    for run in exp.runs:
        verify_condition(run.condition)
        repeat = assemble(exp.request.task, exp.artifact, kind=run.condition_id, delivery_mode=mode)
        assert repeat == run.condition


def test_bundled_tokenizer_needs_no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network access")

    monkeypatch.setattr("urllib.request.urlopen", denied)
    monkeypatch.setattr("requests.get", denied)
    tokenizer.cache_clear()
    assert len(tokenizer().encode(" stone" * 19)) == 19


@pytest.mark.parametrize("mode", MODES)
def test_replicates_settings_and_transcripts(tmp_path, mode):
    ctrl = controller(tmp_path)
    exp = completed(
        ctrl,
        RunRequest(
            task="secret final task",
            delivery_mode=mode,
            replicates=2,
            sampling=SamplingSettings(seed=42, temperature=0.3),
        ),
    )
    assert exp.status == "COMPLETED"
    assert [r.replicate_index for r in exp.runs] == [0, 0, 0, 1, 1, 1]
    assert len({r.run_id for r in exp.runs}) == 6
    for run in exp.runs:
        assert run.model_settings.seed == 42
        assert run.resolved_model == "fixture-echo-v2"
        assert configuration_hash(run) == run.configuration_hash
        assert run.result.structured_response["task_received"] == exp.request.task
        assert len(run.calls) == (2 if mode.endswith("HANDSHAKE") else 1)
        if mode.endswith("HANDSHAKE"):
            assert all(exp.request.task not in m.content for m in run.condition.messages)
            assert run.calls[0].phase == "HANDSHAKE"
            assert run.final_condition.messages[-2].role == "assistant"
            assert run.final_condition.messages[-2].content == run.calls[0].result.raw_response
            assert run.final_condition.prompt_hash != run.condition.prompt_hash
        verify_condition(run.final_condition)


@pytest.mark.parametrize("mode", MODES)
def test_replay_uses_stored_final_prompt_after_disk_changes(tmp_path, mode):
    ctrl = controller(tmp_path)
    exp = completed(ctrl, RunRequest(task="frozen", delivery_mode=mode))
    ctrl.artifacts = ArtifactStore(tmp_path / "missing-references")
    replay = ctrl.prepare_replay(exp.experiment_id)
    assert replay.experiment_id != exp.experiment_id
    assert replay.replay_of_experiment_id == exp.experiment_id
    assert replay.artifact == exp.artifact
    asyncio.run(ctrl.execute(replay))
    for before, after in zip(exp.runs, replay.runs, strict=True):
        assert after.replay_of_run_id == before.run_id
        assert after.final_condition == before.final_condition
        assert after.result.raw_response == before.result.raw_response
        assert [c.phase for c in after.calls] == ["TASK"]
        assert after.configuration_hash == before.configuration_hash


@pytest.mark.parametrize("target", ["task", "prompt", "artifact", "manifest", "settings", "sdk"])
def test_replay_rejects_tampered_snapshot(tmp_path, target):
    ctrl = controller(tmp_path)
    exp = completed(ctrl, RunRequest(task="frozen"))
    if target == "task":
        exp.request.task = "tampered"
    elif target == "prompt":
        exp.runs[0].final_condition.messages = (Message(role="user", content="tampered"),)
    elif target == "artifact":
        exp.artifact.bytes_base64 = base64.b64encode(b"tampered").decode()
    elif target == "manifest":
        exp.artifact.manifest_bytes_base64 = base64.b64encode(b"{}").decode()
    elif target == "settings":
        exp.runs[0].model_settings.max_output_tokens += 1
    else:
        exp.runs[0].provider_versions = {"invented-sdk": "99"}
        exp.runs[0].configuration_hash = configuration_hash(exp.runs[0])
    ctrl.repo.save(exp)
    with pytest.raises(ValueError):
        ctrl.prepare_replay(exp.experiment_id)


def test_replay_preserves_blocked_lane(tmp_path):
    ctrl = controller(tmp_path)
    exp = completed(ctrl, RunRequest(task="blocked"))
    exp.runs[1].condition = exp.runs[1].final_condition = None
    exp.runs[1].status = "BLOCKED"
    exp.runs[1].errors = ["preserved failure"]
    ctrl.repo.save(exp)
    replay = ctrl.prepare_replay(exp.experiment_id)
    assert replay.runs[1].status == "BLOCKED"
    assert replay.runs[1].condition is None


def test_replay_refuses_missing_handshake_and_active_record(tmp_path):
    ctrl = controller(tmp_path)
    exp = ctrl.build(RunRequest(task="test", delivery_mode="USER_PASTE_WITH_HANDSHAKE"))
    ctrl.repo.save(exp)
    with pytest.raises(ValueError, match="terminal"):
        ctrl.prepare_replay(exp.experiment_id)
    exp.status = "FAILED"
    ctrl.repo.save(exp)
    with pytest.raises(ValueError, match="captured final"):
        ctrl.prepare_replay(exp.experiment_id)


def test_queue_reservation_is_atomic_before_threaded_preparation(tmp_path):
    ctrl = controller(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = ctrl.build
    calls = 0
    lock = threading.Lock()

    def slow(request):
        nonlocal calls
        with lock:
            calls += 1
            if calls == 1:
                entered.set()
        assert release.wait(5)
        return original(request)

    ctrl.build = slow

    async def exercise():
        pending = [
            asyncio.create_task(ctrl.create(RunRequest(task=str(i), artifact_id=None)))
            for i in range(17)
        ]
        assert await asyncio.to_thread(entered.wait, 5)
        assert ctrl.reserved == 16 and ctrl.jobs == {}
        release.set()
        results = await asyncio.gather(*pending, return_exceptions=True)
        assert sum(isinstance(r, RuntimeError) for r in results) == 1
        await ctrl.close()
        assert ctrl.reserved == 0 and not ctrl.jobs

    asyncio.run(exercise())


def test_creation_failure_releases_reservation(tmp_path):
    ctrl = controller(tmp_path)

    async def exercise():
        with pytest.raises(OSError):
            await ctrl.create(RunRequest(task="x", artifact_id="missing"))
        assert ctrl.reserved == 0 and not ctrl.jobs

    asyncio.run(exercise())


def test_threaded_io_does_not_block_loop(tmp_path):
    ctrl = controller(tmp_path)
    original = ctrl.repo.save
    threads, ticks = [], []

    async def exercise():
        loop_thread = threading.get_ident()

        def slow_save(exp):
            threads.append(threading.get_ident())
            assert threads[-1] != loop_thread
            time.sleep(0.03)
            original(exp)

        ctrl.repo.save = slow_save

        async def ticker():
            for _ in range(35):
                ticks.append(time.perf_counter())
                await asyncio.sleep(0.01)

        exp, _ = await asyncio.gather(
            ctrl.create(RunRequest(task="io", artifact_id=None)), ticker()
        )
        if exp.experiment_id in ctrl.jobs:
            await ctrl.jobs[exp.experiment_id]
        assert exp.status == "COMPLETED"
        assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.12
        await ctrl.close()

    asyncio.run(exercise())
    assert len(threads) >= 5


def test_cancel_during_preparation_persists_interrupted_and_releases_slot(tmp_path):
    ctrl = controller(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = ctrl.build

    def slow(request):
        entered.set()
        assert release.wait(3)
        return original(request)

    ctrl.build = slow

    async def exercise():
        pending = asyncio.create_task(ctrl.create(RunRequest(task="cancel", artifact_id=None)))
        assert await asyncio.to_thread(entered.wait, 3)
        pending.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert ctrl.reserved == 0 and not ctrl.jobs
        assert ctrl.repo.history()[0]["status"] == "INTERRUPTED"

    asyncio.run(exercise())


def test_immediate_shutdown_leaves_no_queued_lanes(tmp_path):
    ctrl = controller(tmp_path)

    async def exercise():
        exp = await ctrl.create(RunRequest(task="shutdown", artifact_id=None))
        await ctrl.close()
        saved = ctrl.repo.get(exp.experiment_id)
        assert saved.status == "INTERRUPTED"
        assert all(r.status == "INTERRUPTED" for r in saved.runs)

    asyncio.run(exercise())


def response_payload(*, usage=True, status="completed"):
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 0,
        "model": "returned-snapshot-2026-09-19",
        "status": status,
        "output": [
            {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Fixture answer", "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 31, "output_tokens": 4, "total_tokens": 35} if usage else None,
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("usage", [True, False])
def test_real_agents_sdk_through_mock_http_transport(tmp_path, monkeypatch, mode, usage):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    seen = []

    def transport(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=response_payload(usage=usage))

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(transport), trust_env=False
            ),
        )

    request = RunRequest(
        task="exact task",
        provider="openai",
        model="gpt-4o",
        cloud_consent=True,
        delivery_mode=mode,
        sampling=SamplingSettings(temperature=0.2, top_p=0.8, max_output_tokens=123),
    )
    ctrl = controller(tmp_path)
    ctrl.provider = OpenAIProvider(request, client_factory=factory)
    exp = completed(ctrl, request)
    assert exp.status == "COMPLETED"
    assert len(seen) == (6 if mode.endswith("HANDSHAKE") else 3)
    for body in seen:
        assert body["model"] == "gpt-4o"
        assert body["temperature"] == 0.2 and body["top_p"] == 0.8
        assert body["max_output_tokens"] == 123
        assert body["store"] is False and body["truncation"] == "disabled"
        assert body.get("tools") == [] and not body.get("instructions")
        assert "seed" not in body and "previous_response_id" not in body
    expected_inputs = [
        [m.model_dump() for m in condition.messages]
        for run in exp.runs
        for condition in (
            [run.condition, run.final_condition] if mode.endswith("HANDSHAKE") else [run.condition]
        )
    ]
    assert sorted(json.dumps(x, sort_keys=True) for x in expected_inputs) == sorted(
        json.dumps(x["input"], sort_keys=True) for x in seen
    )
    for run in exp.runs:
        assert run.resolved_model == "returned-snapshot-2026-09-19"
        assert run.result.token_usage == (
            {"input_tokens": 31, "output_tokens": 4, "total_tokens": 35} if usage else None
        )
        assert run.result.cost_usd is None and run.result.trace_id is None
        assert run.result.response_id == "resp_fixture"
        assert run.provider_versions["openai-agents"] == "0.22.3"
    assert "synthetic-test-key" not in exp.model_dump_json()


def test_cloud_missing_key_disabled_and_seed_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WORKBENCH_ENABLE_OPENAI", raising=False)
    with TestClient(create_app(tmp_path / "api.db", test_mode=True)) as client:
        assert not client.get("/api/providers").json()[1]["enabled"]
        req = {"task": "test", "provider": "openai", "model": "explicit-model"}
        assert client.post("/api/experiments", json=req).status_code == 422
        req["cloud_consent"] = True
        assert client.post("/api/experiments", json=req).status_code == 400
        req["sampling"] = {"seed": 42}
        assert client.post("/api/experiments", json=req).status_code == 422


def test_http_errors_do_not_leak_and_hidden_retries_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    seen = []

    def transport(request):
        seen.append(1)
        return httpx2.Response(
            429, json={"error": {"message": "sensitive-echo", "type": "rate_limit_error"}}
        )

    def factory(**kwargs):
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(transport), trust_env=False
            ),
        )

    request = RunRequest(
        task="error",
        provider="openai",
        model="gpt-4o",
        cloud_consent=True,
        artifact_id=None,
        max_retries=1,
    )
    ctrl = controller(tmp_path)
    ctrl.provider = OpenAIProvider(request, factory)
    exp = completed(ctrl, request)
    assert exp.status == "FAILED" and len(seen) == 2
    assert "sensitive-echo" not in exp.model_dump_json()
    assert len(exp.runs[0].calls) == 2


def test_d7_manifest_only_changed_line_endings_and_attestation_is_separate():
    name = "QOFT_XI_HEX_STANDALONE_v1.1"
    before = (ROOT / "reference/original" / f"{name}.manifest.v0.1.1.json").read_bytes()
    after = (ROOT / "reference/injectors" / f"{name}.manifest.json").read_bytes()
    assert after == before.replace(b"\r\n", b"\n") and b"\r" not in after
    report = json.loads((ROOT / "docs/restoration-provenance.json").read_bytes())
    historical = json.loads((ROOT / "docs/history/restoration-provenance-v0.1.1.json").read_bytes())
    assert report["successor_manifest_sha256"] == digest(after)
    assert historical["successor_manifest_sha256"] == digest(before)
    assert report["independent_original_LF_copy_accessed"] is False
    assert report["reviewer_attestation"]["independently_reperformed_by_this_build"] is False


def test_migration_backup_preserves_payload_and_rejects_future_schema(tmp_path):
    path = tmp_path / "old.db"
    fixture = json.loads((ROOT / "tests/fixtures/v0.1.0-demo-export.json").read_bytes())[
        "experiment"
    ]
    payload = json.dumps(fixture)
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);"
            "INSERT INTO metadata VALUES('schema_version','1');"
            "CREATE TABLE experiments(id TEXT PRIMARY KEY, created_at TEXT NOT NULL,"
            "title TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);"
        )
        db.execute(
            "INSERT INTO experiments VALUES(?,?,?,?,?)",
            (fixture["experiment_id"], fixture["created_at"], "legacy", fixture["status"], payload),
        )
    backup = migrate(path)
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT value FROM metadata").fetchone()[0] == "1"
        assert db.execute("SELECT payload FROM experiments").fetchone()[0] == payload
    assert migrate(path) is None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT payload FROM experiments").fetchone()[0] == payload
        db.execute("UPDATE metadata SET value='99'")
    with pytest.raises(ValueError):
        migrate(path)


def test_utc_storage_invariant(tmp_path):
    ctrl = controller(tmp_path)
    exp = ctrl.build(RunRequest(task="utc", artifact_id=None))
    exp.created_at = "2026-09-19T01:00:00-07:00"
    with pytest.raises(ValueError, match="UTC"):
        ctrl.repo.save(exp)


@pytest.mark.parametrize(
    "settings",
    [
        {"replicates": 5},
        {"delivery_mode": "unknown"},
        {"sampling": {"temperature": -1}},
        {"sampling": {"top_p": 0}},
        {"sampling": {"seed": -1}},
        {"sampling": {"max_output_tokens": 99999}},
    ],
)
def test_v2_request_constraints(settings):
    with pytest.raises(ValueError):
        RunRequest(task="test", **settings)


def test_cancel_during_initial_write_waits_and_persists_interruption(tmp_path):
    ctrl = controller(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = ctrl.repo.save
    count = 0

    def paused(exp):
        nonlocal count
        count += 1
        if count == 1:
            entered.set()
            assert release.wait(3)
        original(exp)

    ctrl.repo.save = paused

    async def exercise():
        pending = asyncio.create_task(ctrl.create(RunRequest(task="save cancel", artifact_id=None)))
        assert await asyncio.to_thread(entered.wait, 3)
        pending.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert ctrl.repo.history()[0]["status"] == "INTERRUPTED"
        assert ctrl.reserved == 0

    asyncio.run(exercise())


def test_failed_task_preserves_successful_handshake(tmp_path):
    ctrl = controller(tmp_path)

    class SecondCallFails:
        async def generate(self, condition):
            if condition.messages[-1].content == "final task":
                raise RuntimeError("sensitive error")
            return await MockProvider().generate(condition)

    ctrl.provider = SecondCallFails()
    exp = completed(
        ctrl,
        RunRequest(task="final task", delivery_mode="USER_PASTE_WITH_HANDSHAKE", artifact_id=None),
    )
    run = exp.runs[0]
    assert run.status == "FAILED"
    assert run.calls[0].result is not None and run.calls[1].error_type == "RuntimeError"
    assert run.final_condition is not None
    assert "sensitive error" not in exp.model_dump_json()
    assert ctrl.prepare_replay(exp.experiment_id).runs[0].condition == run.final_condition


def test_unversioned_database_refused(tmp_path):
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(RuntimeError, match="Unversioned"):
        Repository(path)
    with sqlite3.connect(path) as db:
        assert [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")] == [
            "unrelated"
        ]


def test_request_execution_mismatch_refuses_replay(tmp_path):
    ctrl = controller(tmp_path)
    exp = completed(ctrl, RunRequest(task="settings"))
    exp.request.timeout_seconds = 180
    ctrl.repo.save(exp)
    with pytest.raises(ValueError, match="disagree"):
        ctrl.prepare_replay(exp.experiment_id)


def test_incomplete_provider_output_does_not_succeed(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")

    def transport(request):
        return httpx2.Response(200, json=response_payload(status="incomplete"))

    def factory(**kwargs):
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(transport), trust_env=False
            ),
        )

    request = RunRequest(
        task="incomplete", artifact_id=None, provider="openai", model="gpt-4o", cloud_consent=True
    )
    ctrl = controller(tmp_path)
    ctrl.provider = OpenAIProvider(request, factory)
    exp = completed(ctrl, request)
    assert exp.status == "FAILED"
    # The pinned SDK raises before returning incomplete output to the adapter.
    assert exp.runs[0].result is None
    assert exp.runs[0].calls[0].error_type == "ModelBehaviorError"


def test_replay_api_cloud_requires_fresh_consent(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKBENCH_ENABLE_OPENAI", raising=False)
    ctrl = controller(tmp_path)
    exp = ctrl.build(
        RunRequest(
            task="cloud", provider="openai", model="explicit", cloud_consent=True, artifact_id=None
        )
    )
    exp.status = "FAILED"
    ctrl.repo.save(exp)
    with TestClient(create_app(ctrl.repo.path, test_mode=True)) as client:
        url = f"/api/experiments/{exp.experiment_id}/replay"
        assert client.post(url, json={}).status_code == 400
        assert client.post(url, json={"cloud_consent": True}).status_code == 409
