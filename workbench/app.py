import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .artifacts import ArtifactStore
from .controller import Controller
from .legacy_models import Experiment as LegacyExperiment
from .legacy_models import ExportRecord as LegacyExportRecord
from .models import ExportRecord, ReplayRequest, RunRequest
from .providers import cloud_available, ollama_models
from .repository import Repository

ROOT = Path(__file__).resolve().parent.parent


class LocalBoundary:
    """Reject cross-origin writes, cap request bodies, and require local Host headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            origin = headers.get(b"origin")
            fetch_site = headers.get(b"sec-fetch-site", b"")
            if origin:
                try:
                    parsed_origin = urlsplit(origin.decode("latin1"))
                except ValueError:
                    return await JSONResponse({"detail": "Invalid Origin header"}, 403)(
                        scope, receive, send
                    )
            if fetch_site in (b"cross-site", b"same-site") or (
                origin
                and (
                    parsed_origin.netloc != headers.get(b"host", b"").decode()
                    or parsed_origin.scheme != scope["scheme"]
                )
            ):
                return await JSONResponse({"detail": "Cross-origin writes are disabled"}, 403)(
                    scope, receive, send
                )
            if not headers.get(b"content-type", b"").startswith(b"application/json"):
                return await JSONResponse({"detail": "JSON requests only"}, 415)(
                    scope, receive, send
                )
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body = message.get("body", b"")
                size += len(body)
                if size > 131072:
                    return await JSONResponse({"detail": "Request exceeds 128 KiB"}, 413)(
                        scope, receive, send
                    )
                chunks.append(body)
                if not message.get("more_body"):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        else:
            await self.app(scope, receive, send)


def create_app(
    db_path: Path | None = None, reference_root: Path | None = None, test_mode: bool = False
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repo = await asyncio.to_thread(
            Repository, db_path or Path(os.getenv("WORKBENCH_DB", ROOT / "data/workbench.sqlite3"))
        )
        artifacts = ArtifactStore(reference_root or ROOT / "reference/injectors")
        await asyncio.to_thread(repo.recover)
        app.state.repo, app.state.artifacts = repo, artifacts
        app.state.controller = Controller(repo, artifacts)
        yield
        await app.state.controller.close()

    app = FastAPI(
        title="Prompt Engineering Workbench",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(LocalBoundary)
    hosts = ["localhost", "127.0.0.1", "[::1]"] + (["testserver"] if test_mode else [])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        app.state.repo.history(1)
        return {
            "status": "ok",
            "version": __version__,
            "mode": "cloud-enabled" if cloud_available() else "offline",
            "database": "ok",
        }

    @app.get("/api/providers")
    def providers():
        local_models = [] if test_mode else ollama_models()
        return [
            {
                "id": "mock",
                "model": "fixture-echo-v2",
                "enabled": True,
                "execution": "local-offline",
            },
            {
                "id": "openai",
                "enabled": cloud_available(),
                "execution": "cloud",
                "reason": "Requires WORKBENCH_ENABLE_OPENAI=1 and server-side OPENAI_API_KEY",
                "seed_supported": False,
            },
            {
                "id": "ollama",
                "enabled": bool(local_models),
                "execution": "local-offline",
                "models": local_models,
                "reason": (
                    None
                    if local_models
                    else "No loopback Ollama server or installed models detected"
                ),
                "seed_supported": True,
            },
        ]

    @app.get("/api/artifacts")
    def artifacts():
        entries = []
        for artifact_id in app.state.artifacts.ids():
            try:
                entries.append(app.state.artifacts.load(artifact_id).identity.model_dump())
            except (ValueError, OSError) as exc:
                entries.append(
                    {
                        "artifact_id": artifact_id,
                        "status": "INVALID",
                        "diagnostics": [f"Cannot load manifest: {type(exc).__name__}"],
                    }
                )
        return entries

    @app.get("/api/experiments")
    def history():
        return app.state.repo.history()

    @app.post("/api/experiments", status_code=202)
    async def create(request: RunRequest):
        try:
            exp = await app.state.controller.create(request)
        except (ValueError, OSError) as exc:
            raise HTTPException(
                400, "Input unavailable, integrity preparation failed, or provider unavailable"
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(429, str(exc)) from exc
        return {"experiment_id": exp.experiment_id, "status": exp.status}

    def get_exp(experiment_id: str):
        try:
            return app.state.repo.get(experiment_id)
        except KeyError as exc:
            raise HTTPException(404, "Experiment not found") from exc

    @app.post("/api/experiments/{experiment_id}/replay", status_code=202)
    async def replay(experiment_id: str, options: ReplayRequest):
        exp = await asyncio.to_thread(get_exp, experiment_id)
        if isinstance(exp, LegacyExperiment):
            raise HTTPException(409, "Legacy v1 has no v2 execution contract; use Reuse setup")
        if exp.request.provider == "openai" and not options.cloud_consent:
            raise HTTPException(
                400, "Replay sends stored prompts to OpenAI; cloud_consent required"
            )
        try:
            replayed = await app.state.controller.create(exp.request, replay_id=experiment_id)
        except (ValueError, OSError) as exc:
            raise HTTPException(
                409,
                "Replay refused: invalid snapshot, incomplete handshake, "
                "changed SDK, or disabled provider",
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(429, str(exc)) from exc
        return {"experiment_id": replayed.experiment_id, "status": replayed.status}

    @app.get("/api/experiments/{experiment_id}")
    def detail(experiment_id: str):
        return get_exp(experiment_id)

    @app.get("/api/experiments/{experiment_id}/export")
    def export(experiment_id: str, format: str = "json"):
        if format not in ("json", "jsonl"):
            raise HTTPException(400, "Choose json or jsonl")
        exp = get_exp(experiment_id)
        record = (
            LegacyExportRecord(experiment=exp)
            if isinstance(exp, LegacyExperiment)
            else ExportRecord(experiment=exp)
        )
        filename = f"experiment-{record.experiment.experiment_id}.{format}"
        text = json.dumps(
            record.model_dump(), ensure_ascii=False, indent=2 if format == "json" else None
        )
        return Response(
            text + "\n",
            media_type="application/json" if format == "json" else "application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/")
    async def home():
        return FileResponse(ROOT / "workbench/static/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "workbench/static"), name="static")
    return app


app = create_app()
