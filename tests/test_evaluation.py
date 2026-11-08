import hashlib
from pathlib import Path
import tempfile
import unittest

from training.evaluate import output_names, verify_checksum, write_jsonl


class EvaluationTests(unittest.TestCase):
    def test_student_output_names_include_model_version(self):
        self.assertEqual(
            output_names("student", "v2"),
            ("student_v2_predictions.jsonl", "student_v2_validation.json"),
        )
        self.assertEqual(
            output_names("teacher"),
            ("teacher_predictions.jsonl", "teacher_validation.json"),
        )

    def test_checksum_manifest_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "config.json"
            artifact.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            (root / "model.sha256").write_text(
                f"{digest}  config.json\n", encoding="utf-8"
            )
            verify_checksum(root)
            artifact.write_text("changed", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                verify_checksum(root)

    def test_prediction_writer_uses_one_json_object_per_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.jsonl"
            write_jsonl(path, [{"id": "V001", "prediction": "{}"}])
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{"id": "V001", "prediction": "{}"}\n',
            )


if __name__ == "__main__":
    unittest.main()

