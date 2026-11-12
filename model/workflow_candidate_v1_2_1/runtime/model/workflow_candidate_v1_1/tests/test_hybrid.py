"""Temporary synthetic fixtures; no official evidence or source mutation."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from model.workflow_candidate_v1.src.analysis import segments,process_maps,cluster
from model.workflow_candidate_v1.src.data import sha
from model.workflow_candidate_v1.src.features import normalized_path
from model.workflow_candidate_v1.src.neural import BoundaryGRU,save_model,seed_all
from model.workflow_candidate_v1_1.src.representation import sequence_vector,combine,components,generic_actions
from model.workflow_candidate_v1_1.src.audit import process_audit,business_summary
from model.workflow_candidate_v1_1.src.infer import infer_events

BASE=Path(__file__).resolve().parents[1]
CFG=json.loads((BASE/'config/representation.json').read_text())
NEURAL=json.loads((BASE.parent/'workflow_candidate_v1/config/default.json').read_text())

def event(i,**kwargs):
    e=dict(event_id=f'e{i}',source_dataset='synthetic',session_id='s',event_time=f'2026-01-01 00:00:{i:02}',event_type='DOM_EVENT',interaction_type='click',element_tag='button',api_method='',api_path='',api_status_code='',page_url='/example/items',page_title='Rainbow',target_selector='button')
    e.update(kwargs);return e

class HybridTests(unittest.TestCase):
    def test_volatile_endpoint(self):
        self.assertEqual(normalized_path('/api/items/3'),normalized_path('/api/items/4'))
        self.assertEqual(normalized_path('/api/items/3?value=private'),'/api/items/:id')
    def test_sequence_order(self):
        self.assertFalse(np.array_equal(sequence_vector(['input','submit','close'],CFG),sequence_vector(['close','submit','input'],CFG)))
    def test_duplicate_burst_collapsed(self):
        np.testing.assert_array_equal(sequence_vector(['input']*100+['submit'],CFG),sequence_vector(['input','submit'],CFG))
    def test_empty_block(self):
        self.assertAlmostEqual(float(np.linalg.norm(sequence_vector([],CFG))),1,places=6)
    def test_http_method_identity(self):
        self.assertNotEqual(generic_actions(event(1,api_method='GET',api_path='/api/items')),generic_actions(event(1,api_method='POST',api_path='/api/items')))
        self.assertIn('read_detail',generic_actions(event(1,api_method='GET',api_path='/api/items/3')))
    def test_block_weights(self):
        blocks={'a':np.array([[1.,0.]]),'b':np.array([[0.,1.]])}
        result=combine(blocks,{'a':0.25,'b':0.75})
        self.assertAlmostEqual(float(np.sum(result[0,:2]**2)),0.25)
        self.assertAlmostEqual(float(np.sum(result[0,2:]**2)),0.75)
        with self.assertRaises(ValueError):combine(blocks,{'a':1.,'b':1.})
    def test_no_metadata_or_input_leakage(self):
        ev=[event(i) for i in range(3)];workflows=segments([ev],[[False]*3]);h=[np.ones((3,64),np.float32)];legacy=np.ones((1,384),np.float32)
        a,sa=components(workflows,[ev],h,legacy,CFG)
        changed=copy.deepcopy(ev)
        for e in changed:e.update(business_unit_id='BU99',business_unit_name='secret',repetition='3',task_name='label',input_data='private',element_text='user value',ground_truth='forbidden')
        b,sb=components(workflows,[changed],h,legacy,CFG)
        for k in a:np.testing.assert_array_equal(a[k],b[k])
        self.assertEqual(sa,sb)
    def test_dimensions(self):
        ev=[event(i) for i in range(3)];workflows=segments([ev],[[False]*3]);blocks,_=components(workflows,[ev],[np.ones((3,64),np.float32)],np.ones((1,384),np.float32),CFG)
        expected=[128,384,640,1152]
        for (name,weights),dim in zip(CFG['candidates'].items(),expected):
            x=combine(blocks,weights);self.assertEqual(x.shape,(1,dim));self.assertAlmostEqual(float(np.linalg.norm(x)),1,places=5)
    def test_reproducible_clustering(self):
        x=np.random.RandomState(1).normal(size=(9,32));x/=np.linalg.norm(x,axis=1,keepdims=True)
        a,da=cluster(x,CFG);b,db=cluster(x,CFG)
        np.testing.assert_array_equal(a,b);self.assertEqual(da,db)
    def test_map_method_collision(self):
        ev=[event(0,interaction_type='api_transaction',api_method='GET',api_path='/api/items',api_status_code='200'),event(1,interaction_type='api_transaction',api_method='POST',api_path='/api/items',api_status_code='201')]
        wf=segments([ev],[[False,True]])
        tables=process_maps(wf,np.array([0,0]),[ev],np.ones((2,2))/np.sqrt(2))
        md={('synthetic',e['event_id']):{'business_unit_id':f'B{i}','execution_id':f'E{i}'} for i,e in enumerate(ev)}
        audit=process_audit(tables,wf,[ev],md)
        self.assertEqual(audit['summary']['cross_business_method_collision_nodes'],1)
        self.assertEqual(audit['summary']['B_models'],1)
        self.assertTrue(audit['models'][0]['all_observed_paths_reconstructable'])
    def test_preserved_family_is_not_automatic_failure(self):
        ev=[event(0,interaction_type='page_view'),event(1),event(2,interaction_type='page_view'),event(3),event(4,interaction_type='popup_open')]
        wf=segments([ev],[[False,False,True,False,False]])
        tables=process_maps(wf,np.array([0,0]),[ev],np.ones((2,2))/np.sqrt(2))
        md={('synthetic',e['event_id']):{'business_unit_id':'B1' if i<2 else 'B2','execution_id':'E1' if i<2 else 'E2'} for i,e in enumerate(ev)}
        audit=process_audit(tables,wf,[ev],md)
        self.assertEqual(audit['summary']['A_models'],1);self.assertEqual(audit['summary']['B_models'],0)
    def test_unobserved_graph_recombination_detected(self):
        ev=[event(0,interaction_type='page_view'),event(1),event(2,interaction_type='change',element_tag='input'),event(3,interaction_type='popup_open'),event(4),event(5,interaction_type='popup_close')]
        wf=segments([ev],[[False,False,False,True,False,False]])
        tables=process_maps(wf,np.array([0,0]),[ev],np.ones((2,2))/np.sqrt(2))
        md={('synthetic',e['event_id']):{'business_unit_id':'B1' if i<3 else 'B2','execution_id':'E1' if i<3 else 'E2'} for i,e in enumerate(ev)}
        audit=process_audit(tables,wf,[ev],md)
        self.assertEqual(audit['summary']['cross_business_unobserved_triples'],2)
        self.assertEqual(audit['summary']['B_models'],1)
        self.assertEqual(audit['summary']['cross_business_method_collision_nodes'],0)
    def test_fragment_metric_counts_minor_fragments(self):
        ev=[event(i) for i in range(4)];wf=segments([ev],[[False,False,True,False]])
        md={('synthetic',e['event_id']):{'business_unit_id':'B1','execution_id':'E1','repetition':'1'} for e in ev}
        b=business_summary(wf,np.array([0,1]),[ev],md)
        self.assertEqual(b['fragmented_bus'],1);self.assertEqual(b['primary_fragmented_bus'],0)
    def test_raw_inference_no_execution_manifest(self):
        seed_all(1)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save_model(BoundaryGRU(NEURAL),root/'model.pt')
            (root/'model_config.json').write_text(json.dumps(NEURAL));(root/'representation_config.json').write_text(json.dumps(CFG))
            (root/'selected_model.json').write_text(json.dumps({'candidate':'C_full','boundary_weights_sha256':sha(root/'model.pt')}))
            stream=[event(i) for i in range(6)]
            a=infer_events([stream],root);b=infer_events([stream],root)
            self.assertEqual(a,b);self.assertEqual(sum(w['event_count'] for w in a['workflows']),6)
            self.assertFalse((root/'execution_manifest.csv').exists())
            (root/'model.pt').write_bytes(b'bad')
            with self.assertRaises(ValueError):infer_events([stream],root)

if __name__=='__main__':unittest.main()
