"""생성 receipt와 adapter가 동일한 단일 검증 입력을 사용하도록 하는 회귀 시험."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m03_integration import _real_input, generate
from backend.m03_provenance import begin_generation, generate_recorded


class M03InputBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ktl-m03-input-binding-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / 'data/analysis'
        self.folder.mkdir(parents=True)
        self.source = self.folder / 'model-output.json'
        self.source.write_text('{"workflow_id":"WF-A","actions":["click"]}', encoding='utf-8')
        self.manifest = self.folder / 'manifest.json'
        self.write_manifest('ANALYSIS-A')
        self.definition = dict(business_unit_id='BU-A', workflow_id='WF-A', business_name='Before receipt',
                               start_screen='https://example.invalid/', required_procedures=['Original procedure'],
                               end_condition='Synthetic outcome')
        self.config = dict(adapters={'scenario_generation': ['never-executed-test-adapter']},
                           m03=dict(generator_mode='REAL', input_manifest='data/analysis/manifest.json',
                                    source_module='temporary-binding-test', source_version='v1',
                                    business_units=[copy.deepcopy(self.definition)]))
        self.request = dict(business_unit_id='BU-A', workflow_id='WF-A', run_mode='DEVELOPMENT', generator_mode='REAL')
        self.response = dict(business_unit_id='BU-A', workflow_id='WF-A', scenario_id='SCN-A', status='SUCCESS',
                             steps=[dict(order=1, action='click', target='temporary control')])

    def write_manifest(self, identity):
        value = dict(dataset_id=identity, synthetic=False, workflow_ids=['WF-A'],
                     files=[dict(path=self.source.name, sha256=hashlib.sha256(self.source.read_bytes()).hexdigest())])
        self.manifest.write_text(json.dumps(value), encoding='utf-8')

    def test_recorded_generation_pins_one_validation_across_manifest_and_definition_change(self):
        original_manifest_sha = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        actual_adapter_input = {}
        def change_after_receipt(root, config, request, analysis_input=None):
            receipt = begin_generation(root, config, request, analysis_input)
            self.write_manifest('ANALYSIS-B')
            config['m03']['business_units'][0]['business_name'] = 'After receipt'
            config['m03']['business_units'][0]['required_procedures'] = ['Changed procedure']
            return receipt
        def adapter(_config, _name, outgoing, _root):
            actual_adapter_input.update(copy.deepcopy(outgoing))
            return copy.deepcopy(self.response)
        with patch('backend.m03_integration._real_input', wraps=_real_input) as verified, \
                patch('backend.m03_provenance.begin_generation', side_effect=change_after_receipt), \
                patch('backend.m03_integration.call_adapter', side_effect=adapter):
            result = generate_recorded(self.root, self.config, self.request)
        self.assertEqual(verified.call_count, 1, 'Receipt and adapter must share one validation, not reload a changed manifest')
        self.assertEqual(actual_adapter_input['analysis_input']['dataset_id'], 'ANALYSIS-A')
        self.assertEqual(actual_adapter_input['analysis_input']['manifest_sha256'], original_manifest_sha)
        self.assertEqual(actual_adapter_input['business_definition'], self.definition)
        folder = self.root / 'results/m03_generations' / result['origin_generation_id']
        receipt = json.loads((folder / 'receipt.json').read_text(encoding='utf-8'))
        started = json.loads((folder / 'started.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['analysis_input'], actual_adapter_input['analysis_input'])
        self.assertEqual(started['analysis_input'], actual_adapter_input['analysis_input'])
        self.assertEqual(receipt['status'], 'COMPLETED')

    def test_http_reader_rejects_changed_source_bytes_before_network_or_response_snapshot(self):
        self.config['m03'].update(transport='HTTP', http={'url': 'http://127.0.0.1:1/generate'})
        def change_after_receipt(root, config, request, analysis_input=None):
            receipt = begin_generation(root, config, request, analysis_input)
            self.source.write_text('{"workflow_id":"WF-A","actions":["changed"]}', encoding='utf-8')
            self.write_manifest('ANALYSIS-B')
            return receipt
        with patch('backend.m03_integration._real_input', wraps=_real_input) as verified, \
                patch('backend.m03_provenance.begin_generation', side_effect=change_after_receipt), \
                patch('backend.m03_http.request.build_opener') as network:
            with self.assertRaises(EvaluationError):
                generate_recorded(self.root, self.config, self.request)
        self.assertEqual(verified.call_count, 1)
        network.assert_not_called()
        receipts = list((self.root / 'results/m03_generations').glob('M03-GEN-*/receipt.json'))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(json.loads(receipts[0].read_text(encoding='utf-8'))['status'], 'ERROR')
        self.assertFalse((receipts[0].parent / 'response.json').exists())
        self.assertFalse((self.root / 'data/development/m03_http').exists())

    def test_existing_direct_generate_still_validates_real_input_once(self):
        with patch('backend.m03_integration._real_input', wraps=_real_input) as verified, \
                patch('backend.m03_integration.call_adapter', return_value=copy.deepcopy(self.response)) as adapter:
            result = generate(self.root, self.config, self.request)
        self.assertEqual(verified.call_count, 1)
        self.assertEqual(result['scenario_id'], 'SCN-A')
        self.assertEqual(adapter.call_args.args[2]['analysis_input']['dataset_id'], 'ANALYSIS-A')

    def test_internal_verified_input_cannot_be_supplied_through_json_request(self):
        payload = dict(self.request, verified_real_input={'dataset_id': 'INJECTED'})
        with patch('backend.m03_integration._real_input') as verified, \
                patch('backend.m03_integration.call_adapter') as adapter:
            with self.assertRaises(EvaluationError):
                generate(self.root, self.config, payload)
        verified.assert_not_called()
        adapter.assert_not_called()

    def test_mock_recorded_generation_does_not_validate_or_read_real_input(self):
        request = dict(self.request, generator_mode='MOCK')
        with patch('backend.m03_integration._real_input', side_effect=AssertionError('Mock read real input')) as verified:
            result = generate_recorded(self.root, self.config, request)
        verified.assert_not_called()
        self.assertTrue(result['synthetic'])
        folder = self.root / 'results/m03_generations' / result['origin_generation_id']
        self.assertIsNone(json.loads((folder / 'receipt.json').read_text(encoding='utf-8'))['analysis_input'])

    def test_invalid_initial_source_does_not_create_started_receipt(self):
        self.source.write_bytes(self.source.read_bytes() + b' ')
        with patch('backend.m03_integration.call_adapter') as adapter:
            with self.assertRaises(EvaluationError):
                generate_recorded(self.root, self.config, self.request)
        adapter.assert_not_called()
        self.assertFalse((self.root / 'results').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
