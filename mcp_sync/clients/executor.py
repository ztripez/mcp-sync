"""Safe CLI execution for MCP client management."""

import logging
import re
import shlex
import subprocess
from typing import Any

from ..config.models import MCPClientConfig

logger = logging.getLogger(__name__)


class CLIExecutor:
    """Safe executor for CLI-based MCP client operations."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _validate_command_name(self, command: str) -> bool:
        """Validate that a command name is safe to execute."""
        if not command or not isinstance(command, str):
            return False

        # Only allow alphanumeric characters, hyphens, underscores, and dots
        pattern = re.compile(r"^[a-zA-Z0-9_.-]+$")
        return bool(pattern.match(command))

    def _sanitize_command_args(self, args: list[str]) -> list[str]:
        """Sanitize command arguments to prevent injection."""
        if not args:
            return []

        sanitized = []
        for arg in args:
            if isinstance(arg, str):
                sanitized.append(shlex.quote(arg))
            else:
                sanitized.append(shlex.quote(str(arg)))

        return sanitized

    def is_cli_available(self, client_config: MCPClientConfig) -> bool:
        """Check if CLI tool is available by testing a simple command."""
        if not client_config.cli_commands:
            self.logger.debug("No CLI commands defined in client config")
            return False

        list_command = client_config.cli_commands.get("list_mcp")
        if not list_command:
            self.logger.debug("No list_mcp command defined in client config")
            return False

        try:
            command_parts = shlex.split(list_command)
            if not command_parts:
                self.logger.warning("Empty command in client config")
                return False

            base_cmd = command_parts[0]

            if not self._validate_command_name(base_cmd):
                self.logger.warning(f"Invalid command name: {base_cmd}")
                return False

            result = subprocess.run(  # noqa: S603
                [base_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
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

    def get_mcp_servers(
        self, client_id: str, client_config: MCPClientConfig
    ) -> dict[str, Any] | None:
        """Get MCP servers from CLI-based client."""
        if not client_id or not isinstance(client_id, str):
            self.logger.warning("Invalid client_id provided")
            return None

        if client_config.config_type != "cli" or not client_config.cli_commands:
            self.logger.debug(f"Client {client_id} is not a CLI client")
            return None

        list_command = client_config.cli_commands.get("list_mcp")
        if not list_command:
            self.logger.warning(f"No list_mcp command for client {client_id}")
            return None

        try:
            command_parts = shlex.split(list_command)
            if not command_parts:
                self.logger.warning(f"Empty list command for client {client_id}")
                return None

            if not self._validate_command_name(command_parts[0]):
                self.logger.warning(f"Invalid command name in list_mcp: {command_parts[0]}")
                return None

            result = subprocess.run(  # noqa: S603
                command_parts, capture_output=True, text=True, timeout=10, check=False
            )

            if result.returncode == 0:
                servers = {}
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            name = parts[0].strip()
                            command_line = parts[1].strip()
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

    def add_mcp_server(
        self,
        client_id: str,
        client_config: MCPClientConfig,
        name: str,
        command: list[str],
        env_vars: dict[str, str] | None = None,
        scope: str = "local",
    ) -> bool:
        """Add MCP server to CLI-based client."""
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

        if client_config.config_type != "cli" or not client_config.cli_commands:
            self.logger.debug(f"Client {client_id} is not a CLI client")
            return False

        add_template = client_config.cli_commands.get("add_mcp")
        if not add_template:
            self.logger.warning(f"No add_mcp command template for client {client_id}")
            return False

        try:
            if not self._validate_command_name(command[0]):
                self.logger.warning(f"Invalid command name: {command[0]}")
                return False

            # Build environment flags safely
            env_flags = []
            if env_vars:
                for key, value in env_vars.items():
                    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                        self.logger.warning(f"Invalid environment variable name: {key}")
                        continue
                    env_flags.extend(["-e", f"{key}={value}"])

            # Build command parts
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
                    cmd_parts.extend(command[1:])
                elif "{command_args}" in part:
                    cmd_parts.append("--")
                    cmd_parts.extend(command)
                else:
                    cmd_parts.append(part)

            cmd_parts = [part for part in cmd_parts if part and part.strip()]

            result = subprocess.run(  # noqa: S603
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

    def remove_mcp_server(
        self, client_id: str, client_config: MCPClientConfig, name: str, scope: str | None = None
    ) -> bool:
        """Remove MCP server from CLI-based client."""
        if not client_id or not isinstance(client_id, str):
            self.logger.warning("Invalid client_id provided")
            return False

        if not name or not isinstance(name, str) or not re.match(r"^[a-zA-Z0-9_-]+$", name):
            self.logger.warning(f"Invalid server name: {name}")
            return False

        if client_config.config_type != "cli" or not client_config.cli_commands:
            self.logger.debug(f"Client {client_id} is not a CLI client")
            return False

        remove_template = client_config.cli_commands.get("remove_mcp")
        if not remove_template:
            self.logger.warning(f"No remove_mcp command template for client {client_id}")
            return False

        if scope is None:
            scope = self._detect_server_scope(client_id, client_config, name)

        if scope not in ["local", "user", "project"]:
            self.logger.warning(f"Invalid scope detected: {scope}")
            scope = "local"

        try:
            cmd_parts = []
            template_parts = shlex.split(remove_template)

            for part in template_parts:
                if "{scope}" in part:
                    cmd_parts.append(part.replace("{scope}", scope))
                elif "{name}" in part:
                    cmd_parts.append(part.replace("{name}", name))
                else:
                    cmd_parts.append(part)

            result = subprocess.run(  # noqa: S603
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

    def _detect_server_scope(
        self, client_id: str, client_config: MCPClientConfig, name: str
    ) -> str:
        """Detect the scope of a CLI MCP server."""
        if not client_id or not isinstance(client_id, str):
            return "local"

        if not name or not isinstance(name, str) or not re.match(r"^[a-zA-Z0-9_-]+$", name):
            return "local"

        if client_config.config_type != "cli" or not client_config.cli_commands:
            return "local"

        get_template = client_config.cli_commands.get("get_mcp")
        if not get_template:
            return "local"

        try:
            cmd_parts = []
            template_parts = shlex.split(get_template)

            for part in template_parts:
                if "{name}" in part:
                    cmd_parts.append(part.replace("{name}", name))
                else:
                    cmd_parts.append(part)

            result = subprocess.run(  # noqa: S603
                cmd_parts, capture_output=True, text=True, timeout=10, check=False
            )

            if result.returncode == 0:
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

        return "local"
