# Upgrade to v0.2.0

This is the complete application, installed into a new folder. Keep your old installation.
v0.2.0 writes experiment/export schema v2 and requires SQLite metadata schema 2.
It does not fabricate missing v2 information for old records.

## Existing v0.1.0 or v0.1.1 installation

1. Finish runs and stop the old server with Ctrl+C. Wait for shutdown complete.
2. Back up the entire stopped data directory, including WAL/SHM companions, outside either installation.
3. Extract v0.2.0 into a new folder and copy the stopped data directory into it.
   Never overwrite an existing new-version database containing experiments.
   Do not overlay old reference files: that would restore obsolete working bytes/manifests.
4. Install the locked environment in the new folder:

```sh
uv sync --locked
```

5. With all servers still stopped, explicitly migrate the copied database:

```sh
uv run --locked python -m workbench.migrate data/workbench.sqlite3
```

The command validates all v1 experiment payloads, creates a SQLite-consistent
`workbench.sqlite3.pre-v2.bak` alongside the copy, and transactionally changes the metadata
version to 2. Historical payloads are retained verbatim. A conflicting backup or unknown
database version is refused. Repeating against schema 2 is a no-op.

For WORKBENCH_DB, use its actual chosen path instead of the default above. Do not run
migration against a live database; the single-server, stopped-database requirement is operational.

6. Start:

```sh
uv run --locked python -m workbench
```

7. Open http://127.0.0.1:8765 on that computer and verify the footer says 0.2.0.
   Reopen an old successful experiment and an old blocked experiment, and export each.

## Preserved behavior

- Old terminal v1 records export as workbench-export-v1 with the same experiment fields.
- New records export as workbench-export-v2.
- Old BLOCKED treatments remain BLOCKED; restored current inputs never retroactively change them.
- Unfinished records are marked INTERRUPTED on startup, under their original schema.
- Replay is available for terminal v2 records with valid stored prompts. Legacy v1 replay
  is refused because its v2 execution contract was never recorded.
- Reuse setup remains available for v1. It creates a fresh v2 experiment with current bytes,
  current defaults, and the newly selected controls. It is not historical replay.

Opening schema 1 directly in the new server fails with migration instructions. Opening
schema 2 in the old application fails its version guard. For rollback, use the preserved
old installation and pre-upgrade backup; do not downgrade a database that holds new v2 runs.

A fresh installation has no data to migrate: simply start the server.
