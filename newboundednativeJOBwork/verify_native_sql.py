#!/usr/bin/env python3
"""Offline reconciliation of the selected native SQL evidence; never retimes.

This post-run analysis is not an execution snapshot source. It checks retained
numbers, model/trace relationships, and original source/input identities. The
unbundled upstream SQL is neither downloaded nor reexecuted by this verifier.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import checker
from src.attestation import campaign_worlds
from src.model import as_plan, block_profile, dot, mask, plan_cost
from src.physical import sqlite_bag
from src.reuse import known_world_plan
from native_sql import SqlTree
from job3b import contract as fixture_contract, instantiate as fixture_instantiate
from experiment import schedules

POLICIES = ('robust', 'known_fixed', 'adaptive', 'sqlite_optimizer')
SCENARIOS = ('stationary', 'migration', 'bursts')
EXECUTED = {'newboundednativeJOBwork/experiment.py', 'newboundednativeJOBwork/native_sql.py',
    'newboundednativeJOBwork/job3b.py', 'attest.py', 'checker.py', 'src/attestation.py',
    'src/model.py', 'src/optimizer.py', 'src/physical.py', 'src/reuse.py'}
ANALYSIS = ['newboundednativeJOBwork/verify_native_sql.py', 'regressions/test_native_sql_reconciliation.py']
ASSETS = {'completion.json', 'environment.json', 'job3b-authored-execution.json',
    'native-certificate.json', 'native-contract.json', 'native-rounds.json.gz', 'native-runs.json',
    'native-summary.json', 'official-source-receipt.json', 'supplied-inputs.json.gz',
    'supplied-validation.json.gz', 'validation-summary.json', 'measurement-receipt.json.gz',
    'execution-source-map.json'}
TEXT_IDENTITY = 'utf8-strict-crlf-to-lf-only-v1'
BINARY_IDENTITY = 'binary-exact-v1'
CONSUMED_SOURCES = {'src/optimizer.py': 'results/native-executed-src/optimizer.py'}


class ReconciliationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReconciliationError(message)


def safe_path(base, name):
    require(type(name) is str and '\\' not in name, 'expected artifact-relative POSIX path')
    p = PurePosixPath(name)
    require(name and not p.is_absolute() and '..' not in p.parts and ':' not in name,
            'unsafe evidence/source path')
    resolved = (base / name).resolve()
    require(resolved.is_relative_to(base.resolve()), 'source/evidence path escapes root')
    return resolved


def read_json(path):
    require(path.is_file() and path.stat().st_size <= 16 * 1024**2, 'missing/oversized evidence asset')
    data = path.read_bytes()
    if path.name.endswith('.gz'):
        with gzip.open(path, 'rb') as stream:
            data = stream.read(16 * 1024**2 + 1)
    require(len(data) <= 16 * 1024**2, 'expanded evidence byte budget')
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate evidence JSON key')
            result[k] = v
        return result
    def constant(value):
        raise ReconciliationError('nonfinite JSON constant: ' + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def clean(value):
    if isinstance(value, dict):
        require('query_3b_sql' not in value, 'upstream SQL text must not be bundled')
        for child in value.values():
            clean(child)
    elif isinstance(value, list):
        for child in value:
            clean(child)
    elif isinstance(value, str):
        require(not re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]', value), 'private absolute path in evidence')
        require(not any(s in value for s in ('branch_handoffs', 'remaining-evidence',
                                           'SELECT MIN(t.title)', '/Users/', '/home/')),
                'private coordination/path or upstream query text in evidence')
    elif type(value) in (int, float):
        require(math.isfinite(value), 'nonfinite evidence number')


def shape(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), 'unexpected fields: ' + label)


def duration(value):
    shape(value, ('wall_s', 'cpu_s'), 'stage timing')
    require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in value.values()),
            'invalid stage CPU/wall observation')


def integers(record, fields, nullable=False):
    require(all(type(record[k]) is int or (nullable and record[k] is None) for k in fields),
            'expected exact evidence integers, not booleans/floats')


def normalized_digest(data):
    try:
        normalized = data.decode('utf-8', errors='strict').replace('\r\n', '\n').encode('utf-8')
    except UnicodeDecodeError as exc:
        raise ReconciliationError('declared UTF-8 identity contains non-UTF-8 bytes') from exc
    return hashlib.sha256(normalized).hexdigest()


def identity_matches(data, binding, raw_key, normalized_key, compressed=False):
    policy = binding.get('identity_policy')
    require(policy == (BINARY_IDENTITY if compressed else TEXT_IDENTITY), 'undeclared/unsupported identity normalization')
    raw = hashlib.sha256(data).hexdigest()
    if compressed:
        require(normalized_key not in binding, 'compressed assets must remain binary-only')
        return raw == binding[raw_key]
    require(re.fullmatch('[0-9a-f]{64}', binding.get(normalized_key, '')), 'missing normalized snapshot digest')
    # Normalize even exact raw matches, checking consistency of both declared
    # identities. No trimming, BOM removal, lone-CR mapping, or JSON rewriting.
    normalized = normalized_digest(data)
    return normalized == binding[normalized_key]


def equal_plan(p, q):
    return as_plan(p) == as_plan(q)


def tree_counts(inst, plan, profiles, world, metrics, explain):
    fields = ('internal_counts', 'intermediate_rows', 'output_rows', 'explain')
    shape(metrics, fields, 'native materialization metrics')
    tree = SqlTree(inst, plan)
    expected = {str(m): dot(profiles[m], world) for m, _, _ in tree.nodes}
    require(type(metrics['internal_counts']) is dict and all(type(v) is int and v >= 0
            for v in metrics['internal_counts'].values()) and type(metrics['intermediate_rows']) is int
            and type(metrics['output_rows']) is int, 'expected exact native count integers')
    require(metrics['internal_counts'] == expected, 'native node count/profile mismatch')
    require(metrics['intermediate_rows'] == sum(expected.values()), 'native intermediate work mismatch')
    require(metrics['output_rows'] == dot(profiles[(1 << inst['n']) - 1], world), 'native final count mismatch')
    if not explain:
        require(metrics['explain'] == [], 'unexpected supplied trace explanation')
        return
    require(len(metrics['explain']) == len(tree.nodes), 'incomplete materialization trace')
    emitted = 0
    for (m, _, select), record in zip(tree.nodes, metrics['explain']):
        shape(record, ('mask', 'sql', 'eqp'), 'CTAS trace')
        require(record['mask'] == m and record['sql'] == select + f' LIMIT {200000 - emitted + 1}',
                'native SQL trace does not match committed tree/budget')
        emitted += expected[str(m)]
        eqp(record['eqp'])


def eqp(records):
    require(type(records) is list and records, 'missing native EXPLAIN receipt')
    require(all(type(r) is list and len(r) == 4 and all(type(x) is int for x in r[:3])
                and type(r[3]) is str for r in records), 'invalid native EXPLAIN record')


def natural_sql(inst):
    n = inst['n']
    return ('SELECT ' + ','.join(f'r{i}.tid{i}' for i in range(n)) + ' FROM ' +
            ','.join(f'r{i}' for i in range(n)) + ' WHERE ' + ' AND '.join(
                f'r{a}.key{a}_{e}=r{b}.key{b}_{e} COLLATE BINARY'
                for e, (a, b) in enumerate(inst['edges'])) + ' LIMIT 200001')


def expected_plan(inst, certificate, profiles, world, policy, initial):
    if policy == 'robust':
        return certificate['states'][str((1 << inst['n']) - 1)]['plans'][certificate['selected']]
    return known_world_plan(inst, profiles, initial if policy == 'known_fixed' else world)


def verify(evidence=ROOT / 'results/native-sql', artifact_root=ROOT):
    evidence, artifact_root = Path(evidence).resolve(), Path(artifact_root).resolve()
    manifest = read_json(evidence / 'reconciliation-map.json')
    require(manifest['schema_version'] == 1 and manifest['full_JOB_validation'] is False, 'manifest scope/schema')
    require(set(manifest['assets']) == ASSETS, 'incomplete/extra adoption manifest assets')
    require(manifest['identity_normalization']['rule'] == TEXT_IDENTITY and
            manifest['identity_normalization']['encoding'] == 'UTF-8 strict; BOM preserved' and
            manifest['identity_normalization']['text_mapping'] == 'Replace CRLF pairs by LF only. Preserve lone CR, all other whitespace, content and final newline.' and
            manifest['identity_normalization']['compressed_policy'] == 'binary-exact-v1; never decompress or normalize for identity comparison',
            'manifest normalization rule')
    require(set(p.name for p in evidence.iterdir()) <= ASSETS | {'reconciliation-map.json',
                                                              'reconciliation-receipt.json'}, 'unexpected public evidence file')
    data = {}
    for name, binding in manifest['assets'].items():
        path = safe_path(evidence, name)
        require(identity_matches(path.read_bytes(), binding, 'public_sha256', 'normalized_public_sha256',
                                 compressed=name.endswith('.gz')),
                'public asset digest mismatch: ' + name)
        if binding['adoption'] == 'byte_exact':
            require(binding['execution_raw_sha256'] == binding['public_sha256'], 'raw/public exact binding mismatch')
        data[name] = read_json(path)
        clean(data[name])
    source_map = data['execution-source-map.json']
    require(source_map['schema_version'] == 1 and source_map['unchanged_before_after'] is True,
            'execution snapshot identity changed')
    require(source_map['postrun_analysis_not_execution_bound'] == ANALYSIS, 'post-run analysis binding mislabeled')
    require(source_map['identity_normalization'] == manifest['identity_normalization'], 'source/asset normalization declarations differ')
    files = source_map['files']
    require(len(files) == source_map['identity_entries'] == 301, 'execution identity inventory mismatch')
    require({p for p, v in files.items() if v['role'] == 'executed_source'} == EXECUTED,
            'executed source set includes post-run/unexecuted analysis or omits a dependency')
    current_source_differences = []
    for path, binding in files.items():
        require(binding['role'] in ('executed_source', 'execution_input', 'observed_only_source'), 'source role')
        require(re.fullmatch('[0-9a-f]{64}', binding['before_sha256']) and
                binding['before_sha256'] == binding['after_sha256'], 'before/after source identity mismatch')
        actual = safe_path(artifact_root, CONSUMED_SOURCES.get(path, path))
        if binding['role'] != 'observed_only_source':
            compressed = path.endswith(('.gz', '.tgz', '.zip'))
            if not compressed:
                require(binding['normalized_before_sha256'] == binding['normalized_after_sha256'],
                        'normalized before/after snapshot differs')
            require(actual.is_file() and identity_matches(actual.read_bytes(), binding,
                    'before_sha256', 'normalized_before_sha256', compressed=compressed),
                    'execution source/input changed: ' + path)
            if path in CONSUMED_SOURCES:
                current = safe_path(artifact_root, path)
                require(current.is_file(), 'current source is missing: ' + path)
                if not identity_matches(current.read_bytes(), binding,
                        'before_sha256', 'normalized_before_sha256'):
                    current_source_differences.append(path)
    require(all(p not in files for p in ANALYSIS), 'post-run code falsely attributed to execution snapshot')

    inst, cert = data['native-contract.json'], data['native-certificate.json']
    checker.verify(inst, cert)
    h = block_profile(inst)
    rounds, runs, summary = data['native-rounds.json.gz'], data['native-runs.json'], data['native-summary.json']
    require(len(rounds) == 864 and len(runs) == 36, 'missing/extra policy-window or run records')
    indexed = {}
    for r in rounds:
        shape(r, ('scenario', 'repeat', 'window', 'world', 'queries', 'policy', 'plan', 'cost',
                  'oracle_cost', 'regret', 'load', 'selection', 'execution', 'loaded_rows',
                  'membership_checks', 'validation_metrics'), 'native window')
        key = (r['scenario'], r['repeat'], r['window'], r['policy'])
        require(key not in indexed, 'duplicate native policy-window')
        indexed[key] = r
        require(r['scenario'] in SCENARIOS and type(r['repeat']) is int and 0 <= r['repeat'] < 3
                and type(r['window']) is int and 1 <= r['window'] <= 24 and r['policy'] in POLICIES,
                'invalid native policy-window identity')
        world, queries = schedules(r['scenario'])[r['window'] - 1]
        require(type(r['world']) is list and all(type(v) is int for v in r['world']), 'exact integer world')
        require(r['world'] == world and r['queries'] == queries, 'schedule/world/query demand mismatch')
        require(type(r['queries']) is int and type(r['loaded_rows']) is int and type(r['membership_checks']) is int,
                'expected exact window denominator integers')
        require(r['loaded_rows'] == 992 and r['membership_checks'] == 2, 'native SQL loading/membership count')
        for stage in ('load', 'selection', 'execution'):
            duration(r[stage])
        oracle = known_world_plan(inst, h, world)
        oracle_cost = dot(plan_cost(oracle, h), world)
        require(r['oracle_cost'] == oracle_cost, 'known-world oracle cost mismatch')
        if r['policy'] == 'sqlite_optimizer':
            require(r['plan'] is None and r['cost'] is None and r['regret'] is None,
                    'ordinary SQL has fabricated cardinality plan/cost/regret')
            shape(r['validation_metrics'], ('output_rows', 'sql', 'eqp'), 'ordinary SQL metrics')
            require(r['validation_metrics']['sql'] == natural_sql(inst), 'ordinary SQL trace mismatch')
            require(r['validation_metrics']['output_rows'] == 16384, 'ordinary SQL output count')
            eqp(r['validation_metrics']['eqp'])
        else:
            require(all(type(r[k]) is int for k in ('cost', 'oracle_cost', 'regret')), 'expected exact native cost integers')
            p = expected_plan(inst, cert, h, world, r['policy'], [24, 8])
            require(equal_plan(r['plan'], p), 'fixed/adaptive plan violates information boundary')
            cost = dot(plan_cost(as_plan(r['plan']), h), world)
            require(r['cost'] == cost and r['regret'] == cost - oracle_cost, 'native cost/regret mismatch')
            require(0 <= r['regret'] <= cert['regret'] if r['policy'] == 'robust' else r['regret'] >= 0,
                    'native regret violates bound')
            if r['policy'] == 'adaptive':
                require(r['regret'] == 0, 'adaptive cost is not the revealed-world optimum')
            tree_counts(inst, r['plan'], h, world, r['validation_metrics'], True)

    run_keys = set()
    for run in runs:
        shape(run, ('scenario', 'repeat', 'policy', 'snapshot_acquisition_wall_s', 'wall_with_acquisition_s',
                    'wall_s', 'cpu_s', 'setup_wall_s', 'membership_load_wall_s', 'selection_wall_s',
                    'execution_wall_s', 'queries', 'selection_calls', 'max_per_query_regret',
                    'abstract_intermediate_rows'), 'native run')
        key = run['scenario'], run['repeat'], run['policy']
        integers(run, ('repeat', 'queries', 'selection_calls'))
        integers(run, ('abstract_intermediate_rows', 'max_per_query_regret'), nullable=True)
        require(key not in run_keys, 'duplicate native run')
        run_keys.add(key)
        group = [indexed[(key[0], key[1], w, key[2])] for w in range(1, 25)]
        require(run['queries'] == sum(r['queries'] for r in group) == 216, 'run query denominator')
        for run_field, window_field in (('membership_load_wall_s', 'load'),
                                        ('selection_wall_s', 'selection'), ('execution_wall_s', 'execution')):
            require(math.isclose(run[run_field], sum(r[window_field]['wall_s'] for r in group), abs_tol=1e-8),
                    'run stage aggregation mismatch: ' + run_field)
        require(math.isclose(run['wall_s'], sum(run[k] for k in ('setup_wall_s', 'membership_load_wall_s',
            'selection_wall_s', 'execution_wall_s')), abs_tol=1e-8), 'run total excludes a charged phase')
        require(math.isclose(run['wall_with_acquisition_s'], run['wall_s'] + run['snapshot_acquisition_wall_s'],
                             abs_tol=1e-8), 'acquisition-inclusive wall mismatch')
        require(run['cpu_s'] >= 0 and run['setup_wall_s'] >= 0 and run['snapshot_acquisition_wall_s'] >= 0,
                'negative run CPU/setup/acquisition observation')
        require(run['selection_calls'] == (24 if key[2] == 'adaptive' else 0 if key[2] == 'sqlite_optimizer' else 1),
                'selection-call denominator')
        if key[2] == 'sqlite_optimizer':
            require(run['abstract_intermediate_rows'] is None and run['max_per_query_regret'] is None,
                    'ordinary SQL fabricated work/regret')
        else:
            require(run['abstract_intermediate_rows'] == sum(r['cost'] * r['queries'] for r in group) and
                    run['max_per_query_regret'] == max(r['regret'] for r in group), 'run work/regret aggregation')
    require(summary['repeats'] == 3 and summary['windows_per_run'] == 24 and
            summary['queries_per_policy_run'] == 216 and summary['certified_regret'] == cert['regret'] == 2048
            and summary['validated_policy_windows'] == len(rounds) and
            summary['timed_native_queries'] == sum(r['queries'] for r in rounds) == 7776, 'summary denominators')
    require(set(summary['policies']) == set(SCENARIOS), 'summary schedule set')
    for scenario, policies in summary['policies'].items():
        require(set(policies) == set(POLICIES), 'summary policy set')
        for policy, row in policies.items():
            group = [r for r in runs if r['scenario'] == scenario and r['policy'] == policy]
            require(len(group) == 3, 'summary repeat coverage')
            for key, value in row.items():
                expected = min(r['wall_s'] for r in group) if key == 'wall_s_min' else max(
                    r['wall_s'] for r in group) if key == 'wall_s_max' else None if group[0][key] is None else statistics.median(r[key] for r in group)
                require(value == expected, 'summary median/range mismatch: ' + key)

    supplied, validations = data['supplied-inputs.json.gz'], data['supplied-validation.json.gz']
    require(len(supplied) == 122 and len(validations) == 1464, 'supplied case/execution denominator')
    cases, expected_inputs = {}, {'newboundednativeJOBwork/authored_job3b.json', 'results/reuse/contract.json'}
    for item in supplied:
        shape(item, ('path', 'contract', 'certificate'), 'supplied input binding')
        path = item['path']
        require(path.startswith('inputs/') or path.startswith('results/topology/inputs/'), 'supplied input provenance path')
        cp = ('results/campaign/certificates/' if path.startswith('inputs/') else 'results/topology/certificates/') + PurePosixPath(path).name
        expected_inputs.update((path, cp))
        require(read_json(safe_path(artifact_root, path)) == item['contract'] and
                read_json(safe_path(artifact_root, cp)) == item['certificate'], 'supplied input/certificate differs from consumed snapshot')
        checker.verify(item['contract'], item['certificate'])
        name = item['contract']['name']
        require(name not in cases, 'duplicate supplied contract')
        cases[name] = (item, block_profile(item['contract']), campaign_worlds(item['contract']))
    require({p for p, b in files.items() if b['role'] == 'execution_input'} == expected_inputs,
            'consumed input source map incomplete/overbroad')
    seen = set()
    for r in validations:
        require(r['case'] in cases and r['policy'] in POLICIES, 'unknown supplied case/policy')
        item, profiles, worlds = cases[r['case']]
        c, certificate = item['contract'], item['certificate']
        k = r['case'], r['window'], r['policy']
        require(k not in seen and type(r['window']) is int and 0 <= r['window'] < len(worlds), 'supplied window duplicate/identity')
        seen.add(k)
        require(r['world'] == worlds[r['window']], 'supplied world differs from frozen construction')
        require(type(r['world']) is list and all(type(v) is int for v in r['world']), 'exact supplied integer world')
        integers(r, ('window', 'output_rows'))
        require(r['scope'] == ('primary-supplied' if item['path'].startswith('inputs/') else 'synthetic-JOB-topology'), 'supplied topology mislabeled as JOB data')
        if r['policy'] == 'sqlite_optimizer':
            shape(r, ('case', 'scope', 'window', 'world', 'policy', 'output_rows', 'sql', 'eqp', 'abstract_cost'), 'supplied ordinary SQL')
            require(r['abstract_cost'] is None and r['eqp'] == [] and r['sql'] == natural_sql(c), 'supplied ordinary SQL trace/cost')
        else:
            shape(r, ('case', 'scope', 'window', 'world', 'policy', 'plan', 'cost', 'oracle_cost', 'regret',
                      'certified_regret', 'internal_counts', 'intermediate_rows', 'output_rows', 'explain',
                      'loaded_rows', 'membership_checks'), 'supplied native tree')
            integers(r, ('cost', 'oracle_cost', 'regret', 'certified_regret', 'loaded_rows', 'membership_checks'))
            p = expected_plan(c, certificate, profiles, r['world'], r['policy'], worlds[0])
            require(equal_plan(r['plan'], p), 'supplied plan information-boundary mismatch')
            cost = dot(plan_cost(as_plan(p), profiles), r['world'])
            optimum = dot(plan_cost(known_world_plan(c, profiles, r['world']), profiles), r['world'])
            require(r['cost'] == cost and r['oracle_cost'] == optimum and r['regret'] == cost - optimum
                    and r['certified_regret'] == certificate['regret'], 'supplied exact cost/regret mismatch')
            require(r['membership_checks'] == 2 and r['loaded_rows'] == sum(
                count * sum(len(rows) for rows in block) for count, block in zip(r['world'], c['blocks'])), 'supplied row loading/membership count')
            if r['policy'] == 'robust':
                require(0 <= r['regret'] <= certificate['regret'], 'supplied robust bound')
            tree_counts(c, p, profiles, r['world'], {k: r[k] for k in
                        ('internal_counts', 'intermediate_rows', 'output_rows', 'explain')}, False)
        require(r['output_rows'] == dot(profiles[(1 << c['n']) - 1], r['world']), 'supplied final output count')
    expected_validation = {'contracts': 122, 'primary_contracts': 102, 'topology_contracts': 20,
        'snapshots': 366, 'native_bag_executions': 1464, 'materialized_tree_executions': 1098,
        'all_bags_and_counts_match': True, 'full_JOB_validation': False}
    require(data['validation-summary.json'] == expected_validation, 'validation summary population mismatch')
    require(sum(item['path'].startswith('inputs/') for item in supplied) == 102 and len(seen) == 1464,
            'validation scope/coverage mismatch')

    fixture = read_json(artifact_root / 'newboundednativeJOBwork/authored_job3b.json')
    job, official = data['job3b-authored-execution.json'], data['official-source-receipt.json']
    require(job['contract'] == fixture_contract(fixture) and job['fixture_provenance'] == fixture['provenance'], 'authored fixture identity/provenance mismatch')
    checker.verify(job['contract'], job['certificate'])
    jh = block_profile(job['contract'])
    require(job['template_profiles'] == {str(k): list(v) for k, v in jh.items()} and job['certified_regret'] == 0,
            'authored fixture profiles/regret mismatch')
    require(job['official_source'] == {k: official[k] for k in ('query_3b_origin', 'query_3b_path', 'query_3b_sha256')}, 'unbundled upstream query identity mismatch')
    require(official['imdb_downloaded'] is False and official['query_count'] == 113 and
            official['headers']['imdb']['content_length'] == 1263193115, 'IMDb/workload provenance changed')
    require(len(job['windows']) == 2, 'authored fixture window coverage')
    for number, window in enumerate(job['windows']):
        world = [3, 0] if number == 0 else [0, 3]
        jc, tables, snapshot, packet = fixture_instantiate(fixture, world)
        reference = sqlite_bag(jc, snapshot)
        payload = [row[1] for row in tables['title'] if row[2] > 2010]
        aggregate = [[min((payload[row[3]] for row in reference), default=None)]]
        require(window['world'] == world and window['official_result'] == aggregate and
                window['preaggregation_rows'] == sum(reference.values()) == 6, 'authored aggregate/bag record mismatch')
        require(set(window['policies']) == set(POLICIES[:-1]), 'authored fixture policy coverage')
        for policy, recorded in window['policies'].items():
            require(recorded['result'] == aggregate, 'authored policy result mismatch')
            p = expected_plan(jc, job['certificate'], jh, world, policy, [3, 0])
            require(equal_plan(recorded['plan'], p), 'authored plan selection mismatch')
            tree_counts(jc, p, jh, world, {k: recorded[k] for k in
                        ('internal_counts', 'intermediate_rows', 'output_rows', 'explain')}, True)

    measurement, completion = data['measurement-receipt.json.gz'], data['completion.json']
    require(measurement['exit_code'] == 0 and measurement['same_identity_before_after'] is True and
            measurement['identity_changes'] == [] and measurement['execution_source_map'] == 'execution-source-map.json', 'measurement completion/source binding')
    samples = measurement['samples']
    require(samples and [r['elapsed_s'] for r in samples] == sorted(r['elapsed_s'] for r in samples), 'memory sample chronology')
    for sample in samples:
        shape(sample, ('elapsed_s', 'working_set_bytes', 'peak_working_set_bytes', 'private_pagefile_bytes'), 'memory sample')
        require(0 <= sample['elapsed_s'] <= measurement['elapsed_wall_s'] and 0 <= sample['working_set_bytes'] <= sample['peak_working_set_bytes'] and sample['private_pagefile_bytes'] >= 0, 'invalid sampled process resource observation')
    require(measurement['peak_working_set_bytes'] == max(r['peak_working_set_bytes'] for r in samples), 'sampled peak reconciliation')
    require(completion['complete'] is True and completion['full_JOB_validation'] is False and
            completion['authored_job3b_passed'] is True and completion['validation'] == expected_validation and
            completion['timed_native_queries'] == 7776 and completion['wall_elapsed_s'] <= measurement['elapsed_wall_s'], 'completion scope/denominators')
    result = {'schema_version': 1, 'verified': True, 'verification': 'offline post-run reconciliation; no retiming or network',
        'execution_sources_bound': 10, 'execution_inputs_bound': 246, 'observed_only_sources': 45,
        'identity_snapshot_entries': 301, 'policy_windows': 864, 'timed_queries_retained': 7776,
        'supplied_contracts': 122, 'supplied_snapshots': 366, 'supplied_native_bag_records': 1464,
        'authored_fixture_windows_reconciled': 2, 'upstream_SQL_reexecuted': False, 'full_JOB_validation': False,
        'declared_text_identity': TEXT_IDENTITY, 'compressed_assets_binary_exact': 4,
        'analysis_files_not_in_execution_snapshot': ANALYSIS,
        'limit': 'Reconciliation checks consistency and recorded source/input identity, not authenticated historical execution, latency guarantees or real IMDb applicability.'}
    retained_receipt = evidence / 'reconciliation-receipt.json'
    if retained_receipt.exists():
        retained = read_json(retained_receipt)
        clean(retained)
        require(retained == result, 'retained reconciliation receipt differs from current reconciliation')
    # The retained receipt describes the selected execution, not later guards.
    # Validate it above before adding current-vs-consumed source information.
    result['consumed_source_locations'] = CONSUMED_SOURCES
    result['current_source_differences'] = current_source_differences
    result['all_current_sources_retimed'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'results/native-sql')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        verdict = verify(args.evidence)
        if args.output:
            with args.output.open('x', encoding='utf-8') as f:
                json.dump(verdict, f, indent=2, sort_keys=True)
                f.write('\n')
        print(json.dumps(verdict, indent=2, sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        print(json.dumps({'verified': False, 'reason': str(exc)}))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
