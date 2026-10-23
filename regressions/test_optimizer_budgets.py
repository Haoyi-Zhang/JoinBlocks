"""Owned finite producer-admission controls, not new workload measurements."""
import unittest
from unittest.mock import patch

from src.generate import make
from src.model import add
from src.optimizer import optimize


class OptimizerBudgetTests(unittest.TestCase):
    def test_state_limit_checked_before_building_over_budget_candidate(self):
        # A fixed repeated-split fixture tests exactly the allocation boundary.
        # It is not supplied to the independent certificate checker.
        instance = make(2, 'path', 4, 'balanced', 7)
        with patch('src.optimizer.subsets', return_value=[1, 2, 3]), \
             patch('src.optimizer.block_profile', return_value={1: (1,), 2: (1,), 3: (1,)}), \
             patch('src.optimizer.cuts', return_value=[(1, 2)] * 50001), \
             patch('src.optimizer.add', wraps=add) as combine:
            with self.assertRaisesRegex(ValueError, 'state expansion limit'):
                optimize(instance)
            self.assertEqual(50000, combine.call_count)

    def test_unsupported_dimensions_stop_before_template_expansion(self):
        for n in (1, 9, True, 3.0):
            with self.subTest(n=n), patch('src.optimizer.block_profile') as expand:
                instance = make(3, 'path', 4, 'balanced', 7)
                instance['n'] = n
                with self.assertRaisesRegex(ValueError, 'relation count'):
                    optimize(instance)
                expand.assert_not_called()

    def test_unknown_pruning_policy_is_not_silently_contract_pruning(self):
        with patch('src.optimizer.block_profile') as expand:
            with self.assertRaisesRegex(ValueError, 'pruning policy'):
                optimize(make(3, 'path', 4, 'balanced', 7), pruning='typo')
            expand.assert_not_called()


if __name__ == '__main__':
    unittest.main()
