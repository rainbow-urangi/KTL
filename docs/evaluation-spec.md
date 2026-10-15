# 평가 명세

최상위 기준: [R&D_COMPLIANCE.md](../R&D_COMPLIANCE.md), 실제 데이터 준비: [공식 매트릭스](compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md).

## 모드와 상태

REFERENCE는 실제 historical artifact 검증이며 공식 성적이 아닙니다.
OFFICIAL은 공식 데이터 출처, 입력 해시 및 필요한 연결이 검증되어야 합니다.
DEV는 unit test 전용이고 실행 API에서 거부합니다.

| 상태 | 의미 |
| --- | --- |
| NOT_CONFIGURED | 필요한 모델/adapter 미연결 |
| WAITING_FOR_DATA | 공식 manifest 또는 데이터 대기 |
| OFFICIAL_M06_BUNDLE_MISSING | 승인 V6.2 563×128 measurement bundle 미보유 |
| REFERENCE_READY | Reference evaluator 실행 가능 |
| READY | 공식 evaluator 실행 가능 |
| RUNNING | 실행 중; 동시 실행 요청은 HTTP 409 |
| COMPLETED | 측정 완료 |
| REFERENCE_PARTIAL | 실제 보관 자료로 일부만 표시; score null |
| EXTERNAL_MODULE_PENDING | 외부 모듈 연동 예정 |
| ERROR | 무결성/계약/계산 오류; HTTP 422 |

준비 상태는 catalog의 status, 최근 실행 상태는 latest.status에 따로 표시합니다.
준비 상태 기록도 실행으로 보존합니다. 실행은 동기식이고 중간 manifest에 RUNNING을 기록합니다.
과거 결과는 현재 원본 변경 여부를 나타내지 않으므로 현재 준비 상태를 함께 확인합니다.

## 산식과 구현 범위

| 지표 | 산식 / 목표 | 현재 구현 |
| --- | --- | --- |
| M01 | 0.5*C1 + 0.3*(100-C2) + 0.2*C3 ≥65% | CollectorAdapter 계약; 외부 개발 |
| M02 | sqrt(Accuracy × Completeness) ≥ 75 | 독립 evaluator + 실제 Reference |
| M03 | 생성 성공 업무 단위 / 20 × 100 ≥80% | 입력/출력 계약, 검증 및 Reference 입력 preview |
| M04 | 성공 실행 / 전체 실행20 ×100 ≥90% | TestRunnerAdapter 계약; 실패도 분모에 포함 |
| M05 | F1 = 2TP / (2TP + FP + FN) ≥ 0.79 | REMOVE 양성, 0~1; 정제 모델 대기 |
| M06 | DBI ≤ 1.0 | feature + labels 독립 evaluator; Reference feature 대기 |
| M07 | both PASS / generated_code_count ×100 ≥80% | 외부 코드 생성/검증 계약 |

M02 Accuracy = 직접 올바르게 매핑된 절차 / 평가 절차 × 100.
Completeness = 포함된 필수 절차 / 정의된 필수 절차 × 100.
M02 v1.1 직접 매핑 판정은 같은 scenario ID 내 절차명의 Unicode NFKC·casefold·모든 Unicode whitespace 제거 후 일대일 완전 일치입니다.
null은 빈 문자열로 정규화하며 빈 canonical label끼리는 정답으로 매칭하지 않습니다.
사전 등록된 승인 alias만 같은 canonical로 매핑할 수 있으며 자동 추론하지 않습니다.
중복, 미일치, 추가 프로세스 절차도 평가 절차 분모에 포함합니다.
보조/trajectory evidence는 일치로 집계하지 않습니다. 순서·의미 유사도·간선 점수는 이 산식에 포함하지 않습니다.
정의된 GT가 있지만 해당 비교 실행이 없는 경우 필수 절차 분모는 유지합니다.
전체 평가 절차 입력이 비어 있으면 임의 0점 대신 오류입니다.

Reference GT는 `poc_scenario_comparison.csv`의 ground_truth_steps 7종/46절차입니다.
같은 파일의 best_instance_id가 지정한 4개 단일 실행에서 73절차를 읽습니다.
나머지 3종은 저장된 단일 실행 지정이 없습니다. GT를 임의 생성하거나 trajectory로 보충하지 않습니다.
선택 metadata는 `V6.2 Legacy Reference Selection`이며 현재 evaluator가 최적 instance를 재검색하지 않습니다.
기존 comparison의 점수는 사용하지 않습니다. 기존 best instance 선택 자체는 legacy 비교에 의존하므로
독립 시험 표본 선정으로 해석할 수 없습니다. 화면에 `V6.2 Legacy Reference Ground Truth`,
`공식 KTL Ground Truth 아님`을 표시합니다.
GT 파일이 없으면 12개 모델 경로 preview만 제공하고 score는 null입니다.

