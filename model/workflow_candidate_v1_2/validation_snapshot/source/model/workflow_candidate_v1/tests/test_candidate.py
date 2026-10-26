"""Temporary synthetic fixtures only; never official evidence."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
import torch
from model.workflow_candidate_v1.src.data import load_logical,sha,sanitize_raw,boundary_labels
from model.workflow_candidate_v1.src.features import normalize,normalized_path,event_vector,features,semantic_text,hash_tokens
from model.workflow_candidate_v1.src.neural import BoundaryGRU,seed_all,train,predict,save_model,load_model
from model.workflow_candidate_v1.src.analysis import boundary_metrics,segments,represent,cluster,process_maps
from model.workflow_candidate_v1.src.adapter import canonical_for_generator
from model.workflow_candidate_v1.training.run import split_data

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/default.json').read_text())

def event(i,**kwargs):
    e=dict(event_id=f'event-{i}',session_id='session-a',source_dataset='synthetic',event_time=f'2026-01-01 00:00:{i:02}',event_type='DOM_EVENT',interaction_type='click',element_tag='button',api_method='',api_status_code='',api_path='',page_url='/example/items',page_title='Rainbow',target_selector='button')
    e.update(kwargs);return e

def write_csv(p,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

class CandidateTests(unittest.TestCase):
    def setUp(self):
        seed_all(5);self.config=dict(CONFIG,epochs=2)
    def test_volatile_normalization(self):
        self.assertEqual(normalized_path('/api/items/123?secret=value'),'/api/items/:id')
        self.assertEqual(normalized_path('/api/items/456'),'/api/items/:id')
        self.assertEqual(normalize('/a/3fa85f64-5717-4562-b3fc-2c963f66afa6'),'/a/:id')
        self.assertEqual(normalize('/a/2026-10-14'),'/a/:id')
    def test_hash_process_determinism(self):
        a=hash_tokens(['example'],32).tolist()
        cmd='from model.workflow_candidate_v1.src.features import hash_tokens;import json;print(json.dumps(hash_tokens(["example"],32).tolist()))'
        b=json.loads(subprocess.check_output([sys.executable,'-c',cmd],text=True))
        self.assertEqual(a,b)
    def test_new_path_not_unknown(self):
        a=event_vector(event(0,page_url='/new/catalog'),CONFIG)
        b=event_vector(event(0,page_url='/unseen/flow'),CONFIG)
        self.assertFalse(np.array_equal(a,b));self.assertGreater(np.linalg.norm(a),0)
    def test_semantic_privacy(self):
        self.assertEqual(semantic_text(event(0,page_title='Private user data',element_text='secret'),CONFIG),'<redacted-title>')
        a=event_vector(event(0,input_data='Alice',element_text='secret'),CONFIG)
        b=event_vector(event(0,input_data='Bob',element_text='different'),CONFIG)
        np.testing.assert_array_equal(a,b)
    def test_forbidden_feature_invariance(self):
        a=event(0);b=dict(a,business_unit_id='BU99',business_unit_name='Private',repetition='R9',execution_id='BU99-R9',task_name='label',workflow_key='answer',ground_truth='secret')
        np.testing.assert_array_equal(features([a],CONFIG),features([b],CONFIG))
        self.assertNotIn('business_unit_id',sanitize_raw(b,'synthetic'))
    def test_provenance_not_feature(self):
        a=event(0);b=dict(a,event_id='other',session_id='other',source_dataset='other')
        np.testing.assert_array_equal(features([a],CONFIG),features([b],CONFIG))
    def test_causal_features(self):
        a=[event(i) for i in range(4)];b=copy.deepcopy(a);b[3]['page_url']='/changed'
        np.testing.assert_array_equal(features(a,CONFIG)[:3],features(b,CONFIG)[:3])
    def test_boundary_label_first_event(self):
        events=[event(i) for i in range(4)]
        metadata={('synthetic',e['event_id']):{'execution_id':'one' if i<2 else 'two'} for i,e in enumerate(events)}
        self.assertEqual(boundary_labels(events,metadata),[0,0,1,0])
    def test_split_excludes_holdout_context(self):
        ev=[event(i) for i in range(6)]
        md={('synthetic',e['event_id']):{'repetition':'3' if i in [2,3] else '1'} for i,e in enumerate(ev)}
        chunks,masks=split_data([ev],md,[[0,0,1,0,1,0]],lambda r:r['repetition']=='1')
        self.assertEqual([[e['event_id'] for e in s] for s,_ in chunks],[['event-0','event-1'],['event-4','event-5']])
        self.assertEqual(masks,[[False,True,False,False,False,True]])
    def test_weighted_training_and_gru(self):
        ev=[event(i) for i in range(8)]
        model,info=train([(ev,[0,0,0,0,1,0,0,0])],self.config)
        self.assertEqual(info['positive'],1);self.assertEqual(info['negative'],6);self.assertEqual(info['pos_weight'],6)
        logits,h=model(torch.from_numpy(features(ev,CONFIG))[None])
        self.assertEqual(tuple(logits.shape),(1,8));self.assertEqual(tuple(h.shape),(1,8,64))
    def test_save_load_deterministic(self):
        ev=[event(i) for i in range(4)];m=BoundaryGRU(CONFIG).eval()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model.pt';save_model(m,path)
            a=predict(m,[ev],CONFIG);b=predict(load_model(path,CONFIG),[ev],CONFIG)
            np.testing.assert_array_equal(a[0][0],b[0][0]);np.testing.assert_array_equal(a[0][1],b[0][1])
    def test_training_reproducible(self):
        ev=[event(i) for i in range(6)];chunks=[(ev,[0,0,1,0,0,0])]
        a,_=train(chunks,self.config);b,_=train(chunks,self.config)
        for k,v in a.state_dict().items():self.assertTrue(torch.equal(v,b.state_dict()[k]))
    def test_boundary_matching_one_to_one(self):
        m=boundary_metrics([[0,0,1,0]],[[0,1,1,0]],[[False,True,True,True]],1)
        self.assertEqual((m['tp'],m['fp'],m['fn']),(1,1,0))
    def test_never_match_across_sessions(self):
        m=boundary_metrics([[0,1],[0,0]],[[0,0],[0,1]],[[False,True],[False,True]],1)
        self.assertEqual(m['tp'],0)
    def test_segmentation_prediction_only(self):
        stream=[event(i) for i in range(5)]
        w=segments([stream],[[False,False,True,False,False]])
        self.assertEqual([r['event_count'] for r in w],[2,3])
        self.assertEqual([eid for r in w for eid in r['source_event_evidence']],[e['event_id'] for e in stream])
    def test_clustering_reproducibility(self):
        rng=np.random.RandomState(3);x=rng.normal(size=(12,8));x/=np.linalg.norm(x,axis=1,keepdims=True)
        a,da=cluster(x,CONFIG);b,db=cluster(x,CONFIG)
        np.testing.assert_array_equal(a,b);self.assertEqual(da,db)
    def test_process_provenance_adapter(self):
        ev=[event(0,interaction_type='page_view'),event(1,interaction_type='change',element_tag='input'),event(2,interaction_type='change',element_tag='input'),event(3,interaction_type='submit')]
        wf=segments([ev],[[False]*4]);tables=process_maps(wf,np.array([0]),[ev],np.ones((1,4))/2)
        self.assertEqual(len(tables['process_steps']),3)
        self.assertEqual(tables['node_inputs'][0]['input_value'],'<redacted>')
        ids=[i for s in tables['process_steps'] for i in s['source_event_evidence']]
        self.assertEqual(ids,[e['event_id'] for e in ev])
        canonical=canonical_for_generator(tables,'PM-001')
        self.assertNotIn('business_unit_id',canonical);self.assertEqual(len(canonical['procedures']),3)
    def test_embedding_dimension_and_evidence(self):
        ev=[event(i) for i in range(4)]
        wf=segments([ev],[[False,False,True,False]])
        hidden=[np.ones((4,64),dtype=np.float32)]
        x,sig=represent(wf,[ev],hidden,CONFIG)
        self.assertEqual(x.shape,(2,384))
        np.testing.assert_allclose(np.linalg.norm(x,axis=1),1,atol=1e-6)
        self.assertEqual(len(sig),2)
    def test_raw_inference_without_execution_manifest(self):
        from model.workflow_candidate_v1.src.infer import infer_csv
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);art=root/'artifacts';art.mkdir()
            (art/'model_config.json').write_text(json.dumps(CONFIG))
            model=BoundaryGRU(CONFIG).eval();save_model(model,art/'model.pt')
            raw=root/'events.csv';write_csv(raw,[event(i) for i in range(6)])
            a=infer_csv(raw,art);b=infer_csv(raw,art)
            self.assertEqual(a,b)
            self.assertEqual(sum(w['event_count'] for w in a['workflows']),6)
            self.assertFalse((root/'execution_manifest.csv').exists())
    def test_reject_single_class_training(self):
        with self.assertRaises(ValueError):
            train([([event(i) for i in range(4)],[0,0,0,0])],self.config)
    def test_logical_reconstruction_and_hash_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dataset=root/'logical';dataset.mkdir();raw=root/'events.csv'
            ev=[event(i) for i in range(4)];write_csv(raw,ev)
            executions=[];index=[]
            for i in range(2):
                a,b=ev[2*i],ev[2*i+1]
                executions.append(dict(execution_id=f'E{i}',business_unit_id=f'B{i}',repetition='1',active='true',event_count='2',start_event_id=a['event_id'],end_event_id=b['event_id'],start_time=a['event_time'],end_time=b['event_time']))
                index.extend(dict(execution_id=f'E{i}',source_dataset='synthetic',event_id=e['event_id'],source_session_id='session-a') for e in [a,b])
            write_csv(dataset/'execution_manifest.csv',executions);write_csv(dataset/'execution_event_index.csv',index)
            manifest=dict(official=False,sources={'synthetic':{'files':[dict(path='events.csv',sha256=sha(raw),row_count=4)]}},files=[dict(path=p.name,sha256=sha(p)) for p in dataset.glob('*.csv')])
            (dataset/'dataset_manifest.json').write_text(json.dumps(manifest))
            streams,md,_=load_logical(root,dataset)
            self.assertEqual(len(streams),1);self.assertEqual(len(streams[0]),4)
            self.assertNotIn('execution_id',streams[0][0]);self.assertEqual(len(md),4)
            raw.write_text(raw.read_text()+'\n')
            with self.assertRaises(ValueError):load_logical(root,dataset)

if __name__=='__main__':unittest.main()
