#!/usr/bin/env python3
"""Label one deterministic shard of commands with the fixed Ollama teacher."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from worker.common import required_env, s3_client


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = Path(os.environ.get("PROMPT_PATH", ROOT / "prompts/teacher_prompt.txt"))
MODEL = os.environ.get("OLLAMA_MODEL", "phi3.5")
OLLAMA_URL = os.environ.get(
    "OLLAMA_URL", "http://host.k3d.internal:11434/api/generate"
)
BUCKET = os.environ.get("DATASET_BUCKET", "datasets")
INPUT_KEY = os.environ.get("INPUT_KEY", "commands_pool.jsonl")
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "teacher")
CHECKPOINT_EVERY = int(os.environ.get("CHECKPOINT_EVERY", "10"))
REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "600"))
MAX_RETRIES = int(os.environ.get("OLLAMA_RETRIES", "3"))


def shard_records(
    records: Iterable[dict], shard_index: int, shard_count: int
) -> Iterable[dict]:
    if shard_count < 1:
        raise ValueError("SHARD_COUNT must be at least 1")
    if not 0 <= shard_index < shard_count:
        raise ValueError("SHARD_INDEX must satisfy 0 <= SHARD_INDEX < SHARD_COUNT")
    for line_number, record in enumerate(records):
        if line_number % shard_count == shard_index:
            yield record


def ollama_payload(prompt: str) -> bytes:
    return json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "seed": 42},
        }
    ).encode("utf-8")


def teacher_reply(prompt: str) -> str:
    request = Request(
        OLLAMA_URL,
        data=ollama_payload(prompt),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                body = json.load(response)
            raw = body.get("response")
            if not isinstance(raw, str):
                raise RuntimeError("Ollama response did not contain a text response field")
            return raw
        except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Teacher request failed after {MAX_RETRIES} attempts"
                ) from error
            delay = 2 ** (attempt - 1)
            print(f"Teacher request failed; retrying in {delay}s (attempt {attempt}).")
            time.sleep(delay)
    raise AssertionError("unreachable")


def parse_jsonl(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line]


def encode_jsonl(records: Iterable[dict]) -> bytes:
    text = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    return text.encode("utf-8")


def load_existing(client, output_key: str) -> list[dict]:
    try:
        body = client.get_object(Bucket=BUCKET, Key=output_key)["Body"].read()
    except client.exceptions.NoSuchKey:
        return []
    return parse_jsonl(body)


def main() -> None:
    shard_index = int(required_env("SHARD_INDEX"))
    shard_count = int(required_env("SHARD_COUNT"))
    output_key = f"{OUTPUT_PREFIX}/shard-{shard_index}.jsonl"
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    if "{{COMMAND}}" not in prompt_template:
        raise RuntimeError("Teacher prompt must contain the {{COMMAND}} placeholder")

    client = s3_client()
    source = client.get_object(Bucket=BUCKET, Key=INPUT_KEY)["Body"].read()
    commands = parse_jsonl(source)
    selected = list(shard_records(commands, shard_index, shard_count))
    output = load_existing(client, output_key)
    completed_ids = {record["id"] for record in output}
    if len(completed_ids) != len(output):
        raise RuntimeError(f"Existing output contains duplicate ids: {output_key}")

    print(
        f"Shard {shard_index}/{shard_count}: {len(selected)} selected, "
        f"{len(output)} already complete."
    )
    new_since_checkpoint = 0
    for record in selected:
        if record["id"] in completed_ids:
            continue
        raw = teacher_reply(prompt_template.replace("{{COMMAND}}", record["text"]))
        output.append(
            {"id": record["id"], "text": record["text"], "teacher_raw": raw}
        )
        completed_ids.add(record["id"])
        new_since_checkpoint += 1
        if new_since_checkpoint >= CHECKPOINT_EVERY:
            client.put_object(Bucket=BUCKET, Key=output_key, Body=encode_jsonl(output))
            print(f"Shard {shard_index}: checkpointed {len(output)}/{len(selected)}.")
            new_since_checkpoint = 0

    expected_ids = {record["id"] for record in selected}
    if completed_ids != expected_ids:
        missing = sorted(expected_ids - completed_ids)
        unexpected = sorted(completed_ids - expected_ids)
        raise RuntimeError(f"Shard coverage mismatch; missing={missing}, unexpected={unexpected}")
    client.put_object(Bucket=BUCKET, Key=output_key, Body=encode_jsonl(output))
    print(f"Shard {shard_index}: completed {len(output)} records at s3://{BUCKET}/{output_key}")


if __name__ == "__main__":
    main()

