"""Private, independent DOM relations; no browser/site/provider is called."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from backend.m04.checks import RuntimeChecks, prepare_contract
from backend.m07.generator import prompt


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT.parent / 'data/changes/20261109-real-execution-7c91e6ab/build_prepared_script.py'
NODE = shutil.which('node')
LOC = lambda value: dict(by='css selector', value=value)


def scenario(condition):
    return dict(scenario_id='PRIVATE-DOM-SYNTHETIC', steps=[dict(order=1, action='verify', target='#detail',
                expected_result='Selected title matches the loaded detail and content exists')],
                execution_contract=dict(version=1, scenario_id='PRIVATE-DOM-SYNTHETIC', steps=[dict(
                    order=1, action='verify', target=LOC('#detail'), checks=[condition])]))


def equality():
    return dict(kind='text_equals_target', target=LOC('#detail'), property='value',
                other_target=LOC('#selected'), other_property='text')


NODE_DOM = r"""const request=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=Object.fromEntries(Object.entries(request.nodes).map(([key,value])=>[key,{
  tagName:Object.hasOwn(value,'value')?'INPUT':'DIV', type:'text', ...value,
  getAttribute(name){return this.attributes?.[name]??this[name]??null;},
  getClientRects(){return this.hidden?[]:[{}];}
}]));
global.document={querySelectorAll(selector){return (request.selectors[selector]||[]).map(id=>nodes[id]);}};
global.getComputedStyle=e=>({visibility:e.visibility||'visible'});
const result=Function(request.script).apply(null,request.args);
process.stdout.write(JSON.stringify({result}));"""


def dom_check(script, args, *, nodes=None, selectors=None):
    payload = dict(script=script, args=list(args), nodes=nodes or dict(
        detail=dict(value=' Synthetic private title '), selected=dict(innerText='Synthetic private title')),
        selectors=selectors or {'#detail': ['detail'], '#selected': ['selected']})
    result = subprocess.run([NODE, '-e', NODE_DOM], input=json.dumps(payload), capture_output=True,
                            encoding='utf-8', check=True)
    returned = json.loads(result.stdout)
    if set(returned) != {'result'} or type(returned['result']) is not bool:
        raise AssertionError('Private DOM comparison must return only a boolean')
    return returned['result']


class PrivateDOMContractTests(unittest.TestCase):
    def test_explicit_text_and_value_relation_and_nonempty_are_normalized(self):
        for condition in (equality(), dict(kind='nonempty', target=LOC('#detail'), property='value')):
            with self.subTest(kind=condition['kind']):
                self.assertEqual(prepare_contract(scenario(condition))['steps'][0]['checks'], [condition])

    def test_ambiguous_fields_properties_auth_and_tautology_are_rejected(self):
        variants = []
        for field, value in [('property', 'innerHTML'), ('property', {}), ('other_property', []),
                             ('target', LOC('#password')), ('other_target', LOC('#auth-token')),
                             ('other_target', LOC('#detail')), ('expected', 'Synthetic private title')]:
            candidate = equality()
            candidate[field] = value
            variants.append(candidate)
        missing = equality()
        del missing['property']
        variants += [missing, dict(kind='nonempty', target=LOC('#detail'), property='text', expected=True)]
        for index, condition in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                prepare_contract(scenario(condition))

    def test_prompt_describes_exact_private_comparison_without_observed_strings(self):
        instructions, data = prompt(scenario(equality()), {})
        self.assertIn('text_equals_target', instructions)
        self.assertIn('nonempty', instructions)
        self.assertIn('return only a boolean', instructions)
        self.assertNotIn('Synthetic private title', instructions + data)


@unittest.skipUnless(NODE, 'Node is required to execute the real fixed DOM predicate with synthetic elements')
class PrivateDOMRuntimeTests(unittest.TestCase):
    def checker(self, condition, **state):
        checker = RuntimeChecks(prepare_contract(scenario(condition)))
        checker._js = lambda driver, script, *args: dom_check(script, args, **state)
        return checker

    def test_real_predicate_matches_distinct_value_to_text_trimmed(self):
        condition = equality()
        self.assertTrue(self.checker(condition)._simple(object(), condition))

    def test_wrong_missing_duplicate_hidden_empty_and_alias_targets_fail(self):
        variants = [
            dict(nodes=dict(detail=dict(value='Wrong item'), selected=dict(innerText='Selected item'))),
            dict(selectors={'#detail': [], '#selected': ['selected']}),
            dict(selectors={'#detail': ['detail', 'selected'], '#selected': ['selected']}),
            dict(nodes=dict(detail=dict(value='Same', hidden=True), selected=dict(innerText='Same'))),
            dict(nodes=dict(detail=dict(value='Same'), selected=dict(innerText='Same', visibility='hidden'))),
            dict(nodes=dict(detail=dict(value='  '), selected=dict(innerText='\n'))),
            dict(nodes=dict(detail=dict(value='Same', innerText='Same')),
                 selectors={'#detail': ['detail'], '#selected': ['detail']}),
            dict(nodes=dict(detail=dict(innerText='Same'), selected=dict(innerText='Same'))),
        ]
        for index, state in enumerate(variants):
            with self.subTest(index=index):
                condition = equality()
                self.assertFalse(self.checker(condition, **state)._simple(object(), condition))

    def test_nonempty_requires_unique_visible_real_string_not_whitespace(self):
        condition = dict(kind='nonempty', target=LOC('#detail'), property='text')
        for expected, state in [
            (True, dict(nodes=dict(detail=dict(innerText='Loaded content')))),
            (False, dict(nodes=dict(detail=dict(innerText=' \n ')))),
            (False, dict(nodes=dict(detail=dict(innerText='Content', hidden=True)))),
            (False, dict(nodes=dict(detail=dict(innerText='Content')), selectors={'#detail': ['detail', 'detail']})),
        ]:
            with self.subTest(expected=expected, state=list(state)):
                self.assertEqual(self.checker(condition, **state)._simple(object(), condition), expected)

    def test_mask_literals_placeholders_and_all_stars_cannot_establish_identity(self):
        condition = dict(equality(), property='text')
        for marker in ('[MASKED]', '[REDACTED]', '[숨김]', '-', '***', '＊ ＊', '<REDACTED>', 'N/A'):
            with self.subTest(case='fixed masking or placeholder literal'):
                state = dict(nodes=dict(detail=dict(innerText=marker), selected=dict(innerText=marker)))
                self.assertFalse(self.checker(condition, **state)._simple(object(), condition))

    def test_nonempty_rejects_masking_and_placeholder_literals(self):
        condition = dict(kind='nonempty', target=LOC('#detail'), property='text')
        for marker in ('[MASKED]', '[REDACTED]', '[숨김]', '-', '***', '＊ ＊', '<REDACTED>', 'N/A'):
            with self.subTest(case='fixed masking or placeholder literal'):
                self.assertFalse(self.checker(condition, nodes=dict(detail=dict(innerText=marker)))._simple(object(), condition))

    def test_alias_cannot_read_password_hidden_auth_or_non_native_value(self):
        condition = equality()
        forbidden = [dict(type='password'), dict(type='hidden'), dict(id='actual-password'),
                     dict(name='user_name'), dict(autocomplete='section-test current-password'),
                     dict(autocomplete='new-password'), dict(autocomplete='username'),
                     dict(tagName='DIV'), dict(attributes=dict(type='password'))]
        for metadata in forbidden:
            with self.subTest(fields=sorted(metadata)):
                state = dict(nodes=dict(detail=dict(value='Same', **metadata), selected=dict(innerText='Same')))
                self.assertFalse(self.checker(condition, **state)._simple(object(), condition))
        state = dict(nodes=dict(detail=dict(value='Same'), selected=dict(innerText='Same', name='username')))
        self.assertFalse(self.checker(condition, **state)._simple(object(), condition))

    def test_normal_business_input_and_textarea_remain_supported(self):
        for tag, identity in [('INPUT', 'schedule-title'), ('TEXTAREA', 'schedule-description')]:
            with self.subTest(tag=tag):
                condition = equality()
                state = dict(nodes=dict(detail=dict(tagName=tag, id=identity, value='Business content'),
                                        selected=dict(innerText='Business content')))
                self.assertTrue(self.checker(condition, **state)._simple(object(), condition))

    def test_runner_evidence_contains_only_boolean_status_without_dom_values(self):
        condition = equality()
        checker = self.checker(condition)
        driver = object()
        checker.raw_execute = lambda *args: None
        checker.begin(1, [driver])
        passed, error, evidence = checker.finish([driver])
        self.assertTrue(passed)
        self.assertIsNone(error)
        self.assertEqual(evidence, [dict(check_index=1, kind='text_equals_target', status='PASS')])
        self.assertNotIn('Synthetic private title', json.dumps(evidence))

    @unittest.skipUnless(HELPER.is_file(), 'Local PREPARED evidence builder is not installed')
    def test_prepared_builder_executes_same_private_predicate_and_fails_wrong_detail(self):
        spec = importlib.util.spec_from_file_location('private_prepared_builder', HELPER)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        source = scenario(equality())
        contract = prepare_contract(source)
        generated = builder.build(source, contract)
        self.assertNotIn('Synthetic private title', generated)
        tree = ast.parse(generated)
        check_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'check')
        script = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'RELATIONAL_CHECK_SCRIPT' for target in node.targets))

        class Wait:
            def until(self, callback):
                if not callback(None):
                    raise TimeoutError('Private DOM condition not satisfied')

        class Driver:
            def __init__(self, wrong=False):
                self.wrong = wrong

            def execute_script(self, body, *args):
                state = dict(nodes=dict(detail=dict(value='Wrong'), selected=dict(innerText='Selected'))) if self.wrong else {}
                return dom_check(body, args, **state)

        env = dict(wait=Wait(), driver=Driver(), RELATIONAL_CHECK_SCRIPT=script)
        exec(compile(ast.Module(body=[check_function], type_ignores=[]), '<prepared-private-check>', 'exec'), env)
        env['check'](equality(), LOC('#detail'))
        env['driver'] = Driver(wrong=True)
        with self.assertRaises(TimeoutError):
            env['check'](equality(), LOC('#detail'))
        env['driver'] = Driver()
        env['check'](dict(kind='nonempty', target=LOC('#detail'), property='value'), LOC('#detail'))


if __name__ == '__main__':
    unittest.main()
