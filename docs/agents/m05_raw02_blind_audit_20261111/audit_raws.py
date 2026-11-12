"""Prediction-blind audit of original M05 raw_01 and raw_02. No model imports."""
import csv, hashlib, json
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
OLD = ROOT / 'docs/agents/m05_raw_blind_audit_20261111'
RAW_DIRS = [ROOT / ('data/evaluation/m05_heldout_raw_0' + str(n)) for n in (1, 2)]
csv.field_size_limit(100_000_000)
KST = timezone(timedelta(hours=9))
FREEZE = datetime(2026, 11, 9, 10, 56, 51, tzinfo=KST)
def canon(o): return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
def h(o): return hashlib.sha256(o).hexdigest()
def fh(p): return h(p.read_bytes())
def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        r=csv.DictReader(f); rows=list(r); return r.fieldnames, rows
def dump(name, o): (OUT/name).write_text(json.dumps(o, ensure_ascii=False, indent=2)+'\n')
def content(r): return {k:v for k,v in r.items() if k not in ('id', 'event_id')}

before = {str(p.relative_to(ROOT)):fh(p) for d in RAW_DIRS for p in sorted(d.glob('*.csv'))}
prior_before = {str(p.relative_to(ROOT)):fh(p) for p in sorted(OLD.iterdir()) if p.is_file()}
reports=[]; all_events=[]; by_dataset={}; row_source={}
for d in RAW_DIRS:
    files={n:read(d/n) for n in ('events.csv','tasks.csv','sessions.csv')}
    events=files['events.csv'][1]; tasks=files['tasks.csv'][1]; sessions=files['sessions.csv'][1]
    by_dataset[d.name]=events
    all_events += events
    issues=[]; timestamps=[]; received=[]; seq=[]; payloads=[]
    sid={r['id'] for r in sessions}; tid={r['id'] for r in tasks}
    for name, (cols, rows) in files.items():
        if len({r['id'] for r in rows}) != len(rows): issues.append([name,'DUPLICATE_PRIMARY_ID'])
        for i,r in enumerate(rows,1):
            if None in r or any(v is None for v in r.values()): issues.append([name,i,'CSV_FIELD_COUNT'])
    if len({r['event_id'] for r in events}) != len(events): issues.append(['DUPLICATE_EVENT_ID'])
    if any(not r['event_id'] for r in events): issues.append(['MISSING_EVENT_ID'])
    if any(r['session_id'] not in sid for r in events+tasks): issues.append(['SESSION_FK'])
    if any(r['task_id'] not in tid for r in events): issues.append(['TASK_FK'])
    for i,r in enumerate(events,1):
        obj=json.loads(r['locators_json']); payloads.append(obj); ec=obj['event_context']
        seq.append(ec['event_sequence'])
        ts=datetime.fromisoformat(ec['event_time'].replace('Z','+00:00'))
        timestamps.append(ts)
        recv=datetime.fromisoformat(obj['analysis']['server_quality_guard']['received_at'].replace('Z','+00:00')); received.append(recv)
        if ec['event_id'] != r['event_id']: issues.append([i,'EVENT_ID_MISMATCH'])
        if obj['session']['page_session_id'] != r['session_id']: issues.append([i,'PAYLOAD_SESSION_MISMATCH'])
        if datetime.fromisoformat(r['event_time']).replace(tzinfo=KST) != ts: issues.append([i,'UTC_KST_MISMATCH'])
        if abs(obj['analysis']['event_ts_ms']-ts.timestamp()*1000)>.1: issues.append([i,'EPOCH_MISMATCH'])
        if ts<=FREEZE: issues.append([i,'NOT_AFTER_FREEZE_REFERENCE'])
        if recv<ts: issues.append([i,'RECEIVED_BEFORE_EVENT'])
        row_source[r['event_id']]={'source_file':str((d/'events.csv').relative_to(ROOT)),'source_position_1based':i,'source_sha256':fh(d/'events.csv'),'raw_row_sha256':h(canon(r))}
    if seq != list(range(1,len(events)+1)): issues.append(['SOURCE_SEQUENCE_NOT_CONTIGUOUS'])
    for r in tasks:
        a=datetime.fromisoformat(r['start_time']); b=datetime.fromisoformat(r['end_time'])
        if b<a or abs((b-a).total_seconds()*1000-int(r['duration_ms']))>.01: issues.append([r['id'],'TASK_DURATION_MISMATCH'])
    for r in sessions:
        times=[datetime.fromisoformat(x['event_time']) for x in events if x['session_id']==r['id']]
        if min(times)!=datetime.fromisoformat(r['start_time']) or max(times)!=datetime.fromisoformat(r['end_time']): issues.append([r['id'],'SESSION_ENVELOPE_MISMATCH'])
    interactions=[p['event_context']['interaction_id'] for p in payloads]
    reqs=[p.get('api_context',{}).get('request_id') for p in payloads if p.get('api_context',{}).get('request_id')]
    back=[{'previous_source_position':i,'source_position':i+1,'delta_ms':round((timestamps[i]-timestamps[i-1]).total_seconds()*1000,3)} for i in range(1,len(timestamps)) if timestamps[i]<timestamps[i-1]]
    reports.append({'dataset':d.name,'status':'RAW_STRUCTURALLY_VALID' if not issues else 'ISSUES','files':{n:{'sha256':fh(d/n),'records':len(r),'columns':c} for n,(c,r) in files.items()},'issues':issues,'session_ids':sorted(sid),'sequence_contiguous':seq==list(range(1,len(events)+1)),'source_sequence_range':[min(seq),max(seq)],'unique_interaction_ids':len(set(interactions))==len(interactions),'unique_request_ids':len(set(reqs))==len(reqs),'interaction_types':dict(Counter(x['interaction_type'] for x in events)),'first_event_kst':min(timestamps).astimezone(KST).isoformat(),'last_event_kst':max(timestamps).astimezone(KST).isoformat(),'first_received_utc':min(received).isoformat(),'last_received_utc':max(received).isoformat(),'all_after_freeze_reference':min(timestamps)>FREEZE,'source_order_timestamp_backtracks':back})
