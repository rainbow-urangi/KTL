"""Conditional native input preserves populated controls; no browser or HTTP."""
from copy import deepcopy
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from backend.m04 import checks


TARGET = {'by': 'css selector', 'value': '#personal-duty'}
FIXTURE = '업무 자동화 시험'
NODE = shutil.which('node')
NODE_DOM = r"""const request=JSON.parse(require('fs').readFileSync(0,'utf8'));
const nodes=Object.fromEntries(Object.entries(request.nodes).map(([key,state])=>[key,{
  tagName:'INPUT',type:'text',value:'',...state,
  getAttribute(name){return (this.attributes||{})[name]||'';},
  getClientRects(){return this.noRects?[]:[{}];}
}]));
for(const node of Object.values(nodes))node.parentElement=nodes[node.parent]||null;
global.document={querySelectorAll(){return request.selected.map(key=>nodes[key]);}};
global.getComputedStyle=node=>({visibility:'visible',opacity:'1',...node.style});
process.stdout.write(JSON.stringify(Function(request.script).call(null,'#personal-duty')));"""


def source(initial_action='fill_empty'):
    condition = dict(kind='fill_empty', target=deepcopy(TARGET), expected=FIXTURE)
    return dict(scenario_id='empty-input-fixture', steps=[
        dict(order=1, action=initial_action, target=TARGET['value'], value=FIXTURE,
             expected_result='빈 입력란만 입력한다.'),
        dict(order=2, action='verify', target=TARGET['value'], expected_result='기존 값과 새 입력을 확인한다.')],
        execution_contract=dict(version=1, scenario_id='empty-input-fixture', steps=[
            dict(order=1, action=initial_action, target=deepcopy(TARGET), checks=[deepcopy(condition)]),
            dict(order=2, action='verify', target=deepcopy(TARGET), checks=[deepcopy(condition)])]))


class PrivateInputDriver:
    def __init__(self, value=''):
        self.value = value
        self.valid = True
        self.commands = []

    def raw(self, driver, name, params):
        self.commands.append(name)
        if name != 'w3cExecuteScript':
            raise AssertionError('Only read-only synthetic JS expected')
        script = params['script']
        if script == checks._FILL_EMPTY_READ_SCRIPT:
            return dict(value=dict(valid=True, value=self.value) if self.valid else dict(valid=False))
        if '.matches(' in script:
            identity = params['args'][0]['element-6066-11e4-a52e-4f735466cecf']
            return dict(value=identity == 'fixture-control' and params['args'][1] == TARGET['value'])
        raise AssertionError('Unexpected synthetic script')


