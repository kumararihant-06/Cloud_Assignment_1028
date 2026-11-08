#!/usr/bin/env python3
"""Create or update the local Kubernetes S3 Secret without writing it to disk."""

import base64
import json
import os
import secrets
import subprocess

NAMESPACES = ("data", "pipeline", "app")


def encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def main() -> None:
    configured_access_key = os.environ.get("S3_ACCESS_KEY")
    configured_secret_key = os.environ.get("S3_SECRET_KEY")
    reused = False
    if not configured_access_key and not configured_secret_key:
        existing = subprocess.run(
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
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if existing.returncode == 0:
            secret_data = json.loads(existing.stdout)["data"]
            reused = True
    if bool(configured_access_key) != bool(configured_secret_key):
        raise SystemExit("Set both S3_ACCESS_KEY and S3_SECRET_KEY, or neither.")

    if not reused:
        access_key = configured_access_key or secrets.token_urlsafe(18)
        secret_key = configured_secret_key or secrets.token_urlsafe(36)
        secret_data = {
            "access-key": encoded(access_key),
            "secret-key": encoded(secret_key),
        }

    for namespace in NAMESPACES:
        manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "s3-credentials", "namespace": namespace},
            "type": "Opaque",
            "data": secret_data,
        }
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=json.dumps(manifest),
            text=True,
            check=True,
        )
    if reused:
        print("Reused the existing S3 credentials across required namespaces.")
    elif not configured_access_key:
        print("Generated S3 credentials and stored them only in the Kubernetes Secret.")


if __name__ == "__main__":
    main()

