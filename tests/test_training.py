import unittest

from training.formatting import prompt_for, target_for, training_text
from training.storage import split_s3_uri


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


if __name__ == "__main__":
    unittest.main()

