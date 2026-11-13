"""Offline generation-plan/HTTP evidence tests; all inputs and transport are synthetic."""
import ast
import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
import hashlib
import http.client
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from backend.m07 import generator
from backend.m07.provider_state import ProviderState


SCENARIO = dict(
    scenario_id='SYNTHETIC-PLAN', scenario_name='Synthetic close form',
    business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
    steps=[dict(order=1, action='open', target='Synthetic page', expected_result='Page is open'),
           dict(order=2, action='click', target='#close', expected_result='Form is hidden')],
    execution_contract=dict(version=1, scenario_id='SYNTHETIC-PLAN', steps=[
        dict(order=1, action='open', target=dict(url='https://example.invalid/synthetic'),
             checks=[dict(kind='url_path', expected='/synthetic')]),
        dict(order=2, action='click', target=dict(by='css selector', value='#close'),
             checks=[dict(kind='visible', target=dict(by='css selector', value='#modal'), expected=False)])]))
SETTINGS = dict(api_key='SYNTHETIC-PRIVATE-KEY', model='synthetic-model', target_url='https://example.invalid')


class Reply:
    def __init__(self, code):
        self.raw = json.dumps(dict(id='resp_synthetic', model='synthetic-returned-model', status='completed',
            output=[dict(type='message', content=[dict(type='output_text', text=code)])])).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.raw[:size]


class GenerationPlanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m07-plan-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = copy.deepcopy(SCENARIO)
        self.config = dict(m07=dict(target_url='https://example.invalid/login', generation_timeout_seconds=35))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No network permitted')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No browser permitted')))

    def metadata(self, *, source=None, config=None, settings=None):
        with patch.object(generator, 'settings', return_value=SETTINGS if settings is None else settings), \
                patch.object(generator.urllib.request, 'urlopen', side_effect=AssertionError('Planning must not send HTTP')):
            return generator.prompt_metadata(self.root, self.config if config is None else config,
                                             self.source if source is None else source)

    def test_offline_plan_is_deterministic_private_key_free_and_does_not_mutate_inputs(self):
        before_source, before_config = copy.deepcopy(self.source), copy.deepcopy(self.config)
        plan = self.metadata()
        self.assertEqual(plan, self.metadata())
        self.assertNotIn(SETTINGS['api_key'], json.dumps(plan))
        self.assertEqual(self.source, before_source)
        self.assertEqual(self.config, before_config)
        unsigned = {key: value for key, value in plan.items() if key != 'generation_spec_sha256'}
        raw = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.assertEqual(plan['generation_spec_sha256'], hashlib.sha256(raw).hexdigest())
        for field in ('instructions', 'input'):
            self.assertEqual(plan[field + '_sha256'], hashlib.sha256(plan[field].encode('utf-8')).hexdigest())
        self.assertEqual(plan['max_attempts'], 1)
        self.assertEqual(plan['generation_timeout_seconds'], 35)
        self.assertIs(plan['store'], False)

    def test_offline_metadata_allows_unconfigured_model_and_key(self):
        plan = self.metadata(settings=dict(SETTINGS, api_key='', model=''))
        self.assertEqual(plan['requested_model'], '')
        self.assertEqual(plan['prompt_version'], generator.PROMPT_VERSION)
        with patch.object(generator, 'settings', return_value=dict(SETTINGS, api_key='', model='')), \
                patch.object(generator.urllib.request, 'urlopen') as transport, \
                self.assertRaises(generator.EvaluationError) as caught:
            generator.generate(self.root, self.config, self.source, expected_metadata=plan)
        self.assertEqual(caught.exception.status, 'NOT_CONFIGURED')
        transport.assert_not_called()

    def test_frozen_plan_matches_actual_request_and_preserves_original_bytes(self):
        plan = self.metadata()
        code = '\ufeff# Synthetic original\r\nSCENARIO_ID = "SYNTHETIC-PLAN"\r\n'
        reply = Reply(code)
        with patch.object(generator, 'settings', return_value=SETTINGS) as settings, \
                patch.object(generator.urllib.request, 'urlopen', return_value=reply) as transport:
            result = generator.generate(self.root, self.config, self.source, expected_metadata=plan)
        settings.assert_called_once()
        transport.assert_called_once()
        request = transport.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body, dict(model=plan['requested_model'], instructions=plan['instructions'],
                                    input=plan['input'], store=False))
        self.assertEqual(request.full_url, plan['endpoint'])
        self.assertEqual(transport.call_args.kwargs['timeout'], 35)
        self.assertEqual(result['code'].encode('utf-8'), code.encode('utf-8'))
        self.assertEqual(result['response_bytes'], reply.raw)
        self.assertEqual(result['generation_spec_sha256'], plan['generation_spec_sha256'])
        self.assertEqual(result['requested_model'], 'synthetic-model')
        self.assertEqual(result['model'], 'synthetic-returned-model')

    def assert_drift_rejected(self, plan, *, settings=None, config=None, source=None):
        with patch.object(generator, 'settings', return_value=SETTINGS if settings is None else settings), \
                patch.object(generator.urllib.request, 'urlopen') as transport, \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, self.config if config is None else config,
                               self.source if source is None else source, expected_metadata=plan)
        transport.assert_not_called()
        self.assertEqual(caught.exception.status, 'NOT_READY')
        proof = caught.exception.evidence
        self.assertIs(proof['http_request_attempted'], False)
        self.assertIs(proof['provider_response_observed'], False)
        self.assertEqual(proof['response']['status'], 'GENERATION_SPEC_CHANGED')
        self.assertEqual(json.loads(proof['response_bytes']), proof['response'])
        self.assertNotIn(SETTINGS['api_key'], json.dumps(proof, default=lambda item: '<bytes>'))

    def test_model_change_is_rejected_before_http(self):
        self.assert_drift_rejected(self.metadata(), settings=dict(SETTINGS, model='different-synthetic-model'))

    def test_changed_contract_or_expected_state_is_rejected_before_http(self):
        plan = self.metadata()
        for field in ('target', 'check', 'expected_result'):
            with self.subTest(field=field):
                source = copy.deepcopy(self.source)
                if field == 'target':
                    source['steps'][1]['target'] = '#other-close'
                    source['execution_contract']['steps'][1]['target']['value'] = '#other-close'
                elif field == 'check':
                    source['execution_contract']['steps'][1]['checks'][0]['target']['value'] = '#other-modal'
                else:
                    source['steps'][1]['expected_result'] = 'A revised required outcome'
                self.assert_drift_rejected(plan, source=source)

    def test_timeout_and_business_context_changes_are_rejected_before_http(self):
        plan = self.metadata()
        for updates in (dict(generation_timeout_seconds=36), dict(target_url='https://example.invalid/other'),
                        dict(execution_contexts={'SYNTHETIC-BU': {'note': 'A revised task context'}})):
            with self.subTest(fields=list(updates)):
                config = copy.deepcopy(self.config)
                config['m07'].update(updates)
                self.assert_drift_rejected(plan, config=config)

    def test_prompt_version_drift_is_rejected_before_http(self):
        plan = self.metadata()
        with patch.object(generator, 'PROMPT_VERSION', 'SYNTHETIC-CHANGED-PROMPT'):
            self.assert_drift_rejected(plan)

    def test_tampered_metadata_including_boolean_numeric_alias_is_rejected(self):
        original = self.metadata()
        for field, value in [('generation_spec_sha256', '0' * 64), ('max_attempts', True),
                             ('instructions', 'Changed instructions'), ('extra_field', 'not accepted')]:
            with self.subTest(field=field):
                plan = dict(original)
                plan[field] = value
                self.assert_drift_rejected(plan)

    def test_existing_three_argument_call_remains_supported(self):
        with patch.object(generator, 'settings', return_value=SETTINGS), \
                patch.object(generator.urllib.request, 'urlopen', return_value=Reply('# Original synthetic code')) as transport:
            result = generator.generate(self.root, self.config, self.source)
        self.assertEqual(result['code'], '# Original synthetic code')
        self.assertTrue(result['generated_by_llm'])
        transport.assert_called_once()

    def test_regular_and_meeting_plans_preserve_literal_focus_close_and_auth_guards(self):
        for meeting in (False, True):
            with self.subTest(meeting=meeting):
                source = dict(self.source, meeting_protocol=meeting)
                plan = self.metadata(source=source)
                instructions = plan['instructions']
                literal = re.search(r'include the exact literal assignment (SCENARIO_ID = .*?)\. Do not', instructions).group(1)
                statement = ast.parse(literal).body[0]
                self.assertIsInstance(statement.value, ast.Constant)
                self.assertEqual(statement.value.value, self.source['scenario_id'])
                self.assertIn('execution_contract explicitly requires a focus check', instructions)
                self.assertIn('do not add arbitrary modal focus waits', instructions)
                self.assertIn('assert not is_visible(driver, locator)', instructions)
                checks = json.loads(plan['input'])['scenario']['execution_contract']['steps'][1]['checks']
                self.assertEqual(checks[0]['kind'], 'visible')
                self.assertIs(checks[0]['expected'], False)
                if meeting:
                    self.assertIn('authenticates BEFORE creating an actual local Chrome session', instructions)
                    self.assertIn('complete_authentication(driver) exactly once', instructions)
                    self.assertEqual(plan['prompt_version'], generator.MEETING_PROMPT_VERSION)
                else:
                    self.assertIn('same-origin authenticated application route distinct from the login route', instructions)
                    self.assertIn('AND the login form to be absent or hidden before any business navigation', instructions)

    def test_explicit_focus_contract_remains_in_frozen_input_without_invented_focus(self):
        source = copy.deepcopy(self.source)
        source['execution_contract']['steps'][1]['checks'].append(dict(kind='focus', expected=True))
        plan = self.metadata(source=source)
        actual = json.loads(plan['input'])['scenario']['execution_contract']['steps'][1]['checks']
        self.assertEqual([check['kind'] for check in actual], ['visible', 'focus'])
        self.assertEqual(len(self.source['execution_contract']['steps'][1]['checks']), 1)

    def test_http429_body_read_failure_keeps_frozen_plan_and_restart_cooldown_without_secrets(self):
        class BrokenBody(io.BytesIO):
            def read(self, size=-1):
                raise http.client.IncompleteRead(b'SYNTHETIC-PRIVATE-PARTIAL-BODY', 20)
        headers = Message()
        headers['x-request-id'] = 'req_synthetic_safe'
        headers['retry-after'] = '13505'
        headers['set-cookie'] = 'SYNTHETIC-PRIVATE-COOKIE'
        failure = urllib.error.HTTPError('https://api.openai.com/v1/responses', 429,
            'SYNTHETIC-PRIVATE-REASON', headers, BrokenBody())
        plan = self.metadata()
        with patch.object(generator, 'settings', return_value=SETTINGS), \
                patch.object(generator.urllib.request, 'urlopen', side_effect=failure) as transport, \
                self.assertRaises(generator.GenerationError) as caught:
            generator.generate(self.root, self.config, self.source, expected_metadata=plan)
        transport.assert_called_once()
        proof = caught.exception.evidence
        self.assertEqual(proof['generation_spec_sha256'], plan['generation_spec_sha256'])
        response = proof['response']
        self.assertEqual(response['http_status'], 429)
        self.assertTrue(response['body_read_failed'])
        self.assertIsNone(response['response_body_sha256'])
        self.assertEqual(response['request_id'], 'req_synthetic_safe')
        self.assertEqual(response['diagnostics']['numeric_headers'], {'retry-after': 13505.0})
        self.assertNotIn('SYNTHETIC-PRIVATE', proof['response_bytes'].decode('utf-8'))
        now = datetime(2026, 11, 13, tzinfo=timezone.utc)
        path = self.root / 'synthetic-provider-state.json'
        def read(file):
            return json.loads(file.read_text(encoding='utf-8'))
        def write(file, value):
            file.write_text(json.dumps(value), encoding='utf-8')
        state = ProviderState(path, read=read, write=write, clock=lambda: now)
        state.record(SETTINGS['model'], response, observed_at=now)
        original = path.read_bytes()
        restarted = ProviderState(path, read=read, write=write, clock=lambda: now + timedelta(seconds=10))
        self.assertTrue(restarted.current(SETTINGS['model'])['blocked'])
        self.assertEqual(restarted.current(SETTINGS['model'])['retry_after_seconds'], 13505.0)
        self.assertFalse(restarted.current('different-synthetic-model')['blocked'])
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn(b'SYNTHETIC-PRIVATE', original)


if __name__ == '__main__':
    unittest.main()
