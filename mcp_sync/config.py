import json
import os
import platform
from pathlib import Path
from typing import Any


class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".mcp-sync"
        self.locations_file = self.config_dir / "locations.json"
        self.global_config_file = self.config_dir / "global.json"
        self.user_client_definitions_file = self.config_dir / "client_definitions.json"
        self.client_definitions = self._load_client_definitions()
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        self.config_dir.mkdir(exist_ok=True)

        # Initialize locations file if it doesn't exist
        if not self.locations_file.exists():
            default_locations = self._get_default_locations()
            self._save_locations(default_locations)

        # Initialize global config if it doesn't exist
        if not self.global_config_file.exists():
            self._save_global_config({"mcpServers": {}})

        # Initialize empty user client definitions if it doesn't exist
        if not self.user_client_definitions_file.exists():
            self._save_user_client_definitions({"clients": {}})

    def _load_client_definitions(self) -> dict[str, Any]:
        """Load client definitions, merging built-in and user definitions"""
        # Load built-in definitions
        builtin_definitions_file = Path(__file__).parent / "client_definitions.json"
        builtin_definitions = {"clients": {}}
        try:
            with open(builtin_definitions_file) as f:
                builtin_definitions = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load built-in client definitions: {e}")

        # Load user definitions (takes precedence)
        user_definitions = {"clients": {}}
        if self.user_client_definitions_file.exists():
            try:
                with open(self.user_client_definitions_file) as f:
                    user_definitions = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load user client definitions: {e}")

        # Merge definitions (user overrides built-in)
        merged_clients = builtin_definitions.get("clients", {}).copy()
        merged_clients.update(user_definitions.get("clients", {}))

        return {"clients": merged_clients}

    def _get_default_locations(self) -> list[dict[str, str]]:
        """Get all auto-discovered client locations from definitions"""
        locations = []

        for client_id, client_config in self.client_definitions.get("clients", {}).items():
            location = self._get_client_location(client_id, client_config)
            if location:
                locations.append(location)

        return locations

    def _get_client_location(
        self, client_id: str, client_config: dict[str, Any]
    ) -> dict[str, str] | None:
        """Get location for a specific client if it exists"""
        platform_name = self._get_platform_name()
        path_template = client_config.get("paths", {}).get(platform_name)

        if not path_template:
            return None

        # Expand path template
        expanded_path = self._expand_path_template(path_template)

        if expanded_path.exists():
            return {
                "path": str(expanded_path),
                "name": client_id,
                "type": "auto",
                "client_name": client_config.get("name", client_id),
                "description": client_config.get("description", ""),
            }

        return None

    def _get_platform_name(self) -> str:
        """Get platform name for client definitions"""
        system = platform.system().lower()
        return {"darwin": "darwin", "windows": "windows", "linux": "linux"}.get(system, "linux")

    def _expand_path_template(self, path_template: str) -> Path:
        """Expand path template with environment variables"""
        # Handle ~ for home directory
        if path_template.startswith("~/"):
            path_template = str(Path.home()) + path_template[1:]

        # Handle Windows environment variables
        if "%" in path_template:
            path_template = os.path.expandvars(path_template)

        return Path(path_template)

    def get_locations(self) -> list[dict[str, str]]:
        if not self.locations_file.exists():
            return []

        with open(self.locations_file) as f:
            data = json.load(f)
            return data.get("locations", [])

    def _save_locations(self, locations: list[dict[str, str]]):
        with open(self.locations_file, "w") as f:
            json.dump({"locations": locations}, f, indent=2)

    def add_location(self, path: str, name: str | None = None) -> bool:
        locations = self.get_locations()

        # Check if location already exists
        for loc in locations:
            if loc["path"] == path:
                return False

        # Add new location
        new_location = {"path": path, "name": name or Path(path).stem, "type": "manual"}
        locations.append(new_location)
        self._save_locations(locations)
        return True

    def remove_location(self, path: str) -> bool:
        locations = self.get_locations()
        original_count = len(locations)

        locations = [loc for loc in locations if loc["path"] != path]

        if len(locations) < original_count:
            self._save_locations(locations)
            return True
        return False

    def get_global_config(self) -> dict[str, Any]:
        if not self.global_config_file.exists():
            return {"mcpServers": {}}

        with open(self.global_config_file) as f:
            return json.load(f)

    def _save_global_config(self, config: dict[str, Any]):
        with open(self.global_config_file, "w") as f:
            json.dump(config, f, indent=2)

    def _save_user_client_definitions(self, definitions: dict[str, Any]):
        """Save user client definitions"""
        with open(self.user_client_definitions_file, "w") as f:
            json.dump(definitions, f, indent=2)

    def scan_configs(self) -> list[dict[str, Any]]:
        found_configs = []
        locations = self.get_locations()

        for location in locations:
            path = Path(location["path"])
            if path.exists():
                try:
                    with open(path) as f:
                        config_data = json.load(f)

                    found_configs.append(
                        {"location": location, "config": config_data, "status": "found"}
                    )
                except (OSError, json.JSONDecodeError) as e:
                    found_configs.append(
                        {"location": location, "config": None, "status": f"error: {str(e)}"}
                    )
            else:
                found_configs.append({"location": location, "config": None, "status": "not_found"})

        return found_configs
