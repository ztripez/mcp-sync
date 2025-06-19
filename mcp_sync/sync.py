import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .clients.executor import CLIExecutor


@dataclass
class SyncResult:
    updated_locations: list[str]
    conflicts: list[dict[str, Any]]
    errors: list[dict[str, str]]
    dry_run: bool = False


@dataclass
class VacuumResult:
    def __init__(
        self,
        imported_servers: dict[str, str] | None = None,
        conflicts: list[dict[str, Any]] | None = None,
        errors: list[dict[str, str]] | None = None,
        skipped_servers: list[str] | None = None,
    ):
        self.imported_servers = imported_servers or {}  # server_name -> source_location
        self.conflicts = conflicts or []  # resolved conflicts
        self.errors = errors or []
        self.skipped_servers = skipped_servers or []


class SyncEngine:
    def __init__(self, settings):
        self.settings = settings
        self.executor = CLIExecutor()
        self.logger = logging.getLogger(__name__)

    def sync_all(
        self,
        dry_run: bool = False,
        global_only: bool = False,
        project_only: bool = False,
        specific_location: str | None = None,
    ) -> SyncResult:
        self.logger.info(
            f"Starting sync operation (dry_run={dry_run}, "
            f"global_only={global_only}, project_only={project_only})"
        )
        result = SyncResult([], [], [], dry_run)

        try:
            # Get master server list from global config + project config
            master_servers = self._build_master_server_list(global_only, project_only)
            self.logger.debug(f"Built master server list with {len(master_servers)} servers")

            # Get locations to sync
            locations = self._get_sync_locations(specific_location, global_only, project_only)
            self.logger.info(f"Found {len(locations)} locations to sync")

            # Sync each location
            for location in locations:
                try:
                    self.logger.debug(f"Syncing location: {location['path']}")
                    self._sync_location(location, master_servers, result)
                except Exception as e:
                    self.logger.error(f"Failed to sync location {location['path']}: {e}")
                    result.errors.append({"location": location["path"], "error": str(e)})

            self.logger.info(
                f"Sync completed: {len(result.updated_locations)} updated, "
                f"{len(result.conflicts)} conflicts, {len(result.errors)} errors"
            )
            return result

        except Exception as e:
            self.logger.error(f"Critical error during sync operation: {e}")
            result.errors.append(
                {"location": "sync_engine", "error": f"Critical sync error: {str(e)}"}
            )
            return result

    def _build_master_server_list(self, global_only: bool, project_only: bool) -> dict[str, Any]:
        master_servers = {}

        # Add global servers
        if not project_only:
            global_config = self.settings.get_global_config()
            global_servers = global_config.mcpServers
            for name, config in global_servers.items():
                master_servers[name] = {**config.model_dump(), "_source": "global"}

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
        locations_config = self.settings.get_locations_config()
        all_locations = [loc.model_dump() for loc in locations_config.locations]

        if specific_location:
            # Find specific location by path or name
            for loc in all_locations:
                if loc["path"] == specific_location or loc["name"] == specific_location:
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
        # Handle CLI-based clients
        if location.get("config_type") == "cli" or location["path"].startswith("cli:"):
            self._sync_cli_location(location, master_servers, result)
            return

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

    def _sync_cli_location(
        self, location: dict[str, str], master_servers: dict[str, Any], result: SyncResult
    ):
        """Sync CLI-based client location"""
        client_id = (
            location["path"].replace("cli:", "")
            if location["path"].startswith("cli:")
            else location["name"]
        )

        # Get current servers from CLI
        client_definitions = self.settings.get_client_definitions()
        client_config = client_definitions.clients.get(client_id)
        if not client_config:
            self.logger.warning(f"Client {client_id} not found in definitions")
            return

        current_servers = self.executor.get_mcp_servers(client_id, client_config) or {}
        self.logger.debug(f"CLI current servers for {client_id}: {list(current_servers.keys())}")

        # Build new server list - only include servers from master list
        new_servers = {}
        conflicts = []

        # Check for conflicts where existing servers differ from master
        for name, config in current_servers.items():
            if name in master_servers:
                master_config = master_servers[name].copy()
                master_config.pop("_source", None)

                # For CLI, we need to compare normalized command arrays
                current_cmd = config.get("command", [])
                master_config_cmd = master_config.get("command", [])
                master_config_args = master_config.get("args", [])
                # Normalize master command to array format
                if isinstance(master_config_cmd, str):
                    master_cmd = [master_config_cmd] + master_config_args
                elif isinstance(master_config_cmd, list):
                    master_cmd = master_config_cmd + master_config_args
                else:
                    master_cmd = []

                if current_cmd != master_cmd:
                    conflicts.append(
                        {
                            "server": name,
                            "location": location["path"],
                            "action": "overridden",
                            "source": master_servers[name]["_source"],
                            "current": current_cmd,
                            "master": master_cmd,
                        }
                    )

        # Add all master servers (this is the new configuration)
        for name, config in master_servers.items():
            clean_config = config.copy()
            clean_config.pop("_source", None)
            new_servers[name] = clean_config

        self.logger.debug(f"CLI new servers for {client_id}: {list(new_servers.keys())}")

        # Filter out URL-based servers from comparison since CLI doesn't support them yet
        current_command_servers = {
            name: config for name, config in current_servers.items() if not config.get("url")
        }
        new_command_servers = {
            name: config for name, config in new_servers.items() if not config.get("url")
        }

        # Check if changes are needed (only for command-based servers)
        changes_needed = set(current_command_servers.keys()) != set(new_command_servers.keys())
        self.logger.debug(
            f"CLI changes needed for {client_id}: {changes_needed} "
            f"(current: {set(current_command_servers.keys())}, "
            f"new: {set(new_command_servers.keys())})"
        )
        if not changes_needed:
            for name in new_command_servers:
                if name in current_command_servers:
                    current_cmd = current_command_servers[name].get("command", [])

                    # Normalize new server command to array format
                    new_config_cmd = new_command_servers[name].get("command", [])
                    new_config_args = new_command_servers[name].get("args", [])
                    if isinstance(new_config_cmd, str):
                        new_cmd = [new_config_cmd] + new_config_args
                    elif isinstance(new_config_cmd, list):
                        new_cmd = new_config_cmd + new_config_args
                    else:
                        new_cmd = []

                    if current_cmd != new_cmd:
                        changes_needed = True
                        break
                else:
                    changes_needed = True
                    break

        if changes_needed:
            if not result.dry_run:
                # Remove servers that are no longer needed
                servers_to_remove = [name for name in current_servers if name not in new_servers]
                for name in servers_to_remove:
                    self.executor.remove_mcp_server(client_id, client_config, name)

                # Add/update servers
                for name, config in new_servers.items():
                    if name not in current_servers or current_servers[name] != config:
                        # Check if this is a URL-based server (SSE/HTTP)
                        url = config.get("url")
                        if url:
                            # This is a URL-based server - skip for now
                            self.logger.info(
                                f"Skipping URL-based server {name} (URL: {url}) - "
                                "CLI client URL support not fully implemented"
                            )
                            continue

                        command = config.get("command", [])
                        args = config.get("args", [])
                        env_vars = config.get("env", {})

                        # Build full command array - combine command and args
                        if isinstance(command, str):
                            full_command = [command] + args
                        elif isinstance(command, list):
                            full_command = command + args
                        else:
                            full_command = []

                        self.logger.debug(
                            f"Processing server {name}: command={command}, args={args}, "
                            f"full_command={full_command}"
                        )
                        if full_command:
                            self.executor.add_mcp_server(
                                client_id, client_config, name, full_command, env_vars
                            )
                        else:
                            self.logger.warning(f"Skipping server {name} - no valid command")

            # Always record the location as updated (even in dry-run)
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
        global_config = self.settings.get_global_config()
        status["global_servers"] = {
            name: config.model_dump() for name, config in global_config.mcpServers.items()
        }

        # Project servers
        project_config = self._get_project_config()
        if project_config:
            status["project_servers"] = project_config.get("mcpServers", {})

        # Location servers
        locations_config = self.settings.get_locations_config()
        locations = [loc.model_dump() for loc in locations_config.locations]
        for location in locations:
            # Handle CLI clients differently from file-based clients
            if location.get("config_type") == "cli" or location["path"].startswith("cli:"):
                client_id = (
                    location["path"].replace("cli:", "")
                    if location["path"].startswith("cli:")
                    else location["name"]
                )
                client_definitions = self.settings.get_client_definitions()
                client_config = client_definitions.clients.get(client_id)
                if client_config:
                    cli_servers = self.executor.get_mcp_servers(client_id, client_config)
                else:
                    cli_servers = None
                if cli_servers is not None:
                    status["location_servers"][location["name"]] = cli_servers
                else:
                    status["location_servers"][location["name"]] = {}
            else:
                # File-based client
                location_path = Path(location["path"])
                config = self._read_json_config(location_path)
                if config is not None:
                    status["location_servers"][location["name"]] = config.get("mcpServers", {})
                else:
                    status["location_servers"][location["name"]] = "error"

        return status

    def add_server_to_global(self, name: str, config: dict[str, Any]) -> bool:
        """Add server to global config"""
        from .config.models import MCPServerConfig

        global_config = self.settings.get_global_config()
        server_config = MCPServerConfig(**config)
        global_config.mcpServers[name] = server_config
        self.settings._save_global_config(global_config)
        return True

    def remove_server_from_global(self, name: str) -> bool:
        """Remove server from global config"""
        global_config = self.settings.get_global_config()
        if name in global_config.mcpServers:
            del global_config.mcpServers[name]
            self.settings._save_global_config(global_config)
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

    def vacuum_configs(
        self, auto_resolve: str | None = None, skip_existing: bool = False
    ) -> "VacuumResult":
        """Import existing MCP configs from all discovered locations"""
        result = VacuumResult(imported_servers={}, conflicts=[], errors=[], skipped_servers=[])

        # First, auto-discover clients and add them as locations
        from .clients.repository import ClientRepository

        repository = ClientRepository()
        discovered_clients = repository.discover_clients()

        # Add discovered clients as locations if they're not already registered
        for client in discovered_clients:
            if not self.settings.add_location(client["path"], client["client_name"]):
                self.logger.debug(f"Location {client['path']} already exists")

        # Get all locations (including newly discovered ones)
        locations_config = self.settings.get_locations_config()
        locations = [loc.model_dump() for loc in locations_config.locations]
        discovered_servers: dict[str, dict[str, Any]] = {}  # server_name -> {config, source_name}

        # Scan all locations for existing servers
        for location in locations:
            # Handle CLI-based clients
            if location.get("config_type") == "cli" or location["path"].startswith("cli:"):
                client_id = (
                    location["path"].replace("cli:", "")
                    if location["path"].startswith("cli:")
                    else location["name"]
                )
                client_definitions = self.settings.get_client_definitions()
                client_config = client_definitions.clients.get(client_id)
                if client_config:
                    cli_servers = self.executor.get_mcp_servers(client_id, client_config)
                else:
                    cli_servers = None

                if cli_servers:
                    for server_name, server_config in cli_servers.items():
                        if server_name in discovered_servers:
                            # Conflict found - need to resolve
                            existing = discovered_servers[server_name]
                            if auto_resolve == "first":
                                choice = "existing"
                            elif auto_resolve == "last":
                                choice = "new"
                            else:
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
                continue

            # Handle file-based clients
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
                    if auto_resolve == "first":
                        choice = "existing"
                    elif auto_resolve == "last":
                        choice = "new"
                    else:
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
            from .config.models import MCPServerConfig

            global_config = self.settings.get_global_config()

            for server_name, server_info in discovered_servers.items():
                if skip_existing and server_name in global_config.mcpServers:
                    result.skipped_servers.append(server_name)
                    continue

                # Skip URL-based servers as they're not supported by MCPServerConfig
                config_data = server_info["config"].copy()
                if "url" in config_data and "command" not in config_data:
                    self.logger.info(
                        f"Skipping URL-based server {server_name} - "
                        "not supported by current config model"
                    )
                    result.skipped_servers.append(server_name)
                    continue

                # Normalize command format for MCPServerConfig validation
                if "command" in config_data and isinstance(config_data["command"], str):
                    config_data["command"] = [config_data["command"]]

                try:
                    server_config = MCPServerConfig(**config_data)
                    global_config.mcpServers[server_name] = server_config
                    result.imported_servers[server_name] = server_info["source"]
                except Exception as e:
                    self.logger.warning(f"Failed to import server {server_name}: {e}")
                    result.errors.append(
                        {
                            "location": server_info["source"],
                            "error": f"Failed to import {server_name}: {str(e)}",
                        }
                    )

            self.settings._save_global_config(global_config)

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
