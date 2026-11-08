#!/usr/bin/env python3
"""Create or update the local Kubernetes S3 Secret without writing it to disk."""

import base64
import json
import os
import secrets
import subprocess


def encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def main() -> None:
    configured_access_key = os.environ.get("S3_ACCESS_KEY")
    configured_secret_key = os.environ.get("S3_SECRET_KEY")
    if not configured_access_key and not configured_secret_key:
        existing = subprocess.run(
            ["kubectl", "-n", "data", "get", "secret", "s3-credentials"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if existing.returncode == 0:
            print("Reusing the existing in-cluster S3 Secret.")
            return
    if bool(configured_access_key) != bool(configured_secret_key):
        raise SystemExit("Set both S3_ACCESS_KEY and S3_SECRET_KEY, or neither.")

    access_key = configured_access_key or secrets.token_urlsafe(18)
    secret_key = configured_secret_key or secrets.token_urlsafe(36)

    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "s3-credentials", "namespace": "data"},
        "type": "Opaque",
        "data": {
            "access-key": encoded(access_key),
            "secret-key": encoded(secret_key),
        },
    }
    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest),
        text=True,
        check=True,
    )
    if not configured_access_key:
        print("Generated S3 credentials and stored them only in the Kubernetes Secret.")


if __name__ == "__main__":
    main()

