"""The displayed protocol preserves both independent proof obligations."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('schematic', ROOT/'plots/draw_schematics.py')
schematic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schematic)


class SchematicContractTests(unittest.TestCase):
    def test_two_branches_share_the_full_contract_and_conclusion(self):
        self.assertEqual(set(schematic.EDGES), {
            ('contract','snapshot'), ('contract','search'),
            ('snapshot','membership'), ('membership','mcheck'),
            ('search','plancert'), ('plancert','pcheck'),
            ('mcheck','result'), ('pcheck','result')})
        self.assertEqual(len(schematic.EDGES), 8)
        self.assertEqual(len(schematic.NODES), 8)

    def test_checker_labels_preserve_their_semantic_obligations(self):
        self.assertIn('cover, renaming, isolation', schematic.NODES['mcheck'][4])
        self.assertIn('profiles and inequalities', schematic.NODES['pcheck'][4])
        self.assertIn('snapshot regret is bounded', schematic.NODES['result'][4])


if __name__ == '__main__':
    unittest.main()
