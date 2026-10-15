# Workflow Candidate v1.2

DEVELOPMENT 전용 boundary 개선 및 HTTP-method-aware process map입니다. 새 데이터 수집 없이 current_site_20x3_v3의 866 events를 사용합니다. v1/v1.1/V6.2/원본 CSV/제품 API는 변경하지 않습니다.

결과와 판단은 [개발 보고서](diagnostics/development_report.md), [전체 비교 CSV](diagnostics/comparison.csv), [실측 JSON](diagnostics/development_evaluation.json)에 있습니다.

## 범위와 기준

AGENTS.md, R&D_COMPLIANCE.md, v1/v1.1 구현·산출물, v3 manifest를 확인했습니다. 사용자가 허용한 DEVELOPMENT 실행 경계 supervised label만 사용하며 M02 GT step/process를 읽거나 학습하지 않습니다. BU ID/name/task_name/반복 번호는 모델 feature가 아닙니다. 반복 번호는 train/holdout, BU는 group split과 사후 평가에만 사용합니다. 공식 KTL 점수나 OFFICIAL 데이터는 생성하지 않습니다.

## 오류 분석

기존 exact 55/60에서 벗어난 execution 5개를 익명 boundary 기준으로 먼저 분석했습니다. false-positive/false-negative 경계 주위 ±10 event를 raw/general signal로 기록했으며 입력값이나 자유 텍스트는 저장하지 않았습니다.

- `baseline_anonymous_execution_errors.csv`: start/end event ID, 익명 실행, 오류 분류.
- `baseline_boundary_windows.csv`: timestamp, path, interaction, target role, HTTP method/normalized endpoint/status, gap, 경계 label/prediction.
- `baseline_errors_posthoc.csv`: 분석 완료 후 execution ID/BU/repetition 연결.
- `remaining_execution_errors.csv`, `remaining_boundary_windows.csv`: v1.2의 남은 오류.

OVER와 UNDER는 동시에 존재할 수 있습니다. 예를 들어 이전 업무 말미를 먼저 잘라 다음 업무와 합치면 이전 execution은 과분할이고 두 execution은 병합에 포함됩니다. START/END 오류는 정답 시작/끝 위치에 predicted boundary가 없는 경우입니다. 실제 시간 공백이 없는 임의 경계를 추가하지 않습니다.

일반 원인은 popup 종료 후 탐색/배경 click을 새 업무 시작으로 너무 일찍 판단하는 패턴, route change 없이 새 modal이 열리는 실제 시작을 놓치는 패턴, terminal `page_close`를 새 업무 시작으로 판단한 패턴입니다. 특정 page/API/BU 전용 split 규칙은 없습니다.

## Boundary 모델

Projection 64 → GRU hidden 64×1 → MLP hidden 32를 유지했습니다. 입력만 기존 396차원에 일반 구조 신호 32개를 추가해 428차원으로 늘렸습니다. 파라미터 수는 54,529입니다.

추가 신호는 popup 활성 상태/종료 이후 간격, HTTP method 분리, 직전 API family 변화, mutation completion, 직전 사용자 조작 역할, 현재 button/item/grid-cell/container 역할, completion→navigation, page/action transition 등입니다. DOM selector는 일반 역할 판별에만 사용하며 입력값·element_text를 읽지 않습니다.

**Offline feature:** 최대 1초·3개 subsequent event에서 popup/route/API 결과를 확인합니다. 다음 사용자 조작을 만나면 탐색을 중단합니다. 앞선 배경 click에 다음 버튼의 popup을 잘못 귀속하지 않기 위함입니다. 모델은 즉시 streaming/causal inference 제품이 아닙니다. 실시간 사용 시 버퍼/지연 계약이 별도로 필요합니다.

`page_close`, `collector_boot`, `popup_structure`는 새 업무 시작으로 허용하지 않는 generic lifecycle decoder를 적용했습니다. 이벤트는 삭제하지 않고 앞 workflow provenance에 남깁니다. source session 시작은 기존처럼 별도 강제 시작입니다. 데이터셋의 execution 수를 보고 cut 수를 보정하지 않습니다.

## 학습과 평가

- R1/R2 학습, R3 내부 holdout. Weighted BCE, positive weight=`negative/positive`.
- seed 20261014, epochs 80, Adam lr 0.003, gradient clip 1, threshold 0.5.
- 한 가지 feature/config 후보만 사전 고정했습니다. threshold/grid/seed sweep은 수행하지 않았습니다.
- GRU를 처음부터 학습하며 기존 v1 checkpoint로 warm start하지 않았습니다.
- 각 training chunk 안에서만 feature를 계산하므로 holdout 이벤트를 training lookahead로 읽지 않습니다. chunk 첫 transition은 기존 방식대로 loss에서 제외합니다.
- group 3-fold는 v1과 정확히 같은 BU 분할/seed이며 각 fold도 처음부터 학습합니다. BU는 split 선택에만 사용합니다.
- 평가: 동일 세션 ±1 event 일대일 매칭. exact boundary metric도 저장합니다. 세션 최초 시작과 해당 split을 가로지르는 transition은 split 점수에서 제외합니다.
- `under_segmented_execution_count`는 병합 예측에 포함된 실제 execution의 고유 수이고, `under_segmented_workflow_count`는 병합된 predicted workflow 수입니다. 혼동하지 않습니다.

