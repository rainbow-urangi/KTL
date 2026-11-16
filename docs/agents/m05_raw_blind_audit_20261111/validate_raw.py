"""Read-only raw CSV audit. Never imports model, adapter, evaluator, or prediction files."""
import csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / 'data/evaluation/m05_heldout_raw_01'
OUT = Path(__file__).resolve().parent
csv.field_size_limit(100_000_000)

def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        return list(reader.fieldnames or []), rows

def content(row):
    # This preserves nested source provenance. It is NOT an inference feature hash.
    return {k:v for k,v in row.items() if k not in ('id', 'event_id')}

raw = {}
for name in ('events.csv', 'tasks.csv', 'sessions.csv'):
    columns, rows = read_csv(RAW/name)
    raw[name] = {'columns':columns, 'rows':rows, 'sha256':file_hash(RAW/name)}
events = raw['events.csv']['rows']
tasks = raw['tasks.csv']['rows']
sessions = raw['sessions.csv']['rows']
issues=[]
for name, data in raw.items():
    for n, row in enumerate(data['rows'], 1):
        if None in row or any(v is None for v in row.values()):
            issues.append({'code':'CSV_FIELD_COUNT_MISMATCH', 'file':name, 'record':n})
    ids=[row.get('id') for row in data['rows']]
    if len(ids)!=len(set(ids)):
        issues.append({'code':'DUPLICATE_PRIMARY_ID', 'file':name})

session_ids={r['id'] for r in sessions}
task_ids={r['id'] for r in tasks}
event_ids={r['event_id'] for r in events}
if len(event_ids)!=len(events): issues.append({'code':'DUPLICATE_EVENT_ID'})
if any(not r['event_id'] for r in events): issues.append({'code':'MISSING_EVENT_ID'})
if any(r['session_id'] not in session_ids for r in events+tasks): issues.append({'code':'SESSION_FK_MISSING'})
if any(r['task_id'] not in task_ids for r in events): issues.append({'code':'TASK_FK_MISSING'})
KST=timezone(timedelta(hours=9))
freeze=datetime(2026,11,9,10,56,51,tzinfo=KST)
payloads=[]
utc_times=[]
received=[]
sequence=[]
for n,row in enumerate(events,1):
    try: obj=json.loads(row['locators_json'])
    except Exception as exc:
        issues.append({'code':'BAD_LOCATORS_JSON','record':n,'error':str(exc)})
        continue
    payloads.append(obj)
    ec=obj.get('event_context',{})
    sequence.append(ec.get('event_sequence'))
    if ec.get('event_id')!=row['event_id']: issues.append({'code':'EVENT_ID_MISMATCH','record':n})
    if obj.get('session',{}).get('page_session_id')!=row['session_id']: issues.append({'code':'PAYLOAD_SESSION_MISMATCH','record':n})
    utc=datetime.fromisoformat(ec['event_time'].replace('Z','+00:00'))
    utc_times.append(utc)
    export_time=datetime.fromisoformat(row['event_time']).replace(tzinfo=KST)
    if export_time!=utc: issues.append({'code':'EXPORT_PAYLOAD_TIME_MISMATCH','record':n})
    ms=obj.get('analysis',{}).get('event_ts_ms')
    if ms is not None and abs(ms-utc.timestamp()*1000)>0.1: issues.append({'code':'EPOCH_TIME_MISMATCH','record':n})
    received.append(datetime.fromisoformat(obj['analysis']['server_quality_guard']['received_at'].replace('Z','+00:00')))
    if utc<=freeze: issues.append({'code':'NOT_AFTER_FREEZE','record':n})
    if received[-1]<utc: issues.append({'code':'RECEIVED_BEFORE_EVENT','record':n})
if sequence!=list(range(1,len(events)+1)): issues.append({'code':'NONCONTIGUOUS_SOURCE_SEQUENCE'})
backtracks=[{'previous_source_position':i,'source_position':i+1,'delta_ms':round((utc_times[i]-utc_times[i-1]).total_seconds()*1000,3),'interaction_type':events[i]['interaction_type']} for i in range(1,len(utc_times)) if utc_times[i]<utc_times[i-1]]
for row in tasks:
    start=datetime.fromisoformat(row['start_time'])
    end=datetime.fromisoformat(row['end_time'])
    if start>end: issues.append({'code':'TASK_REVERSED_TIME','task_id':row['id']})
    if abs((end-start).total_seconds()*1000-int(row['duration_ms']))>0.01: issues.append({'code':'TASK_DURATION_MISMATCH','task_id':row['id']})
for row in sessions:
    ts=[datetime.fromisoformat(r['event_time']) for r in events if r['session_id']==row['id']]
    if min(ts)!=datetime.fromisoformat(row['start_time']) or max(ts)!=datetime.fromisoformat(row['end_time']): issues.append({'code':'SESSION_ENVELOPE_MISMATCH','session_id':row['id']})

