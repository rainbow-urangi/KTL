# Workflow candidate v1 DEVELOPMENT 보고서

**INTERNAL DEVELOPMENT HOLDOUT — NOT INDEPENDENT UNSEEN VALIDATION**

CPU 단방향 GRU: projection 64 → GRU 64×1 → MLP 32 → sigmoid. 파라미터 52,481개.
전체 866 events. 학습 positive 38, negative 518. weighted BCE 사용.

| 모델/분할 | Precision | Recall | F1 | 예측 boundary |
|---|---:|---:|---:|---:|
| rule/all_development | 0.7627 | 0.7759 | 0.7692 | 59 |
| rule/training | 0.7692 | 0.7895 | 0.7792 | 39 |
| rule/internal_holdout | 0.7222 | 0.7222 | 0.7222 | 18 |
| neural/all_development | 0.9661 | 0.9828 | 0.9744 | 59 |
| neural/training | 1.0000 | 1.0000 | 1.0000 | 38 |
| neural/internal_holdout | 0.8947 | 0.9444 | 0.9189 | 19 |

위 표는 ±1 event, 동일 source session 내 one-to-one 매칭. exact 결과도 JSON에 보관. 세션 시작은 모델 예측이 아니므로 경계 성능에서 제외.
예측 workflow 61, exact segmentation 55/60, 과분할 execution 3, 병합된 predicted workflow 2.
Embedding 384차원. cluster/process model 10개. silhouette 0.8449639081954956, DBI 0.47002456140744286 (DEVELOPMENT, 공식 M06 아님).
동일 BU 세 반복의 대표 cluster 일치 20/20; event-weighted purity 0.6686. 분할 fragment를 event 수 최다 cluster에 귀속하는 진단이며 exact grouping 성공률이 아님.
BU 그룹 3-fold neural F1 평균 0.2000. 서로 다른 split에서 얻은 참고 진단이며 공식 일반화 성능이 아님.

## 혼동 진단

| 업무 pair | 같은 cluster 실행 pair / 전체 |
|---|---:|
| BU04 / BU05 | 9 / 9 |
| BU12 / BU13 | 9 / 9 |
| BU15 / BU16 | 9 / 9 |
| BU18 / BU19 | 9 / 9 |
| BU07 / BU09 | 0 / 9 |
| BU07 / BU11 | 0 / 9 |
| BU09 / BU11 | 0 / 9 |
| BU14 / BU17 | 0 / 9 |
| BU14 / BU20 | 0 / 9 |
| BU17 / BU20 | 0 / 9 |

## 해석과 한계

조회·상세·등록을 같은 cluster로 합친 경우가 많다. 가장 높은 혼동 pair: [('BU02', 'BU03', 9), ('BU04', 'BU05', 9), ('BU06', 'BU07', 9), ('BU08', 'BU09', 9), ('BU10', 'BU11', 9), ('BU12', 'BU13', 9), ('BU12', 'BU14', 9), ('BU13', 'BU14', 9)]. 높은 silhouette과 20/20 반복 일치만으로 업무 구분 성공을 판단하지 않는다.
V6.2 frozen-forward 참고값은 dev_01 273→7 segments→2 workflows, dev_02 320→3→1이다. 이번 866 events와 데이터가 달라 성능 향상을 직접 주장하지 않는다. 구조 OOV는 UNK 대신 결정적 해싱으로 처리하며 기존 모델·API·데이터는 변경하지 않았다.
BU 그룹 F1은 [0.6, 0.0, 0.0]; 규칙 기준은 [0.4615, 0.6667, 0.75]. 내부 반복 holdout 개선이 새로운 업무 유형으로 이어지지 않았다. 이것이 가장 큰 failure mode이다.
과분할/병합이 남아 있으면 프로세스맵 또한 불완전하다. 특히 같은 화면에서 반복되는 조회와 팝업 동작은 task 종료를 명시하지 않아 경계가 모호할 수 있다. 순서·사용자·수행 속도가 다른 연속 원시 세션이 필요하다.
학습 threshold와 epoch는 config에서 사전 고정했다. 최종 downstream 산출물은 neural prediction을 사용하며 baseline보다 개선이 없는 경우에도 결과를 숨기지 않는다.
활성 event 선택 자체에 기존 실행 범위가 사용되었다. 추론은 실행 경계로 분할하거나 상태를 초기화하지 않지만, 이 선별로 만들어진 간격이 경계 단서가 될 수 있다. 미선별 연속 로그 검증이 필요하다.
독립 raw CSV 추론 경로를 제공한다. 자유 입력 텍스트는 제거하고 static title만 허용한다. 사전 학습 semantic encoder는 사용하지 않았다.
기존 M03 API는 변경하지 않았다. canonical adapter는 생성기 전달용 절차/evidence만 제공하며 자동 시나리오 생성 성공을 주장하지 않는다.

**최종 판정: MORE_DEVELOPMENT_DATA_NEEDED**
