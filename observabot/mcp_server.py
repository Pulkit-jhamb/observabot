"""MCP server exposing the same observability tools to any MCP-compatible client.

Run over stdio for desktop clients (Claude Desktop, Claude Code, ...):
    python -m observabot.mcp_server

Or over streamable HTTP for containers / remote clients:
    python -m observabot.mcp_server --http
"""

import logging
import sys

from mcp.server.mcpserver import MCPServer

from .alertmanager import AlertmanagerError
from .config import Settings
from .prometheus import PrometheusError
from .tools import Observability, to_text

log = logging.getLogger("observabot.mcp")


def _run(call, *args) -> str:
    """Return tool output as text. Backend failures come back as an error payload the client can read."""
    try:
        return to_text(call(*args))
    except (PrometheusError, AlertmanagerError) as exc:
        log.warning("Backend error: %s", exc)
        return to_text({"error": str(exc)})


def build_server(obs: Observability) -> MCPServer:
    mcp = MCPServer(
        name="observabot",
        instructions=(
            "Read-only platform health tools backed by Prometheus, Alertmanager and the team's runbooks."
        ),
    )

    @mcp.tool()
    def list_services() -> str:
        """List every monitored service and whether its scrape target is up."""
        return _run(obs.list_services)

    @mcp.tool()
    def service_health(service: str) -> str:
        """Request rate (req/s), 5xx error ratio and p95 latency (s) for one service over 5 minutes."""
        return _run(obs.service_health, service)

    @mcp.tool()
    def get_firing_alerts(service: str | None = None) -> str:
        """List currently firing alerts, optionally filtered to one service."""
        return _run(obs.get_firing_alerts, service)

    @mcp.tool()
    def query_prometheus(promql: str) -> str:
        """Run a read-only PromQL instant query and return the matching series."""
        return _run(obs.query_prometheus, promql)

    @mcp.tool()
    def lookup_runbook(query: str) -> str:
        """Search runbooks by keyword (alert name or symptom) and return the best matches."""
        return _run(obs.lookup_runbook, query)

    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    settings = Settings.from_env()
    server = build_server(Observability(settings))

    if "--http" in sys.argv:
        log.info("Serving MCP over streamable HTTP on %s:%d", settings.mcp_host, settings.mcp_port)
        server.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
