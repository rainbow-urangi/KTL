"""GT-independent abstraction, then GT-only contract materialization; no comparison."""
from pathlib import Path
import copy,csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.m02_business_abstraction import abstract,RULES,canonical
from backend.m02_abstraction_comparator import RULES as COMPARISON_RULES,CONTRACT
from backend.m02_abstraction_candidate import REQUIRED_DEPENDENCIES,DATASET,SNAPSHOT
from backend.m02_semantic_scope import scope_steps
from backend.evaluators import csv_evidence
SOURCE='evaluation_contracts/development/m02_logical_evaluation_v3_provenance'
SOURCE_HASH='972f0460adc8bac5490bb5754188a1b11050c3c044353ce5e155f1262e4c0f72'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 source=ROOT/SOURCE
 if sha(source/'manifest.json')!=SOURCE_HASH:raise ValueError('Frozen source manifest changed')
 previous=json.loads((source/'manifest.json').read_text());hashes={}
 for name,h in previous['input_code_sha256'].items():
  p=Path(name) if Path(name).is_absolute() else ROOT/name
  if name not in ('backend/m02_candidate.py','frontend/app.js') and sha(p)!=h:raise ValueError('Unexpected source/model change: '+name)
  hashes[name]=sha(p)
 for name,h in previous['outputs'].items():
  if sha(source/name)!=h:raise ValueError('Original source output changed')
  hashes[SOURCE+'/'+name]=h
 old=json.loads((source/'business_steps.json').read_text())
 raw_path='data/development/current_site_unseen_validation_v1/events.csv';raw=list(csv.DictReader((ROOT/raw_path).open()))
 output=abstract(old,raw)  # no execution IDs, BU/GT labels, role counts or comparison results
 # Freeze serializer output bytes before loading evaluation-only role metadata.
 out=ROOT/SNAPSHOT;out.mkdir(exist_ok=False);(out/'business_steps.json').write_bytes(canonical(output))
 execution_path='data/development/current_site_unseen_validation_v1/validation_execution_manifest.csv'
 executions=list(csv.DictReader((ROOT/execution_path).open()));targets=previous['scope_summary']['target_units']
 scoped=scope_steps(output,executions,targets)
 (out/'scope.json').write_bytes(canonical(scoped))
 # Original GT roles remain unchanged; this is evaluation-only, after serialization.
 (out/'gt_roles.json').write_bytes((source/'gt_roles.json').read_bytes())
 (out/'abstraction_rules.json').write_bytes(canonical(RULES));(out/'comparison_contract.json').write_bytes(canonical(COMPARISON_RULES))
 rows=[dict(row_type='generated_step',match_status='NOT_EVALUATED',**s) for s in scoped['ownership_ledger']]
 rows.extend(dict(row_type='raw_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in output['raw_evidence_ledger'])
 rows.extend(dict(row_type='technical_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in output['original_technical_evidence_ledger'])
 rows.extend(dict(row_type='evidence_disposition',**e) for e in output['raw_event_disposition'])
 rows.extend(dict(row_type='unresolved_source_reference',**e) for e in output.get('unresolved_source_references',[]))
 (out/'evidence_preview.csv').write_text(csv_evidence(rows),encoding='utf-8')
 for name in REQUIRED_DEPENDENCIES:hashes[name]=sha(ROOT/name)
 hashes[SOURCE+'/manifest.json']=SOURCE_HASH
 artifacts={key:dict(path=SNAPSHOT+'/'+name,sha256=sha(out/name)) for key,name in [('business_steps','business_steps.json'),('scope','scope.json')]}
 hashes.update({v['path']:v['sha256'] for v in artifacts.values()})
 boundary=dict(previous['evaluation_boundary'],comparison_contract=CONTRACT)
 m=dict(stage='PRE_ABSTRACTION_COMPARISON',score_computed=False,run_mode='DEVELOPMENT',official=False,verification='PENDING_INDEPENDENT_VERIFICATION',
  dataset_id=DATASET,serializer_version=output['serializer_version'],model_version=previous['model_version'],model_binding=previous['model_binding'],
  input_code_sha256=hashes,comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),source_snapshot_path=SOURCE+'/manifest.json',source_snapshot_sha256=SOURCE_HASH,
  evaluation_boundary=boundary,generated_artifacts=artifacts,scope_summary=scoped['scope_summary'],
  serializer_input_policy='RAW_ONLY_SEMANTICS_FROZEN_MODEL_MEMBERSHIP_IDS_NO_GT_COUNTS_OR_PREDICTION_LABELS',
  outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 (out/'manifest.json').write_bytes(canonical(m))
 print(json.dumps(dict(manifest_sha256=sha(out/'manifest.json'),scope=scoped['scope_summary'],score_computed=False),indent=2))
if __name__=='__main__':main()
