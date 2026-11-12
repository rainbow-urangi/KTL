"""Verified archive order is sidecar provenance, never a model feature."""
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
from model.workflow_candidate_v1.src.analysis import action
from .errors import ValidationError


POLICY_PATH = Path(__file__).resolve().parents[1] / 'policy.json'
CAPTURE_FIELDS = ('capture_run_id', 'capture_tab_id', 'capture_frame_id',
                  'capture_root_tab_id', 'capture_tab_path')


def _require(value, reason):
    if not value:
        raise ValidationError('CAPTURE_PROVENANCE_INVALID', reason)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'Duplicate JSON key in capture evidence')
        result[key] = value
    return result


def read_json(raw):
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON evidence')))


def load_capture(csv_path, manifest_path):
    """Validate original byte/row/context binding and explicit session transitions."""
    csv_path, manifest_path = Path(csv_path), Path(manifest_path)
    _require(not csv_path.is_symlink() and not manifest_path.is_symlink(), 'Capture source symlinks are unsupported')
    raw, manifest_raw = csv_path.read_bytes(), manifest_path.read_bytes()
    manifest = read_json(manifest_raw)
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    headers, rows = reader.fieldnames, list(reader)
    _require(headers and len(headers) == len(set(headers)) and None not in headers, 'Capture CSV headers are invalid')
    _require(set(CAPTURE_FIELDS) <= set(headers) and {'id', 'event_id', 'session_id', 'event_time', 'interaction_type'} <= set(headers),
             'Capture CSV lacks required provenance columns')
    _require(rows and all(None not in row and all(value is not None for value in row.values()) for row in rows),
             'Capture CSV rows do not match their headers')
    _require(isinstance(manifest, dict) and manifest.get('capture_scope_version') == 2 and manifest.get('active') is False,
             'Stopped capture scope version 2 is required')
    _require(manifest.get('csv_sha256') == hashlib.sha256(raw).hexdigest()
             and manifest.get('csv_byte_count') == len(raw), 'Capture CSV bytes do not match the manifest')
    _require(manifest.get('columns') == headers and manifest.get('event_count') == len(rows),
             'Capture CSV columns or count do not match the manifest')
    evidence = manifest.get('event_evidence')
    _require(isinstance(evidence, list) and len(evidence) == len(rows), 'Capture evidence row count mismatch')
    run, target = manifest.get('run_id'), manifest.get('target_tab_id')
    _require(isinstance(run, str) and bool(run) and type(target) is int and target >= 0,
             'Capture run and target tab are required')
    _require(manifest.get('capture_tab_paths') == {str(target): [target]},
             'Capture policy cannot order concurrent tabs or a branched tab tree')
    seen_ids, contexts, bindings = set(), set(), []
    blocks, session_sequences, seen_sessions = [], {}, set()
    for number, (row, ev) in enumerate(zip(rows, evidence), 1):
        _require(isinstance(ev, dict) and type(ev.get('csv_row')) is int and ev['csv_row'] == number
                 and row['id'] == str(number), 'Capture archive ordinal binding mismatch')
        _require(all(isinstance(row.get(key), str) and row[key] for key in ('event_id', 'session_id', 'event_time')),
                 'Capture event identity is missing')
        _require(row['event_id'] not in seen_ids, 'Duplicate capture event ID')
        seen_ids.add(row['event_id'])
        _require(all(ev.get(key) == row[key] for key in ('event_id', 'session_id', 'event_time')),
                 'Capture event identity differs from its manifest evidence')
        _require(row['capture_run_id'] == run and row['capture_root_tab_id'] == str(target)
                 and row['capture_tab_id'] == str(target), 'Capture run or root tab differs across rows')
        _require(row['capture_frame_id'].isdigit(), 'Capture frame identity is invalid')
        frame = int(row['capture_frame_id'])
        _require(type(ev.get('tab_id')) is int and ev['tab_id'] == target
                 and type(ev.get('frame_id')) is int and ev['frame_id'] == frame,
                 'Capture tab/frame evidence differs from CSV')
        _require(read_json(row['capture_tab_path']) == [target], 'Capture tab path differs from its root')
        contexts.add((target, frame))
        _require(len(contexts) == 1, 'Capture policy cannot order concurrent tabs or frames')
        sequence = ev.get('event_sequence')
        _require(type(sequence) is int and sequence > 0, 'Capture local event sequence is missing')
        sid = row['session_id']
        if not blocks or blocks[-1]['session_id'] != sid:
            _require(sid not in seen_sessions, 'Interleaved session blocks cannot be joined')
            seen_sessions.add(sid)
            blocks.append(dict(session_id=sid, first_csv_row=number, last_csv_row=number))
        blocks[-1]['last_csv_row'] = number
        _require(sid not in session_sequences or sequence > session_sequences[sid],
                 'Local session event sequence is duplicated or reversed')
        session_sequences[sid] = sequence
        binding = dict(csv_row=number, event_id=row['event_id'], source_session_id=sid,
                       capture_run_id=run, capture_tab_id=target, capture_frame_id=frame,
                       capture_root_tab_id=target, capture_tab_path=[target], event_sequence=sequence)
        for key in ('interaction_id', 'related_interaction_id', 'related_event_id', 'parent_event_id',
                    'cause_event_id', 'causal_chain_id', 'correlation_id'):
            if key in ev:
                binding[key] = deepcopy(ev[key])
        bindings.append(binding)
    transitions = []
    for previous, following in zip(blocks, blocks[1:]):
        old_end, new_start = previous['last_csv_row'], following['first_csv_row']
        _require(rows[old_end - 1]['interaction_type'] == 'page_close',
                 'Session transition lacks a preceding page_close')
        _require(new_start < following['last_csv_row']
                 and rows[new_start - 1]['interaction_type'] == 'collector_boot'
                 and rows[new_start]['interaction_type'] == 'page_view',
                 'Session transition lacks observed collector_boot and page_view')
        transitions.append(dict(previous_session_id=previous['session_id'],
            next_session_id=following['session_id'], previous_last_csv_row=old_end,
            next_first_csv_row=new_start, evidence='SAME_CAPTURE_TAB_FRAME_PAGE_CLOSE_BOOT_PAGE_VIEW'))
    return dict(rows=rows, headers=headers, bindings=bindings, session_blocks=blocks, transitions=transitions,
                run_id=run, csv_sha256=hashlib.sha256(raw).hexdigest(),
                capture_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
                csv_path=str(csv_path.resolve()), capture_manifest_path=str(manifest_path.resolve()))


