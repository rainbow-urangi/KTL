"""Transport checks. Real frozen-evaluator API reproduction is separately recorded."""
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import m02_main_web as bridge
from backend.evaluators import EvaluationError
from backend.server import Service

class M02MainWebTests(unittest.TestCase):
    def synthetic_snapshot(self, tmp):
        root=Path(tmp)/'synthetic 한글 root'
        snapshot=root/bridge.FREEZE/'snapshot'
        snapshot.mkdir(parents=True)
        artifacts=[]
        for index,source in enumerate(('/historic/m02/source.txt', r'C:\historic\m02-windows\source.txt')):
            relative='snapshot/absolute/source-'+str(index)+'.txt'
            raw=('SYNTHETIC 한글 '+str(index)).encode('utf-8')
            path=root/bridge.FREEZE/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            artifacts.append(dict(source_path=source,snapshot_path=relative,sha256=hashlib.sha256(raw).hexdigest()))
        manifest=snapshot.parent/'manifest.json'
        manifest.write_text(json.dumps(dict(artifacts=artifacts)),encoding='utf-8')
        routing=root/bridge.ROUTING_MANIFEST;routing.parent.mkdir(parents=True,exist_ok=True);routing.write_bytes(b'{}')
        server=snapshot/bridge.OUTPUT/'web_ready/server.py';server.parent.mkdir(parents=True)
        server.write_text("from pathlib import Path\nimport hashlib\nROOT=Path(__file__).resolve().parents[4]\n"
            "sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()\n"
            "def measure():\n"
            +''.join(' assert sha(ROOT/Path('+repr(row['source_path'])+'))=='+repr(row['sha256'])+'\n' for row in artifacts)
            +" return {'label':'SYNTHETIC 한글'}\n",encoding='utf-8')
        return root,snapshot,manifest,hashlib.sha256(b'{}').hexdigest()

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

    def test_absolute_source_aliases_and_utf8_preserve_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,snapshot,_,routing_hash=self.synthetic_snapshot(tmp)
            before={str(p.relative_to(snapshot)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in snapshot.rglob('*') if p.is_file()}
            actual_run=bridge.subprocess.run
            with patch.object(bridge,'ROUTING_HASH',routing_hash),patch.object(bridge.subprocess,'run',wraps=actual_run) as child:
                self.assertEqual(bridge.measure(snapshot),{'label':'SYNTHETIC 한글'})
            args,options=child.call_args
            self.assertEqual(args[0][:5],[sys.executable,'-X','utf8','-B','-c'])
            self.assertEqual(options['encoding'],'utf-8')
            self.assertEqual(options['env']['PYTHONUTF8'],'1')
            self.assertEqual(options['env']['PYTHONIOENCODING'],'utf-8')
            self.assertEqual(before,{str(p.relative_to(snapshot)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in snapshot.rglob('*') if p.is_file()})

    def test_alias_escape_and_wrong_sha_fail_before_subprocess(self):
        for invalid_path in (True,False):
            with self.subTest(escape=invalid_path),tempfile.TemporaryDirectory() as tmp:
                _,snapshot,manifest,routing_hash=self.synthetic_snapshot(tmp)
                value=json.loads(manifest.read_text(encoding='utf-8'))
                if invalid_path:value['artifacts'][0]['snapshot_path']='snapshot/../../outside.txt'
                else:value['artifacts'][0]['sha256']='0'*64
                manifest.write_text(json.dumps(value),encoding='utf-8')
                with patch.object(bridge,'ROUTING_HASH',routing_hash),patch.object(bridge.subprocess,'run',side_effect=AssertionError('must not execute')) as child:
                    with self.assertRaises(EvaluationError):bridge.measure(snapshot)
                    child.assert_not_called()
