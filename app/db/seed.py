"""Seed initial settings from config/*.yaml into the database."""
import json
import os
from pathlib import Path

import yaml
from sqlalchemy import create_engine, text


def main() -> None:
    dsn = os.getenv("DATABASE_URL", "sqlite:///app.db")
    engine = create_engine(dsn)
    config_dir = Path("config")
    files = sorted(config_dir.glob("*.yaml"))
    with engine.begin() as conn:
        for file in files:
            key = file.stem
            value = yaml.safe_load(file.read_text()) or {}
            conn.execute(
                text(
                    "INSERT INTO settings(key, value) VALUES (:key, :value) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value"
                ),
                {"key": key, "value": json.dumps(value)},
            )
    print(f"Seeded {len(files)} settings")


if __name__ == "__main__":
    main()
