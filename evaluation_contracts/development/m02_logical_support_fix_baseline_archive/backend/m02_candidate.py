"""Persisted candidate maps → post-hoc M02 evaluation; no model invocation.

Technical signatures are serialized directly. Their semantic equivalence to TD-04
is never invented from auxiliary source evidence. Unresolved comparison has a null score.
"""
from pathlib import Path
from .evaluators import read_json, digest, require, M02Evaluator
from .run_storage import save_run

DATASET = 'v1_2_1_unseen_m02_development'
MANIFEST = 'data/development/current_site_unseen_validation_v1/m02_frozen_output/manifest.json'


def checked(root, item):
    path = (root / item['path']).resolve()
    require(path.is_relative_to(root.resolve()), 'M02 input must be inside repository')
    require(path.is_file() and digest(path) == item['sha256'], 'M02 input SHA-256 mismatch: ' + item['path'])
    return path


def serialize_maps(models, nodes, identity):
    """GT-free, lossless canonical occurrence export. No GT labels accepted."""
    by_node = {n['node_id']: n for n in nodes}
    require(len(by_node) == len(nodes), 'Duplicate candidate node ID')
    require(len(set(identity.values())) == len(identity), 'Duplicate process identity pairing')
    by_model = {m['process_model_id']: m for m in models}
    require(len(by_model) == len(models), 'Duplicate candidate model ID')
    require(set(identity.values()) <= set(by_model), 'Missing paired process map')
    rename = {source: target for target, source in identity.items()}
    result = []
    for model in models:
        source_id = model['process_model_id']
        procedures = []
        for order, nid in enumerate(model['canonical_node_sequence'], 1):
            require(nid in by_node and by_node[nid]['process_model_id'] == source_id,
                    'Broken canonical node reference')
            node = by_node[nid]
            # Existing typed map fields are direct output, not auxiliary input
            # labels. A comparison contract must authorize their equivalence to
            # business procedures; merely constructing this key is not a match.
            signature = '|'.join(str(node.get(k, '')) for k in
                ('action', 'page_path', 'target_role', 'http_method', 'normalized_endpoint'))
            label = node.get('direct_label') or signature
            require(label is None or isinstance(label, str), 'Invalid direct procedure label')
            procedures.append({'id': source_id + '-S' + str(order).zfill(3),
                'label': label, 'evidence_type': 'direct', 'step_order': order,
                'node_id': nid, 'action': node['action'], 'page_path': node['page_path'],
                'target': node['target_role'], 'http_method': node['http_method'],
                'endpoint': node['normalized_endpoint'],
                'technical_signature': signature})
        result.append({'id': rename.get(source_id, source_id), 'source_process_id': source_id,
                       'canonical_instance_id': model['canonical_instance_id'], 'procedures': procedures})
    return {'processes': result}


SNAPSHOT = 'evaluation_contracts/development/m02_serializer_v3'

def adapt_business_steps(snapshot, identity):
    """Evaluation-only ID pairing; never derives labels from auxiliary evidence."""
    source_ids = {p['source_process_id'] for p in snapshot['processes']}
    require(len(source_ids) == len(snapshot['processes']), 'Duplicate business process ID')
    require(len(set(identity.values())) == len(identity) and set(identity.values()) <= source_ids,
            'Invalid business process identity mapping')
    rename = {source: target for target, source in identity.items()}
    processes = []
    for process in snapshot['processes']:
        steps = []
        for step in process['business_steps']:
            signature = '|'.join(str(step.get(k, '')) for k in
                                ('action_type', 'menu_page', 'target', 'http_method', 'endpoint'))
            steps.append(dict(step, id=step['generated_step_id'], label=signature,
                              evidence_type='direct', technical_signature=signature,
                              node_id=step['source_node_ids'][0]))
        processes.append(dict(id=rename.get(process['source_process_id'], process['source_process_id']),
            source_process_id=process['source_process_id'],
            canonical_instance_id=process['canonical_instance_id'], procedures=steps,
            unlinked_technical_evidence=process['unlinked_technical_evidence']))
    require(sum(len(p['procedures']) for p in processes) == snapshot['generated_business_step_count'],
            'Business step denominator changed')
    return {'processes': processes, 'serializer_version': snapshot['serializer_version']}


def frozen_business_output(root, sources):
    from .business_process_serializer import serialize, canonical_bytes
    manifest_path = root / SNAPSHOT / 'manifest.json'
    frozen = read_json(manifest_path)
    require(frozen['stage'] == 'PRE_GT_COMPARISON' and frozen['score_computed'] is False,
            'Not a precomparison serializer snapshot')
    sources[str(manifest_path.relative_to(root))] = digest(manifest_path)
    for name, expected in {**frozen['files'], **frozen['provenance_inputs']}.items():
        path = root / name
        require(path.is_file() and digest(path) == expected, 'Serializer frozen input mismatch: ' + name)
        sources[name] = expected
    output_path = root / SNAPSHOT / 'business_steps.json'
    require(digest(output_path) == frozen['output_sha256'], 'Serializer frozen output mismatch')
    sources[str(output_path.relative_to(root))] = frozen['output_sha256']
    models, nodes = [read_json(root / name) for name in frozen['files'] if name.endswith(('process_models.json', 'process_nodes.json'))]
    occurrences = read_json(next(Path(name) for name in frozen['provenance_inputs'] if name.endswith('process_steps.json')))
    output = read_json(output_path)
    require(canonical_bytes(serialize(models, nodes, occurrences)) == output_path.read_bytes(),
            'Serializer output not reproducible')
    return output


