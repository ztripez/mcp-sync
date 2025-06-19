"""Configuration management using dynaconf."""

import json
import logging
from pathlib import Path

from dynaconf import Dynaconf
from platformdirs import user_config_dir
from pydantic import ValidationError

from .models import (
    ClientDefinitions,
    GlobalConfig,
    LocationConfig,
    LocationsConfig,
)

logger = logging.getLogger(__name__)


class Settings:
    """Configuration settings manager using dynaconf."""

    def __init__(self):
        self.config_dir = Path(user_config_dir("mcp-sync"))
        self.locations_file = self.config_dir / "locations.json"
        self.global_config_file = self.config_dir / "global.json"
        self.user_client_definitions_file = self.config_dir / "client_definitions.json"

        # Initialize dynaconf for settings
        self.settings = Dynaconf(
            settings_files=[str(self.global_config_file)],
            environments=False,
            load_dotenv=False,
        )

        self._ensure_config_dir()
        self._client_definitions: ClientDefinitions | None = None

    def _ensure_config_dir(self) -> None:
        """Ensure configuration directory and files exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize locations file if it doesn't exist
        if not self.locations_file.exists():
            default_locations = self._get_default_locations()
            self._save_locations_config(LocationsConfig(locations=default_locations))

        # Initialize global config if it doesn't exist
        if not self.global_config_file.exists():
            self._save_global_config(GlobalConfig())

        # Initialize empty user client definitions if it doesn't exist
        if not self.user_client_definitions_file.exists():
            self._save_user_client_definitions(ClientDefinitions())

    def _get_default_locations(self) -> list[LocationConfig]:
        """Get all auto-discovered client locations from definitions."""
        # Avoid circular import by returning empty list initially
        # Locations will be discovered later when needed
        return []

    def get_locations_config(self) -> LocationsConfig:
        """Get locations configuration."""
        if not self.locations_file.exists():
            return LocationsConfig()

        try:
            with open(self.locations_file) as f:
                data = json.load(f)
            return LocationsConfig(**data)
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Error loading locations config: {e}")
            return LocationsConfig()

    def _save_locations_config(self, config: LocationsConfig) -> None:
        """Save locations configuration."""
        with open(self.locations_file, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

    def get_global_config(self) -> GlobalConfig:
        """Get global configuration."""
        if not self.global_config_file.exists():
            return GlobalConfig()

        try:
            with open(self.global_config_file) as f:
                data = json.load(f)
            return GlobalConfig(**data)
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Error loading global config: {e}")
            return GlobalConfig()

    def _save_global_config(self, config: GlobalConfig) -> None:
        """Save global configuration."""
        with open(self.global_config_file, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

    def get_client_definitions(self) -> ClientDefinitions:
        """Get merged client definitions (built-in + user)."""
        if self._client_definitions is not None:
            return self._client_definitions

        # Load built-in definitions
        builtin_definitions_file = Path(__file__).parent.parent / "client_definitions.json"
        builtin_definitions = ClientDefinitions()

        try:
            with open(builtin_definitions_file) as f:
                data = json.load(f)
            builtin_definitions = ClientDefinitions(**data)
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Could not load built-in client definitions: {e}")

        # Load user definitions
        user_definitions = ClientDefinitions()
        if self.user_client_definitions_file.exists():
            try:
                with open(self.user_client_definitions_file) as f:
                    data = json.load(f)
                user_definitions = ClientDefinitions(**data)
            except (OSError, json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Could not load user client definitions: {e}")

        # Merge definitions (user overrides built-in)
        merged_clients = builtin_definitions.clients.copy()
        merged_clients.update(user_definitions.clients)

        self._client_definitions = ClientDefinitions(clients=merged_clients)
        return self._client_definitions

    def _save_user_client_definitions(self, definitions: ClientDefinitions) -> None:
        """Save user client definitions."""
        with open(self.user_client_definitions_file, "w") as f:
            json.dump(definitions.model_dump(), f, indent=2)

    def add_location(self, path: str, name: str | None = None) -> bool:
        """Add a new location."""
        config = self.get_locations_config()

        # Check if location already exists
        for location in config.locations:
            if location.path == path:
                return False

        # Add new location
        location_name = name or Path(path).stem
        new_location = LocationConfig(path=path, name=location_name, type="manual")
        config.locations.append(new_location)
        self._save_locations_config(config)
        return True

    def remove_location(self, path: str) -> bool:
        """Remove a location."""
        config = self.get_locations_config()
        original_count = len(config.locations)

        config.locations = [loc for loc in config.locations if loc.path != path]

        if len(config.locations) < original_count:
            self._save_locations_config(config)
            return True
        return False


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
