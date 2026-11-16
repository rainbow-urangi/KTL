"""Explicit user-authorized DEVELOPMENT eligibility; never certifies held-out history.

The preserved strict manifest and source labels remain unchanged. This separate
policy is bound to their hashes and is excluded from all engine inputs.
"""
import csv
import json
from collections import Counter
from pathlib import Path
from .evaluators import require

POLICY_PATH = 'evaluation_contracts/m05_development_authorization.json'
MODE = 'USER_AUTHORIZED_DEVELOPMENT_EXISTING_LOCKED_TARGETS'


def policy_for(root, manifest):
    from .m05_full_context import digest, FREEZE_SHA256
    path = Path(root) / POLICY_PATH
    if not path.exists():
        return None
    policy = json.loads(path.read_text())
    if policy.get('dataset_id') != manifest.get('dataset_id'):
        return None
    require(policy.get('schema_version') == 'm05-user-authorized-development-v1'
            and policy.get('run_mode') == 'DEVELOPMENT' and policy.get('official_pass') is None
            and policy.get('eligibility') == MODE and policy.get('authorization_source')
            and policy.get('manifest_sha256') == digest(manifest)
            and policy.get('target_labels_sha256') == manifest['target_labels']['sha256']
            and policy.get('original_locked_targets_sha256') == manifest['original_locked_targets']['sha256']
            and policy.get('engine_freeze_sha256') == FREEZE_SHA256
            and policy.get('full_event_count') == 417 and policy.get('target_event_count') == 20
            and policy.get('held_out_evidence_status') == 'INSUFFICIENT_NOT_BLOCKING_FOR_THIS_DEVELOPMENT',
            'DEVELOPMENT_AUTHORIZATION_BINDING_MISMATCH')
    return policy


def prepare(root, manifest, config, policy):
    from . import m05_full_context as fc
    root = Path(root).resolve()
    freeze = fc.validate_freeze(root, config)
    normalizer = fc.frozen_normalizer(freeze)
    bundle = root / 'data/held_out/m05' / manifest['dataset_id']
    collection = fc.read_json(root, manifest['collection'], bundle)
    events, provenance, raw_sha, bundle = fc.load_full_sequence(root, manifest, collection, normalizer, fc.instant(freeze['frozen_at_utc']))
    require(len(events) == policy['full_event_count'], 'FULL_SEQUENCE_COUNT_MISMATCH')
    with fc.artifact(root, manifest['target_labels'], bundle).open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames == list(fc.LABEL_FIELDS), 'TARGET_LABEL_SCHEMA_MISMATCH')
        labels = list(reader)
    with fc.artifact(root, manifest['original_locked_targets'], bundle).open(newline='', encoding='utf-8-sig') as f:
        originals = list(csv.DictReader(f))
    ids = [r['event_id'] for r in labels]
    require(len(ids) == len(set(ids)) == 20 and set(ids).issubset(provenance), 'TARGET_ID_MISMATCH')
    require(Counter(r['expected_label'] for r in labels) == {'KEEP':10, 'REMOVE':10}, 'KEEP10_REMOVE10_REQUIRED')
    require([(r['event_id'], r['expected_label'], r['remove_category'], r['label_rationale']) for r in labels]
            == [(r['event_id'], r['expected_label'], r['remove_category'], r['rationale']) for r in originals], 'ORIGINAL_LABELS_CHANGED')
    source_lock = fc.read_json(root, manifest['source_lock'], bundle)
    require(source_lock['target_order'] == ids and source_lock['target_labels20_sha256'] == manifest['original_locked_targets']['sha256'], 'SOURCE_LOCK_MISMATCH')
    require(fc.instant(collection['collection_ended_at_utc']) <= fc.instant(source_lock['created_at_utc']) <= fc.utc_now(), 'SOURCE_LOCK_TIME_MISMATCH')
    # Retain and verify original sources, not just the exported copy.
    for name, expected in source_lock['protected_sources_and_previous_audits'].items():
        if name.startswith('data/evaluation/'):
            fc.artifact(root, {'path':name,'sha256':expected})
    selection = fc.read_json(root, manifest['target_selection'], bundle)
    binding = fc.read_json(root, manifest['label_lock'], bundle)
    require(selection['event_ids'] == ids and selection['raw_sequence_sha256'] == raw_sha, 'TARGET_SELECTION_LOCK_MISMATCH')
    require(binding['target_labels_sha256'] == manifest['target_labels']['sha256']
            and binding['target_selection_sha256'] == manifest['target_selection']['sha256']
            and binding['raw_sequence_sha256'] == raw_sha
            and binding['normalized_input_sha256'] == fc.digest({'events':events}), 'LABEL_LOCK_HASH_MISMATCH')
    by_id = {e['id']:e for e in events}
    for row in labels:
        require(all(str(provenance[row['event_id']][k]) == row[k] for k in fc.PROVENANCE_FIELDS), 'TARGET_RAW_PROVENANCE_MISMATCH')
        # Preserve unknown held_out/author/time fields, never turn them into facts.
        row['features'] = by_id[row['event_id']]['features']
    run_binding = dict(manifest_sha256=fc.digest(manifest), raw_sequence_sha256=raw_sha,
                       normalized_input_sha256=fc.digest({'events':events}), engine_freeze_sha256=fc.FREEZE_SHA256,
                       development_authorization_sha256=fc.sha(root / POLICY_PATH))
    return dict(events=events, provenance=provenance, targets=labels, binding=run_binding,
                bundle_sha256=fc.digest(run_binding), approval=policy, development_policy=policy)


def calculate_binary(targets, predictions, metadata):
    """Central binary score only; historical held-out/category proof is not a gate."""
    require(len(targets) == len(predictions) == 20 and len({t['event_id'] for t in targets}) == 20, 'EXACTLY_20_TARGETS_REQUIRED')
    require(Counter(t['expected_label'] for t in targets) == {'KEEP':10,'REMOVE':10}, 'KEEP10_REMOVE10_REQUIRED')
    require(len({p['event_id'] for p in predictions}) == 20 and {p['event_id'] for p in predictions} == {t['event_id'] for t in targets}, 'Prediction ID mismatch')
    pred = {p['event_id']:p['predicted_label'] for p in predictions}
    table = {('REMOVE','REMOVE'):'TP', ('KEEP','REMOVE'):'FP', ('REMOVE','KEEP'):'FN', ('KEEP','KEEP'):'TN'}
    rows = []
    for t in targets:
        key = (t['expected_label'], pred[t['event_id']])
        require(key in table, 'Invalid binary label')
        rows.append(dict(event_id=t['event_id'],expected_label=key[0],predicted_label=key[1],remove_category=t['remove_category'],classification=table[key],**metadata))
    c = Counter(r['classification'] for r in rows)
    tp,fp,fn,tn = (c[k] for k in ('TP','FP','FN','TN'))
    p = tp/(tp+fp) if tp+fp else 0
    r = tp/(tp+fn) if tp+fn else 0
    f1 = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0
    return dict(status='COMPLETE',run_mode='DEVELOPMENT',official_pass=None,total=20,REMOVE=10,KEEP=10,
                TP=tp,FP=fp,FN=fn,TN=tn,precision=p,recall=r,f1=f1,target=.79,passed=f1>=.79),rows
