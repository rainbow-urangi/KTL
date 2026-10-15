# 업무 프로세스 가시화 개발자 전달 명세 — V6.2

## 1. 목적

본 산출물은 딥러닝 모델이 추출한 latent workflow를 개발자가 화면에 시각화할 수 있도록 전달하기 위한 중간 명세입니다.

현재 단계에서는 DB schema를 확정하지 않습니다.
아래 CSV 구조와 HTML preview를 기준으로 실제 서비스 DB/화면 구현 가능 여부를 먼저 검토합니다.

### V6.2 변경 — Stable Consensus Workflow + Customer Report

V6.2은 **V5.7 calibrated segmentation을 유지**하고,
single-seed prototype 대신 multi-seed consensus를 최종 process/node assignment에 사용합니다.

- 유지: frozen multilingual semantic encoder (`intfloat/multilingual-e5-small`)
- 유지: semantic weight `0.20`
- 유지: Structural-aware Event Boundary
- 유지: Segment Transformer / workflow mean pooling
- 유지: Transition Contrastive Workflow Boundary
- 유지: V5.7 calibrated event/workflow threshold
- 변경: prototype full-batch 20 step → 최대 `300` optimization step + early stopping
- 변경: single-seed SP/WP → `5`-seed consensus SP/WP
- 추가: reportability score 및 고객 보고 대상 workflow 선정
- 추가: `customer_workflow_report.html`
- 추가: `reportable_workflows.csv` / `reportable_workflow_steps.csv`
- Gold 업무명은 training / threshold / consensus clustering / reportability score에 사용하지 않음

### urangi Gold Evaluation

알려진 6개 실제 업무 프로세스는 **학습에 사용하지 않습니다.**
최종 추출 결과에 대해서만 post-hoc anchor evaluation을 수행합니다.

평가 산출물:

```text
diagnostics/gold_anchor_confusion.csv
diagnostics/gold_anchor_summary.csv
diagnostics/gold_pair_cooccurrence.csv
diagnostics/evaluation_v2_anchor_provenance.csv
diagnostics/evaluation_v2_summary.csv
diagnostics/evaluation_v2_instance_labels.csv
diagnostics/evaluation_v2_pair_cooccurrence.csv
diagnostics/event_threshold_diagnostics.csv
diagnostics/workflow_threshold_diagnostics.csv
diagnostics/workflow_threshold_signal_summary.csv
diagnostics/workflow_cut_jaccard.csv
diagnostics/prototype_seed_stability.csv
diagnostics/workflow_quality_report.html
diagnostics/workflow_transition_training.csv
diagnostics/workflow_boundary_scores.csv
diagnostics/prototype_ensemble_runs.csv
diagnostics/prototype_seed_pairwise.csv
diagnostics/consensus_k_search.csv
diagnostics/workflow_consensus_assignments.csv
```

V6.2 고객 화면 / 사용자 궤적 변경:

- `sessions.session_id → sessions.user_id`를 이용해 동일 사용자의 process instance를 시간순으로 연결
- `user_id`는 event embedding / prototype clustering feature로 사용하지 않음
- 동일 사용자의 여러 session을 generic temporal episode/window로 연결해 상위 시나리오 후보 생성
- Ground Truth 비교는 single instance뿐 아니라 user trajectory를 primary presentation으로 사용
- 고객 HTML에는 raw user_id 대신 stable hash 기반 `USER-XXXXXXXX` 표시
- 7개 PoC Ground Truth Scenario는 모델 학습 이후 post-hoc 비교에만 사용
- compressed path를 Aggregate process graph보다 먼저 표시
- 조회/팝업/필드/달력 등 사람이 읽을 수 있는 하위 단계는 유지
- `SPxx` / `WPxx`처럼 표시명이 prototype ID뿐인 단계만 HTML path에서 숨김
- Ground Truth와 일치하는 단계는 `✓ Ground Truth`로 강조
- 기준 단계 확인 수 / 기준 순서 재현 / 미확인 기준 단계를 함께 표시
- 전체 `events.csv` row를 제한 없이 사용

고객 전달용 주요 산출물:

```text
main_results/customer_workflow_report.html
main_results/reportable_workflows.csv
main_results/reportable_workflow_steps.csv
main_results/workflow_reportability.csv
```

평가 지표는 workflow separation을 보기 위한 근사 diagnostic이며,
event-level start/end ground truth accuracy로 해석하지 않습니다.


V5.7부터는 기존 anchor 평가는 `legacy` 비교용으로 유지하고,
공식 비교는 `Evaluation v2`를 사용합니다.

- navigation click과 current-page context를 분리
- multi-gold instance는 ARI/NMI에서 제외
- anchor sensitivity를 여러 모드로 동시에 공개
- purity/Hungarian은 참고값으로만 사용

---

## 2. 모델 결과 개요

- dataset: `poc_full`
- events: 32,273
- latent segments: 5,167
- latent workflows: 563
- session-safe process instances: 1,619
- process models: 12
- process nodes: 91
- process edges: 257
- compressed instance steps: 3,137
- process node inputs: 3,992
- customer report selected workflows: 9
- strict reportable workflows: 9

---

## 3. V6.2의 중요 변경

### Session-safe instance

session을 business workflow 정답으로 사용하지 않습니다.

다만 하나의 실제 실행 사례가 서로 다른 session을 넘으면 화면 해석이 어려워지므로,
export 단계에서 `session_id`를 **최대 경계**로만 사용합니다.

즉:

