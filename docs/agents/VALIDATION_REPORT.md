# VALIDATION_REPORT — baseline 및 검증 누적

작성일: 2026-10-26. 문서 Development Task 상태 **READY_FOR_VERIFICATION**. 독립 Verification 결과 **미실행**. 공식 성적/성능 PASS 선언 없음.

## BASELINE-20261026-INIT

| 항목 | 이번 확인/결과 | 한계 |
|---|---|---|
| checkout | main HEAD d033c0920bff01861af10ba8d1e0050574a62adf, 시작 git status는 FINAL PDF untracked만 존재 | 기존 사용자 변경 보존 |
| 허용 변경 | docs/agents/CURRENT_STATE.md, TASK_QUEUE.md, VALIDATION_REPORT.md 신규 작성만 | 제품/평가 backend 변경 없음, commit/push 없음 |
| 원문 | FINAL 11p 전체 PDFKit 텍스트 읽기, p.3/4/6–11 로컬 렌더 시각확인 | PDF 외부 업로드 없음 |
| 원문 SHA-256 | 5cdfe8e0abdc6eff552f419681182d4c897a886f1df3cdc9cb5dadc75fb22768 | 사용자 확정 최우선 기준 |
| 이번 테스트 | unit/regression/HTTP/모델/학습/데이터검증/공식시험 모두 미실행 | 문서만 변경. 전체 suite는 보호 reference 복사/사용 및 runtime 경로 포함하므로 실행하지 않음 |
| 기존 테스트 기록 | docs/integration-update-20261026.md 최종 기록: Python108 PASS, DOM24 PASS, Sandbox JS PASS, diff check PASS | **과거 문서의 자기보고 기록**, 이번 재실행/독립 검증 결과가 아님 |
| 현재 공식 데이터 | backend/config.json:16–24 M01–M07 전부 null, adapters cleaning/scenario_generation empty, cleaning_model_version null | 공식 측정 불가, 결측을 0점/성공으로 바꾸지 않음 |
| candidate | manifest:4 FROZEN_FOR_UNSEEN_DEVELOPMENT_VALIDATION; official=false; snapshot 보존 | unseen 평가 완료 또는 최종 제품 freeze 아님; 전수 hash 재감사 안 함 |

## PDF 페이지별 열람 근거

| PDF 페이지 | 확인 내용 |
|---|---|
| 1 | 제품 v1.0, 시험7항목, 수집→AI정제/업무패턴→맵/매뉴얼/시나리오/스크립트/실행 용도; 수집 에이전트·업무패턴 분석 엔진 구성 |
| 2 | Chrome와 Excel(근거 CSV 재계산) 시험도구 |
| 3 | 텍스트에는 구성도 내용 누락. 이미지 확인: PC Chrome/수집 에이전트 ↔ 네트워크 ↔ 서버 검증웹/업무웹/정제/분석/시나리오생성/실행러너/문서생성 |
| 4 | PC/서버 HW·OS·SW 표 실제 시각 확인. Windows11/Ubuntu26.04, Python3.12.3, PyTorch2.13.0+cu132 등은 원문 기재값이며 현재 설치 확인 아님 |
| 5 | 제조사·모델번호·OS버전·SW 해당없음 표 |
| 6 | M01 산식≥65, 이벤트10, 1종1회와10독립세션 동시 기재; M02 TD-03 업무20/GT5/TD-04 필드 |
| 7 | M02 GT5, 전체 생성절차 Accuracy 분모, 전체GT필수 Completeness, 기하평균≥75, 보조 evidence 직접매핑 제외 |
| 8 | M03 TD-03공유/TD-05업무10, schema/순서/action/target, ≥80; M04 고정 Selenium Python10/scenario_id/assert/수동수정 없음 |
| 9 | M04 오류/중단 FAIL 및 전체실행분모≥90; M05 F1≥0.79, TD-06 총20/remove10/keep100과 TD-07/주석 총200/100/100 상충을 시각 재확인 |
| 10 | M05 목표 후속; M06 embedding+label, DBI≤1, Si/Mij 수식·sklearn 교차확인. 특정모델/수량/차원/군집수 없음. M07 C1두검사 교집합/C2 |
| 11 | M07 시나리오20×1, 생성20/C2고정20, AST/py_compile, M04동일Runner, ≥80; 작성일2026-09-18. 권위는 사용자 지정에 따름 |

