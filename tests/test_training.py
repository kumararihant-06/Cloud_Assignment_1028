import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from training.formatting import prompt_for, target_for, training_text
from training.storage import split_s3_uri
from training.train import upload_artifacts


class TrainingFormattingTests(unittest.TestCase):
    def test_training_example_has_required_command_and_json_format(self):
        text = training_text("weather in london", '{"intent":"weather_query"}')
        self.assertEqual(
            text,
            'Command: weather in london\nJSON: {"intent":"weather_query"}',
        )

    def test_prompt_and_target_are_separate_for_label_masking(self):
        self.assertEqual(prompt_for("set alarm"), "Command: set alarm\nJSON:")
        self.assertEqual(target_for("{}"), " {}")

    def test_s3_uri_parser(self):
        self.assertEqual(
            split_s3_uri("s3://datasets/v1/train.jsonl"),
            ("datasets", "v1/train.jsonl"),
        )
        with self.assertRaises(ValueError):
            split_s3_uri("https://example.com/train.jsonl")

    def test_model_upload_disables_small_multipart_transfers(self):
        storage = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.safetensors"
            path.write_bytes(b"weights")
            with patch("training.train.s3_client", return_value=storage):
                upload_artifacts(Path(directory), "v1")
        transfer = storage.upload_file.call_args.kwargs["Config"]
        self.assertEqual(transfer.multipart_threshold, 512 * 1024 * 1024)
        self.assertFalse(transfer.use_threads)


if __name__ == "__main__":
    unittest.main()

