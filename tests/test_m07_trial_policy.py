"""Pure synthetic policy validation; no files, provider, model, browser or GT."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m07.meeting import prepare_batch, schema
from backend.m07.trial import describe_trial, normalize_policy


def scenario(number):
    identity = f'SYNTHETIC-SCENARIO-{number:02d}'
    path = f'/synthetic/work/{number:02d}'
    url = 'https://example.invalid' + path
    return dict(scenario_id=identity, scenario_name=f'Synthetic workflow {number}',
                business_unit_id=f'SYNTHETIC-BU-{number:02d}', workflow_id=f'SYNTHETIC-WF-{number:02d}',
                steps=[dict(order=1, action='open', target='Synthetic business screen', url=url,
                            expected_result='The independently specified synthetic page is displayed')],
                execution_contract=dict(version=1, scenario_id=identity, steps=[dict(
                    order=1, action='open', target=dict(url=url),
                    checks=[dict(kind='url_path', expected=path)])]))


def legacy():
    return dict(items=[dict(input_id=f'SYNTHETIC-INPUT-{number:02d}', scenario=scenario(number))
                       for number in range(1, 21)])


def two_batches():
    payload = legacy()
    for index in range(10, 20):
        payload['items'][index]['scenario'] = deepcopy(payload['items'][index - 10]['scenario'])
    payload['trial_policy'] = dict(batches=[dict(batch_id=f'BATCH-{number + 1}',
        input_ids=[row['input_id'] for row in payload['items'][number * 10:(number + 1) * 10]])
        for number in range(2)])
    return payload


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


class TrialPolicyTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection', 'urllib.request.urlopen', 'subprocess.Popen', 'pathlib.Path.open'):
            self.enterContext(patch(target, side_effect=AssertionError('Policy validation must not perform I/O')))

    def test_legacy_input_remains_globally_unique_and_policy_is_read_only(self):
        payload = legacy()
        before = deepcopy(payload)
        policy = normalize_policy(payload)
        self.assertEqual(policy['mode'], 'LEGACY_UNIQUE_SCENARIOS')
        self.assertEqual(len(policy['batches']), 1)
        self.assertEqual(policy['batches'][0]['input_ids'], [row['input_id'] for row in payload['items']])
        self.assertEqual(len(prepare_batch(payload)), 20)
        policy['batches'][0]['input_ids'].clear()
        self.assertEqual(payload, before)
        repeated = two_batches()
        repeated.pop('trial_policy')
        with self.assertRaises(EvaluationError):
            prepare_batch(repeated)

    def test_explicit_ten_scenarios_twice_preserves_all_original_rows_without_new_fields(self):
        payload = two_batches()
        before = deepcopy(payload)
        prepared = prepare_batch(payload)
        self.assertEqual(len(prepared), 20)
        self.assertEqual(payload, before)
        for row, original in zip(prepared, before['items']):
            self.assertEqual(set(row), {'input_id', 'scenario', 'source_raw'})
            self.assertEqual(row['source_raw'], original)
            self.assertEqual(row['scenario'], original['scenario'])
            self.assertNotIn('batch_id', row['source_raw'])
        self.assertEqual(prepared[0]['scenario'], prepared[10]['scenario'])
        self.assertNotEqual(prepared[0]['input_id'], prepared[10]['input_id'])
        prepared[0]['scenario']['steps'].clear()
        prepared[10]['source_raw']['scenario']['steps'].clear()
        self.assertEqual(payload, before)
        self.assertTrue(prepared[0]['source_raw']['scenario']['steps'])
        self.assertTrue(prepared[10]['scenario']['steps'])

    def test_same_batch_rejects_same_id_and_behavior_even_when_labels_change(self):
        for change in ('scenario_id', 'behavior'):
            payload = two_batches()
            original = payload['items'][0]['scenario']
            replacement = payload['items'][1]['scenario']
            if change == 'scenario_id':
                replacement = deepcopy(original)
                payload['items'][1]['scenario'] = replacement
            else:
                replacement['steps'] = deepcopy(original['steps'])
                replacement['steps'][0]['expected_result'] = 'Different prose does not create a new execution'
                replacement['execution_contract']['steps'] = deepcopy(original['execution_contract']['steps'])
            with self.subTest(change=change), self.assertRaises(EvaluationError):
                prepare_batch(payload)

    def test_repeated_scenario_id_requires_the_entire_source_to_be_identical(self):
        for change in ('name', 'description', 'workflow', 'route', 'checkpoint'):
            payload = two_batches()
            duplicate = payload['items'][10]['scenario']
            if change == 'name':
                duplicate['scenario_name'] += ' changed'
            elif change == 'description':
                duplicate['description'] = 'A new source with the same identifier'
            elif change == 'workflow':
                duplicate['workflow_id'] = 'SYNTHETIC-OTHER-WORKFLOW'
            elif change == 'route':
                duplicate['steps'][0]['url'] += '/changed'
                duplicate['execution_contract']['steps'][0]['target']['url'] += '/changed'
                duplicate['execution_contract']['steps'][0]['checks'][0]['expected'] += '/changed'
            else:
                duplicate['screenshot_checkpoints'] = dict(before=1, after=1)
            with self.subTest(change=change), self.assertRaises(EvaluationError):
                prepare_batch(payload)
        payload = two_batches()
        payload['items'][10]['scenario'] = dict(reversed(list(payload['items'][10]['scenario'].items())))
        self.assertEqual(len(prepare_batch(payload)), 20, 'JSON object key order does not change the source')

    def test_cross_batch_identical_behavior_can_have_distinct_scenario_ids(self):
        payload = two_batches()
        duplicate = payload['items'][10]['scenario']
        duplicate['scenario_id'] = 'SYNTHETIC-SECOND-TRIAL-ID'
        duplicate['execution_contract']['scenario_id'] = duplicate['scenario_id']
        prepared = prepare_batch(payload)
        self.assertEqual(len(prepared), 20)
        self.assertEqual(len({row['scenario']['scenario_id'] for row in prepared}), 11)

    def test_all_input_ids_are_unique_across_batches(self):
        payload = two_batches()
        payload['items'][10]['input_id'] = payload['items'][0]['input_id']
        payload['trial_policy']['batches'][1]['input_ids'][0] = payload['items'][0]['input_id']
        with self.assertRaises(EvaluationError):
            normalize_policy(payload)
        with self.assertRaises(EvaluationError):
            prepare_batch(payload)

    def test_batch_membership_is_complete_unique_and_never_silently_reordered(self):
        for change in ('missing', 'unknown', 'repeated', 'batch-order', 'item-order', 'empty', 'batch-id'):
            payload = two_batches()
            batches = payload['trial_policy']['batches']
            if change == 'missing':
                batches[1]['input_ids'].pop()
            elif change == 'unknown':
                batches[1]['input_ids'][-1] = 'SYNTHETIC-UNKNOWN-ID'
            elif change == 'repeated':
                batches[1]['input_ids'][-1] = batches[0]['input_ids'][0]
            elif change == 'batch-order':
                batches.reverse()
            elif change == 'item-order':
                batches[0]['input_ids'].reverse()
            elif change == 'empty':
                batches[0]['input_ids'] = []
            else:
                batches[1]['batch_id'] = batches[0]['batch_id']
            before = deepcopy(payload)
            with self.subTest(change=change), self.assertRaises(EvaluationError):
                normalize_policy(payload)
            self.assertEqual(payload, before)

    def test_policy_never_accepts_caller_retry_model_or_official_overrides(self):
        for container, key, value in [('policy', 'max_attempts_per_input', 2), ('policy', 'automatic_retry_count', 1),
                ('policy', 'model', 'other-model'), ('policy', 'official_pass', True),
                ('batch', 'retry', True), ('payload', 'score', 100)]:
            payload = two_batches()
            target = payload['trial_policy'] if container == 'policy' else payload['trial_policy']['batches'][0] if container == 'batch' else payload
            target[key] = value
            with self.subTest(key=key), self.assertRaises(EvaluationError):
                normalize_policy(payload)

    def test_malformed_types_unsafe_ids_and_nonfinite_json_fail_without_echoing_values(self):
        for value in (None, [], '', True, {'batches': None}, {'batches': []}):
            payload = two_batches(); payload['trial_policy'] = value
            with self.subTest(kind=type(value).__name__), self.assertRaises(EvaluationError):
                normalize_policy(payload)
        for value in ('', ' bad', 'SYNTHETIC-PRIVATE\nVALUE', '\ud800', 'x' * 257, 7, None, True):
            payload = two_batches(); payload['trial_policy']['batches'][0]['batch_id'] = value
            with self.subTest(kind=type(value).__name__), self.assertRaises(EvaluationError) as error:
                normalize_policy(payload)
            self.assertNotIn('SYNTHETIC-PRIVATE', str(error.exception))
        for value in (float('nan'), object()):
            payload = two_batches(); payload['items'][0]['scenario']['description'] = value
            with self.assertRaises(EvaluationError):
                normalize_policy(payload)

    def test_fixed_description_distinguishes_twenty_inputs_ten_scenarios_and_two_batches(self):
        payload = two_batches(); before = deepcopy(payload); prepared = prepare_batch(payload)
        description = describe_trial(payload, prepared, 'SYNTHETIC-MODEL', 'synthetic-prompt-v1')
        self.assertEqual((description['input_count'], description['denominator'], description['distinct_scenario_count'],
                          description['business_unit_count'], description['batch_count']), (20, 20, 10, 10, 2))
        self.assertEqual([row['input_count'] for row in description['batches']], [10, 10])
        self.assertEqual([row['distinct_scenario_count'] for row in description['batches']], [10, 10])
        self.assertEqual([row['input_count'] for row in description['business_units']], [2] * 10)
        self.assertEqual([row['batch_id'] for row in description['inputs']], ['BATCH-1'] * 10 + ['BATCH-2'] * 10)
        self.assertEqual(description['max_attempts_per_input'], 1)
        self.assertEqual(description['automatic_retry_count'], 0)
        self.assertIs(description['stop_remaining_on_http_429'], True)
        self.assertIsNone(description['official_pass'])
        self.assertNotIn('score', description)
        self.assertEqual(description['input_payload_sha256'], hashlib.sha256(encoded(payload)).hexdigest())
        self.assertEqual(description['inputs'][0]['source_sha256'], hashlib.sha256(encoded(payload['items'][0])).hexdigest())
        self.assertEqual(description['inputs'][0]['scenario_sha256'], description['inputs'][10]['scenario_sha256'])
        self.assertNotEqual(description['inputs'][0]['source_sha256'], description['inputs'][10]['source_sha256'])
        self.assertEqual(encoded(description), encoded(describe_trial(payload, prepared, 'SYNTHETIC-MODEL', 'synthetic-prompt-v1')))
        self.assertEqual(payload, before)
        description['policy']['batches'][0]['input_ids'].clear()
        description['inputs'].clear()
        self.assertEqual(payload, before)

    def test_description_binds_model_prompt_and_batch_plan_without_copying_business_values(self):
        payload = two_batches()
        for row in payload['items']:
            row['scenario']['description'] = 'SYNTHETIC-PRIVATE-BUSINESS-SENTINEL'
        prepared = prepare_batch(payload)
        first = describe_trial(payload, prepared, 'SYNTHETIC-MODEL', 'synthetic-prompt-v1')
        self.assertNotIn('SYNTHETIC-PRIVATE-BUSINESS-SENTINEL', json.dumps(first))
        for model, prompt in [('OTHER-MODEL', 'synthetic-prompt-v1'), ('SYNTHETIC-MODEL', 'other-prompt-v2')]:
            changed = describe_trial(payload, prepared, model, prompt)
            self.assertNotEqual(hashlib.sha256(encoded(first)).hexdigest(), hashlib.sha256(encoded(changed)).hexdigest())
        changed = deepcopy(payload); changed['trial_policy']['batches'][0]['batch_id'] = 'RENAMED-BATCH'
        self.assertNotEqual(first['input_payload_sha256'],
                            describe_trial(changed, prepare_batch(changed), 'SYNTHETIC-MODEL', 'synthetic-prompt-v1')['input_payload_sha256'])

    def test_description_rejects_changed_or_unprepared_sources_and_empty_model_versions(self):
        payload = two_batches(); prepared = prepare_batch(payload)
        for change in ('source', 'scenario', 'order', 'missing', 'extra'):
            items = deepcopy(prepared)
            if change == 'source':
                items[0]['source_raw']['scenario']['scenario_name'] += ' changed'
            elif change == 'scenario':
                items[0]['scenario']['scenario_name'] += ' changed'
            elif change == 'order':
                items.reverse()
            elif change == 'missing':
                items.pop()
            else:
                items[0]['batch_id'] = 'not part of the original returned row'
            with self.subTest(change=change), self.assertRaises(EvaluationError):
                describe_trial(payload, items, 'SYNTHETIC-MODEL', 'synthetic-prompt-v1')
        for model, prompt in [('', 'version'), ('model', ''), (None, 'version'), ('model', '\nprivate')]:
            with self.subTest(model_type=type(model).__name__), self.assertRaises(EvaluationError):
                describe_trial(payload, prepared, model, prompt)

    def test_guidance_exposes_optional_policy_without_changing_original_example(self):
        value = schema()
        self.assertEqual(value['input_schema']['required'], ['items'])
        self.assertIn('trial_policy', value['input_schema']['properties'])
        self.assertEqual(value['example'], {'items': [value['example_item']]})
        self.assertEqual(len(value['example']['items']), 1)
        self.assertEqual(value['denominator'], 20)


if __name__ == '__main__':
    unittest.main()
