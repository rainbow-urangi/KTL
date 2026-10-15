"""원본과 v2를 유지하며 ID, 세션, 시간 및 화면 이동으로 논리 v3를 구성합니다."""
import csv, json, hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
BASE=ROOT/'data/development'
PARENT=BASE/'current_site_20x3_v2'
NEW='current_site_recollection_02'
OLD='current_site_20x3_v1'
REPLACE={'BU01-R1','BU01-R2','BU01-R3','BU02-R1','BU02-R2'}
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,rows):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def key(e):return (datetime.fromisoformat(e['event_time']),e['event_id'])
protected=[p for d in [PARENT,BASE/OLD,BASE/'current_site_recollection_01',BASE/NEW] for p in d.rglob('*') if p.is_file()]
before={str(p.relative_to(ROOT)):sha(p) for p in protected}
events={ds:read(BASE/ds/'events.csv') for ds in [OLD,NEW]}
byid={ds:{e['event_id']:e for e in ev} for ds,ev in events.items()}
for ds,ev in events.items():
 assert len(byid[ds])==len(ev)
 sessions={s.get('session_id',s.get('id')) for s in read(BASE/ds/'sessions.csv')}
 tasks={t['id']:t for t in read(BASE/ds/'tasks.csv')}
 assert all(e['session_id'] in sessions and e['task_id'] in tasks and tasks[e['task_id']]['session_id']==e['session_id'] for e in ev)
 for e in ev:key(e)
previous=read(BASE/'current_site_recollection_01/events.csv')
previous_ids={e['event_id'] for e in previous}
new_sessions={e['session_id'] for e in events[NEW]}-{e['session_id'] for e in previous}
assert len(new_sessions)==1
sid=next(iter(new_sessions))
new=sorted([e for e in events[NEW] if e['session_id']==sid],key=key)
assert not ({e['event_id'] for e in new}&previous_ids)
# 새 세션의 화면 이동을 실행 경계로 사용합니다.
menus={'개인정보','일정 관리','조직도/담당업무','일반 정보'}
markers=[e for e in new if e['interaction_type']=='click' and e['element_text'].strip() in menus]
starts=[new[0]]+[e for e in markers if e['element_text'].strip() in {'개인정보','일정 관리'}]
assert new[0]['interaction_type']=='collector_boot' and new[0]['page_url'].endswith('/mypage/personal-info')
occurrences=Counter(); replacement={}; members={}; candidates=[]
parent=read(PARENT/'execution_manifest.csv');fields=list(parent[0])
for start in starts:
 following=[e for e in markers if key(e)>key(start)]
 stop=min(following,key=key) if following else None
 ev=[e for e in new if key(e)>=key(start) and (stop is None or key(e)<key(stop))]
 bu='BU01' if start==new[0] or start['element_text'].strip()=='개인정보' else 'BU02'
 occurrences[bu]+=1; eid=f'{bu}-R{occurrences[bu]}'
 candidates.append({'candidate_id':eid,'selected':eid in REPLACE,'start_event_id':ev[0]['event_id'],'end_event_id':ev[-1]['event_id'],'event_count':len(ev),'next_menu_event_id':stop['event_id'] if stop else None})
 if eid not in REPLACE:continue
 endpoint='/api/auth/me' if bu=='BU01' else '/api/schedules'
 assert any(e['api_method']=='GET' and e['api_path']==endpoint and e['api_status_code']=='200' for e in ev)
 assert not any(e['api_method'] and e['api_method'].upper() not in {'GET','HEAD','OPTIONS'} for e in ev)
 assert not any(e['interaction_type'] in {'input','change','submit'} for e in ev)
 assert not any(e['interaction_type']=='click' and e['element_text'].strip() in {'확인','저장','등록'} for e in ev)
 if bu=='BU02':assert any(e['interaction_type']=='popup_open' for e in ev)
 row=dict(execution_id=eid,business_unit_id=bu,repetition=str(occurrences[bu]),source_dataset=NEW,source_session_id=sid,start_event_id=ev[0]['event_id'],end_event_id=ev[-1]['event_id'],start_time=ev[0]['event_time'],end_time=ev[-1]['event_time'],event_count=str(len(ev)),status='COMPLETED',replacement_reason='사용자 요청: 확인/저장 없는 순수 조회 재수집으로 v2 참조 교체',active='true',boundary_source='신규 session의 최초 수집 또는 메뉴 click부터 다음 메뉴 click 직전까지; event ID/time으로 검증',notes='최초 개인정보 화면은 이미 열린 상태에서 수집 시작; 메뉴 click 미관찰. page_close 이후 같은 세션 이벤트가 이어지므로 메뉴 이동 경계 사용.' if start==new[0] else '조회 응답 및 화면/팝업 표시 확인; 확인/저장 및 mutation 요청 미관찰',completion_evidence=json.dumps([{'event_id':e['event_id'],'interaction_type':e['interaction_type'],'method':e['api_method'],'endpoint':e['api_path'],'status':e['api_status_code']} for e in ev if e['api_path'] or e['interaction_type'] in {'page_view','screen_change','popup_open','popup_close'}],ensure_ascii=False))
 replacement[eid]={k:row[k] for k in fields};members[eid]=ev
