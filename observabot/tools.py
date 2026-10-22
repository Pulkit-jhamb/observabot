"""Read-only observability tools shared by the Claude agent (Slack) and the MCP server.

Each tool returns a plain, JSON-serialisable dict so both callers can present it
however they like.
"""

import json
from dataclasses import asdict

from . import runbooks as runbook_store
from .alertmanager import AlertmanagerClient
from .config import Settings
from .prometheus import PrometheusClient, ServiceHealth


class Observability:
    """Holds the clients and loaded runbooks so they are created once per process."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.prometheus = PrometheusClient(settings.prometheus_url)
        self.alertmanager = AlertmanagerClient(settings.alertmanager_url)
        self.runbooks = runbook_store.load_runbooks(settings.runbook_dir)

    def query_prometheus(self, promql: str) -> dict:
        result = self.prometheus.instant_query(promql)
        return {"query": promql, "series": result[:50], "series_count": len(result)}

    def list_services(self) -> dict:
        return {"services": self.prometheus.list_services()}

    def service_health(self, service: str) -> dict:
        health: ServiceHealth = self.prometheus.service_health(service)
        return asdict(health)

    def get_firing_alerts(self, service: str | None = None) -> dict:
        alerts = self.alertmanager.firing_alerts(service)
        return {"service": service, "firing_count": len(alerts), "alerts": alerts}

    def lookup_runbook(self, query: str) -> dict:
        matches = runbook_store.search_runbooks(self.runbooks, query)
        return {
            "query": query,
            "matches": [
                {"slug": rb.slug, "title": rb.title, "content": runbook_store.excerpt(rb)}
                for rb in matches
            ],
        }


# JSON schemas for the Anthropic Messages API `tools` parameter.
TOOL_SCHEMAS = [
    {
        "name": "list_services",
        "description": "List every monitored service and whether its scrape target is up.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "service_health",
        "description": (
            "Get request rate (req/s), 5xx error ratio and p95 latency (seconds) for one service "
            "over the last 5 minutes. The service name is the Prometheus `job` label."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string", "description": "Service name, e.g. 'checkout'."}},
            "required": ["service"],
        },
    },
    {
        "name": "get_firing_alerts",
        "description": "List currently firing alerts, optionally filtered to one service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Optional service name to filter by."},
            },
        },
    },
    {
        "name": "query_prometheus",
        "description": (
            "Run an arbitrary read-only PromQL instant query. Prefer service_health for common questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"promql": {"type": "string", "description": "A PromQL expression."}},
            "required": ["promql"],
        },
    },
    {
        "name": "lookup_runbook",
        "description": (
            "Search the team's runbooks by keyword (e.g. an alert name or symptom) and return the "
            "best matches with their steps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Keywords to search for."}},
            "required": ["query"],
        },
    },
]


def dispatch(obs: Observability, name: str, arguments: dict) -> dict:
    """Run a tool by name. Raises KeyError for unknown tools and TypeError for bad arguments."""
    handlers = {
        "list_services": lambda: obs.list_services(),
        "service_health": lambda: obs.service_health(arguments["service"]),
        "get_firing_alerts": lambda: obs.get_firing_alerts(arguments.get("service")),
        "query_prometheus": lambda: obs.query_prometheus(arguments["promql"]),
        "lookup_runbook": lambda: obs.lookup_runbook(arguments["query"]),
    }
    if name not in handlers:
        raise KeyError(name)
    return handlers[name]()


def to_text(result: dict) -> str:
    return json.dumps(result, indent=2, default=str)
