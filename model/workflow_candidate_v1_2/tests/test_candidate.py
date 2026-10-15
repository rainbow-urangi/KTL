"""Synthetic temporary fixtures only; no production dataset mutation."""
import copy,json,tempfile
from pathlib import Path
import unittest
import numpy as np
import torch
from model.workflow_candidate_v1.src.data import sha
from model.workflow_candidate_v1.src.analysis import segments
from model.workflow_candidate_v1.src.neural import BoundaryGRU as Encoder
from model.workflow_candidate_v1_1.src.audit import process_audit
from model.workflow_candidate_v1_2.src.features import features,decisions,EXTRA_NAMES
from model.workflow_candidate_v1_2.src.neural import BoundaryGRU,seed_all,train,predict,save_model,load_model
from model.workflow_candidate_v1_2.src.process_map import process_maps
from model.workflow_candidate_v1_2.src.adapter import canonical_for_generator
from model.workflow_candidate_v1_2.src.infer import infer_events
from model.workflow_candidate_v1_2.src.failures import inspect_errors

BASE=Path(__file__).resolve().parents[1]
CFG=json.loads((BASE/'config/model.json').read_text())
OLD=json.loads((BASE.parent/'workflow_candidate_v1/config/default.json').read_text())
REP=json.loads((BASE.parent/'workflow_candidate_v1_1/config/representation.json').read_text())

def event(i,**kw):
    e=dict(event_id=f'e{i}',source_dataset='synthetic',session_id='s',event_time=f'2026-01-01 00:00:{i:02}',event_type='DOM_EVENT',interaction_type='click',element_tag='button',api_method='',api_path='',api_status_code='',page_url='/example/items',page_title='Rainbow',target_selector='button')
    e.update(kw);return e

def extra(x,name,i=0):return x[i,396+EXTRA_NAMES.index(name)]

