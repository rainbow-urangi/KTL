# CURRENT_STATE — 총괄 초기화

작성일: 2026-10-26. 상태: **PASS (INIT-01 초기화 문서 독립 재검증)**. 제품 공식시험 완료를 뜻하지 않는다.
기준 checkout: `/Users/sooeunkim/workspace/RainbowKTL`, branch main, HEAD `d033c0920bff01861af10ba8d1e0050574a62adf`.
시작 상태는 미추적 `docs/compliance/source/KTL_TEST_CRITERIA_FINAL.pdf` 하나뿐이었다. 사용자 PDF를 보존한다. 이번 변경은 docs/agents의 세 문서 생성뿐이며 제품 코드·기존 기준 문서·모델·데이터·PDF·보호 산출물은 변경하지 않는다. commit/push 및 큐의 후속 구현은 실행하지 않는다.

## 권위와 원문 확인

사용자 확정 우선순위: **FINAL PDF → R&D_COMPLIANCE.md → 연구개발계획서 → 과거 KTL 초안/문서**. FINAL의 작성일 표기가 2026-09-18이어도 사용자 지정 최신 기준이라는 권위는 확정되어 있다. 기존 문서의 “최신 서명본 미확보”를 현재 권위 미확정 사유로 사용하지 않는다. FINAL 내부 상충은 별도 확인 대상으로 보존한다.

- 원본: `docs/compliance/source/KTL_TEST_CRITERIA_FINAL.pdf`, 11페이지.
- SHA-256: `5cdfe8e0abdc6eff552f419681182d4c897a886f1df3cdc9cb5dadc75fb22768`.
- macOS Swift/PDFKit으로 p.1–11 전체 텍스트를 실제 읽었다. PDFKit/AppKit으로 로컬 렌더링하여 텍스트에서 누락된 p.3 시험구성도, p.4 환경 표, p.6–11 표/수식/수량을 시각 확인했다. 외부 서비스 전송 없음. 임시 추출/이미지는 /tmp에만 생성했다.
- AGENTS.md와 R&D_COMPLIANCE.md 전체 확인. 저장소 및 상위 workspace/user `.agents/skills`를 확인했으나 해당 디렉터리는 없었고, 사용 가능한 executor skill 목록에도 PDF skill은 없었다. 별도 설치 없이 OS PDFKit 사용.

## FINAL 요구와 현재 구현의 구분

