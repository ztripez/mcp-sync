# mcp-sync

Sync MCP (Model Context Protocol) configurations across AI tools.

## Overview

`mcp-sync` is a command-line tool that helps you manage and synchronize MCP server configurations across different AI coding tools like Claude Desktop, Claude Code, Cline, VS Code extensions, and more.

## Features

- **Auto-discovery**: Automatically finds MCP configs on your system
- **Manual registration**: Add custom config file locations for future-proofing
- **Global & project configs**: Supports both user-wide and project-specific servers
- **Conflict resolution**: Smart merging with project configs taking priority
- **Dry-run mode**: Preview changes before applying them
- **Cross-platform**: Works on macOS, Windows, and Linux

## Installation

### Quick Usage (Recommended)
```bash
uvx mcp-sync status
uvx mcp-sync sync --dry-run
```

### Persistent Installation
```bash
uv tool install mcp-sync
mcp-sync status
```

### Development Install
```bash
git clone <repo-url>
cd mcp-sync
uv pip install -e .
```

## Quick Start

1. **Scan for existing configs**:
   ```bash
   mcp-sync scan
   ```

2. **Check current status**:
   ```bash
   mcp-sync status
   ```

3. **Add a server to global config**:
   ```bash
   mcp-sync add-server filesystem
   # Follow prompts to configure
   ```

4. **Preview sync changes**:
   ```bash
   mcp-sync diff
   mcp-sync sync --dry-run
   ```

5. **Sync configurations**:
   ```bash
   mcp-sync sync
   ```

## Commands

### Discovery & Status
- `mcp-sync scan` - Auto-discover known MCP configs
- `mcp-sync status` - Show sync status
- `mcp-sync diff` - Show config differences

### Config Location Management
- `mcp-sync add-location <path> [--name <alias>]` - Register custom config file
- `mcp-sync remove-location <path>` - Unregister config location
- `mcp-sync list-locations` - Show all registered config paths

### Sync Operations
- `mcp-sync sync` - Sync all registered configs
- `mcp-sync sync --dry-run` - Preview changes without applying
- `mcp-sync sync --global-only` - Sync only global configs
- `mcp-sync sync --project-only` - Sync only project configs
- `mcp-sync sync --location <path>` - Sync specific location only

### Server Management
- `mcp-sync add-server <name>` - Add MCP server to sync
- `mcp-sync remove-server <name>` - Remove server from sync
- `mcp-sync list-servers` - Show all managed servers

### Project Management
- `mcp-sync init` - Create project `.mcp.json`
- `mcp-sync template` - Show template config

## Configuration Hierarchy

`mcp-sync` uses a three-tier configuration system:

1. **Global Config** (`~/.mcp-sync/global.json`)
   - Personal development servers
   - Synced across all tools

2. **Project Config** (`.mcp.json` in project root)
   - Project-specific servers
   - Version controlled with your project
   - Takes priority over global config

3. **Tool Configs** (Auto-discovered locations)
   - Claude Desktop, VS Code, Cline, etc.
   - Updated by sync operations

## Supported Tools

- **Claude Desktop** - `~/Library/Application Support/Claude/` (macOS)
- **Claude Code** - `~/.claude/settings.json`
- **Cline** - VS Code global storage
- **VS Code** - User and workspace settings
- **Custom tools** - Via manual location registration

## Example Workflow

```bash
# 1. Initialize project config
mcp-sync init

# 2. Add project-specific server
mcp-sync add-server database
# Choose "2. Project config"
# Command: python
# Args: /path/to/db-server.py
# Env: DB_URL=postgresql://...

# 3. Add global development server
mcp-sync add-server filesystem
# Choose "1. Global config"  
# Command: npx
# Args: -y, @modelcontextprotocol/server-filesystem, /home/user

# 4. Sync to all tools
mcp-sync sync

# 5. Check status
mcp-sync status
```

## Configuration File Format

### MCP Server Configuration
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem", 
        "/path/to/directory"
      ]
    },
    "custom-server": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "API_KEY": "your-api-key"
      }
    }
  }
}
```

## Development

### Requirements
- Python 3.12+
- uv package manager

### Setup
```bash
git clone <repo-url>
cd mcp-sync
uv sync
uv pip install -e .
```

### Code Quality
```bash
uv run ruff check .     # Linting
uv run ruff format .    # Formatting
uv run pytest          # Tests (when available)
```

## License

[License details here]

## Contributing

[Contributing guidelines here]