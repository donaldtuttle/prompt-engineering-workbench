import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .legacy_models import Experiment as LegacyExperiment
from .models import Experiment, now


def parse_experiment(payload):
    data = json.loads(payload)
    if data.get("schema_version") == "workbench-experiment-v1":
        return LegacyExperiment.model_validate(data)
    if data.get("schema_version") == "workbench-experiment-v2":
        return Experiment.model_validate(data)
    raise RuntimeError("Unsupported experiment schema")


class Repository:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables and "metadata" not in tables:
                raise RuntimeError("Unversioned database; refusing implicit migration")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
            version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if tables and version is None:
                raise RuntimeError("Unversioned database; refusing implicit migration")
            if version and version[0] == "1":
                raise RuntimeError(
                    "Database schema 1 requires explicit migration: "
                    "python -m workbench.migrate PATH"
                )
            if version and version[0] != "2":
                raise RuntimeError("Unsupported database schema; do not overwrite this database")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version', '2')")
            db.execute("""CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,
                status TEXT NOT NULL, payload TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, experiment: Experiment) -> None:
        # Lexical ordering is valid only for this exact UTC timestamp representation.
        from datetime import UTC, datetime

        parsed = datetime.fromisoformat(experiment.created_at)
        if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat() != experiment.created_at:
            raise ValueError("created_at must use canonical UTC isoformat")
        with self.connect() as db:
            db.execute(
                """INSERT INTO experiments VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload""",
                (
                    experiment.experiment_id,
                    experiment.created_at,
                    experiment.request.title,
                    experiment.status,
                    experiment.model_dump_json(),
                ),
            )

    def get(self, experiment_id: str) -> Experiment:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM experiments WHERE id=?", (experiment_id,)
            ).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return parse_experiment(row[0])

    def history(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, created_at, title, status FROM experiments
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            dict(zip(("experiment_id", "created_at", "title", "status"), r, strict=True))
            for r in rows
        ]

    def recover(self) -> None:
        """Single-worker startup recovery. Never silently rerun interrupted experiments."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM experiments WHERE status IN ('QUEUED','RUNNING')"
            )
            pending = [parse_experiment(r[0]) for r in rows]
        for exp in pending:
            exp.status, exp.ended_at = "INTERRUPTED", now()
            for run in exp.runs:
                if run.status in ("QUEUED", "RUNNING"):
                    run.status, run.ended_at = "INTERRUPTED", now()
                    run.errors.append(
                        "Server stopped before this lane finished; no automatic replay"
                    )
            self.save(exp)
