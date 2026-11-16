"""Synthetic M03-to-Selenium compiler checks; no browser, provider or business call."""
import ast
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
import re
import sys
import types
import unittest
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m04.scenario_compiler import compile_code, SUPPORTED_ACTIONS, SUPPORTED_CHECKS


def css(value):
    return {'by': 'css selector', 'value': value}


def scenario():
    steps = [
        dict(order=1, action='open', target='http://127.0.0.1:9/work',
             url='http://127.0.0.1:9/work', expected_result='Synthetic work screen'),
        dict(order=2, action='input', target='#synthetic-input', value='Synthetic input',
             expected_result='Synthetic value is entered'),
        dict(order=3, action='verify', target='#synthetic-output',
             expected_result='Synthetic output is visible'),
    ]
    contract = dict(version=1, scenario_id='SYNTHETIC-COMPILER-01', steps=[
        dict(order=1, action='open', target={'url': steps[0]['url']},
             checks=[dict(kind='url_path', expected='/work')]),
        dict(order=2, action='input', target=css('#synthetic-input'),
             checks=[dict(kind='value', target=css('#synthetic-input'), expected='Synthetic input')]),
        dict(order=3, action='verify', target=css('#synthetic-output'),
             checks=[dict(kind='text_equals', target=css('#synthetic-output'), expected='Synthetic saved')]),
    ])
    value = dict(scenario_id=contract['scenario_id'], business_unit_id='SYNTHETIC-BU',
                 workflow_id='SYNTHETIC-WF', steps=steps, execution_contract=deepcopy(contract),
                 official=False, generated_by_llm=False, run_mode='DEVELOPMENT')
    return value, contract


class FakeElement:
    def __init__(self, driver, selector, *, text='', value='', tag='input', shown=True, enabled=True, attributes=None):
        self.driver, self.selector = driver, selector
        self.text, self.value, self.tag_name, self.shown = text, value, tag, shown
        self.attributes = dict(attributes or {})
        self.enabled = enabled
        self.children, self.find_calls = {}, []

    def is_displayed(self):
        return self.shown

    def is_enabled(self):
        return self.enabled

    def click(self):
        self.driver.actions.append(('click', self.selector))
        self.driver.switch_to.active_element = self
        if hasattr(self, 'after_click'):
            self.after_click()

    def find_elements(self, by, selector):
        if by != 'css selector':
            raise AssertionError('Compiler must keep row and cell CSS locators explicit')
        self.find_calls.append(selector)
        return self.children.get(selector, [])

    def clear(self):
        self.driver.actions.append(('clear', self.selector))
        self.value = ''

    def send_keys(self, *values):
        self.driver.actions.append(('send_keys', self.selector, values))
        self.driver.switch_to.active_element = self
        if values == ('CTRL', 'a'):
            self.selected = True
        elif values == ('BACKSPACE',):
            self.value = ''
        else:
            self.value += ''.join(values)

    def submit(self):
        self.driver.actions.append(('submit', self.selector))

    def get_attribute(self, name):
        if name in self.attributes:
            return self.attributes[name]
        return {'value': self.value, 'type': 'text', 'tagName': self.tag_name,
                'innerText': self.text, 'textContent': self.text}.get(name)

    def get_property(self, name):
        return self.get_attribute(name)


class FakeDriver:
    def __init__(self):
        self.actions, self.script_calls = [], []
        self.current_url, self.quit_count = '', 0
        self.switch_to = types.SimpleNamespace(active_element=None)
        self.elements = {}
        self.add('#synthetic-input')
        self.add('#synthetic-output', text='Synthetic saved', tag='div')

    def add(self, selector, **options):
        element = FakeElement(self, selector, **options)
        self.elements[selector] = [element]
        return element

    def find_elements(self, by, selector):
        if by != 'css selector':
            raise AssertionError('Compiler must use the explicit CSS locator')
        return self.elements.get(selector, [])

    def find_element(self, by, selector):
        elements = self.find_elements(by, selector)
        if len(elements) != 1:
            raise AssertionError('Synthetic element is not unique')
        return elements[0]

    def get(self, url):
        self.actions.append(('get', url))
        self.current_url = url

    def back(self):
        self.actions.append(('back',))

    def forward(self):
        self.actions.append(('forward',))

    def refresh(self):
        self.actions.append(('refresh',))

    def quit(self):
        self.quit_count += 1

    def set_page_load_timeout(self, value):
        self.actions.append(('page_timeout', value))

    def execute_script(self, script, *args):
        self.script_calls.append((script, args))
        if 'M03_PREPARED_TYPED_CHECK' in script:
            selector, kind, expected, count = args
            items = self.elements.get(selector, [])
            first = items[0] if items else None
            if kind == 'visible':
                return len(items) == 1 and first.shown if expected else not any(item.shown for item in items)
            if kind == 'focus':
                return (first is not None and self.switch_to.active_element is first) == expected
            if kind == 'value':
                return first is not None and first.value == expected
            if kind == 'text_equals':
                return first is not None and first.text.strip() == expected
            if kind == 'text_contains':
                return first is not None and expected in first.text
            if kind == 'count':
                return len(items) == expected
            if kind == 'text_count':
                return sum(item.shown and item.text.strip() == expected for item in items) == count
            raise AssertionError('Unexpected synthetic typed predicate')
        if 'const qa=s=>' in script:
            selector, prop, other_selector, other_prop, kind = args

            def useful(value):
                return bool(value.strip()) and not re.search(
                    r'^(?:[-–—]+|n/a|null|undefined)$|\[\s*(?:masked|redacted|hidden|숨김|마스킹|비공개)',
                    value.strip(), re.I)

            def read(target, property_name):
                items = self.elements.get(target, [])
                if len(items) != 1 or not items[0].shown:
                    return None, None
                item = items[0]
                return item, item.value if property_name == 'value' else item.text

            left, a = read(selector, prop)
            if left is None or not useful(a):
                return False
            if kind == 'nonempty':
                return True
            right, b = read(other_selector, other_prop)
            return right is not None and left is not right and useful(b) and a.strip() == b.strip()
        if 'document.readyState' in script:
            return 'complete'
        if 'scrollIntoView' in script:
            if hasattr(self, 'before_scroll'):
                self.before_scroll(args[0])
            return None
        if 'elementFromPoint' in script:
            return True
        if 'document.activeElement' in script:
            return self.switch_to.active_element is args[0] if args else self.switch_to.active_element
        raise AssertionError('Unexpected synthetic JavaScript: ' + script[:100])


