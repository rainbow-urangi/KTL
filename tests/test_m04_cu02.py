"""CU02 준비·고정 계약 회귀. 합성 입력만 사용하고 브라우저/업무/GPT를 실행하지 않는다."""
import ast
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

from backend.evaluators import EvaluationError
from backend.m04 import cu02
from backend.m04.checks import prepare_contract
from backend.m04.store import M04Manager
from backend.session import RuntimeSession


SYNTHETIC_LOGIN = {
    'KTL_M04_RBEM_USERNAME': 'SYNTHETIC_CU02_ACCOUNT_ONLY',
    'KTL_M04_RBEM_PASSWORD': 'SYNTHETIC_CU02_SECRET_ONLY',
}
SYNTHETIC_TOKEN = 'SYNTHETIC_CU02_RUNTIME_TOKEN_ONLY'
DEFAULT_AUTH_REPLY = object()


def inputs():
    return dict(date='2026-11-13', title='SYNTHETIC CU02 schedule',
                description='Synthetic preparation only; no site execution.', browser='edge')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CU02PreparationTests(unittest.TestCase):
    def test_new_inputs_and_workflow_default_to_chrome_even_when_edge_is_installed(self):
        payload = inputs()
        payload.pop('browser')
        with patch.dict(os.environ, {'PROGRAMFILES(X86)': 'C:/SYNTHETIC_BROWSER_INSTALL'}), \
                patch('backend.m04.cu02.Path.is_file', return_value=True), \
                patch('backend.m04.cu02.login_configured', return_value=True):
            self.assertEqual(cu02.default_browser(), 'chrome')
            self.assertEqual(cu02.prepare(payload)['parameters']['browser'], 'chrome')
            workflow = cu02.workflow(Path('C:/SYNTHETIC_PROJECT'))
        self.assertEqual(workflow['defaults']['browser'], 'chrome')
        self.assertEqual(workflow['browser_name'], 'Chrome')

    def test_normalized_inputs_remain_data_and_prepare_has_no_external_work(self):
        payload = inputs()
        payload.update(title='  Synthetic "quoted" title  ', description='  First line\nSecond line  ')
        original = deepcopy(payload)
        with patch('subprocess.Popen', side_effect=AssertionError('No process during preparation')), \
                patch('socket.create_connection', side_effect=AssertionError('No network during preparation')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP during preparation')):
            result = cu02.prepare(payload)
        self.assertEqual(payload, original)
        self.assertEqual(result['parameters']['title'], 'Synthetic "quoted" title')
        self.assertEqual(result['parameters']['description'], 'First line\nSecond line')
        compile(result['code'], '<synthetic-cu02-fixed-script>', 'exec')
        tree = ast.parse(result['code'])
        constants = {target.id: ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                     for target in node.targets if isinstance(target, ast.Name)}
        self.assertEqual(json.loads(constants['DATA_JSON'])['title'], result['parameters']['title'])
        self.assertEqual(constants['SCENARIO_ID'], result['scenario']['scenario_id'])
        self.assertEqual(prepare_contract(result['scenario']), result['contract'])
        self.assertEqual(cu02.prepare(deepcopy(payload)), result)

    def test_date_selection_uses_sunday_first_grid_and_retains_month_boundaries(self):
        cases = [('2026-11-01', 1), ('2026-11-30', 30), ('2026-06-01', 2),
                 ('2026-05-01', 6), ('2026-08-01', 7), ('2026-08-31', 37), ('2024-02-29', 33)]
        for day, index in cases:
            with self.subTest(day=day):
                payload = inputs()
                payload['date'] = day
                result = cu02.prepare(payload)
                definition = result['definition']
                self.assertTrue(definition['calendar_cell'].endswith(':nth-child(' + str(index) + ')'))
                self.assertEqual(definition['date_target'], definition['calendar_cell'] + ' .monthly-calendar__date-number')
                self.assertEqual(result['contract']['steps'][0]['checks'][1]['expected'], day[:7].replace('-', '.'))
                self.assertEqual(json.loads(result['source_files']['cu02_parameters.json'])['date'], day)

    def test_invalid_payloads_dates_text_and_browser_types_are_rejected(self):
        invalid = [None, [], {}, dict(inputs(), unknown=True),
                   dict(inputs(), date='2026-2-03'), dict(inputs(), date='2026-02-29'),
                   dict(inputs(), date='2026-04-31'), dict(inputs(), date='1999-12-31'),
                   dict(inputs(), date='2101-01-01'), dict(inputs(), date=20261113),
                   dict(inputs(), title=' '), dict(inputs(), title='x' * 121),
                   dict(inputs(), title='line\nbreak'), dict(inputs(), title=123),
                   dict(inputs(), description='x' * 2001), dict(inputs(), description='bad\x00text'),
                   dict(inputs(), description=None), dict(inputs(), browser='firefox'),
                   dict(inputs(), browser=True), dict(inputs(), browser=[]), dict(inputs(), browser={})]
        for payload in invalid:
            with self.subTest(payload_type=type(payload).__name__, field_types={k: type(v).__name__ for k, v in payload.items()} if isinstance(payload, dict) else None):
                with self.assertRaises(EvaluationError):
                    cu02.prepare(payload)

    def test_secret_literals_and_client_execution_instructions_are_rejected(self):
        for changes in [dict(title='Authorization: Bearer SYNTHETIC'),
                        dict(description='https://example.invalid/path?token=SYNTHETIC'),
                        dict(password='SYNTHETIC'), dict(target_url='https://example.invalid'),
                        dict(run_mode='OFFICIAL')]:
            with self.subTest(fields=list(changes)), self.assertRaises(EvaluationError):
                cu02.prepare(dict(inputs(), **changes))

    def test_business_steps_follow_all_five_pdf_procedures_without_m03_or_gt(self):
        result = cu02.prepare(inputs())
        self.assertEqual(result['definition']['procedures'], ['일정관리', '날짜 선택', '일정 입력', '등록', '종료'])
        self.assertEqual(result['definition']['source_document_sha256'],
                         '8f0fb27bf28de7d39d221d71781c82fae5456dcdfb0750205024fcf85bcbef72')
        self.assertEqual([step['action'] for step in result['scenario']['steps']], ['open', 'click', 'input', 'submit', 'verify'])
        self.assertEqual([step['order'] for step in result['scenario']['steps']], [1, 2, 3, 4, 5])
        self.assertEqual([step['order'] for step in result['contract']['steps']], [1, 2, 3, 4, 5])
        self.assertFalse(result['scenario']['official'])
        self.assertFalse(result['scenario']['generated_by_llm'])
        self.assertEqual(result['scenario']['run_mode'], 'DEVELOPMENT')
        source = result['code']
        tree = ast.parse(source)
        blocks = [node for node in ast.walk(tree) if isinstance(node, ast.With)
                  and any(isinstance(item.context_expr, ast.Call)
                          and isinstance(item.context_expr.func, ast.Name)
                          and item.context_expr.func.id == 'business_step' for item in node.items)]
        blocks.sort(key=lambda node: node.lineno)
        self.assertEqual([ast.literal_eval(node.items[0].context_expr.args[0]) for node in blocks], [1, 2, 3, 4, 5])
        self.assertNotIn('/api/m03', source)
        self.assertNotIn('ground_truth', source)
        self.assertNotIn('openai', source.lower())

    def test_native_date_number_click_guards_against_edit_mode_and_readonly_dates(self):
        result = cu02.prepare(inputs())
        source = result['code']
        tree = ast.parse(source)
        click_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'click')
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr == 'click' for node in ast.walk(click_function)))
        scripts = [ast.literal_eval(node.args[0]) for node in ast.walk(click_function)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'execute_script']
        self.assertTrue(scripts)
        self.assertTrue(all('scrollIntoView' in code or 'elementFromPoint' in code for code in scripts))
        self.assertIn("click(DATA['date_target'])", source)
        self.assertIn("cell.get_attribute('aria-readonly') != 'true'", source)
        self.assertIn("monthly-calendar__cell--outside", source)
        self.assertIn("read(DATA['modal'] + ' h2') == '업무 등록'", source)
        self.assertEqual(result['contract']['steps'][1]['checks'][1]['expected'], '업무 등록')
        self.assertEqual(result['contract']['steps'][0]['checks'][-1]['count'], 0)

    def test_saved_state_requires_reload_detail_values_and_modal_exit(self):
        result = cu02.prepare(inputs())
        source = result['code']
        start = source.index('with business_step(5):')
        final_step = source[start:]
        self.assertLess(final_step.index('driver.refresh()'), final_step.index('event.click()'))
        self.assertIn('target_month()', final_step)
        self.assertIn("get_attribute('value') == DATA['title']", final_step)
        self.assertIn("get_attribute('value') == DATA['description']", final_step)
        self.assertIn('button[aria-label="닫기"]', final_step)
        self.assertIn('modal_closed()', final_step)
        self.assertEqual([result['contract']['steps'][i]['checks'][-1]['count'] for i in (3, 4)], [1, 1])
        self.assertTrue(any(isinstance(node, ast.Try) and any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'quit'
            for statement in node.finalbody for call in ast.walk(statement)) for node in ast.walk(ast.parse(source))))

    def test_initial_and_expected_states_are_fixed_before_the_script_runs(self):
        result = cu02.prepare(inputs())
        states = result['definition']['expected_states']
        self.assertEqual(states['before'], dict(step_order=2, date=inputs()['date'], modal_heading='업무 등록',
                                               fields={cu02.TITLE: '', cu02.DESCRIPTION: ''}))
        self.assertEqual(states['after'], dict(step_order=5, date=inputs()['date'], reload_required=True,
                                              fields={cu02.TITLE: inputs()['title'], cu02.DESCRIPTION: inputs()['description']},
                                              matching_schedule_count=1))
        initial_checks = result['contract']['steps'][1]['checks']
        self.assertEqual({check['target']['value']: check['expected'] for check in initial_checks if check['kind'] == 'value'},
                         {cu02.TITLE: '', cu02.DESCRIPTION: ''})
        self.assertEqual(result['scenario']['screenshot_checkpoints'], dict(before=2, after=5))
        self.assertEqual(json.loads(result['source_files']['cu02_definition.json'])['expected_states'], states)


