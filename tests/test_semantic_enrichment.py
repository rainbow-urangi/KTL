"""Synthetic-only semantic and ownership regression fixtures."""
import copy
import unittest
from backend.semantic_enrichment import enrich, allowed_event
from backend.business_process_serializer import canonical_bytes
from backend.m02_semantic_scope import scope_steps

class SemanticTests(unittest.TestCase):
    def fixture(self, labels=('Name', 'Email')):
        raw = [dict(event_id=f'e{i}', session_id='session', page_url='https://example.invalid/form',
            target_selector=f'#field{i}', element_text=label, associated_label=label,
            locators_json={'event_context': {'action':'change', 'interaction_id':f'gesture{i}'},
            'input_context': {'id':f'f{i}', 'associated_label':label}}) for i,label in enumerate(labels)]
        node=dict(node_id='n',process_model_id='p',action='input',http_method='',normalized_endpoint='',page_path='/form',target_role='input_control')
        occurrence=dict(node,process_instance_id='w',step_order=1,source_session_id='session',source_event_evidence=[r['event_id'] for r in raw])
        return [dict(process_model_id='p',canonical_instance_id='w',canonical_node_sequence=['n'])], [node], [occurrence], raw

    def test_distinct_field_split_and_conservation(self):
        result=enrich(*self.fixture())
        steps=result['processes'][0]['business_steps']
        self.assertEqual([s['target'] for s in steps],['Name','Email'])
        self.assertEqual([s['source_event_ids'] for s in steps],[['e0'],['e1']])
        self.assertTrue(all(s['split_from']=='p-B001' for s in steps))

    def test_determinism_and_no_mutation(self):
        args=self.fixture();before=copy.deepcopy(args)
        self.assertEqual(canonical_bytes(enrich(*args)),canonical_bytes(enrich(*args)))
        self.assertEqual(args,before)

    def test_forbidden_metadata_invariance(self):
        args=self.fixture();expected=enrich(*args)
        for row in args[3]:
            row.update(task_id='forbidden',business_unit_id='forbidden',workflow_key='forbidden',score=99,ground_truth='forbidden')
            row['locators_json']['analysis']={'business_unit_id':'forbidden','score':100}
            row['locators_json']['input_context']['value']='do not pass values'
        self.assertEqual(expected,enrich(*args))

    def test_only_same_interaction_same_field_can_compress(self):
        args=self.fixture(('Name','Name'))
        args[3][1]['target_selector']=args[3][0]['target_selector']
        args[3][1]['locators_json']=copy.deepcopy(args[3][0]['locators_json'])
        result=enrich(*args)
        self.assertEqual(result['generated_business_step_count'],1)
        self.assertEqual(result['processes'][0]['business_steps'][0]['source_event_ids'],['e0','e1'])
        args[3][1]['locators_json']['event_context']['interaction_id']='different'
        self.assertEqual(enrich(*args)['generated_business_step_count'],2)

    def test_same_label_selector_different_name_type_never_compressed(self):
        for different in ('name', 'type'):
            args=self.fixture(('Contact','Contact'))
            for row in args[3]:
                row['target_selector']='input.contact'
                row['locators_json']={'event_context':{'action':'change','interaction_id':'same-batch'},
                    'input_context':{'id':'','name':'phone','type':'tel','associated_label':'Contact'}}
            args[3][1]['locators_json']['input_context'][different]='email'
            result=enrich(*args)
            self.assertEqual(result['generated_business_step_count'],2)
            self.assertEqual([s['source_event_ids'] for s in result['processes'][0]['business_steps']],[['e0'],['e1']])

    def test_ambiguous_identity_never_compressed(self):
        args=self.fixture(('Contact','Contact'))
        for row in args[3]:
            row['target_selector']='input.contact'
            row['locators_json']={'event_context':{'action':'change','interaction_id':'same-batch'},
                'input_context':{'id':'','name':'','type':'text','associated_label':'Contact'}}
        self.assertEqual(enrich(*args)['generated_business_step_count'],2)

    def test_save_confirm_separate_and_http_method_preserved(self):
        args=self.fixture(('저장','확인'))
        args[1][0]['action']='selection';args[2][0]['action']='selection'
        for row in args[3]:row['locators_json']['event_context']['action']='click'
        result=enrich(*args)
        self.assertEqual([s['action_type'] for s in result['processes'][0]['business_steps']],['SAVE','CONFIRM'])
        for method in ['GET','POST','PATCH']:
            args[1][0].update(action='api_confirmation',http_method=method)
            args[2][0].update(action='api_confirmation',http_method=method)
            result=enrich(*args)
            self.assertEqual(result['generated_business_step_count'],0)
            self.assertEqual(result['processes'][0]['unlinked_technical_evidence'][0]['http_method'],method)

    def test_missing_raw_or_wrong_session_fails(self):
        args=self.fixture();args[3].pop()
        with self.assertRaises(ValueError):enrich(*args)
        args=self.fixture();args[3][0]['session_id']='other'
        with self.assertRaises(ValueError):enrich(*args)

    def test_unknown_retained(self):
        args=self.fixture(('',))
        args[3][0]['locators_json']['input_context']['id']=''
        result=enrich(*args)
        self.assertEqual(result['generated_business_step_count'],1)
        self.assertEqual(result['processes'][0]['business_steps'][0]['resolution_status'],'UNRESOLVED')

