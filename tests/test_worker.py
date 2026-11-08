import json
import unittest

from worker.clean import clean_records, rejection_reason, verify_coverage
from worker.label import ollama_payload, shard_records


def record(record_id, text, reply):
    return {
        "id": record_id,
        "text": text,
        "teacher_raw": reply if isinstance(reply, str) else json.dumps(reply),
    }


class ShardingTests(unittest.TestCase):
    def test_modulo_shards_are_complete_and_disjoint(self):
        commands = [{"id": f"C{i:04d}"} for i in range(10)]
        shards = [list(shard_records(commands, index, 3)) for index in range(3)]
        ids = [[item["id"] for item in shard] for shard in shards]
        self.assertEqual(ids[0], ["C0000", "C0003", "C0006", "C0009"])
        self.assertEqual(len({value for shard in ids for value in shard}), 10)

    def test_teacher_payload_fixes_required_settings_and_output_schema(self):
        payload = json.loads(ollama_payload("prompt"))
        self.assertEqual(payload["model"], "phi3.5")
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertEqual(payload["options"]["seed"], 42)
        self.assertEqual(payload["options"]["num_predict"], 96)
        self.assertFalse(payload["format"]["additionalProperties"])


class CleaningTests(unittest.TestCase):
    def test_rejection_categories(self):
        self.assertEqual(rejection_reason(record("C1", "weather london", "bad")), "invalid_json")
        self.assertEqual(
            rejection_reason(record("C2", "weather london", {"intent": "weather_query"})),
            "wrong_keys",
        )
        self.assertEqual(
            rejection_reason(
                record(
                    "C3",
                    "weather london",
                    {"intent": "other", "date": None, "time": None, "place": "london"},
                )
            ),
            "invalid_intent",
        )
        self.assertEqual(
            rejection_reason(
                record(
                    "C4",
                    "weather london",
                    {
                        "intent": "weather_query",
                        "date": None,
                        "time": None,
                        "place": "paris",
                    },
                )
            ),
            "invalid_slot",
        )

    def test_cleaning_keeps_smallest_duplicate_id_and_balances_counts(self):
        reply = {
            "intent": "weather_query",
            "date": None,
            "time": None,
            "place": "london",
        }
        records = [
            record("C0002", "weather london", reply),
            record("C0001", "weather london", reply),
            record("C0003", "weather paris", "not json"),
        ]
        cleaned, counts = clean_records(records)
        self.assertEqual([item["id"] for item in cleaned], ["C0001"])
        self.assertEqual(counts["duplicates"], 1)
        self.assertEqual(counts["invalid_json"], 1)
        self.assertEqual(counts["input_records"], 3)

    def test_coverage_rejects_missing_or_repeated_ids(self):
        commands = [{"id": "C1"}, {"id": "C2"}]
        with self.assertRaises(ValueError):
            verify_coverage(commands, [{"id": "C1"}, {"id": "C1"}])


if __name__ == "__main__":
    unittest.main()

