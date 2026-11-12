"""Main-web bridge to frozen M05 engine and central evaluator. No cleaning rules."""
import json
import uuid
from pathlib import Path
from . import m05_full_context as fc
from .m05_readiness_web import load_dataset
from .m05_session_candidate import prepare, validate_response, CONFIG_PATH
from .m05_development_contract import calculate_binary
from .m05_full_context_csv import recalculate_csv
from .evaluators import require, call_adapter, EvaluationError
from .run_storage import save_run

DATASET='raw01_raw02_raw03_target20_20261111'
FREEZE='evaluation_contracts/development/m05_session_cleaning_frozen_v2/freeze.json'
FREEZE_HASH='077eb74cb94c998fd2bdb3d304ad1eaf1a22c6881c794979926042c5dd975931'

def verify_freeze(root):
    root=Path(root)
    require(fc.sha(root/FREEZE)==FREEZE_HASH,'M05 freeze changed')
    freeze=json.loads((root/FREEZE).read_text())
    for entry in freeze['immutable_implementation_artifacts']+[freeze['baseline_freeze']]:
        require(fc.sha(root/entry['path'])==entry['sha256'],'M05 frozen artifact changed: '+entry['path'])
    return freeze

def inputs(root):
    freeze=verify_freeze(root)
    manifest,_=load_dataset(root,DATASET)
    config=json.loads((Path(root)/CONFIG_PATH).read_text())
    return manifest,config,prepare(root,manifest,config),freeze

def readiness(root):
    try:
        m,c,p,f=inputs(root)
        return dict(status='READY',dataset_id=DATASET,details=dict(full_event_count=len(p['events']),target_event_count=len(p['targets']),context_event_count=len(p['events'])-len(p['targets']),model_version=c['cleaning_model_version'],config_path=CONFIG_PATH,config_sha256=fc.sha(Path(root)/CONFIG_PATH),input_sha256=p['binding'],selection_method='전체 417 events를 처리하고 기존 KEEP 10 / REMOVE 10 target만 scoring. DEVELOPMENT 전용.'))
    except (EvaluationError,OSError,ValueError,KeyError,TypeError) as exc:
        return dict(status='BLOCKED',dataset_id=DATASET,details={'missing':[str(exc)]},error=str(exc))

def run(root,web_config):
    root=Path(root); manifest,config,p,freeze=inputs(root)
    started=fc.utc_now().isoformat()
    # Explicit user-requested reproduction: preserve original one-shot result/claim.
    archive=root/'results/development/m05_web_reproductions'/uuid.uuid4().hex
    archive.mkdir(parents=True,exist_ok=False)
    fc.write_json(archive/'attempt.json',dict(status='STARTED',started_at_utc=started,binding=p['binding']))
    for name,value in [('engine_input.json',{'events':p['events']}),('locked_target_snapshot.json',{'targets':p['targets']}),('engine_config.json',config),('normalization_provenance.json',p['provenance'])]:fc.write_json(archive/name,value)
    response=call_adapter(config,'cleaning',{'events':p['events']},root)
    fc.write_json(archive/'full_predictions.json',response)
    by=validate_response(response,p['events'],config)
    metadata=dict(model_version=config['cleaning_model_version'],model_sha256=config['model_artifact']['sha256'],adapter_sha256=config['adapter_artifact']['sha256'],**p['binding'],target_labels_sha256=manifest['target_labels']['sha256'],run_mode='DEVELOPMENT',is_target=True,evaluation_eligibility=p['development_policy']['eligibility'],held_out_evidence_status=p['development_policy']['held_out_evidence_status'])
    result,rows=calculate_binary(p['targets'],[dict(event_id=t['event_id'],predicted_label=by[t['event_id']]['label']) for t in p['targets']],metadata)
    for row in rows:
        pred=by[row['event_id']]
        row.update(p['provenance'][row['event_id']],held_out='',remove_reason=pred['remove_reason'],duplicate_of_event_id=pred['duplicate_of_event_id'])
    checked=recalculate_csv(fc.csv_text(rows))
    require(all(result[k]==v for k,v in checked.items()),'CSV mismatch')
    require(inputs(root)[2]==p,'Input changed during run')
    require(web_config['targets']['M05']==result['target'],'M05 target mismatch')
    details=dict(result,**readiness(root)['details'],csv_recalculation='PASS',engine_freeze_sha256=FREEZE_HASH,known_limitations=freeze['known_limitations'])
    details.update({k.lower():result[k] for k in ('TP','FP','FN','TN')})
    saved=save_run(root,'M05','DEVELOPMENT',web_config,dict(status='COMPLETED',score=result['f1'],sample_count=20,dataset_id=DATASET,source_type='DEVELOPMENT',details=details,input_sha256=p['binding'],started_at=started,evaluator_version='frozen-central-m05-binary',reproduction_archive=str(archive.relative_to(root))),rows)
    evidence=root/'results/development'/saved['run_id']/'evidence.csv'
    require(recalculate_csv(evidence.read_text(encoding='utf-8-sig'))==checked,'Saved evidence mismatch')
    fc.write_json(archive/'result.json',saved)
    fc.write_json(archive/'run_manifest.json',dict(status='COMPLETE',web_run_id=saved['run_id'],full_event_count=len(p['events']),target_event_count=20,files={x.name:fc.sha(x) for x in archive.iterdir() if x.is_file()}))
    return saved
