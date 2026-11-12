"""Evidence preparation only. No cleaning adapter, prediction, or scoring calls."""
import csv, hashlib, io, json, os, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from backend.m05_full_context import (FREEZE_PATH, FREEZE_SHA256, LABEL_FIELDS,
    PROVENANCE_FIELDS, digest, sha, validate_freeze, frozen_normalizer, raw_rows,
    load_full_sequence, instant, validate_bundle)
from backend.m05_timestamp_evidence import prepare_policy, resolve_event_time

DOC = ROOT / 'docs/agents/m05_full_context_bundle_20261111'
DATASET = 'raw01_raw02_raw03_target20_20261111'
OUT = ROOT / 'data/held_out/m05' / DATASET
SOURCE_LOCK = ROOT / 'docs/agents/m05_raw03_attested_label_lock_20261111'
NOW = datetime.now(timezone.utc).isoformat()
def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))
def ref(p):
    return dict(path=rel(p), sha256=sha(Path(p)))
def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return ref(p)
def copy(p, q):
    q.parent.mkdir(parents=True, exist_ok=True)
    with q.open('xb') as f:
        f.write(p.read_bytes())
    assert sha(p) == sha(q)
    return ref(q)
def readrows(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
if OUT.exists():
    raise SystemExit('Existing preparation is immutable; no overwrite.')
config = json.loads((ROOT / 'evaluation_contracts/m05_engine.json').read_text())
freeze = validate_freeze(ROOT, config)
normalizer = frozen_normalizer(freeze)
lock = json.loads((SOURCE_LOCK / 'target_label_lock.json').read_text())
assert sha(SOURCE_LOCK / 'target_labels20.csv') == lock['target_labels20_sha256']
protected = {**lock['protected_sources_and_previous_audits'],
             **lock['artifacts']}
protected[rel(SOURCE_LOCK / 'target_label_lock.json')] = sha(SOURCE_LOCK / 'target_label_lock.json')
protected[rel(SOURCE_LOCK / 'target_label_lock.sha256')] = sha(SOURCE_LOCK / 'target_label_lock.sha256')
for p in list((ROOT / 'backend').glob('*.py')) + list((ROOT / 'tests').glob('*')) + [
    ROOT / 'R&D_COMPLIANCE.md', ROOT / 'frontend/app.js']:
    if p.is_file():
        protected[rel(p)] = sha(p)
for p, h in protected.items():
    assert sha(ROOT / p) == h, p
write(DOC / 'protected_before.json', protected)

raw_refs, source_refs, source_copies, rows_by_file, payloads, standard_all = [], [], [], {}, {}, []
for n in ('01', '02', '03'):
    source = ROOT / f'data/evaluation/m05_heldout_raw_{n}'
    for filename in ('events.csv', 'sessions.csv', 'tasks.csv'):
        src = source / filename
        dest = OUT / ('raw' if filename == 'events.csv' else 'source_metadata') / f'raw_{n}' / filename
        source_refs.append(ref(src))
        copied = copy(src, dest)
        source_copies.append(dict(original=ref(src), copy=copied, byte_identical=True))
        if filename == 'events.csv':
            rows, standard, mapping = raw_rows(dest, normalizer)
            rows_by_file[n] = rows
            raw_refs.append(dict(**copied, row_count=len(rows), column_mapping=mapping))
            standard_all.extend(standard)
            for row in rows:
                payloads[row['event_id']] = json.loads(row['locators_json'])
for p in SOURCE_LOCK.iterdir():
    if p.is_file():
        copy(p, OUT / 'source_label_lock' / p.name)
assert [len(rows_by_file[n]) for n in ('01','02','03')] == [203,147,67]
write(OUT / 'source_copy_bindings.json', dict(files=source_copies))
raw_sha = digest(raw_refs)
policy = dict(schema_version='m05-timestamp-evidence-v1', timestamp_column='event_time',
    timezone='Asia/Seoul', raw_files=[{k:r[k] for k in ('path','sha256')} for r in raw_refs],
    payload_sources=[dict(column='locators_json',
        event_id_path=['event_context','event_id'],
        session_id_path=['session','page_session_id'],
        timestamps=[
            dict(path=['event_context','event_time'], format='iso8601'),
            dict(path=['analysis','event_ts_ms'], format='unix_ms'),
            dict(path=['raw_payload','event_context','event_time'], format='iso8601')])])
clock = dict(dataset_id=DATASET,
    findings='For every one of 417 events, raw event/session identity and all three authoritative event-time fields must agree exactly, and reproduce the CSV wall time in Asia/Seoul. Raw bytes and frozen features.ts are unchanged. Receipt time and file mtime are not event-time evidence.',
    timestamp_policy=policy,
    source_bindings=source_refs,
    coverage='Complete supplied 417 rows; server-side export authority independently unverified.')
clock_ref = write(OUT / 'clock_evidence.json', clock)
collection_stub = dict(dataset_id=DATASET, timezone='Asia/Seoul', raw_files=raw_refs)
prepared_policy = prepare_policy(collection_stub, clock,
    lambda r: json.loads((ROOT/r['path']).read_text()), lambda r: ROOT/r['path'])
resolved, timestamp_rows, sessions, tasks, collection_checks = {}, [], [], [], []
for n in ('01','02','03'):
    rows = rows_by_file[n]
    assert [payloads[r['event_id']]['event_context']['event_sequence'] for r in rows] == list(range(1,len(rows)+1))
    assert rows[0]['interaction_type'] == 'collector_boot' and rows[-1]['interaction_type'] == 'page_close'
    groups = defaultdict(list)
    for r in rows:
        eid = r['event_id']; p = payloads[eid]
        assert p['raw_payload']['event_context']['event_id'] == eid
        t, method = resolve_event_time(r, prepared_policy)
        assert t > instant(freeze['frozen_at_utc'])
        resolved[eid] = t
        groups[(r['session_id'],r['task_id'])].append(eid)
        timestamp_rows.append(dict(event_id=eid, raw_event_timestamp=r['event_time'],
            event_time_utc=t.isoformat(), method=method, payload_utc=p['event_context']['event_time'],
            payload_epoch_ms=p['analysis']['event_ts_ms'],
            nested_payload_utc=p['raw_payload']['event_context']['event_time']))
    metadir = OUT / 'source_metadata' / f'raw_{n}'
    sr = readrows(metadir/'sessions.csv'); tr = readrows(metadir/'tasks.csv')
    assert len(sr)==1 and {r['session_id'] for r in rows}=={sr[0]['id']}
    assert {(r['session_id'],r['id']) for r in tr}==set(groups)
    def wall(v):
        # Only a source metadata boundary already matched to an event's UTC proof.
        return datetime.fromisoformat(v).replace(tzinfo=ZoneInfo('Asia/Seoul')).astimezone(timezone.utc)
    session_start, session_end = wall(sr[0]['start_time']), wall(sr[0]['end_time'])
    assert session_start == resolved[rows[0]['event_id']] and session_end == resolved[rows[-1]['event_id']]
    sessions.append(dict(source_session_id=sr[0]['id'],
        event_ids=[r['event_id'] for r in rows], complete=True,
        started_at_utc=session_start.isoformat(), ended_at_utc=session_end.isoformat(),
        completion_evidence=dict(source=ref(metadir/'sessions.csv'),
            basis='Supplied export has collector_boot through page_close, contiguous source sequence 1..N, exact source boundary matches. This is export-internal completeness, not a server audit.')))
    for trr in tr:
        ids=groups[(trr['session_id'],trr['id'])]
        a,b=wall(trr['start_time']),wall(trr['end_time'])
        assert trr['status']=='COMPLETED' and a==min(resolved[e] for e in ids) and b==max(resolved[e] for e in ids)
        tasks.append(dict(source_session_id=trr['session_id'],source_case_id=trr['id'],
            event_ids=ids, complete=True, started_at_utc=a.isoformat(),ended_at_utc=b.isoformat(),
            completion_evidence=dict(source=ref(metadir/'tasks.csv'), source_status=trr['status'],
                basis='Exact event task_id membership; source task boundaries match first/last UTC-proven events. No case regrouping.')))
    collection_checks.append(dict(source=f'raw_{n}',event_count=len(rows),task_count=len(tr),
        source_sequence_contiguous=True, starts_collector_boot=True, ends_page_close=True,
        session_task_boundary_matches=True))
sessions_ref=write(OUT/'sessions.json',dict(sessions=sessions))
tasks_ref=write(OUT/'tasks.json',dict(tasks=tasks))
export_ref=write(OUT/'export_evidence.json',dict(dataset_id=DATASET,
    findings='All 417 supplied events, three sessions, and 313 completed task rows are copied byte-identically. Every event is accounted for once, source sequence is contiguous within each session, and session/task boundary rows agree with event UTC proof. No claim is made that inaccessible server records, deleted exports, or execution/access logs are complete.',
    raw_sequence_sha256=raw_sha, source_copies=source_copies, checks=collection_checks,
    source_export_authority='NOT_INDEPENDENTLY_ATTESTED'))
collector_ids={p['source'] for p in payloads.values()}
collector_versions={(p['event_context']['collector_build'],p['event_context']['extension_version']) for p in payloads.values()}
assert len(collector_ids)==len(collector_versions)==1
version,extension=next(iter(collector_versions))
collection=dict(dataset_id=DATASET, scope='COMPLETE_SESSIONS_AND_TASKS',
    collection_started_at_utc=min(resolved.values()).isoformat(),
    collection_ended_at_utc=max(resolved.values()).isoformat(),
    collector_id=next(iter(collector_ids)), collector_version=f'{version}; extension {extension}',
    timezone='Asia/Seoul', completion_reason='Each supplied session terminates with page_close and contiguous event_sequence. Independent export authority remains pending.',
    event_count=417, raw_files=raw_refs,sessions=sessions_ref,tasks=tasks_ref,
    clock_evidence=clock_ref,export_evidence=export_ref)
collection_ref=write(OUT/'collection.json',collection)
events,provenance,computed_raw_sha,bundle=load_full_sequence(ROOT,dict(dataset_id=DATASET),collection,normalizer,instant(freeze['frozen_at_utc']))
assert raw_sha==computed_raw_sha
input_sha=digest(dict(events=events))
write(OUT/'normalized_input_PREPARATION_ONLY.json',dict(events=events))
write(OUT/'normalization_provenance.json',provenance)
write(OUT/'timestamp_proof_rows.json',dict(timestamp_policy_sha256=clock_ref['sha256'],events=timestamp_rows))

oldlabels=readrows(SOURCE_LOCK/'target_labels20.csv')
assert len(oldlabels)==20 and [r['event_id'] for r in oldlabels]==lock['target_order']
assert Counter(r['expected_label'] for r in oldlabels)=={'KEEP':10,'REMOVE':10}
converted, mappings=[],[]
for row in oldlabels:
    p=provenance[row['event_id']]
    assert int(row['source_position_1based'])==p['csv_record_number']
    assert row['source_sha256']==p['source_file_sha256']
    assert row['session_id']==p['source_session_id'] and row['event_time_kst']==p['raw_event_timestamp']
    new=dict(event_id=row['event_id'], expected_label=row['expected_label'],
        remove_category=row['remove_category'],held_out='',
        **{k:str(p[k]) for k in PROVENANCE_FIELDS},
        label_rationale=row['rationale'],labeler='',labeled_at_utc='')
    converted.append(new)
    mappings.append(dict(event_id=row['event_id'],source_label=row,
        candidate_provenance={k:new[k] for k in PROVENANCE_FIELDS},
        semantic_fields_unchanged=True, unresolved_fields=['held_out','labeler','labeled_at_utc']))
label_path=OUT/'target_labels.schema_candidate.csv'
with label_path.open('x',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=LABEL_FIELDS);w.writeheader();w.writerows(converted)
labels_ref=ref(label_path)
write(OUT/'target_label_mapping.json',dict(source_labels=ref(SOURCE_LOCK/'target_labels20.csv'),
    source_lock=ref(SOURCE_LOCK/'target_label_lock.json'),source_lock_created_at_utc=lock['created_at_utc'],
    rule='No relabeling. Source does not record individual labeler or labeled_at_utc; blank fields remain unresolved. Source batch lock time is not falsely represented as per-label annotation time.',
    mappings=mappings))
selection_ref=write(OUT/'target_selection.json',dict(event_ids=lock['target_order'],raw_sequence_sha256=raw_sha,
    selection_principle='Preserve exact 20 IDs, order, binary labels, categories and rationales from the already locked source artifact. All other 397 events remain context only.',
    source_target_labels=ref(SOURCE_LOCK/'target_labels20.csv')))
binding_ref=write(OUT/'label_binding_candidate.json',dict(
    target_labels_sha256=labels_ref['sha256'],target_selection_sha256=selection_ref['sha256'],
    raw_sequence_sha256=raw_sha,normalized_input_sha256=input_sha,
    source_lock=ref(SOURCE_LOCK/'target_label_lock.json'),
    source_lock_created_at_utc=lock['created_at_utc'],binding_prepared_at_utc=NOW,
    locked_at_utc=None,prediction_blind=None,labeler=None,
    status='BLOCKED_UNTIL_SOURCE_ATTRIBUTION_AND_ACCESS_COVERAGE_VERIFIED',
    note='This preparer binds existing labels to unchanged full context. It does not act as a new independent labeler or retroactively certify blindness.'))

hist_source=json.loads((ROOT/'docs/agents/m05_raw03_blind_audit_20261111/history_inventory.json').read_text())
current_ids={e['id'] for e in events}; current_fp={digest(e['features']) for e in events}
inventories={}; history_checks=[]; index_checks=[]
for scope in ('training','development'):
    files=[]; entries=[]
    for src in hist_source['files']:
        name=src['path']
        if name.startswith('data/evaluation/m05_heldout_raw_'): continue
        s='training' if name.startswith('data/training/') else 'development'
        if s!=scope:continue
        p=ROOT/name
        assert sha(p)==src['sha256']
        if src['source_type']!='event_rows':
            rr=readrows(p)
            ids={r.get('event_id') for r in rr if r.get('event_id')}
            index_checks.append(dict(**ref(p),row_count=len(rr),overlap=sorted(ids&current_ids),
                checked='event IDs only; reference index lacks frozen feature schema'))
            assert not ids&current_ids
            continue
        rr,ss,mm=raw_rows(p,normalizer)
        local=[dict(event_id=r['source_event_pk'],feature_sha256=digest({k:r[k] for k in ('case_id','activity','ts')})) for r in ss]
        id_overlap=sorted({e['event_id'] for e in local}&current_ids)
        fp_overlap=sorted({e['feature_sha256'] for e in local}&current_fp)
        assert not id_overlap and not fp_overlap
        entries.extend(local);files.append(ref(p))
        history_checks.append(dict(**ref(p),scope=scope,row_count=len(local),event_id_overlap=id_overlap,
            feature_sha256_overlap=fp_overlap,column_mapping=mm))
    inventories[scope]=write(OUT/f'history/{scope}_inventory.json',
        dict(scope=scope,source_files=files,events=entries,coverage_complete=False,
             limitation='Accessible recorded sources only. No attestation of all deleted, external, unrecorded, or remote use.'))
assert sum(c['row_count'] for c in history_checks)==34553
history_audit_ref=write(OUT/'history/source_history_reconciliation.json',dict(
    method='SOURCE_HISTORY_RECONCILIATION',raw_sequence_sha256=raw_sha,
    inventory_sha256=[r['sha256'] for r in inventories.values()],coverage_complete=False,
    findings='34553 accessible historical source rows normalized with the exact frozen task_id/case_id, activity, ts mapper. Zero full-input event-ID and exact model-feature-hash overlap. Three reference indexes checked for ID overlap separately. raw01/raw02 are current full context, not historical use, and are excluded from history inventories.',
    per_source=history_checks,reference_index_checks=index_checks,
    limitations=['Historical source-file existence and hash do not establish all actual uses.',
        'External/deleted/undocumented/remote histories are not accounted for.',
        'No independent completeness reviewer has supplied a signed or otherwise authoritative coverage record.']))
history_summary=dict(source_file_count=len(history_checks),source_row_count=34553,
    reference_index_count=len(index_checks),reference_index_rows=sum(x['row_count'] for x in index_checks),
    event_id_overlap_count=0,feature_hash_overlap_count=0,coverage_complete=False)

# Observe existing records without creating or pretending complete execution logs.
log_candidates=[]
for base in ('results','docs/agents','evaluation_contracts'):
    for p in sorted((ROOT/base).rglob('*')):
        if not p.is_file() or DOC in p.parents: continue
        if ('m05' in str(p).lower() and (p.suffix=='.log' or p.name in ('attempt.json','run_manifest.json','audit_snapshot_pre_prediction.json','gate_report.json','functional_validation.json'))):
            log_candidates.append(dict(**ref(p),source_kind='existing_project_record',
                coverage='Not an exhaustive execution/access log'))
claim_dir=ROOT/'results/development/m05_full_context/attempts'
claim_files=[ref(p) for p in sorted(claim_dir.glob('*.json'))] if claim_dir.exists() else []
shell=Path.home()/'.zsh_history'
shell_observation=dict(path=str(shell),exists=shell.is_file(),coverage_complete=False)
if shell.is_file():
    content=shell.read_bytes()
    lines=content.decode('utf-8',errors='replace').splitlines()
    shell_observation.update(sha256=hashlib.sha256(content).hexdigest(),line_count=len(lines),
        relevant_line_count=sum('m05' in s.lower() or 'm05_heldout_raw_' in s for s in lines),
        matching_raw_session_lines=sum(any(sid in line for sid in {r['source_session_id'] for r in sessions}) for line in lines),
        content_copied=False, limitation='Interactive shell history can omit subprocesses, other shells, other tools, deleted history, and file views. Its current existence or mtime is not coverage proof.')
access_ref=write(OUT/'prediction_access_audit.INCOMPLETE.json',dict(
    label_lock_sha256=binding_ref['sha256'],source_label_lock_sha256=sha(SOURCE_LOCK/'target_label_lock.json'),
    raw_sequence_sha256=raw_sha,coverage_complete=False,
    prediction_runs=None,prediction_views=None,method='EXECUTION_AND_ACCESS_LOG_RECONCILIATION',
    findings='Accessible record inventory and current attempt-directory observation only. No matching durable full-context attempt file exists at observation time, but this cannot establish zero executions/views or coverage from collection start through lock. Existing agent reports are self-reports, not exhaustive execution/access logs.',
    reviewer=None,reviewed_until_utc=None,source_logs=[],
    source_record_inventory=log_candidates,existing_claim_files=claim_files,
    matching_normalized_input_attempt_exists=(claim_dir/(input_sha+'.json')).is_file(),
    shell_history_observation=shell_observation,
    prep_prediction_executions=0,prep_scoring_executions=0,
    required_coverage_start=collection['collection_started_at_utc'],
    required_coverage_end=lock['created_at_utc']))
manifest=dict(schema_version='m05-full-context-v1',dataset_id=DATASET,
    preparation_status='BLOCKED_EVIDENCE_INCOMPLETE_NOT_EXECUTABLE',
    used_for_training=None,used_for_development=None,
    collection=collection_ref,target_labels=labels_ref,target_selection=selection_ref,
    label_lock=binding_ref,prediction_access_audit=access_ref,
    provenance=dict(reviewer=None,reviewed_at_utc=None,complete_history_attested=False,
        training_inventories=[inventories['training']],development_inventories=[inventories['development']],
        audit_evidence=[history_audit_ref]),
    original_locked_targets=ref(OUT/'source_label_lock/target_labels20.csv'),
    user_attestation=ref(OUT/'source_label_lock/user_attestation.json'),
    source_lock=ref(OUT/'source_label_lock/target_label_lock.json'),
    evidence_boundary='RAW_CONTEXT_PLUS_DIRECT_USER_RECOLLECTION for the two raw03 REMOVE labels, not raw-only evidence. Source labels unchanged.',
    official_result=False)
manifest_ref=write(OUT/'manifest.json',manifest)
gate_error=None
try:
    validate_bundle(ROOT,manifest,config)
except Exception as exc:
    gate_error=str(exc)
assert gate_error=='PRIOR_USE_DECLARATIONS_REQUIRED',gate_error
assert not (ROOT/'evaluation_contracts/m05_full_context_approvals.json').exists()
after={p:sha(ROOT/p) for p in protected}
assert after==protected
validate_freeze(ROOT,config)
report=dict(created_at_utc=NOW,status='PREPARED_BLOCKED',full_event_count=417,
    target_event_count=20,context_event_count=397,session_count=3,task_case_count=len(tasks),
    source_rows=[203,147,67],labels={'KEEP':10,'REMOVE':10},
    label_categories=dict(Counter(r['remove_category'] for r in oldlabels if r['expected_label']=='REMOVE')),
    raw_sequence_sha256=raw_sha,normalized_input_sha256=input_sha,
    source_target_labels_sha256=lock['target_labels20_sha256'],
    source_target_lock_sha256=sha(SOURCE_LOCK/'target_label_lock.json'),
    engine_freeze_sha256=FREEZE_SHA256,manifest_byte_sha256=manifest_ref['sha256'],
    manifest_canonical_sha256=digest(manifest),history=history_summary,
    frozen_artifact_count=len(freeze['immutable_artifacts'])+1,
    protected_files_unchanged=len(after),timestamp_proof_pass_count=417,
    collection_validation='PASS_EXPORTED_ROW_CONTINUITY_AND_BOUNDARIES',
    collection_authority='PENDING_INDEPENDENT_EXPORT_COMPLETENESS',
    runtime_validation=dict(status='BLOCKED',reason=gate_error),
    blockers=['Complete training/development use-history coverage is unproven.',
        'Actual prediction execution/access logs covering collection through label lock are unavailable; no false empty log was written.',
        'Original CSV omits labeler and individual labeled_at_utc. Source batch-lock time was not recast as per-label time; attributable preservation/review is pending.',
        'Independent full-context approval registry does not exist; label correctness PASS alone is not full-context readiness.'],
    prediction_executions=0,score_executions=0,metrics_generated=False,
    independent_review_status='REQUESTED_SEPARATELY_NOT_SELF_APPROVED',
    source_files_modified=False,engine_or_adapter_modified=False,
    read_only_checks_only=True,full_backend_tests='NOT_RUN_METADATA_ONLY_NO_BACKEND_CHANGE')
write(DOC/'preparation_report.json',report)
write(DOC/'protected_after.json',after)
with (DOC/'README.md').open('x',encoding='utf-8') as f:
    f.write('# M05 full-context preparation, 2026-11-11\n\n')
    f.write('Prepared all 417 raw events (203 + 147 + 67), three sessions and 313 original task/case groups. Target IDs/order/labels/categories/rationales remain the locked KEEP10/REMOVE10; only those 20 would be scored. All nine raw CSVs and the original label-lock artifacts are byte-identical copies. No prediction, adapter, or scoring was run.\n\n')
    f.write('Bundle: '+rel(OUT)+'\n\n')
    f.write('All 417 timestamps were checked against source event/session IDs, UTC, epoch milliseconds and nested raw UTC. Frozen engine features.ts remains the untouched CSV timestamp. Collection/task boundaries and source sequences validate without changing task to case mapping.\n\n')
    f.write('34553 accessible historical source rows have no event-ID or exact frozen feature-hash overlap; three reference indexes have no ID overlap. This is bounded evidence, not an all-history assertion. raw01/raw02 belong to current context, not historical use.\n\n')
    f.write('BLOCKED: source-history completeness, actual execution/access-log coverage, attributable evaluation-schema label metadata, and independent full-context approval are not established. Used-for-training/development remain null and held_out remains blank. The actual validator rejects the draft with PRIOR_USE_DECLARATIONS_REQUIRED. No generated empty execution log or approval registry was created.\n\n')
    f.write('The two new labels remain raw plus retrospective user recollection. Their original raw-only uncertainties are unchanged. The original target label SHA-256 is '+lock['target_labels20_sha256']+'.\n\n')
    f.write('No source, frozen engine, adapter, backend or tests were edited. Full backend regression was not run for this metadata-only bundle. Independent review must inspect preparation_report.json and all hash bindings before any later release.\n')
files=[p for p in OUT.rglob('*') if p.is_file()]+[p for p in DOC.rglob('*') if p.is_file()]
write(DOC/'artifact_manifest.json',dict(created_at_utc=NOW,status='PREPARED_BLOCKED',
    files=[ref(p) for p in sorted(files)],note='This artifact inventory excludes itself. It is not independent approval.'))
print(json.dumps(report,ensure_ascii=False,indent=2))
