"""합성 A→B→A 절차의 M03 원본/M07/M04 저장 전달 검증. 브라우저·GPT 실행 없음."""
import base64
import copy
import hashlib
import io
import json
import unittest
import zipfile
from unittest.mock import Mock, patch

import test_m03_canonical_adapter as adapter_fixture
from backend import execution_contexts
from backend.m03_canonical_adapter import generate_canonical
from backend.m04.store import M04Manager
from backend.m07.store import M07Manager
from backend.run_storage import save_run


class RevisitedProcedureHandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixture = adapter_fixture.CanonicalAdapterTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        document = self.fixture.revisited_document()
        for index, procedure in enumerate(document[0]['procedures'], 1):
            procedure.update(action='click', http_method='', source_workflow_id='WF-TEST',
                             source_process_model_id='PM-TEST', source_session_id='SYNTHETIC-SESSION',
                             source_csv_rows=[1] if index == 1 else [2, 3] if index == 2 else [4])
            procedure['target'] = dict(page_path='/synthetic', role='button-a' if index != 2 else 'button-b',
                                       normalized_endpoint='')
        self.fixture.write_document(document)
        self.scenario = generate_canonical(self.root, self.fixture.payload)
        self.config = dict(targets={'M03': 80, 'M04': 90, 'M07': 80}, m04={}, m07={})
        received = dict(details={}, scenarios=[copy.deepcopy(self.scenario)])
        stored = save_run(self.root, 'M03', 'DEVELOPMENT', self.config,
                          dict(score=None, sample_count=1, status='COMPLETED',
                               details={'evaluation_status': 'NOT_READY'}, input_sha256={}), [], received=received)
        self.run_id = stored['run_id']
        self.original_path = self.root/'results/development'/self.run_id/'received_payload.json'
        self.original_bytes = self.original_path.read_bytes()
        expected = [dict(order=i, expected_result='Synthetic visible state '+str(i)) for i in range(1, 4)]
        self.contract = dict(version=1, scenario_id=self.scenario['scenario_id'], steps=[
            dict(order=i, action='click', target=dict(by='css selector', value='#a' if i != 2 else '#b'),
                 checks=[dict(kind='visible')]) for i in range(1, 4)])
        execution_contexts.save(self.root, self.run_id, self.scenario, self.config, self.contract, expected)
        self.provider = Mock(side_effect=AssertionError('No GPT/model/provider execution in handoff test'))
        self.m07 = M07Manager(self.root, lambda: copy.deepcopy(self.config), generator=self.provider)
        self.m04 = M04Manager(self.root, lambda: copy.deepcopy(self.config))
        self.code = (
            '# SYNTHETIC HANDOFF ONLY; NEVER EXECUTED\n'
            'SCENARIO_ID='+repr(self.scenario['scenario_id'])+'\n'
            'from selenium import webdriver\n'
            'from ktl_runtime import business_step\n'
            'driver = webdriver.Chrome()\n'
            'with business_step(1):\n'
            '    driver.find_element("css selector", "#a").click()\n'
            '    assert driver.title == "SYNTHETIC"\n'
            'with business_step(2):\n'
            '    driver.find_element("css selector", "#b").click()\n'
            '    assert driver.title == "SYNTHETIC"\n'
            'with business_step(3):\n'
            '    driver.find_element("css selector", "#a").click()\n'
            '    assert driver.title == "SYNTHETIC"\n'
            'driver.quit()\n').encode('utf-8')

    def assert_occurrences(self, scenario):
        self.assertEqual(len(scenario['steps']), 3)
        self.assertEqual([step['id'] for step in scenario['steps']], ['NODE-1', 'NODE-2', 'NODE-1'])
        self.assertEqual([step['node_id'] for step in scenario['steps']], ['NODE-1', 'NODE-2', 'NODE-1'])
        self.assertEqual([step['occurrence_id'] for step in scenario['steps']], ['OCC-0001', 'OCC-0002', 'OCC-0003'])
        self.assertEqual([step['order'] for step in scenario['steps']], [1, 2, 3])
        for original, observed in zip(self.scenario['steps'], scenario['steps']):
            for key in ('id', 'node_id', 'occurrence_id', 'order', 'action', 'target', 'evidence',
                        'source_workflow_id', 'source_process_model_id', 'source_session_id', 'source_csv_rows'):
                self.assertEqual(observed[key], original[key])

    def test_m07_source_and_execution_overlay_keep_every_occurrence_and_evidence(self):
        source, synthetic = self.m07._source(self.run_id, self.scenario['scenario_id'])
        self.assertFalse(synthetic)
        self.assertEqual(source, self.scenario)
        self.assert_occurrences(source)
        effective = execution_contexts.resolve(self.root, self.run_id, source, self.config)['scenario']
        self.assert_occurrences(effective)
        self.assertEqual([step['order'] for step in effective['execution_contract']['steps']], [1, 2, 3])
        source['steps'].pop()
        self.assertEqual(self.original_path.read_bytes(), self.original_bytes)
        self.provider.assert_not_called()

    def test_m04_direct_registration_keeps_raw_and_execution_snapshots(self):
        metadata = self.m04.register(dict(filename='synthetic-revisit.py',
            python_base64=base64.b64encode(self.code).decode('ascii'), scenario_id=self.scenario['scenario_id'],
            m03_run_id=self.run_id))['script']
        folder = self.m04.script_directory/metadata['script_id']
        for name in ('source_scenario.json', 'execution_scenario.json'):
            self.assert_occurrences(json.loads((folder/name).read_text(encoding='utf-8')))
        self.assertEqual((folder/'script.py').read_bytes(), self.code)
        self.assertTrue(metadata['business_step_required'])
        self.assertEqual(self.original_path.read_bytes(), self.original_bytes)
        self.provider.assert_not_called()

    def test_m07_prepared_archive_and_m04_export_keep_three_occurrences_without_provider(self):
        prepared = dict(scenario_id=self.scenario['scenario_id'], filename='synthetic-revisit.py',
                        code_base64=base64.b64encode(self.code).decode('ascii'),
                        sha256=hashlib.sha256(self.code).hexdigest())
        with patch('backend.m07.prepared._known_secrets', return_value=[]), \
             patch.object(self.m07, '_launch', side_effect=lambda identity, phase, lock: lock.close()):
            created = self.m07.create(dict(scenario_refs=[dict(m03_run_id=self.run_id,
                         scenario_id=self.scenario['scenario_id'])], prepared_codes=[prepared]))['generation']
        job = self.m07._job(created['execution_id'])
        self.m07._generate(job)
        self.assertEqual(job['status'], 'GENERATED')
        self.assertEqual(job['cases'][0]['generation_status'], 'PASS')
        self.assertFalse(job['cases'][0]['generated_by_llm'])
        archive, _ = self.m07.artifact(job['execution_id'], 'code.zip')
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            for name in ('source_scenario.json', 'execution_scenario.json'):
                self.assert_occurrences(json.loads(zipped.read('CASE-001/'+name)))
            self.assertEqual(zipped.read('CASE-001/script.py'), self.code)
        exported = self.m07.export_m04(job['execution_id'], {'case_ids': ['CASE-001']}, self.m04)
        self.assertEqual(len(exported['scripts']), 1)
        metadata = exported['scripts'][0]
        folder = self.m04.script_directory/metadata['script_id']
        for name in ('source_scenario.json', 'execution_scenario.json'):
            self.assert_occurrences(json.loads((folder/name).read_text(encoding='utf-8')))
        self.assertEqual(metadata['source_kind'], 'M07_PREPARED_SCRIPT')
        self.assertFalse(metadata['generated_by_llm'])
        self.assertEqual(self.original_path.read_bytes(), self.original_bytes)
        self.provider.assert_not_called()


if __name__ == '__main__':
    unittest.main()