assert set(replacement)==REPLACE
active=[replacement.get(r['execution_id'],r.copy()) for r in parent]
inactive=[dict(r,active='false',replacement_reason='v3에서 recollection_02 참조로 대체; v2 파일은 변경하지 않음') for r in parent if r['execution_id'] in REPLACE]
parent_index=read(PARENT/'execution_event_index.csv')
for r in active:
 eid=r['execution_id'];ds=r['source_dataset']
 if eid not in REPLACE:
  members[eid]=sorted([byid[ds][i['event_id']] for i in parent_index if i['execution_id']==eid],key=key)
 ev=members[eid]
 assert len(ev)==int(r['event_count'])
 assert ev[0]['event_id']==r['start_event_id'] and ev[-1]['event_id']==r['end_event_id']
 assert ev[0]['event_time']==r['start_time'] and ev[-1]['event_time']==r['end_time']
 interval=[e for e in events[ds] if e['session_id']==r['source_session_id'] and r['start_time']<=e['event_time']<=r['end_time']]
 assert {e['event_id'] for e in interval}=={e['event_id'] for e in ev}
selection=[dict(execution_id=r['execution_id'],source_dataset=r['source_dataset'],source_session_id=e['session_id'],event_id=e['event_id']) for r in active for e in members[r['execution_id']]]
assert len(selection)==len({i['event_id'] for i in selection})
assert len(active)==len({r['execution_id'] for r in active})==60
assert all({r['repetition'] for r in active if r['business_unit_id']==f'BU{b:02}'}=={'1','2','3'} for b in range(1,21))
assert Counter(r['business_unit_id'] for r in active)==dict.fromkeys([f'BU{b:02}' for b in range(1,21)],3)
assert all(r==next(p for p in parent if p['execution_id']==r['execution_id']) for r in active if r['execution_id'] not in REPLACE)
assert sum(r['source_dataset']==OLD for r in active)==55
comparison={}
for eid in ['BU02-R1','BU02-R2','BU02-R3']:
 ev=members[eid]
 checks={
 'schedule_menu':any(e['interaction_type']=='click' and e['element_text'].strip()=='일정 관리' for e in ev),
 'schedule_read_200':any(e['api_method']=='GET' and e['api_path']=='/api/schedules' and e['api_status_code']=='200' for e in ev),
 'detail_popup_open':any(e['interaction_type']=='popup_open' for e in ev),
 'detail_popup_close':any(e['interaction_type']=='popup_close' for e in ev),
 'no_mutation':not any(e['api_method'] and e['api_method'].upper() not in {'GET','HEAD','OPTIONS'} for e in ev)}
 assert all(checks.values())
 comparison[eid]={'checks':checks,'event_count':len(ev),'api_method_counts':dict(Counter(e['api_method'] for e in ev if e['api_method'])),'interaction_sequence':[e['interaction_type'] for e in ev],'additional_next_month_click':any(e['element_text'].strip()=='다음 달' for e in ev)}
