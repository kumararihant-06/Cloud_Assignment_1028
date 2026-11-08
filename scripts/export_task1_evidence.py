#!/usr/bin/env python3
"""Export Task 1 coverage, checksums, Kubernetes state, and logs to results/."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from training.storage import client as s3_client


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def jsonl(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line]


def kubectl(*arguments: str) -> str:
    return subprocess.check_output(["kubectl", *arguments], text=True)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    storage = s3_client()
    commands = jsonl(
        storage.get_object(Bucket="datasets", Key="commands_pool.jsonl")["Body"].read()
    )
    shard_records = {}
    for index in (0, 1):
        key = f"teacher/shard-{index}.jsonl"
        shard_records[key] = jsonl(
            storage.get_object(Bucket="datasets", Key=key)["Body"].read()
        )

    expected_ids = {record["id"] for record in commands}
    all_ids = [
        record["id"] for records in shard_records.values() for record in records
    ]
    id_counts = Counter(all_ids)
    coverage = {
        "expected_records": len(commands),
        "shards": {key: len(records) for key, records in shard_records.items()},
        "total_shard_records": len(all_ids),
        "unique_ids": len(id_counts),
        "missing_ids": sorted(expected_ids - set(all_ids)),
        "unexpected_ids": sorted(set(all_ids) - expected_ids),
        "duplicate_ids": sorted(
            record_id for record_id, count in id_counts.items() if count > 1
        ),
        "coverage_valid": set(all_ids) == expected_ids
        and len(all_ids) == len(expected_ids),
    }
    (RESULTS / "task1_shard_coverage.json").write_text(
        json.dumps(coverage, indent=2) + "\n", encoding="utf-8"
    )
    if not coverage["coverage_valid"]:
        raise RuntimeError("Teacher shard coverage is not exact")

    report = storage.get_object(
        Bucket="datasets", Key="v1/cleaning_report.json"
    )["Body"].read()
    checksum = storage.get_object(
        Bucket="datasets", Key="v1/train.sha256"
    )["Body"].read()
    train_data = storage.get_object(Bucket="datasets", Key="v1/train.jsonl")[
        "Body"
    ].read()
    expected_digest = checksum.decode("utf-8").split()[0]
    actual_digest = hashlib.sha256(train_data).hexdigest()
    if expected_digest != actual_digest:
        raise RuntimeError("Downloaded training dataset checksum does not match")
    (RESULTS / "task1_cleaning_report.json").write_bytes(report)
    (RESULTS / "task1_train.sha256").write_bytes(checksum)

    job_state = kubectl(
        "-n", "pipeline", "get", "jobs,pods", "-o", "wide"
    )
    (RESULTS / "task1_kubernetes_state.txt").write_text(
        job_state, encoding="utf-8"
    )
    for name in ("teacher-worker-0", "teacher-worker-1", "clean-teacher-data"):
        log = kubectl("-n", "pipeline", "logs", f"job/{name}")
        (RESULTS / f"task1_{name}.log").write_text(log, encoding="utf-8")

    print(json.dumps(coverage, indent=2))
    print(f"Verified train.jsonl SHA-256: {actual_digest}")


if __name__ == "__main__":
    main()