raw_row_hashes={digest_bytes(canonical(r)) for r in events}
raw_content_hashes={digest_bytes(canonical(content(r))) for r in events}
inventory=[]
for path in sorted((ROOT/'data').rglob('*.csv')):
    if RAW==path.parent: continue
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        columns=list(reader.fieldnames or [])
        if 'event_id' not in columns and not ('session_id' in columns and 'event_type' in columns): continue
        count=0;ids=set();overlap=set();full_overlap=set();content_overlap=set();session_overlap=set()
        source_type='event_rows' if 'event_type' in columns else 'event_reference_index'
        for row in reader:
            count+=1
            event_id=row.get('event_id','')
            if event_id: ids.add(event_id)
            if event_id in event_ids: overlap.add(event_id)
            if row.get('session_id') in session_ids: session_overlap.add(row['session_id'])
            if source_type=='event_rows':
                rh=digest_bytes(canonical(row))
                ch=digest_bytes(canonical(content(row)))
                if rh in raw_row_hashes: full_overlap.add(rh)
                if ch in raw_content_hashes: content_overlap.add(ch)
        inventory.append({'path':str(path.relative_to(ROOT)), 'resolved_path':str(path.resolve().relative_to(ROOT)), 'source_type':source_type,'sha256':file_hash(path),'rows':count,'unique_event_ids':len(ids),'event_id_overlap':sorted(overlap),'session_id_overlap':sorted(session_overlap),'canonical_row_hash_overlap':sorted(full_overlap),'id_excluded_raw_content_hash_overlap':sorted(content_overlap)})

inventory_obj={'scope':'All data/**/*.csv with an event_id column or session_id plus event_type, excluding the newly supplied raw directory. Event references are checked separately from full event rows. No filesystem-external or unavailable historical uses can be certified.', 'files':inventory}
(OUT/'history_inventory.json').write_text(json.dumps(inventory_obj,ensure_ascii=False,indent=2)+'\n')
report={
 'status':'RAW_STRUCTURALLY_VALID' if not issues else 'RAW_VALIDATION_ISSUES',
 'raw_directory':str(RAW.relative_to(ROOT)),
 'raw_files':{name:{k:v for k,v in data.items() if k!='rows'}|{'record_count':len(data['rows'])} for name,data in raw.items()},
 'session_ids':sorted(session_ids), 'event_count':len(events),'task_count':len(tasks),'session_count':len(sessions),
 'event_types':dict(Counter(r['interaction_type'] for r in events)),
 'source_sequence':{'min':min(sequence),'max':max(sequence),'contiguous':sequence==list(range(1,len(events)+1)),'preserve_order':True},
 'freeze_reference':{'kst':freeze.isoformat(),'utc':freeze.astimezone(timezone.utc).isoformat(),'authority':'Parent-supplied freeze cutoff; engine manifest independently verified by another worker, not opened by blind labeler.'},
 'timestamps':{'first_payload_utc':min(utc_times).isoformat(),'last_payload_utc':max(utc_times).isoformat(),'first_export_kst':min(utc_times).astimezone(KST).isoformat(),'last_export_kst':max(utc_times).astimezone(KST).isoformat(),'received_at_min_utc':min(received).isoformat(),'received_at_max_utc':max(received).isoformat(),'all_after_freeze':min(utc_times)>freeze,'csv_payload_offset_hours':9,'source_order_timestamp_backtracks':backtracks},
 'checks':{'unique_event_ids':len(event_ids)==len(events),'json_payloads_parsed':len(payloads),'raw_canonical_distinct_rows':len(raw_row_hashes),'raw_id_excluded_distinct_content':len(raw_content_hashes),'history_event_id_overlap_count':sum(len(x['event_id_overlap']) for x in inventory),'history_session_id_overlap_count':sum(len(x['session_id_overlap']) for x in inventory),'history_canonical_row_overlap_count':sum(len(x['canonical_row_hash_overlap']) for x in inventory),'history_id_excluded_raw_content_overlap_count':sum(len(x['id_excluded_raw_content_hash_overlap']) for x in inventory)},
 'issues':issues,
 'history_inventory_sha256':file_hash(OUT/'history_inventory.json'),
 'held_out_evidence':{'new_collection_after_freeze':True,'distinct_from_available_csv_history':all(not x['event_id_overlap'] and not x['session_id_overlap'] and not x['canonical_row_hash_overlap'] and not x['id_excluded_raw_content_hash_overlap'] for x in inventory),'complete_historical_nonuse_certified':False,'inference_feature_content_hash_check':'NOT_PERFORMED: this blind audit did not read the adapter or derive its model-facing feature mapping. Raw content hashes include nested source IDs and timestamps and are not a model-feature nonoverlap proof.'},
 'blindness':{'model_code_read':False,'prediction_files_read':False,'model_or_adapter_executed':False,'engine_prediction_generated':False},
 'created_at_utc':datetime.now(timezone.utc).isoformat()
}
(OUT/'raw_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('status','event_count','task_count','session_count','checks','issues','timestamps','history_inventory_sha256')},ensure_ascii=False,indent=2))
print('INVENTORY_FILES',len(inventory),'RAW_HISTORY_EVENT_ROWS',sum(x['rows'] for x in inventory if x['source_type']=='event_rows'))
