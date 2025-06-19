"""Client discovery and repository management."""

import json
import logging
import platform
from pathlib import Path
from typing import Any

from ..config.models import MCPClientConfig

logger = logging.getLogger(__name__)


class ClientRepository:
    """Repository for discovering and managing MCP clients."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def discover_clients(self) -> list[dict[str, Any]]:
        """Discover all available clients and return their locations."""
        from ..config.settings import get_settings

        settings = get_settings()
        client_definitions = settings.get_client_definitions()
        locations = []

        for client_id, client_config in client_definitions.clients.items():
            location = self._get_client_location(client_id, client_config)
            if location:
                locations.append(location)

        return locations

    def _get_client_location(
        self, client_id: str, client_config: MCPClientConfig
    ) -> dict[str, Any] | None:
        """Get location for a specific client if it exists."""
        if client_config.config_type == "cli":
            from .executor import CLIExecutor

            executor = CLIExecutor()
            if executor.is_cli_available(client_config):
                return {
                    "path": f"cli:{client_id}",
                    "name": client_id,
                    "type": "auto",
                    "config_type": "cli",
                    "client_name": client_config.name,
                    "description": client_config.description,
                }
        else:
            platform_name = self._get_platform_name()
            path_template = None

            if client_config.paths:
                path_template = client_config.paths.get(platform_name)

            if not path_template and client_config.fallback_paths:
                path_template = client_config.fallback_paths.get(platform_name)

            if path_template:
                expanded_path = self._expand_path_template(path_template)
                if expanded_path.exists():
                    return {
                        "path": str(expanded_path),
                        "name": client_id,
                        "type": "auto",
                        "config_type": "file",
                        "client_name": client_config.name,
                        "description": client_config.description,
                    }

        return None

    def _get_platform_name(self) -> str:
        """Get platform name for client definitions."""
        system = platform.system().lower()
        return {"darwin": "darwin", "windows": "windows", "linux": "linux"}.get(system, "linux")

    def _expand_path_template(self, path_template: str) -> Path:
        """Expand path template with environment variables."""
        import os

        # Handle ~ for home directory
        if path_template.startswith("~/"):
            path_template = str(Path.home()) + path_template[1:]

        # Handle Windows environment variables
        if "%" in path_template:
            path_template = os.path.expandvars(path_template)

        return Path(path_template)

    def scan_configs(self) -> list[dict[str, Any]]:
        """Scan all configured locations for MCP configurations."""
        from ..config.settings import get_settings

        settings = get_settings()
        locations_config = settings.get_locations_config()
        found_configs = []

        for location in locations_config.locations:
            path = Path(location.path)
            if path.exists():
                try:
                    with open(path) as f:
                        config_data = json.load(f)

                    found_configs.append(
                        {
                            "location": location.model_dump(),
                            "config": config_data,
                            "status": "found",
                        }
                    )
                except (OSError, json.JSONDecodeError) as e:
                    found_configs.append(
                        {
                            "location": location.model_dump(),
                            "config": None,
                            "status": f"error: {str(e)}",
                        }
                    )
            else:
                found_configs.append(
                    {"location": location.model_dump(), "config": None, "status": "not_found"}
                )

        return found_configs
