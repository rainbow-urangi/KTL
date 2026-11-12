"""Synthetic checkpoint/capture tests; never launch a browser or contact a service."""
import base64
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from backend.m04 import runner


PNG = b'\x89PNG\r\n\x1a\nSYNTHETIC_MASKED_IMAGE'


class ScreenshotCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.script = Path(self.directory.name) / 'synthetic.py'
        self.script.write_text('assert True\n', encoding='utf-8')
        self.output = io.StringIO()

    def observer(self, checkpoints=None):
        scenario = dict(steps=[dict(order=order) for order in range(1, 6)])
        if checkpoints is not None:
            scenario['screenshot_checkpoints'] = checkpoints
        return runner.Observer(self.script, self.output, scenario)

    def connect(self, observer, failure=None):
        calls = []
        driver = types.SimpleNamespace(state='INITIAL_BROWSER')

        def execute(current, name, params=None):
            params = params or {}
            calls.append((current.state, name, params))
            if name == 'executeCdpCommand':
                if params['cmd'] == 'DOM.getDocument':
                    node = {'nodeName': 'HTML', 'children': []}
                    if failure == 'shadow':
                        node['shadowRoots'] = [dict(shadowRootType='closed')]
                    return {'value': {'root': node}}
                return {'value': {}}
            if name == 'w3cExecuteScript':
                mode = params['args'][1]
                if failure == mode:
                    return {'value': {'ok': False, 'reason': 'synthetic_mask_failure'}}
                return {'value': {'ok': True}}
            if name == 'screenshot':
                return {'value': base64.b64encode(PNG).decode('ascii')}
            raise AssertionError('Unexpected synthetic command: ' + name)

        observer.drivers.append(driver)
        observer.raw_execute = execute
        return driver, calls

    def test_explicit_hooks_capture_empty_and_reloaded_forms_in_declared_steps(self):
        observer = self.observer({'before': 2, 'after': 5})
        driver, calls = self.connect(observer)
        observer.capture_screen('before', driver)
        self.assertEqual(observer.screenshots, {})
        observer.current_step = dict(sequence=2)
        driver.state = 'EMPTY_REGISTRATION_FORM'
        observer.capture_evidence('before')
        observer.current_step = dict(sequence=5)
        driver.state = 'RELOADED_PERSISTED_FORM'
        observer.capture_evidence('after')
        rows = observer.screenshot_result()
        self.assertEqual([row['status'] for row in rows], ['CAPTURED', 'CAPTURED'])
        self.assertEqual([row['business_step_order'] for row in rows], [2, 5])
        self.assertTrue(all(row['policy'] == runner.SCREENSHOT_POLICY for row in rows))
        self.assertTrue(all(row['capture_mode'] == 'EXPLICIT_BUSINESS_CHECKPOINT' for row in rows))
        self.assertEqual([state for state, name, _ in calls if name == 'screenshot'],
                         ['EMPTY_REGISTRATION_FORM', 'RELOADED_PERSISTED_FORM'])
        for row in rows:
            self.assertEqual((self.script.parent / row['file']).read_bytes(), PNG)

    def test_missing_checkpoint_cannot_fall_back_to_unrelated_browser_state(self):
        observer = self.observer({'before': 2, 'after': 5})
        driver, calls = self.connect(observer)
        observer.capture_screen('before', driver)
        driver.state = 'ERROR_OR_CLOSED_MODAL'
        observer.capture_screen('after', driver)
        rows = observer.screenshot_result()
        self.assertEqual([row['status'] for row in rows], ['NOT_CAPTURED', 'NOT_CAPTURED'])
        self.assertTrue(all(row['reason'] == 'checkpoint_not_reached' for row in rows))
        self.assertFalse(calls)
        self.assertFalse(list(self.script.parent.glob('*.png')))

    def test_hook_rejects_undeclared_or_incorrect_business_step(self):
        observer = self.observer({'before': 2, 'after': 5})
        _, calls = self.connect(observer)
        for step, phase in ((None, 'before'), (1, 'before'), (2, 'after'), (5, 'unknown')):
            observer.current_step = None if step is None else dict(sequence=step)
            with self.subTest(step=step, phase=phase), self.assertRaises(RuntimeError):
                observer.capture_evidence(phase)
        generic = self.observer()
        generic.current_step = dict(sequence=2)
        with self.assertRaises(RuntimeError):
            generic.capture_evidence('before')
        self.assertFalse(calls)

    def test_checkpoint_schema_is_bounded_and_exact_before_browser_execution(self):
        for points in ({}, {'before': 0, 'after': 5}, {'before': True, 'after': 5},
                       {'before': 2, 'after': 6}, {'before': 5, 'after': 2},
                       {'before': 2, 'after': 5, 'extra': 1}, [2, 5]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                self.observer(points)

    def test_mask_or_shadow_verification_failure_never_stores_a_capture(self):
        for failure in ('apply', 'check', 'remove', 'shadow'):
            with self.subTest(failure=failure):
                observer = self.observer({'before': 2, 'after': 5})
                _, calls = self.connect(observer, failure)
                observer.current_step = dict(sequence=2)
                observer.capture_evidence('before')
                row = observer.screenshots['before']
                self.assertEqual(row['status'], 'NOT_CAPTURED')
                self.assertIsNone(row['file'])
                self.assertIsNone(row['sha256'])
                self.assertFalse((self.script.parent / 'before.png').exists())
                if failure in {'apply', 'shadow'}:
                    self.assertFalse(any(name == 'screenshot' for _, name, _ in calls))

    def test_default_capture_behavior_remains_automatic_and_first_capture_is_preserved(self):
        observer = self.observer()
        driver, calls = self.connect(observer)
        observer.capture_screen('before', driver)
        driver.state = 'LATER_STATE'
        observer.capture_screen('before', driver)
        observer.capture_screen('after', driver)
        rows = observer.screenshot_result()
        self.assertEqual([state for state, name, _ in calls if name == 'screenshot'],
                         ['INITIAL_BROWSER', 'LATER_STATE'])
        self.assertTrue(all(row['status'] == 'CAPTURED' for row in rows))
        self.assertTrue(all('capture_mode' not in row for row in rows))

    def test_runtime_exposes_checkpoint_hook_without_changing_success_checks(self):
        observer = self.observer()
        _, calls = self.connect(observer)
        raw_execute = observer.raw_execute

        class WebDriver:
            def __init__(self):
                self.state = 'INITIAL_BROWSER'
                self.start_session({})

            def start_session(self, capabilities):
                self.capabilities = {'browserVersion': 'SYNTHETIC'}

            def execute(self, name, params=None):
                if name in {'executeCdpCommand', 'w3cExecuteScript', 'screenshot'}:
                    return raw_execute(self, name, params)
                if name == 'getTitle':
                    return {'value': 'SYNTHETIC'}
                return {'value': None}

            def get(self, url):
                self.state = 'DECLARED_FORM'
                self.execute('get', {'url': url})

            @property
            def title(self):
                return self.execute('getTitle')['value']

            def quit(self):
                self.execute('quit')

        modules = {}
        for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.remote'):
            modules[name] = types.ModuleType(name)
            modules[name].__path__ = []
        modules['selenium.webdriver.remote.webdriver'] = types.ModuleType('selenium.webdriver.remote.webdriver')
        modules['selenium.webdriver.remote.webdriver'].WebDriver = WebDriver
        source = ("from selenium.webdriver.remote.webdriver import WebDriver\n"
                  "from ktl_runtime import business_step, capture_evidence\n"
                  "driver = WebDriver()\nwith business_step(1):\n"
                  "    driver.get('https://synthetic.invalid/form')\n"
                  "    assert driver.title == 'SYNTHETIC'\n"
                  "    capture_evidence('before')\n"
                  "    capture_evidence('after')\n"
                  "driver.quit()\n")
        self.script.write_text(source, encoding='utf-8')
        scenario = dict(scenario_id='SYNTHETIC-CHECKPOINT', screenshot_checkpoints=dict(before=1, after=1),
                        steps=[dict(order=1, action='open', target='https://synthetic.invalid/form',
                                    expected_result='Synthetic form is open')])
        with patch.dict(sys.modules, modules), patch.object(runner, 'load_login_settings', return_value={}), \
                contextlib.redirect_stdout(self.output):
            code = runner.execute(self.script, scenario)
        events = [json.loads(line) for line in self.output.getvalue().splitlines()]
        terminal = events[-1]
        self.assertEqual(code, 0)
        self.assertEqual(terminal['status'], 'PASS')
        self.assertTrue(terminal['browser_started'])
        self.assertTrue(terminal['business_step_complete'])
        self.assertEqual([row['status'] for row in terminal['screenshots']], ['CAPTURED', 'CAPTURED'])
        self.assertEqual([state for state, name, _ in calls if name == 'screenshot'],
                         ['DECLARED_FORM', 'DECLARED_FORM'])


if __name__ == '__main__':
    unittest.main()