ids={r['event_id'] for r in all_events}; sessions={r['session_id'] for r in all_events}
rh={h(canon(r)) for r in all_events}; ch={h(canon(content(r))) for r in all_events}
inventory=[]; skipped=[]
for p in sorted((ROOT/'data').rglob('*.csv')):
    if p.parent in RAW_DIRS: continue
    if any(w in str(p).lower() for w in ('prediction','predicted','confusion')): skipped.append({'path':str(p.relative_to(ROOT)),'reason':'prediction-related name'}); continue
    with p.open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f); cols=r.fieldnames or []
        if any(c in cols for c in ('predicted_label','prediction','predicted_keep')): skipped.append({'path':str(p.relative_to(ROOT)),'reason':'prediction-related columns; body not read'}); continue
        if 'event_id' not in cols and not ('session_id' in cols and 'event_type' in cols): continue
        rows=0; eid=set(); sid=set(); rr=set(); cc=set()
        typ='event_rows' if 'event_type' in cols else 'event_reference_index'
        for x in r:
            rows+=1
            if x.get('event_id') in ids: eid.add(x['event_id'])
            if x.get('session_id') in sessions: sid.add(x['session_id'])
            if typ=='event_rows':
                a=h(canon(x));b=h(canon(content(x)))
                if a in rh: rr.add(a)
                if b in ch: cc.add(b)
        inventory.append({'path':str(p.relative_to(ROOT)),'sha256':fh(p),'source_type':typ,'records':rows,'event_id_overlap':sorted(eid),'session_id_overlap':sorted(sid),'canonical_row_overlap':sorted(rr),'id_excluded_raw_content_overlap':sorted(cc)})
dump('history_inventory.json',{'scope':'Available repository data/**/*.csv, excluding raw_01/raw_02 and prediction-related bodies. Not an external/deleted/complete historical-use certification. Raw hashes retain nested IDs/timestamps and are not engine-feature hashes.','files':inventory,'skipped':skipped})
cols, candidates=read(OLD/'partial_label_candidates_NOT_FOR_EVALUATION.csv')
events01=by_dataset['m05_heldout_raw_01'];events02=by_dataset['m05_heldout_raw_02']
for c in candidates:
    x=events01[int(c['source_position_1based'])-1]
    assert c['event_id']==x['event_id']
    assert c['source_sha256']==fh(RAW_DIRS[0]/'events.csv')
    assert c['raw_row_sha256']==h(canon(x))
    assert not c['held_out']
