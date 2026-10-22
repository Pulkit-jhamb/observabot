"""Read-only client for Alertmanager's v2 API."""

import httpx


class AlertmanagerError(RuntimeError):
    pass


class AlertmanagerClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def firing_alerts(self, service: str | None = None) -> list[dict]:
        """Active, non-silenced alerts, optionally limited to one service (the `job` label)."""
        try:
            resp = self._client.get(
                f"{self.base_url}/api/v2/alerts",
                params={"active": "true", "silenced": "false", "inhibited": "false"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AlertmanagerError(f"Alertmanager request failed: {exc}") from exc

        alerts = []
        for item in resp.json():
            labels = item.get("labels", {})
            if item.get("status", {}).get("state") != "active":
                continue
            if service and labels.get("job") != service:
                continue
            alerts.append(
                {
                    "alertname": labels.get("alertname", "unknown"),
                    "service": labels.get("job", "unknown"),
                    "severity": labels.get("severity", "unknown"),
                    "summary": item.get("annotations", {}).get("summary", ""),
                    "runbook": item.get("annotations", {}).get("runbook", ""),
                    "starts_at": item.get("startsAt", ""),
                }
            )
        return alerts
