import json
import os
import platform
from pathlib import Path
from typing import Any


class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".yagni-mcp"
        self.locations_file = self.config_dir / "locations.json"
        self.global_config_file = self.config_dir / "global.json"
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

    def _get_default_locations(self) -> list[dict[str, str]]:
        locations = []
        system = platform.system()

        # Claude Desktop
        if system == "Darwin":  # macOS
            claude_path = (
                Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
            )
        elif system == "Windows":
            claude_path = Path(os.environ.get("APPDATA", "")) / "Claude/claude_desktop_config.json"
        else:  # Linux
            claude_path = Path.home() / ".config/claude/claude_desktop_config.json"

        if claude_path.exists():
            locations.append(
                {"path": str(claude_path), "name": "claude-desktop", "type": "auto-discovered"}
            )

        # Claude Code
        claude_code_path = Path.home() / ".claude/settings.json"
        if claude_code_path.exists():
            locations.append(
                {"path": str(claude_code_path), "name": "claude-code", "type": "auto-discovered"}
            )

        # Cline
        if system == "Darwin":  # macOS
            cline_path = (
                Path.home()
                / "Library/Application Support/Code/User/globalStorage/cline_mcp_settings.json"
            )
        elif system == "Windows":
            cline_path = (
                Path(os.environ.get("APPDATA", ""))
                / "Code/User/globalStorage/cline_mcp_settings.json"
            )
        else:  # Linux
            cline_path = Path.home() / ".config/Code/User/globalStorage/cline_mcp_settings.json"

        if cline_path.exists():
            locations.append({"path": str(cline_path), "name": "cline", "type": "auto-discovered"})

        # VS Code User Settings
        if system == "Darwin":  # macOS
            vscode_path = Path.home() / "Library/Application Support/Code/User/settings.json"
        elif system == "Windows":
            vscode_path = Path(os.environ.get("APPDATA", "")) / "Code/User/settings.json"
        else:  # Linux
            vscode_path = Path.home() / ".config/Code/User/settings.json"

        if vscode_path.exists():
            locations.append(
                {"path": str(vscode_path), "name": "vscode-user", "type": "auto-discovered"}
            )

        return locations

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
