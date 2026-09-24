"""Snapshot-membership checker tests, including adversarial packet mutations."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from attest import Rejected, load, verify
from attestation_campaign import MUTATIONS
from src.attestation import campaign_worlds, materialize_attestation
from src.generate import make


class AttestationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance = make(6, "star", 4, "balanced", 1)
        cls.world = campaign_worlds(cls.instance)[1]
        cls.snapshot, cls.packet = materialize_attestation(cls.instance, cls.world, seed=17)

    def reject(self, mutation=None, instance_mutation=None):
        inst = copy.deepcopy(self.instance)
        snapshot = copy.deepcopy(self.snapshot)
        packet = copy.deepcopy(self.packet)
        if mutation:
            self.assertTrue(mutation(inst, snapshot, packet))
        if instance_mutation:
            instance_mutation(inst)
        with self.assertRaises((Rejected, KeyError, TypeError, ValueError, IndexError, RecursionError)):
            verify(inst, snapshot, packet)

    def test_valid(self):
        verdict = verify(self.instance, self.snapshot, self.packet)
        self.assertEqual(verdict["world"], self.world)
        self.assertEqual(verdict["copies"], self.instance["total"])

    def test_three_campaign_worlds(self):
        worlds = campaign_worlds(self.instance)
        self.assertEqual(len(worlds), 3)
        for seed, world in enumerate(worlds):
            snapshot, packet = materialize_attestation(self.instance, world, seed=seed)
            self.assertEqual(verify(self.instance, snapshot, packet)["world"], world)

    def test_duplicate_assignment(self):
        self.reject(MUTATIONS["duplicate-assignment"])

    def test_uncovered_row(self):
        self.reject(MUTATIONS["uncovered-row"])

    def test_missing_attribute(self):
        self.reject(MUTATIONS["missing-attribute"])

    def test_extra_attribute(self):
        self.reject(MUTATIONS["extra-attribute"])

    def test_copy_count(self):
        self.reject(MUTATIONS["copy-count"])

    def test_wrong_instance(self):
        self.reject(MUTATIONS["wrong-instance"])

    def test_cross_copy_namespace(self):
        self.reject(MUTATIONS["cross-copy-namespace"])

    def test_noninjective_renaming(self):
        self.reject(MUTATIONS["noninjective-renaming"])

    def test_inconsistent_renaming(self):
        self.reject(MUTATIONS["inconsistent-renaming"])

    def test_bad_template_type(self):
        def mutation(inst, snapshot, packet):
            del inst, snapshot
            packet["copies"][0]["type"] = 999
            return True
        self.reject(mutation)

    def test_boolean_row_index(self):
        def mutation(inst, snapshot, packet):
            del inst, snapshot
            packet["copies"][0]["rows"][0][0] = True
            return True
        self.reject(mutation)

    def test_changed_template(self):
        self.reject(instance_mutation=lambda inst: inst["blocks"][0][0].pop())

    def test_extra_contract_field(self):
        self.reject(instance_mutation=lambda inst: inst.__setitem__("unexpected", 0))

    def test_null_seed(self):
        self.reject(instance_mutation=lambda inst: inst.__setitem__("seed", None))

    def test_extra_snapshot_field(self):
        def mutation(inst, snapshot, packet):
            del inst, packet
            snapshot["unexpected"] = 0
            return True
        self.reject(mutation)

    def test_extra_attestation_field(self):
        def mutation(inst, snapshot, packet):
            del inst, snapshot
            packet["unexpected"] = 0
            return True
        self.reject(mutation)

    def test_top_level_array_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(Rejected):
                load(path)

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.json"
            path.write_text('{"instance":"x","instance":"y"}', encoding="utf-8")
            with self.assertRaises(Rejected):
                load(path)


if __name__ == "__main__":
    unittest.main()