class FakeWait:
    def __init__(self, driver, timeout, **options):
        self.driver = driver

    def until(self, predicate, message=''):
        for _ in range(4):
            result = predicate(self.driver)
            if result:
                return result
        raise TimeoutError(message or 'Synthetic condition was not satisfied')


def execute_synthetic(code, driver):
    """Execute generated Python with injected browser modules and hard network guards."""
    modules = {}
    for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.common',
                 'selenium.webdriver.common.by', 'selenium.webdriver.common.keys',
                 'selenium.webdriver.support', 'selenium.webdriver.support.ui', 'ktl_runtime'):
        modules[name] = types.ModuleType(name)
    webdriver = modules['selenium.webdriver']
    options = type('Options', (), {'add_argument': lambda *args: None})
    webdriver.ChromeOptions = options
    webdriver.Chrome = lambda **kwargs: driver
    modules['selenium'].webdriver = webdriver
    modules['selenium.webdriver.common.by'].By = types.SimpleNamespace(CSS_SELECTOR='css selector')
    modules['selenium.webdriver.common.keys'].Keys = types.SimpleNamespace(
        CONTROL='CTRL', BACKSPACE='BACKSPACE', ENTER='ENTER', TAB='TAB', ESCAPE='ESCAPE')
    modules['selenium.webdriver.support.ui'].WebDriverWait = FakeWait

    class Select:
        def __init__(self, element):
            self.element = element

        def select_by_value(self, value):
            driver.actions.append(('select', self.element.selector, value))
            self.element.value = value

        def select_by_visible_text(self, value):
            driver.actions.append(('select_text', self.element.selector, value))
            self.element.value = value

    modules['selenium.webdriver.support.ui'].Select = Select
    runtime = modules['ktl_runtime']
    runtime.authenticated_chrome = lambda: driver
    runtime.complete_authentication = lambda current: driver.actions.append(('authentication',))
    runtime.capture_evidence = lambda phase: driver.actions.append(('capture', phase))
    entered = []

    @contextmanager
    def business_step(order):
        entered.append(order)
        driver.actions.append(('step_begin', order))
        if hasattr(driver, 'before_step'):
            driver.before_step(order)
        try:
            yield
        finally:
            driver.actions.append(('step_end', order))

    runtime.business_step = business_step
    with patch.dict(sys.modules, modules), \
            patch('socket.create_connection', side_effect=AssertionError('No real network')), \
            patch('urllib.request.urlopen', side_effect=AssertionError('No real HTTP')), \
            patch('subprocess.Popen', side_effect=AssertionError('No real browser')), \
            redirect_stdout(io.StringIO()):
        exec(compile(code, '<synthetic-compiled-browser>', 'exec'), {})
    return entered