| Metric | FINAL 요구 / 페이지 | 현재 구현·준비 상태 |
|---|---|---|
| M01 | p.6: `0.5*C1+0.3*(100-C2)+0.2*C3`, ≥65%; 필수 이벤트10건. 방법3은 “시나리오1종 각각1회”와 “총10개 독립 세션”을 함께 기재 | legacy 수신 endpoint와 산식 존재. 기존 OFFICIAL_SPEC은 5종×2회, 회당10/총100, 6필드/8유형을 강제(`backend/official_contracts.py:5`). FINAL은 5×2·총100·필드6·유형8을 명시하지 않음. 수량 해석 확인 전 변경/시험 금지 |
| M02 | p.6–7: TD-03 업무20종, 그중 GT5종; Accuracy=직접 정답/생성맵 전체 절차, Completeness=포함필수/GT전체필수; 기하평균 ≥75%. 보조 evidence 직접 정답 금지 | `backend/evaluators.py:102` v1.1, Unicode 정규화/승인 alias/동일 process ID 일대일 direct만 매칭, 모든 생성 절차 분모 유지. 공식 TD-03/GT/모델 산출물 미등록. provider는 연결된 결과를 검증하며 실제 엔진을 실행했다는 사실을 자동 입증하지 않음 |
| M03 | p.8: M02와 같은 TD-03, TD-05 업무10종, JSON Schema·단계순서·action/target 성공검사, ≥80% | generate API와 결과 접수 API 존재; OFFICIAL 분모10. MOCK은 합성·공식 금지, REAL adapter 비어 있음. `backend/m03_integration.py:33`, `backend/config.json:12` |
| M04 | p.8–9: 수동수정 없이 사전 고정한 Selenium/Python 스크립트10건, scenario_id/assert, 한 번 일괄 실행; 정상완료/전체실행 ≥90%, 오류·중단 FAIL | 외부 결과 수신/계산 존재; 공식10 및 실패 분모 유지. 서버가 Selenium을 직접 실행하지 않음. 실제 코드 archive/hash/고정 기록/전체 로그 필요 |
| M05 | p.9–10: REMOVE 양성 F1 ≥0.79; 학습·개발 미사용. TD-06은 총20·remove10·keep100, TD-07은 200·remove100(4종각25)·keep100, 주석 총200으로 내부 상충 | `backend/evaluators.py:171` F1/TP/FP/FN/TN 구현. `backend/official_contracts.py:11`, `backend/data_sources.py:216`은 기존200/100/100 강제. cleaning adapter 및 version 미설정. **200이 FINAL의 유일 확정 수량이라고 선언할 수 없음** |
| M06 | p.10: AI 업무패턴 분석 엔진의 workflow embedding + cluster label; DBI≤1.0, Si/Mij 최대비 평균, sklearn 교차확인. V6.2/563/128/12 제한 없음 | generic DBI evaluator(`backend/evaluators.py:190`)와 별개로 OFFICIAL provider는 V6.2/563×128/12를 강제(`backend/data_sources.py:199`). stale 계약 때문에 현재 OFFICIAL_M06_BUNDLE_MISSING 경로 유지. 이는 현재 코드 상태이며 FINAL 필수조건이 아님. 새 엔진 산출물을 자동 공식 승격하지 않음 |
| M07 | p.10–11: 시나리오20종 각1회, Selenium Python 코드20개, C2=20; AST/py_compile 문법검사 후 동일 M04 Runner 실행; 두 검사 모두 PASS/C2 ≥80% | 공식 고정20·개별 cases 교집합 서버 재계산 존재(`backend/external_results.py:47`). 비공식 generated_code_count 가변분모는 호환 정책일 뿐 공식 기준 아님. 실제 LLM/Runner 호출 연결·증거 없음 |

M01의 필수 이벤트10건과 독립 세션10개 문구는 그대로 기록하며 총100건으로 외삽하지 않는다. M05 수량 상충을 단순 오타라고 자가 수정하지 않는다. M05 원문 “정답 라벨 포함 데이터셋을 AI 정제 모듈에 입력”은 평가 보관 구조와 inference 입력을 구분해야 한다. AGENTS.md의 GT evaluation-only 규칙에 따라 label/category는 모델로 보내지 않는다(`backend/data_sources.py:218`, `backend/contracts.py:64–72` cleaning_payload 정의 및 `backend/server.py:118` adapter 호출 전 적용).
M02 TD-03 20종과 M03 TD-05 10종은 서로 다른 범위다. 동일 로그를 공유한다는 이유로 업무 ID 집합 전체가 같아야 한다고 요구할 수 없다(`backend/data_sources.py:177`의 집합동일 검사는 검토 필요).

## 제품·모델·validation candidate

- V6.2 frozen/reference/runtime은 보호한다. 승인 수량은 32,273 events / 5,167 segments / 563 workflows / 1,619 instances / 12 models (`AGENTS.md:5`). 이 수량은 보호 기준이며 FINAL M06 입력 수량으로 전용하지 않는다.
- workflow_candidate_v1_2는 DEVELOPMENT 후보. README:26의 GRU boundary 입력428차원, representation C_full 1152차원, average/cosine Agglomerative. README:96의 과거 개발 결과: F1 0.9828, R3 0.9444, exact56/60, DBI0.4168, purity99.65%, mixed-risk2개, group fold F1 0.8333/0/0.7143. 이번 재측정 아님, 공식 점수 아님.
- README:45–49: INTERNAL DEVELOPMENT HOLDOUT이며 R3를 이미 오류분석에 사용하여 독립 unseen 아님. README:98 판정 BOUNDARY_NEEDS_MINOR_ADJUSTMENT.
- `model/workflow_candidate_v1_2/VALIDATION_CANDIDATE_MANIFEST.json:3` 상태 FROZEN_FOR_UNSEEN_DEVELOPMENT_VALIDATION, final_product_freeze=false, official=false, official_pass=null. 2026-10-15 snapshot, validation timezone Asia/Seoul. model.pt 기록 hash `1832314d23fa44962eb17fc85d5000477476aed7e0508ee9fd8ed93a869f741e` (이번 전수 hash 검증은 하지 않음).
- validation_snapshot/README.md:9–17: 개발60 workflow/21 cluster reference, transductive clustering이며 unseen assignment/rejection rule 미정. threshold0.25는 개발 clustering 선택값으로 unseen rejection threshold가 아니다. snapshot 덮어쓰기/튜닝 금지. src/run.py는 학습·산출물 갱신 명령이라 실행하지 않음. snapshot 존재는 unseen 검증 완료가 아님.

