"""Daily service-health pipeline.

    collect_snapshot  ->  spark_trends

1. Snapshot every service's health from Prometheus into data/snapshots/dt=<date>/health.jsonl
2. Run the Spark job that aggregates all snapshots into data/trends/service_trends.csv

Set PROJECT_DIR to the ObservaBot checkout if Airflow runs from another working directory.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", Path(__file__).resolve().parents[2]))
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", str(PROJECT_DIR / "data" / "snapshots"))
TRENDS_DIR = os.getenv("TRENDS_DIR", str(PROJECT_DIR / "data" / "trends"))


@dag(
    dag_id="service_health_daily",
    description="Snapshot service health from Prometheus, then aggregate daily trends with Spark.",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["observabot", "spark"],
)
def service_health_daily():
    @task
    def collect_snapshot(ds: str | None = None) -> str:
        from pipeline.snapshot import collect, write_snapshot
        from observabot.config import Settings
        from observabot.prometheus import PrometheusClient

        client = PrometheusClient(Settings.from_env().prometheus_url)
        records = collect(client, datetime.utcnow())
        path = write_snapshot(records, SNAPSHOT_DIR, ds)
        return str(path)

    spark_trends = BashOperator(
        task_id="spark_trends",
        bash_command=(
            f'cd "{PROJECT_DIR}" && "{sys.executable}" -m pipeline.spark_trends '
            f'--snapshots "{SNAPSHOT_DIR}" --output "{TRENDS_DIR}"'
        ),
    )

    collect_snapshot() >> spark_trends


service_health_daily()
