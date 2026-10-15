# Workflow Candidate v1

DEVELOPMENT 전용 경량 신경망 workflow 분석 후보입니다. M01/M03/M04/M07 외부 API, V6.2 frozen/reference/runtime, 원본 데이터는 변경하지 않습니다. 공식 KTL 점수 또는 PASS/FAIL을 생성하지 않습니다.

실측 결과와 최종 판정은 [개발 보고서](diagnostics/development_report.md), 전체 수치는 [development_evaluation.json](diagnostics/development_evaluation.json)에 보관합니다.

## 기준과 허용 범위

작업 시 루트 AGENTS.md, R&D_COMPLIANCE.md, 최신 KTL 확인서 PDF p.6–11, v3 manifest, V6.2 manifest 및 notebook의 Event/Segment Transformer 구조를 확인했습니다. 최신 KTL 기준 파일의 hash는 루트 compliance 문서와 일치합니다. V6.2 승인 결과는 재실행하지 않았습니다.

사용자가 이번 요청에서 명시적으로 허용한 DEVELOPMENT execution boundary supervised 학습을 적용합니다. M02 GT, BU 이름/ID, task_name, 반복 번호는 feature로 사용하지 않습니다. BU ID는 그룹 split과 사후 분석에만, repetition은 train/holdout 분할에만 사용합니다. GT process/step 파일은 읽지 않습니다.

## 데이터와 추론의 분리

`src/data.py`는 논리 manifest와 source CSV hash를 검증하고 active event membership의 합집합을 재구성합니다. provenance와 execution metadata를 분리한 뒤 **source dataset + source session별로 timestamp/event ID 순 정렬**합니다. 다음 execution으로 넘어가도 GRU state를 초기화하지 않습니다. 세션 간 연결은 하지 않습니다. workflow_index, workflow_key, task_id, execution_id, BU, repetition, raw input_data, element_text는 추론 feature에서 제외됩니다.

논리 데이터의 **선별 자체에 기존 execution 범위가 사용되었다**는 제한이 있습니다. 제외된 원시 이벤트로 생긴 시간 간격이 단서가 될 수 있으므로, 결과를 연속 미선별 로그의 성능으로 해석하면 안 됩니다. 경계 라벨은 별도의 `training/boundary_labels.csv`에만 기록합니다. 첫 세션 시작은 강제 시작점으로 별도 취급합니다.

실제 deployment 형태를 시험할 수 있는 `src/infer.py`는 **raw events CSV와 모델 artifact만** 받습니다. execution manifest나 업무 목록은 받지 않습니다. 새로운 CSV의 필드 이름은 현행 events schema를 따르며 특정 source 경로나 현재 event ID에 의존하지 않습니다.

## 모델과 feature

- CPU, 입력 396차원 → projection 64/tanh → 단방향 GRU 64, 1 layer → MLP 32/ReLU/dropout 0.1 → boundary logit.
- 입력은 현재 이벤트 signed SHA-256 hash 256차원, 직전 이벤트 hash 128차원, temporal/transition flag 12차원입니다.
- event_type, interaction_type, element_tag, HTTP method/status category, generic target role, normalized page/API path, 안전한 static page title을 해싱합니다. path/API/title에는 character 3–5 gram도 사용합니다.
- UUID, 숫자/날짜/시간/긴 hex token은 `:id`로 치환하고 URL query/fragment는 제거합니다. vocabulary/UNK가 없으므로 새로운 경로도 표현됩니다. 해시 충돌 가능성은 남습니다.
- target_selector는 navigation/input/dialog/item 등의 일반 역할 판별에만 사용합니다. 자유로운 target text, 입력값, payload는 버립니다. page_title은 config의 static allowlist만 사용하며 나머지는 `<redacted-title>`입니다.
- pretrained semantic encoder는 사용하지 않습니다. 따라서 encoder 이름/revision은 null입니다. 의미 임베딩 전처리 경로도 동일한 privacy 필터를 적용하며 별도 외부 다운로드가 없습니다.
- temporal: log-scaled 이전 이벤트 간격, 세션 경과시간, 과거 10초 event density, inactivity 20초, page change와 이전 완료/현재 동작 flags. 미래 이벤트는 사용하지 않습니다.

`config/default.json`에 모든 학습/분할/해싱/군집 설정을 공개합니다. 80 epochs, Adam lr 0.003, seed 20261014, gradient clip 1.0, weighted BCE의 positive weight=`train_negative/train_positive`입니다. threshold=0.5는 학습 전 고정하며 holdout으로 최적화하지 않았습니다. 작은 synthetic fixture로 학습 재현성을 검사합니다.

## 기준선과 평가 정의

일반 메뉴 click, route/page change, 이전 popup-close 또는 성공 mutation 이후 새 click, inactivity gap을 사용하는 rule baseline입니다. 특정 BU 경로→업무 매핑은 없습니다. baseline은 최종 모델로 승격하지 않습니다. downstream 산출물은 GRU prediction으로 생성합니다.

학습: R1/R2. 내부 holdout: R3.

**INTERNAL DEVELOPMENT HOLDOUT**

