"""Fail-closed full-context orchestration. Frozen cleaning/score code is untouched.

Only temporary synthetic fixtures may bypass external evidence in unit tests via
mocking. There is no runtime bypass, fixture switch, or prediction-only endpoint.
"""
import ast
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .evaluators import EvaluationError, require, call_adapter
from .m05_heldout import calculate, digest, sha, validate_engine
from .m05_timestamp_evidence import prepare_policy, resolve_event_time

SCHEMA = 'm05-full-context-v1'
FREEZE_PATH = 'evaluation_contracts/development/m05_baseline_frozen_v1/freeze.json'
FREEZE_SHA256 = '23fde29b22c23976ccf02760f58b2c2490f3e5b054c385193fc7c463f5f00d10'
APPROVALS_PATH = 'evaluation_contracts/m05_full_context_approvals.json'
CATEGORY_COUNTS = {'duplicate': 3, 'noise': 3, 'repeated_action': 2, 'irrelevant_action': 2}
PROVENANCE_FIELDS = ('source_dataset', 'source_session_id', 'source_case_id',
                     'source_file', 'source_file_sha256', 'raw_sequence_index',
                     'csv_record_number', 'raw_event_timestamp')
LABEL_FIELDS = ('event_id', 'expected_label', 'remove_category', 'held_out',
                *PROVENANCE_FIELDS, 'label_rationale', 'labeler', 'labeled_at_utc')


def utc_now():
    return datetime.now(timezone.utc)


def instant(value):
    require(isinstance(value, str) and value.strip(), 'TIMESTAMP_MISSING')
    try:
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise EvaluationError('INVALID_TIMESTAMP') from exc
    # Do not silently guess the collector or engine host timezone.
    require(value.tzinfo is not None and value.utcoffset() is not None,
            'TIMESTAMP_TIMEZONE_REQUIRED')
    return value.astimezone(timezone.utc)


def artifact(root, entry, under=None):
    require(isinstance(entry, dict) and isinstance(entry.get('path'), str), 'ARTIFACT_REFERENCE_REQUIRED')
    path = (Path(root) / entry['path']).resolve()
    require(path.is_relative_to(Path(root).resolve()), 'ARTIFACT_OUTSIDE_REPOSITORY')
    if under is not None:
        require(path.is_relative_to(Path(under).resolve()), 'ARTIFACT_OUTSIDE_HELDOUT_BUNDLE')
    require(path.is_file() and sha(path) == entry.get('sha256'), 'ARTIFACT_HASH_MISMATCH: ' + str(path))
    return path


def read_json(root, entry, under=None):
    return json.loads(artifact(root, entry, under).read_text(encoding='utf-8'))


def validate_freeze(root, config):
    root = Path(root).resolve()
    path = root / FREEZE_PATH
    require(path.is_file() and sha(path) == FREEZE_SHA256, 'ENGINE_FREEZE_MISMATCH')
    freeze = json.loads(path.read_text())
    require(freeze.get('status') == 'FROZEN_AFTER_INDEPENDENT_PASS', 'ENGINE_NOT_FROZEN')
    for entry in freeze['immutable_artifacts'] + [freeze['active_engine_config']]:
        path = Path(entry['path'])
        require(path.is_file() and sha(path) == entry['sha256'], 'FROZEN_ARTIFACT_MISMATCH: ' + str(path))
    require(config == json.loads(Path(freeze['active_engine_config']['path']).read_text()),
            'ACTIVE_ENGINE_CONFIG_MISMATCH')
    validate_engine(root, config)
    return freeze


