# TASK_QUEUE — KTL 시험성적서 최소 준비 순서

2026-11-03 사용자 우선순위 재설정. **KTL_READINESS_ASSESSMENT: READY_FOR_VERIFICATION**. 이번 단계는 코드 수정 없이 조사·DEVELOPMENT 재계산·큐 정렬만 수행했다. 후속 구현은 아직 시작하지 않는다. FINAL PDF 우선, v1.2.1 그대로 유지. 공식 PASS 아님. 상세 근거: [KTL_READINESS_ASSESSMENT](KTL_READINESS_ASSESSMENT.md). 아래 역사적 표와 완료/미해결 이력은 그대로 보존하며 새 우선순위가 과거 “상위5개/첫추천”을 대체한다.

| 우선/Task ID | 목적/최소 결과 | 대상 | 상태 | 선행조건/승인 |
|---|---|---|---|---|
| P0 READINESS-VER-01 | FINAL 원문과 실제 파일/계산/큐 독립 대조 | M02/03/05/06 | READY_FOR_VERIFICATION | 별도 Verification Task. 준비자가 자체 PASS 금지 |
| P0 M02-TD04-READY | PDF ★GT BU03/07/09/17/20 절차를 TD-04 ID/순서/별칭/직접매핑 계약으로 문서화·확정; 다섯 raw evidence 이미 확보 | M02 | TODO | 사용자 절차/매핑 검토. BU01/04/12/15/18 종료 AMBIGUOUS는 blocker 아님. GT 모델 입력 금지 |
| P1 M06-01 | 이미 목표 충족한 22×1152/21 출력 DBI0.318206를 기존 웹 입력선택·실행·CSV·재계산에 연결; stale563/128/12 제거 | M06 | TODO | FINAL 및 실제 frozen engine output/hash. 일반 adapter/계약 정비, 모델 변경 없음. OFFICIAL 사용은 별도 승인 |
| P1 M02-MEASURE-01 | 고정 후보 process map serializer와 사전 비교 계약 연결 후 sqrt(A×C) DEVELOPMENT 측정 | M02 | TODO | TD-04 계약; 모든 생성 절차 분모 유지, 보조근거 직접정답 금지. Boundary F1 미사용 |
| P1 M03-READY-01 / M02M03-01 | 사용자 선택 TD-05 열 업무 + 실제 generator 연결; JSON/order/action/target; 10회 실패포함 측정 | M03 | TODO | 열 업무 선택 승인, REAL adapter. 기존20-unit TD-03와10-unit TD-05 부분집합 계약 수정; Mock 성능 대용 금지 |
| P1 INTEGRATION-01 | 주니어 integration API 실제10 scripts/20 codes 수행·실패·archive 근거 연결 | M04/M07 | TODO | 담당자 실제 결과. 현재 개발자의 신규 모델 연구 blocker 아님 |
| P1 WEB-EVIDENCE-01 / DOC-01 / TEST-01 | 기존 측정 페이지 목표/계산근거/CSV download/input hashes/동일값 재계산 대조; stale 문구 동기화, 합성 회귀 | M02/M03/M06 및 통합 | TODO | 위 연결 후 export→독립/Excel 재계산, 새 연구 UI 금지 |
| P2 ENV-01 | FINAL 문서 환경과 실제 설치·exact versions 확인 | 전체 | TODO | 시험 PC/서버 담당자 접근 자료 |
| Parallel CRITERIA-05 / M05-01 | KTL에 TD-06 총20/remove10/keep100 vs TD-07/주석200 확인; cleaning model/version/held-out 미사용 이력 확보 | M05 | BLOCKED | 공식 수량 계약만 KTL 확인 전 BLOCKED. 다른 준비를 막지 않음. label/category inference 금지 |
| Parallel M01-OWNER | 기존 CRITERIA-01 중 M01 수량 확인은 담당자 별도 범위 | M01 | TODO | 현재 개발 담당 범위 밖; 전체 준비 blocker 아님 |
| P2 DATA-01 | 공식 입력 정의/반입/provenance 및 최종 모델 freeze 승인 | 전체 | TODO | DEVELOPMENT를 공식 승격하지 않음. 이번 단계 OFFICIAL 데이터 생성 금지 |
| P3 OFFICIAL-01 | 승인된 입력/환경으로 KTL 실제 측정·전체 evidence 및 성적서 | 전체 | BLOCKED | 각 metric 준비/확인 완료 및 명시 승인; M05 해결은 전체7개 성적서 전 필요 |
| Long-term VALIDATION-01 | MODEL-VAL-01 unseen boundary/generalization diagnostics 보존 | 장기 R&D | TODO | KTL M02/M03/M06 gate로 추가하지 않음. 이번 v1.3/재학습/튜닝 금지 |

