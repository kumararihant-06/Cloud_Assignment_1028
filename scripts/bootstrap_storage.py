#!/usr/bin/env python3
"""Create assignment buckets and upload the provided command pool."""

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
COMMANDS_PATH = ROOT / "data" / "commands_pool.jsonl"
BUCKETS = ("datasets", "models")


def kubernetes_credentials() -> tuple[str, str]:
    raw = subprocess.check_output(
        [
            "kubectl",
            "-n",
            "data",
            "get",
            "secret",
            "s3-credentials",
            "-o",
            "json",
        ],
        text=True,
    )
    data = json.loads(raw)["data"]
    decode = lambda value: base64.b64decode(value).decode("utf-8")
    return decode(data["access-key"]), decode(data["secret-key"])


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        print(f"Bucket already exists: {bucket}")
    except ClientError as error:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status not in (403, 404):
            raise
        client.create_bucket(Bucket=bucket)
        print(f"Created bucket: {bucket}")


def main() -> None:
    access_key, secret_key = kubernetes_credentials()
    endpoint = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    for bucket in BUCKETS:
        ensure_bucket(client, bucket)

    client.upload_file(str(COMMANDS_PATH), "datasets", "commands_pool.jsonl")
    metadata = client.head_object(Bucket="datasets", Key="commands_pool.jsonl")
    checksum = hashlib.sha256(COMMANDS_PATH.read_bytes()).hexdigest()
    line_count = sum(1 for line in COMMANDS_PATH.open(encoding="utf-8") if line.strip())
    print(
        json.dumps(
            {
                "bucket": "datasets",
                "key": "commands_pool.jsonl",
                "bytes": metadata["ContentLength"],
                "records": line_count,
                "sha256": checksum,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

