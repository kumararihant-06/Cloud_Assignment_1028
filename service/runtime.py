"""Model download, checksum verification, loading, and CPU inference."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import threading
from urllib.parse import urlparse

import boto3
from botocore.config import Config
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


@dataclass(frozen=True)
class Settings:
    model_uri: str
    model_version: str
    s3_endpoint: str
    max_new_tokens: int
    fault_inject: bool

    @classmethod
    def from_environment(cls) -> "Settings":
        values = {}
        for name in ("MODEL_URI", "MODEL_VERSION", "S3_ENDPOINT", "MAX_NEW_TOKENS"):
            value = os.environ.get(name)
            if not value:
                raise RuntimeError(f"Required environment variable is not set: {name}")
            values[name] = value
        max_new_tokens = int(values["MAX_NEW_TOKENS"])
        if max_new_tokens < 1:
            raise RuntimeError("MAX_NEW_TOKENS must be positive")
        return cls(
            model_uri=values["MODEL_URI"],
            model_version=values["MODEL_VERSION"],
            s3_endpoint=values["S3_ENDPOINT"],
            max_new_tokens=max_new_tokens,
            fault_inject=os.environ.get("FAULT_INJECT", "0") == "1",
        )


def model_location(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise RuntimeError(f"MODEL_URI must be an S3 URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/").rstrip("/")


def verify_checksums(directory: Path) -> None:
    manifest = directory / "model.sha256"
    if not manifest.exists():
        raise RuntimeError("Downloaded model is missing model.sha256")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = directory / relative
        if not path.is_file():
            raise RuntimeError(f"Model file listed in checksum is missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch for model file: {relative}")


class ModelRuntime:
    def __init__(self):
        self.ready = False
        self.load_error: str | None = None
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()

    def _s3_client(self, endpoint: str):
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not access_key or not secret_key:
            raise RuntimeError("S3 credentials are not available")
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
            config=Config(
                signature_version="s3v4", s3={"addressing_style": "path"}
            ),
        )

    def _download(self, settings: Settings) -> Path:
        bucket, prefix = model_location(settings.model_uri)
        destination = Path(os.environ.get("MODEL_CACHE_DIR", "/models")) / settings.model_version
        temporary = destination.with_name(f".{destination.name}.downloading")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir(parents=True)
        storage = self._s3_client(settings.s3_endpoint)
        paginator = storage.get_paginator("list_objects_v2")
        found = 0
        object_prefix = f"{prefix}/" if prefix else ""
        for page in paginator.paginate(Bucket=bucket, Prefix=object_prefix):
            for item in page.get("Contents", []):
                relative = item["Key"].removeprefix(object_prefix)
                if not relative:
                    continue
                path = temporary / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                storage.download_file(bucket, item["Key"], str(path))
                found += 1
        if not found:
            raise RuntimeError(f"No model files found at {settings.model_uri}")
        verify_checksums(temporary)
        if destination.exists():
            shutil.rmtree(destination)
        temporary.rename(destination)
        return destination

    def load(self, settings: Settings) -> None:
        try:
            model_path = self._download(settings)
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(model_path)
            model.to(torch.device("cpu"))
            model.eval()
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            self._tokenizer = tokenizer
            self._model = model
            self.ready = True
            print(f"model_download_complete uri={settings.model_uri}", flush=True)
            print(f"model_ready version={settings.model_version}", flush=True)
        except Exception as error:
            self.load_error = str(error)
            print(f"model_load_failed error={error}", flush=True)

    def generate(self, text: str, max_new_tokens: int) -> str:
        if not self.ready or self._model is None or self._tokenizer is None:
            raise RuntimeError("Model is not ready")
        prompt = f"Command: {text}\nJSON:"
        with self._lock:
            encoded = self._tokenizer(prompt, return_tensors="pt")
            with torch.inference_mode():
                generated = self._model.generate(
                    **encoded,
                    do_sample=False,
                    max_new_tokens=max_new_tokens,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )
            new_tokens = generated[0, encoded["input_ids"].shape[1] :]
            return self._tokenizer.decode(
                new_tokens, skip_special_tokens=True
            ).strip()

