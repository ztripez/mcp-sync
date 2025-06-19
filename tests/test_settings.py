"""Comprehensive unit tests for Settings class."""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from mcp_sync.config.models import (
    ClientDefinitions,
    GlobalConfig,
    LocationConfig,
    LocationsConfig,
    MCPClientConfig,
    MCPServerConfig,
)
from mcp_sync.config.settings import Settings, get_settings


# Test fixtures
@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_settings(temp_config_dir):
    """Create a Settings instance with a temporary config directory."""
    with patch("mcp_sync.config.settings.user_config_dir") as mock_user_config:
        mock_user_config.return_value = str(temp_config_dir)
        settings = Settings()
        return settings


@pytest.fixture
def sample_locations_config():
    """Sample locations configuration data."""
    return LocationsConfig(
        locations=[
            LocationConfig(
                path="/home/user/.config/claude/claude_desktop_config.json",
                name="Claude Desktop",
                type="auto",
                config_type="file",
                client_name="claude-desktop",
            ),
            LocationConfig(
                path="/home/user/.config/test/config.json",
                name="Test Location",
                type="manual",
                config_type="file",
            ),
        ]
    )


@pytest.fixture
def sample_global_config():
    """Sample global configuration data."""
    return GlobalConfig(
        mcpServers={
            "test-server": MCPServerConfig(
                command=["python", "-m", "test_server"],
                args=["--port", "8080"],
                env={"DEBUG": "true"},
            )
        }
    )


@pytest.fixture
def sample_client_definitions():
    """Sample client definitions data."""
    return ClientDefinitions(
        clients={
            "test-client": MCPClientConfig(
                name="Test Client",
                description="A test client",
                config_type="file",
                paths={"linux": "~/.config/test/config.json"},
            )
        }
    )


@pytest.fixture
def builtin_client_definitions():
    """Built-in client definitions data."""
    return ClientDefinitions(
        clients={
            "claude-desktop": MCPClientConfig(
                name="Claude Desktop",
                description="Official Claude Desktop application",
                config_type="file",
                paths={
                    "darwin": "~/Library/Application Support/Claude/claude_desktop_config.json",
                    "linux": "~/.config/claude/claude_desktop_config.json",
                },
            ),
            "test-client": MCPClientConfig(
                name="Built-in Test Client",
                description="Built-in version",
                config_type="file",
            ),
        }
    )


class TestSettingsInitialization:
    """Tests for Settings initialization."""

    def test_default_initialization(self, temp_config_dir):
        """Test default initialization with platformdirs."""
        with patch("mcp_sync.config.settings.user_config_dir") as mock_user_config:
            mock_user_config.return_value = str(temp_config_dir)
            settings = Settings()

            assert settings.config_dir == temp_config_dir
            assert settings.locations_file == temp_config_dir / "locations.json"
            assert settings.global_config_file == temp_config_dir / "global.json"
            assert settings.user_client_definitions_file == (
                temp_config_dir / "client_definitions.json"
            )
            assert settings._client_definitions is None

    def test_config_directory_creation(self, mock_settings):
        """Test that config directory is created during initialization."""
        assert mock_settings.config_dir.exists()
        assert mock_settings.config_dir.is_dir()

    def test_default_file_creation(self, mock_settings):
        """Test that default config files are created."""
        # All default files should be created
        assert mock_settings.locations_file.exists()
        assert mock_settings.global_config_file.exists()
        assert mock_settings.user_client_definitions_file.exists()

        # Check content of default files
        with open(mock_settings.locations_file) as f:
            locations_data = json.load(f)
        assert "locations" in locations_data
        assert isinstance(locations_data["locations"], list)

        with open(mock_settings.global_config_file) as f:
            global_data = json.load(f)
        assert "mcpServers" in global_data
        assert isinstance(global_data["mcpServers"], dict)

        with open(mock_settings.user_client_definitions_file) as f:
            client_data = json.load(f)
        assert "clients" in client_data
        assert isinstance(client_data["clients"], dict)

    def test_dynaconf_initialization(self, mock_settings):
        """Test that dynaconf is properly initialized."""
        assert mock_settings.settings is not None
        # Dynaconf has different attributes, check for a common one
        assert hasattr(mock_settings.settings, "get")