class ScenarioCompilerContractTests(unittest.TestCase):
    def rejected(self, source, contract):
        with self.assertRaises(EvaluationError) as caught:
            compile_code(source, contract)
        self.assertEqual(caught.exception.status, 'NOT_READY')

    def test_preparation_is_pure_deterministic_and_preserves_both_inputs(self):
        source, contract = scenario()
        original = deepcopy((source, contract))
        with patch('socket.create_connection', side_effect=AssertionError('No network in compiler')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP in compiler')), \
                patch('subprocess.Popen', side_effect=AssertionError('No browser in compiler')):
            first = compile_code(source, contract)
            second = compile_code(source, contract)
        self.assertEqual((source, contract), original)
        self.assertEqual(first, second)
        self.assertIsInstance(first, str)
        compile(first, '<synthetic-compiled-scenario>', 'exec')
        self.assertFalse(source['generated_by_llm'])

    def test_literal_identity_and_every_business_step_are_in_the_original_order(self):
        source, contract = scenario()
        tree = ast.parse(compile_code(source, contract))
        identities = [ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'SCENARIO_ID' for target in node.targets)]
        self.assertEqual(identities, [source['scenario_id']])
        blocks = [node for node in ast.walk(tree) if isinstance(node, ast.With)
                  and any(isinstance(item.context_expr, ast.Call)
                          and isinstance(item.context_expr.func, ast.Name)
                          and item.context_expr.func.id == 'business_step' for item in node.items)]
        blocks.sort(key=lambda node: node.lineno)
        self.assertTrue(blocks)
        self.assertEqual(execute_synthetic(compile_code(source, contract), FakeDriver()), [1, 2, 3])
        self.assertTrue(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))

    def test_missing_contract_never_creates_inferred_checks(self):
        source, _ = scenario()
        source.pop('execution_contract')
        for contract in (None, {}, []):
            with self.subTest(contract_type=type(contract).__name__):
                self.rejected(source, contract)

    def test_unknown_actions_are_rejected_without_mutating_source(self):
        for action in ('NAVIGATE', 'REGISTER', 'run_python', 'unknown'):
            source, contract = scenario()
            source['steps'][1]['action'] = contract['steps'][1]['action'] = action
            source['execution_contract'] = deepcopy(contract)
            original = deepcopy((source, contract))
            with self.subTest(action=action):
                self.rejected(source, contract)
                self.assertEqual((source, contract), original)

    def test_duplicate_reversed_and_missing_orders_are_not_repaired(self):
        for orders in ([1, 1, 3], [3, 2, 1], [1, 3, 4], [1, True, 3]):
            source, contract = scenario()
            for step, rule, order in zip(source['steps'], contract['steps'], orders):
                step['order'] = rule['order'] = order
            source['execution_contract'] = deepcopy(contract)
            with self.subTest(orders=orders):
                self.rejected(source, contract)

    def test_contract_identity_step_action_and_length_must_match(self):
        for change in ('identity', 'action', 'length'):
            source, contract = scenario()
            if change == 'identity':
                contract['scenario_id'] = 'SYNTHETIC-OTHER-SCENARIO'
            elif change == 'action':
                contract['steps'][1]['action'] = 'click'
            else:
                contract['steps'].pop()
            with self.subTest(change=change):
                self.rejected(source, contract)

    def test_missing_expected_result_or_all_typed_checks_is_not_ready(self):
        for change in ('expected_result', 'empty_checks', 'unknown_check'):
            source, contract = scenario()
            if change == 'expected_result':
                source['steps'][1].pop('expected_result')
            elif change == 'empty_checks':
                contract['steps'][1]['checks'] = []
            else:
                contract['steps'][1]['checks'] = [dict(kind='infer_business_success')]
            source['execution_contract'] = deepcopy(contract)
            with self.subTest(change=change):
                self.rejected(source, contract)

    def test_input_requires_an_explicit_action_value_even_if_the_check_has_one(self):
        for action in ('input', 'type', 'select'):
            for change in ('missing', 'none', 'number'):
                source, contract = scenario()
                source['steps'][1]['action'] = contract['steps'][1]['action'] = action
                if change == 'missing':
                    source['steps'][1].pop('value')
                else:
                    source['steps'][1]['value'] = None if change == 'none' else 123
                source['execution_contract'] = deepcopy(contract)
                with self.subTest(action=action, change=change):
                    self.rejected(source, contract)

    def test_reserved_keys_and_invalid_match_or_checkpoint_metadata_are_rejected(self):
        for value in ('bad\x00value', 'bad\tvalue', 'bad\ue007value'):
            source, contract = scenario()
            source['steps'][1]['value'] = value
            contract['steps'][1]['checks'][0]['expected'] = value
            with self.subTest(value_type='reserved_key'):
                self.rejected(source, contract)
        for checkpoints in ({'before': 0, 'after': 3}, {'before': 3, 'after': 1},
                            {'before': True, 'after': 3}, {'before': 1}, []):
            source, contract = scenario()
            source['screenshot_checkpoints'] = checkpoints
            with self.subTest(checkpoints=checkpoints):
                self.rejected(source, contract)
        for match in ('', ' ', None, ['Synthetic']):
            source, contract = scenario()
            source['steps'][1]['match_text'] = match
            with self.subTest(match_type=type(match).__name__):
                self.rejected(source, contract)

    def test_recursive_truth_and_authentication_values_are_not_compiled(self):
        for key, value in [('ground_truth', ['SYNTHETIC']), ('gt_steps', [1]),
                           ('expected_label', 'PASS'), ('official_pass', True),
                           ('password', 'SYNTHETIC-PRIVATE'), ('api_key', 'SYNTHETIC-PRIVATE')]:
            for owner in ('source', 'contract'):
                source, contract = scenario()
                (source if owner == 'source' else contract)['nested'] = [{'nested': {key: value}}]
                with self.subTest(key=key, owner=owner):
                    self.rejected(source, contract)

    def test_authentication_target_or_literal_is_never_used_as_business_input(self):
        for change in ('target', 'literal', 'url'):
            source, contract = scenario()
            if change == 'target':
                source['steps'][1]['target'] = '#password'
                contract['steps'][1]['target'] = css('#password')
                contract['steps'][1]['checks'][0]['target'] = css('#password')
            elif change == 'literal':
                source['steps'][1]['value'] = 'Authorization: Bearer SYNTHETIC'
                contract['steps'][1]['checks'][0]['expected'] = source['steps'][1]['value']
            else:
                source['steps'][0]['url'] = source['steps'][0]['target'] = 'https://example.invalid/work?token=SYNTHETIC'
                contract['steps'][0]['target'] = {'url': source['steps'][0]['url']}
            source['execution_contract'] = deepcopy(contract)
            with self.subTest(change=change):
                self.rejected(source, contract)

    def test_supported_scope_is_explicit_and_complex_checks_do_not_silently_disappear(self):
        self.assertEqual(SUPPORTED_ACTIONS, frozenset({'open', 'navigate', 'click', 'input', 'type',
                         'fill_empty', 'clear', 'submit', 'select', 'back', 'forward', 'refresh', 'verify'}))
        self.assertEqual(SUPPORTED_CHECKS, frozenset({'visible', 'focus', 'value', 'text_equals',
                         'fill_empty', 'text_contains', 'count', 'text_count', 'url_path', 'nonempty', 'text_equals_target'}))
        complex_checks = [
            dict(kind='native_submit_response', method='POST', api_origin='https://example.invalid',
                 api_path='/api/synthetic', expected_status=201),
            dict(kind='cards_state'), dict(kind='cards_search'),
        ]
        for condition in complex_checks:
            source, contract = scenario()
            contract['steps'][2]['checks'].append(condition)
            source['execution_contract'] = deepcopy(contract)
            with self.subTest(kind=condition['kind']):
                self.rejected(source, contract)

    def test_quotes_newlines_and_code_like_values_cannot_inject_python(self):
        source, contract = scenario()
        payload = "');__import__('subprocess').Popen(['SYNTHETIC']);#\n한글"
        selector = "#synthetic[data-note=\"');raise RuntimeError('SYNTHETIC');#\"]"
        source['scenario_id'] = contract['scenario_id'] = "SYNTHETIC';raise RuntimeError('SYNTHETIC');#"
        source['steps'][1].update(target=selector, value=payload)
        contract['steps'][1].update(target=css(selector), checks=[dict(kind='value', target=css(selector), expected=payload)])
        source['execution_contract'] = deepcopy(contract)
        code = compile_code(source, contract)
        tree = ast.parse(code)
        compile(tree, '<synthetic-literal-injection>', 'exec')
        forbidden_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                           and ((isinstance(node.func, ast.Name) and node.func.id in {'exec', 'eval', '__import__'})
                                or (isinstance(node.func, ast.Attribute) and node.func.attr in {'Popen', 'system'}))]
        self.assertEqual(forbidden_calls, [])
        ids = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == 'SCENARIO_ID' for target in node.targets)]
        self.assertEqual(ids, [source['scenario_id']])


