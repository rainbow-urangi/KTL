"""실행 sidecar의 원본 입력 식별자·행·SHA 경계 회귀. 브라우저/모델 실행 없음."""
import copy
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from backend.evaluators import EvaluationError
from backend.execution_contexts import encoded
from backend.execution_plan import load_observations, prepare, source_digest


ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT.parent / 'data/collections/20261109-cu10-3b9c95f1'
RESPONSES = ROOT.parent / 'data/changes/20261109-m03-repair-e2b7c4a1/trial/http'
HEADERS = ('id', 'event_id', 'session_id', 'task_id', 'workflow_index', 'step_duration_ms',
           'workflow_key', 'workflow_outcome', 'event_time', 'event_type', 'page_url', 'target_selector',
           'locators_json', 'data_testid', 'element_tag', 'selector_xpath', 'interaction_type', 'input_data',
           'api_path', 'api_method', 'api_status_code', 'page_title', 'element_text', 'associated_label',
           'api_latency_ms', 'target_key', 'target_key_source', 'input_control_type', 'capture_run_id',
           'capture_tab_id', 'capture_frame_id', 'capture_root_tab_id', 'capture_tab_path')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


class NativeObservationInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-source-input-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.csv = self.root / 'observations/events.csv'
        self.manifest = self.root / 'observations/capture-manifest.json'
        self.csv.parent.mkdir()
        self.rows = []
        for index, (selector, tag, control) in enumerate((('#synthetic-title', 'input', 'text'),
                                                        ('#synthetic-description', 'textarea', 'textarea')), 1):
            row = dict.fromkeys(HEADERS, '')
            row.update(id=str(index), event_id='SYNTHETIC-E' + str(index), session_id='SYNTHETIC-S1',
                       event_time='2026-11-09T00:00:0' + str(index) + '.000Z', event_type='DOM_EVENT',
                       page_url='https://example.invalid/synthetic', page_title='Synthetic fixture',
                       target_selector=selector, selector_xpath='//*[@id="' + selector[1:] + '"]',
                       locators_json=json.dumps(dict(selector_css=selector,
                           selector_xpath='//*[@id="' + selector[1:] + '"]', element_tag=tag)),
                       element_tag=tag, interaction_type='change', target_key='css:' + selector,
                       target_key_source='selector', input_control_type=control,
                       capture_run_id='SYNTHETIC-CAPTURE', capture_tab_id='1', capture_frame_id='0',
                       capture_root_tab_id='1', capture_tab_path='[1]')
            self.rows.append(row)
        self.capture = dict(capture_scope_version=2, active=False, run_id='SYNTHETIC-CAPTURE', target_tab_id=1,
                            columns=list(HEADERS), capture_tab_paths={'1': [1]}, event_count=2,
                            event_evidence=[dict(csv_row=i, event_id=row['event_id'], session_id=row['session_id'],
                                                 event_time=row['event_time'], tab_id=1, frame_id=0, event_sequence=i)
                                            for i, row in enumerate(self.rows, 1)])
        self.source = dict(scenario_id='SYNTHETIC-SCENARIO', business_unit_id='SYNTHETIC-BU',
                           workflow_id='SYNTHETIC-WF', steps=[dict(id='SYNTHETIC-NODE', occurrence_id='OCC-SYNTHETIC-1', order=1, action='input',
                           target='input_control', evidence=['SYNTHETIC-E1', 'SYNTHETIC-E2'],
                           source_csv_rows=[1, 2], source_session_id='SYNTHETIC-S1')])
        self.plan = dict(version=1, parameter_source='NEW_TEST_PARAMETERS',
                         parameters=dict(title='Fresh synthetic title', description='Fresh synthetic description'),
                         items=[self.execute(1, 'SYNTHETIC-E1', '#synthetic-title', 'title'),
                                self.execute(1, 'SYNTHETIC-E2', '#synthetic-description', 'description')])
        self.refresh()

    @staticmethod
    def execute(order, event_id, selector, parameter):
        return dict(kind='execute', source_refs=[dict(order=order, event_ids=[event_id])], action='input',
                    target=dict(by='css selector', value=selector), value_param=parameter,
                    expected_result='New synthetic input is present',
                    checks=[dict(kind='value', expected_param=parameter)])

    def refresh(self):
        self.csv.write_bytes(csv_bytes(self.rows))
        self.capture.update(csv_sha256=sha(self.csv.read_bytes()), csv_byte_count=self.csv.stat().st_size)
        self.manifest.write_bytes(encoded(self.capture))
        self.source.update(source_csv_sha256=sha(self.csv.read_bytes()),
                           source_capture_manifest_sha256=sha(self.manifest.read_bytes()))
        self.plan['source_scenario_sha256'] = source_digest(self.source)
        self.plan['observation_sources'] = dict(csv=dict(path='observations/events.csv', sha256=sha(self.csv.read_bytes())),
            capture_manifest=dict(path='observations/capture-manifest.json', sha256=sha(self.manifest.read_bytes())))

    def reject(self, callback):
        with self.assertRaises(EvaluationError) as error:
            callback()
        self.assertEqual(error.exception.status, 'NOT_READY')

    def test_original_33_columns_native_controls_and_data_ordinal_are_preserved(self):
        observed = load_observations(self.root, self.source, self.plan)
        self.assertEqual(observed['rows'], self.rows)
        self.assertEqual(len(observed['rows'][0]), 33)
        for index, row in enumerate(self.rows, 1):
            binding = observed['rows_by_event_id'][row['event_id']]
            self.assertEqual(binding['csv_row'], index)
            self.assertEqual(binding['row'], row)
            self.assertEqual(binding['evidence']['csv_row'], index)
        self.assertNotEqual(observed['rows'][0]['target_key'], observed['rows'][1]['target_key'])

    def test_one_observed_input_step_splits_only_explicit_evidence_into_two_native_inputs(self):
        original = encoded(self.source)
        raw = self.csv.read_bytes(), self.manifest.read_bytes()
        result = prepare(self.source, self.plan, observations=load_observations(self.root, self.source, self.plan))
        self.assertEqual([step['action'] for step in result['scenario']['steps']], ['input', 'input'])
        self.assertEqual([step['target'] for step in result['contract']['steps']],
                         [dict(by='css selector', value='#synthetic-title'),
                          dict(by='css selector', value='#synthetic-description')])
        self.assertEqual([step['value'] for step in result['scenario']['steps']],
                         ['Fresh synthetic title', 'Fresh synthetic description'])
        self.assertEqual(encoded(self.source), original)
        self.assertEqual((self.csv.read_bytes(), self.manifest.read_bytes()), raw)
        self.assertTrue(all(not row['input_data'] for row in self.rows))

    def test_cross_field_selector_and_generic_control_alias_are_rejected(self):
        observed = load_observations(self.root, self.source, self.plan)
        for selector in ('#synthetic-description', 'input_control'):
            with self.subTest(alias=selector):
                plan = copy.deepcopy(self.plan)
                plan['items'][0]['target']['value'] = selector
                self.reject(lambda: prepare(self.source, plan, observations=observed))

    def test_parameter_value_does_not_come_from_original_collected_input_data(self):
        self.rows[0]['input_data'] = 'SYNTHETIC-ORIGINAL-MUST-NOT-BECOME-NEW-INPUT'
        self.refresh()
        result = prepare(self.source, self.plan, observations=load_observations(self.root, self.source, self.plan))
        self.assertEqual(result['scenario']['steps'][0]['value'], 'Fresh synthetic title')
        self.assertNotIn(self.rows[0]['input_data'], json.dumps(result['scenario']))

    def test_non_native_or_password_control_cannot_be_silently_treated_as_text_input(self):
        for tag, control in (('div', ''), ('input', 'password')):
            with self.subTest(tag=tag, control=control):
                self.rows[0].update(element_tag=tag, input_control_type=control)
                self.refresh()
                observed = load_observations(self.root, self.source, self.plan)
                self.reject(lambda: prepare(self.source, self.plan, observations=observed))

    def test_csv_manifest_and_source_scenario_raw_hash_mismatch_is_not_normalized_away(self):
        for target in ('csv', 'manifest', 'source'):
            with self.subTest(target=target):
                plan = copy.deepcopy(self.plan)
                if target == 'source':
                    plan['source_scenario_sha256'] = '0' * 64
                    self.reject(lambda: prepare(self.source, plan,
                                observations=load_observations(self.root, self.source, plan)))
                else:
                    plan['observation_sources']['csv' if target == 'csv' else 'capture_manifest']['sha256'] = '0' * 64
                    self.reject(lambda: load_observations(self.root, self.source, plan))

    def test_manifest_physical_csv_line_cannot_replace_header_excluded_data_ordinal(self):
        self.capture['event_evidence'][0]['csv_row'] = 2
        self.refresh()
        self.reject(lambda: load_observations(self.root, self.source, self.plan))

    def test_manifest_event_or_session_identity_mismatch_is_rejected_after_valid_hash_refresh(self):
        for field in ('event_id', 'session_id'):
            with self.subTest(field=field):
                self.capture['event_evidence'][0][field] = 'SYNTHETIC-WRONG'
                self.refresh()
                self.reject(lambda: load_observations(self.root, self.source, self.plan))
                self.capture['event_evidence'][0][field] = self.rows[0][field]

    def test_source_physical_line_numbers_do_not_rebind_the_original_input_events(self):
        self.source['steps'][0]['source_csv_rows'] = [2, 3]
        self.plan['source_scenario_sha256'] = source_digest(self.source)
        self.reject(lambda: load_observations(self.root, self.source, self.plan))

    def test_evidence_omission_and_duplicate_classification_are_rejected(self):
        observed = load_observations(self.root, self.source, self.plan)
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                plan = copy.deepcopy(self.plan)
                if duplicate:
                    plan['items'].append(copy.deepcopy(plan['items'][0]))
                else:
                    plan['items'].pop()
                self.reject(lambda: prepare(self.source, plan, observations=observed))


