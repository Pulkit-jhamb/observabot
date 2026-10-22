# High Latency (HighLatencyP95)

Alert: `HighLatencyP95` fires when the p95 request latency for a service stays above 500ms for 3 minutes.

## Triage
1. Use `service_health` to see the p95 latency and request rate. A rate spike with rising latency suggests saturation.
2. Check CPU and memory of the service's containers; a throttled container adds latency with no errors.
3. Check downstream dependency latency (database query time, external API calls).

## Mitigation
- Saturation: scale out replicas or raise the concurrency limit, then re-check p95.
- Slow dependency: add a timeout and fallback on the slow call, and page the dependency owner.
- Recent deploy: roll back if p95 started rising at the time of the release.

## Verify recovery
- p95 latency below 300ms for 10 minutes.
