import asyncio
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from workbench.app import ROOT, create_app
from workbench.artifacts import ArtifactStore, digest
from workbench.controller import Controller, assemble
from workbench.models import RunRequest
from workbench.providers import MockProvider, OllamaProvider, OpenAIProvider
from workbench.repository import Repository

DEMO_HASH = "adb50bebae4e3576c2c96c70866f4d1357888c35b2e13d76d2c88383870fc541"
QOFT_HASH = "772bd882431107f5d1f622325a681402efbb05a76bb82df05abb7ffc6d7e0b27"
QOFT_LF_HASH = "6ee2dc6f39bbc24aee92656aa74f71020caf7d4ca4c0897a3b14c0b245242db6"


@pytest.fixture
def store():
    return ArtifactStore(ROOT / "reference/injectors")


@pytest.fixture
def controller(tmp_path, store):
    return Controller(Repository(tmp_path / "test.sqlite3"), store)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite3", test_mode=True)) as c:
        yield c


def finish(client, experiment_id):
    for _ in range(150):
        record = client.get(f"/api/experiments/{experiment_id}").json()
        if record["status"] not in ("QUEUED", "RUNNING"):
            return record
        time.sleep(0.01)
    pytest.fail("Experiment did not complete")


def copy_fixture(tmp_path):
    for name in ("DEMO_OFFLINE_FIXTURE.txt", "DEMO_OFFLINE_FIXTURE.manifest.json"):
        (tmp_path / name).write_bytes((ROOT / "reference/injectors" / name).read_bytes())
    return ArtifactStore(tmp_path)


def test_frozen_fixture_identity(store):
    snap = store.load("DEMO_OFFLINE_FIXTURE")
    manifest = json.loads(base64.b64decode(snap.manifest_bytes_base64))
    assert manifest["full_file_sha256"] == DEMO_HASH
    assert snap.identity.sha256 == manifest["full_file_sha256"]
    assert snap.identity.status == "VALID"
    assert snap.identity.byte_length == 168
    assert (
        base64.b64decode(snap.bytes_base64)
        == (store.root / "DEMO_OFFLINE_FIXTURE.txt").read_bytes()
    )


def copy_qoft(tmp_path, rejected=False):
    name = "QOFT_XI_HEX_STANDALONE_v1.1"
    manifest_path = ROOT / "reference/injectors" / f"{name}.manifest.json"
    (tmp_path / manifest_path.name).write_bytes(manifest_path.read_bytes())
    source = (
        ROOT / "reference/rejected" / f"{name}.CRLF.txt"
        if rejected
        else ROOT / "reference/injectors" / f"{name}.txt"
    )
    (tmp_path / f"{name}.txt").write_bytes(source.read_bytes())
    return ArtifactStore(tmp_path)


def test_supplied_qoft_rejected_without_repair(tmp_path):
    store = copy_qoft(tmp_path, rejected=True)
    snap = store.load("QOFT_XI_HEX_STANDALONE_v1.1")
    manifest = json.loads(base64.b64decode(snap.manifest_bytes_base64))
    assert snap.identity.sha256 == QOFT_HASH
    assert snap.identity.byte_length == 82644
    assert snap.identity.line_endings == "CRLF"
    assert snap.identity.expected_sha256 == manifest["full_file_sha256"]
    assert snap.identity.status == "INVALID"
    assert len(snap.identity.diagnostics) == 4
    assert (
        snap.identity.expected_scoped_sha256 == manifest["scoped_verification"]["expected_sha256"]
    )
    with pytest.raises(ValueError, match="blocked"):
        assemble("probe", snap)


def test_baseline_and_exact_treatment(store):
    task = "  Ξ probe\r\nKeep this whitespace.\n "
    baseline = assemble(task)
    snapshot = store.load("DEMO_OFFLINE_FIXTURE")
    full = assemble(task, snapshot)
    assert len(baseline.messages) == 1 and baseline.injector is None
    assert baseline.messages[0].content == task
    assert len(full.messages) == 2
    assert full.messages[0].content.encode() == base64.b64decode(snapshot.bytes_base64)
    assert full.messages[1].content == task
    assert baseline.prompt_hash != full.prompt_hash
    assert full.prompt_hash == assemble(task, snapshot).prompt_hash
    serialized = json.dumps(
        [m.model_dump() for m in full.messages], ensure_ascii=False, separators=(",", ":")
    ).encode()
    assert digest(serialized) == full.prompt_hash


