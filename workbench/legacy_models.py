from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now() -> str:
    return datetime.now(UTC).isoformat()


def uid() -> str:
    return str(uuid4())


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactIdentity(Schema):
    artifact_id: str
    source_path: str
    byte_length: int
    sha256: str
    encoding: str | None = None
    line_endings: str
    loaded_at: str
    status: Literal["VALID", "INVALID"]
    expected_byte_length: int | None = None
    expected_sha256: str | None = None
    scoped_sha256: str | None = None
    expected_scoped_sha256: str | None = None
    manifest_sha256: str | None = None
    diagnostics: list[str] = Field(default_factory=list)


class ArtifactSnapshot(Schema):
    identity: ArtifactIdentity
    bytes_base64: str
    manifest_bytes_base64: str


class Message(Schema):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["system", "user"]
    content: str


class Condition(Schema):
    condition_id: Literal["BASELINE", "FULL_INJECTOR"]
    injector: ArtifactIdentity | None = None
    messages: tuple[Message, ...]
    prompt_hash: str
    prompt_byte_length: int
    assembly_version: Literal["messages-json-v1"] = "messages-json-v1"


class ProviderResult(Schema):
    raw_response: str
    structured_response: dict[str, Any] | None = None
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
    trace_id: str | None = None


class Run(Schema):
    run_id: str = Field(default_factory=uid)
    experiment_id: str
    probe_id: str
    condition_id: Literal["BASELINE", "FULL_INJECTOR"]
    condition: Condition | None = None
    provider: str = "mock"
    model: str = "fixture-echo-v1"
    model_settings: dict[str, Any] = Field(default_factory=lambda: {"deterministic": True})
    execution: Literal["local-offline"] = "local-offline"
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "INTERRUPTED"] = "QUEUED"
    started_at: str | None = None
    ended_at: str | None = None
    latency_ms: float | None = None
    attempts: int = 0
    retries: int = 0
    result: ProviderResult | None = None
    errors: list[str] = Field(default_factory=list)
    evaluation: dict[str, Any] | None = None


class RunRequest(Schema):
    task: str = Field(min_length=1, max_length=20000)
    title: str = Field(default="Untitled experiment", min_length=1, max_length=120)
    probe_id: str = Field(default="manual-probe", min_length=1, max_length=120)
    artifact_id: str | None = "DEMO_OFFLINE_FIXTURE"
    provider: Literal["mock"] = "mock"
    concurrency: int = Field(default=2, ge=1, le=4)
    timeout_seconds: float = Field(default=10, ge=0.05, le=60)
    max_retries: int = Field(default=0, ge=0, le=2)

    @field_validator("task")
    @classmethod
    def check_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank probe; its original whitespace will be preserved.")
        value.encode("utf-8")
        return value


class Experiment(Schema):
    schema_version: Literal["workbench-experiment-v1"] = "workbench-experiment-v1"
    experiment_id: str = Field(default_factory=uid)
    created_at: str = Field(default_factory=now)
    ended_at: str | None = None
    request: RunRequest
    task_sha256: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "INTERRUPTED"] = "QUEUED"
    resolution: Literal["INSUFFICIENT_EVIDENCE"] = "INSUFFICIENT_EVIDENCE"
    evidence_scope: str = "SOFTWARE_FIXTURE_ONLY; no LLM or QOFT mechanism tested"
    artifact: ArtifactSnapshot | None = None
    runs: list[Run] = Field(default_factory=list)


class ExportRecord(Schema):
    export_schema: Literal["workbench-export-v1"] = "workbench-export-v1"
    exported_at: str = Field(default_factory=now)
    experiment: Experiment