class TestConfigurationLoading:
    """Tests for configuration loading methods."""

    def test_get_locations_config_success(self, mock_settings, sample_locations_config):
        """Test successful loading of locations config."""
        # Write sample config to file
        with open(mock_settings.locations_file, "w") as f:
            json.dump(sample_locations_config.model_dump(), f)

        config = mock_settings.get_locations_config()
        assert isinstance(config, LocationsConfig)
        assert len(config.locations) == 2
        assert config.locations[0].name == "Claude Desktop"
        assert config.locations[1].name == "Test Location"

    def test_get_locations_config_missing_file(self, mock_settings):
        """Test loading locations config when file doesn't exist."""
        # Remove the file that was created during initialization
        mock_settings.locations_file.unlink()

        config = mock_settings.get_locations_config()
        assert isinstance(config, LocationsConfig)
        assert config.locations == []

    def test_get_locations_config_corrupted_json(self, mock_settings, caplog):
        """Test loading locations config with corrupted JSON."""
        # Write invalid JSON
        with open(mock_settings.locations_file, "w") as f:
            f.write("invalid json content")

        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_locations_config()

        assert isinstance(config, LocationsConfig)
        assert config.locations == []
        assert "Error loading locations config" in caplog.text

    def test_get_locations_config_validation_error(self, mock_settings, caplog):
        """Test loading locations config with validation errors."""
        # Write JSON with invalid structure
        invalid_data = {"locations": [{"path": "/test"}]}  # Missing required 'name' field
        with open(mock_settings.locations_file, "w") as f:
            json.dump(invalid_data, f)

        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_locations_config()

        assert isinstance(config, LocationsConfig)
        assert config.locations == []
        assert "Error loading locations config" in caplog.text

    def test_get_global_config_success(self, mock_settings, sample_global_config):
        """Test successful loading of global config."""
        # Write sample config to file
        with open(mock_settings.global_config_file, "w") as f:
            json.dump(sample_global_config.model_dump(), f)

        config = mock_settings.get_global_config()
        assert isinstance(config, GlobalConfig)
        assert "test-server" in config.mcpServers
        assert config.mcpServers["test-server"].command == ["python", "-m", "test_server"]

    def test_get_global_config_missing_file(self, mock_settings):
        """Test loading global config when file doesn't exist."""
        # Remove the file that was created during initialization
        mock_settings.global_config_file.unlink()

        config = mock_settings.get_global_config()
        assert isinstance(config, GlobalConfig)
        assert config.mcpServers == {}

    def test_get_global_config_corrupted_json(self, mock_settings, caplog):
        """Test loading global config with corrupted JSON."""
        # Write invalid JSON
        with open(mock_settings.global_config_file, "w") as f:
            f.write("invalid json content")

        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_global_config()

        assert isinstance(config, GlobalConfig)
        assert config.mcpServers == {}
        assert "Error loading global config" in caplog.text

    def test_get_global_config_validation_error(self, mock_settings, caplog):
        """Test loading global config with validation errors."""
        # Write JSON with invalid structure
        invalid_data = {"mcpServers": {"invalid": {"command": []}}}  # Empty command
        with open(mock_settings.global_config_file, "w") as f:
            json.dump(invalid_data, f)

        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_global_config()

        assert isinstance(config, GlobalConfig)
        assert config.mcpServers == {}
        assert "Error loading global config" in caplog.text

    def test_get_client_definitions_builtin_only(self, mock_settings, builtin_client_definitions):
        """Test loading client definitions with only built-in definitions."""
        # Mock the built-in definitions file
        builtin_file = mock_settings.config_dir.parent / "client_definitions.json"
        builtin_file.parent.mkdir(exist_ok=True)
        with open(builtin_file, "w") as f:
            json.dump(builtin_client_definitions.model_dump(), f)

        # Mock the builtin definitions file path
        with patch.object(mock_settings, "get_client_definitions") as mock_get_defs:
            mock_get_defs.return_value = builtin_client_definitions
            definitions = mock_settings.get_client_definitions()

        assert isinstance(definitions, ClientDefinitions)
        assert "claude-desktop" in definitions.clients
        assert "test-client" in definitions.clients
        assert definitions.clients["test-client"].name == "Built-in Test Client"

    def test_get_client_definitions_user_override(
        self, mock_settings, builtin_client_definitions, sample_client_definitions
    ):
        """Test that user definitions override built-in definitions."""
        # Reset cache
        mock_settings._client_definitions = None

        # Setup user definitions (override test-client)
        with open(mock_settings.user_client_definitions_file, "w") as f:
            json.dump(sample_client_definitions.model_dump(), f)

        # Create a mock builtin definitions file path
        builtin_path = mock_settings.config_dir.parent / "mcp_sync" / "client_definitions.json"
        builtin_path.parent.mkdir(parents=True, exist_ok=True)
        with open(builtin_path, "w") as f:
            json.dump(builtin_client_definitions.model_dump(), f)

        # Patch the module's __file__ attribute to point to our mock location
        import mcp_sync.config.settings as settings_module

        original_file = settings_module.__file__
        try:
            settings_module.__file__ = str(builtin_path.parent / "settings.py")
            definitions = mock_settings.get_client_definitions()
        finally:
            settings_module.__file__ = original_file

        assert isinstance(definitions, ClientDefinitions)
        assert "claude-desktop" in definitions.clients  # From built-in
        assert "test-client" in definitions.clients  # Overridden by user
        assert definitions.clients["test-client"].name == "Test Client"  # User version

    def test_get_client_definitions_caching(self, mock_settings, builtin_client_definitions):
        """Test that client definitions are cached."""
        # Setup built-in definitions
        builtin_file = mock_settings.config_dir.parent / "client_definitions.json"
        builtin_file.parent.mkdir(exist_ok=True)
        with open(builtin_file, "w") as f:
            json.dump(builtin_client_definitions.model_dump(), f)

        # Mock the path resolution for built-in definitions
        original_method = mock_settings.get_client_definitions
        mock_settings._client_definitions = None  # Reset cache

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(builtin_client_definitions.model_dump())),
        ):
            with patch.object(Path, "exists", return_value=True):
                # First call
                definitions1 = original_method()
                # Second call should return cached version
                definitions2 = original_method()

        assert definitions1 is definitions2  # Same object reference

    def test_get_client_definitions_builtin_load_error(self, mock_settings, caplog):
        """Test handling of built-in definitions load error."""
        # Reset cache and mock file operations to simulate error
        mock_settings._client_definitions = None

        with patch("builtins.open", side_effect=OSError("File not found")):
            with caplog.at_level(logging.WARNING):
                definitions = mock_settings.get_client_definitions()

        assert isinstance(definitions, ClientDefinitions)
        assert definitions.clients == {}
        assert "Could not load built-in client definitions" in caplog.text

    def test_get_client_definitions_user_load_error(
        self, mock_settings, builtin_client_definitions, caplog
    ):
        """Test handling of user definitions load error."""
        # Reset cache
        mock_settings._client_definitions = None

        # Corrupt user definitions file
        with open(mock_settings.user_client_definitions_file, "w") as f:
            f.write("invalid json")

        # Create a mock builtin definitions file path
        builtin_path = mock_settings.config_dir.parent / "mcp_sync" / "client_definitions.json"
        builtin_path.parent.mkdir(parents=True, exist_ok=True)
        with open(builtin_path, "w") as f:
            json.dump(builtin_client_definitions.model_dump(), f)

        # Patch the module's __file__ attribute to point to our mock location
        import mcp_sync.config.settings as settings_module

        original_file = settings_module.__file__
        try:
            settings_module.__file__ = str(builtin_path.parent / "settings.py")
            with caplog.at_level(logging.WARNING):
                definitions = mock_settings.get_client_definitions()
        finally:
            settings_module.__file__ = original_file

        assert isinstance(definitions, ClientDefinitions)
        assert "claude-desktop" in definitions.clients  # Built-in still loaded
        assert "Could not load user client definitions" in caplog.text