def frozen_normalizer(freeze):
    """Compile the original normalization definitions, excluding batching/imports.

    No definition is rewritten; notably CSVCaseAdapter.load_cases is never used.
    Its min/max-length filtering, cleaning and truncation must not touch input.
    """
    sources = {Path(e['path']).name: e for e in freeze['immutable_artifacts']}
    normalizer = Path(sources['csv_adapter.py']['path'])
    dataset = Path(sources['dataset_original.py']['path'])
    ns = dict(csv=csv, hashlib=hashlib, Path=Path, urlsplit=urlsplit, datetime=datetime)
    for path, wanted in ((dataset, {'parse_ts', 'status_bucket'}),
                         (normalizer, {'STANDARD_FIELDS', '_clean', 'normalize_case_id',
                                       'generic_activity', '_timestamp_sort_key', 'read_standard_rows'})):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.FunctionDef) and n.name in wanted) or
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets))]
        names = {n.name if isinstance(n, ast.FunctionDef) else n.targets[0].id for n in nodes}
        require(names == wanted, 'FROZEN_NORMALIZATION_DEFINITIONS_MISSING')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns


def raw_rows(path, normalizer):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        require(len(headers) == len(set(headers)), 'DUPLICATE_RAW_COLUMNS')
        require({'event_id', 'task_id', 'session_id', 'event_time'}.issubset(headers), 'RAW_SCHEMA_MISSING')
        rows = list(reader)
    require(rows and all(None not in r and all(v is not None for v in r.values()) for r in rows), 'MALFORMED_OR_EMPTY_RAW_CSV')
    mapping = {k: k for k in normalizer['STANDARD_FIELDS'] if k in headers}
    mapping.update(case_id='task_id', source_event_pk='event_id', ts='event_time')
    standard = normalizer['read_standard_rows'](str(path), mapping)
    require(len(standard) == len(rows), 'NORMALIZATION_ROW_LOSS')
    return rows, standard, mapping


