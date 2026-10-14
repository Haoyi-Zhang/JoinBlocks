#!/usr/bin/env python3
"""Bounded native SQL bridge, current receipts, and fair fixed/adaptive costs.

Run timings through the shared measurement protocol. No full JOB claim. Only
the tiny official query archive is fetched; no IMDb data is downloaded.
Original code/fixture are MIT under ../LICENSE, not the upstream SQL or IMDb.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import sys
import tarfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from src.attestation import campaign_worlds, materialize_attestation
from src.model import as_plan, block_profile, dot, plan_cost
from src.optimizer import optimize
from src.physical import sqlite_bag
from src.reuse import ReuseSession, known_world_plan
from native_sql import SqlTree, SqlWindow, bag
from job3b import run_fixture

POLICIES = ('robust', 'known_fixed', 'adaptive', 'sqlite_optimizer')


def timed(fn):
    wall, cpu = time.perf_counter(), time.process_time()
    result = fn()
    return result, {'wall_s': time.perf_counter() - wall, 'cpu_s': time.process_time() - cpu}


def save(output, name, value):
    payload = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    if name.endswith('.gz'):
        payload = gzip.compress(payload, mtime=0)
    (output / name).write_bytes(payload)


def official_sources():
    start = time.perf_counter()
    urls = {name: f'https://event.cwi.nl/da/job/{name}.tgz' for name in ('job', 'imdb')}
    receipt = {'retrieved_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'headers': {}, 'imdb_downloaded': False,
               'imdb_blocker': 'Original 2013 dataset absent in scoped search; >500 MB needs main authorization. Current IMDb TSVs are not the original JOB schema/data.',
               'licensing': {
                   'author_readme': 'https://event.cwi.nl/da/job/readme.txt',
                   'imdb_official': 'https://data.imdb.com/non-commercial-datasets/',
                   'query_archive': 'No explicit redistribution license file found; fetched query remains private in execution receipt, not vendored in candidate.',
                   'data': 'CWI states optimizer research/engineering purpose and unanswered request to IMDb; do not treat public hosting as blanket redistribution permission.',
                   'native_engine': 'SQLite public domain: https://www.sqlite.org/copyright.html',
                   'own_inputs': 'Original authored fixture and supplied generated P111 bags: artifact/LICENSE (MIT).'}}
    for name, url in urls.items():
        request = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(request, timeout=30) as response:
            receipt['headers'][name] = {'url': url, 'status': response.status,
                'content_length': int(response.headers.get('Content-Length', 0)),
                'last_modified': response.headers.get('Last-Modified')}
    with urllib.request.urlopen(urls['job'], timeout=30) as response:
        data = response.read(200_001)
    if len(data) > 200_000:
        raise ValueError('official query archive exceeds bounded 200 kB fetch')
    archive = tarfile.open(fileobj=io.BytesIO(data), mode='r:gz')
    members = [m for m in archive.getmembers() if m.isfile() and '/._' not in m.name]
    if sum(m.size for m in members) > 2_000_000:
        raise ValueError('official SQL archive expansion budget')
    query = archive.extractfile('job/3b.sql').read().decode('utf-8')
    receipt.update({'archive_bytes': len(data), 'archive_sha256': hashlib.sha256(data).hexdigest(),
                    'query_count': sum(bool(re.fullmatch(r'job/\d+[a-z]\.sql', m.name)) for m in members),
                    'query_3b_sha256': hashlib.sha256(query.encode()).hexdigest(),
                    'query_3b_sql': query, 'query_3b_path': 'job/3b.sql',
                    'query_3b_origin': urls['job'],
                    'query_archive_license_files': [m.name for m in members if 'licen' in m.name.lower()],
                    'source_acquisition_wall_s': time.perf_counter() - start})
    return query, receipt


def validate_supplied(output):
    paths = [(p, ROOT / 'results/campaign/certificates' / p.name, 'primary-supplied')
             for p in sorted((ROOT / 'inputs').glob('*.json'))]
    paths += [(p, ROOT / 'results/topology/certificates' / p.name, 'synthetic-JOB-topology')
              for p in sorted((ROOT / 'results/topology/inputs').glob('*.json'))]
    records, assets = [], []
    for path, cert_path, scope in paths:
        inst, cert = json.loads(path.read_text()), json.loads(cert_path.read_text())
        session = ReuseSession(inst, cert)
        h = block_profile(inst)
        worlds = campaign_worlds(inst)
        fixed = known_world_plan(inst, h, worlds[0])
        engine = SqlWindow(inst)
        assets.append({'path': str(path), 'contract': inst, 'certificate': cert})
        try:
            for window, world in enumerate(worlds):
                snapshot, packet = materialize_attestation(inst, world, seed=window)
                frozen, revealed = session.open_window(window, inst, snapshot, packet)
                loaded, load_metrics = engine.open_window(window, inst, snapshot, packet)
                if loaded != revealed:
                    raise AssertionError('SQL/membership world mismatch')
                expected = sqlite_bag(inst, frozen)
                adaptive = known_world_plan(inst, h, revealed)
                oracle_cost = dot(plan_cost(as_plan(adaptive), h), revealed)
                for policy, plan in (('robust', session.plan), ('known_fixed', fixed),
                                     ('adaptive', adaptive)):
                    rows, metrics = engine.execute(SqlTree(inst, plan))
                    cost = dot(plan_cost(as_plan(plan), h), revealed)
                    if bag(rows) != expected or metrics['intermediate_rows'] != cost:
                        raise AssertionError('supplied SQL bag/cost mismatch')
                    if any(count != dot(h[mask], revealed) for mask, count in metrics['internal_counts'].items()):
                        raise AssertionError('supplied SQL internal-state mismatch')
                    regret = cost - oracle_cost
                    if regret < 0 or (policy == 'robust' and regret > cert['regret']):
                        raise AssertionError('supplied SQL regret violation')
                    records.append({'case': inst['name'], 'scope': scope, 'window': window,
                                    'world': world, 'policy': policy, 'plan': plan,
                                    'cost': cost, 'oracle_cost': oracle_cost, 'regret': regret,
                                    'certified_regret': cert['regret'], **metrics, **load_metrics})
                rows, metrics = engine.natural()
                if bag(rows) != expected:
                    raise AssertionError('supplied natural SQL bag mismatch')
                records.append({'case': inst['name'], 'scope': scope, 'window': window,
                                'world': world, 'policy': 'sqlite_optimizer', **metrics,
                                'abstract_cost': None})
        finally:
            engine.close()
    save(output, 'supplied-inputs.json.gz', assets)
    save(output, 'supplied-validation.json.gz', records)
    return {'contracts': len(paths), 'primary_contracts': sum(p[2] == 'primary-supplied' for p in paths),
            'topology_contracts': sum(p[2] == 'synthetic-JOB-topology' for p in paths),
            'snapshots': len(records) // 4, 'native_bag_executions': len(records),
            'materialized_tree_executions': sum(r['policy'] != 'sqlite_optimizer' for r in records),
            'all_bags_and_counts_match': True,
            'full_JOB_validation': False}


def schedules(kind):
    if kind == 'stationary':
        first = [24] * 24
    elif kind == 'migration':
        first = list(range(24, 7, -2)) + [8] * 4 + list(range(10, 25, 2)) + [24] * 3
    elif kind == 'bursts':
        first = [24] * 4 + [8] * 8 + [24] * 4 + [8] * 8
    else:
        raise ValueError(kind)
    return [([x, 32 - x], (4, 8, 16, 8)[i % 4]) for i, x in enumerate(first)]


def physical(output, repeats):
    inst = json.loads((ROOT / 'results/reuse/contract.json').read_text())
    rounds, runs = [], []
    for scenario in ('stationary', 'migration', 'bursts'):
        for repeat in range(repeats):
            h, profile_time = timed(lambda: block_profile(inst))
            (initial, packet), acquisition = timed(lambda: materialize_attestation(inst, [24, 8], seed=991))
            (cert, _, _), produce_time = timed(lambda: optimize(inst))
            session, check_time = timed(lambda: ReuseSession(inst, cert))
            fixed, fixed_time = timed(lambda: known_world_plan(inst, h, [24, 8]))
            states, engines, trees = {}, {}, {}
            acquisition_total = acquisition['wall_s']

            def charge(state, phase, t):
                state['wall_s'] += t['wall_s']
                state['cpu_s'] += t['cpu_s']
                state[phase + '_wall_s'] += t['wall_s']

            for policy in POLICIES:
                state = states[policy] = {key: 0 for key in ('wall_s', 'cpu_s', 'setup_wall_s',
                    'membership_load_wall_s', 'selection_wall_s', 'execution_wall_s', 'queries',
                    'selection_calls', 'max_per_query_regret', 'abstract_intermediate_rows')}
                # Native optimizer neither needs nor pays for our exact profiles.
                if policy != 'sqlite_optimizer':
                    charge(state, 'setup', profile_time)
                engine, setup = timed(lambda: SqlWindow(inst))
                engines[policy] = engine
                charge(state, 'setup', setup)
                (_, _), initial_load = timed(lambda: engine.open_window(0, inst, initial, packet))
                charge(state, 'setup', initial_load)
                if policy == 'robust':
                    charge(state, 'setup', produce_time)
                    charge(state, 'setup', check_time)
                    tree, installation = timed(lambda: SqlTree(inst, session.plan))
                    trees[policy] = tree
                    charge(state, 'setup', installation)
                    state['selection_calls'] = 1
                elif policy == 'known_fixed':
                    charge(state, 'setup', fixed_time)
                    tree, installation = timed(lambda: SqlTree(inst, fixed))
                    trees[policy] = tree
                    charge(state, 'setup', installation)
                    state['selection_calls'] = 1
                elif policy == 'sqlite_optimizer':
                    state['abstract_intermediate_rows'] = None
                    state['max_per_query_regret'] = None
            try:
                for window, (world, queries) in enumerate(schedules(scenario), start=1):
                    (snapshot, mapping), acquisition = timed(
                        lambda: materialize_attestation(inst, world, seed=1000 + window))
                    acquisition_total += acquisition['wall_s']
                    expected = sqlite_bag(inst, snapshot)  # untimed correctness reference
                    optimum_plan = known_world_plan(inst, h, world)
                    oracle_cost = dot(plan_cost(as_plan(optimum_plan), h), world)
                    shift = (window + repeat) % len(POLICIES)
                    for policy in POLICIES[shift:] + POLICIES[:shift]:
                        state, engine = states[policy], engines[policy]
                        (revealed, load_metrics), load = timed(
                            lambda: engine.open_window(window, inst, snapshot, mapping))
                        charge(state, 'membership_load', load)
                        selection = {'wall_s': 0, 'cpu_s': 0}
                        if policy == 'adaptive':
                            tree, selection = timed(lambda: SqlTree(inst, known_world_plan(inst, h, revealed)))
                            trees[policy] = tree
                            charge(state, 'selection', selection)
                            state['selection_calls'] += 1
                        tree = trees.get(policy)
                        if tree is None:
                            checked_rows, metrics = engine.natural(explain=True)
                            cost, regret = None, None
                        else:
                            checked_rows, metrics = engine.execute(tree, explain=True)
                            cost = dot(plan_cost(as_plan(tree.plan), h), revealed)
                            regret = cost - oracle_cost
                            if metrics['intermediate_rows'] != cost or any(
                                    value != dot(h[mask], revealed) for mask, value in metrics['internal_counts'].items()):
                                raise AssertionError('native physical node counts mismatch')
                            if regret < 0 or (policy == 'robust' and regret > cert['regret']):
                                raise AssertionError('native physical regret violation')
                            if policy == 'adaptive' and regret:
                                raise AssertionError('adaptive scalar cost is not known-world optimum')
                        if bag(checked_rows) != expected:
                            raise AssertionError('native physical bag mismatch')
                        del checked_rows

                        def batch():
                            for _ in range(queries):
                                rows, measured = engine.natural() if tree is None else engine.execute(tree)
                                del rows
                            return measured

                        _, execution = timed(batch)
                        charge(state, 'execution', execution)
                        state['queries'] += queries
                        if tree is not None:
                            state['abstract_intermediate_rows'] += cost * queries
                            state['max_per_query_regret'] = max(state['max_per_query_regret'], regret)
                        rounds.append({'scenario': scenario, 'repeat': repeat, 'window': window,
                            'world': world, 'queries': queries, 'policy': policy,
                            'plan': tree.plan if tree else None, 'cost': cost, 'oracle_cost': oracle_cost,
                            'regret': regret, 'load': load, 'selection': selection,
                            'execution': execution, **load_metrics, 'validation_metrics': metrics})
                for policy in POLICIES:
                    _, close_time = timed(engines[policy].close)
                    charge(states[policy], 'setup', close_time)
                    runs.append({'scenario': scenario, 'repeat': repeat, 'policy': policy,
                        'snapshot_acquisition_wall_s': acquisition_total,
                        'wall_with_acquisition_s': states[policy]['wall_s'] + acquisition_total,
                        **states[policy]})
                engines.clear()
                print(json.dumps({'completed': scenario, 'repeat': repeat,
                                  'policy_wall_s': {p: states[p]['wall_s'] for p in POLICIES}}), flush=True)
            finally:
                for engine in engines.values():
                    engine.close()
    summary = {'scope': 'Native SQLite on the real supplied positive-output synthetic P111 contract; not JOB data.',
        'policies': {}, 'repeats': repeats, 'windows_per_run': 24, 'queries_per_policy_run': 216,
        'validated_policy_windows': len(rounds), 'timed_native_queries': sum(r['queries'] for r in rounds),
        'certified_regret': cert['regret'], 'physical_binding': 'Separate native CTAS for every logical node, with EQP receipt; no cross-node flattening. Local binary physical order/index choice is SQLite\'s.',
        'cost_accounting': 'All SQL creation, two membership checks (input and SQL readback), row loading, materialized writes/count probes/cleanup, result fetch, scalar adaptation, and robust certificate/check are charged. Initial/future authored snapshot generation separately reported. Existing runtime; dependency install cost zero. No remote/network/storage durability/deployment capture costs measured.',
        'excluded': 'Offline SQL/oracle/bag validation, EXPLAIN inspection, serialization and source acquisition. Measurement-lock does not exclude unrelated OS applications; not CPU pinned; no latency-optimality inference.',
        'natural_baseline': 'Single native optimizer SELECT on the same row bags, same loading/membership. No exact-profile charge. Its physical intermediate count is unavailable, not assigned a model regret.'}
    for scenario in ('stationary', 'migration', 'bursts'):
        summary['policies'][scenario] = {}
        for policy in POLICIES:
            group = [r for r in runs if r['scenario'] == scenario and r['policy'] == policy]
            stats = {key: None if group[0][key] is None else statistics.median(r[key] for r in group)
                     for key in ('wall_s', 'cpu_s', 'setup_wall_s', 'membership_load_wall_s',
                                 'selection_wall_s', 'execution_wall_s', 'selection_calls',
                                 'abstract_intermediate_rows', 'max_per_query_regret', 'wall_with_acquisition_s')}
            stats.update({'wall_s_min': min(r['wall_s'] for r in group),
                          'wall_s_max': max(r['wall_s'] for r in group)})
            summary['policies'][scenario][policy] = stats
    save(output, 'native-contract.json', inst)
    save(output, 'native-certificate.json', cert)
    save(output, 'native-rounds.json.gz', rounds)
    save(output, 'native-runs.json', runs)
    save(output, 'native-summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3, choices=range(1, 6))
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('choose a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    save(output, 'environment.json', {'python': sys.version, 'executable': sys.executable,
        'platform': platform.platform(), 'sqlite': sqlite3.sqlite_version,
        'sqlite_compile_options': sqlite3.connect(':memory:').execute('PRAGMA compile_options').fetchall(),
        'runtime_dependencies': 'Python standard library, SQLite already bundled; no install/download of an engine.'})
    official_sql, sources = official_sources()
    save(output, 'official-source-receipt.json', sources)
    validation = validate_supplied(output)
    save(output, 'validation-summary.json', validation)
    print(json.dumps(validation), flush=True)
    fixture = json.loads((HERE / 'authored_job3b.json').read_text())
    job = run_fixture(fixture, official_sql, {k: sources[k] for k in (
        'query_3b_origin', 'query_3b_sha256', 'query_3b_path')})
    save(output, 'job3b-authored-execution.json', job)
    print(json.dumps({'authored_job3b': 'passed', 'certified_regret': job['certified_regret']}), flush=True)
    native = physical(output, args.repeats)
    save(output, 'completion.json', {'complete': True, 'full_JOB_validation': False,
        'wall_elapsed_s': time.perf_counter() - started, 'validation': validation,
        'authored_job3b_passed': True, 'timed_native_queries': native['timed_native_queries']})
    print(json.dumps(native, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
