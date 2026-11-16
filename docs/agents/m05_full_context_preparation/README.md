# M05 full-context / target-20 준비 계약

상태: **WAITING_FOR_HELDOUT_RAW_COLLECTION**. DEVELOPMENT만 해당. 코드·정제 rule·adapter·활성 config 변경 없음. 새 raw/GT/prediction/F1은 생성하지 않았다. 이 문서와 header-only CSV는 설계·수집 준비 자료이며 실행 가능한 새 validator 또는 웹 지원 구현이 아니다.

## 조사 및 현재 지원 범위

- `data/` 전체 및 저장소/인접 AI-model의 event/export 후보를 확인했다. `data/held_out`은 없고, 기존 source CSV 12개는 모두 training/development 이력이다. 최신 raw는 `m02_recovery_data_05`의 2026-11-08 22:26:05.323(원문 timestamp, timezone 미포함)이다. 새 수집 근거가 없는 기존 자료는 전부 제외한다. 파일 mtime을 수집 시각 증거로 사용하지 않는다.
- 엔진 동결 기준: `evaluation_contracts/development/m05_baseline_frozen_v1/freeze.json`, 2026-11-09T01:56:51.019524+00:00 (=2026-11-09 10:56:51.019524 Asia/Seoul). 원본 freeze와 모든 immutable artifact 및 active engine config hash 재확인 PASS. 상세 `preparation_audit.json`.
- 기존 `backend/m05_baseline_adapter.py::predict`는 길이 20 제한 없이 전체 context를 받는다. case별 기존 정렬/RLE를 유지하고 모든 입력 event의 KEEP/REMOVE 및 provenance를 반환한다. GT 전달은 금지되어 있다.
- 기존 `backend/m05_heldout.py::evaluate`는 validate_dataset 결과 20개만 엔진에 전달한다. 그러므로 현재 웹/evaluate 경로는 이번 full-context 요구를 충족하지 않는다. 현재 경로로 20 target만 실행하지 않는다.
- 기존 `calculate`는 정확히 20 predictions의 ID를 검증하고 중앙 F1 계산을 할 수 있다. 새 orchestration/validator/schema 연결은 새 raw 확보 후 준비해야 하며, 이번에는 구현하지 않는다. 기존 adapter/cleaning behavior는 이후에도 변경하지 않는다. evaluator가 freeze immutable 목록에 있으므로 원본을 덮어쓰지 않고 별도 평가 orchestration을 추가하는 방식이 최소 범위다.

## 준비된 처리 계약 (아직 미구현)

1. full raw sequence와 sessions/tasks 및 collection manifest의 원본을 hash로 봉인한다. 완전한 수집 세션/업무 case의 경계와 종료 근거를 보관한다. target 선택 전에 context 범위를 고정한다. target 이외 event도 삭제/필터링/샘플링하지 않는다.
2. 독립 라벨러가 raw 의미와 업무 목적만으로 target 20개 및 라벨을 정한다. engine prediction을 실행하거나 보여주기 전에 target selection 및 labels hash를 timestamp와 함께 잠근다. labeler와 verification reviewer를 구분한다. 예측 조회 이력/실행 log 및 사람 확인을 보관한다. 단순 `prediction_blind=true` 선언만으로 독립성을 증명하지 않는다.
3. 기존 frozen CSV normalization 및 column mapping을 그대로 사용해 full input을 만든다. raw ID/session/case/record 위치에서 normalized `id, features`까지 1:1 매핑을 기록한다. CSVCaseAdapter의 min-length/max-length batching/truncation 경로는 사용하지 않는다. 정규화에서 activity가 파생되더라도 기존 함수 그대로이며 GT/category로 값을 보정하지 않는다.
4. adapter에는 오직 `{events: [{id, features: {case_id, activity, ts}}, ...]}`를 보낸다. expected_label/category/target 여부/held_out/라벨 근거는 포함하지 않는다. full sequence 전체를 1회 batch로 처리하고 기존 case grouping과 timestamp/tie-break 정렬을 유지한다. 서로 다른 session의 case ID 충돌을 자동 병합하거나 ID를 임의 재작성하지 말고, 충돌 시 BLOCKED로 검토한다.
5. 반환 prediction ID 집합이 full input ID 집합과 정확히 같은지 확인한다. 누락/중복/추가/잘못된 label은 BLOCKED. full predictions를 봉인한 뒤 별도 target manifest와 event_id로 join해 정확히 20개만 추출한다. context prediction은 감사용으로 남기되 점수 rows/분모에서 제외한다.
6. 중앙 계산기에서 target GT와 prediction으로 TP/FP/FN/TN, Precision/Recall/F1을 계산한다. GT REMOVE가 양성이다. P=TP/(TP+FP), R=TP/(TP+FN), F1=2TP/(2TP+FP+FN). 0분모는 기존 계산기와 같이 0. PASS는 반올림 전 F1>=0.79. TP+FP+FN+TN=20, TP+FN=10, TN+FP=10. official_pass=null.
7. evidence는 정확히 target20행이며 CSV에서 동일 산식을 독립 재계산한다. context는 별도 full_predictions artifact로 유지한다. run manifest에 raw/normalization/input/label/selection/prediction/evidence/engine hash를 기록한다.

## Target contract 및 라벨링