@unittest.skipUnless(COLLECTION.is_dir() and RESPONSES.is_dir(), 'Archived real CU10 evidence is not installed')
class ArchivedCU10InputCompatibilityTests(unittest.TestCase):
    def test_all_ten_original_csvs_and_manifest_rows_bind_existing_M03_evidence(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-real-source-binding-test-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        for folder in sorted(path for path in COLLECTION.glob('CU??-*') if path.is_dir()):
            with self.subTest(unit=folder.name[:4]):
                source = json.loads((RESPONSES / (folder.name[:4] + '-generate-response.json')).read_bytes())
                raw = (folder / 'events.csv').read_bytes()
                manifest_raw = (folder / 'capture-manifest.json').read_bytes()
                target = root / folder.name
                target.mkdir()
                (target / 'events.csv').write_bytes(raw)
                (target / 'capture-manifest.json').write_bytes(manifest_raw)
                plan = dict(version=1, source_scenario_sha256=source_digest(source),
                            observation_sources=dict(csv=dict(path=folder.name + '/events.csv', sha256=sha(raw)),
                                capture_manifest=dict(path=folder.name + '/capture-manifest.json', sha256=sha(manifest_raw))))
                original = encoded(source)
                observed = load_observations(root, source, plan)
                expected = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
                self.assertEqual(observed['rows'], expected)
                self.assertEqual(encoded(source), original)
                for step in source['steps']:
                    for event_id in step['evidence']:
                        item = observed['rows_by_event_id'][event_id]
                        self.assertIn(item['csv_row'], step['source_csv_rows'])
                        self.assertEqual(item['row']['session_id'], step['source_session_id'])
                self.assertEqual((folder / 'events.csv').read_bytes(), raw)
                self.assertEqual((folder / 'capture-manifest.json').read_bytes(), manifest_raw)
                if folder.name.startswith('CU02-'):
                    plan.update(parameter_source='NEW_TEST_PARAMETERS', parameters={}, items=[])
                    for step in source['steps']:
                        original_rows = [observed['rows_by_event_id'][eid]['row'] for eid in step['evidence']]
                        if all(row['interaction_type'] in {'input', 'change', 'paste'} for row in original_rows):
                            for eid, row in zip(step['evidence'], original_rows):
                                key = 'fresh_field_' + str(len(plan['parameters']) + 1)
                                plan['parameters'][key] = 'Fresh compatibility test value ' + str(len(plan['parameters']) + 1)
                                plan['items'].append(NativeObservationInputTests.execute(
                                    step['order'], eid, row['target_selector'], key))
                        else:
                            plan['items'].append(dict(kind='reference', source_refs=[dict(
                                order=step['order'], event_ids=copy.deepcopy(step['evidence']))],
                                reason='Observed background/screen event; no browser replay in this compatibility regression'))
                    prepared = prepare(source, plan, observations=observed)
                    self.assertEqual([step['target']['value'] for step in prepared['contract']['steps']],
                                     ['#schedule-title', '#schedule-description'])
                    self.assertEqual([step['action'] for step in prepared['scenario']['steps']], ['input', 'input'])
                    self.assertEqual(encoded(source), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