가장 작은 계산 완료 항목은 M06이며, **M02는 먼저 TD-04 계약 준비를 우선 시작**한다. 독립검증 이후 최소 웹 연결 M06과 TD-04 문서화를 병행하고 M02 실제 점수 → M03 실제 열 업무로 진행한다. 모델 개선 제안은 M02<75%, 실제 frozen M06 DBI>1.0, 실제 M03 8/10 미만, 또는 process map으로 시험 자체 수행 불가능일 때만 한다. 현재 M06은 목표 충족, M02/M03은 미측정이므로 모델 개선 조건을 확인하지 못했다.

---

## 이전 큐 및 감사 이력 (2026-10-26; 위 새 우선순위로 대체)

# TASK_QUEUE — 초기화 후속 작업

작성일: 2026-10-26. 초기화 문서 상태 **PASS (VER-INIT-02-INDEPENDENT)**. 이번 요청은 초기화뿐이며 아래 후속 구현은 시작하지 않았다. 허용 상태: TODO / IN_PROGRESS / READY_FOR_VERIFICATION / PASS / BLOCKED. 독립 검증 전 PASS 사용 금지.
근거: [CURRENT_STATE](CURRENT_STATE.md)의 PDF 전페이지 근거 및 S01–S08, [VALIDATION_REPORT](VALIDATION_REPORT.md). 최우선 원문은 FINAL PDF, SHA-256 `5cdfe8e0abdc6eff552f419681182d4c897a886f1df3cdc9cb5dadc75fb22768`.

| 우선/Task ID | 목적 | 대상 metric | 예상 변경 범위 | 선행조건 | 상태 | 사용자 승인 필요 여부 |
|---|---|---|---|---|---|---|
| P0 INIT-01 | 세 문서와 실제 파일/PDF 근거를 별도 Verification Task로 검증 | 전체 | docs/agents 세 문서, read-only 대조 | DEV-FIX-INIT-01 F01–F03 문서 보완 | PASS | VER-INIT-02-INDEPENDENT에서 F01–F03 해결 독립 확인; 공식시험 PASS 아님. 최초 FIX_REQUIRED 이력 보존 |
| P0 CRITERIA-01 | FINAL 내부 M01/M05 수량 상충을 사용자/KTL과 명확화 | M01/M05 | 승인된 해석 기록; 원본 PDF 자의 수정 금지 | FINAL p.6,9 시각 확인 완료 | BLOCKED | 필요: M01 시나리오1종1회/총10세션, M05 총20/remove10/keep100 대 총200 해석 |
| P1 DOC-01 | 문서 source priority·수량·API 준비상태 정합화(S01/S03/S05/S08) | 전체 | R&D_COMPLIANCE.md, docs/evaluation-spec.md,data-contracts.md,external-integration-api.md,official matrix, integration update | INIT-01 및 상충 항목은 CRITERIA-01 | TODO | 일반 문서 동기화는 기존 자율 권한; 이번 세 파일 범위 밖이므로 미실행 |
| P1 M06-01 | FINAL p.10에 없는 V6.2/563/128/12 강제조건 제거 설계·구현(S04) | M06 | official_contracts/data_sources/표시 metadata 및 synthetic regression; frozen artifact 변경 없음 | INIT-01, 사용할 엔진/version/output provenance 계약 합의 | TODO | 일반 비breaking backend/합성 회귀는 기존 자율 권한; 이번 범위 밖 미실행. 승인 6종/보호 변경은 별도 |
| P1 M02M03-01 | 공유 TD-03의 업무20과 M03 TD-05 업무10 범위 연결 계약 정리(S07) | M02/M03 | data_sources의 동일집합 검사, integration manifest 계약/문서 및 synthetic tests | INIT-01, TD-05 10개와 TD-03 업무20의 대응 정의 | TODO | 일반 구현/합성 회귀는 기존 자율 권한; 이번 범위 밖 미실행. OFFICIAL 정의 변경/공식 데이터 사용은 승인 |
| P1 M05-01 | 승인 수량 기반 held-out 정제 계약·실제 adapter 연결 | M05 | official_contracts/data_sources/config/adapter 및 synthetic regression | CRITERIA-01, 미사용 이력·모델 version 확보 | BLOCKED | 원문 수량 해석 확인 및 OFFICIAL 정의 변경/공식 데이터 사용 승인 필요; 일반 adapter 구현은 자율. GT 모델 전달 금지 |
| P1 INTEGRATION-01 | 실제 generator/LLM/Runner 결과 연결과 실패/전체 시도 증거 보존 | M03/M04/M07 | 실제 adapter 연동, evidence provenance, archive/hash 및 endpoint 회귀 | INIT-01, 담당 모듈 계약·시나리오10/코드20·실행 환경 확보 | TODO | 일반 adapter 구현/합성 회귀는 기존 자율 권한; 공식 데이터 사용/API breaking 변경은 승인. 이번 미실행; Mock 공식 증거 금지 |
| P2 DATA-01 | 공식 TD-01/03/04/05/06/07/08 반입과 승인 inventory 작성 | 전체 | 승인된 data/evaluation 및 manifest/config; 공식 측정은 별도 | CRITERIA-01, M06-01, M02M03-01 및 공급자료 확보 | BLOCKED | 공식 데이터 채택/반입 승인 필요; dev/reference 자동 승격 금지 |
| P2 VALIDATION-01 | frozen v1.2 candidate의 독립 unseen 검증 프로토콜과 데이터 확보 | 후보/M02/M06 | 새 독립 validation 입력·별도 결과 경로; snapshot 보존 | transductive vs unseen assignment 정책 합의, 독립 데이터 확보 | BLOCKED | 일반 합성 검증 설계/회귀는 자율; 공식 데이터 사용/보호 변경은 승인 경계. 기존 snapshot 튜닝/덮어쓰기 금지 |
| P2 ENV-01 | FINAL p.3–5의 환경 표와 실제 시험장 설치 대조 | 전체/M04/M07 | 환경 inventory/version evidence; 문서상 버전과 실측 구분 | 시험 PC/서버 접근과 실제 담당자 자료 | TODO | 일반 환경 조사/문서화는 자율; 장비 접근 권한 확보 필요, 공식 데이터 사용은 승인. 이번 미실행 |
| P2 TEST-01 | 승인된 변경 범위별 synthetic 회귀 및 결과 누적 | 관련 metric | 임시 fixture/output; VALIDATION_REPORT 기록 | 각 변경 범위 확정·부작용 감사 | TODO | 일반 합성 테스트/regression은 기존 자율 권한; 공식 데이터 사용/보호 변경은 별도 승인 경계 |
| P3 OFFICIAL-01 | 실제 KTL 측정과 evidence/성적서 운영 | 전체 | 별도 승인 시험 입력·results/official; 전체 실패 시도 보존 | DATA/ENV/연동/회귀 및 관리기관 인정 확인 | BLOCKED | 명시적 공식시험 실행 승인 필요; 이번 실행 금지 |

