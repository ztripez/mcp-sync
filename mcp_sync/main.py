import argparse
import json
import logging
import sys
from pathlib import Path

from . import setup_logging
from .config import ConfigManager
from .sync import SyncEngine

logger = logging.getLogger(__name__)


def create_parser():
    parser = argparse.ArgumentParser(
        prog="mcp-sync",
        description="Sync MCP (Model Context Protocol) configurations across AI tools",
    )

    # Global options
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Discovery and status commands
    subparsers.add_parser("scan", help="Auto-discover known MCP configs")
    subparsers.add_parser("status", help="Show sync status")
    subparsers.add_parser("diff", help="Show config differences")

    # Config location management
    add_location_parser = subparsers.add_parser(
        "add-location", help="Register custom config file path"
    )
    add_location_parser.add_argument("path", help="Path to config file")
    add_location_parser.add_argument("--name", help="Friendly name for the location")

    remove_location_parser = subparsers.add_parser(
        "remove-location", help="Unregister config location"
    )
    remove_location_parser.add_argument("path", help="Path to config file")

    subparsers.add_parser("list-locations", help="Show all registered config paths")

    # Sync operations
    sync_parser = subparsers.add_parser("sync", help="Sync all registered configs")
    sync_parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without applying"
    )
    sync_parser.add_argument("--global-only", action="store_true", help="Sync only global configs")
    sync_parser.add_argument(
        "--project-only", action="store_true", help="Sync only project configs"
    )
    sync_parser.add_argument("--location", help="Sync specific location only")

    # Server management
    add_server_parser = subparsers.add_parser("add-server", help="Add MCP server to sync")
    add_server_parser.add_argument("name", help="Server name")
    add_server_parser.add_argument("--cmd", dest="server_cmd", help="Command to run the server")
    add_server_parser.add_argument("--args", help="Command arguments (comma-separated)")
    add_server_parser.add_argument("--env", help="Environment variables (KEY=value,KEY2=value2)")
    add_server_parser.add_argument("--scope", choices=["global", "project"], help="Config scope")

    remove_server_parser = subparsers.add_parser("remove-server", help="Remove server from sync")
    remove_server_parser.add_argument("name", help="Server name")
    remove_server_parser.add_argument("--scope", choices=["global", "project"], help="Config scope")

    subparsers.add_parser("list-servers", help="Show all managed servers")

    # Migration
    vacuum_parser = subparsers.add_parser(
        "vacuum", help="Import existing MCP configs from all discovered locations"
    )
    vacuum_parser.add_argument(
        "--auto-resolve", choices=["first", "last"], help="Auto-resolve conflicts without prompts"
    )
    vacuum_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not overwrite servers already in global config",
    )

    # Project management
    subparsers.add_parser("init", help="Create project .mcp.json")
    subparsers.add_parser("template", help="Show template config")

    # Client management
    subparsers.add_parser("list-clients", help="Show all supported clients")
    subparsers.add_parser("client-info", help="Show detailed client information").add_argument(
        "client", nargs="?", help="Client ID to show info for"
    )
    subparsers.add_parser(
        "edit-client-definitions", help="Open user client definitions file for editing"
    )

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else args.log_level
    setup_logging(log_level)

    logger.debug(f"Starting mcp-sync with command: {args.command}")
    logger.debug(f"Arguments: {vars(args)}")

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        config_manager = ConfigManager()
        sync_engine = SyncEngine(config_manager)
        logger.debug("Initialized ConfigManager and SyncEngine")
    except Exception as e:
        logger.error(f"Failed to initialize configuration: {e}")
        print(f"Error: Failed to initialize configuration: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        match args.command:
            case "scan":
                handle_scan(config_manager)
            case "status":
                handle_status(sync_engine)
            case "diff":
                handle_diff(sync_engine)
            case "add-location":
                handle_add_location(config_manager, args.path, args.name)
            case "remove-location":
                handle_remove_location(config_manager, args.path)
            case "list-locations":
                handle_list_locations(config_manager)
            case "sync":
                handle_sync(sync_engine, args)
            case "add-server":
                handle_add_server(sync_engine, args)
            case "remove-server":
                handle_remove_server(sync_engine, args)
            case "list-servers":
                handle_list_servers(sync_engine)
            case "vacuum":
                handle_vacuum(sync_engine, args.auto_resolve, args.skip_existing)
            case "init":
                handle_init()
            case "template":
                handle_template()
            case "list-clients":
                handle_list_clients(config_manager)
            case "client-info":
                handle_client_info(config_manager, args.client)
            case "edit-client-definitions":
                handle_edit_client_definitions(config_manager)
            case _:
                logger.error(f"Unknown command: {args.command}")
                print(f"Unknown command: {args.command}")
                sys.exit(1)

        logger.debug(f"Command {args.command} completed successfully")

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\nOperation cancelled.")
        sys.exit(130)  # Standard exit code for SIGINT
    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        print(f"Error: Permission denied. {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"Error: File not found. {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        print(f"Error: Invalid JSON in configuration file. {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during {args.command}: {e}", exc_info=True)
        print(
            "Error: An unexpected error occurred. Use --verbose for more details.", file=sys.stderr
        )
        if args.verbose:
            print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)


def handle_scan(config_manager):
    print("Scanning for MCP configurations...")
    configs = config_manager.scan_configs()

    if not configs:
        print("No registered config locations found.")
        return

    for config_info in configs:
        location = config_info["location"]
        status = config_info["status"]

        print(f"\n{location['name']} ({location.get('type', 'Unknown')})")
        print(f"  Path: {location['path']}")
        print(f"  Status: {status}")

        if config_info["config"] and status == "found":
            mcp_servers = config_info["config"].get("mcpServers", {})
            if mcp_servers:
                print(f"  Servers: {', '.join(mcp_servers.keys())}")
            else:
                print("  Servers: none")


def handle_status(sync_engine):
    print("Server Status:")
    status = sync_engine.get_server_status()

    print("\nGlobal Servers:")
    global_servers = status["global_servers"]
    if global_servers:
        for name, config in global_servers.items():
            print(f"  {name}: {config.get('command', 'unknown')}")
    else:
        print("  None")

    print("\nProject Servers:")
    project_servers = status["project_servers"]
    if project_servers:
        for name, config in project_servers.items():
            print(f"  {name}: {config.get('command', 'unknown')}")
    else:
        print("  None")

    print("\nLocation Status:")
    for location_name, servers in status["location_servers"].items():
        if servers == "error":
            print(f"  {location_name}: ERROR reading config")
        elif servers:
            print(f"  {location_name}: {len(servers)} servers")
        else:
            print(f"  {location_name}: No servers")


def handle_diff(sync_engine):
    print("Checking for differences...")

    # Simulate a dry run to see what would change
    result = sync_engine.sync_all(dry_run=True)

    if not result.updated_locations and not result.conflicts:
        print("All configurations are in sync.")
        return

    if result.updated_locations:
        print("\nLocations that would be updated:")
        for location in result.updated_locations:
            print(f"  {location}")

    if result.conflicts:
        print("\nConflicts detected:")
        for conflict in result.conflicts:
            print(f"  Server '{conflict['server']}' in {conflict['location']}")
            print(f"    Current: {conflict['current']}")
            print(f"    Master ({conflict['source']}): {conflict['master']}")


def handle_add_location(config_manager, path, name):
    if config_manager.add_location(path, name):
        print(f"Added location: {path}")
        if name:
            print(f"  Name: {name}")
    else:
        print(f"Location already exists: {path}")


def handle_remove_location(config_manager, path):
    if config_manager.remove_location(path):
        print(f"Removed location: {path}")
    else:
        print(f"Location not found: {path}")


def handle_list_locations(config_manager):
    locations = config_manager.get_locations()

    if not locations:
        print("No registered locations.")
        return

    print("Registered config locations:")
    for location in locations:
        name = location.get("name", "Unnamed")
        location_type = location.get("type", "Unknown")
        path = location.get("path", "No path")
        print(f"  {name} ({location_type})")
        print(f"    Path: {path}")


def handle_sync(sync_engine, args):
    print("Syncing configurations...")

    result = sync_engine.sync_all(
        dry_run=args.dry_run,
        global_only=args.global_only,
        project_only=args.project_only,
        specific_location=args.location,
    )

    if args.dry_run:
        print("DRY RUN - No changes made")

    if result.updated_locations:
        action = "Would update" if args.dry_run else "Updated"
        print(f"\n{action} {len(result.updated_locations)} locations:")
        for location in result.updated_locations:
            print(f"  {location}")

    if result.conflicts:
        print(f"\nConflicts detected ({len(result.conflicts)}):")
        for conflict in result.conflicts:
            print(f"  Server '{conflict['server']}' in {conflict['location']}")
            print(f"    Resolved using {conflict['source']} config")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  {error['location']}: {error['error']}")

    if not result.updated_locations and not result.conflicts and not result.errors:
        print("All configurations are already in sync.")


def handle_add_server(sync_engine, args):
    name = args.name

    try:
        # Check if inline parameters provided
        if args.server_cmd and args.scope:
            # Inline mode
            scope = args.scope
            config = _build_server_config_from_args(args)
        else:
            # Interactive mode
            scope = _prompt_for_server_scope()
            config = _prompt_for_server_config(name)

        if scope == "global":
            sync_engine.add_server_to_global(name, config)
            print(f"Added '{name}' to global config")
        else:
            sync_engine.add_server_to_project(name, config)
            print(f"Added '{name}' to project config")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled")


def _build_server_config_from_args(args):
    """Build server config from inline command arguments"""
    config = {"command": args.server_cmd}

    if args.args:
        config["args"] = [arg.strip() for arg in args.args.split(",")]

    if args.env:
        env_vars = {}
        for pair in args.env.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                env_vars[key.strip()] = value.strip()
        if env_vars:
            config["env"] = env_vars

    return config


def _prompt_for_server_scope():
    print("Add server to:")
    print("1. Global config")
    print("2. Project config")

    choice = input("Choose (1 or 2): ").strip()
    if choice == "1":
        return "global"
    elif choice == "2":
        return "project"
    else:
        print("Invalid choice")
        return _prompt_for_server_scope()


def _prompt_for_server_config(name):
    print(f"\nEnter server configuration for '{name}':")
    command = input("Command: ").strip()

    config = {"command": command}

    args_input = input("Args (comma-separated): ").strip()
    if args_input:
        config["args"] = [arg.strip() for arg in args_input.split(",")]

    env_vars = _prompt_for_env_vars()
    if env_vars:
        config["env"] = env_vars

    return config


def _prompt_for_env_vars():
    env_input = input("Environment variables (KEY=value, comma-separated, optional): ").strip()
    if not env_input:
        return {}

    env_vars = {}
    for pair in env_input.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            env_vars[key.strip()] = value.strip()
    return env_vars


def handle_remove_server(sync_engine, args):
    name = args.name

    try:
        # Check if inline scope provided
        if args.scope:
            scope = args.scope
        else:
            scope = _prompt_for_removal_scope(name)

        if scope == "global":
            if sync_engine.remove_server_from_global(name):
                print(f"Removed '{name}' from global config")
            else:
                print(f"Server '{name}' not found in global config")
        else:
            print("Project server removal not implemented yet")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled")


def _prompt_for_removal_scope(name):
    print(f"Remove server '{name}' from:")
    print("1. Global config")
    print("2. Project config")

    choice = input("Choose (1 or 2): ").strip()
    if choice == "1":
        return "global"
    elif choice == "2":
        return "project"
    else:
        print("Invalid choice")
        return _prompt_for_removal_scope(name)


def handle_list_servers(sync_engine):
    status = sync_engine.get_server_status()
    all_servers = _get_all_server_names(status)

    if not all_servers:
        print("No servers configured.")
        return

    print("Configured servers:")
    for server_name in sorted(all_servers):
        sources = _get_server_sources(server_name, status)
        _display_server_info(server_name, sources, status)


def _get_all_server_names(status):
    all_servers = set()
    all_servers.update(status["global_servers"].keys())
    all_servers.update(status["project_servers"].keys())
    return all_servers


def _get_server_sources(server_name, status):
    sources = []
    if server_name in status["global_servers"]:
        sources.append("global")
    if server_name in status["project_servers"]:
        sources.append("project")
    return sources


def _display_server_info(server_name, sources, status):
    print(f"  {server_name} ({', '.join(sources)})")

    config = _get_effective_config(server_name, status)
    print(f"    Command: {config.get('command', 'unknown')}")
    if config.get("args"):
        print(f"    Args: {config['args']}")
    if config.get("env"):
        print(f"    Env: {config['env']}")


def _get_effective_config(server_name, status):
    if server_name in status["project_servers"]:
        return status["project_servers"][server_name]
    else:
        return status["global_servers"][server_name]


def handle_init():
    project_config = {"mcpServers": {}}

    config_path = Path(".mcp.json")
    if config_path.exists():
        print(".mcp.json already exists")
        return

    with open(config_path, "w") as f:
        json.dump(project_config, f, indent=2)

    print("Created .mcp.json in current directory")


def handle_vacuum(sync_engine, auto_resolve: str | None, skip_existing: bool):
    """Import existing MCP configs from all discovered locations"""
    try:
        result = sync_engine.vacuum_configs(auto_resolve=auto_resolve, skip_existing=skip_existing)

        if not result.imported_servers and not result.conflicts:
            print("No MCP servers found in any discovered locations.")
            return

        # Show imported servers
        if result.imported_servers:
            print(f"Successfully imported {len(result.imported_servers)} servers:")
            for server_name, source in result.imported_servers.items():
                print(f"  {server_name} (from {source})")

        # Show conflicts that were resolved
        if result.conflicts:
            print(f"\nResolved {len(result.conflicts)} conflicts:")
            for conflict in result.conflicts:
                print(f"  {conflict['server']} - kept version from {conflict['chosen_source']}")

        if result.skipped_servers:
            print(f"\nSkipped {len(result.skipped_servers)} existing servers:")
            for name in result.skipped_servers:
                print(f"  {name}")

        print("\nVacuum complete! Run 'mcp-sync sync' to standardize all configs.")

    except (KeyboardInterrupt, EOFError):
        print("\nVacuum cancelled")


def handle_template():
    template = {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/directory"],
            },
            "custom-server": {
                "command": "python",
                "args": ["/path/to/custom/server.py"],
                "env": {"API_KEY": "your-api-key"},
            },
        }
    }

    print("MCP Configuration Template:")
    print(json.dumps(template, indent=2))


