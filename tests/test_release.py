import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_release import ASSET_NAMES, prepare


class ReleaseTests(unittest.TestCase):
    def test_release_assets_are_verified_and_staged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            for name in ASSET_NAMES:
                if name != "model.sha256":
                    (source / name).write_text(
                        json.dumps({"model_version": "v2"})
                        if name == "version.json"
                        else name,
                        encoding="utf-8",
                    )
            entries = []
            for name in ASSET_NAMES:
                if name == "model.sha256":
                    continue
                checksum = hashlib.sha256((source / name).read_bytes()).hexdigest()
                entries.append(f"{checksum}  {name}")
            (source / "model.sha256").write_text(
                "\n".join(entries) + "\n", encoding="utf-8"
            )

            staged = prepare(source, destination, "v2")

            self.assertEqual(len(staged), len(ASSET_NAMES) + 1)
            self.assertTrue((destination / "model.safetensors").is_file())
            self.assertIn("model.safetensors", (destination / "SHA256SUMS").read_text())

    def test_checksum_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for name in ASSET_NAMES:
                (source / name).write_text(
                    json.dumps({"model_version": "v2"})
                    if name == "version.json"
                    else name,
                    encoding="utf-8",
                )
            (source / "model.sha256").write_text(
                f"{'0' * 64}  model.safetensors\n", encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                prepare(source, root / "destination", "v2")


if __name__ == "__main__":
    unittest.main()
