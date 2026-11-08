#!/usr/bin/env python3
"""Generate and score validation predictions for teacher, base, or student."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import yaml

from training.formatting import prompt_for
from training.storage import client as s3_client


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
VALIDATION = ROOT / "data" / "validation.jsonl"
CONFIG = yaml.safe_load((ROOT / "training" / "config.yaml").read_text())
OUTPUT_NAMES = {
    "teacher": ("teacher_predictions.jsonl", "teacher_validation.json"),
    "untrained": ("untrained_predictions.jsonl", "untrained_validation.json"),
    "student": ("student_predictions.jsonl", "student_validation.json"),
}


def validation_records() -> list[dict]:
    return [
        json.loads(line)
        for line in VALIDATION.read_text(encoding="utf-8").splitlines()
        if line
    ]


def verify_checksum(directory: Path) -> None:
    checksum_path = directory / "model.sha256"
    if not checksum_path.exists():
        raise RuntimeError(f"Missing model checksum: {checksum_path}")
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = directory / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch for {path}")


def download_student(version: str) -> Path:
    local = ROOT / "training" / "artifacts" / version
    if (local / "model.sha256").exists():
        verify_checksum(local)
        return local

    local = ROOT / "training" / "downloads" / version
    local.mkdir(parents=True, exist_ok=True)
    storage = s3_client()
    paginator = storage.get_paginator("list_objects_v2")
    found = 0
    for page in paginator.paginate(Bucket="models", Prefix=f"{version}/"):
        for item in page.get("Contents", []):
            relative = item["Key"].removeprefix(f"{version}/")
            if not relative:
                continue
            destination = local / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            storage.download_file("models", item["Key"], str(destination))
            found += 1
    if not found:
        raise RuntimeError(f"No model objects found under s3://models/{version}/")
    verify_checksum(local)
    return local


def teacher_predictions(records: list[dict]) -> list[dict]:
    from worker.label import teacher_reply

    template = (ROOT / "prompts" / "teacher_prompt.txt").read_text(encoding="utf-8")
    predictions = []
    for index, record in enumerate(records, 1):
        raw = teacher_reply(template.replace("{{COMMAND}}", record["text"]))
        predictions.append({"id": record["id"], "prediction": raw})
        print(f"teacher validation: {index}/{len(records)}")
    return predictions


def causal_predictions(records: list[dict], model_source: str | Path) -> list[dict]:
    tokenizer = AutoTokenizer.from_pretrained(model_source)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_source)
    model.to(torch.device("cpu"))
    model.eval()
    predictions = []
    for index, record in enumerate(records, 1):
        encoded = tokenizer(
            prompt_for(record["text"]),
            return_tensors="pt",
            truncation=True,
            max_length=CONFIG["max_sequence_length"],
        )
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                do_sample=False,
                max_new_tokens=96,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        new_tokens = generated[0, encoded["input_ids"].shape[1] :]
        raw = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        predictions.append({"id": record["id"], "prediction": raw})
        print(f"model validation: {index}/{len(records)}")
    return predictions


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def score(predictions_path: Path, report_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "score.py"),
            str(predictions_path),
            str(VALIDATION),
            "--out",
            str(report_path),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", choices=("teacher", "untrained", "student"), required=True
    )
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()
    records = validation_records()
    if args.model == "teacher":
        predictions = teacher_predictions(records)
    elif args.model == "untrained":
        predictions = causal_predictions(records, CONFIG["base_model"])
    else:
        predictions = causal_predictions(records, download_student(args.version))

    RESULTS.mkdir(exist_ok=True)
    prediction_name, report_name = OUTPUT_NAMES[args.model]
    predictions_path = RESULTS / prediction_name
    report_path = RESULTS / report_name
    write_jsonl(predictions_path, predictions)
    score(predictions_path, report_path)
    print(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

