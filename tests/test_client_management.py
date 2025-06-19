import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

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
        # CLI clients have cli_commands instead of paths
        if clients[client].get("config_type") == "cli":
            assert "cli_commands" in clients[client]
        else:
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


# CLI Client Tests
def test_cli_client_detection():
    """Test CLI client detection and configuration"""
    cm = ConfigManager()
    clients = cm.client_definitions.get("clients", {})

    # Should have claude-code as CLI client
    assert "claude-code" in clients
    claude_code = clients["claude-code"]
    assert claude_code.get("config_type") == "cli"
    assert "cli_commands" in claude_code
    assert "list_mcp" in claude_code["cli_commands"]


@patch("mcp_sync.config.subprocess.run")
def test_is_cli_available_success(mock_run):
    """Test CLI availability check when command succeeds"""
    cm = ConfigManager()

    # Mock successful version check
    mock_run.return_value = Mock(returncode=0)

    client_config = {"config_type": "cli", "cli_commands": {"list_mcp": "claude mcp list"}}

    assert cm._is_cli_available(client_config)
    mock_run.assert_called_once_with(
        ["claude", "--version"], capture_output=True, text=True, timeout=5, check=False
    )


@patch("mcp_sync.config.subprocess.run")
def test_is_cli_available_failure(mock_run):
    """Test CLI availability check when command fails"""
    cm = ConfigManager()

    # Mock failed version check
    mock_run.return_value = Mock(returncode=1)

    client_config = {"config_type": "cli", "cli_commands": {"list_mcp": "nonexistent mcp list"}}

    assert not cm._is_cli_available(client_config)


def test_get_client_location_cli():
    """Test client location detection for CLI clients"""
    cm = ConfigManager()

    with patch.object(cm, "_is_cli_available", return_value=True):
        client_config = {
            "name": "Test CLI Client",
            "config_type": "cli",
            "cli_commands": {"list_mcp": "test mcp list"},
        }

        location = cm._get_client_location("test-cli", client_config)

        assert location is not None
        assert location["path"] == "cli:test-cli"
        assert location["name"] == "test-cli"
        assert location["type"] == "auto"
        assert location["config_type"] == "cli"
        assert location["client_name"] == "Test CLI Client"


def test_get_client_location_cli_unavailable():
    """Test client location detection when CLI is unavailable"""
    cm = ConfigManager()

    with patch.object(cm, "_is_cli_available", return_value=False):
        client_config = {
            "name": "Test CLI Client",
            "config_type": "cli",
            "cli_commands": {"list_mcp": "test mcp list"},
        }

        location = cm._get_client_location("test-cli", client_config)
        assert location is None


@patch("mcp_sync.config.subprocess.run")
def test_get_cli_mcp_servers(mock_run):
    """Test reading MCP servers from CLI"""
    cm = ConfigManager()

    # Mock CLI output
    mock_run.return_value = Mock(
        returncode=0, stdout="server1: echo test1\nserver2: uvx --from git+example.com tool\n"
    )

    servers = cm.get_cli_mcp_servers("claude-code")

    assert servers == {
        "server1": {"command": ["echo", "test1"]},
        "server2": {"command": ["uvx", "--from", "git+example.com", "tool"]},
    }

    # Verify the subprocess call was made with proper arguments
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][0] == ["claude", "mcp", "list"]
    assert not call_args[1]["check"]


@patch("mcp_sync.config.subprocess.run")
def test_add_cli_mcp_server(mock_run):
    """Test adding MCP server via CLI"""
    cm = ConfigManager()

    # Mock successful add
    mock_run.return_value = Mock(returncode=0)

    success = cm.add_cli_mcp_server(
        "claude-code", "test-server", ["echo", "test"], env_vars={"KEY": "value"}, scope="user"
    )

    assert success
    # Verify the command was called correctly
    expected_cmd = [
        "claude",
        "mcp",
        "add",
        "test-server",
        "-e",
        "KEY=value",
        "--scope",
        "user",
        "--transport",
        "stdio",
        "echo test",
    ]
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    # Remove empty strings from args for comparison
    args = [arg for arg in args if arg.strip()]
    assert args == expected_cmd


@patch("mcp_sync.config.subprocess.run")
def test_remove_cli_mcp_server_with_scope_detection(mock_run):
    """Test removing MCP server via CLI with scope detection"""
    cm = ConfigManager()

    # Mock scope detection (get command)
    get_mock = Mock(returncode=0, stdout="test-server:\n  Scope: User\n  Type: stdio")
    # Mock removal command
    remove_mock = Mock(returncode=0)

    mock_run.side_effect = [get_mock, remove_mock]

    success = cm.remove_cli_mcp_server("claude-code", "test-server")

    assert success
    assert mock_run.call_count == 2

    # First call should be scope detection
    first_call = mock_run.call_args_list[0][0][0]
    assert "claude mcp get test-server".split() == first_call

    # Second call should be removal with detected scope
    second_call = mock_run.call_args_list[1][0][0]
    assert "claude mcp remove --scope user test-server".split() == second_call


@patch("mcp_sync.config.subprocess.run")
def test_detect_cli_server_scope(mock_run):
    """Test CLI server scope detection"""
    cm = ConfigManager()

    # Test user scope detection
    mock_run.return_value = Mock(
        returncode=0, stdout="test-server:\n  Scope: User (available in all your projects)\n"
    )

    scope = cm._detect_cli_server_scope("claude-code", "test-server")
    assert scope == "user"

    # Test project scope detection
    mock_run.return_value = Mock(returncode=0, stdout="test-server:\n  Scope: Project\n")

    scope = cm._detect_cli_server_scope("claude-code", "test-server")
    assert scope == "project"

    # Test local scope detection
    mock_run.return_value = Mock(returncode=0, stdout="test-server:\n  Scope: Local\n")

    scope = cm._detect_cli_server_scope("claude-code", "test-server")
    assert scope == "local"

    # Test fallback on error
    mock_run.return_value = Mock(returncode=1)
    scope = cm._detect_cli_server_scope("claude-code", "test-server")
    assert scope == "local"
