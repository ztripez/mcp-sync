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


@dataclass
class VacuumResult:
    imported_servers: dict[str, str]  # server_name -> source_location
    conflicts: list[dict[str, Any]]  # resolved conflicts
    errors: list[dict[str, str]]


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
                master_servers[name] = {**config, "_source": "global"}

        # Add project servers (override global)
        if not global_only:
            project_config = self._get_project_config()
            if project_config:
                project_servers = project_config.get("mcpServers", {})
                for name, config in project_servers.items():
                    master_servers[name] = {**config, "_source": "project"}

        return master_servers

    def _get_project_config(self) -> dict[str, Any] | None:
        project_config_path = Path(".mcp.json")
        return self._read_json_config(project_config_path) if project_config_path.exists() else None

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
        current_config = self._read_json_config(location_path)
        if current_config is None:
            result.errors.append({"location": location["path"], "error": "Failed to read config"})
            return

        # Extract current MCP servers
        current_servers = current_config.get("mcpServers", {})

        # Build new server list
        new_servers = {}
        conflicts = []

        # Keep existing servers that aren't in master list and log overrides
        for name, config in current_servers.items():
            if name not in master_servers:
                new_servers[name] = config
            else:
                master_config = master_servers[name].copy()
                master_config.pop("_source", None)

                if config != master_config:
                    # Log override (project configs always win)
                    conflicts.append(
                        {
                            "server": name,
                            "location": location["path"],
                            "action": "overridden",
                            "source": master_servers[name]["_source"],
                        }
                    )

        # Add master servers (they always override existing)
        for name, config in master_servers.items():
            clean_config = config.copy()
            clean_config.pop("_source", None)
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
                self._write_json_config(location_path, new_config)

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
            config = self._read_json_config(location_path)
            if config is not None:
                status["location_servers"][location["name"]] = config.get("mcpServers", {})
            else:
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

        project_config = self._read_json_config(project_config_path)
        if project_config is None:
            project_config = {"mcpServers": {}}

        project_config["mcpServers"][name] = config
        self._write_json_config(project_config_path, project_config)
        return True

    def _read_json_config(self, path: Path) -> dict[str, Any] | None:
        """Read JSON config file, return None on error"""
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_json_config(self, path: Path, config: dict[str, Any]):
        """Write JSON config file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(config, f, indent=2)

    def vacuum_configs(self) -> "VacuumResult":
        """Import existing MCP configs from all discovered locations"""
        result = VacuumResult(imported_servers={}, conflicts=[], errors=[])

        # Get all locations (excluding project .mcp.json files)
        locations = self.config_manager.get_locations()
        discovered_servers = {}  # server_name -> {config, source_name}

        # Scan all locations for existing servers
        for location in locations:
            location_path = Path(location["path"])
            if location_path.name == ".mcp.json":
                continue  # Skip project files

            config = self._read_json_config(location_path)
            if config is None:
                continue

            mcp_servers = config.get("mcpServers", {})
            for server_name, server_config in mcp_servers.items():
                if server_name in discovered_servers:
                    # Conflict found - need to resolve
                    existing = discovered_servers[server_name]
                    choice = self._resolve_conflict(
                        server_name,
                        existing["config"],
                        existing["source"],
                        server_config,
                        location["name"],
                    )

                    if choice == "new":
                        discovered_servers[server_name] = {
                            "config": server_config,
                            "source": location["name"],
                        }
                        result.conflicts.append(
                            {
                                "server": server_name,
                                "chosen_source": location["name"],
                                "rejected_source": existing["source"],
                            }
                        )
                    else:
                        result.conflicts.append(
                            {
                                "server": server_name,
                                "chosen_source": existing["source"],
                                "rejected_source": location["name"],
                            }
                        )
                else:
                    discovered_servers[server_name] = {
                        "config": server_config,
                        "source": location["name"],
                    }

        # Import all discovered servers to global config
        if discovered_servers:
            global_config = self.config_manager.get_global_config()

            for server_name, server_info in discovered_servers.items():
                global_config["mcpServers"][server_name] = server_info["config"]
                result.imported_servers[server_name] = server_info["source"]

            self.config_manager._save_global_config(global_config)

        return result

    def _resolve_conflict(
        self, server_name: str, config1: dict, source1: str, config2: dict, source2: str
    ) -> str:
        """Interactively resolve server config conflicts"""
        print(f"\nFound '{server_name}' server in multiple locations:")
        print(f"1. {source1}: {config1}")
        print(f"2. {source2}: {config2}")

        while True:
            choice = input("Choose which to keep (1 or 2): ").strip()
            if choice == "1":
                return "existing"
            elif choice == "2":
                return "new"
            else:
                print("Invalid choice. Please enter 1 or 2.")
