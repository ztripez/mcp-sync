from unittest.mock import patch

from mcp_sync.sync import SyncEngine, SyncResult


class DummyConfig:
    def __init__(self, locations):
        self._locations = locations

    def get_locations(self):
        return self._locations

    def get_global_config(self):
        return {"mcpServers": {}}


def test_get_sync_locations_filters(tmp_path):
    locs = [
        {"path": str(tmp_path / "g.json"), "name": "g", "scope": "global"},
        {"path": str(tmp_path / "p.json"), "name": "p", "scope": "project"},
        {"path": str(tmp_path / ".mcp.json"), "name": "proj", "scope": "project"},
    ]
    engine = SyncEngine(DummyConfig(locs))

    all_locs = engine._get_sync_locations(None, False, False)
    assert len(all_locs) == 2
    assert all(loc["path"] != str(tmp_path / ".mcp.json") for loc in all_locs)

    g_only = engine._get_sync_locations(None, True, False)
    assert g_only == [locs[0]]

    p_only = engine._get_sync_locations(None, False, True)
    assert p_only == [locs[1]]

    spec = engine._get_sync_locations(locs[1]["path"], False, False)
    assert spec == [locs[1]]

    missing = engine._get_sync_locations("/nope", False, False)
    assert missing == []


# CLI Sync Tests
class DummyCLIConfig:
    def __init__(self, locations):
        self._locations = locations
        self._global_config = {"mcpServers": {}}
        self._cli_servers = {}

    def get_locations(self):
        return self._locations

    def get_global_config(self):
        return self._global_config

    def set_global_config(self, config):
        self._global_config = config

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

    def _save_global_config(self, config):
        self._global_config = config


def test_sync_cli_location_add_servers():
    """Test syncing CLI location with new servers"""
    config = DummyCLIConfig([])
    engine = SyncEngine(config)

    # Set up master servers
    master_servers = {
        "server1": {"command": ["echo", "test1"], "_source": "global"},
        "server2": {"command": ["echo", "test2"], "_source": "global"},
    }

    # Set up CLI location with no existing servers
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])
    engine._sync_cli_location(cli_location, master_servers, result)

    # Should update the location and add both servers
    assert "cli:claude-code" in result.updated_locations
    assert len(result.conflicts) == 0
    assert len(result.errors) == 0

    # Verify servers were added
    cli_servers = config.get_cli_mcp_servers("claude-code")
    assert "server1" in cli_servers
    assert "server2" in cli_servers
    assert cli_servers["server1"]["command"] == ["echo", "test1"]


def test_sync_cli_location_remove_servers():
    """Test syncing CLI location with server removal"""
    config = DummyCLIConfig([])
    engine = SyncEngine(config)

    # Set up existing CLI servers
    config.set_cli_servers(
        "claude-code",
        {
            "server1": {"command": ["echo", "test1"]},
            "server2": {"command": ["echo", "test2"]},
            "server3": {"command": ["echo", "test3"]},
        },
    )

    # Master only has server1 and server2 (server3 should be removed)
    master_servers = {
        "server1": {"command": ["echo", "test1"], "_source": "global"},
        "server2": {"command": ["echo", "test2"], "_source": "global"},
    }

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])
    engine._sync_cli_location(cli_location, master_servers, result)

    # Should update the location
    assert "cli:claude-code" in result.updated_locations

    # Verify server3 was removed
    cli_servers = config.get_cli_mcp_servers("claude-code")
    assert "server1" in cli_servers
    assert "server2" in cli_servers
    assert "server3" not in cli_servers


def test_sync_cli_location_detect_conflicts():
    """Test CLI sync conflict detection"""
    config = DummyCLIConfig([])
    engine = SyncEngine(config)

    # Set up existing CLI server with different command
    config.set_cli_servers("claude-code", {"server1": {"command": ["echo", "old-command"]}})

    # Master has same server with different command
    master_servers = {"server1": {"command": ["echo", "new-command"], "_source": "global"}}

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])
    engine._sync_cli_location(cli_location, master_servers, result)

    # Should detect conflict
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict["server"] == "server1"
    assert conflict["action"] == "overridden"
    assert conflict["source"] == "global"

    # Server should be updated to master version
    cli_servers = config.get_cli_mcp_servers("claude-code")
    assert cli_servers["server1"]["command"] == ["echo", "new-command"]


def test_sync_cli_location_no_changes_needed():
    """Test CLI sync when no changes are needed"""
    config = DummyCLIConfig([])
    engine = SyncEngine(config)

    # Set up CLI servers that match master exactly
    config.set_cli_servers(
        "claude-code",
        {"server1": {"command": ["echo", "test1"]}, "server2": {"command": ["echo", "test2"]}},
    )

    # Master has same servers
    master_servers = {
        "server1": {"command": ["echo", "test1"], "_source": "global"},
        "server2": {"command": ["echo", "test2"], "_source": "global"},
    }

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [])
    engine._sync_cli_location(cli_location, master_servers, result)

    # Should not update anything (no changes needed)
    assert "cli:claude-code" not in result.updated_locations
    assert len(result.conflicts) == 0
    assert len(result.errors) == 0


