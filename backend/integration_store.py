"""외부 제출 provenance 확인과 파일 기반 중복 방지."""
import hashlib
import json
import os
from pathlib import Path
from .external_results import calculate
from .evaluators import require,read_json,digest,EvaluationError
from .run_storage import save_run
from .official_contracts import validate_official_contract
from .m02_contracts import validate_fixed_at
from datetime import datetime


def ingest(root,config,metric,payload):
    score,count,details,rows=calculate(metric,payload)
    mode=payload['run_mode'];dataset=payload['dataset_id']
    registered=config.get('integration_datasets',{}).get(dataset)
    require(isinstance(registered,dict) and registered.get('run_mode')==mode,'Dataset not registered for requested mode')
    allowed=(root/'data/evaluation').resolve()
    path=(root/registered['manifest']).resolve()
    require(path.is_relative_to(allowed),'Manifest must be under data/evaluation')
    manifest=read_json(path);sha=digest(path)
    require(sha==payload['dataset_manifest_sha256'],'Dataset manifest SHA-256 mismatch')
    require(manifest.get('dataset_id')==dataset,'Dataset ID mismatch')
    if mode=='OFFICIAL':
        require(manifest.get('source_type')=='OFFICIAL' and manifest.get('run_mode')=='OFFICIAL'
                and manifest.get('approved_for_official') is True and manifest.get('metric_id')==metric
                and manifest.get('official') is not False and manifest.get('synthetic') is not True,
                'Approved official manifest provenance required')
        validate_official_contract(metric,manifest,payload['counts'])
        if metric=='M04':
            validate_fixed_at(manifest.get('fixed_at'),datetime.fromisoformat(payload['submitted_at'].replace('Z','+00:00')),'Script set')
            require(manifest.get('scripts_manually_modified') is False and manifest.get('script_language')=='python' and manifest.get('script_framework')=='selenium','Official M04 requires unmodified generated Selenium/Python scripts')
            require(isinstance(manifest.get('files'),dict) and 'scripts' in manifest['files'],'Official M04 fixed script archive hash required')
    elif mode=='DEVELOPMENT':
        require(manifest.get('official') is False and manifest.get('data_class')=='DEVELOPMENT','DEVELOPMENT provenance required')
    else:require(manifest.get('run_mode')=='REFERENCE','REFERENCE provenance required')
    hashes={str(path.relative_to(root)):sha};entries=manifest.get('files')
    require(isinstance(entries,(dict,list)) and bool(entries),'Input file hashes required')
    for item in entries.values() if isinstance(entries,dict) else entries:
        require(isinstance(item,dict) and isinstance(item.get('path'),str),'Invalid manifest file')
        source=((root if isinstance(entries,dict) else path.parent)/item['path']).resolve()
        require(source.is_relative_to(allowed) and source.is_file(),'Invalid input path')
        actual=digest(source);require(actual==item.get('sha256'),'Input SHA-256 mismatch: '+item['path'])
        if mode=='OFFICIAL':
            ref=root/'backend/reference_manifest.json'
            require(not ref.exists() or actual not in read_json(ref)['files'].values(),'Reference input prohibited')
            for dev in (root/'data/evaluation').glob('*/data_manifest.json'):
                value=read_json(dev)
                if value.get('official') is False:
                    require(actual not in [x.get('sha256') for x in value.get('files',[]) if isinstance(x,dict)],'Development input prohibited')
            if source.suffix=='.json':
                def forbidden(v):
                    if isinstance(v,dict):
                        return v.get('synthetic') is True or v.get('dev_only') is True or any(str(v.get(k,'')).upper() in {'DEV','DEV_ONLY','DEVELOPMENT','REFERENCE','V62_FROZEN_REFERENCE'} for k in ('source_type','data_class','run_mode')) or any(forbidden(x) for x in v.values())
                    return any(forbidden(x) for x in v) if isinstance(v,list) else False
                require(not forbidden(read_json(source)),'DEV/reference input prohibited')
        hashes[str(source.relative_to(root))]=actual
    # Metric + external ID is global across modes and survives server restarts.
    key=hashlib.sha256((metric+'\0'+payload['external_run_id']).encode()).hexdigest()
    index=root/'results/integrations';index.mkdir(parents=True,exist_ok=True);reservation=index/(key+'.json')
    try:fd=os.open(reservation,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError:raise EvaluationError('Duplicate external_run_id for metric','DUPLICATE_EXTERNAL_RUN')
    with os.fdopen(fd,'w') as f:json.dump({'metric_id':metric,'external_run_id':payload['external_run_id'],'status':'RESERVED'},f)
    result={'dataset_id':dataset,'source_type':mode,'score':score,'sample_count':count,'status':'COMPLETED','details':details,
            'input_sha256':hashes,'dataset_manifest_sha256':sha,'provenance':{k:payload[k] for k in ['source_module','source_version','external_run_id','submitted_at']}}
    # A persistence failure leaves a reservation, preventing an uncertain duplicate.
    result=save_run(root,metric,mode,config,result,rows,received=payload)
    reservation.write_text(json.dumps({'metric_id':metric,'external_run_id':payload['external_run_id'],'run_id':result['run_id'],'status':'COMPLETED'}))
    return result
