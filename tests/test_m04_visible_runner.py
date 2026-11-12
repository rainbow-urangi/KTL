"""Synthetic driver tests only: no browser, network, credentials or real business execution."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from backend.m04 import runner


class VisibleRunnerTests(unittest.TestCase):
    def driver(self, capabilities=None, *, remote=False, alive=True):
        process = types.SimpleNamespace(poll=lambda: None if alive else 1)
        return types.SimpleNamespace(service=None if remote else types.SimpleNamespace(
            service_url='http://127.0.0.1:55555', process=process),
            command_executor=types.SimpleNamespace(_client_config=types.SimpleNamespace(
                remote_server_addr='http://127.0.0.1:55555')))

    def test_chrome_capabilities_remove_only_headless_without_mutating_fixed_options(self):
        source = dict(browserName='chrome', **{'goog:chromeOptions': dict(
            args=['--headless', '--headless=new', 'headless', '--window-size=1440,1100', '--lang=ko'],
            prefs={'synthetic': True}), 'goog:loggingPrefs': {'browser': 'ALL'}})
        original = deepcopy(source)
        result = runner._visible_capabilities(self.driver(), source)
        self.assertEqual(source, original)
        self.assertEqual(result['goog:chromeOptions']['args'], ['--window-size=1440,1100', '--lang=ko'])
        self.assertEqual(result['goog:chromeOptions']['prefs'], original['goog:chromeOptions']['prefs'])
        result['goog:chromeOptions']['prefs']['synthetic'] = False
        self.assertEqual(source, original)

    def test_local_edge_supported_with_its_own_options_namespace(self):
        source = {'browserName': 'MicrosoftEdge', 'ms:edgeOptions': {'args': ['--headless=new', '--inprivate']}}
        result = runner._visible_capabilities(self.driver(), source)
        self.assertEqual(result['ms:edgeOptions']['args'], ['--inprivate'])
        self.assertEqual(source['ms:edgeOptions']['args'][0], '--headless=new')

    def test_remote_grid_without_a_local_service_and_stopped_service_are_rejected(self):
        for driver in (self.driver(remote=True), self.driver(alive=False)):
            with self.subTest(driver=driver), self.assertRaisesRegex(ValueError, 'local Chrome or Edge'):
                runner._visible_capabilities(driver, {'browserName': 'chrome'})

    def test_nonlocal_mismatched_or_credentialed_executor_is_rejected(self):
        for url in ('https://example.invalid', 'http://127.0.0.1:44444',
                    'http://secret@127.0.0.1:55555', 'http://127.0.0.1:55555/?private=1'):
            driver = self.driver()
            driver.command_executor._client_config.remote_server_addr = url
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'local Chrome or Edge'):
                runner._visible_capabilities(driver, {'browserName': 'chrome'})

    def test_invalid_browser_or_options_do_not_silently_claim_visibility(self):
        for value in ({'browserName': 'firefox'}, {'browserName': 'chrome', 'goog:chromeOptions': []},
                      {'browserName': 'chrome', 'goog:chromeOptions': {'args': '--headless'}},
                      {'browserName': 'chrome', 'goog:chromeOptions': {'args': [123]}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner._visible_capabilities(self.driver(), value)

    def test_presentation_values_are_bounded_exact_types_and_require_visible_mode(self):
        runner._presentation_options(False, 0, 0)
        runner._presentation_options(True, 2000, 60)
        for values in ((1, 0, 0), (True, True, 0), (True, -1, 0), (True, 2001, 0),
                       (True, 1.5, 0), (True, 0, True), (True, 0, 61), (False, 1, 0), (False, 0, 1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                runner._presentation_options(*values)

    def execute_fake(self, *, visible=True, body=None, quit_in_script=True, strict=False, fail_hold=False):
        calls, sleeps, sessions = [], [], []
        original_caps = {'browserName': 'chrome', 'goog:chromeOptions': {'args': ['--headless=new', '--window-size=1440,1100']}}
        outer = self

        class WebDriver:
            def __init__(self):
                local = outer.driver()
                self.service, self.command_executor = local.service, local.command_executor
                self.start_session(original_caps)

            def start_session(self, capabilities):
                sessions.append(deepcopy(capabilities))
                self.capabilities = {'browserVersion': 'SYNTHETIC'}

            def execute(self, name, params=None):
                calls.append(name)
                params = params or {}
                if name == 'getTitle':
                    return {'value': 'SYNTHETIC'}
                if name in {'findElement', 'findElements'}:
                    element = {'element-6066-11e4-a52e-4f735466cecf': params['value']}
                    return {'value': [element] if name == 'findElements' else element}
                if name == 'w3cExecuteScript':
                    if '.matches(' in params['script']:
                        return {'value': params['args'][0]['element-6066-11e4-a52e-4f735466cecf'] == params['args'][1]}
                    return {'value': True}
                if name == 'isElementDisplayed':
                    return {'value': True}
                return {'value': None}

            def get(self, url):
                return self.execute('get', {'url': url})

            def find_element(self, using, value):
                self.execute('findElement', {'using': using, 'value': value})
                return WebElement(self, value)

            @property
            def title(self):
                return self.execute('getTitle')['value']

            def quit(self):
                self.execute('quit')

        class WebElement:
            def __init__(self, parent, identity):
                self._parent, self.id = parent, identity

            def click(self):
                self._parent.execute('clickElement', {'id': self.id})

            def submit(self):
                return self._parent.execute('w3cExecuteScript', {'script': 'SYNTHETIC_STANDARD_SUBMIT', 'args': []})

        modules = {}
        for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.remote'):
            modules[name] = types.ModuleType(name)
            modules[name].__path__ = []
        modules['selenium.webdriver.remote.webdriver'] = types.ModuleType('selenium.webdriver.remote.webdriver')
        modules['selenium.webdriver.remote.webdriver'].WebDriver = WebDriver
        modules['selenium.webdriver.remote.webelement'] = types.ModuleType('selenium.webdriver.remote.webelement')
        modules['selenium.webdriver.remote.webelement'].WebElement = WebElement
        original_methods = WebDriver.start_session, WebDriver.execute, WebElement.submit
        body = body or "driver.get('http://127.0.0.1/synthetic')\nassert driver.title == 'SYNTHETIC'\n"
        if strict:
            body = 'from ktl_runtime import business_step\nwith business_step(1):\n' + ''.join('    '+line+'\n' for line in body.splitlines())
        text = 'from selenium.webdriver.remote.webdriver import WebDriver\ndriver=WebDriver()\n' + body
        if quit_in_script:
            text += 'driver.quit()\n'
        scenario = {'scenario_id': 'SYNTHETIC-VISIBLE', 'steps': [{'order': 1, 'action': 'click', 'target': '#button', 'expected_result': 'Synthetic visible outcome'}]} if strict else None
        contract = {'version': 1, 'scenario_id': scenario['scenario_id'], 'steps': [{'order': 1, 'action': 'click', 'target': {'by': 'css selector', 'value': '#button'},
            'checks': [{'kind': 'visible', 'target': {'by': 'css selector', 'value': '#outcome'}, 'expected': True}]}]} if strict else None

        def sleep(seconds):
            sleeps.append(seconds)
            if fail_hold and seconds == 15:
                raise RuntimeError('SYNTHETIC hold failure')

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'synthetic.py'
            script.write_bytes(text.encode('utf-8'))
            before = script.read_bytes()
            with patch.dict(sys.modules, modules), patch.object(runner, 'load_login_settings', return_value={}), \
                    patch.object(runner.Observer, 'capture_screen'), patch.object(runner.Observer, 'screenshot_result', return_value=[]), \
                    patch.object(runner.time, 'sleep', side_effect=sleep), contextlib.redirect_stdout(output):
                code = runner.execute(script, scenario, required=strict, contract=contract,
                    **({'visible_browser': True, 'action_delay_ms': 700, 'keep_open_seconds': 15} if visible else {}))
            self.assertEqual(script.read_bytes(), before)
        self.assertEqual((WebDriver.start_session, WebDriver.execute, WebElement.submit), original_methods)
        self.assertEqual(original_caps['goog:chromeOptions']['args'][0], '--headless=new')
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]['code_sha256'], hashlib.sha256(before).hexdigest())
        return code, events[-1], calls, sleeps, sessions

    def test_legacy_default_keeps_headless_and_has_no_added_sleep(self):
        code, terminal, calls, sleeps, sessions = self.execute_fake(visible=False)
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [])
        self.assertIn('--headless=new', sessions[0]['goog:chromeOptions']['args'])
        self.assertFalse(terminal['browser_presentation']['visible_browser'])
        self.assertIn('quit', calls)

    def test_visible_mode_paces_native_action_not_reads_and_holds_only_once(self):
        code, terminal, calls, sleeps, sessions = self.execute_fake()
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [.7, 15])
        self.assertIn('getTitle', calls)
        self.assertNotIn('--headless=new', sessions[0]['goog:chromeOptions']['args'])
        self.assertFalse(terminal['browser_presentation']['physical_visibility_verified'])

    def test_missing_script_quit_still_holds_and_cleans_up(self):
        code, _, calls, sleeps, _ = self.execute_fake(quit_in_script=False)
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [.7, 15])
        self.assertEqual(calls.count('quit'), 1)

    def test_hold_failure_cannot_skip_final_driver_cleanup(self):
        _, _, calls, sleeps, _ = self.execute_fake(quit_in_script=False, fail_hold=True)
        self.assertEqual(sleeps, [.7, 15])
        self.assertEqual(calls.count('quit'), 1)

    def test_script_failure_still_holds_and_quits_without_becoming_pass(self):
        code, terminal, calls, sleeps, _ = self.execute_fake(body="driver.get('http://127.0.0.1/synthetic')\nassert driver.title == 'WRONG'\n")
        self.assertEqual(code, 1)
        self.assertEqual(terminal['status'], 'FAIL')
        self.assertEqual(sleeps, [.7, 15])
        self.assertEqual(calls.count('quit'), 1)

    def test_public_native_submit_is_paced_but_javascript_observation_is_not(self):
        code, _, calls, sleeps, _ = self.execute_fake(body="form=driver.find_element('css selector','#form')\nform.submit()\nassert driver.title == 'SYNTHETIC'\n")
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [.7, 15])
        self.assertIn('w3cExecuteScript', calls)

    def test_business_step_and_independent_conditions_remain_required(self):
        for selector, expected in (('#button', 0), ('#wrong', 1)):
            with self.subTest(selector=selector):
                code, terminal, _, sleeps, _ = self.execute_fake(strict=True, body=
                    f"button=driver.find_element('css selector',{selector!r})\nbutton.click()\nassert driver.title == 'SYNTHETIC'\n")
                self.assertEqual(code, expected)
                self.assertEqual(terminal['business_step_complete'], expected == 0)
                self.assertEqual(sleeps, [.7, 15])
                self.assertEqual(terminal['business_steps'][0]['observed_actions'], ['click'])


if __name__ == '__main__':
    unittest.main()
