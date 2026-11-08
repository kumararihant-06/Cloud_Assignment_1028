#!/usr/bin/env python3
"""Calculate cost per 1,000 requests from the supplied rate card and Locust CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def aggregated_stats(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    try:
        return next(row for row in rows if row["Name"] == "Aggregated")
    except StopIteration as error:
        raise RuntimeError(f"No Aggregated row in {path}") from error


def calculate(rate_card: dict, stats: dict[str, str], replicas: int) -> dict:
    if replicas < 1:
        raise ValueError("replicas must be positive")
    requests = int(stats["Request Count"])
    failures = int(stats["Failure Count"])
    requests_per_second = float(stats["Requests/s"])
    if requests < 1 or requests_per_second <= 0 or failures >= requests:
        raise ValueError("load statistics need positive successful throughput")

    cpu_limit = 2.0
    memory_limit_gib = 1.0
    per_replica_hour = (
        cpu_limit * float(rate_card["vcpu_hour"])
        + memory_limit_gib * float(rate_card["gib_memory_hour"])
    )
    hourly_cost = replicas * per_replica_hour
    attempted_per_hour = requests_per_second * 3600
    success_ratio = (requests - failures) / requests
    successful_per_hour = attempted_per_hour * success_ratio

    return {
        "currency": rate_card["currency"],
        "replicas": replicas,
        "cpu_limit_per_replica": cpu_limit,
        "memory_limit_gib_per_replica": memory_limit_gib,
        "cost_per_replica_hour": round(per_replica_hour, 4),
        "total_cost_per_hour": round(hourly_cost, 4),
        "measured_requests_per_second": round(requests_per_second, 6),
        "measured_success_ratio": round(success_ratio, 6),
        "attempted_requests_per_hour": round(attempted_per_hour, 4),
        "successful_requests_per_hour": round(successful_per_hour, 4),
        "cost_per_1000_attempted_requests": round(
            hourly_cost / attempted_per_hour * 1000, 4
        ),
        "cost_per_1000_successful_requests": round(
            hourly_cost / successful_per_hour * 1000, 4
        ),
        "billing_rule": rate_card["billing_rule"],
        "assumption": (
            "Steady-state cost uses the HPA maximum replica count because the "
            "measured four-user workload scaled to that count."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rate-card", type=Path, default=ROOT / "data" / "rate_card.json"
    )
    parser.add_argument(
        "--stats", type=Path, default=ROOT / "results" / "loadtest_optimized_stats.csv"
    )
    parser.add_argument("--replicas", type=int, default=4)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "results" / "cost.json"
    )
    args = parser.parse_args()
    rate_card = json.loads(args.rate_card.read_text(encoding="utf-8"))
    report = calculate(rate_card, aggregated_stats(args.stats), args.replicas)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