class CandidateTests(unittest.TestCase):
    def setUp(self):seed_all(3)
    def test_feature_shape(self):
        self.assertEqual(features([event(0),event(1)],CFG).shape,(2,428))
    def test_no_business_or_private_value_features(self):
        ev=[event(0),event(1)];changed=copy.deepcopy(ev)
        for e in changed:e.update(business_unit_id='BU99',repetition='R3',task_name='SECRET',input_data='private',element_text='private',execution_id='GT')
        np.testing.assert_array_equal(features(ev,CFG),features(changed,CFG))
    def test_direct_popup_signal(self):
        x=features([event(0),event(1,interaction_type='popup_open')],CFG)
        self.assertEqual(extra(x,'next_popup_open_direct'),1)
    def test_next_user_action_stops_popup_attribution(self):
        ev=[event(0),event(1,event_time='2026-01-01 00:00:00.200'),event(2,event_time='2026-01-01 00:00:00.300',interaction_type='popup_open')]
        x=features(ev,CFG)
        self.assertEqual(extra(x,'next_popup_open_direct',0),0);self.assertEqual(extra(x,'next_popup_open_direct',1),1)
    def test_lookahead_time_bound(self):
        x=features([event(0),event(2,interaction_type='popup_open')],CFG)
        self.assertEqual(extra(x,'next_popup_open_direct'),0)
    def test_lookahead_event_bound(self):
        ev=[event(0)]+[event(i,event_time=f'2026-01-01 00:00:00.{i}00',interaction_type='screen_change') for i in range(1,4)]+[event(4,event_time='2026-01-01 00:00:00.400',interaction_type='popup_open')]
        self.assertEqual(extra(features(ev,CFG),'next_popup_open_direct'),0)
    def test_popup_state_and_recent_close(self):
        ev=[event(0,interaction_type='popup_open'),event(1,interaction_type='change'),event(2,interaction_type='popup_close'),event(3)]
        x=features(ev,CFG)
        self.assertEqual(extra(x,'input_inside_popup',1),1);self.assertEqual(extra(x,'popup_active_before',3),0);self.assertEqual(extra(x,'recent_popup_close',3),1)
    def test_method_and_family_features(self):
        ev=[event(0,api_method='POST',api_path='/api/objects',api_status_code='201'),event(1,api_method='GET',api_path='/api/objects/3',api_status_code='200')]
        x=features(ev,CFG);self.assertEqual(extra(x,'current_post'),1);self.assertEqual(extra(x,'last_api_family_change',1),1);self.assertEqual(extra(x,'recent_mutation',1),1)
    def test_terminal_guard_keeps_evidence(self):
        ev=[event(0),event(1,interaction_type='page_close')];p=[np.array([0.,.99])]
        cuts=decisions(p,[ev],CFG);w=segments([ev],cuts)
        self.assertEqual(len(w),1);self.assertEqual(w[0]['event_count'],2)
    def test_gru_architecture_and_training(self):
        ev=[event(i) for i in range(6)];model,stats=train([(ev,[0,0,1,0,0,0])],dict(CFG,epochs=2))
        self.assertEqual(model.gru.hidden_size,64);self.assertEqual(model.gru.num_layers,1);self.assertEqual(model.head[0].out_features,32)
        self.assertEqual(stats['positive'],1);self.assertEqual(stats['negative'],4)
        logits,h=model(torch.from_numpy(features(ev,CFG))[None]);self.assertEqual(tuple(h.shape),(1,6,64))
    def test_save_load_and_training_reproducible(self):
        chunks=[([event(i) for i in range(5)],[0,0,1,0,0])];cfg=dict(CFG,epochs=2)
        a,_=train(chunks,cfg);b,_=train(chunks,cfg)
        for k in a.state_dict():self.assertTrue(torch.equal(a.state_dict()[k],b.state_dict()[k]))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'m.pt';save_model(a,path)
            np.testing.assert_array_equal(predict(a,[chunks[0][0]],cfg)[0][0],predict(load_model(path,cfg),[chunks[0][0]],cfg)[0][0])
    def test_http_method_identity_and_compression(self):
        ev=[event(i,interaction_type='api_transaction',api_path='/api/resource',api_method=m,api_status_code='200') for i,m in enumerate(['GET','GET','POST','PATCH','GET'])]
        wf=segments([ev],[[False]*len(ev)]);t=process_maps(wf,np.array([0]),[ev],np.ones((1,4))/2)
        self.assertEqual(len(t['process_nodes']),3);self.assertEqual(len(t['process_steps']),4)
        self.assertEqual(t['process_steps'][0]['source_event_evidence'],['e0','e1'])
        self.assertEqual({n['http_method'] for n in t['process_nodes']},{'GET','POST','PATCH'})
        canonical=canonical_for_generator(t,'PM-001');self.assertEqual([p['http_method'] for p in canonical['procedures']],['GET','POST','PATCH','GET'])
        self.assertTrue(all(p['target']['normalized_endpoint']=='/api/resource' for p in canonical['procedures']))
    def test_cross_business_method_audit_zero(self):
        ev=[event(0,interaction_type='api_transaction',api_method='GET',api_path='/api/objects',api_status_code='200'),event(1,interaction_type='api_transaction',api_method='POST',api_path='/api/objects',api_status_code='201')]
        wf=segments([ev],[[False,True]]);t=process_maps(wf,np.array([0,0]),[ev],np.ones((2,4))/2)
        md={('synthetic',e['event_id']):{'business_unit_id':f'B{i}','execution_id':f'E{i}'} for i,e in enumerate(ev)}
        audit=process_audit(t,wf,[ev],md)
        self.assertEqual(audit['summary']['all_read_write_collision_nodes'],0)
    def test_error_analysis_anonymous_and_classification(self):
        ev=[event(i) for i in range(5)];md={('synthetic',e['event_id']):{'execution_id':'BU99-R1' if i<3 else 'BU98-R1'} for i,e in enumerate(ev)}
        cuts=[np.array([False,False,True,False,False])];wf=segments([ev],cuts)
        err,windows,_=inspect_errors([ev],md,[[0,0,0,1,0]],cuts,wf,OLD)
        self.assertEqual(len(err),2);self.assertTrue(any('CROSS_WORKFLOW_MERGE' in r['categories'] for r in err))
        self.assertNotIn('BU99',json.dumps(err));self.assertNotIn('BU98',json.dumps(windows))
    def test_raw_inference_without_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);save_model(BoundaryGRU(CFG),p/'model.pt');save_model(Encoder(OLD),p/'representation_encoder.pt')
            for name,data in [('model_config.json',CFG),('representation_encoder_config.json',OLD),('representation_config.json',REP)]:
                (p/name).write_text(json.dumps(data))
            (p/'model_manifest.json').write_text(json.dumps({'artifact_sha256':{f.name:sha(f) for f in p.iterdir()}}))
            ev=[event(i) for i in range(6)];a=infer_events([ev],p);b=infer_events([ev],p)
            self.assertEqual(a,b);self.assertEqual(sum(w['event_count'] for w in a['workflows']),6)
            self.assertTrue(a['offline']);self.assertFalse((p/'execution_manifest.csv').exists())

if __name__=='__main__':unittest.main()
