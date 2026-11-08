#!/usr/bin/env python3
"""Verify and stage model assets for a GitHub Release without touching Git."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
ASSET_NAMES = (
    "config.json",
    "generation_config.json",
    "loss.csv",
    "model.safetensors",
    "model.sha256",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "version.json",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(source: Path, version: str) -> None:
    missing = [name for name in ASSET_NAMES if not (source / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing release assets: {', '.join(missing)}")
    for line in (source / "model.sha256").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        actual = digest(source / relative)
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch: {relative}")
    metadata = json.loads((source / "version.json").read_text(encoding="utf-8"))
    if metadata.get("model_version") != version:
        raise RuntimeError("version.json does not match the requested release version")


def prepare(source: Path, destination: Path, version: str) -> list[Path]:
    verify(source, version)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    staged = []
    for name in ASSET_NAMES:
        target = destination / name
        shutil.copy2(source / name, target)
        staged.append(target)
    checksum_lines = [f"{digest(path)}  {path.name}" for path in staged]
    checksum_path = destination / "SHA256SUMS"
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    staged.append(checksum_path)
    return staged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v2")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    source = args.source or ROOT / "training" / "artifacts" / args.version
    destination = args.destination or ROOT / "dist" / f"model-{args.version}"
    staged = prepare(source, destination, args.version)
    print(f"Verified and staged {len(staged)} release assets in {destination}")
    for path in staged:
        print(f"{digest(path)}  {path.name}")


if __name__ == "__main__":
    main()
