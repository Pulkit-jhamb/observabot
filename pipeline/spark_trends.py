"""Spark job: turns daily health snapshots into per-service daily trends.

Reads   <snapshot_dir>/dt=*/health.jsonl   (written by pipeline.snapshot)
Writes  <output_dir>/service_trends.csv    one row per service per day

Run from the command line:
    python -m pipeline.spark_trends --snapshots data/snapshots --output data/trends
"""

import argparse
import os
import shutil
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    StringType,
    StructField,
    StructType,
)

SNAPSHOT_SCHEMA = StructType(
    [
        StructField("snapshot_time", StringType(), False),
        StructField("service", StringType(), False),
        StructField("request_rate", DoubleType(), True),
        StructField("error_ratio", DoubleType(), True),
        StructField("p95_latency_s", DoubleType(), True),
        StructField("up", BooleanType(), True),
    ]
)


def build_session(app_name: str = "observabot-trends") -> SparkSession:
    spark = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def read_snapshots(spark: SparkSession, snapshot_dir: str) -> DataFrame:
    # The dt=YYYY-MM-DD directory name becomes a `dt` column via partition discovery.
    # `basePath` keeps the partition column even though we read the files directly.
    return (
        spark.read.schema(SNAPSHOT_SCHEMA)
        .option("basePath", snapshot_dir)
        .json(f"{snapshot_dir}/dt=*/health.jsonl")
        .withColumn("dt", F.regexp_extract(F.col("_metadata.file_path"), r"dt=([0-9-]+)", 1))
    )


def daily_trends(snapshots: DataFrame) -> DataFrame:
    """Aggregate snapshots into one row per (dt, service)."""
    return (
        snapshots.groupBy("dt", "service")
        .agg(
            F.count("*").alias("snapshots"),
            F.round(F.avg("request_rate"), 3).alias("avg_request_rate"),
            F.round(F.avg("error_ratio") * 100, 3).alias("avg_error_pct"),
            F.round(F.max("error_ratio") * 100, 3).alias("max_error_pct"),
            F.round(F.max("p95_latency_s") * 1000, 1).alias("max_p95_ms"),
            F.round(F.avg(F.when(F.col("up"), 0.0).otherwise(1.0)) * 100, 1).alias("downtime_pct"),
        )
        .orderBy("service", "dt")
    )


def write_csv(df: DataFrame, output_dir: str) -> Path:
    """Write a single CSV file at <output_dir>/service_trends.csv."""
    out = Path(output_dir)
    staging = out / "_staging"
    if staging.exists():
        shutil.rmtree(staging)
    df.coalesce(1).write.mode("overwrite").option("header", True).csv(str(staging))

    part = next(staging.glob("part-*.csv"))
    final = out / "service_trends.csv"
    shutil.move(str(part), final)
    shutil.rmtree(staging)
    return final


def run(snapshot_dir: str, output_dir: str, spark: SparkSession | None = None) -> Path:
    owns_session = spark is None
    spark = spark or build_session()
    try:
        trends = daily_trends(read_snapshots(spark, snapshot_dir))
        return write_csv(trends, output_dir)
    finally:
        if owns_session:
            spark.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshots", default=os.getenv("SNAPSHOT_DIR", "data/snapshots"))
    parser.add_argument("--output", default=os.getenv("TRENDS_DIR", "data/trends"))
    args = parser.parse_args()

    path = run(args.snapshots, args.output)
    print(f"wrote trends to {path}")


if __name__ == "__main__":
    main()
