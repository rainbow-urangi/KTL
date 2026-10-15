"""임시 DEV fixture는 계산 검증 전용이며 서비스 평가 자료로 배포하지 않습니다."""
import hashlib
import http.client
import json
import math
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from backend.evaluators import M02Evaluator, M05Evaluator, M06Evaluator, EvaluationError, csv_evidence
from backend.data_sources import V62ReferenceProvider, OfficialEvaluationDataSource
from backend.contracts import cleaning_payload, validate_business_unit, validate_scenario
from backend.server import Service, make_handler, ROOT
from backend.registry import OWNERSHIP, STATUSES


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


def processes(labels):
    return {'processes':[{'id':'p','procedures':[{'id':str(i),'label':v} for i,v in enumerate(labels)]}]}


class PureEvaluatorTests(unittest.TestCase):
    def test_m02_formula(self):
        score, n, d, rows = M02Evaluator().evaluate(processes(['a','b','x','y']), processes(['a','b','c','d','e']))
        self.assertAlmostEqual(score, math.sqrt(50*40)); self.assertEqual(d['accuracy'],50); self.assertEqual(d['completeness'],40)
        self.assertEqual(sum(r['direct_match'] for r in rows),2)

    def test_m02_auxiliary_and_duplicate(self):
        actual=processes(['a','a','b']); actual['processes'][0]['procedures'][2]['evidence_type']='trajectory'
        _,_,d,_=M02Evaluator().evaluate(actual,processes(['a','b']))
        self.assertEqual(d['correctly_mapped'],1); self.assertEqual(d['evaluated_procedures'],3)

    def test_m02_empty_detection_is_not_zero(self):
        with self.assertRaises(EvaluationError): M02Evaluator().evaluate(processes([]),processes(['a']))

    def test_m02_missing_process_remains_denominator(self):
        gt=processes(['a']); gt['processes'].append({'id':'missing','procedures':[{'id':'b','label':'b'}]})
        _,_,d,_=M02Evaluator().evaluate(processes(['a']),gt); self.assertEqual(d['completeness'],50)

    def test_m05_metrics(self):
        events=[{'id':str(i),'label':v} for i,v in enumerate(['REMOVE','REMOVE','REMOVE','KEEP','KEEP'])]
        pred=[{'id':str(i),'label':v} for i,v in enumerate(['REMOVE','REMOVE','KEEP','REMOVE','KEEP'])]
        score,_,d,_=M05Evaluator().evaluate(events,pred)
        self.assertAlmostEqual(score,2/3); self.assertEqual((d['tp'],d['fp'],d['fn'],d['tn']),(2,1,1,1))
        self.assertAlmostEqual(d['precision'],2/3); self.assertAlmostEqual(d['recall'],2/3)

    def test_m05_bad_prediction_ids(self):
        with self.assertRaises(EvaluationError): M05Evaluator().evaluate([{'id':'x','label':'KEEP'}],[])

    def test_cleaning_gt_not_sent(self):
        event={'id':'x','features':{'text':'value'},'label':'REMOVE','category':'noise','secret':'ignore'}
        self.assertEqual(cleaning_payload([event]),{'events':[{'id':'x','features':{'text':'value'}}]})
        event['features']['nested']=[{'ground_truth':'REMOVE'}]
        with self.assertRaises(EvaluationError): cleaning_payload([event])

    def test_dbi(self):
        score,n,d,rows=M06Evaluator().evaluate([[0,0],[0,2],[10,0],[10,2]],[0,0,1,1])
        self.assertAlmostEqual(score,.2); self.assertEqual(n,4); self.assertEqual(d['dimensions'],2)

    def test_dbi_invalid(self):
        for features,labels in [([[0],[1]],[0,0]), ([[0],[1,2],[3]],[0,1,1]), ([[0],[1],[2]],[0,1]), ([[0],[float('nan')],[2]],[0,1,1]), ([[0],[0],[0]],[0,1,1])]:
            with self.subTest(features=features), self.assertRaises(EvaluationError): M06Evaluator().evaluate(features,labels)

    def test_scenario_contract(self):
        unit={'id':'unit','name':'업무','steps':[{'id':'1','label':'조회'}]}
        scenario={'id':'s','name':'조회 검증','business_unit_id':'unit','generator_version':'test-DEV_ONLY','steps':[{'id':'1','action':'조회','expected_outcome':'목록 표시'}]}
        self.assertEqual(validate_scenario(scenario,unit),scenario)
        scenario['steps'][0].pop('expected_outcome')
        with self.assertRaises(EvaluationError): validate_scenario(scenario,unit)
        with self.assertRaises(EvaluationError): validate_business_unit({'id':'x','name':'x','steps':[]})

    def test_csv_injection(self):
        csv=csv_evidence([{'value':'=1+1','nested':{'a':1}}]); self.assertIn("'=1+1",csv); self.assertTrue(csv.startswith('\ufeff'))


class SourceAndServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        shutil.copytree(ROOT/'backend',self.root/'backend',ignore=shutil.ignore_patterns('__pycache__'))
        base=ROOT/'model/v6_2/frozen'
        # 실제 artifact 복사본이며 synthetic Reference fixture가 아닙니다.
        for relative in ['run_manifest.json','main_results/process_models.csv','main_results/process_instances.csv','main_results/process_instance_steps.csv','main_results/poc_scenario_comparison.csv','diagnostics/workflow_consensus_assignments.csv']:
            dest=self.root/'model/v6_2/frozen'/relative; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(base/relative,dest)
        self.service=Service(self.root)

    def tearDown(self): self.temp.cleanup()

    def test_reference_loading(self):
        p=V62ReferenceProvider(self.root); r=p.prepare('M02'); self.assertEqual(r['status'],'REFERENCE_READY')
        self.assertEqual(r['details']['ground_truth_count'],7)
        score,_,d,_=M02Evaluator().evaluate(*r['inputs']); self.assertEqual(d['defined_required'],46); self.assertEqual(d['correctly_mapped'],17)
        self.assertAlmostEqual(score,math.sqrt(100*17/73*100*17/46))

    def test_reference_missing_gt(self):
        (self.root/'model/v6_2/frozen/main_results/poc_scenario_comparison.csv').unlink()
        r=self.service.run('M02'); self.assertEqual(r['status'],'REFERENCE_PARTIAL'); self.assertIsNone(r['score'])
        self.assertEqual(len(r['details']['rows']),12)

    def test_reference_tamper(self):
        p=self.root/'model/v6_2/frozen/main_results/process_models.csv'; p.write_bytes(p.read_bytes()+b'\n')
        r=self.service.run('M02'); self.assertEqual(r['status'],'ERROR'); self.assertIn('SHA-256',r['error'])
        self.assertIsNone(r['official_pass'])

    def test_reference_manifest_and_immutability(self):
        protected=self.root/'model'; before={str(p):p.read_bytes() for p in protected.rglob('*') if p.is_file()}
        r=self.service.run('M02'); self.assertEqual(r['status'],'COMPLETED'); self.assertIsNone(r['official_pass']); self.assertIsNone(r['pass'])
        self.assertFalse(r['threshold_met']); self.assertTrue(r['run_id'].startswith('REF-M02-'))
        d=self.root/'results/reference'/r['run_id']; manifest=json.loads((d/'run_manifest.json').read_text())
        for key in ['run_mode','source_type','input_paths','input_sha256','evaluator_version','model_reference_version','started_at','completed_at','evidence_files','error']: self.assertIn(key,manifest)
        self.assertEqual(manifest['run_mode'],'REFERENCE'); self.assertTrue((d/'evidence.csv').read_text().startswith('\ufeff'))
        self.assertEqual(before,{str(p):p.read_bytes() for p in protected.rglob('*') if p.is_file()})

    def test_isolation(self):
        ref=self.service.run('M02'); official=self.service.run('M02','OFFICIAL')
        self.assertEqual(official['status'],'WAITING_FOR_DATA'); self.assertIsNone(official['score']); self.assertIsNone(official['official_pass'])
        self.assertTrue(official['run_id'].startswith('EVAL-M02-'))
        for mode,expected in [('REFERENCE',ref),('OFFICIAL',official)]:
            m=next(m for m in self.service.catalog(mode)['metrics'] if m['metric_id']=='M02'); self.assertEqual(m['latest']['run_id'],expected['run_id'])
        with self.assertRaises(EvaluationError): self.service.run('M02','DEV')

    def test_external_and_m05(self):
        for mode in ['REFERENCE','OFFICIAL']:
            for metric in ['M01','M04','M07']:
                self.assertEqual(self.service.run(metric,mode)['status'],'EXTERNAL_MODULE_PENDING')
        self.assertEqual(self.service.run('M05')['status'],'NOT_CONFIGURED')
        self.assertEqual(OWNERSHIP['M03'],('shared','core_generator_only'))
        self.assertNotIn('owner',json.dumps(self.service.catalog()))

    def test_m03_preview(self):
        r=self.service.run('M03'); self.assertEqual(r['status'],'REFERENCE_PARTIAL'); self.assertIsNone(r['score'])
        self.assertEqual(len(r['details']['input_preview']),12)
        for u in r['details']['input_preview']: validate_business_unit(u)

    def test_m06_partial(self):
        r=self.service.run('M06'); self.assertEqual(r['status'],'REFERENCE_PARTIAL'); self.assertIsNone(r['score'])
        self.assertEqual(r['sample_count'],563); self.assertEqual(r['details']['cluster_count'],12)
        self.assertEqual(sum(x['workflow_count'] for x in r['details']['rows']),563)

    def official_manifest(self, changes=None):
        # 인증 흐름 검증용 임시 fixture. 실제 공식 실행/결과와 완전히 분리됩니다.
        data=self.root/'data/evaluation/input.json'; write(data,{'source_type':'DEV','processes':[]})
        m={'run_mode':'OFFICIAL','source_type':'OFFICIAL','approved_for_official':True,'dataset_id':'test-only','metric_id':'M02','model_connected':True,'model_version':'test',
           'files':{'ground_truth':{'path':'data/evaluation/input.json','sha256':hashlib.sha256(data.read_bytes()).hexdigest()}}}
        if changes: m.update(changes)
        write(self.root/'data/evaluation/manifest.json',m)
        config=self.service.config(); config['official_manifests']['M02']='data/evaluation/manifest.json'; write(self.root/'backend/config.json',config)
        return m,data

    def test_official_dev_rejected(self):
        self.official_manifest(); r=self.service.run('M02','OFFICIAL'); self.assertEqual(r['status'],'ERROR'); self.assertIn('DEV',r['error'])

    def test_official_hash_required_and_checked(self):
        m,data=self.official_manifest(); write(data,{'processes':[]})
        r=self.service.run('M02','OFFICIAL'); self.assertEqual(r['status'],'ERROR'); self.assertIn('SHA-256',r['error'])
        m['files']['ground_truth'].pop('sha256'); write(self.root/'data/evaluation/manifest.json',m)
        self.assertEqual(self.service.run('M02','OFFICIAL')['status'],'ERROR')

    def test_official_reference_copy_rejected(self):
        m,data=self.official_manifest(); data.write_bytes((self.root/'model/v6_2/frozen/run_manifest.json').read_bytes())
        m['files']['ground_truth']['sha256']=hashlib.sha256(data.read_bytes()).hexdigest(); write(self.root/'data/evaluation/manifest.json',m)
        r=self.service.run('M02','OFFICIAL'); self.assertIn('Historical reference',r['error'])

    def test_official_path_escape(self):
        m,_=self.official_manifest(); m['files']['ground_truth']['path']='backend/config.json'; write(self.root/'data/evaluation/manifest.json',m)
        self.assertIn('data/evaluation',self.service.run('M02','OFFICIAL')['error'])

    def test_running_lock(self):
        self.service.lock.acquire()
        try:
            with self.assertRaises(EvaluationError) as raised: self.service.run('M02')
            self.assertEqual(raised.exception.status,'RUNNING')
        finally: self.service.lock.release()

    def test_official_same_evaluator_and_pass(self):
        # Service 판정 정책만 검증합니다. synthetic 데이터를 실제 source에 등록하지 않습니다.
        with patch.object(OfficialEvaluationDataSource,'prepare',return_value={'status':'READY','details':{},'inputs':(processes(['a']),processes(['a']))}):
            r=self.service.run('M02','OFFICIAL')
        self.assertEqual(r['score'],100); self.assertTrue(r['official_pass'])