@pytest.mark.parametrize("task", ["", " \n ", "x" * 20001])
def test_invalid_task_rejected(client, task):
    assert client.post("/api/experiments", json={"task": task}).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "openai"),
        ("concurrency", 0),
        ("concurrency", 5),
        ("timeout_seconds", 0),
        ("max_retries", 3),
        ("extra", "not allowed"),
    ],
)
def test_invalid_configuration(client, field, value):
    assert client.post("/api/experiments", json={"task": "test", field: value}).status_code == 422


def test_health_home_and_static(client):
    assert client.get("/health").json()["database"] == "ok"
    response = client.get("/")
    assert response.status_code == 200
    assert "Experiment workspace" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_full_api_lifecycle_and_exports(client):
    start = client.post(
        "/api/experiments",
        json={
            "task": "Ξ <script>alert(1)</script>\r\n ",
            "title": "Exact test",
            "probe_id": "p-17",
        },
    )
    assert start.status_code == 202
    key = start.json()["experiment_id"]
    exp = finish(client, key)
    assert exp["status"] == "COMPLETED"
    assert exp["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert [r["status"] for r in exp["runs"]] == ["SUCCEEDED", "SUCCEEDED", "SUCCEEDED"]
    assert len({r["run_id"] for r in exp["runs"]}) == 3
    for run in exp["runs"]:
        assert run["probe_id"] == "p-17" and run["experiment_id"] == key
        assert run["result"]["token_usage"] is None
        assert run["result"]["cost_usd"] is None
        assert run["result"]["trace_id"] is None and run["evaluation"] is None
        assert run["latency_ms"] >= 0
    assert client.get("/api/experiments").json()[0]["experiment_id"] == key
    for fmt in ["json", "jsonl"]:
        response = client.get(f"/api/experiments/{key}/export?format={fmt}")
        record = response.json()
        assert record["export_schema"] == "workbench-export-v2"
        assert record["experiment"] == exp
        assert f".{fmt}" in response.headers["content-disposition"]
        if fmt == "jsonl":
            assert len(response.text.splitlines()) == 1
        raw = base64.b64decode(record["experiment"]["artifact"]["bytes_base64"])
        assert digest(raw) == DEMO_HASH


def test_baseline_only(client):
    key = client.post("/api/experiments", json={"task": "test", "artifact_id": None}).json()[
        "experiment_id"
    ]
    exp = finish(client, key)
    assert exp["artifact"] is None
    assert len(exp["runs"]) == 1 and exp["status"] == "COMPLETED"


def test_invalid_injector_blocks_only_treatment(tmp_path):
    store = copy_qoft(tmp_path, rejected=True)
    with TestClient(create_app(tmp_path / "test.db", store.root, test_mode=True)) as client:
        key = client.post(
            "/api/experiments", json={"task": "test", "artifact_id": "QOFT_XI_HEX_STANDALONE_v1.1"}
        ).json()["experiment_id"]
        exp = finish(client, key)
    assert exp["status"] == "PARTIAL"
    baseline, treatment, control = exp["runs"]
    assert control["status"] == "BLOCKED"
    assert baseline["status"] == "SUCCEEDED"
    assert treatment["status"] == "BLOCKED"
    assert treatment["condition"] is None and treatment["attempts"] == 0
    assert treatment["result"] is None
    assert exp["artifact"]["identity"]["sha256"] == QOFT_HASH


def test_repository_survives_restart(tmp_path, store):
    path = tmp_path / "runs.db"
    first = Repository(path)
    ctrl = Controller(first, store)
    exp = ctrl.build(RunRequest(task="restart test"))
    asyncio.run(ctrl.execute(exp))
    second = Repository(path)
    second.recover()
    assert second.get(exp.experiment_id) == exp


def test_interrupted_recovery_preserves_success(tmp_path, store):
    path = tmp_path / "runs.db"
    repo = Repository(path)
    exp = Controller(repo, store).build(RunRequest(task="interrupted"))
    exp.status = "RUNNING"
    exp.runs[0].status = "SUCCEEDED"
    exp.runs[1].status = "RUNNING"
    repo.save(exp)
    reopened = Repository(path)
    reopened.recover()
    saved = reopened.get(exp.experiment_id)
    assert saved.status == "INTERRUPTED"
    assert [r.status for r in saved.runs] == ["SUCCEEDED", "INTERRUPTED", "INTERRUPTED"]


def test_persisted_partial_results_during_execution(controller):
    seen = []

    class Observer:
        async def generate(self, condition):
            if condition.condition_id == "FULL_INJECTOR":
                seen.append(controller.repo.get(exp.experiment_id).runs[0].status)
            return await MockProvider().generate(condition)

    exp = controller.build(RunRequest(task="serial", concurrency=1))
    controller.provider = Observer()
    asyncio.run(controller.execute(exp))
    assert seen == ["SUCCEEDED"]


def test_timeout_retries_and_lane_isolation(controller):
    class Failure:
        async def generate(self, condition):
            if condition.condition_id == "FULL_INJECTOR":
                await asyncio.sleep(1)
            return await MockProvider().generate(condition)

    controller.provider = Failure()
    exp = controller.build(RunRequest(task="timing", timeout_seconds=0.2, max_retries=1))
    asyncio.run(controller.execute(exp))
    assert exp.status == "PARTIAL"
    assert exp.runs[0].status == "SUCCEEDED"
    assert exp.runs[1].status == "FAILED"
    assert exp.runs[1].attempts == 2 and exp.runs[1].retries == 1
    assert exp.runs[1].errors == ["Attempt 1: TimeoutError", "Attempt 2: TimeoutError"]


def test_error_text_cannot_leak_secrets(controller):
    class Failure:
        async def generate(self, condition):
            raise RuntimeError("FAKE_SECRET_FOR_TEST")

    controller.provider = Failure()
    exp = controller.build(RunRequest(task="safe errors"))
    asyncio.run(controller.execute(exp))
    assert "FAKE_SECRET_FOR_TEST" not in exp.model_dump_json()
    assert exp.status == "FAILED"


def test_global_concurrency_across_experiments(controller):
    class Tracking:
        active = maximum = 0

        async def generate(self, condition):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                return await MockProvider().generate(condition)
            finally:
                self.active -= 1

    tracker = Tracking()
    controller.provider = tracker
    controller.limiter = asyncio.Semaphore(2)
    exps = [controller.build(RunRequest(task=f"probe {i}")) for i in range(4)]

    async def run_all():
        await asyncio.gather(*(controller.execute(e) for e in exps))

    asyncio.run(run_all())
    assert tracker.maximum == 2
    assert all(e.status == "COMPLETED" for e in exps)
    for i, exp in enumerate(exps):
        assert all(r.result.structured_response["task_received"] == f"probe {i}" for r in exp.runs)


def test_shutdown_marks_runs_interrupted(controller):
    async def cancel():
        exp = await controller.create(RunRequest(task="cancel"))
        await asyncio.sleep(0.03)
        await controller.close()
        return controller.repo.get(exp.experiment_id)

    saved = asyncio.run(cancel())
    assert saved.status == "INTERRUPTED"
    assert all(r.status == "INTERRUPTED" for r in saved.runs)


def test_snapshot_isolated_from_later_disk_edits(tmp_path):
    local_store = copy_fixture(tmp_path)
    ctrl = Controller(Repository(tmp_path / "test.db"), local_store)
    exp = ctrl.build(RunRequest(task="snapshot"))
    (tmp_path / "DEMO_OFFLINE_FIXTURE.txt").write_bytes(b"changed after creation")
    asyncio.run(ctrl.execute(exp))
    assert exp.status == "COMPLETED"
    assert exp.artifact.identity.sha256 == DEMO_HASH
    assert local_store.load("DEMO_OFFLINE_FIXTURE").identity.status == "INVALID"


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd", "..\\outside"])
def test_traversal_rejected(store, client, name):
    with pytest.raises(ValueError):
        store.load(name)
    assert (
        client.post("/api/experiments", json={"task": "test", "artifact_id": name}).status_code
        == 400
    )


def test_manifest_filename_traversal_rejected(tmp_path):
    store = copy_fixture(tmp_path)
    manifest_path = tmp_path / "DEMO_OFFLINE_FIXTURE.manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["filename"] = "../outside.txt"
    manifest_path.write_text(json.dumps(manifest))
    snapshot = store.load("DEMO_OFFLINE_FIXTURE")
    assert snapshot.identity.status == "INVALID"
    assert base64.b64decode(snapshot.bytes_base64) == b""


@pytest.mark.parametrize(
    "mutation", ["placeholder", "missing_hash", "bad_offsets", "bad_scope_hash", "array", "json"]
)
def test_bad_manifests_fail_closed(tmp_path, mutation):
    store = copy_fixture(tmp_path)
    path = tmp_path / "DEMO_OFFLINE_FIXTURE.manifest.json"
    manifest = json.loads(path.read_bytes())
    if mutation == "placeholder":
        manifest["full_file_sha256"] = "PASTE_HASH_HERE"
    elif mutation == "missing_hash":
        del manifest["full_file_sha256"]
    elif mutation in ("bad_offsets", "bad_scope_hash"):
        manifest["scoped_verification"] = {
            "algorithm": "sha256",
            "start_offset_zero_based": 0,
            "length_bytes": 99999 if mutation == "bad_offsets" else 168,
            "end_offset_exclusive": 168,
            "expected_sha256": "0" * 64,
        }
    elif mutation == "array":
        manifest = []
    path.write_text("{bad json" if mutation == "json" else json.dumps(manifest))
    assert store.load("DEMO_OFFLINE_FIXTURE").identity.status == "INVALID"


def test_symlink_rejected(tmp_path):
    store = copy_fixture(tmp_path)
    original = tmp_path / "DEMO_OFFLINE_FIXTURE.txt"
    other = tmp_path / "other.txt"
    original.rename(other)
    original.symlink_to(other)
    assert store.load("DEMO_OFFLINE_FIXTURE").identity.status == "INVALID"


def test_cross_origin_and_host_protection(client):
    assert (
        client.post(
            "/api/experiments", json={"task": "test"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/experiments", json={"task": "test"}, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/api/experiments", content="task=test").status_code == 415


def test_body_limit(client):
    assert (
        client.post(
            "/api/experiments", content=b"x" * 131073, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )


def test_unknown_records_and_export_type(client):
    assert client.get("/api/experiments/absent").status_code == 404
    assert client.get("/api/experiments/absent/export").status_code == 404
    assert client.get("/api/experiments/absent/export?format=html").status_code == 400


def test_providers_disabled_without_keys(client):
    providers = client.get("/api/providers").json()
    assert [p["enabled"] for p in providers] == [True, False, False]
    with pytest.raises(NotImplementedError):
        asyncio.run(OllamaProvider().generate(assemble("test")))
    request = RunRequest(task="test", provider="openai", model="test-model", cloud_consent=True)
    with pytest.raises(RuntimeError):
        asyncio.run(OpenAIProvider(request).generate(assemble("test")))


def test_mock_is_deterministic(store):
    condition = assemble("same input", store.load("DEMO_OFFLINE_FIXTURE"))
    one = asyncio.run(MockProvider().generate(condition))
    two = asyncio.run(MockProvider().generate(condition))
    assert one == two


def test_queue_admission_limit(controller):
    controller.reserved = 16
    with pytest.raises(RuntimeError, match="Queue is full"):
        asyncio.run(controller.create(RunRequest(task="over capacity")))


def test_database_schema_guard(tmp_path):
    path = tmp_path / "test.db"
    repo = Repository(path)
    with repo.connect() as db:
        db.execute("UPDATE metadata SET value='99' WHERE key='schema_version'")
    with pytest.raises(RuntimeError, match="Unsupported database schema"):
        Repository(path)


def test_valid_scoped_verification(tmp_path):
    store = copy_fixture(tmp_path)
    path = tmp_path / "DEMO_OFFLINE_FIXTURE.manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["scoped_verification"] = {
        "algorithm": "sha256",
        "start_offset_zero_based": 0,
        "length_bytes": 168,
        "end_offset_exclusive": 168,
        "expected_sha256": DEMO_HASH,
    }
    path.write_text(json.dumps(manifest))
    snap = store.load("DEMO_OFFLINE_FIXTURE")
    assert snap.identity.status == "VALID"
    assert snap.identity.scoped_sha256 == DEMO_HASH


@pytest.mark.parametrize(
    "content", [b"\xffinvalid utf8", b"\xef\xbb\xbfBOM", b"altered\r\n", b"x" * 2_000_001]
)
def test_bad_artifact_bytes_rejected_without_rewrite(tmp_path, content):
    store = copy_fixture(tmp_path)
    path = tmp_path / "DEMO_OFFLINE_FIXTURE.txt"
    path.write_bytes(content)
    assert store.load("DEMO_OFFLINE_FIXTURE").identity.status == "INVALID"
    assert path.read_bytes() == content


def test_malformed_origin_denied(client):
    assert (
        client.post(
            "/api/experiments", json={"task": "test"}, headers={"Origin": "http://[invalid"}
        ).status_code
        == 403
    )