class CU02ScriptHydrationTests(unittest.TestCase):
    """The deployed edit modal mounts empty, then hydrates its two controlled inputs."""

    def run_script(self, *, immediate_field=None, wrong_field=None, lookup_reply=None,
                   auth_reply=DEFAULT_AUTH_REPLY, auth_error=None, auth_status=200,
                   auth_url=None, login_environment=None, cdp_error=None,
                   remove_error=None, bootstrap_reply=DEFAULT_AUTH_REPLY, initial_values=None):
        prepared = cu02.prepare(inputs())
        tree = ast.parse(prepared['code'])
        data = next(json.loads(ast.literal_eval(node.value)) for node in tree.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'DATA_JSON' for target in node.targets))
        if immediate_field:
            # Reproduce the former immediate assertion while keeping every other
            # generated statement, native action and wait unchanged.
            final = next(node for node in ast.walk(tree) if isinstance(node, ast.With)
                         and isinstance(node.items[0].context_expr, ast.Call)
                         and ast.literal_eval(node.items[0].context_expr.args[0]) == 5)
            replacements = 0
            for node in final.body:
                if not (isinstance(node, ast.Assert) and isinstance(node.test, ast.Call)
                        and isinstance(node.test.func, ast.Attribute) and node.test.func.attr == 'until'
                        and node.test.args and isinstance(node.test.args[0], ast.Lambda)):
                    continue
                predicate = node.test.args[0].body
                if isinstance(predicate, ast.Compare) and any(
                        isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name)
                        and value.value.id == 'DATA' and isinstance(value.slice, ast.Constant)
                        and value.slice.value == immediate_field for value in predicate.comparators):
                    node.test = predicate
                    replacements += 1
            self.assertEqual(replacements, 1, 'Only the intended final value wait may be removed')
            ast.fix_missing_locations(tree)

        class Keys:
            CONTROL = 'SYNTHETIC_CONTROL'
            BACKSPACE = 'SYNTHETIC_BACKSPACE'

        class Element:
            def __init__(self, driver, kind, text=''):
                self.driver, self.kind, self.text = driver, kind, text

            def is_displayed(self):
                return True

            def is_enabled(self):
                return True

            def get_attribute(self, name):
                if self.kind == 'cell':
                    return 'monthly-calendar__cell' if name == 'class' else None
                if name == 'value' and self.kind in {'title', 'description'}:
                    if self.driver.modal == 'edit':
                        self.driver.edit_reads[self.kind] += 1
                        if self.driver.edit_reads[self.kind] == 1:
                            return ''
                        return 'SYNTHETIC WRONG SAVED VALUE' if self.kind == wrong_field else self.driver.saved[self.kind]
                    return self.driver.values[self.kind]
                raise AssertionError('Unexpected synthetic attribute access')

            def send_keys(self, *values):
                self.driver.field_writes += 1
                if values == (Keys.CONTROL, 'a'):
                    return
                elif values == (Keys.BACKSPACE,):
                    self.driver.values[self.kind] = ''
                else:
                    self.driver.values[self.kind] += ''.join(values)
                    self.driver.actions.append('input-' + self.kind)

            def click(self):
                driver = self.driver
                driver.actions.append(self.kind)
                if self.kind == 'date-number':
                    driver.modal, driver.values = 'create', {'title': '', 'description': ''}
                    driver.values.update(initial_values or {})
                elif self.kind == 'create-submit':
                    if driver.modal != 'create' or driver.values != {key: data[key] for key in ('title', 'description')}:
                        raise AssertionError('Only the populated new-registration form may submit')
                    driver.saved, driver.modal = dict(driver.values), None
                elif self.kind == 'saved-event':
                    driver.modal, driver.edit_reads = 'edit', {'title': 0, 'description': 0}
                elif self.kind == 'close':
                    if driver.modal != 'edit':
                        raise AssertionError('Saved details must be opened before closing')
                    driver.modal = None
                else:
                    raise AssertionError('Unexpected synthetic native click')

        class Driver:
            def __init__(self):
                self.current_url, self.modal, self.saved = '', None, None
                self.values, self.edit_reads = {}, {'title': 0, 'description': 0}
                self.actions, self.steps = [], []
                self.false_polls = 0
                self.async_lookups = 0
                self.created = 0
                self.auth_requests = []
                self.cdp_commands = []
                self.field_writes = 0
                self.checkpoints = []

            def set_page_load_timeout(self, timeout):
                pass

            def get(self, url):
                if url != data['target_url'] or not self.cdp_commands:
                    raise AssertionError('The first visible page must be the authenticated schedule')
                self.current_url = url
                self.actions.append('get-schedule')

            def find_elements(self, by, selector):
                fixed = {data['calendar']: ('calendar', ''), data['month']: ('month', data['date'][:7].replace('-', '.')),
                         '.schedule-viewer-bar__copy strong': ('viewer', '내 일정'),
                         data['cell']: ('cell', ''), data['date_target']: ('date-number', str(int(data['date'][-2:])))}
                if selector == data['event_target']:
                    return [Element(self, 'saved-event', self.saved['title'])] if self.saved else []
                if self.modal:
                    fixed.update({data['modal']: ('modal', ''), data['modal'] + ' h2': ('heading', '업무 등록' if self.modal == 'create' else '업무 내용'),
                                  data['title_target']: ('title', ''), data['description_target']: ('description', ''),
                                  data['submit_target']: ('create-submit', '등록' if self.modal == 'create' else '확인'),
                                  data['modal'] + ' button[aria-label="닫기"]': ('close', '닫기')})
                return [Element(self, *fixed[selector])] if selector in fixed else []

            def find_element(self, by, selector):
                found = self.find_elements(by, selector)
                if len(found) != 1:
                    raise AssertionError('Synthetic selector must resolve exactly once')
                return found[0]

            def execute_script(self, source, *args):
                if 'scrollIntoView' not in source and 'elementFromPoint' not in source:
                    raise AssertionError('Synthetic driver permits only scrolling and hit testing')
                return True

            def execute_cdp_cmd(self, command, parameters):
                if cdp_error is not None:
                    raise cdp_error
                if command == 'Page.removeScriptToEvaluateOnNewDocument':
                    if remove_error is not None:
                        raise remove_error
                    if parameters != {'identifier': 'SYNTHETIC_BOOTSTRAP'}:
                        raise AssertionError('Only the registered session bootstrap may be removed')
                    self.cdp_commands.append((command, deepcopy(parameters)))
                    self.actions.append('remove-bootstrap')
                    return {}
                if command != 'Page.addScriptToEvaluateOnNewDocument' or not isinstance(parameters.get('source'), str):
                    raise AssertionError('Authentication may only bootstrap the initial document')
                self.cdp_commands.append((command, deepcopy(parameters)))
                self.actions.append('bootstrap-auth')
                return {'identifier': 'SYNTHETIC_BOOTSTRAP'} if bootstrap_reply is DEFAULT_AUTH_REPLY else bootstrap_reply

            def execute_async_script(self, source, *args):
                if args != (data['date'], data['title']):
                    raise AssertionError('Read-only duplicate lookup must use the selected date and exact title')
                self.async_lookups += 1
                self.actions.append('check-existing')
                return deepcopy({'ok': True, 'count': 0} if lookup_reply is None else lookup_reply)

            def refresh(self):
                if not self.saved or self.modal:
                    raise AssertionError('Refresh must follow a completed registration')
                self.actions.append('refresh')

            def quit(self):
                self.actions.append('quit')

        driver = Driver()
        valid_reply = dict(success=True, token=SYNTHETIC_TOKEN, role='USER',
                           name='SYNTHETIC CU02 User', login_id='SYNTHETIC_ACCOUNT')
        reply = valid_reply if auth_reply is DEFAULT_AUTH_REPLY else auth_reply

        class AuthResponse:
            status = auth_status

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, size=-1):
                raw = reply if isinstance(reply, bytes) else json.dumps(reply).encode('utf-8')
                return raw if size < 0 else raw[:size]

            def geturl(self):
                return auth_url or cu02.TARGET_ORIGIN + '/api/auth/login'

            def getcode(self):
                return self.status

        def authenticate(request, *args, **kwargs):
            self.assertEqual(driver.created, 0, 'Authentication must precede browser creation')
            self.assertEqual(request.full_url, cu02.TARGET_ORIGIN + '/api/auth/login')
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(kwargs.get('timeout'), 30)
            sent = json.loads(request.data)
            self.assertEqual(sent, dict(loginId=SYNTHETIC_LOGIN['KTL_M04_RBEM_USERNAME'],
                                        password=SYNTHETIC_LOGIN['KTL_M04_RBEM_PASSWORD']))
            driver.auth_requests.append(dict(url=request.full_url, method=request.get_method()))
            driver.actions.append('authenticate')
            if auth_error is not None:
                raise auth_error
            return AuthResponse()

        def create_driver(**kwargs):
            driver.created += 1
            driver.actions.append('create-browser')
            if not driver.auth_requests:
                raise AssertionError('Browser creation must follow authentication')
            return driver

        def no_redirect_opener(*handlers):
            self.assertEqual(len(handlers), 1)
            self.assertIsInstance(handlers[0], urllib.request.HTTPRedirectHandler)
            redirected = handlers[0].redirect_request(urllib.request.Request(cu02.TARGET_ORIGIN + '/api/auth/login'),
                                                       None, 302, 'SYNTHETIC redirect', {}, 'https://example.invalid/redirect')
            self.assertIsNone(redirected, 'Credentials must never follow an authentication redirect')
            return types.SimpleNamespace(open=authenticate)

        class Wait:
            def __init__(self, actual_driver, timeout):
                if actual_driver is not driver:
                    raise AssertionError('Unexpected synthetic driver')

            def until(self, predicate):
                for _ in range(8):
                    result = predicate(driver)
                    if result:
                        return result
                    driver.false_polls += 1
                raise TimeoutError('Synthetic condition never became true')

        class Options:
            def add_argument(self, value):
                pass

        @contextmanager
        def business_step(order):
            driver.steps.append(order)
            yield

        def capture_evidence(phase):
            driver.checkpoints.append(dict(phase=phase, step_order=driver.steps[-1],
                                           modal=driver.modal, fields=deepcopy(driver.values),
                                           saved=deepcopy(driver.saved), edit_reads=deepcopy(driver.edit_reads),
                                           action_count=len(driver.actions)))

        modules = {}
        for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.common', 'selenium.webdriver.support',
                     'selenium.webdriver.common.by', 'selenium.webdriver.common.keys', 'selenium.webdriver.support.ui', 'ktl_runtime'):
            modules[name] = types.ModuleType(name)
            modules[name].__path__ = []
        webdriver = modules['selenium.webdriver']
        webdriver.EdgeOptions = webdriver.ChromeOptions = Options
        webdriver.Edge = webdriver.Chrome = create_driver
        modules['selenium'].webdriver = webdriver
        modules['selenium.webdriver.common.by'].By = types.SimpleNamespace(CSS_SELECTOR='css selector')
        modules['selenium.webdriver.common.keys'].Keys = Keys
        modules['selenium.webdriver.support.ui'].WebDriverWait = Wait
        modules['ktl_runtime'].business_step = business_step
        modules['ktl_runtime'].capture_evidence = capture_evidence
        failure = None
        output = io.StringIO()
        namespace = {'__name__': '__synthetic_cu02__'}
        with redirect_stdout(output), patch.dict(sys.modules, modules), patch.dict(os.environ, SYNTHETIC_LOGIN if login_environment is None else login_environment), \
                patch('subprocess.Popen', side_effect=AssertionError('No real process in hydration regression')), \
                patch('socket.create_connection', side_effect=AssertionError('No real network in hydration regression')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('Only the synthetic no-redirect opener may authenticate')), \
                patch('urllib.request.build_opener', side_effect=no_redirect_opener):
            try:
                exec(compile(tree, '<synthetic-cu02-hydration>', 'exec'), namespace)
            except (AssertionError, TimeoutError, RuntimeError) as exc:
                failure = exc
        driver.output = output.getvalue()
        driver.runtime_session = namespace.get('session')
        return driver, failure

    def test_all_five_steps_wait_for_edit_hydration_after_one_registration_and_reload(self):
        driver, failure = self.run_script()
        self.assertIsNone(failure)
        self.assertEqual(driver.steps, [1, 2, 3, 4, 5])
        self.assertEqual(driver.edit_reads, {'title': 2, 'description': 2})
        self.assertGreaterEqual(driver.false_polls, 2)
        self.assertEqual(driver.async_lookups, 1)
        self.assertEqual(driver.actions, ['authenticate', 'create-browser', 'bootstrap-auth', 'get-schedule', 'remove-bootstrap', 'check-existing', 'date-number',
                                         'input-title', 'input-description', 'create-submit', 'refresh',
                                         'saved-event', 'close', 'quit'])
        self.assertEqual(driver.saved, {key: inputs()[key] for key in ('title', 'description')})

    def test_prefilled_new_form_fails_before_any_field_is_cleared_or_submitted(self):
        for field in ('title', 'description'):
            with self.subTest(field=field):
                driver, failure = self.run_script(initial_values={field: 'SYNTHETIC unexpected existing value'})
                self.assertIsInstance(failure, AssertionError)
                self.assertEqual(driver.steps, [1, 2])
                self.assertEqual(driver.field_writes, 0)
                self.assertIsNone(driver.saved)
                self.assertEqual(driver.checkpoints, [])
                self.assertNotIn('create-submit', driver.actions)
                self.assertEqual(driver.actions[-1], 'quit')

    def test_screenshot_hooks_follow_empty_form_and_reloaded_values_before_modal_exit(self):
        driver, failure = self.run_script()
        self.assertIsNone(failure)
        before, after = driver.checkpoints
        self.assertEqual((before['phase'], before['step_order'], before['modal']), ('before', 2, 'create'))
        self.assertEqual(before['fields'], {'title': '', 'description': ''})
        self.assertIsNone(before['saved'])
        self.assertEqual(driver.actions[before['action_count'] - 1], 'date-number')
        self.assertEqual((after['phase'], after['step_order'], after['modal']), ('after', 5, 'edit'))
        self.assertEqual(after['saved'], {key: inputs()[key] for key in ('title', 'description')})
        self.assertEqual(after['edit_reads'], {'title': 2, 'description': 2})
        self.assertEqual(driver.actions[after['action_count'] - 1], 'saved-event')
        self.assertEqual(driver.actions[after['action_count']], 'close')

    def test_authentication_precedes_browser_creation_and_bootstraps_only_the_initial_schedule_document(self):
        driver, failure = self.run_script()
        self.assertIsNone(failure)
        self.assertEqual(driver.created, 1)
        self.assertEqual(driver.auth_requests, [dict(url=cu02.TARGET_ORIGIN + '/api/auth/login', method='POST')])
        self.assertEqual([command for command, _ in driver.cdp_commands],
                         ['Page.addScriptToEvaluateOnNewDocument', 'Page.removeScriptToEvaluateOnNewDocument'])
        bootstrap = driver.cdp_commands[0][1]['source']
        self.assertIn(SYNTHETIC_TOKEN, bootstrap)
        self.assertIn('localStorage', bootstrap)
        self.assertIn(cu02.TARGET_ORIGIN, bootstrap)
        self.assertIn('location.origin', bootstrap)
        self.assertIn('window.top', bootstrap)
        self.assertEqual(driver.runtime_session, {})
        source = cu02.prepare(inputs())['code']
        for sensitive in [SYNTHETIC_TOKEN, *SYNTHETIC_LOGIN.values()]:
            self.assertNotIn(sensitive, source)
            self.assertNotIn(sensitive, repr(driver.actions))
            self.assertNotIn(sensitive, repr(driver.auth_requests))
            self.assertNotIn(sensitive, driver.output)
        self.assertNotIn('get-login', driver.actions)
        self.assertNotIn('login-submit', driver.actions)

    def test_only_success_and_token_are_required_and_unneeded_profile_data_never_enters_the_browser(self):
        for reply in [dict(success=True, token=SYNTHETIC_TOKEN),
                      dict(success=True, token=SYNTHETIC_TOKEN, role=None,
                           name='SYNTHETIC_UNNEEDED_PROFILE_ONLY', login_id=123)]:
            with self.subTest(fields=list(reply)):
                driver, failure = self.run_script(auth_reply=reply)
                self.assertIsNone(failure)
                bootstrap = driver.cdp_commands[0][1]['source']
                self.assertIn(SYNTHETIC_TOKEN, bootstrap)
                self.assertNotIn('SYNTHETIC_UNNEEDED_PROFILE_ONLY', bootstrap)
                self.assertNotIn('login_id', bootstrap)
                self.assertEqual(driver.runtime_session, {})

    def test_runtime_session_bootstrap_writes_token_only_on_the_exact_origin_top_frame(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is unavailable for the isolated JavaScript bootstrap regression')
        driver, failure = self.run_script()
        self.assertIsNone(failure)
        script = driver.cdp_commands[0][1]['source']
        javascript = r'''
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const scenarios=[
  {origin:input.origin,child:false},
  {origin:input.origin,child:true},
  {origin:'https://example.invalid',child:false},
  {origin:input.origin+'.example.invalid',child:false},
  {origin:input.origin.replace('https:','http:'),child:false},
  {origin:input.origin+':8443',child:false},
  {origin:'https://example.invalid',child:true}
];
const results=scenarios.map(({origin,child})=>{
  const writes=[],top={};top.top=top;
  const window=child?{top}:top;
  vm.runInNewContext(input.source,{window,location:{origin},localStorage:{
    setItem(key,value){writes.push({key,value});}
  }},{timeout:1000});
  return {count:writes.length,tokenOnly:writes.every(row=>row.key==='token'&&row.value===input.token)};
});
process.stdout.write(JSON.stringify(results));
'''
        completed = subprocess.run([node, '-e', javascript],
            input=json.dumps(dict(source=script, origin=cu02.TARGET_ORIGIN, token=SYNTHETIC_TOKEN)),
            capture_output=True, text=True, encoding='utf-8', timeout=10, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        results = json.loads(completed.stdout)
        self.assertEqual([row['count'] for row in results], [1, 0, 0, 0, 0, 0, 0])
        self.assertTrue(all(row['tokenOnly'] for row in results))

    def test_failed_malformed_or_oversized_authentication_never_creates_a_browser(self):
        base = dict(success=True, token=SYNTHETIC_TOKEN, role='USER', name='SYNTHETIC', login_id='SYNTHETIC')
        replies = [None, [], {}, dict(base, success=False), dict(base, success=1),
                   dict(base, token=''), dict(base, token=123), dict(base, token='x' * 16385),
                   dict(base, token=' ' + SYNTHETIC_TOKEN), dict(base, token=SYNTHETIC_TOKEN + '\nextra'),
                   b'SYNTHETIC INVALID JSON', b'{' + b' ' * 70000 + b'}']
        for reply in replies:
            with self.subTest(reply_type=type(reply).__name__):
                driver, failure = self.run_script(auth_reply=reply)
                self.assertIsInstance(failure, RuntimeError)
                self.assertEqual(driver.created, 0)
                self.assertEqual(driver.steps, [])
                self.assertEqual(driver.cdp_commands, [])
                self.assertEqual(driver.actions, ['authenticate'])
                for sensitive in [SYNTHETIC_TOKEN, *SYNTHETIC_LOGIN.values()]:
                    self.assertNotIn(sensitive, str(failure))

    def test_unsuccessful_http_redirect_and_transport_fail_before_browser_creation_without_secret_errors(self):
        variants = [dict(auth_status=401), dict(auth_status=302), dict(auth_status=True),
                    dict(auth_url='https://example.invalid/redirected-login'),
                    dict(auth_error=urllib.error.HTTPError(cu02.TARGET_ORIGIN + '/api/auth/login', 401,
                                                           SYNTHETIC_TOKEN, {}, None)),
                    dict(auth_error=urllib.error.URLError(SYNTHETIC_TOKEN))]
        for variant in variants:
            with self.subTest(fields=list(variant)):
                driver, failure = self.run_script(**variant)
                self.assertIsInstance(failure, RuntimeError)
                self.assertEqual(driver.created, 0)
                self.assertEqual(driver.cdp_commands, [])
                self.assertEqual(driver.steps, [])
                self.assertNotIn(SYNTHETIC_TOKEN, str(failure))

    def test_missing_login_configuration_does_not_authenticate_or_open_a_browser(self):
        for missing in SYNTHETIC_LOGIN:
            environment = dict(SYNTHETIC_LOGIN, **{missing: ''})
            with self.subTest(field=missing):
                driver, failure = self.run_script(login_environment=environment)
                self.assertIsInstance(failure, RuntimeError)
                self.assertEqual(driver.created, 0)
                self.assertEqual(driver.auth_requests, [])
                self.assertEqual(driver.actions, [])

    def test_session_bootstrap_failure_closes_browser_before_any_visible_navigation(self):
        variants = [dict(cdp_error=RuntimeError(SYNTHETIC_TOKEN)), dict(bootstrap_reply={}),
                    dict(bootstrap_reply={'identifier': ''}), dict(bootstrap_reply={'identifier': 123})]
        for variant in variants:
            with self.subTest(fields=list(variant)):
                driver, failure = self.run_script(**variant)
                self.assertIsInstance(failure, RuntimeError)
                self.assertEqual(driver.created, 1)
                self.assertEqual(driver.steps, [])
                self.assertEqual(driver.current_url, '')
                self.assertEqual(driver.actions[-1], 'quit')
                self.assertNotIn(SYNTHETIC_TOKEN, str(failure))

    def test_failed_bootstrap_cleanup_stops_before_registration_without_exposing_cdp_data(self):
        driver, failure = self.run_script(remove_error=RuntimeError(SYNTHETIC_TOKEN))
        self.assertIsInstance(failure, RuntimeError)
        self.assertEqual(driver.created, 1)
        self.assertEqual(driver.steps, [1])
        self.assertEqual(driver.current_url, cu02.TARGET_URL)
        self.assertIsNone(driver.saved)
        self.assertNotIn('check-existing', driver.actions)
        self.assertNotIn('create-submit', driver.actions)
        self.assertEqual(driver.actions[-1], 'quit')
        self.assertEqual(driver.runtime_session, {})
        self.assertNotIn(SYNTHETIC_TOKEN, str(failure))
        self.assertNotIn(SYNTHETIC_TOKEN, driver.output)

    def test_former_immediate_title_or_description_read_fails_on_the_same_delayed_modal(self):
        for field in ('title', 'description'):
            with self.subTest(field=field):
                driver, failure = self.run_script(immediate_field=field)
                self.assertIsInstance(failure, AssertionError)
                self.assertEqual(driver.edit_reads[field], 1)
                self.assertEqual(driver.actions.count('create-submit'), 1)
                self.assertEqual(driver.actions.count('refresh'), 1)
                self.assertNotIn('close', driver.actions)
                self.assertEqual(driver.actions[-1], 'quit')

    def test_wrong_saved_title_or_description_never_passes_even_after_repeated_polls(self):
        for field in ('title', 'description'):
            with self.subTest(field=field):
                driver, failure = self.run_script(wrong_field=field)
                self.assertIsInstance(failure, TimeoutError)
                self.assertEqual(driver.edit_reads[field], 8)
                self.assertEqual(driver.actions.count('create-submit'), 1)
                self.assertNotIn('close', driver.actions)
                self.assertEqual(driver.actions[-1], 'quit')

    def test_duplicate_in_readonly_response_blocks_creation_even_when_calendar_dom_is_empty(self):
        driver, failure = self.run_script(lookup_reply={'ok': True, 'count': 1})
        self.assertIsInstance(failure, AssertionError)
        self.assertEqual(driver.steps, [1])
        self.assertEqual(driver.async_lookups, 1)
        self.assertIsNone(driver.saved)
        self.assertEqual(driver.actions, ['authenticate', 'create-browser', 'bootstrap-auth', 'get-schedule', 'remove-bootstrap', 'check-existing', 'quit'])

    def test_failed_or_malformed_readonly_lookup_never_becomes_an_empty_calendar_success(self):
        replies = [{'ok': False}, {'ok': True}, {'ok': True, 'count': True},
                   {'ok': True, 'count': 0.0}, {'ok': True, 'count': '0'},
                   {'ok': 1, 'count': 0}, [], 'SYNTHETIC_INVALID_RESPONSE']
        for reply in replies:
            with self.subTest(reply_type=type(reply).__name__):
                driver, failure = self.run_script(lookup_reply=reply)
                self.assertIsInstance(failure, RuntimeError)
                self.assertEqual(driver.steps, [1])
                self.assertEqual(driver.async_lookups, 1)
                self.assertIsNone(driver.saved)
                self.assertEqual(driver.actions, ['authenticate', 'create-browser', 'bootstrap-auth', 'get-schedule', 'remove-bootstrap', 'check-existing', 'quit'])


class CU02FixedScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-cu02-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.enterContext(patch.dict(os.environ, SYNTHETIC_LOGIN))
        self.enterContext(patch('backend.m04.cu02.default_browser', return_value='edge'))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No subprocess in synthetic CU02 regression')))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No site in synthetic CU02 regression')))
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP/provider in synthetic CU02 regression')))
        self.config = dict(targets={'M04': 90}, m04={}, m07={}, integration_datasets={})
        self.session = RuntimeSession()
        self.manager = M04Manager(self.root, lambda: self.config, session=self.session)

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): sha(path.read_bytes())
                for path in self.root.rglob('*') if path.is_file()}

    def register(self):
        return self.manager.prepare_cu02(inputs())['script']

    def test_workflow_read_is_readonly_and_does_not_disclose_credentials(self):
        before = self.snapshot()
        workflow = self.manager.cu02()
        self.assertEqual(workflow['workflow_id'], 'CU02')
        self.assertTrue(workflow['login_configured'])
        self.assertEqual(workflow['defaults']['browser'], 'edge')
        self.assertEqual(workflow['run_mode'], 'DEVELOPMENT')
        for secret in SYNTHETIC_LOGIN.values():
            self.assertNotIn(secret, json.dumps(workflow))
        self.assertEqual(self.snapshot(), before)

    def test_missing_login_refuses_preparation_without_writing_scripts(self):
        before = self.snapshot()
        with patch.dict(os.environ, {key: '' for key in SYNTHETIC_LOGIN}):
            self.assertFalse(self.manager.cu02()['login_configured'])
            with self.assertRaises(EvaluationError) as failure:
                self.manager.prepare_cu02(inputs())
        self.assertEqual(failure.exception.status, 'NOT_CONFIGURED')
        self.assertEqual(self.snapshot(), before)

    def test_registration_pins_original_sources_and_is_not_execution_or_m03_generation(self):
        expected = cu02.prepare(inputs())
        with patch.object(self.manager, 'create', side_effect=AssertionError('Preparation cannot start execution')):
            metadata = self.register()
        self.assertEqual(metadata['source_kind'], 'CU02_SCHEDULE_REGISTRATION')
        self.assertEqual(metadata['workflow_id'], 'CU02')
        self.assertEqual(metadata['browser'], 'edge')
        self.assertFalse(metadata['generated_by_llm'])
        self.assertIsNone(metadata['source_m03_run_id'])
        self.assertTrue(metadata['business_step_required'])
        stored, raw = self.manager._script(metadata['script_id'])
        self.assertEqual(raw, expected['code'].encode('utf-8'))
        self.assertEqual(stored['sha256'], sha(raw))
        folder = self.manager.script_directory / metadata['script_id']
        for name, original in expected['source_files'].items():
            self.assertEqual((folder / name).read_bytes(), original)
            self.assertEqual(stored['source_cu02_files'][name], sha(original))
        self.assertEqual(json.loads((folder / 'source_scenario.json').read_bytes()), expected['scenario'])
        fixed = self.manager._fixed_execution(stored, folder)
        self.assertEqual(fixed['contract'], expected['contract'])
        self.assertEqual(fixed['scenario'], expected['scenario'])
        self.assertEqual(self.manager.list_runs()['executions'], [])
        self.assertEqual(list((self.root / 'results/development').glob('DEV-M03-*')), [])
        self.assertFalse((self.root / 'results/development/latest-M04.json').exists())
        for path in folder.iterdir():
            if path.is_file():
                for secret in SYNTHETIC_LOGIN.values():
                    self.assertNotIn(secret.encode(), path.read_bytes())

    def test_foreign_server_session_cannot_read_or_execute_the_fixed_script(self):
        metadata = self.register()
        foreign = M04Manager(self.root, lambda: self.config, session=RuntimeSession())
        with self.assertRaises(EvaluationError) as failure:
            foreign._script(metadata['script_id'])
        self.assertEqual(failure.exception.status, 'SESSION_EXPIRED')
        self.assertEqual(foreign.scripts()['scripts'], [])

    def test_changed_fixed_source_or_definition_is_rejected_before_execution(self):
        for filename in ('script.py', 'cu02_parameters.json', 'cu02_definition.json', 'execution_contract.json'):
            with self.subTest(filename=filename):
                metadata = self.register()
                path = self.manager.script_directory / metadata['script_id'] / filename
                path.write_bytes(path.read_bytes() + b'\n')
                with self.assertRaises(EvaluationError):
                    self.manager._script(metadata['script_id'])

    def test_explicit_execution_snapshots_all_cu02_sources_into_archive_without_running(self):
        metadata = self.register()
        script_folder = self.manager.script_directory / metadata['script_id']
        expected = {name: (script_folder / name).read_bytes() for name in
                    ('script.py', 'source_scenario.json', 'execution_contract.json', 'cu02_definition.json', 'cu02_parameters.json')}
        starts = []

        def no_execution(execution_id, lock):
            starts.append(execution_id)
            lock.close()

        class ImmediateThread:
            def __init__(self, *, target, args, **kwargs):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch.object(self.manager, '_execute', side_effect=no_execution), \
                patch('backend.m04.store.threading.Thread', ImmediateThread):
            job = self.manager.create(dict(script_ids=[metadata['script_id']], visible_browser=True,
                                          action_delay_ms=100, keep_open_seconds=1))['execution']
        self.assertEqual(starts, [job['execution_id']])
        self.assertIsNone(job['result'])
        self.assertEqual(job['counts']['total_execution_count'], 1)
        case = job['cases'][0]
        self.assertEqual(case['source_kind'], 'CU02_SCHEDULE_REGISTRATION')
        self.assertEqual(case['source_cu02_files'], metadata['source_cu02_files'])
        folder = self.manager.execution_directory / job['execution_id'] / 'CASE-001'
        archive = self.root / 'data/evaluation' / job['dataset_id'] / 'scripts.zip'
        with zipfile.ZipFile(archive) as saved:
            for name, original in expected.items():
                self.assertEqual((folder / name).read_bytes(), original)
                self.assertEqual(saved.read('CASE-001/' + name), original)
        (folder / 'cu02_parameters.json').write_bytes(expected['cu02_parameters.json'] + b'\n')
        with self.assertRaises(EvaluationError):
            self.manager._provenance(job)


if __name__ == '__main__':
    unittest.main()
