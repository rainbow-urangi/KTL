"""CU02 고정 계약의 native submit 관측. 합성 메타데이터만 사용한다."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from backend.m04 import checks, cu02


def event(method, identity='SYNTHETIC_CU02_POST', **params):
    return dict(message=json.dumps(dict(message=dict(method='Network.' + method,
        params=dict(requestId=identity, **params)))))


def chain(identity='SYNTHETIC_CU02_POST', status=201, wall=100.01):
    url = cu02.TARGET_ORIGIN + '/api/schedules'
    return [event('requestWillBeSent', identity, timestamp=10, wallTime=wall,
                  request=dict(url=url, method='POST', headers={'Authorization': 'SYNTHETIC_PRIVATE'},
                               postData='SYNTHETIC_PRIVATE')),
            event('responseReceived', identity, timestamp=10.02,
                  response=dict(url=url, status=status, headers={'Set-Cookie': 'SYNTHETIC_PRIVATE'})),
            event('loadingFinished', identity, timestamp=10.03)]


class CU02SubmitContractTests(unittest.TestCase):
    def run_check(self, entries, *, prior=(), native=True, available=True, action_id=cu02.SUBMIT):
        prepared = cu02.prepare(dict(date='2026-11-13', title='SYNTHETIC CU02 new schedule',
                                     description='Synthetic only; no external execution.', browser='chrome'))
        original = copy.deepcopy(prepared)
        checker = checks.RuntimeChecks(checks.prepare_contract(prepared['scenario']))
        driver = object()
        pending = list(prior)
        delivered = False

        def raw(actual, name, params):
            nonlocal delivered
            self.assertIs(actual, driver)
            if name == 'getLog':
                self.assertEqual(params, {'type': 'performance'})
                if not available:
                    raise RuntimeError('SYNTHETIC_PRIVATE')
                if pending:
                    result = list(pending)
                    pending.clear()
                    return {'value': result}
                if checker.target_action and not delivered:
                    delivered = True
                    return {'value': list(entries)}
                return {'value': []}
            self.assertEqual(name, 'w3cExecuteScript')
            if '.matches(' in params['script']:
                identity = params['args'][0]['element-6066-11e4-a52e-4f735466cecf']
                return {'value': identity == params['args'][1] == cu02.SUBMIT}
            # 명시적으로 성공한 합성 DOM 상태. HTTP 판정을 대신하지 않는다.
            return {'value': True}

        checker.raw_execute = raw
        checker.begin(4, [driver])
        with patch.object(checks.time, 'time', return_value=100), \
                patch.object(checks.time, 'monotonic', side_effect=range(100)), \
                patch.object(checks.time, 'sleep'):
            try:
                checker.before_command(driver, 'submitElement' if native else 'clickElement', {'id': action_id})
            except RuntimeError as exc:
                self.assertNotIn('SYNTHETIC_PRIVATE', str(exc))
                return False, str(exc), []
            if native:
                checker.native_submit_completed(driver, True)
            result = checker.finish([driver])
        self.assertEqual(prepared, original)
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(result))
        return result

    def test_new_post_201_and_same_request_finished_pass_with_dom_checks(self):
        passed, error, evidence = self.run_check(chain())
        self.assertTrue(passed)
        self.assertIsNone(error)
        self.assertEqual([item['kind'] for item in evidence],
                         ['native_submit_response', 'visible', 'text_count'])
        receipt = evidence[0]['network']
        self.assertEqual((receipt['method'], receipt['path'], receipt['http_status']), ('POST', '/api/schedules', 201))
        self.assertEqual(receipt['request_id_sha256'], hashlib.sha256(b'SYNTHETIC_CU02_POST').hexdigest())
        self.assertFalse(receipt['direct_causal_id_proven'])
        self.assertEqual(receipt['association'], 'EXACT_NATIVE_SUBMIT_OBSERVATION_WINDOW')

    def test_missing_finished_wrong_status_and_mismatched_request_ids_fail_even_when_dom_succeeds(self):
        good = chain()
        variants = {'201_not_finished': good[:2], '200_finished': chain(status=200),
                    'different_response_id': [good[0], event('responseReceived', 'OTHER_POST', timestamp=10.02,
                        response=dict(url=cu02.TARGET_ORIGIN + '/api/schedules', status=201)), good[2]],
                    'different_finish_id': good[:2] + [event('loadingFinished', 'OTHER_POST', timestamp=10.03)],
                    'no_response': [], 'two_posts': good + chain('SECOND_POST')}
        for name, entries in variants.items():
            with self.subTest(case=name):
                passed, error, evidence = self.run_check(entries)
                self.assertFalse(passed)
                self.assertEqual(error, '독립 기대 결과 검사 실패: native_submit_response')
                self.assertEqual(evidence[0]['status'], 'FAIL')

    def test_previous_response_cannot_be_reused_for_new_registration(self):
        for entries in ([], chain()):
            with self.subTest(replayed=bool(entries)):
                passed, _, evidence = self.run_check(entries, prior=chain(wall=99))
                self.assertFalse(passed)
                self.assertEqual(evidence[0]['status'], 'FAIL')

    def test_click_without_native_submit_cannot_pass_with_matching_network_and_dom(self):
        passed, _, evidence = self.run_check(chain(), native=False)
        self.assertFalse(passed)
        self.assertFalse(evidence[0]['network']['native_submit_succeeded'])

    def test_wrong_target_and_missing_performance_logs_reject_before_submit(self):
        for kwargs in (dict(action_id='#OTHER_BUTTON'), dict(available=False)):
            with self.subTest(case=kwargs):
                passed, error, evidence = self.run_check(chain(), **kwargs)
                self.assertFalse(passed)
                self.assertTrue(error)
                self.assertEqual(evidence, [])


if __name__ == '__main__':
    unittest.main()
