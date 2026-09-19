"""Explicit offline schema-1 admission upgrade. Historical payloads are never converted."""

import argparse
import sqlite3
from pathlib import Path

from .repository import parse_experiment


def migrate(path: Path):
    if not path.is_file():
        raise ValueError("Database does not exist")
    backup = path.with_name(path.name + ".pre-v2.bak")
    with sqlite3.connect(path, timeout=1) as db:
        version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
        if version and version[0] == "2":
            return None
        if version != ("1",):
            raise ValueError("Only schema 1 can be migrated")
        if backup.exists():
            raise ValueError("Backup already exists; preserve it and choose a fresh database copy")
        # Validate every old payload before changing anything.
        for (payload,) in db.execute("SELECT payload FROM experiments"):
            exp = parse_experiment(payload)
            if exp.schema_version != "workbench-experiment-v1":
                raise ValueError("Schema-1 database contains a non-v1 record")
        with backup.open("xb"):
            pass
        with sqlite3.connect(backup) as dest:
            db.backup(dest)
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
        db.commit()
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    result = migrate(args.database)
    print(f"Migrated; backup: {result}" if result else "Already schema 2; unchanged")


if __name__ == "__main__":
    main()
