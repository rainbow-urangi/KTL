"""Synthetic checkpoint/capture tests; never launch a browser or contact a service."""
import base64
from copy import deepcopy
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

    def observer(self, checkpoints=None, *, visible_browser=False):
        scenario = dict(steps=[dict(order=order) for order in range(1, 6)])
        if checkpoints is not None:
            scenario['screenshot_checkpoints'] = checkpoints
        return runner.Observer(self.script, self.output, scenario, visible_browser=visible_browser)

    def window_capture(self, *, visible_browser=True, window_state='normal', frozen_visibility='hidden',
                       failure=None, minimize_delay=0, visible_delay=0):
        """Model only this driver's CDP window; fake time prevents real waits."""
        original_script = self.script.read_bytes()
        folder = Path(self.directory.name) / ('capture-' + str(len(list(Path(self.directory.name).glob('capture-*')))))
        folder.mkdir()
        self.script = folder / 'synthetic.py'
        self.script.write_bytes(original_script)
        observer = self.observer({'before': 2, 'after': 5}, visible_browser=visible_browser)
        driver = types.SimpleNamespace(state='DECLARED_MASKED_FORM')
        original = dict(left=-1400, top=36, width=1280, height=900, windowState=window_state)
        model = dict(bounds=deepcopy(original), visibility='visible', frozen=False, masked=False,
                     minimized_at=None, brought_at=None, clock=100.0, sleeps=[], calls=[])

        def execute(current, name, params=None):
            self.assertIs(current, driver)
            params = params or {}
            model['calls'].append((name, deepcopy(params)))
            if name == 'executeCdpCommand':
                command, values = params['cmd'], params['params']
                if command == 'DOM.getDocument':
                    return {'value': {'root': {'nodeName': 'HTML', 'children': []}}}
                if command == 'Page.setWebLifecycleState':
                    if values['state'] == 'frozen':
                        model.update(frozen=True, visibility=frozen_visibility)
                    elif failure == 'active':
                        raise RuntimeError('synthetic_active_failure')
                    else:
                        model['frozen'] = False
                    return {'value': {}}
                if command == 'Browser.getWindowForTarget':
                    if failure == 'get_window':
                        raise RuntimeError('synthetic_window_failure')
                    if model['minimized_at'] is not None and model['brought_at'] is None:
                        if failure == 'minimize_poll':
                            raise RuntimeError('synthetic_minimize_poll_failure')
                        if failure != 'minimize_timeout' and model['clock'] >= model['minimized_at'] + minimize_delay:
                            model['bounds']['windowState'] = 'minimized'
                    bounds = deepcopy(model['bounds'])
                    window_id = 71
                    if failure == 'invalid_window_id':
                        window_id = True
                    if failure == 'invalid_bounds':
                        bounds['width'] = 0
                    if model['brought_at'] is not None:
                        if failure == 'final_window_id':
                            window_id = 72
                        elif failure == 'final_geometry':
                            bounds['left'] += 1
                        elif failure == 'final_window_state':
                            bounds['windowState'] = 'minimized'
                    return {'value': dict(windowId=window_id, bounds=bounds)}
                if command == 'Browser.setWindowBounds':
                    self.assertEqual(values['windowId'], 71, 'never touch another window')
                    bounds = values['bounds']
                    state = bounds.get('windowState')
                    if state == 'minimized':
                        model['minimized_at'] = model['clock']
                        if failure == 'minimize':
                            raise RuntimeError('synthetic_minimize_failure')
                        if not minimize_delay and failure != 'minimize_timeout':
                            model['bounds']['windowState'] = state
                    elif state == 'normal':
                        if failure == 'normal':
                            raise RuntimeError('synthetic_normal_failure')
                        model['bounds']['windowState'] = state
                    elif state:
                        if failure == 'original_state':
                            raise RuntimeError('synthetic_original_state_failure')
                        model['bounds']['windowState'] = state
                    else:
                        if failure == 'geometry':
                            raise RuntimeError('synthetic_geometry_failure')
                        model['bounds'].update(bounds)
                    return {'value': {}}
                if command == 'Page.bringToFront':
                    model['brought_at'] = model['clock']
                    if failure == 'bring_front':
                        raise RuntimeError('synthetic_front_failure')
                    return {'value': {}}
                raise AssertionError('Unexpected CDP command: ' + command)
            if name == 'w3cExecuteScript':
                if params['script'] == 'return document.visibilityState;':
                    if failure == 'unknown_visibility':
                        return {'value': 'prerender'}
                    if model['brought_at'] is not None and failure != 'final_visibility' and model['clock'] >= model['brought_at'] + visible_delay:
                        model['visibility'] = 'visible'
                    return {'value': model['visibility']}
                self.assertEqual(params['script'], runner._SCREENSHOT_MASK)
                mode = params['args'][1]
                if mode == 'apply':
                    model['masked'] = True
                elif mode == 'remove':
                    if failure == 'remove':
                        return {'value': {'ok': False, 'reason': 'synthetic_mask_failure'}}
                    model['masked'] = False
                elif mode == 'check':
                    self.assertTrue(model['masked'])
                    if failure == 'check':
                        return {'value': {'ok': False, 'reason': 'synthetic_mask_failure'}}
                return {'value': {'ok': True}}
            if name == 'screenshot':
                self.assertTrue(model['frozen']);self.assertTrue(model['masked'])
                return {'value': base64.b64encode(PNG).decode('ascii')}
            raise AssertionError('Unexpected driver command: ' + name)

        def sleep(seconds):
            self.assertEqual(seconds, .05)
            model['sleeps'].append(seconds)
            model['clock'] += seconds

        observer.drivers.append(driver)
        observer.raw_execute = execute
        observer.current_step = dict(sequence=2)
        with patch.object(runner.time, 'monotonic', side_effect=lambda: model['clock']), \
                patch.object(runner.time, 'sleep', side_effect=sleep):
            observer.capture_evidence('before')
        self.assertEqual(self.script.read_bytes(), original_script)
        return observer.screenshots['before'], model, original

    @staticmethod
    def window_commands(model):
        return [(params['cmd'], params['params']) for name, params in model['calls']
                if name == 'executeCdpCommand' and (params['cmd'].startswith('Browser.') or params['cmd'] == 'Page.bringToFront')]

    def assert_no_image(self, record):
        self.assertEqual(record['status'], 'NOT_CAPTURED')
        self.assertIsNone(record['file']);self.assertIsNone(record['sha256'])
        self.assertFalse((self.script.parent / 'before.png').exists())

    def test_headed_hidden_capture_restores_own_original_state_geometry_and_mask_before_png(self):
        for state in ('normal', 'maximized', 'fullscreen'):
            with self.subTest(state=state):
                record, model, original = self.window_capture(window_state=state)
                self.assertEqual(record['status'], 'CAPTURED')
                self.assertEqual((self.script.parent / record['file']).read_bytes(), PNG)
                self.assertEqual(model['bounds'], original)
                self.assertEqual(model['visibility'], 'visible')
                self.assertFalse(model['masked']);self.assertFalse(model['frozen'])
                commands = self.window_commands(model)
                sets = [values for name, values in commands if name == 'Browser.setWindowBounds']
                geometry = {key: original[key] for key in ('left', 'top', 'width', 'height')}
                expected = [dict(windowState='minimized'), dict(windowState='normal'), geometry]
                if state != 'normal':
                    expected.append(dict(windowState=state))
                self.assertEqual(sets, [dict(windowId=71, bounds=value) for value in expected])
                self.assertEqual(sum(name == 'Page.bringToFront' for name, _ in commands), 1)
                calls = model['calls']
                active = next(i for i, (name, values) in enumerate(calls) if name == 'executeCdpCommand'
                              and values == dict(cmd='Page.setWebLifecycleState', params=dict(state='active')))
                remove = next(i for i, (name, values) in enumerate(calls) if name == 'w3cExecuteScript'
                              and values.get('args', [None])[-1] == 'remove')
                minimize = next(i for i, (name, values) in enumerate(calls) if name == 'executeCdpCommand'
                                and values.get('cmd') == 'Browser.setWindowBounds')
                self.assertLess(active, remove);self.assertLess(remove, minimize)
                self.assertEqual(model['sleeps'], [])

    def test_already_visible_headed_capture_never_cycles_or_focuses_a_window(self):
        record, model, _ = self.window_capture(frozen_visibility='visible')
        self.assertEqual(record['status'], 'CAPTURED')
        self.assertEqual(self.window_commands(model), [])
        self.assertEqual(model['sleeps'], [])

    def test_headless_capture_preserves_lifecycle_and_cleanup_without_window_or_visibility_commands(self):
        record, model, _ = self.window_capture(visible_browser=False)
        self.assertEqual(record['status'], 'CAPTURED')
        self.assertEqual(self.window_commands(model), [])
        self.assertFalse(any(name == 'w3cExecuteScript' and values['script'] == 'return document.visibilityState;'
                             for name, values in model['calls']))
        lifecycle = [values['params']['state'] for name, values in model['calls']
                     if name == 'executeCdpCommand' and values['cmd'] == 'Page.setWebLifecycleState']
        self.assertEqual(lifecycle, ['frozen', 'active'])
        self.assertFalse(model['masked']);self.assertFalse(model['frozen'])

    def test_active_failure_still_removes_mask_and_cannot_publish_a_png(self):
        record, model, _ = self.window_capture(failure='active')
        self.assert_no_image(record)
        self.assertFalse(model['masked'])
        self.assertEqual(record['reason'], 'browser_lifecycle_restore_unverified')
        self.assertTrue(any(name == 'w3cExecuteScript' and values.get('args', [None])[-1] == 'remove'
                            for name, values in model['calls']))

    def test_mask_or_visibility_restoration_failure_never_publishes_a_png(self):
        for failure in ('remove', 'get_window', 'invalid_window_id', 'invalid_bounds', 'unknown_visibility',
                        'bring_front', 'final_visibility', 'final_window_id', 'final_geometry', 'final_window_state'):
            with self.subTest(failure=failure):
                record, model, _ = self.window_capture(failure=failure)
                self.assert_no_image(record)
                self.assertEqual(record['reason'], 'mask_cleanup_unverified' if failure == 'remove'
                                 else 'visible_browser_restore_unverified')
                self.assertTrue(any(name == 'w3cExecuteScript' and values.get('args', [None])[-1] == 'remove'
                                    for name, values in model['calls']))

    def test_failed_minimize_poll_and_each_restore_command_still_attempt_all_original_restore_steps(self):
        for failure in ('minimize', 'minimize_poll', 'minimize_timeout', 'normal', 'geometry', 'original_state'):
            with self.subTest(failure=failure):
                record, model, original = self.window_capture(window_state='maximized', failure=failure)
                self.assert_no_image(record)
                self.assertFalse(model['masked'])
                sets = [values['bounds'] for name, values in self.window_commands(model)
                        if name == 'Browser.setWindowBounds']
                self.assertEqual(sets, [dict(windowState='minimized'), dict(windowState='normal'),
                                       {key: original[key] for key in ('left', 'top', 'width', 'height')},
                                       dict(windowState='maximized')])
                self.assertTrue(any(name == 'Page.bringToFront' for name, _ in self.window_commands(model)))
                self.assertLessEqual(sum(model['sleeps']), 2.051)

    def test_async_state_changes_are_polled_but_share_one_two_second_deadline(self):
        record, model, _ = self.window_capture(minimize_delay=.15, visible_delay=.15)
        self.assertEqual(record['status'], 'CAPTURED')
        self.assertGreaterEqual(sum(model['sleeps']), .3 - 1e-8)
        self.assertTrue(all(seconds == .05 for seconds in model['sleeps']))
        record, model, _ = self.window_capture(minimize_delay=.6, failure='final_visibility')
        self.assert_no_image(record)
        self.assertGreaterEqual(sum(model['sleeps']), 2 - 1e-8)
        self.assertLessEqual(sum(model['sleeps']), 2.051, 'final visibility must not get another two-second budget')

    def test_failed_mask_check_still_restores_the_headed_window_without_publishing_a_png(self):
        record, model, original = self.window_capture(failure='check')
        self.assert_no_image(record)
        self.assertEqual(model['bounds'], original)
        self.assertEqual(model['visibility'], 'visible')
        self.assertFalse(model['masked']);self.assertFalse(model['frozen'])

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