class EmptyInputContractTests(unittest.TestCase):
    def test_exact_conditional_contract_and_later_verification_are_accepted(self):
        data = source()
        contract = checks.prepare_contract(data)
        self.assertEqual(contract, data['execution_contract'])
        self.assertEqual(checks.planned_check_results(contract['steps'][0]['checks'])[0]['expected'],
                         dict(empty_input_filled=True, populated_input_preserved=True))

    def test_missing_or_mismatched_conditional_contract_is_rejected(self):
        mutations = [
            lambda data: data['execution_contract']['steps'][0]['checks'].clear(),
            lambda data: data['execution_contract']['steps'][0]['checks'][0].update(target=dict(by='css selector', value='#other')),
            lambda data: data['execution_contract']['steps'][0]['checks'][0].update(expected='다른 값'),
            lambda data: data['steps'][0].update(value=''),
            lambda data: data['execution_contract']['steps'][1]['checks'][0].update(expected='다른 값'),
            lambda data: data['execution_contract']['steps'][1]['checks'][0].update(target=dict(by='css selector', value='#other')),
            lambda data: data['execution_contract']['steps'][0]['checks'].append(
                deepcopy(data['execution_contract']['steps'][0]['checks'][0])),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data = source()
                mutation(data)
                with self.assertRaises(ValueError):
                    checks.prepare_contract(data)

    def test_conditional_check_cannot_redefine_an_ordinary_input(self):
        with self.assertRaises(ValueError):
            checks.prepare_contract(source('input'))

    def test_verification_must_follow_a_declared_conditional_input(self):
        data = source()
        data['steps'][0].update(action='verify')
        data['execution_contract']['steps'][0]['action'] = 'verify'
        with self.assertRaises(ValueError):
            checks.prepare_contract(data)

    def test_authentication_target_is_rejected(self):
        data = source()
        for step in data['steps']:
            step['target'] = '#password'
        for definition in data['execution_contract']['steps']:
            definition['target']['value'] = '#password'
            definition['checks'][0]['target']['value'] = '#password'
        with self.assertRaises(ValueError):
            checks.prepare_contract(data)

    def test_duplicate_conditional_input_cannot_reset_the_original_baseline(self):
        data = source()
        data['steps'][1].update(action='fill_empty', value=FIXTURE)
        data['execution_contract']['steps'][1]['action'] = 'fill_empty'
        with self.assertRaises(ValueError):
            checks.prepare_contract(data)


@unittest.skipUnless(NODE, 'Node is required to execute the real fixed DOM read predicate')
class EmptyInputReadPredicateTests(unittest.TestCase):
    def read(self, *, nodes=None, selected=None):
        request = dict(script=checks._FILL_EMPTY_READ_SCRIPT,
                       nodes={'field': {}} if nodes is None else nodes,
                       selected=['field'] if selected is None else selected)
        completed = subprocess.run([NODE, '-e', NODE_DOM], input=json.dumps(request),
            encoding='utf-8', capture_output=True, check=True)
        return json.loads(completed.stdout)

    def test_native_text_and_textarea_values_are_read_exactly_without_trimming(self):
        for kind in ({}, dict(tagName='TEXTAREA'), dict(type='email'), dict(type='tel'), dict(type='url')):
            for value in ('', ' ', 'Already populated'):
                with self.subTest(kind=kind, value=value):
                    self.assertEqual(self.read(nodes=dict(field=dict(value=value, **kind))),
                                     dict(valid=True, value=value))

    def test_missing_duplicate_hidden_readonly_disabled_or_non_native_never_expose_value(self):
        private = 'Private source value'
        bad = [dict(readOnly=True), dict(disabled=True), dict(type='date'), dict(type='password'),
               dict(tagName='DIV'), dict(noRects=True), dict(style=dict(visibility='hidden')),
               dict(style=dict(opacity='0')), dict(attributes=dict(id='auth-token')),
               dict(attributes=dict(autocomplete='current-password'))]
        for state in bad:
            with self.subTest(state=state):
                self.assertEqual(self.read(nodes=dict(field=dict(value=private, **state))), dict(valid=False))
        self.assertEqual(self.read(selected=[]), dict(valid=False))
        self.assertEqual(self.read(nodes=dict(field=dict(value=private), other=dict(value=private)),
                                   selected=['field', 'other']), dict(valid=False))
        self.assertEqual(self.read(nodes=dict(field=dict(value=private, parent='container'),
                                             container=dict(style=dict(opacity='0')))), dict(valid=False))


class EmptyInputRuntimeChecksTests(unittest.TestCase):
    def setup_checker(self, value=''):
        driver = PrivateInputDriver(value)
        checker = checks.RuntimeChecks(checks.prepare_contract(source()))
        checker.raw_execute = driver.raw
        checker.begin(1, [driver])
        return driver, checker

    def finish(self, checker, driver):
        with patch.object(checks.time, 'monotonic', side_effect=range(0, 300, 3)):
            return checker.finish([driver])

    def command(self, checker, driver, **changes):
        params = dict(id='fixture-control', text=FIXTURE, value=list(FIXTURE))
        params.update(changes)
        checker.before_command(driver, 'sendKeysToElement', params)

    def test_empty_control_accepts_exact_native_input_and_later_verification(self):
        driver, checker = self.setup_checker('')
        self.command(checker, driver)
        driver.value = FIXTURE
        passed, failure, evidence = self.finish(checker, driver)
        self.assertTrue(passed, failure)
        self.assertTrue(evidence[0]['observed']['initial_empty'])
        self.assertTrue(evidence[0]['observed']['input_performed'])
        checker.begin(2, [driver])
        self.assertTrue(self.finish(checker, driver)[0])

    def test_populated_control_is_a_read_only_pass_without_input(self):
        original = '사용자 기존 값 / private@example.invalid'
        driver, checker = self.setup_checker(original)
        passed, failure, evidence = self.finish(checker, driver)
        self.assertTrue(passed, failure)
        self.assertFalse(checker.target_action)
        self.assertFalse(evidence[0]['observed']['input_performed'])
        self.assertTrue(evidence[0]['observed']['populated_input_preserved'])
        self.assertNotIn(original, json.dumps(evidence, ensure_ascii=False))
        self.assertNotIn('private@example.invalid', json.dumps(evidence, ensure_ascii=False))
        self.assertNotIn('value', evidence[0]['observed'])
        checker.begin(2, [driver])
        self.assertTrue(self.finish(checker, driver)[0])

    def test_whitespace_is_populated_and_stays_unchanged(self):
        driver, checker = self.setup_checker('  ')
        self.assertTrue(self.finish(checker, driver)[0])
        self.assertEqual(driver.value, '  ')

    def test_changed_populated_value_fails_at_step_and_final_verification(self):
        driver, checker = self.setup_checker('Original private value')
        driver.value = FIXTURE
        self.assertFalse(self.finish(checker, driver)[0])
        checker.begin(2, [driver])
        self.assertFalse(self.finish(checker, driver)[0])

    def test_native_input_into_populated_control_is_blocked_before_execution(self):
        driver, checker = self.setup_checker('Original private value')
        with self.assertRaises(RuntimeError):
            self.command(checker, driver)
        self.assertEqual(driver.value, 'Original private value')
        self.assertFalse(self.finish(checker, driver)[0])

    def test_late_autofill_is_not_overwritten(self):
        driver, checker = self.setup_checker('')
        driver.value = 'Browser-provided value'
        with self.assertRaises(RuntimeError):
            self.command(checker, driver)
        self.assertEqual(driver.value, 'Browser-provided value')

    def test_one_focus_click_then_exact_native_input_is_allowed_for_empty_control(self):
        driver, checker = self.setup_checker('')
        checker.before_command(driver, 'clickElement', dict(id='fixture-control'))
        self.assertFalse(checker.target_action)
        self.command(checker, driver)
        driver.value = FIXTURE
        self.assertTrue(self.finish(checker, driver)[0])

    def test_populated_control_and_repeated_focus_click_are_blocked(self):
        driver, checker = self.setup_checker('Original')
        with self.assertRaises(RuntimeError):
            checker.before_command(driver, 'clickElement', dict(id='fixture-control'))
        self.assertEqual(driver.value, 'Original')
        driver, checker = self.setup_checker('')
        checker.before_command(driver, 'clickElement', dict(id='fixture-control'))
        with self.assertRaises(RuntimeError):
            checker.before_command(driver, 'clickElement', dict(id='fixture-control'))

    def test_focus_time_autofill_is_not_overwritten(self):
        driver, checker = self.setup_checker('')
        checker.before_command(driver, 'clickElement', dict(id='fixture-control'))
        driver.value = 'Autofill triggered by focus'
        with self.assertRaises(RuntimeError):
            self.command(checker, driver)
        self.assertEqual(driver.value, 'Autofill triggered by focus')

    def test_clear_and_navigation_are_not_conditional_input(self):
        for name in ('clearElement', 'submitElement', 'get', 'goBack', 'goForward', 'refresh'):
            with self.subTest(command=name):
                driver, checker = self.setup_checker('')
                with self.assertRaises(RuntimeError):
                    checker.before_command(driver, name, dict(id='fixture-control'))
                self.assertFalse(self.finish(checker, driver)[0])

    def test_wrong_target_or_keys_cannot_satisfy_empty_input(self):
        for changes in (dict(id='other-control'), dict(text='\ue009a', value=['\ue009', 'a']),
                        dict(value=['different']), dict(text=FIXTURE + 'extra'), dict(value=[17])):
            with self.subTest(changes=changes):
                driver, checker = self.setup_checker('')
                with self.assertRaises(RuntimeError):
                    self.command(checker, driver, **changes)

    def test_script_only_value_change_does_not_count_as_native_input(self):
        driver, checker = self.setup_checker('')
        driver.value = FIXTURE
        self.assertFalse(self.finish(checker, driver)[0])

    def test_later_cross_field_change_is_caught_by_final_verification(self):
        driver, checker = self.setup_checker('Original')
        self.assertTrue(self.finish(checker, driver)[0])
        driver.value = 'Changed during another input'
        checker.begin(2, [driver])
        self.assertFalse(self.finish(checker, driver)[0])

    def test_invalid_target_and_missing_private_baseline_fail_closed(self):
        driver = PrivateInputDriver('')
        driver.valid = False
        checker = checks.RuntimeChecks(checks.prepare_contract(source()))
        checker.raw_execute = driver.raw
        checker.begin(1, [driver])
        self.assertFalse(self.finish(checker, driver)[0])
        checker.begin(2, [driver])
        self.assertFalse(self.finish(checker, driver)[0])

    def test_ordinary_clear_action_keeps_existing_behavior(self):
        driver = PrivateInputDriver('Original')
        checker = checks.RuntimeChecks(dict(steps=[dict(order=1, action='clear', target=TARGET,
            checks=[dict(kind='value', target=TARGET, expected='')])]))
        checker.raw_execute = driver.raw
        checker.begin(1, [driver])
        checker.before_command(driver, 'clearElement', dict(id='fixture-control'))
        self.assertTrue(checker.target_action)
        self.assertEqual(checker._fill_empty_snapshots, {})


if __name__ == '__main__':
    unittest.main()