def load_full_sequence(root, manifest, collection, normalizer, frozen_at):
    root = Path(root).resolve()
    dataset_id = manifest['dataset_id']
    heldout = root / 'data/held_out/m05'
    bundle = heldout / dataset_id
    require(bundle.resolve().is_relative_to(heldout.resolve()) and heldout.resolve().is_relative_to(root / 'data/held_out'), 'HELDOUT_PATH_REDIRECTED')
    raw_dir = bundle / 'raw'
    start, end = (instant(collection.get(k)) for k in ('collection_started_at_utc', 'collection_ended_at_utc'))
    require(frozen_at < start <= end <= utc_now(), 'NOT_POST_FREEZE_COLLECTION')
    require(collection.get('dataset_id') == dataset_id and collection.get('scope') == 'COMPLETE_SESSIONS_AND_TASKS', 'COLLECTION_SCOPE_INCOMPLETE')
    for key in ('collector_id', 'collector_version', 'timezone', 'completion_reason'):
        require(isinstance(collection.get(key), str) and collection[key].strip(), 'COLLECTION_EVIDENCE_MISSING: ' + key)
    # Hash-verified supporting records plus independent approval are necessary;
    # boolean assertions alone never open the gate.
    supporting_evidence = {}
    for key in ('clock_evidence', 'export_evidence'):
        evidence = read_json(root, collection.get(key), bundle)
        require(evidence.get('dataset_id') == dataset_id and evidence.get('findings'), 'COLLECTOR_EVIDENCE_INSUFFICIENT')
        supporting_evidence[key] = evidence
    timestamp_policy = prepare_policy(
        collection, supporting_evidence['clock_evidence'],
        lambda entry: read_json(root, entry, bundle),
        lambda entry: artifact(root, entry, bundle))
    refs = collection.get('raw_files')
    require(isinstance(refs, list) and refs, 'RAW_FILES_REQUIRED')
    events, provenance, seen_paths, identity_by_case = [], {}, set(), {}
    resolved_times = {}
    for ref in refs:
        path = artifact(root, ref, raw_dir)
        require(path.suffix == '.csv' and path not in seen_paths, 'DUPLICATE_OR_INVALID_RAW_FILE')
        seen_paths.add(path)
        raw, standard, mapping = raw_rows(path, normalizer)
        require(type(ref.get('row_count')) is int and ref['row_count'] == len(raw), 'RAW_ROW_COUNT_MISMATCH')
        require(ref.get('column_mapping') == mapping, 'RAW_COLUMN_MAPPING_MISMATCH')
        for record, (source, row) in enumerate(zip(raw, standard), 1):
            eid = row['source_event_pk']
            require(eid == source['event_id'] and isinstance(eid, str) and eid.strip() and eid not in provenance, 'DUPLICATE_OR_INVALID_RAW_EVENT_ID')
            require(source['session_id'].strip() and row['case_id'] is not None and source['task_id'] == row['source_case_id'], 'RAW_IDENTITY_MISSING_OR_REWRITTEN')
            event_time, timestamp_method = resolve_event_time(source, timestamp_policy)
            resolved_times[eid] = event_time
            require(start <= event_time <= end and event_time > frozen_at, 'EVENT_OUTSIDE_POST_FREEZE_COLLECTION')
            identity = (source['session_id'], source['task_id'])
            case = row['case_id']
            require(case not in identity_by_case or identity_by_case[case] == identity, 'CROSS_SESSION_CASE_ID_COLLISION')
            identity_by_case[case] = identity
            index = len(events)
            features = {k: row[k] for k in ('case_id', 'activity', 'ts')}
            events.append({'id': eid, 'features': features})
            provenance[eid] = dict(source_dataset=dataset_id, source_session_id=source['session_id'],
                                   source_case_id=source['task_id'], source_file=str(path.relative_to(root)),
                                   source_file_sha256=ref['sha256'], raw_sequence_index=index,
                                   csv_record_number=record, raw_event_timestamp=source['event_time'],
                                   engine_input_index=index,
                                   validated_event_timestamp_utc=event_time.isoformat(),
                                   timestamp_resolution_method=timestamp_method,
                                   timestamp_evidence_sha256=collection['clock_evidence']['sha256'])
    require(collection.get('event_count') == len(events), 'FULL_SEQUENCE_COUNT_MISMATCH')
    require(seen_paths == {p.resolve() for p in raw_dir.rglob('*.csv')}, 'UNDECLARED_OR_OMITTED_RAW_FILE')
    # Complete session/task inventories bind every row, including non-targets.
    for key, identity_fields in (('sessions', ('source_session_id',)), ('tasks', ('source_session_id', 'source_case_id'))):
        entries = read_json(root, collection.get(key), bundle).get(key)
        require(isinstance(entries, list) and entries, 'SESSION_TASK_INVENTORY_MISSING')
        groups = {}
        for event in events:
            p = provenance[event['id']]
            groups.setdefault(tuple(p[f] for f in identity_fields), []).append(event['id'])
        seen = set()
        for entry in entries:
            identity = tuple(entry.get(f) for f in identity_fields)
            require(identity not in seen and identity in groups, 'SESSION_TASK_ID_MISMATCH')
            seen.add(identity)
            require(entry.get('event_ids') == groups[identity] and entry.get('complete') is True and entry.get('completion_evidence'), 'INCOMPLETE_SESSION_OR_TASK')
            a, b = instant(entry.get('started_at_utc')), instant(entry.get('ended_at_utc'))
            require(start <= a <= b <= end, 'SESSION_TASK_TIME_RANGE_MISMATCH')
            require(all(a <= resolved_times[e] <= b for e in groups[identity]), 'EVENT_OUTSIDE_SESSION_TASK')
        require(seen == set(groups), 'SESSION_TASK_COVERAGE_MISMATCH')
    grouped = {}
    for index, event in enumerate(events):
        grouped.setdefault(event['features']['case_id'], []).append(dict(event['features'], _row_index=index, id=event['id']))
    for group in grouped.values():
        for index, row in enumerate(sorted(group, key=normalizer['_timestamp_sort_key'])):
            provenance[row['id']]['case_order_index'] = index
    return events, provenance, digest(collection['raw_files']), bundle


