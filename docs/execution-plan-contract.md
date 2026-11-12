# 관측 M03와 실행계획 계약

M03 원본 관측 단계와 별도의 실행계획을 보관한다. `page_entry`, `selection`, `api_confirmation`, 팝업 등 분석 어휘는 그 자체로 브라우저 조작을 뜻하지 않는다. 실행계획은 검증한 원 CSV·capture manifest의 event 근거, 독립 업무 정의의 실행 조건, 새 시험 매개변수를 사용한다. M03의 형식/정답 순서 평가 정답과 별개이며 평가 reference를 입력하지 않는다.

`backend.execution_plan.load_observations(root, source, plan)`은 runtime root 내부에 복사한 원바이트 CSV와 capture manifest를 SHA로 검증한다. 선언한 SHA는 M03 원본의 `source_csv_sha256`, `source_capture_manifest_sha256`와 같아야 한다. header·건수·byte count, event ID/time/session, capture/tab/frame/opener path, session-local sequence, page navigation 전환, M03 occurrence/event/csv_row/session 대응을 확인한다. `csv_row`는 헤더를 제외한 1기반 worker archive ordinal이다. timestamp 정렬이나 node ID 역추정으로 빠진 연결을 만들지 않는다. 현재 단일 root tab/frame만 실행계획으로 연결한다.

`prepare(source, plan, config=None, *, observations=verified_bundle)`는 I/O 없는 변환이다. 반환값은 `scenario`, 기존 v1 typed `contract`, 정규화 `execution_plan`이다. 원본 source는 수정하지 않는다. 실행 가능한 파생 단계만 1부터 재번호를 매기고 기존 `m04.checks.prepare_contract`에 그대로 통과시킨다. 검사 종류·기대 결과·실제 동작 검사를 완화하지 않는다. 준비 부족은 `EvaluationError(..., 'NOT_READY')`이며 실행 실패율 0%로 바꾸지 않는다.

```json
{
  "version": 1,
  "source_scenario_sha256": "<source_digest(source)>",
  "observation_sources": {
    "csv": {"path": "inputs/events.csv", "sha256": "<original CSV SHA>"},
    "capture_manifest": {"path": "inputs/capture-manifest.json", "sha256": "<original manifest SHA>"}
  },
  "parameter_source": "NEW_TEST_PARAMETERS",
  "parameters": {"title": "새 시험 제목"},
  "items": [
    {
      "kind": "execute",
      "source_refs": [{"order": 1, "event_ids": ["<original input event ID>"]}],
      "action": "input",
      "target": {"by": "css selector", "value": "<original CSS>"},
      "value_param": "title",
      "expected_result": "독립 실행 조건: 새 시험 제목이 입력된다",
      "checks": [{"kind": "value", "expected_param": "title"}]
    },
    {
      "kind": "reference",
      "source_refs": [{"order": 2, "event_ids": ["<original API event ID>"]}],
      "reason": "API 완료 관측은 추가 요청으로 재실행하지 않는다"
    }
  ]
}
```

`source_digest`는 기존 실행 조건과 동일한 UTF-8, sorted keys, indent=2, newline JSON의 SHA-256이다. 정규화 계획의 `source_mapping`은 원 order/occurrence/node/event/row/session과 실행 order 또는 참조 제외를 연결한다. 저장된 mapping은 다시 계산한 내용과 같아야 한다.

- `execute`: 원 click→click, 원 page_view/route_change→동일 URL의 open/navigate, 원 native text/textarea 변화→input/type/clear, native select→select, 실제 submit→submit만 입증한다. 실행 CSS는 해당 원 event의 target_selector/locator CSS/target_key와 정확히 일치해야 한다.
- `check`: 명시한 독립 실행 조건을 기존 `verify`와 typed checks로 변환한다. 추가 검사 selector는 실행 조건에 명시하며, 어댑터가 관측 API를 클릭이나 요청 생성으로 추측하지 않는다.
- `reference`: 원본 근거와 제외 이유를 유지하며 실행 단계 수에서 제외한다. 모든 원 M03 evidence event는 세 분류 중 하나에 한 번씩 포함되어야 한다. 모든 항목을 reference로만 분류한 계획은 실행 준비가 되지 않는다.

압축된 관측 input 하나가 여러 native control event를 담으면 같은 원 order를 event ID별로 분할할 수 있다. source_refs의 event를 중복하거나 뒤바꾸거나 누락할 수 없다. 입력은 `value_param`, 기대값은 `expected_param`으로 새 parameters를 바인딩한다. `input_data`나 마스킹된 과거 값으로 입력값을 복원하지 않는다. 인증 입력과 평가 정답은 기존 guard에 따라 금지하며 로그인은 기존 환경변수 경로를 사용한다.

원본 M03, 실행계획, 파생 실행 시나리오, typed contract는 각각 SHA와 개정 연결을 보관한다. M07에는 파생 steps와 typed contract만 전달하고 raw CSV와 실행계획 전체를 prompt에 넣지 않는다. 실행 후에도 이를 M03 독립 정답 순서 평가 성공으로 간주하지 않는다. 저장·M07/M04 전달은 실행 조건 저장 모듈의 개정 snapshot 계약을 사용한다.

조회 내용 검사용 `text_equals_target`은 `target`/`property`와 `other_target`/`other_property`의 실제 DOM 문자열을 trim 후 비교한다. `nonempty`는 `target`/`property`의 유효한 내용 존재를 검사한다. property는 `text` 또는 native input/textarea의 `value`다. 각 locator는 표시된 요소 한 개여야 하며 비교 대상은 서로 다른 DOM 요소여야 한다. 인증 요소, 공백, `-`/`N/A` 등 고정 placeholder, `[MASKED]`/`[REDACTED]` 등 고정 마스킹 표시와 전체 별표 문자열은 통과하지 않는다. 부분 마스킹을 일반적으로 식별하는 검사는 아니므로 업무 정의에서 마스킹되지 않는 비교 대상을 선택해야 한다. 읽은 문자열은 결과나 로그에 보관하지 않고 boolean 검사 결과만 남긴다. 컨테이너 표시만으로 상세 조회 완료를 판정하지 않으며 정확한 typed predicate를 기다린 뒤 assert한다.

M04 Runner는 표준 Selenium `WebElement.submit()`을 관측한다. script-origin 단계의 정확한 form target을 기존 동작 검사로 확인하고 원 메서드 성공 뒤에만 submit 수행을 기록한다. 실패한 submit이나 임의 `execute_script`는 submit 성공 근거가 아니다. PREPARED scroll-v2와 M07 prompt v5는 native 조작 전 instant center scroll 및 viewport/center hit 대기를 사용하며 JavaScript click으로 바꾸지 않는다.

실행계획 저장은 `POST /api/development/m07/execution-plans`의 JSON 계약(`m03_run_id`, `scenario_id`, `execution_plan`, 최대 1MiB)으로 제공한다. 계획 편집 GUI는 구현하지 않았다. 저장·준비 완료는 실행 성공과 별개이며, 준비 거부는 실행을 하지 않은 `NOT_READY`로 보관한다. 실제 실행을 시작한 뒤의 예외·기대 조건 불일치는 실행 실패로 보관하고 원본 코드와 계약을 수정하지 않는다.
