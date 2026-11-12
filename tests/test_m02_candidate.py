"""Temporary synthetic fixtures only; never official KTL evidence."""
import copy
import tempfile
import unittest
from backend.m02_candidate import serialize_maps
from backend.evaluators import EvaluationError, M02Evaluator

class CandidateSerializationTests(unittest.TestCase):
    def fixture(self):
        return ([{'process_model_id':'P','canonical_instance_id':'W',
                  'canonical_node_sequence':['N','N']},
                 {'process_model_id':'EXTRA','canonical_instance_id':'E',
                  'canonical_node_sequence':['E']}],
                [{'node_id':'N','process_model_id':'P','action':'input','page_path':'/x',
                  'target_role':'input_control','http_method':'','normalized_endpoint':'',
                  'source_event_evidence':['not-a-direct-label']},
                 {'node_id':'E','process_model_id':'EXTRA','action':'selection','page_path':'/y',
                  'target_role':'button','http_method':'','normalized_endpoint':''}])

    def test_preserves_every_occurrence_and_unpaired_map(self):
        models,nodes=self.fixture();out=serialize_maps(models,nodes,{'BU':'P'})
        self.assertEqual([len(p['procedures']) for p in out['processes']],[2,1])
        self.assertEqual([p['id'] for p in out['processes']],['BU','EXTRA'])
        self.assertEqual(len({s['id'] for s in out['processes'][0]['procedures']}),2)

    def test_auxiliary_evidence_never_creates_label(self):
        models,nodes=self.fixture();before=copy.deepcopy((models,nodes))
        out=serialize_maps(models,nodes,{'BU':'P'})
        self.assertTrue(all('not-a-direct-label' not in s['label'] for p in out['processes'] for s in p['procedures']))
        self.assertEqual(out['processes'][0]['procedures'][0]['label'],'input|/x|input_control||')
        self.assertEqual((models,nodes),before)

    def test_future_direct_label_supported_without_reduction(self):
        models,nodes=self.fixture();nodes[0]['direct_label']='input'
        out=serialize_maps(models,nodes,{'BU':'P'})
        gt={'processes':[{'id':'BU','procedures':[{'id':'G','label':'input'}]}]}
        _,_,d,_=M02Evaluator().evaluate(out,gt)
        self.assertEqual(d['correctly_mapped'],1)
        self.assertEqual(d['evaluated_procedures'],3)

    def test_invalid_references_and_duplicate_mapping_rejected(self):
        models,nodes=self.fixture()
        with self.assertRaises(EvaluationError):serialize_maps(models,nodes,{'A':'P','B':'P'})
        models[0]['canonical_node_sequence'].append('MISSING')
        with self.assertRaises(EvaluationError):serialize_maps(models,nodes,{'A':'P'})

