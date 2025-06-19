import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from mcp_sync.config.settings import Settings, get_settings
from mcp_sync.main import handle_client_info, handle_list_clients


def test_settings_loads_client_definitions():
    """Test that Settings loads built-in client definitions"""
    settings = get_settings()
    client_definitions = settings.get_client_definitions()
    clients = client_definitions.clients

    # Should have at least the built-in clients
    expected_clients = ["claude-desktop", "claude-code", "cline", "roo", "vscode-user"]
    for client in expected_clients:
        assert client in clients
        assert clients[client].name
        # CLI clients have cli_commands instead of paths
        if clients[client].config_type == "cli":
            assert clients[client].cli_commands
        else:
            assert clients[client].paths


def test_settings_merges_user_definitions():
    """Test that user client definitions override built-in ones"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a temporary settings with custom config dir
        settings = Settings()
        settings.config_dir = Path(temp_dir)
        settings.user_client_definitions_file = settings.config_dir / "client_definitions.json"

        # Create user definitions that override a built-in client
        from mcp_sync.config.models import ClientDefinitions, MCPClientConfig

        user_definitions = ClientDefinitions(
            clients={
                "roo": MCPClientConfig(
                    name="Custom Roo",
                    description="Custom Roo client",
                    paths={"linux": "~/custom/roo/path.json"},
                ),
                "custom-client": MCPClientConfig(
                    name="My Custom Client",
                    description="A custom client",
                    paths={"linux": "~/.config/custom/config.json"},
                ),
            }
        )

        settings.config_dir.mkdir(exist_ok=True)
        settings._save_user_client_definitions(user_definitions)

        # Clear cache and reload definitions
        settings._client_definitions = None
        client_definitions = settings.get_client_definitions()
        clients = client_definitions.clients

        # Should have custom client
        assert "custom-client" in clients
        assert clients["custom-client"].name == "My Custom Client"

        # Should have overridden built-in roo client
        assert "roo" in clients
        assert clients["roo"].name == "Custom Roo"


def test_handle_list_clients(capsys):
    """Test the list-clients command output"""
    settings = get_settings()
    handle_list_clients(settings)

    captured = capsys.readouterr()
    output = captured.out

    assert "Supported Clients:" in output
    assert "claude-desktop" in output
    assert "roo" in output
    assert "✅ Found" in output or "❌ Not found" in output


def test_handle_client_info_existing_client(capsys):
    """Test client-info command for existing client"""
    settings = get_settings()
    handle_client_info(settings, "roo")

    captured = capsys.readouterr()
    output = captured.out

    assert "Client: Roo" in output
    assert "Paths:" in output
    assert "linux:" in output
    assert "Config type:" in output


def test_handle_client_info_missing_client(capsys):
    """Test client-info command for non-existent client"""
    settings = get_settings()
    handle_client_info(settings, "nonexistent")

    captured = capsys.readouterr()
    output = captured.out

    assert "Client 'nonexistent' not found" in output


def test_handle_client_info_no_client_specified(capsys):
    """Test client-info command without specifying a client"""
    settings = get_settings()
    handle_client_info(settings, None)

    captured = capsys.readouterr()
    output = captured.out

    assert "Available clients:" in output
    assert "claude-desktop" in output


# CLI Client Tests
def test_cli_client_detection():
    """Test CLI client detection and configuration"""
    settings = get_settings()
    client_definitions = settings.get_client_definitions()
    clients = client_definitions.clients

    # Should have claude-code as CLI client
    assert "claude-code" in clients
    claude_code = clients["claude-code"]
    assert claude_code.config_type == "cli"
    assert claude_code.cli_commands
    assert "list_mcp" in claude_code.cli_commands


@patch("mcp_sync.clients.executor.subprocess.run")
def test_is_cli_available_success(mock_run):
    """Test CLI availability check when command succeeds"""
    from mcp_sync.clients.executor import CLIExecutor
    from mcp_sync.config.models import MCPClientConfig

    executor = CLIExecutor()

    # Mock successful version check
    mock_run.return_value = Mock(returncode=0)

    client_config = MCPClientConfig(
        name="Test CLI", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
    )

    assert executor.is_cli_available(client_config)
    mock_run.assert_called_once_with(
        ["claude", "--version"], capture_output=True, text=True, timeout=5, check=False
    )


@patch("mcp_sync.clients.executor.subprocess.run")
def test_is_cli_available_failure(mock_run):
    """Test CLI availability check when command fails"""
    from mcp_sync.clients.executor import CLIExecutor
    from mcp_sync.config.models import MCPClientConfig

    executor = CLIExecutor()

    # Mock failed version check
    mock_run.return_value = Mock(returncode=1)

    client_config = MCPClientConfig(
        name="Test CLI", config_type="cli", cli_commands={"list_mcp": "nonexistent mcp list"}
    )

    assert not executor.is_cli_available(client_config)


@patch("mcp_sync.clients.executor.subprocess.run")
def test_get_cli_mcp_servers(mock_run):
    """Test reading MCP servers from CLI"""
    from mcp_sync.clients.executor import CLIExecutor
    from mcp_sync.config.models import MCPClientConfig

    executor = CLIExecutor()

    # Mock CLI output
    mock_run.return_value = Mock(
        returncode=0, stdout="server1: echo test1\nserver2: uvx --from git+example.com tool\n"
    )

    client_config = MCPClientConfig(
        name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
    )

    servers = executor.get_mcp_servers("claude-code", client_config)

    assert servers == {
        "server1": {"command": ["echo", "test1"]},
        "server2": {"command": ["uvx", "--from", "git+example.com", "tool"]},
    }

    # Verify the subprocess call was made with proper arguments
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][0] == ["claude", "mcp", "list"]
    assert not call_args[1]["check"]


@patch("mcp_sync.clients.executor.subprocess.run")
def test_add_cli_mcp_server(mock_run):
    """Test adding MCP server via CLI"""
    from mcp_sync.clients.executor import CLIExecutor
    from mcp_sync.config.models import MCPClientConfig

    executor = CLIExecutor()

    # Mock successful add
    mock_run.return_value = Mock(returncode=0)

    client_config = MCPClientConfig(
        name="Claude Code",
        config_type="cli",
        cli_commands={
            "add_mcp": (
                "claude mcp add {name} -e {env_flags} --scope {scope} "
                "--transport {transport} {command_args}"
            )
        },
    )

    success = executor.add_mcp_server(
        "claude-code",
        client_config,
        "test-server",
        ["echo", "test"],
        env_vars={"KEY": "value"},
        scope="user",
    )

    assert success
    # Verify the command was called correctly
    mock_run.assert_called_once()


@patch("mcp_sync.clients.executor.subprocess.run")
def test_remove_cli_mcp_server_with_scope_detection(mock_run):
    """Test removing MCP server via CLI with scope detection"""
    from mcp_sync.clients.executor import CLIExecutor
    from mcp_sync.config.models import MCPClientConfig

    executor = CLIExecutor()

    # Mock scope detection (get command)
    get_mock = Mock(returncode=0, stdout="test-server:\n  Scope: User\n  Type: stdio")
    # Mock removal command
    remove_mock = Mock(returncode=0)

    mock_run.side_effect = [get_mock, remove_mock]

    client_config = MCPClientConfig(
        name="Claude Code",
        config_type="cli",
        cli_commands={
            "get_mcp": "claude mcp get {name}",
            "remove_mcp": "claude mcp remove --scope {scope} {name}",
        },
    )

    success = executor.remove_mcp_server("claude-code", client_config, "test-server")

    assert success
    assert mock_run.call_count == 2


@patch("mcp_sync.clients.executor.subprocess.run")
def test_detect_cli_server_scope(mock_run):
    """Test CLI server scope detection"""
    from mcp_sync.clients.executor import CLIExecutor
    from mcp_sync.config.models import MCPClientConfig

    executor = CLIExecutor()

    client_config = MCPClientConfig(
        name="Claude Code", config_type="cli", cli_commands={"get_mcp": "claude mcp get {name}"}
    )

    # Test user scope detection
    mock_run.return_value = Mock(
        returncode=0, stdout="test-server:\n  Scope: User (available in all your projects)\n"
    )

    scope = executor._detect_server_scope("claude-code", client_config, "test-server")
    assert scope == "user"

    # Test project scope detection
    mock_run.return_value = Mock(returncode=0, stdout="test-server:\n  Scope: Project\n")

    scope = executor._detect_server_scope("claude-code", client_config, "test-server")
    assert scope == "project"

    # Test local scope detection
    mock_run.return_value = Mock(returncode=0, stdout="test-server:\n  Scope: Local\n")

    scope = executor._detect_server_scope("claude-code", client_config, "test-server")
    assert scope == "local"

    # Test fallback on error
    mock_run.return_value = Mock(returncode=1)
    scope = executor._detect_server_scope("claude-code", client_config, "test-server")
    assert scope == "local"
