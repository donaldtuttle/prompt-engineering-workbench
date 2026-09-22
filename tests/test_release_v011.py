import base64
import json
import sqlite3
import tomllib

import pytest
from fastapi.testclient import TestClient

from scripts.restore_release_artifact import restore_bytes
from workbench import __version__
from workbench.app import ROOT, create_app
from workbench.artifacts import ArtifactStore, digest
from workbench.controller import assemble
from workbench.migrate import migrate
from workbench.models import ExportRecord
from workbench.repository import Repository

QOFT_ID = "QOFT_XI_HEX_STANDALONE_v1.1"
LF_HASH = "6ee2dc6f39bbc24aee92656aa74f71020caf7d4ca4c0897a3b14c0b245242db6"
CRLF_HASH = "772bd882431107f5d1f622325a681402efbb05a76bb82df05abb7ffc6d7e0b27"
SCOPE_HASH = "83b31740773a0ec0cc772104bf78fe4209a0161ef58b6ac8ecd20ebd4075a0c2"
ORIGINAL_MANIFEST_HASH = "6bfe67f552222f21b23f2c52e20bb0ed5a4a420872b8502e571ce37c2dbb538d"


def test_restored_qoft_is_valid_with_original_pins():
    store = ArtifactStore(ROOT / "reference/injectors")
    snapshot = store.load(QOFT_ID)
    identity = snapshot.identity
    assert identity.status == "VALID" and identity.diagnostics == []
    assert identity.byte_length == 80140 and identity.line_endings == "LF"
    assert identity.sha256 == identity.expected_sha256 == LF_HASH
    assert identity.scoped_sha256 == identity.expected_scoped_sha256 == SCOPE_HASH
    raw = base64.b64decode(snapshot.bytes_base64)
    assert b"\r" not in raw
    assert raw == (store.root / f"{QOFT_ID}.txt").read_bytes()
    condition = assemble("exact task\r\n ", snapshot)
    assert condition.messages[0].content.encode("utf-8") == raw
    assert condition.messages[1].content == "exact task\r\n "


def test_original_inputs_and_successor_manifest():
    original_bytes = (
        ROOT / "reference/original" / f"{QOFT_ID}.manifest.original.json"
    ).read_bytes()
    original = json.loads(original_bytes)
    successor = json.loads((ROOT / "reference/injectors" / f"{QOFT_ID}.manifest.json").read_bytes())
    assert digest(original_bytes) == ORIGINAL_MANIFEST_HASH
    assert successor == {
        **original,
        "manifest_schema": "workbench-artifact-manifest-v2",
        "required_line_endings": "LF",
    }
    rejected = (ROOT / "reference/rejected" / f"{QOFT_ID}.CRLF.txt").read_bytes()
    assert len(rejected) == 82644 and digest(rejected) == CRLF_HASH
    restored = (ROOT / "reference/injectors" / f"{QOFT_ID}.txt").read_bytes()
    assert restore_bytes(rejected, original) == restored
    provenance = json.loads((ROOT / "docs/restoration-provenance.json").read_bytes())
    assert provenance["source_sha256"] == CRLF_HASH
    assert provenance["target_sha256"] == LF_HASH
    assert provenance["scoped_sha256"] == SCOPE_HASH
    assert provenance["original_manifest_sha256"] == digest(original_bytes)
    assert provenance["successor_manifest_sha256"] == digest(
        (ROOT / "reference/injectors" / f"{QOFT_ID}.manifest.json").read_bytes()
    )
    assert provenance["injector_hash_pins_changed"] is False


def test_restoration_refuses_unreviewed_bytes():
    manifest = json.loads(
        (ROOT / "reference/original" / f"{QOFT_ID}.manifest.original.json").read_bytes()
    )
    with pytest.raises(ValueError, match="Not the reviewed CRLF source"):
        restore_bytes(b"different input\r\n", manifest)


@pytest.mark.parametrize("field", ["full_file_sha256", "expected_byte_length", "scope"])
def test_restoration_fails_if_original_pin_changes(field):
    source = (ROOT / "reference/rejected" / f"{QOFT_ID}.CRLF.txt").read_bytes()
    manifest = json.loads(
        (ROOT / "reference/original" / f"{QOFT_ID}.manifest.original.json").read_bytes()
    )
    if field == "scope":
        manifest["scoped_verification"]["expected_sha256"] = "0" * 64
    else:
        manifest[field] = 0 if field == "expected_byte_length" else "0" * 64
    with pytest.raises(ValueError):
        restore_bytes(source, manifest)


def make_manifest_fixture(tmp_path, data, **metadata):
    # These generated test inputs deliberately match their pins. The test is the independent
    # declared line-ending rule, NOT the validity of the frozen QOFT/demo expected hashes.
    filename = "unrelated-artifact.txt"
    (tmp_path / filename).write_bytes(data)
    manifest = {
        "filename": filename,
        "full_file_sha256": digest(data),
        "expected_byte_length": len(data),
        **metadata,
    }
    (tmp_path / "unrelated-artifact.manifest.json").write_text(json.dumps(manifest))
    return ArtifactStore(tmp_path).load("unrelated-artifact")