class CandidateAssessmentTests(unittest.TestCase):
    def fixture_root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def bundle(self,status):
        models,nodes=CandidateSerializationTests().fixture()
        generated=serialize_maps(models,nodes,{'BU':'P'})
        truth={'version':'synthetic','status':status,'processes':[
            {'id':'BU','business_name':'synthetic','procedures':[
                {'id':'G','label':'input','step_order':1,'menu_screen_name':'test',
                 'allowed_aliases':['input|/x|input_control||']}]}]}
        manifest={'model_version':'synthetic','identity_mapping_basis':'synthetic only',
                  'representation':'canonical occurrences','process_identity_mapping':{'BU':'P'}}
        return manifest,generated,truth,{},2

    def test_unresolved_mapping_never_becomes_zero_score(self):
        from unittest.mock import patch
        from backend.m02_candidate import assess
        with patch('backend.m02_candidate.load_bundle',return_value=self.bundle('DIRECT_MAPPING_UNRESOLVED')):
            result,rows=assess(self.fixture_root())
        self.assertIsNone(result['score'])
        self.assertIsNone(result['details']['per_business_unit'][0]['accuracy'])
        self.assertEqual(result['status'],'NOT_CONFIGURED')
        self.assertEqual(sum(r['row_type']=='generated_step' for r in rows),3)
        self.assertEqual(sum(r['row_type']=='required_step' for r in rows),1)

    def test_validated_mapping_uses_all_maps_in_global_denominator(self):
        from unittest.mock import patch
        from backend.m02_candidate import assess
        with patch('backend.m02_candidate.load_bundle',return_value=self.bundle('VALIDATED_DIRECT_MAPPING')):
            result,rows=assess(self.fixture_root())
        self.assertEqual(result['status'],'COMPLETED')
        self.assertAlmostEqual(result['score'],(10000/3)**0.5)
        self.assertEqual(result['details']['evaluated_procedures'],3)
        self.assertEqual(result['details']['correctly_mapped'],1)


    def test_csv_ledger_recalculates_score_and_retains_repeat_unpaired_missing(self):
        import math
        from unittest.mock import patch
        from backend.m02_candidate import assess
        from backend.evaluators import csv_evidence
        import csv, io
        bundle=list(self.bundle('VALIDATED_DIRECT_MAPPING'))
        bundle[2]['processes'][0]['procedures'].append(dict(
            id='ABSENT', label='absent', step_order=2, menu_screen_name='test', allowed_aliases=[]))
        with patch('backend.m02_candidate.load_bundle',return_value=bundle):
            result,rows=assess(self.fixture_root())
        exported=list(csv.DictReader(io.StringIO(csv_evidence(rows).lstrip('\ufeff'))))
        actual=[r for r in exported if r['row_type']=='generated_step']
        required=[r for r in exported if r['row_type']=='required_step']
        aggregate=next(r for r in exported if r['row_type']=='aggregate_calculation')
        self.assertEqual(len(actual),3)
        self.assertEqual(len({r['id'] for r in actual}),3)
        self.assertTrue(all(r['technical_signature'] and r['node_id'] for r in actual))
        self.assertEqual(sum(r['match_status']=='MATCHED' for r in actual),1)
        self.assertEqual(sum(r['match_status']=='MISSING' for r in required),1)
        hit=next(r for r in actual if r['match_status']=='MATCHED')
        self.assertEqual(hit['matched_required_step_id'],'G')
        self.assertEqual(required[0]['matched_generated_id'],hit['id'])
        self.assertTrue(any(r['process_id']=='EXTRA' and r['match_status']=='UNMATCHED' for r in actual))
        score=math.sqrt((100*float(aggregate['accuracy_numerator'])/float(aggregate['accuracy_denominator']))*
                        (100*float(aggregate['completeness_numerator'])/float(aggregate['completeness_denominator'])))
        self.assertAlmostEqual(score,result['score'])
        self.assertEqual(float(aggregate['accuracy_denominator']),len(actual))
        self.assertEqual(float(aggregate['completeness_denominator']),len(required))


class BusinessStepAdapterTests(unittest.TestCase):
    def snapshot(self):
        return dict(serializer_version='synthetic', generated_business_step_count=2, processes=[
            dict(source_process_id=pid,canonical_instance_id=pid, business_steps=[dict(
                generated_step_id=pid+'-B001',step_order=1,action_type='SELECT',menu_page='/new',
                target='button',http_method='',endpoint='',source_node_ids=[pid+'-N'],
                source_event_ids=['e'],evidence=[{'label':'never promote'}])],
                unlinked_technical_evidence=[{'technical_evidence_id':pid+'-T', 'action_type':'HTTP_WRITE'}])
            for pid in ['P','EXTRA']])

    def test_business_denominator_and_no_auxiliary_direct_labels(self):
        from backend.m02_candidate import adapt_business_steps
        source=self.snapshot(); before=copy.deepcopy(source)
        generated=adapt_business_steps(source,{'BU':'P'})
        self.assertEqual(source,before)
        self.assertEqual([p['id'] for p in generated['processes']],['BU','EXTRA'])
        self.assertEqual(sum(len(p['procedures']) for p in generated['processes']),2)
        self.assertTrue(all(s['label']=='SELECT|/new|button||' for p in generated['processes'] for s in p['procedures']))
        self.assertEqual(sum(len(p['unlinked_technical_evidence']) for p in generated['processes']),2)
        truth={'processes':[{'id':'BU','procedures':[{'id':'G','label':'SELECT|/new|button||'}]}]}
        _,_,stats,_=M02Evaluator().evaluate(generated,truth)
        self.assertEqual(stats['evaluated_procedures'],2)
        self.assertEqual(stats['correctly_mapped'],1)

    def test_invalid_count_or_pairing_fails_closed(self):
        from backend.m02_candidate import adapt_business_steps
        s=self.snapshot();s['generated_business_step_count']=1
        with self.assertRaises(EvaluationError):adapt_business_steps(s,{'BU':'P'})
        with self.assertRaises(EvaluationError):adapt_business_steps(self.snapshot(),{'A':'P','B':'P'})