```text
한 session 안에서 여러 workflow 가능
서로 다른 session을 하나의 표시용 instance로 연결하지 않음
```

### Consecutive prototype compression

모델이 만든 원본 sequence:

```text
SP09 → SP09 → SP09 → SP22
```

화면/DB 전달용 sequence:

```text
SP09 (repeat_count=3) → SP22
```

모델 학습 결과를 변경하는 것이 아니라 presentation/export 단계에서만 압축합니다.

### 입력값

QA/테스트 목적이므로 V6.2에서는 `input_data`를 추가 masking하지 않습니다.

- 원본 값이 있으면 그대로 `input_value`로 전달
- 원본 로그가 이미 `[REDACTED]` 또는 `[IDENTITY_CONTEXT]`이면 그 문자열을 그대로 유지
- `is_source_redacted`는 원본이 이미 가려져 있었는지를 표시

---

## 4. 전달 파일

### `process_models.csv`

프로세스 목록의 최상위 단위.

주요 컬럼:
- `model_id`
- `workflow_prototype`
- `display_name`
- `instance_count`
- `node_count`
- `edge_count`
- `avg_compressed_step_count`
- `avg_source_segment_count`
- `input_count`
- `first_seen`
- `last_seen`

### `process_nodes.csv`

프로세스 맵의 node.

주요 컬럼:
- `node_id`
- `model_id`
- `segment_prototype`
- `display_label`
- `sort_order`
- `support_step_count`
- `support_segment_count`
- `support_instance_count`
- `avg_step_position`
- `avg_repeat_count`
- `input_count`
- `representative_evidence`

`display_label`은 presentation layer에서 생성한 이름이며 학습 라벨이 아닙니다.

HTML preview의 업무 프로세스 명칭도 같은 원칙으로,
`WPxx · 추출 업무 프로세스 NN` 형식의 중립적 표시명을 사용합니다.
이 변경은 `workflow_prototype`, `model_id`, clustering 결과, CSV의 원본 `display_name`을 변경하지 않습니다.

### `process_edges.csv`

실제 압축된 instance sequence에서 관찰된 node transition.

주요 컬럼:
- `from_node_id`
- `to_node_id`
- `transition_count`
- `transition_ratio`

V6.2 preview는 이 edge를 실제 graph topology로 사용합니다.

### `process_instances.csv`

session-safe 실제 실행 사례.

주요 컬럼:
- `instance_id`
- `model_id`
- `source_workflow_id`
- `session_id`
- `session_part`
- `start_time`
- `end_time`
- `compressed_step_count`
- `source_segment_count`
- `input_count`

### `process_instance_steps.csv`

**특정 실제 실행의 전체 step sequence**를 복원하기 위한 파일.

주요 컬럼:
- `instance_step_id`
- `instance_id`
- `step_order`
- `node_id`
- `segment_prototype`
- `display_label`
- `repeat_count`
- `source_segment_ids`
- `start_time`
- `end_time`
- `event_count`
- `input_count`

화면에서 특정 실행을 선택했을 때 이 파일을 `instance_id + step_order` 순으로 조회하면 됩니다.

### `process_node_inputs.csv`

각 실행 step에 연결된 실제 입력/선택 값.

주요 컬럼:
- `instance_id`
- `instance_step_id`
- `node_id`
- `step_order`
- `input_kind`
- `input_label`
- `input_value`
- `is_direct_user_input`
- `is_source_redacted`

---

## 5. 데이터 관계

```text
process_models
    │
    ├── process_nodes
    │       │
    │       └── process_edges
    │
    └── process_instances
            │
            └── process_instance_steps
                    │
                    └── process_node_inputs
```

권장 연결:
- `process_models.model_id` → nodes / edges / instances
- `process_instances.instance_id` → instance_steps
- `process_instance_steps.instance_step_id` → node_inputs
- `process_nodes.node_id` → edges / instance_steps / node_inputs

---

## 6. 권장 화면

### A. Process model 선택
`process_models`

### B. Aggregate process graph
`process_nodes + process_edges`

- node = 업무 step prototype
- edge = 실제 관찰 transition
- transition ratio가 낮은 edge는 화면에서 필터링 가능
- branch는 여러 outgoing edge로 표현

### C. 실제 실행 사례 선택
`process_instances`

### D. 선택한 실행의 정확한 path
`process_instance_steps`

예:

```text
학생검색
  ↓
프로그램선택
  ↓
학생정보입력 (반복 3회)
  ↓
저장
```

### E. 당시 입력값
`process_node_inputs`

`instance_step_id` 기준으로 조회하여 해당 step 아래에 표시합니다.

---

## 7. 개발자 검토 포인트

1. 현재 6개 CSV 구조로 기존 DB에 적재 가능한지
2. `process_instance_steps`를 별도 테이블로 두는 것이 적절한지
3. 문자열 ID를 그대로 사용할지 내부 numeric PK를 둘지
4. `input_value`를 row 단위로 유지할지 JSON으로 묶을지
5. 관리자용 process/node 표시명 수정 컬럼이 필요한지
6. aggregate graph와 actual instance path를 화면에서 어떻게 구분할지
7. transition ratio threshold UI가 필요한지
8. graph library 선택
9. workflow prototype 버전 관리 필요 여부

---

## 8. 중요한 해석 원칙

- `WPxx` / `SPxx`는 모델이 발견한 latent prototype
- session은 workflow 정답이 아니라 export instance의 최대 경계
- 연속 SP compression은 presentation layer 처리
- `display_label`은 presentation layer 처리
- input 값은 workflow 학습 라벨로 사용하지 않음
