#!/usr/bin/env python3
"""Offline future-window experiment; explicit plans, timed execution, exact checks."""
import argparse
import gzip
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import attest
from src.attestation import materialize_attestation
from src.model import as_plan, block_profile, dot, plan_cost
from src.optimizer import optimize
from src.oracle import oracle
from src.physical import HashPlan, sqlite_bag
from src.reuse import ReuseSession, checked_window, known_world_plan

POLICIES = ('robust', 'known_fixed', 'adaptive')


def contract():
    # Positive-output extension of the mathematical hedge, not a JOB workload.
    a, b, c = {0, 1, 2, 6}, {3, 4, 5, 6}, {0, 1, 3, 6}
    blocks = []
    for zeros in ((a, b, c), (a, c, b)):
        center = [{str(e): 0 if row in zeros[e] else 1 for e in range(3)}
                  for row in range(7)]
        blocks.append([center] + [[{str(e): 0} for _ in range(8)] for e in range(3)])
    return {'name': 'positive-output-reuse', 'n': 4, 'edges': [[0, 1], [0, 2], [0, 3]],
            'lower': [0, 0], 'upper': [32, 32], 'total': 32, 'blocks': blocks,
            'family': 'synthetic-isolated-tenants', 'regime': 'positive-output-hedge'}


def schedule(kind):
    # Copy replacements model a tenant mix; cadence and demand fixed before timing.
    if kind == 'stationary':
        first = [24] * 24
    elif kind == 'migration':
        first = list(range(24, 7, -2)) + [8] * 4 + list(range(10, 25, 2)) + [24] * 3
    elif kind == 'bursts':
        first = [24] * 4 + [8] * 8 + [24] * 4 + [8] * 8
    else:
        raise ValueError(kind)
    assert len(first) == 24
    return [([x, 32 - x], (4, 8, 16, 8)[i % 4]) for i, x in enumerate(first)]


def timed(fn):
    wall, cpu = time.perf_counter(), time.process_time()
    result = fn()
    return result, {'wall_s': time.perf_counter() - wall, 'cpu_s': time.process_time() - cpu}


def add(target, amount):
    for key in ('wall_s', 'cpu_s'):
        target[key] += amount[key]


