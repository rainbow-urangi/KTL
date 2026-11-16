"""Evaluation-only freeze. DOES NOT run model/serializer or regenerate any step.
GT-role compilation receives only authoritative GT text/menu/order, never outputs.
Generated artifact bytes are hash-bound/copied by reference, never interpreted here.
"""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.m02_logical_gt import compile_roles,RULES,CONTRACT

DEST='evaluation_contracts/development/m02_logical_evaluation_v1'
BASE='evaluation_contracts/development/m02_serializer_v4'
ARCHIVE='evaluation_contracts/development/m02_logical_baseline_v2_archive'
BASE_HASH='322ea5277b597e01068643a2e1667b6899b8c3e6b8f46730c79b1f17ce71d86a'
CODE=['backend/m02_logical_comparator.py','backend/m02_logical_candidate.py','backend/m02_logical_gt.py',
    'backend/m02_candidate.py','backend/evaluators.py','backend/run_storage.py','backend/server.py','backend/config.json',
    'backend/semantic_enrichment.py','backend/m02_semantic_scope.py','backend/business_process_serializer.py',
    'backend/m02_semantic_candidate.py','scripts/freeze_m02_logical_evaluation.py',
    'docs/agents/M02_LOGICAL_EVALUATION_CONTRACT.md','frontend/app.js']
SOURCE_TEXT='evaluation_contracts/development/gt_only_review_v1/source_extracted_text.txt'
SOURCE_READ='evaluation_contracts/development/gt_only_review_v1/source_library_read.json'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def resolve(root,name):return Path(name) if Path(name).is_absolute() else root/name

def main(root=ROOT):
    root=Path(root).resolve();base=root/BASE
    if sha(base/'manifest.json')!=BASE_HASH:raise ValueError('Original generated baseline changed')
    previous=json.loads((base/'manifest.json').read_text())
    oldgate=json.loads((base/'independent_verification.json').read_text())
    if oldgate.get('verdict')!='PASS' or oldgate.get('snapshot_manifest_sha256')!=BASE_HASH:
        raise ValueError('Original independent generation verification missing')
    hashes={};archive_hashes={}
    for name,expected in previous['input_code_sha256'].items():
        path=resolve(root,name)
        if name=='backend/m02_candidate.py':
            if sha(root/ARCHIVE/name)!=expected:raise ValueError('Old routing source not preserved')
        elif sha(path)!=expected:raise ValueError('Generation/model/source input changed: '+name)
        hashes[name]=sha(path)
    for name in previous['comparison_dependencies']:
        p=root/ARCHIVE/name
        if sha(p)!=previous['input_code_sha256'][name]:raise ValueError('Original execution archive changed')
        archive_hashes[str(p.relative_to(root))]=sha(p)
    for p in (root/ARCHIVE/'snapshot').iterdir():
        if p.is_file():archive_hashes[str(p.relative_to(root))]=sha(p)
    artifacts={}
    for key,name in [('business_steps','business_steps.json'),('scope','scope.json')]:
        p=base/name
        if sha(p)!=previous['outputs'][name]:raise ValueError('Frozen generated steps changed')
        artifacts[key]=dict(path=str(p.relative_to(root)),sha256=sha(p))
        hashes[str(p.relative_to(root))]=sha(p)
    for name in CODE+[BASE+'/manifest.json',BASE+'/independent_verification.json',SOURCE_TEXT,SOURCE_READ]:
        hashes[name]=sha(root/name)
    hashes.update(archive_hashes)
    boundary=dict(previous['evaluation_boundary'],comparison_contract=CONTRACT)
    gt_path=root/boundary['td04_path']
    if sha(gt_path)!=boundary['td04_sha256']:raise ValueError('Original GT changed')
    # GT-only semantic authoring, sanctioned evaluation input. No output is passed.
    truth=json.loads(gt_path.read_text());roles=compile_roles(truth)
    if roles['source_intent_unresolved_ids']:raise ValueError('Unresolved GT intent: '+str(roles['source_intent_unresolved_ids']))
    roles['original_gt_sha256']=boundary['td04_sha256'];roles['source_text_sha256']=hashes[SOURCE_TEXT]
    out=root/DEST;out.mkdir(exist_ok=False)
    outputs={'gt_roles.json':roles,'logical_contract.json':RULES}
    for name,value in outputs.items():(out/name).write_bytes(canonical(value))
    source_record=json.loads((root/SOURCE_READ).read_text())
    manifest=dict(stage='PRE_LOGICAL_COMPARISON',run_mode='DEVELOPMENT',official=False,score_computed=False,
        contract=CONTRACT,verification='PENDING_INDEPENDENT_VERIFICATION',
        serializer_version=previous['serializer_version'],model_version=previous['model_version'],
        input_code_sha256=hashes,comparison_dependencies=CODE,
        generated_artifacts=artifacts,model_binding=previous['model_binding'],evaluation_boundary=boundary,
        baseline_manifest_sha256=BASE_HASH,baseline_manifest_path=BASE+'/manifest.json',baseline_execution_archive=ARCHIVE,
        generation_policy='UNCHANGED_BYTES_NO_MODEL_OR_SERIALIZER_EXECUTION',
        scope_summary=previous['scope_summary'],
        gt_provenance=dict(original_gt_path=boundary['td04_path'],original_gt_sha256=boundary['td04_sha256'],
            source_library_file_id=source_record['library_file_id'],source_file_id=source_record['file_id'],
            source_text_sha256=hashes[SOURCE_TEXT],source_binary_sha256=None,
            warning='Library source text independently corroborated; original PDF bytes/version not materialized'),
        conditional_end_ids=roles['conditional_end_ids'],
        readiness='CONDITIONAL_DIRECT_END_PROOF_OR_AUTHORITATIVE_END_DEFINITION_REQUIRED',
        outputs={name:sha(out/name) for name in outputs})
    (out/'manifest.json').write_bytes(canonical(manifest))
    print(json.dumps(dict(manifest_sha256=sha(out/'manifest.json'),contract=CONTRACT,
        generated_artifacts=artifacts,required_count=roles['required_count'],
        conditional_end_ids=roles['conditional_end_ids'],model_files=len(previous['model_binding']['file_sha256'])),indent=2))
if __name__=='__main__':main()
