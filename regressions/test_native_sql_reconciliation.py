"""Post-run offline reconciliation controls, separate from 15 native methods.

Some controls deliberately update a local asset digest after corrupting a copied
record to test arithmetic/provenance checks, rather than only byte integrity.
They do not edit executed source files or alter the retained selected evidence.
"""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'newboundednativeJOBwork'))
from verify_native_sql import ReconciliationError, normalized_digest, read_json, verify


class NativeReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p111-native-reconcile-')
        self.evidence = Path(self.temp.name) / 'evidence'
        shutil.copytree(ROOT / 'results/native-sql', self.evidence)

    def tearDown(self):
        self.temp.cleanup()

    def rewrite(self, name, value, rebind=True):
        data = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
        if name.endswith('.gz'):
            data = gzip.compress(data, mtime=0)
        (self.evidence / name).write_bytes(data)
        if rebind:
            manifest = read_json(self.evidence / 'reconciliation-map.json')
            binding = manifest['assets'][name]
            binding['public_sha256'] = hashlib.sha256(data).hexdigest()
            if not name.endswith('.gz'):
                binding['normalized_public_sha256'] = normalized_digest(data)
            if binding['adoption'] == 'byte_exact':
                binding['execution_raw_sha256'] = binding['public_sha256']
            (self.evidence / 'reconciliation-map.json').write_text(json.dumps(manifest))

    def test_current_evidence_reconciles_without_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden in reconciliation')):
            result = verify(self.evidence)
        self.assertTrue(result['verified'])
        self.assertEqual(result['timed_queries_retained'], 7776)
        self.assertEqual(result['execution_sources_bound'], 10)
        self.assertFalse(result['upstream_SQL_reexecuted'])
        self.assertFalse(result['full_JOB_validation'])

    def test_timing_byte_tamper_is_rejected(self):
        runs = read_json(self.evidence / 'native-runs.json')
        runs[0]['wall_s'] += 1
        self.rewrite('native-runs.json', runs, rebind=False)
        with self.assertRaisesRegex(ReconciliationError, 'digest mismatch'):
            verify(self.evidence)

    def test_dropping_an_unfavorable_repeat_is_rejected(self):
        runs = read_json(self.evidence / 'native-runs.json')
        worst = max((r for r in runs if r['policy'] == 'robust'), key=lambda r: r['wall_s'])
        runs.remove(worst)
        self.rewrite('native-runs.json', runs)
        with self.assertRaisesRegex(ReconciliationError, 'missing/extra'):
            verify(self.evidence)

    def test_favorable_replacement_median_is_rejected(self):
        summary = read_json(self.evidence / 'native-summary.json')
        summary['policies']['bursts']['robust']['wall_s'] = 0.0
        self.rewrite('native-summary.json', summary)
        with self.assertRaisesRegex(ReconciliationError, 'median/range mismatch'):
            verify(self.evidence)

    def test_omitting_charged_setup_from_total_is_rejected(self):
        runs = read_json(self.evidence / 'native-runs.json')
        runs[0]['wall_s'] -= runs[0]['setup_wall_s']
        self.rewrite('native-runs.json', runs)
        with self.assertRaisesRegex(ReconciliationError, 'charged phase'):
            verify(self.evidence)

    def test_fixed_policy_switch_after_revelation_is_rejected(self):
        rounds = read_json(self.evidence / 'native-rounds.json.gz')
        adaptive = next(r for r in rounds if r['scenario'] == 'bursts' and r['window'] == 5 and r['policy'] == 'adaptive')
        fixed = next(r for r in rounds if r['scenario'] == 'bursts' and r['window'] == 5 and r['policy'] == 'known_fixed')
        fixed['plan'] = deepcopy(adaptive['plan'])
        self.rewrite('native-rounds.json.gz', rounds)
        with self.assertRaisesRegex(ReconciliationError, 'information boundary'):
            verify(self.evidence)

    def test_postrun_verifier_cannot_be_execution_hashed(self):
        source = read_json(self.evidence / 'execution-source-map.json')
        observed = next(p for p, b in source['files'].items() if b['role'] == 'observed_only_source')
        source['files'].pop(observed)
        path = 'newboundednativeJOBwork/verify_native_sql.py'
        h = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        source['files'][path] = {'role': 'executed_source', 'before_sha256': h, 'after_sha256': h}
        self.rewrite('execution-source-map.json', source)
        with self.assertRaisesRegex(ReconciliationError, 'post-run/unexecuted analysis'):
            verify(self.evidence)

    def test_changed_consumed_input_is_rejected(self):
        inputs = read_json(self.evidence / 'supplied-inputs.json.gz')
        inputs[0]['contract']['total'] -= 1
        self.rewrite('supplied-inputs.json.gz', inputs)
        with self.assertRaisesRegex(ReconciliationError, 'consumed snapshot'):
            verify(self.evidence)
        self.rewrite('supplied-inputs.json.gz', read_json(ROOT / 'results/native-sql/supplied-inputs.json.gz'))
        records = read_json(self.evidence / 'supplied-validation.json.gz')
        zero = next(r for r in records if r['policy'] != 'sqlite_optimizer' and r['regret'] == 0)
        zero['regret'] = False
        self.rewrite('supplied-validation.json.gz', records)
        with self.assertRaisesRegex(ReconciliationError, 'exact evidence integers'):
            verify(self.evidence)

    def test_authored_result_and_scope_cannot_be_replaced(self):
        job = read_json(self.evidence / 'job3b-authored-execution.json')
        job['windows'][0]['official_result'] = [['Another authored title']]
        self.rewrite('job3b-authored-execution.json', job)
        with self.assertRaisesRegex(ReconciliationError, 'authored aggregate/bag'):
            verify(self.evidence)

    def test_private_path_and_unbundled_query_fields_are_rejected(self):
        environment = read_json(self.evidence / 'environment.json')
        environment['executable'] = 'D:/private/runtime/python.exe'
        self.rewrite('environment.json', environment)
        with self.assertRaisesRegex(ReconciliationError, 'private absolute path'):
            verify(self.evidence)
        environment.pop('executable')
        self.rewrite('environment.json', environment)
        source = read_json(self.evidence / 'official-source-receipt.json')
        source['query_3b_sql'] = 'Excluded upstream text placeholder, not an actual query.'
        self.rewrite('official-source-receipt.json', source)
        with self.assertRaisesRegex(ReconciliationError, 'upstream SQL text'):
            verify(self.evidence)

    def checkout(self, style):
        target = Path(self.temp.name) / ('checkout-' + style)
        source = read_json(self.evidence / 'execution-source-map.json')
        for relative, binding in source['files'].items():
            if binding['role'] == 'observed_only_source':
                continue
            data = (ROOT / relative).read_bytes()
            if not relative.endswith(('.gz', '.tgz', '.zip')):
                data = data.decode('utf-8').replace('\r\n', '\n').encode()
                if style == 'CRLF':
                    data = data.replace(b'\n', b'\r\n')
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return target

    def test_declared_lf_and_crlf_checkouts_reconcile_offline(self):
        for style in ('LF', 'CRLF'):
            with self.subTest(style=style):
                checkout = self.checkout(style)
                # Simulate text conversion by Git on evidence JSON too. The
                # compressed bytes are deliberately left completely unchanged.
                for path in self.evidence.glob('*.json'):
                    data = path.read_bytes().replace(b'\r\n', b'\n')
                    path.write_bytes(data if style == 'LF' else data.replace(b'\n', b'\r\n'))
                with patch('urllib.request.urlopen', side_effect=AssertionError('offline only')):
                    self.assertTrue(verify(self.evidence, artifact_root=checkout)['verified'])

    def test_normalization_rejects_substantive_text_byte_and_policy_edits(self):
        checkout = self.checkout('LF')
        path = checkout / 'newboundednativeJOBwork/experiment.py'
        original = path.read_bytes()
        for changed in (original + b'\n# post-run substantive addition\n',
                        original.replace(b'Bounded native', b'Changed native', 1),
                        b'\xef\xbb\xbf' + original, original.replace(b'\n', b'\r'), original + b'\xff'):
            with self.subTest(change=changed[:24]):
                path.write_bytes(changed)
                with self.assertRaises(ReconciliationError):
                    verify(self.evidence, artifact_root=checkout)
        path.write_bytes(original)
        source = read_json(self.evidence / 'execution-source-map.json')
        source['files']['newboundednativeJOBwork/experiment.py']['identity_policy'] = 'strip-all-whitespace'
        self.rewrite('execution-source-map.json', source)
        with self.assertRaisesRegex(ReconciliationError, 'unsupported identity normalization'):
            verify(self.evidence, artifact_root=checkout)

    def test_compressed_asset_is_binary_only_even_with_same_decoded_json(self):
        path = self.evidence / 'native-rounds.json.gz'
        original = path.read_bytes()
        changed = bytearray(original)
        changed[4] ^= 1  # gzip timestamp header only; decoded JSON is identical.
        self.assertEqual(gzip.decompress(original), gzip.decompress(changed))
        path.write_bytes(changed)
        with self.assertRaisesRegex(ReconciliationError, 'digest mismatch'):
            verify(self.evidence)


if __name__ == '__main__':
    unittest.main(verbosity=2)
