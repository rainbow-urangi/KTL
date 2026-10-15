# Workflow candidate v1.1

v1의 boundary model·preprocessing·61개 predicted workflow를 유지한 DEVELOPMENT representation/clustering 개선입니다. 학습과 새 데이터 수집을 하지 않습니다. v1/V6.2/원본 데이터/제품 API는 수정하지 않습니다.

결과: [비교 보고서](diagnostics/development_report.md), [전체 후보 비교 CSV](diagnostics/candidate_comparison.csv), [선택 근거](diagnostics/selection_review.json).

## 구현 및 비교 조건

`src/representation.py`에는 event provenance·입력 metadata를 feature로 넣지 않는 sequence hashing과 결합 함수를 구현했습니다. 원래 v1의 feature preprocessing과 경계 모델은 import하여 재사용하며 가중치는 새 artifacts에 동일 bytes로 복사합니다. 새 representation은 boundary inference 이후에만 적용됩니다.

| 후보 | 구성 | 정규화 후 block energy weight | 차원 |
|---|---|---|---:|
| A0 | 순수 GRU hidden mean/max | 1 | 128 |
| A | 기존 v1 embedding | 1 | 384 |
| B | 기존 embedding + page | 0.5 / 0.5 | 640 |
| C | 기존 embedding + page + action + API | 각각 0.25 | 1152 |

A는 이미 neural 128 + structural 평균 256이 결합된 v1 표현입니다. 순수 neural과 혼동하지 않도록 A0도 제공합니다. 각 block을 L2 normalize한 뒤 `sqrt(weight)`를 곱해 concatenate하고 전체 L2 normalize합니다. page/action/API block은 각각 256차원입니다. 모든 가중치는 첫 실행 전에 `config/representation.json`에 고정했습니다.

- Page: 정규화한 path 순서, 인접 transition, 1/2/3-gram.
- Action: interaction_type 순서 및 generic navigation/input/submit/modal/read/create-or-command/update-or-command signature. 이름이나 업무 ID를 사용하지 않습니다. GET의 마지막 segment가 `:id`이면 `read_detail`, 아니면 `read_collection_or_resource`로 표현합니다. API 설계를 근거로 한 generic 신호이며 실제 업무 의미의 정답이 아닙니다.
- API: HTTP method + 정규화 endpoint 순서의 1/2/3-gram.
- 연속 중복 token을 축약하고 n-gram 반복은 `log(1+count)`로 가중합니다. SHA-256 signed hashing으로 vocabulary/UNK 없이 표현합니다.
- URL의 UUID/숫자/날짜/시간/긴 hex token은 v1 normalization으로 처리하며 query/fragment는 제외합니다. 입력값·element_text·업무명·task_name·BU·repetition·GT는 새 representation에 들어가지 않습니다.

모든 후보에 동일한 Agglomerative average linkage/cosine, v1과 같은 threshold 후보 `[0.15,0.25,0.35,0.45,0.55,0.65,0.75,0.85]`를 적용했습니다. silhouette−0.1×singleton fraction을 최대화하며 K는 강제하지 않습니다. tie는 config 순서입니다. silhouette은 cosine, DBI는 sklearn Euclidean 기반이며 공식 M06이 아닙니다. 비교 목적을 충분히 확인했으므로 DBSCAN은 추가하지 않았습니다.

## Leakage와 단계 분리

1. 논리 dataset source/hash 검증 및 active event 합집합 재구성.
2. v1 checkpoint로 세션별 재추론. 기존 probability/decision/workflow membership/embedding과 동일성 검증.
3. BU metadata를 전달하지 않고 모든 후보 표현·군집·process map 생성 완료.
4. `clustering_stage_manifest.json`에 결과 hash 고정.
5. 그 뒤에만 BU metadata로 post-hoc purity/consistency/fragmentation/process-map 영향을 분석.

Label은 feature나 clustering 함수 인자가 아닙니다. 후보 선택에는 사용자가 요청한 post-hoc 안정성·업무 분리 진단도 고려하지만, 선택 이후 weight/threshold/경계를 다시 최적화하지 않습니다. M02 GT 파일은 읽지 않습니다. 실행 경계는 결과 검산에만 사용하며 새 segmentation을 강제하지 않습니다. 현재 논리 dataset 자체가 선별된 이벤트 집합이라는 v1의 제한도 유지됩니다.

## 지표 정의

