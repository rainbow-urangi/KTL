"""최신 연동 계약의 합성 입력 검증. 실제 시험 근거를 생성하지 않습니다."""
import copy
import json
import unittest
from pathlib import Path
from backend.external_results import calculate
from backend.evaluators import EvaluationError
from backend.m03_integration import validate_scenario_result

CATALOG=json.loads((Path(__file__).resolve().parents[1]/'frontend/integration-samples.json').read_text())
def sample(metric):
    return copy.deepcopy(next(s['request'] for s in CATALOG['samples'] if s['metric_id']==metric))

class LatestIntegrationTests(unittest.TestCase):
    def test_m03_eight_of_ten(self):
        p=sample('M03');p['score']=100
        score,total,details,rows=calculate('M03',p)
        self.assertEqual((score,total),(80,10));self.assertEqual(sum(r['success'] for r in rows),8)
    def test_m03_missing_fields_and_schema(self):
        good=sample('M03')['scenarios'][0]
        for field in ['action','target','order']:
            row=copy.deepcopy(good);del row['steps'][0][field]
            self.assertFalse(validate_scenario_result(row)['success'])
        for steps in [None,{},[],['invalid'],[dict(order=True,action='click',target='x')]]:
            row=dict(good,steps=steps);self.assertFalse(validate_scenario_result(row)['success'])
    def test_m03_order_and_failed_status(self):
        row=sample('M03')['scenarios'][0];row['steps'][0]['order']=2
        self.assertFalse(validate_scenario_result(row)['step_order_valid'])
        row['steps'][0]['order']=1;row['status']='FAILED'
        self.assertFalse(validate_scenario_result(row)['success'])
    def test_m03_official_ten_and_unique_units(self):
        p=sample('M03');p['run_mode']='OFFICIAL'
        self.assertEqual(calculate('M03',p)[:2],(80,10))
        p['scenarios'].pop()
        with self.assertRaises(EvaluationError):calculate('M03',p)
        p['run_mode']='DEVELOPMENT';self.assertEqual(calculate('M03',p)[1],9)
        p['scenarios'][1]['business_unit_id']=p['scenarios'][0]['business_unit_id']
        with self.assertRaises(EvaluationError):calculate('M03',p)
    def test_m04_counts_alias_and_failures(self):
        p=sample('M04');p['score']=100;p['run_mode']='OFFICIAL'
        self.assertEqual(calculate('M04',p)[:2],(90,10))
        p['counts']=dict(total_execution_count=10,passed_execution_count=8,failed_execution_count=2)
        self.assertEqual(calculate('M04',p)[:2],(80,10))
        p['counts']['total_execution_count']=20
        with self.assertRaises(EvaluationError):calculate('M04',p)
    def test_m07_official_fixed_twenty(self):
        p=sample('M07');p['run_mode']='OFFICIAL';p['score']=100
        self.assertEqual(calculate('M07',p)[:2],(80,20))
        p['cases'][0]['syntax_status']='FAIL';p['cases'][0]['final_status']='FAIL'
        p['counts']['both_pass_count']=15;p['counts']['syntax_pass_count']=17
        self.assertEqual(calculate('M07',p)[:2],(75,20))
        for field in ['generation_request_count','generated_code_count']:
            bad=copy.deepcopy(p);bad['counts'][field]=19
            with self.assertRaises(EvaluationError):calculate('M07',bad)
    def test_m07_individual_results_required_and_checked(self):
        p=sample('M07');p['run_mode']='OFFICIAL';del p['cases']
        with self.assertRaises(EvaluationError):calculate('M07',p)
        p=sample('M07');p['cases'][0]['syntax_status']='FAIL'
        with self.assertRaises(EvaluationError):calculate('M07',p)
    def test_nonofficial_request_count_not_denominator(self):
        p=sample('M07');del p['cases'];p['counts']['generation_request_count']=25
        self.assertEqual(calculate('M07',p)[:2],(80,20))
        p['run_mode']='OFFICIAL'
        with self.assertRaises(EvaluationError):calculate('M07',p)
    def test_official_m03_store_provenance_and_unit_set(self):
        import tempfile
        import hashlib
        from backend.integration_store import ingest
        from backend.official_contracts import OFFICIAL_SPEC
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();folder=root/'data/evaluation/test';folder.mkdir(parents=True)
            source=folder/'input.csv';source.write_text('temporary_test_only\n1\n')
            manifest=dict(dataset_id='temporary-test',source_type='OFFICIAL',run_mode='OFFICIAL',approved_for_official=True,
                          metric_id='M03',official_contract=OFFICIAL_SPEC['M03'],business_unit_ids=[f'BU{i:02}' for i in range(1,11)],
                          files={'input':dict(path=str(source.relative_to(root)),sha256=hashlib.sha256(source.read_bytes()).hexdigest())})
            path=folder/'manifest.json';path.write_text(json.dumps(manifest))
            config=dict(targets={'M03':80},integration_datasets={'temporary-test':dict(run_mode='OFFICIAL',manifest=str(path.relative_to(root)))})
            p=sample('M03');p.update(dataset_id='temporary-test',run_mode='OFFICIAL',dataset_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            p['details']={}
            for row in p['scenarios']:
                row.pop('synthetic',None);row.pop('generator_mode',None)
            p['run_id']=p.pop('external_run_id')
            # Temporary fixtures are isolated and never written as project official evidence.
            result=ingest(root,config,'M03',p)
            self.assertTrue(result['official_pass']);self.assertEqual(result['score'],80)
            p['run_id']+='-bad';p['scenarios'][0]['business_unit_id']='UNREGISTERED'
            with self.assertRaisesRegex(EvaluationError,'do not match'):ingest(root,config,'M03',p)
            p['scenarios'][0]['business_unit_id']='BU01';p['scenarios'][0]['synthetic']=True
            with self.assertRaisesRegex(EvaluationError,'Mock scenarios'):ingest(root,config,'M03',p)