## 데이터 구조 (manifest/read-only inventory 기준)

| 구분 | 현재 경로·상태 | 한계 |
|---|---|---|
| DEVELOPMENT | data/development/current_site_20x3_v1/v2/v3, recollection_01/02. v3 dataset_manifest.json:49는 업무20/실행60; README의 논리 입력866 events. data/evaluation/current_site_dev_01는 4×2=8실행/273 events, dev_02는320 events/1 session/243 tasks | manifest/기존 문서의 기록값이며 이번 데이터 검증/재계수 아님. dev_02의 실행 수는 행수로 추정하지 않음. 공식 전환 금지 |
| VALIDATION | 위 validation_snapshot 및 상위 후보 manifest 존재. 별도 data/validation 디렉터리는 현재 inventory에 없음 | 새 독립 unseen 데이터의 확보/승인·평가 완료 증거 미확인. snapshot/reference를 validation 입력으로 재사용해 독립성 주장 금지 |
| OFFICIAL | backend/config.json:16–24의 M01–M07 official_manifests 전부 null; data/evaluation에는 DEVELOPMENT/Mock manifests만 확인 | 등록된 공식시험 데이터/완료 성적 없음. M01/M05 상충 해소, M06 계약 정비 후 별도 반입·승인 필요 |
| REFERENCE/Mock | data/evaluation/mock-dataset-01는 synthetic REFERENCE. V6.2 frozen artifacts는 historical reference | Mock 성공/기존 개발 점수를 공식 증거로 바꾸지 않음 |
| 향후 training | 정책은 data/training/raw 신규 schema CSV; 현재 실재하는 training 하위는 v6_2_source, data/reference/v6_2_source와 raw는 inventory에 없음 | AGENTS.md 정책 경로와 실제 보관 위치의 차이를 기록만 함. 이동/학습/하드코딩하지 않음 |

## 외부 API contract와 Mock

현재 문서 `docs/external-integration-api.md:15` 및 구현을 읽어 확인한 계약이다. 실제 HTTP 호출은 하지 않았다.

- POST /api/m03/generate: business_unit_id/workflow_id, 기본 DEVELOPMENT/MOCK. 결정론적 합성 scenario/steps, synthetic=true, official_pass=null. MOCK+OFFICIAL 422; REAL 미설정503 (`backend/m03_integration.py:54`).
- POST /api/integrations/{m03|m04|m07}/result: metadata external_run_id,dataset_id,run_mode,source_module,source_version,submitted_at,dataset_manifest_sha256와 details/evidence. M03 scenarios, M04 counts 및 선택 cases, M07 counts/공식 개별 cases. 등록 dataset/manifest hash 검증, 클라이언트 score 무시, 서버 재계산. 성공201/중복409/계약오류422. 생성 성공은200.
- M03 공식 고유 업무10/분모10, M04 total10/성공/실패 일관성, M07 요청·생성20/분모20·syntax와 execution 교집합. 실패 시도는 분모 유지하고 누락 실행을 임의 성공/0점으로 만들지 않음.
- results/<mode>/<run_id>/received_payload.json,result.json,evidence.csv,run_manifest.json 저장 계약. 이번 저장 실행 없음. REFERENCE/DEVELOPMENT official_pass=null.
- Sandbox는 mock-dataset-01/REFERENCE 예시8/10,9/10,16/20. 실제 generator/LLM/Selenium 실행 없음. evidence URL 보관만 하며 수행 사실 인증 아님.
- legacy M01 endpoint 유지. M06 신규 integration API 없음. backend/contracts.py Protocol과 실제 외부 실행 adapter 연결은 구분한다.

