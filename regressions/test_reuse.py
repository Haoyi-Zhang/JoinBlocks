"""Lifecycle, scalar-DP, and actual hash-plan regressions; no network inputs."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import attest
import checker
from reuse_experiment import contract, schedule
from src.attestation import materialize_attestation
from src.model import all_plans, as_plan, block_profile, dot, plan_cost
from src.optimizer import optimize
from src.oracle import oracle
from src.physical import HashPlan, sqlite_bag
from src.reuse import ReuseSession, known_world_plan


class ReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst = contract()
        cls.cert, _, cls.h = optimize(cls.inst)

    def test_revealed_world_dp_is_exact_all_33_worlds(self):
        exact = oracle(self.inst)
        self.assertEqual(self.cert['regret'], exact['optimum'])
        self.assertEqual(self.cert['regret'], 2048)
        for world in exact['worlds']:
            plan = known_world_plan(self.inst, self.h, world)
            self.assertEqual(dot(plan_cost(plan, self.h), world),
                             min(dot(c, world) for _, c in exact['plans']))

    def test_future_windows_do_not_reoptimize_or_recheck_plan(self):
        with patch('checker.verify', wraps=checker.verify) as checks:
            session = ReuseSession(self.inst, self.cert)
            committed = session.plan
            with patch('src.optimizer.optimize', side_effect=AssertionError('reoptimized')):
                for window, (world, _) in enumerate(schedule('migration')):
                    snap, packet = materialize_attestation(self.inst, world, seed=window)
                    _, revealed = session.open_window(window, self.inst, snap, packet)
                    self.assertEqual(revealed, tuple(world))
                    self.assertEqual(session.plan, committed)
                    session.require_active()
            self.assertEqual(checks.call_count, 1)
            self.assertEqual(session.membership_checks, 24)

    def test_failure_revokes_previous_window(self):
        session = ReuseSession(self.inst, self.cert)
        snap, packet = materialize_attestation(self.inst, [24, 8])
        session.open_window(0, self.inst, snap, packet)
        packet['copies'].pop()
        with self.assertRaises(attest.Rejected):
            session.open_window(1, self.inst, snap, packet)
        with self.assertRaisesRegex(ValueError, 'no accepted'):
            session.require_active()

    def test_changed_contract_same_name_requires_new_session(self):
        session = ReuseSession(self.inst, self.cert)
        snap, packet = materialize_attestation(self.inst, [24, 8])
        for field, value in (('total', 31), ('lower', [1, 0]), ('edges', [[0, 2], [0, 1], [0, 3]])):
            changed = deepcopy(self.inst)
            changed[field] = value
            with self.assertRaisesRegex(ValueError, 'changed contract'):
                session.open_window(session._last_window + 1, changed, snap, packet)

    def test_owned_input_and_plan_copies(self):
        inst, cert = deepcopy(self.inst), deepcopy(self.cert)
        session = ReuseSession(inst, cert)
        committed = session.plan
        inst['total'] = 0
        cert['regret'] = -1
        exported = session.plan
        if type(exported) is list:
            exported[0] = 99
        self.assertEqual(session.plan, committed)
        snap, packet = materialize_attestation(self.inst, [24, 8])
        frozen, _ = session.open_window(0, self.inst, snap, packet)
        snap['tables'][0][0]['0'] = -999
        self.assertNotEqual(frozen, snap)
        with self.assertRaises(TypeError):
            frozen['tables'][0][0]['0'] = -999

    def test_replayed_window_revokes_authorization(self):
        session = ReuseSession(self.inst, self.cert)
        snap, packet = materialize_attestation(self.inst, [24, 8])
        session.open_window(2, self.inst, snap, packet)
        with self.assertRaisesRegex(ValueError, 'advance'):
            session.open_window(2, self.inst, snap, packet)
        with self.assertRaises(ValueError):
            session.require_active()

    def test_hash_execution_all_orders_matches_sql_bags_and_costs(self):
        small = deepcopy(self.inst)
        small['total'], small['upper'] = 1, [1, 1]
        profiles = block_profile(small)
        for world in ([1, 0], [0, 1]):
            snap, _ = materialize_attestation(small, world)
            expected = sqlite_bag(small, snap)
            self.assertEqual(sum(expected.values()), 512)
            for plan in all_plans(small):
                rows, metrics = HashPlan(small, plan).execute(snap)
                self.assertEqual(Counter(rows), expected)
                self.assertEqual(metrics['intermediate_rows'], dot(plan_cost(plan, profiles), world))

    def test_hash_execution_keeps_wide_key_identity_and_bag_occurrences(self):
        inst = {'n': 2, 'edges': [[0, 1]]}
        snap = {'tables': [[{'0': 1 << 100}, {'0': 1 << 100}, {'0': (1 << 100) + 1}],
                           [{'0': 1 << 100}, {'0': 1 << 100}, {'0': (1 << 100) + 1}]]}
        rows, metrics = HashPlan(inst, (0, 1)).execute(snap)
        self.assertEqual(Counter(rows), sqlite_bag(inst, snap))
        self.assertEqual(metrics['output_rows'], 5)

    def test_hash_rejects_cartesian_and_incomplete_plans(self):
        for plan in (((1, 2), (0, 3)), (0, 0), (0, 1)):
            with self.assertRaises(ValueError):
                HashPlan(self.inst, plan)

    def test_all_102_retained_contracts_reuse_and_known_world_dp(self):
        root = Path(__file__).resolve().parents[1]
        checked = 0
        for path in sorted((root / 'inputs').glob('*.json')):
            inst = attest.load(path)
            cert = checker.load(root / 'results/campaign/certificates' / path.name)
            exact = oracle(inst)
            session = ReuseSession(inst, cert)
            committed = as_plan(session.plan)
            for window, world in enumerate((exact['worlds'][0], exact['worlds'][-1])):
                snap, packet = materialize_attestation(inst, list(world), seed=window)
                _, revealed = session.open_window(window, inst, snap, packet)
                adaptive = known_world_plan(inst, exact['h'], revealed)
                best = min(dot(c, world) for _, c in exact['plans'])
                self.assertEqual(dot(plan_cost(adaptive, exact['h']), world), best)
                self.assertLessEqual(dot(plan_cost(committed, exact['h']), world) - best, cert['regret'])
                self.assertEqual(as_plan(session.plan), committed)
            self.assertEqual(session.plan_checks, 1)
            checked += 1
        self.assertEqual(checked, 102)


if __name__ == '__main__':
    unittest.main()
