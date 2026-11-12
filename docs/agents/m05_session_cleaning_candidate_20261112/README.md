# M05 generic cleaning 개선 DEVELOPMENT 후보

## 결과

- TP 7 / FP 0 / FN 3 / TN 10
- Precision 1.00 / Recall 0.70 / F1 0.8235294117647058 ≥ 0.79
- 전체 원문맥 417행 → prediction 417개 → 원래 target20만 계산. context397 분모 제외.
- KEEP10 모두 보존. 전체 prediction은 KEEP409/REMOVE8(비평가 context의 collector_boot 1건 포함).
- 후보 목표 충족으로 추가 rule 확대/tuning 중단. Independent Verification 후 freeze 대기.
- 원본·기존 잠금 GT·기존 baseline/engine/config 등 보호78파일 SHA-256 전후 일치.

## 변경 범위와 원인

`fn10_audit.csv`는 10개 FN 전체의 ID/GT사유/raw activity/page/target/session/task/case크기/기존 규칙 통과 이유/적용가능 generic 규칙/앞뒤 이벤트/원본 CSV와 hash를 포함한다.

기존 `rle_dedupe_rows`는 case_id 내부에서만 비교한다. 원래 case는 task에서 만들어지며 FN repeated8 모두 case 크기1이다. 원래 case를 재작성하지 않고 별도 원본 session chronological context를 새 후보에 추가했다.

- noise2: `collector_boot` + html + API/outcome 없음으로 복구.
- repeated5: 명시적 빈 pre-paste value/selection0..0에 연결된 같은 field focus 반복2, 이미 현재 목적지에 머무르는 메뉴 재선택3.
- FN3 유지: `215fe929-63e1-46d5-9c31-e7008b403fbd`, `885531a6-3cb7-4ac9-9035-86160605f408`, `2acf909a-1edc-4e9e-b576-e78d2a317d4e`. raw click value=null/selection 미기록, 바로 다음 입력의 명시적 빈 pre-state도 없음. GT REMOVE는 변경하지 않되 null을 빈 값으로 취급하지 않아서 candidate는 KEEP. 사용자 회상/GT를 engine features로 주입하지 않았다.

## 검증

- 합성 신규17 테스트 PASS: session/task scope, page/target/popup 분리, 입력 mutation/selection/unknown state, 긴 간격, checkbox/button 보호, navigation refresh/route/API/popup 보호, 첫 메뉴 보존, deterministic/입력 불변/GT key 거부/정렬.
- repository 전체 `python3 -m unittest discover -s tests -v`: 439 PASS.
- 후보 웹 `python3 -m backend.m05_session_candidate_web` : `http://127.0.0.1:8769`.
- 실제 HTTP `/measure` 1회, `/validate` 저장 결과 재조회 일치, target20 evidence CSV 다운로드 원바이트 SHA 일치, 독립 CSV 산식 재계산 PASS.
- 초기 다운로드는 기존 공통 웹 read_text의 CRLF→LF 변환으로 바이트가 달랐다. 값은 동일했다. 후보 웹만 read_bytes().decode로 수정해 원바이트 일치를 확인했다. engine/score는 재실행 또는 변경하지 않았다.
- 실제 브라우저 버튼 클릭 검증은 수행하지 않음. HTTP 검증을 실브라우저 PASS로 표현하지 않는다.

## 파일 / rollback

- 기존 `backend/m05_baseline_adapter.py`, `evaluation_contracts/m05_engine.json`, baseline frozen manifest 및 원본 dataset.py 변경 없음.
- 신규 후보 `backend/m05_session_cleaning.py`, `backend/m05_session_candidate.py`, `backend/m05_session_candidate_web.py`.
- 신규 후보 config `evaluation_contracts/development/m05_session_cleaning_candidate/`.
- 결과 `results/development/m05_full_context/538f253c49816ede31831e052e8e42519c9c26768e130e096f925f0474e0a7bf/`.
- rollback은 신규 후보 웹을 사용하지 않고 기존 baseline 서비스를 사용하는 것. 기존 결과와 파일 삭제 불필요.
- `candidate_pre_measurement.json`의 웹 hash는 CSV 전달 수정 전 버전이다. 최종 `implementation_hashes.json`이 현재 웹 hash. engine/runner/rules/config는 최초 prediction 전 hash 그대로다.

## 한계

이는 같은 데이터로 개선한 DEVELOPMENT 결과이며 새 held-out/KTL 공식 성적이 아니다. 원래 engine은 ML classifier가 아닌 deterministic rules이다. 메뉴 목적지 연결은 인접 click→route의 관측 관계로만 사용하며 실제 causal ID를 만들어내지 않는다. 수집에 없는 UI side effect나 다음 동작 이후의 지연 응답은 이 규칙의 보장 범위가 아니며 새 환경 적용은 별도 확인이 필요하다. 무조건 session RLE로 확대하지 않았고 점수 충족 뒤 FN3을 줄이기 위한 추가 예외를 만들지 않았다.

## 독립 검증 후 재현용 동결

부모가 전달한 별도 Verification Task 결과는 현재 측정 PASS이다. 단 current click의 has_api=True를 반복 제거 규칙이 일괄 차단하지 않는 generic 안전성 제한이 발견되었다. 이번 REMOVE8에는 해당하지 않는다는 독립 검증 보고를 기록한다. 별도 repository 검증 보고서는 제공되지 않았으며 존재를 주장하지 않는다.

코드/규칙 수정이나 재측정 없이 `evaluation_contracts/development/m05_session_cleaning_frozen_v2/freeze.json`에 정확한 DEVELOPMENT 재현용 hash를 동결했다. 공식 시험 준비 완료/새 데이터에서의 안전성 PASS로 해석하지 않는다. baseline freeze/원본/GT는 그대로 유지한다. 후속 변경에는 별도 승인이 필요하다.
