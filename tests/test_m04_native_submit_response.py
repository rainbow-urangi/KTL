"""Independent native-submit HTTP metadata checks; synthetic drivers/events only."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from backend.m04 import checks, runner
import test_m04_submit_observation as submit_fixture


CONDITION = dict(kind='native_submit_response', method='POST', api_origin='https://example.invalid',
                 api_path='/api/save', expected_status=201)
SECRET = 'SYNTHETIC-PRIVATE-HEADER-AND-BODY'


def event(method, identity='synthetic-request', **params):
    return dict(message=json.dumps(dict(message=dict(method='Network.' + method,
        params=dict(requestId=identity, **params)))))


def chain(identity='synthetic-request', since=100):
    url = 'https://example.invalid/api/save'
    return [event('requestWillBeSent', identity, timestamp=10, wallTime=since + .01,
                  request=dict(url=url, method='POST', headers={'Authorization': SECRET}, postData=SECRET)),
            event('responseReceived', identity, timestamp=10.02,
                  response=dict(url=url, status=201, headers={'Set-Cookie': SECRET})),
            event('loadingFinished', identity, timestamp=10.019)]


def changed(entry, **fields):
    value = json.loads(entry['message'])
    value['message']['params'].update(fields)
    return dict(message=json.dumps(value))


def source(condition=CONDITION, action='submit'):
    return dict(scenario_id='SYNTHETIC-NATIVE-NETWORK', steps=[dict(order=1, action=action,
        target='#correct-form', expected_result='Saved result and response are verified')],
        execution_contract=dict(version=1, scenario_id='SYNTHETIC-NATIVE-NETWORK', steps=[dict(
            order=1, action=action, target=dict(by='css selector', value='#correct-form'),
            checks=[copy.deepcopy(condition)])]))


class NativeSubmitContractTests(unittest.TestCase):
    def test_explicit_contract_is_additive_and_immutable(self):
        value = source(); original = copy.deepcopy(value)
        result = checks.prepare_contract(value)
        self.assertEqual(result['steps'][0]['checks'][0], CONDITION)
        self.assertEqual(value, original)
        legacy = source(dict(kind='visible', expected=True))
        self.assertEqual(checks.prepare_contract(legacy)['steps'][0]['checks'],
            [dict(kind='visible', target=dict(by='css selector', value='#correct-form'), expected=True)])

    def test_invalid_contracts_and_non_submit_actions_are_rejected(self):
        variants = [dict(method='GET'), dict(method=[]), dict(expected_status=True), dict(expected_status=400),
                    dict(api_origin='https://user:secret@example.invalid'), dict(api_origin='https://example.invalid?'),
                    dict(api_origin='https://example.invalid#'), dict(api_path='/api/save?x=1'),
                    dict(api_path='/api/save?'), dict(api_path='/api/save#'), dict(api_path='//example.invalid/api/save'),
                    dict(api_path='https://example.invalid/api/save'), dict(unexpected='field')]
        for fields in variants:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                checks.prepare_contract(source(dict(CONDITION, **fields)))
        with self.assertRaises(ValueError):
            checks.prepare_contract(source(action='click'))
        value=source();value['execution_contract']['steps'][0]['checks'] *= 2
        with self.assertRaises(ValueError):
            checks.prepare_contract(value)


class NativeSubmitLedgerTests(unittest.TestCase):
    def ledger(self, events, prior=None, succeeded=True):
        value = checks._NativeSubmitResponse(CONDITION)
        value.prior.update(prior or [])
        value.since, value.succeeded = 100, succeeded
        value.consume(events)
        return value

    def test_same_id_phases_finish_before_response_timestamp_is_valid(self):
        receipt = self.ledger(chain()).receipt()
        self.assertEqual(receipt['http_status'], 201)
        self.assertEqual(receipt['request_id_sha256'], hashlib.sha256(b'synthetic-request').hexdigest())
        self.assertAlmostEqual(receipt['finish_after_request_ms'], 19)
        self.assertFalse(receipt['direct_causal_id_proven'])
        self.assertNotIn(SECRET, json.dumps(receipt))
        self.assertNotIn('headers', json.dumps(receipt))
        self.assertNotIn('postData', json.dumps(receipt))

    def test_wrong_missing_old_duplicate_failed_and_misordered_events_reject(self):
        good = chain()
        wrong_method = changed(good[0], request=dict(url='https://example.invalid/api/save', method='PUT'))
        variants = {'no_events': [], 'request_only':good[:1], 'no_finish':good[:2],
            'wrong_method':[wrong_method,*good[1:]],
            'wrong_origin':[changed(good[0],request=dict(url='https://other.invalid/api/save',method='POST')),*good[1:]],
            'wrong_path':[changed(good[0],request=dict(url='https://example.invalid/api/other',method='POST')),*good[1:]],
            'query':[changed(good[0],request=dict(url='https://example.invalid/api/save?',method='POST')),*good[1:]],
            'fragment':[changed(good[0],request=dict(url='https://example.invalid/api/save#x',method='POST')),*good[1:]],
            'userinfo':[changed(good[0],request=dict(url='https://u:p@example.invalid/api/save',method='POST')),*good[1:]],
            'wrong_status':[good[0],changed(good[1],response=dict(url='https://example.invalid/api/save',status=200)),good[2]],
            'unrelated_response':[good[0],event('responseReceived','other',timestamp=10.02,response=dict(url='https://example.invalid/api/save',status=201)),good[2]],
            'old_wall':[changed(good[0],wallTime=99),*good[1:]],
            'nonfinite_wall':[changed(good[0],wallTime=float('inf')),*good[1:]],
            'nonfinite_request':[changed(good[0],timestamp=float('nan')),*good[1:]],
            'response_before_request_time':[good[0],changed(good[1],timestamp=9),good[2]],
            'finish_before_request_time':[*good[:2],changed(good[2],timestamp=9)],
            'finish_before_response_event':[good[0],good[2],good[1]],
            'response_before_request_event':[good[1],*good],
            'finish_before_request_event':[good[2],*good],
            'failure_before_request_event':[event('loadingFailed'),*good],
            'loading_failed':[good[0],event('loadingFailed'),*good[1:]],
            'redirect':[changed(good[0],redirectResponse={}),*good[1:]],
            'duplicate_id':[good[0],*good],
            'two_matching_posts':[*good,*chain('second-request')],
            'query_post_and_valid_post':[changed(good[0],request=dict(url='https://example.invalid/api/save?x=1',method='POST')),
                                         *good[1:],*chain('second-request')],
            'poisoned_id_and_another_valid_post':[good[1],*good,*chain('second-request')],
            'response_wrong_origin':[good[0],changed(good[1],response=dict(url='https://other.invalid/api/save',status=201)),good[2]]}
        for name, events in variants.items():
            with self.subTest(case=name):
                self.assertIsNone(self.ledger(events).receipt())
        self.assertIsNone(self.ledger(good,prior=['synthetic-request']).receipt())
        self.assertIsNone(self.ledger(good,succeeded=False).receipt())

    def test_unrelated_get_and_out_of_order_other_ids_do_not_poison_good_post(self):
        other = [event('requestWillBeSent','other',timestamp=9,wallTime=100.01,
                       request=dict(url='https://example.invalid/background',method='GET')),
                 event('responseReceived','other',timestamp=9.1,response=dict(url='https://example.invalid/background',status=200)),
                 event('loadingFinished','other',timestamp=9.2)]
        self.assertIsNotNone(self.ledger(other+chain()).receipt())

    def test_pre_arm_drain_and_second_native_submit_are_not_reused(self):
        value=checks._NativeSubmitResponse(CONDITION);value.consume(chain())
        with patch.object(checks.time,'time',return_value=100):value.arm()
        value.succeeded=True;value.consume(chain())
        self.assertIsNone(value.receipt())
        value=self.ledger(chain());value.arm()
        self.assertIsNone(value.receipt())


class NativeSubmitIntegrationTests(unittest.TestCase):
    def run_fake(self, mode, logs=True):
        runtime=runner.checks;prepare=runtime.prepare_contract;raw=runtime.RuntimeChecks._raw
        def contract(value,config=None):
            item=copy.deepcopy(value)
            item['execution_contract']['steps'][0]['checks'].append(copy.deepcopy(CONDITION))
            return prepare(item,config)
        def independent(checker,driver,name,params=None):
            if name=='getLog':
                native=checker.network.get('native') if checker.network else None
                if logs and native and native.succeeded and not getattr(checker,'synthetic_delivered',False):
                    checker.synthetic_delivered=True
                    return chain(since=native.since)
                return []
            return raw(checker,driver,name,params)
        fixture=submit_fixture.SubmitObservationTests('runTest')
        with patch.object(runtime,'prepare_contract',side_effect=contract), \
                patch.object(runtime.RuntimeChecks,'_raw',independent):
            return fixture.run_fake(mode)

    def test_native_submit_with_independent_log_chain_passes_and_restores_methods(self):
        code,result,_=self.run_fake('correct')
        self.assertEqual(code,0)
        item=result['business_steps'][0]['check_results'][-1]
        self.assertEqual(item['kind'],'native_submit_response')
        self.assertEqual(item['network']['http_status'],201)
        self.assertNotIn(SECRET,json.dumps(result))

    def test_missing_independent_logs_cannot_pass_with_other_assertions(self):
        code,result,_=self.run_fake('correct',logs=False)
        self.assertEqual(code,1)
        self.assertFalse(result['business_steps'][0]['independent_checks_passed'])

    def test_wrong_failed_and_arbitrary_script_submit_remain_rejected(self):
        for mode in ('wrong','failed','script_only'):
            with self.subTest(mode=mode):
                code,result,_=self.run_fake(mode)
                self.assertEqual(code,1)
                self.assertFalse(result['business_step_complete'])


class NativeSubmitIndependentObservationTests(unittest.TestCase):
    def checker(self, unavailable=False):
        checker=checks.RuntimeChecks(checks.prepare_contract(source()))
        driver=object()
        def raw(driver,name,params):
            if name=='getLog':
                if unavailable:
                    raise RuntimeError(SECRET)
                return {'value':[]}
            return {'value':True}
        checker.raw_execute=raw
        checker.begin(1,[driver])
        return checker,driver

    def test_user_get_log_is_also_consumed_independently_and_other_driver_is_ignored(self):
        checker,driver=self.checker()
        checker.before_command(driver,'submitElement',{'id':'synthetic-form'})
        checker.native_submit_completed(driver,True)
        entries=chain(since=checker.network['native'].since)
        checker.observe(object(),'getLog',{'type':'performance'},{'value':entries})
        self.assertEqual(checker.network['native'].requests,{})
        checker.observe(driver,'getLog',{'type':'performance'},{'value':entries})
        passed,error,evidence=checker.finish([driver])
        self.assertTrue(passed)
        self.assertIsNone(error)
        self.assertEqual(evidence[0]['network']['http_status'],201)

    def test_logging_unavailable_rejects_before_native_action_without_private_error(self):
        checker,driver=self.checker(unavailable=True)
        with self.assertRaises(RuntimeError) as caught:
            checker.before_command(driver,'submitElement',{'id':'synthetic-form'})
        self.assertNotIn(SECRET,str(caught.exception))
        self.assertFalse(checker.target_action)
        self.assertFalse(checker.network['native'].succeeded)

    def test_failed_check_diagnostic_retains_only_sanitized_network_metadata(self):
        ledger=checks._NativeSubmitResponse(CONDITION)
        ledger.since,ledger.succeeded=100,True
        entries=chain();entries[1]=changed(entries[1],response=dict(url='https://example.invalid/api/save',status=503,headers={'Authorization':SECRET}))
        ledger.consume(entries)
        diagnostic=ledger.diagnostic()
        self.assertEqual(diagnostic['requests'][0]['http_status'],503)
        self.assertTrue(diagnostic['requests'][0]['rejected'])
        self.assertNotIn(SECRET,json.dumps(diagnostic))
        self.assertNotIn('synthetic-request',json.dumps(diagnostic))


if __name__=='__main__':
    unittest.main()
