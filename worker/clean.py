#!/usr/bin/env python3
"""Validate, de-duplicate, order, and checksum raw teacher shard outputs."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from worker.common import s3_client
from worker.label import BUCKET, INPUT_KEY, OUTPUT_PREFIX, encode_jsonl, parse_jsonl


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "data" / "schema.json").read_text(encoding="utf-8"))
EXPECTED_KEYS = set(SCHEMA["keys"])
VALID_INTENTS = set(SCHEMA["intents"])
SHARD_KEY = re.compile(rf"^{re.escape(OUTPUT_PREFIX)}/shard-\d+\.jsonl$")


def rejection_reason(record: dict) -> str | None:
    try:
        reply = json.loads(record["teacher_raw"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return "invalid_json"
    if not isinstance(reply, dict):
        return "invalid_json"
    if set(reply) != EXPECTED_KEYS:
        return "wrong_keys"
    if not isinstance(reply["intent"], str) or reply["intent"] not in VALID_INTENTS:
        return "invalid_intent"
    command = record["text"]
    for slot in ("date", "time", "place"):
        value = reply[slot]
        if value is not None and (
            not isinstance(value, str) or not value or value not in command
        ):
            return "invalid_slot"
    return None


def verify_coverage(commands: list[dict], shards: list[dict]) -> None:
    expected = [record["id"] for record in commands]
    actual = [record.get("id") for record in shards]
    counts = Counter(actual)
    duplicates = sorted(record_id for record_id, count in counts.items() if count > 1)
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    if duplicates or missing or unexpected or len(actual) != len(expected):
        raise ValueError(
            "Shard coverage must contain every command id exactly once; "
            f"missing={missing}, duplicate_ids={duplicates}, unexpected={unexpected}"
        )


def clean_records(records: Iterable[dict]) -> tuple[list[dict], dict[str, int]]:
    ordered = sorted(records, key=lambda record: record["id"])
    counts = {
        "input_records": len(ordered),
        "invalid_json": 0,
        "wrong_keys": 0,
        "invalid_intent": 0,
        "invalid_slot": 0,
        "duplicates": 0,
        "records_kept": 0,
    }
    valid: list[dict] = []
    for record in ordered:
        reason = rejection_reason(record)
        if reason:
            counts[reason] += 1
        else:
            valid.append(record)

    kept: list[dict] = []
    seen_commands: set[str] = set()
    for record in valid:
        if record["text"] in seen_commands:
            counts["duplicates"] += 1
            continue
        seen_commands.add(record["text"])
        kept.append(record)
    counts["records_kept"] = len(kept)

    accounted = sum(
        counts[key]
        for key in (
            "invalid_json",
            "wrong_keys",
            "invalid_intent",
            "invalid_slot",
            "duplicates",
            "records_kept",
        )
    )
    if accounted != counts["input_records"]:
        raise AssertionError("Cleaning counts do not balance")
    return kept, counts


def list_shard_keys(client) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{OUTPUT_PREFIX}/"):
        keys.extend(
            item["Key"] for item in page.get("Contents", []) if SHARD_KEY.match(item["Key"])
        )
    return sorted(keys)


def main() -> None:
    client = s3_client()
    commands = parse_jsonl(
        client.get_object(Bucket=BUCKET, Key=INPUT_KEY)["Body"].read()
    )
    shard_keys = list_shard_keys(client)
    if len(shard_keys) < 2:
        raise RuntimeError("At least two teacher shard objects are required")
    records: list[dict] = []
    for key in shard_keys:
        records.extend(
            parse_jsonl(client.get_object(Bucket=BUCKET, Key=key)["Body"].read())
        )
    verify_coverage(commands, records)

    cleaned, counts = clean_records(records)
    train_data = encode_jsonl(cleaned)
    digest = hashlib.sha256(train_data).hexdigest()
    report = {"shards": shard_keys, **counts, "sha256": digest}
    client.put_object(Bucket=BUCKET, Key="v1/train.jsonl", Body=train_data)
    client.put_object(
        Bucket=BUCKET, Key="v1/train.sha256", Body=f"{digest}  train.jsonl\n".encode()
    )
    client.put_object(
        Bucket=BUCKET,
        Key="v1/cleaning_report.json",
        Body=(json.dumps(report, indent=2) + "\n").encode(),
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

