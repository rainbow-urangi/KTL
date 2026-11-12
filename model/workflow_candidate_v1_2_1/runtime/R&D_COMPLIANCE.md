# R&D / KTL Compliance 기준

확인 날짜: 2026-10-08. 평가 시스템을 수정하기 전에 반드시 확인하는 최상위 프로젝트 compliance 기준입니다. 과거 메모·구버전 명세보다 아래 원본을 우선합니다. 해석이 충돌하거나 불명확하면 임의 변경 없이 사용자에게 확인합니다.

## 원본 및 우선순위

| Filename | SHA-256 | Document role |
|---|---|---|
| `docs/compliance/source/RND_PLAN_ORIGINAL.pdf` | `42f8c48099e216398f38bd70b4b565fe815b74bd1524414c0a6ee211789b8bb4` | 과제 목적, 개발 목표, 7개 지표·목표값, 기술개발 방향의 상위 기준 |
| `docs/compliance/source/KTL_TEST_CRITERIA_CURRENT.pdf` | `88784570e568f5873bf89d3163ec7c227e442cde8fab860ba47c3ec82debeafd` | 최신 실제 시험 데이터 수량, 시험 절차, 세부 산식, 공식 측정·판정 운영 기준 |

페이지 번호는 PDF 기준입니다. 연구개발계획서 p.7–8은 지표·산식, 최신 KTL 확인서 p.6–11은 지표별 시험 운영 기준입니다. KTL 문서 작성일은 2026-09-18입니다.

## 고정 지표와 authoritative source

| 지표 | 목표 | 확정 산식 | 공식 시험 운영 기준 및 원본 |
|---|---|---|---|
| M01 수집정확도 | ≥65% | `0.5*C1 + 0.3*(100-C2) + 0.2*C3` | KTL p.6: 5종×2회, 독립 수집 세션 10개, 회당 필수 이벤트 10건, 총 100건 |
| M02 프로세스맵 정확도/완전성 | ≥75% | `sqrt(Accuracy*Completeness)` | KTL p.7: TD-03 업무단위 20종 로그, 그중 TD-04 GT 5종 |
| M03 테스트 시나리오 자동생성 비율 | ≥80% | 성공 시나리오 수 / 전체 업무단위 20 ×100 | KTL p.8: M02와 동일한 TD-03, TD-05 업무단위 정의 20종, 업무당 1회 요청 |
| M04 자동실행 성공률 | ≥90% | 정상 완료 테스트 수 / 전체 자동 실행 테스트 수 ×100 | KTL p.8–9: 사전 고정 Selenium/Python 스크립트 20건, 각각 1회 실행 |
| M05 AI 정제 F1 | ≥0.79 | `2*Precision*Recall/(Precision+Recall)` | KTL p.9: 학습·개발 미사용 held-out 200건 |
| M06 흐름 군집 품질 | DBI ≤1.0 | Davies-Bouldin Index | KTL p.10: 승인 V6.2 workflow embedding 563×128, final 12개 군집 label |
| M07 LLM 코드 유효성·정확성 | ≥80% | `both_pass_count/generated_code_count*100` | KTL p.10–11: 실제 생성 코드 전체가 C2, 문법·실행 모두 PASS한 코드가 C1 |

목표값은 연구개발계획서의 최종 목표를 사용합니다. 산식·목표를 임의로 변경하지 않습니다. `official_pass`는 유효한 OFFICIAL 결과에만 설정하며 REFERENCE/DEVELOPMENT는 null입니다. 근거가 없으면 점수를 만들지 않습니다.

### M01

C1은 필수 이벤트 수집률, C2는 전체 수집 이벤트×필수 필드 수 대비 누락률, C3는 유형 커버리지이며 모두 백분율입니다.
필수 필드는 `session_id,event_time,event_type,page_url,page_title,target_key` 6종입니다.
유형은 화면 이동, 클릭, 입력, 선택/변경, 제출/저장, 팝업, 네트워크 요청, 키 입력의 8종입니다. 필수 이벤트 목록과 실제 매칭 ID, 누락 유형, 검산 근거를 보관합니다.

### M02 / M03

공식 M02 흐름은 `TD-03 → AI 업무패턴 분석 엔진 → 프로세스맵 → GT 사후 비교`입니다. historical V6.2 frozen weights 사용을 필수 조건으로 강제하지 않습니다.
TD-04에는 process_id, 업무명, 필수 절차 ID, 메뉴/화면명, 절차 순서, 허용 별칭을 고정합니다.
Accuracy 분모는 **생성 프로세스맵 전체 절차 수**이며 GT 대상만 선택하여 분모를 줄이지 않습니다. Completeness 분모는 GT 전체 필수 절차 수입니다. 보조/trajectory 증거는 직접 일치로 자동 계산하지 않습니다.
OFFICIAL은 사전 process ID 대응으로 비교할 수 있고 개발용 execution/temporal pairing 정책을 필수로 강제하지 않습니다. 별도 pairing을 제출하면 GT와 독립적으로 사전 확정하고 중복 선택을 금지하며, 연결되지 않은 맵도 Accuracy 분모에 유지합니다.
M03은 동일한 TD-03과 업무단위 20종을 재사용하고 업무당 생성 요청 1회, 분모 20을 유지합니다. 별도 20개 수집 dataset을 요구하지 않습니다. TD-05에는 업무 ID/명칭, 시작 화면, 필수 수행 화면/절차, 종료 조건을 명시하고, 생성 성공 판정에는 JSON Schema 필수항목과 단계 순서·action/target 정보를 확인합니다. 업무단위 정의는 입력이며 시나리오는 시스템이 생성해야 합니다.

