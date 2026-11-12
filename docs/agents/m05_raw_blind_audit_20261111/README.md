# M05 새 raw의 prediction-blind 검증 및 라벨링 보류

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
