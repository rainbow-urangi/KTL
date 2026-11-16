"""Synthetic relocation/runtime transport only; no real M05 prediction run."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from backend import m05_full_context as original_fc
from backend import m05_portable as portable
from backend.evaluators import EvaluationError


class PortableM05Tests(unittest.TestCase):
    def fixture(self, root, version):
        backend=root/'backend';backend.mkdir(parents=True)
        source=Path(portable.__file__).parent
        names=['__init__','evaluators','paths','m05_heldout','m05_portable',
               'm05_baseline_adapter','m05_session_cleaning','m05_full_context',
               'm05_development_contract','m05_session_candidate']
        for name in names:
            (backend/(name+'.py')).write_bytes((source/(name+'.py')).read_bytes())
        folder=root/'synthetic';folder.mkdir()
        dataset=folder/'dataset.py'
        dataset.write_text('''DROP_EXACT={'NOISE'}
DROP_PREFIX=('TECH:',)
def parse_ts(value):
    return datetime.fromisoformat(value)
def should_drop_activity(value):
    return not value or value in DROP_EXACT or value.startswith(DROP_PREFIX)
def rle_dedupe_rows(rows):
    kept=[];last=None
    for row in rows:
        if not should_drop_activity(row['activity']) and row['activity']!=last:
            kept.append(row);last=row['activity']
    return kept
''',encoding='utf-8')
        baseline=folder/'baseline.json'
        baseline.write_text(json.dumps(dict(rule_version='existing-dataset-cleaning-event-adapter-v1',
            cleaning_source=dict(path='dataset.py',sha256=portable._sha(dataset)))),encoding='utf-8')
        model=baseline
        if version=='session-context-cleaning-v2':
            model=folder/'session.json'
            model.write_text(json.dumps(dict(rule_version=version,
                baseline_rules_path='/Users/synthetic/RainbowKTL/synthetic/baseline.json')),encoding='utf-8')
        adapter=backend/(portable.VERSIONS[version]+'.py')
        config=dict(cleaning_model_version=version,
            model_artifact=dict(path='/Users/synthetic/RainbowKTL/synthetic/'+model.name,sha256=portable._sha(model)),
            adapter_artifact=dict(path='/Users/synthetic/RainbowKTL/backend/'+adapter.name,sha256=portable._sha(adapter)),
            interpreter_artifact=dict(path='/Library/synthetic/python',sha256='0'*64))
        config['adapters']={'cleaning':[config['interpreter_artifact']['path'],
            config['adapter_artifact']['path'],'--model',config['model_artifact']['path']]}
        return config,model

    def test_real_subprocess_relocates_both_engines_with_unicode(self):
        for version in portable.VERSIONS:
            with self.subTest(version=version), tempfile.TemporaryDirectory(prefix='M05 한글 공백 ') as tmp:
                root=Path(tmp)/'RainbowKTL';config,_=self.fixture(root,version)
                before=copy.deepcopy(config)
                rows=[]
                for i,activity in enumerate(['입력 ✓','입력 ✓','NOISE']):
                    features=dict(case_id='SYNTHETIC',activity=activity,ts='2026-11-13T12:00:00+09:00')
                    if version=='session-context-cleaning-v2':
                        features['context']=dict(session_id='SYNTHETIC',timestamp_utc=features['ts'],
                            action='input',page='https://example.invalid',target='',tag='body',text='',
                            popup_id=None,input_value=None,selection_start=None,selection_end=None,
                            input_type=None,interaction_id=None,related_interaction_id=None,has_api=False,has_outcome=False)
                    rows.append(dict(id='SYN-'+str(i),features=features))
                response=portable.call_adapter(config,'cleaning',{'events':rows},root)
                self.assertEqual(response['model_version'],version)
                self.assertEqual([p['label'] for p in response['predictions']],['KEEP','REMOVE','REMOVE'])
                self.assertEqual(response['predictions'][0]['activity'],'입력 ✓')
                self.assertEqual(config,before)
                self.assertFalse((root/'results').exists())

    def test_local_interpreter_is_reported_and_original_hash_checks_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'RainbowKTL';config,model=self.fixture(root,'session-context-cleaning-v2')
            runtime=portable.runtime_provenance(root,config)
            self.assertEqual(runtime['run_mode'],'DEVELOPMENT')
            self.assertFalse(runtime['historical_interpreter_reproduced'])
            self.assertEqual(runtime['local_interpreter_artifact']['sha256'],portable._sha(Path(sys.executable)))
            with self.assertRaisesRegex(EvaluationError,'DEVELOPMENT_ONLY'):
                portable.runtime_provenance(root,config,'OFFICIAL')
            bad=copy.deepcopy(config);bad['adapters']['cleaning']=['python','-c','print(1)']
            with self.assertRaisesRegex(EvaluationError,'argv must bind'):
                portable.runtime_provenance(root,bad)
            model.write_bytes(b'changed synthetic model')
            with self.assertRaisesRegex(EvaluationError,'Engine artifact hash mismatch'):
                portable.runtime_provenance(root,config)

    def test_private_path_imports_preserve_original_modules_and_global_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'RainbowKTL';self.fixture(root,'session-context-cleaning-v2')
            original_path=list(sys.path);original_validator=original_fc.validate_engine
            clone=portable._loader(root)('m05_session_candidate')
            self.assertIsNot(clone.fc,original_fc)
            self.assertIs(original_fc.validate_engine,original_validator)
            self.assertEqual(sys.path,original_path)
            self.assertNotIn(clone.__name__,sys.modules)
            self.assertNotIn(clone.fc.__name__,sys.modules)
            local=clone.fc.Path('/Users/synthetic/RainbowKTL/synthetic/baseline.json')
            self.assertEqual(local.read_text(),(root/'synthetic/baseline.json').read_text(encoding='utf-8'))
            self.assertEqual(str(local.relative_to(root)),'synthetic/baseline.json')

    def test_missing_external_source_reports_configured_local_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'RainbowKTL';root.mkdir()
            with self.assertRaisesRegex(EvaluationError,'M05_EXTERNAL_SOURCE_MISSING') as error:
                portable._resolve(root,'/Users/synthetic/workspace/AI-model/adapters/csv_adapter.py')
            self.assertIn(str(root.parent/'AI-model/adapters/csv_adapter.py'),str(error.exception))

    def test_runtime_binding_tracks_transport_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'RainbowKTL';config,_=self.fixture(root,'session-context-cleaning-v2')
            before=portable.runtime_provenance(root,config)
            helper=root/'backend/paths.py'
            helper.write_bytes(helper.read_bytes()+b'\n# synthetic transport change\n')
            after=portable.runtime_provenance(root,config)
            self.assertNotEqual(before['transport_sha256'],after['transport_sha256'])

    def test_subprocess_errors_do_not_expose_raw_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'RainbowKTL';config,_=self.fixture(root,'session-context-cleaning-v2')
            failed=SimpleNamespace(returncode=1,stderr='ValueError: private synthetic field',stdout='')
            with patch.object(portable.subprocess,'run',return_value=failed):
                with self.assertRaises(EvaluationError) as error:
                    portable.call_adapter(config,'cleaning',{'events':[]},root)
            self.assertIn('exited with code 1',str(error.exception))
            self.assertNotIn('private synthetic field',str(error.exception))



class RuntimeArchiveTests(unittest.TestCase):
    def fixture(self, host):
        directory=host/portable.RUNTIME_ROOT
        directory.mkdir(parents=True)
        files={}
        for name in ('backend/m05_portable.py','backend/paths.py'):
            raw=(Path(portable.__file__).parents[1]/name).read_bytes()
            for root in (host,directory):
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            files[name]=portable._sha(directory/name)
        original=host/'data/synthetic.csv';original.parent.mkdir(exist_ok=True)
        original.write_bytes(b'original\r\n')
        copied=directory/'data/synthetic.csv';copied.parent.mkdir(exist_ok=True)
        copied.write_bytes(b'original\n')
        files['data/synthetic.csv']=portable._sha(copied)
        manifest=dict(schema_version='m05-frozen-runtime-copy-v1',run_mode='DEVELOPMENT',
            official_pass=None,files=files,host_input_originals={'data/synthetic.csv':portable._sha(original)})
        path=directory/portable.RUNTIME_MANIFEST
        path.write_text(json.dumps(manifest),encoding='utf-8')
        return directory,manifest,path

    def test_missing_archive_stays_blocked_and_get_never_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(EvaluationError,'ARCHIVE_MISSING'):
                portable.runtime_root(root)
            self.assertEqual(list(root.iterdir()),[])

    def test_exact_archive_accepts_while_host_raw_bytes_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory,_,_=self.fixture(root)
            before=(root/'data/synthetic.csv').read_bytes()
            self.assertEqual(portable.runtime_root(root),directory)
            self.assertEqual(portable._source_root(directory),root)
            self.assertEqual((root/'data/synthetic.csv').read_bytes(),before)
            self.assertEqual((directory/'data/synthetic.csv').read_bytes(),b'original\n')

    def test_archive_tamper_and_host_transport_drift_fail_before_execution(self):
        for target in ('archive','transport'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);directory,_,_=self.fixture(root)
                path=directory/'data/synthetic.csv' if target=='archive' else root/'backend/m05_portable.py'
                path.write_bytes(path.read_bytes()+b'changed')
                with patch.object(portable.subprocess,'run',side_effect=AssertionError('no subprocess')):
                    with self.assertRaisesRegex(EvaluationError,'ARCHIVE_CHANGED|TRANSPORT_CHANGED'):
                        portable.runtime_root(root)

    def test_host_input_drift_is_not_silently_replaced_by_old_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory,_,_=self.fixture(root)
            preserved=(directory/'data/synthetic.csv').read_bytes()
            (root/'data/synthetic.csv').write_bytes(b'new input')
            with self.assertRaisesRegex(EvaluationError,'HOST_INPUT_CHANGED'):
                portable.runtime_root(root)
            self.assertEqual((directory/'data/synthetic.csv').read_bytes(),preserved)

    def test_official_archive_and_path_escape_are_rejected(self):
        for change in ('official','escape','malformed'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);_,manifest,path=self.fixture(root)
                if change=='official':manifest['run_mode']='OFFICIAL'
                elif change=='escape':manifest['files']['../escape']='0'*64
                else:manifest=[]
                path.write_text(json.dumps(manifest),encoding='utf-8')
                with self.assertRaises((EvaluationError,ValueError)):
                    portable.runtime_root(root)

    def test_external_source_mapping_uses_host_config_not_the_isolated_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory,_,_=self.fixture(root)
            source=root/'synthetic-ai/adapters/csv_adapter.py'
            source.parent.mkdir(parents=True);source.write_bytes(b'# synthetic source\n')
            (root/'backend/runtime_paths.json').write_text(json.dumps({'ai_model_root':'synthetic-ai'}),encoding='utf-8')
            mapped=portable._resolve(directory,'/Users/synthetic/AI-model/adapters/csv_adapter.py')
            self.assertEqual(Path(mapped),source)


if __name__=='__main__':
    unittest.main()
