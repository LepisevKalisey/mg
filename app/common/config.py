"""Configuration loading utilities with layered precedence.

Order of precedence (lowest to highest):
1. Values from a ``.env`` file.
2. YAML files inside ``config/`` directory.
3. Settings fetched from a database.

The resulting configuration dictionary is the merge of all three sources
with later sources overriding earlier ones.
"""
from __future__ import annotations

import glob
import os
import sqlite3
from typing import Dict, Any

try:
    import yaml
except Exception:  # pragma: no cover - dependency might be missing at runtime
    yaml = None  # type: ignore
from .errors import ConfigError



def _load_env(path: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            if "=" not in raw:
                continue
            key, val = raw.split("=", 1)
            data[key.strip()] = val.strip()
    return data


def _load_yaml_files(config_dir: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not yaml or not os.path.isdir(config_dir):
        return data
    for path in sorted(glob.glob(os.path.join(config_dir, "*.yaml"))):
        with open(path, "r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                raise ConfigError(f"YAML file {path} did not produce a mapping")
            data.update(loaded)
    return data


def _load_db_settings(db_url: str | None) -> Dict[str, Any]:
    if not db_url:
        return {}
    if db_url.startswith("sqlite:///"):
        path = db_url[len("sqlite:///") :]
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)"
            )
            cur.execute("SELECT key, value FROM settings")
            rows = cur.fetchall()
            return {k: v for k, v in rows}
        finally:
            conn.close()
    raise ConfigError(f"Unsupported database URL: {db_url}")


def load_config(
    config_dir: str = "config", env_file: str = ".env", db_url: str | None = None
) -> Dict[str, Any]:
    """Load configuration with standard precedence.

    Precedence (highest first):
    1. Settings retrieved from ``db_url`` (or ``DATABASE_URL`` env variable).
    2. YAML files under ``config_dir``.
    3. The ``env_file``.
    """
    config: Dict[str, Any] = {}
    # Lowest precedence - .env values
    config.update(_load_env(env_file))
    # YAML overrides env
    config.update(_load_yaml_files(config_dir))
    # DB settings override YAML and env
    db_url = db_url or os.getenv("DATABASE_URL")
    config.update(_load_db_settings(db_url))
    return config


__all__ = ["load_config", "ConfigError"]
