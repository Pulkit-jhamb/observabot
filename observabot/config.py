"""Runtime configuration, read from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    prometheus_url: str
    alertmanager_url: str
    runbook_dir: str
    claude_model: str
    slack_bot_token: str
    slack_app_token: str
    anthropic_api_key: str
    mcp_host: str
    mcp_port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            prometheus_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/"),
            alertmanager_url=os.getenv("ALERTMANAGER_URL", "http://localhost:9093").rstrip("/"),
            runbook_dir=os.getenv("RUNBOOK_DIR", "runbooks"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
            slack_bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
            slack_app_token=os.getenv("SLACK_APP_TOKEN", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.getenv("MCP_PORT", "8001")),
        )
