"""Offline tests for the read-only PostgreSQL/SurrealDB parity probe."""

import unittest
from benchmark_readonly import CASES, ProbeError, normalize_pg, normalize_surreal


class ParityProbeTests(unittest.TestCase):
    def test_queries_are_read_only_and_pinned(self) -> None:
        self.assertEqual(len(CASES), 14)
        self.assertEqual(len(set(item.name for item in CASES)), len(CASES))
        for item in CASES:
            self.assertTrue(item.pg.startswith("SELECT "))
            self.assertTrue(item.surreal.startswith("SELECT "))
            self.assertIn("5e9fdbc3", item.pg)
            self.assertIn("5e9fdbc3", item.surreal)

    def test_counts(self) -> None:
        self.assertEqual(normalize_pg("405\n", "count"), 405)
        self.assertEqual(normalize_surreal('[[{"n":405}]]', "count"), 405)
        self.assertEqual(normalize_surreal('[{"n":405}]', "count"), 405)
        self.assertEqual(normalize_surreal('{"result":[{"n":405}]}', "count"), 405)

    def test_model_ids(self) -> None:
        self.assertEqual(normalize_pg("ai21/jamba-large\n", "ids"), ["ai21/jamba-large"])
        self.assertEqual(
            normalize_surreal('[["ai21/jamba-large"]]', "ids"),
            ["ai21/jamba-large"],
        )

    def test_invalid_json_or_types(self) -> None:
        for response in ("", "not-json", '[{"n":"405"}]', '[{"n":true}]'):
            with self.subTest(response=response), self.assertRaises(ProbeError):
                normalize_surreal(response, "count")


if __name__ == "__main__":
    unittest.main()
