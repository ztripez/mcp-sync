from unittest.mock import patch

from mcp_sync.config.models import (
    ClientDefinitions,
    GlobalConfig,
    LocationConfig,
    LocationsConfig,
    MCPClientConfig,
    MCPServerConfig,
)
from mcp_sync.sync import SyncEngine, SyncResult


class MockSettings:
    """Mock Settings class that implements the new Settings interface."""

    def __init__(self, locations=None, global_config=None, client_definitions=None):
        self._locations_config = LocationsConfig(
            locations=[LocationConfig(**loc) for loc in (locations or [])]
        )
        self._global_config = global_config or GlobalConfig()
        self._client_definitions = client_definitions or ClientDefinitions()
        self._cli_servers = {}

    def get_locations_config(self):
        return self._locations_config

    def get_global_config(self):
        return self._global_config

    def get_client_definitions(self):
        return self._client_definitions

    def _save_global_config(self, config):
        self._global_config = config

    # CLI server management methods for testing
    def get_cli_mcp_servers(self, client_id):
        return self._cli_servers.get(client_id, {})

    def set_cli_servers(self, client_id, servers):
        self._cli_servers[client_id] = servers

    def add_cli_mcp_server(self, client_id, name, command, env_vars=None):
        if client_id not in self._cli_servers:
            self._cli_servers[client_id] = {}
        self._cli_servers[client_id][name] = {"command": command, "env": env_vars or {}}
        return True

    def remove_cli_mcp_server(self, client_id, name, scope=None):
        if client_id in self._cli_servers and name in self._cli_servers[client_id]:
            del self._cli_servers[client_id][name]
            return True
        return False


def test_get_sync_locations_filters(tmp_path):
    # Create LocationConfig objects with proper fields
    locs = [
        LocationConfig(path=str(tmp_path / "g.json"), name="g", type="manual", config_type="file"),
        LocationConfig(path=str(tmp_path / "p.json"), name="p", type="manual", config_type="file"),
        LocationConfig(
            path=str(tmp_path / ".mcp.json"), name="proj", type="manual", config_type="file"
        ),
    ]
    locations_config = LocationsConfig(locations=locs)
    settings = MockSettings()
    settings._locations_config = locations_config
    engine = SyncEngine(settings)

    all_locs = engine._get_sync_locations(None, False, False)
    assert len(all_locs) == 2
    assert all(loc["path"] != str(tmp_path / ".mcp.json") for loc in all_locs)

    # Since the scope filtering logic in _get_sync_locations doesn't use scope field,
    # we need to test the actual filtering behavior
    # The method filters by .mcp.json files, not by scope

    # Test specific location selection
    spec = engine._get_sync_locations(str(tmp_path / "p.json"), False, False)
    assert len(spec) == 1
    assert spec[0]["path"] == str(tmp_path / "p.json")

    missing = engine._get_sync_locations("/nope", False, False)
    assert missing == []


# CLI Sync Tests
def test_sync_cli_location_add_servers():
    """Test syncing CLI location with new servers"""
    # Set up client definitions with claude-code CLI client
    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[], client_definitions=client_definitions)
    engine = SyncEngine(settings)

    # Set up master servers
    master_servers = {
        "server1": {"command": ["echo", "test1"], "_source": "global"},
        "server2": {"command": ["echo", "test2"], "_source": "global"},
    }

    # Set up CLI location with no existing servers
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])

    # Mock the CLI executor methods
    with patch.object(engine.executor, "get_mcp_servers", return_value={}):
        with patch.object(engine.executor, "add_mcp_server", return_value=True) as mock_add:
            with patch.object(engine.executor, "remove_mcp_server", return_value=True):
                engine._sync_cli_location(cli_location, master_servers, result)

                # Should update the location and add both servers
                assert "cli:claude-code" in result.updated_locations
                assert len(result.conflicts) == 0
                assert len(result.errors) == 0

                # Verify add_mcp_server was called for both servers
                assert mock_add.call_count == 2


def test_sync_cli_location_remove_servers():
    """Test syncing CLI location with server removal"""
    # Set up client definitions with claude-code CLI client
    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[], client_definitions=client_definitions)
    engine = SyncEngine(settings)

    # Set up existing CLI servers
    existing_servers = {
        "server1": {"command": ["echo", "test1"]},
        "server2": {"command": ["echo", "test2"]},
        "server3": {"command": ["echo", "test3"]},
    }

    # Master only has server1 and server2 (server3 should be removed)
    master_servers = {
        "server1": {"command": ["echo", "test1"], "_source": "global"},
        "server2": {"command": ["echo", "test2"], "_source": "global"},
    }

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])

    # Mock the CLI executor methods
    with patch.object(engine.executor, "get_mcp_servers", return_value=existing_servers):
        with patch.object(engine.executor, "add_mcp_server", return_value=True):
            with patch.object(
                engine.executor, "remove_mcp_server", return_value=True
            ) as mock_remove:
                engine._sync_cli_location(cli_location, master_servers, result)

                # Should update the location
                assert "cli:claude-code" in result.updated_locations

                # Verify server3 was removed
                mock_remove.assert_called_once_with(
                    "claude-code", client_definitions.clients["claude-code"], "server3"
                )


