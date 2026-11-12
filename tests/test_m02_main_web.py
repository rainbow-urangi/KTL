"""Transport checks. Real frozen-evaluator API reproduction is separately recorded."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import m02_main_web as bridge
from backend.evaluators import EvaluationError
from backend.server import Service

class M02MainWebTests(unittest.TestCase):
    def test_explicit_dataset_dispatch_only(self):
        service=Service()
        with patch.object(bridge,'run',return_value={'sentinel':True}) as run:
            self.assertEqual(service.run('M02','DEVELOPMENT',bridge.DATASET),{'sentinel':True})
            run.assert_called_once()
            for metric,mode in [('M03','DEVELOPMENT'),('M02','OFFICIAL'),('M02','REFERENCE')]:
                with self.assertRaises(EvaluationError):service.run(metric,mode,bridge.DATASET)
            self.assertEqual(run.call_count,1)
    def test_missing_or_modified_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/bridge.FREEZE;folder.mkdir(parents=True)
            (folder/'manifest.json').write_text('{}')
            with patch.object(bridge,'measure',side_effect=AssertionError('must not execute')):
                self.assertEqual(bridge.readiness(root)['status'],'BLOCKED')
                with self.assertRaises(EvaluationError):bridge.run(root,Service().config())
    def test_catalog_does_not_execute(self):
        from backend.measurement_ui import catalog
        with patch.object(bridge,'measure',side_effect=AssertionError('must not execute')):
            item=next(x for x in catalog(Service())['metrics'] if x['metric_id']=='M02')
            self.assertTrue(item['execution_available'])
            self.assertIn(bridge.DATASET,item['execution_url'])
