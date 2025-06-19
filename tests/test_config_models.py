"""Unit tests for Pydantic config models."""

import pytest
from pydantic import ValidationError

from mcp_sync.config.models import (
    ClientDefinitions,
    GlobalConfig,
    LocationConfig,
    LocationsConfig,
    MCPClientConfig,
    MCPServerConfig,
)


# Test fixtures for common test data
@pytest.fixture
def valid_server_config():
    """Valid MCPServerConfig data."""
    return {
        "command": ["python", "-m", "server"],
        "args": ["--port", "8080"],
        "env": {"DEBUG": "true", "PORT": "8080"},
    }


@pytest.fixture
def valid_client_config():
    """Valid MCPClientConfig data."""
    return {
        "name": "Test Client",
        "description": "A test client",
        "config_type": "file",
        "paths": {"linux": "~/.config/test/config.json", "darwin": "~/Library/test/config.json"},
        "fallback_paths": {"linux": "~/.test/config.json"},
        "cli_commands": {"list_mcp": "test mcp list"},
    }


@pytest.fixture
def valid_location_config():
    """Valid LocationConfig data."""
    return {
        "path": "/home/user/.config/test/config.json",
        "name": "Test Location",
        "type": "manual",
        "config_type": "file",
        "client_name": "test-client",
        "description": "A test location",
    }