def test_sync_cli_location_detect_conflicts():
    """Test CLI sync conflict detection"""
    # Set up client definitions with claude-code CLI client
    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[], client_definitions=client_definitions)
    engine = SyncEngine(settings)

    # Set up existing CLI server with different command
    existing_servers = {"server1": {"command": ["echo", "old-command"]}}

    # Master has same server with different command
    master_servers = {"server1": {"command": ["echo", "new-command"], "_source": "global"}}

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])

    # Mock the CLI executor methods
    with patch.object(engine.executor, "get_mcp_servers", return_value=existing_servers):
        with patch.object(engine.executor, "add_mcp_server", return_value=True):
            with patch.object(engine.executor, "remove_mcp_server", return_value=True):
                engine._sync_cli_location(cli_location, master_servers, result)

                # Should detect conflict
                assert len(result.conflicts) == 1
                conflict = result.conflicts[0]
                assert conflict["server"] == "server1"
                assert conflict["action"] == "overridden"
                assert conflict["source"] == "global"


def test_sync_cli_location_no_changes_needed():
    """Test CLI sync when no changes are needed"""
    # Set up client definitions with claude-code CLI client
    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[], client_definitions=client_definitions)
    engine = SyncEngine(settings)

    # Set up CLI servers that match master exactly
    existing_servers = {
        "server1": {"command": ["echo", "test1"]},
        "server2": {"command": ["echo", "test2"]},
    }

    # Master has same servers
    master_servers = {
        "server1": {"command": ["echo", "test1"], "_source": "global"},
        "server2": {"command": ["echo", "test2"], "_source": "global"},
    }

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])

    # Mock the CLI executor methods
    with patch.object(engine.executor, "get_mcp_servers", return_value=existing_servers):
        with patch.object(engine.executor, "add_mcp_server", return_value=True):
            with patch.object(engine.executor, "remove_mcp_server", return_value=True):
                engine._sync_cli_location(cli_location, master_servers, result)

                # Should not update anything (no changes needed)
                assert "cli:claude-code" not in result.updated_locations
                assert len(result.conflicts) == 0
                assert len(result.errors) == 0


def test_sync_cli_location_dry_run():
    """Test CLI sync in dry run mode"""
    # Set up client definitions with claude-code CLI client
    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[], client_definitions=client_definitions)
    engine = SyncEngine(settings)

    # Set up existing server to be removed
    existing_servers = {"old-server": {"command": ["echo", "old"]}}

    # Master has different server
    master_servers = {"new-server": {"command": ["echo", "new"], "_source": "global"}}

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [], dry_run=True)

    # Mock the CLI executor methods
    with patch.object(engine.executor, "get_mcp_servers", return_value=existing_servers):
        with patch.object(engine.executor, "add_mcp_server", return_value=True) as mock_add:
            with patch.object(
                engine.executor, "remove_mcp_server", return_value=True
            ) as mock_remove:
                engine._sync_cli_location(cli_location, master_servers, result)

                # Should detect changes and record them (even in dry run)
                assert "cli:claude-code" in result.updated_locations

                # Verify no actual changes were made (no CLI calls in dry run)
                mock_add.assert_not_called()
                mock_remove.assert_not_called()


def test_sync_all_includes_cli_clients():
    """Test that sync_all includes CLI clients"""
    cli_location = LocationConfig(
        path="cli:claude-code", name="claude-code", type="manual", config_type="cli"
    )
    file_location = LocationConfig(
        path="/test/file.json", name="test-file", type="manual", config_type="file"
    )

    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    locations_config = LocationsConfig(locations=[cli_location, file_location])
    settings = MockSettings(client_definitions=client_definitions)
    settings._locations_config = locations_config
    engine = SyncEngine(settings)

    # Track which sync methods are called
    cli_calls = []

    def track_cli_sync(location, master_servers, result):
        cli_calls.append(location)

    # Mock both sync methods
    with patch.object(engine, "_sync_cli_location", side_effect=track_cli_sync) as mock_cli_sync:
        with patch.object(engine, "_read_json_config", return_value={"mcpServers": {}}):
            engine.sync_all()

            # Should call CLI sync for CLI client
            assert len(cli_calls) == 1
            # Compare the path since the location dict will have additional fields
            assert cli_calls[0]["path"] == "cli:claude-code"
            assert cli_calls[0]["config_type"] == "cli"

            # File sync should not call CLI sync (file is handled by _sync_location)
            # Just verify _sync_location was called for both
            mock_cli_sync.assert_called_once()