class ScopeTests(SemanticTests):
    def execution(self,bu,start,end,xid):
        return dict(execution_id=xid,business_unit_id=bu,session_id='session',start_event_id=start,end_event_id=end)

    def test_scope_excludes_unrelated_preserves_split_maps(self):
        snapshot=enrich(*self.fixture())
        second=copy.deepcopy(snapshot['processes'][0]);second['source_process_id']='fragment'
        second['business_steps']=[dict(second['business_steps'][0],generated_step_id='fragment-C001')]
        snapshot['processes'].append(second)
        result=scope_steps(snapshot,[self.execution('target','e0','e0','x'),self.execution('other','e1','e1','y')],['target'])
        self.assertEqual(result['scope_summary']['total_generated_steps'],2)
        self.assertEqual(result['scope_summary']['out_of_scope_count'],1)

    def test_mixed_once_ineligible_not_repaired(self):
        snapshot=enrich(*self.fixture());steps=snapshot['processes'][0]['business_steps']
        steps[0]['source_event_ids']=['e0','e1'];steps.pop()
        result=scope_steps(snapshot,[self.execution('target','e0','e0','x'),self.execution('other','e1','e1','y')],['target','other'])
        self.assertEqual(result['scope_summary']['total_generated_steps'],1)
        self.assertEqual(result['scope_summary']['mixed_count'],1)
        self.assertFalse(result['mixed_steps'][0]['matching_eligible'])
        self.assertEqual(result['mixed_steps'][0]['source_event_ids'],['e0','e1'])

    def test_unassigned_and_missing_end_not_guessed(self):
        result=scope_steps(enrich(*self.fixture()),[self.execution('target','e0','','x')],['target'])
        self.assertEqual(result['scope_summary']['total_generated_steps'],1)
        self.assertEqual(result['scope_summary']['unassigned_count'],1)

class GateTests(unittest.TestCase):
    def test_gate_precedes_any_gt_access(self):
        import inspect
        from backend.m02_semantic_candidate import assess
        source=inspect.getsource(assess)
        self.assertLess(source.index('if not approved:'),source.index("truth = read_json(gt_path)"))
        self.assertNotIn('read_json',inspect.getsource(enrich))
        self.assertNotIn('read_json',inspect.getsource(scope_steps))
    def test_pending_and_unbound_gate_do_not_open_gt(self):
        import tempfile
        import json
        from pathlib import Path
        from backend.m02_semantic_candidate import assess, SNAPSHOT
        snapshot = enrich(*SemanticTests().fixture())
        scoped = scope_steps(snapshot, [dict(execution_id='x', business_unit_id='unit', session_id='session', start_event_id='e0', end_event_id='e1')], ['unit'])
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / SNAPSHOT
            directory.mkdir(parents=True)
            (directory/'business_steps.json').write_bytes(canonical_bytes(snapshot))
            (directory/'scope.json').write_bytes(canonical_bytes(scoped))
            from test_m02_semantic_comparator import dependency_fixture
            manifest = dependency_fixture(Path(temp))
            manifest.update(stage='PRE_GT_COMPARISON', score_computed=False,
                outputs={}, model_version='synthetic', serializer_version='synthetic')
            (directory/'manifest.json').write_bytes(canonical_bytes(manifest))
            result, rows = assess(temp)
            self.assertEqual(result['status'], 'NOT_CONFIGURED')
            self.assertIsNone(result['score'])
            self.assertEqual(sum(row['row_type']=='generated_step' for row in rows), 2)
            (directory/'independent_verification.json').write_text(json.dumps(dict(verdict='PASS', snapshot_manifest_sha256='wrong')))
            self.assertIsNone(assess(temp)[0]['score'])
