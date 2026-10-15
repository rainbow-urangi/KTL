"""개발 runner와 외부 수신 계약. 임시 synthetic fixture만 사용합니다."""
import ast
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.server import Service
from backend.evaluators import EvaluationError,digest
from backend.external_results import calculate
from backend.model_runner import checked_files,EvaluationModelRunner
from backend.model_runner.evaluation import temporal_mapping,evaluate_run
from backend.model_runner.forward import encode,consensus_guard

ROOT=Path(__file__).resolve().parents[1]
COUNTS={
'M01':dict(defined_required_event_count=100,collected_required_event_count=95,total_collected_event_count=110,required_field_count=5,missing_required_field_count=11,defined_event_type_count=10,collected_event_type_count=9),
'M04':dict(total_execution_count=3,successful_execution_count=2),
'M07':dict(generation_request_count=4,generated_code_count=3,syntax_pass_count=2,execution_pass_count=2,both_pass_count=1)}

def payload(metric):
    return dict(external_run_id='test-'+metric,dataset_id='fixture',run_mode='DEVELOPMENT',source_module='test-only',source_version='1',submitted_at='2026-10-08T00:00:00Z',dataset_manifest_sha256='0'*64,details={},counts=copy.deepcopy(COUNTS[metric]))

def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

class ExternalTests(unittest.TestCase):
    def test_scores_and_denominators(self):
        for metric,expected in [('M01',94.9),('M04',200/3),('M07',100/3)]:
            p=payload(metric);p['score']=100
            self.assertAlmostEqual(calculate(metric,p)[0],expected)
    def test_invalid_counts_and_missing(self):
        for metric in COUNTS:
            for key in COUNTS[metric]:
                p=payload(metric);del p['counts'][key]
                with self.assertRaises(EvaluationError):calculate(metric,p)
                for invalid in [-1,True,1.5]:
                    p=payload(metric);p['counts'][key]=invalid
                    with self.assertRaises(EvaluationError):calculate(metric,p)
        for metric,key in [('M01','defined_required_event_count'),('M01','total_collected_event_count'),('M01','required_field_count'),('M01','defined_event_type_count'),('M04','total_execution_count'),('M07','generation_request_count')]:
            p=payload(metric);p['counts'][key]=0
            with self.assertRaises(EvaluationError):calculate(metric,p)
    def test_relationships(self):
        for metric,key,value in [('M01','collected_required_event_count',101),('M01','missing_required_field_count',551),('M01','collected_event_type_count',11),('M04','successful_execution_count',4),('M07','generated_code_count',5),('M07','both_pass_count',3),('M07','both_pass_count',0),('M07','syntax_pass_count',4)]:
            p=payload(metric);p['counts'][key]=value
            with self.assertRaises(EvaluationError):calculate(metric,p)
    def test_failed_cases_stay_denominator(self):
        p=payload('M04');p['cases']=[dict(case_id=str(i),status=v) for i,v in enumerate(['PASS','PASS','FAIL'])]
        self.assertAlmostEqual(calculate('M04',p)[0],200/3)
        p['cases'].pop()
        with self.assertRaises(EvaluationError):calculate('M04',p)
    def test_m07_cases(self):
        p=payload('M07');p['cases']=[dict(case_id=str(i),generation_status=g,syntax_status=s,execution_status=e,final_status=f) for i,(g,s,e,f) in enumerate([
            ('PASS','PASS','PASS','PASS'),('PASS','PASS','FAIL','FAIL'),('PASS','FAIL','PASS','FAIL'),('FAIL','SKIPPED','SKIPPED','FAIL')])]
        self.assertEqual(calculate('M07',p)[0],100/3)
        p['cases'][3]['final_status']='PASS'
        with self.assertRaises(EvaluationError):calculate('M07',p)

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        data=self.root/'data/evaluation/fixture/events.csv';data.parent.mkdir(parents=True);data.write_text('id\n1\n')
        self.path=data.parent/'data_manifest.json'
        write(self.path,dict(dataset_id='fixture',official=False,data_class='DEVELOPMENT',synthetic=True,files=[dict(path='events.csv',sha256=digest(data))]))
        self.config=json.loads((ROOT/'backend/config.json').read_text());self.config['integration_datasets']={'fixture':dict(manifest=str(self.path.relative_to(self.root)),run_mode='DEVELOPMENT')}
        write(self.root/'backend/config.json',self.config);self.service=Service(self.root)
    def tearDown(self):self.temp.cleanup()
    def submit(self,metric):
        p=payload(metric);p['dataset_manifest_sha256']=digest(self.path);return p
    def test_persistence_provenance_duplicate_all_metrics(self):
        for metric in COUNTS:
            p=self.submit(metric);r=self.service.ingest(metric,p)
            self.assertIsNone(r['official_pass']);self.assertIsNone(r['pass'])
            self.assertEqual(r['provenance']['source_version'],'1')
            out=self.root/'results/development'/r['run_id']
            self.assertTrue(all((out/x).exists() for x in ['received_payload.json','result.json','evidence.csv','run_manifest.json']))
            self.assertEqual(json.loads((out/'received_payload.json').read_text()),p)
            self.assertEqual(Service(self.root).catalog('DEVELOPMENT')['metrics'][int(metric[1:])-1]['status'],'COMPLETED')
            with self.assertRaises(EvaluationError) as ctx:Service(self.root).ingest(metric,p)
            self.assertEqual(ctx.exception.status,'DUPLICATE_EXTERNAL_RUN')
    def test_hash_mode_rejection_no_score(self):
        p=self.submit('M04');p['dataset_manifest_sha256']='0'*64
        with self.assertRaises(EvaluationError):self.service.ingest('M04',p)
        p=self.submit('M04');p['run_mode']='OFFICIAL'
        with self.assertRaises(EvaluationError):self.service.ingest('M04',p)
        (self.path.parent/'events.csv').write_text('id\n2\n')
        with self.assertRaises(EvaluationError):self.service.ingest('M04',self.submit('M04'))
        self.assertFalse((self.root/'results/development/latest-M04.json').exists())
    def test_official_requires_provenance(self):
        self.config['integration_datasets']['fixture']['run_mode']='OFFICIAL';write(self.root/'backend/config.json',self.config)
        p=self.submit('M04');p['run_mode']='OFFICIAL'
        with self.assertRaises(EvaluationError):self.service.ingest('M04',p)
    def test_duplicate_across_modes(self):
        self.service.ingest('M04',self.submit('M04'))
        value=json.loads(self.path.read_text());value.update(run_mode='REFERENCE');write(self.path,value)
        self.config['integration_datasets']['fixture']['run_mode']='REFERENCE';write(self.root/'backend/config.json',self.config)
        p=self.submit('M04');p['run_mode']='REFERENCE'
        with self.assertRaises(EvaluationError) as ctx:self.service.ingest('M04',p)
        self.assertEqual(ctx.exception.status,'DUPLICATE_EXTERNAL_RUN')

