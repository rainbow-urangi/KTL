"""합성 인증 응답과 가짜 드라이버만 사용하며 외부 통신·브라우저를 실행하지 않는다."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from backend.m04 import authenticated_chrome as authentication
from backend.m04 import runner


LOGIN = {'KTL_M04_RBEM_USERNAME': 'SYNTHETIC_ACCOUNT_ONLY',
         'KTL_M04_RBEM_PASSWORD': 'SYNTHETIC_SECRET_ONLY'}
TOKEN = 'SYNTHETIC_RUNTIME_TOKEN_ONLY'
AUTH_ERROR = '시험 계정 로그인에 실패했습니다. 계정과 연결 상태를 확인하세요.'


class Response:
    def __init__(self, value=None, *, raw=None, status=200, url=authentication.AUTH_URL):
        self.raw = raw if raw is not None else json.dumps(
            {'success': True, 'token': TOKEN} if value is None else value).encode('utf-8')
        self.status, self.url, self.closed, self.read_sizes = status, url, False, []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def geturl(self):
        return self.url

    def read(self, size):
        self.read_sizes.append(size)
        return self.raw[:size]


class Driver:
    def __init__(self, *, add_reply=None, add_error=None, session=True,
                 read_error=None, remove_error=None, quit_error=None):
        self.add_reply = {'identifier': 'SYNTHETIC_BOOTSTRAP_ID'} if add_reply is None else add_reply
        self.add_error, self.read_error = add_error, read_error
        self.remove_error, self.quit_error = remove_error, quit_error
        self.session, self.commands, self.reads, self.quits = session, [], [], 0

    def execute_cdp_cmd(self, name, values):
        self.commands.append((name, values))
        if name == 'Page.addScriptToEvaluateOnNewDocument':
            if self.add_error:
                raise self.add_error
            return self.add_reply
        if self.remove_error:
            raise self.remove_error
        return {}

    def execute_script(self, source):
        self.reads.append(source)
        if self.read_error:
            raise self.read_error
        return self.session

    def quit(self):
        self.quits += 1
        if self.quit_error:
            raise self.quit_error


class Options:
    def __init__(self):
        self.arguments = []

    def add_argument(self, value):
        self.arguments.append(value)


class AuthenticatedChromeTests(unittest.TestCase):
    def setUp(self):
        authentication._BOOTSTRAPS.clear()

    def tearDown(self):
        authentication._BOOTSTRAPS.clear()

    def fake_selenium(self, driver):
        webdriver = types.SimpleNamespace(Chrome=Mock(return_value=driver), ChromeOptions=Options,
                                          Edge=Mock(side_effect=AssertionError('Chrome only')))
        selenium = types.ModuleType('selenium')
        selenium.webdriver = webdriver
        return webdriver, patch.dict(sys.modules, {'selenium': selenium})

    def test_import_is_inert(self):
        path = Path(authentication.__file__)
        spec = importlib.util.spec_from_file_location('synthetic_inert_authentication', path)
        module = importlib.util.module_from_spec(spec)
        with patch('urllib.request.build_opener', side_effect=AssertionError('No network on import')), \
                patch('subprocess.Popen', side_effect=AssertionError('No process on import')):
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.authenticated_chrome))

    def test_missing_credentials_do_not_request_or_create_browser(self):
        for environment in ({}, {next(iter(LOGIN)): LOGIN[next(iter(LOGIN))]},
                            dict(LOGIN, KTL_M04_RBEM_USERNAME=' '),
                            dict(LOGIN, KTL_M04_RBEM_PASSWORD='')):
            with self.subTest(environment_keys=list(environment)), \
                    patch.dict(os.environ, environment, clear=True), \
                    patch.object(authentication, 'build_opener') as opener, \
                    patch('subprocess.Popen', side_effect=AssertionError('No browser')):
                with self.assertRaisesRegex(RuntimeError, '^시험 계정 연결이 필요합니다.$'):
                    authentication.authenticated_chrome()
                opener.assert_not_called()

    def test_authentication_finishes_before_chrome_creation_and_clears_session(self):
        response, driver, events, requests = Response(), Driver(), [], []
        webdriver, selenium = self.fake_selenium(driver)

        def open_request(request, timeout):
            events.append('authentication')
            requests.append((request, timeout))
            return response

        def create_chrome(**kwargs):
            self.assertTrue(response.closed)
            events.append('chrome')
            return driver

        webdriver.Chrome.side_effect = create_chrome
        with patch.dict(os.environ, LOGIN, clear=True), selenium, \
                patch.object(authentication, 'build_opener', return_value=types.SimpleNamespace(open=open_request)):
            result = authentication.authenticated_chrome()
        self.assertIs(result, driver)
        self.assertEqual(events, ['authentication', 'chrome'])
        request, timeout = requests[0]
        self.assertEqual(request.full_url, authentication.AUTH_URL)
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(json.loads(request.data), dict(loginId=LOGIN['KTL_M04_RBEM_USERNAME'],
                                                      password=LOGIN['KTL_M04_RBEM_PASSWORD']))
        self.assertEqual(timeout, 30)
        self.assertEqual(response.read_sizes, [65537])
        webdriver.Edge.assert_not_called()
        self.assertEqual(webdriver.Chrome.call_args.kwargs['options'].arguments,
                         ['--window-size=1440,1100', '--headless=new'])
        source = driver.commands[0][1]['source']
        self.assertIn('window!==window.top', source)
        self.assertIn('location.origin!=="' + authentication.TARGET_ORIGIN + '"', source)
        self.assertIn('localStorage.setItem("token",state.token)', source)
        self.assertIn(TOKEN, source)
        self.assertNotIn(LOGIN['KTL_M04_RBEM_PASSWORD'], source)
        self.assertEqual(list(authentication._BOOTSTRAPS.values()), ['SYNTHETIC_BOOTSTRAP_ID'])

    def test_returned_session_mapping_is_cleared_after_bootstrap(self):
        session, driver = {'token': TOKEN}, Driver()
        _, selenium = self.fake_selenium(driver)
        with selenium, patch.object(authentication, '_preauthenticate', return_value=session):
            authentication.authenticated_chrome()
        self.assertEqual(session, {})

    def test_headless_is_disabled_only_by_explicit_zero(self):
        for value in ('0', '1', '', 'false'):
            driver, session = Driver(), {'token': TOKEN}
            webdriver, selenium = self.fake_selenium(driver)
            with self.subTest(value=value), selenium, patch.dict(os.environ, {'KTL_M04_HEADLESS': value}), \
                    patch.object(authentication, '_preauthenticate', return_value=session):
                authentication.authenticated_chrome()
            self.assertEqual('--headless=new' in webdriver.Chrome.call_args.kwargs['options'].arguments, value != '0')

    def test_bad_auth_responses_are_masked_and_never_start_chrome(self):
        bad = [Response({'success': False, 'token': TOKEN}), Response({'success': 1, 'token': TOKEN}),
               Response({'success': True}), Response({'success': True, 'token': ''}),
               Response({'success': True, 'token': ' token'}),
               Response({'success': True, 'token': 'token\n'}),
               Response({'success': True, 'token': 'token\x7f'}),
               Response({'success': True, 'token': 'x' * 16385}), Response(raw=b'x' * 65537),
               Response(raw=b'invalid JSON ' + TOKEN.encode()), Response(status=201), Response(status=True),
               Response(url=authentication.AUTH_URL + '?private=SYNTHETIC'),
               Response(url='https://example.invalid/api/auth/login')]
        for index, response in enumerate(bad):
            webdriver, selenium = self.fake_selenium(Driver())
            with self.subTest(index=index), selenium, patch.dict(os.environ, LOGIN, clear=True), \
                    patch.object(authentication, 'build_opener', return_value=types.SimpleNamespace(
                        open=lambda *a, **k: response)):
                with self.assertRaises(RuntimeError) as failure:
                    authentication.authenticated_chrome()
                self.assertEqual(str(failure.exception), AUTH_ERROR)
                self.assertTrue(failure.exception.__suppress_context__)
                webdriver.Chrome.assert_not_called()

    def test_auth_transport_errors_and_redirects_are_never_echoed(self):
        webdriver, selenium = self.fake_selenium(Driver())
        opener = Mock()
        opener.open.side_effect = RuntimeError(TOKEN + LOGIN['KTL_M04_RBEM_PASSWORD'])
        with selenium, patch.dict(os.environ, LOGIN, clear=True), \
                patch.object(authentication, 'build_opener', return_value=opener):
            with self.assertRaises(RuntimeError) as failure:
                authentication.authenticated_chrome()
        self.assertEqual(str(failure.exception), AUTH_ERROR)
        webdriver.Chrome.assert_not_called()
        self.assertIsNone(authentication._RejectRedirects().redirect_request(None, None, 302, '', {},
                                                                            'https://example.invalid'))

    def test_chrome_and_cdp_failures_clear_session_and_hide_sensitive_errors(self):
        for mode in ('chrome', 'cdp', 'identifier'):
            driver = Driver(add_error=RuntimeError(TOKEN) if mode == 'cdp' else None,
                            add_reply={} if mode == 'identifier' else None,
                            quit_error=RuntimeError(TOKEN))
            session = {'token': TOKEN}
            webdriver, selenium = self.fake_selenium(driver)
            if mode == 'chrome':
                webdriver.Chrome.side_effect = RuntimeError(TOKEN + LOGIN['KTL_M04_RBEM_PASSWORD'])
            with self.subTest(mode=mode), selenium, \
                    patch.object(authentication, '_preauthenticate', return_value=session):
                with self.assertRaises(RuntimeError) as failure:
                    authentication.authenticated_chrome()
            self.assertEqual(str(failure.exception), '로그인 세션을 Chrome에 준비하지 못했습니다.')
            self.assertTrue(failure.exception.__suppress_context__)
            self.assertEqual(session, {})
            self.assertEqual(len(authentication._BOOTSTRAPS), 0)
            self.assertEqual(driver.quits, int(mode != 'chrome'))

    def test_complete_checks_session_as_boolean_and_removes_bootstrap_once(self):
        driver = Driver()
        authentication._BOOTSTRAPS[driver] = 'SYNTHETIC_BOOTSTRAP_ID'
        self.assertIsNone(authentication.complete_authentication(driver))
        self.assertEqual(driver.reads, [authentication._SESSION_PRESENT])
        self.assertEqual(driver.commands, [('Page.removeScriptToEvaluateOnNewDocument',
                                           {'identifier': 'SYNTHETIC_BOOTSTRAP_ID'})])
        self.assertEqual(len(authentication._BOOTSTRAPS), 0)
        self.assertEqual(driver.quits, 0)
        with self.assertRaisesRegex(RuntimeError, '^초기화할 Chrome 로그인 세션이 없습니다.$'):
            authentication.complete_authentication(driver)
        self.assertEqual(len(driver.commands), 1)

    def test_complete_rejects_wrong_origin_nonboolean_and_cdp_failures(self):
        for value, read_error, remove_error in [(False, None, None), (1, None, None),
                                              (True, RuntimeError(TOKEN), None),
                                              (True, None, RuntimeError(TOKEN))]:
            driver = Driver(session=value, read_error=read_error, remove_error=remove_error,
                            quit_error=RuntimeError(TOKEN))
            authentication._BOOTSTRAPS[driver] = 'SYNTHETIC_BOOTSTRAP_ID'
            with self.subTest(value=value, read_error=bool(read_error), remove_error=bool(remove_error)):
                with self.assertRaises(RuntimeError) as failure:
                    authentication.complete_authentication(driver)
            self.assertEqual(str(failure.exception), 'Chrome 로그인 세션 초기화를 완료하지 못했습니다.')
            self.assertTrue(failure.exception.__suppress_context__)
            self.assertEqual(driver.quits, 1)
            self.assertEqual(len(driver.commands), 1)
            self.assertEqual(len(authentication._BOOTSTRAPS), 0)

    def test_complete_requires_a_driver_prepared_by_the_helper(self):
        for driver in (None, {}, object(), Driver()):
            with self.subTest(driver_type=type(driver).__name__):
                with self.assertRaisesRegex(RuntimeError, '^초기화할 Chrome 로그인 세션이 없습니다.$'):
                    authentication.complete_authentication(driver)

    def test_runtime_exposes_authentication_without_starting_browser_on_auth_failure(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory(prefix='ktl-synthetic-authentication-') as directory:
            script = Path(directory) / 'script.py'
            script.write_text('from ktl_runtime import authenticated_chrome, complete_authentication\n'
                              'authenticated_chrome()\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=True), patch.object(runner, 'load_login_settings', return_value={}), \
                    patch('urllib.request.build_opener', side_effect=AssertionError('No network')), \
                    patch('subprocess.Popen', side_effect=AssertionError('No browser')), redirect_stdout(stream):
                result = runner.execute(script)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        terminal = next(event for event in events if event.get('event') == 'result')
        self.assertEqual(result, 2)
        self.assertFalse(terminal['browser_started'])
        self.assertIn('시험 계정 연결이 필요합니다.', terminal['error'])
        self.assertNotIn('ImportError', terminal['error'])

    def test_runtime_observes_browser_and_independent_business_step_with_helper(self):
        calls = []

        class WebDriver:
            def __init__(self, options):
                self.url = 'about:blank'
                self.start_session({'browserName': 'chrome', 'goog:chromeOptions': {'args': options.arguments}})

            def start_session(self, capabilities):
                self.capabilities = dict(capabilities, browserVersion='SYNTHETIC')

            def execute(self, name, params=None):
                calls.append(name)
                params = params or {}
                if name == 'get':
                    self.url = params['url']
                if name == 'getCurrentUrl':
                    return {'value': self.url}
                if name == 'w3cExecuteScript':
                    return {'value': True}
                if name == 'executeCdpCommand':
                    return {'value': {'identifier': 'SYNTHETIC_BOOTSTRAP_ID'}}
                return {'value': None}

            def get(self, url):
                return self.execute('get', {'url': url})

            @property
            def current_url(self):
                return self.execute('getCurrentUrl')['value']

            def execute_script(self, source):
                return self.execute('w3cExecuteScript', {'script': source, 'args': []})['value']

            def execute_cdp_cmd(self, command, values):
                return self.execute('executeCdpCommand', {'cmd': command, 'params': values})['value']

            def quit(self):
                self.execute('quit')

        modules = {name: types.ModuleType(name) for name in (
            'selenium', 'selenium.webdriver', 'selenium.webdriver.remote',
            'selenium.webdriver.remote.webdriver', 'selenium.webdriver.remote.webelement')}
        for name in ('selenium', 'selenium.webdriver', 'selenium.webdriver.remote'):
            modules[name].__path__ = []
        modules['selenium'].webdriver = modules['selenium.webdriver']
        modules['selenium.webdriver'].Chrome = WebDriver
        modules['selenium.webdriver'].ChromeOptions = Options
        modules['selenium.webdriver.remote.webdriver'].WebDriver = WebDriver
        modules['selenium.webdriver.remote.webelement'].WebElement = type('WebElement', (), {'submit': lambda self: None})
        scenario = dict(scenario_id='SYNTHETIC-AUTHENTICATED', steps=[dict(
            order=1, action='open', target='synthetic page', url=authentication.TARGET_ORIGIN + '/mypage/synthetic',
            expected_result='Synthetic application route')])
        contract = dict(version=1, scenario_id=scenario['scenario_id'], steps=[dict(
            order=1, action='open', target={'url': scenario['steps'][0]['url']},
            checks=[dict(kind='url_path', expected='/mypage/synthetic')])])
        source = ('from ktl_runtime import authenticated_chrome, complete_authentication, business_step\n'
                  'driver = authenticated_chrome()\ntry:\n    with business_step(1):\n'
                  '        driver.get("https://rainbowlab.ai.kr/mypage/synthetic")\n'
                  '        complete_authentication(driver)\n'
                  '        assert driver.current_url.endswith("/mypage/synthetic")\n'
                  'finally:\n    driver.quit()\n')
        stream = io.StringIO()
        response = Response()
        with tempfile.TemporaryDirectory(prefix='ktl-synthetic-authenticated-business-') as directory:
            script = Path(directory) / 'script.py'
            script.write_text(source, encoding='utf-8')
            with patch.dict(sys.modules, modules), patch.dict(os.environ, LOGIN, clear=True), \
                    patch.object(runner, 'load_login_settings', return_value={}), \
                    patch.object(runner.Observer, 'capture_screen'), \
                    patch.object(runner.Observer, 'screenshot_result', return_value=[]), \
                    patch('urllib.request.build_opener', return_value=types.SimpleNamespace(open=lambda *a, **k: response)), \
                    patch('subprocess.Popen', side_effect=AssertionError('No real browser')), redirect_stdout(stream):
                result = runner.execute(script, scenario, required=True, contract=contract)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        terminal = events[-1]
        self.assertEqual(result, 0, terminal)
        self.assertTrue(terminal['browser_started'])
        self.assertTrue(terminal['business_step_complete'])
        self.assertTrue(terminal['independent_checks_passed'])
        self.assertIn('get', calls)
        self.assertNotIn(TOKEN, stream.getvalue())
        self.assertNotIn(LOGIN['KTL_M04_RBEM_PASSWORD'], stream.getvalue())


if __name__ == '__main__':
    unittest.main()
