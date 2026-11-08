import unittest

from scripts.cost import calculate


class CostTests(unittest.TestCase):
    def test_cost_uses_limits_replica_count_and_success_ratio(self):
        rate_card = {
            "currency": "INR",
            "vcpu_hour": 3.50,
            "gib_memory_hour": 0.45,
            "billing_rule": "bill limits",
        }
        stats = {
            "Request Count": "10",
            "Failure Count": "2",
            "Requests/s": "2.0",
        }
        result = calculate(rate_card, stats, replicas=4)
        self.assertEqual(result["cost_per_replica_hour"], 7.45)
        self.assertEqual(result["total_cost_per_hour"], 29.8)
        self.assertEqual(result["attempted_requests_per_hour"], 7200.0)
        self.assertEqual(result["successful_requests_per_hour"], 5760.0)
        self.assertEqual(result["cost_per_1000_attempted_requests"], 4.1389)
        self.assertEqual(result["cost_per_1000_successful_requests"], 5.1736)

    def test_invalid_throughput_is_rejected(self):
        rate_card = {
            "currency": "INR",
            "vcpu_hour": 3.50,
            "gib_memory_hour": 0.45,
            "billing_rule": "bill limits",
        }
        with self.assertRaises(ValueError):
            calculate(
                rate_card,
                {"Request Count": "1", "Failure Count": "1", "Requests/s": "0"},
                replicas=4,
            )


if __name__ == "__main__":
    unittest.main()