class RunnerTests(unittest.TestCase):
    def test_temporal_mapping_and_ambiguity(self):
        e=[dict(execution_id='E1',session_id='S',start_time='2026-01-01T00:00:00',end_time='2026-01-01T00:00:10')]
        def inst(i,start,end,session='S'):return dict(instance_id=i,session_id=session,start_time='2026-01-01T00:00:'+start,end_time='2026-01-01T00:00:'+end)
        rows=temporal_mapping(e,[inst('A','00','06'),inst('B','00','05'),inst('C','00','10','OTHER')]);self.assertEqual(rows[0]['process_instance_id'],'A');self.assertEqual(rows[0]['overlap_ratio'],.6)
        rows=temporal_mapping(e,[inst('A','00','06'),inst('B','04','10')]);self.assertEqual(rows[0]['mapping_status'],'AMBIGUOUS');self.assertEqual(rows[0]['process_instance_id'],'')
        self.assertEqual(temporal_mapping(e,[])[0]['mapping_status'],'UNMAPPED')
    def test_unknown_is_unk_without_mutation(self):
        vocab={'<PAD>':0,'<UNK>':1,'click':2};old=dict(vocab)
        ids,diagnostic=encode(['click','new','new'],vocab)
        self.assertEqual(ids.tolist(),[2,1,1]);self.assertEqual(vocab,old);self.assertEqual(diagnostic['count'],2)
    def test_small_dataset_no_lowered_k(self):
        for n,m in [(9,12),(10,6),(1,1)]:
            with self.assertRaises(EvaluationError) as ctx:consensus_guard(n,m)
            self.assertEqual(ctx.exception.status,'INSUFFICIENT_DATA_FOR_CONSENSUS')
        consensus_guard(10,7)
    def test_input_hash_and_count(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events.csv';p.write_text('id\n1\n')
            entries=[dict(path='events.csv',sha256=digest(p),row_count=1)]
            checked_files(p.parent,entries,['events.csv']);p.write_text('id\n2\n')
            with self.assertRaises(EvaluationError):checked_files(p.parent,entries,['events.csv'])
    def test_no_training_or_evaluation_inputs_in_forward(self):
        source=(ROOT/'backend/model_runner/forward.py').read_text();tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='process')
        self.assertEqual([a.arg for a in fn.args.args],['events','runtime','bundle','semantic_path','output','diagnostics'])
        for name in ['ground_truth.csv','execution_manifest.csv','evaluation_pairing.csv']:self.assertNotIn(name,source)
        for path in ['forward.py','notebook_ops.py','process_export.py']:
            text=(ROOT/'backend/model_runner'/path).read_text()
            for prohibited in ['.backward(','.step(','.fit_transform(','.train(']:self.assertNotIn(prohibited,text)
        # Only notebook's explicitly authorized new-dataset consensus fitting is retained.
        self.assertIn('model.requires_grad_(False)',source)
    def test_blocked_run_persists_null_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=root/'data/evaluation/current_site_dev_01';base.mkdir(parents=True)
            entries=[]
            for name in ['events.csv','sessions.csv','tasks.csv']:
                p=base/name;p.write_text('id\n1\n');entries.append(dict(path=name,sha256=digest(p),row_count=1))
            write(base/'data_manifest.json',dict(dataset_id='current_site_dev_01',official=False,synthetic=False,files=entries))
            with patch('model.v6_2.inference.loader.load_runtime',side_effect=ValueError('fixture missing runtime')):
                r=EvaluationModelRunner(root).run()
            self.assertEqual(r['status'],'BLOCKED');self.assertIsNone(r['score']);self.assertEqual(len(r['input_sha256']),3)
            self.assertFalse(r['historical_equivalence_verified']);self.assertIn('execution_manifest.csv',r['excluded_model_inputs'])
            self.assertTrue((Path(r['output_directory'])/'diagnostics.json').exists())

