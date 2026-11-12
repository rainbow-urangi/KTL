"""Freeze GT-independent completion serialization BEFORE independent comparison.
No evaluator/model invocation. GT-only role compiler receives no generated data.
"""
from pathlib import Path
import csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.m02_completion_semantics import extend,RULES,canonical
from backend.m02_semantic_scope import scope_steps
from backend.m02_logical_gt import compile_roles,RULES as LOGICAL_RULES,CONTRACT
from backend.m02_logical_candidate import REQUIRED_DEPENDENCIES
BASE='evaluation_contracts/development/m02_serializer_v4'
DEST='evaluation_contracts/development/m02_logical_evaluation_v2_completion'
BASE_HASH='322ea5277b597e01068643a2e1667b6899b8c3e6b8f46730c79b1f17ce71d86a'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    base=ROOT/BASE;out=ROOT/DEST
    if sha(base/'manifest.json')!=BASE_HASH:raise ValueError('Base generation manifest changed')
    previous=json.loads((base/'manifest.json').read_text());hashes={}
    # All frozen model and original generation inputs are verified; changed execution
    # dependencies are rebound below, never silently accepted as the original code.
    keep=[k for k in previous['input_code_sha256'] if k.startswith(('model/','data/')) or Path(k).is_absolute()]
    for name in keep:
        p=Path(name) if Path(name).is_absolute() else ROOT/name
        if sha(p)!=previous['input_code_sha256'][name]:raise ValueError('Frozen input changed: '+name)
        hashes[name]=sha(p)
    for name,expected in previous['outputs'].items():
        if sha(base/name)!=expected:raise ValueError('Original serializer output changed')
        hashes[BASE+'/'+name]=expected
    snapshot=json.loads((base/'business_steps.json').read_text())
    revised=extend(snapshot)
    # No GT content is accepted by extension or scope: only execution ownership IDs.
    execution_path='data/development/current_site_unseen_validation_v1/validation_execution_manifest.csv'
    executions=list(csv.DictReader((ROOT/execution_path).open()))
    target_units=previous['scope_summary']['target_units']
    scoped=scope_steps(revised,executions,target_units)
    boundary=dict(previous['evaluation_boundary'],comparison_contract=CONTRACT)
    gtpath=ROOT/boundary['td04_path']
    if sha(gtpath)!=boundary['td04_sha256']:raise ValueError('GT source changed')
    roles=compile_roles(json.loads(gtpath.read_text()))  # GT only
    if roles['source_intent_unresolved_ids']:raise ValueError('Unresolved source intent')
    source_names=['evaluation_contracts/development/gt_only_review_v1/source_extracted_text.txt',
        'evaluation_contracts/development/gt_only_review_v1/source_library_read.json',BASE+'/manifest.json',
        execution_path,boundary['td04_path']]
    for name in sorted(set(REQUIRED_DEPENDENCIES)|set(source_names)):
        hashes[name]=sha(ROOT/name)
    outputs={'business_steps.json':revised,'scope.json':scoped,'gt_roles.json':roles,
        'logical_contract.json':LOGICAL_RULES,'completion_rules.json':RULES}
    out.mkdir(exist_ok=False)
    for name,value in outputs.items():(out/name).write_bytes(canonical(value))
    artifacts={key:dict(path=DEST+'/'+name,sha256=sha(out/name)) for key,name in [('business_steps','business_steps.json'),('scope','scope.json')]}
    hashes.update({v['path']:v['sha256'] for v in artifacts.values()})
    manifest=dict(stage='PRE_LOGICAL_COMPARISON',run_mode='DEVELOPMENT',official=False,score_computed=False,
        contract=CONTRACT,verification='PENDING_INDEPENDENT_VERIFICATION',
        serializer_version=revised['serializer_version'],model_version=previous['model_version'],
        input_code_sha256=hashes,comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),
        generated_artifacts=artifacts,model_binding=previous['model_binding'],evaluation_boundary=boundary,
        baseline_manifest_sha256=BASE_HASH,baseline_manifest_path=BASE+'/manifest.json',
        generation_policy='FROZEN_MODEL_AND_PRIOR_STEPS_PLUS_EXPLICIT_RAW_UI_STATE_OBSERVATIONS',
        scope_summary=scoped['scope_summary'],conditional_end_ids=roles['conditional_end_ids'],
        user_semantics_source='docs/agents/M02_COMPLETION_CONTRACT.md',
        historical_ui_source_used=False,outputs={name:sha(out/name) for name in outputs})
    (out/'manifest.json').write_bytes(canonical(manifest))
    print(json.dumps(dict(manifest_sha256=sha(out/'manifest.json'),scope=scoped['scope_summary'],
        outcome_audit=revised['completion_rule_audit'],score_computed=False),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