def validate_history(root, manifest, events, raw_sha, normalizer):
    proof = manifest.get('provenance', {})
    require(proof.get('reviewer') and proof.get('complete_history_attested') is True, 'HELD_OUT_PROVENANCE_INSUFFICIENT')
    instant(proof.get('reviewed_at_utc'))
    ids = {e['id'] for e in events}
    fingerprints = {digest(e['features']) for e in events}
    inventories = []
    for scope in ('training', 'development'):
        refs = proof.get(scope + '_inventories')
        require(isinstance(refs, list) and refs, 'HISTORY_INVENTORIES_REQUIRED')
        for ref in refs:
            history = read_json(root, ref)
            require(history.get('scope') == scope and history.get('source_files'), 'HISTORY_SCOPE_OR_SOURCES_MISSING')
            actual = []
            for source in history['source_files']:
                path = artifact(root, source)
                require(not path.is_relative_to((Path(root) / 'data/held_out').resolve()), 'HISTORY_CANNOT_USE_HELDOUT')
                raw, standard, _ = raw_rows(path, normalizer)
                for row in standard:
                    require(row['source_event_pk'] and row['case_id'] is not None, 'HISTORY_IDENTITY_MISSING')
                    item = {'event_id': row['source_event_pk'], 'feature_sha256': digest({k: row[k] for k in ('case_id', 'activity', 'ts')})}
                    require(item['event_id'] not in ids and item['feature_sha256'] not in fingerprints, 'HELD_OUT_OVERLAP')
                    actual.append(item)
            key = lambda e: (e['event_id'], e['feature_sha256'])
            require(actual and sorted(actual, key=key) == sorted(history.get('events', []), key=key), 'HISTORY_SOURCE_RECONCILIATION_FAILED')
            inventories.append(ref['sha256'])
    audits = proof.get('audit_evidence')
    require(isinstance(audits, list) and audits, 'HELD_OUT_AUDIT_REQUIRED')
    for ref in audits:
        audit = read_json(root, ref)
        require(audit.get('raw_sequence_sha256') == raw_sha and sorted(audit.get('inventory_sha256', [])) == sorted(inventories)
                and audit.get('method') == 'SOURCE_HISTORY_RECONCILIATION' and audit.get('coverage_complete') is True
                and audit.get('findings'), 'HELD_OUT_AUDIT_INSUFFICIENT')
    return proof


