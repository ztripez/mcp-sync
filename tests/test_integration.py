"""Integration tests for the full client management workflow"""

import tempfile
from pathlib import Path

from mcp_sync.config import ConfigManager


def test_full_client_management_workflow():
    """Test the complete workflow of client management"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup a custom config manager
        cm = ConfigManager()
        cm.config_dir = Path(temp_dir)
        cm.locations_file = cm.config_dir / "locations.json"
        cm.global_config_file = cm.config_dir / "global.json"
        cm.user_client_definitions_file = cm.config_dir / "client_definitions.json"

        # Initialize the config directory
        cm._ensure_config_dir()

        # Should have empty user client definitions
        user_defs = cm._load_client_definitions()
        assert "clients" in user_defs

        # Add a custom client definition
        custom_client = {
            "name": "Test IDE",
            "description": "A test IDE for development",
            "paths": {
                "linux": "~/.config/test-ide/settings.json",
                "darwin": "~/Library/Application Support/TestIDE/settings.json",
                "windows": "%APPDATA%/TestIDE/settings.json",
            },
            "config_format": "json",
            "mcp_key": "mcpServers",
        }

        # Save custom client
        user_defs = {"clients": {"test-ide": custom_client}}
        cm._save_user_client_definitions(user_defs)

        # Reload and verify custom client is merged with built-ins
        cm.client_definitions = cm._load_client_definitions()
        clients = cm.client_definitions.get("clients", {})

        # Should have both built-in and custom clients
        assert "claude-desktop" in clients  # Built-in
        assert "test-ide" in clients  # Custom
        assert clients["test-ide"]["name"] == "Test IDE"

        # Test path expansion for custom client
        location = cm._get_client_location("test-ide", custom_client)
        # Should be None since path doesn't exist
        assert location is None

        # Test with existing path
        test_config_path = Path(temp_dir) / "test_settings.json"
        test_config_path.write_text('{"mcpServers": {}}')

        custom_client_existing = custom_client.copy()
        current_platform = cm._get_platform_name()
        custom_client_existing["paths"][current_platform] = str(test_config_path)

        location = cm._get_client_location("test-ide", custom_client_existing)
        assert location is not None
        assert location["path"] == str(test_config_path)
        assert location["client_name"] == "Test IDE"


def test_platform_specific_paths():
    """Test that platform-specific paths work correctly"""
    cm = ConfigManager()

    # Test each platform name
    platforms = ["darwin", "windows", "linux"]
    current_platform = cm._get_platform_name()
    assert current_platform in platforms

    # Test path expansion with different templates
    test_cases = [
        ("~/test/path.json", Path("test/path.json")),
        ("~/.config/app/settings.json", Path(".config/app/settings.json")),
    ]

    for template, expected_path in test_cases:
        expanded = cm._expand_path_template(template)
        expanded_path = Path(expanded)
        assert str(expanded_path).startswith(str(Path.home()))
        # Compare path parts for cross-platform compatibility
        assert expanded_path.parts[-len(expected_path.parts) :] == expected_path.parts


def test_default_locations_discovery():
    """Test that default location discovery works with new config system"""
    cm = ConfigManager()
    locations = cm._get_default_locations()

    # Should return a list of location dictionaries
    assert isinstance(locations, list)

    # Each location should have required fields
    for location in locations:
        assert "path" in location
        assert "name" in location
        assert "type" in location
        assert location["type"] == "auto"
        assert "client_name" in location

        # Path should exist (since it was discovered) or be a CLI client
        if location.get("config_type") == "cli":
            # CLI clients use special "cli:" prefix format
            assert location["path"].startswith("cli:")
        else:
            # File-based clients should have existing paths
            assert Path(location["path"]).exists()


def test_client_definitions_error_handling():
    """Test error handling when client definitions are malformed"""
    with tempfile.TemporaryDirectory() as temp_dir:
        cm = ConfigManager()
        cm.config_dir = Path(temp_dir)
        cm.user_client_definitions_file = cm.config_dir / "client_definitions.json"

        # Create malformed JSON
        cm.config_dir.mkdir(exist_ok=True)
        with open(cm.user_client_definitions_file, "w") as f:
            f.write("{ invalid json }")

        # Should handle error gracefully and fall back to built-in definitions
        definitions = cm._load_client_definitions()
        assert "clients" in definitions

        # Should still have built-in clients despite malformed user file
        clients = definitions["clients"]
        assert "claude-desktop" in clients