old_candidates=[dict(x) for x in candidates]
x=events02[0]
new={k:'' for k in cols}
new.update({'source_position_1based':'1','csv_record_number_including_header':'2','event_id':x['event_id'],'raw_id':x['id'],'session_id':x['session_id'],'source_event_sequence':'1','event_time_kst':x['event_time'],'proposed_label':'REMOVE','proposed_remove_category':'noise','held_out_status':'SUPPORTED_BY_AVAILABLE_HISTORY_NOT_CERTIFIED','label_status':'PARTIAL_REVIEW_NOT_TARGET_LOCK','source_file':row_source[x['event_id']]['source_file'],'source_sha256':row_source[x['event_id']]['source_sha256'],'raw_row_sha256':row_source[x['event_id']]['raw_row_sha256'],'context_source_positions':'2 3 4 5 6 7 8','rationale':'collector_boot는 확장 수집기의 시작 진단이다. 입력/API context가 비어 있고 뒤에서 실제 로그인 행위가 시작된다. 업무 행동 자체가 아닌 기술 진단으로 noise 후보를 보완한다.'})
candidates.append(new)
assert candidates[:13]==old_candidates
assert len({x['event_id'] for x in candidates})==14
with (OUT/'partial_label_candidates_NOT_FOR_EVALUATION.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(candidates)
ambiguous=[
 {'category':'duplicate','positions':[9,10],'reason':'동일 GET /api/auth/me지만 서로 다른 request_id, start/end timestamp를 가진 별도 요청이다. 응답 본문이 수집되지 않아 의미 중복을 확인할 수 없다.'},
 {'category':'duplicate','positions':[139,141,144],'reason':'같은 저장 완료 팝업이지만 open lifecycle, ui_outcome, 구조 snapshot의 의미가 다르다. 무엇을 canonical로 보존할지 사전 규약이 없다.'},
 {'category':'duplicate','positions':[42,52,71],'reason':'현재 메뉴 재선택은 별도 interaction ID를 가진 사용자 행위다. 반복행동 의도는 인정하나 duplicate와 repeated_action의 독립적 구별/동일 사건 중복수집 증거가 없어 duplicate 3건으로 간주하지 않는다.'},
 {'category':'duplicate','positions':[18,22,27,29,34,37,43,47],'reason':'일정 상세 확인은 각각 /api/schedules/16, /18, /28, /32에 별도 PATCH를 일으킨다. 서로 다른 업무 객체를 동일 사건의 복제라고 볼 근거가 없다.'},
 {'category':'duplicate','positions':[107,108],'reason':'동일 제목 필드의 연속 클릭이나 각각 별도 interaction_id이다. repeated_action에 가깝고 쿼터를 위해 duplicate로 바꾸지 않는다. raw01 반복행동 2건은 유지한다.'},
 {'category':'noise','positions':[12,147],'reason':'visibilitychange_hidden에 따른 page_close는 세션/사용자 탭 상태 경계 정보를 갖는다. 단순 noise라는 근거가 없다.'},
 {'category':'noise','positions':[21,46,68,81,86,101,133,144],'reason':'popup_structure는 화면 상태와 폼/결과 문맥을 갖는다. 기술 이벤트라는 이유만으로 제거하지 않는다.'},
 {'category':'irrelevant_action','positions':[59,89,114],'reason':'명함 관리로의 이동은 일일보고 작업 사이의 우회로 보이나 수집 후 회상에 무관행동 2건 의도가 있으나 ID/행위 대응이 없어 해당 이동이 조회 업무인지 시험상 무관행동인지 구별할 수 없다.'},
 {'category':'irrelevant_action','positions':[84,87,99,112],'reason':'보고서 열기/닫기·중단은 실제 업무 준비/취소와 무관행동을 구별할 수 없다. 수집 후 회상의 category 수량만으로 특정 중단을 무관행동에 대응시킬 수 없다.'}
]
for a in ambiguous:
    a['events']=[{'event_id':events02[i-1]['event_id'],**row_source[events02[i-1]['event_id']]} for i in a['positions']]
dump('ambiguous_candidates_NOT_GT.json',{'status':'NOT_GT','candidates':ambiguous})
after={str(p.relative_to(ROOT)):fh(p) for d in RAW_DIRS for p in sorted(d.glob('*.csv'))}
prior_after={str(p.relative_to(ROOT)):fh(p) for p in sorted(OLD.iterdir()) if p.is_file()}
assert before==after and prior_before==prior_after
counts=Counter(c['proposed_label'] for c in candidates)
cats=Counter(c['proposed_remove_category'] for c in candidates if c['proposed_label']=='REMOVE')
report={'status':'RAW_VALID_TARGET20_BLOCKED','raws':reports,'combined':{'events':len(all_events),'unique_event_ids':len(ids),'session_count':len(sessions),'cross_raw_event_id_unique':len(ids)==len(all_events),'canonical_distinct_rows':len(rh),'id_excluded_raw_distinct_rows':len(ch)},'history':{'inventory_sha256':fh(OUT/'history_inventory.json'),'files':len(inventory),'event_row_count':sum(i['records'] for i in inventory if i['source_type']=='event_rows'),'overlap_counts':{k:sum(len(i[k]) for i in inventory) for k in ('event_id_overlap','session_id_overlap','canonical_row_overlap','id_excluded_raw_content_overlap')},'complete_historical_nonuse_certified':False,'inference_feature_hash_check':'NOT_PERFORMED_BY_BLIND_LABELER'},'engine_freeze_reference':{'kst':FREEZE.isoformat(),'authority':'Prior audit parent-supplied cutoff. Blind labeler did not open engine manifest/code.'},'collection_intent_evidence':{'status':'POST_COLLECTION_USER_RECOLLECTION_BEFORE_PREDICTION','latest_user_correction':'m05_heldout_raw_02 수집 당시 별도 메모 파일은 작성하지 않았습니다.','pre_collection_memo_exists':False,'intended_counts':{'duplicate':3,'additional_noise':'about 2 or more','irrelevant_action':2,'repeated_action':'prefer existing raw01 candidates'},'event_id_mapping_supplied':False,'assessment':'Retrospective intent is evidence of the intended collection exercise, not proof of category identity for a specific event. Actual event semantics were independently reconsidered. Ambiguous events remain unselected.','supersedes_previous_memo_claim':True},'candidates':{'preserved_raw01_rows':13,'added_raw02_rows':1,'labels':dict(counts),'remove_categories':dict(cats),'unfilled_requested_categories':{'duplicate':3,'noise':1,'repeated_action':0,'irrelevant_action':2},'held_out_fields':'blank until nonuse evidence is complete','target_lock_created':False},'integrity':{'raw_files_unchanged':before==after,'previous_audit_files_unchanged':prior_before==prior_after,'raw_sha256':before,'previous_audit_sha256':prior_before},'blindness':{'model_code_read':False,'adapter_code_read':False,'prediction_files_read':False,'model_or_adapter_executed':False,'engine_prediction_generated':False,'raw_session_semantics_reviewed':True},'limitations':['Raw timestamps are later than frozen cutoff but cannot alone certify complete training/development nonuse.','Latest user correction confirms no separate pre-collection memo. Only post-collection recollection before cleaning prediction is available; no event IDs/category mapping were supplied.','Shared install_id/tab and workflow continuity across raw sessions are retained; no synthetic boundary or reorder was introduced.','Source-order API timestamps may go backward; preserve original record order.'],'created_at_utc':datetime.now(timezone.utc).isoformat()}
dump('raw_validation.json',report)
print(json.dumps({'status':report['status'],'combined':report['combined'],'history':report['history'],'candidates':report['candidates'],'raws':[{k:r[k] for k in ('dataset','status','first_event_kst','last_event_kst','issues','source_order_timestamp_backtracks')} for r in reports]},ensure_ascii=False,indent=2))
