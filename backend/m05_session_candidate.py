"""Versioned DEVELOPMENT candidate runner; preserves baseline/raw/GT artifacts."""
import csv
import json
from pathlib import Path
from . import m05_full_context as fc
from .m05_development_contract import calculate_binary
from .m05_full_context_csv import recalculate_csv
from .m05_session_cleaning import context_from_raw, VERSION
from .m05_heldout import validate_engine
from .evaluators import require, call_adapter

CONFIG_PATH='evaluation_contracts/development/m05_session_cleaning_candidate/engine.json'


def prepare(root,manifest,config):
    root=Path(root).resolve()
    baseline=json.loads((root/'evaluation_contracts/m05_engine.json').read_text())
    p=fc.validate_bundle(root,manifest,baseline)
    validate_engine(root,config)
    rules=json.loads(Path(config['model_artifact']['path']).read_text())
    require(rules['rule_version']==VERSION,'CANDIDATE_VERSION_MISMATCH')
    for entry in rules['dependencies']:
        require(fc.sha(Path(entry['path']))==entry['sha256'],'CANDIDATE_DEPENDENCY_CHANGED')
    raw={}
    for name in {v['source_file'] for v in p['provenance'].values()}:
        with (root/name).open(newline='',encoding='utf-8-sig') as f:
            raw.update({r['event_id']:r for r in csv.DictReader(f)})
    events=[]
    for event in p['events']:
        c=context_from_raw(raw[event['id']],p['provenance'][event['id']]['validated_event_timestamp_utc'])
        events.append(dict(id=event['id'],features=dict(event['features'],context=c)))
    p['baseline_normalized_input_sha256']=p['binding']['normalized_input_sha256']
    p['events']=events
    p['binding']=dict(p['binding'],baseline_normalized_input_sha256=p['baseline_normalized_input_sha256'],
                       normalized_input_sha256=fc.digest({'events':events}),candidate_engine_config_sha256=fc.digest(config),
                       candidate_runner_sha256=fc.sha(Path(__file__)))
    p['bundle_sha256']=fc.digest(p['binding'])
    return p


def validate_response(response,events,config):
    require(response.get('model_version')==config['cleaning_model_version'],'ENGINE_VERSION_MISMATCH')
    rows=response.get('predictions',[]); ids=[r.get('id') for r in rows]
    require(len(ids)==len(set(ids))==len(events) and set(ids)=={e['id'] for e in events},'FULL_PREDICTION_ID_MISMATCH')
    by={p['id']:p for p in rows}; ev={e['id']:e for e in events}
    reasons={'empty_activity','drop_exact','drop_prefix','consecutive_same_activity',
             'collector_boot_diagnostic','redundant_empty_field_focus','current_navigation_no_observed_change'}
    for i,e in enumerate(events):
        p=by[e['id']]
        require(p['source_row_index']==i and p['case_id']==e['features']['case_id'] and p['activity']==e['features']['activity'],'PROVENANCE_CHANGED')
        require(p['label'] in {'KEEP','REMOVE'},'INVALID_LABEL')
        require((p['label']=='KEEP' and p['remove_reason'] is None and p['duplicate_of_event_id'] is None) or (p['label']=='REMOVE' and p['remove_reason'] in reasons),'INVALID_REASON')
        anchor=p['duplicate_of_event_id']
        if anchor:
            require(anchor in ev and anchor!=e['id'] and by[anchor]['label']=='KEEP' and ev[anchor]['features']['context']['session_id']==e['features']['context']['session_id'],'ANCHOR_INVALID')
        require(all(x in ev and ev[x]['features']['context']['session_id']==e['features']['context']['session_id'] for x in p.get('rule_evidence_event_ids',[])),'EVIDENCE_INVALID')
    return by


def evaluate(root,manifest,config):
    root=Path(root).resolve(); p=prepare(root,manifest,config)
    out=root/'results/development/m05_full_context'/p['bundle_sha256']
    out.parent.mkdir(parents=True,exist_ok=True)
    # One claim per candidate and complete input. Never overwrites baseline run.
    claim=out.parent/'attempts'/(p['bundle_sha256']+'.json')
    claim.parent.mkdir(exist_ok=True)
    run=dict(status='STARTED',run_id=out.name,run_mode='DEVELOPMENT',official_pass=None,
             binding=p['binding'],full_event_count=len(p['events']),target_event_count=20,
             context_event_count=len(p['events'])-20,started_at_utc=fc.utc_now().isoformat(),
             engine_status='CANDIDATE_PENDING_INDEPENDENT_VERIFICATION')
    fc.write_json(claim,run);out.mkdir();fc.write_json(out/'attempt.json',run)
    require(prepare(root,manifest,config)==p,'INPUT_CHANGED')
    for name,value in [('engine_input.json',{'events':p['events']}),('validated_manifest.json',manifest),
                       ('normalization_provenance.json',p['provenance']),('locked_target_snapshot.json',{'targets':p['targets']}),('engine_config.json',config)]:fc.write_json(out/name,value)
    response=call_adapter(config,'cleaning',{'events':p['events']},root)
    fc.write_json(out/'full_predictions.json',response)
    by=validate_response(response,p['events'],config)
    policy=p['development_policy']
    metadata=dict(model_version=config['cleaning_model_version'],model_sha256=config['model_artifact']['sha256'],adapter_sha256=config['adapter_artifact']['sha256'],
                  **p['binding'],target_labels_sha256=manifest['target_labels']['sha256'],target_selection_sha256=manifest['target_selection']['sha256'],
                  predictions_sha256=fc.sha(out/'full_predictions.json'),run_id=out.name,run_mode='DEVELOPMENT',is_target=True,
                  evaluation_eligibility=policy['eligibility'],held_out_evidence_status=policy['held_out_evidence_status'])
    result,rows=calculate_binary(p['targets'],[{'event_id':t['event_id'],'predicted_label':by[t['event_id']]['label']} for t in p['targets']],metadata)
    for row in rows:
        pred=by[row['event_id']]
        row.update(p['provenance'][row['event_id']],held_out='',remove_reason=pred['remove_reason'],duplicate_of_event_id=pred['duplicate_of_event_id'],rule_evidence_event_ids=json.dumps(pred.get('rule_evidence_event_ids',[])))
    evidence=fc.csv_text(rows);checked=recalculate_csv(evidence)
    require(all(result[k]==v for k,v in checked.items()),'CSV_MISMATCH')
    require(prepare(root,manifest,config)==p,'INPUT_CHANGED_DURING_INFERENCE')
    with (out/'evidence.csv').open('x',encoding='utf-8',newline='') as f:f.write(evidence)
    result.update(full_event_count=len(p['events']),target_event_count=20,context_event_count=len(p['events'])-20,run_id=out.name,csv_recalculation='PASS',engine_status=run['engine_status'])
    fc.write_json(out/'result.json',result)
    run.update(status='COMPLETE',completed_at_utc=fc.utc_now().isoformat(),files={f.name:fc.sha(f) for f in out.iterdir() if f.is_file()})
    fc.write_json(out/'run_manifest.json',run)
    return result,rows
