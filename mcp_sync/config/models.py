"""Pydantic models for configuration validation."""

from pydantic import BaseModel, Field, field_validator


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server."""

    command: list[str] = Field(..., description="Command to run the server")
    args: list[str] | None = Field(default=None, description="Additional arguments")
    env: dict[str, str] | None = Field(default=None, description="Environment variables")

    @field_validator("command")
    @classmethod
    def validate_command(cls, v):
        if not v or not v[0]:
            raise ValueError("Command cannot be empty")
        return v


class MCPClientConfig(BaseModel):
    """Configuration for an MCP client."""

    name: str = Field(..., description="Display name of the client")
    description: str = Field(default="", description="Description of the client")
    config_type: str = Field(default="file", description="Type of configuration (file or cli)")
    paths: dict[str, str] | None = Field(default=None, description="Platform-specific config paths")
    fallback_paths: dict[str, str] | None = Field(default=None, description="Fallback config paths")
    cli_commands: dict[str, str] | None = Field(
        default=None, description="CLI commands for management"
    )

    @field_validator("config_type")
    @classmethod
    def validate_config_type(cls, v):
        if v not in ["file", "cli"]:
            raise ValueError("config_type must be 'file' or 'cli'")
        return v


class LocationConfig(BaseModel):
    """Configuration for a client location."""

    path: str = Field(..., description="Path to the configuration file or CLI identifier")
    name: str = Field(..., description="Display name for the location")
    type: str = Field(default="manual", description="Type of location (auto or manual)")
    config_type: str = Field(default="file", description="Type of configuration")
    client_name: str | None = Field(default=None, description="Name of the client")
    description: str | None = Field(default=None, description="Description of the location")


class GlobalConfig(BaseModel):
    """Global configuration structure."""

    mcpServers: dict[str, MCPServerConfig] = Field(  # noqa: N815
        default_factory=dict, description="MCP server configurations"
    )


class ClientDefinitions(BaseModel):
    """Client definitions structure."""

    clients: dict[str, MCPClientConfig] = Field(
        default_factory=dict, description="Client configurations"
    )


class LocationsConfig(BaseModel):
    """Locations configuration structure."""

    locations: list[LocationConfig] = Field(
        default_factory=list, description="List of client locations"
    )
