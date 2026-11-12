"""Public Selenium submit observation with a fake driver; no browser/network execution."""
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


class SubmitObservationTests(unittest.TestCase):
    def run_fake(self, mode):
        class WebDriver:
            def __init__(self):
                self.form_present = True
                self.start_session({})

            def start_session(self, capabilities):
                self.capabilities = {'browserVersion': 'SYNTHETIC'}

            def execute(self, name, params=None):
                params = params or {}
                if name == 'findElement':
                    return {'value': {'element-6066-11e4-a52e-4f735466cecf': params['value']}}
                if name == 'getTitle':
                    return {'value': 'SYNTHETIC'}
                if name == 'w3cExecuteScript':
                    script, args = params['script'], params.get('args', [])
                    if '.matches(' in script:
                        identity = args[0]['element-6066-11e4-a52e-4f735466cecf']
                        return {'value': self.form_present and identity == args[1]}
                    if script == 'SYNTHETIC_STANDARD_SUBMIT' or script == 'ARBITRARY_SCRIPT_ONLY':
                        self.form_present = False
                    return {'value': True}
                return {'value': None}

            def find_element(self, using, value):
                self.execute('findElement', {'using': using, 'value': value})
                return WebElement(self, value)

            @property
            def title(self):
                return self.execute('getTitle')['value']

            def execute_script(self, script, *args):
                return self.execute('w3cExecuteScript', {'script': script, 'args': list(args)})['value']

            def quit(self):
                self.execute('quit')

        class WebElement:
            def __init__(self, parent, identity):
                self._parent, self.id = parent, identity

            def submit(self):
                if mode == 'failed':
                    raise RuntimeError('SYNTHETIC submit failure')
                return self._parent.execute_script('SYNTHETIC_STANDARD_SUBMIT',
                    {'element-6066-11e4-a52e-4f735466cecf': self.id})

        original_submit, original_execute, original_session = WebElement.submit, WebDriver.execute, WebDriver.start_session
        modules = {}
        for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.remote'):
            modules[name] = types.ModuleType(name)
            modules[name].__path__ = []
        modules['selenium.webdriver.remote.webdriver'] = types.ModuleType('selenium.webdriver.remote.webdriver')
        modules['selenium.webdriver.remote.webdriver'].WebDriver = WebDriver
        modules['selenium.webdriver.remote.webelement'] = types.ModuleType('selenium.webdriver.remote.webelement')
        modules['selenium.webdriver.remote.webelement'].WebElement = WebElement
        selector = '#wrong-form' if mode == 'wrong' else '#correct-form'
        body = ("driver.execute_script('ARBITRARY_SCRIPT_ONLY')" if mode == 'script_only' else
                "try:\n            form.submit()\n        except RuntimeError:\n            pass" if mode == 'failed' else 'form.submit()')
        source = ("from selenium.webdriver.remote.webdriver import WebDriver\n"
                  "from ktl_runtime import business_step\n"
                  "driver = WebDriver()\ntry:\n    with business_step(1):\n"
                  "        form = driver.find_element('css selector', " + repr(selector) + ")\n"
                  "        " + body + "\n        assert driver.title == 'SYNTHETIC'\nfinally:\n    driver.quit()\n")
        scenario = dict(scenario_id='SYNTHETIC-SUBMIT', steps=[dict(order=1, action='submit',
            target='#correct-form', expected_result='Saved state is visible')])
        contract = dict(version=1, scenario_id=scenario['scenario_id'], steps=[dict(order=1, action='submit',
            target=dict(by='css selector', value='#correct-form'),
            checks=[dict(kind='visible', target=dict(by='css selector', value='#saved'), expected=True)])])
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'synthetic.py'
            script.write_text(source, encoding='utf-8')
            with patch.dict(sys.modules, modules), patch.object(runner, 'load_login_settings', return_value={}), \
                    patch.object(runner.Observer, 'capture_screen'), \
                    patch.object(runner.Observer, 'screenshot_result', return_value=[]), contextlib.redirect_stdout(output):
                code = runner.execute(script, scenario, required=True, contract=contract)
        self.assertIs(WebElement.submit, original_submit)
        self.assertIs(WebDriver.execute, original_execute)
        self.assertIs(WebDriver.start_session, original_session)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        return code, events[-1], events

    def test_standard_submit_on_exact_form_passes_even_when_form_disappears(self):
        code, terminal, events = self.run_fake('correct')
        self.assertEqual(code, 0)
        self.assertTrue(terminal['business_step_complete'])
        self.assertTrue(terminal['independent_checks_passed'])
        self.assertIn('submit', terminal['business_steps'][0]['observed_actions'])
        self.assertTrue(any(e.get('step', {}).get('action') == 'submit'
                            and e.get('step', {}).get('status') == 'PASS' for e in events))

    def test_wrong_form_is_not_accepted_even_with_visible_outcome(self):
        code, terminal, _ = self.run_fake('wrong')
        self.assertEqual(code, 1)
        self.assertFalse(terminal['business_step_complete'])
        self.assertFalse(terminal['business_steps'][0]['independent_checks_passed'])

    def test_failed_submit_cannot_be_hidden_by_catching_exception(self):
        code, terminal, _ = self.run_fake('failed')
        self.assertEqual(code, 1)
        self.assertEqual(terminal['business_steps'][0]['status'], 'FAIL')
        self.assertNotIn('submit', terminal['business_steps'][0]['observed_actions'])

    def test_arbitrary_execute_script_is_not_a_submit(self):
        code, terminal, _ = self.run_fake('script_only')
        self.assertEqual(code, 1)
        self.assertFalse(terminal['business_step_complete'])
        self.assertNotIn('submit', terminal['business_steps'][0]['observed_actions'])


if __name__ == '__main__':
    unittest.main()
