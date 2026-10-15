# 외부 결과 수신 API

## Quick Start

1. 서버를 `python3 -m backend.server --port 8000`으로 실행하고 [Developer Sandbox](http://127.0.0.1:8000/developer/integration-api)를 엽니다.
2. 기존 `/api/integrations/m01/result`, `/m04/result`, `/m07/result`로 **POST**합니다. `score` 대신 **raw counts**를 보냅니다.
3. `external_run_id`는 metric별로 유일해야 합니다. Sandbox는 전송·복사 때마다 고유 mock ID와 제출 시각을 생성합니다.
4. 먼저 `mock-dataset-01`, `run_mode=REFERENCE`로 테스트합니다. **Copy Request JSON / Copy curl**에 유효한 manifest 해시가 포함됩니다.
5. 성공 **HTTP 201 Created**와 실제 Response JSON을 확인합니다. 기존 API 계약은 200이 아닌 201입니다. `official_pass=null`이어야 합니다.

Sandbox URL: http://127.0.0.1:8000/developer/integration-api

M01 기본 예시는 약 97.363636%, M04는 90%, M07은 83.333…% (15/18)입니다. Sample Response는 설명용이며 실제 Response는 기존 중앙 evaluator가 계산합니다. M04/M07의 부분 사례는 `details.example_cases`에 넣었습니다. 최상위 `cases`는 M04 전체 실행, M07 전체 요청(생성 실패 진단 포함)을 모두 보낼 때 사용하세요. M07 점수 분모는 생성된 코드 수입니다.

**오류 예시 불러오기 → Send Test Request**로 분모 0의 HTTP 422 응답을 확인할 수 있습니다. OFFICIAL 모드 전송은 Sandbox에서 차단합니다. API의 기존 중복 정책은 그대로이며 같은 curl을 다시 실행하면 409입니다. 다시 Copy curl을 누르면 새 ID가 생성됩니다.

Mock 제출도 `results/reference/`에 실제 저장되며 M01/M04/M07의 REFERENCE latest를 갱신합니다. 합성 예시 데이터이므로 KTL 성능 근거로 사용하지 않습니다. 실제 모듈 연결 시에는 해당 데이터셋을 등록하고 올바른 manifest 해시를 사용하세요.

평가 서버 실행: `python3 -m backend.server --port 8000`. 아래 API는 localhost에서 접근하며 외부 Collector, Selenium Runner, LLM 생성기를 실행하지 않습니다. 제출된 `score`는 사용하지 않고 원시 `counts`로 중앙에서 계산합니다. DEVELOPMENT 결과는 공식 시험성적이 아닙니다.

## 공통 계약

`POST /api/integrations/m01/result`, `/m04/result`, `/m07/result`, `Content-Type: application/json`. 최대 1 MiB. 모든 예시의 해시는 실제 manifest SHA-256으로 바꾸세요.

필수 metadata: `external_run_id`, `dataset_id`, `run_mode`(DEVELOPMENT/REFERENCE/OFFICIAL), `source_module`, `source_version`, `submitted_at`(timezone 포함 ISO 8601), `dataset_manifest_sha256`, `counts`, 그리고 `details` 객체 또는 `evidence` 객체/배열. metadata 문자열은 1~256자입니다. 모든 count는 0 이상의 정수이며 boolean은 허용하지 않습니다.

서버 `backend/config.json`의 `integration_datasets`에 dataset ID, manifest 경로, 허용 모드를 등록해야 합니다. 현재는 `current_site_dev_01`의 DEVELOPMENT와 `mock-dataset-01`의 REFERENCE가 등록되어 있습니다. 클라이언트는 경로나 명령을 지정할 수 없습니다. manifest 해시와 manifest에 등록된 입력 파일 해시를 모두 확인합니다. OFFICIAL은 metric이 일치하는 `run_mode/source_type=OFFICIAL`, `approved_for_official=true` manifest가 필요하며 개발/Reference 입력을 재사용할 수 없습니다. 이 등록과 승인 절차가 끝나기 전에는 공식 제출을 받지 않습니다.

`external_run_id + metric_id`는 모드와 서버 재시작에 관계없이 유일해야 합니다. 재전송은 409입니다. 정정 제출은 새 external ID로 보내고 `details.supersedes_external_run_id`에 이전 ID를 기록하세요. 중복 ID 예약 후 저장이 실패한 경우 자동 재시도 대신 저장 상태를 확인해야 합니다.

선택 필드: `cases` 배열, 자유 형식 `details`/`evidence`. M04 cases는 전체 실행, M07 cases는 전체 요청을 포함하며 count와 일치해야 합니다. M07 생성 실패 요청은 진단 근거이며 점수 분모에는 포함하지 않습니다. 일부 사례만 공유할 때는 `evidence`에 넣으세요. evidence URL은 보관만 하며 서버가 내려받아 검증하지 않습니다.

## M01: 수집 정확도

```json
{
  "external_run_id": "collector-dev-001",
  "dataset_id": "current_site_dev_01",
  "run_mode": "DEVELOPMENT",
  "source_module": "browser-collector",
  "source_version": "1.0.0",
  "submitted_at": "2026-10-08T12:00:00+09:00",
  "dataset_manifest_sha256": "REPLACE_WITH_ACTUAL_SHA256",
  "counts": {
    "defined_required_event_count": 100,
    "collected_required_event_count": 95,
    "total_collected_event_count": 110,
    "required_field_count": 5,
    "missing_required_field_count": 11,
    "defined_event_type_count": 10,
    "collected_event_type_count": 9
  },
  "details": {},
  "evidence": [{"case_id": "C01", "note": "원시 수집 로그 참조"}]
}
```

7개 counts 모두 필수입니다. defined required, total collected, required fields, defined types는 양수입니다. collected required ≤ defined required 및 total collected, missing ≤ total collected × required fields, collected types ≤ defined types 및 total collected를 검증합니다. missing은 **누락 필드 셀 수**, collected required는 **필수 이벤트를 충족한 수**입니다.

C1 = 100 × collected required / defined required

C2 = 100 × missing / (total collected × required fields)

C3 = 100 × collected types / defined types

점수 = 0.5 C1 + 0.3 (100 − C2) + 0.2 C3. 예시 점수는 94.9입니다. optional cases에는 고유 `case_id`가 필요하며 세부 구조는 evidence 용도로 보관합니다.

## M04: 자동 실행 성공률

```json
{
  "external_run_id": "runner-dev-001",
  "dataset_id": "current_site_dev_01",
  "run_mode": "DEVELOPMENT",
  "source_module": "selenium-runner",
  "source_version": "1.0.0",
  "submitted_at": "2026-10-08T12:00:00+09:00",
  "dataset_manifest_sha256": "REPLACE_WITH_ACTUAL_SHA256",
  "counts": {"total_execution_count": 2, "successful_execution_count": 1},
  "details": {},
  "cases": [
    {"case_id": "C01", "status": "PASS", "started_at": "2026-10-08T11:00:00+09:00", "completed_at": "2026-10-08T11:00:10+09:00"},
    {"case_id": "C02", "status": "TIMEOUT", "error_type": "TIMEOUT"}
  ]
}
```

두 counts 필수. total > 0, successful ≤ total. 점수 = 100 × successful / total. 예시 50%. 실패·timeout·skip을 분모에서 제거하면 안 됩니다. 연구개발계획서의 과거 분자/분모 오기와 구분하여 프로젝트에서 확정한 정상 성공률을 사용합니다.

optional cases: `case_id`, `status` 필수, `error_type/started_at/completed_at` 선택(근거로 보관). status는 PASS/FAIL/ERROR/TIMEOUT/SKIPPED. PASS 수와 successful count가 일치해야 합니다.

## M07: 생성 코드 유효성 및 정확도

```json
{
  "external_run_id": "codegen-dev-001",
  "dataset_id": "current_site_dev_01",
  "run_mode": "DEVELOPMENT",
  "source_module": "llm-code-validator",
  "source_version": "1.0.0",
  "submitted_at": "2026-10-08T12:00:00+09:00",
  "dataset_manifest_sha256": "REPLACE_WITH_ACTUAL_SHA256",
  "counts": {
    "generation_request_count": 3,
    "generated_code_count": 2,
    "syntax_pass_count": 2,
    "execution_pass_count": 1,
    "both_pass_count": 1
  },
  "details": {"m03_run_id": "실제_M03_run_ID"},
  "cases": [
    {"case_id": "C01", "generation_status": "PASS", "syntax_status": "PASS", "execution_status": "PASS", "final_status": "PASS"},
    {"case_id": "C02", "generation_status": "PASS", "syntax_status": "PASS", "execution_status": "FAIL", "final_status": "FAIL"},
    {"case_id": "C03", "generation_status": "FAIL", "syntax_status": "SKIPPED", "execution_status": "SKIPPED", "final_status": "FAIL", "error_type": "GENERATION_ERROR"}
  ]
}
```

5개 counts 필수. requests > 0, 0 < generated ≤ requests, syntax/execution ≤ generated, both ≤ min(syntax, execution), both ≥ syntax + execution − generated를 검증합니다.

공식 C2는 **LLM이 실제 생성한 전체 코드 수**입니다. 점수 = 100 × both / generated, 위 예시 50% (1/2), sample_count=2입니다. generation_request_count는 diagnostic/provenance로 보존합니다. 생성된 코드의 문법/실행 실패는 분모에 포함하고 generated=0이면 422 오류입니다. Sandbox는 requests20/generated18/syntax17/execution16/both15로 83.333…%를 검증합니다. 외부 모듈은 M03 run ID/시나리오 목록과 생성 코드·검사·실행 근거를 남깁니다. 서버는 count 내부 일관성을 검사하며 외부 수행 사실 자체를 인증하지 않습니다.

optional cases의 5개 status/ID 필드는 예시와 같이 필수, error_type은 선택입니다. status enum은 M04와 같습니다. 생성되지 않은 코드는 syntax/execution PASS가 될 수 없고 final PASS는 생성·구문·실행 모두 PASS일 때만 허용합니다.

## 성공·오류 응답과 저장

세 endpoint 모두 HTTP 201이며 동일한 result 형태입니다. 아래는 M04 예시의 핵심 필드입니다. M01은 score=94.9, sample_count=100, M07은 score=50, sample_count=2으로 바뀝니다.

```json
{
  "metric_id": "M04",
  "run_mode": "DEVELOPMENT",
  "status": "COMPLETED",
  "score": 50.0,
  "sample_count": 2,
  "target": null,
  "threshold_met": null,
  "official_pass": null,
  "pass": null,
  "provenance": {"source_module":"selenium-runner","source_version":"1.0.0","external_run_id":"runner-dev-001","submitted_at":"2026-10-08T12:00:00+09:00"},
  "evidence_file": "/api/evaluations/m04/runs/DEV-M04-<timestamp>-<id>/evidence.csv"
}
```

- 400: JSON 문법 오류, 잘못된 Content-Length.
- 403: localhost Host 또는 same-origin 조건 위반.
- 409: `{"status":"DUPLICATE_EXTERNAL_RUN","error":"Duplicate external_run_id for metric"}`.
- 422: 필수 metadata/count 누락, 분모 0, 불가능한 count, 모드/해시/provenance 불일치. 예: `{"status":"ERROR","error":"Invalid count: total_execution_count"}`.
- 500: 결과 파일 저장 실패. 새 ID로 재제출하기 전에 운영자가 저장/예약 상태를 확인하세요.

`results/<mode>/run_id/`에 `received_payload.json`, `result.json`, `evidence.csv`, `run_manifest.json`을 저장하고 해당 모드의 latest만 갱신합니다. 응답의 result_file/manifest_file/evidence_file로 다운로드합니다. target 미설정 시 threshold와 pass는 null, DEVELOPMENT/REFERENCE에서는 target 충족 여부와 무관하게 official_pass/pass=null입니다. 외부 결과가 없으면 화면은 EXTERNAL_MODULE_PENDING입니다.

## OFFICIAL 반입 계약

기준은 [R&D_COMPLIANCE.md](../R&D_COMPLIANCE.md)입니다. 공식 manifest는 metric_id, OFFICIAL source/run mode, approved_for_official=true, 입력 파일 해시 및 해당 official_contract를 요구합니다. REFERENCE/DEVELOPMENT 예제를 공식 성적으로 사용하지 않습니다.

- M01 official_contract: scenario_count=5, executions_per_scenario=2, independent_session_count=10, required_events_per_execution=10, defined_required_event_count=100, required_field_count=6, defined_event_type_count=8. required_fields와 event_types는 compliance 문서의 순서대로 명시합니다.
- M04 official_contract: fixed_script_count=20, execution_per_script=1. total_execution_count=20을 요구하며 실패를 포함합니다. manifest의 fixed_at은 제출 이전 사전 고정 시각, scripts_manually_modified=false, script_language=python, script_framework=selenium, files.scripts는 고정 코드 archive의 path/sha256입니다. 각 코드의 scenario_id/assert와 실제 1회 실행·시험 이전 고정 사실은 외부 근거로 확인합니다. 서버는 hash/선언/수량을 검증하며 Python 코드를 실행해 검사하지 않습니다.
- M07: C2=generated_code_count. 요청 건수는 공식 denominator가 아닙니다. 생성 코드와 M03·문법/실행 결과의 연결 근거를 보관합니다.

공식 target은 M01=65, M04=90, M07=80입니다. 외부 결과 evaluator version은 `external-counts-v2-generated-code-denominator`이며 과거 저장 결과를 재작성하지 않습니다.
