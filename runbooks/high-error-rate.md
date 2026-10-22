# High Error Rate (HighErrorRate)

Alert: `HighErrorRate` fires when the 5xx ratio for a service stays above 5% for 2 minutes.

## Triage
1. Ask ObservaBot for `service_health` on the affected service to confirm the current error ratio and request rate.
2. Check whether the error ratio started with a deploy: compare the alert start time with the latest release.
3. Check upstream dependencies (database, payment provider, cache) for their own alerts.

## Mitigation
- If the error started with a deploy, roll back to the previous image and watch the error ratio for 5 minutes.
- If a dependency is failing, enable the circuit breaker or fallback for that dependency and page its owning team.
- If traffic spiked, scale out the service replicas before investigating further.

## Verify recovery
- Error ratio is back below 1% for 10 minutes and the alert has resolved in Alertmanager.

## Escalate
- Still above 5% after 15 minutes with no clear cause: page the service owner and open an incident.
