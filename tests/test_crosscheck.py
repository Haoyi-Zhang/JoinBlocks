"""Deterministic small-instance cross-checks against the independent exhaustive oracle."""
from __future__ import annotations

import unittest

from checker import verify as verify_plan
from src.generate import make
from src.model import as_plan, plan_cost
from src.optimizer import optimize
from src.oracle import oracle


class IndependentCrossCheckTests(unittest.TestCase):
    def test_optimizer_checker_and_oracle_agree_on_36_instances(self):
        checked = 0
        for n in (3, 4, 5):
            for shape in ("star", "path", "branch"):
                for regime in ("balanced", "skewed"):
                    for seed in (7, 13):
                        instance = make(n, shape, 4, regime, seed)
                        certificate, _, profiles = optimize(instance)
                        verdict = verify_plan(instance, certificate)
                        exact = oracle(instance)

                        root = str((1 << n) - 1)
                        selected_plan = as_plan(
                            certificate["states"][root]["plans"][certificate["selected"]]
                        )
                        selected_profile = plan_cost(selected_plan, profiles)

                        self.assertTrue(verdict["accepted"])
                        self.assertEqual(certificate["regret"], exact["optimum"])
                        self.assertIn(selected_profile, exact["regret_by_profile"])
                        self.assertEqual(
                            exact["regret_by_profile"][selected_profile], exact["optimum"]
                        )
                        self.assertEqual(
                            {mask: tuple(values) for mask, values in profiles.items()}, exact["h"]
                        )
                        checked += 1
        self.assertEqual(checked, 36)


if __name__ == "__main__":
    unittest.main()