class TestMCPServerConfig:
    """Tests for MCPServerConfig model."""

    def test_valid_configuration_creation(self, valid_server_config):
        """Test creating valid MCPServerConfig."""
        config = MCPServerConfig(**valid_server_config)
        assert config.command == ["python", "-m", "server"]
        assert config.args == ["--port", "8080"]
        assert config.env == {"DEBUG": "true", "PORT": "8080"}

    def test_minimal_valid_configuration(self):
        """Test creating MCPServerConfig with minimal required fields."""
        config = MCPServerConfig(command=["echo", "test"])
        assert config.command == ["echo", "test"]
        assert config.args is None
        assert config.env is None

    def test_command_field_validation_non_empty(self):
        """Test that command field cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(command=[])

        error = exc_info.value.errors()[0]
        assert error["type"] == "value_error"
        assert "Command cannot be empty" in str(exc_info.value)

    def test_command_field_validation_empty_first_element(self):
        """Test that first command element cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(command=["", "arg"])

        error = exc_info.value.errors()[0]
        assert error["type"] == "value_error"
        assert "Command cannot be empty" in str(exc_info.value)

    def test_optional_args_field(self):
        """Test optional args field handling."""
        config = MCPServerConfig(command=["test"])
        assert config.args is None

        config_with_args = MCPServerConfig(command=["test"], args=["--verbose"])
        assert config_with_args.args == ["--verbose"]

    def test_optional_env_field(self):
        """Test optional env field handling."""
        config = MCPServerConfig(command=["test"])
        assert config.env is None

        config_with_env = MCPServerConfig(command=["test"], env={"KEY": "value"})
        assert config_with_env.env == {"KEY": "value"}

    def test_invalid_command_type(self):
        """Test validation error for wrong command type."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(command="not a list")  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "list_type"

    def test_invalid_args_type(self):
        """Test validation error for wrong args type."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(command=["test"], args="not a list")  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "list_type"

    def test_invalid_env_type(self):
        """Test validation error for wrong env type."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(command=["test"], env=["not", "a", "dict"])  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "dict_type"


class TestMCPClientConfig:
    """Tests for MCPClientConfig model."""

    def test_valid_configuration_creation(self, valid_client_config):
        """Test creating valid MCPClientConfig."""
        config = MCPClientConfig(**valid_client_config)
        assert config.name == "Test Client"
        assert config.description == "A test client"
        assert config.config_type == "file"
        assert config.paths == {
            "linux": "~/.config/test/config.json",
            "darwin": "~/Library/test/config.json",
        }
        assert config.fallback_paths == {"linux": "~/.test/config.json"}
        assert config.cli_commands == {"list_mcp": "test mcp list"}

    def test_minimal_valid_configuration(self):
        """Test creating MCPClientConfig with minimal required fields."""
        config = MCPClientConfig(name="Minimal Client")
        assert config.name == "Minimal Client"
        assert config.description == ""
        assert config.config_type == "file"
        assert config.paths is None
        assert config.fallback_paths is None
        assert config.cli_commands is None

    def test_config_type_validation_file(self):
        """Test config_type validation with 'file' value."""
        config = MCPClientConfig(name="Test", config_type="file")
        assert config.config_type == "file"

    def test_config_type_validation_cli(self):
        """Test config_type validation with 'cli' value."""
        config = MCPClientConfig(name="Test", config_type="cli")
        assert config.config_type == "cli"

    def test_config_type_validation_invalid(self):
        """Test config_type validation with invalid value."""
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig(name="Test", config_type="invalid")

        error = exc_info.value.errors()[0]
        assert error["type"] == "value_error"
        assert "config_type must be 'file' or 'cli'" in str(exc_info.value)

    def test_optional_fields_handling(self):
        """Test handling of optional fields."""
        config = MCPClientConfig(name="Test")
        assert config.paths is None
        assert config.fallback_paths is None
        assert config.cli_commands is None

    def test_cli_client_configuration(self):
        """Test configuration for CLI client."""
        config = MCPClientConfig(
            name="CLI Client",
            config_type="cli",
            cli_commands={"list_mcp": "cli mcp list", "add_mcp": "cli mcp add {name}"},
        )
        assert config.config_type == "cli"
        assert config.cli_commands == {"list_mcp": "cli mcp list", "add_mcp": "cli mcp add {name}"}

    def test_file_client_configuration(self):
        """Test configuration for file-based client."""
        config = MCPClientConfig(
            name="File Client",
            config_type="file",
            paths={"linux": "~/.config/client/config.json"},
            fallback_paths={"linux": "~/.client/config.json"},
        )
        assert config.config_type == "file"
        assert config.paths == {"linux": "~/.config/client/config.json"}
        assert config.fallback_paths == {"linux": "~/.client/config.json"}

    def test_missing_required_name(self):
        """Test validation error for missing required name field."""
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig()  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "missing"
        assert error["loc"] == ("name",)

    def test_invalid_paths_type(self):
        """Test validation error for wrong paths type."""
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig(name="Test", paths=["not", "a", "dict"])  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "dict_type"

    def test_invalid_cli_commands_type(self):
        """Test validation error for wrong cli_commands type."""
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig(name="Test", cli_commands=["not", "a", "dict"])  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "dict_type"


class TestLocationConfig:
    """Tests for LocationConfig model."""

    def test_valid_configuration_creation(self, valid_location_config):
        """Test creating valid LocationConfig."""
        config = LocationConfig(**valid_location_config)
        assert config.path == "/home/user/.config/test/config.json"
        assert config.name == "Test Location"
        assert config.type == "manual"
        assert config.config_type == "file"
        assert config.client_name == "test-client"
        assert config.description == "A test location"

    def test_minimal_valid_configuration(self):
        """Test creating LocationConfig with minimal required fields."""
        config = LocationConfig(path="/test/path", name="Test")
        assert config.path == "/test/path"
        assert config.name == "Test"
        assert config.type == "manual"  # default value
        assert config.config_type == "file"  # default value
        assert config.client_name is None
        assert config.description is None

    def test_default_values(self):
        """Test default values for type and config_type fields."""
        config = LocationConfig(path="/test", name="Test")
        assert config.type == "manual"
        assert config.config_type == "file"

    def test_optional_fields(self):
        """Test optional fields handling."""
        config = LocationConfig(path="/test", name="Test")
        assert config.client_name is None
        assert config.description is None

        config_with_optional = LocationConfig(
            path="/test", name="Test", client_name="client", description="desc"
        )
        assert config_with_optional.client_name == "client"
        assert config_with_optional.description == "desc"

    def test_cli_location_configuration(self):
        """Test configuration for CLI location."""
        config = LocationConfig(
            path="cli:claude-code",
            name="Claude Code",
            type="auto",
            config_type="cli",
            client_name="claude-code",
        )
        assert config.path == "cli:claude-code"
        assert config.config_type == "cli"
        assert config.type == "auto"

    def test_missing_required_path(self):
        """Test validation error for missing required path field."""
        with pytest.raises(ValidationError) as exc_info:
            LocationConfig(name="Test")  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "missing"
        assert error["loc"] == ("path",)

    def test_missing_required_name(self):
        """Test validation error for missing required name field."""
        with pytest.raises(ValidationError) as exc_info:
            LocationConfig(path="/test")  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "missing"
        assert error["loc"] == ("name",)

    def test_field_type_validation(self):
        """Test field type validation."""
        with pytest.raises(ValidationError) as exc_info:
            LocationConfig(path=123, name="Test")  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "string_type"

    def test_none_values_for_optional_fields(self):
        """Test explicit None values for optional fields."""
        config = LocationConfig(path="/test", name="Test", client_name=None, description=None)
        assert config.client_name is None
        assert config.description is None


class TestGlobalConfig:
    """Tests for GlobalConfig model."""

    def test_valid_configuration_with_servers(self, valid_server_config):
        """Test creating GlobalConfig with mcpServers."""
        config = GlobalConfig(mcpServers={"test-server": MCPServerConfig(**valid_server_config)})
        assert "test-server" in config.mcpServers
        assert isinstance(config.mcpServers["test-server"], MCPServerConfig)
        assert config.mcpServers["test-server"].command == ["python", "-m", "server"]

    def test_empty_configuration(self):
        """Test creating empty GlobalConfig with default factory."""
        config = GlobalConfig()
        assert config.mcpServers == {}
        assert isinstance(config.mcpServers, dict)

    def test_default_factory(self):
        """Test that default factory creates empty dict."""
        config1 = GlobalConfig()
        config2 = GlobalConfig()

        # Should be separate instances
        assert config1.mcpServers is not config2.mcpServers

        # Both should be empty dicts
        assert config1.mcpServers == {}
        assert config2.mcpServers == {}

    def test_nested_server_config_validation(self):
        """Test nested MCPServerConfig validation."""
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig(mcpServers={"invalid": {"command": []}})  # type: ignore

        # Should have validation error for nested MCPServerConfig
        assert "Command cannot be empty" in str(exc_info.value)

    def test_multiple_servers(self):
        """Test configuration with multiple servers."""
        config = GlobalConfig(
            mcpServers={
                "server1": MCPServerConfig(command=["echo", "test1"]),
                "server2": MCPServerConfig(command=["echo", "test2"], args=["--verbose"]),
            }
        )
        assert len(config.mcpServers) == 2
        assert "server1" in config.mcpServers
        assert "server2" in config.mcpServers
        assert config.mcpServers["server2"].args == ["--verbose"]

    def test_invalid_servers_type(self):
        """Test validation error for wrong mcpServers type."""
        with pytest.raises(ValidationError) as exc_info:
            GlobalConfig(mcpServers=["not", "a", "dict"])  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "dict_type"


class TestClientDefinitions:
    """Tests for ClientDefinitions model."""

    def test_valid_configuration_with_clients(self, valid_client_config):
        """Test creating ClientDefinitions with clients."""
        config = ClientDefinitions(clients={"test-client": MCPClientConfig(**valid_client_config)})
        assert "test-client" in config.clients
        assert isinstance(config.clients["test-client"], MCPClientConfig)
        assert config.clients["test-client"].name == "Test Client"

    def test_empty_configuration(self):
        """Test creating empty ClientDefinitions with default factory."""
        config = ClientDefinitions()
        assert config.clients == {}
        assert isinstance(config.clients, dict)

    def test_default_factory(self):
        """Test that default factory creates empty dict."""
        config1 = ClientDefinitions()
        config2 = ClientDefinitions()

        # Should be separate instances
        assert config1.clients is not config2.clients

        # Both should be empty dicts
        assert config1.clients == {}
        assert config2.clients == {}

    def test_nested_client_config_validation(self):
        """Test nested MCPClientConfig validation."""
        with pytest.raises(ValidationError) as exc_info:
            ClientDefinitions(clients={"invalid": {"config_type": "invalid"}})  # type: ignore

        # Should have validation errors for nested MCPClientConfig
        errors = exc_info.value.errors()
        assert len(errors) >= 1  # At least one validation error

    def test_multiple_clients(self):
        """Test configuration with multiple clients."""
        config = ClientDefinitions(
            clients={
                "client1": MCPClientConfig(name="Client 1", config_type="file"),
                "client2": MCPClientConfig(name="Client 2", config_type="cli"),
            }
        )
        assert len(config.clients) == 2
        assert "client1" in config.clients
        assert "client2" in config.clients
        assert config.clients["client1"].config_type == "file"
        assert config.clients["client2"].config_type == "cli"

    def test_invalid_clients_type(self):
        """Test validation error for wrong clients type."""
        with pytest.raises(ValidationError) as exc_info:
            ClientDefinitions(clients=["not", "a", "dict"])  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "dict_type"


class TestLocationsConfig:
    """Tests for LocationsConfig model."""

    def test_valid_configuration_with_locations(self, valid_location_config):
        """Test creating LocationsConfig with locations."""
        config = LocationsConfig(locations=[LocationConfig(**valid_location_config)])
        assert len(config.locations) == 1
        assert isinstance(config.locations[0], LocationConfig)
        assert config.locations[0].name == "Test Location"

    def test_empty_configuration(self):
        """Test creating empty LocationsConfig with default factory."""
        config = LocationsConfig()
        assert config.locations == []
        assert isinstance(config.locations, list)

    def test_default_factory(self):
        """Test that default factory creates empty list."""
        config1 = LocationsConfig()
        config2 = LocationsConfig()

        # Should be separate instances
        assert config1.locations is not config2.locations

        # Both should be empty lists
        assert config1.locations == []
        assert config2.locations == []

    def test_nested_location_config_validation(self):
        """Test nested LocationConfig validation."""
        with pytest.raises(ValidationError) as exc_info:
            LocationsConfig(locations=[{"path": "/test"}])  # type: ignore

        # Should have validation error for nested LocationConfig
        errors = exc_info.value.errors()
        # Check that there's a missing field error for the name field in the first location
        assert any(error["type"] == "missing" and "name" in str(error["loc"]) for error in errors)

    def test_multiple_locations(self):
        """Test configuration with multiple locations."""
        config = LocationsConfig(
            locations=[
                LocationConfig(path="/path1", name="Location 1"),
                LocationConfig(path="/path2", name="Location 2", type="auto"),
            ]
        )
        assert len(config.locations) == 2
        assert config.locations[0].name == "Location 1"
        assert config.locations[1].name == "Location 2"
        assert config.locations[1].type == "auto"

    def test_invalid_locations_type(self):
        """Test validation error for wrong locations type."""
        with pytest.raises(ValidationError) as exc_info:
            LocationsConfig(locations={"not": "a list"})  # type: ignore

        error = exc_info.value.errors()[0]
        assert error["type"] == "list_type"

    def test_mixed_location_types(self):
        """Test configuration with mixed file and CLI locations."""
        config = LocationsConfig(
            locations=[
                LocationConfig(path="/file/path", name="File Location", config_type="file"),
                LocationConfig(path="cli:client", name="CLI Location", config_type="cli"),
            ]
        )
        assert len(config.locations) == 2
        assert config.locations[0].config_type == "file"
        assert config.locations[1].config_type == "cli"


# Edge case and integration tests
class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_empty_string_values(self):
        """Test handling of empty string values."""
        # MCPClientConfig allows empty description
        config = MCPClientConfig(name="Test", description="")
        assert config.description == ""

        # LocationConfig allows empty optional strings
        location = LocationConfig(path="/test", name="Test", description="")
        assert location.description == ""

    def test_none_vs_missing_optional_fields(self):
        """Test difference between None and missing optional fields."""
        # Explicit None
        config1 = MCPClientConfig(name="Test", paths=None)
        assert config1.paths is None

        # Missing field (should also be None)
        config2 = MCPClientConfig(name="Test")
        assert config2.paths is None

    def test_complex_nested_structure(self):
        """Test complex nested configuration structure."""
        global_config = GlobalConfig(
            mcpServers={
                "server1": MCPServerConfig(
                    command=["python", "-m", "server1"],
                    args=["--port", "8080"],
                    env={"DEBUG": "true"},
                ),
                "server2": MCPServerConfig(command=["echo", "server2"]),
            }
        )

        assert len(global_config.mcpServers) == 2
        assert global_config.mcpServers["server1"].env == {"DEBUG": "true"}
        assert global_config.mcpServers["server2"].args is None

    def test_model_serialization_roundtrip(self, valid_server_config):
        """Test that models can be serialized and deserialized."""
        original = MCPServerConfig(**valid_server_config)

        # Convert to dict and back
        data = original.model_dump()
        reconstructed = MCPServerConfig(**data)

        assert original.command == reconstructed.command
        assert original.args == reconstructed.args
        assert original.env == reconstructed.env
