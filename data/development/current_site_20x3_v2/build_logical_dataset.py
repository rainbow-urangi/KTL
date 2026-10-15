"""원본 불변 논리 dataset 구성. 행 번호 대신 event ID/session/time과 관찰 전환 사용."""
import csv,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
OLD='current_site_20x3_v1';NEW='current_site_recollection_01'
prior=ROOT/'results/development/current_site_20x3_v1_profile/execution_manifest.csv'
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dt(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def write(name,data):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
protected=[p for d in [ROOT/'data/development'/OLD,ROOT/'data/development'/NEW,prior.parent] for p in d.rglob('*') if p.is_file()]
before={str(p.relative_to(ROOT)):sha(p) for p in protected}
sources={};events={}
for ds in [OLD,NEW]:
 base=ROOT/'data/development'/ds
 sources[ds]={'directory':str(base.relative_to(ROOT)),'files':[{ 'path':str(p.relative_to(ROOT)), 'sha256':sha(p),'row_count':len(read(p))} for p in sorted(base.glob('*.csv'))]}
 events[ds]=read(base/'events.csv')
 assert len({e['event_id'] for e in events[ds]})==len(events[ds])
 sessions={s.get('session_id',s.get('id')) for s in read(base/'sessions.csv')}
 tasks={t['id']:t for t in read(base/'tasks.csv')}
 assert all(e['session_id'] in sessions and e['task_id'] in tasks and tasks[e['task_id']]['session_id']==e['session_id'] for e in events[ds])
def resolve(ds,sid,startid,endid,start,end):
 byid={e['event_id']:e for e in events[ds]}
 a,b=byid[startid],byid[endid]
 assert a['session_id']==b['session_id']==sid
 assert a['event_time']==start and b['event_time']==end
 result=sorted((e for e in events[ds] if e['session_id']==sid and dt(start)<=dt(e['event_time'])<=dt(end)),key=lambda e:(dt(e['event_time']),e['event_id']))
 assert startid in {e['event_id'] for e in result} and endid in {e['event_id'] for e in result}
 return result
oldrows=read(prior);assert len(oldrows)==60
for x in oldrows:
 ev=resolve(OLD,x['session_id'],x['start_event_id'],x['end_event_id'],x['start_time'],x['end_time'])
 assert len(ev)==int(x['event_count']),x['execution_id']
# 화면 재진입 메뉴를 경계로 삼습니다. 초기 수집은 이미 개인정보 화면에서 시작합니다.
new=sorted(events[NEW],key=lambda e:(dt(e['event_time']),e['event_id']))
startmarkers=[e for e in new if e['interaction_type']=='click' and e['element_text'].strip() in ['개인정보','일정 관리']]
assert new[0]['page_url'].endswith('/mypage/personal-info')
starts=[new[0]]+startmarkers
occurrences=Counter();candidates=[]
for index,a in enumerate(starts):
 stop=dt(starts[index+1]['event_time']) if index+1<len(starts) else None
 ev=[e for e in new if e['session_id']==a['session_id'] and dt(e['event_time'])>=dt(a['event_time']) and (stop is None or dt(e['event_time'])<stop)]
 # 다음 개인정보 진입을 준비하는 상위 메뉴 click과 page_close는 해당 조회에 넣지 않습니다.
 ev=[e for e in ev if e['interaction_type']!='page_close' and not(e['interaction_type']=='click' and e['element_text'].strip()=='일반 정보')]
 bu='BU01' if a==new[0] or a['element_text'].strip()=='개인정보' else 'BU02'
 occurrences[bu]+=1
 endpoint='/api/auth/me' if bu=='BU01' else '/api/schedules'
 assert any(e['api_method']=='GET' and e['api_path']==endpoint and e['api_status_code']=='200' for e in ev)
 if bu=='BU02':assert any(e['interaction_type']=='popup_open' and e['element_text']=='업무 내용' for e in ev)
 a,b=ev[0],ev[-1]
 ev=resolve(NEW,a['session_id'],a['event_id'],b['event_id'],a['event_time'],b['event_time'])
 writes=[e for e in ev if e['api_method'] in ['POST','PATCH','PUT','DELETE']]
 candidates.append(dict(execution_id=f'{bu}-R{occurrences[bu]}',business_unit_id=bu,repetition=str(occurrences[bu]),source_dataset=NEW,source_session_id=a['session_id'],start_event_id=a['event_id'],end_event_id=b['event_id'],start_time=a['event_time'],end_time=b['event_time'],event_count=str(len(ev)),status='PARTIAL' if writes else 'COMPLETED',replacement_reason='사용자 지정 재수집 교체; 원본 v1 조회에 저장 동작 혼입',active='true',boundary_source='session/time + initial collector or menu click; next menu boundary; no row indices',notes='조회 중 쓰기 요청 잔존: '+','.join(e['api_method']+' '+e['api_path'] for e in writes) if writes else '조회 성공 근거 확인',completion_evidence=json.dumps([{'event_id':e['event_id'],'method':e['api_method'],'endpoint':e['api_path'],'status':e['api_status_code']} for e in ev if e['api_path']],ensure_ascii=False)))
assert occurrences=={'BU01':3,'BU02':3}
replace={'BU01-R1','BU01-R2','BU01-R3','BU02-R1','BU02-R2'}
lookup={x['execution_id']:x for x in candidates if x['execution_id'] in replace}
assert set(lookup)==replace
active=[];inactive=[]
for x in oldrows:
 row={k:x[k] for k in ['execution_id','business_unit_id','repetition','start_event_id','end_event_id','start_time','end_time','event_count','status']}
 row.update(source_dataset=OLD,source_session_id=x['session_id'],replacement_reason='',active='true',boundary_source='unchanged prior execution_manifest event IDs and times',notes=x.get('notes',''),completion_evidence=x.get('completion_evidence',''))
 if x['execution_id'] in replace:
  row.update(active='false',replacement_reason='v2에서 recollection_01 동일 execution ID로 대체; v1 원본 및 기존 분석은 변경하지 않음')
  inactive.append(row);active.append(lookup[x['execution_id']])
 else:active.append(row)
# 열 순서를 고정하되 데이터 범위를 행 번호로 결정하지 않습니다.
fields=['execution_id','business_unit_id','repetition','source_dataset','source_session_id','start_event_id','end_event_id','start_time','end_time','event_count','status','replacement_reason','active','boundary_source','notes','completion_evidence']
active=[{k:x[k] for k in fields} for x in active];inactive=[{k:x[k] for k in fields} for x in inactive]
unused=[dict(x,active='false',replacement_reason='BU02-R3는 사용자 교체 대상 아님; 기존 v1 BU02-R3 유지') for x in candidates if x['execution_id'] not in replace]
assert len(active)==len({x['execution_id'] for x in active})==60
assert Counter(x['business_unit_id'] for x in active)==dict.fromkeys([f'BU{i:02}' for i in range(1,21)],3)
assert all({x['repetition'] for x in active if x['business_unit_id']==f'BU{i:02}'}=={'1','2','3'} for i in range(1,21))
assert {x['execution_id'] for x in active if x['source_dataset']==NEW}==replace
assert sum(x['source_dataset']==OLD for x in active)==55
selected=set();selection=[]
for x in active:
 ev=resolve(x['source_dataset'],x['source_session_id'],x['start_event_id'],x['end_event_id'],x['start_time'],x['end_time'])
 assert len(ev)==int(x['event_count'])
 for e in ev:
  key=(x['source_dataset'],e['event_id']);assert key not in selected;selected.add(key)
  selection.append(dict(execution_id=x['execution_id'],source_dataset=x['source_dataset'],source_session_id=e['session_id'],event_id=e['event_id']))
for x in active:
 if x['source_dataset']==OLD:
  original=next(t for t in oldrows if t['execution_id']==x['execution_id'])
  assert all(original[k]==x[k] for k in ['business_unit_id','repetition','start_event_id','end_event_id','start_time','end_time','event_count','status'])
assert before=={str(p.relative_to(ROOT)):sha(p) for p in protected}
write('execution_manifest.csv',active);write('inactive_executions.csv',inactive);write('unused_recollection_executions.csv',unused);write('execution_event_index.csv',selection)
checks={'active_execution_count_60':len(active)==60,'each_business_repetitions_1_2_3':True,'five_replacements_reference_new_source':True,'remaining_55_unchanged_v1_references':True,'source_id_time_count_verified':True,'no_active_event_overlap':True,'original_files_unchanged':True}
dump('validation_report.json',dict(checks=checks,all_pass=all(checks.values()),active_count=60,inactive_v1_count=5,unused_recollection_execution_count=len(unused),active_event_count=len(selection),active_status_counts=dict(Counter(x['status'] for x in active)),source_before_after_sha256=before,quality_notice='Structural replacement PASS does not mean recollection quality is corrected; five replacements remain PARTIAL'))
dump('dataset_manifest.json',dict(dataset_id='current_site_20x3_v2',purpose='DEVELOPMENT',dataset_role='WORKFLOW_MODEL_DEVELOPMENT',official=False,synthetic=False,logical_dataset=True,created_at=datetime.now(timezone.utc).isoformat(),sources=sources,parent_execution_manifest={'path':str(prior.relative_to(ROOT)),'sha256':sha(prior)},active_execution_count=60,business_unit_count=20,repetitions_per_business_unit=3,replaced_execution_ids=sorted(replace),mapping_policy='Chronological occurrence within each observed business: personal-info first three; schedule first two. Third schedule recollection unused, original BU02-R3 retained.',event_selection_policy='source dataset + session + inclusive timestamp interval; endpoints must resolve to exact event IDs/times; explicit execution_event_index is authoritative membership, bound to source hashes',ordering_notice='execution_id repetition is logical identity, not global chronological order; preserve source timestamps, do not concatenate across source sessions',inactive_policy='Only inactive_executions.csv in this v2 overlay deactivates five v1 references; original v1 remains immutable',quality_status='55 COMPLETED / 5 PARTIAL; recollected views still contain PATCH',model_inference_executed=False,files=[dict(path=n,sha256=sha(OUT/n)) for n in ['execution_manifest.csv','inactive_executions.csv','unused_recollection_executions.csv','execution_event_index.csv','validation_report.json','build_logical_dataset.py']]))
print(json.dumps({'checks':checks,'active_status_counts':dict(Counter(x['status'] for x in active)),'replacements':[{k:x[k] for k in ['execution_id','start_time','end_time','event_count','status']} for x in active if x['source_dataset']==NEW]},ensure_ascii=False,indent=2))
