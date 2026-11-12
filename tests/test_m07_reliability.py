"""Synthetic prompt/HTTP-error regression only; no provider, browser or real files."""
import ast
import copy
from email.message import Message
import hashlib
import http.client
import io
import json
import re
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from backend.m07 import generator


SCENARIO = dict(scenario_id='SYNTHETIC-M07-RELIABILITY', scenario_name='Synthetic route',
    business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
    steps=[dict(order=1, action='open', target='Synthetic route', expected_result='Synthetic route is open')],
    execution_contract=dict(version=1, scenario_id='SYNTHETIC-M07-RELIABILITY', steps=[dict(
        order=1, action='open', target=dict(url='https://example.invalid/synthetic'),
        checks=[dict(kind='url_path', expected='/synthetic')])]))
SETTINGS = dict(api_key='SYNTHETIC-KEY-NOT-FOR-NETWORK', model='synthetic-model', target_url='https://example.invalid/login')


class Reply:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.raw[:size]


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ktl-m07-reliability-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def http_failure(self, raw=b'{}', headers=None, status=429):
        error = urllib.error.HTTPError('https://api.openai.com/v1/responses', status,
            'SYNTHETIC-SECRET-ERROR-REASON', headers, io.BytesIO(raw))
        with mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                mock.patch.object(generator.urllib.request, 'urlopen', side_effect=error) as network, \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, {}, SCENARIO)
        network.assert_called_once()
        evidence = caught.exception.evidence
        self.assertEqual(json.loads(evidence['response_bytes']), evidence['response'])
        self.assertEqual(evidence['max_attempts'], 1)
        self.assertIs(evidence['http_request_attempted'], True)
        self.assertIs(evidence['provider_response_observed'], True)
        self.assertEqual(evidence['response']['diagnostics']['max_attempts'], 1)
        self.assertEqual(evidence['response']['body_policy'], 'HASH_ONLY')
        self.assertNotIn('SYNTHETIC-SECRET-ERROR-REASON', str(caught.exception))
        return evidence

    def detail(self, value, headers=None):
        return self.http_failure(json.dumps(value).encode('utf-8'), headers)

    def test_prompt_version_literal_id_and_source_immutability(self):
        source = copy.deepcopy(SCENARIO)
        instructions, text = generator.prompt(source, {})
        self.assertEqual(generator.PROMPT_VERSION, 'ktl-selenium-v7')
        literal = re.search(r'include the exact literal assignment (SCENARIO_ID = .*?)\. Do not', instructions).group(1)
        statement = ast.parse(literal).body[0]
        self.assertIsInstance(statement, ast.Assign)
        self.assertEqual(statement.targets[0].id, 'SCENARIO_ID')
        self.assertIsInstance(statement.value, ast.Constant)
        self.assertEqual(statement.value.value, source['scenario_id'])
        self.assertEqual(json.loads(text)['scenario']['scenario_id'], source['scenario_id'])
        self.assertEqual(source, SCENARIO)

    def test_prompt_focus_only_explicit_contract_and_actions_inside_blocks(self):
        instructions, text = generator.prompt(SCENARIO, {})
        self.assertIn('execution_contract explicitly requires a focus check', instructions)
        self.assertIn('do not add arbitrary modal focus waits', instructions)
        self.assertNotIn('For click-input steps assert activeElement/focus', instructions)
        self.assertIn('action inside its own corresponding business_step block, not before it', instructions)
        self.assertNotIn('focus', json.dumps(json.loads(text)['scenario']['execution_contract']))

    def test_prompt_hidden_wait_success_truth_is_not_hidden_state_false(self):
        instructions, _ = generator.prompt(SCENARIO, {})
        snippet = re.search(r'for example (wait\.until\(lambda d: not is_visible\(d, locator\)\); '
                            r'assert not is_visible\(driver, locator\))\.', instructions).group(1)
        class Wait:
            def __init__(self, driver):
                self.driver = driver
            def until(self, predicate):
                if not predicate(self.driver):
                    raise TimeoutError('Synthetic predicate is not ready')
                return True
        for visible in (False, True):
            driver = dict(visible=visible)
            scope = dict(wait=Wait(driver), driver=driver, locator='synthetic',
                         is_visible=lambda d, locator: d['visible'])
            if visible:
                with self.assertRaises(TimeoutError):
                    exec(compile(snippet, '<synthetic prompt example>', 'exec'), scope)
            else:
                exec(compile(snippet, '<synthetic prompt example>', 'exec'), scope)

    def test_prompt_auth_wait_precedes_business_navigation_without_token_values(self):
        instructions, text = generator.prompt(SCENARIO, {})
        self.assertIn('same-origin authenticated application route distinct from the login route', instructions)
        self.assertIn('AND the login form to be absent or hidden before any business navigation', instructions)
        self.assertIn('Do not read, return or log authentication token values', instructions)
        login = json.loads(text)['execution_context']['login']
        self.assertEqual(login['username_env'], 'KTL_M04_RBEM_USERNAME')
        self.assertEqual(login['password_env'], 'KTL_M04_RBEM_PASSWORD')
        self.assertNotIn(SETTINGS['api_key'], instructions + text)

    def test_success_preserves_original_code_even_if_contract_literal_missing(self):
        code = '\ufeff# Synthetic original\r\nfrom selenium import webdriver\r\nassert True\r\n'
        value = dict(id='resp_synthetic', model='synthetic-returned-model', status='completed',
            output=[dict(type='message', content=[dict(type='output_text', text=code)])])
        raw = json.dumps(value).encode('utf-8') + b'\r\n'
        with mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                mock.patch.object(generator.urllib.request, 'urlopen', return_value=Reply(raw)) as network:
            result = generator.generate(self.root, {}, SCENARIO)
        network.assert_called_once()
        self.assertEqual(result['code'].encode('utf-8'), code.encode('utf-8'))
        self.assertEqual(result['response_bytes'], raw)
        self.assertIs(result['http_request_attempted'], True)
        self.assertIs(result['provider_response_observed'], True)
        self.assertNotIn('SCENARIO_ID', result['code'])
        body = json.loads(network.call_args.args[0].data)
        self.assertEqual(body['instructions'], result['instructions'])
        self.assertFalse(body['store'])

    def test_transport_failure_distinguishes_attempt_from_observed_response(self):
        for failure in (urllib.error.URLError('Synthetic connection failure'), TimeoutError('Synthetic timeout')):
            with self.subTest(kind=type(failure).__name__), \
                    mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                    mock.patch.object(generator.urllib.request, 'urlopen', side_effect=failure) as network, \
                    self.assertRaises(generator.GenerationError) as caught:
                generator.generate(self.root, {}, SCENARIO)
            network.assert_called_once()
            self.assertIs(caught.exception.evidence['http_request_attempted'], True)
            self.assertIs(caught.exception.evidence['provider_response_observed'], False)

    def test_response_read_timeout_retains_observed_response_flag(self):
        reply = Reply(b'')
        reply.read = mock.Mock(side_effect=TimeoutError('Synthetic body timeout'))
        with mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                mock.patch.object(generator.urllib.request, 'urlopen', return_value=reply), \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, {}, SCENARIO)
        self.assertIs(caught.exception.evidence['http_request_attempted'], True)
        self.assertIs(caught.exception.evidence['provider_response_observed'], True)

    def test_429_body_read_failure_preserves_stop_metadata_without_fabricated_body_hash(self):
        error = urllib.error.HTTPError('https://api.openai.com/v1/responses', 429,
            'SYNTHETIC-PRIVATE-ERROR', {'Retry-After': '120', 'x-request-id': 'req_Synthetic'}, None)
        error.read = mock.Mock(side_effect=OSError('SYNTHETIC-PRIVATE-READ-FAILURE'))
        with mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                mock.patch.object(generator.urllib.request, 'urlopen', side_effect=error) as network, \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, {}, SCENARIO)
        network.assert_called_once()
        evidence, response = caught.exception.evidence, caught.exception.evidence['response']
        self.assertIs(evidence['http_request_attempted'], True)
        self.assertIs(evidence['provider_response_observed'], True)
        self.assertEqual(response['http_status'], 429)
        self.assertEqual(response['diagnostics']['numeric_headers'], {'retry-after': 120.0})
        self.assertIsNone(response['response_body_sha256'])
        self.assertIsNone(response['body_truncated'])
        self.assertIs(response['body_read_failed'], True)
        self.assertNotIn('SYNTHETIC-PRIVATE', str(caught.exception))
        self.assertNotIn(b'SYNTHETIC-PRIVATE', evidence['response_bytes'])

    def truncated_chunked_response(self, status):
        class SyntheticSocket:
            def makefile(self, *args, **kwargs):
                # A declared 5-byte chunk ends after 3 bytes; stdlib raises IncompleteRead.
                return io.BytesIO(('HTTP/1.1 ' + str(status) + ' Synthetic\r\n'
                    'Transfer-Encoding: chunked\r\nRetry-After: 120\r\n\r\n5\r\nabc').encode('ascii'))
        response = http.client.HTTPResponse(SyntheticSocket())
        response.begin()
        return response

    def test_real_stdlib_truncated_chunked_429_keeps_cooldown_evidence(self):
        response = self.truncated_chunked_response(429)
        error = urllib.error.HTTPError('https://api.openai.com/v1/responses', 429,
            'Synthetic failure', response.headers, response)
        with mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                mock.patch.object(generator.urllib.request, 'urlopen', side_effect=error) as network, \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, {}, SCENARIO)
        network.assert_called_once()
        proof = caught.exception.evidence
        self.assertIs(proof['http_request_attempted'], True)
        self.assertIs(proof['provider_response_observed'], True)
        self.assertEqual(proof['response']['http_status'], 429)
        self.assertEqual(proof['response']['diagnostics']['numeric_headers']['retry-after'], 120.0)
        self.assertIsNone(proof['response']['response_body_sha256'])
        self.assertIs(proof['response']['body_read_failed'], True)

    def test_real_stdlib_truncated_chunked_success_keeps_transport_evidence(self):
        response = self.truncated_chunked_response(200)
        with mock.patch.object(generator, 'settings', return_value=SETTINGS), \
                mock.patch.object(generator.urllib.request, 'urlopen', return_value=response) as network, \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, {}, SCENARIO)
        network.assert_called_once()
        proof = caught.exception.evidence
        self.assertIs(proof['http_request_attempted'], True)
        self.assertIs(proof['provider_response_observed'], True)
        self.assertEqual(proof['response'], {'status': 'TRANSPORT_ERROR'})

    def test_preflight_failure_performs_no_http_attempt(self):
        with mock.patch.object(generator, 'settings', return_value={**SETTINGS, 'api_key': ''}), \
                mock.patch.object(generator.urllib.request, 'urlopen') as network, \
                self.assertRaises(generator.EvaluationError):
            generator.generate(self.root, {}, SCENARIO)
        network.assert_not_called()

    def test_native_submit_network_check_is_runner_owned_and_cannot_be_fabricated(self):
        instructions, _ = generator.prompt(SCENARIO, {})
        self.assertIn('native_submit_response condition is observed independently by the Runner', instructions)
        self.assertIn('call standard WebElement.submit() on the exact contract form', instructions)
        self.assertIn('Do not fabricate a network receipt', instructions)

    def test_known_error_enums_and_numeric_headers_only(self):
        headers = {'X-Request-ID': 'req_Synthetic_123', 'Retry-After': '1.25',
                   'x-ratelimit-limit-requests': '500', 'x-ratelimit-remaining-tokens': '0',
                   'x-ratelimit-limit-project-tokens': '10000', 'x-ratelimit-reset-tokens': '2.5',
                   'Authorization': 'SYNTHETIC-SECRET-HEADER', 'Set-Cookie': 'SYNTHETIC-SECRET-COOKIE'}
        raw = json.dumps(dict(error=dict(type='rate_limit_error', code='slow_down',
            message='SYNTHETIC-PRIVATE-MESSAGE', param='SYNTHETIC-PRIVATE-PARAM'))).encode()
        evidence = self.http_failure(raw, headers)
        saved, diagnostic = evidence['response'], evidence['response']['diagnostics']
        self.assertEqual(evidence['request_id'], 'req_Synthetic_123')
        self.assertEqual(saved['response_body_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(diagnostic['error_type'], 'rate_limit_error')
        self.assertEqual(diagnostic['error_code'], 'slow_down')
        self.assertEqual(diagnostic['numeric_headers'], {'retry-after': 1.25, 'x-ratelimit-limit-requests': 500,
            'x-ratelimit-remaining-tokens': 0, 'x-ratelimit-limit-project-tokens': 10000, 'x-ratelimit-reset-tokens': 2.5})
        for sentinel in ('SYNTHETIC-PRIVATE-MESSAGE', 'SYNTHETIC-PRIVATE-PARAM', 'SYNTHETIC-SECRET-HEADER',
                         'SYNTHETIC-SECRET-COOKIE', SETTINGS['api_key']):
            self.assertNotIn(sentinel.encode(), evidence['response_bytes'])

    def test_documented_quota_codes_are_saved_as_enums_without_inferring_a_cause(self):
        for code in ('credit_balance_exhausted', 'organization_spend_limit_exceeded',
                     'project_spend_limit_exceeded', 'organization_usage_limit_exceeded',
                     'rate_limit_exceeded', 'insufficient_quota'):
            with self.subTest(code=code):
                diagnostic = self.detail({'error': {'type': 'insufficient_quota', 'code': code}})['response']['diagnostics']
                self.assertEqual(diagnostic['error_code'], code)
                self.assertNotIn('message', diagnostic)

    def test_unknown_or_nonstring_error_fields_are_omitted(self):
        for value in ('SYNTHETIC-SECRET-CODE', '', 'RATE_LIMIT_ERROR', 'rate_limit_error\n', None, [], {}, 123):
            with self.subTest(value=value):
                diagnostic = self.detail({'error': {'type': value, 'code': value}})['response']['diagnostics']
                self.assertNotIn('error_type', diagnostic)
                self.assertNotIn('error_code', diagnostic)

    def test_invalid_duplicate_non_utf8_or_nonstandard_json_has_no_classification(self):
        bodies = [b'{', b'\xff', b'[]', b'null', b'{"error":null}',
            b'{"error":{"code":"slow_down","code":"rate_limit_exceeded","type":"rate_limit_error"}}',
            b'{"error":{"type":"rate_limit_error","code":"slow_down","nested":{"x":1,"x":2}}}',
            b'{"error":{"type":"rate_limit_error","code":"slow_down","message":NaN}}',
            b'{"error":{"type":"rate_limit_error","code":"slow_down","message":Infinity}}']
        for raw in bodies:
            with self.subTest(raw=raw):
                diagnostic = self.http_failure(raw)['response']['diagnostics']
                self.assertNotIn('error_type', diagnostic)
                self.assertNotIn('error_code', diagnostic)

    def test_truncated_body_is_bounded_hash_only_even_if_prefix_has_known_enums(self):
        prefix = b'{"error":{"type":"rate_limit_error","code":"slow_down"}}'
        raw = prefix + b' ' * (1024 * 1024 + 10)
        evidence = self.http_failure(raw, {'x-request-id': 'req_Synthetic', 'retry-after': '2'})
        saved = evidence['response']
        self.assertTrue(saved['body_truncated'])
        self.assertEqual(saved['response_body_sha256'], hashlib.sha256(raw[:1024 * 1024 + 1]).hexdigest())
        self.assertNotIn('error_type', saved['diagnostics'])
        self.assertNotIn('error_code', saved['diagnostics'])
        self.assertEqual(saved['diagnostics']['numeric_headers'], {'retry-after': 2.0})
        self.assertLess(len(evidence['response_bytes']), 1024)

    def test_request_id_validation_discards_arbitrary_or_secret_values(self):
        for value in ('synthetic-http-error', 'sk-SYNTHETIC-SECRET', 'Bearer SYNTHETIC', 'user@example.invalid',
                      'req_good\r\nAuthorization: secret', 'req_\u00e9', 'req_', 'req_' + 'a' * 129,
                      'https://example.invalid/private', ['req_Synthetic']):
            with self.subTest(value=value):
                evidence = self.http_failure(headers={'x-request-id': value})
                self.assertIsNone(evidence['request_id'])
                self.assertIsNone(evidence['response']['request_id'])

    def test_duplicate_headers_are_not_selected_even_with_same_values(self):
        for headers in ({'X-Request-ID': 'req_A', 'x-request-id': 'req_B', 'Retry-After': '1', 'retry-after': '1'}, Message()):
            if isinstance(headers, Message):
                for name, value in [('x-request-id', 'req_A'), ('X-Request-ID', 'req_A'),
                                    ('retry-after', '1'), ('Retry-After', '2')]:
                    headers[name] = value
            with self.subTest(kind=type(headers).__name__):
                evidence = self.http_failure(headers=headers)
                self.assertIsNone(evidence['request_id'])
                self.assertEqual(evidence['response']['diagnostics']['numeric_headers'], {})

    def test_invalid_numeric_headers_and_duration_strings_are_omitted(self):
        for value in ('-1', 'NaN', 'Infinity', '1e3', '1s', '6m0s', 'Tue, 10 Nov 2026 00:00:00 GMT',
                      '1, 2', '1\n', '10000000000000', '\u0661', '86400.000001'):
            with self.subTest(value=value):
                diagnostic = self.http_failure(headers={'retry-after': value, 'x-ratelimit-remaining-requests': value})['response']['diagnostics']
                self.assertEqual(diagnostic['numeric_headers'], {})

    def test_numeric_bounds_and_no_headers(self):
        diagnostic = self.http_failure(headers={'retry-after': '86400', 'x-ratelimit-limit-tokens': '1000000000000'})['response']['diagnostics']
        self.assertEqual(diagnostic['numeric_headers'], {'retry-after': 86400.0, 'x-ratelimit-limit-tokens': 10 ** 12})
        saved = self.http_failure()['response']
        self.assertIsNone(saved['request_id'])
        self.assertEqual(saved['diagnostics']['numeric_headers'], {})


if __name__ == '__main__':
    unittest.main()