**NOT INDEPENDENT UNSEEN VALIDATION**

훈련에서는 선택된 training 이벤트의 연속 chunk만 입력하며, holdout 이벤트가 사이에 있으면 chunk를 끊습니다. chunk 첫 transition은 loss에서 제외합니다. execution마다 chunk를 만들지 않습니다. 분할 양쪽에 걸친 transition은 해당 split 평가에서 제외합니다. 전체 평가에는 모두 포함됩니다. 추론은 완전한 세션의 과거 context를 사용하므로 holdout 시작 직전 training 이벤트 context가 남을 수 있지만 label은 전달되지 않습니다.

BU 그룹 3-fold는 seed로 섞은 BU 목록을 round-robin으로 분할합니다. held BU 이벤트는 학습에 포함하지 않습니다. 같은 train/holdout 그룹 내 인접 event transition만 평가하므로 fold별 boundary 수가 작습니다. 별도 독립 검증이 아닙니다.

- boundary precision/recall/F1: 같은 source session 내 ±1 event 허용, 정렬된 one-to-one matching. exact(0 tolerance)도 저장합니다. 세션 최초 시작은 제외합니다.
- predicted workflow count: model boundary + 세션 최초 시작 수.
- correct segmentation: predicted event 집합이 한 execution event 집합과 정확히 일치한 수. ±1 허용을 적용하지 않습니다.
- over-segmented execution: 여러 predicted workflow에 걸친 실제 execution 수. extra_fragments도 별도 보관합니다.
- under-segmented workflow: 여러 실제 execution을 포함한 predicted workflow 수. merged_execution_excess도 별도 보관합니다.
- train/holdout report의 prediction은 전체 stream causal inference로 산출합니다. training loss의 chunk reset 조건과 완전히 같지는 않습니다.

## Workflow, clustering, process map

GRU hidden mean/max pooling 128차원과 structural event hash 평균 256차원을 결합합니다. 각 블록 L2 normalize 후 sqrt(0.35)/sqrt(0.65) 가중, 최종 L2 normalize하여 **384차원**을 얻습니다. page/action/API의 연속 중복 제거 signature와 edit similarity를 별도 설명 근거로 저장합니다. neural hidden은 순서를 반영하지만 structural 평균은 순서를 보존하지 않습니다.

Agglomerative average linkage/cosine distance. config의 threshold 0.15~0.85를 탐색하며 `cosine silhouette - 0.1 * singleton fraction` 최대를 선택합니다. K는 지정하지 않습니다. business metadata 없이 계산하며 동률이면 config에서 먼저 나온 threshold를 선택합니다. DBI는 Euclidean 기반 sklearn 구현을 사용하며 **공식 M06 아님**을 기록합니다. 전체 dataset embedding을 이용한 transductive DEVELOPMENT 군집 진단입니다.

모든 cluster가 계산된 뒤 event overlap으로 execution→cluster 대표값을 정합니다. 가장 많은 이벤트를 포함한 cluster를 택하고 동률이면 낮은 ID를 사용합니다. 이 대표값은 fragment나 병합을 감추기 쉬우므로 segmentation 오류 수 및 cluster purity와 함께 읽어야 합니다.

cluster별 cosine medoid instance를 canonical 순서로 보관하고, 다른 instance의 transition도 관찰 graph에 유지합니다. event를 page_entry / selection / input / submit_save / detail_open / detail_close / api_confirmation / api_failure로 압축하고 연속 동일 action+context를 병합합니다. collector 내부 이벤트는 node로 만들지 않습니다. step/node/edge/input은 source event 또는 source instance로 추적됩니다. 입력값은 `<redacted>`입니다. 이 action 수준 map은 사람이 확정한 업무 GT가 아닙니다.

`src/adapter.py`는 model→canonical procedure/evidence 경계를 제공합니다. 기존 M03 contract를 변경하거나 생성기를 실행하지 않습니다. 모델 artifact를 바꾸어도 외부 API 변경은 필요하지 않습니다.

## 실행

프로젝트 루트에서 실행합니다. Python 3.10, torch 1.13.0, numpy 1.23.5, scikit-learn 1.1.3으로 검증했습니다.

```sh
python3 -m model.workflow_candidate_v1.training.run --dataset data/development/current_site_20x3_v3
python3 -m model.workflow_candidate_v1.src.infer --events /path/to/new/events.csv --artifacts model/workflow_candidate_v1/artifacts --output /tmp/workflow_prediction.json
python3 -m unittest discover -s model/workflow_candidate_v1/tests -v
python3 -m unittest discover -s tests -v
```

첫 명령은 candidate artifact/diagnostic만 다시 생성합니다. 원본은 변경하지 않으며 V6.2를 호출하지 않습니다. artifact manifest에 weights/config/code hash, training manifest에 데이터 hash/분할/seed/library version/훈련 시각을 기록합니다. `protected_files_verification.json`에 V6.2·기존 API·source dataset 파일 불변 검증을 보관합니다. 공식 점수·새 GT·원본 CSV는 만들지 않습니다.
