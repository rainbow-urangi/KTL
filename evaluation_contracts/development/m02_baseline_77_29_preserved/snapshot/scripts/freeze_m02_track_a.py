"""Track A isolated candidate freeze. No GT comparison or shared web mutation."""
from pathlib import Path
import csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.m02_track_a_native_submit import recover,RULES,canonical
from backend.m02_track_a_candidate import REQUIRED_DEPENDENCIES,SNAPSHOT
from backend.m02_semantic_scope import scope_steps
from backend.evaluators import csv_evidence
SOURCE='evaluation_contracts/development/m02_business_abstraction_v1'
SOURCE_HASH='d00201019debb6f7488c3dae9123f08bb4c15cf4d762244180d0b5b4ab2616b8'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 source=ROOT/SOURCE
 if sha(source/'manifest.json')!=SOURCE_HASH:raise ValueError('Baseline manifest changed')
 previous=json.loads((source/'manifest.json').read_text());gate=json.loads((source/'independent_verification.json').read_text())
 if gate.get('verdict')!='PASS' or gate.get('snapshot_manifest_sha256')!=SOURCE_HASH:raise ValueError('Baseline PASS provenance unavailable')
 hashes={}
 for name in REQUIRED_DEPENDENCIES:
  p=ROOT/name
  if name in previous['input_code_sha256'] and sha(p)!=previous['input_code_sha256'][name]:raise ValueError('Frozen semantic dependency changed: '+name)
  hashes[name]=sha(p)
 for name,h in previous['model_binding']['file_sha256'].items():
  if sha(ROOT/name)!=h:raise ValueError('Model file changed')
  hashes[name]=h
 model=previous['model_binding'];hashes[model['manifest_path']]=model['manifest_sha256']
 if sha(ROOT/model['manifest_path'])!=model['manifest_sha256']:raise ValueError('Model manifest changed')
 for name,h in previous['outputs'].items():
  if sha(source/name)!=h:raise ValueError('Baseline output changed')
  hashes[SOURCE+'/'+name]=h
 raw_path='data/development/current_site_unseen_validation_v1/events.csv';execution_path='data/development/current_site_unseen_validation_v1/validation_execution_manifest.csv'
 for name in (raw_path,execution_path):
  if sha(ROOT/name)!=previous['input_code_sha256'][name]:raise ValueError('Original data changed')
  hashes[name]=sha(ROOT/name)
 old=json.loads((source/'business_steps.json').read_text());rows=list(csv.DictReader((ROOT/raw_path).open()))
 new=recover(old,rows)  # No GT, execution manifest, labels or scores.
 out=ROOT/SNAPSHOT;out.mkdir(exist_ok=False);(out/'business_steps.json').write_bytes(canonical(new))
 scoped=scope_steps(new,list(csv.DictReader((ROOT/execution_path).open())),previous['scope_summary']['target_units'])
 if scoped['scope_summary']!=previous['scope_summary']:raise ValueError('Native-only recovery changed scope/counts')
 (out/'scope.json').write_bytes(canonical(scoped));(out/'native_submit_rules.json').write_bytes(canonical(RULES))
 for name in ('gt_roles.json','comparison_contract.json','abstraction_rules.json'):(out/name).write_bytes((source/name).read_bytes())
 before_steps={s['generated_step_id']:s for p in old['processes'] for s in p['business_steps']};after_steps={s['generated_step_id']:s for p in new['processes'] for s in p['business_steps']}
 if set(before_steps)!=set(after_steps):raise ValueError('Intent identities changed')
 diffs=[]
 for sid,before in before_steps.items():
  after=after_steps[sid];changed={k:dict(before=before.get(k),after=after.get(k)) for k in set(before)|set(after) if before.get(k)!=after.get(k)}
  if changed:diffs.append(dict(generated_step_id=sid,changed_fields=changed))
 (out/'evidence_diff.json').write_bytes(canonical(dict(before_snapshot_sha256=previous['outputs']['business_steps.json'],changed_steps=diffs,audit=new['native_submit_recovery_audit'])))
 evidence=[dict(row_type='generated_step',match_status='NOT_EVALUATED',**s) for s in scoped['ownership_ledger']]
 evidence.extend(dict(row_type='raw_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in new['raw_evidence_ledger'])
 evidence.extend(dict(row_type='evidence_disposition',**e) for e in new['raw_event_disposition'])
 evidence.extend(dict(row_type='technical_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in new['original_technical_evidence_ledger'])
 evidence.extend(dict(row_type='native_submit_audit',**e) for e in new['native_submit_recovery_audit'])
 (out/'evidence_preview.csv').write_text(csv_evidence(evidence),encoding='utf-8')
 hashes[SOURCE+'/manifest.json']=SOURCE_HASH;hashes[SOURCE+'/independent_verification.json']=sha(source/'independent_verification.json')
 artifacts={key:dict(path=SNAPSHOT+'/'+name,sha256=sha(out/name)) for key,name in [('business_steps','business_steps.json'),('scope','scope.json')]};hashes.update({v['path']:v['sha256'] for v in artifacts.values()})
 shared=[]
 for name in ('backend/server.py','frontend/app.js'):
  shared.append(dict(path=name,baseline_sha256=previous['input_code_sha256'][name],current_sha256=sha(ROOT/name),role='SHARED_INTEGRATION_PENDING_NOT_EXECUTED_BY_ISOLATED_CANDIDATE'))
 manifest=dict(stage='PRE_TRACK_A_COMPARISON',score_computed=False,run_mode='DEVELOPMENT',official=False,verification='PENDING_INDEPENDENT_VERIFICATION',
  serializer_version=new['serializer_version'],model_version=previous['model_version'],model_binding=model,
  input_code_sha256=hashes,comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),source_snapshot_path=SOURCE+'/manifest.json',source_snapshot_sha256=SOURCE_HASH,
  generated_artifacts=artifacts,evaluation_boundary=previous['evaluation_boundary'],scope_summary=scoped['scope_summary'],
  unchanged_comparison_contract_sha256=previous['outputs']['comparison_contract.json'],shared_web_integration_pending=True,shared_dependency_observations=shared,
  outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 (out/'manifest.json').write_bytes(canonical(manifest))
 print(json.dumps(dict(manifest_sha256=sha(out/'manifest.json'),scope=scoped['scope_summary'],native_audit=new['native_submit_recovery_audit'],score_computed=False,shared_web_integration_pending=True),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
