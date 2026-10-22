"""Thin read-only client for the Prometheus HTTP API, plus service-health helpers."""

from dataclasses import dataclass

import httpx


class PrometheusError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceHealth:
    service: str
    request_rate: float | None  # requests per second over 5m
    error_ratio: float | None  # fraction of 5xx responses over 5m
    p95_latency_s: float | None  # seconds, from the request-duration histogram
    up: float | None  # 1 when the scrape target is healthy


def _format_value(raw: str) -> float | None:
    if raw == "NaN":
        return None
    return float(raw)


class PrometheusClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def instant_query(self, promql: str) -> list[dict]:
        """Run an instant query and return the raw result vector."""
        try:
            resp = self._client.get(f"{self.base_url}/api/v1/query", params={"query": promql})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise PrometheusError(f"Prometheus request failed: {exc}") from exc

        body = resp.json()
        if body.get("status") != "success":
            raise PrometheusError(body.get("error", "unknown Prometheus error"))
        return body["data"]["result"]

    def scalar(self, promql: str) -> float | None:
        """Return the single value of a query, or None when it has no data."""
        result = self.instant_query(promql)
        if not result:
            return None
        return _format_value(result[0]["value"][1])

    def list_services(self) -> list[dict]:
        """Every scrape job (one per service) with its health status."""
        services = []
        for series in self.instant_query("up"):
            labels = series["metric"]
            services.append(
                {
                    "service": labels.get("job", "unknown"),
                    "instance": labels.get("instance", "unknown"),
                    "up": _format_value(series["value"][1]) == 1.0,
                }
            )
        return sorted(services, key=lambda s: (s["service"], s["instance"]))

    def service_health(self, service: str) -> ServiceHealth:
        """Request rate, error ratio, p95 latency and scrape status for one service."""
        selector = f'job="{_escape_label(service)}"'
        return ServiceHealth(
            service=service,
            request_rate=self.scalar(f"sum(rate(http_requests_total{{{selector}}}[5m]))"),
            error_ratio=self._error_ratio(selector),
            p95_latency_s=self.scalar(
                "histogram_quantile(0.95, sum by (le) "
                f"(rate(http_request_duration_seconds_bucket{{{selector}}}[5m])))"
            ),
            up=self.scalar(f"max(up{{{selector}}})"),
        )

    def _error_ratio(self, selector: str) -> float | None:
        total = self.scalar(f"sum(rate(http_requests_total{{{selector}}}[5m]))")
        if not total:
            return None
        errors = self.scalar(f'sum(rate(http_requests_total{{{selector},status=~"5.."}}[5m]))') or 0.0
        return errors / total


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