class TestConfigurationSaving:
    """Tests for configuration saving methods."""

    def test_save_locations_config(self, mock_settings, sample_locations_config):
        """Test saving locations configuration."""
        mock_settings._save_locations_config(sample_locations_config)

        # Verify file was written correctly
        assert mock_settings.locations_file.exists()
        with open(mock_settings.locations_file) as f:
            data = json.load(f)

        assert "locations" in data
        assert len(data["locations"]) == 2
        assert data["locations"][0]["name"] == "Claude Desktop"

    def test_save_global_config(self, mock_settings, sample_global_config):
        """Test saving global configuration."""
        mock_settings._save_global_config(sample_global_config)

        # Verify file was written correctly
        assert mock_settings.global_config_file.exists()
        with open(mock_settings.global_config_file) as f:
            data = json.load(f)

        assert "mcpServers" in data
        assert "test-server" in data["mcpServers"]
        assert data["mcpServers"]["test-server"]["command"] == ["python", "-m", "test_server"]

    def test_save_user_client_definitions(self, mock_settings, sample_client_definitions):
        """Test saving user client definitions."""
        mock_settings._save_user_client_definitions(sample_client_definitions)

        # Verify file was written correctly
        assert mock_settings.user_client_definitions_file.exists()
        with open(mock_settings.user_client_definitions_file) as f:
            data = json.load(f)

        assert "clients" in data
        assert "test-client" in data["clients"]
        assert data["clients"]["test-client"]["name"] == "Test Client"

    def test_save_with_proper_json_formatting(self, mock_settings, sample_global_config):
        """Test that saved JSON is properly formatted with indentation."""
        mock_settings._save_global_config(sample_global_config)

        # Read raw file content to check formatting
        with open(mock_settings.global_config_file) as f:
            content = f.read()

        # Should have proper indentation (2 spaces)
        assert "  " in content  # Indented content
        assert content.count("\n") > 1  # Multiple lines

    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    def test_save_permission_error(self, mock_open_func, mock_settings, sample_global_config):
        """Test handling of permission errors during save."""
        with pytest.raises(PermissionError):
            mock_settings._save_global_config(sample_global_config)


