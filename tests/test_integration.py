"""Integration tests for the full client management workflow"""

import tempfile
from pathlib import Path

from mcp_sync.config.models import ClientDefinitions, MCPClientConfig
from mcp_sync.config.settings import Settings


def test_full_client_management_workflow():
    """Test the complete workflow of client management"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup a custom settings manager
        settings = Settings()
        settings.config_dir = Path(temp_dir)
        settings.locations_file = settings.config_dir / "locations.json"
        settings.global_config_file = settings.config_dir / "global.json"
        settings.user_client_definitions_file = settings.config_dir / "client_definitions.json"

        # Initialize the config directory
        settings._ensure_config_dir()

        # Should have empty user client definitions initially
        user_defs = ClientDefinitions()
        settings._save_user_client_definitions(user_defs)

        # Add a custom client definition
        custom_client = MCPClientConfig(
            name="Test IDE",
            description="A test IDE for development",
            paths={
                "linux": "~/.config/test-ide/settings.json",
                "darwin": "~/Library/Application Support/TestIDE/settings.json",
                "windows": "%APPDATA%/TestIDE/settings.json",
            },
            config_type="file",
        )

        # Save custom client
        user_defs = ClientDefinitions(clients={"test-ide": custom_client})
        settings._save_user_client_definitions(user_defs)

        # Clear cache and reload to verify custom client is merged with built-ins
        settings._client_definitions = None
        client_definitions = settings.get_client_definitions()
        clients = client_definitions.clients

        # Should have both built-in and custom clients
        assert "claude-desktop" in clients  # Built-in
        assert "test-ide" in clients  # Custom
        assert clients["test-ide"].name == "Test IDE"

        # Test with existing path
        test_config_path = Path(temp_dir) / "test_settings.json"
        test_config_path.write_text('{"mcpServers": {}}')

        # Create a repository to test client location detection
        from mcp_sync.clients.repository import ClientRepository

        repository = ClientRepository()

        # Test path expansion for custom client with existing file
        custom_client_existing = MCPClientConfig(
            name="Test IDE",
            description="A test IDE for development",
            paths={
                "linux": str(test_config_path),
                "darwin": str(test_config_path),
                "windows": str(test_config_path),
            },
            config_type="file",
        )

        location = repository._get_client_location("test-ide", custom_client_existing)
        assert location is not None
        assert location["path"] == str(test_config_path)
        assert location["client_name"] == "Test IDE"


def test_platform_specific_paths():
    """Test that platform-specific paths work correctly"""
    from mcp_sync.clients.repository import ClientRepository

    repository = ClientRepository()

    # Test each platform name
    platforms = ["darwin", "windows", "linux"]
    current_platform = repository._get_platform_name()
    assert current_platform in platforms

    # Test path expansion with different templates
    test_cases = [
        ("~/test/path.json", Path("test/path.json")),
        ("~/.config/app/settings.json", Path(".config/app/settings.json")),
    ]

    for template, expected_path in test_cases:
        expanded = repository._expand_path_template(template)
        expanded_path = Path(expanded)
        assert str(expanded_path).startswith(str(Path.home()))
        # Compare path parts for cross-platform compatibility
        assert expanded_path.parts[-len(expected_path.parts) :] == expected_path.parts


def test_default_locations_discovery():
    """Test that default location discovery works with new config system"""
    from mcp_sync.clients.repository import ClientRepository

    repository = ClientRepository()
    locations = repository.discover_clients()

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
        settings = Settings()
        settings.config_dir = Path(temp_dir)
        settings.user_client_definitions_file = settings.config_dir / "client_definitions.json"

        # Create malformed JSON
        settings.config_dir.mkdir(exist_ok=True)
        with open(settings.user_client_definitions_file, "w") as f:
            f.write("{ invalid json }")

        # Should handle error gracefully and fall back to built-in definitions
        definitions = settings.get_client_definitions()
        assert definitions.clients

        # Should still have built-in clients despite malformed user file
        clients = definitions.clients
        assert "claude-desktop" in clients


def test_settings_initialization():
    """Test that Settings initializes correctly"""
    with tempfile.TemporaryDirectory() as temp_dir:
        settings = Settings()
        settings.config_dir = Path(temp_dir)
        settings.locations_file = settings.config_dir / "locations.json"
        settings.global_config_file = settings.config_dir / "global.json"
        settings.user_client_definitions_file = settings.config_dir / "client_definitions.json"

        # Initialize the config directory
        settings._ensure_config_dir()

        # Check that all required files are created
        assert settings.config_dir.exists()
        assert settings.locations_file.exists()
        assert settings.global_config_file.exists()
        assert settings.user_client_definitions_file.exists()

        # Check that configurations can be loaded
        locations_config = settings.get_locations_config()
        assert locations_config.locations is not None

        global_config = settings.get_global_config()
        assert global_config.mcpServers is not None

        client_definitions = settings.get_client_definitions()
        assert client_definitions.clients is not None
