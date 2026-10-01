import json
import unittest

from checker import verify
from src.generate import (
    load_job_tree_topologies,
    make,
    make_job_topology,
    make_tree,
)
from src.optimizer import optimize
from src.oracle import oracle
from src.oracle_json import from_jsonable, to_jsonable



class JobTopologyTests(unittest.TestCase):
    def test_generic_path_is_original_generator(self):
        for n in (4, 6, 8):
            edges = [(i, i + 1) for i in range(n - 1)]
            original = make(n, "path", 4, "balanced", 313)
            generic = make_tree(n, edges, "path", 4, "balanced", 313)
            self.assertEqual(original, generic)
            self.assertTrue(all(type(edge) is list for edge in generic["edges"]))

        minimal = make_tree(2, [[0, 1]], "minimal", 4, "balanced", 7)
        certificate, _stats, _profiles = optimize(minimal)
        self.assertTrue(verify(minimal, certificate)["accepted"])
        exact = oracle(minimal)
        encoded = to_jsonable(exact)
        decoded = from_jsonable(json.loads(json.dumps(encoded, sort_keys=True)))
        self.assertEqual(decoded, exact)
        self.assertEqual(certificate["regret"], exact["optimum"])

    def test_manifest_is_closed_and_tree_validated(self):
        data = load_job_tree_topologies()
        self.assertEqual(data["source"]["commit"], "a39603662e023e449cb2121997a5034df9e02ebf")
        self.assertEqual([len(q["aliases"]) for q in data["queries"]], [4, 5, 6, 7, 8])
        self.assertEqual(len({q["blob_sha"] for q in data["queries"]}), 5)

    def test_each_derived_topology_has_exact_checked_solution(self):
        data = load_job_tree_topologies()
        for entry in data["queries"]:
            with self.subTest(query_id=entry["query_id"]):
                instance = make_job_topology(entry, 4, "balanced", 313)
                certificate, _stats, _profiles = optimize(instance)
                verify(instance, certificate)
                exact = oracle(instance)
                self.assertEqual(certificate["regret"], exact["optimum"])

    def test_tree_validation_rejects_non_trees(self):
        with self.assertRaises(ValueError):
            make_tree(4, [(0, 1), (1, 2)], "bad", 4, "balanced", 1)
        with self.assertRaises(ValueError):
            make_tree(4, [(0, 1), (1, 2), (2, 0)], "bad", 4, "balanced", 1)
        with self.assertRaises(ValueError):
            make_tree(4, [(0, 1), (1, 2), (1, 2)], "bad", 4, "balanced", 1)


if __name__ == "__main__":
    unittest.main()