FINAL 자체 모순은 원문 열람 실패가 아니다. M01/M05는 사용자/KTL 해석 확인 대기이며, “FINAL 최신성 미확정” 또는 “M05는 확정200”으로 기록하지 않는다. GT는 평가 전용이며 p.9 절차를 근거로 모델에 라벨을 전달하지 않는다.

## stale / implementation baseline

상세 위치/요구값은 CURRENT_STATE S01–S08을 기준으로 누적한다.

| ID | 현재 증거 | FINAL 근거 / 판정 |
|---|---|---|
| S01 | R&D_COMPLIANCE.md:10,16 및 external-integration-api.md:4 | FINAL 전체/사용자 권위 확정; 출처 문서 갱신 대기 |
| S02 | official_contracts.py:5–6의 M01 5×2/100/6/8 | p.6은 이벤트10·총10세션/1종1회 상충; 수량 확인 BLOCKED |
| S03 | evaluation-spec.md:34–35,96; data-contracts.md:130–136; matrix:9–10의 과거20 | p.8–9 M03/M04 10/10, 현재 official_contracts.py:8–9와 문서 불일치 |
| S04 | official_contracts.py:12; data_sources.py:204–208; test_official_compliance.py:53–84 | p.10에 V6.2/563/128/12 제한 없음. generic DBI와 stale provider 구분 |
| S05 | evaluation-spec.md:38,97; matrix:13의 M07 generated_code_count 가변 공식분모 | p.11 C2=20. external_results.py:54 비공식 가변분모는 공식에 적용하지 않음 |
| S06 | official_contracts.py:11 및 data_sources.py:216–217의 M05 200/100/100 | p.9 일부200과 일치/TD-06 총20과 충돌; 자동교체 금지 |
| S07 | data_sources.py:177–181 업무ID 집합동일 검사 | p.6 TD-03업무20, p.8 TD-05업무10·같은TD-03; 계약 후속 검토 |
| S08 | R&D_COMPLIANCE.md:82–92 환경 TODO | p.4 환경 표 존재; 실제 설치 대조와 원문 값 반영 별도 |

과거 V6.2 수량/결과 및 snapshot 문구는 보호 역사기록이며 그 자체를 새 공식조건으로 사용하지 않는다. README:96의 candidate 개발점수/DBI0.4168도 이번 측정 또는 FINAL 통과 증거가 아니다.

## 실행 안전성 및 범위

- 읽기: git status/rev-parse, 파일 목록/문서·코드·manifest 열람, FINAL SHA-256 및 로컬 PDFKit 추출/렌더. 모델 import/inference/훈련/재군집화 없음.
- 기본 swift 시도는 사용자 cache 경로 접근 오류로 실패했다. 임시 module cache를 /tmp로 지정해 정상 추출했다. ps 읽기는 OS 권한으로 거부되어 재시도하지 않았으며 작업 결과에 영향 없음. PDF 읽기 성공은 실제 11페이지 출력 및 이미지 확인에 근거한다.
- tests/test_evaluations.py:85–91은 보호 V6.2 reference 파일 복사/사용, tests/test_v62_runtime.py는 runtime 관련 경로를 포함한다. 사용자 제한에 따라 전체 discover는 실행하지 않았다. backend/evaluation 변경이 없어 AGENTS의 변경 후 필수 suite 조건도 이번에는 적용되지 않는다. 이후 synthetic만 선택할 때 전체 import/setUp/출력경로 사전 감사와 PYTHONDONTWRITEBYTECODE/임시 디렉터리 격리가 필요하다.
- 실제 데이터 재계수/검증, 기존 결과 재생성, API 제출/저장, 공식/개발 점수 생성 없음. 이번 확인은 문서 초기화용 정적 inspection이다.

## 독립 Verification 누적란

| Verification ID | 담당/일시 | 입력 HEAD·문서 hash | 확인 범위·실행 명령 | 결과 | 증거/잔여 이슈 |
|---|---|---|---|---|---|
| VER-INIT-01 | 별도 Task 예정 | 위 baseline HEAD, 문서 hash는 검증시 기록 | 세 파일 내용/변경범위/FINAL 페이지·hash/코드 줄 대조 | READY_FOR_VERIFICATION | 아직 독립 결과 없음 |