상위 5개는 INIT-01 → CRITERIA-01 → DOC-01 → M06-01 → M02M03-01이다. **첫 추천은 INIT-01 독립 문서검증**이며, 동시에 CRITERIA-01 질문을 사용자/KTL에 전달할 수 있도록 준비한다. 제품 코드를 먼저 고쳐 수량을 추측하지 않는다.

stale 우선근거: M03/M04 과거20은 docs/evaluation-spec.md:34–35 vs FINAL p.8–9의10, M07 가변 공식분모는 동 문서:38,97 vs p.11 고정20, M06 고정563×128/12는 backend/official_contracts.py:12 및 data_sources.py:204–208 vs p.10의 엔진 embedding/labels. M05의 기존200은 FINAL p.9 일부와 일치하므로 무조건20으로 교체하는 작업이 아니다. M01 기존5×2/100도 FINAL p.6 내부 모순 해소 전 확정하지 않는다.


## DEV-FIX-INIT-01 권한 정정 누적 — 2026-10-26

일반 코드·문서 동기화·테스트·regression은 기존 사용자 자율 권한이다. 이번 초기화/보완 범위가 세 문서뿐이라 후속 작업을 실행하지 않는 것과 사용자 승인 필수를 구분한다. 승인 필수 6종은 큰 모델 architecture 변경, KTL 공식 시험 기준 변경, OFFICIAL 데이터 정의 변경, 외부 API breaking change, 최종 model freeze, 공식 시험 데이터 사용이다. V6.2 재학습/boundary/prototype clustering 변경/출력 재생성/승인 artifact 변경은 명시 사용자 지시 없이 금지하며 validation snapshot을 덮어쓰거나 튜닝하지 않는다. GT evaluation-only·실패 분모·결측 증거·보조 evidence 보호 규칙은 CURRENT_STATE와 AGENTS.md를 따른다. M01/M05 해석 확인과 S01–S08은 미해결 그대로다.