## stale requirement 목록 — 이번에는 수정하지 않음

아래 파일:줄은 현재 checkout 기준. 과거 snapshot·results·초안은 역사자료로 보존하며 현행 기준으로 인용하지 않는다.

| ID | 현재 잔존 위치·값 | FINAL과의 차이 / 조치 후보 |
|---|---|---|
| S01 | R&D_COMPLIANCE.md:9–16, docs/external-integration-api.md:4, docs/integration-update-20261026.md:3 | CURRENT PDF 중심 및 최신 서명본 미확보 설명. 사용자 확정 FINAL을 최우선으로 출처 갱신 필요 |
| S02 | R&D_COMPLIANCE.md:24, backend/official_contracts.py:5–6 | M01 5×2/총100/6필드8유형. FINAL p.6의 명시 수량과 다름/미기재. 내부 세션 모순 확인 필요 |
| S03 | docs/evaluation-spec.md:34–35,96; docs/data-contracts.md:130–138; docs/compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md:9–10 | M03/M04 20건/분모20 및 M03 성공검사 미연결 설명은 FINAL p.8–9(10/10) 및 현재 integration 코드와 불일치 |
| S04 | R&D_COMPLIANCE.md:29,59–61; backend/official_contracts.py:12; backend/data_sources.py:201–208; docs/data-contracts.md:109–110; docs/evaluation-spec.md:15,66; docs/compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md:12; tests/test_official_compliance.py:53–84 | V6.2/563/128/12 및 특정 bundle만 공식 허용. FINAL p.10에 없는 제한. frozen 보호는 유지하되 현행 엔진 output 계약으로 별도 변경 설계 필요 |
| S05 | docs/evaluation-spec.md:38,97; docs/compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md:13 | M07 공식/비공식 구분 없는 generated_code_count 가변분모. FINAL p.11 공식 C2=20. backend/external_results.py:54 비공식 호환은 유지 가능 |
| S06 | R&D_COMPLIANCE.md:28,55; backend/official_contracts.py:11; backend/data_sources.py:216–217; docs/data-contracts.md:120–122; matrix:11 | M05 200/100/100만 유일 기준처럼 제시. FINAL p.9는 일부200과 일치하나 TD-06 총20/remove10/keep100과 충돌. **stale 확정값 교체가 아닌 내부 원문 확인 BLOCKED** |
| S07 | backend/data_sources.py:177–181 | M02/M03 업무ID 집합 동일 강제. FINAL p.6/8은 TD-03 동일, 업무20/TD-05 10을 구분. 실제 두 manifest 등록 시 호환 위험 |
| S08 | R&D_COMPLIANCE.md:82–92 | 시험환경 전부 TODO. FINAL p.4는 PC/서버 OS·CPU·RAM·GPU·SW 버전 명시. 실제 배치 검증은 별개이며 Selenium/LLM exact identifier는 FINAL에도 없음 |

p.4 문서상 PC: Windows11 Pro64, i7-14650HX,32GB,2TB,RTX5060 Laptop8GB,Chrome152.0.7977.82/Collector1.0. 서버: Ubuntu26.04 LTS64,i7-6900K,128GB,1TB,RTX3090 24GB,Docker29.1.3,Node18.20.8,Python3.12.3,PyTorch2.13.0+cu132,MariaDB11.4.10. 이 표는 FINAL의 요구/기재값이며 현재 Mac 실행환경 또는 실제 시험장 설치 확인값이 아니다.

## 해결·미해결·승인 경계

