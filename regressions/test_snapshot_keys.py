"""Exact snapshot-key/SQLite boundary regressions, separate from the frozen suite."""
import unittest

import attest
from attestation_campaign import sql_profile
from src.optimizer import optimize
from verify_chain import verify


class SnapshotKeyTests(unittest.TestCase):
    def check_keys(self, first, second):
        # Duplicate occurrences must remain a bag: 2*2 + 1*1 = 5 matches.
        inst = {"name": "snapshot-key-domain", "n": 2, "edges": [[0, 1]],
                "lower": [1], "upper": [1], "total": 1,
                "blocks": [[[{'0': 0}, {'0': 0}, {'0': 1}],
                            [{'0': 0}, {'0': 0}, {'0': 1}]]]}
        snapshot = {"instance": inst["name"], "tables": [
            [{'0': first}, {'0': first}, {'0': second}],
            [{'0': first}, {'0': first}, {'0': second}]]}
        packet = {"instance": inst["name"], "copies": [
            {"type": 0, "rows": [[0, 1, 2], [0, 1, 2]]}]}
        self.assertNotEqual(first, second)
        self.assertTrue(attest.verify(inst, snapshot, packet)["accepted"])
        self.assertTrue(verify(inst, snapshot, packet, optimize(inst)[0])["accepted"])
        self.assertEqual(sql_profile(inst, snapshot), {1: 3, 2: 3, 3: 5})

    def test_adjacent_wide_integers_remain_distinct(self):
        self.check_keys(1 << 100, (1 << 100) + 1)

    def test_signed_120_bit_boundary_preserves_bags(self):
        self.check_keys((1 << 120) - 1, -((1 << 120) - 1))

    def test_zero_and_negative_integer_keys(self):
        self.check_keys(0, -1)


if __name__ == "__main__":
    unittest.main()
