"""Temporary synthetic M07 input validation only; no browser, model, or official evidence."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m04.checks import prepare_contract
from backend.m07 import meeting


def batch():
    rows = []
    for number in range(1, 21):
        identity = 'SYNTHETIC-MEETING-' + str(number)
        value = 'SYNTHETIC INPUT ' + str(number)
        url = 'https://synthetic.example.invalid/work'
        field = dict(by='css selector', value='#business-search')
        rows.append(dict(input_id='INPUT-' + str(number), scenario=dict(
            scenario_id=identity, scenario_name='SYNTHETIC scenario ' + str(number),
            business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
            preconditions=['SYNTHETIC authenticated business page'],
            steps=[dict(order=1, action='open', target='SYNTHETIC work page', url=url,
                        expected_result='SYNTHETIC work page displayed'),
                   dict(order=2, action='input', target='SYNTHETIC search field', value=value,
                        expected_result='SYNTHETIC search field holds the supplied value')],
            execution_contract=dict(version=1, scenario_id=identity, steps=[
                dict(order=1, action='open', target=dict(url=url),
                     checks=[dict(kind='url_path', expected='/work'), dict(kind='visible', target=field)]),
                dict(order=2, action='input', target=field, checks=[dict(kind='value', expected=value)])]),
            screenshot_checkpoints=dict(before=1, after=2))))
    return dict(items=rows)


class MeetingInputContractTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No test network')))
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No test HTTP/LLM')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No test subprocess/browser')))

    def assert_invalid(self, payload):
        with self.assertRaises(EvaluationError):
            meeting.prepare_batch(payload)

    def test_exactly_twenty_valid_inputs_preserve_raw_values_without_m03_claims(self):
        payload = batch()
        before = deepcopy(payload)
        result = meeting.prepare_batch(payload)
        self.assertEqual(payload, before)
        self.assertEqual(len(result), 20)
        self.assertEqual([row['input_id'] for row in result], [row['input_id'] for row in before['items']])
        for actual, source in zip(result, before['items']):
            self.assertEqual(actual['source_raw'], source)
            self.assertEqual(actual['scenario'], source['scenario'])
            self.assertEqual(prepare_contract(actual['scenario'])['version'], 1)
            self.assertNotIn('status', actual['scenario'])
            self.assertNotIn('source_m03_run_id', actual['scenario'])
            self.assertNotIn('generated_by_llm', actual['scenario'])
        result[0]['scenario']['steps'][0]['target'] = 'changed'
        result[1]['source_raw']['scenario']['steps'].clear()
        self.assertEqual(payload, before)
        self.assertEqual(result[0]['source_raw'], before['items'][0])
        self.assertTrue(result[1]['scenario']['steps'])
        self.assertEqual(meeting.normalize_batch(payload), meeting.prepare_batch(payload))

    def test_count_container_and_row_fields_are_strict(self):
        invalid = [None, [], {}, dict(items=None), dict(items=[]), dict(items=batch()['items'][:19]),
                   dict(items=batch()['items'] + [deepcopy(batch()['items'][0])]),
                   dict(batch(), run_mode='OFFICIAL')]
        for replacement in [None, 'text', {}, dict(input_id='x'), dict(batch()['items'][0], source_m03_run_id='fake')]:
            payload = batch()
            payload['items'][0] = replacement
            invalid.append(payload)
        for payload in invalid:
            with self.subTest(kind=type(payload).__name__):
                self.assert_invalid(payload)

    def test_ids_and_actual_execution_inputs_must_be_independent(self):
        for key in ['input_id', 'scenario_id', 'behavior']:
            payload = batch()
            if key == 'input_id':
                payload['items'][1]['input_id'] = payload['items'][0]['input_id']
            elif key == 'scenario_id':
                identity = payload['items'][0]['scenario']['scenario_id']
                payload['items'][1]['scenario']['scenario_id'] = identity
                payload['items'][1]['scenario']['execution_contract']['scenario_id'] = identity
            else:
                original = payload['items'][0]['scenario']
                duplicate = payload['items'][1]['scenario']
                duplicate['steps'] = deepcopy(original['steps'])
                duplicate['execution_contract']['steps'] = deepcopy(original['execution_contract']['steps'])
                duplicate['business_unit_id'] = 'DIFFERENT_LABEL'
                duplicate['steps'][0]['expected_result'] = 'Different description for the same check'
            with self.subTest(key=key):
                self.assert_invalid(payload)

    def test_scenario_input_does_not_accept_code_result_or_fabricated_provenance(self):
        for key, value in [('code', 'print(1)'), ('code_source', 'PREPARED'), ('generated_by_llm', True),
                           ('m03_run_id', 'DEV-M03-FAKE'), ('source_m03_run_id', 'fake'), ('status', 'SUCCESS'),
                           ('official', True), ('score', 100), ('syntax_status', 'PASS'), ('final_status', 'PASS'),
                           ('ground_truth', []), ('evaluation_pairing', []), ('official_pass', None)]:
            payload = batch()
            payload['items'][0]['scenario'][key] = value
            with self.subTest(key=key):
                self.assert_invalid(payload)
        payload = batch()
        payload['items'][0]['scenario']['steps'][0]['ground_truth'] = ['hidden']
        self.assert_invalid(payload)

    def test_credentials_gt_and_unsafe_auth_checks_are_rejected_recursively(self):
        replacements = [('expected_result', 'password=SYNTHETIC_SECRET'),
                        ('expected_result', 'Bearer SYNTHETIC_SECRET'),
                        ('url', 'https://user:secret@synthetic.example.invalid/work'),
                        ('url', 'https://synthetic.example.invalid/work?token=x'),
                        ('url', 'https://synthetic.example.invalid/work#fragment')]
        for field, value in replacements:
            payload = batch()
            payload['items'][0]['scenario']['steps'][0][field] = value
            with self.subTest(field=field, value=value):
                self.assert_invalid(payload)
        payload = batch()
        step = payload['items'][0]['scenario']['execution_contract']['steps'][1]
        step['target'] = dict(by='css selector', value='#password')
        self.assert_invalid(payload)
        payload = batch()
        payload['items'][0]['scenario']['execution_contract']['steps'][1]['checks'][0]['gt_label'] = 'hidden'
        self.assert_invalid(payload)

    def test_explicit_complete_conditions_match_the_scenario_and_browser_contract(self):
        def no_contract(scenario):
            scenario.pop('execution_contract')

        def no_checks(scenario):
            scenario['execution_contract']['steps'][1]['checks'] = []

        def unknown_check(scenario):
            scenario['execution_contract']['steps'][1]['checks'][0]['kind'] = 'made_up_success'

        def incorrect_order(scenario):
            scenario['steps'][1]['order'] = 3

        def mismatched_action(scenario):
            scenario['execution_contract']['steps'][1]['action'] = 'click'

        def different_url(scenario):
            scenario['execution_contract']['steps'][0]['target']['url'] += '/different'

        def invalid_checkpoint(scenario):
            scenario['screenshot_checkpoints'] = dict(before=2, after=1)

        def missing_input(scenario):
            scenario['steps'][1].pop('value')

        def local_file(scenario):
            scenario['steps'][0]['url'] = 'file:///C:/private.txt'
            scenario['execution_contract']['steps'][0]['target']['url'] = 'file:///C:/private.txt'

        for change in [no_contract, no_checks, unknown_check, incorrect_order, mismatched_action,
                       different_url, invalid_checkpoint, missing_input, local_file]:
            payload = batch()
            change(payload['items'][0]['scenario'])
            with self.subTest(change=change.__name__):
                self.assert_invalid(payload)

    def test_input_is_bounded_json_with_no_silent_type_coercion(self):
        for key, value in [('scenario_id', ' '), ('scenario_name', 'x' * 257), ('workflow_id', 'bad\nline'),
                           ('description', 'x' * 4097), ('description', float('nan')),
                           ('description', object()), ('description', 'bad\x00text'), ('description', '\ud800'),
                           ('preconditions', 'not a list')]:
            payload = batch()
            payload['items'][0]['scenario'][key] = value
            with self.subTest(key=key):
                self.assert_invalid(payload)
        payload = batch()
        payload['items'][0]['scenario']['steps'][0]['order'] = True
        self.assert_invalid(payload)
        payload = batch()
        recursive = []
        recursive.append(recursive)
        payload['items'][0]['scenario']['description'] = recursive
        self.assert_invalid(payload)
        for malformed in [None, False, [], {}, 7]:
            payload = batch()
            payload['items'][0]['scenario']['steps'][0]['action'] = malformed
            with self.subTest(action_type=type(malformed).__name__):
                self.assert_invalid(payload)

    def test_batch_size_is_limited_before_generation_and_without_modifying_input(self):
        payload = batch()
        for row in payload['items']:
            row['scenario']['description'] = 'S' * 2000
            row['scenario']['preconditions'] = ['S' * 2000] * 20
        self.assertGreater(len(json.dumps(payload).encode('utf-8')), meeting.MAX_BATCH_BYTES)
        before = deepcopy(payload)
        self.assert_invalid(payload)
        self.assertEqual(payload, before)

    def test_schema_is_read_only_guidance_and_never_fabricates_twenty_approved_inputs(self):
        value = meeting.schema()
        self.assertEqual(value['required_count'], 20)
        self.assertEqual(value['denominator'], 20)
        self.assertEqual(value['target_percent'], 80)
        self.assertEqual(value['browser'], 'chrome')
        self.assertEqual(value['max_batch_bytes'], 256 * 1024)
        item_schema = value['input_schema']['properties']['items']
        self.assertEqual(item_schema['minItems'], 20)
        self.assertEqual(item_schema['maxItems'], 20)
        self.assertEqual(item_schema['items']['required'], ['input_id', 'scenario'])
        self.assertEqual(value['example_item'], value['example']['items'][0])
        self.assertTrue(value['example_only'])
        self.assertEqual(len(value['example']['items']), 1)
        self.assert_invalid(value['example'])
        self.assertEqual(value['source_document']['timestamps'][0], '32:39')
        self.assertEqual(value['source_document']['timestamps'][-1], '35:51')
        self.assertNotIn('code', json.dumps(value['example']))
        value['source_document']['timestamps'].clear()
        value['example']['items'].clear()
        self.assertTrue(meeting.schema()['source_document']['timestamps'])
        self.assertEqual(len(meeting.schema()['example']['items']), 1)


if __name__ == '__main__':
    unittest.main()