해결된 문서 초기화 사항: FINAL의 실제 전 페이지 열람 및 권위/해시 확정, 현재 구현과 요구값 구분, stale 목록/후속 큐/검증 baseline 작성. 기존 구현에서 M03/M04/M07 10/10/20·실패 분모·Mock 공식 차단·M02 direct-only가 확인되지만 이번 독립 테스트 PASS는 아니다.
미해결: M01/M05 원문 내부 상충, M02/M03 공유로그와 서로 다른 업무범위 계약, M06 stale 고정계약, REAL 생성/정제/Runner/LLM 연결, 공식 input provenance/환경/시나리오 연결, 독립 unseen 평가와 transductive 정책. KTL 성적서 관리기관 인정 여부도 별도 행정 확인 대상(R&D_COMPLIANCE.md:80).
기존 자율 권한: 일반 코드 수정, 문서 동기화, 테스트 및 regression 수정. 이번 초기화와 Development Fix Task는 세 문서만 허용하므로 후속 제품 구현을 지금 실행하지 않는다. 이는 일반 작업에 새 사용자 승인이 필수라는 뜻이 아니다. FINAL에 없는 M06 고정조건 제거도 이번 범위 밖이므로 큐에만 둔다.
사용자 승인 필수 6종: (1) 모델 architecture의 큰 변경 (2) KTL 공식 시험 기준 변경 (3) OFFICIAL 데이터 정의 변경 (4) 외부 API contract의 breaking change (5) 최종 model freeze (6) 공식 시험 데이터 사용. M01/M05 원문 모순 해석은 사용자/KTL 확인을 유지한다. 엔진/환경 조사·일반 adapter 구현·합성 회귀 자체에 일괄 재승인 조건을 추가하지 않으며, 위 6종 또는 보호 변경에 해당하는 실제 행위는 별도 승인 경계를 적용한다.
별도 보호: V6.2 frozen/reference/runtime의 재학습, boundary logic/prototype clustering 변경, 출력 재생성 및 승인 artifact 변경은 명시 사용자 지시 없이 금지. validation snapshot 덮어쓰기/튜닝 금지. GT는 평가 전용이며 모델/생성/학습으로 전달하지 않는다. 결측 증거는 0점/성공으로 대체하지 않고 실패 시도는 분모에 유지하며 보조 process evidence는 direct match로 자동 집계하지 않는다.


## DEV-FIX-INIT-01 — CSV 재계산 준비도 보완 (2026-10-26)

FINAL p.2의 Excel/산출 근거 CSV 요구에 대해 **코드 정적 대조만 완료**했다. 실제 export→CSV 재계산 비교는 모든 지표 미실행이다. 아래 “가능”은 유효하고 완전한 성공 결과 rows의 산술 재계산 가능성을 뜻하며, 실제 외부 수행·공식 적합성·원시 입력의 완전성 검증 완료가 아니다. 오류/결측 시 status-only CSV는 점수 재계산 근거가 아니다.

