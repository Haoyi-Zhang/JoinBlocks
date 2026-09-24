"""End-to-end composition tests for membership and plan certificates."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

import attest
import checker
from src.attestation import materialize_attestation
from verify_chain import Rejected, verify


class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.instance = attest.load(root / "inputs" / "star-4-4-balanced-101.json")
        cls.certificate = checker.load(
            root / "results" / "campaign" / "certificates" / "star-4-4-balanced-101.json"
        )
        cls.world = cls.certificate["containment"][str((1 << cls.instance["n"]) - 1)]["max_world"]
        cls.snapshot, cls.packet = materialize_attestation(cls.instance, cls.world, seed=41)

    def test_valid_chain(self):
        verdict = verify(self.instance, self.snapshot, self.packet, self.certificate)
        self.assertTrue(verdict["accepted"])
        self.assertEqual(verdict["world"], self.world)
        self.assertEqual(verdict["regret"], self.certificate["regret"])

    def test_membership_failure_is_labeled(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tables"][0][0].pop(next(iter(snapshot["tables"][0][0])))
        with self.assertRaisesRegex(Rejected, "^membership:"):
            verify(self.instance, snapshot, self.packet, self.certificate)

    def test_plan_failure_is_labeled(self):
        certificate = copy.deepcopy(self.certificate)
        certificate["regret"] += 1
        with self.assertRaisesRegex(Rejected, "^plan:"):
            verify(self.instance, self.snapshot, self.packet, certificate)


if __name__ == "__main__":
    unittest.main()