used={i['event_id'] for i in selection if i['source_dataset']==NEW}
excluded=[dict(event_id=e['event_id'],source_session_id=e['session_id'],timestamp=e['event_time'],reason='이전 recollection_01 세션의 누적 내보내기; v3 교체 대상 아님' if e['event_id'] in previous_ids else '새 세션의 조직도 조회/상위 메뉴 준비/교체 대상 외 마지막 일정 화면; 선택 실행 경계 밖') for e in events[NEW] if e['event_id'] not in used]
checks=dict(active_execution_count_60=True,each_bu_repetitions_1_2_3=True,five_replacements_reference_recollection_02=True,remaining_55_exactly_unchanged=True,new_five_no_mutation_requests=True,new_five_completed=True,bu02_core_structure_consistent=True,no_active_event_overlap_including_cross_source_ids=True,source_id_time_count_verified=True)
assert before=={str(p.relative_to(ROOT)):sha(p) for p in protected}
checks['original_csv_and_v2_unchanged']=True
write('execution_manifest.csv',active);write('execution_event_index.csv',selection);write('inactive_executions.csv',inactive);write('excluded_recollection_events.csv',excluded)
report=dict(checks=checks,all_pass=True,conclusion='DATASET_READY_FOR_MODEL_PROTOTYPE',active_count=60,active_event_count=len(selection),active_status_counts=dict(Counter(r['status'] for r in active)),replacements=[{k:r[k] for k in ['execution_id','start_time','end_time','event_count','status']} for r in active if r['execution_id'] in REPLACE],recollection_inventory={'total_events':len(events[NEW]),'new_session_events':len(new),'prior_export_events':len(previous_ids & set(byid[NEW])),'selected_events':len(used),'excluded_events':len(excluded)},candidate_boundaries=candidates,bu02_structure_comparison=comparison,limitations=[],source_before_after_sha256=before)
# 보고 문구는 한국어 또는 영어로만 저장합니다.
report['limitations']=['판정 대상은 기록된 통신이며 미수집 통신의 부재까지 증명하지 않음.','BU01-R1 메뉴 click은 미수집. 초기 page_view와 GET 200을 표시 확인 근거로 사용.','BU02-R3만 상세를 닫은 뒤 다음 달 조회가 추가됨. 공통 조회 흐름은 일치.']
dump('validation_report.json',report)
sources={ds:{'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'row_count':len(read(p))} for p in sorted((BASE/ds).glob('*.csv'))]} for ds in [OLD,NEW]}
dump('dataset_manifest.json',dict(dataset_id='current_site_20x3_v3',purpose='DEVELOPMENT',official=False,logical_dataset=True,created_at=datetime.now(timezone.utc).isoformat(),parent_dataset='current_site_20x3_v2',parent_manifest_sha256=sha(PARENT/'dataset_manifest.json'),sources=sources,active_execution_count=60,business_unit_count=20,repetitions_per_business_unit=3,replaced_execution_ids=sorted(REPLACE),event_selection_policy='Source hashes + session + inclusive start/end ID/time; execution_event_index.csv is explicit membership. No row-number boundaries.',mapping_policy='새 세션 개인정보 3회, 일정 상세 2회를 각 BU 내 발생순으로 대응. 기존 BU02-R3 유지.',inactive_policy='이 v3 overlay에서만 이전 5개 참조 비활성화; v2는 불변.',model_input_policy='business_unit_id, repetition, status 및 업무 metadata는 모델 입력에서 제외해야 함.',model_inference_executed=False,model_training_executed=False,quality_status=report['conclusion'],files=[{'path':name,'sha256':sha(OUT/name)} for name in ['execution_manifest.csv','execution_event_index.csv','inactive_executions.csv','excluded_recollection_events.csv','validation_report.json','build_logical_dataset.py']]))
assert before=={str(p.relative_to(ROOT)):sha(p) for p in protected}
print(json.dumps({k:report[k] for k in ['checks','conclusion','active_event_count','active_status_counts','replacements','recollection_inventory']},ensure_ascii=False,indent=2))
