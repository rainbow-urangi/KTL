"""실행 계획 통합 회귀. 임시 저장소만 쓰며 GPT/브라우저/모델을 실행하지 않는다."""
import copy
import base64
import csv
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from backend import execution_contexts
from backend.evaluators import EvaluationError
from backend.m04.store import M04Manager
from backend.m07.store import M07Manager
from backend.m07.generator import prompt
from backend.server import Service, make_handler


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = 'DEV-M03-20261109T074055-6dc6b7f9ed6f'
ACTUAL_CU10_RECEIVED = (ROOT.parent / 'data/changes/20261109-m03-repair-e2b7c4a1'
                      / 'trial/runtime/results/development' / RUN_ID / 'received_payload.json')
ACTUAL_CU10_SHA256 = '53b687565cf42614f10628ba65663e433b57e558d85fdb4f1b2f01701eea3a01'


class ExecutionPlanIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = dict(targets={'M03': 80, 'M04': 90, 'M07': 80}, m04={},
                           m07=dict(model='SYNTHETIC_TEST_ONLY', target_url='https://example.invalid/synthetic'))
        self.provider = Mock(side_effect=AssertionError('External provider must never run in this regression'))
        self.m07 = M07Manager(self.root, lambda: copy.deepcopy(self.config), generator=self.provider)
        self.m07._readiness = lambda: dict(selenium=True, chrome=True, message='SYNTHETIC_TEST_ONLY')
        self.m04 = M04Manager(self.root, lambda: copy.deepcopy(self.config))

    def install_sources(self, scenarios, *, raw=None):
        folder = self.root / 'results/development' / RUN_ID
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'result.json').write_bytes(execution_contexts.encoded(
            dict(metric_id='M03', run_mode='DEVELOPMENT', status='COMPLETED', score=None)))
        path = folder / 'received_payload.json'
        path.write_bytes(raw if raw is not None else execution_contexts.encoded(dict(
            details=dict(synthetic=True), scenarios=scenarios)))
        return path

    @staticmethod
    def legacy_source():
        return dict(business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
                    scenario_id='SYNTHETIC-SCN', status='SUCCESS', synthetic=True,
                    steps=[dict(order=1, action='open', target='Synthetic page')])

    def plan_fixture(self):
        fields = ('id event_id session_id task_id workflow_index step_duration_ms workflow_key workflow_outcome '
                  'event_time event_type page_url target_selector locators_json data_testid element_tag selector_xpath '
                  'interaction_type input_data api_path api_method api_status_code page_title element_text associated_label '
                  'api_latency_ms target_key target_key_source input_control_type capture_run_id capture_tab_id '
                  'capture_frame_id capture_root_tab_id capture_tab_path').split()
        rows = []
        evidence = []
        for order, (kind, selector, tag, control) in enumerate((
                ('input', '#synthetic-title', 'input', 'text'),
                ('input', '#synthetic-description', 'textarea', 'textarea'),
                ('api_transaction', '', '', ''), ('route_change', '', '', '')), 1):
            row = dict.fromkeys(fields, '')
            row.update(id=str(order), event_id='SYNTHETIC-E' + str(order), session_id='SYNTHETIC-SESSION',
                       event_time='2026-11-09T00:00:0' + str(order) + 'Z', event_type='DOM_EVENT',
                       page_url='https://example.invalid/synthetic', target_selector=selector, element_tag=tag,
                       interaction_type=kind, input_control_type=control, capture_run_id='SYNTHETIC-CAPTURE',
                       capture_tab_id='7', capture_frame_id='0', capture_root_tab_id='7', capture_tab_path='[7]',
                       target_key='css:' + selector if selector else '', target_key_source='selector' if selector else '',
                       locators_json=json.dumps(dict(selector_css=selector, selector_xpath='', element_tag=tag)))
            if kind == 'api_transaction':
                row.update(api_path='/api/synthetic', api_method='POST', api_status_code='201')
            rows.append(row)
            evidence.append(dict(csv_row=order, event_id=row['event_id'], session_id=row['session_id'],
                                 event_time=row['event_time'], tab_id=7, frame_id=0, event_sequence=order))
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        raw = buffer.getvalue().encode('utf-8-sig')
        directory = self.root / 'data/development/observations'
        directory.mkdir(parents=True)
        csv_path = directory / 'events.csv'
        csv_path.write_bytes(raw)
        manifest = dict(capture_scope_version=2, active=False, run_id='SYNTHETIC-CAPTURE', target_tab_id=7,
                        capture_tab_paths={'7': [7]}, csv_sha256=hashlib.sha256(raw).hexdigest(), csv_byte_count=len(raw),
                        columns=fields, event_count=len(rows), event_evidence=evidence)
        manifest_path = directory / 'capture-manifest.json'
        manifest_path.write_bytes(execution_contexts.encoded(manifest))
        source = self.legacy_source()
        source.update(canonical_kind='CAPTURE_OBSERVED_SEQUENCE', source_csv_sha256=manifest['csv_sha256'],
                      source_capture_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(), steps=[])
        for order, (action, ids) in enumerate((('input', [1, 2]), ('api_confirmation', [3]), ('page_entry', [4])), 1):
            source['steps'].append(dict(id='NODE-' + str(order), node_id='NODE-' + str(order),
                occurrence_id='OCC-' + str(order).zfill(4), order=order, action=action, target='Observed role',
                evidence=['SYNTHETIC-E' + str(i) for i in ids], source_csv_rows=ids,
                source_session_id='SYNTHETIC-SESSION'))
        path = self.install_sources([source])
        ref = lambda order, eid: [dict(order=order, event_ids=['SYNTHETIC-E' + str(eid)])]
        plan = dict(version=1, source_scenario_sha256=hashlib.sha256(execution_contexts.encoded(source)).hexdigest(),
                    observation_sources=dict(csv=dict(path=csv_path.relative_to(self.root).as_posix(), sha256=manifest['csv_sha256']),
                        capture_manifest=dict(path=manifest_path.relative_to(self.root).as_posix(),
                                              sha256=source['source_capture_manifest_sha256'])),
                    parameter_source='NEW_TEST_PARAMETERS', parameters=dict(title='Fresh synthetic title', description='Fresh description'),
                    items=[dict(kind='execute', source_refs=ref(1, 1), action='input',
                                target=dict(by='css selector', value='#synthetic-title'), value_param='title',
                                expected_result='New title is entered', checks=[dict(kind='value', expected_param='title')]),
                           dict(kind='execute', source_refs=ref(1, 2), action='input',
                                target=dict(by='css selector', value='#synthetic-description'), value_param='description',
                                expected_result='New description is entered', checks=[dict(kind='value', expected_param='description')]),
                           dict(kind='reference', source_refs=ref(2, 3), reason='Recorded API evidence; not a browser click'),
                           dict(kind='check', source_refs=ref(3, 4), target=dict(by='css selector', value='#synthetic-complete'),
                                expected_result='Business completion state is visible',
                                checks=[dict(kind='visible', expected=True)])])
        return source, plan, path

    def prepared_job(self, source):
        code = ('# SYNTHETIC STORAGE ONLY; NEVER EXECUTED\nSCENARIO_ID=' + repr(source['scenario_id']) + '\n'
                'from selenium import webdriver\nfrom ktl_runtime import business_step\n'
                'with business_step(1):\n    assert webdriver is not None\n').encode('utf-8')
        record = dict(scenario_id=source['scenario_id'], filename='synthetic-plan.py',
                      code_base64=base64.b64encode(code).decode('ascii'), sha256=hashlib.sha256(code).hexdigest())
        with patch('backend.m07.prepared._known_secrets', return_value=[]), \
                patch.object(self.m07, '_launch', side_effect=lambda identity, phase, lock: lock.close()):
            created = self.m07.create(dict(scenario_refs=[dict(m03_run_id=RUN_ID, scenario_id=source['scenario_id'])],
                                          prepared_codes=[record]))['generation']
        job = self.m07._job(created['execution_id'])
        self.m07._generate(job)
        self.assertEqual(job['status'], 'GENERATED')
        self.provider.assert_not_called()
        return job

    def test_saved_plan_splits_grouped_native_inputs_and_preserves_immutable_source(self):
        source, plan, path = self.plan_fixture()
        original = path.read_bytes()
        saved = self.m07.save_execution_plan(dict(m03_run_id=RUN_ID, scenario_id=source['scenario_id'], execution_plan=plan))['execution_context']
        prepared = execution_contexts.resolve(self.root, RUN_ID, source, self.config)
        self.assertTrue(saved['execution_ready'])
        self.assertEqual(prepared['revision_id'], saved['saved_revision_id'])
        self.assertEqual([s['action'] for s in prepared['scenario']['steps']], ['input', 'input', 'verify'])
        self.assertEqual([s.get('value') for s in prepared['scenario']['steps']], ['Fresh synthetic title', 'Fresh description', None])
        self.assertEqual(len(prepared['execution_plan']['source_mapping']), 4)
        self.assertEqual(len(source['steps']), 3)
        self.assertEqual(source['steps'][1]['action'], 'api_confirmation')
        self.assertEqual(path.read_bytes(), original)

    def test_plan_snapshots_survive_m07_archive_m04_export_and_later_revision(self):
        source, plan, path = self.plan_fixture()
        original = path.read_bytes()
        first = execution_contexts.save_plan(self.root, RUN_ID, source, self.config, plan)
        job = self.prepared_job(source)
        case = job['cases'][0]
        folder = self.m07._case_path(job, case, 'execution_plan.json').parent
        plan_raw = (folder / 'execution_plan.json').read_bytes()
        self.assertEqual(case['execution_plan_sha256'], hashlib.sha256(plan_raw).hexdigest())
        archive, _ = self.m07.artifact(job['execution_id'], 'code.zip')
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(zipped.read('CASE-001/execution_plan.json'), plan_raw)
        metadata = self.m07.export_m04(job['execution_id'], dict(case_ids=['CASE-001']), self.m04)['scripts'][0]
        fixed = self.m04.script_directory / metadata['script_id']
        self.assertEqual((fixed / 'execution_plan.json').read_bytes(), plan_raw)
        self.assertEqual(metadata['execution_plan_sha256'], case['execution_plan_sha256'])
        changed = copy.deepcopy(plan)
        changed['parameters']['title'] = 'New revision title'
        second = execution_contexts.save_plan(self.root, RUN_ID, source, self.config, changed)
        self.assertNotEqual(first['saved_revision_id'], second['saved_revision_id'])
        prepared = self.m04._fixed_execution(metadata, fixed)
        self.assertEqual(prepared['revision_id'], first['saved_revision_id'])
        self.assertEqual(prepared['scenario']['steps'][0]['value'], 'Fresh synthetic title')
        self.assertEqual((folder / 'execution_plan.json').read_bytes(), plan_raw)
        self.assertEqual((fixed / 'execution_plan.json').read_bytes(), plan_raw)
        self.assertEqual(path.read_bytes(), original)
        self.provider.assert_not_called()

    def test_plan_snapshot_tampering_blocks_m07_and_m04(self):
        source, plan, _ = self.plan_fixture()
        execution_contexts.save_plan(self.root, RUN_ID, source, self.config, plan)
        job = self.prepared_job(source)
        metadata = self.m07.export_m04(job['execution_id'], dict(case_ids=['CASE-001']), self.m04)['scripts'][0]
        generated = self.m07._case_path(job, job['cases'][0], 'execution_plan.json')
        generated.write_bytes(generated.read_bytes() + b' ')
        with self.assertRaises(EvaluationError):
            self.m07._check(job, job['cases'][0])
        fixed = self.m04.script_directory / metadata['script_id'] / 'execution_plan.json'
        fixed.write_bytes(fixed.read_bytes() + b' ')
        with self.assertRaises(EvaluationError):
            self.m04._script(metadata['script_id'])
        self.provider.assert_not_called()

    def test_direct_m04_registration_pins_plan_without_m07_or_provider(self):
        source, plan, path = self.plan_fixture()
        original = path.read_bytes()
        saved = execution_contexts.save_plan(self.root, RUN_ID, source, self.config, plan)
        code = ('# SYNTHETIC STORAGE ONLY; NEVER EXECUTED\nSCENARIO_ID=' + repr(source['scenario_id']) + '\n'
                'from selenium import webdriver\nfrom ktl_runtime import business_step\n'
                'with business_step(1):\n    assert webdriver is not None\n').encode('utf-8')
        metadata = self.m04.register(dict(filename='synthetic-direct.py',
            python_base64=base64.b64encode(code).decode('ascii'), scenario_id=source['scenario_id'],
            m03_run_id=RUN_ID, require_business_steps=True))['script']
        fixed = self.m04.script_directory / metadata['script_id']
        self.assertEqual(metadata['execution_context_revision_id'], saved['saved_revision_id'])
        self.assertEqual(metadata['execution_plan_sha256'], hashlib.sha256((fixed / 'execution_plan.json').read_bytes()).hexdigest())
        self.assertEqual(json.loads((fixed / 'source_scenario.json').read_bytes()), source)
        self.assertEqual([s['action'] for s in json.loads((fixed / 'execution_scenario.json').read_bytes())['steps']],
                         ['input', 'input', 'verify'])
        self.assertEqual(path.read_bytes(), original)
        self.provider.assert_not_called()

    def test_fixed_m04_execution_copies_plan_into_case_and_pre_execution_archive(self):
        source, plan, _ = self.plan_fixture()
        execution_contexts.save_plan(self.root, RUN_ID, source, self.config, plan)
        job = self.prepared_job(source)
        metadata = self.m07.export_m04(job['execution_id'], dict(case_ids=['CASE-001']), self.m04)['scripts'][0]
        with patch.object(self.m04, '_global_lock', return_value=Mock()), \
                patch('backend.m04.store.threading.Thread') as thread:
            execution = self.m04.create(dict(script_ids=[metadata['script_id']]))['execution']
        thread.return_value.start.assert_called_once()
        case = execution['cases'][0]
        folder = self.m04.execution_directory / execution['execution_id'] / case['case_id']
        plan_raw = (folder / 'execution_plan.json').read_bytes()
        self.assertEqual(case['execution_plan_sha256'], metadata['execution_plan_sha256'])
        self.assertEqual(hashlib.sha256(plan_raw).hexdigest(), case['execution_plan_sha256'])
        self.assertEqual(execution['counts']['total_execution_count'], 1)
        self.assertIsNone(execution['result'])
        with zipfile.ZipFile(self.root / 'data/evaluation' / execution['dataset_id'] / 'scripts.zip') as zipped:
            self.assertEqual(zipped.read('CASE-001/execution_plan.json'), plan_raw)
        self.provider.assert_not_called()

    def test_generation_prompt_gets_compiled_execution_information_without_raw_observations(self):
        source, plan, _ = self.plan_fixture()
        prepared = execution_contexts.prepare_plan(self.root, source, self.config, plan)
        _, text = prompt(prepared['scenario'], self.config)
        payload = json.loads(text)
        steps = payload['scenario']['steps']
        self.assertEqual([s['action'] for s in steps], ['input', 'input', 'verify'])
        self.assertEqual(steps[0]['value'], plan['parameters']['title'])
        self.assertEqual(steps[1]['value'], plan['parameters']['description'])
        for excluded in ('observation_sources', 'source_mapping', 'locators_json', 'source_refs', str(self.root)):
            self.assertNotIn(excluded, text)
        self.provider.assert_not_called()

    def test_plan_save_http_endpoint_and_strict_json_boundary(self):
        source, plan, _ = self.plan_fixture()
        service = Service(self.root)
        service.m07 = lambda: self.m07
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        body = dict(m03_run_id=RUN_ID, scenario_id=source['scenario_id'], execution_plan=plan)
        def request(raw, content_type='application/json', declared=None):
            conn = http.client.HTTPConnection(*server.server_address, timeout=3)
            try:
                headers = {'Content-Type': content_type}
                if declared is not None:
                    headers['Content-Length'] = str(declared)
                conn.request('POST', '/api/development/m07/execution-plans', raw, headers)
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        status, value = request(json.dumps(body).encode('utf-8'))
        self.assertEqual(status, 201)
        self.assertTrue(value['execution_context']['execution_ready'])
        raw = json.dumps(body).encode('utf-8')[:-1] + b',"scenario_id":"AMBIGUOUS"}'
        self.assertEqual(request(raw)[0], 400)
        self.assertEqual(request(json.dumps(body).encode('utf-8'), 'text/plain')[0], 422)
        self.assertEqual(request(b'{}', declared=1048577)[0], 422)
        self.provider.assert_not_called()

    def test_legacy_v1_context_remains_compatible_and_preserves_m03_bytes(self):
        source = self.legacy_source()
        path = self.install_sources([source])
        original = path.read_bytes()
        contract = dict(version=1, scenario_id=source['scenario_id'], steps=[dict(
            order=1, action='open', target=dict(url='https://example.invalid/synthetic'),
            checks=[dict(kind='visible', expected=True, target=dict(by='css selector', value='#ready'))])])
        saved = execution_contexts.save(self.root, RUN_ID, source, self.config, contract,
                                       [dict(order=1, expected_result='Synthetic page is visible')])
        prepared = execution_contexts.resolve(self.root, RUN_ID, source, self.config)
        self.assertTrue(saved['execution_ready'])
        self.assertEqual(prepared['revision_id'], saved['saved_revision_id'])
        self.assertEqual(prepared['scenario']['steps'][0]['action'], 'open')
        self.assertEqual(prepared['contract'], contract)
        self.assertNotIn('expected_result', source['steps'][0])
        self.assertEqual(path.read_bytes(), original)
        self.provider.assert_not_called()

    def test_captured_actions_without_plan_are_not_silently_turned_into_clicks(self):
        sources = []
        for number, action in enumerate(('page_entry', 'selection', 'api_confirmation'), 1):
            source = self.legacy_source()
            source.update(scenario_id='OBSERVED-' + str(number), steps=[dict(
                order=1, action=action, target='Observed role', expected_result='A supplied expectation')])
            sources.append(source)
        path = self.install_sources(sources)
        original = path.read_bytes()
        for source in sources:
            with self.subTest(action=source['steps'][0]['action']):
                editor = execution_contexts.editor(self.root, RUN_ID, source, self.config)
                self.assertFalse(editor['execution_ready'])
                with self.assertRaises(EvaluationError) as error:
                    execution_contexts.resolve(self.root, RUN_ID, source, self.config)
                self.assertEqual(error.exception.status, 'NOT_READY')
        self.assertEqual(path.read_bytes(), original)
        self.provider.assert_not_called()

    def test_archived_actual_cu10_without_plan_remain_zero_ready_without_execution_score(self):
        """기존 실제 10개 원본 재열람 회귀이며 새로운 실제 업무 시험이 아니다."""
        if not ACTUAL_CU10_RECEIVED.is_file():
            self.skipTest('Local immutable CU10 archive is unavailable; synthetic guards still run')
        archived = ACTUAL_CU10_RECEIVED.read_bytes()
        self.assertEqual(hashlib.sha256(archived).hexdigest(), ACTUAL_CU10_SHA256)
        scenarios = json.loads(archived)['scenarios']
        self.assertEqual(len(scenarios), 10)
        self.assertEqual({s['business_unit_id'] for s in scenarios}, {'CU' + str(i).zfill(2) for i in range(1, 11)})
        path = self.install_sources(scenarios, raw=archived)
        context = self.m07.context()
        self.assertEqual(len(context['scenarios']), 10)
        self.assertEqual(sum(row['execution_ready'] for row in context['scenarios']), 0)
        refs = [dict(m03_run_id=RUN_ID, scenario_id=s['scenario_id']) for s in scenarios]
        with self.assertRaises(EvaluationError) as error:
            self.m07.create(dict(scenario_refs=refs))
        self.assertEqual(error.exception.status, 'NOT_READY')
        self.assertEqual(list(self.m07.execution_directory.iterdir()), [])
        self.assertEqual(list(self.m04.execution_directory.iterdir()), [])
        self.assertFalse((self.root / 'results/development/latest-M04.json').exists())
        self.assertFalse((self.root / 'results/development/latest-M07.json').exists())
        self.assertEqual(path.read_bytes(), archived)
        self.assertEqual(ACTUAL_CU10_RECEIVED.read_bytes(), archived)
        self.provider.assert_not_called()


if __name__ == '__main__':
    unittest.main()