class TestLocationManagement:
    """Tests for location management methods."""

    def test_add_location_success(self, mock_settings):
        """Test successfully adding a new location."""
        result = mock_settings.add_location("/new/path", "New Location")

        assert result is True

        # Verify location was added
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 1
        assert config.locations[0].path == "/new/path"
        assert config.locations[0].name == "New Location"
        assert config.locations[0].type == "manual"

    def test_add_location_without_name(self, mock_settings):
        """Test adding location without explicit name (uses path stem)."""
        result = mock_settings.add_location("/path/to/config.json")

        assert result is True

        # Verify location was added with path stem as name
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 1
        assert config.locations[0].path == "/path/to/config.json"
        assert config.locations[0].name == "config"

    def test_add_location_duplicate_path(self, mock_settings):
        """Test adding location with duplicate path."""
        # Add first location
        mock_settings.add_location("/test/path", "First")

        # Try to add duplicate
        result = mock_settings.add_location("/test/path", "Second")

        assert result is False

        # Verify only one location exists
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 1
        assert config.locations[0].name == "First"

    def test_add_location_to_existing_config(self, mock_settings, sample_locations_config):
        """Test adding location to existing configuration."""
        # Setup existing config
        mock_settings._save_locations_config(sample_locations_config)

        # Add new location
        result = mock_settings.add_location("/new/path", "New Location")

        assert result is True

        # Verify new location was added to existing ones
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 3  # 2 existing + 1 new
        assert config.locations[2].path == "/new/path"

    def test_remove_location_success(self, mock_settings, sample_locations_config):
        """Test successfully removing an existing location."""
        # Setup existing config
        mock_settings._save_locations_config(sample_locations_config)

        # Remove location
        result = mock_settings.remove_location(
            "/home/user/.config/claude/claude_desktop_config.json"
        )

        assert result is True

        # Verify location was removed
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 1
        assert config.locations[0].name == "Test Location"

    def test_remove_location_not_found(self, mock_settings, sample_locations_config):
        """Test removing location that doesn't exist."""
        # Setup existing config
        mock_settings._save_locations_config(sample_locations_config)

        # Try to remove non-existent location
        result = mock_settings.remove_location("/non/existent/path")

        assert result is False

        # Verify no locations were removed
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 2

    def test_remove_location_empty_config(self, mock_settings):
        """Test removing location from empty configuration."""
        result = mock_settings.remove_location("/any/path")

        assert result is False

        # Verify config is still empty
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 0


