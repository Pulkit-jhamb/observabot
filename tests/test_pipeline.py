import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from observabot.prometheus import PrometheusClient
from pipeline.snapshot import collect, write_snapshot


def vector(value, labels=None):
    result = [{"metric": labels or {}, "value": [0, value]}] if value is not None else []
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def fake_prometheus():
    def handler(request):
        query = request.url.params["query"]
        if query == "up":
            body = vector("1", {"job": "payments"})
            body["data"]["result"] += vector("0", {"job": "catalog"})["data"]["result"]
            return httpx.Response(200, json=body)
        if 'job="catalog"' in query and "status" in query:
            return httpx.Response(200, json=vector("1"))
        if 'job="catalog"' in query and "histogram" in query:
            return httpx.Response(200, json=vector("0.4"))
        if 'job="catalog"' in query and "rate" in query:
            return httpx.Response(200, json=vector("10"))
        if 'job="payments"' in query and "histogram" in query:
            return httpx.Response(200, json=vector("0.1"))
        if 'job="payments"' in query and "rate" in query:
            return httpx.Response(200, json=vector("20"))
        return httpx.Response(200, json=vector("1"))

    return PrometheusClient("http://prom", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_collect_writes_one_record_per_service():
    records = collect(fake_prometheus(), datetime(2026, 10, 23, tzinfo=timezone.utc))
    by_service = {r["service"]: r for r in records}
    assert set(by_service) == {"catalog", "payments"}
    assert by_service["payments"]["up"] is True
    assert by_service["catalog"]["up"] is True
    assert by_service["payments"]["p95_latency_s"] == pytest.approx(0.1)


def test_write_snapshot_uses_dt_partition(tmp_path):
    path = write_snapshot([{"service": "a"}, {"service": "b"}], tmp_path, "2026-10-23")
    assert path == tmp_path / "dt=2026-10-23" / "health.jsonl"
    lines = path.read_text().splitlines()
    assert [json.loads(line)["service"] for line in lines] == ["a", "b"]


def _use_homebrew_jdk():
    """Point JAVA_HOME at Homebrew's OpenJDK 17 if nothing else is configured. The macOS java stub doesn't count."""
    if os.getenv("JAVA_HOME"):
        return True
    brew_jdk = Path("/opt/homebrew/opt/openjdk@17")
    if brew_jdk.exists():
        os.environ["JAVA_HOME"] = str(brew_jdk)
        return True
    return False


@pytest.mark.skipif(not _use_homebrew_jdk(), reason="needs a JDK for Spark (brew install openjdk@17)")
def test_spark_trends_aggregates_per_service_per_day(tmp_path):
    from pipeline.spark_trends import build_session, run

    snapshots = tmp_path / "snapshots"
    rows_day1 = [
        {"snapshot_time": "t1", "service": "catalog", "request_rate": 10.0, "error_ratio": 0.02, "p95_latency_s": 0.2, "up": True},
        {"snapshot_time": "t2", "service": "catalog", "request_rate": 20.0, "error_ratio": 0.06, "p95_latency_s": 0.6, "up": True},
        {"snapshot_time": "t3", "service": "catalog", "request_rate": 30.0, "error_ratio": 0.0, "p95_latency_s": 0.3, "up": False},
    ]
    rows_day2 = [
        {"snapshot_time": "t4", "service": "catalog", "request_rate": 5.0, "error_ratio": 0.0, "p95_latency_s": 0.1, "up": True},
    ]
    write_snapshot(rows_day1, snapshots, "2026-10-22")
    write_snapshot(rows_day2, snapshots, "2026-10-23")

    spark = build_session("observabot-test")
    try:
        out = run(str(snapshots), str(tmp_path / "trends"), spark=spark)
    finally:
        spark.stop()

    lines = out.read_text().splitlines()
    header = lines[0].split(",")
    rows = [dict(zip(header, line.split(","))) for line in lines[1:]]
    assert [(r["dt"], r["service"]) for r in rows] == [("2026-10-22", "catalog"), ("2026-10-23", "catalog")]

    day1 = rows[0]
    assert day1["snapshots"] == "3"
    assert float(day1["avg_error_pct"]) == pytest.approx(2.667, abs=0.01)
    assert float(day1["max_error_pct"]) == pytest.approx(6.0)
    assert float(day1["max_p95_ms"]) == pytest.approx(600.0)
    assert float(day1["downtime_pct"]) == pytest.approx(33.3, abs=0.1)
    assert float(rows[1]["downtime_pct"]) == pytest.approx(0.0)
