"""DEVELOPMENT-only recovery measurement through an independently verified freeze.
Generation receives raw events + fixed model outputs, never GT or BU definitions.
"""
import csv
import json
from pathlib import Path
from .evaluators import EvaluationError, digest, read_json, require

DATASET = 'm02_recovery_data_01'
SNAPSHOT = 'evaluation_contracts/development/m02_recovery_rules_v1'
REQUIRED_INPUTS = ('raw_events', 'predictions', 'execution_manifest', 'td04', 'roles')
CHECKS = ('generic_contract_check', 'gt_leakage_check', 'provenance_check', 'regression_check')


def verify(root):
    root = Path(root)
    folder = root / SNAPSHOT
    manifest = read_json(folder / 'manifest.json')
    require(manifest.get('run_mode') == 'DEVELOPMENT' and manifest.get('dataset_id') == DATASET,
            'Recovery manifest must be DEVELOPMENT for the selected dataset')
    hashes = manifest.get('sha256')
    require(isinstance(hashes, dict) and bool(hashes), 'Recovery frozen hashes required')
    for field in REQUIRED_INPUTS:
        require(isinstance(manifest.get(field), str) and manifest[field] in hashes,
                'Recovery input missing from freeze: ' + field)
    for name, expected in hashes.items():
        require(digest(root / name) == expected, 'Frozen recovery dependency changed: ' + name)
    gate = read_json(folder / 'independent_verification.json') if (folder / 'independent_verification.json').is_file() else {}
    snapshot_hash = digest(folder / 'manifest.json')
    require(gate.get('verdict') == 'PASS' and gate.get('snapshot_manifest_sha256') == snapshot_hash
            and all(gate.get(key) == 'PASS' for key in CHECKS),
            'Independent PASS for exact recovery snapshot required')
    frozen = read_json(folder / 'freeze.json') if (folder / 'freeze.json').is_file() else {}
    require(frozen.get('status') == 'FROZEN' and frozen.get('snapshot_manifest_sha256') == snapshot_hash
            and frozen.get('independent_verification_sha256') == digest(folder / 'independent_verification.json'),
            'Post-verification recovery rule freeze required')
    return manifest


def prepare(root):
    """Readiness only: listing a dataset must never evaluate GT or compute score."""
    try:
        manifest = verify(root)
        return dict(status='READY', dataset_id=DATASET, details=dict(input_dataset=DATASET,
            model_version='workflow_candidate_v1_2_1', comparison_contract='M02_USER_CONFIRMED_V1',
            input_sha256=manifest['sha256'], official=False))
    except (EvaluationError, OSError, ValueError, TypeError, KeyError) as exc:
        return dict(status='BLOCKED', dataset_id=DATASET, details=dict(missing=[str(exc)]), error=str(exc))


def generate(root, manifest):
    """Rebuild all semantic stages; GT is loaded only later in assess()."""
    from .semantic_enrichment import enrich
    from .m02_completion_semantics import extend
    from .m02_provenance_restore import restore
    from .m02_business_abstraction import abstract
    from .m02_track_a_native_submit import recover
    from .m02_semantic_scope import scope_steps
    root = Path(root)
    with (root / manifest['raw_events']).open(encoding='utf-8-sig', newline='') as handle:
        raw = list(csv.DictReader(handle))
    predictions = read_json(root / manifest['predictions'])
    require(predictions.get('mode') == 'DEVELOPMENT', 'Recovery predictions must remain DEVELOPMENT')
    tables = predictions['tables']
    artifacts = {}
    semantic = enrich(tables['process_models'], tables['process_nodes'], tables['process_steps'], raw)
    artifacts['01_semantic.json'] = semantic
    completion = extend(semantic); artifacts['02_completion.json'] = completion
    restored, audit = restore(completion, raw)
    artifacts['03_provenance.json'] = restored; artifacts['provenance_audit.json'] = audit
    abstraction = abstract(restored, raw); artifacts['04_abstraction.json'] = abstraction
    business = recover(abstraction, raw); artifacts['business_steps.json'] = business
    # Execution ownership is assigned after the entire process map is generated.
    executions = read_json(root / manifest['execution_manifest'])
    targets = list(dict.fromkeys(x['business_unit_id'] for x in executions))
    scoped = scope_steps(business, executions, targets); artifacts['scope.json'] = scoped
    return scoped, artifacts


def assess(root):
    root = Path(root); manifest = verify(root)
    scoped, artifacts = generate(root, manifest)
    from .m02_user_confirmed_comparator import evaluate, CONTRACT, VERSION
    truth = read_json(root / manifest['td04']); roles = read_json(root / manifest['roles'])
    score, count, stats, evidence = evaluate(scoped, truth, roles)
    artifacts['required_evidence.json'] = evidence
    stats.update(target=75, development_target_met=score >= 75, comparison_contract=CONTRACT,
                 model_version='workflow_candidate_v1_2_1', input_dataset=DATASET,
                 serializer_version=scoped['serializer_version'], serializer_hash=scoped['serializer_rules_hash'],
                 source_message_id=manifest.get('source_message_id'),
                 frozen_manifest_sha256=digest(root / SNAPSHOT / 'manifest.json'),
                 raw_evidence_missing=manifest.get('raw_evidence_missing', []),
                 comparison_status='COMPLETED_WITH_MISSING_EVIDENCE' if stats['semantic_uncertainties'] else 'COMPLETED')
    result = dict(status='COMPLETED', score=score, sample_count=count, dataset_id=DATASET,
                  source_type='DEVELOPMENT', evaluator_version=VERSION, input_sha256=manifest['sha256'], details=stats)
    rows = [dict(row_type='generated_step', **s) for s in scoped['ownership_ledger']]
    rows += [dict(row_type='required_step', **e) for e in evidence]
    rows += [dict(row_type='business_summary', **s) for s in stats['per_business_unit']]
    rows.append(dict(row_type='aggregate_calculation', score=score, accuracy=stats['accuracy'],
        completeness=stats['completeness'], accuracy_numerator=stats['correctly_mapped'],
        accuracy_denominator=stats['evaluated_procedures'], completeness_numerator=stats['included_required'],
        completeness_denominator=stats['defined_required']))
    verify(root)
    return result, rows, artifacts


def run(root, config):
    from .run_storage import save_run
    root = Path(root)
    result, rows, artifacts = assess(root)
    saved = save_run(root, 'M02', 'DEVELOPMENT', config, result, rows)
    directory = root / 'results/development' / saved['run_id']
    for name, value in artifacts.items():
        (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return saved