- Boundary F1: 기존 R3 internal holdout, 동일 세션 ±1 event 일대일 매칭. 모든 probability와 segmentation membership을 동일하게 유지했습니다.
- BU consistency: 각 execution의 event 수 최다 cluster를 대표값으로 정하고, 3회 대표값이 모두 같은 BU 수. 동률은 낮은 cluster ID.
- Cluster purity: cluster별 가장 많은 BU event 수 합 / 전체 866 events.
- Merged BU pairs: 어떤 cluster에서든 event가 공존하는 고유 서로 다른 BU pair 수. 작은 boundary 오차도 포함합니다.
- Fragmented BUs: 소수 fragment까지 포함해 event가 2개 이상 cluster에 걸치는 BU 수.
- Primary fragmented BUs: 대표 cluster가 서로 다른 반복을 가진 BU 수. 위 fragment 수와 다릅니다.

C는 22 cluster, consistency 19/20, purity 99.65%, merged pair 2, all-fragment BU 4입니다. 이 4개는 BU01, BU02, BU13, BU20입니다. 대표 cluster만 보면 분산 BU는 BU01 한 개입니다. 선택을 20 cluster에 맞추지 않았습니다.

## Process map 감사

생성기는 v1 `process_maps`와 adapter를 그대로 사용했습니다. cluster만 달라졌을 때 영향을 비교하기 위함입니다. 생성기 수정은 이번 범위에 포함하지 않았습니다.

- A: 동일 dominant page family이고, instance별 path가 보존되며, 아래 혼합 신호가 검출되지 않은 다중 BU model.
- B: 이미 mixed-BU workflow가 들어 있거나, cross-business GET/write 의미가 같은 node로 소실되거나, 서로 다른 BU edge를 연결한 미관찰 3-node 경로가 union graph에 가능하거나, 다른 page family가 한 model에 합쳐진 경우.
- 단일 BU model은 A/B와 별도로 집계합니다. 같은 BU 내 method 소실은 별도 지표입니다.

A는 잠정적인 structural family 판정이며 M02/M03 출력의 의미적 정확성을 보증하지 않습니다. 실제 출력 adapter는 관찰된 medoid 하나를 반환합니다. 미관찰 3-node 조합은 graph 자유 순회 시의 위험이지, adapter가 그런 시나리오를 이미 출력했다는 의미가 아닙니다. instance 경로가 보존되어 있다는 사실과 aggregate node 의미 손실도 구분합니다.

v1 BU04/BU05는 A 사례입니다. 다른 BU들을 무조건 분리해야 한다고 평가하지 않았습니다. C의 B model 2개는 기존 WF-0038(BU02 event 2개 + BU03 event 17개), WF-0049(BU13 event 1개 + BU14 event 39개)의 upstream 경계 오류입니다. 이 구간은 수정하지 않았습니다. method를 node key에서 생략하는 기존 생성기 때문에 동일 BU 내부까지 포함한 GET/write 충돌 node 7개는 남습니다. 실제 event method는 evidence로 역추적할 수 있습니다.

## 실행과 산출물

프로젝트 루트에서:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m model.workflow_candidate_v1_1.src.run
PYTHONDONTWRITEBYTECODE=1 python3 -m model.workflow_candidate_v1_1.src.infer --events /path/to/events.csv --output /tmp/workflow_v11.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s model/workflow_candidate_v1_1/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

비교 runner는 현재 v3와 고정 v1 baseline을 검증하며 새 neural 학습을 수행하지 않습니다. 독립 raw CSV inference는 execution manifest나 업무 목록을 받지 않습니다. v1의 코드 의존성을 유지하며 관련 source SHA-256을 manifest에 기록합니다. 새 입력의 군집화는 동일 threshold grid를 쓰는 transductive 방식입니다.

각 후보 디렉터리에는 embedding, cluster assignments, unsupervised diagnostics, process_models/nodes/edges/instances/steps/node_inputs, post-hoc business evaluation과 process-map 감사가 있습니다. `observed_variants.csv`는 사후 감사용이며 BU label을 모델 입력에 사용하면 안 됩니다.

원본 전체 hash 불변 검사, artifact/code hash, 실제 재추론 동일성, synthetic 테스트 및 기존 회귀 테스트 결과를 diagnostics에 보관합니다. 후보의 학습/임의 weight 탐색, 새 수집, OFFICIAL 데이터 생성 또는 공식 KTL 점수 계산은 하지 않았습니다.

**최종 판정: B. CLUSTERING_NEEDS_MINOR_ADJUSTMENT**

C가 분리와 graph 혼합 측면에서 가장 균형이 좋지만 최초 페이지 진입 방식 차이로 인한 fragment 민감도와 기존 process-map method 표현을 추가 검토해야 합니다. 기존 boundary 그룹 일반화 문제를 이번 작업으로 해결했다고 주장하지 않습니다.
