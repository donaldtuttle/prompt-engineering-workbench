from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now() -> str:
    return datetime.now(UTC).isoformat()


def uid() -> str:
    return str(uuid4())


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Identity format stays compatible with preserved v1 snapshots.
from .legacy_models import ArtifactIdentity, ArtifactSnapshot  # noqa: E402,F401

DeliveryMode = Literal["SYSTEM_SLOT", "USER_PASTE", "USER_PASTE_WITH_HANDSHAKE"]
ConditionID = Literal["BASELINE", "FULL_INJECTOR", "NEUTRAL_LENGTH_CONTROL"]


class Message(Schema):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["system", "user", "assistant"]
    content: str


class Condition(Schema):
    condition_id: ConditionID
    injector: ArtifactIdentity | None = None
    delivery_mode: DeliveryMode = "SYSTEM_SLOT"
    messages: tuple[Message, ...]
    prompt_hash: str
    prompt_byte_length: int
    assembly_version: Literal["messages-json-v1"] = "messages-json-v1"
    control_metadata: dict[str, Any] | None = None


class SamplingSettings(Schema):
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    max_output_tokens: int = Field(default=512, ge=16, le=8192)


class ProviderResult(Schema):
    raw_response: str
    structured_response: dict[str, Any] | None = None
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
    trace_id: str | None = None
    resolved_model: str | None = None
    response_id: str | None = None
    response_status: str | None = None


class CallRecord(Schema):
    phase: Literal["HANDSHAKE", "TASK"]
    attempt: int
    prompt_hash: str
    started_at: str
    ended_at: str | None = None
    result: ProviderResult | None = None
    error_type: str | None = None


class Run(Schema):
    run_id: str = Field(default_factory=uid)
    experiment_id: str
    probe_id: str
    condition_id: ConditionID
    condition: Condition | None = None
    final_condition: Condition | None = None
    replicate_index: int = Field(default=0, ge=0)
    delivery_mode: DeliveryMode = "SYSTEM_SLOT"
    provider: str = "mock"
    model: str = "fixture-echo-v2"
    resolved_model: str | None = None
    model_settings: SamplingSettings = Field(default_factory=SamplingSettings)
    configuration_hash: str = ""
    execution_settings: dict[str, int | float] = Field(default_factory=dict)
    provider_versions: dict[str, str] = Field(default_factory=dict)
    seed_supported: bool = True
    execution: Literal["local-offline", "cloud"] = "local-offline"
    replay_of_run_id: str | None = None
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "INTERRUPTED"] = "QUEUED"
    started_at: str | None = None
    ended_at: str | None = None
    latency_ms: float | None = None
    attempts: int = 0
    retries: int = 0
    calls: list[CallRecord] = Field(default_factory=list)
    result: ProviderResult | None = None
    errors: list[str] = Field(default_factory=list)
    evaluation: dict[str, Any] | None = None


class RunRequest(Schema):
    task: str = Field(min_length=1, max_length=20000)
    title: str = Field(default="Untitled experiment", min_length=1, max_length=120)
    probe_id: str = Field(default="manual-probe", min_length=1, max_length=120)
    artifact_id: str | None = "DEMO_OFFLINE_FIXTURE"
    provider: Literal["mock", "openai", "ollama"] = "mock"
    model: str = Field(default="fixture-echo-v2", min_length=1, max_length=160)
    delivery_mode: DeliveryMode = "SYSTEM_SLOT"
    replicates: int = Field(default=1, ge=1, le=4)
    sampling: SamplingSettings = Field(default_factory=SamplingSettings)
    cloud_consent: bool = False
    concurrency: int = Field(default=2, ge=1, le=4)
    timeout_seconds: float = Field(default=30, ge=0.05, le=300, allow_inf_nan=False)
    max_retries: int = Field(default=0, ge=0, le=2)

    @field_validator("task")
    @classmethod
    def check_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonblank probe; original whitespace is preserved.")
        value.encode("utf-8")
        return value

    @model_validator(mode="after")
    def validate_provider(self):
        if self.provider == "mock" and self.model != "fixture-echo-v2":
            raise ValueError("Mock model must be fixture-echo-v2")
        if self.provider == "openai":
            if not self.cloud_consent:
                raise ValueError("Cloud runs require explicit cloud_consent")
            if self.model.startswith("fixture-"):
                raise ValueError("Choose an explicit OpenAI model or snapshot ID")
            if self.sampling.seed is not None:
                raise ValueError("This Responses adapter does not support seed; leave it null")
        if self.provider == "ollama" and self.model.startswith("fixture-"):
            raise ValueError("Choose an installed Ollama model")
        return self


class ReplayRequest(Schema):
    cloud_consent: bool = False


class Experiment(Schema):
    schema_version: Literal["workbench-experiment-v2"] = "workbench-experiment-v2"
    experiment_id: str = Field(default_factory=uid)
    created_at: str = Field(default_factory=now)
    ended_at: str | None = None
    request: RunRequest
    task_sha256: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "INTERRUPTED"] = "QUEUED"
    resolution: Literal["INSUFFICIENT_EVIDENCE"] = "INSUFFICIENT_EVIDENCE"
    evidence_scope: str = "SOFTWARE_FIXTURE_ONLY; no LLM or QOFT mechanism tested"
    artifact: ArtifactSnapshot | None = None
    replay_of_experiment_id: str | None = None
    replay_mode: Literal["FROZEN_FINAL_PROMPT"] | None = None
    runs: list[Run] = Field(default_factory=list)


class ExportRecord(Schema):
    export_schema: Literal["workbench-export-v2"] = "workbench-export-v2"
    exported_at: str = Field(default_factory=now)
    experiment: Experiment