def capture_view(capture, analysis):
    """Use every model-derived action event in verified archive order; no medoid choice."""
    lookup, workflow_events = {}, {}
    for workflow in analysis['workflows']:
        for eid in workflow['source_event_evidence']:
            _require(eid not in workflow_events, 'Model workflows overlap source events')
            workflow_events[eid] = workflow['workflow_instance_id']
    rows = capture['rows']
    _require(set(workflow_events) == {row['event_id'] for row in rows}, 'Model workflows omit or add capture events')
    for step in analysis['tables']['process_steps']:
        for eid in step['source_event_evidence']:
            _require(eid not in lookup and workflow_events.get(eid) == step['process_instance_id'],
                     'Model procedure provenance overlaps or differs from its workflow')
            lookup[eid] = step
    action_ids = {row['event_id'] for row in rows if action(row)}
    _require(action_ids and set(lookup) == action_ids, 'Model procedures omit or add actionful source events')
    procedures, lineage, excluded = [], [], []
    previous_key = None
    for row, binding in zip(rows, capture['bindings']):
        eid = row['event_id']
        mapped = deepcopy(binding)
        mapped['source_workflow_id'] = workflow_events[eid]
        if eid not in lookup:
            mapped.update(representation='EXCLUDED_BY_EXISTING_ACTION_POLICY', source_process_model_id=None, node_id=None)
            excluded.append(dict(csv_row=binding['csv_row'], event_id=eid,
                                 source_session_id=row['session_id'], interaction_type=row['interaction_type']))
            lineage.append(mapped)
            continue
        step = lookup[eid]
        _require(step['source_session_id'] == row['session_id'] and step['action'] == action(row),
                 'Model action or session differs from the original event')
        signature = tuple(step[key] for key in ('action', 'http_method', 'normalized_endpoint', 'page_path', 'target_role'))
        owner = (step['process_instance_id'], step['process_model_id'], row['session_id'])
        key = (owner, signature)
        mapped.update(representation='OBSERVED_PROCEDURE', source_process_model_id=step['process_model_id'], node_id=step['node_id'])
        lineage.append(mapped)
        if procedures and previous_key == key:
            procedures[-1]['evidence'].append(eid)
            procedures[-1]['source_csv_rows'].append(binding['csv_row'])
        else:
            procedures.append(dict(id=step['node_id'], node_id=step['node_id'], order=len(procedures) + 1,
                action=step['action'], http_method=step['http_method'],
                target=dict(page_path=step['page_path'], role=step['target_role'], normalized_endpoint=step['normalized_endpoint']),
                evidence=[eid], source_workflow_id=step['process_instance_id'],
                source_process_model_id=step['process_model_id'], source_session_id=row['session_id'],
                source_csv_rows=[binding['csv_row']]))
        previous_key = key
    token = hashlib.sha256(capture['run_id'].encode('utf-8')).hexdigest()[:12]
    model_id, instance_id = 'CAPTURE-PM-' + token, 'CAPTURE-WF-' + token
    policy_sha = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    canonical = dict(schema_version='workflow-canonical-1.2', canonical_kind='CAPTURE_OBSERVED_SEQUENCE',
        process_model_id=model_id, canonical_instance_id=instance_id, procedures=procedures,
        source_workflow_ids=list(dict.fromkeys(p['source_workflow_id'] for p in procedures)),
        source_process_model_ids=list(dict.fromkeys(p['source_process_model_id'] for p in procedures)),
        source_session_ids=list(dict.fromkeys(p['source_session_id'] for p in procedures)),
        source_csv_sha256=capture['csv_sha256'], source_capture_manifest_sha256=capture['capture_manifest_sha256'],
        capture_policy_sha256=policy_sha)
    model = dict(process_model_id=model_id, canonical_instance_id=instance_id, mode='DEVELOPMENT',
                 scope='CAPTURE_OBSERVED_SEQUENCE', canonical_policy='VERIFIED_CAPTURE_ARCHIVE_ORDER',
                 source_process_model_ids=canonical['source_process_model_ids'],
                 source_workflow_ids=canonical['source_workflow_ids'])
    learned_ids = {eid for c in analysis['canonical'] for p in c['procedures'] for eid in p['evidence']}
    return dict(scope='CAPTURE_OBSERVED_SEQUENCE', status='COMPLETED', canonical=canonical, process_model=model,
        lineage=lineage, transitions=capture['transitions'], session_blocks=capture['session_blocks'],
        diagnostics=dict(raw_event_count=len(rows), action_event_count=len(action_ids), excluded_event_count=len(excluded),
            workflow_event_count=len(workflow_events), all_process_steps_event_count=len(lookup),
            learned_canonical_event_count=len(learned_ids), capture_canonical_event_count=len(action_ids),
            excluded_events=excluded, scope_notice='Observed capture execution; no typical-business semantic or official correctness claim',
            ordering='CAPTURE_ARCHIVE_ORDINAL', timestamp_reordering=False))
