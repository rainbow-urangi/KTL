"""Isolated Track A candidate. No shared web routing changes; no implicit evaluation."""
from pathlib import Path
from .evaluators import read_json,digest,require
from .m02_abstraction_comparator import CONTRACT,VERSION,evaluate,LogicalSchemaError

SNAPSHOT='evaluation_contracts/development/m02_track_a_native_submit_v1'
DATASET='v1_2_1_unseen_m02_development'
REQUIRED_DEPENDENCIES=frozenset((
 'backend/m02_track_a_native_submit.py','backend/m02_track_a_candidate.py',
 'backend/semantic_enrichment.py','backend/business_process_serializer.py',
 'backend/m02_semantic_scope.py','backend/m02_abstraction_comparator.py','backend/m02_logical_comparator.py',
 'backend/evaluators.py','backend/run_storage.py','scripts/freeze_m02_track_a.py',
 'docs/agents/TRACK_A_NATIVE_SUBMIT_CONTRACT.md'))

def verify(root,manifest,sources):
 hashes=manifest['input_code_sha256']
 require(REQUIRED_DEPENDENCIES<=set(hashes) and REQUIRED_DEPENDENCIES<=set(manifest['comparison_dependencies']),'Incomplete abstraction dependency freeze')
 for name,h in hashes.items():
  p=Path(name) if Path(name).is_absolute() else root/name
  require(p.is_file() and digest(p)==h,'Frozen abstraction dependency changed: '+name);sources[name]=h
 model=manifest['model_binding'];model_manifest=read_json(root/model['manifest_path'])
 declared={str(Path(model['manifest_path']).parent/name):h for name,h in model_manifest['file_sha256'].items()}
 require(declared==model['file_sha256'] and hashes.get(model['manifest_path'])==model['manifest_sha256'] and all(hashes.get(n)==h for n,h in declared.items()),'Model freeze incomplete')
 require(manifest['evaluation_boundary']['comparison_contract']==CONTRACT,'Abstraction comparison contract changed')
 for name,h in manifest['outputs'].items():
  require(digest(root/SNAPSHOT/name)==h,'Abstraction output changed: '+name);sources[SNAPSHOT+'/'+name]=h
 for item in manifest['generated_artifacts'].values():require(hashes.get(item['path'])==item['sha256'],'Generated artifact not bound')