def test_sync_cli_location_dry_run():
    """Test CLI sync in dry run mode"""
    config = DummyCLIConfig([])
    engine = SyncEngine(config)

    # Set up existing server to be removed
    config.set_cli_servers("claude-code", {"old-server": {"command": ["echo", "old"]}})

    # Master has different server
    master_servers = {"new-server": {"command": ["echo", "new"], "_source": "global"}}

    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    result = SyncResult([], [], [], dry_run=True)
    engine._sync_cli_location(cli_location, master_servers, result)

    # Should detect changes but not apply them
    assert "cli:claude-code" not in result.updated_locations

    # Verify no actual changes were made
    cli_servers = config.get_cli_mcp_servers("claude-code")
    assert "old-server" in cli_servers  # Still there
    assert "new-server" not in cli_servers  # Not added


def test_sync_all_includes_cli_clients():
    """Test that sync_all includes CLI clients"""
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}
    file_location = {"path": "/test/file.json", "name": "test-file", "config_type": "file"}

    config = DummyCLIConfig([cli_location, file_location])
    engine = SyncEngine(config)

    # Track which sync methods are called
    cli_calls = []
    file_calls = []

    def track_cli_sync(location, master_servers, result):
        cli_calls.append(location)

    def track_file_sync(location, master_servers, result):
        file_calls.append(location)

    # Mock both sync methods
    with patch.object(engine, "_sync_cli_location", side_effect=track_cli_sync) as mock_cli_sync:
        with patch.object(engine, "_read_json_config", return_value={"mcpServers": {}}):
            engine.sync_all()

            # Should call CLI sync for CLI client
            assert len(cli_calls) == 1
            assert cli_calls[0] == cli_location

            # File sync should not call CLI sync (file is handled by _sync_location)
            # Just verify _sync_location was called for both
            mock_cli_sync.assert_called_once()


# CLI Vacuum Tests
def test_vacuum_includes_cli_clients():
    """Test that vacuum includes CLI clients"""
    # Set up CLI and file locations
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}
    file_location = {"path": "/test/file.json", "name": "test-file", "config_type": "file"}

    config = DummyCLIConfig([cli_location, file_location])

    # Add some servers to CLI client
    config.set_cli_servers(
        "claude-code",
        {
            "cli-server1": {"command": ["echo", "cli1"]},
            "cli-server2": {"command": ["echo", "cli2"]},
        },
    )

    engine = SyncEngine(config)

    # Mock file operations to avoid actual file reads
    with patch.object(engine, "_read_json_config") as mock_read:
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
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}
    file_location = {"path": "/test/file.json", "name": "test-file", "config_type": "file"}

    config = DummyCLIConfig([cli_location, file_location])

    # Both clients have same server name but different configs
    config.set_cli_servers("claude-code", {"shared-server": {"command": ["echo", "from-cli"]}})

    engine = SyncEngine(config)

    with patch.object(engine, "_read_json_config") as mock_read:
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
            assert args[1] == {"command": ["echo", "from-cli"]}  # existing (CLI processed first)
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
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    config = DummyCLIConfig([cli_location])
    # CLI has no servers (empty dict)
    config.set_cli_servers("claude-code", {})

    engine = SyncEngine(config)
    result = engine.vacuum_configs()

    # Should complete without errors
    assert len(result.imported_servers) == 0
    assert len(result.conflicts) == 0
    assert len(result.errors) == 0


def test_vacuum_saves_to_global_config():
    """Test that vacuum saves discovered servers to global config"""
    cli_location = {"path": "cli:claude-code", "name": "claude-code", "config_type": "cli"}

    config = DummyCLIConfig([cli_location])
    config.set_cli_servers("claude-code", {"test-server": {"command": ["echo", "test"]}})

    engine = SyncEngine(config)
    result = engine.vacuum_configs()

    # Should import the server
    assert len(result.imported_servers) == 1
    assert "test-server" in result.imported_servers

    # Should save to global config
    global_config = config.get_global_config()
    assert "test-server" in global_config["mcpServers"]
    assert global_config["mcpServers"]["test-server"]["command"] == ["echo", "test"]


def test_vacuum_auto_resolve_first():
    """Conflicts should be resolved automatically keeping first seen version"""
    cli_loc = {"path": "cli:cli", "name": "cli", "config_type": "cli"}
    file_loc = {"path": "/tmp/f.json", "name": "file", "config_type": "file"}

    config = DummyCLIConfig([cli_loc, file_loc])
    config.set_cli_servers("cli", {"srv": {"command": ["echo", "cli"]}})

    engine = SyncEngine(config)
    with patch.object(engine, "_read_json_config") as mock_read:
        mock_read.return_value = {"mcpServers": {"srv": {"command": ["echo", "file"]}}}
        with patch.object(engine, "_resolve_conflict") as mock_resolve:
            result = engine.vacuum_configs(auto_resolve="first")
            mock_resolve.assert_not_called()
            assert result.imported_servers["srv"] == "cli"
            assert result.conflicts[0]["chosen_source"] == "cli"
            assert result.conflicts[0]["rejected_source"] == "file"


def test_vacuum_skip_existing():
    """Existing global servers are not overwritten when skip_existing is True"""
    cli_loc = {"path": "cli:code", "name": "code", "config_type": "cli"}
    config = DummyCLIConfig([cli_loc])
    config.set_cli_servers("code", {"existing": {"command": ["echo", "new"]}})
    config.set_global_config({"mcpServers": {"existing": {"command": ["echo", "old"]}}})

    engine = SyncEngine(config)
    result = engine.vacuum_configs(skip_existing=True)

    assert "existing" in result.skipped_servers
    assert "existing" not in result.imported_servers
    assert config.get_global_config()["mcpServers"]["existing"]["command"] == ["echo", "old"]
