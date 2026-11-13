"""합성 DOM의 실제 관측값·판정·마스킹 검사."""
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from backend.m04.checks import RuntimeChecks, _NativeSubmitResponse, planned_check_results


NODE = shutil.which('node')
LOC = dict(by='css selector', value='#field')
NODE_DOM = r"""const r=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=Object.fromEntries(Object.entries(r.nodes).map(([id,state])=>[id,{
 tagName:Object.hasOwn(state,'value')?'INPUT':'DIV',type:'text',...state,
 getAttribute(name){return this.attributes?.[name]??this[name]??null;},
 getClientRects(){return this.hidden?[]:[{}];}
}]));
for(const n of Object.values(nodes))n.parentElement=nodes[n.parent]||null;
global.document={querySelectorAll(s){return(r.selectors[s]||[]).map(id=>nodes[id]);},
 querySelector(s){return this.querySelectorAll(s)[0]||null;},activeElement:nodes[r.focus]||null};
global.getComputedStyle=n=>({visibility:'visible',opacity:'1',...n.style});
process.stdout.write(JSON.stringify(Function(r.script).apply(null,r.args)));"""


@unittest.skipUnless(NODE, '합성 DOM 실행에 Node 필요')
class ObservationTests(unittest.TestCase):
    def checker(self, condition, nodes=None, selectors=None, focus=None):
        definition = dict(order=1, action='verify', target=LOC, checks=[condition])
        checker = RuntimeChecks(dict(steps=[definition]))
        driver = object()
        checker.raw_execute = lambda *args: dict(value='/fixture')
        checker.begin(1, [driver])
        state = dict(nodes={'field': dict(value='Synthetic actual')} if nodes is None else nodes,
                     selectors={'#field': ['field']} if selectors is None else selectors, focus=focus)
        calls = []

        def execute(unused, script, *args):
            calls.append((script, args))
            payload = dict(state, script=script, args=args)
            result = subprocess.run([NODE, '-e', NODE_DOM], input=json.dumps(payload),
                                    capture_output=True, encoding='utf-8', check=True)
            return json.loads(result.stdout)

        checker._js = execute
        return checker, driver, calls

    def finish(self, condition, **state):
        checker, driver, calls = self.checker(condition, **state)
        with patch('backend.m04.checks.time.monotonic', side_effect=[0, 3]):
            passed, error, evidence = checker.finish([driver])
        return passed, evidence[0], calls

    def test_failed_value_records_actual_not_expected_from_same_dom_snapshot(self):
        passed, item, calls = self.finish(dict(kind='value', target=LOC, expected='Synthetic expected'))
        self.assertFalse(passed)
        self.assertEqual(item['expected'], 'Synthetic expected')
        self.assertEqual(item['observed'], 'Synthetic actual')
        self.assertEqual(item['observation_status'], 'RECORDED')
        self.assertEqual(item['comparison_mode'], 'EXACT')
        self.assertEqual(len(calls), 1)

    def test_passed_value_and_empty_field_have_real_scalar_observations(self):
        for value in ('Synthetic actual', ''):
            passed, item, _ = self.finish(dict(kind='value', target=LOC, expected=value),
                                           nodes=dict(field=dict(value=value)))
            self.assertTrue(passed)
            self.assertEqual(item['observed'], value)
            self.assertEqual(item['status'], 'PASS')

    def test_text_contains_records_match_and_length_without_dom_text(self):
        text = 'A private unrequested body and Synthetic token'
        passed, item, _ = self.finish(dict(kind='text_contains', target=LOC, expected='Synthetic token'),
                                     nodes=dict(field=dict(innerText=text)))
        self.assertTrue(passed)
        self.assertEqual(item['observed'], dict(match_found=True, text_length=len(text)))
        self.assertNotIn(text, json.dumps(item))

    def test_visible_focus_count_and_text_count_keep_boolean_api(self):
        cases = [dict(kind='visible', expected=True), dict(kind='focus', expected=True),
                 dict(kind='count', expected=1), dict(kind='text_count', expected='Synthetic title', count=1)]
        for item in cases:
            with self.subTest(kind=item['kind']):
                condition = dict(item, target=LOC)
                checker, driver, _ = self.checker(condition, nodes=dict(field=dict(innerText='Synthetic title')),
                                                 focus='field')
                self.assertIs(checker._simple(driver, condition), True)
                passed, evidence, _ = self.finish(condition, nodes=dict(field=dict(innerText='Synthetic title')),
                                                   focus='field')
                self.assertTrue(passed)
                self.assertEqual(evidence['observation_status'], 'RECORDED')
                self.assertIsNotNone(evidence['observed'])

    def test_ambiguous_visible_target_keeps_failure_with_counts(self):
        passed, item, _ = self.finish(dict(kind='visible', target=LOC, expected=True),
                                     nodes=dict(a={}, b={}), selectors={'#field': ['a', 'b']})
        self.assertFalse(passed)
        self.assertEqual(item['observed'], dict(matched_count=2, visible_count=2))

    def test_runtime_password_alias_redacts_actual_even_for_empty_expected(self):
        for metadata in (dict(type='password'), dict(id='actual-auth-token'),
                         dict(autocomplete='current-password'), dict(type='hidden')):
            with self.subTest(metadata=metadata):
                passed, item, _ = self.finish(dict(kind='value', target=LOC, expected=''),
                                             nodes=dict(field=dict(value='synthetic-secret-value', **metadata)))
                self.assertFalse(passed)
                self.assertEqual(item['observed'], '[REDACTED]')
                self.assertEqual(item['observation_status'], 'REDACTED')
                self.assertNotIn('synthetic-secret-value', json.dumps(item))

    def test_credentials_personal_strings_and_urls_are_not_persisted(self):
        for value in ('Bearer synthetic-secret', 'password=synthetic-secret',
                      'person@example.invalid', '010-1234-5678',
                      'https://example.invalid/path?credential=private#fragment'):
            with self.subTest(kind=value.split(':', 1)[0]):
                passed, item, _ = self.finish(dict(kind='value', target=LOC, expected='Synthetic expected'),
                                             nodes=dict(field=dict(value=value)))
                self.assertFalse(passed)
                self.assertNotIn(value, json.dumps(item, ensure_ascii=False))
                self.assertEqual(item['observation_status'], 'REDACTED')

    def test_missing_or_failed_observation_never_copies_expected(self):
        passed, item, _ = self.finish(dict(kind='value', target=LOC, expected='Expected only'),
                                     nodes={}, selectors={})
        self.assertFalse(passed)
        self.assertIsNone(item['observed'])
        self.assertEqual(item['observation_status'], 'NOT_RECORDED')
        checker, driver, _ = self.checker(dict(kind='value', target=LOC, expected='Expected only'))
        checker._js = lambda *args: (_ for _ in ()).throw(RuntimeError('private unavailable error'))
        with patch('backend.m04.checks.time.monotonic', side_effect=[0, 3]):
            passed, _, rows = checker.finish([driver])
        self.assertFalse(passed)
        self.assertIsNone(rows[0]['observed'])
        self.assertNotIn('private unavailable error', json.dumps(rows))

    def test_long_value_is_bounded_and_marked_partial_without_changing_verdict(self):
        value = 'x' * 10000
        passed, item, _ = self.finish(dict(kind='value', target=LOC, expected='Short expected'),
                                     nodes=dict(field=dict(value=value)))
        self.assertFalse(passed)
        self.assertLess(len(json.dumps(item)), 900)
        self.assertEqual(item['observed']['length'], len(value))
        self.assertEqual(len(item['observed']['value']), 160)
        self.assertEqual(item['observation_status'], 'PARTIAL')

    def test_personal_pattern_is_masked_before_long_value_is_truncated(self):
        value = 'x' * 154 + '010-1234-5678' + 'y' * 200
        passed, item, _ = self.finish(dict(kind='value', target=LOC, expected='Short expected'),
                                     nodes=dict(field=dict(value=value)))
        self.assertFalse(passed)
        self.assertNotIn('010-', json.dumps(item['observed']))
        self.assertEqual(item['observation_status'], 'PARTIAL')

    def test_relational_checks_record_comparison_metadata_without_dom_strings(self):
        condition = dict(kind='text_equals_target', target=LOC, property='value',
                         other_target=dict(by='css selector', value='#other'), other_property='text')
        for actual in ('Synthetic private title', 'Different title'):
            with self.subTest(equal=actual.startswith('Synthetic')):
                passed, item, _ = self.finish(condition, nodes=dict(field=dict(value=actual),
                    other=dict(innerText='Synthetic private title')), selectors={'#field': ['field'], '#other': ['other']})
                self.assertEqual(passed, actual.startswith('Synthetic'))
                self.assertEqual(item['observed']['equal'], passed)
                self.assertNotIn(actual, json.dumps(item))
        passed, item, _ = self.finish(dict(kind='nonempty', target=LOC, property='value'))
        self.assertTrue(passed)
        self.assertTrue(item['observed']['left_nonempty'])

    def test_url_observation_excludes_query_and_fragment(self):
        condition = dict(kind='url_path', expected='/fixture')
        checker, driver, _ = self.checker(condition)
        checker.raw_execute = lambda *args: dict(value='https://example.invalid/fixture?secret=private#value')
        passed, _, rows = checker.finish([driver])
        self.assertTrue(passed)
        self.assertEqual(rows[0]['observed'], '/fixture')
        self.assertNotIn('private', json.dumps(rows))

    def test_cards_records_counts_and_comparisons_without_category_strings(self):
        condition = dict(kind='cards_state', api_path='/api/cards', keyword='', search_type='category',
                         **{name: LOC for name in ('search_input', 'search_type_target', 'table', 'rows', 'category_cells', 'empty_state')},
                         empty_text=['None'])
        checker, driver, _ = self.checker(condition)
        checker.summaries[(None, '/api/cards', '')] = dict(categories=['Private category'], total=1)
        checker._js = lambda *args: dict(keyword='', type='category', visible=True, loading=False,
                                        rows=1, categories=['Private category'], empty=False)
        passed, _, rows = checker.finish([driver])
        self.assertTrue(passed)
        self.assertEqual(rows[0]['observed']['rows'], 1)
        self.assertTrue(rows[0]['observed']['category_values_match'])
        self.assertNotIn('Private category', json.dumps(rows))