def assess(root):
 root=Path(root).resolve();directory=root/SNAPSHOT;m=read_json(directory/'manifest.json');sources={SNAPSHOT+'/manifest.json':digest(directory/'manifest.json')}
 require(m['score_computed'] is False and m['stage']=='PRE_TRACK_A_COMPARISON','Freeze must precede comparison');verify(root,m,sources)
 snapshot=read_json(root/m['generated_artifacts']['business_steps']['path']);generated=read_json(root/m['generated_artifacts']['scope']['path']);scope=generated['scope_summary']
 roles=read_json(directory/'gt_roles.json')
 details=dict(model_version=m['model_version'],serializer_version=snapshot['serializer_version'],serializer_hash=snapshot['serializer_rules_hash'],
  serializer_snapshot_hash=m['source_snapshot_sha256'],evaluation_contract_hash=digest(directory/'manifest.json'),comparison_contract=CONTRACT,
  input_dataset=DATASET,ground_truth_count=len(scope['target_units']),target_ground_truth_ids=scope['target_units'],business_unit_count=20,
  process_model_count=len(snapshot['processes']),evaluated_procedures=scope['total_generated_steps'],defined_required=roles['required_count'],
  all_generated_procedures=scope['all_generated_steps'],mixed_count=scope['mixed_count'],unassigned_count=scope['unassigned_count'],out_of_scope_count=scope['out_of_scope_count'],
  scope_policy=scope['policy'],technical_evidence_count=snapshot['technical_evidence_count'],formula='sqrt(Accuracy * Completeness)',target=75,
  auxiliary_evidence_counted=False,comparison_status='PENDING_TRACK_A_VERIFICATION',missing=[],per_business_unit=[])
 rows=[dict(row_type='generated_step',match_status='NOT_EVALUATED',**s) for s in generated['ownership_ledger']]
 rows.extend(dict(row_type='technical_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in snapshot['original_technical_evidence_ledger'])
 rows.extend(dict(row_type='raw_evidence',match_status='AUXILIARY_NOT_DIRECT',**e) for e in snapshot['raw_evidence_ledger'])
 rows.extend(dict(row_type='evidence_disposition',**e) for e in snapshot['raw_event_disposition'])
 rows.extend(dict(row_type='native_submit_audit',**e) for e in snapshot.get('native_submit_recovery_audit',[]))
 rows.extend(dict(row_type='unresolved_source_reference',**e) for e in snapshot.get('unresolved_source_references',[]))
 for bu in scope['target_units']:
  details['per_business_unit'].append(dict(business_unit_id=bu,generated_count=scope['per_business_unit'][bu],
   required_count=len(next(p for p in roles['processes'] if p['id']==bu)['procedures']),matched_count=None,included_required_count=None,unmatched_count=None,missing_count=None,accuracy=None,completeness=None,score=None,status='PENDING_INDEPENDENT_VERIFICATION'))
 gate=read_json(directory/'independent_verification.json') if (directory/'independent_verification.json').is_file() else {}
 approved=gate.get('verdict')=='PASS' and gate.get('snapshot_manifest_sha256')==digest(directory/'manifest.json') and gate.get('gt_leakage_check')=='PASS' and gate.get('scope_check')=='PASS' and gate.get('direct_comparison_contract')==CONTRACT and gate.get('native_submit_recovery_check')=='PASS'
 if not approved:
  details['missing']=['Independent PASS for isolated Track A native submitter recovery and exact manifest hash required; shared web integration remains separate.']
  return dict(status='NOT_CONFIGURED',score=None,sample_count=len(scope['target_units']),dataset_id=DATASET,source_type='DEVELOPMENT',evaluator_version=VERSION,input_sha256=sources,details=details),rows
 boundary=m['evaluation_boundary'];gt=root/boundary['td04_path'];require(gt.resolve().is_relative_to(root) and digest(gt)==boundary['td04_sha256'],'Original GT source changed')
 truth=read_json(gt);require({p['id'] for p in truth['processes']}==set(scope['target_units']),'GT scope changed');sources[boundary['td04_path']]=digest(gt)
 try:score,count,stats,evidence=evaluate(generated,truth,roles)
 except LogicalSchemaError as exc:
  details.update(comparison_status='INVALID_ABSTRACTION_SCHEMA',missing=[str(exc)])
  return dict(status='NOT_CONFIGURED',score=None,sample_count=len(scope['target_units']),dataset_id=DATASET,source_type='DEVELOPMENT',evaluator_version=VERSION,input_sha256=sources,details=details),rows
 details.update(stats,comparison_status='COMPLETED_WITH_MISSING_EVIDENCE' if stats['semantic_uncertainties'] else 'COMPLETED',missing=[])
 direct={e['detected_id']:e for e in evidence if e['direct_match']}
 for row in rows:
  if row['row_type']=='generated_step':
   inside=row['in_m02_denominator'];hit=direct.get(row['generated_step_id'])
   row['match_status']=('MATCHED' if hit else 'UNMATCHED') if inside else 'UNASSIGNED' if row['business_unit_ownership']=='UNASSIGNED' else 'OUT_OF_SCOPE'
   row['matched_required_step_id']=hit['required_step_id'] if hit else ''
 rows.extend(dict(row_type='required_step',match_status='INCLUDED' if e['required_included'] else 'MISSING',**e) for e in evidence)
 rows.extend(dict(row_type='business_summary',**s) for s in details['per_business_unit'])
 rows.append(dict(row_type='aggregate_calculation',**{k:v for k,v in stats.items() if k not in ('per_business_unit','semantic_uncertainties')},score=score,
  accuracy_numerator=stats['correctly_mapped'],accuracy_denominator=stats['evaluated_procedures'],completeness_numerator=stats['included_required'],completeness_denominator=stats['defined_required']))
 return dict(status='COMPLETED',score=score,sample_count=count,dataset_id=DATASET,source_type='DEVELOPMENT',evaluator_version=VERSION,input_sha256=sources,details=details),rows
