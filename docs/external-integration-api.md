# 외부 연동 API — 2026-10-26

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

동일 BU/workflow ID는 동일 Mock 응답을 반환합니다. 실제 업무명이나 GT를 생성하지 않습니다. REAL도 동일 응답 구조를 사용하며 서버의 `adapters.scenario_generation` 설정이 필요합니다. 미설정 시 503 NOT_CONFIGURED, MOCK+OFFICIAL은 422입니다. 실제 generator 연결은 TODO입니다.

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

M06의 최신 설명은 **최종 업무패턴 분석 엔진의 workflow embedding + cluster label**입니다. 신규 연동 API는 제공하지 않으며 이번 작업에서는 M06 evaluator와 모델 구현을 변경하지 않습니다. M05도 수량 상충 확인 전까지 유지합니다.
