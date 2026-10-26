"""공식 계약 회귀검사. 합성 bundle은 임시 디렉터리에서만 사용합니다."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from backend.official_contracts import OFFICIAL_SPEC, validate_official_contract
from backend.data_sources import OfficialEvaluationDataSource
from backend.evaluators import EvaluationError
from backend.external_results import calculate
from test_development_runner import payload

ROOT=Path(__file__).resolve().parents[1]

class OfficialComplianceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'backend').mkdir();(self.root/'backend/reference_manifest.json').write_text('{"files":{}}')
        (self.root/'data/evaluation').mkdir(parents=True)
    def tearDown(self):self.temp.cleanup()
    def source(self, metric, manifest, data):
        p=self.root/'data/evaluation/input.json';p.write_text(json.dumps(data))
        manifest=dict(manifest,metric_id=metric,run_mode='OFFICIAL',source_type='OFFICIAL',dataset_id='temporary-test',approved_for_official=True,
                      files={'clustering' if metric=='M06' else 'events':{'path':'data/evaluation/input.json','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}})
        (self.root/'data/evaluation/manifest.json').write_text(json.dumps(manifest))
        return OfficialEvaluationDataSource(self.root,{'official_manifests':{metric:'data/evaluation/manifest.json'}})
    def test_targets(self):
        self.assertEqual(json.loads((ROOT/'backend/config.json').read_text())['targets'],dict(M01=65,M02=75,M03=80,M04=90,M05=.79,M06=1.0,M07=80))
        from backend.evaluators import METRICS
        self.assertEqual(METRICS['M06'][3],'<=')
    def test_generated_code_denominator(self):
        p=payload('M07');p['counts']=dict(generation_request_count=20,generated_code_count=18,syntax_pass_count=17,execution_pass_count=16,both_pass_count=15)
        score,count,_,_=calculate('M07',p)
        self.assertAlmostEqual(score,83.33333333333333);self.assertEqual(count,18);self.assertNotEqual(score,75)
        p['counts']['generated_code_count']=0
        with self.assertRaises(EvaluationError):calculate('M07',p)
    def test_m02_m03_fixed_counts(self):
        for metric in ['M02','M03']:
            manifest={'official_contract':copy.deepcopy(OFFICIAL_SPEC[metric])}
            validate_official_contract(metric,manifest)
            manifest['official_contract']['business_unit_count']=4
            with self.assertRaises(EvaluationError):validate_official_contract(metric,manifest)
        manifest={'official_contract':dict(business_unit_count=20,ground_truth_process_count=7)}
        with self.assertRaises(EvaluationError):validate_official_contract('M02',manifest)
    def test_m05_heldout_false_rejected_before_adapter(self):
        manifest=dict(official_contract=OFFICIAL_SPEC['M05'],held_out=False,used_for_training=False,used_for_development=False)
        with self.assertRaisesRegex(EvaluationError,'held-out'):
            self.source('M05',manifest,{'events':[]}).prepare('M05')
    def test_official_m06_no_fallback(self):
        source=OfficialEvaluationDataSource(self.root,{})
        self.assertEqual(source.prepare('M06')['status'],'OFFICIAL_M06_BUNDLE_MISSING')
        manifest=dict(official_contract=OFFICIAL_SPEC['M06'],feature_space='consensus_80',model_version='V6.2',fixed_at='2020-01-01T00:00:00Z')
        bundle=dict(features=[[i]*80 for i in range(563)],labels=[i%12 for i in range(563)],workflow_ids=[f'W{i}' for i in range(563)],row_order='workflow_ids')
        with self.assertRaisesRegex(EvaluationError,'workflow_embedding_128'):
            self.source('M06',manifest,bundle).prepare('M06')
        manifest['feature_space']='workflow_embedding_128'
        with self.assertRaisesRegex(EvaluationError,'128'):
            self.source('M06',manifest,bundle).prepare('M06')
        bundle['features']=[[i]*128 for i in range(563)]
        self.assertEqual(self.source('M06',manifest,bundle).prepare('M06')['status'],'READY')
        bundle['labels'].pop()
        with self.assertRaises(EvaluationError):self.source('M06',manifest,bundle).prepare('M06')
    def test_m01_and_m04_counts(self):
        from backend.official_contracts import M01_FIELDS, M01_TYPES
        m={'official_contract':dict(OFFICIAL_SPEC['M01'],required_fields=M01_FIELDS,event_types=M01_TYPES)}
        validate_official_contract('M01',m,dict(defined_required_event_count=100,required_field_count=6,defined_event_type_count=8))
        with self.assertRaises(EvaluationError):
            validate_official_contract('M01',m,dict(defined_required_event_count=99,required_field_count=6,defined_event_type_count=8))
        m={'official_contract':OFFICIAL_SPEC['M04']}
        validate_official_contract('M04',m,{'total_execution_count':10})
        with self.assertRaises(EvaluationError):validate_official_contract('M04',m,{'total_execution_count':19})
    def test_m06_cross_check_with_temporary_bundle(self):
        import importlib.util
        if importlib.util.find_spec('sklearn') is None:self.skipTest('scikit-learn unavailable')
        from backend.server import Service
        manifest=dict(official_contract=OFFICIAL_SPEC['M06'],feature_space='workflow_embedding_128',model_version='V6.2',fixed_at='2020-01-01T00:00:00Z')
        bundle=dict(features=[[(i%12)*1000+(i//12)%3]*128 for i in range(563)],labels=[i%12 for i in range(563)],workflow_ids=[f'TEST-{i}' for i in range(563)],row_order='workflow_ids')
        self.source('M06',manifest,bundle)
        config=json.loads((ROOT/'backend/config.json').read_text());config['official_manifests']['M06']='data/evaluation/manifest.json'
        (self.root/'backend/config.json').write_text(json.dumps(config))
        result=Service(self.root).run('M06','OFFICIAL')
        self.assertEqual(result['status'],'COMPLETED',result.get('error'))
        self.assertTrue(result['details']['cross_check_pass']);self.assertEqual(result['details']['dimensions'],128)
        self.assertAlmostEqual(result['score'],result['details']['sklearn_dbi'],places=9)