class NativeAndPlanningObservationTests(unittest.TestCase):
    def test_pending_checks_use_safe_expectations_and_no_fabricated_observation(self):
        rows = planned_check_results([dict(kind='value', expected='person@example.invalid'),
                                      dict(kind='visible', expected=True)])
        self.assertEqual([item['check_index'] for item in rows], [1, 2])
        self.assertEqual(rows[0]['expected'], '[REDACTED]')
        self.assertTrue(all(item['status'] == 'PENDING' and item['observed'] is None
                            and item['observation_status'] == 'NOT_RECORDED' for item in rows))

    def native(self, status=201, completed=True):
        condition = dict(kind='native_submit_response', method='POST', api_origin='https://example.invalid',
                         api_path='/api/save', expected_status=201)
        definition = dict(order=1, action='submit', target=LOC, checks=[condition])
        checker = RuntimeChecks(dict(steps=[definition]))
        driver = object()
        checker.raw_execute = lambda *args: dict(value=[])
        checker.begin(1, [driver])
        checker.target_action = True
        ledger = checker.network['native']
        ledger.since, ledger.succeeded = 100, True
        def event(method, **params):
            return dict(message=json.dumps(dict(message=dict(method='Network.' + method,
                                        params=dict(requestId='synthetic-request-id', **params)))))
        events = [event('requestWillBeSent', timestamp=1, wallTime=101,
                        request=dict(method='POST', url='https://example.invalid/api/save')),
                  event('responseReceived', timestamp=2,
                        response=dict(status=status, url='https://example.invalid/api/save'))]
        if completed:
            events.append(event('loadingFinished', timestamp=3))
        ledger.consume(events)
        with patch('backend.m04.checks.time.monotonic', side_effect=[0, 3]):
            passed, _, rows = checker.finish([driver])
        return passed, rows[0]

    def test_native_complete_chain_records_real_receipt_and_no_raw_request_id(self):
        passed, item = self.native()
        self.assertTrue(passed)
        self.assertTrue(item['observed']['loading_finished'])
        self.assertEqual(item['observed']['http_status'], 201)
        self.assertNotIn('synthetic-request-id', json.dumps(item))

    def test_native_failed_or_partial_chain_never_claims_expected_status_or_finish(self):
        for status, completed in ((503, True), (201, False)):
            with self.subTest(status=status, completed=completed):
                passed, item = self.native(status, completed)
                self.assertFalse(passed)
                self.assertEqual(item['observation_status'], 'PARTIAL')
                self.assertIsNone(item['observed']['loading_finished'])
                self.assertNotIn('http_status', {key: value for key, value in item['observed'].items() if key != 'requests'})
                self.assertEqual(item['observed']['requests'][0]['http_status'], status)


if __name__ == '__main__':
    unittest.main()
