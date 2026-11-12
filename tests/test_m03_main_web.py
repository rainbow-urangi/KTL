"""Synthetic batch transport checks; no real generation in regression suite."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import m03_main_web as bridge
from backend.server import Service
from backend.evaluators import EvaluationError

class M03MainWebTests(unittest.TestCase):
    def test_catalog_never_generates(self):
        from backend.measurement_ui import catalog
        with patch.object(bridge,'generate',side_effect=AssertionError('GET must not generate')):
            item=next(x for x in catalog(Service())['metrics'] if x['metric_id']=='M03')
        self.assertTrue(item['execution_available'])
        self.assertEqual(len(item['details']['business_units']),10)
        self.assertIn(bridge.DATASET,item['execution_url'])
    def test_dispatch(self):
        with patch.object(bridge,'run',return_value={'ok':True}) as run:
            self.assertEqual(Service().run('M03','DEVELOPMENT',bridge.DATASET),{'ok':True})
            for metric,mode in [('M05','DEVELOPMENT'),('M03','OFFICIAL'),('M03','REFERENCE')]:
                with self.assertRaises(EvaluationError):Service().run(metric,mode,bridge.DATASET)
            self.assertEqual(run.call_count,1)
    def test_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(bridge.readiness(Path(tmp))['status'],'BLOCKED')
    def test_all_ten_attempts_central_evaluation_and_unique_run(self):
        selection=[dict(business_unit_id='SYN-'+str(i),name='Synthetic',mapping={'workflow_id':'W'+str(i),'source_event_ids_outside_execution_window':[]},source_execution_status='COMPLETED') for i in range(10)]
        candidate={'selection':selection,'candidate_id':'SYNTHETIC'}
        manifest={'sha256':{},'candidate_sha256':'fixture','generator_version':'fixture'}
        def generate(root,config,payload):
            i=int(payload['business_unit_id'].split('-')[1]);return dict(payload,scenario_id='S'+str(i),status='SUCCESS' if i else 'FAILED',steps=[dict(order=1 if i else 2,action='click',target='synthetic')],generator_version='fixture',source_snapshot_sha256='fixture',issues=[])
        config={'targets':{'M03':80}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge,'verify',return_value=(manifest,candidate)), patch.object(bridge,'read_json',return_value=config), patch.object(bridge,'digest',return_value='fixture'), patch.object(bridge,'generate',side_effect=generate) as gen:
            root=Path(tmp)
            first=bridge.run(root,config);second=bridge.run(root,config)
            self.assertEqual(gen.call_count,20)
            self.assertTrue(all(c.args[2]['generator_mode']=='REAL' for c in gen.call_args_list))
            self.assertEqual(first['score'],90);self.assertEqual(first['sample_count'],10)
            self.assertEqual(first['details']['failure'],1)
            self.assertNotEqual(first['run_id'],second['run_id'])
            self.assertEqual(len(first['details']['rows']),10)
            self.assertTrue((root/'results/development'/first['run_id']/'received_payload.json').exists())