def load_bundle(root):
    root = Path(root).resolve()
    manifest = read_json(root / MANIFEST)
    require(manifest['run_mode'] == 'DEVELOPMENT' and manifest['official'] is False,
            'Candidate M02 is DEVELOPMENT only')
    require(manifest['business_unit_count'] == 20 and len(set(manifest['business_unit_ids'])) == 20,
            'M02 requires 20 business log units')
    sources = {MANIFEST: digest(root / MANIFEST)}
    for item in [*manifest['files'].values(), manifest['raw_input'],
                 {'path': manifest['model_manifest_path'], 'sha256': manifest['model_manifest_sha256']},
                 {'path': manifest['td04_path'], 'sha256': manifest['td04_sha256']}]:
        checked(root, item); sources[item['path']] = item['sha256']
    frozen = read_json(root / manifest['model_manifest_path'])
    for name, expected in frozen['file_sha256'].items():
        checked(root, {'path': str(Path(manifest['model_manifest_path']).parent / name), 'sha256': expected})
    models = read_json(root / manifest['files']['process_models.json']['path'])
    nodes = read_json(root / manifest['files']['process_nodes.json']['path'])
    # Identity only: raw anchors identify maps, never count as direct matches.
    for bu, source in manifest['process_identity_mapping'].items():
        anchor = manifest['identity_anchor_events'][bu]
        owners = {n['process_model_id'] for n in nodes if anchor in n['source_event_evidence']}
        require(owners == {source}, 'Ambiguous raw anchor process identity: ' + bu)
    snapshot = frozen_business_output(root, sources)
    generated = adapt_business_steps(snapshot, manifest['process_identity_mapping'])
    # GT is deliberately loaded only after model-output serialization.
    truth = read_json(root / manifest['td04_path'])
    require(len(truth['processes']) == 5, 'M02 requires five GT processes')
    require({p['id'] for p in truth['processes']} == set(manifest['process_identity_mapping']), 'GT identity mismatch')
    return manifest, generated, truth, sources, len(nodes)



def scored_csv_rows(generated, truth, evidence, computed, score):
    """Lossless occurrence ledger, plus sufficient aggregate values for CSV-only recalculation."""
    rows = []
    matched = {}
    for gt in truth['processes']:
        comparisons = [r for r in evidence if r['process_id'] == gt['id']]
        for required, comparison in zip(gt['procedures'], comparisons):
            detected_id = comparison['detected_id']
            if comparison['direct_match']:
                matched[detected_id] = required['id']
            rows.append(dict(row_type='required_step', process_id=gt['id'],
                business_unit_id=gt['id'], required_step_id=required['id'],
                required_label=required['label'], required_order=required['step_order'],
                menu_screen_name=required['menu_screen_name'], allowed_aliases=required['allowed_aliases'],
                matched_generated_id=detected_id,
                match_status='MATCHED' if comparison['direct_match'] else 'MISSING'))
    gt_ids = {p['id'] for p in truth['processes']}
    for process in generated['processes']:
        for step in process['procedures']:
            rows.append(dict(row_type='generated_step', process_id=process['id'],
                source_process_id=process['source_process_id'],
                canonical_instance_id=process['canonical_instance_id'],
                business_unit_id=process['id'] if process['id'] in gt_ids else '',
                matched_required_step_id=matched.get(step['id'], ''),
                match_status='MATCHED' if step['id'] in matched else 'UNMATCHED', **step))
    rows.append(dict(row_type='aggregate_calculation',
        accuracy_numerator=computed['correctly_mapped'],
        accuracy_denominator=computed['evaluated_procedures'],
        completeness_numerator=computed['included_required'],
        completeness_denominator=computed['defined_required'],
        accuracy=computed['accuracy'], completeness=computed['completeness'], score=score,
        formula='sqrt((100*accuracy_numerator/accuracy_denominator)*(100*completeness_numerator/completeness_denominator))',
        denominator_scope='ALL generated business steps, including unpaired maps',
        match_status='COMPLETED'))
    return rows