def load_locked_targets(root, manifest, events, provenance, raw_sha, bundle):
    path = artifact(root, manifest.get('target_labels'), bundle)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == list(LABEL_FIELDS), 'TARGET_LABEL_SCHEMA_MISMATCH')
        labels = list(reader)
    require(len(labels) == 20 and all(None not in r and all(v is not None for v in r.values()) for r in labels), 'EXACTLY_20_TARGETS_REQUIRED')
    ids = [r['event_id'] for r in labels]
    require(len(set(ids)) == 20 and all(eid in provenance for eid in ids), 'TARGET_ID_MISMATCH')
    selection = read_json(root, manifest.get('target_selection'), bundle)
    require(selection.get('event_ids') == ids and selection.get('raw_sequence_sha256') == raw_sha
            and selection.get('selection_principle'), 'TARGET_SELECTION_LOCK_MISMATCH')
    require(Counter(r['expected_label'] for r in labels) == {'KEEP': 10, 'REMOVE': 10}, 'KEEP10_REMOVE10_REQUIRED')
    require(Counter(r['remove_category'] for r in labels if r['expected_label'] == 'REMOVE') == CATEGORY_COUNTS, 'REMOVE_CATEGORY_3_3_2_2_REQUIRED')
    lock = read_json(root, manifest.get('label_lock'), bundle)
    locked_at = instant(lock.get('locked_at_utc'))
    require(lock.get('target_labels_sha256') == manifest['target_labels']['sha256']
            and lock.get('target_selection_sha256') == manifest['target_selection']['sha256']
            and lock.get('raw_sequence_sha256') == raw_sha
            and lock.get('normalized_input_sha256') == digest({'events': events}), 'LABEL_LOCK_HASH_MISMATCH')
    require(lock.get('prediction_blind') is True and lock.get('labeler'), 'LABEL_INDEPENDENCE_MISSING')
    by_id = {e['id']: e for e in events}
    target_events = []
    for row in labels:
        require(row['held_out'] == 'true', 'HELD_OUT_STRICT_TRUE_REQUIRED')
        require(row['expected_label'] != 'KEEP' or row['remove_category'] == '', 'KEEP_CATEGORY_MUST_BE_EMPTY')
        require(row['labeler'] == lock['labeler'] and row['label_rationale'].strip(), 'INDEPENDENT_LABEL_RATIONALE_REQUIRED')
        require(instant(manifest['_collection_end']) <= instant(row['labeled_at_utc']) <= locked_at <= utc_now(), 'LABEL_NOT_LOCKED_BEFORE_PREDICTION')
        require(all(str(provenance[row['event_id']][k]) == row[k] for k in PROVENANCE_FIELDS), 'TARGET_RAW_PROVENANCE_MISMATCH')
        target_events.append(dict(row, held_out=True, features=by_id[row['event_id']]['features']))
    audit = read_json(root, manifest.get('prediction_access_audit'), bundle)
    require(audit.get('label_lock_sha256') == manifest['label_lock']['sha256']
            and audit.get('raw_sequence_sha256') == raw_sha and audit.get('coverage_complete') is True
            and audit.get('prediction_runs') == [] and audit.get('prediction_views') == []
            and audit.get('method') == 'EXECUTION_AND_ACCESS_LOG_RECONCILIATION'
            and audit.get('findings') and audit.get('reviewer') != lock['labeler'] and audit.get('reviewer')
            and instant(audit.get('reviewed_until_utc')) >= locked_at, 'PREDICTION_BLINDNESS_NOT_SUBSTANTIATED')
    require(audit.get('source_logs'), 'PREDICTION_ACCESS_LOGS_REQUIRED')
    for ref in audit['source_logs']:
        log = read_json(root, ref, bundle)
        require(log.get('raw_sequence_sha256') == raw_sha and log.get('entries') == []
                and instant(log.get('coverage_started_at_utc')) <= instant(manifest['_collection_start'])
                and instant(log.get('coverage_ended_at_utc')) >= locked_at,
                'PREDICTION_ACCESS_LOG_COVERAGE_INSUFFICIENT')
    return target_events, lock