def run(output, repeats=3):
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('choose a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    inst = contract()
    exact = oracle(inst)
    assert exact['optimum'] == 2048
    all_rounds, all_runs = [], []
    for scenario in ('stationary', 'migration', 'bursts'):
        for repeat in range(repeats):
            h, profile_time = timed(lambda: block_profile(inst))
            (initial, mapping), initial_acquisition = timed(
                lambda: materialize_attestation(inst, [24, 8], seed=991))
            initial_verdict, initial_time = timed(lambda: attest.verify(inst, initial, mapping))
            # Commit from initial information. Future windows are generated only below.
            (cert, _, _), produce_time = timed(lambda: optimize(inst))
            robust, check_time = timed(lambda: ReuseSession(inst, cert))
            fixed, fixed_time = timed(lambda: known_world_plan(inst, h, initial_verdict['world']))
            rengine, rcompile = timed(lambda: HashPlan(inst, robust.plan))
            fengine, fcompile = timed(lambda: HashPlan(inst, fixed))
            states = {p: {'wall_s': 0.0, 'cpu_s': 0.0, 'setup_wall_s': 0.0,
                          'membership_wall_s': 0.0, 'selection_wall_s': 0.0,
                          'execution_wall_s': 0.0, 'intermediate_rows': 0,
                          'max_per_query_regret': 0, 'selection_calls': 0}
                      for p in POLICIES}
            for p in POLICIES:
                add(states[p], profile_time)
                add(states[p], initial_time)
            for t in (produce_time, check_time, rcompile):
                add(states['robust'], t)
            for t in (fixed_time, fcompile):
                add(states['known_fixed'], t)
            states['robust']['selection_calls'] = 1
            states['known_fixed']['selection_calls'] = 1
            for p in POLICIES:
                states[p]['setup_wall_s'] = states[p]['wall_s']
            acquired = initial_acquisition['wall_s']
            for window, (world, queries) in enumerate(schedule(scenario)):
                (snapshot, packet), acquisition = timed(
                    lambda: materialize_attestation(inst, world, seed=1000 + window))
                acquired += acquisition['wall_s']
                # Untimed SQL and oracle validation is outside every policy budget.
                expected = sqlite_bag(inst, snapshot)
                optimum = min(dot(c, world) for _, c in exact['plans'])
                order = POLICIES[(repeat + window) % 3:] + POLICIES[:(repeat + window) % 3]
                for policy in order:
                    if policy == 'robust':
                        (frozen, revealed), membership = timed(
                            lambda: robust.open_window(window, inst, snapshot, packet))
                        robust.require_active()
                        plan, engine = robust.plan, rengine
                    else:
                        (frozen, revealed), membership = timed(
                            lambda: checked_window(inst, snapshot, packet))
                        plan, engine = fixed, fengine
                    state = states[policy]
                    add(state, membership)
                    state['membership_wall_s'] += membership['wall_s']
                    selection = {'wall_s': 0.0, 'cpu_s': 0.0}
                    if policy == 'adaptive':
                        def select():
                            p = known_world_plan(inst, h, revealed)
                            return p, HashPlan(inst, p)
                        (plan, engine), selection = timed(select)
                        add(state, selection)
                        state['selection_wall_s'] += selection['wall_s']
                        state['selection_calls'] += 1
                    realized_cost = dot(plan_cost(as_plan(plan), h), world)
                    regret = realized_cost - optimum
                    assert 0 <= regret
                    if policy == 'robust':
                        assert regret <= cert['regret']
                    if policy == 'adaptive':
                        assert regret == 0
                    # Bag checks and count checks outside measured execution only.
                    rows, metrics = engine.execute(frozen)
                    assert Counter(rows) == expected
                    assert metrics['intermediate_rows'] == realized_cost
                    for mask, count in metrics['internal_counts'].items():
                        assert count == dot(h[mask], world)
                    del rows
                    def execute_batch():
                        for _ in range(queries):
                            rows, stats = engine.execute(frozen)
                            del rows
                        return stats
                    _, execution = timed(execute_batch)
                    add(state, execution)
                    state['execution_wall_s'] += execution['wall_s']
                    state['intermediate_rows'] += queries * realized_cost
                    state['max_per_query_regret'] = max(state['max_per_query_regret'], regret)
                    all_rounds.append({'scenario': scenario, 'repeat': repeat, 'window': window,
                                       'world': world, 'queries': queries, 'policy': policy,
                                       'plan': plan, 'cost': realized_cost, 'oracle_cost': optimum,
                                       'regret': regret, 'metrics': metrics,
                                       'membership': membership, 'selection': selection,
                                       'execution': execution})
            assert robust.plan_checks == 1 and robust.membership_checks == 24
            for policy in POLICIES:
                all_runs.append({'scenario': scenario, 'repeat': repeat, 'policy': policy,
                                 'shared_snapshot_acquisition_wall_s': acquired,
                                 'total_with_acquisition_wall_s': states[policy]['wall_s'] + acquired,
                                 **states[policy]})
    summary = {'scope': 'Synthetic positive-output hash joins, not JOB or a DBMS benchmark.',
               'python': sys.version, 'platform': platform.platform(),
               'repeats': repeats, 'windows_per_run': 24, 'queries_per_run': 216,
               'certified_regret': 2048, 'checked_plan_sessions': 3 * repeats,
               'bag_checked_policy_windows': len(all_rounds),
               'physical_query_executions': sum(r['queries'] for r in all_rounds),
               'excluded_from_policy_time': 'Initial and future snapshot generation (reported separately), SQL/oracle/bag validation, output serialization; no disk capture or deployment cost measured.',
               'scenarios': {}}
    for scenario in ('stationary', 'migration', 'bursts'):
        summary['scenarios'][scenario] = {}
        for policy in POLICIES:
            group = [r for r in all_runs if r['scenario'] == scenario and r['policy'] == policy]
            summary['scenarios'][scenario][policy] = {
                k: statistics.median(r[k] for r in group)
                for k in ('wall_s', 'cpu_s', 'setup_wall_s', 'membership_wall_s',
                          'selection_wall_s', 'execution_wall_s', 'intermediate_rows',
                          'max_per_query_regret', 'selection_calls', 'total_with_acquisition_wall_s')}
            summary['scenarios'][scenario][policy]['wall_s_min'] = min(r['wall_s'] for r in group)
            summary['scenarios'][scenario][policy]['wall_s_max'] = max(r['wall_s'] for r in group)
    for name, value in (('contract.json', inst), ('certificate.json', cert),
                        ('rounds.json', all_rounds), ('runs.json', all_runs), ('summary.json', summary)):
        payload = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode('utf-8')
        if name == 'rounds.json':
            (output / (name + '.gz')).write_bytes(gzip.compress(payload, mtime=0))
        else:
            (output / name).write_bytes(payload)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error('repeats must be 1..5')
    print(json.dumps(run(args.output, args.repeats), indent=2, sort_keys=True))