def assess(root):
    if (Path(root) / 'evaluation_contracts/development/m02_logical_evaluation_v1/manifest.json').is_file():
        from .m02_logical_candidate import assess as assess_logical
        return assess_logical(root)
    if (Path(root) / 'evaluation_contracts/development/m02_serializer_v4/manifest.json').is_file():
        from .m02_semantic_candidate import assess as assess_semantic
        return assess_semantic(root)
    manifest, generated, truth, sources, node_count = load_bundle(root)
    all_steps = [s for p in generated['processes'] for s in p['procedures']]
    missing_labels = sum(not M02Evaluator.canonical_label(s['label']) for s in all_steps)
    details = {'model_version': manifest['model_version'], 'business_unit_count': 20,
        'ground_truth_count': 5, 'process_model_count': len(generated['processes']),
        'graph_node_count': node_count, 'evaluated_procedures': len(all_steps),
        'defined_required': sum(len(p['procedures']) for p in truth['processes']),
        'unresolved_direct_labels': missing_labels,
        'direct_mapping_contract_status': truth.get('status'), 'formula': 'sqrt(Accuracy * Completeness)',
        'auxiliary_evidence_counted': False, 'selection_method': manifest['identity_mapping_basis'],
        'representation': ('Frozen serializer v3 business steps; HTTP retained as unlinked evidence' if generated.get('serializer_version') else manifest['representation']), 'per_business_unit': [],
        'missing': [], 'notice': 'DEVELOPMENT only; official_pass=null'}
    rows = []
    details['serializer_version'] = generated.get('serializer_version')
    technical = [dict(row_type='technical_evidence', process_id=p['id'], match_status='AUXILIARY_NOT_DIRECT', **e) for p in generated['processes'] for e in p.get('unlinked_technical_evidence', [])]
    details['technical_evidence_count'] = len(technical)
    rows.extend(technical)
    rows.append(dict(row_type='denominator_audit', generated_business_step_count=len(all_steps), technical_evidence_count=len(technical), defined_required=details['defined_required'], denominator_scope='ALL generated business steps across ALL processes', comparison_status=truth.get('status')))
    by_id = {p['id']: p for p in generated['processes']}
    # No 0% claim when direct semantic comparison is unsupported.
    if missing_labels or truth.get('status') != 'VALIDATED_DIRECT_MAPPING':
        details['missing'] = ['DIRECT_PROCEDURE_MAPPING_REQUIRED: business action/page/target signatures have no validated direct equivalence contract to the 27 TD-04 procedures; raw input labels/node evidence cannot supply answers (FINAL p.7). No model change is required merely to define a mapping contract.']
        for gt in truth['processes']:
            steps = by_id[gt['id']]['procedures']
            summary = {'business_unit_id': gt['id'], 'business_name': gt['business_name'],
                'generated_count': len(steps), 'required_count': len(gt['procedures']),
                'matched_count': None, 'unmatched_count': None, 'missing_count': None,
                'accuracy': None, 'completeness': None, 'score': None,
                'status': 'DIRECT_PROCEDURE_MAPPING_REQUIRED'}
            details['per_business_unit'].append(summary)
            rows.append(dict(row_type='business_summary', **summary))
            for required in gt['procedures']:
                rows.append({'row_type': 'required_step', 'business_unit_id': gt['id'],
                    'required_step_id': required['id'], 'required_label': required['label'],
                    'required_order': required['step_order'], 'menu_screen_name': required['menu_screen_name'],
                    'allowed_aliases': required['allowed_aliases'], 'match_status': 'NOT_EVALUATED'})
        for process in generated['processes']:
            for step in process['procedures']:
                rows.append(dict(row_type='generated_step', business_unit_id=process['id'] if process['id'] in manifest['process_identity_mapping'] else '',
                    source_process_id=process['source_process_id'], process_id=process['id'],
                    match_status='NOT_EVALUATED', **step))
        return {'status':'NOT_CONFIGURED', 'score':None, 'sample_count':5,
            'dataset_id':DATASET,'source_type':'DEVELOPMENT','input_sha256':sources,
            'evaluator_version':M02Evaluator.version,'details':details}, rows
    aliases = {'version': truth['version'], 'aliases': [
        {'canonical': s['label'], 'accepted': s['allowed_aliases']}
        for p in truth['processes'] for s in p['procedures']]}
    evaluator = M02Evaluator(aliases)
    score, count, computed, evidence = evaluator.evaluate(generated, truth)
    details.update(computed)
    for gt in truth['processes']:
        p = by_id[gt['id']]
        value, _, stats, _ = evaluator.evaluate({'processes':[p]}, {'processes':[gt]})
        summary = {'business_unit_id':gt['id'], 'business_name':gt['business_name'],
            'accuracy':stats['accuracy'], 'completeness':stats['completeness'], 'score':value,
            'generated_count':len(p['procedures']), 'required_count':len(gt['procedures']),
            'matched_count':stats['correctly_mapped'],
            'unmatched_count':len(p['procedures'])-stats['correctly_mapped'],
            'missing_count':len(gt['procedures'])-stats['correctly_mapped'], 'status':'COMPLETED'}
        details['per_business_unit'].append(summary); rows.append(dict(row_type='business_summary', **summary))
    rows.extend(dict(row_type='match_evidence', **r) for r in evidence)
    rows.extend(scored_csv_rows(generated, truth, evidence, computed, score))
    return {'status':'COMPLETED','score':score,'sample_count':count,'dataset_id':DATASET,
            'source_type':'DEVELOPMENT','input_sha256':sources,'evaluator_version':M02Evaluator.version,'details':details}, rows


def run(root, config):
    result, rows = assess(root)
    return save_run(Path(root), 'M02', 'DEVELOPMENT', config, result, rows)