def validate_bundle(root, manifest, config):
    root = Path(root).resolve()
    require(isinstance(manifest, dict) and manifest.get('schema_version') == SCHEMA, 'FULL_CONTEXT_MANIFEST_REQUIRED')
    name = manifest.get('dataset_id')
    require(isinstance(name, str) and name not in ('', '.', '..') and Path(name).name == name, 'INVALID_DATASET_ID')
    require(manifest.get('used_for_training') is False and manifest.get('used_for_development') is False, 'PRIOR_USE_DECLARATIONS_REQUIRED')
    freeze = validate_freeze(root, config)
    normalizer = frozen_normalizer(freeze)
    bundle = root / 'data/held_out/m05' / name
    collection = read_json(root, manifest.get('collection'), bundle)
    events, provenance, raw_sha, bundle = load_full_sequence(root, manifest, collection, normalizer, instant(freeze['frozen_at_utc']))
    proof = validate_history(root, manifest, events, raw_sha, normalizer)
    augmented = dict(manifest, _collection_start=collection['collection_started_at_utc'], _collection_end=collection['collection_ended_at_utc'])
    targets, lock = load_locked_targets(root, augmented, events, provenance, raw_sha, bundle)
    require(instant(collection['collection_ended_at_utc']) <= instant(lock['locked_at_utc']), 'CONTEXT_NOT_FIXED_BEFORE_LABEL_LOCK')
    binding = {'manifest_sha256': digest(manifest), 'raw_sequence_sha256': raw_sha,
               'normalized_input_sha256': digest({'events': events}), 'engine_freeze_sha256': FREEZE_SHA256}
    approval_path = root / APPROVALS_PATH
    require(approval_path.is_file(), 'INDEPENDENT_FULL_CONTEXT_APPROVAL_MISSING')
    approvals = json.loads(approval_path.read_text()).get('approvals', [])
    approval = next((a for a in approvals if a.get('binding') == binding and a.get('status') == 'PASS'), None)
    require(approval and approval.get('reviewer') and approval['reviewer'] not in {proof['reviewer'], lock['labeler']}
            and approval.get('evidence_review') == 'SOURCE_COMPLETENESS_POST_FREEZE_HISTORY_AND_BLIND_LABEL_LOCK'
            and instant(lock['locked_at_utc']) <= instant(approval.get('reviewed_at_utc')) <= utc_now(),
            'INDEPENDENT_FULL_CONTEXT_APPROVAL_MISSING')
    return dict(events=events, provenance=provenance, targets=targets, binding=binding,
                bundle_sha256=digest(binding), approval=approval)


def validate_predictions(response, events, config):
    require(isinstance(response, dict) and response.get('model_version') == config['cleaning_model_version'], 'ENGINE_VERSION_MISMATCH')
    predictions = response.get('predictions')
    require(isinstance(predictions, list) and all(isinstance(p, dict) for p in predictions), 'FULL_PREDICTIONS_REQUIRED')
    ids = [p.get('id') for p in predictions]
    require(all(isinstance(i, str) for i in ids) and len(ids) == len(set(ids)) == len(events)
            and set(ids) == {e['id'] for e in events}, 'FULL_PREDICTION_ID_MISMATCH')
    by_id = {p['id']: p for p in predictions}
    for index, event in enumerate(events):
        p = by_id[event['id']]
        require(p.get('label') in ('KEEP', 'REMOVE') and p.get('source_row_index') == index
                and p.get('case_id') == event['features']['case_id'] and p.get('activity') == event['features']['activity'], 'INVALID_PREDICTION_OR_PROVENANCE')
        require('remove_reason' in p and 'duplicate_of_event_id' in p, 'PREDICTION_REASON_MISSING')
        require((p['label'] == 'KEEP' and p['remove_reason'] is None and p['duplicate_of_event_id'] is None)
                or (p['label'] == 'REMOVE' and p['remove_reason'] in {'empty_activity', 'drop_exact', 'drop_prefix', 'consecutive_same_activity'}), 'INVALID_PREDICTION_REASON')
        duplicate = p['duplicate_of_event_id']
        require(duplicate is None or (isinstance(duplicate, str) and duplicate in by_id and duplicate != event['id']
                and by_id[duplicate].get('case_id') == p['case_id'] and by_id[duplicate].get('label') == 'KEEP'), 'INVALID_DUPLICATE_PROVENANCE')
    return by_id


