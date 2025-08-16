"""Environment variables module."""

import os
from pathlib import Path
from typing import Dict, Optional


def load_env_file(env_file: Optional[str] = None) -> Dict[str, str]:
    """Load environment variables from a .env file.

    Args:
        env_file: Path to the .env file. If not provided, will try to load from
            the default locations: ./config/owner.env or ./owner.env

    Returns:
        Dictionary of environment variables loaded from the file.
    """
    if env_file is None:
        # Try default locations
        project_root = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        possible_paths = [
            project_root / "config" / "owner.env",
            project_root / "owner.env",
        ]
        for path in possible_paths:
            if path.exists():
                env_file = str(path)
                break

    if env_file is None or not os.path.exists(env_file):
        return {}

    env_vars = {}
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()

    return env_vars


def set_env_vars(env_vars: Dict[str, str]) -> None:
    """Set environment variables.

    Args:
        env_vars: Dictionary of environment variables to set.
    """
    for key, value in env_vars.items():
        os.environ[key] = value


def load_and_set_env_vars(env_file: Optional[str] = None) -> Dict[str, str]:
    """Load environment variables from a .env file and set them.

    Args:
        env_file: Path to the .env file. If not provided, will try to load from
            the default locations: ./config/owner.env or ./owner.env

    Returns:
        Dictionary of environment variables loaded from the file.
    """
    env_vars = load_env_file(env_file)
    set_env_vars(env_vars)
    return env_vars