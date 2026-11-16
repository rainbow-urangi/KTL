"""Bridge tests: scoring stays in the frozen central evaluator."""
import unittest
import tempfile
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
    def test_readiness_reports_the_executed_archive_config_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'isolated-runtime'
            host_config=root/web.CONFIG_PATH;used_config=archive/web.CONFIG_PATH
            for path in (host_config,used_config):path.parent.mkdir(parents=True,exist_ok=True)
            host_config.write_bytes(b'{"synthetic":"host"}\r\n')
            used_config.write_bytes(b'{"synthetic":"archive"}\n')
            prepared=dict(events=[{}],targets=[{}],binding={'synthetic':'unchanged'})
            with patch.object(web,'inputs',return_value=({},dict(cleaning_model_version='synthetic'),prepared,{})),patch.object(web,'runtime_root',return_value=archive):
                result=web.readiness(root)
            self.assertEqual(result['status'],'READY')
            self.assertEqual(result['details']['config_path'],web.CONFIG_PATH)
            self.assertEqual(result['details']['config_sha256'],web.fc.sha(used_config))
            self.assertNotEqual(result['details']['config_sha256'],web.fc.sha(host_config))
