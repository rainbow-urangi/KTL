"""파일 기반 평가 실행 저장. 공식 판정은 OFFICIAL에만 허용합니다."""
import json
import uuid
from datetime import datetime, timezone
from .evaluators import METRICS, csv_evidence


def now(): return datetime.now(timezone.utc).isoformat()

def save_run(root, metric, mode, config, result, rows, received=None):
    prefix={'REFERENCE':'REF','OFFICIAL':'EVAL','DEVELOPMENT':'DEV'}[mode]
    run_id=prefix+'-'+metric+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
    directory=root/'results'/mode.lower()/run_id;directory.mkdir(parents=True,exist_ok=False)
    target=config['targets'].get(metric); operator=METRICS[metric][3]
    score=result.get('score');threshold=None
    if score is not None and target is not None:
        threshold=score<=target if operator=='<=' else score>=target
    result.update(metric_id=metric,metric_name=METRICS[metric][0],run_id=run_id,run_mode=mode,target=target,operator=operator,
                  threshold_met=threshold,official_pass=threshold if mode=='OFFICIAL' else None)
    result['pass']=result['official_pass'];result.setdefault('started_at',now());result['completed_at']=now()
    result.setdefault('error',None);result.setdefault('evaluator_version','external-counts-v2-generated-code-denominator')
    result.setdefault('details',{})['rows']=rows
    result['input_paths']=list(result.get('input_sha256',{}))
    for key,name in [('evidence_file','evidence.csv'),('result_file','result.json'),('manifest_file','run_manifest.json')]:
        result[key]=f'/api/evaluations/{metric.lower()}/runs/{run_id}/{name}'
    result['evidence_files']=['result.json','evidence.csv','run_manifest.json']
    if received is not None:
        result['evidence_files'].append('received_payload.json')
        (directory/'received_payload.json').write_text(json.dumps(received,ensure_ascii=False,indent=2,allow_nan=False))
    (directory/'evidence.csv').write_text(csv_evidence(rows or [{'status':result['status'],'error':result.get('error')}]),encoding='utf-8')
    text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
    (directory/'result.json').write_text(text,encoding='utf-8')
    (directory/'run_manifest.json').write_text(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2,allow_nan=False))
    latest=directory.parent/('latest-'+metric+'.json');temp=latest.with_suffix('.tmp');temp.write_text(text,encoding='utf-8');temp.replace(latest)
    return result
