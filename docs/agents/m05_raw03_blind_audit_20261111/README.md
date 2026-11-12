# M05 raw03 prediction-blind 독립 감사

## 결론

**BLOCKED_ADDITIONAL_REMOVE_EVIDENCE_REQUIRED. 기존 KEEP 10 / REMOVE 8, 총18건을 그대로 유지한다. raw03에서 객관적으로 확정한 추가 REMOVE는 0건이며 2건이 부족하다. target20 lock과 prediction/점수는 만들지 않았다.**

67개 event의 원래 순서, 1개 session과 업무 등록 2회의 전후 문맥을 확인했다. 두 등록은 POST /api/schedules 201로 성공했다. 저장 성공과 재클릭의 제거 가능성은 별도 판단이다.

## 판단 근거

- 첫 제목: focus22 뒤 click23~27, change28이다. click26/27은 166/167ms 연속 클릭이지만 value=null이고 selection이 없다. change28은 입력 시작 시점을 보장하지 않는다. 뒤이어 같은 문자열이 내용에 paste30되므로 제목 선택/복사 가능성을 배제하지 않는다.
- 첫 내용: paste30이 click31~34보다 먼저다. focus36→click37→paste38만 떼면 반복 후보처럼 보이지만, 앞선 paste30과 후행 paste38 모두 직전 빈 값을 기록한다. 미기록 삭제/선택 또는 첫 paste 취소 여부가 없어 click37 당시 빈 값인지 확정할 수 없다. click37을 잠정 검토했으나 최종 채택하지 않았다.
- 두 번째 제목: paste52 뒤 click53~55, 수정 값 change56이다. 빈 필드 재클릭으로 판정하지 않는다.
- 두 번째 폼의 click51/59는 다른 필드를 거쳐 돌아온 focus다. 입력을 위한 필드 재진입을 제거하지 않는다.
- 모호한 후보는 KEEP 정답으로 바꾼 것이 아니라 미확정이다. category 수나 20건에 맞추어 label을 만들지 않았다.

raw source position은 헤더 제외 1부터이며 csv record는 그 값에 1을 더한다. 상세 event ID, raw ID, session, popup, target signature/hash, KST/UTC 시각, 값/selection, 앞뒤 보존 문맥은 raw_context_index.json과 ambiguous_candidates_NOT_GT.json에 있다.

## 무결성과 held-out 범위

기존 감사 및 18행 CSV의 hash를 재확인했고 partial CSV는 byte-identical 복사본이다. 원본 CSV, 과거 감사, 모델, 엔진, adapter, 평가 계약을 변경하지 않았다. 기존 15개 학습/개발 source/index와 raw01/02, 총17개 파일에 대해 event ID/session/raw row/id-excluded raw content 중복을 비교했다. 실제 결과와 원본 해시는 raw_validation.json 및 history_inventory.json을 따른다.

수집 시각은 기존 감사의 freeze cutoff 2026-11-09 10:56:51 KST 이후다. 이 cutoff의 현재 엔진 메타데이터 재검증은 별도이며 이 labeler는 엔진/adapter/prediction을 읽거나 실행하지 않았다.

외부·삭제·미기록 학습/개발 이력이나 실제 inference feature-content의 미중복은 인증하지 않는다. raw content hash에는 nested ID/time이 남아 있으므로 feature hash가 아니다. held_out 필드는 비워 두고 공식/완전한 미사용을 주장하지 않는다.

## 다음 증거

기존 녹화나 동시 기록된 전후 value/selection 증거가 있으면 event ID와 대조할 수 있다. 없으면 선행 paste가 없는 새 빈 필드에서 최초 focus를 보존하고 추가 클릭 뒤 바로 paste하되, paste 직전 value='' 및 selection 0..0, 실제 입력/저장까지 기록하는 새 수집이 필요하다. 두 건 확보를 미리 보장하지 않는다. 누락 증거를 원본에 사후 삽입하지 않는다.

## 검증

python3 docs/agents/m05_raw03_blind_audit_20261111/verify_audit.py

backend나 평가 구현을 수정하지 않았으므로 backend 전체 unit test는 실행하지 않았다. 이 검증은 raw integrity, history overlap, 기존18행/원본/산출물 hash 및 prediction 미생성 상태만 확인한다.