- 정확히 event_id 20개, 고유한 비어 있지 않은 ID. KEEP10/REMOVE10, held_out=true. target의 ID는 full raw 내 정확히 한 건과 일치해야 한다.
- REMOVE category는 duplicate/noise/repeated_action/irrelevant_action 중 하나. 권장 3/3/2/2는 hard requirement가 아니지만 수집 전에 선정 원칙을 고정한다. 지원 안 되는 irrelevant_action을 모델 예측 때문에 제외·교체·재분류하지 않는다.
- duplicate/repeated_action category 명칭이 달라도 binary REMOVE prediction은 TP다. category별 결과는 진단용이며 binary 정답을 바꾸지 않는다.
- KEEP은 remove_category를 비워둔다. raw 의미상 실제 업무 이벤트인지, 반복이라도 별도 의도가 있는지 라벨 근거를 남긴다. 단순 activity token 동일성을 GT로 삼지 않는다. 애매한 event는 예측 전 독립 검토하며 억지로10/10을 맞추지 않는다.
- source_dataset/session/case/file/hash를 보존한다. `raw_sequence_index`는 봉인된 full sequence의 0-based 위치, `csv_record_number`는 헤더 제외 1-based CSV record 번호이며 물리적 줄 번호와 구분한다. 여러 파일이면 file manifest 순서를 먼저 고정한다.
- `target_labels.template.csv`는 **헤더만 있는 빈 양식**이다. 20개 가상 ID나 GT를 만들어 채우지 않았다. `held_out`은 제출 시 boolean true로 검증하며 CSV 문자열은 명시적 strict parser로 처리해야 한다.

## Held-out validator 검증 명세 (아직 미구현)

모든 gate는 fail-closed. 실패/불충분이면 점수 null, PASS/FAIL 계산 안 함.

| Gate | 필수 근거 및 거부 조건 |
|---|---|
| Freeze | 원본 freeze/cleaning/adapter/config/normalization hash 일치. mismatch면 중단 |
| Post-freeze | full context 전부의 collection start/end, event timestamp 및 timezone/collector clock 근거. freeze 이후 수집임을 확인. timezone/시각 또는 수집 시작 근거 불명확하면 BLOCKED |
| Source completeness | 전체 session/case export, 원본 row count/SHA-256/schema, session-task 참조, event ID 유일성, timestamp ordering/tie order, export 범위/끝 확인. 단순 최대20 또는 target 앞뒤 일부 잘라내기 거부 |
| Separation | `data/held_out/m05/<dataset>/raw/` 등 별도 경로. dev01/dev02/workflow development 및 그 복사본 거부. 새 수집 사실과 기존 training/development source inventory 대조, ID/내용 overlap 및 이력 감사. held_out=true만으로 통과시키지 않음 |
| Target | 20고유 ID/10KEEP/10REMOVE/category/원본 위치/hash 일치. ID 누락/중복/범위 밖 거부 |
| Label independence | prediction 전에 target·label lock hash/시각/라벨러 근거와 독립 reviewer 확인. prediction 보고 재선정·label 변경·irrelevant 제외 금지. 불명확하면 BLOCKED |
| Input | full input ID/순서/case mapping 보존, 원래 normalization, GT 전달 없음, trimming/사전 cleaning 금지 |
| Prediction | full output ID집합 일치, 유효 binary label, 고정 engine version/hash. target extraction 후 정확히20개 |
| Score/CSV | context 제외/20행/confusion 합20/공식/P/R/F1 재계산 일치/해시 일치 |

기존 validator는 20 target JSON의 features/history proof를 요구하지만 full context/source completeness/post-freeze/label lock을 검사하지 않는다. 기존 검증을 우회하거나 self-attestation으로 채우지 말고 후속 orchestration에서 위 gate를 추가해야 한다. 기존 feature fingerprint 중복 검사는 독립수집 의미 판정과 구분하고 자동 완화하지 않는다.

## Evidence CSV 명세

`evidence.template.csv`의 필드는 target ID/GT/prediction/category/confusion, source dataset/session/case/file/hash/raw 위치, input/case 순서, remove_reason/duplicate_of_event_id, model/version/freeze/adapter/hash, raw/input/labels/selection/predictions hash, run_id/DEVELOPMENT/is_target를 포함한다. `is_target`은 모든20행 true다. engine의 reason은 GT category와 별개로 원문 보존한다. annotation을 prediction에 복사하지 않는다. 실제 CSV hash는 run manifest에 기록하고 CSV 자기 해시는 필드에 넣지 않는다.

## 수집자에게 필요한 최소 입력

동결 시각 이후 별도 수집한 **전체 raw 이벤트 export**와 관련 sessions/tasks, collection start/end/timezone/수집 범위·완료 기록을 제공한다. 현재 엔진의 성공 패턴을 만들기 위한 synthetic event/수동 raw 편집은 하지 않는다. 실제 업무의 정상 행동과 중복·잡음·반복·업무 무관 행동의 의미를 독립 사람이 구분할 수 있게 업무 목적/관찰 기록을 남긴다. 20 target을 얻기 위해 전체 raw가20건일 필요는 없으며 충분한 실제 context를 보존한다. 수집된20/10/10 구성 달성이 불확실하면 raw를 조작하지 말고 상태를 보고한다.

## 독립 Verification 요청 및 남은 작업

지금 검증 가능한 것은 문서 계약/빈 template/기존 코드 지원 범위/동결 hash 불변뿐이다. 새 데이터 이후 수집시점·라벨독립·context·target count·prediction·산식·CSV 실측 검증은 **NOT_RUN**이다. 후속 최소 작업은 새 raw 확인 → label/selection lock → 별도 context-preserving 평가 orchestration/validator 구현 및 합성검증 → 독립 검증 → frozen engine1회 평가 → CSV 재계산이다. 이번에 새 코드 구현, F1 측정, 웹 실측 완료를 주장하지 않는다.
