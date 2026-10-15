"""M02 v1.1 규칙 검증. 합성 입력은 임시 테스트 디렉터리에서만 사용합니다."""
import copy
import hashlib
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import test_evaluations as existing_tests
from test_evaluations import processes, write
from backend.evaluators import M02Evaluator, EvaluationError
from backend.data_sources import V62ReferenceProvider, OfficialEvaluationDataSource
from backend.m02_contracts import official_m02_inputs


class M02NormalizationTests(unittest.TestCase):
    def test_normalization(self):
        for left,right in [('국제교류학년도 학기','국제교류학년도학기'),('a   b','ab'),('a\tb','ab'),('a\nb','ab'),
                           ('a\u00a0\u2003\u3000b','ab'),('ABc','abc'),('ＡＢＣ①','abc1')]:
            with self.subTest(left=left):
                self.assertEqual(M02Evaluator().evaluate(processes([left]),processes([right]))[0],100)
        self.assertEqual(M02Evaluator.canonical_label(None),'')
        _,_,d,_=M02Evaluator().evaluate(processes([None]),processes([None]));self.assertEqual(d['correctly_mapped'],0)

    def test_alias_only_registered(self):
        contract={'version':'1.0','aliases':[{'canonical':'교류학생관리(IN)','accepted':['교류학생관리 IN']}]}
        actual=processes(['교류학생관리 IN']);gt=processes(['교류학생관리(IN)'])
        self.assertEqual(M02Evaluator(contract).evaluate(actual,gt)[0],100)
        self.assertEqual(M02Evaluator().evaluate(actual,gt)[0],0)
        self.assertEqual(M02Evaluator(contract).evaluate(processes(['교류학생관리']),gt)[0],0)

    def test_alias_conflict(self):
        with self.assertRaises(EvaluationError):
            M02Evaluator({'version':'1.0','aliases':[{'canonical':'a','accepted':['x']},{'canonical':'b','accepted':['x']}]})

    def test_one_to_one_and_scenario_isolation(self):
        actual=processes(['a b']);gt=processes(['ab','AB'])
        self.assertEqual(M02Evaluator().evaluate(actual,gt)[2]['correctly_mapped'],1)
        actual['processes'].append({'id':'q','procedures':[{'id':'0','label':'AB'}]})
        self.assertEqual(M02Evaluator().evaluate(actual,gt)[2]['correctly_mapped'],1)

    def test_auxiliary_alias_not_direct(self):
        actual=processes(['a b']); actual['processes'][0]['procedures'][0]['evidence_type']='trajectory'
        self.assertEqual(M02Evaluator().evaluate(actual,processes(['ab']))[2]['correctly_mapped'],0)


