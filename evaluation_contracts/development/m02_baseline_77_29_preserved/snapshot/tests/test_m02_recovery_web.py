"""Synthetic-only recovery web routing and fail-closed freeze checks."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from backend import m02_recovery_candidate as candidate
from backend.evaluators import EvaluationError, digest
from backend.server import Service

class RecoveryWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / candidate.SNAPSHOT; self.folder.mkdir(parents=True)
        (self.root / 'backend').mkdir()
        (self.root / 'backend/config.json').write_text((Path(__file__).resolve().parents[1] / 'backend/config.json').read_text())
        self.manifest = dict(run_mode='DEVELOPMENT', dataset_id=candidate.DATASET, sha256={})
        for key in candidate.REQUIRED_INPUTS:
            filename = key + '.json'
            (self.root / filename).write_text('{}')
            self.manifest[key] = filename
            self.manifest['sha256'][filename] = digest(self.root / filename)
        self.write('manifest.json', self.manifest)
    def write(self, name, obj):
        (self.folder / name).write_text(json.dumps(obj))
    def gate(self):
        gate = dict(verdict='PASS', snapshot_manifest_sha256=digest(self.folder / 'manifest.json'))
        gate.update({key: 'PASS' for key in candidate.CHECKS})
        self.write('independent_verification.json', gate)
    def freeze(self):
        self.write('freeze.json', dict(status='FROZEN', snapshot_manifest_sha256=digest(self.folder / 'manifest.json'),
            independent_verification_sha256=digest(self.folder / 'independent_verification.json')))
    def test_requires_independent_pass_then_matching_freeze(self):
        self.assertEqual(candidate.prepare(self.root)['status'], 'BLOCKED')
        self.gate()
        self.assertEqual(candidate.prepare(self.root)['status'], 'BLOCKED')
        self.freeze()
        self.assertEqual(candidate.prepare(self.root)['status'], 'READY')
        self.write('freeze.json', dict(status='FROZEN', snapshot_manifest_sha256='old'))
        self.assertEqual(candidate.prepare(self.root)['status'], 'BLOCKED')
    def test_tampered_source_or_gate_fails_closed(self):
        self.gate(); self.freeze()
        (self.root / self.manifest['raw_events']).write_text('{"changed":true}')
        self.assertEqual(candidate.prepare(self.root)['status'], 'BLOCKED')
        with patch.object(candidate, 'generate', side_effect=AssertionError('must not generate')):
            with self.assertRaises(EvaluationError): candidate.assess(self.root)
    def test_missing_input_hash_and_wrong_mode_rejected(self):
        del self.manifest['sha256'][self.manifest['td04']]
        self.write('manifest.json', self.manifest); self.gate(); self.freeze()
        self.assertEqual(candidate.prepare(self.root)['status'], 'BLOCKED')
        self.manifest['run_mode'] = 'OFFICIAL'
        self.write('manifest.json', self.manifest); self.gate(); self.freeze()
        self.assertEqual(candidate.prepare(self.root)['status'], 'BLOCKED')
    def test_catalog_lists_development_only_without_calculation(self):
        service = Service(self.root)
        with patch.object(candidate, 'assess', side_effect=AssertionError('no catalog measurement')):
            catalog = service.catalog('DEVELOPMENT')
            item = next(m for m in catalog['metrics'] if m['metric_id'] == 'M02')
            option = next(o for o in item['input_options'] if o['id'] == candidate.DATASET)
            self.assertEqual(option['readiness']['status'], 'BLOCKED')
            self.assertEqual(item['target'], 75)
            for mode in ('REFERENCE', 'OFFICIAL'):
                source = Mock(dataset_id='synthetic')
                source.prepare.return_value = dict(status='READY', details={})
                with patch.object(service, 'source', return_value=source):
                    catalog = service.catalog(mode)
                self.assertFalse(any(o.get('id') == candidate.DATASET for m in catalog['metrics'] for o in m['input_options']))
    def test_dispatch_development_only_and_no_legacy_model(self):
        service = Service(self.root)
        with patch.object(candidate, 'run', return_value={'sentinel': True}) as run:
            self.assertEqual(service.run('M02', 'DEVELOPMENT', candidate.DATASET), {'sentinel': True})
            run.assert_called_once()
            for mode in ('REFERENCE', 'OFFICIAL'):
                with self.assertRaises(EvaluationError): service.run('M02', mode, candidate.DATASET)
            with self.assertRaises(EvaluationError): service.run('M03', 'DEVELOPMENT', candidate.DATASET)
    def test_save_uses_existing_evidence_contract_and_stage_snapshots(self):
        self.gate(); self.freeze()
        result = dict(status='COMPLETED', score=50, sample_count=1, dataset_id=candidate.DATASET,
            source_type='DEVELOPMENT', details={})
        with patch.object(candidate, 'assess', return_value=(result, [{'row_type':'synthetic'}], {'scope.json':{'synthetic':True}})):
            saved = candidate.run(self.root, Service(self.root).config())
        directory = self.root / 'results/development' / saved['run_id']
        self.assertEqual(saved['dataset_id'], candidate.DATASET)
        self.assertIsNone(saved['official_pass'])
        self.assertTrue((directory / 'evidence.csv').is_file())
        self.assertTrue((directory / 'scope.json').is_file())
        self.assertTrue(saved['evidence_file'].endswith('/evidence.csv'))
