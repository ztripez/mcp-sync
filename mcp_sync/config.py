import json
import logging
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


class ConfigManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
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
        config_type = client_config.get("config_type", "file")

        if config_type == "cli":
            if self._is_cli_available(client_config):
                return {
                    "path": f"cli:{client_id}",
                    "name": client_id,
                    "type": "auto",
                    "config_type": "cli",
                    "client_name": client_config.get("name", client_id),
                    "description": client_config.get("description", ""),
                }
        else:
            platform_name = self._get_platform_name()
            path_template = client_config.get("paths", {}).get(platform_name)

            if not path_template:
                fallback_paths = client_config.get("fallback_paths", {})
                path_template = fallback_paths.get(platform_name)

            if path_template:
                expanded_path = self._expand_path_template(path_template)
                if expanded_path.exists():
                    return {
                        "path": str(expanded_path),
                        "name": client_id,
                        "type": "auto",
                        "config_type": "file",
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

    def _validate_command_name(self, command: str) -> bool:
        """Validate that a command name is safe to execute"""
        if not command or not isinstance(command, str):
            return False

        # Only allow alphanumeric characters, hyphens, underscores, and dots
        # This prevents shell injection and command chaining
        pattern = re.compile(r"^[a-zA-Z0-9_.-]+$")
        return bool(pattern.match(command))

    def _validate_file_path(self, path: str) -> bool:
        """Validate that a file path is safe"""
        if not path or not isinstance(path, str):
            return False

        try:
            # Convert to Path to normalize and validate
            Path(path).resolve()
            # Ensure it's not trying to escape to system directories
            return not any(part.startswith("..") for part in Path(path).parts)
        except (OSError, ValueError):
            return False

    def _sanitize_command_args(self, args: list[str]) -> list[str]:
        """Sanitize command arguments to prevent injection"""
        if not args:
            return []

        sanitized = []
        for arg in args:
            if isinstance(arg, str):
                # Use shlex.quote to properly escape arguments
                sanitized.append(shlex.quote(arg))
            else:
                # Convert to string and quote
                sanitized.append(shlex.quote(str(arg)))

        return sanitized

    def _is_cli_available(self, client_config: dict[str, Any]) -> bool:
        """Check if CLI tool is available by testing a simple command"""
        cli_commands = client_config.get("cli_commands", {})
        list_command = cli_commands.get("list_mcp")

        if not list_command:
            self.logger.debug("No list_mcp command defined in client config")
            return False

        try:
            # Extract base command (e.g., "claude" from "claude mcp list")
            command_parts = shlex.split(list_command)
            if not command_parts:
                self.logger.warning("Empty command in client config")
                return False

            base_cmd = command_parts[0]

            # Validate the base command name
            if not self._validate_command_name(base_cmd):
                self.logger.warning(f"Invalid command name: {base_cmd}")
                return False

            # Use subprocess with list of arguments (safer than shell=True)
            result = subprocess.run(  # noqa: S603 # Validated command with safe arguments
                [base_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,  # Don't raise exception on non-zero exit
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout checking CLI availability for {base_cmd}")
            return False
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            self.logger.debug(f"CLI not available: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error checking CLI availability: {e}")
            return False

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

    def get_cli_mcp_servers(self, client_id: str) -> dict[str, Any] | None:
        """Get MCP servers from CLI-based client"""
        if not client_id or not isinstance(client_id, str):
            self.logger.warning("Invalid client_id provided")
            return None

        client_config = self.client_definitions.get("clients", {}).get(client_id)
        if not client_config or client_config.get("config_type") != "cli":
            self.logger.debug(f"Client {client_id} is not a CLI client")
            return None

        cli_commands = client_config.get("cli_commands", {})
        list_command = cli_commands.get("list_mcp")

        if not list_command:
            self.logger.warning(f"No list_mcp command for client {client_id}")
            return None

        try:
            # Safely parse the command
            command_parts = shlex.split(list_command)
            if not command_parts:
                self.logger.warning(f"Empty list command for client {client_id}")
                return None

            # Validate the base command
            if not self._validate_command_name(command_parts[0]):
                self.logger.warning(f"Invalid command name in list_mcp: {command_parts[0]}")
                return None

            result = subprocess.run(  # noqa: S603 # Validated command with safe arguments
                command_parts, capture_output=True, text=True, timeout=10, check=False
            )

            if result.returncode == 0:
                # Parse the output - claude mcp list returns server definitions
                servers = {}
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        # Format: "server_name: command args"
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            name = parts[0].strip()
                            command_line = parts[1].strip()
                            # Validate server name
                            if name and re.match(r"^[a-zA-Z0-9_-]+$", name):
                                servers[name] = {"command": shlex.split(command_line)}
                return servers
            else:
                self.logger.warning(f"CLI command failed for {client_id}: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout getting MCP servers for {client_id}")
        except (subprocess.SubprocessError, ValueError) as e:
            self.logger.error(f"Error getting MCP servers for {client_id}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error getting MCP servers for {client_id}: {e}")

        return None

    def add_cli_mcp_server(
        self,
        client_id: str,
        name: str,
        command: list[str],
        env_vars: dict[str, str] | None = None,
        scope: str = "local",
    ) -> bool:
        """Add MCP server to CLI-based client"""
        # Input validation
        if not client_id or not isinstance(client_id, str):
            self.logger.warning("Invalid client_id provided")
            return False

        if not name or not isinstance(name, str) or not re.match(r"^[a-zA-Z0-9_-]+$", name):
            self.logger.warning(f"Invalid server name: {name}")
            return False

        if not command or not isinstance(command, list) or not command[0]:
            self.logger.warning("Invalid command provided")
            return False

        if scope not in ["local", "user", "project"]:
            self.logger.warning(f"Invalid scope: {scope}")
            return False

        client_config = self.client_definitions.get("clients", {}).get(client_id)
        if not client_config or client_config.get("config_type") != "cli":
            self.logger.debug(f"Client {client_id} is not a CLI client")
            return False

        cli_commands = client_config.get("cli_commands", {})
        add_template = cli_commands.get("add_mcp")

        if not add_template:
            self.logger.warning(f"No add_mcp command template for client {client_id}")
            return False

        try:
            # Validate command parts
            if not self._validate_command_name(command[0]):
                self.logger.warning(f"Invalid command name: {command[0]}")
                return False

            # Build environment flags safely
            env_flags = []
            if env_vars:
                for key, value in env_vars.items():
                    # Validate env var names
                    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                        self.logger.warning(f"Invalid environment variable name: {key}")
                        continue
                    env_flags.extend(["-e", f"{key}={value}"])

            # Safely build the command using individual components
            # Don't use string formatting with user input - build args list directly
            cmd_parts = []
            template_parts = shlex.split(add_template)

            for part in template_parts:
                if "{scope}" in part:
                    cmd_parts.append(part.replace("{scope}", scope))
                elif "{transport}" in part:
                    cmd_parts.append(part.replace("{transport}", "stdio"))
                elif "{env_flags}" in part:
                    cmd_parts.extend(env_flags)
                elif "{name}" in part:
                    cmd_parts.append(part.replace("{name}", name))
                elif "{command}" in part:
                    cmd_parts.append(part.replace("{command}", command[0]))
                elif "{args}" in part:
                    cmd_parts.extend(command[1:])  # Add args as separate elements
                elif "{command_args}" in part:
                    # Combine command parts into a single quoted string for Claude CLI
                    command_str = shlex.join(command)
                    cmd_parts.append(command_str)
                else:
                    cmd_parts.append(part)

            # Remove any empty parts
            cmd_parts = [part for part in cmd_parts if part and part.strip()]

            result = subprocess.run(  # noqa: S603 # Validated command with safe arguments
                cmd_parts, capture_output=True, text=True, timeout=10, check=False
            )

            if result.returncode == 0:
                self.logger.info(f"Successfully added MCP server {name} to {client_id}")
                return True
            else:
                self.logger.warning(f"Failed to add MCP server {name}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout adding MCP server {name} to {client_id}")
            return False
        except (subprocess.SubprocessError, ValueError) as e:
            self.logger.error(f"Error adding MCP server {name} to {client_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error adding MCP server {name}: {e}")
            return False

    def remove_cli_mcp_server(self, client_id: str, name: str, scope: str | None = None) -> bool:
        """Remove MCP server from CLI-based client"""
        # Input validation
        if not client_id or not isinstance(client_id, str):
            self.logger.warning("Invalid client_id provided")
            return False

        if not name or not isinstance(name, str) or not re.match(r"^[a-zA-Z0-9_-]+$", name):
            self.logger.warning(f"Invalid server name: {name}")
            return False

        client_config = self.client_definitions.get("clients", {}).get(client_id)
        if not client_config or client_config.get("config_type") != "cli":
            self.logger.debug(f"Client {client_id} is not a CLI client")
            return False

        cli_commands = client_config.get("cli_commands", {})
        remove_template = cli_commands.get("remove_mcp")

        if not remove_template:
            self.logger.warning(f"No remove_mcp command template for client {client_id}")
            return False

        # If no scope provided, try to detect it by getting server details
        if scope is None:
            scope = self._detect_cli_server_scope(client_id, name)

        if scope not in ["local", "user", "project"]:
            self.logger.warning(f"Invalid scope detected: {scope}")
            scope = "local"  # Fallback to safe default

        try:
            # Safely build command parts
            cmd_parts = []
            template_parts = shlex.split(remove_template)

            for part in template_parts:
                if "{scope}" in part:
                    cmd_parts.append(part.replace("{scope}", scope))
                elif "{name}" in part:
                    cmd_parts.append(part.replace("{name}", name))
                else:
                    cmd_parts.append(part)

            result = subprocess.run(  # noqa: S603 # Validated command with safe arguments
                cmd_parts, capture_output=True, text=True, timeout=10, check=False
            )

            if result.returncode == 0:
                self.logger.info(f"Successfully removed MCP server {name} from {client_id}")
                return True
            else:
                self.logger.warning(f"Failed to remove MCP server {name}: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.warning(f"Timeout removing MCP server {name} from {client_id}")
            return False
        except (subprocess.SubprocessError, ValueError) as e:
            self.logger.error(f"Error removing MCP server {name} from {client_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error removing MCP server {name}: {e}")
            return False

    def _detect_cli_server_scope(self, client_id: str, name: str) -> str:
        """Detect the scope of a CLI MCP server"""
        # Input validation
        if not client_id or not isinstance(client_id, str):
            return "local"

        if not name or not isinstance(name, str) or not re.match(r"^[a-zA-Z0-9_-]+$", name):
            return "local"

        client_config = self.client_definitions.get("clients", {}).get(client_id)
        if not client_config or client_config.get("config_type") != "cli":
            return "local"

        cli_commands = client_config.get("cli_commands", {})
        get_template = cli_commands.get("get_mcp")

        if not get_template:
            return "local"

        try:
            # Safely build command parts
            cmd_parts = []
            template_parts = shlex.split(get_template)

            for part in template_parts:
                if "{name}" in part:
                    cmd_parts.append(part.replace("{name}", name))
                else:
                    cmd_parts.append(part)

            result = subprocess.run(  # noqa: S603 # Validated command with safe arguments
                cmd_parts, capture_output=True, text=True, timeout=10, check=False
            )

            if result.returncode == 0:
                # Parse output to find scope
                output = result.stdout.lower()
                if "scope: user" in output:
                    return "user"
                elif "scope: project" in output:
                    return "project"
                elif "scope: local" in output:
                    return "local"

        except subprocess.TimeoutExpired:
            self.logger.debug(f"Timeout detecting scope for {name} in {client_id}")
        except (subprocess.SubprocessError, ValueError) as e:
            self.logger.debug(f"Error detecting scope for {name} in {client_id}: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error detecting scope for {name}: {e}")

        return "local"  # Default fallback
