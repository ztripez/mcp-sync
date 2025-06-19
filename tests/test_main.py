import argparse

from mcp_sync import main


def test_create_parser_subcommands():
    parser = main.create_parser()
    commands = [
        ("scan", []),
        ("status", []),
        ("diff", []),
        ("add-location", ["path"]),
        ("remove-location", ["path"]),
        ("list-locations", []),
        ("sync", []),
        ("add-server", ["name"]),
        ("remove-server", ["name"]),
        ("list-servers", []),
        ("vacuum", []),
        ("init", []),
        ("template", []),
        ("list-clients", []),
        ("client-info", []),
        ("edit-client-definitions", []),
    ]
    for cmd, extra in commands:
        args = parser.parse_args([cmd] + extra)
        assert args.command == cmd


def test_build_server_config_from_args():
    args = argparse.Namespace(server_cmd="python", args="a,b", env="A=1,B=2", scope=None)
    config = main._build_server_config_from_args(args)
    assert config == {
        "command": ["python"],
        "args": ["a", "b"],
        "env": {"A": "1", "B": "2"},
    }


def test_get_effective_config_project_overrides():
    status = {
        "project_servers": {"s": {"command": "proj"}},
        "global_servers": {"s": {"command": "glob"}},
    }
    cfg = main._get_effective_config("s", status)
    assert cfg["command"] == "proj"