다음 검증자는 세 문서만 변경되었는지, 사용자 미추적 PDF가 보존됐는지, 수량 상충을 임의 해결하지 않았는지, FINAL에 없는 M06 제한을 공식 요구로 유지하지 않았는지 확인한다. 실패/미실행을 PASS로 바꾸지 않고 기존 행을 보존하며 새 결과를 누적한다.

## 작성자 범위 자체 확인 (독립 검증 아님)

문서 생성 직후 git status는 docs/agents/와 원래 사용자 FINAL PDF만 untracked였고, git diff --stat는 비어 있었다. HEAD는 baseline과 동일하고 git diff --check는 오류가 없었다(단, 기본 diff는 미추적 세 문서 내용을 검사하지 않는다). 세 문서 파일 목록 및 공백 검사를 별도로 수행한다. FINAL SHA-256 재확인도 동일했다. 이 결과는 변경 범위 자체 확인이며 VER-INIT-01 PASS로 승격하지 않는다.

## VER-INIT-01-INDEPENDENT — 2026-10-26

**판정: FIX_REQUIRED.** 대상은 초기화 문서의 정확성·완전성·범위이며 제품 공식시험 PASS 판정이 아니다.

### 독립 확인 증거

- 실제 main HEAD `d033c0920bff01861af10ba8d1e0050574a62adf`. 시작 dirty는 미추적 CURRENT_STATE.md/TASK_QUEUE.md/VALIDATION_REPORT.md/FINAL.pdf 네 파일. 초기 작성 전 PDF 하나뿐이었다는 과거 상태는 현재 git으로 소급 증명할 수 없으며 작성자 보고와 구분한다. tracked/staged diff는 모두 비어 있었다.
- 입력 문서 SHA-256: CURRENT_STATE `83448fe3befff94073b18402ca95119f565a6f736123574150b7e4f95957f878`; TASK_QUEUE `3628236c431cd0c734b538e8e7283c8608c23cd4a8ac5f6fdc97f299b7cc9de6`; 본 보고서 누적 전 `fd3c6f70691244a0eb18ffe8d57e7c0523c5c6ec1e28d9c41771c594fc2de307`.
- FINAL 독립 shasum `5cdfe8e0abdc6eff552f419681182d4c897a886f1df3cdc9cb5dadc75fb22768`, PDFKit pageCount=11. /tmp/verify_ktl.swift와 /tmp module cache로 전체 텍스트 추출 및 11장 PNG 생성 후 **11페이지 모두 직접 시각 대조**. 외부 전송 없음. p.3 구성도, p.4 환경, p.6–11 표/수식은 초기화 요약과 일치.
- M01 p.6 필수10/시나리오1종1회/총10세션, M05 p.9 TD-06 총20/remove10/keep100 대 TD-07 200/remove100(4×25)/keep100와 주석200을 그대로 보존한 것은 정확하다. M06 p.10에는 V6.2/563/128/12 요구가 없으며 data_sources.py:204–208/official_contracts.py:12는 현재 구현 제한이다. 초기화는 이를 구분한다.
- backend/evaluators.py:102–218, contracts.py cleaning_payload, data_sources.py:125–222, official_contracts.py, m03_integration.py, external_results.py, integration_store.py, run_storage.py 및 server.py:112–158/224–240을 직접 읽었다. direct-only/전체절차 분모, GT 제거, 고정10/10/20, 실패 분모, hash/등록/중복 검사, MOCK 차단과 REAL 미설정503은 정적 근거와 일치. GT 누출 부재를 전체 training/inference 경로에 대해 감사 완료했다는 뜻은 아니다.
- config 공식 manifest 전부 null, adapter empty. candidate manifest의 official=false/final_product_freeze=false, 60 workflow/21 cluster와 transductive 정책, README 개발점수는 기록으로 확인. 이번 데이터 전수 재계수·모델 artifact 전수 hash 검증·독립 unseen 검증은 하지 않았다.

### 수정이 필요한 문제