class TestClientDefinitionsCaching:
    """Tests for client definitions caching mechanism."""

    def test_cache_invalidation_on_new_instance(self, temp_config_dir, builtin_client_definitions):
        """Test that cache is not shared between instances."""
        # Setup built-in definitions
        builtin_file = temp_config_dir / "client_definitions.json"
        with open(builtin_file, "w") as f:
            json.dump(builtin_client_definitions.model_dump(), f)

        with patch("mcp_sync.config.settings.user_config_dir") as mock_user_config:
            mock_user_config.return_value = str(temp_config_dir)

            # Mock built-in definitions loading for both instances
            with patch(
                "builtins.open",
                mock_open(read_data=json.dumps(builtin_client_definitions.model_dump())),
            ):
                with patch.object(Path, "exists", return_value=True):
                    settings1 = Settings()
                    settings2 = Settings()

                    definitions1 = settings1.get_client_definitions()
                    definitions2 = settings2.get_client_definitions()

                # Should be different instances
                assert definitions1 is not definitions2
                # But should have same content
                assert definitions1.clients == definitions2.clients

    def test_cache_persistence_within_instance(self, mock_settings, builtin_client_definitions):
        """Test that cache persists within the same instance."""
        # Setup built-in definitions
        builtin_file = mock_settings.config_dir.parent / "client_definitions.json"
        builtin_file.parent.mkdir(exist_ok=True)
        with open(builtin_file, "w") as f:
            json.dump(builtin_client_definitions.model_dump(), f)

        # Reset cache and mock built-in file loading
        mock_settings._client_definitions = None

        with patch(
            "builtins.open",
            mock_open(read_data=json.dumps(builtin_client_definitions.model_dump())),
        ):
            with patch.object(Path, "exists", return_value=True):
                # Multiple calls should return same cached object
                definitions1 = mock_settings.get_client_definitions()
                definitions2 = mock_settings.get_client_definitions()
                definitions3 = mock_settings.get_client_definitions()

            assert definitions1 is definitions2 is definitions3


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @patch("builtins.open", side_effect=OSError("File system error"))
    def test_file_system_error_handling(self, mock_open_func, mock_settings, caplog):
        """Test handling of file system errors."""
        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_locations_config()

        assert isinstance(config, LocationsConfig)
        assert config.locations == []
        assert "Error loading locations config" in caplog.text

    def test_json_decode_error_handling(self, mock_settings, caplog):
        """Test handling of JSON decode errors."""
        # Write malformed JSON
        with open(mock_settings.locations_file, "w") as f:
            f.write('{"locations": [invalid json}')

        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_locations_config()

        assert isinstance(config, LocationsConfig)
        assert config.locations == []
        assert "Error loading locations config" in caplog.text

    def test_pydantic_validation_error_handling(self, mock_settings, caplog):
        """Test handling of Pydantic validation errors."""
        # Write JSON with invalid data structure that will actually cause validation error
        invalid_data = {
            "locations": [
                {"path": "/test"}  # Missing required 'name' field
            ]
        }
        with open(mock_settings.locations_file, "w") as f:
            json.dump(invalid_data, f)

        with caplog.at_level(logging.WARNING):
            config = mock_settings.get_locations_config()

        assert isinstance(config, LocationsConfig)
        assert config.locations == []
        assert "Error loading locations config" in caplog.text

    @patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied"))
    def test_directory_creation_failure(self, mock_mkdir, temp_config_dir):
        """Test handling of directory creation failures."""
        with patch("mcp_sync.config.settings.user_config_dir") as mock_user_config:
            mock_user_config.return_value = str(temp_config_dir)

            with pytest.raises(PermissionError):
                Settings()

    def test_graceful_fallback_to_defaults(self, mock_settings):
        """Test graceful fallback to default configurations."""
        # Remove all config files
        mock_settings.locations_file.unlink()
        mock_settings.global_config_file.unlink()
        mock_settings.user_client_definitions_file.unlink()

        # Should return default configurations
        locations_config = mock_settings.get_locations_config()
        global_config = mock_settings.get_global_config()

        assert isinstance(locations_config, LocationsConfig)
        assert locations_config.locations == []
        assert isinstance(global_config, GlobalConfig)
        assert global_config.mcpServers == {}


