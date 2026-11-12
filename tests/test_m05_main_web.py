"""Bridge tests: scoring stays in the frozen central evaluator."""
import unittest
from unittest.mock import patch
from pathlib import Path
from backend.server import Service
from backend import m05_main_web as web
from backend.evaluators import EvaluationError

class MainWebTests(unittest.TestCase):
    def test_development_route_reuses_bridge(self):
        service=Service()
        with patch.object(web,'run',return_value={'sentinel':True}) as run:
            self.assertEqual(service.run('M05','DEVELOPMENT'),{'sentinel':True})
            run.assert_called_once()
    def test_unknown_dataset_rejected_before_engine(self):
        with patch.object(web,'run') as run:
            with self.assertRaises(EvaluationError):Service().run('M05','DEVELOPMENT','other')
            run.assert_not_called()
    def test_catalog_count_and_dataset(self):
        with patch.object(web,'readiness',return_value=dict(status='READY',dataset_id=web.DATASET,details={})):
            m=next(m for m in Service().catalog('DEVELOPMENT')['metrics'] if m['metric_id']=='M05')
            self.assertEqual(m['expected_sample_count'],20)
            self.assertEqual(m['dataset'],web.DATASET)
    def test_freeze_refuses_modified_manifest(self):
        with patch.object(web.fc,'sha',return_value='different'):
            with self.assertRaises(EvaluationError):web.verify_freeze(Path('.'))