| ID | 문제 파일/위치 | 이유 | 최소 수정 범위 | 재검증 |
|---|---|---|---|---|
| F01 | CURRENT_STATE.md:81; TASK_QUEUE.md:10–18 | 일반 문서 동기화/backend 수정까지 새 사용자 승인 필수로 확대했다. 이번 초기화에서 실행하지 않는다는 범위 제한과 기존 일반 수정·테스트·regression 자율 권한을 혼동한다. 별도 승인 6종도 완전하게 열거하지 않았다 | 이번 task 금지와 향후 일반 자율 권한을 구분하고, 큰 architecture 변경/KTL 공식기준 변경/OFFICIAL 데이터 정의 변경/외부 API breaking change/최종 model freeze/공식시험 데이터 사용 6종을 명시. V6.2·보호 artifact 별도 보호도 유지. 원문 모순 해석은 사용자 확인 유지 | 신뢰된 사용자 지시와 각 task 승인 칸을 대조. 일반 작업의 불필요한 재승인 요구가 없어야 함 |
| F02 | CURRENT_STATE.md 외부 API 절 및 VALIDATION_REPORT baseline | PDF p.2는 근거 CSV로 재계산을 요구하지만, 저장 파일 존재 설명만 있고 지표별 CSV만으로 재계산 가능한 수준/보조 입력 필요/미검증을 구분하지 않았다 | CSV 재계산 준비도 표 추가. M01 count 행이면 가능, M02 direct rows 가능, M03 success rows 가능, M04 cases 선택 시 count가 result/received_payload에만 남을 수 있음, M05 expected/predicted 가능, M06 scatter/max_ratio로 평균만 재계산 가능하며 원 embedding/labels로 전체 DBI 검증 필요, M07 cases 교집합 가능. 모두 실제 export 재계산 미실행임을 명시 | 임시 합성 fixture/output만으로 CSV와 result/received_payload 재계산을 비교하거나 정적 확인 수준으로 명확히 한정. 공식/보호 결과 재생성 금지 |
| F03 | CURRENT_STATE.md:28 | cleaning_payload의 정의 위치를 backend/evaluators.py로 잘못 참조 | backend/contracts.py:64–75(정의), backend/server.py:118(실제 adapter 호출 전 적용)로 근거 정정 | 정의와 호출 지점 직접 대조 |

F01–F03은 이 검증에서 직접 수정하지 않았다. 이 누적 보고와 INIT task 상태 갱신만 허용된다.

### 테스트 및 재현성의 실제 확인 수준

