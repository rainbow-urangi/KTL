# Official Evaluation Data Matrix

확인: 2026-10-08. 기준: [R&D_COMPLIANCE.md](../../R&D_COMPLIANCE.md), 최신 KTL 확인서 p.6–11. 현재 `backend/config.json`의 공식 manifest 등록은 모두 비어 있습니다. 아래 수량은 수집·확보 체크리스트이며 공식 측정 완료를 뜻하지 않습니다.

| Metric | Official input | Fixed count | Training use allowed? | Current readiness | Missing item |
|---|---|---|---|---|---|
| M01 | 5 시나리오×2 독립 세션×10 필수 이벤트 | 100건 / 10세션 / 6필드 / 8유형 | N/A, 시험 근거 보존 | MISSING: 수신 API·산식 준비 | 시나리오/필수 목록, 실제 수집·매칭 근거, 공식 manifest |
| M02 | TD-03 20종 수행 로그 + TD-04 GT5 | 20업무 / GT5 | GT 학습·추론·군집화 금지 | MISSING: 사후 evaluator·계약 준비 | 공식 로그, GT5, 독립 AI 엔진 산출물 및 전체 절차·ID 연결 |
| M03 | M02와 동일 TD-03 + TD-05 업무 정의 | 20업무×1회 / 분모20 | GT 모델 입력 금지 | MISSING: 계약 있음, generator 연결 미완료 | TD-03/05, generator 및 단계 순서·action/target 성공 판정 연결, 실제 생성 결과·20회 근거 |
| M04 | 사전 고정 TD-08 Selenium/Python 스크립트 | 20건×1회 / 분모20 | N/A | MISSING: 수신 API·산식 준비 | 수정하지 않은 코드20건, scenario_id/assert, 고정 hash, 전체 실행 로그 |
| M05 | 학습·개발 미사용 held-out 정답 이벤트 | 200=KEEP100+REMOVE100; 제거4종×25 | NO | MISSING: F1·held-out 검증 준비 | 미사용 평가 데이터, 이력·manifest, cleaning adapter/model version |
| M06 | 승인 V6.2 563×128 embedding + final12군집 label | workflow563 / 차원128 / 군집12 | NO, 고정 측정 전용 | PARTIAL / OFFICIAL_M06_BUNDLE_MISSING | 정확한 embedding matrix, 행 ID 대응 및 승인 source hash·고정 manifest |
| M07 | M03 생성 시나리오 → LLM 실제 생성 코드와 검사·실행 결과 | C2=generated_code_count | GT 모델 입력 금지 | MISSING: 수신 API·산식 준비 | 실제 생성 코드와 syntax/실행 전체 근거, M03 연결, 정확한 LLM API identifier |

## M06 읽기 전용 bundle 감사

- 존재: `model/v6_2/frozen/diagnostics/workflow_consensus_assignments.csv`의 workflow ID 563개(중복 없음), workflow_idx 0–562, final `consensus_cluster` 12종.
- 해당 CSV SHA-256: `c64452cb65487b4ba1993af274aef2b0651e3c0a150972077c8c40a0bf2e2648`.
- 미확인/누락: **563×128 workflow embedding matrix**. 기존 `model_bundle.pt`는 모델 checkpoint이며 측정 embedding matrix가 아닙니다. confidence/margin 컬럼은 embedding을 대체하지 않습니다.
- CSV 내부 workflow_idx/ID 연결은 있으나, 누락된 embedding 행과의 대응·matrix hash는 검증할 수 없습니다. 따라서 전체 측정 bundle의 source hash와 사전 고정 기록도 완결되지 않았습니다.
- 80차원 DEVELOPMENT feature와 새 사이트 결과는 공식 자료로 전환하지 않습니다. 실제 DBI 측정, inference, reconstruction, clustering은 이번 감사에서 수행하지 않았습니다.

확보 계획: 승인 당시 실행의 원본 보관처에서 563×128 workflow embedding export, 그 행의 workflow ID 목록, 동일 실행의 final cluster assignments와 run/source hash를 확보합니다. CSV ID/label과 대조 후 **승인 원본에서 나온 bundle임을 확인**하고 공식 evaluation 디렉터리에 별도 고정합니다. 승인 원본을 확보할 수 없다면 사용자/KTL과 확보 방법을 확인하며 모델을 재실행해 대체물을 만들지 않습니다.

## 수집 전 체크

TD-03 20개 업무와 그중 GT 평가대상5개, TD-05 20개 업무 정의를 먼저 확정합니다. M01은 필수 이벤트100건·필드6종·유형8종·독립세션10개를 사전 설계합니다. M05는 개발에 사용하지 않을 별도 held-out 모집단과 보관 경로를 확정합니다. M02/M03 데이터는 공용이므로 두 번 수집하지 않습니다.
정확한 환경 버전과 기관의 KTL 인정 여부 확인은 root compliance의 TODO를 따릅니다. 등록·자동 검사 성공만으로 데이터의 실제 수행 사실이나 held-out 이력을 인증하지는 않습니다.
