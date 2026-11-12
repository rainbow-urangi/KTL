"""Opt-in DEVELOPMENT projection of observed business steps; no GT or inference."""
import hashlib
import json
from pathlib import Path
from .evaluators import require, digest, read_json

VERSION = 'm03-observed-business-steps-v1'
ACTIONS = frozenset(('INPUT', 'FORM_INPUT', 'REGISTER', 'SAVE', 'UPDATE',
                     'DETAIL_OPEN', 'CONFIRM', 'RESULT_CHECK', 'SEARCH', 'DELETE', 'NAVIGATE'))


def valid_source_ids(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, str) and bool(item.strip()) for item in value))


def generate_observed(root, config, payload):
    require(payload.get('run_mode', 'DEVELOPMENT') == 'DEVELOPMENT',
            'Local REAL generator is DEVELOPMENT only; OFFICIAL selection not approved')
    binding = config['m03_real_generator']
    require(isinstance(binding, dict), 'm03_real_generator must be an object')
    root = Path(root).resolve()
    path = (root / binding.get('snapshot_path', '')).resolve()
    require(path.is_relative_to(root) and path.is_file(), 'Invalid process snapshot path')
    require(digest(path) == binding.get('snapshot_sha256'), 'Process snapshot hash mismatch')
    snapshot = read_json(path)
    processes = snapshot.get('processes', [])
    selected = [p for p in processes if p.get('canonical_instance_id') == payload['workflow_id']]
    require(len(selected) == 1, 'Workflow must identify exactly one observed process')
    process = selected[0]
    observed = process.get('business_steps', [])
    require(isinstance(observed, list) and all(isinstance(s, dict) for s in observed), 'Invalid business steps')
    steps, issues = [], []
    for order, source in enumerate(observed, 1):
        action, target = source.get('action_type'), source.get('target')
        valid = (action in ACTIONS and isinstance(target, str) and bool(target.strip())
                 and len(target) <= 256 and type(source.get('step_order')) is int
                 and source['step_order'] == order
                 and valid_source_ids(source.get('source_event_ids'))
                 and valid_source_ids(source.get('source_node_ids'))
                 and source.get('resolution_status') == 'RESOLVED')
        if not valid:
            issues.append(dict(order=order, source_step_id=source.get('generated_step_id'),
                               reason='UNRESOLVED_OR_UNSUPPORTED_OBSERVED_STEP'))
            continue
        steps.append(dict(order=order, action=action, target=target,
                          source_step_id=source.get('generated_step_id'),
                          source_event_ids=source['source_event_ids'], source_node_ids=source['source_node_ids'],
                          page_context=source.get('menu_page'), fields=source.get('fields', []),
                          http_evidence=source.get('http_evidence', []),
                          completion_evidence=source.get('completion_evidence', []),
                          serializer_rule_id=source.get('serializer_rule_id')))
    # Never turn a partial projection into a successful scenario or renumber away omissions.
    if not observed:
        issues.append(dict(reason='EMPTY_OBSERVED_PROCESS'))
    identity = dict(version=VERSION, snapshot_sha256=binding['snapshot_sha256'],
                    business_unit_id=payload['business_unit_id'], workflow_id=payload['workflow_id'])
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    return dict(business_unit_id=payload['business_unit_id'], workflow_id=payload['workflow_id'],
                scenario_id='REAL-SCN-' + key, status='FAILED' if issues else 'SUCCESS',
                steps=steps, issues=issues, generator_version=VERSION,
                source_process_id=process.get('source_process_id'), source_snapshot_sha256=binding['snapshot_sha256'],
                readiness_only=True)
