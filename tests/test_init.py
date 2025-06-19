from mcp_sync.main import handle_init


def test_handle_init_creates_file(tmp_path, monkeypatch, capsys):
    """Test that handle_init creates a .mcp.json file with proper structure"""
    monkeypatch.chdir(tmp_path)
    handle_init()
    assert (tmp_path / ".mcp.json").exists()
    out = capsys.readouterr().out
    assert "Created .mcp.json" in out

    # Verify the file has the correct structure
    import json

    with open(tmp_path / ".mcp.json") as f:
        config = json.load(f)
    assert "mcpServers" in config
    assert isinstance(config["mcpServers"], dict)


def test_handle_init_existing_file(tmp_path, monkeypatch, capsys):
    """Test that handle_init doesn't overwrite existing .mcp.json files"""
    cfg = tmp_path / ".mcp.json"
    cfg.write_text("{}")
    monkeypatch.chdir(tmp_path)
    handle_init()
    out = capsys.readouterr().out
    assert ".mcp.json already exists" in out
