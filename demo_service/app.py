"""A small Flask service instrumented with Prometheus metrics, used as the monitored target.

Metrics:
  http_requests_total{method,endpoint,status}          counter
  http_request_duration_seconds{method,endpoint}       histogram

Chaos controls (for demos and alert testing) are runtime-adjustable:
  POST /chaos?error_rate=0.3&latency_ms=800   inject 5xx responses and extra latency
  POST /chaos?error_rate=0&latency_ms=0       reset
"""

import os
import random
import time

from flask import Flask, Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

chaos = {
    "error_rate": float(os.getenv("ERROR_RATE", "0")),
    "latency_ms": float(os.getenv("LATENCY_MS", "0")),
}


@app.before_request
def start_timer():
    request.environ["obs.start"] = time.perf_counter()
    if request.endpoint not in ("metrics", "healthz", "chaos") and chaos["latency_ms"] > 0:
        time.sleep(chaos["latency_ms"] / 1000)


@app.after_request
def record(response):
    start = request.environ.get("obs.start")
    endpoint = request.endpoint or "unknown"
    if start is not None and endpoint not in ("metrics", "healthz"):
        LATENCY.labels(request.method, endpoint).observe(time.perf_counter() - start)
    REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
    return response


@app.get("/")
def index():
    return jsonify(service=os.getenv("SERVICE_NAME", "demo"), status="ok")


@app.get("/api/items")
def items():
    if random.random() < chaos["error_rate"]:
        return jsonify(error="injected failure"), 500
    return jsonify(items=[{"id": i, "name": f"item-{i}"} for i in range(5)])


@app.post("/chaos")
def set_chaos():
    chaos["error_rate"] = min(max(float(request.args.get("error_rate", chaos["error_rate"])), 0.0), 1.0)
    chaos["latency_ms"] = max(float(request.args.get("latency_ms", chaos["latency_ms"])), 0.0)
    return jsonify(chaos)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
