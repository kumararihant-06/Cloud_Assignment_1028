"""S3 access using credentials supplied by environment or Kubernetes Secret."""

import base64
import json
import os
import subprocess
from urllib.parse import urlparse

import boto3
from botocore.config import Config


def credentials() -> tuple[str, str]:
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if bool(access_key) != bool(secret_key):
        raise RuntimeError("Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    if access_key and secret_key:
        return access_key, secret_key

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


def client():
    access_key, secret_key = credentials()
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def split_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")