M05는 precision, recall, F1, TP/FP/FN/TN을 반환합니다.
분모가 0인 precision/recall/F1은 0으로 정의합니다. ID 누락/중복 예측은 오류입니다.

M06 DBI는 유클리드 거리 기반 군집 중심 내 평균 거리와 군집 간 중심 거리로 계산합니다.
입력은 기존 feature matrix와 동일 순서의 labels뿐이며 군집화를 수행하지 않습니다.
단일 군집, 표본 수만큼의 군집, 차원 불일치, label 길이 불일치, 비유한 값,
중심이 일치하는 군집은 오류입니다.
OFFICIAL M06은 승인 V6.2 563×128 workflow embedding과 행이 일치하는 final12군집 label을 사용합니다. 시험 전에 고정하고 1회 결정론적으로 측정하며 scikit-learn DBI와 교차 검증합니다. 승인 당시 80차원 consensus feature와 새 사이트 clustering 산출물은 DEVELOPMENT 진단용으로만 사용합니다. 현재 정확한 128차원 matrix가 없어 공식 상태는 OFFICIAL_M06_BUNDLE_MISSING입니다. feature를 재생성하거나 confidence/margin으로 대체하지 않습니다.

## API 및 기록

- `GET /api/evaluations?mode=REFERENCE|OFFICIAL`
- `POST /api/evaluations/m01/run?mode=REFERENCE|OFFICIAL` ~ m07 (본문 없음)
- `GET /api/evaluations/mxx/runs/<run_id>/result.json`
- 같은 경로의 `evidence.csv`, `run_manifest.json`

mode 생략 시 REFERENCE입니다. 임의 파일 경로나 실행 명령은 API에서 받지 않습니다.
REFERENCE ID는 REF-Mxx-..., OFFICIAL ID는 EVAL-Mxx-...입니다.
각각 `results/reference/`, `results/official/`에 저장하고 latest-Mxx.json도 분리합니다.
기존 `results/Mxx/` 기록은 읽지 않습니다.

result/run manifest는 모드, 지표, dataset/source, 시작/종료 시각, 상태, 입력 경로/해시,
evaluator/model/reference version, 점수/목표/threshold_met/official_pass, 근거 파일, 오류를 기록합니다.
REFERENCE는 기준 충족 여부만 표시하며 official_pass/pass는 null입니다.
OFFICIAL의 완료된 평가에서만 목표값이 있으면 official_pass/pass를 계산합니다.
CSV는 UTF-8 BOM이며 spreadsheet formula injection 문자를 이스케이프합니다.

## M02 v1.1 변경 이력

기존 `evaluation-2.0` 실행 기록은 보존합니다. 신규 M02의 evaluator_version만
`m02-evaluator-v1.1`이며 다른 지표 버전은 그대로입니다.
동일한 Reference 입력에서 직접 일치 16→17, Accuracy 21.917808→23.287671%,
Completeness 34.782609→36.956522%, Final Score 27.610841→29.336519입니다.
추가 일치는 SC01의 `국제교류학년도 학기`와 `국제교류학년도학기`입니다.
GT 46개와 model step 73개 분모는 유지합니다. alias 파일 없이 canonical normalization만 적용한 결과입니다.

OFFICIAL M02는 TD-03 20업무 로그와 TD-04 GT5를 받으며 특정 historical frozen weights를 필수로 강제하지 않습니다. 사전 process ID로 비교하거나 별도 사전 확정 pairing을 제출할 수 있습니다. pairing은 선택 사항이며 DEVELOPMENT의 시간 매핑 정책을 자동 적용하지 않습니다. 모든 생성 맵의 절차를 Accuracy 분모에 유지하고 GT 절차명으로 instance를 검색하지 않습니다.
M03은 동일 TD-03과 TD-05 20업무 정의를 사용해 각각1회 요청, 분모20입니다. 실제 generator는 아직 미연결입니다. M05 OFFICIAL은 학습/개발 미사용 held-out 200건이어야 합니다.
M07 C2는 실제 생성 코드 수이고 요청 수는 진단값입니다. M04 확정 성공률 산식은 KTL 기준이며 원문 역산식 차이는 미해결 사항이 아닙니다.
상세 입력 계약은 data-contracts.md를 참고하세요.