@pytest.mark.parametrize(
    "policy,data,status",
    [
        ("LF", b"line\n", "VALID"),
        ("LF", b"line\r\n", "INVALID"),
        ("LF", b"line\r", "INVALID"),
        ("LF", b"no newline", "VALID"),
        ("CRLF", b"line\r\n", "VALID"),
        ("CRLF", b"line\n", "INVALID"),
        ("CRLF", b"one\r\ntwo\n", "INVALID"),
        ("CRLF", b"line\r", "INVALID"),
        ("CRLF", b"no newline", "VALID"),
    ],
)
def test_name_independent_line_ending_policy(tmp_path, policy, data, status):
    snapshot = make_manifest_fixture(
        tmp_path,
        data,
        required_line_endings=policy,
        manifest_schema="workbench-artifact-manifest-v2",
    )
    assert snapshot.identity.status == status
    assert base64.b64decode(snapshot.bytes_base64) == data
    assert (tmp_path / "unrelated-artifact.txt").read_bytes() == data
    if status == "INVALID":
        assert len(snapshot.identity.diagnostics) == 1
        assert "Line-ending policy mismatch" in snapshot.identity.diagnostics[0]


@pytest.mark.parametrize("policy", [None, "lf", "ANY", "", 1, [], {}])
def test_invalid_line_ending_policy_fails_closed(tmp_path, policy):
    snapshot = make_manifest_fixture(tmp_path, b"line\n", required_line_endings=policy)
    assert snapshot.identity.status == "INVALID"
    assert any("Invalid required_line_endings" in d for d in snapshot.identity.diagnostics)


def test_legacy_manifest_without_policy_still_loads(tmp_path):
    snapshot = make_manifest_fixture(tmp_path, b"legacy\r\n")
    assert snapshot.identity.status == "VALID"


@pytest.mark.parametrize("schema", [None, "future-v999", [], 2])
def test_unknown_manifest_schema_fails_closed(tmp_path, schema):
    assert (
        make_manifest_fixture(tmp_path, b"test", manifest_schema=schema).identity.status
        == "INVALID"
    )


def test_no_artifact_name_specific_validation():
    source = (ROOT / "workbench/artifacts.py").read_text()
    assert "QOFT" not in source
    assert "STANDALONE" not in source


def test_release_version_and_declared_dependency():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == __version__ == "0.2.1"
    assert "pydantic>=2.13.5,<3" in project["dependencies"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    app = next(p for p in lock["package"] if p["name"] == project["name"])
    assert app["version"] == "0.2.1"
    assert {"name": "pydantic"} in app["dependencies"]


@pytest.mark.parametrize(
    "fixture", ["v0.1.0-demo-export.json", "v0.1.0-blocked-export.json", "v0.1.1-qoft-export.json"]
)
def test_upgrade_preserves_legacy_records_and_raw_payload(tmp_path, fixture):
    legacy = json.loads((ROOT / "tests/fixtures" / fixture).read_bytes())["experiment"]
    serialized = json.dumps(legacy, ensure_ascii=False)
    path = tmp_path / "upgrade.sqlite3"
    # Construct a v1 database using the original SQL format and a frozen v0.1.0 export,
    # not the new Repository.save path. Explicit migration admits old payloads unchanged.
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO metadata VALUES ('schema_version','1')")
        db.execute(
            "CREATE TABLE experiments (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
            "title TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO experiments VALUES (?, ?, ?, ?, ?)",
            (
                legacy["experiment_id"],
                legacy["created_at"],
                legacy["request"]["title"],
                legacy["status"],
                serialized,
            ),
        )
    with pytest.raises(RuntimeError, match="explicit migration"):
        Repository(path)
    migrate(path)
    with TestClient(create_app(path, test_mode=True)) as client:
        assert client.get("/health").json()["version"] == "0.2.1"
        url = f"/api/experiments/{legacy['experiment_id']}"
        assert client.get(url).json() == legacy
        assert client.get(url + "/export").json()["experiment"] == legacy
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT payload FROM experiments").fetchone()[0] == serialized
        assert (
            db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == "2"
        )
    assert Repository(path).get(legacy["experiment_id"]).model_dump(mode="json") == legacy
    if fixture == "v0.1.0-blocked-export.json":
        assert legacy["runs"][1]["status"] == "BLOCKED"
        assert legacy["artifact"]["identity"]["sha256"] == CRLF_HASH


def test_restored_qoft_api_round_trip(tmp_path):
    import time

    with TestClient(create_app(tmp_path / "qoft.db", test_mode=True)) as client:
        start = client.post(
            "/api/experiments", json={"task": "restored QOFT fixture run", "artifact_id": QOFT_ID}
        )
        assert start.status_code == 202
        key = start.json()["experiment_id"]
        for _ in range(200):
            record = client.get(f"/api/experiments/{key}").json()
            if record["status"] == "COMPLETED":
                break
            time.sleep(0.01)
        assert record["status"] == "COMPLETED"
        exported = client.get(f"/api/experiments/{key}/export").json()
    exp = ExportRecord.model_validate(exported).experiment
    assert all(r.status == "SUCCEEDED" for r in exp.runs)
    assert exp.resolution == "INSUFFICIENT_EVIDENCE"
    assert exp.artifact.identity.sha256 == LF_HASH
    assert digest(base64.b64decode(exp.artifact.bytes_base64)) == LF_HASH
    assert all(r.evaluation is None and r.result.token_usage is None for r in exp.runs)
