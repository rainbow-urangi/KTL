# Workflow candidate v1.1 DEVELOPMENT 비교

선택: **C_full**. 최종 판정: **B. CLUSTERING_NEEDS_MINOR_ADJUSTMENT**.

GRU 재학습·boundary architecture/전처리 변경·데이터 추가 수집을 하지 않았다. v1, V6.2, 원본 CSV, 외부 API는 불변이다. 공식 KTL/M02/M06 점수는 계산하지 않았다.

## 고정 비교 조건

A0는 순수 GRU hidden mean/max 128차원. A는 기존 v1 hybrid 384차원이며 순수 neural embedding이 아니다. B는 A+page, C는 A+page+action+API이다. 추가 block은 각각 256차원, 각 block L2 정규화 후 동일 energy weight의 sqrt로 결합하고 최종 정규화했다. B는 0.5/0.5, C는 0.25씩이다.
모든 후보에 v1과 동일한 Agglomerative average/cosine, threshold 후보 0.15~0.85, silhouette−0.1×singleton fraction 선택식을 적용했다. K 고정 없음. 전체 clustering/geometry 기반 선택이 완료된 뒤에만 BU metadata를 post-hoc에 사용했다. 결과 확인 후 weight/threshold 탐색 범위를 변경하지 않았다.
경계 전처리의 volatile ID normalization을 재사용한다. page transition 및 action/API sequence 1/2/3-gram을 결정적 해싱한다. URL query, 입력값, 자유 텍스트, 업무명은 사용하지 않는다. GET collection/resource, GET :id, POST command, PATCH/PUT command 등의 일반 신호이며 특정 endpoint→BU 규칙이 없다.

## 후보 결과

| 후보 | 차원 | Cluster | Silhouette | DBI | 반복 일치 | Purity | Merged BU pairs | Fragmented BUs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | 384 | 10 | 0.8450 | 0.4700 | 20/20 | 66.86% | 14 | 1 |
| A0_pure_gru | 128 | 2 | 0.9307 | 0.1547 | 20/20 | 11.43% | 190 | 1 |
| A_existing | 384 | 10 | 0.8450 | 0.4700 | 20/20 | 66.86% | 14 | 1 |
| B_page | 640 | 18 | 0.9203 | 0.2606 | 18/20 | 88.34% | 6 | 2 |
| C_full | 1152 | 22 | 0.8526 | 0.4070 | 19/20 | 99.65% | 2 | 4 |

Merged BU pairs는 하나 이상의 동일 cluster에 실제 event가 함께 존재하는 고유 BU pair 수다. Fragmented BUs는 모든 fragment를 포함해 2개 이상 cluster에 걸친 BU 수다. 대표 cluster만 비교하는 반복 일치와 다르다. execution 대표 cluster는 event 수 최다 cluster(동률 최저 ID)로 정한다. Purity는 event-weighted이며 새로운 데이터의 일반화 성능이 아니다.
C의 대표 cluster 기준 분산 BU는 1개, 모든 fragment 기준은 4개다.

## v1 / 선택된 v1.1

| 지표 | v1 | v1.1 C |
|---|---:|---:|
| Boundary R3 F1 (±1 event) | 0.9189 | 0.9189 |
| Predicted workflows | 61 | 61 |
| Exact segmentation | 55/60 | 55/60 |
| Cluster count | 10 | 22 |
| Silhouette | 0.8450 | 0.8526 |
| DBI | 0.4700 | 0.4070 |
| BU consistency | 20 | 19 |
| Cluster purity | 66.86% | 99.65% |
| Merged BU pairs | 14 | 2 |
| Fragmented BUs | 1 | 4 |

**INTERNAL DEVELOPMENT HOLDOUT — NOT INDEPENDENT UNSEEN VALIDATION**
모든 event의 boundary probability, threshold 판정, predicted workflow 시작/종료 ID 및 membership이 v1과 일치함을 검증했다. 동일 가중치로 재추론했으며 boundary label은 검산 시에만 사용했다. 기존 BU 그룹 holdout의 약한 일반화는 이번 작업으로 개선하거나 재검증한 것이 아니다.

## 업무 구분 및 남은 fragment

