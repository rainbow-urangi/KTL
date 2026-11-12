# M05 raw_01 + raw_02 prediction-blind 추가 감사

## 결론

**원본 구조 검증 통과 / 20-target 확정 BLOCKED / cleaning prediction 실행 0회.**

raw_01의 기존 후보 13건을 동일 ID·label·category·근거로 보존했고, raw_02의 collector_boot 1건만 noise 후보로 추가했다. 현재 KEEP 10 / REMOVE 4 (noise 2, repeated_action 2)이다. 요청 구성에서 duplicate 3 / noise 1 / irrelevant_action 2가 부족하다. 애매한 이벤트를 수량에 맞춰 재분류하지 않았다.

이는 최종 GT 또는 실행 가능한 target manifest가 아니다. held_out 필드는 비워 두었으며 최종 target lock을 생성하지 않았다. 엔진·adapter·prediction 파일을 열람하거나 실행하지 않았다.

## 수집 의도 근거의 정정

사용자의 최신 확인에 따르면 **raw_02 수집 당시 별도 메모 파일은 작성하지 않았다.** 사용자는 cleaning prediction 실행 전에, duplicate 3건 목적의 반복 동작, 약 2건 이상의 추가 noise, 2건의 업무 무관 동작을 의도했다고 회상했다. repeated_action은 기존 raw_01 후보를 우선한다.

이 근거는 **수집 후 작성된 사용자 회상 기록**이다. 사전 작성 메모 또는 timestamp가 있는 사전 category 정의로 표현하지 않는다. 이전의 별도 사전 메모 주장보다 이 정정을 우선한다. category 목적은 확인됐으나 특정 event ID 또는 canonical 보존 규약은 제공되지 않았다.

## 원본 검증

- raw_01: events 203 / tasks 152 / sessions 1.
- raw_02: events 147 / tasks 104 / sessions 1.
- 합계 350개 event ID 모두 고유하며, 원본 PK/FK, JSON payload의 ID·세션·UTC/KST·epoch, source sequence, task duration, session envelope 검증에 오류가 없었다.
- 각 세션의 source sequence는 1–203, 1–147로 연속한다. 모든 interaction ID 및 실제 API request ID도 세션 안에서 고유하다.
- raw_02 수집시각은 2026-11-11 21:36:45.064–21:38:29.307 KST. 두 raw 모두 전달받은 엔진 동결 기준 2026-11-09 10:56:51 KST 이후다. 이 labeler는 엔진 manifest를 직접 열람하지 않았다.
- raw_01 #51→52, #81→82, #110→111과 raw_02 #141→142에서 API 종료시각이 앞 source record보다 수 ms 빠르다. 원본 순서를 바꾸지 않았다.
- raw_01 마지막 row와 raw_02 첫 row는 다른 page/browser session이며 같은 install_id·tab 및 actor workflow 연속성이 남아 있다. raw_02의 첫 step_duration_ms=1,468,716은 두 세션 사이 실제 gap을 반영한다. 임의 초기화·재정렬·원본 가공은 하지 않았다.
- 원본 6개 CSV와 기존 감사 폴더의 모든 파일은 감사 전후 SHA가 동일하다.

## 보존·추가한 후보

기존 raw_01 13개 row는 원본 row SHA와 기존 후보를 다시 대조했고 동일한 label·category를 유지했다. raw_01 전체 203개 이벤트와 raw_02 전체 147개 이벤트의 세션 흐름을 검토했다.

추가 후보:
- raw_02 source position 1, event_id 8e08307c-5f51-44ae-b078-b126a3b8a3a7.
- REMOVE / noise. collector_boot는 확장 수집기 시작 진단이며 입력·API context가 비어 있고 실제 로그인은 후속 행위에서 시작한다.
- 해당 원본 row/hash와 인접 #2–8의 문맥을 후보 CSV에 기록했다.

## 확정하지 않은 이유

- **duplicate:** #9/#10은 같은 인증 API지만 request_id와 요청시각이 다른 실제 호출이고 응답 body는 수집되지 않았다. #139/#141/#144는 같은 결과 팝업의 lifecycle/outcome/구조 snapshot으로 의미가 다르다. 어떤 기록을 canonical로 남길지 사전 규약이 없다.
- **duplicate와 repeated_action 구별:** #42/#52/#71 메뉴 재선택, #107/#108 제목 필드 추가 클릭은 서로 다른 interaction ID를 가진 사용자 동작이다. 반복 생성 의도를 인정하더라도 수집 중복으로 단정하지 않는다.
- **다른 업무 객체:** 일정 상세 확인은 schedule ID 16/18/28/32에 별도 PATCH를 일으킨다. 여러 확인 동작을 같은 사건의 복제로 취급하지 않았다.
- **추가 noise:** page_close는 visibilitychange_hidden이라는 경계 정보를 가진다. popup_structure는 화면/폼/결과 구조를 담는다. 기술 이벤트라는 이유만으로 제거하지 않는다.
- **irrelevant_action:** 일일보고 사이의 명함 관리 이동(#59/#89/#114), 보고서 열기·닫기·중단은 시험상 우회일 수 있다. 그러나 사용자가 회상한 무관행동 2건과 특정 이벤트의 대응이 없고 조회·취소라는 실제 업무 의미도 있어 확정하지 않았다.

## held-out 근거의 범위

가용 data/**/*.csv inventory 15개(원본 event rows 34,553건 및 event reference index 포함)와 비교했다. raw_01/raw_02의 event ID, session ID, canonical raw row, id/event_id 제외 raw content의 일치는 0이다. 두 신규 raw를 과거 이력에서 제외하고 서로 간의 ID 고유성은 별도로 확인했다.

이 결과는 외부·삭제된 학습/개발 이력까지 포함한 과거 미사용 인증이 아니다. nested ID·timestamp를 보존한 raw-content hash는 실제 추론 feature-content hash가 아니다. 해당 검사는 모델을 보지 않는 labeler가 수행하지 않았다. 따라서 held_out=true를 선언하지 않았다.

## 동결·재현·산출물

- audit_raws.py: 표준 라이브러리만 사용하는 독립 감사. 모델·adapter·evaluator import 없음.
- raw_validation.json: 6개 원본 hash, 구조·시간·분리·무변경 검증 및 최신 사후 회상 근거.
- history_inventory.json: 가용 이력 file SHA와 중복 대조.
- partial_label_candidates_NOT_FOR_EVALUATION.csv: raw_01 13개 + raw_02 1개 부분후보. 평가 실행 금지.
- ambiguous_candidates_NOT_GT.json: 보류 candidate의 실제 ID·원본 위치·근거.
- raw_context_index.json: 원본 350개 event의 위치/순서/row SHA 인덱스. label을 모델에 전달하는 파일이 아니다.
- audit_snapshot_pre_prediction.json: 이번 감사 산출물 및 원본의 사전 hash snapshot. **최종 target lock 아님.**

최종20 확정과 미사용 감사 완료 전에는 prediction을 실행하지 않는다. 추가 확인이 이루어지더라도 이 감사 snapshot은 보존하고 새 버전으로 기록한다. 이번 변경은 감사 문서/스크립트만 추가했으며 backend·모델·compliance·기존 평가자료는 수정하지 않았다.