class ScenarioCompilerExecutionTests(unittest.TestCase):
    def test_real_generated_input_and_typed_output_assertions_execute_against_a_fake_browser(self):
        source, contract = scenario()
        driver = FakeDriver()
        entered = execute_synthetic(compile_code(source, contract), driver)
        self.assertEqual(entered, [1, 2, 3])
        self.assertEqual(driver.elements['#synthetic-input'][0].value, 'Synthetic input')
        self.assertIn(('get', 'http://127.0.0.1:9/work'), driver.actions)
        self.assertTrue(any(action[0] == 'send_keys' for action in driver.actions))
        self.assertEqual(driver.quit_count, 1)

    def test_failed_typed_output_assertion_stops_the_code_and_always_quits(self):
        source, contract = scenario()
        driver = FakeDriver()
        driver.elements['#synthetic-output'][0].text = 'Synthetic wrong persisted value'
        with self.assertRaises((AssertionError, TimeoutError)):
            execute_synthetic(compile_code(source, contract), driver)
        self.assertEqual(driver.quit_count, 1)

    def test_dom_authentication_aliases_are_refused_before_typing_and_still_quit(self):
        for attributes in ({'type': 'password'}, {'type': 'hidden'}, {'id': 'loginId'},
                           {'name': 'account_password'}, {'autocomplete': 'current-password'}):
            source, contract = scenario()
            driver = FakeDriver()
            driver.elements['#synthetic-input'][0].attributes = attributes
            with self.subTest(attribute_names=list(attributes)):
                with self.assertRaises(RuntimeError):
                    execute_synthetic(compile_code(source, contract), driver)
                self.assertFalse(any(action[0] in {'send_keys', 'clear'} for action in driver.actions))
                self.assertEqual(driver.quit_count, 1)

    def test_multiline_values_need_a_textarea_and_select_or_submit_need_native_controls(self):
        for tag, success in [('input', False), ('textarea', True)]:
            source, contract = scenario()
            source['steps'][1]['value'] = 'Synthetic first\nSynthetic second'
            contract['steps'][1]['checks'][0]['expected'] = source['steps'][1]['value']
            source['execution_contract'] = deepcopy(contract)
            driver = FakeDriver()
            driver.elements['#synthetic-input'][0].tag_name = tag
            with self.subTest(action='input', tag=tag):
                if success:
                    execute_synthetic(compile_code(source, contract), driver)
                    self.assertEqual(driver.elements['#synthetic-input'][0].value, source['steps'][1]['value'])
                else:
                    with self.assertRaises(RuntimeError):
                        execute_synthetic(compile_code(source, contract), driver)
                    self.assertFalse(any(action[0] == 'send_keys' for action in driver.actions))
                self.assertEqual(driver.quit_count, 1)
        for action, tag, attributes in [('select', 'div', {}), ('submit', 'div', {}),
                                        ('submit', 'input', {'type': 'text'}),
                                        ('submit', 'button', {'type': 'reset'})]:
            source, contract = scenario()
            source['steps'][1]['action'] = contract['steps'][1]['action'] = action
            contract['steps'][1]['checks'] = [dict(kind='visible', target=css('#synthetic-output'), expected=True)]
            source['execution_contract'] = deepcopy(contract)
            driver = FakeDriver()
            driver.elements['#synthetic-input'][0].tag_name = tag
            driver.elements['#synthetic-input'][0].attributes = attributes
            with self.subTest(action=action, tag=tag, input_type=attributes.get('type')):
                with self.assertRaises(RuntimeError):
                    execute_synthetic(compile_code(source, contract), driver)
                self.assertFalse(any(record[0] in {'select', 'select_text', 'submit', 'click'} for record in driver.actions))
                self.assertEqual(driver.quit_count, 1)

    def test_explicit_trusted_setup_and_screenshot_hooks_preserve_the_business_denominator(self):
        source, contract = scenario()
        source['steps'].pop(0)
        contract['steps'].pop(0)
        for order, (step, rule) in enumerate(zip(source['steps'], contract['steps']), 1):
            step['order'] = rule['order'] = order
        source['execution_contract'] = deepcopy(contract)
        with self.assertRaises(EvaluationError) as caught:
            compile_code(source, contract)
        self.assertEqual(caught.exception.status, 'NOT_READY')
        source['start_url'] = 'http://127.0.0.1:9/setup'
        with self.assertRaises(EvaluationError):
            compile_code(source, contract)
        source['start_url'] = 'https://rainbowlab.ai.kr/mypage/synthetic'
        source['screenshot_checkpoints'] = {'before': 1, 'after': 2}
        driver = FakeDriver()
        self.assertEqual(execute_synthetic(compile_code(source, contract), driver), [1, 2])
        self.assertEqual(driver.actions.count(('authentication',)), 1)
        self.assertLess(driver.actions.index(('authentication',)), driver.actions.index(('step_begin', 1)))
        self.assertEqual([action for action in driver.actions if action[0] == 'capture'],
                         [('capture', 'before'), ('capture', 'after')])
        self.assertEqual(driver.quit_count, 1)

    def test_zero_or_duplicate_input_targets_are_not_silently_selected(self):
        for count in (0, 2):
            source, contract = scenario()
            driver = FakeDriver()
            driver.elements['#synthetic-input'] = [FakeElement(driver, '#synthetic-input') for _ in range(count)]
            with self.subTest(count=count):
                with self.assertRaises((AssertionError, TimeoutError)):
                    execute_synthetic(compile_code(source, contract), driver)
                self.assertFalse(any(action[0] == 'send_keys' for action in driver.actions))
                self.assertEqual(driver.quit_count, 1)

    def test_all_twelve_declared_actions_run_native_commands_in_their_business_step(self):
        source, contract = scenario()
        actions = [
            ('open', 'http://127.0.0.1:9/work', None),
            ('navigate', 'http://127.0.0.1:9/other', None),
            ('click', '#synthetic-button', None),
            ('input', '#synthetic-input', 'Synthetic input'),
            ('type', '#synthetic-typed', 'Synthetic typed'),
            ('clear', '#synthetic-clear', None),
            ('submit', '#synthetic-form', None),
            ('select', '#synthetic-select', 'Synthetic option'),
            ('back', '#synthetic-output', None),
            ('forward', '#synthetic-output', None),
            ('refresh', '#synthetic-output', None),
            ('verify', '#synthetic-output', None),
        ]
        source['steps'], contract['steps'] = [], []
        for order, (action, target, value) in enumerate(actions, 1):
            step = dict(order=order, action=action, target=target, expected_result='Synthetic explicit outcome')
            rule = dict(order=order, action=action, target=css(target),
                        checks=[dict(kind='visible', target=css('#synthetic-output'), expected=True)])
            if action in {'open', 'navigate'}:
                step['url'] = target
                rule['target'] = {'url': target}
                rule['checks'] = [dict(kind='url_path', expected='/work' if order == 1 else '/other')]
            elif action in {'input', 'type', 'select', 'clear'}:
                if value is not None:
                    step['value'] = value
                rule['checks'] = [dict(kind='value', target=css(target), expected=value or '')]
            source['steps'].append(step)
            contract['steps'].append(rule)
        source['execution_contract'] = deepcopy(contract)
        driver = FakeDriver()
        for selector, tag, value in [('#synthetic-button', 'button', ''), ('#synthetic-typed', 'input', ''),
                                     ('#synthetic-clear', 'input', 'Synthetic previous'),
                                     ('#synthetic-form', 'form', ''), ('#synthetic-select', 'select', '')]:
            driver.add(selector, tag=tag, value=value)
        entered = execute_synthetic(compile_code(source, contract), driver)
        self.assertEqual(entered, list(range(1, 13)))
        expected_commands = {1: 'get', 2: 'get', 3: 'click', 4: 'send_keys', 5: 'send_keys',
                             6: 'clear', 7: 'submit', 9: 'back', 10: 'forward', 11: 'refresh'}
        for order, command in expected_commands.items():
            start = driver.actions.index(('step_begin', order))
            end = driver.actions.index(('step_end', order))
            with self.subTest(order=order, command=command):
                self.assertIn(command, [record[0] for record in driver.actions[start + 1:end]])
        self.assertTrue(any(record[0] in {'select', 'select_text'} for record in driver.actions))
        self.assertEqual(driver.elements['#synthetic-clear'][0].value, '')
        self.assertEqual(driver.elements['#synthetic-typed'][0].value, 'Synthetic typed')
        self.assertEqual(driver.elements['#synthetic-select'][0].value, 'Synthetic option')
        self.assertEqual(driver.quit_count, 1)

    def test_each_unconditional_typed_check_accepts_observed_success_and_rejects_counterevidence(self):
        conditions = [
            dict(kind='visible', target=css('#synthetic-output'), expected=True),
            dict(kind='focus', target=css('#synthetic-input'), expected=True),
            dict(kind='value', target=css('#synthetic-input'), expected='Synthetic input'),
            dict(kind='text_equals', target=css('#synthetic-output'), expected='Synthetic saved'),
            dict(kind='text_contains', target=css('#synthetic-output'), expected='saved'),
            dict(kind='count', target=css('#synthetic-output'), expected=1),
            dict(kind='text_count', target=css('#synthetic-output'), expected='Synthetic saved', count=1),
            dict(kind='url_path', expected='/work'),
            dict(kind='nonempty', target=css('#synthetic-output'), property='text'),
            dict(kind='text_equals_target', target=css('#synthetic-input'), property='value',
                 other_target=css('#synthetic-mirror'), other_property='value'),
        ]
        # fill_empty requires its earlier typed input snapshot; its conditional
        # cases are exercised by the dedicated empty-input and BU01 regressions.
        self.assertEqual({condition['kind'] for condition in conditions}, SUPPORTED_CHECKS - {'fill_empty'})
        for condition in conditions:
            source, contract = scenario()
            contract['steps'][2]['checks'] = [condition]
            source['execution_contract'] = deepcopy(contract)
            code = compile_code(source, contract)
            driver = FakeDriver()
            driver.add('#synthetic-mirror', value='Synthetic input')
            with self.subTest(kind=condition['kind'], observed='matching'):
                execute_synthetic(code, driver)
                self.assertEqual(driver.quit_count, 1)
            driver = FakeDriver()
            driver.add('#synthetic-mirror', value='Synthetic different')

            def counterevidence(order):
                if order != 3:
                    return
                kind = condition['kind']
                if kind == 'visible':
                    driver.elements['#synthetic-output'][0].shown = False
                elif kind == 'focus':
                    driver.switch_to.active_element = None
                elif kind == 'value':
                    driver.elements['#synthetic-input'][0].value = 'Synthetic different'
                elif kind == 'count':
                    driver.elements['#synthetic-output'] = []
                elif kind == 'url_path':
                    driver.current_url = 'http://127.0.0.1:9/wrong'
                else:
                    driver.elements['#synthetic-output'][0].text = ''

            driver.before_step = counterevidence
            with self.subTest(kind=condition['kind'], observed='counterevidence'):
                with self.assertRaises((AssertionError, TimeoutError)):
                    execute_synthetic(code, driver)
                self.assertEqual(driver.quit_count, 1)

    def test_match_text_requires_exact_normalized_unique_text_and_never_falls_back_to_first(self):
        for texts, expected in [(['Synthetic wrong', ' Synthetic   selected '], 1),
                                (['Synthetic wrong'], None),
                                (['Synthetic selected', 'Synthetic  selected'], None)]:
            source, contract = scenario()
            source['steps'][1].update(action='click', target='.synthetic-choice', match_text='Synthetic selected')
            source['steps'][1].pop('value')
            contract['steps'][1].update(action='click', target=css('.synthetic-choice'), checks=[
                dict(kind='visible', target=css('#synthetic-output'), expected=True)])
            source['execution_contract'] = deepcopy(contract)
            driver = FakeDriver()
            driver.elements['.synthetic-choice'] = [FakeElement(driver, 'choice-' + str(i), text=text, tag='button')
                                                     for i, text in enumerate(texts)]
            with self.subTest(candidate_count=len(texts), expected=expected):
                if expected is None:
                    with self.assertRaises((AssertionError, TimeoutError)):
                        execute_synthetic(compile_code(source, contract), driver)
                    self.assertFalse(any(action[0] == 'click' for action in driver.actions))
                else:
                    execute_synthetic(compile_code(source, contract), driver)
                    self.assertIn(('click', 'choice-' + str(expected)), driver.actions)
                    self.assertNotIn(('click', 'choice-0'), driver.actions)
                self.assertEqual(driver.quit_count, 1)


