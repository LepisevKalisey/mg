"""Configuration module for the application."""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Configuration class for the application."""

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize the configuration.

        Args:
            config_dir: Directory containing configuration files.
                If not provided, will use the default config directory.
        """
        if config_dir is None:
            # Default to the config directory in the project root
            self.config_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "config"
        else:
            self.config_dir = Path(config_dir)

        # Load configuration files
        self.app_config = self._load_yaml("app.yaml")
        self.models_config = self._load_yaml("models.yaml")
        self.owner_inputs_config = self._load_yaml("owner_inputs.yaml")
        self.prices_config = self._load_yaml("prices.yaml")
        self.schedule_config = self._load_yaml("schedule.yaml")
        self.logging_config = self._load_yaml("logging.yaml")
        self.api_config = self._load_yaml("api.yaml")
        self.components_config = self._load_yaml("components.yaml")

        # Resolve environment variables in the configuration
        self._resolve_env_vars()

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """Load a YAML configuration file.

        Args:
            filename: Name of the YAML file to load.

        Returns:
            Dictionary containing the configuration.

        Raises:
            FileNotFoundError: If the configuration file does not exist.
        """
        file_path = self.config_dir / filename
        if not file_path.exists():
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _resolve_env_vars(self) -> None:
        """Resolve environment variables in the configuration."""
        self.app_config = self._resolve_env_vars_in_dict(self.app_config)

    def _resolve_env_vars_in_dict(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve environment variables in a dictionary.

        Args:
            config_dict: Dictionary to resolve environment variables in.

        Returns:
            Dictionary with resolved environment variables.
        """
        result = {}
        for key, value in config_dict.items():
            if isinstance(value, dict):
                result[key] = self._resolve_env_vars_in_dict(value)
            elif isinstance(value, str) and value.startswith("${")\
                    and value.endswith("}"):
                env_var = value[2:-1]
                result[key] = os.environ.get(env_var, value)
            else:
                result[key] = value
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Configuration key in dot notation (e.g., "database.url").
            default: Default value to return if the key is not found.

        Returns:
            Configuration value or default if not found.
        """
        keys = key.split(".")
        config = self.app_config

        for k in keys:
            if isinstance(config, dict) and k in config:
                config = config[k]
            else:
                return default

        return config

    def get_models_config(self) -> Dict[str, Any]:
        """Get the models configuration.

        Returns:
            Dictionary containing the models configuration.
        """
        return self.models_config

    def get_owner_inputs_config(self) -> Dict[str, Any]:
        """Get the owner inputs configuration.

        Returns:
            Dictionary containing the owner inputs configuration.
        """
        return self.owner_inputs_config

    def get_prices_config(self) -> Dict[str, Any]:
        """Get the prices configuration.

        Returns:
            Dictionary containing the prices configuration.
        """
        return self.prices_config

    def get_schedule_config(self) -> Dict[str, Any]:
        """Get the schedule configuration.

        Returns:
            Dictionary containing the schedule configuration.
        """
        return self.schedule_config

    def get_logging_config(self) -> Dict[str, Any]:
        """Get the logging configuration.

        Returns:
            Dictionary containing the logging configuration.
        """
        return self.logging_config

    def get_api_config(self) -> Dict[str, Any]:
        """Get the API configuration.

        Returns:
            Dictionary containing the API configuration.
        """
        return self.api_config

    def get_components_config(self) -> Dict[str, Any]:
        """Get the components configuration.

        Returns:
            Dictionary containing the components configuration.
        """
        return self.components_config


# Singleton instance
_config_instance = None


def get_config(config_dir: Optional[str] = None) -> Config:
    """Get the configuration instance.

    Args:
        config_dir: Directory containing configuration files.
            If not provided, will use the default config directory.

    Returns:
        Configuration instance.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_dir)
    return _config_instance


def reload_config(config_dir: Optional[str] = None) -> Config:
    """Reload the configuration.

    Args:
        config_dir: Directory containing configuration files.
            If not provided, will use the default config directory.

    Returns:
        Reloaded configuration instance.
    """
    global _config_instance
    _config_instance = Config(config_dir)
    return _config_instance