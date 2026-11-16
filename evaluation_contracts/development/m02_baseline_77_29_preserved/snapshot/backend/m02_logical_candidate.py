"""Frozen logical evaluation boundary; unchanged generated/serializer artifacts."""
from pathlib import Path
from .evaluators import read_json, digest, require
from .m02_logical_comparator import CONTRACT, VERSION, evaluate, LogicalSchemaError, LogicalMeaningIncomplete

SNAPSHOT = 'evaluation_contracts/development/m02_logical_evaluation_v3_provenance'
DATASET = 'v1_2_1_unseen_m02_development'
REQUIRED_DEPENDENCIES = frozenset((
    'backend/semantic_enrichment.py', 'backend/m02_semantic_scope.py',
    'backend/business_process_serializer.py', 'backend/m02_semantic_candidate.py',
    'backend/m02_logical_comparator.py', 'backend/m02_logical_gt.py',
    'backend/m02_logical_candidate.py', 'backend/evaluators.py',
    'backend/m02_candidate.py', 'backend/run_storage.py', 'backend/server.py',
    'backend/config.json', 'scripts/freeze_m02_logical_evaluation.py',
    'docs/agents/M02_LOGICAL_EVALUATION_CONTRACT.md','frontend/app.js','backend/m02_completion_semantics.py','scripts/freeze_m02_completion.py',
    'docs/agents/M02_COMPLETION_CONTRACT.md','backend/m02_provenance_restore.py',
    'scripts/freeze_m02_provenance.py','docs/agents/M02_PROVENANCE_PRESERVATION_CONTRACT.md'))

def verify_frozen_inputs(root, manifest, sources):
    hashes = manifest['input_code_sha256']
    require(REQUIRED_DEPENDENCIES <= set(hashes)
        and REQUIRED_DEPENDENCIES <= set(manifest.get('comparison_dependencies', [])),
        'Comparison dependency freeze incomplete')
    for name, expected in hashes.items():
        path = Path(name) if Path(name).is_absolute() else root / name
        require(path.is_file() and digest(path) == expected, 'Frozen semantic input changed: ' + name)
        sources[name] = expected
    model = manifest['model_binding']
    require(hashes.get(model['manifest_path']) == model['manifest_sha256'], 'Model manifest not bound')
    model_manifest = read_json(root / model['manifest_path'])
    declared_files = {str((Path(model['manifest_path']).parent / name)): expected
        for name, expected in model_manifest['file_sha256'].items()}
    require(declared_files == model['file_sha256']
        and all(hashes.get(name) == expected for name, expected in declared_files.items()),
        'Model files not bound')
    require(hashes.get(manifest['baseline_manifest_path']) == manifest['baseline_manifest_sha256'],
        'Original serializer snapshot binding missing')
    artifacts=manifest['generated_artifacts']
    require(set(artifacts)=={'business_steps','scope'} and all(
        hashes.get(item['path'])==item['sha256'] for item in artifacts.values()),
        'Frozen generated artifacts not bound')
    boundary = manifest['evaluation_boundary']
    require(hashes.get(boundary['source_manifest_path']) == boundary['source_manifest_sha256']
        and boundary['comparison_contract'] == CONTRACT
        and isinstance(boundary['td04_sha256'], str) and len(boundary['td04_sha256']) == 64,
        'Evaluation source boundary not frozen')