class TestIntegrationScenarios:
    """Integration tests for full workflows."""

    def test_full_workflow_load_modify_save_reload(self, mock_settings):
        """Test complete workflow: load -> modify -> save -> reload."""
        # Initial load (should be empty)
        config = mock_settings.get_locations_config()
        assert len(config.locations) == 0

        # Add location
        success = mock_settings.add_location("/test/path", "Test Location")
        assert success is True

        # Reload and verify
        reloaded_config = mock_settings.get_locations_config()
        assert len(reloaded_config.locations) == 1
        assert reloaded_config.locations[0].path == "/test/path"

        # Remove location
        success = mock_settings.remove_location("/test/path")
        assert success is True

        # Reload and verify removal
        final_config = mock_settings.get_locations_config()
        assert len(final_config.locations) == 0

    def test_multiple_settings_instances_independence(self, temp_config_dir):
        """Test that multiple Settings instances work independently."""
        with patch("mcp_sync.config.settings.user_config_dir") as mock_user_config:
            mock_user_config.return_value = str(temp_config_dir)

            settings1 = Settings()
            settings2 = Settings()

            # Add location in first instance
            settings1.add_location("/path1", "Location 1")

            # Second instance should see the change (same config dir)
            config2 = settings2.get_locations_config()
            assert len(config2.locations) == 1
            assert config2.locations[0].path == "/path1"

            # Add location in second instance
            settings2.add_location("/path2", "Location 2")

            # First instance should see both changes
            config1 = settings1.get_locations_config()
            assert len(config1.locations) == 2

    def test_platform_specific_path_handling(self, temp_config_dir):
        """Test platform-specific path handling."""
        with patch("mcp_sync.config.settings.user_config_dir") as mock_user_config:
            mock_user_config.return_value = str(temp_config_dir)

            settings = Settings()

            # Verify paths are constructed correctly
            assert settings.config_dir == temp_config_dir
            assert settings.locations_file.name == "locations.json"
            assert settings.global_config_file.name == "global.json"
            assert settings.user_client_definitions_file.name == "client_definitions.json"


class TestGlobalSettingsFunction:
    """Tests for the global get_settings() function."""

    def test_get_settings_singleton_behavior(self):
        """Test that get_settings() returns the same instance."""
        # Clear any existing global instance
        import mcp_sync.config.settings

        mcp_sync.config.settings._settings = None

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_get_settings_creates_instance_on_first_call(self):
        """Test that get_settings() creates instance on first call."""
        # Clear any existing global instance
        import mcp_sync.config.settings

        mcp_sync.config.settings._settings = None

        assert mcp_sync.config.settings._settings is None

        settings = get_settings()

        assert settings is not None
        assert isinstance(settings, Settings)
        assert mcp_sync.config.settings._settings is settings

    def test_get_settings_returns_existing_instance(self):
        """Test that get_settings() returns existing instance if available."""
        # Clear and set a mock instance
        import mcp_sync.config.settings

        mock_settings = Mock(spec=Settings)
        mcp_sync.config.settings._settings = mock_settings

        settings = get_settings()

        assert settings is mock_settings


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_config_files(self, mock_settings):
        """Test handling of empty config files."""
        # Create empty files
        mock_settings.locations_file.write_text("")
        mock_settings.global_config_file.write_text("")

        # Should handle gracefully
        locations_config = mock_settings.get_locations_config()
        global_config = mock_settings.get_global_config()

        assert isinstance(locations_config, LocationsConfig)
        assert isinstance(global_config, GlobalConfig)

    def test_very_large_config_files(self, mock_settings):
        """Test handling of large configuration files."""
        # Create a large locations config
        large_locations = LocationsConfig(
            locations=[LocationConfig(path=f"/path/{i}", name=f"Location {i}") for i in range(1000)]
        )

        # Should handle large configs without issues
        mock_settings._save_locations_config(large_locations)
        loaded_config = mock_settings.get_locations_config()

        assert len(loaded_config.locations) == 1000
        assert loaded_config.locations[999].name == "Location 999"

    def test_unicode_content_handling(self, mock_settings):
        """Test handling of Unicode content in configurations."""
        # Add location with Unicode characters
        unicode_path = "/测试/路径/配置.json"
        unicode_name = "测试位置"

        success = mock_settings.add_location(unicode_path, unicode_name)
        assert success is True

        # Verify Unicode content is preserved
        config = mock_settings.get_locations_config()
        assert config.locations[0].path == unicode_path
        assert config.locations[0].name == unicode_name

    def test_concurrent_access_simulation(self, mock_settings):
        """Test simulation of concurrent access to config files."""
        # This is a basic test since we can't easily test true concurrency
        # in unit tests, but we can test rapid successive operations

        for i in range(10):
            mock_settings.add_location(f"/path/{i}", f"Location {i}")

        config = mock_settings.get_locations_config()
        assert len(config.locations) == 10

        for i in range(5):
            mock_settings.remove_location(f"/path/{i}")

        final_config = mock_settings.get_locations_config()
        assert len(final_config.locations) == 5
