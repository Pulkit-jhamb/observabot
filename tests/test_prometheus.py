import httpx
import pytest

from observabot.prometheus import PrometheusClient, PrometheusError


def vector(value, labels=None):
    return {"status": "success", "data": {"resultType": "vector", "result": [{"metric": labels or {}, "value": [1700000000, value]}] if value is not None else []}}


def make_client(responses):
    """responses maps a PromQL substring to a JSON body. Unmatched queries return an empty vector."""

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        for needle, body in responses.items():
            if needle in query:
                return httpx.Response(200, json=body)
        return httpx.Response(200, json=vector(None))

    return PrometheusClient("http://prom", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_service_health_computes_error_ratio_from_rates():
    client = make_client(
        {
            'status=~"5.."': vector("2"),
            "http_requests_total{job=\"checkout\"}[5m]))": vector("40"),
            "histogram_quantile": vector("0.25"),
            "up{": vector("1"),
        }
    )

    health = client.service_health("checkout")

    assert health.request_rate == 40.0
    assert health.error_ratio == pytest.approx(0.05)
    assert health.p95_latency_s == 0.25
    assert health.up == 1.0


def test_service_health_without_traffic_reports_none():
    client = make_client({})
    health = client.service_health("idle")
    assert health.request_rate is None
    assert health.error_ratio is None
    assert health.p95_latency_s is None


def test_nan_values_become_none():
    client = make_client({"histogram_quantile": vector("NaN")})
    assert client.service_health("svc").p95_latency_s is None


def test_list_services_reports_up_state():
    body = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"job": "payments", "instance": "payments:8000"}, "value": [0, "1"]},
                {"metric": {"job": "catalog", "instance": "catalog:8000"}, "value": [0, "0"]},
            ],
        },
    }
    client = make_client({"up": body})
    assert client.list_services() == [
        {"service": "catalog", "instance": "catalog:8000", "up": False},
        {"service": "payments", "instance": "payments:8000", "up": True},
    ]


def test_prometheus_error_status_raises():
    client = make_client({"up": {"status": "error", "error": "parse error"}})
    with pytest.raises(PrometheusError, match="parse error"):
        client.list_services()


def test_http_failure_raises_prometheus_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = PrometheusClient("http://prom", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(PrometheusError, match="request failed"):
        client.instant_query("up")


def test_service_name_is_escaped_in_selector():
    seen = []

    def handler(request):
        seen.append(request.url.params["query"])
        return httpx.Response(200, json=vector(None))

    client = PrometheusClient("http://prom", client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.service_health('a"b')
    assert all('job="a\\"b"' in q for q in seen)
