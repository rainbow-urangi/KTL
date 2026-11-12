"""Freeze semantic generation + execution scope + comparison dependency boundary.
No GT semantics are parsed. TD-04 bytes are used only for an opaque digest.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.semantic_enrichment import enrich, RULES, VERSION
from backend.m02_semantic_scope import scope_steps
from backend.business_process_serializer import canonical_bytes
from backend.m02_semantic_comparator import CONTRACT

DEST = 'evaluation_contracts/development/m02_serializer_v4'
TARGETS = ['BU03', 'BU07', 'BU09', 'BU17', 'BU20']  # evaluation scope ONLY
SOURCE_MANIFEST = 'data/development/current_site_unseen_validation_v1/m02_frozen_output/manifest.json'
COMPARISON_DEPENDENCIES = [
    'backend/semantic_enrichment.py', 'backend/m02_semantic_scope.py',
    'backend/business_process_serializer.py', 'backend/m02_semantic_candidate.py',
    'backend/m02_semantic_comparator.py', 'backend/evaluators.py',
    'backend/m02_candidate.py', 'backend/run_storage.py', 'backend/server.py',
    'backend/config.json', 'scripts/freeze_m02_semantic.py',
    'docs/agents/M02_SEMANTIC_V4_CONTRACT.md']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main(root=ROOT):
    root = Path(root).resolve()
    previous = json.loads((root / 'evaluation_contracts/development/m02_serializer_v3/manifest.json').read_text())
    source = json.loads((root / SOURCE_MANIFEST).read_text())
    inputs = list(previous['provenance_inputs']) + [
        source['files']['process_models.json']['path'], source['files']['process_nodes.json']['path'],
        source['raw_input']['path'],
        'data/development/current_site_unseen_validation_v1/validation_execution_manifest.csv',
        SOURCE_MANIFEST, source['model_manifest_path']]
    model_manifest_path = root / source['model_manifest_path']
    if sha(model_manifest_path) != source['model_manifest_sha256']:
        raise ValueError('Frozen model manifest changed')
    model_manifest = json.loads(model_manifest_path.read_text())
    model_files = {}
    for name, expected in model_manifest['file_sha256'].items():
        path = (model_manifest_path.parent / name).resolve()
        if not path.is_relative_to(root) or sha(path) != expected:
            raise ValueError('Frozen model file changed')
        model_files[str(path.relative_to(root))] = expected
    inputs += list(model_files)
    paths = {p: Path(p) if Path(p).is_absolute() else root / p for p in inputs + COMPARISON_DEPENDENCIES}
    hashes = {p: sha(path) for p, path in paths.items()}
    for p, expected in previous['provenance_inputs'].items():
        if hashes[p] != expected:
            raise ValueError('Frozen provenance changed')
    for p, expected in previous['files'].items():
        if sha(root / p) != expected:
            raise ValueError('Frozen serializer v3 input changed')
    for item in [*source['files'].values(), source['raw_input']]:
        if sha(root / item['path']) != item['sha256']:
            raise ValueError('Frozen source changed')
    gt_path = (root / source['td04_path']).resolve()
    if not gt_path.is_relative_to(root) or sha(gt_path) != source['td04_sha256']:
        raise ValueError('Opaque TD-04 digest changed')
    # Never json.loads/read_json GT: boundary stores identifiers and opaque hashes only.
    evaluation_boundary = dict(source_manifest_path=SOURCE_MANIFEST,
        source_manifest_sha256=hashes[SOURCE_MANIFEST], td04_path=source['td04_path'],
        td04_sha256=source['td04_sha256'], comparison_contract=CONTRACT)
    models = json.loads(paths[source['files']['process_models.json']['path']].read_text())
    nodes = json.loads(paths[source['files']['process_nodes.json']['path']].read_text())
    occurrence_path = next(p for p in previous['provenance_inputs'] if p.endswith('process_steps.json'))
    occurrences = json.loads(Path(occurrence_path).read_text())
    with paths[source['raw_input']['path']].open(newline='') as stream:
        raw = list(csv.DictReader(stream))
    with paths['data/development/current_site_unseen_validation_v1/validation_execution_manifest.csv'].open(newline='') as stream:
        executions = list(csv.DictReader(stream))
    snapshot = enrich(models, nodes, occurrences, raw)
    if canonical_bytes(snapshot) != canonical_bytes(enrich(models, nodes, occurrences, raw)):
        raise ValueError('Nondeterministic generation')
    scoped = scope_steps(snapshot, executions, TARGETS)
    output = root / DEST
    output.mkdir(exist_ok=False)
    outputs = {'business_steps.json': snapshot, 'scope.json': scoped, 'rules.json': RULES}
    for name, value in outputs.items():
        (output / name).write_bytes(canonical_bytes(value))
    manifest = {'mode': 'DEVELOPMENT', 'official': False, 'stage': 'PRE_GT_COMPARISON',
        'score_computed': False, 'verification': 'PENDING_INDEPENDENT_VERIFICATION',
        'serializer_version': VERSION, 'input_code_sha256': hashes,
        'comparison_dependencies': COMPARISON_DEPENDENCIES, 'evaluation_boundary': evaluation_boundary,
        'model_binding': dict(manifest_path=source['model_manifest_path'],
            manifest_sha256=source['model_manifest_sha256'], file_sha256=model_files),
        'outputs': {name: sha(output / name) for name in outputs},
        'scope_summary': scoped['scope_summary'], 'model_version': source['model_version'],
        'comparison_gate': 'INDEPENDENT_VERIFICATION_PASS_BOUND_TO_MANIFEST_HASH_AND_CONTRACT_REQUIRED'}
    (output / 'manifest.json').write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