- 이번 실행: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_latest_integration.py -v` → **9 tests PASS (0.019s)**. 파일 전체를 먼저 읽었고 임시 합성 fixture만 사용, /tmp TemporaryDirectory 결과는 제거됨. 이 PASS는 연동 계산/검증 회귀에 한정되며 실제 LLM/Selenium/공식시험 PASS가 아니다.
- 테스트 존재: tests/test_evaluations.py PureEvaluatorTests는 M02/F1/DBI/GT/CSV escaping 검사를 포함. 전체 discover는 미실행. SourceAndServiceTests.setUp:85–90은 실제 frozen artifact를 임시 경로로 복사하고 일부 테스트가 복사본을 삭제/변조한다. tests/test_v62_runtime.py:17–19는 build_sidecars를 호출한다. 원본을 변경한다고 단정하지 않으며, 보호 reference 재구성/사용 없는 합성 검증 범위로 제한했다. backend 변경이 없어 전체 suite 의무 조건은 발생하지 않았다.
- 과거 Python108/DOM24/Sandbox PASS는 기존 문서의 보고로만 남으며 이번 실행 PASS와 구분한다.
- run_storage.py:25–35는 result/CSV/manifest/received payload를 기록하지만 결과 파일 자체 hash를 manifest에 저장하지 않는다. integration_store.py는 입력 파일 hash를 검증한다. 원시 데이터의 실제 미사용 이력·실제 외부 수행 사실·산출 CSV 전체 재계산 성공은 이 코드/선언만으로 입증되지 않는다.
- S01–S08 stale 목록을 직접 대조했고 주요 수치/구현 차이는 정확하다. 추가 잔존 M06 표시 metadata: backend/evaluators.py:22의 563 및 server.py:132 workflow_embedding_128. 동기화 시 함께 검토하되 이번에는 변경하지 않는다.

### 다음 우선순위와 승인 경계

사용자 다음 최우선은 **CRITERIA-01: FINAL p.6 M01 및 p.9 M05 모순의 해석 확인**. 문서 수정 담당은 F01–F03 보완 후 INIT 재검증을 병행할 수 있다. 이후 상위 다섯 작업: (1) INIT 보완·재검증 (2) CRITERIA-01 (3) DOC-01 (4) M06-01 (5) M02M03-01. 일반 문서/비breaking backend/합성 회귀는 기존 자율 권한이며 이번 검증에서는 수행 범위 밖이다. 위 6종과 frozen/보호 artifact 변경은 별도 승인 경계를 따른다. 원문 수량 모순은 임의 결정하지 않는다.

최종 범위: CURRENT_STATE 원문/제품/기존 문서/모델/데이터/PDF는 미수정. TASK_QUEUE INIT-01만 BLOCKED(문서 FIX_REQUIRED 해결 후 재검증)로 갱신하고 본 결과를 누적. commit/push 없음.


## DEV-FIX-INIT-01 — 2026-10-26 보완 누적

상태 **READY_FOR_VERIFICATION**. VER-INIT-01-INDEPENDENT의 FIX_REQUIRED 판정·증거·테스트 이력은 보존하며 자체 PASS를 선언하지 않는다.

- F01: CURRENT_STATE 권한 절과 TASK_QUEUE 승인 칸에서 일반 코드/문서/합성 회귀의 기존 자율 권한과 이번 세 문서 범위 제한을 구분했다. 승인 필수 6종과 V6.2/validation snapshot/GT/실패 분모/결측/보조 evidence 보호를 명시했다.
- F02: CURRENT_STATE에 M01–M07별 CSV 단독 산술 범위, 원시 입력/JSON 필요 부분, exporter/저장 코드 위치 및 미검증 범위를 누적했다. evaluator·CSV 생성 코드를 직접 읽은 정적 대조이며 실제 CSV export/재계산은 모든 지표 미실행이다. 특히 M04 cases와 counts-only, M06 max_ratio 평균과 전체 DBI 재검증을 구분했다.
- F03: cleaning_payload 정의를 backend/contracts.py:64–72, 실제 adapter 전 적용을 backend/server.py:118로 정정했다. features 내부 금지 key를 재귀 검사하고 id/features만 전달한다는 코드 범위 확인이며 전체 모델 경로 GT 감사 완료 주장이 아니다.
- 선행 열람: AGENTS.md, R&D_COMPLIANCE.md, docs/agents 세 문서 전체, FINAL PDF 11페이지 전체 PDFKit 텍스트를 직접 확인. 명령: `swift -module-cache-path /tmp/ktl-swift-cache /tmp/ktl_pdf_read.swift docs/compliance/source/KTL_TEST_CRITERIA_FINAL.pdf`. 이번에는 추가 이미지 렌더/시각 재검증은 하지 않았으며 이전 시각 검증 이력과 구분한다. FINAL 모순과 S01–S08 stale 값은 수정하지 않았다.
- 테스트: unit/regression/HTTP/모델/학습/공식 데이터 사용/CSV 실제 재계산 모두 미실행. 문서만 수정했고 evaluation/backend 변경이 없어 AGENTS.md의 변경 후 전체 unittest 의무 조건은 발생하지 않는다. 안전한 정적 확인 수준으로 한정했으며 과거 9 tests PASS를 이번 실행으로 재사용하지 않는다.
- 입력 HEAD: `d033c0920bff01861af10ba8d1e0050574a62adf`. 수정 전 SHA-256: CURRENT_STATE `83448fe3befff94073b18402ca95119f565a6f736123574150b7e4f95957f878`, TASK_QUEUE `ce4cd89d8d95157bd2d4c3f5a6aa2b30b01f9542880b6aa2908054844ac7687a`, VALIDATION_REPORT `920bed4aff04d67929e6e4465f90756259891f882193a108f4f8bf4ea82d6418`.
- 변경 범위는 docs/agents/CURRENT_STATE.md, TASK_QUEUE.md, VALIDATION_REPORT.md뿐이다. 제품 코드/기존 문서/PDF/모델/데이터/보호 artifact, commit/push 없음. 문서가 미추적이므로 기본 git diff만으로 내용 확인 불가; 수정 전 사본 `/tmp/ktl-fix-before/`와 세 파일을 비교한다. 최종 파일 hash는 자기참조를 피하도록 완료 응답에 기록한다.
- 별도 재검증: 최종 HEAD/세 문서/PDF hash, tracked/staged diff와 untracked 목록, 위 사본 대비 diff를 확인하고 F01 권한 경계/F02 코드 대조 및 정적 확인 한계/F03 정의·호출 위치를 검증한다. 실제 재계산이 필요하면 합성 fixture와 임시 출력만 사용한다. 기존 FIX_REQUIRED 행을 지우지 말고 독립 결과를 새로 누적한다.


## VER-INIT-02-INDEPENDENT — 2026-10-26 재검증

**판정: PASS. INIT-01 초기화 세 문서 품질에 한정한다. 제품 공식시험 PASS, 공식 데이터 승인 또는 모델 freeze를 뜻하지 않는다.** 최초 VER-INIT-01-INDEPENDENT의 FIX_REQUIRED 및 DEV-FIX-INIT-01 기록을 삭제·교체하지 않고 이 결과를 누적한다.

### 독립 입력·원문·변경 범위

- 실제 checkout HEAD는 `d033c0920bff01861af10ba8d1e0050574a62adf`. AGENTS.md, R&D_COMPLIANCE.md, CURRENT_STATE.md, TASK_QUEUE.md 및 본 보고서 전체를 먼저 확인했다. 사용자 확정 FINAL 우선순위를 적용했으며 R&D의 CURRENT/최신 서명본 TODO는 잔존 stale로 구분했다.
- 재검증 입력 SHA-256: CURRENT_STATE `ff58669bf166b2b6123b6b22fc74b5b67f8cb8b8e4663f75d514e008bf94c2bb`, TASK_QUEUE `52bc37103afa0ac333f896ec036dbe192d562dd9444b732d74c436304be633b4`, VALIDATION_REPORT `4321f185808c35c63f5b2233ac311f0da63959504c98d1ca08a8942a65eb3e96`.
- FINAL을 직접 SHA-256 계산하여 `5cdfe8e0abdc6eff552f419681182d4c897a886f1df3cdc9cb5dadc75fb22768` 일치를 확인했다. `swift -module-cache-path /tmp/ktl-independent-cache /tmp/ktl_pdf_read.swift docs/compliance/source/KTL_TEST_CRITERIA_FINAL.pdf`로 PDFKit pageCount=11 및 p.1–11 전체 텍스트를 직접 읽었다. 렌더 스크립트를 읽고 별도 `/tmp/ktl_independent_render.swift`로 11페이지 PNG를 생성한 후 p.3 구성도/p.6 M01/p.9 M05/p.10 M06를 직접 시각 대조했다. 나머지 페이지는 이번 텍스트 대조이며 전 페이지 시각 재검증으로 주장하지 않는다. 외부 업로드 없음.
- 시작 tracked/staged diff는 비어 있고 untracked는 docs/agents/와 사용자 FINAL.pdf였다. 초기 작성 전 상태는 현 git으로 소급 증명할 수 없다. `/tmp/ktl-fix-before`는 보완 차이 비교에만 사용했고 실제 현재 코드·PDF 검증을 대체하지 않았다. 이번 시작 사본은 `/tmp/ktl-independent-before`에 보관했다.

### F01–F03 판정

| 항목 | 결과 | 독립 근거와 한계 |
|---|---|---|
| F01 권한 경계 | 해결 | CURRENT_STATE 권한 절 및 TASK_QUEUE 각 승인 칸은 일반 코드/문서/합성 회귀의 기존 자율 권한과 이번 미실행 범위를 분리했다. 큰 architecture 변경, 공식 시험기준 변경, OFFICIAL 정의 변경, 외부 API breaking change, 최종 freeze, 공식 데이터 사용의 6종을 완전하게 열거한다. V6.2 재학습/boundary/prototype/출력/승인 artifact 및 snapshot 보호를 별도로 유지한다. 후속 제품 작업은 실행하지 않았다. |
| F02 metric별 CSV/evidence | 해결 | evaluators.py:85–218, external_results.py 전체, m03_integration.py 전체, run_storage.py 전체, server.py:112–158, data_sources.py:125–222 및 official_contracts.py를 직접 대조했다. M01 counts/cases 차이, M02 전체 detected/GT 분모와 공백 GT, M03 success rows, M04 cases/counts 및 실패 분모, M05 REMOVE 양성, M06 max_ratio 평균만 가능한 CSV 한계, M07 공식20/비공식 generated 분모가 표와 일치한다. status-only CSV로 점수를 만들지 않으며 원본/alias/모드/실제 실행/provenance/held-out 이력 추가 필요와 정적 확인 한계를 명시했다. 아래 합성 산술 검사는 추가 근거이며 실제 시험·운영 export 완료를 뜻하지 않는다. |
| F03 cleaning_payload | 해결 | 실제 정의 backend/contracts.py:64–72, 호출 backend/server.py:118 및 사전검사 data_sources.py:218 확인. id/features만 전달하고 features 내부 dict/list의 금지 key를 재귀 검사한다. 합성으로 top-level 평가 label 제외 및 nested Ground_Truth 거부를 확인했다. 전체 training/inference 경로 누출 감사는 미검증이다. |

### 실제 실행과 미검증

- 실행 명령: `PYTHONDONTWRITEBYTECODE=1 python3 /tmp/ktl_independent_synthetic.py` → **15 synthetic checks PASS**, exit 0. 스크립트/입력은 /tmp, DEVELOPMENT 모드와 메모리 CSV round-trip만 사용했다. M01 counts 재산술 및 cases 시 count 부재, M02 direct/auxiliary/미매칭·공백 GT 분모, M03 실패 포함 비율, M04 cases/counts 두 경로 및 TIMEOUT 분모, M05 TP/FP/FN, M06 max_ratio 평균 및 centroid 부재, M07 3요청/2생성 비공식 분모와 counts-only, cleaning payload 두 검사를 포함한다. backend calculate/evaluator/exporter 함수를 호출했으며 모델·adapter·HTTP·save_run·ingest는 호출하지 않았다. 보호 artifact/실제 OFFICIAL 입력 사용 없음.
- 실제 run_storage/server 저장 파일 export와 result/received_payload end-to-end 재계산, Excel 실행, 공식 M01–M07, 실제 generator/cleaning/LLM/Selenium, sklearn DBI 교차검증, 전체 unittest discover, 데이터 전수계수/미사용 이력, 보호 artifact 전수 hash는 **미실행/미검증**. 이번은 backend/evaluation 변경이 없어 AGENTS의 변경 후 전체 suite 의무 조건에 해당하지 않는다. 이전 9 tests 및 과거 108 tests는 이번 실행 결과로 재사용하지 않는다.
- S01–S08의 주요 실제 위치를 읽고 대조했다. R&D의 source/환경 TODO, evaluation-spec/data-contracts/matrix의 M03/M04 20 및 M07 가변분모, official_contracts/data_sources의 M01 구판값·M05 200·M06 563×128/12와 업무ID 동일집합 검사가 남아 있다. 모두 목록화되었으며 이번에는 기존 문서/코드 값을 수정하지 않았다. M06 표시 metadata도 이전 검증 목록에 보존되어 있다.
- M01 p.6은 **필수 이벤트10건**, 방법3 **시나리오1종 각각1회**와 **총10개 독립 수집 세션**을 함께 기재한다. 기존 구현 **5종×2회/총100/6필드/8유형**을 FINAL 확정값으로 승격하지 않았다.
- M05 p.9 TD-06은 **총20건/remove10/keep100**(구성 합계도110), TD-07은 **200 event_id/remove100(duplicate/noise/repeated_action/irrelevant_action 각25)/keep100**, 주석은 **총200건 1회 일괄**이다. 어느 값을 오타로 확정하거나 원문을 수정하지 않았다. CRITERIA-01은 BLOCKED 그대로다.

### 종료 범위 및 다음 작업

INIT-01만 PASS로 닫고 CURRENT_STATE 초기화 상태를 동기화한다. 변경은 본 검증 누적, TASK_QUEUE의 INIT 상태와 완료 후 순서 표기, CURRENT_STATE의 초기화 상태 표기에 한정한다. 제품/기존 기준문서/모델/데이터/PDF/보호 artifact, 학습/공식시험/commit/push 없음. 미해결 제품 task 상태는 변경하지 않는다.

남은 상위 5개: **CRITERIA-01 → DOC-01 → M06-01 → M02M03-01 → M05-01**. 첫 추천은 CRITERIA-01의 M01/M05 수량 해석을 사용자/KTL에 확인하는 것이다. 일반 자율 작업과 승인6종/보호 변경을 구분하며 모순을 추측해 구현하지 않는다. 새 초기화 결함은 발견하지 않아 추가 Development Fix Task는 만들지 않는다.
