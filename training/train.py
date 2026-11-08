#!/usr/bin/env python3
"""CPU-only fine-tuning for sequence-level knowledge distillation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
from typing import Any

import boto3
import torch
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data import DataLoader, Dataset
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
import yaml

from training.formatting import prompt_for, target_for
from training.storage import client as s3_client, split_s3_uri


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "training" / "config.yaml"
ARTIFACT_ROOT = ROOT / "training" / "artifacts"


def load_config() -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    version = os.environ.get("MODEL_VERSION") or config["model_version"]
    if version not in config["versions"]:
        raise ValueError(f"Unknown MODEL_VERSION: {version}")
    merged = dict(config)
    merged.update(config["versions"][version] or {})
    merged["model_version"] = version
    return merged


def load_records(config: dict[str, Any]) -> tuple[list[dict], str]:
    bucket, key = split_s3_uri(config["dataset_uri"])
    data = s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    records = [
        json.loads(line) for line in data.decode("utf-8").splitlines() if line
    ]
    limit = config["max_training_examples"]
    subset = os.environ.get("SUBSET", "").strip()
    if subset:
        requested = int(subset)
        if requested < 1:
            raise ValueError("SUBSET must be a positive integer")
        limit = min(limit, requested)
    selected = records[:limit]
    if not selected:
        raise RuntimeError("The cleaned training dataset is empty")
    return selected, hashlib.sha256(data).hexdigest()


class DistillationDataset(Dataset):
    def __init__(self, records, tokenizer, max_length: int):
        self.examples = []
        eos = tokenizer.eos_token or ""
        for record in records:
            prompt_ids = tokenizer(
                prompt_for(record["text"]), add_special_tokens=False
            )["input_ids"]
            target_ids = tokenizer(
                target_for(record["teacher_raw"]) + eos, add_special_tokens=False
            )["input_ids"]
            input_ids = (prompt_ids + target_ids)[:max_length]
            labels = ([-100] * len(prompt_ids) + target_ids)[:max_length]
            if not any(label != -100 for label in labels):
                raise ValueError("Maximum sequence length removed the complete target")
            self.examples.append((input_ids, labels))

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, index):
        input_ids, labels = self.examples[index]
        return torch.tensor(input_ids), torch.tensor(labels)


def collator(pad_token_id: int):
    def collate(batch):
        inputs, labels = zip(*batch)
        padded_inputs = pad_sequence(inputs, batch_first=True, padding_value=pad_token_id)
        padded_labels = pad_sequence(labels, batch_first=True, padding_value=-100)
        attention_mask = pad_sequence(
            [torch.ones_like(item) for item in inputs],
            batch_first=True,
            padding_value=0,
        )
        return {
            "input_ids": padded_inputs,
            "attention_mask": attention_mask,
            "labels": padded_labels,
        }

    return collate


def sha256_manifest(directory: Path) -> str:
    lines = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        if path.name == "model.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(directory).as_posix()}")
    manifest = "\n".join(lines) + "\n"
    (directory / "model.sha256").write_text(manifest, encoding="utf-8")
    return manifest


def upload_artifacts(directory: Path, version: str) -> None:
    storage = s3_client()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        key = f"{version}/{path.relative_to(directory).as_posix()}"
        storage.upload_file(str(path), "models", key)
        print(f"Uploaded {path.name} to s3://models/{key}")


def train() -> None:
    config = load_config()
    seed = int(config["seed"])
    random.seed(seed)
    torch.manual_seed(seed)
    set_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))

    records, dataset_sha256 = load_records(config)
    tokenizer = AutoTokenizer.from_pretrained(config["base_model"])
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(config["base_model"])
    model.to(torch.device("cpu"))
    model.config.pad_token_id = tokenizer.pad_token_id

    dataset = DistillationDataset(records, tokenizer, config["max_sequence_length"])
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        dataset,
        batch_size=config["batch_size"],
        shuffle=True,
        generator=generator,
        collate_fn=collator(tokenizer.pad_token_id),
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"])
    epoch_losses = []
    for epoch in range(1, int(config["epochs"]) + 1):
        model.train()
        total_loss = 0.0
        for batch in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), config["gradient_clip_norm"]
            )
            optimizer.step()
            total_loss += loss.item()
        mean_loss = total_loss / len(loader)
        epoch_losses.append((epoch, mean_loss))
        print(f"epoch={epoch} training_loss={mean_loss:.6f}")

    version = config["model_version"]
    loss_filename = "loss.csv" if version == "v1" else f"loss_{version}.csv"
    loss_path = ROOT / "training" / loss_filename
    with loss_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["epoch", "training_loss"])
        writer.writerows((epoch, f"{loss:.8f}") for epoch, loss in epoch_losses)

    artifact_dir = ARTIFACT_ROOT / version
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    model.save_pretrained(artifact_dir, safe_serialization=True)
    tokenizer.save_pretrained(artifact_dir)
    shutil.copy2(loss_path, artifact_dir / "loss.csv")
    version_info = {
        "model_version": version,
        "base_model": config["base_model"],
        "training_examples": len(records),
        "dataset_sha256": dataset_sha256,
        "seed": seed,
        "learning_rate": config["learning_rate"],
        "batch_size": config["batch_size"],
        "epochs": config["epochs"],
        "max_sequence_length": config["max_sequence_length"],
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "boto3": boto3.__version__,
    }
    (artifact_dir / "version.json").write_text(
        json.dumps(version_info, indent=2) + "\n", encoding="utf-8"
    )
    sha256_manifest(artifact_dir)
    upload_artifacts(artifact_dir, version)
    print(json.dumps(version_info, indent=2))


if __name__ == "__main__":
    train()

