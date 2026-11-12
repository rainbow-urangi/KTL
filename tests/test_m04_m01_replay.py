"""임시 합성 M01 원본만 사용한다. 실제 모델·브라우저·업무 실행·GT 등록은 없다."""
import ast
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from backend.evaluators import EvaluationError
from backend.m01 import M01CsvStore
from backend.m04.checks import prepare_contract
from backend.m04.replay import inspect_source, prepare_replay
from backend.session import RuntimeSession


class M01ObservedReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m01-replay-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.session = RuntimeSession()
        self.config = dict(targets={f'M0{i}': value for i, value in enumerate((65, 75, 80, 90, .79, 1, 80), 1)})
        self.fields = ('id event_id session_id event_time event_type page_url target_selector locators_json '
                       'element_tag interaction_type input_data page_title target_key input_control_type '
                       'capture_run_id capture_tab_id capture_frame_id capture_root_tab_id capture_tab_path').split()

    def rows(self, *, submit=False):
        definitions = [('page_view', 'body', 'body', ''), ('click', '#synthetic-title', 'input', 'text'),
                       ('change', '#synthetic-title', 'input', 'text'), ('click', '#synthetic-save', 'button', '')]
        if submit:
            definitions += [('submit', '#synthetic-form', 'form', ''), ('popup_close', '#synthetic-modal', 'div', '')]
        rows = []
        for index, (kind, target, tag, control) in enumerate(definitions, 1):
            row = dict.fromkeys(self.fields, '')
            xpath = '/html/body/form/button' if target == '#synthetic-save' else '/html/body/form' if tag == 'form' else '/html/body/' + tag
            row.update(id=str(index), event_id='SYNTHETIC-E' + str(index), session_id='SYNTHETIC-S1',
                event_time=f'2026-11-12T01:00:0{index}.000+00:00', event_type='DOM_EVENT',
                page_url='http://127.0.0.1:43210/synthetic', target_selector=target, element_tag=tag,
                locators_json=json.dumps(dict(selector_css=target, selector_xpath=xpath, element_tag=tag)),
                interaction_type=kind, input_data='PRIVATE_RAW_VALUE_NOT_RESTORED' if kind == 'change' else '',
                page_title='Synthetic fixture', target_key='css:' + target, input_control_type=control)
            rows.append(row)
        return rows

    def upload(self, rows=None):
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, self.fields)
        writer.writeheader()
        writer.writerows(rows or self.rows())
        raw = output.getvalue().encode('utf-8-sig')
        result = M01CsvStore(self.root, session=self.session).upload(dict(
            filename='synthetic-source.csv', csv_base64=base64.b64encode(raw).decode()), self.config)
        return result['dataset'], raw

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob('*') if path.is_file()}

    def test_inspection_only_reads_original_bytes_and_reports_fresh_parameter_names(self):
        dataset, raw = self.upload()
        before = self.snapshot()
        result = inspect_source(self.root, dataset['dataset_id'], session=self.session)
        self.assertEqual(result['status'], 'NEEDS_INPUT')
        self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['event_count'], 4)
        self.assertEqual(result['session_id'], 'SYNTHETIC-S1')
        self.assertEqual(result['missing_inputs'][0]['name'], 'row_3_value')
        self.assertEqual(result['missing_inputs'][0]['target'], '#synthetic-title')
        self.assertEqual([row['row'] for row in result['steps']], [1, 2, 3, 4])
        self.assertNotIn('PRIVATE_RAW_VALUE', json.dumps(result))
        self.assertNotIn('code', result)
        self.assertEqual(self.snapshot(), before)

    def test_prepare_preserves_all_four_sources_and_passes_the_unchanged_strict_contract(self):
        dataset, raw = self.upload()
        before = self.snapshot()
        result = prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': 'SYNTHETIC-FRESH'}, self.session)
        self.assertEqual(set(result), {'code', 'scenario', 'contract', 'source', 'source_files'})
        self.assertEqual(result['source']['dataset_id'], dataset['dataset_id'])
        self.assertFalse(result['source']['original_input_values_recovered'])
        self.assertEqual(set(result['source_files']), {'m01_source.csv', 'm01_manifest.json', 'm01_replay_source.json', 'm01_parameters.json'})
        self.assertEqual(result['source_files']['m01_source.csv'], raw)
        self.assertEqual(json.loads(result['source_files']['m01_replay_source.json']), result['source'])
        self.assertEqual(json.loads(result['source_files']['m01_parameters.json']), {'row_3_value': 'SYNTHETIC-FRESH'})
        self.assertEqual(prepare_contract(result['scenario']), result['contract'])
        self.assertEqual([step['source_csv_row'] for step in result['scenario']['steps']], [1, 2, 3, 4])
        self.assertEqual(result['scenario']['steps'][2]['value'], 'SYNTHETIC-FRESH')
        self.assertEqual(result['scenario']['source_kind'], 'M01_OBSERVED_REPLAY')
        self.assertFalse(result['scenario']['model_inference'])
        tree = ast.parse(result['code'])
        self.assertTrue(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
        self.assertIn('from ktl_runtime import business_step', result['code'])
        self.assertIn("SCENARIO_ID = 'M01-REPLAY-", result['code'])
        self.assertNotIn('--headless', result['code'])
        self.assertNotIn('PRIVATE_RAW_VALUE_NOT_RESTORED', result['code'])
        self.assertNotIn('OPENAI', result['code'])
        self.assertEqual(self.snapshot(), before, 'Pure preparation must not register, persist or execute')

    def test_submit_after_an_exact_form_child_click_is_a_reference_and_never_executed_twice(self):
        dataset, _ = self.upload(self.rows(submit=True))
        inspection = inspect_source(self.root, dataset['dataset_id'], self.session)
        self.assertEqual(inspection['status'], 'NEEDS_INPUT', inspection)
        self.assertEqual(inspection['steps'][4]['kind'], 'reference')
        result = prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': 'SYNTHETIC'}, self.session)
        self.assertEqual([step['action'] for step in result['scenario']['steps']], ['open', 'click', 'input', 'click', 'verify'])
        self.assertNotIn(".submit(", result['code'])
        self.assertEqual([row['row'] for row in result['source']['row_ids']], [1, 2, 3, 4, 5, 6])

    def test_broad_calendar_cell_blocks_creation_instead_of_inventing_a_native_child(self):
        rows = self.rows()
        rows[1].update(target_selector='.monthly-calendar__cell:nth-of-type(10)',
                       target_key='css:.monthly-calendar__cell:nth-of-type(10)', element_tag='div',
                       locators_json=json.dumps(dict(selector_css='.monthly-calendar__cell:nth-of-type(10)', element_tag='div')))
        dataset, _ = self.upload(rows)
        inspection = inspect_source(self.root, dataset['dataset_id'], self.session)
        self.assertEqual(inspection['status'], 'NOT_READY')
        self.assertIn(2, [row['row'] for row in inspection['blockers']])
        self.assertIn('등록', inspection['blockers'][0]['reason'])
        with self.assertRaises(EvaluationError):
            prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': 'SYNTHETIC'}, self.session)

    def test_collector_result_and_enrichment_events_remain_references_without_inventing_actions(self):
        rows = self.rows()
        reference_kinds = ('ui_outcome', 'api_transaction_error', 'api_transaction_timeout',
                           'fetch_error', 'xhr_error', 'value_reflection', 'grid_context_enrichment')
        for number, kind in enumerate(reference_kinds, len(rows) + 1):
            rows.append(dict(rows[0], id=str(number), event_id=f'SYNTHETIC-E{number}',
                             interaction_type=kind))
        dataset, raw = self.upload(rows)
        before = self.snapshot()
        inspection = inspect_source(self.root, dataset['dataset_id'], self.session)
        self.assertEqual(inspection['status'], 'NEEDS_INPUT', inspection['blockers'])
        self.assertEqual(inspection['event_count'], len(rows))
        self.assertEqual([item['interaction_type'] for item in inspection['steps'][4:]], list(reference_kinds))
        self.assertTrue(all(item['kind'] == 'reference' and item['action'] is None
                            for item in inspection['steps'][4:]))
        prepared = prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': 'SYNTHETIC'}, self.session)
        self.assertEqual([item['action'] for item in prepared['scenario']['steps']],
                         ['open', 'click', 'input', 'click'])
        self.assertEqual(prepared['source_files']['m01_source.csv'], raw)
        self.assertEqual(prepared['source']['row_ids'],
                         [dict(row=index, event_id=row['event_id']) for index, row in enumerate(rows, 1)])
        self.assertEqual(self.snapshot(), before)

    def test_missing_or_inconsistent_selectors_unsupported_controls_and_unknown_events_are_not_dropped(self):
        mutations = [lambda row: row.update(target_selector=''),
                     lambda row: row.update(target_key='css:#different'),
                     lambda row: row.update(locators_json=json.dumps(dict(selector_css='#different'))),
                     lambda row: row.update(input_control_type='password'),
                     lambda row: row.update(interaction_type='keydown'),
                     lambda row: row.update(interaction_type='unknown-native-action')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                rows = self.rows(); mutate(rows[2]); dataset, _ = self.upload(rows)
                inspection = inspect_source(self.root, dataset['dataset_id'], self.session)
                self.assertEqual(inspection['status'], 'NOT_READY')
                self.assertEqual(inspection['blockers'][0]['row'], 3)
                self.assertEqual(len(inspection['steps']), 4)

    def test_missing_extra_masked_and_secret_parameters_fail_without_echoing_the_raw_value(self):
        dataset, _ = self.upload()
        for parameters in ({}, {'row_99_value': 'x'}, {'row_3_value': '[MASKED]'},
                           {'row_3_value': 'password=PRIVATE-SENTINEL'}, {'row_3_value': 'x\nprivate'}):
            with self.subTest(parameters_shape=list(parameters)):
                with self.assertRaises(EvaluationError) as error:
                    prepare_replay(self.root, dataset['dataset_id'], parameters, self.session)
                self.assertNotIn('PRIVATE-SENTINEL', str(error.exception))
                self.assertNotIn('x\nprivate', str(error.exception))

    def test_source_sha_changes_expired_sessions_and_archive_bypass_are_rejected(self):
        dataset, raw = self.upload()
        with self.assertRaises(EvaluationError):
            inspect_source(self.root, dataset['dataset_id'], RuntimeSession())
        with self.assertRaises(EvaluationError):
            inspect_source(self.root, dataset['dataset_id'], self.session, allow_archived=True)
        path = self.root / 'data/development/m01_uploads' / dataset['dataset_id'] / 'source.csv'
        path.write_bytes(raw + b' ')
        with self.assertRaises(EvaluationError):
            prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': 'SYNTHETIC'}, self.session)

    def test_row_order_is_never_resorted_and_explicit_session_scope_keeps_original_row_numbers(self):
        rows = self.rows()
        rows[2]['event_time'] = '2026-11-11T01:00:00.000+00:00'
        other = dict(rows[0], id='5', event_id='SYNTHETIC-OTHER', session_id='SYNTHETIC-S2')
        rows.append(other)
        dataset, _ = self.upload(rows)
        with self.assertRaises(EvaluationError):
            inspect_source(self.root, dataset['dataset_id'], self.session)
        result = prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': 'SYNTHETIC'},
                                self.session, session_id='SYNTHETIC-S1')
        self.assertEqual([row['row'] for row in result['source']['row_ids']], [1, 2, 3, 4])
        self.assertEqual([row['source_csv_row'] for row in result['scenario']['steps']], [1, 2, 3, 4])

    def test_unproven_submit_multitab_iframe_and_unsafe_url_are_blocked(self):
        for alter in ('submit', 'tabs', 'iframe', 'url'):
            with self.subTest(alter=alter):
                rows = self.rows(submit=True)
                if alter == 'submit':
                    rows[3]['locators_json'] = json.dumps(dict(selector_css='#synthetic-save', element_tag='button', selector_xpath='/unrelated/button'))
                elif alter == 'tabs':
                    for row in rows:
                        row.update(capture_run_id='KTL-M01-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                                   capture_tab_id='1', capture_frame_id='0', capture_root_tab_id='1', capture_tab_path='[1]')
                    rows[1].update(capture_tab_id='2', capture_tab_path='[1,2]')
                elif alter == 'iframe':
                    for row in rows:
                        row.update(capture_run_id='KTL-M01-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                                   capture_tab_id='1', capture_frame_id='0')
                    rows[1]['capture_frame_id'] = '3'
                else:
                    rows[0]['page_url'] = 'http://127.0.0.1:43210/synthetic?token=PRIVATE-SENTINEL'
                dataset, _ = self.upload(rows)
                inspection = inspect_source(self.root, dataset['dataset_id'], self.session)
                self.assertEqual(inspection['status'], 'NOT_READY')
                self.assertNotIn('PRIVATE-SENTINEL', json.dumps(inspection['blockers']))

    def test_generated_source_uses_only_safe_literals_and_never_executes_during_preparation(self):
        dataset, _ = self.upload()
        payload = "'); __import__('os').system('NEVER_EXECUTE'); #"
        result = prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': payload}, self.session)
        tree = ast.parse(result['code'])
        literal = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'DATA' for target in node.targets))
        self.assertIsInstance(literal, ast.Call)
        self.assertEqual(json.loads(ast.literal_eval(literal.args[0]))['scenario']['steps'][2]['value'], payload)
        self.assertNotIn('exec(', result['code'])
        self.assertNotIn('eval(', result['code'])

    def test_webdriver_reserved_keys_cannot_be_injected_as_business_text(self):
        dataset, _ = self.upload()
        # Selenium uses these private key code points for Enter/modifiers/etc.;
        # treating them as text could execute an unintended submit before failing.
        for value in ('\ue000', '\ue007', 'SYNTHETIC\ue009', '\ue053', '\ue05d'):
            with self.subTest(codepoints=[ord(char) for char in value]):
                with self.assertRaises(EvaluationError):
                    prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': value}, self.session)
        for value in ('정상 업무값 123 ✓', 'SYNTHETIC\ue100'):
            result = prepare_replay(self.root, dataset['dataset_id'], {'row_3_value': value}, self.session)
            self.assertEqual(result['scenario']['steps'][2]['value'], value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
