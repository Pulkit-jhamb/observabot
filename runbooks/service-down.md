# Service Down (ServiceDown)

Alert: `ServiceDown` fires when Prometheus cannot scrape a service's `/metrics` endpoint for 1 minute.

## Triage
1. Use `list_services` to see which scrape targets are down.
2. Check the container or pod status for the service. A crash loop or OOM kill is the most common cause.
3. Hit the service's `/healthz` endpoint directly from inside the network to confirm it is unreachable.

## Mitigation
- Crash loop: read the last 100 log lines, then roll back if the crash started after a deploy.
- Network issue: confirm DNS resolution and that the service is on the expected network.
- If the service is intentionally stopped (maintenance), silence the alert in Alertmanager with a note.

## Escalate
- Down for more than 5 minutes with no recovery path: page the service owner and start an incident.
