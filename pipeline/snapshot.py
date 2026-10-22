"""Daily health snapshot: writes one JSON line per service from Prometheus.

Run from the command line:
    python -m pipeline.snapshot --date 2026-10-23 --out data/snapshots
The output lands in <out>/dt=<date>/health.jsonl, which is the layout the Spark job reads.
"""

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from observabot.config import Settings
from observabot.prometheus import PrometheusClient


def collect(client: PrometheusClient, snapshot_time: datetime) -> list[dict]:
    """Return one health record per service that Prometheus knows about."""
    records = []
    for job in sorted({s["service"] for s in client.list_services()}):
        health = asdict(client.service_health(job))
        records.append(
            {
                "snapshot_time": snapshot_time.isoformat(),
                "service": job,
                "request_rate": health["request_rate"],
                "error_ratio": health["error_ratio"],
                "p95_latency_s": health["p95_latency_s"],
                "up": health["up"] == 1.0 if health["up"] is not None else False,
            }
        )
    return records


def write_snapshot(records: list[dict], out_dir: str | Path, date: str) -> Path:
    path = Path(out_dir) / f"dt={date}" / "health.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--out", default=os.getenv("SNAPSHOT_DIR", "data/snapshots"))
    args = parser.parse_args()

    settings = Settings.from_env()
    client = PrometheusClient(settings.prometheus_url)
    records = collect(client, datetime.now(timezone.utc))
    path = write_snapshot(records, args.out, args.date)
    print(f"wrote {len(records)} service records to {path}")


if __name__ == "__main__":
    main()
