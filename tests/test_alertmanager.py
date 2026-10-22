import httpx

from observabot.alertmanager import AlertmanagerClient

ALERTS = [
    {
        "labels": {"alertname": "HighErrorRate", "job": "checkout", "severity": "critical"},
        "annotations": {"summary": "checkout 5xx above 5%", "runbook": "runbooks/high-error-rate.md"},
        "startsAt": "2026-10-23T10:00:00Z",
        "status": {"state": "active"},
    },
    {
        "labels": {"alertname": "ServiceDown", "job": "payments", "severity": "critical"},
        "annotations": {"summary": "payments is down"},
        "startsAt": "2026-10-23T10:05:00Z",
        "status": {"state": "suppressed"},
    },
    {
        "labels": {"alertname": "HighLatencyP95", "job": "catalog", "severity": "warning"},
        "annotations": {},
        "startsAt": "2026-10-23T10:07:00Z",
        "status": {"state": "active"},
    },
]


def client():
    def handler(request):
        assert request.url.params["active"] == "true"
        return httpx.Response(200, json=ALERTS)

    return AlertmanagerClient("http://am", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_returns_only_active_alerts():
    names = [a["alertname"] for a in client().firing_alerts()]
    assert names == ["HighErrorRate", "HighLatencyP95"]


def test_filters_by_service():
    alerts = client().firing_alerts("checkout")
    assert [a["alertname"] for a in alerts] == ["HighErrorRate"]
    assert alerts[0]["runbook"] == "runbooks/high-error-rate.md"


def test_missing_annotations_default_to_empty_strings():
    alert = client().firing_alerts("catalog")[0]
    assert alert["summary"] == ""
    assert alert["runbook"] == ""