**INTERNAL DEVELOPMENT HOLDOUT**

**NOT INDEPENDENT UNSEEN VALIDATION**

R3를 이미 특성 분석과 오류 진단에 사용했습니다. 이 개선을 독립 일반화 결과로 해석하면 안 됩니다. 논리 dataset은 execution 범위로 사전 선별된 이벤트 집합이며 완전한 미선별 연속 로그도 아닙니다. offline 추론은 전 세션 문맥을 읽지만 업무 label을 받지 않습니다.

## Representation C와 clustering 고정

새 boundary 모델의 hidden state를 C에 대입하지 않았습니다. **v1 representation encoder 가중치를 그대로 복사·고정**하고 동일 stream에서 얻은 hidden을 새 predicted 구간에 pooling합니다. 따라서 representation encoder와 구성까지 동일하며 새로 바뀐 부분은 pooling 구간뿐입니다.

v1.1 C의 existing embedding + page + action + API, 각 block energy weight 0.25, 총 1152차원, SHA-256 sequence hashing을 그대로 사용합니다. `representation_config.json`은 v1.1 파일과 bytes/hash가 같습니다.

Agglomerative average/cosine, threshold 후보 0.15~0.85, silhouette−0.1×singleton fraction 선택식을 그대로 사용합니다. K=20 또는 22를 강제하지 않으며 purity를 보고 parameter를 바꾸지 않습니다. clustering을 완료하고 결과 hash를 남긴 뒤 business post-hoc 평가를 수행합니다.

## Process map 수정

Node identity:

`generic action + HTTP method + normalized endpoint + page context + target role`

GET/POST/PATCH가 동일 endpoint라는 이유로 한 node에 합쳐지지 않습니다. 동일 identity의 연속 이벤트는 하나의 step으로 압축하고 같은 identity가 재등장하면 동일 node를 재사용합니다. 예를 들어 GET, GET, POST, PATCH, GET은 node 3개·step 4개입니다. event ID를 node key로 사용하지 않습니다.

Nodes/steps/canonical procedure에 method와 normalized endpoint를 기록하며 각 source event evidence는 유지합니다. 새 candidate 내부 canonical schema는 `workflow-canonical-1.1`입니다. 기존 backend M03 및 M01/M04/M07 API는 변경하지 않습니다.

Process-map audit는 v1.1과 동일합니다. method를 보존했더라도 boundary 단계에서 이미 다른 업무가 하나의 workflow로 합쳐진 경우는 B 혼합 위험으로 남습니다. graph에서 연결 가능한 미관찰 경로와 실제 medoid output은 구분합니다.

효과 분리:

- `generator_only_ablation.json`: v1.1 구간/cluster에 새 generator만 적용.
- `boundary_only_ablation.json`: 새 구간/cluster에 기존 generator 적용.
- `lifecycle_guard_ablation.json`: 새 학습 모델의 raw logits와 terminal decoder 적용 차이.

현재 main R3의 분할 개선은 terminal decoder로 page_close 과분할 한 건을 제거한 결과입니다. 두 조기 경계 오류가 neural feature만으로 해결됐다고 주장하지 않습니다. Group fold 개선은 별도의 진단입니다.

## 산출물과 실행

프로젝트 루트에서:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m model.workflow_candidate_v1_2.src.run
PYTHONDONTWRITEBYTECODE=1 python3 -m model.workflow_candidate_v1_2.src.infer --events /path/to/new/events.csv --output /tmp/workflow_v12.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s model/workflow_candidate_v1_2/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

첫 명령은 candidate만 학습하고 3-fold를 다시 계산하며 candidate artifacts/diagnostics를 갱신합니다. 독립 raw CSV 추론은 실행 manifest나 업무 label을 받지 않습니다. weights/config hash 검증을 수행합니다. 원본 데이터와 부모 모델 파일은 before/after hash로 보호합니다.

artifacts에는 boundary model, model/feature config, frozen representation encoder/config, representation config, training/model manifest를 보관합니다. training manifest는 source hash, split, seed, version, timestamp, 설정과 loss history를 포함합니다. diagnostics에는 60 predicted workflow, embeddings, clusters, process tables, canonical output, 오류 문맥, 비교/ablation/검증 결과가 있습니다.

## 현재 판단

DEVELOPMENT 채택 조건은 통과했습니다. 전체 F1 0.9828, R3 F1 0.9444, exact segmentation 56/60, DBI 0.4168, purity 99.65%, GET/write mixed node 0입니다. Mixed-risk process model 2개와 기존 두 업무 혼합 pair는 남습니다. Group fold F1은 0.8333/0/0.7143으로 개선됐지만 fold 2의 실패가 계속됩니다.

**최종 판정: B. BOUNDARY_NEEDS_MINOR_ADJUSTMENT**

새 수집을 요구하거나 수행하지 않았고, 현재 모델을 unseen 검증 준비 완료로 승격하지 않았습니다.