| 지표 | CSV 단독 산술 재계산 범위 | 추가 입력 및 미검증 범위 | 실제 코드 근거 |
|---|---|---|---|
| M01 | count 행이 있으면 C1=100×collected_required_event_count/defined_required_event_count, C2=100×missing_required_field_count/(total_collected_event_count×required_field_count), C3=100×collected_event_type_count/defined_event_type_count 및 가중합 가능 | optional cases가 비어 있지 않으면 counts 대신 cases만 export될 수 있어 count 필드 보장 안 됨. 이 경우 result.details.raw_counts/received_payload.counts 필요. count 진위는 TD-01/수집 원시 이벤트·필드·유형·매칭 근거 필요. 원문 수량 모순 미해결 | external_results.py:25–32,58–80 |
| M02 | direct_match=True 수=m, 비어 있지 않은 detected_id 수=a(전체 생성절차), 전체 rows에서 detected_id 없는 미매칭 GT 행도 포함해 GT 행 수=g를 복원하여 sqrt((100m/a)×(100m/g)) 가능. g는 ground_truth_step 또는 direct_match 또는 detected_id 없는 GT 행으로 식별(공백 GT label도 고려) | 라벨/alias 및 동일 process ID의 일대일 direct 판정 재검증에는 원 생성맵·GT·승인 alias 계약 필요. CSV에는 원 evidence_type/GT step ID/alias 계약이 없어 보조 증거 배제 판정 자체를 독립 입증하지 못함 | evaluators.py:133–168 |
| M03 | success=True 수/전체 시도 rows×100; OFFICIAL은 10행/분모10 확인 필요 | schema_valid/step_order_valid/action_present/target_present flags의 타당성 재판정에는 원 scenarios/steps와 입력 업무목록 필요. CSV는 생성 모듈 실제 수행 증거 아님 | m03_integration.py:10–46 |
| M04 | counts-only 행이면 성공/total×100. cases 행이면 status=PASS 수/전체 cases 수×100(FAIL/ERROR/TIMEOUT/SKIPPED 포함), 공식은10 확인 | cases 선택 시 원 count는 CSV가 아닌 result.details.raw_counts와 received_payload.counts에 남으므로 상호 일관성 확인에 JSON 필요. 실제 정상완료/assert/실패 로그 및 TD-08 archive/hash/고정 이력은 별도 필요 | external_results.py:33–42,58–80 |
| M05 | expected/predicted의 REMOVE 양성 TP/FP/FN/TN, Precision/Recall/F1=2TP/(2TP+FP+FN) 재계산 가능. 0분모 처리도 코드와 대조 | 원 이벤트/예측 ID의 일치·전체성, held-out/미사용 이력과 실제 cleaning model/version 수행 증거 필요. CSV로 모델 GT 미전달 전체 경로를 입증하지 못함. FINAL 수량 모순 보존 | evaluators.py:173–187 |
| M06 | cluster별 max_ratio 평균만 재계산 가능; scatter/workflow_count도 export됨 | centroid와 쌍별 거리 Mij가 CSV에 없어 scatter와 max_ratio를 처음부터 검증 불가. 원 workflow embedding/labels와 ID·행순서 mapping으로 전체 DBI 및 sklearn 교차검증 필요. 모델 재실행/재군집화로 보충 금지 | evaluators.py:192–214; server.py:123–132 |
| M07 | cases이면 generation_status/syntax_status/execution_status 모두 PASS 교집합/공식20×100. 비공식은 generation_status PASS 수(생성 코드 수)를 분모로 사용하며 전체 요청 행수를 그대로 쓰지 않음. counts-only 비공식은 both_pass_count/generated_code_count×100 | 공식 cases 필수. CSV 자체에 mode/공식 분모 정책 보장 없으므로 result/received_payload로 모드·고정20·count 일관성 확인. 실제 소스 코드·문법검사/동일 M04 Runner 로그·시나리오/프롬프트 연결 별도 필요 | external_results.py:43–80 |

공통 exporter는 evaluators.py:85–99(csv_evidence): UTF-8 BOM, dict/list JSON 직렬화, =/+/-/@ 시작 문자열 앞 apostrophe 처리이므로 원 label 비교 시 export escaping을 고려한다. run_storage.py:22–34는 rows 또는 status fallback을 CSV로 쓰고 result/manifest/received payload를 저장한다. server.py:151–158의 내부 M02/M05/M06 저장 경로도 rows를 같은 exporter에 전달한다. JSON/파일 존재만으로 원시 사실이나 CSV 재계산 성공을 주장하지 않는다. 결과 파일 자체 hash는 manifest에 자동 저장되지 않는다. 재검증자는 합성 fixture와 임시 출력만으로 위 경로별 계산을 비교할 수 있다.

F01 권한 구분, F02 위 정적 근거/한계, F03 cleaning_payload 참조를 보완했다. 상태 **READY_FOR_VERIFICATION**, 자체 PASS 아님. 기존 독립 FIX_REQUIRED 이력과 S01–S08 및 FINAL 모순은 보존한다.


## VER-INIT-02 초기화 상태 동기화 — 2026-10-26

INIT-01 **PASS**. F01–F03 해결은 VALIDATION_REPORT의 VER-INIT-02-INDEPENDENT에서 독립 확인했다. 위 READY_FOR_VERIFICATION은 보완 당시 이력으로 보존한다. 제품 공식시험/실제 export 재계산 완료 선언이 아니며 S01–S08, M01/M05 원문 상충 및 제품 task는 미해결 그대로다.


