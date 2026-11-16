"""Synthetic fixtures only; transport preservation, not semantic comparison."""
import copy,csv,io,json,unittest
import test_semantic_enrichment as fixtures
from backend.semantic_enrichment import enrich,allowed_event,RULES_HASH
from backend.m02_provenance_restore import restore,additions
from backend.evaluators import csv_evidence

class ProvenanceTests(unittest.TestCase):
    def fixture(self):
        args=fixtures.SemanticTests().fixture(('Field',))
        c=args[3][0]['locators_json']
        c['event_context'].update(event_id='raw-exact',related_event_id='related',parent_event_id='parent',cause_event_id='cause',related_interaction_id='i-related')
        c['popup_context']={'active_popup_id':'popup','opener_event_id':'open','opener_interaction_id':'i-open',
            'closer_event_id':'close','closer_interaction_id':'i-close','target_popup':{'popup_id':'popup',
            'opened_by_event_id':'opened','opened_by_interaction_id':'i-opened'}}
        c['api_context']={'request_id':'request','related_event_id':'api-event','related_interaction_id':'api-interaction','related_strategy':'recent_action_fallback','method':'POST','status':200}
        return args
    def test_raw_enrichment_serializer_csv_exact_same_ids_and_strategy(self):
        args=self.fixture();result=enrich(*args);event=result['raw_evidence_ledger'][0]
        self.assertEqual(event,allowed_event(args[3][0]))
        self.assertEqual(result['serializer_rules_hash'],RULES_HASH)
        for entry in [result['processes'][0]['business_steps'][0]['evidence'][0],event]:
            self.assertEqual(entry['event']['cause_event_id'],'cause')
            self.assertEqual(entry['popup']['opener_event_id'],'open')
            self.assertEqual(entry['popup']['target_popup']['opened_by_event_id'],'opened')
            self.assertEqual(entry['api']['related_event_id'],'api-event')
            self.assertEqual(entry['api']['related_strategy'],'recent_action_fallback')
        text=csv_evidence([dict(row_type='generated_step',**result['processes'][0]['business_steps'][0])])
        row=next(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))));roundtrip=json.loads(row['evidence'])[0]
        self.assertEqual(roundtrip,event)
    def test_additions_only_deterministic_no_input_mutation_or_new_step(self):
        args=self.fixture();snapshot=enrich(*args)
        def legacy(v):
            if isinstance(v,list):return [legacy(x) for x in v]
            if not isinstance(v,dict):return v
            return {k:legacy(x) for k,x in v.items() if k not in ('api','event_id','related_event_id','parent_event_id','cause_event_id','related_interaction_id','opener_event_id','opener_interaction_id','closer_event_id','closer_interaction_id','opened_by_event_id','opened_by_interaction_id')}
        # Strip only newly preserved payload fields, retaining event identity.
        for e in snapshot['raw_evidence_ledger']+snapshot['processes'][0]['business_steps'][0]['evidence']:
            for key in ['event','popup']:e[key]=legacy(e[key])
            e.pop('api',None)
        snapshot['processes'][0]['business_steps'][0]['popup']=legacy(snapshot['processes'][0]['business_steps'][0]['popup'])
        before=copy.deepcopy((snapshot,args[3]));result,audit=restore(snapshot,args[3])
        self.assertEqual((result,audit),restore(snapshot,args[3]));self.assertEqual((snapshot,args[3]),before)
        self.assertEqual(result['generated_business_step_count'],1);self.assertEqual(result['serializer_rules_hash'],snapshot['serializer_rules_hash'])
        self.assertTrue(audit);self.assertEqual(restore(result,args[3])[1],[])
        self.assertEqual(result['processes'][0]['business_steps'][0]['source_event_ids'],['e0'])
    def test_missing_fields_do_not_invent_causal_relationships(self):
        args=fixtures.SemanticTests().fixture(('Field',));result=enrich(*args)
        event=result['raw_evidence_ledger'][0]
        self.assertNotIn('cause_event_id',event['event']);self.assertNotIn('opener_event_id',event['popup'])
        self.assertNotIn('related_event_id',event['api'])
        restored,audit=restore(result,args[3]);self.assertEqual(restored,result);self.assertEqual(audit,[])
    def test_existing_field_change_missing_identity_duplicate_rejected(self):
        with self.assertRaises(ValueError):additions({'id':'old'},{'id':'new'})
        args=self.fixture();snapshot=enrich(*args)
        args[3][0]['locators_json']['event_context']['cause_event_id']='different'
        with self.assertRaises(ValueError):restore(snapshot,args[3])
        with self.assertRaises(ValueError):restore(snapshot,[])
        with self.assertRaises(ValueError):restore(snapshot,args[3]*2)
if __name__=='__main__':unittest.main()
