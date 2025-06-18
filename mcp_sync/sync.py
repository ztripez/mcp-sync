import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SyncResult:
    updated_locations: list[str]
    conflicts: list[dict[str, Any]]
    errors: list[dict[str, str]]
    dry_run: bool = False


class SyncEngine:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    def sync_all(
        self,
        dry_run: bool = False,
        global_only: bool = False,
        project_only: bool = False,
        specific_location: str | None = None,
    ) -> SyncResult:
        result = SyncResult([], [], [], dry_run)

        # Get master server list from global config + project config
        master_servers = self._build_master_server_list(global_only, project_only)

        # Get locations to sync
        locations = self._get_sync_locations(specific_location, global_only, project_only)

        # Sync each location
        for location in locations:
            try:
                self._sync_location(location, master_servers, result)
            except Exception as e:
                result.errors.append({"location": location["path"], "error": str(e)})

        return result

    def _build_master_server_list(self, global_only: bool, project_only: bool) -> dict[str, Any]:
        master_servers = {}

        # Add global servers
        if not project_only:
            global_config = self.config_manager.get_global_config()
            global_servers = global_config.get("mcpServers", {})
            for name, config in global_servers.items():
                master_servers[name] = {**config, "_source": "global", "_priority": 1}

        # Add project servers (higher priority)
        if not global_only:
            project_config = self._get_project_config()
            if project_config:
                project_servers = project_config.get("mcpServers", {})
                for name, config in project_servers.items():
                    master_servers[name] = {**config, "_source": "project", "_priority": 2}

        return master_servers

    def _get_project_config(self) -> dict[str, Any] | None:
        project_config_path = Path(".mcp.json")
        if project_config_path.exists():
            try:
                with open(project_config_path) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return None
        return None

    def _get_sync_locations(
        self, specific_location: str | None, global_only: bool, project_only: bool
    ) -> list[dict[str, str]]:
        all_locations = self.config_manager.get_locations()

        if specific_location:
            # Find specific location
            for loc in all_locations:
                if loc["path"] == specific_location:
                    return [loc]
            return []

        # Filter by scope
        filtered_locations = []
        for loc in all_locations:
            # Skip project config file itself
            if loc["path"].endswith(".mcp.json"):
                continue

            # Apply filters
            if global_only and loc.get("scope") == "project":
                continue
            if project_only and loc.get("scope") == "global":
                continue

            filtered_locations.append(loc)

        return filtered_locations

    def _sync_location(
        self, location: dict[str, str], master_servers: dict[str, Any], result: SyncResult
    ):
        location_path = Path(location["path"])

        # Read current config
        current_config = {}
        if location_path.exists():
            try:
                with open(location_path) as f:
                    current_config = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                result.errors.append(
                    {"location": location["path"], "error": f"Failed to read config: {str(e)}"}
                )
                return

        # Extract current MCP servers
        current_servers = current_config.get("mcpServers", {})

        # Build new server list
        new_servers = {}
        conflicts = []

        # Keep existing servers that aren't in master list
        for name, config in current_servers.items():
            if name not in master_servers:
                new_servers[name] = config
            else:
                # Check for conflicts
                master_config = master_servers[name].copy()
                master_config.pop("_source", None)
                master_config.pop("_priority", None)

                if config != master_config:
                    conflicts.append(
                        {
                            "server": name,
                            "location": location["path"],
                            "current": config,
                            "master": master_config,
                            "source": master_servers[name]["_source"],
                        }
                    )

        # Add master servers
        for name, config in master_servers.items():
            clean_config = config.copy()
            clean_config.pop("_source", None)
            clean_config.pop("_priority", None)
            new_servers[name] = clean_config

        # Update config
        new_config = current_config.copy()
        new_config["mcpServers"] = new_servers

        # Check if changes are needed
        if current_config.get("mcpServers", {}) != new_servers:
            if not result.dry_run:
                # Ensure directory exists
                location_path.parent.mkdir(parents=True, exist_ok=True)

                # Write new config
                with open(location_path, "w") as f:
                    json.dump(new_config, f, indent=2)

            result.updated_locations.append(location["path"])

        # Add conflicts to result
        result.conflicts.extend(conflicts)

    def get_server_status(self) -> dict[str, Any]:
        """Get status of all servers across all locations"""
        status = {
            "global_servers": {},
            "project_servers": {},
            "location_servers": {},
            "conflicts": [],
        }

        # Global servers
        global_config = self.config_manager.get_global_config()
        status["global_servers"] = global_config.get("mcpServers", {})

        # Project servers
        project_config = self._get_project_config()
        if project_config:
            status["project_servers"] = project_config.get("mcpServers", {})

        # Location servers
        locations = self.config_manager.get_locations()
        for location in locations:
            location_path = Path(location["path"])
            if location_path.exists():
                try:
                    with open(location_path) as f:
                        config = json.load(f)
                    status["location_servers"][location["name"]] = config.get("mcpServers", {})
                except (OSError, json.JSONDecodeError):
                    status["location_servers"][location["name"]] = "error"

        return status

    def add_server_to_global(self, name: str, config: dict[str, Any]) -> bool:
        """Add server to global config"""
        global_config = self.config_manager.get_global_config()
        global_config["mcpServers"][name] = config
        self.config_manager._save_global_config(global_config)
        return True

    def remove_server_from_global(self, name: str) -> bool:
        """Remove server from global config"""
        global_config = self.config_manager.get_global_config()
        if name in global_config.get("mcpServers", {}):
            del global_config["mcpServers"][name]
            self.config_manager._save_global_config(global_config)
            return True
        return False

    def add_server_to_project(self, name: str, config: dict[str, Any]) -> bool:
        """Add server to project config"""
        project_config_path = Path(".mcp.json")

        if project_config_path.exists():
            with open(project_config_path) as f:
                project_config = json.load(f)
        else:
            project_config = {"mcpServers": {}}

        project_config["mcpServers"][name] = config

        with open(project_config_path, "w") as f:
            json.dump(project_config, f, indent=2)

        return True
