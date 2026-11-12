"""Count exact visible synthetic titles without a browser or business data."""
import copy
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from backend.m04.checks import RuntimeChecks, prepare_contract


NODE = shutil.which('node')
LOCATOR = dict(by='css selector', value='.synthetic-day .synthetic-title')
TITLE = 'Synthetic new schedule'
NODE_DOM = r"""const request=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=Object.fromEntries(Object.entries(request.nodes).map(([key,state])=>[key,{
  ...state, getClientRects(){return this.noRects?[]:[{}];}
}]));
for(const node of Object.values(nodes)) node.parentElement=nodes[node.parent]||null;
global.document={querySelectorAll(selector){return (request.selectors[selector]||[]).map(id=>nodes[id]);}};
global.getComputedStyle=node=>({visibility:'visible',opacity:'1',...node.style});
const result=Function(request.script).apply(null,request.args);
process.stdout.write(JSON.stringify({result}));"""


def condition(count=1, expected=TITLE):
    return dict(kind='text_count', target=LOCATOR, expected=expected, count=count)


def scenario(check):
    return dict(scenario_id='TEXT-COUNT-SYNTHETIC', steps=[dict(
        order=1, action='verify', target=LOCATOR['value'], expected_result='Exact new title count')],
        execution_contract=dict(version=1, scenario_id='TEXT-COUNT-SYNTHETIC', steps=[dict(
            order=1, action='verify', target=LOCATOR, checks=[check])]))


class TextCountContractTests(unittest.TestCase):
    def test_valid_exact_title_and_nonnegative_count_are_preserved(self):
        for count in (0, 1, 2):
            check = condition(count)
            self.assertEqual(prepare_contract(scenario(check))['steps'][0]['checks'], [check])

    def test_wrong_types_missing_extra_fields_and_oversized_text_are_rejected(self):
        variants = [dict(condition(), count=value) for value in (-1, True, 1.0, '1', None)]
        variants += [dict(condition(), expected=value) for value in (None, 1, [], {}, 'x' * 2001)]
        variants += [dict(condition(), extra=True), dict(condition(), target=dict(by='xpath', value='//*'))]
        for name in ('target', 'expected', 'count'):
            check = copy.deepcopy(condition())
            del check[name]
            variants.append(check)
        for check in variants:
            with self.subTest(check=check), self.assertRaises(ValueError):
                prepare_contract(scenario(check))

    def test_codepoint_boundary_and_unicode_title_are_supported(self):
        for expected in ('일정 등록 확인', '\U0001f4c5' * 2000):
            check = condition(expected=expected)
            self.assertEqual(prepare_contract(scenario(check))['steps'][0]['checks'], [check])

    def test_authentication_targets_and_secret_literals_are_rejected(self):
        for check in (dict(condition(), target=dict(by='css selector', value='#password')),
                      dict(condition(), expected='Bearer synthetic-secret'),
                      dict(condition(), expected='https://synthetic.invalid/?token=example')):
            with self.subTest(check=check), self.assertRaises(ValueError):
                prepare_contract(scenario(check))
        source = scenario(condition())
        source['steps'][0]['target'] = '#password'
        source['execution_contract']['steps'][0]['target'] = dict(by='css selector', value='#password')
        with self.assertRaises(ValueError):
            prepare_contract(source)


@unittest.skipUnless(NODE, 'Node is required to execute the real fixed DOM predicate')
class TextCountRuntimeTests(unittest.TestCase):
    def checker(self, count, *, nodes=None, selectors=None):
        check = condition(count)
        checker = RuntimeChecks(prepare_contract(scenario(check)))

        def run(driver, script, *args):
            payload = dict(script=script, args=list(args), nodes={} if nodes is None else nodes,
                           selectors={} if selectors is None else selectors)
            completed = subprocess.run([NODE, '-e', NODE_DOM], input=json.dumps(payload),
                                       capture_output=True, encoding='utf-8', check=True)
            returned = json.loads(completed.stdout)
            if set(returned) != {'result'} or type(returned['result']) is not bool:
                raise AssertionError('text_count must return only a boolean')
            return returned['result']

        checker._js = run
        return checker, check

    def check(self, count, **state):
        checker, check = self.checker(count, **state)
        return checker._simple(object(), check)

    def test_zero_matches_establishes_absence_but_not_creation(self):
        self.assertTrue(self.check(0))
        self.assertFalse(self.check(1))

    def test_trimmed_exact_match_ignores_other_titles_and_case_changes(self):
        state = dict(nodes=dict(new=dict(innerText='  ' + TITLE + '\n'),
                                other=dict(innerText=TITLE + ' other'), case=dict(innerText=TITLE.lower())),
                     selectors={LOCATOR['value']: ['new', 'other', 'case']})
        self.assertTrue(self.check(1, **state))
        self.assertFalse(self.check(0, **state))

    def test_duplicate_visible_titles_do_not_pass_exactly_one(self):
        state = dict(nodes=dict(a=dict(innerText=TITLE), b=dict(innerText=TITLE)),
                     selectors={LOCATOR['value']: ['a', 'b']})
        self.assertFalse(self.check(1, **state))
        self.assertTrue(self.check(2, **state))

    def test_hidden_and_zero_opacity_titles_do_not_count(self):
        state = dict(nodes=dict(a=dict(innerText=TITLE, noRects=True),
                                b=dict(innerText=TITLE, style=dict(visibility='hidden')),
                                c=dict(innerText=TITLE, style=dict(opacity='0')),
                                d=dict(innerText=TITLE, parent='container'),
                                container=dict(style=dict(opacity='0'))),
                     selectors={LOCATOR['value']: ['a', 'b', 'c', 'd']})
        self.assertTrue(self.check(0, **state))
        self.assertFalse(self.check(1, **state))

    def test_day_selector_scope_excludes_same_title_elsewhere(self):
        state = dict(nodes=dict(a=dict(innerText=TITLE), elsewhere=dict(innerText=TITLE)),
                     selectors={LOCATOR['value']: ['a'], '.other-day .synthetic-title': ['elsewhere']})
        self.assertTrue(self.check(1, **state))

    def test_missing_inner_text_is_not_an_exact_text_match(self):
        self.assertTrue(self.check(0, nodes=dict(a={}), selectors={LOCATOR['value']: ['a']}))

    def test_finish_records_only_status_and_rejects_existing_or_duplicate_title(self):
        for requested, ids in ((0, ['a']), (1, ['a', 'b'])):
            with self.subTest(requested=requested, ids=ids):
                checker, _ = self.checker(requested, nodes=dict(a=dict(innerText=TITLE), b=dict(innerText=TITLE)),
                                           selectors={LOCATOR['value']: ids})
                driver = object()
                checker.raw_execute = lambda *args: None
                checker.begin(1, [driver])
                with patch('backend.m04.checks.time.monotonic', side_effect=[0, 3]):
                    passed, error, evidence = checker.finish([driver])
                self.assertFalse(passed)
                self.assertEqual(error, '독립 기대 결과 검사 실패: text_count')
                self.assertEqual(evidence, [dict(check_index=1, kind='text_count', status='FAIL')])
                self.assertNotIn(TITLE, json.dumps(evidence))


if __name__ == '__main__':
    unittest.main()