## M02 Phase1 — 2026-11-03 READY_FOR_VERIFICATION

User approved readiness and ordered M02 first. Development adapter/web/TD-04 transcript implemented, but Phase1 is incomplete: actual score is null (DIRECT_PROCEDURE_MAPPING_REQUIRED), not 0 or PASS. 21 frozen maps/176 canonical occurrences versus27 PDF procedures require a validated direct equivalence/granularity contract; raw labels/node evidence cannot become direct matches. Six synthetic tests added;114 unit tests and frontend/HTTP checks pass. See M02_PHASE1_DEVELOPMENT_REPORT.md for exact evidence, limitations and separate Verification Task request. Model untouched; Phase2/3 not started.

## M05 사용자 결정 20건 계약 (2026-11-11 갱신) — 최신 운영 기준

사용자 직접 결정으로 총20건(REMOVE10/KEEP10), 학습·DEVELOPMENT tuning 미사용 held-out, 1회 일괄 평가, F1≥0.79를 적용한다. REMOVE category는 실제 raw에서 객관적으로 확인 가능한 duplicate/noise/repeated_action/irrelevant_action 중 하나이며 category별 고정 quota는 없다. remove_category는 evidence/설명용 metadata이고 binary REMOVE/KEEP F1을 평가한다. prediction을 본 뒤 target이나 label을 변경하지 않는다. 기존 본문/구형 evaluator의 200/REMOVE100/KEEP100 및 각 category25는 **STALE REQUIREMENT / 역사 기록**이다. FINAL PDF는 수정하지 않았으며 사용자 결정은 KTL 승인 증거가 아니다. 공식 성적서 수용 확인은 별도다.

현재 M05 구현은 `backend/m05_full_context.py`, 별도 웹 `python3 -m backend.m05_readiness_web` (localhost:8768). 동결 정제 엔진은 그대로 유지하며 전체 raw sequence를 1회 처리한 후 사전 잠금 target20만 평가한다. M02 frozen dependency인 기존 server/evaluator/config/frontend 파일은 변경하지 않았다. 따라서 기존 main web의 구형 M05 경로는 stale, 사용 금지이며 별도 화면이 현재20건 경로다. 실제 target20의 독립 blind label lock 및 완전한 held-out 감사·승인이 대기 중이므로 측정 BLOCKED이고 score/confusion/Precision/Recall/F1은 미산출이다. 임시 합성 fixture는 테스트 전용이며 실측 evidence가 아니다.

평가 데이터는 `data/held_out/m05/<dataset>/`에 분리한다. 각 event의 event_id/expected_label/remove_category/held_out/features, dataset SHA-256, training 및 development 이력 inventory SHA-256, event ID+feature content hash 비중복 검증, 이력 completeness reviewer/감사 근거를 요구한다. 선언만으로 held-out 증명하지 않는다. 모델에는 id/features만 전달한다. 중앙 evaluator가 raw prediction으로 TP/FP/FN/TN 및 P/R/F1을 계산한다. evidence CSV는 event_id, expected_label, predicted_label, remove_category, classification, model_version/model_sha256, dataset_sha256을 포함한다.

TODO: 실제 held-out20건과 전체 사용 이력 감사/정제 engine artifact+adapter+version/hash 확보 → 별도 Independent Verification → 실데이터 1회 측정 → 실제 브라우저 실행/결과/CSV 다운로드 검증. 모델 tuning 금지. M02 77.29% freeze와 M06/M03 상태는 유지.


### M05 DEVELOPMENT 2026-11-12 사용자 승인 측정
417 full-context / locked target20, frozen engine 단1회. TP0 FP0 FN10 TN10, F1 0.00 (목표0.79 미달). strict provenance 한계는 보존하되 이번 DEVELOPMENT blocker 아님. raw/GT/engine 불변, 추가 engine 개선은 승인 대기. `docs/agents/m05_development_measurement_20261112/` 참조. Independent Verification 진행 대상.
