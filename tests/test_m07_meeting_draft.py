"""The optional twenty-input draft is task data, never generated code or evidence."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from backend.m07 import generator
from backend.m07.meeting import prepare_batch
from backend.m07.meeting_draft import draft


class MeetingDraftTests(unittest.TestCase):
    def test_draft_contains_twenty_distinct_reviewable_inputs_without_code_or_success_claims(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('No draft network')), \
                patch('subprocess.Popen', side_effect=AssertionError('No draft browser')):
            result = draft()
        self.assertTrue(result['draft'])
        self.assertFalse(result['approved_for_official'])
        self.assertEqual(len(result['items']), 20)
        self.assertEqual(len(prepare_batch({'items': result['items']})), 20)
        self.assertEqual({row['scenario']['workflow_id'] for row in result['items']}, {f'CU{number:02d}' for number in range(1, 11)})
        for item in result['items']:
            self.assertEqual(set(item), {'input_id', 'scenario'})
            self.assertNotIn('code', item['scenario'])
            self.assertNotIn('generated_by_llm', item['scenario'])
            self.assertNotIn('status', item['scenario'])
        self.assertNotIn('webdriver.Chrome', json.dumps(result))

    def test_lookup_variants_select_different_real_rows_and_registration_inputs_differ(self):
        items = draft()['items']
        for number in range(0, 20, 2):
            first, second = (items[number + offset]['scenario'] for offset in (0, 1))
            self.assertNotEqual(first['execution_contract']['steps'], second['execution_contract']['steps'])
            if first['workflow_id'] in {'CU01', 'CU03', 'CU05', 'CU07', 'CU09'}:
                self.assertNotEqual(first['execution_contract']['steps'][1]['target'], second['execution_contract']['steps'][1]['target'])

    def test_new_drafts_do_not_overwrite_previous_inputs(self):
        first = draft()
        frozen = deepcopy(first)
        second = draft()
        self.assertEqual(first, frozen)
        self.assertTrue({row['scenario']['scenario_id'] for row in first['items']}.isdisjoint(
                        row['scenario']['scenario_id'] for row in second['items']))

    def test_meeting_prompt_uses_trusted_chrome_authentication_but_requires_llm_business_code(self):
        scenario = draft()['items'][2]['scenario']
        original = deepcopy(scenario)
        instructions, text = generator.prompt(dict(scenario, meeting_protocol=True), {})
        self.assertIn('driver = authenticated_chrome()', instructions)
        self.assertIn('complete_authentication(driver)', instructions)
        self.assertIn('generate every native business UI action', instructions)
        self.assertIn('no prepared Python code is supplied', instructions)
        self.assertNotIn('After login submit, wait', instructions)
        request = json.loads(text)
        self.assertEqual(request['scenario']['screenshot_checkpoints'], scenario['screenshot_checkpoints'])
        self.assertEqual(request['scenario']['description'], scenario['description'])
        self.assertNotIn('username_selector', request['execution_context']['login'])
        self.assertEqual(scenario, original)

    def test_card_registration_prompt_has_no_unrelated_category_search_requirements(self):
        scenario = draft()['items'][-1]['scenario']
        _, text = generator.prompt(dict(scenario, meeting_protocol=True), {})
        self.assertNotIn('cards', json.loads(text)['execution_context'])


if __name__ == '__main__':
    unittest.main()
