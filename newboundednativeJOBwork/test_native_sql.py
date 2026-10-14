"""Finite native SQL proof relation and local lifecycle regressions."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from src.attestation import campaign_worlds, materialize_attestation
from src.model import all_plans, as_plan, block_profile, dot, plan_cost
from src.optimizer import optimize
from src.physical import sqlite_bag
from src.reuse import ReuseSession, known_world_plan
from native_sql import SqlTree, SqlWindow, bag
from certified_sql import CertifiedSqlSession
import job3b


class NativeSqlTests(unittest.TestCase):
    def setUp(self):
        self.inst = json.loads((ROOT / 'results/reuse/contract.json').read_text())
        self.snapshot, self.packet = materialize_attestation(self.inst, [24, 8], seed=137)
        self.cert, _, self.h = optimize(self.inst)
        self.session = ReuseSession(self.inst, self.cert)

    def test_supplied_102_contracts_and_20_topologies(self):
        cases = [(p, ROOT / 'results/campaign/certificates' / p.name)
                 for p in sorted((ROOT / 'inputs').glob('*.json'))]
        cases += [(p, ROOT / 'results/topology/certificates' / p.name)
                  for p in sorted((ROOT / 'results/topology/inputs').glob('*.json'))]
        self.assertEqual(len(cases), 122)
        for path, cert_path in cases:
            inst, cert = json.loads(path.read_text()), json.loads(cert_path.read_text())
            session = ReuseSession(inst, cert)
            h = block_profile(inst)
            engine = SqlWindow(inst)
            try:
                for window, world in enumerate(campaign_worlds(inst)):
                    snapshot, packet = materialize_attestation(inst, world, seed=window)
                    frozen, revealed = session.open_window(window, inst, snapshot, packet)
                    actual, _ = engine.open_window(window, inst, snapshot, packet)
                    self.assertEqual(actual, revealed)
                    expected = sqlite_bag(inst, frozen)
                    for p in (session.plan, known_world_plan(inst, h, revealed)):
                        rows, metrics = engine.execute(SqlTree(inst, p))
                        self.assertEqual(bag(rows), expected, path.name)
                        self.assertEqual(metrics['intermediate_rows'], dot(plan_cost(as_plan(p), h), world))
                        for mask, count in metrics['internal_counts'].items():
                            self.assertEqual(count, dot(h[mask], world))
                    rows, _ = engine.natural()
                    self.assertEqual(bag(rows), expected)
            finally:
                engine.close()

    def test_positive_bags_and_exact_node_counts(self):
        engine = SqlWindow(self.inst)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            rows, metrics = engine.execute(SqlTree(self.inst, self.session.plan), explain=True)
            self.assertEqual(bag(rows), sqlite_bag(self.inst, self.snapshot))
            self.assertEqual(metrics['output_rows'], 16384)
            self.assertEqual(metrics['intermediate_rows'], 21504)
            self.assertEqual(len(metrics['explain']), 3)
        finally:
            engine.close()

    def test_all_six_trees_in_both_one_copy_worlds(self):
        inst = deepcopy(self.inst)
        inst['total'], inst['upper'] = 1, [1, 1]
        h = block_profile(inst)
        engine = SqlWindow(inst)
        try:
            for window, world in enumerate(([1, 0], [0, 1])):
                snapshot, mapping = materialize_attestation(inst, world, seed=window)
                engine.open_window(window, inst, snapshot, mapping)
                expected = sqlite_bag(inst, snapshot)
                plans = all_plans(inst)
                self.assertEqual(len(plans), 6)
                for plan in plans:
                    rows, metrics = engine.execute(SqlTree(inst, plan))
                    self.assertEqual(bag(rows), expected)
                    self.assertEqual(metrics['intermediate_rows'], dot(plan_cost(plan, h), world))
        finally:
            engine.close()

    def test_installed_tree_does_not_follow_caller_mutation(self):
        plan = json.loads(json.dumps(self.session.plan))
        tree = SqlTree(self.inst, plan)
        plan[0] = 99
        engine = SqlWindow(self.inst)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            rows, _ = engine.execute(tree)
            self.assertEqual(bag(rows), sqlite_bag(self.inst, self.snapshot))
        finally:
            engine.close()

    def test_empty_world_and_empty_join(self):
        inst = deepcopy(self.inst)
        inst['total'] = 0
        snap, packet = materialize_attestation(inst, [0, 0])
        engine = SqlWindow(inst)
        try:
            engine.open_window(0, inst, snap, packet)
            self.assertEqual(engine.execute(SqlTree(inst, self.session.plan))[0], [])
        finally:
            engine.close()

    def test_large_signed_exact_keys(self):
        snapshot = deepcopy(self.snapshot)
        for rows in snapshot['tables']:
            for row in rows:
                for e, v in row.items():
                    row[e] = -(1 << 100) + v
        engine = SqlWindow(self.inst)
        try:
            engine.open_window(0, self.inst, snapshot, self.packet)
            rows, _ = engine.execute(SqlTree(self.inst, self.session.plan))
            self.assertEqual(bag(rows), sqlite_bag(self.inst, snapshot))
        finally:
            engine.close()

    def test_changed_contract_and_failed_refresh_revoke(self):
        engine = SqlWindow(self.inst)
        tree = SqlTree(self.inst, self.session.plan)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            bad = deepcopy(self.packet)
            bad['copies'].pop()
            with self.assertRaises(ValueError):
                engine.open_window(1, self.inst, self.snapshot, bad)
            with self.assertRaisesRegex(ValueError, 'no accepted'):
                engine.execute(tree)
            changed = deepcopy(self.inst)
            changed['total'] = 31
            with self.assertRaisesRegex(ValueError, 'changed SQL contract'):
                engine.open_window(2, changed, self.snapshot, self.packet)
            with self.assertRaisesRegex(ValueError, 'no accepted'):
                engine.natural()
        finally:
            engine.close()

    def test_replayed_window_revoke_and_recover(self):
        engine = SqlWindow(self.inst)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            with self.assertRaises(ValueError):
                engine.open_window(0, self.inst, self.snapshot, self.packet)
            with self.assertRaises(ValueError):
                engine.natural()
            engine.open_window(1, self.inst, self.snapshot, self.packet)
            self.assertEqual(len(engine.natural()[0]), 16384)
        finally:
            engine.close()

    def test_owns_caller_rows_and_base_write_guard(self):
        engine = SqlWindow(self.inst)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            self.snapshot['tables'][0].clear()
            self.assertEqual(len(engine.natural()[0]), 16384)
            with self.assertRaises(sqlite3.DatabaseError):
                engine._db.execute('UPDATE r0 SET key0_0 = "other"')
        finally:
            engine.close()

    def test_invalid_trees_and_query_mismatch(self):
        for p in (True, [0, 0], [0, [1, 2]], [0, 1]):
            with self.assertRaises(ValueError):
                SqlTree(self.inst, p)

    def test_output_budget_leaves_no_temp_tables(self):
        engine = SqlWindow(self.inst, max_rows=10)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            with self.assertRaisesRegex(ValueError, 'budget'):
                engine.execute(SqlTree(self.inst, self.session.plan))
            self.assertEqual(engine._db.execute('SELECT name FROM sqlite_temp_master').fetchall(), [])
            engine.max_rows = 200_000
            rows, metrics = engine.execute(SqlTree(self.inst, self.session.plan), explain=True)
            self.assertEqual(len(rows), 16384)
            self.assertTrue(all(' LIMIT ' in record['sql'] for record in metrics['explain']))
        finally:
            engine.close()

    def test_budget_rejects_invalid_values_and_native_output_overflow(self):
        for value in (-1, True, 200001, 1.5):
            with self.assertRaisesRegex(ValueError, 'invalid SQL row budget'):
                SqlWindow(self.inst, max_rows=value)
        engine = SqlWindow(self.inst, max_rows=10)
        try:
            engine.open_window(0, self.inst, self.snapshot, self.packet)
            with self.assertRaisesRegex(ValueError, 'budget'):
                engine.natural()
        finally:
            engine.close()

    def test_authored_job_projection_membership(self):
        fixture = json.loads((HERE / 'authored_job3b.json').read_text())
        inst, tables, snapshot, packet = job3b.instantiate(fixture, [1, 2])
        cert, _, h = optimize(inst)
        session = ReuseSession(inst, cert)
        _, world = session.open_window(0, inst, snapshot, packet)
        self.assertEqual(world, (1, 2))
        engine = SqlWindow(inst)
        try:
            engine.open_window(0, inst, snapshot, packet)
            rows, metrics = engine.execute(SqlTree(inst, session.plan))
            self.assertEqual(bag(rows), sqlite_bag(inst, snapshot))
            self.assertEqual(len(rows), 6)
        finally:
            engine.close()

    def test_certified_api_executes_only_owned_committed_tree(self):
        inst, cert = deepcopy(self.inst), deepcopy(self.cert)
        native = CertifiedSqlSession(inst, cert)
        try:
            inst['total'] = 0
            cert['regret'] = -1
            with self.assertRaisesRegex(ValueError, 'no accepted'):
                native.execute()
            for window, world in enumerate(([24, 8], [8, 24])):
                snap, mapping = materialize_attestation(self.inst, world, seed=window)
                native.open_window(window, self.inst, snap, mapping)
                rows, metrics = native.execute()
                self.assertEqual(bag(rows), sqlite_bag(self.inst, snap))
                self.assertEqual(metrics['intermediate_rows'], 21504)
            self.assertEqual(native.plan_checks, 1)
            self.assertEqual(native.accepted_windows, 2)
            bad = deepcopy(self.packet)
            bad['copies'].pop()
            with self.assertRaises(ValueError):
                native.open_window(2, self.inst, self.snapshot, bad)
            with self.assertRaisesRegex(ValueError, 'no accepted'):
                native.execute()
        finally:
            native.close()

    def test_certified_api_rejects_invalid_plan_packet(self):
        cert = deepcopy(self.cert)
        cert['regret'] = -1
        with self.assertRaises(ValueError):
            CertifiedSqlSession(self.inst, cert)


if __name__ == '__main__':
    unittest.main(verbosity=2)