# CLI Vacuum Tests
def test_vacuum_includes_cli_clients():
    """Test that vacuum includes CLI clients"""
    # Set up CLI and file locations
    cli_location = {
        "path": "cli:claude-code",
        "name": "claude-code",
        "type": "manual",
        "config_type": "cli",
    }
    file_location = {
        "path": "/test/file.json",
        "name": "test-file",
        "type": "manual",
        "config_type": "file",
    }

    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(
        locations=[cli_location, file_location], client_definitions=client_definitions
    )

    # Add some servers to CLI client
    cli_servers = {
        "cli-server1": {"command": ["echo", "cli1"]},
        "cli-server2": {"command": ["echo", "cli2"]},
    }

    engine = SyncEngine(settings)

    # Mock the repository.discover_clients() call
    with patch("mcp_sync.clients.repository.ClientRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.discover_clients.return_value = []  # No new clients discovered

        # Mock file operations to avoid actual file reads
        with patch.object(engine, "_read_json_config") as mock_read:
            with patch.object(engine.executor, "get_mcp_servers", return_value=cli_servers):
                # Mock file config with servers
                mock_read.return_value = {
                    "mcpServers": {
                        "file-server1": {"command": ["echo", "file1"]},
                        "file-server2": {"command": ["echo", "file2"]},
                    }
                }

                # Mock the conflict resolution to always choose first option
                with patch.object(engine, "_resolve_conflict", return_value="existing"):
                    result = engine.vacuum_configs()

                    # Should import servers from both CLI and file clients
                    assert len(result.imported_servers) == 4
                    assert "cli-server1" in result.imported_servers
                    assert "cli-server2" in result.imported_servers
                    assert "file-server1" in result.imported_servers
                    assert "file-server2" in result.imported_servers

                    # CLI servers should be attributed to CLI client
                    assert result.imported_servers["cli-server1"] == "claude-code"
                    assert result.imported_servers["cli-server2"] == "claude-code"


def test_vacuum_cli_conflict_resolution():
    """Test vacuum conflict resolution between CLI and file clients"""
    cli_location = {
        "path": "cli:claude-code",
        "name": "claude-code",
        "type": "manual",
        "config_type": "cli",
    }
    file_location = {
        "path": "/test/file.json",
        "name": "test-file",
        "type": "manual",
        "config_type": "file",
    }

    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(
        locations=[cli_location, file_location], client_definitions=client_definitions
    )

    # Both clients have same server name but different configs
    cli_servers = {"shared-server": {"command": ["echo", "from-cli"]}}

    engine = SyncEngine(settings)

    # Mock the repository.discover_clients() call
    with patch("mcp_sync.clients.repository.ClientRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.discover_clients.return_value = []  # No new clients discovered

        with patch.object(engine, "_read_json_config") as mock_read:
            with patch.object(engine.executor, "get_mcp_servers", return_value=cli_servers):
                mock_read.return_value = {
                    "mcpServers": {"shared-server": {"command": ["echo", "from-file"]}}
                }

                # Mock conflict resolution to choose CLI version (new)
                with patch.object(engine, "_resolve_conflict", return_value="new") as mock_resolve:
                    result = engine.vacuum_configs()

                    # Should detect conflict and resolve it
                    mock_resolve.assert_called_once()
                    args = mock_resolve.call_args[0]
                    assert args[0] == "shared-server"  # server name
                    assert args[1] == {
                        "command": ["echo", "from-cli"]
                    }  # existing (CLI processed first)  # noqa: E501
                    assert args[2] == "claude-code"  # existing source
                    assert args[3] == {"command": ["echo", "from-file"]}  # new (file)
                    assert args[4] == "test-file"  # new source

                    # Should have one conflict in results
                    assert len(result.conflicts) == 1
                    conflict = result.conflicts[0]
                    assert conflict["server"] == "shared-server"
                    assert conflict["chosen_source"] == "test-file"  # "new" was chosen
                    assert conflict["rejected_source"] == "claude-code"

                    # Final imported server should be file version (since "new" was chosen)
                    assert result.imported_servers["shared-server"] == "test-file"


def test_vacuum_cli_no_servers():
    """Test vacuum when CLI client has no servers"""
    cli_location = {
        "path": "cli:claude-code",
        "name": "claude-code",
        "type": "manual",
        "config_type": "cli",
    }

    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[cli_location], client_definitions=client_definitions)
    # CLI has no servers (empty dict)

    engine = SyncEngine(settings)

    # Mock the repository.discover_clients() call
    with patch("mcp_sync.clients.repository.ClientRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.discover_clients.return_value = []  # No new clients discovered

        with patch.object(engine.executor, "get_mcp_servers", return_value={}):
            result = engine.vacuum_configs()

            # Should complete without errors
            assert len(result.imported_servers) == 0
            assert len(result.conflicts) == 0
            assert len(result.errors) == 0


def test_vacuum_saves_to_global_config():
    """Test that vacuum saves discovered servers to global config"""
    cli_location = {
        "path": "cli:claude-code",
        "name": "claude-code",
        "type": "manual",
        "config_type": "cli",
    }

    client_definitions = ClientDefinitions(
        clients={
            "claude-code": MCPClientConfig(
                name="Claude Code", config_type="cli", cli_commands={"list_mcp": "claude mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[cli_location], client_definitions=client_definitions)
    cli_servers = {"test-server": {"command": ["echo", "test"]}}

    engine = SyncEngine(settings)

    # Mock the repository.discover_clients() call
    with patch("mcp_sync.clients.repository.ClientRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.discover_clients.return_value = []  # No new clients discovered

        with patch.object(engine.executor, "get_mcp_servers", return_value=cli_servers):
            result = engine.vacuum_configs()

            # Should import the server
            assert len(result.imported_servers) == 1
            assert "test-server" in result.imported_servers

            # Should save to global config
            global_config = settings.get_global_config()
            assert "test-server" in global_config.mcpServers
            assert global_config.mcpServers["test-server"].command == ["echo", "test"]


def test_vacuum_auto_resolve_first():
    """Conflicts should be resolved automatically keeping first seen version"""
    cli_loc = {"path": "cli:cli", "name": "cli", "type": "manual", "config_type": "cli"}
    file_loc = {"path": "/tmp/f.json", "name": "file", "type": "manual", "config_type": "file"}

    client_definitions = ClientDefinitions(
        clients={
            "cli": MCPClientConfig(
                name="CLI Client", config_type="cli", cli_commands={"list_mcp": "cli mcp list"}
            )
        }
    )
    settings = MockSettings(locations=[cli_loc, file_loc], client_definitions=client_definitions)
    cli_servers = {"srv": {"command": ["echo", "cli"]}}

    engine = SyncEngine(settings)

    # Mock the repository.discover_clients() call
    with patch("mcp_sync.clients.repository.ClientRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.discover_clients.return_value = []  # No new clients discovered

        with patch.object(engine, "_read_json_config") as mock_read:
            with patch.object(engine.executor, "get_mcp_servers", return_value=cli_servers):
                mock_read.return_value = {"mcpServers": {"srv": {"command": ["echo", "file"]}}}
                with patch.object(engine, "_resolve_conflict") as mock_resolve:
                    result = engine.vacuum_configs(auto_resolve="first")
                    mock_resolve.assert_not_called()
                    assert result.imported_servers["srv"] == "cli"
                    assert result.conflicts[0]["chosen_source"] == "cli"
                    assert result.conflicts[0]["rejected_source"] == "file"


def test_vacuum_skip_existing():
    """Existing global servers are not overwritten when skip_existing is True"""
    cli_loc = {"path": "cli:code", "name": "code", "type": "manual", "config_type": "cli"}

    client_definitions = ClientDefinitions(
        clients={
            "code": MCPClientConfig(
                name="Code Client", config_type="cli", cli_commands={"list_mcp": "code mcp list"}
            )
        }
    )

    # Set up global config with existing server
    global_config = GlobalConfig(mcpServers={"existing": MCPServerConfig(command=["echo", "old"])})
    settings = MockSettings(
        locations=[cli_loc], global_config=global_config, client_definitions=client_definitions
    )

    cli_servers = {"existing": {"command": ["echo", "new"]}}

    engine = SyncEngine(settings)

    # Mock the repository.discover_clients() call
    with patch("mcp_sync.clients.repository.ClientRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.discover_clients.return_value = []  # No new clients discovered

        with patch.object(engine.executor, "get_mcp_servers", return_value=cli_servers):
            result = engine.vacuum_configs(skip_existing=True)

            assert "existing" in result.skipped_servers
            assert "existing" not in result.imported_servers
            assert settings.get_global_config().mcpServers["existing"].command == ["echo", "old"]
