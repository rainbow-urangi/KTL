# 외부 연동 API — 2026-10-26

현재 연동 대상은 **M03 Scenario Generation → M04 Selenium Runner → M07 LLM Code Generation**입니다.
기준은 [R&D_COMPLIANCE.md](../R&D_COMPLIANCE.md)의 최신 사용자 확인 협의입니다. 보관된 2026-09-18 KTL PDF의 구판 수량과 구분하며 최신 서명본 확보는 TODO입니다.

## 시작하기

`python3 -m backend.server --port 8000` 실행 후 [Developer Sandbox](http://127.0.0.1:8000/developer/integration-api)를 엽니다.
기본 카드는 M03/M04/M07 순서입니다. M04 9/10=90%, M07 16/20=80%의 예시를 제공합니다. M03은 독립 평가 정답이 없으면 형식이 정상이더라도 순서 평가 대기·점수 null입니다. 표시되는 실제 점수는 서버 응답입니다. Mock은 실제 업무 생성·Selenium·LLM 실행을 수행하지 않습니다.

Sandbox는 `mock-dataset-01` / REFERENCE 합성 예시만 전송합니다. 생성 응답은 200, 평가 접수는 201입니다. 전송·JSON/curl 복사 시 고유 external ID와 제출 시각을 생성합니다. 실제 결과는 `results/reference/`에 저장되므로 공식 시험 근거로 사용하지 않습니다.

## 웹 화면과 API의 역할

M03 화면은 `POST /api/m03/generate`의 시나리오 응답을 표시한 뒤 `POST /api/integrations/m03/result`로 평가·보관합니다. 이미 외부에서 접수한 M03 결과도 저장된 이력과 접수 원본을 조회하여 표시합니다. 이 조회에는 생성기를 다시 호출하지 않습니다. M03 화면에서 CSV를 직접 분석하거나 M02를 대신 실행하지 않습니다.

M04 화면은 선택한 M03 시나리오로 스크립트를 준비하고 명시적인 실행 버튼으로 Runner를 시작합니다. 로컬 Runner는 `POST /api/integrations/m04/result`와 같은 접수·검증 계약으로 결과를 저장합니다. 외부 실행기가 해당 API로 전달한 결과도 기존 결과 영역에서 조회할 수 있습니다. 결과 접수나 조회만으로 브라우저 실행을 시작하지 않으며, 실행별 상세가 없는 counts 전용 결과에는 실패 단계·실행 로그를 만들어 붙이지 않습니다. 새로고침은 최신 접수 결과를 다시 조회합니다.

## 공통 평가 계약

`POST /api/integrations/{m03|m04|m07}/result`, JSON, 최대 1 MiB.
필수 metadata: `external_run_id`, `dataset_id`, `run_mode`, `source_module`, `source_version`, `submitted_at`(timezone 포함 ISO8601), `dataset_manifest_sha256`, 그리고 `details` 객체 또는 `evidence` 객체/배열입니다. 문자열은 1~256자입니다. M03은 `run_id`를 external_run_id의 별칭으로 허용합니다. 내부 저장 run_id는 서버가 발급합니다.

서버 config의 `integration_datasets` 등록과 입력 파일/manifest SHA-256 일치가 필요합니다. 클라이언트는 경로나 실행 명령을 지정하지 않습니다. DEVELOPMENT는 `official=false, data_class=DEVELOPMENT`, REFERENCE는 REFERENCE manifest가 필요합니다. OFFICIAL은 metric과 일치하는 승인 manifest, `source_type=run_mode=OFFICIAL`, `approved_for_official=true` 및 아래 공식 계약이 필요합니다. 개발·합성 데이터는 공식 근거로 사용하지 않습니다.

동일 metric의 external_run_id 재사용은 모드와 서버 재시작에 관계없이 409입니다. 정정 시 새 ID와 `details.supersedes_external_run_id`를 사용합니다. 제출한 최종 score는 무시합니다. counts는 정수이며 boolean을 허용하지 않습니다.

## M03 생성

`POST /api/m03/generate`: workflow 식별자로 생성 계약을 호출합니다. 기본은 DEVELOPMENT / MOCK입니다.

```json
{"business_unit_id":"BU03","workflow_id":"WF-001","run_mode":"DEVELOPMENT","generator_mode":"MOCK"}
```

```sh
curl -i http://127.0.0.1:8000/api/m03/generate \
  -H 'Content-Type: application/json' \
  --data-raw '{"business_unit_id":"BU03","workflow_id":"WF-001"}'
```

200 응답 구조(식별자 예시):

```json
{"business_unit_id":"BU03","workflow_id":"WF-001","scenario_id":"MOCK-SCN-<deterministic hash>","status":"SUCCESS","steps":[{"order":1,"action":"open","target":"mock workflow screen"},{"order":2,"action":"click","target":"mock action control"}],"run_mode":"DEVELOPMENT","generator_mode":"MOCK","synthetic":true,"official_pass":null}
```

동일 BU/workflow ID의 Mock 단계와 scenario ID는 결정론적이지만 각 생성 요청의 `origin_generation_id`는 새로 발급됩니다. 위 예시에도 실제 응답에는 `origin_generation_id`가 추가됩니다. 실제 업무명이나 GT를 생성하지 않습니다. REAL은 서버의 local argv 또는 HTTP 연결, 업무 정의와 SHA가 검증된 분석 manifest가 필요합니다. 미설정 시 503 NOT_CONFIGURED, 잘못되거나 없는 입력은 422이며 MOCK+OFFICIAL도 422입니다.

생성 요청은 위4개 필드와 선택 `dataset_id`만 받습니다. OFFICIAL/REAL에는 등록된 `dataset_id`가 필수입니다. DEVELOPMENT UI는 `/api/development/m03/context`에서 얻은 dataset ID를 포함합니다. 생성 전 서버가 원생성 시각·입력 SHA·당시 등록된 평가 정답 SHA를 보관하고 생성 응답을 원본 SHA로 연결합니다. 평가 정답 내용은 생성기에 전달하지 않습니다.

현재 로컬 `backend.m03_canonical_adapter` 연결은 `DEV-CANON-PM-001 / WF-0037`의 기존 canonical 8단계를 M03 JSON으로 변환하는 DEVELOPMENT 시험입니다. `generation_method=DETERMINISTIC_CANONICAL_ADAPTER`, `official=false`를 유지하며 새 AI 추론·공식 CU01~CU10 평가를 뜻하지 않습니다.

## M03 평가

`POST /api/integrations/m03/result`: 공통 metadata와 `scenarios` 배열을 전송합니다. 서버는 [JSON Schema](../evaluation_contracts/m03-scenario.schema.json)에 해당하는 필수 타입/항목 및 1부터 연속된 단계 순서를 검증합니다.

```json
{"business_unit_id":"BU01","scenario_id":"SCN-001","status":"SUCCESS","steps":[{"order":1,"action":"click","target":"대상 메뉴"}]}
```

위 객체들을 scenarios에 넣습니다. 형식 검증은 schema_valid AND step_order_valid AND action_present AND target_present이며 명시적 FAILED는 실패입니다. 최종 성공에는 서버에 등록한 독립 정답의 `business_unit_id,workflow_id`와 정확한 `action,target` 전체 순서 일치가 추가로 필요합니다. 위 최소 예시만으로 순서 성공을 증명하지 않습니다. 정답이 없거나 대상 업무의 정답이 부족하면 `details.evaluation_status=NOT_READY`, `score=null`입니다. 등록한 정답의 SHA/schema 오류는 ERROR입니다.

action/target/order/유효한 schema가 없는 **제출된 생성 실패 결과는 분모에 유지**합니다. 업무 ID 누락·중복, 유효 scenario_id 중복은 422입니다. 비공식은1~10개 결과를 허용하고 제출된 업무 수를 분모로 사용합니다.

OFFICIAL은 manifest에 고유 `business_unit_ids`10개를 사전 고정하며 `official_contract={"business_unit_count":10,"generation_attempt_per_business_unit":1,"official_denominator":10}`입니다. 결과는0~10개를 허용하되 대상 밖 ID나10개 초과는 거부합니다. 정답10개·정상 결과9개이면 누락1개도 실패로 세어90%입니다. 제출 원본9개를 유지하고 누락은 별도 evidence로 남깁니다. 정답이9개라면 결과9개 또는10개 모두 평가 대기·점수 null입니다. Mock 결과는 공식 제출할 수 없습니다. 8개 성공/10개=80%, 목표≥80%를 유지합니다.

평가 정답은 `m03_evaluation_references[dataset_id]={"path":"<evaluation reference path>","sha256":"<reference SHA-256>"}`로 서버 설정에 등록합니다. `m03-order-reference-v1`, `evaluation_only=true`, `matching_policy=EXACT_ACTION_TARGET_SEQUENCE`, timezone 포함 `fixed_at`, 업무별 `business_unit_id,workflow_id,steps(order,action,target)`가 필요합니다. 생성기 분석 입력이나 요청에 평가 정답을 넣지 않습니다.

새 접수 ID·제출 시각으로 재평가할 때 원래 `origin_generation_id`와 원본 응답을 그대로 제출합니다. 공식 판정에는 생성 시점의 승인 입력·동일 정답 SHA와 원생성 이전 `fixed_at`이 필요합니다. receipt 부재·사후 정답은 `POSTHOC_REEVALUATION`이며 점수가80% 이상이어도 `official_pass=null`입니다. `submitted_at`은 평가 접수 시각으로만 사용합니다.

## M04 자동 실행

DEVELOPMENT 화면의 **CU02 일정 등록**은 `디딤돌_업무흐름_10.pdf`의 일정관리 → 날짜 선택 → 일정 입력 → 등록 → 종료를 실행합니다. `GET /api/development/m04/cu02`는 입력 기본값과 로그인 준비 여부만 조회합니다. `POST /api/development/m04/cu02/scripts`에 `date`(YYYY-MM-DD), `title`(1~120자), `description`(0~2000자), 선택 `browser`(`chrome`/`edge`)를 보내면 고정 스크립트를 준비하고 201을 반환합니다. 준비만으로 로그인·등록·브라우저 실행을 시작하지 않으며 실제 실행은 기존 `POST /api/development/m04/executions`를 사용합니다.

CU02는 창을 열기 전에 실행 환경의 시험 계정으로 로그인 API에 인증합니다. 성공한 경우에만 브라우저를 만들고 대상 origin의 `localStorage.token`을 런타임에서 초기화하여 일정관리 화면부터 표시합니다. 인증값과 응답 토큰은 고정 코드·입력·증빙에 저장하지 않으며, 인증 실패 시 브라우저를 시작하지 않습니다. 날짜 숫자를 native click하여 **신규** 등록 창인지 확인하고, 대상 날짜에 같은 시험 제목이 이미 있으면 중단합니다. 제목·내용이 모두 비어 있는지 실제 입력 전에 독립 검사하고 이 폼을 `before`로 캡처합니다. 등록 후 해당 날짜의 제목이 정확히 한 개 표시되는지 검사하고, 새로고침 후 동일 일정의 상세 제목·내용도 확인한 뒤 상세 폼을 `after`로 캡처하고 닫습니다. 캡처는 사전 고정한 `screenshot_checkpoints={before:2,after:5}`의 명시적 hook에서 수행하며 도달하지 못한 화면은 `NOT_CAPTURED`입니다. 화면은 기존 문자·이미지 마스킹 정책을 유지하고 값 비교는 DOM 판정 기록을 사용합니다. 업무 정의·시험 입력·Python 원본·독립 실행 조건을 SHA와 함께 보관하고, 실패한 실행은 기존 M04 분모에 유지합니다. 이 경로는 GPT/M03 생성이나 공식 평가 정답을 사용하지 않는 DEVELOPMENT 실행이며 공식 10건 시험으로 승격하지 않습니다.

`POST /api/development/m04/cu02/evaluations`는 CU02 일정 등록 10건을 고정하고 실제 실행을 한 번 요청합니다. 입력은 단건과 같은 `date`, `title`, `description`, 선택 `browser`이며 제목은 번호를 제외하고 최대 105자입니다. 실행 표시 설정 `visible_browser`(boolean), `action_delay_ms`(0~2000), `keep_open_seconds`(0~60)를 선택할 수 있습니다. 간격·유지 시간은 `visible_browser=true`일 때만 허용합니다. 제목마다 평가 ID 일부와 01~10 번호를 붙여 고유한 일정 10건을 준비합니다. 이 요청은 실제 사이트에 일정 10건을 생성할 수 있습니다.

응답은 201 `{evaluation, execution}`입니다. `evaluation`에는 `evaluation_id`(`CU02-EVAL-`+32자리 hex), `workflow_id=CU02`, `case_count=10`, `counting_unit=SCHEDULE_REGISTRATION`, `target_percent=90`, `required_success_count=9`, `fixed_at`, `script_ids`, `cases[{case_id,case_number,script_id,scenario_id,sha256,expected:{date,title,description,browser}}]`가 있습니다. `execution.cu02_evaluation`과 같은 값을 보관하고 `cu02_evaluation_sha256`으로 고정합니다. 각 실행 사례에는 `cu02_evaluation_id`와 `cu02_case_number`를 기록합니다. 일정 1건의 신규 등록·실제 입력·등록 버튼 클릭·새로고침 후 상세값 재조회까지 전체 성공이 평가 1건이며 내부 업무 단계 5개를 별도 평가 건수로 세지 않습니다. 준비부터 실행까지 서버 간 브라우저 잠금을 유지합니다.

기존 실행 조회·중단·보고서 API를 그대로 사용합니다. 실행 전 `cu02_evaluation.json`과 10건의 원본·기대값을 고정 archive에 넣고, 결과 접수 원본의 `details.cu02_evaluation`에도 연결합니다. 10건을 각 1회 순차 실행하고 오류도 분모 10에 유지하며 자동 재시도하지 않습니다. 전체 실행과 중앙 결과 저장이 완료된 뒤에만 최종 성공률을 표시합니다. 이 CU02 집계 기준은 개발 화면의 평가 구성입니다. 공식 manifest나 M03/LLM 생성 증빙을 대신하지 않습니다.

DEVELOPMENT 화면의 **M01 동작 가져오기**는 M01에서 검증한 CSV·선택 세션의 원본을 읽어 Selenium 재현 코드를 고정합니다. M01의 평가 정답과 점수는 코드 생성에 쓰지 않으며 M02·M03·GPT를 호출하지 않습니다. `GET /api/development/m04/m01-source`로 원본과 준비 상태를 조회하고 `POST /api/development/m04/import-m01`에 `comparison_id` 또는 `dataset_id`, `parameters`를 전달합니다. 입력값이 수집되지 않았다면 행별 `row_N_value`를 명시해야 합니다. 정확한 대상·순서 근거가 부족하면 해당 행을 표시하고 준비를 거부합니다. 관측 원본은 보존하며 재현 완료를 업무 목적 전체의 달성이나 공식 시험 합격으로 확대하지 않습니다.

가져오기는 실행을 시작하지 않습니다. 별도 실행 버튼의 **새 창으로 실행** 기본 설정은 `visible_browser=true, action_delay_ms=700, keep_open_seconds=15`입니다. 원본 Python을 바꾸지 않고 로컬 Chrome/Edge의 headless 실행 옵션만 제외하며, 실제 조작 간격과 종료 화면 표시 시간을 적용한 뒤 브라우저를 정리합니다. 표시 설정은 실행 이력에 보관합니다. API에서 표시 설정을 생략하면 기존 실행 동작을 유지합니다. 표시용 대기 시간은 실행 제한 시간에 별도로 반영하며 M07 실행 동작은 바꾸지 않습니다.

`POST /api/integrations/m04/result`: 공통 metadata와 다음 counts를 전송합니다.

```json
{"total_execution_count":10,"successful_execution_count":9,"failed_execution_count":1}
```

`passed_execution_count`는 successful_execution_count의 별칭입니다. 두 필드를 동시에 보내면 같아야 합니다. failed count는 선택이나 제출 시 total-success와 일치해야 합니다. 전체 실패·ERROR·TIMEOUT·SKIPPED를 분모에 포함하여 9/10=90%, 8/10=80%, 목표≥90%입니다.

선택 cases는 모든 실행을 포함하며 `case_id,status`가 필요합니다. status는 PASS/FAIL/ERROR/TIMEOUT/SKIPPED, PASS 수는 성공 count와 일치해야 합니다. 이 결과 접수 API는 실행기를 직접 실행하지 않습니다.

OFFICIAL: 사전 고정한 Selenium/Python script 10건, 각 1회 실행. `official_contract={"fixed_script_count":10,"execution_per_script":1}`, `fixed_at`은 제출 이전 시각, `scripts_manually_modified=false, script_language=python, script_framework=selenium`, `files.scripts`에 archive path/sha256이 필요합니다. 비공식 수량은 고정하지 않습니다. 고정 시점과 실제 실행의 진실성은 외부 로그로 증빙합니다.

## M07 코드 검증

M07 기본 화면은 회의록의 **독립 입력 20건 → 실제 LLM 생성 → 별도 문법·실행 검사 → 20행 PASS/FAIL·성공률** 흐름입니다. `GET /api/development/m07/meeting-context`는 정확한 수량 20, 목표 80%, 입력 형식·단일 작성 예시·Chrome/로그인/LLM 준비 여부를 반환합니다. 모델 표시명 `GPT 루나`와 실제 API 모델 ID는 구분하며 인증값은 반환하지 않습니다. 미설정이면 업무 컴퓨터의 연결 설정이 필요하다고 표시합니다.

`POST /api/development/m07/meeting-generations`는 최대 256 KiB의 `{items:[{input_id,scenario}, ...20개]}`를 받습니다. `scenario`에는 `scenario_id`, `scenario_name`, `business_unit_id`, `workflow_id`, `steps`, `execution_contract`가 필요하며 설명·사전조건·마스킹 화면 기록 단계는 선택입니다. 각 단계에 동작·대상·기대 결과를 지정하고 입력/선택 단계는 실제 `value`, 이동 단계는 `url`을 지정합니다. 서로 다른 입력·시나리오 ID와 실제 실행 내용이 구분된 20건이어야 하며 동일 내용을 ID만 바꾸어 복제하거나 코드·판정·GT·가짜 M03 증빙을 넣으면 거부합니다. URL·CSS·검사 조건은 실제 앱 근거로 사전에 확정합니다.

응답 202 `{generation}`은 `meeting_protocol=true`, `measurement_protocol=M07_MEETING_20_V1`, `required_count=20`, `code_source=LLM`, `source_kind=MEETING_LLM_BATCH`입니다. 생성 전에 입력 20건과 계약을 고정하며 각 사례에 `input_id`, `meeting_input_sha256`, `source_m03_run_id=null`을 기록합니다. 입력별 LLM 요청 1회씩 수행하고 원본 응답·프롬프트·코드를 보관합니다. 이 경로는 직접 등록한 입력이며 M03 산출물을 만들지 않습니다. 기존 코드 조회 API는 실제 LLM 원본에도 `code_base64`, `identity_verification`을 제공해 화면·고정 원본·검사 코드가 동일한지 검증합니다.

별도 `POST /api/development/m07/generations/{id}/validate`(본문 `{}`)로 생성 원본을 문법 검사한 후 Chrome에서 실행합니다. 실제 LLM 코드는 `ktl_runtime.authenticated_chrome()`으로 창 생성 전 인증된 Chrome을 얻고, 첫 업무 `driver.get()` 직후 `complete_authentication(driver)`을 호출해 세션 bootstrap을 제거합니다. 도우미는 인증·브라우저 초기화만 제공하며 업무 조작·판정은 생성 코드가 수행합니다. 문법·실행을 모두 통과한 경우만 최종 PASS입니다. 요청한 20건의 실제 HTTP 근거와 검사가 완료되면 `both_pass_count / 20 × 100`으로 중앙 결과를 보관합니다. 생성 성공이 19건이어도 16건 통과는 80%입니다. 20건 모두 실제 요청 후 실패한 경우는 0%, 공급자 제한 등으로 미시도·근거 불명이 남으면 `NOT_READY`, 점수 `null`입니다. 기존 생성 성공 건수 분모의 개발 평가기를 회의용 판정에 사용하지 않습니다.

`GET /api/development/m07/meeting-input-draft`는 `{draft:true,approved_for_official:false,description,items:[20개]}`를 반환합니다. PDF의 10업무에서 다른 입력값·기존 조회 행을 구성한 **검토용 초안**입니다. 자동으로 시험 목록을 확정하거나 생성·실행하지 않습니다. 사용자가 명시적으로 불러와 내용을 검토한 후 실제 생성 버튼을 사용합니다. 모든 회의용 개발 결과는 `official_pass=null`이며 실제 업무 PC LLM 연결·실행을 대신한 증빙으로 표시하지 않습니다.

보조 도구에는 **준비 코드**와 **M03 연결** 경로가 있습니다. `GET /api/development/m07/workflows`는 CU01~CU10의 이름·원문 업무 흐름·조회/등록 유형·기본 입력값·`parameter_fields`·로그인 준비 여부·Chrome 실행 환경을 반환합니다. 조회만으로 외부 앱이나 LLM을 호출하지 않습니다.

`POST /api/development/m07/workflows/prepare`의 본문은 `{workflow_ids:["CU01",...],parameters:{...}}`입니다. 업무는 중복 없는 1~10개, `cases_per_workflow`는 1 또는 2(기본 2)로 최대 20개 코드를 준비합니다. 입력은 `date`(YYYY-MM-DD), `title`(최대 90자), `description`(필수·2000자 이하), `contact_name`, `company`, `phone`, `email`, 선택 `lookup_title`, `cases_per_workflow`이며 생략값은 서버 기본값을 씁니다. 새 등록 제목·회사명에는 실행별 고유 접미사가 붙습니다. 조회는 첫 기존 항목을 사용하고 `lookup_title`을 지정하면 그 첫 항목의 제목·회사명과 비교하며 다른 항목으로 자동 변경하지 않습니다.

응답 201 `{generation,workflows}`의 작업은 `source_kind=RBEM_PREPARED_WORKFLOW`, `code_source=PREPARED`, `generated_by_llm=false`, `browser=chrome`입니다. 사례마다 `workflow_id`, `workflow_case_number`, 원본 코드·업무 정의·입력·실행 계약 SHA를 보관합니다. `source_m03_run_id=null`이며 M03 결과를 만들지 않습니다. 준비는 기존 생성 작업 형식을 재사용해 코드 파일을 고정하고 `GENERATED` 상태에 도달하지만 LLM 요청을 보내지 않습니다. 화면은 이를 준비 완료로 표시합니다. 코드 조회의 `identity_verification`으로 표시한 바이트와 고정 원본이 일치하는지 확인합니다.

실제 검사는 기존 `POST /api/development/m07/generations/{id}/validate`(본문 `{}`)를 별도로 호출합니다. 문법 검사 후 고정 원본을 실제 Chrome에서 각 1회 실행하며, 로그인은 창 생성 전에 처리합니다. 빈 신규등록 화면·입력값·실제 UI 저장·새로고침 후 상세값을 확인하고 업무별 시점에서 마스킹 화면을 기록합니다. 조회 대상이 없거나 실행이 실패하면 통과로 처리하지 않습니다. 새 작업은 `visible_browser=true,action_delay_ms=350,keep_open_seconds=3`을 보관하여 Chrome 창과 실제 조작을 보여줍니다. 준비 코드 결과는 등록 코드의 검사 통과율이며 LLM 생성 성능이나 공식 M07 실적에 포함하지 않습니다. 기존 파일 등록·실제 LLM·M03 연계 경로는 유지합니다.

`POST /api/integrations/m07/result`: 공통 metadata와 counts 및 개별 cases를 전송합니다.

```json
{"generation_request_count":20,"generated_code_count":20,"syntax_pass_count":18,"execution_pass_count":17,"both_pass_count":16}
```

각 case 구조:

```json
{"case_id":"CODE-001","generation_status":"PASS","syntax_status":"PASS","execution_status":"PASS","final_status":"PASS"}
```

상태 enum은 M04와 같습니다. final PASS는 generation/syntax/execution 모두 PASS일 때만 허용합니다. cases가 있으면 모든 요청을 포함해야 하며 중앙 서버가 개별 문법·실행 PASS의 교집합을 계산하고 모든 counts와 대조합니다. 불일치는 422입니다. syntax18, execution17이라고 C1을 추정하지 않습니다.

OFFICIAL: 시나리오20 × 각 요청1회 → 생성 코드20, **C2=20 고정**. 개별 cases 필수이며 20건 미충족은 422입니다. C1=16이면80%, C1=15이면75%, 목표≥80%. `official_contract={"scenario_count":20,"generation_attempt_per_scenario":1,"generated_code_count":20,"official_denominator":20}`. M03 산출물·생성 코드·문법·실행 로그를 evidence로 연결합니다.

기존 DEVELOPMENT/REFERENCE count 클라이언트만 호환 목적으로 generated_code_count 분모와 선택 cases를 유지합니다. 이때 generation_request_count는 분모가 아닙니다. 응답 `denominator_policy`로 OFFICIAL_FIXED_20과 NON_OFFICIAL_GENERATED_COUNT를 구분합니다. Sandbox는 20개 전체 cases를 전송합니다. 실제 LLM/Selenium 내부는 변경하지 않습니다.

## 실행 가능한 평가 curl 예시

저장된 sample에는 mock manifest의 실제 해시와 공통 metadata가 있습니다. 다음 명령은 임시 JSON만 생성합니다. metric을 m03/m04/m07로 각각 바꿔 호출하세요.

```sh
python3 - <<'PY'
import json, uuid
from datetime import datetime, timezone
from pathlib import Path
samples=json.loads(Path('frontend/integration-samples.json').read_text())['samples']
for sample in samples:
    payload=sample['request']
    payload['external_run_id']=sample['metric_id']+'-DOC-'+uuid.uuid4().hex
    payload['submitted_at']=datetime.now(timezone.utc).isoformat()
    Path('/tmp/'+sample['metric_id'].lower()+'-request.json').write_text(json.dumps(payload))
PY
curl -i http://127.0.0.1:8000/api/integrations/m03/result -H 'Content-Type: application/json' --data-binary @/tmp/m03-request.json
curl -i http://127.0.0.1:8000/api/integrations/m04/result -H 'Content-Type: application/json' --data-binary @/tmp/m04-request.json
curl -i http://127.0.0.1:8000/api/integrations/m07/result -H 'Content-Type: application/json' --data-binary @/tmp/m07-request.json
```

## 성공·오류 및 저장

평가 결과 접수·보관 성공은 201이며 평가 통과를 뜻하지 않습니다. 아래 M03 수치 예시는 독립 정답이 등록되어 비교가 완료된 경우입니다. 기본 Mock 예시는 정답이 없어 score가 null입니다.

```json
{"metric_id":"M03","run_mode":"REFERENCE","status":"COMPLETED","score":80.0,"sample_count":10,"target":80,"official_pass":null,"pass":null,"details":{"successful_scenario_count":8,"total_scenario_count":10}}
```

M04는 score90/sample10/target90, M07은 score80/sample20/target80입니다. 실제 응답에는 run_id, provenance, input_sha256, evidence_file 등이 추가됩니다. REFERENCE/DEVELOPMENT의 official_pass/pass는 항상 null이며 유효한 OFFICIAL에서만 공식 판정합니다. M03은 `details.official_eligible=true`와 순서 평가 완료도 필요합니다.

`GET /api/health`는 서버 세션·시작 시각·평가 관련8개 소스의 시작 시점 디스크 SHA를 반환합니다. 실행 서버 교체 확인용이며 전체 loaded bytecode attestation은 아닙니다.

| HTTP | 의미 |
|---|---|
| 200 | 생성 성공 |
| 201 | 평가 결과 저장 성공 |
| 400 | JSON/Content-Length 문법 오류 |
| 403 | localhost Host/same-origin 위반 |
| 409 | DUPLICATE_EXTERNAL_RUN |
| 422 | 필수 metadata/수량/schema envelope/모드/해시/count 일관성 오류 |
| 503 | REAL 생성 adapter 미설정 |
| 500 | 저장/파일 접근 실패; 중복 예약과 저장 상태 확인 필요 |

오류 예: `{"status":"ERROR","error":"Invalid count: total_execution_count"}`. 생성기 미설정은 `{"status":"NOT_CONFIGURED","error":"..."}`입니다. 오류 시 score를 생성하지 않습니다.

`results/<mode>/<run_id>/`에 received_payload.json/result.json/evidence.csv/run_manifest.json을 저장합니다. 응답 다운로드 URL로 확인합니다. 제출된 evidence URL은 보관하며 서버가 외부 URL을 내려받거나 실제 수행 사실을 인증하지 않습니다. M03 evaluator version은 `m03-structure-and-reference-order-v1`, M04/M07은 `external-integration-v3-ktl-20261026`이며 과거 결과는 재작성하지 않습니다. M03 평가 이력 저장 실패 시 원본·evidence와 RESERVED 기록은 유지하고 완료 result/manifest/latest는 발행하지 않습니다.

## Legacy / 현재 연동 대상 아님

`POST /api/integrations/m01/result`와 전체 KTL dashboard의 M01은 유지됩니다. 기존 공통 metadata와 일곱 counts(defined_required_event_count, collected_required_event_count, total_collected_event_count, required_field_count, missing_required_field_count, defined_event_type_count, collected_event_type_count)를 받습니다. 산식은 0.5*C1+0.3*(100-C2)+0.2*C3, 목표65%입니다. 기존 요청·응답·201·검증 계약은 유지하며 합성 예시는 integration-samples.json의 legacy_samples에서 확인합니다.

M06의 최신 설명은 **최종 업무패턴 분석 엔진의 workflow embedding + cluster label**입니다. 신규 연동 API는 제공하지 않으며 이번 작업에서는 M06 evaluator와 모델 구현을 변경하지 않습니다. M05도 수량 상충 확인 전까지 유지합니다.
