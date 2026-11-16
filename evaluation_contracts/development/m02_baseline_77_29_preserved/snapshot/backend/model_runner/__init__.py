"""현재 개발 데이터 전용 평가 runner. reference 산출물은 읽기 전용입니다."""
import csv
import json
import uuid
from pathlib import Path
from ..evaluators import digest, read_json, require, EvaluationError
from ..run_storage import now

DATASET='current_site_dev_01'

def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def checked_files(directory, entries, names):
    indexed={e['path']:e for e in entries};hashes={}
    for name in names:
        require(name in indexed,'Missing manifest entry: '+name)
        p=directory/name;expected=indexed[name]['sha256']
        require(p.is_file() and digest(p)==expected,'Input SHA-256 mismatch: '+name)
        if 'row_count' in indexed[name]:require(len(read_csv(p))==indexed[name]['row_count'],'Row count mismatch: '+name)
        hashes[str(p)]=expected
    return hashes

class EvaluationModelRunner:
    def __init__(self,root):self.root=Path(root)
    def run(self):
        from model.v6_2.inference.loader import load_runtime
        from model.v6_2.inference.schema import validate_csvs
        directory=self.root/'data/evaluation'/DATASET
        run_id='DEV-MODEL-'+now().replace(':','').split('.')[0].replace('-','')+'-'+uuid.uuid4().hex[:12]
        out=self.root/'results/model-runs/dev'/run_id;out.mkdir(parents=True)
        manifest={'run_id':run_id,'dataset_id':DATASET,'run_mode':'DEVELOPMENT','official':False,'official_pass':None,
            'status':'RUNNING','weights_updated':False,'started_at':now(),'model_version':'V6.2','runner_version':'development-runner-v1',
            'semantic_model_name':'intfloat/multilingual-e5-small','resolved_revision':None,
            'revision_verification_status':'UNAVAILABLE','historical_equivalence_verified':False,
            'model_input_files':['events.csv'],'validation_only_files':['sessions.csv','tasks.csv'],
            'excluded_model_inputs':['ground_truth.csv','ground_truth_candidate.csv','execution_manifest.csv','evaluation_pairing.csv','business_unit_id','business_unit_name'],
            'implementation_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
            'input_sha256':{},'output_directory':str(out),'score':None}
        from importlib.metadata import version, PackageNotFoundError
        manifest['dependencies']={}
        for package in ['torch','numpy','pandas','scikit-learn','sentence-transformers','transformers','huggingface-hub']:
            try:manifest['dependencies'][package]=version(package)
            except PackageNotFoundError:manifest['dependencies'][package]='UNAVAILABLE'
        diagnostics={};write_json(out/'run_manifest.json',manifest)
        try:
            data=read_json(directory/'data_manifest.json')
            require(data['dataset_id']==DATASET and data.get('official') is False and data.get('synthetic') is False,'Actual DEVELOPMENT dataset required')
            manifest['input_sha256']=checked_files(directory,data['files'],['events.csv','sessions.csv','tasks.csv'])
            manifest['dataset_manifest_sha256']=digest(directory/'data_manifest.json')
            runtime=load_runtime(self.root);rm=runtime['manifest']
            manifest['runtime_metadata_status']=runtime['status'];manifest['runtime_manifest_sha256']=digest(self.root/'model/v6_2/runtime/runtime_manifest.json')
            manifest['frozen_bundle_sha256']=rm['source_bundle_sha256'];manifest['reference_notebook_sha256']=rm['reference_notebook_sha256']
            diagnostics['schema']=validate_csvs(directory/'events.csv',directory/'sessions.csv',runtime['vocabularies'],directory/'tasks.csv')
            require(diagnostics['schema']['valid'],'Schema validation failed')
            source=read_json(self.root/'results/model-cache/semantic_source.json')
            require(source.get('semantic_model_name')==manifest['semantic_model_name'] and len(source.get('resolved_revision',''))==40,'Pinned E5 revision required')
            semantic=Path(source['local_path']).resolve();require(semantic.is_relative_to((self.root/'results/model-cache').resolve()),'Semantic cache outside model-cache')
            require(semantic.name==source['resolved_revision'],'Semantic revision/path mismatch')
            manifest.update(resolved_revision=source['resolved_revision'],revision_verification_status='RESOLVED_CURRENT_REVISION_NOT_HISTORICALLY_VERIFIED')
            manifest['semantic_files_sha256']={str(p.relative_to(semantic)):digest(p) for p in semantic.rglob('*') if p.is_file()}
            import pandas as pd
            import torch
            from .forward import process
            bundle=torch.load(self.root/rm['source_bundle_path'],map_location='cpu',weights_only=False)
            process(pd.read_csv(directory/'events.csv'),runtime,bundle,semantic,out,diagnostics)
            require(digest(self.root/rm['source_bundle_path'])==manifest['frozen_bundle_sha256'],'Frozen bundle changed')
            manifest['status']='COMPLETED'
        except EvaluationError as exc:
            manifest.update(status=exc.status if exc.status not in {'NOT_CONFIGURED'} else 'BLOCKED',error=str(exc))
        except Exception as exc:
            manifest.update(status='BLOCKED',error=f'{type(exc).__name__}: {exc}')
        if manifest.get('frozen_bundle_sha256'):
            manifest['frozen_bundle_verified_after_run']=digest(self.root/rm['source_bundle_path'])==manifest['frozen_bundle_sha256']
            if not manifest['frozen_bundle_verified_after_run']:manifest.update(status='ERROR',error='Frozen bundle integrity changed')
        manifest['completed_at']=now();manifest['counts']={k:v for k,v in diagnostics.items() if k.endswith('_count')}
        write_json(out/'diagnostics.json',diagnostics)
        manifest['output_sha256']={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='run_manifest.json'}
        write_json(out/'run_manifest.json',manifest)
        write_json(out.parent/'latest.json',manifest)
        return manifest
