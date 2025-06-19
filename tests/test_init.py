from mcp_sync.main import handle_init


def test_handle_init_creates_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    handle_init()
    assert (tmp_path / ".mcp.json").exists()
    out = capsys.readouterr().out
    assert "Created .mcp.json" in out


def test_handle_init_existing_file(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / ".mcp.json"
    cfg.write_text("{}")
    monkeypatch.chdir(tmp_path)
    handle_init()
    out = capsys.readouterr().out
    assert ".mcp.json already exists" in out