def assess(root):
    root = Path(root).resolve()
    directory = root / SNAPSHOT
    manifest_path = directory / 'manifest.json'
    manifest = read_json(manifest_path)
    require(manifest['stage'] == 'PRE_LOGICAL_COMPARISON' and manifest['score_computed'] is False,
            'Semantic snapshot must precede comparison')
    sources = {str(manifest_path.relative_to(root)): digest(manifest_path)}
    verify_frozen_inputs(root, manifest, sources)
    require(manifest.get('contract') == CONTRACT and {'gt_roles.json','logical_contract.json'} <= set(manifest['outputs']),
        'Logical contract/sidecar freeze incomplete')
    for name, expected in manifest['outputs'].items():
        require(digest(directory / name) == expected, 'Frozen semantic output changed')
        sources[str((directory / name).relative_to(root))] = expected
    snapshot = read_json(root / manifest['generated_artifacts']['business_steps']['path'])
    generated = read_json(root / manifest['generated_artifacts']['scope']['path'])
    role_contract = read_json(directory / 'gt_roles.json')
    scope = generated['scope_summary']
    details = dict(model_version=manifest['model_version'], serializer_version=manifest['serializer_version'],
        serializer_hash=snapshot['serializer_rules_hash'], serializer_snapshot_hash=manifest['baseline_manifest_sha256'], evaluation_contract_hash=digest(manifest_path),
        input_dataset=DATASET, ground_truth_count=len(scope['target_units']), target_ground_truth_ids=scope['target_units'],
        business_unit_count=20, process_model_count=len(snapshot['processes']),
        evaluated_procedures=scope['total_generated_steps'],
        all_generated_procedures=scope['all_generated_steps'],
        mixed_count=scope['mixed_count'], unassigned_count=scope['unassigned_count'],
        out_of_scope_count=scope['out_of_scope_count'], scope_policy=scope['policy'],
        technical_evidence_count=snapshot['technical_evidence_count'],
        formula='sqrt(Accuracy * Completeness)', auxiliary_evidence_counted=False,
        target=75, per_business_unit=[], missing=[], comparison_status='PENDING_LOGICAL_CONTRACT_VERIFICATION',
        comparison_contract=CONTRACT, physical_screen_requirement='ONLY_WHERE_AUTHORITATIVELY_DECLARED',
        conditional_end_ids=role_contract['conditional_end_ids'],
        defined_required=role_contract['required_count'])
    rows = []
    for step in generated['ownership_ledger']:
        rows.append(dict(row_type='generated_step', match_status='NOT_EVALUATED', **step))
    for process in snapshot['processes']:
        rows.extend(dict(row_type='technical_evidence', process_id=process['source_process_id'],
            match_status='AUXILIARY_NOT_DIRECT', **e) for e in process['unlinked_technical_evidence'])
    rows.extend(dict(row_type='raw_evidence', match_status='AUXILIARY_NOT_DIRECT', **e) for e in snapshot['raw_evidence_ledger'])
    for bu in scope['target_units']:
        details['per_business_unit'].append(dict(business_unit_id=bu,
            generated_count=scope['per_business_unit'][bu], required_count=len(next(p for p in role_contract['processes'] if p['id']==bu)['procedures']),
            matched_count=None, unmatched_count=None, missing_count=None,
            accuracy=None, completeness=None, score=None, status='PENDING_LOGICAL_CONTRACT_VERIFICATION'))
    gate_path = directory / 'independent_verification.json'
    gate = read_json(gate_path) if gate_path.is_file() else {}
    approved = (gate.get('verdict') == 'PASS' and gate.get('snapshot_manifest_sha256') == digest(manifest_path)
        and gate.get('gt_leakage_check') == 'PASS' and gate.get('scope_check') == 'PASS'
        and gate.get('direct_comparison_contract') == CONTRACT)
    if not approved:
        details['missing'] = ['Independent PASS for logical evaluation contract required before comparison. Normal completion state semantics require the new hash-bound independent PASS.']
        return dict(status='NOT_CONFIGURED', score=None, sample_count=5, dataset_id=DATASET,
            source_type='DEVELOPMENT', evaluator_version=VERSION, input_sha256=sources, details=details), rows
    # Evaluation-only GT semantic access starts HERE. Boundary is frozen before PASS.
    boundary = manifest['evaluation_boundary']
    require(boundary['comparison_contract'] == CONTRACT, 'Comparison boundary contract changed')
    gt_path = (root / boundary['td04_path']).resolve()
    require(gt_path.is_relative_to(root) and digest(gt_path) == boundary['td04_sha256'], 'Frozen TD-04 boundary changed')
    truth = read_json(gt_path)
    require({p['id'] for p in truth['processes']} == set(scope['target_units']), 'GT scope mismatch')
    sources[boundary['td04_path']] = digest(gt_path)
    try:
        score, count, stats, evidence = evaluate(generated, truth, role_contract)
    except (LogicalSchemaError, LogicalMeaningIncomplete) as exc:
        status = 'LOGICAL_SEMANTICS_INCOMPARABLE' if isinstance(exc, LogicalMeaningIncomplete) else 'GT_LOGICAL_CONTRACT_REQUIRED'
        details.update(comparison_status=status, missing=[str(exc)],
            semantic_uncertainties=getattr(exc, 'uncertainties', []))
        for summary in details['per_business_unit']:
            summary['status'] = status
        return dict(status='NOT_CONFIGURED', score=None, sample_count=len(truth['processes']),
            dataset_id=DATASET, source_type='DEVELOPMENT', evaluator_version=VERSION,
            input_sha256=sources, details=details), rows
    details.update(stats, comparison_status='COMPLETED', missing=[])
    details['per_business_unit'] = []
    for gt in truth['processes']:
        actual = next(p for p in generated['processes'] if p['id'] == gt['id'])
        own_matches = sum(e['direct_match'] for e in evidence if e['process_id'] == gt['id'])
        n, required = len(actual['procedures']), len(gt['procedures'])
        accuracy = 100 * own_matches / n if n else None
        completeness = 100 * own_matches / required
        summary = dict(business_unit_id=gt['id'], business_name=gt['business_name'],
            generated_count=n, required_count=required, matched_count=own_matches,
            unmatched_count=n-own_matches, missing_count=required-own_matches,
            accuracy=accuracy, completeness=completeness,
            score=(accuracy * completeness)**0.5 if accuracy is not None else None,
            status='COMPLETED' if n else 'NO_GENERATED_EVIDENCE')
        details['per_business_unit'].append(summary)
        rows.append(dict(row_type='business_summary', **summary))
    hits = {e['detected_id']: e for e in evidence if e['direct_match']}
    for row in rows:
        if row['row_type'] == 'generated_step':
            row['match_status'] = ('MATCHED' if row['generated_step_id'] in hits else 'UNMATCHED') if row['in_m02_denominator'] else 'OUT_OF_SCOPE' if row['business_unit_ownership'] != 'UNASSIGNED' else 'UNASSIGNED'
            row['matched_required_label'] = hits.get(row['generated_step_id'], {}).get('ground_truth_step', '')
            row['matched_required_step_id'] = hits.get(row['generated_step_id'], {}).get('required_step_id', '')
    rows.extend(dict(row_type='required_step', match_status='MATCHED' if e['direct_match'] else 'MISSING', **e) for e in evidence if e.get('required_step_id'))
    rows.extend(dict(row_type='match_evidence', **e) for e in evidence)
    rows.append(dict(row_type='aggregate_calculation', **stats, score=score,
        denominator_scope='FIVE_TARGET_EXECUTIONS_PLUS_RELEVANT_MIXED_ONCE'))
    return dict(status='COMPLETED', score=score, sample_count=count, dataset_id=DATASET,
        source_type='DEVELOPMENT', evaluator_version=VERSION, input_sha256=sources, details=details), rows