def handle_list_clients(config_manager):
    """List all supported clients"""
    clients = config_manager.client_definitions.get("clients", {})

    if not clients:
        print("No client definitions found.")
        return

    print("Supported Clients:")
    for client_id, client_config in clients.items():
        name = client_config.get("name", client_id)
        description = client_config.get("description", "")

        # Check if client is found on this system
        location = config_manager._get_client_location(client_id, client_config)
        status = "✅ Found" if location else "❌ Not found"

        print(f"  {client_id}: {name} - {status}")
        if description:
            print(f"    {description}")


def handle_client_info(config_manager, client_id):
    """Show detailed information about a client"""
    clients = config_manager.client_definitions.get("clients", {})

    if not client_id:
        print("Available clients:")
        for cid in clients.keys():
            print(f"  {cid}")
        return

    if client_id not in clients:
        print(f"Client '{client_id}' not found.")
        print("Use 'mcp-sync list-clients' to see available clients.")
        return

    client_config = clients[client_id]
    print(f"Client: {client_config.get('name', client_id)}")
    print(f"Description: {client_config.get('description', 'No description')}")

    print("\nPaths:")
    for platform, path in client_config.get("paths", {}).items():
        print(f"  {platform}: {path}")

    print(f"\nConfig format: {client_config.get('config_format', 'unknown')}")
    print(f"MCP key: {client_config.get('mcp_key', 'unknown')}")

    # Check if found on current system
    location = config_manager._get_client_location(client_id, client_config)
    if location:
        print(f"\n✅ Found on this system: {location['path']}")
    else:
        platform_name = config_manager._get_platform_name()
        expected_path = client_config.get("paths", {}).get(platform_name, "unknown")
        expanded_path = (
            config_manager._expand_path_template(expected_path)
            if expected_path != "unknown"
            else "unknown"
        )
        print("\n❌ Not found on this system")
        print(f"Expected location: {expanded_path}")