class M02SourceTests(unittest.TestCase):
    setUp = existing_tests.SourceAndServiceTests.setUp
    tearDown = existing_tests.SourceAndServiceTests.tearDown

    def setup_official(self, aliases=False):
        gt={'processes':[{'id':f'S{i}','procedures':[{'id':'g','label':'correct'}]} for i in range(5)]}
        model={'processes':[{'id':f'I{i}','execution_id':f'E{i}','procedures':[{'id':'m','label':'wrong'}]} for i in range(5)]}
        # 점수가 더 높은 미지정 instance는 선택되지 않아야 합니다.
        model['processes'].append({'id':'BEST','execution_id':'E0','procedures':[{'id':'m','label':'correct'}]})
        pairing={'version':'1.0','fixed_at':'2020-01-01T00:00:00Z','ground_truth_independent':True,
                 'pairs':[{'scenario_id':f'S{i}','execution_id':f'E{i}','process_instance_id':f'I{i}','selection_method':'execution_linked'} for i in range(5)]}
        payloads={'event_log':{'events':[]},'ground_truth':gt,'process_result':model,'pairing':pairing}
        if aliases: payloads['aliases']={'version':'1.0','aliases':[{'canonical':'correct','accepted':['wrong']}]}
        manifest={'run_mode':'OFFICIAL','source_type':'OFFICIAL','approved_for_official':True,'dataset_id':'temporary-unit-test',
                  'official_contract':{'business_unit_count':20,'ground_truth_process_count':5},'business_unit_ids':[f'B{i}' for i in range(20)],'metric_id':'M02','model_version':'test-only','model_connected':True,'files':{}}
        for role,value in payloads.items():
            relative=f'data/evaluation/{role}.json';write(self.root/relative,value)
            manifest['files'][role]={'path':relative,'sha256':hashlib.sha256((self.root/relative).read_bytes()).hexdigest()}
            if role=='aliases': manifest['files'][role]['fixed_at']='2020-01-01T00:00:00Z'
        self.manifest=manifest; self.payloads=payloads
        write(self.root/'data/evaluation/manifest.json',manifest)
        c=self.service.config();c['official_manifests']['M02']='data/evaluation/manifest.json';write(self.root/'backend/config.json',c)

    def update_role(self,role):
        item=self.manifest['files'][role];write(self.root/item['path'],self.payloads[role]);item['sha256']=hashlib.sha256((self.root/item['path']).read_bytes()).hexdigest()
        write(self.root/'data/evaluation/manifest.json',self.manifest)

    def test_pairing_is_optional(self):
        self.setup_official();self.manifest['files'].pop('pairing');write(self.root/'data/evaluation/manifest.json',self.manifest)
        r=self.service.run('M02','OFFICIAL');self.assertEqual(r['status'],'COMPLETED');self.assertEqual(r['details']['evaluated_procedures'],6)

    def test_no_best_instance_search(self):
        self.setup_official();r=self.service.run('M02','OFFICIAL')
        self.assertEqual(r['status'],'COMPLETED');self.assertEqual(r['score'],0)
        self.assertEqual([p['process_instance_id'] for p in r['pairing_pairs']],[f'I{i}' for i in range(5)])
        self.payloads['pairing']['pairs'][0]['selection_method']='gt_best_match';self.update_role('pairing')
        self.assertEqual(self.service.run('M02','OFFICIAL')['status'],'ERROR')

    def test_pairing_hash_and_invalid_instance(self):
        self.setup_official(); p=self.root/'data/evaluation/pairing.json';p.write_text(p.read_text()+' ')
        self.assertIn('SHA-256',self.service.run('M02','OFFICIAL')['error'])
        self.payloads['pairing']['pairs'][0]['process_instance_id']='MISSING';self.update_role('pairing')
        self.assertIn('Invalid paired process instance',self.service.run('M02','OFFICIAL')['error'])

    def test_pairing_fixed_independent_execution_and_coverage(self):
        for change in ['future','independence','execution','duplicate']:
            with self.subTest(change=change):
                self.setup_official(); p=self.payloads['pairing']
                if change=='future':p['fixed_at']='2999-01-01T00:00:00Z'
                if change=='independence':p['ground_truth_independent']=False
                if change=='execution':p['pairs'][0]['execution_id']='OTHER'
                if change=='duplicate':p['pairs'][0]['scenario_id']='S1'
                self.update_role('pairing');self.assertEqual(self.service.run('M02','OFFICIAL')['status'],'ERROR')

    def test_pairing_selection_does_not_use_gt_labels(self):
        self.setup_official();cutoff=datetime.now(timezone.utc)
        a=official_m02_inputs(self.payloads['process_result'],self.payloads['ground_truth'],self.payloads['pairing'],cutoff)[0]
        gt=copy.deepcopy(self.payloads['ground_truth']);gt['processes'][0]['procedures'][0]['label']='different'
        b=official_m02_inputs(self.payloads['process_result'],gt,self.payloads['pairing'],cutoff)[0];self.assertEqual(a,b)

    def test_official_alias_hash_and_fixed_at(self):
        self.setup_official(aliases=True);r=self.service.run('M02','OFFICIAL')
        self.assertAlmostEqual(r['score'],(100*100*5/6)**0.5)
        self.assertEqual(r['details']['evaluated_procedures'],6)
        manifest=json.loads((self.root/'results/official'/r['run_id']/'run_manifest.json').read_text())
        for role in ['aliases','pairing']:
            key='alias' if role=='aliases' else role
            self.assertEqual(manifest[key+'_sha256'],self.manifest['files'][role]['sha256'])
        self.manifest['files']['aliases']['fixed_at']='2999-01-01T00:00:00Z';write(self.root/'data/evaluation/manifest.json',self.manifest)
        self.assertEqual(self.service.run('M02','OFFICIAL')['status'],'ERROR')
        self.manifest['files']['aliases']['fixed_at']='2020-01-01T00:00:00Z';write(self.root/'data/evaluation/manifest.json',self.manifest)
        p=self.root/'data/evaluation/aliases.json';p.write_text(p.read_text()+' ')
        self.assertIn('SHA-256',self.service.run('M02','OFFICIAL')['error'])

    def test_reference_stored_selection_and_no_alias_file(self):
        p=V62ReferenceProvider(self.root);prepared=p.prepare('M02')
        self.assertIsNone(p.m02_aliases)
        self.assertEqual([len(x['procedures']) for x in prepared['inputs'][0]['processes']],[8,44,11,10,0,0,0])
        # 지정되지 않은 행을 완벽한 정답으로 만들어도 선택 결과는 그대로입니다.
        original=p.read
        def read(name,optional=False):
            rows=original(name,optional)
            if name=='main_results/process_instance_steps.csv':
                rows=copy.deepcopy(rows);rows.append({'instance_id':'UNSELECTED','instance_step_id':'new','step_order':'1','display_label':'교류기관관리'})
            return rows
        with patch.object(p,'read',side_effect=read):second=p.prepare('M02')
        self.assertEqual(prepared['inputs'],second['inputs'])
        r=self.service.run('M02');self.assertEqual(r['selection_method'],'V6.2 Legacy Reference Selection');self.assertEqual(r['evaluator_version'],'m02-evaluator-v1.1')

    def test_reference_alias_hash(self):
        write(self.root/'evaluation_contracts/m02_aliases.json',{'version':'1.0','aliases':[]})
        r=self.service.run('M02');self.assertIsNotNone(r['alias_sha256'])
        m=json.loads((self.root/'results/reference'/r['run_id']/'run_manifest.json').read_text())
        self.assertEqual(m['alias_sha256'],r['input_sha256']['evaluation_contracts/m02_aliases.json'])
