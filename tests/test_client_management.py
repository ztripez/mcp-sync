import json
import tempfile
from pathlib import Path

from mcp_sync.config import ConfigManager
from mcp_sync.main import handle_client_info, handle_list_clients


def test_config_manager_loads_client_definitions():
    """Test that ConfigManager loads built-in client definitions"""
    cm = ConfigManager()
    clients = cm.client_definitions.get("clients", {})

    # Should have at least the built-in clients
    expected_clients = ["claude-desktop", "claude-code", "cline", "roo", "vscode-user"]
    for client in expected_clients:
        assert client in clients
        assert "name" in clients[client]
        assert "paths" in clients[client]


def test_config_manager_merges_user_definitions():
    """Test that user client definitions override built-in ones"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary config manager with custom config dir
        cm = ConfigManager()
        cm.config_dir = Path(temp_dir)
        cm.user_client_definitions_file = cm.config_dir / "client_definitions.json"

        # Create user definitions that override a built-in client
        user_definitions = {
            "clients": {
                "roo": {
                    "name": "Custom Roo",
                    "description": "Custom Roo client",
                    "paths": {"linux": "~/custom/roo/path.json"},
                },
                "custom-client": {
                    "name": "My Custom Client",
                    "description": "A custom client",
                    "paths": {"linux": "~/.config/custom/config.json"},
                },
            }
        }

        cm.config_dir.mkdir(exist_ok=True)
        with open(cm.user_client_definitions_file, "w") as f:
            json.dump(user_definitions, f)

        # Reload definitions
        cm.client_definitions = cm._load_client_definitions()
        clients = cm.client_definitions.get("clients", {})

        # Should have custom client
        assert "custom-client" in clients
        assert clients["custom-client"]["name"] == "My Custom Client"

        # Should have overridden built-in roo client
        assert "roo" in clients
        assert clients["roo"]["name"] == "Custom Roo"


def test_get_client_location_existing_path(tmp_path):
    """Test client location detection when path exists"""
    cm = ConfigManager()

    # Create a test file
    test_file = tmp_path / "test_config.json"
    test_file.write_text("{}")

    # Use the current platform for the test
    current_platform = cm._get_platform_name()
    client_config = {"name": "Test Client", "paths": {current_platform: str(test_file)}}

    location = cm._get_client_location("test-client", client_config)

    assert location is not None
    assert location["path"] == str(test_file)
    assert location["name"] == "test-client"
    assert location["type"] == "auto"
    assert location["client_name"] == "Test Client"


def test_get_client_location_missing_path():
    """Test client location detection when path doesn't exist"""
    cm = ConfigManager()

    current_platform = cm._get_platform_name()
    client_config = {"name": "Test Client", "paths": {current_platform: "/nonexistent/path.json"}}

    location = cm._get_client_location("test-client", client_config)
    assert location is None


def test_expand_path_template():
    """Test path template expansion"""
    cm = ConfigManager()

    # Test home directory expansion
    expanded = cm._expand_path_template("~/.test/config.json")
    assert str(expanded).startswith(str(Path.home()))
    # Use Path for cross-platform comparison
    expected_suffix = Path(".test/config.json")
    assert Path(expanded).name == expected_suffix.name
    assert Path(expanded).parts[-2:] == expected_suffix.parts


def test_handle_list_clients(capsys):
    """Test the list-clients command output"""
    cm = ConfigManager()
    handle_list_clients(cm)

    captured = capsys.readouterr()
    output = captured.out

    assert "Supported Clients:" in output
    assert "claude-desktop" in output
    assert "roo" in output
    assert "✅ Found" in output or "❌ Not found" in output


def test_handle_client_info_existing_client(capsys):
    """Test client-info command for existing client"""
    cm = ConfigManager()
    handle_client_info(cm, "roo")

    captured = capsys.readouterr()
    output = captured.out

    assert "Client: Roo" in output
    assert "Paths:" in output
    assert "linux:" in output
    assert "Config format:" in output


def test_handle_client_info_missing_client(capsys):
    """Test client-info command for non-existent client"""
    cm = ConfigManager()
    handle_client_info(cm, "nonexistent")

    captured = capsys.readouterr()
    output = captured.out

    assert "Client 'nonexistent' not found" in output


def test_handle_client_info_no_client_specified(capsys):
    """Test client-info command without specifying a client"""
    cm = ConfigManager()
    handle_client_info(cm, None)

    captured = capsys.readouterr()
    output = captured.out

    assert "Available clients:" in output
    assert "claude-desktop" in output