class ScenarioCompilerRowMatchTests(unittest.TestCase):
    """Synthetic row identity checks; real row values and browser calls are absent."""

    rows_css = '.synthetic-record-row'
    cell_css = '.synthetic-company'
    button_css = 'button.synthetic-detail'
    expected_company = 'Synthetic Company'

    def fixture(self):
        source, contract = scenario()
        source['steps'][1] = dict(order=2, action='click', target=self.button_css,
            row_match=dict(rows=self.rows_css, cell=self.cell_css, expected=self.expected_company),
            expected_result='Synthetic matching record is opened')
        contract['steps'][1] = dict(order=2, action='click', target=css(self.button_css), checks=[
            dict(kind='text_equals', target=css('#synthetic-output'), expected='Synthetic matching detail')])
        contract['steps'][2]['checks'][0]['expected'] = 'Synthetic matching detail'
        source['execution_contract'] = deepcopy(contract)
        driver = FakeDriver()
        driver.elements['#synthetic-output'][0].text = 'Synthetic not opened'
        # A global target and the first row are deliberate wrong-target decoys.
        driver.add(self.button_css, tag='button', attributes={'type': 'button'})
        wrong = self.add_row(driver, 'wrong', 'Synthetic Other Company')
        matching = self.add_row(driver, 'matching', ' Synthetic\n  Company ')
        driver.elements[self.rows_css] = [wrong, matching]
        return source, contract, driver, matching

    def add_row(self, driver, identity, company, *, shown=True):
        row = FakeElement(driver, 'row-' + identity, tag='tr', shown=shown)
        cell = FakeElement(driver, 'company-' + identity, tag='td', text=company)
        button = FakeElement(driver, 'detail-' + identity, tag='button', attributes={'type': 'button'})
        button.after_click = lambda: setattr(driver.elements['#synthetic-output'][0], 'text',
            'Synthetic matching detail' if identity == 'matching' else 'Synthetic wrong detail')
        row.children = {self.cell_css: [cell], self.button_css: [button]}
        return row

    def assert_no_click_and_quit(self, source, contract, driver):
        with self.assertRaises((AssertionError, RuntimeError, TimeoutError)):
            execute_synthetic(compile_code(source, contract), driver)
        self.assertFalse(any(action[0] == 'click' for action in driver.actions))
        self.assertEqual(driver.quit_count, 1)

    def test_exact_normalized_company_selects_only_its_native_descendant_and_checks_the_result(self):
        source, contract, driver, matching = self.fixture()
        original = deepcopy((source, contract))
        self.assertEqual(execute_synthetic(compile_code(source, contract), driver), [1, 2, 3])
        self.assertEqual([action for action in driver.actions if action[0] == 'click'], [('click', 'detail-matching')])
        self.assertIn(self.cell_css, matching.find_calls)
        self.assertIn(self.button_css, matching.find_calls)
        self.assertEqual(driver.elements['#synthetic-output'][0].text, 'Synthetic matching detail')
        self.assertTrue(any('M03_PREPARED_TYPED_CHECK' in script and args[1] == 'text_equals'
                            for script, args in driver.script_calls))
        self.assertEqual((source, contract), original)
        self.assertEqual(driver.quit_count, 1)

    def test_no_duplicate_prefix_or_hidden_company_match_never_uses_a_global_or_first_button(self):
        for variant in ('missing_rows', 'wrong', 'prefix', 'duplicate', 'hidden'):
            source, contract, driver, matching = self.fixture()
            if variant == 'missing_rows':
                driver.elements[self.rows_css] = []
            elif variant in {'wrong', 'prefix'}:
                matching.children[self.cell_css][0].text = ('Synthetic Another' if variant == 'wrong'
                                                           else self.expected_company + ' Subsidiary')
            elif variant == 'duplicate':
                driver.elements[self.rows_css].append(self.add_row(driver, 'duplicate', self.expected_company))
            else:
                matching.shown = False
            with self.subTest(variant=variant):
                self.assert_no_click_and_quit(source, contract, driver)

    def test_missing_duplicate_or_hidden_cells_and_buttons_do_not_silently_choose_one(self):
        for owner in ('cell', 'button'):
            for count in (0, 2):
                source, contract, driver, matching = self.fixture()
                selector = self.cell_css if owner == 'cell' else self.button_css
                original = matching.children[selector][0]
                matching.children[selector] = [original] * count
                with self.subTest(owner=owner, count=count):
                    self.assert_no_click_and_quit(source, contract, driver)
        for owner in ('cell', 'button'):
            source, contract, driver, matching = self.fixture()
            matching.children[self.cell_css if owner == 'cell' else self.button_css][0].shown = False
            with self.subTest(hidden=owner):
                self.assert_no_click_and_quit(source, contract, driver)

    def test_authentication_aliases_and_non_native_descendant_targets_are_never_clicked(self):
        for owner in ('cell', 'button'):
            for attributes in ({'type': 'password'}, {'type': 'hidden'}, {'id': 'loginId'},
                               {'name': 'account_password'}, {'autocomplete': 'current-password'}):
                source, contract, driver, matching = self.fixture()
                matching.children[self.cell_css if owner == 'cell' else self.button_css][0].attributes = attributes
                with self.subTest(owner=owner, attribute_names=list(attributes)):
                    self.assert_no_click_and_quit(source, contract, driver)
        for owner in ('row', 'button'):
            source, contract, driver, matching = self.fixture()
            (matching if owner == 'row' else matching.children[self.button_css][0]).enabled = False
            with self.subTest(disabled=owner):
                self.assert_no_click_and_quit(source, contract, driver)
        source, contract, driver, matching = self.fixture()
        matching.children[self.button_css][0].tag_name = 'div'
        self.assert_no_click_and_quit(source, contract, driver)

    def test_row_or_company_changed_after_scroll_is_rechecked_before_click(self):
        for variant in ('row_replaced', 'company_changed', 'button_auth_alias'):
            source, contract, driver, matching = self.fixture()

            def change_dom(_):
                if variant == 'row_replaced':
                    driver.elements[self.rows_css] = [self.add_row(driver, 'replacement', 'Synthetic Wrong')]
                elif variant == 'company_changed':
                    matching.children[self.cell_css][0].text = 'Synthetic Wrong'
                else:
                    matching.children[self.button_css][0].attributes = {'type': 'password'}

            driver.before_scroll = change_dom
            with self.subTest(variant=variant):
                self.assert_no_click_and_quit(source, contract, driver)

    def test_native_click_alone_cannot_satisfy_an_independent_wrong_detail_result(self):
        source, contract, driver, matching = self.fixture()
        matching.children[self.button_css][0].after_click = lambda: setattr(
            driver.elements['#synthetic-output'][0], 'text', 'Synthetic wrong detail')
        with self.assertRaises((AssertionError, TimeoutError)):
            execute_synthetic(compile_code(source, contract), driver)
        self.assertEqual([action for action in driver.actions if action[0] == 'click'], [('click', 'detail-matching')])
        self.assertEqual(driver.quit_count, 1)

    def test_row_match_schema_is_strict_and_does_not_accept_implicit_selection_or_combined_text_matching(self):
        cases = [None, [], {}, {'rows': self.rows_css, 'cell': self.cell_css},
                 {'rows': self.rows_css, 'cell': self.cell_css, 'expected': ''},
                 {'rows': self.rows_css, 'cell': self.cell_css, 'expected': ' '},
                 {'rows': self.rows_css, 'cell': self.cell_css, 'expected': 123},
                 {'rows': self.rows_css, 'cell': self.cell_css, 'expected': 'S' * 2001},
                 {'rows': self.rows_css, 'cell': self.cell_css, 'expected': self.expected_company, 'first': True}]
        for value in cases:
            source, contract, _, _ = self.fixture()
            source['steps'][1]['row_match'] = value
            with self.subTest(row_match_type=type(value).__name__, keys=list(value) if isinstance(value, dict) else None):
                with self.assertRaises(EvaluationError) as caught:
                    compile_code(source, contract)
                self.assertEqual(caught.exception.status, 'NOT_READY')
        for action in ('input', 'type', 'submit', 'select', 'verify', 'clear'):
            source, contract, _, _ = self.fixture()
            source['steps'][1]['action'] = contract['steps'][1]['action'] = action
            source['steps'][1]['value'] = 'Synthetic new input'
            source['execution_contract'] = deepcopy(contract)
            with self.subTest(action=action):
                with self.assertRaises(EvaluationError) as caught:
                    compile_code(source, contract)
                self.assertEqual(caught.exception.status, 'NOT_READY')
        source, contract, _, _ = self.fixture()
        source['steps'][1]['match_text'] = 'Synthetic matching detail'
        with self.assertRaises(EvaluationError) as caught:
            compile_code(source, contract)
        self.assertEqual(caught.exception.status, 'NOT_READY')

    def test_row_match_empty_url_auth_selectors_and_secret_literals_are_not_compiled(self):
        for key in ('rows', 'cell'):
            for value in ('', ' ', None, [], 'https://example.invalid/work', 'http://example.invalid',
                          'file:///synthetic', 'javascript:void(0)', '#password', ' .synthetic', '.synthetic '):
                source, contract, _, _ = self.fixture()
                source['steps'][1]['row_match'][key] = value
                with self.subTest(key=key, value_type=type(value).__name__):
                    with self.assertRaises(EvaluationError) as caught:
                        compile_code(source, contract)
                    self.assertEqual(caught.exception.status, 'NOT_READY')
        for value in ('Authorization: Bearer SYNTHETIC', 'password=SYNTHETIC'):
            source, contract, _, _ = self.fixture()
            source['steps'][1]['row_match']['expected'] = value
            with self.subTest(literal_kind=value.split(':', 1)[0].split('=', 1)[0]):
                with self.assertRaises(EvaluationError) as caught:
                    compile_code(source, contract)
                self.assertEqual(caught.exception.status, 'NOT_READY')

    def test_row_match_code_like_expected_text_stays_literal_data_and_preserves_origin(self):
        source, contract, driver, matching = self.fixture()
        payload = "Synthetic ');raise RuntimeError('INJECTION');#\n회사"
        source['steps'][1]['row_match']['expected'] = payload
        matching.children[self.cell_css][0].text = payload
        original = deepcopy((source, contract))
        code = compile_code(source, contract)
        tree = ast.parse(code)
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id in {'eval', 'exec', '__import__'} for node in ast.walk(tree)))
        self.assertEqual(execute_synthetic(code, driver), [1, 2, 3])
        self.assertFalse(source['generated_by_llm'])
        self.assertEqual((source, contract), original)
        self.assertEqual(driver.quit_count, 1)


if __name__ == '__main__':
    unittest.main()
