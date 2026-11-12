"""User-decided 20-event M05 contract; not a KTL confirmation or M02 mutation."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from .evaluators import EvaluationError, require, call_adapter

TARGET = .79
CATEGORIES = {'duplicate', 'noise', 'repeated_action', 'irrelevant_action'}
CONTRACT = {'total':20, 'REMOVE':10, 'KEEP':10, 'target':TARGET,
            'authority':'USER_DECISION', 'ktl_confirmation':False, 'run_mode':'DEVELOPMENT'}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()).hexdigest()

def check_events(events):
    require(isinstance(events,list) and len(events)==20, 'M05 requires exactly 20 events')
    require(all(isinstance(e,dict) for e in events), 'Invalid events')
    ids=[e.get('event_id') for e in events]
    require(all(isinstance(i,str) and i.strip() for i in ids) and len(set(ids))==20, 'Duplicate or invalid event_id')
    require(Counter(e.get('expected_label') for e in events)=={'REMOVE':10,'KEEP':10}, 'REMOVE 10 / KEEP 10 required')
    for e in events:
        require(e.get('held_out') is True, 'held_out=true required')
        require(e['expected_label']=='KEEP' or e.get('remove_category') in CATEGORIES, 'Invalid remove_category')
        require(isinstance(e.get('features'),dict) and e['features'], 'Raw model features required')
        forbidden={'label','expected_label','remove_category','category','ground_truth','prediction','predicted_label','held_out'}
        def safe(v):
            return (not forbidden.intersection(str(k).lower() for k in v) and all(safe(x) for x in v.values())) if isinstance(v,dict) else all(safe(x) for x in v) if isinstance(v,list) else True
        require(safe(e['features']), 'GT leakage in model features')
    return events

def verified_json(root, entry):
    p=(root/entry['path']).resolve()
    require(p.is_relative_to(root.resolve()), 'Artifact outside repository')
    require(p.is_file() and sha(p)==entry.get('sha256'), 'Artifact hash mismatch: '+str(p))
    return json.loads(p.read_text()),p

def validate_dataset(root, manifest):
    root=Path(root)
    require(manifest.get('used_for_training') is False and manifest.get('used_for_development') is False, 'Prior-use declarations required')
    obj,path=verified_json(root,manifest['dataset'])
    require(path.is_relative_to((root/'data/held_out').resolve()), 'Evaluation dataset must be separated under data/held_out')
    events=check_events(obj['events'])
    proof=manifest.get('provenance',{})
    require(proof.get('reviewer') and proof.get('reviewed_at') and proof.get('complete_history_attested') is True, 'HELD_OUT_PROVENANCE_INSUFFICIENT')
    require(proof.get('training_inventories') and proof.get('development_inventories'), 'Training and development inventories required')
    ids={e['event_id'] for e in events}; fingerprints={digest(e['features']) for e in events}
    inventory_hashes=[]
    for scope in ('training','development'):
        for entry in proof[scope+'_inventories']:
            history,_=verified_json(root,entry)
            require(history.get('scope')==scope, 'History scope mismatch')
            require(isinstance(history.get('events'),list) and history['events'], 'Nonempty history event inventory required')
            require(history.get('source_files'), 'History source files required')
            actual=[]
            for source in history['source_files']:
                raw,_=verified_json(root,source)
                require(isinstance(raw.get('events'),list) and raw['events'], 'Nonempty source events required')
                for event in raw['events']:
                    require(isinstance(event.get('event_id'),str) and isinstance(event.get('features'),dict) and event['features'], 'Source event identity/features missing')
                    actual.append({'event_id':event['event_id'],'feature_sha256':digest(event['features'])})
            require(sorted(actual,key=lambda e:(e['event_id'],e['feature_sha256']))==sorted(history['events'],key=lambda e:(e['event_id'],e['feature_sha256'])), 'History inventory does not reproduce source rows')
            for e in actual:
                require(e['event_id'] not in ids and e['feature_sha256'] not in fingerprints, 'HELD_OUT_OVERLAP')
            inventory_hashes.append(entry['sha256'])
    require(proof.get('audit_evidence'), 'HELD_OUT_PROVENANCE_INSUFFICIENT')
    audit_hashes=[]
    for entry in proof['audit_evidence']:
        audit,_=verified_json(root,entry)
        require(audit.get('dataset_sha256')==manifest['dataset']['sha256'] and
                sorted(audit.get('inventory_sha256',[]))==sorted(inventory_hashes) and
                audit.get('method')=='SOURCE_HISTORY_RECONCILIATION' and
                audit.get('findings') and audit.get('coverage_complete') is True,
                'Audit must substantiate dataset and complete source inventory coverage')
        audit_hashes.append(entry['sha256'])
    # Dataset-supplied assertions are not authority. An independent review must
    # pre-register the exact evidence bundle in a separately maintained registry.
    registry_path=root/'evaluation_contracts/m05_approved_provenance.json'
    require(registry_path.is_file(), 'INDEPENDENT_PROVENANCE_APPROVAL_MISSING')
    registry=json.loads(registry_path.read_text())
    approval=next((x for x in registry.get('approvals',[]) if x.get('dataset_sha256')==manifest['dataset']['sha256']),None)
    require(approval and approval.get('status')=='PASS' and approval.get('reviewer') and
            approval.get('reviewer')!=proof['reviewer'] and approval.get('reviewed_at') and
            sorted(approval.get('inventory_sha256',[]))==sorted(inventory_hashes) and
            sorted(approval.get('audit_sha256',[]))==sorted(audit_hashes),
            'INDEPENDENT_PROVENANCE_APPROVAL_MISSING')
    return events

def calculate(events,predictions,metadata):
    check_events(events)
    require(isinstance(predictions,list) and all(isinstance(p,dict) for p in predictions), 'Predictions required')
    ids=[p.get('event_id') for p in predictions]
    require(len(ids)==len(set(ids))==20 and set(ids)=={e['event_id'] for e in events}, 'Prediction ID mismatch')
    require(all(p.get('predicted_label') in {'REMOVE','KEEP'} for p in predictions), 'Invalid prediction')
    pred={p['event_id']:p['predicted_label'] for p in predictions}; rows=[]
    for e in events:
        p=pred[e['event_id']]
        outcome=('TP' if e['expected_label']=='REMOVE' else 'FP') if p=='REMOVE' else ('FN' if e['expected_label']=='REMOVE' else 'TN')
        rows.append(dict(event_id=e['event_id'],expected_label=e['expected_label'],predicted_label=p,remove_category=e.get('remove_category',''),classification=outcome,**metadata))
    c=Counter(r['classification'] for r in rows); tp,fp,fn,tn=(c[x] for x in ('TP','FP','FN','TN'))
    precision=tp/(tp+fp) if tp+fp else 0; recall=tp/(tp+fn) if tp+fn else 0
    f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0
    return dict(status='COMPLETE',run_mode='DEVELOPMENT',official_pass=None,total=20,REMOVE=10,KEEP=10,TP=tp,FP=fp,FN=fn,TN=tn,precision=precision,recall=recall,f1=f1,target=TARGET,passed=meets_target(f1)),rows

def meets_target(f1):
    return f1>=TARGET

def validate_engine(root,config):
    root=Path(root).resolve()
    require(config.get('cleaning_model_version') and config.get('model_artifact') and config.get('adapter_artifact') and config.get('interpreter_artifact'), 'REAL_CLEANING_ENGINE_NOT_CONFIGURED')
    resolved={}
    for key in ('model_artifact','adapter_artifact','interpreter_artifact'):
        p=(root/config[key]['path']).resolve()
        require((key=='interpreter_artifact' or p.is_relative_to(root)) and p.is_file() and sha(p)==config[key]['sha256'], 'Engine artifact hash mismatch')
        resolved[key]=str(p)
    # No shell, -c, modules or extra args: hashed entrypoint and model are the
    # actual command arguments, not unrelated artifacts beside another command.
    expected=[resolved['interpreter_artifact'],resolved['adapter_artifact'],'--model',resolved['model_artifact']]
    require(config.get('adapters',{}).get('cleaning')==expected, 'Engine argv must bind hashed interpreter, adapter and model')
    return expected

def evaluate(root, manifest, config):
    events=validate_dataset(root,manifest) # MUST precede engine call or scoring
    validate_engine(root,config)
    response=call_adapter(config,'cleaning',{'events':[{'id':e['event_id'],'features':e['features']} for e in events]},root)
    require(response.get('model_version')==config['cleaning_model_version'], 'Engine model version mismatch')
    predictions=[{'event_id':p['id'],'predicted_label':p['label']} for p in response.get('predictions',[])]
    return calculate(events,predictions,{'model_version':config['cleaning_model_version'],'model_sha256':config['model_artifact']['sha256'],'dataset_sha256':manifest['dataset']['sha256']})

def evidence_csv(rows):
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()
