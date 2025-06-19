from mcp_sync.sync import SyncEngine


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
