"""Current-only finite support/whole-plan checks, separate from frozen 68."""
from copy import deepcopy
from itertools import product
import unittest
from checker import verify
from src.generate import make
from src.model import as_plan, plan_cost
from src.optimizer import optimize, _support_query
from src.oracle import oracle


def support_cases():
    for k in (1, 2, 3):
        for bounds in product([(l, u) for l in range(3) for u in range(l, 3)], repeat=k):
            lo, hi = [x[0] for x in bounds], [x[1] for x in bounds]
            for total in range(sum(lo), sum(hi) + 1):
                worlds = [w for w in product(*(range(l, u + 1) for l, u in bounds)) if sum(w) == total]
                yield lo, hi, total, worlds


class SupportReuseTests(unittest.TestCase):
    def test_bounded_support_definition_and_weak_duality(self):
        count = 0
        for lo, hi, total, worlds in support_cases():
            query = _support_query(lo, hi, total)
            for direction in product(range(-2, 3), repeat=len(lo)):
                value, world, threshold = query(direction)
                self.assertEqual(value, max(sum(x * y for x, y in zip(direction, w)) for w in worlds))
                self.assertIn(tuple(world), worlds)
                dual = sum(x * l for x, l in zip(direction, lo)) + threshold * (total - sum(lo))
                dual += sum((u - l) * max(x - threshold, 0) for x, l, u in zip(direction, lo, hi))
                self.assertEqual(value, dual)
                self.assertEqual(query(list(direction)), (value, world, threshold))
                count += 1
        self.assertEqual(count, 83150)

    def test_lru_eviction_and_fresh_worlds(self):
        query = _support_query([0, 0], [2, 2], 2, maxsize=2)
        first = query((1, 0))
        first[1][0] = -999
        self.assertEqual(query((1, 0)), (2, [2, 0], 1))
        query((0, 1)); query((-1, 0)); query((1, 0))
        info = query.cache_info()
        self.assertEqual((info.hits, info.misses, info.currsize), (1, 4, 2))
        uncached = _support_query([0, 0], [2, 2], 2, maxsize=0)
        for direction in product(range(-1, 2), repeat=2):
            self.assertEqual(query(direction), uncached(direction))

    def test_full_packets_all_pruning_modes_and_independent_oracle(self):
        for n, shape, regime, seed in product((3, 4, 5), ('star', 'path', 'branch'), ('balanced', 'skewed'), (7, 13)):
            inst = make(n, shape, 4, regime, seed)
            saved, exact = deepcopy(inst), oracle(inst)
            for mode in ('contract', 'component', 'none'):
                cert, stats, profiles = optimize(inst, pruning=mode)
                self.assertTrue(verify(inst, cert)['accepted'])
                self.assertEqual(profiles, exact['h'])
                selected = as_plan(cert['states'][str((1 << n) - 1)]['plans'][cert['selected']])
                self.assertEqual(exact['regret_by_profile'][plan_cost(selected, profiles)], exact['optimum'])
                self.assertEqual(cert['regret'], exact['optimum'])
                self.assertGreater(stats['support_calls'], 0)
                worlds = [entry[field] for entry in cert['containment'].values() for field in ('min_world', 'max_world')]
                worlds += [entry['world'] for entry in cert['lower_witnesses']]
                self.assertEqual(len(worlds), len({id(w) for w in worlds}))
            self.assertEqual(inst, saved)

    def test_contract_isolation_and_error_boundaries(self):
        lower, upper = [0, 0], [2, 2]
        first = _support_query(lower, upper, 2)
        lower[0] = 1; upper[1] = 1
        second = _support_query(lower, upper, 2)
        self.assertEqual(first((0, 1)), (2, [0, 2], 1))
        self.assertEqual(second((0, 1)), (1, [1, 1], 1))
        for lo, hi, total in (([1], [1], 0), ([0], [1], 2)):
            query = _support_query(lo, hi, total)
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, 'infeasible contract'):
                    query((1,))
            self.assertEqual(query.cache_info().currsize, 0)
        for total in (0, 1, 2):
            inst = make(3, 'path', 4, 'balanced', 7)
            inst['lower'], inst['upper'], inst['total'] = [0] * 4, [1] * 4, total
            cert, _, _ = optimize(inst)
            self.assertTrue(verify(inst, cert)['accepted'])
            self.assertEqual(cert['regret'], oracle(inst)['optimum'])


if __name__ == '__main__':
    unittest.main()
