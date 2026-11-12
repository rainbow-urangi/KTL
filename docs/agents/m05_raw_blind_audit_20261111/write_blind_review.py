"""Create a partial semantic review; deliberately do not produce executable GT or a 20-target lock."""
import csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
RAW=ROOT/'data/evaluation/m05_heldout_raw_01'
rows=list(csv.DictReader((RAW/'events.csv').open(encoding='utf-8-sig',newline='')))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def row_sha(row): return hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
# Human semantic judgments fixed independently of predictions. These are partial candidates, not a target dataset.
candidates=[
 (17,'KEEP','', [18,19], '일정 날짜 25 선택 직후 업무 등록 팝업이 열린다. 등록 업무를 시작하는 의미 있는 사용자 동작이다.'),
 (24,'KEEP','', [20,21,22,23,28,30], '일정 제목 필드에 실제 값 변경이 기록되고 뒤이어 등록과 성공 응답이 이어진다.'),
 (28,'KEEP','', [29,30,31,32], '일정 등록 버튼 클릭이다. submit 및 POST 201과 팝업 닫힘으로 완료 의미가 뒷받침된다.'),
 (30,'KEEP','', [28,29,31,32], '일정 생성 API의 POST 201 응답이다. 앞선 등록 행동의 성공 결과를 보존해야 한다.'),
 (48,'KEEP','', [43,47,49,51,52], '일일보고 저장 클릭이며 저장 완료 메시지와 생성 성공 응답이 이어진다.'),
 (69,'KEEP','', [65,66,70,74,78], '주간보고 날짜 선택 팝업에서 2026-11-02를 선택한다. 단순 배경 클릭이 아니라 업무 입력값 결정이다.'),
 (78,'KEEP','', [74,77,79,81,82], '주간보고 저장 클릭이며 저장 완료 메시지와 생성 성공 응답으로 연결된다.'),
 (98,'KEEP','', [95,96,99,103,107], '월간보고 날짜 선택 팝업에서 2026-11-30을 선택한다. 업무 입력값 결정 동작이다.'),
 (170,'KEEP','', [159,161,163,167,169,171,173], '거래처 정보 저장 클릭이며 POST 201과 등록 완료 메시지가 뒤따른다.'),
 (195,'KEEP','', [188,191,192,194,196,198], '자산 정보 저장 클릭이며 POST 201과 등록 완료 메시지가 뒤따른다.'),
 (1,'REMOVE','noise', [2,3,4,5], 'collector_boot는 확장 수집기의 부팅 진단이며 업무 사용자 동작이 아니다. 업무 흐름 정제에서 제외 가능한 명확한 기술 이벤트 후보이다.'),
 (22,'REMOVE','repeated_action', [20,21,23,24], '동일 일정 제목 input과 같은 팝업에서 연속 추가 클릭이다. 앞 클릭 21 이후 129ms에 발생하고 값 변경 없이 다음 클릭이 이어진다. 원본에는 별도 interaction ID가 있어 수집 중복으로 단정하지 않는다.'),
 (23,'REMOVE','repeated_action', [20,21,22,24], '동일 일정 제목 input과 같은 팝업에서 연속 추가 클릭이다. 클릭 22 이후 118ms에 발생하며 실제 제목 change는 24에서 한 번 발생한다. 원본에는 별도 interaction ID가 있어 수집 중복으로 단정하지 않는다.'),
]
fields=['source_position_1based','csv_record_number_including_header','event_id','raw_id','session_id','source_event_sequence','event_time_kst','proposed_label','proposed_remove_category','held_out','held_out_status','label_status','source_file','source_sha256','raw_row_sha256','context_source_positions','rationale']
with (OUT/'partial_label_candidates_NOT_FOR_EVALUATION.csv').open('w',encoding='utf-8',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for pos,label,category,context,reason in candidates:
        row=rows[pos-1]; ec=json.loads(row['locators_json'])['event_context']
        writer.writerow(dict(zip(fields,[pos,pos+1,row['event_id'],row['id'],row['session_id'],ec['event_sequence'],row['event_time'],label,category,'','SUPPORTED_BY_AVAILABLE_HISTORY_NOT_CERTIFIED','PARTIAL_REVIEW_NOT_TARGET_LOCK','data/evaluation/m05_heldout_raw_01/events.csv',sha(RAW/'events.csv'),row_sha(row),' '.join(map(str,context)),reason])))
ambiguous=[
 {'source_positions':[9,10], 'possible_category':'duplicate', 'reason':'GET /api/auth/me가 304ms 간격으로 두 번 나타나지만 서로 다른 transaction/interaction ID와 시각을 가진다. 동일 요청의 이중 수집이라는 증거가 없으며 인증 상태 확인을 임의 noise로 바꾸지 않는다.'},
 {'source_positions':[49,51,79,81,108,110], 'possible_category':'duplicate', 'reason':'각 popup_open/ui_outcome 쌍은 동일 저장 결과를 담지만 전자는 팝업 생명주기와 opener, 후자는 결과 메시지 의미를 담는다. 어떤 표현을 canonical로 유지하는지 사전 평가 정의가 없어 세 건을 쿼터에 맞춰 duplicate로 단정하지 않는다.'},
 {'source_positions':[19,46,54,67,68,84,94,97,122,147,157,175,186,200], 'possible_category':'noise', 'reason':'popup_structure에는 폼 구조·팝업 문맥·관련 API 등 업무 흐름 설명에 필요한 정보가 있을 수 있다. 단순히 보조 이벤트라는 이유로 noise 3건을 채우지 않는다.'},
 {'source_positions':[2,203], 'possible_category':'noise', 'reason':'page_view와 page_close는 세션 시작/종료 문맥이다. 제거 규약 없이 boot와 함께 noise로 묶지 않는다.'},
 {'source_positions':[100], 'possible_category':'irrelevant_action', 'reason':'월간보고 폼 body div 클릭이며 텍스트와 직접 결과가 없다. 다만 focus 이동·입력 전 준비·dismiss 등과 구분할 시나리오/의도 증거가 없어 무관행동으로 확정하지 않는다.'},
 {'source_positions':[178], 'possible_category':'irrelevant_action', 'reason':'거래처 등록 종료 뒤 sidebar panel div 클릭이며 다음에는 자산 관리로 이동한다. 빈 배경 오클릭인지 메뉴 준비 동작인지 원본만으로 확정하지 않는다.'}
]
for item in ambiguous:
    item['events']=[{'source_position_1based':p,'event_id':rows[p-1]['event_id'],'raw_row_sha256':row_sha(rows[p-1])} for p in item['source_positions']]
(OUT/'ambiguous_candidates_NOT_GT.json').write_text(json.dumps(ambiguous,ensure_ascii=False,indent=2)+'\n')
readme='''# M05 새 raw의 prediction-blind 검증 및 라벨링 보류

## 결론

**RAW 검증 통과 / 20-target 라벨링 BLOCKED / prediction 0회.** 원본 CSV를 변경하지 않았다. 엔진 코드·adapter·prediction 파일을 열람하거나 실행하지 않고 실제 이벤트 의미와 인접 문맥만 검토했다.

KEEP 10건은 독립 후보로 선정할 수 있다. 제거 후보는 수집기 boot noise 1건과 동일 필드의 연속 추가 클릭 repeated_action 2건을 기록했다. 그러나 요청한 REMOVE 10건, 특히 duplicate 3 / noise 3 / irrelevant_action 2를 확정할 근거가 부족하다. 수량을 맞추기 위한 재분류나 원본 복제·합성·다른 개발 데이터 혼합은 하지 않았다.

`partial_label_candidates_NOT_FOR_EVALUATION.csv`는 부분 후보 13건이며 실행 가능한 GT도, 완성된 target manifest도 아니다. 각 후보의 ID, 출처 SHA, 원본 record 위치, event_sequence, 문맥 위치, 판단 근거를 기록했다. held_out boolean은 의도적으로 비워 두었고, 가용 이력의 분리 근거와 완전한 과거 미사용 인증을 구분했다. 이 파일을 모델 입력 또는 점수 산출에 사용하면 안 된다.

## Raw 검증

- events 203 / tasks 152 / sessions 1. CSV 구조, PK 및 FK, 203개 JSON payload, event ID, source sequence 1–203, session envelope 및 task duration이 일치한다.
- 수집 시각은 2026-11-11 21:09:46.818–21:12:16.348 KST. payload의 UTC 시각·epoch 및 서버 received_at이 이를 뒷받침하며, 전달받은 동결 기준 2026-11-09 10:56:51 KST 이후다.
- 원본 sequence에는 비동기 API event 시각이 앞 record보다 6ms/6ms/4ms 이른 세 곳이 있다. 잘못된 CSV가 아니라 소스 기록 순서와 timestamp 정렬 차이로 기록했고 원본 순서를 보존했다. 추론 전에 묵시적으로 재정렬하지 말아야 한다.
- `data/**/*.csv` 중 event ID/이벤트를 가진 기존 파일 15개를 inventory로 보관했다. 실제 event 원본 12개, 총 34,553 rows와 reference index 3개에서 event ID·session ID·canonical raw row·id/event_id 제외 raw content 일치는 0이다.
- raw content hash는 nested source IDs/timestamps를 보존한다. 이는 모델에 실제 전달되는 feature-content hash 비중복 검사의 대체물이 아니다. external/deleted history까지 확인했다는 주장도 하지 않는다.

## 라벨링을 멈춘 이유

- 동일 제목 input의 빠른 클릭은 별도의 interaction ID를 가진 사용자 반복 동작이다. 이를 duplicate와 repeated_action으로 임의 분할하여 쿼터를 채우지 않았다.
- 저장 결과의 popup_open / ui_outcome은 문자열이 유사해도 팝업 수명주기와 결과 메시지라는 서로 다른 의미를 제공한다. 사전 canonical 보존 규약 없이 duplicate 3건으로 고르지 않았다.
- popup_structure 및 인증 API를 단순 기술 이벤트라는 이유만으로 noise로 확정하지 않았다. 업무 문맥·인증 확인·후속 API 관계를 지닐 수 있다.
- 빈 폼 div 클릭(#100)과 sidebar div 클릭(#178)은 무관행동 후보지만, focus/dismiss/메뉴 준비 동작과 구분할 근거가 없다. 사용자는 별도 수집 시나리오나 무관행동 정의를 제공하지 않았다고 부모 작업에서 확인했다.

## 후속 조건

1. 모델 prediction을 보기 전에 수집자가 해당 행동의 업무 목적과 어떤 기록을 중복으로 처리할지 설명하거나, 명확한 제거 사례를 포함한 새로운 독립 raw를 제공해야 한다.
2. 새 수집이 필요하면 원본 이벤트를 복제/변조하지 않고 실제 행동을 수집한다. 추가 수집 전 라벨 의미를 정하고 그 이력을 남긴다.
3. 유효한 20개 target이 확정되어야 ID/category/provenance/sequence 위치와 dataset/labels SHA를 lock할 수 있다. 현재는 20-target lock을 만들지 않았다.
4. 이력 completeness와 실제 추론 feature hash를 독립 확인한 뒤에만 frozen 엔진을 1회 일괄 실행한다.

## 산출물

- `raw_validation.json`: 원본 해시·schema·세션·시간·분리 검증 결과.
- `history_inventory.json`: 기존 event 원본/reference inventory 및 파일별 해시·중복 대조.
- `partial_label_candidates_NOT_FOR_EVALUATION.csv`: 확정 GT가 아닌 독립 부분 후보 13건.
- `ambiguous_candidates_NOT_GT.json`: 보류한 category 후보와 의미적 근거 부족.
- `audit_snapshot_pre_prediction.json`: 위 감사 산출물의 사전 SHA snapshot. **target lock 아님.**
- `validate_raw.py`, `write_blind_review.py`: 재현 가능한 감사 도구. 모델을 import/호출하지 않는다.
'''
(OUT/'README.md').write_text(readme)
snapshot={'status':'BLOCKED_LABEL_EVIDENCE_INSUFFICIENT','target_count_locked':0,'partial_candidate_count':len(candidates),'candidate_counts':{'KEEP':10,'REMOVE':3,'noise':1,'repeated_action':2},'required_target_counts':{'KEEP':10,'REMOVE':10,'duplicate':3,'noise':3,'repeated_action':2,'irrelevant_action':2},'prediction_runs':0,'prediction_seen':False,'created_at_utc':datetime.now(timezone.utc).isoformat(),'artifacts':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='audit_snapshot_pre_prediction.json'},'raw_files':{p.name:sha(p) for p in sorted(RAW.iterdir()) if p.is_file()},'note':'Evidence snapshot only, not a target lock. Do not score partial or ambiguous candidates. A complete held-out nonuse claim is not certified.'}
(OUT/'audit_snapshot_pre_prediction.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(snapshot,ensure_ascii=False,indent=2))
print('snapshot_sha256',sha(OUT/'audit_snapshot_pre_prediction.json'))
