# 외부 연동 API — 2026-11-12 계약 점검

현재 연동 대상은 **M03 Scenario Generation → M04 Selenium Runner → M07 LLM Code Generation**입니다.
기준은 [R&D_COMPLIANCE.md](../R&D_COMPLIANCE.md)의 최신 사용자 확인 협의입니다. 보관된 2026-09-18 KTL PDF의 구판 수량과 구분하며 최신 서명본 확보는 TODO입니다.

## 시작하기

`python3 -m backend.server --port 8000` 실행 후 [Developer Sandbox](http://127.0.0.1:8000/developer/integration-api)를 엽니다.
기본 카드는 M03/M04/M07 순서이며 8/10=80%, 9/10=90%, 16/20=80% 예시를 제공합니다. 표시되는 실제 점수는 서버 응답입니다. Mock은 실제 업무 생성·Selenium·LLM 실행을 수행하지 않습니다.

Sandbox는 `mock-dataset-01` / REFERENCE 합성 예시만 전송합니다. 생성 응답은 200, 평가 접수는 201입니다. 전송·JSON/curl 복사 시 고유 external ID와 제출 시각을 생성합니다. 실제 결과는 `results/reference/`에 저장되므로 공식 시험 근거로 사용하지 않습니다.

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

동일 BU/workflow ID는 동일 Mock 응답을 반환합니다. 실제 업무명이나 GT를 생성하지 않습니다. REAL도 기존 응답 구조를 유지합니다. 현재 기본 `backend/config.json`의 `m03_real_generator`가 기존 관측 business-step snapshot에 연결되며 `adapters.scenario_generation`보다 우선합니다. 로컬 REAL은 DEVELOPMENT 전용이며 REFERENCE/OFFICIAL은 422입니다. binding과 외부 adapter를 모두 제거한 경우에만 503 NOT_CONFIGURED입니다. MOCK+OFFICIAL은 422입니다.

## M03 평가

`POST /api/integrations/m03/result`: 공통 metadata와 `scenarios` 배열을 전송합니다. 서버는 [JSON Schema](../evaluation_contracts/m03-scenario.schema.json)에 해당하는 필수 타입/항목 및 1부터 연속된 단계 순서를 검증합니다.

```json
{"business_unit_id":"BU01","scenario_id":"SCN-001","status":"SUCCESS","steps":[{"order":1,"action":"click","target":"대상 메뉴"}]}
```

위 객체들을 scenarios에 넣습니다. workflow_id/status/description/expected_result/source_workflow_id/evidence는 선택 정보입니다. 성공은 schema_valid AND step_order_valid AND action_present AND target_present이며 명시적 FAILED는 실패입니다. action/target/order/유효한 schema가 없는 **제출된 생성 실패 결과는 분모에 유지**합니다. 누락된 실행을 자동 성공/실패로 꾸미지 않습니다. 빈 scenarios, 업무 ID 누락·중복, 유효 scenario_id 중복은 422입니다.

OFFICIAL은 고유 업무단위 정확히 10개가 필요합니다. manifest `business_unit_ids`와 일치해야 하며 `official_contract={"business_unit_count":10,"generation_attempt_per_business_unit":1,"official_denominator":10}`입니다. Mock 결과는 공식 제출할 수 없습니다. 비공식은 1~10개를 허용하고 제출된 전체 업무단위 수를 분모로 사용합니다. 8개 성공/10개=80%, 목표≥80%. details의 검증 결과와 CSV로 실패 원인을 확인합니다.

## M04 자동 실행

`POST /api/integrations/m04/result`: 공통 metadata와 다음 counts를 전송합니다.

```json
{"total_execution_count":10,"successful_execution_count":9,"failed_execution_count":1}
```

`passed_execution_count`는 successful_execution_count의 별칭입니다. 두 필드를 동시에 보내면 같아야 합니다. failed count는 선택이나 제출 시 total-success와 일치해야 합니다. 전체 실패·ERROR·TIMEOUT·SKIPPED를 분모에 포함하여 9/10=90%, 8/10=80%, 목표≥90%입니다.

선택 cases는 모든 실행을 포함하며 `case_id,status`가 필요합니다. status는 PASS/FAIL/ERROR/TIMEOUT/SKIPPED, PASS 수는 성공 count와 일치해야 합니다. 서버는 실행기를 직접 실행하지 않습니다.

OFFICIAL: 사전 고정한 Selenium/Python script 10건, 각 1회 실행. `official_contract={"fixed_script_count":10,"execution_per_script":1}`, `fixed_at`은 제출 이전 시각, `scripts_manually_modified=false, script_language=python, script_framework=selenium`, `files.scripts`에 archive path/sha256이 필요합니다. 비공식 수량은 고정하지 않습니다. 고정 시점과 실제 실행의 진실성은 외부 로그로 증빙합니다.

## M07 코드 검증

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

평가 성공은 201입니다. 핵심 응답 예시:

```json
{"metric_id":"M03","run_mode":"REFERENCE","status":"COMPLETED","score":80.0,"sample_count":10,"target":80,"official_pass":null,"pass":null,"details":{"successful_scenario_count":8,"total_scenario_count":10}}
```

M04는 score90/sample10/target90, M07은 score80/sample20/target80입니다. 실제 응답에는 run_id, provenance, input_sha256, evidence_file 등이 추가됩니다. REFERENCE/DEVELOPMENT의 official_pass/pass는 항상 null이며 OFFICIAL에서만 공식 판정합니다.

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

`results/<mode>/<run_id>/`에 received_payload.json/result.json/evidence.csv/run_manifest.json을 저장합니다. 응답 다운로드 URL로 확인합니다. 제출된 evidence URL은 보관하며 서버가 외부 URL을 내려받거나 실제 수행 사실을 인증하지 않습니다. 새 evaluator version은 `external-integration-v3-ktl-20261026`이며 과거 결과는 재작성하지 않습니다.

## Legacy / 현재 연동 대상 아님

`POST /api/integrations/m01/result`와 전체 KTL dashboard의 M01은 유지됩니다. 기존 공통 metadata와 일곱 counts(defined_required_event_count, collected_required_event_count, total_collected_event_count, required_field_count, missing_required_field_count, defined_event_type_count, collected_event_type_count)를 받습니다. 산식은 0.5*C1+0.3*(100-C2)+0.2*C3, 목표65%입니다. 기존 요청·응답·201·검증 계약은 유지하며 합성 예시는 integration-samples.json의 legacy_samples에서 확인합니다.

M06의 최신 설명은 **최종 업무패턴 분석 엔진의 workflow embedding + cluster label**입니다. 신규 연동 API는 제공하지 않으며 이번 작업에서는 M06 evaluator와 모델 구현을 변경하지 않습니다. M05는 별도 검증된 20 target / 전체 417 context의 DEVELOPMENT F1 0.8235 흐름을 유지하며 이번 API 계약 범위에 포함하지 않습니다.


## 2026-11-12 주니어 연동 계약 고정 범위

아래 표는 희망 구조가 아니라 현재 route/검증기 구현입니다. wire request/response, 계산기, 데이터, config는 이 점검에서 변경하지 않습니다. M03의 내부 생성 개선도 아래 요청/응답 core를 유지해야 합니다. 추가 metadata는 허용되므로 응답의 알 수 없는 필드는 무시하세요.

### 접속과 역할

Base URL: `http://127.0.0.1:8000` (`python3 -m backend.server --port 8000`). 현재 서버는 loopback에만 bind하며 Host는 해당 port의 localhost/127.0.0.1, Origin은 없거나 같은 origin이어야 합니다. **다른 PC에서 직접 호출하는 원격 공개 API가 아닙니다.** 주니어 프로그램은 동일 호스트에서 실행하거나 별도 승인된 배포 계약이 필요합니다. 인증/프록시 설정을 임의 우회하지 않습니다.

| Method / URL | caller → receiver | 목적 / 필수 요청 | 선택 요청 | 응답 / HTTP | 현재 상태 / 테스트 |
|---|---|---|---|---|---|
| POST `/api/m03/generate` | 외부 scenario consumer → RainbowKTL generator | `business_unit_id`, `workflow_id`: 공백 아닌 1~256자 문자열 | `run_mode` (기본 DEVELOPMENT), `generator_mode` (기본 MOCK). 이 4개 외 요청 key 거부 | 200: BU/workflow/scenario ID, status, steps, run_mode, generator_mode, synthetic, official_pass | MOCK/REAL 구현·합성 HTTP 검증. 기존 REAL snapshot binding 연결 |
| POST `/api/integrations/m03/result` | M03 생성/연동 모듈 → 중앙 evaluator | 공통 metadata + `scenarios` 1~10개 | `counts`, row의 workflow_id/status/description/expected_result/evidence; `run_id`는 external_run_id 대체 가능 | 201: 공통 평가 응답 + 중앙 schema/order/action/target 판정 | 구현·합성 HTTP 검증 |
| POST `/api/integrations/m04/result` | 주니어 Selenium Runner → 중앙 evaluator | 공통 metadata + `counts.total_execution_count`, `counts.successful_execution_count` 또는 passed 별칭 | failed_execution_count, cases(case_id/status/error/evidence) | 201: 공통 평가 응답 + 집계 count | 구현·합성 HTTP 검증; 실제 Runner 실행은 외부 책임 |
| POST `/api/integrations/m07/result` | 주니어 LLM code/실행 모듈 → 중앙 evaluator | 공통 metadata + counts 5종; OFFICIAL은 cases 필수 | 비공식 cases, error/evidence | 201: 공통 평가 응답 + 교집합 검증 | 구현·합성 HTTP 검증; 실제 생성/실행은 외부 책임 |

공통 평가 응답 필드: `metric_id, metric_name, run_id, run_mode, dataset_id, source_type, status, score, sample_count, target, operator, threshold_met, official_pass, pass, started_at, completed_at, error, details, evaluator_version, input_sha256, input_paths, dataset_manifest_sha256, provenance, evidence_file, result_file, manifest_file, evidence_files`.
`details.rows`는 CSV 근거와 같습니다. `threshold_met`는 모든 모드의 목표 비교이며 `pass/official_pass`는 OFFICIAL 이외 null입니다. 외부는 score/PASS를 확정하지 않습니다.

### 중앙 계산 책임과 제한

- M03: 외부가 시나리오 원문을 제출하고 서버가 schema, 연속 order, action, target, FAILED status를 판정합니다. schema 완전성 검증이지 실제 브라우저 수행 성공 인증은 아닙니다.
- M04: 외부가 실행 count와 가능하면 전체 cases를 제출합니다. 서버가 count 범위를 검증하고 성공/전체×100을 계산합니다. cases가 있으면 PASS 수를 count와 대조합니다. **현재 cases는 OFFICIAL에서도 선택**입니다. 개별 case 강제는 별도 호환성 변경이므로 이번에 추가하지 않습니다.
- M07: OFFICIAL은 전체 cases가 필수이고 서버가 generation/syntax/execution 모두 PASS인 교집합 C1을 계산합니다. C2=20. 비공식 count-only 호환 경로는 유지됩니다.
- 외부 `score` 필드는 계산에 사용하지 않습니다. raw/count의 진실성과 실제 실행은 외부 로그/evidence가 뒷받침해야 합니다. 서버는 원격 evidence URL을 실행/다운로드하지 않습니다.

### 고정 수량과 현재 차단 상태

FINAL 운영 목표는 M03 10 business units / M04 10 scripts / M07 C2=20입니다. `backend/official_contracts.py`의 해당 3개 계약과 일치합니다. 내부 non-OFFICIAL 부분표본/가변 분모는 호환 API이며 FINAL 수량을 바꾸는 근거가 아닙니다.

현재 등록 dataset은 mock-dataset-01(REFERENCE), current_site_dev_01(DEVELOPMENT)이며 승인 OFFICIAL dataset은 기본 config에 등록되어 있지 않습니다. 따라서 **schema 연동과 합성 검증 가능 ≠ 실제 FINAL 시험 실행 준비 완료**입니다. REAL M03 연결은 완료했지만 승인된 10 업무단위/10 scripts/20 codes의 manifest/evidence는 별도 준비가 필요합니다.

기존 상위 문서의 2026-09-18 PDF/서명본 TODO 표현은 역사적 설명입니다. 현재 `docs/compliance/source/KTL_TEST_CRITERIA_FINAL.pdf`가 존재합니다. 이번 점검에서는 원본 PDF나 시험 데이터 자체를 수정하지 않습니다. M05 200건/수량상충 문구 등 범위 밖 stale 값은 FINAL API 수량으로 재사용하지 않습니다.

### 재시도와 오류

생성 MOCK은 동일 BU/workflow에 결정론적 응답이며 저장 run을 만들지 않습니다. REAL 재호출의 외부 부작용/idempotency는 보장하지 않습니다. result 제출은 `(metric, external_run_id)` 전역 중복 방지이므로 같은 제출 재시도는 409입니다. 다른 metric에서 같은 ID는 별도입니다. 실패/timeout 후 무조건 새 ID로 재제출하지 말고 저장 상태를 확인하세요. 저장 실패 시 RESERVED가 남을 수 있습니다.

오류 예시는 세 result endpoint에 공통입니다:
```json
{"status":"ERROR","error":"Required field: dataset_id"}
```
```json
{"status":"DUPLICATE_EXTERNAL_RUN","error":"Duplicate external_run_id for metric"}
```
REAL 미설정은 503 + status NOT_CONFIGURED입니다. envelope 형식 오류는 422, JSON 문법/Content-Length 오류는 400, origin/Host 위반은 403입니다. 실패한 scenario의 action 누락은 envelope 거부가 아니라 분모에 포함된 실패 row가 됩니다.

**Malformed enum 타입:** 공통 `require_string_enum`은 membership 검사 전에 문자열 타입을 검증합니다. list/dict/bool/number/null은 구조화된 HTTP 422 오류로 처리합니다. 예: `{"status":"ERROR","error":"Invalid type for generator_mode: expected string"}`. 기존 필수 필드 검증이 먼저 적용되는 외부 `run_mode` 오류는 기존 `Required field: run_mode` 문구를 유지합니다. 정상 문자열 enum과 success response 계약은 바뀌지 않습니다.


### 완전한 request/response 예시와 검증

`frontend/integration-samples.json`의 samples 배열은 각 endpoint의 **완전한 실행 가능한 JSON request와 response 예시**입니다. 위 curl 생성 절차는 실제 manifest hash를 보존하며 제출 ID/시간만 새로 만듭니다. 합성 REFERENCE 데이터이므로 실제 점수 증빙으로 쓰지 않습니다. M03 생성 예시는 위 본문과 동일합니다.

검증 파일: `tests/test_junior_api_contract.py`, `tests/test_latest_integration.py`, `tests/test_integration_sandbox.py`. 모든 HTTP 제출은 임시 디렉터리/합성 fixture만 사용하며 기존 results나 dataset을 변경하지 않습니다. M03 REAL은 임시 합성 snapshot으로 실제 HTTP 생성/재시도/잘못된 workflow/허용되지 않은 mode를 검증합니다. 기본 binding의 기존 snapshot/code/schema hash도 읽기 전용으로 대조합니다. 실제 10건 성능 재평가 및 브라우저 클릭은 이번 작업에서 하지 않습니다.


### M03 REAL 연결 상세 (2026-11-12)

- 호출 경로: `POST /api/m03/generate` → `backend.m03_integration.generate` → `backend.m03_real_generator.generate_observed`.
- 기본 설정: `backend/config.json`의 `m03_real_generator.snapshot_path` = `results/development/m03_current_semantics_20261109/business_steps.json`; `snapshot_sha256` = `86b1e77c8ca4ec365806d7d145d99ffa802bc097347b3db16ed9b3f600503f39`.
- workflow ID는 위 snapshot의 `canonical_instance_id` 하나와 정확히 일치해야 합니다. caller의 business_unit_id는 응답 identity이며 GT를 generator에 전달하지 않습니다. 외부에 임의 workflow 데이터를 등록하는 API는 아닙니다.
- 이 snapshot은 기존 raw `data/development/current_site_unseen_validation_v1/events.csv`와 동결 predictions에 기존 semantic/process-map 처리를 적용해 보존한 출력입니다. API는 이를 읽어 observed steps를 투영하며 workflow model을 재추론하지 않습니다.
- 기존 6/10 진단의 `remeasure.py`도 같은 `generate` → `generate_observed`를 사용했습니다. generator SHA-256 `cdb9e03002923e9166f515c09059efcc459a4a29c85b19a2e84ea71c94cbe52b` 및 scenario schema SHA-256 `4ed1caada4bb194de2a95ac4954e6aa7b86479646f8cfa601fa3c4d4277de101`이 해당 manifest와 같습니다. 이번 변경은 API binding과 malformed 입력 검증뿐이며 generator logic을 변경하지 않았습니다.
- 기존 6/10은 `REUSED_PRIOR_PROPOSAL_COHORT_NOT_FINAL_TEN_BUSINESS_UNITS` 진단입니다. 승인된 FINAL 10 business units 성능으로 표현하지 않습니다.
- response의 기존 `issues`, `generator_version`, `source_process_id`, `source_snapshot_sha256`, `readiness_only` provenance를 유지합니다. HTTP 200의 `status: FAILED`는 생성 경로 실행 성공과 시나리오 생성 실패를 구분하며, 평가 시 실패를 분모에서 제거하지 않습니다.
- 현재 로컬 generator는 파일/측정 결과를 쓰지 않으며 동일 snapshot/ID에 결정론적 응답입니다. 향후 외부 adapter의 부작용까지 보장하는 계약은 아닙니다.
- 주니어 프로그램의 실제 배치 host는 현재 문서에서 확정되지 않았습니다. 동일 host이면 현재 loopback 그대로 사용합니다. 별도 PC/서버 호출이 필요하면 `REMOTE_ACCESS_REQUIRED`로 분리하고 별도 승인 전 공개 bind/프록시/인증 우회를 하지 않습니다.
