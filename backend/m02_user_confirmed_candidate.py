"""Owner-confirmed DEVELOPMENT comparison; exact-snapshot independent PASS required."""
from pathlib import Path
from .evaluators import read_json, digest, require
from .m02_user_confirmed_comparator import evaluate, CONTRACT, VERSION
SNAPSHOT='evaluation_contracts/development/m02_user_confirmed_v1'

def verify(root):
 root=Path(root); folder=root/SNAPSHOT; manifest=read_json(folder/'manifest.json')
 for name,h in manifest['sha256'].items():
  require(digest(root/name)==h,'Frozen dependency changed: '+name)
 gate=read_json(folder/'independent_verification.json') if (folder/'independent_verification.json').exists() else {}
 require(gate.get('verdict')=='PASS' and gate.get('snapshot_manifest_sha256')==digest(folder/'manifest.json') and gate.get('gt_leakage_check')=='PASS' and gate.get('provenance_check')=='PASS' and gate.get('generic_contract_check')=='PASS','Independent PASS for exact user-confirmed contract required')
 return manifest

def assess(root):
 root=Path(root);m=verify(root)
 generated=read_json(root/m['source_scope']);truth=read_json(root/m['td04']);roles=read_json(root/m['roles'])
 score,count,stats,evidence=evaluate(generated,truth,roles)
 stats.update(target=75,development_target_met=score>=75,comparison_contract=CONTRACT,source_message_id=m['source_message_id'],comparison_status='COMPLETED_WITH_MISSING_EVIDENCE' if stats['semantic_uncertainties'] else 'COMPLETED')
 result=dict(status='COMPLETED',score=score,sample_count=count,dataset_id='v1_2_1_unseen_m02_development',source_type='DEVELOPMENT',evaluator_version=VERSION,input_sha256=m['sha256'],details=stats)
 rows=[dict(row_type='generated_step',**s) for s in generated['ownership_ledger']]
 rows += [dict(row_type='required_step',**e) for e in evidence]
 rows += [dict(row_type='business_summary',**s) for s in stats['per_business_unit']]
 rows.append(dict(row_type='aggregate_calculation',score=score,accuracy=stats['accuracy'],completeness=stats['completeness'],accuracy_numerator=stats['correctly_mapped'],accuracy_denominator=stats['evaluated_procedures'],completeness_numerator=stats['included_required'],completeness_denominator=stats['defined_required']))
 return result,rows

def run(root,config):
 from .run_storage import save_run
 result,rows=assess(root)
 return save_run(Path(root),'M02','DEVELOPMENT',config,result,rows)