class HTTPTests(unittest.TestCase):
    def test_routes_modes_and_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); shutil.copytree(ROOT/'backend',root/'backend',ignore=shutil.ignore_patterns('__pycache__')); shutil.copytree(ROOT/'frontend',root/'frontend')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Service(root)))
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            def request(method,path,headers=None):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port); c.request(method,path,headers=headers or {}); r=c.getresponse(); value=r.read(); status=r.status; c.close(); return status,value
            try:
                for i in range(1,8): self.assertEqual(request('GET',f'/metrics/m0{i}?mode=OFFICIAL')[0],200)
                code,body=request('POST','/api/evaluations/m02/run?mode=OFFICIAL'); r=json.loads(body)
                self.assertEqual(code,200); self.assertEqual(r['status'],'WAITING_FOR_DATA')
                for key in ['evidence_file','manifest_file','result_file']: self.assertEqual(request('GET',r[key])[0],200)
                self.assertEqual(request('GET',r['result_file'].replace('/m02/','/m03/'))[0],404)
                self.assertEqual(request('POST','/api/evaluations/m02/run?mode=DEV')[0],422)
                self.assertEqual(request('POST','/api/evaluations/m02/run',{'Origin':'https://example.com'})[0],403)
                self.assertEqual(request('GET','/api/evaluations?mode=OFFICIAL')[0],200)
            finally: server.shutdown(); server.server_close(); thread.join()


if __name__=='__main__': unittest.main()