def csv_text(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def write_json(path, value):
    # Exclusive creation: no previous run artifact is overwritten.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def attempt_path(root, prepared):
    # Stable input identity prevents a new label/approval manifest from reopening
    # a raw input that already exposed predictions, even under a different name.
    return Path(root) / 'results/development/m05_full_context/attempts' / (prepared['binding']['normalized_input_sha256'] + '.json')


def evaluate(root, manifest, config):
    """Validate first; infer all rows once; join/scoring only the locked twenty."""
    prepared = validate_bundle(root, manifest, config)
    root = Path(root).resolve()
    out = root / 'results/development/m05_full_context' / prepared['bundle_sha256']
    require(out.resolve().is_relative_to(root), 'RESULT_PATH_OUTSIDE_REPOSITORY')
    out.parent.mkdir(parents=True, exist_ok=True)
    claim = attempt_path(root, prepared)
    claim.parent.mkdir(exist_ok=True)
    started_at = utc_now().isoformat()
    try:
        write_json(claim, dict(run_id=out.name, binding=prepared['binding'], started_at_utc=started_at))
        out.mkdir()  # Persistent claim, including failed/uncertain attempts.
    except FileExistsError as exc:
        raise EvaluationError('BUNDLE_ALREADY_ATTEMPTED_NO_AUTOMATIC_RERUN') from exc
    run = dict(status='STARTED', run_id=out.name, run_mode='DEVELOPMENT', official_pass=None,
               started_at_utc=started_at, binding=prepared['binding'], approval=prepared['approval'],
               full_event_count=len(prepared['events']), target_event_count=20,
               context_event_count=len(prepared['events']) - 20)
    write_json(out / 'attempt.json', run)
    try:
        # Recheck every input/evidence/freeze hash after the durable claim.
        require(validate_bundle(root, manifest, config) == prepared, 'BUNDLE_CHANGED_BEFORE_INFERENCE')
        payload = {'events': prepared['events']}
        write_json(out / 'engine_input.json', payload)
        write_json(out / 'validated_manifest.json', manifest)
        write_json(out / 'normalization_provenance.json', prepared['provenance'])
        write_json(out / 'locked_target_snapshot.json', {'targets': prepared['targets']})
        response = call_adapter(config, 'cleaning', payload, root)
        write_json(out / 'full_predictions.json', response)
        predictions = validate_predictions(response, prepared['events'], config)
        target_predictions = [{'event_id': e['event_id'], 'predicted_label': predictions[e['event_id']]['label']} for e in prepared['targets']]
        metadata = dict(model_version=config['cleaning_model_version'], engine_freeze_sha256=FREEZE_SHA256,
                        model_sha256=config['model_artifact']['sha256'], adapter_sha256=config['adapter_artifact']['sha256'],
                        **{k: v for k, v in prepared['binding'].items() if k != 'engine_freeze_sha256'},
                        target_labels_sha256=manifest['target_labels']['sha256'],
                        target_selection_sha256=manifest['target_selection']['sha256'],
                        predictions_sha256=sha(out / 'full_predictions.json'), run_id=out.name, run_mode='DEVELOPMENT', is_target=True)
        result, rows = calculate(prepared['targets'], target_predictions, metadata)
        for row in rows:
            p = predictions[row['event_id']]
            row.update(prepared['provenance'][row['event_id']], held_out=True,
                       remove_reason=p['remove_reason'], duplicate_of_event_id=p['duplicate_of_event_id'])
        evidence = csv_text(rows)
        from .m05_full_context_csv import recalculate_csv
        checked = recalculate_csv(evidence)
        require(all(result[k] == checked[k] for k in checked), 'INDEPENDENT_CSV_RECALCULATION_MISMATCH')
        # No score publication if source/labels/engine changed while inference ran.
        require(validate_bundle(root, manifest, config) == prepared, 'BUNDLE_CHANGED_DURING_INFERENCE')
        with (out / 'evidence.csv').open('x', encoding='utf-8', newline='') as stream:
            stream.write(evidence)
        result.update(full_event_count=len(prepared['events']), context_event_count=len(prepared['events']) - 20,
                      target_event_count=20, run_id=out.name, csv_recalculation='PASS')
        write_json(out / 'result.json', result)
        run.update(status='COMPLETE', completed_at_utc=utc_now().isoformat(),
                   files={p.name: sha(p) for p in out.iterdir() if p.is_file()})
        write_json(out / 'run_manifest.json', run)
        return result, rows
    except Exception as exc:
        write_json(out / 'blocked.json', dict(status='BLOCKED', score=None, f1=None, official_pass=None,
                                              reason=str(exc), run_id=out.name, attempted_at_utc=started_at))
        raise