보고 조회/작성, 전체업무 목록/상세, 명함·거래처·자산 목록/상세/등록의 기존 혼동 대부분이 분리되었다. 남은 event-level pair는 BU02/BU03(일정 조회/등록), BU13/BU14(명함 상세/등록)이다. 두 pair 모두 대표 cluster 기준 실행 간 혼동은 0/9이며 기존 WF-0038, WF-0049 내부에 다른 업무 event가 이미 포함된 boundary 오차다.
BU01-R1은 수집 시작 시 이미 열린 화면에서 page_view로 시작하고 R2/R3는 메뉴 이동으로 시작한다. C가 이 관찰 구조 차이를 구별하면서 BU01 반복 일치가 깨졌다. BU02, BU13, BU20은 기존 boundary 오차/fragment 영향으로 여러 cluster에 걸친다. 이를 제거하기 위해 execution 경계를 바꾸지 않았다.
기존 혼동 14 pair의 후보별 상세 비교는 v1_confused_pairs_comparison.csv에 있다. 단순히 20 cluster를 목표로 맞추지 않았다.

## Process-map 영향: 보존과 혼합을 구별

process map 생성기는 v1의 것을 그대로 사용해 representation/clustering 효과만 비교했다. process_steps의 instance별 전체 node path는 모두 역추적 가능하다. 그러나 aggregate graph와 medoid 단일 경로 출력은 서로 다른 의미를 가진다.
v1: A(동일 page family의 보존된 variant) 1개, B(혼합 또는 혼합 위험) 7개. C: A 0개, B 2개. 단일 BU process model은 A/B 집계에서 제외한다.
A 사례: v1 BU04/BU05는 같은 화면 family의 instance path가 보존되고 이번 감사에서 cross-business HTTP method 충돌/미관찰 graph 연결이 검출되지 않았다. 같은 cluster라는 이유만으로 실패로 분류하지 않았다. 다만 M03 adapter는 한 medoid만 내보내므로 모든 variant의 출력 적합성까지 증명된 것은 아니다.
B 근거: 서로 다른 BU의 GET/POST가 동일 api_confirmation node에 합쳐지는 node 수 7→1; 다른 BU edge를 이어 관찰되지 않은 3-node 경로를 만들 수 있는 경우 76→0.
미관찰 3-node 경로는 aggregate graph를 자유 순회할 때의 위험이며, 현 adapter가 실제로 그 경로를 생성했다는 주장이 아니다. 현 adapter는 관찰 medoid 경로를 출력한다.
C의 B 2개는 기존 경계 오류가 들어 있는 PM-011, PM-012다. M02 직접 절차 비교 시 다른 업무 step이 섞이거나 node 의미가 손실될 가능성이 있으므로 영향 가능성을 명시한다. GT step이나 공식 점수로 판단하지 않았다.
별도로 HTTP method를 node key에 보존하지 않는 v1 생성기 특성은 남는다. 동일 BU 내부까지 포함한 GET/write 병합 node는 7개로 그대로다. 이번 scope에서 생성기/adapter는 변경하지 않았다. event evidence를 통해 원래 method는 추적 가능하다.

## 선택 근거와 제한

순수 GRU A0는 silhouette이 가장 높지만 대부분의 업무를 합쳐 표현 목적을 충족하지 않는다. B는 geometry 점수가 높지만 반복 일치가 18/20이고 혼합 pair가 6개 남는다. C는 v1보다 silhouette/DBI가 개선되고 19/20 반복 일치, 혼합 pair 2개, cross-business graph 연결 위험 0으로 균형이 가장 낫다. 차원이 1152로 증가하지만 추가 neural model/학습은 없다. Purity만으로 선택하지 않았다.
모든 후보는 동일 입력 재실행 결과가 일치하며 input permutation 후 cluster ARI도 1.0이다. cluster 수/threshold 선택은 현재 61개 workflow 전체를 이용한 transductive DEVELOPMENT 분석이다. 새로운 실행에서의 성능은 아직 증명되지 않았다.
추가 수집 없이 목적 대부분은 개선되었다. 다음 검토 대상은 최초 화면 진입 차이로 인한 fragment 민감도와 inherited map method/variant 표현이다. Boundary model을 이번 변경으로 바꾸지 않는다. 현재 상태를 전체 시스템 unseen validation 준비 완료로 판정하지 않는다.

**최종 판정: B. CLUSTERING_NEEDS_MINOR_ADJUSTMENT**