F01–F03 보완은 **READY_FOR_VERIFICATION**. 다음 단계는 별도 Verification Task이며 기존 FIX_REQUIRED를 PASS로 바꾸지 않는다.


## VER-INIT-02 종료 상태 — 2026-10-26

INIT-01 **PASS**. 위 상위5개/첫추천 INIT 표기는 검증 전 계획 이력이다. 완료 후 남은 상위5개는 **CRITERIA-01 → DOC-01 → M06-01 → M02M03-01 → M05-01**이며 첫 추천은 CRITERIA-01의 M01/M05 원문 수량 해석 확인이다. 미해결 제품 task 상태는 그대로 유지한다.


## User-approved execution order supersedes earlier priority — 2026-11-03

1. **P0 M02-PHASE1**: TD-04/serializer/web implemented; READY_FOR_VERIFICATION, actual score NOT MEASURED because direct semantic equivalence/granularity remains unresolved. Independent verifier first checks whether an objective typed-signature mapping is possible. If so, Development Fix→tests→reverification; if not, report the exact decision to user. Do not manufacture score or call Phase1 complete.
2. **P1 M06-PHASE2**: frozen artifact/hash/dynamic counts/DBI/sklearn/CSV web connection; NOT STARTED, wait for M02 report. No reclustering/tuning.
3. **P1 M03-PHASE3**: REAL generator minimal connection and candidate10 proposal; NOT STARTED, official10 require user approval. Preserve Mock API contract.
4. **P1 VERIFICATION** per phase: separate task must return PASS/PASS_WITH_WARNINGS/FIX_REQUIRED; fix objective defects autonomously and reverify, do not self-certify.
5. M04/M07 junior API integration; consolidated web/evidence/recalculation/environment; approved official trial/certificate later. M05 only official quantity contract remains BLOCKED pending KTL; M01 not a development blocker.

No v1.3, retraining, validation tuning, OFFICIAL data creation, final freeze or external breaking change. See M02_PHASE1_DEVELOPMENT_REPORT.md.

## M05 사용자 결정 20건 계약 (2026-11-09) — 최신 운영 기준

사용자 직접 결정으로 총20건(REMOVE10/KEEP10), 학습·DEVELOPMENT tuning 미사용 held-out, 1회 일괄 평가, F1≥0.79를 적용한다. REMOVE 권장구성 duplicate3/noise3/repeated_action2/irrelevant_action2는 권장이지 강제하지 않는다. 기존 본문/구형 evaluator의 200/REMOVE100/KEEP100 및 각 category25는 **STALE REQUIREMENT / 역사 기록**이다. FINAL PDF는 수정하지 않았으며 사용자 결정은 KTL 승인 증거가 아니다. 공식 성적서 수용 확인은 별도다.

현재 M05 구현은 `backend/m05_heldout.py`, 별도 웹 `python3 -m backend.m05_readiness_web` (localhost:8768). M02 frozen dependency인 기존 server/evaluator/config/frontend 파일은 변경하지 않았다. 따라서 기존 main web의 구형 M05 경로는 stale, 사용 금지이며 별도 화면이 현재20건 경로다. 실제20건 데이터/미사용 감사 근거/실제 정제 모델이 확보되지 않아 측정 BLOCKED이고 score/confusion/Precision/Recall/F1은 미산출이다. 임시 합성 fixture는 테스트 전용이며 실측 evidence가 아니다.

평가 데이터는 `data/held_out/m05/<dataset>/`에 분리한다. 각 event의 event_id/expected_label/remove_category/held_out/features, dataset SHA-256, training 및 development 이력 inventory SHA-256, event ID+feature content hash 비중복 검증, 이력 completeness reviewer/감사 근거를 요구한다. 선언만으로 held-out 증명하지 않는다. 모델에는 id/features만 전달한다. 중앙 evaluator가 raw prediction으로 TP/FP/FN/TN 및 P/R/F1을 계산한다. evidence CSV는 event_id, expected_label, predicted_label, remove_category, classification, model_version/model_sha256, dataset_sha256을 포함한다.

TODO: 실제 held-out20건과 전체 사용 이력 감사/정제 engine artifact+adapter+version/hash 확보 → 별도 Independent Verification → 실데이터 1회 측정 → 실제 브라우저 실행/결과/CSV 다운로드 검증. 모델 tuning 금지. M02 77.29% freeze와 M06/M03 상태는 유지.
