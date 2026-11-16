"""Provenance-only snapshot freeze; no semantic regeneration/GT comparison."""
from pathlib import Path
import copy,csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.m02_provenance_restore import restore,SCHEMA_VERSION
from backend.m02_semantic_scope import scope_steps
from backend.m02_completion_semantics import canonical
from backend.m02_logical_candidate import REQUIRED_DEPENDENCIES
from backend.evaluators import csv_evidence
SOURCE='evaluation_contracts/development/m02_logical_evaluation_v2_completion'
DEST='evaluation_contracts/development/m02_logical_evaluation_v3_provenance'
SOURCE_HASH='aa7ff8dede4cf549614508512d4f51d9644c2b0179c359a3c68dc1c064363e84'
CHANGED={'backend/semantic_enrichment.py','backend/m02_logical_candidate.py','backend/m02_candidate.py'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=ROOT/SOURCE
    if sha(source/'manifest.json')!=SOURCE_HASH:raise ValueError('Previous snapshot changed')
    previous=json.loads((source/'manifest.json').read_text());hashes={}
    for name,h in previous['input_code_sha256'].items():
        p=Path(name) if Path(name).is_absolute() else ROOT/name
        if name not in CHANGED and sha(p)!=h:raise ValueError('Unapproved input change: '+name)
        hashes[name]=sha(p)
    for name,h in previous['outputs'].items():
        if sha(source/name)!=h:raise ValueError('Previous generated/rule artifact changed')
        hashes[SOURCE+'/'+name]=h
    rawpath='data/development/current_site_unseen_validation_v1/events.csv'
    raw=list(csv.DictReader((ROOT/rawpath).open()))
    old=json.loads((source/'business_steps.json').read_text());new,diff=restore(old,raw)
    execution_path='data/development/current_site_unseen_validation_v1/validation_execution_manifest.csv'
    executions=list(csv.DictReader((ROOT/execution_path).open()))
    scoped=scope_steps(new,executions,previous['scope_summary']['target_units'])
    if scoped['scope_summary']!=previous['scope_summary']:raise ValueError('Scope/count changed')
    owners={s['generated_step_id']:s.get('business_unit_ids',[]) for s in scoped['ownership_ledger']}
    event_bu={}
    for step in scoped['ownership_ledger']:
        for eid in step['source_event_ids']:event_bu.setdefault(eid,set()).update(owners[step['generated_step_id']])
    for item in diff:item['business_unit_ids']=sorted(event_bu.get(item['source_event_id'],set()))
    rows=[dict(row_type='generated_step',match_status='NOT_EVALUATED',**s) for s in scoped['ownership_ledger']]
    for p in new['processes']:
        rows.extend(dict(row_type='technical_evidence',match_status='AUXILIARY_NOT_DIRECT',process_id=p['source_process_id'],**e) for e in p['unlinked_technical_evidence'])
    rows.extend(dict(row_type='raw_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in new['raw_evidence_ledger'])
    out=ROOT/DEST;out.mkdir(exist_ok=False)
    outputs={'business_steps.json':new,'scope.json':scoped,'provenance_diff.json':dict(schema_version=SCHEMA_VERSION,evidence_entities_added=0,causal_inference=False,events=diff)}
    for name,value in outputs.items():(out/name).write_bytes(canonical(value))
    for name in ['gt_roles.json','logical_contract.json','completion_rules.json']:(out/name).write_bytes((source/name).read_bytes())
    (out/'evidence_preview.csv').write_text(csv_evidence(rows),encoding='utf-8')
    for name in sorted(REQUIRED_DEPENDENCIES):hashes[name]=sha(ROOT/name)
    hashes[SOURCE+'/manifest.json']=SOURCE_HASH
    artifacts={k:dict(path=DEST+'/'+n,sha256=sha(out/n)) for k,n in [('business_steps','business_steps.json'),('scope','scope.json')]}
    hashes.update({v['path']:v['sha256'] for v in artifacts.values()})
    m=copy.deepcopy(previous);m.update(input_code_sha256=hashes,comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),
        generated_artifacts=artifacts,verification='PENDING_INDEPENDENT_VERIFICATION',
        generation_policy='PROVENANCE_ONLY_NO_MODEL_SERIALIZER_OR_COMPLETION_REGENERATION',
        provenance_source_manifest=SOURCE+'/manifest.json',provenance_source_sha256=SOURCE_HASH,
        provenance_schema_version=SCHEMA_VERSION,score_computed=False,
        outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_bytes(canonical(m))
    print(json.dumps(dict(manifest_sha256=sha(out/'manifest.json'),restored_event_count=len(diff),scope=scoped['scope_summary'],outputs=m['outputs'],score_computed=False),indent=2))
if __name__=='__main__':main()