class PosthocTests(unittest.TestCase):
    def test_semantic_notebook_prefix_and_empty(self):
        import numpy as np
        from backend.model_runner.forward import semantic_features
        class Encoder:
            def encode(self,texts,**kwargs):
                self.texts=texts
                return np.ones((len(texts),384),dtype='float32')
        encoder=Encoder();x=semantic_features(encoder,['PAGE: Home','',None])
        self.assertEqual(encoder.texts,['passage: PAGE: Home']);self.assertEqual(x.shape,(3,384));self.assertEqual(float(x[1:].sum()),0)
    def test_notebook_export_synthetic_instance(self):
        import pandas as pd
        import numpy as np
        from backend.model_runner.notebook_ops import prep,safe_str
        from backend.model_runner.process_export import export_processes
        events=pd.DataFrame([dict(id=i,event_time=f'2026-01-01T00:00:0{i}',session_id='S',workflow_key='worker#W1',page_title='Test',associated_label='입력',element_text='저장',input_data='test',interaction_type='change') for i in range(4)])
        df=prep(events);stream=df.stream_id.iloc[0]
        seg=pd.DataFrame([dict(segment_idx=i,segment_id=f'S{i}',stream_id=stream,start_global_idx=2*i,end_global_idx=2*i+1,segment_prototype=f'SP0{i}',segment_prototype_confidence=.8,evidence='test') for i in range(2)])
        wf=pd.DataFrame([dict(workflow_idx=0,workflow_id='W1',stream_id=stream,segment_start=0,segment_end=1,workflow_prototype='WP00',workflow_prototype_confidence=.8)])
        frames=export_processes(dict(df=df,segdf=seg,workflow_df=wf,workflow_members=[np.array([0,1])],safe_str=safe_str,DATASET_NAME='synthetic-test'))
        self.assertEqual(len(frames['process_instances']),1);self.assertEqual(len(frames['process_instance_steps']),2)
        self.assertIn('instance_step_id',frames['process_instance_steps'].columns)
    def test_m02_m06_development_evidence_and_null_official(self):
        import csv
        def csvfile(path,rows):
            with path.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();base=root/'data/evaluation/current_site_dev_01';base.mkdir(parents=True)
            executions=[dict(execution_id=f'EXEC-{i+1:03}',session_id='S',start_time=f'2026-01-01T00:00:{i*2:02}',end_time=f'2026-01-01T00:00:{i*2+1:02}') for i in range(8)]
            pair=[dict(execution_id=e['execution_id'],business_unit_id=f'BUS{i//2+1:02}',business_unit_name='Test',execution_number=str(i%2+1)) for i,e in enumerate(executions)]
            truth=[dict(business_unit_id=f'BUS{i+1:02}',step_order='1',step_label='저장',required='true',status='FINAL') for i in range(4)]
            entries=[]
            for name,rows in [('execution_manifest.csv',executions),('evaluation_pairing.csv',pair),('ground_truth.csv',truth)]:
                csvfile(base/name,rows);entries.append(dict(path=name,sha256=digest(base/name),row_count=len(rows)))
            write(base/'data_manifest.json',dict(derived_artifacts=entries))
            out=root/'results/model-runs/dev/fixture';out.mkdir(parents=True)
            instances=[dict(instance_id=f'I{i}',session_id='S',start_time=e['start_time'],end_time=e['end_time']) for i,e in enumerate(executions)]
            csvfile(out/'process_instances.csv',instances)
            csvfile(out/'process_instance_steps.csv',[dict(instance_id=f'I{i}',instance_step_id=f'S{i}',display_label='저장') for i in range(8)])
            csvfile(out/'workflow_consensus_features.csv',[dict(workflow_id=f'W{i}',**{f'f{j:02}':float(i) for j in range(80)}) for i in range(8)])
            csvfile(out/'workflow_cluster_labels.csv',[dict(workflow_id=f'W{i}',cluster_label=str(i//4)) for i in range(8)])
            write(out/'diagnostics.json',{})
            manifest=dict(run_id='fixture',status='COMPLETED',output_directory=str(out),input_sha256={},counts={'latent_workflow_count':8},output_sha256={p.name:digest(p) for p in out.iterdir()})
            write(out/'run_manifest.json',manifest)
            config={'targets':{'M02':75,'M06':1}}
            result=evaluate_run(root,config,manifest)
            self.assertEqual(result['M02']['score'],100);self.assertEqual(len(result['M02']['details']['rows']),8)
            self.assertIsNotNone(result['M06']['score'])
            for value in result.values():
                self.assertEqual(value['run_mode'],'DEVELOPMENT');self.assertIsNone(value['official_pass']);self.assertIsNone(value['pass'])
                self.assertTrue((root/'results/development'/value['run_id']/'evidence.csv').exists())

class ExternalHTTPTests(StoreTests):
    def test_http_endpoints_validation_and_downloads(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from backend.server import make_handler
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(method,path,value=None):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            body=json.dumps(value) if value is not None else None
            c.request(method,path,body,{'Content-Type':'application/json'});r=c.getresponse();data=r.read();status=r.status;c.close();return status,data
        try:
            for metric in COUNTS:
                path=f'/api/integrations/{metric.lower()}/result';p=self.submit(metric)
                status,body=request('POST',path,p);self.assertEqual(status,201)
                result=json.loads(body)
                for field in ['evidence_file','manifest_file','result_file']:
                    self.assertEqual(request('GET',result[field])[0],200)
                self.assertEqual(request('GET',result['result_file'].replace('result.json','received_payload.json'))[0],200)
                self.assertEqual(request('POST',path,p)[0],409)
                p['external_run_id']+='bad';p['counts']={};self.assertEqual(request('POST',path,p)[0],422)
        finally:server.shutdown();thread.join();server.server_close()