### M04: 확정된 시험 산식

`정상 완료 테스트 수 / 전체 자동 실행 테스트 수 ×100`, 목표 ≥90%는 **확정된 시험 산식**입니다. 연구개발계획서 원문의 역산식은 KTL 제출 과정에서 수정·확정됐으므로 미해결 오류로 분류하지 않습니다. 코드/UI에서 역산식을 쓰거나 실패를 분모에서 빼지 않습니다.
TD-08 스크립트 20건은 시험 전에 고정한 자동생성 Selenium/Python 코드이며 수동 수정하지 않습니다. scenario_id와 assert를 포함하고 각 스크립트를 1회 실행합니다. 원본 archive/hash, 사전 고정 기록, 전체 실행 로그를 보관합니다.

### M05

KEEP 100 / REMOVE 100이며 REMOVE의 duplicate, noise, repeated_action, irrelevant_action은 각각 25건입니다. 평가 manifest에는 `held_out=true, used_for_training=false, used_for_development=false`와 고정 official contract를 요구합니다. OFFICIAL 입력은 training/development 경로와 분리합니다. 이러한 선언만으로 과거 미사용 사실까지 자동 증명되지는 않으므로 별도 데이터 이력을 보관합니다. REMOVE를 양성으로 F1을 측정하고 GT label/category를 정제 모델에 전달하지 않습니다.

### M06

`source=approved_v6_2_measurement_bundle`, `workflow_count=563`, `embedding_dimension=128`, `cluster_count=12`로 고정합니다.
563개 workflow ID, 563×128 embedding, 563개의 final label, 동일 행 순서/ID mapping, source hash 및 시험 전 고정 기록이 필요합니다. 고정 입력으로 결정론적 DBI를 1회 측정하고 scikit-learn `davies_bouldin_score`와 교차 확인합니다.
current_site_dev 또는 새 사이트 clustering 결과, 80차원 consensus feature는 OFFICIAL 입력이나 fallback으로 사용할 수 없습니다. 80차원 측정은 DEVELOPMENT 진단용입니다. 정확한 bundle 미보유 시 `OFFICIAL_M06_BUNDLE_MISSING`을 보고하며 재구성·추론·재학습·재군집화로 보충하지 않습니다.
현재 준비 상태와 확보 계획은 [공식 데이터 매트릭스](docs/compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md)에 기록합니다.

### M07

C1은 문법검사 PASS와 실행테스트 PASS를 모두 만족한 코드 수, C2는 LLM이 **실제로 생성한 전체 코드 수**입니다. 생성된 코드의 문법·실행 실패도 분모에 포함합니다. `generation_request_count`는 진단/provenance이며 공식 분모가 아닙니다. 생성 코드가 0이면 산식을 계산하지 않고 입력 오류로 처리합니다. 20회 요청, 18건 생성, both PASS 15건이면 83.333…%입니다. 입력 시나리오는 M03 생성 산출물이며 코드·검사·실행 근거와 연결합니다.

## 모델 / 평가 분리 및 범위

GT는 post-hoc evaluation 전용입니다. ground_truth.csv, business_unit label, GT step, M02 match result, PASS/FAIL을 모델 학습·추론·군집화에 사용하지 않습니다. GT를 보고 threshold, cluster, instance selection을 점수 향상 목적으로 조정하지 않습니다. 업무단위 정의를 시나리오 생성 입력으로 사용하는 M03 계약과 모델의 GT 누출 금지를 구분합니다.
V6.2 frozen/reference/runtime과 승인 산출물은 명시적 승인 없이 변경하지 않습니다. 승인 수량은 events 32,273 / segments 5,167 / workflows 563 / instances 1,619 / models 12입니다. `current_site_dev_01`(4종×2회)은 DEVELOPMENT이며 공식 데이터로 승격하지 않습니다.

연구개발 목적은 사용자 행위 자동 수집, AI 정제, 반복 패턴 분석, 흐름 군집화, 프로세스맵·시나리오 생성, 자동 실행, 지속학습·변경 대응입니다. Transformer/self-supervised learning/prototype ensemble/consensus clustering 등은 성능 개선을 위한 알고리즘 고도화로 기록할 수 있습니다. 계획서 예시의 K-medoids/DBSCAN을 실제 사용했다는 허위 표현을 금지합니다. 기술 방향을 유지한다는 설명은 모든 기능이 현재 완성됐다는 주장이 아닙니다.
우선 목적은 KTL 평가 수행과 근거 보관입니다. 데이터 검증, 평가 모델 실행, M01–M07 측정, 외부 결과 API, 점수·evidence·run manifest/hash/provenance는 범위 내입니다. 범용 SaaS, DB 운영 플랫폼, 제품 UI 대규모 개편, 신규 사업 기능, 무관한 모델 연구, V7은 명시적 요청 없이는 시작하지 않습니다.

## External Administrative Confirmation Required

- TODO: 과제 관리기관에 KTL 시험성적서 인정 가능 여부 확인

## 시험환경 TODO

실제 시험환경 확정 후 작성합니다. 현재 개발환경 값을 공식 환경으로 대입하지 않습니다.

- 시험 PC OS / CPU / RAM / Storage
- 시험 Server OS / CPU / RAM / Storage / GPU
- Python exact version
- PyTorch exact version
- Selenium exact version
- Chrome exact version
- LLM exact API model identifier/version

KTL 원문의 제품명 수준 표기는 정확한 API identifier 확정을 대신하지 않습니다.
