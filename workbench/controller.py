import asyncio
import base64
import json
from time import perf_counter

from .artifacts import ArtifactStore, digest
from .conditions import assemble, verify_condition, with_messages
from .models import CallRecord, Experiment, Message, ProviderResult, Run, RunRequest, now
from .providers import (
    ClaudeProvider,
    MockProvider,
    OpenAIProvider,
    claude_available,
    cloud_available,
    provider_versions,
)
from .repository import Repository


def configuration_hash(run):
    config = {
        "provider": run.provider,
        "model": run.model,
        "model_settings": run.model_settings.model_dump(),
        "delivery_mode": run.delivery_mode,
        "replicate_index": run.replicate_index,
        "provider_versions": run.provider_versions,
        "execution_settings": run.execution_settings,
        "api_mode": {"openai": "responses", "claude": "messages"}.get(run.provider, "fixture"),
        "tracing": False,
        "tools": [],
        "store": False,
    }
    return digest(json.dumps(config, sort_keys=True, separators=(",", ":")).encode())


def _default_provider(request):
    if request.provider == "openai":
        return OpenAIProvider(request)
    if request.provider == "claude":
        return ClaudeProvider(request)
    return MockProvider(request)


class Controller:
    def __init__(self, repo: Repository, artifacts: ArtifactStore, provider=None, global_limit=4):
        self.repo, self.artifacts, self.provider = repo, artifacts, provider
        self.limiter = asyncio.Semaphore(global_limit)
        self.jobs = {}
        self.reserved = 0
        self.admission = asyncio.Lock()
        self.closing = False
        self.creations = set()

    def build(self, request: RunRequest) -> Experiment:
        """Pure synchronous preparation; API calls this only on a worker thread."""
        snapshot = self.artifacts.load(request.artifact_id) if request.artifact_id else None
        exp = Experiment(
            request=request, task_sha256=digest(request.task.encode()), artifact=snapshot
        )
        if request.provider in ("openai", "claude"):
            exp.evidence_scope = "UNBLINDED_MODEL_OUTPUT; evaluation not performed"
        kinds = (
            ["BASELINE", "FULL_INJECTOR", "NEUTRAL_LENGTH_CONTROL"] if snapshot else ["BASELINE"]
        )
        for replicate in range(request.replicates):
            for kind in kinds:
                run = Run(
                    experiment_id=exp.experiment_id,
                    probe_id=request.probe_id,
                    condition_id=kind,
                    replicate_index=replicate,
                    delivery_mode=request.delivery_mode,
                    provider=request.provider,
                    model=request.model,
                    model_settings=request.sampling.model_copy(deep=True),
                    execution_settings={
                        "timeout_seconds": request.timeout_seconds,
                        "max_retries": request.max_retries,
                        "concurrency": request.concurrency,
                    },
                    provider_versions=provider_versions(request.provider),
                    seed_supported=request.provider == "mock",
                    execution=(
                        "cloud" if request.provider in ("openai", "claude") else "local-offline"
                    ),
                )
                run.configuration_hash = configuration_hash(run)
                if snapshot and kind != "BASELINE" and snapshot.identity.status != "VALID":
                    run.status, run.ended_at = "BLOCKED", now()
                    run.errors = list(snapshot.identity.diagnostics)
                else:
                    run.condition = assemble(
                        request.task, snapshot, kind=kind, delivery_mode=request.delivery_mode
                    )
                exp.runs.append(run)
        return exp

    async def _admit(self):
        async with self.admission:
            if self.closing or self.reserved >= 16:
                raise RuntimeError("Queue is full or shutting down (16 experiments maximum)")
            self.reserved += 1

    async def create(self, request, replay_id=None):
        if request.provider == "openai" and not cloud_available():
            raise ValueError("OpenAI is disabled or its server-side key is missing")
        if request.provider == "claude" and not claude_available():
            raise ValueError("Claude is disabled or its server-side key is missing")
        await self._admit()
        owner = asyncio.current_task()
        self.creations.add(owner)
        transferred = False
        # Shield preparation so a disconnected request cannot leave a worker writing after shutdown.
        preparation = asyncio.create_task(
            asyncio.to_thread(
                self.prepare_replay if replay_id else self.build, replay_id or request
            )
        )
        exp = None
        try:
            exp = await asyncio.shield(preparation)
            initial_write = asyncio.create_task(
                asyncio.to_thread(self.repo.save, exp.model_copy(deep=True))
            )
            try:
                await asyncio.shield(initial_write)
            except asyncio.CancelledError:
                await initial_write
                raise
            task = asyncio.create_task(self.execute(exp))
            self.jobs[exp.experiment_id] = task
            transferred = True

            def finished(done):
                self.jobs.pop(exp.experiment_id, None)
                self.reserved -= 1
                if not done.cancelled():
                    done.exception()  # retrieved; failures retain startup recovery path

            task.add_done_callback(finished)
            return exp
        except asyncio.CancelledError:
            if exp is None:
                exp = await preparation
            exp.status, exp.ended_at = "INTERRUPTED", now()
            for run in exp.runs:
                if run.status == "QUEUED":
                    run.status, run.ended_at = "INTERRUPTED", now()
            await asyncio.to_thread(self.repo.save, exp)
            raise
        finally:
            self.creations.discard(owner)
            if not transferred:
                self.reserved -= 1

    def prepare_replay(self, experiment_id):
        old = self.repo.get(experiment_id)
        if not isinstance(old, Experiment):
            raise ValueError("v1 lacks the v2 execution contract; use Reuse setup")
        if old.status in ("QUEUED", "RUNNING"):
            raise ValueError("Replay requires a terminal source experiment")
        if old.task_sha256 != digest(old.request.task.encode()):
            raise ValueError("Stored task hash mismatch")
        if old.artifact:
            raw = base64.b64decode(old.artifact.bytes_base64, validate=True)
            manifest = base64.b64decode(old.artifact.manifest_bytes_base64, validate=True)
            if (
                digest(raw) != old.artifact.identity.sha256
                or len(raw) != old.artifact.identity.byte_length
            ):
                raise ValueError("Stored artifact hash mismatch")
            if digest(manifest) != old.artifact.identity.manifest_sha256:
                raise ValueError("Stored manifest hash mismatch")
        exp = Experiment(
            request=old.request.model_copy(deep=True),
            task_sha256=old.task_sha256,
            artifact=old.artifact.model_copy(deep=True) if old.artifact else None,
            evidence_scope=old.evidence_scope,
            replay_of_experiment_id=experiment_id,
            replay_mode="FROZEN_FINAL_PROMPT",
        )
        for source in old.runs:
            expected_execution = {
                "timeout_seconds": old.request.timeout_seconds,
                "max_retries": old.request.max_retries,
                "concurrency": old.request.concurrency,
            }
            if (
                source.execution_settings != expected_execution
                or source.provider != old.request.provider
                or source.model != old.request.model
                or source.model_settings != old.request.sampling
            ):
                raise ValueError("Stored request and execution contract disagree")
            if configuration_hash(source) != source.configuration_hash:
                raise ValueError("Stored configuration hash mismatch")
            if source.provider_versions != provider_versions(source.provider):
                raise ValueError("Provider SDK versions changed; exact replay refused")
            if source.condition:
                verify_condition(source.condition)
            final = source.final_condition or source.condition
            if (
                source.status != "BLOCKED"
                and source.delivery_mode == "USER_PASTE_WITH_HANDSHAKE"
                and source.final_condition is None
            ):
                raise ValueError("Handshake source lacks a captured final prompt")
            if final:
                verify_condition(final)
            run = Run(
                experiment_id=exp.experiment_id,
                probe_id=source.probe_id,
                condition_id=source.condition_id,
                condition=final.model_copy(deep=True) if final else None,
                replicate_index=source.replicate_index,
                delivery_mode=source.delivery_mode,
                provider=source.provider,
                model=source.model,
                model_settings=source.model_settings.model_copy(deep=True),
                configuration_hash=source.configuration_hash,
                execution_settings=dict(source.execution_settings),
                provider_versions=source.provider_versions,
                seed_supported=source.seed_supported,
                execution=source.execution,
                replay_of_run_id=source.run_id,
            )
            if source.status == "BLOCKED":
                run.status, run.ended_at, run.errors = "BLOCKED", now(), list(source.errors)
            exp.runs.append(run)
        return exp

    async def execute(self, exp):
        persistence = asyncio.Lock()

        async def save():
            async with persistence:
                snapshot = exp.model_copy(deep=True)
                # Await completion even during cancellation; never overlap writes out of order.
                write = asyncio.create_task(asyncio.to_thread(self.repo.save, snapshot))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    await write
                    raise

        exp.status = "RUNNING"
        local_limit = asyncio.Semaphore(exp.request.concurrency)
        provider = self.provider or _default_provider(exp.request)

        async def call(run, condition, phase):
            record = CallRecord(
                phase=phase,
                attempt=run.attempts,
                prompt_hash=condition.prompt_hash,
                started_at=now(),
            )
            run.calls.append(record)
            await save()
            try:
                record.result = await provider.generate(condition.model_copy(deep=True))
                return record.result
            except BaseException as exc:
                record.error_type = type(exc).__name__
                gate = getattr(exc, "receive_gate", None)
                if isinstance(gate, dict) and record.result is None:
                    record.result = ProviderResult(
                        raw_response="",
                        structured_response={"receive_gate": gate},
                    )
                raise
            finally:
                record.ended_at = now()
                await save()

        async def lane(run):
            if run.status == "BLOCKED":
                return
            async with local_limit, self.limiter:
                run.status, run.started_at = "RUNNING", now()
                begin = perf_counter()
                await save()
                try:
                    for attempt in range(exp.request.max_retries + 1):
                        run.attempts, run.retries = attempt + 1, attempt
                        try:
                            async with asyncio.timeout(exp.request.timeout_seconds):
                                verify_condition(run.condition)
                                final = run.condition
                                if (
                                    run.delivery_mode == "USER_PASTE_WITH_HANDSHAKE"
                                    and not exp.replay_mode
                                ):
                                    handshake = await call(run, run.condition, "HANDSHAKE")
                                    if handshake.response_status not in (None, "completed"):
                                        raise ValueError("Handshake response incomplete")
                                    final = with_messages(
                                        run.condition,
                                        [
                                            *run.condition.messages,
                                            Message(
                                                role="assistant", content=handshake.raw_response
                                            ),
                                            Message(role="user", content=exp.request.task),
                                        ],
                                    )
                                run.final_condition = final.model_copy(deep=True)
                                await save()
                                run.result = await call(run, final, "TASK")
                                run.resolved_model = run.result.resolved_model
                                run.status = (
                                    "SUCCEEDED"
                                    if run.result.response_status in (None, "completed")
                                    else "FAILED"
                                )
                                break
                        except Exception as exc:
                            run.errors.append(f"Attempt {attempt + 1}: {type(exc).__name__}")
                            run.status = "FAILED"
                except asyncio.CancelledError:
                    run.status = "INTERRUPTED"
                    run.errors.append("Run cancelled during server shutdown")
                    raise
                finally:
                    run.ended_at, run.latency_ms = now(), round((perf_counter() - begin) * 1000, 3)
                    await save()

        try:
            await save()
            async with asyncio.TaskGroup() as group:
                for run in exp.runs:
                    group.create_task(lane(run))
            states = [r.status for r in exp.runs]
            exp.status = (
                "COMPLETED"
                if all(s == "SUCCEEDED" for s in states)
                else "PARTIAL"
                if "SUCCEEDED" in states
                else "FAILED"
            )
        except asyncio.CancelledError:
            exp.status = "INTERRUPTED"
            for run in exp.runs:
                if run.status in ("QUEUED", "RUNNING"):
                    run.status, run.ended_at = "INTERRUPTED", now()
            raise
        finally:
            exp.ended_at = now()
            await save()

    async def close(self):
        self.closing = True
        # Pending submissions finish/cancel before background jobs are cancelled.
        if self.creations:
            await asyncio.gather(*list(self.creations), return_exceptions=True)
        tasks = list(self.jobs.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(self.repo.recover)