def handle_edit_client_definitions(config_manager):
    """Open user client definitions file for editing"""
    import logging
    import os
    import re
    import subprocess

    logger = logging.getLogger(__name__)

    # Ensure the file exists
    if not config_manager.user_client_definitions_file.exists():
        # Create with template
        template = {
            "clients": {
                "example-client": {
                    "name": "Example Client",
                    "description": "Example client configuration",
                    "paths": {
                        "darwin": "~/path/to/client/config.json",
                        "windows": "%APPDATA%/Client/config.json",
                        "linux": "~/.config/client/config.json",
                    },
                    "config_format": "json",
                    "mcp_key": "mcpServers",
                }
            }
        }
        config_manager._save_user_client_definitions(template)
        print("Created user client definitions file with example.")

    file_path = config_manager.user_client_definitions_file
    print(f"Opening: {file_path}")

    # Try to open with default editor
    editor = os.environ.get("EDITOR", "nano")

    # Enhanced validation to prevent command injection
    if not editor or not isinstance(editor, str):
        print("Invalid or missing EDITOR environment variable.")
        print(f"Please manually edit: {file_path}")
        return

    # Only allow safe editor names (no paths, arguments, or shell metacharacters)
    if not re.match(r"^[a-zA-Z0-9_.-]+$", editor):
        logger.warning(f"Unsafe editor name detected: {editor}")
        print(f"Editor name contains unsafe characters: {editor}")
        print("Only alphanumeric characters, dots, hyphens, and underscores are allowed.")
        print(f"Please manually edit: {file_path}")
        return

    # Validate file path
    try:
        validated_path = Path(file_path).resolve()
        if not validated_path.exists():
            logger.error(f"File does not exist: {validated_path}")
            print(f"File does not exist: {validated_path}")
            return
    except (OSError, ValueError) as e:
        logger.error(f"Invalid file path: {e}")
        print(f"Invalid file path: {file_path}")
        return

    try:
        # Use subprocess.run with explicit arguments list (safer than shell=True)
        subprocess.run(  # noqa: S603 # Validated editor and file path with safe arguments
            [editor, str(validated_path)],
            check=True,
            timeout=300,  # 5 minute timeout for editing
            text=True,
        )
        print("Client definitions updated. Run 'mcp-sync scan' to reload.")
    except subprocess.TimeoutExpired:
        logger.warning("Editor timed out after 5 minutes")
        print("Editor session timed out.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Editor failed with exit code {e.returncode}")
        print(f"Editor failed with exit code {e.returncode}.")
        print(f"Please manually edit: {file_path}")
    except FileNotFoundError:
        logger.error(f"Editor not found: {editor}")
        print(f"Editor '{editor}' not found in PATH.")
        print(f"Please manually edit: {file_path}")
        print("Or set the EDITOR environment variable to a valid editor.")
    except Exception as e:
        logger.error(f"Unexpected error opening editor: {e}")
        print(f"Unexpected error: {e}")
        print(f"Please manually edit: {file_path}")


if __name__ == "__main__":
    main()
