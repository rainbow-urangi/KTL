# 데이터 source 및 adapter 계약

상위 기준: [R&D_COMPLIANCE.md](../R&D_COMPLIANCE.md). 고정 contract 값은 `backend/official_contracts.py`의 OFFICIAL_SPEC에 정의합니다.

## 읽기 전용 Reference

`V62ReferenceProvider`는 `model/v6_2/frozen/`의 JSON/CSV를 원본에서 읽습니다.
`backend/reference_manifest.json`은 실제 보관 파일의 SHA-256 inventory입니다.
읽은 bytes의 해시를 확인한 뒤 같은 bytes를 파싱하며 사용한 입력 해시는 실행에 기록합니다.
존재하지 않는 필수 자료는 부분 동작, 변경된 자료는 ERROR입니다.
원본이나 runtime 파일을 수정하지 않습니다. 모델 `.pt`를 역직렬화하거나 재저장하지 않습니다.

M02: run_manifest, process_models, process_instances, process_instance_steps,
poc_scenario_comparison. M03: manifest, process_models/instances.
M06: manifest, workflow_consensus_assignments. 추가 frozen diagnostics도 provider.read로 검증 후 읽을 수 있습니다.
미사용 파일 전체를 매 요청마다 검증하는 것은 아니며 사용 파일별 검증을 수행합니다.

## 공식 source

`backend/config.json`의 official_manifests.M02/M05/M06에
`data/evaluation/` 아래 manifest 상대 경로를 설정합니다. 기본값은 null입니다.
공식 파일과 manifest는 모두 이 디렉터리 안에 있어야 하며 symlink로 경계를 벗어나면 거부합니다.

구조 설명용 예시이며 공식 데이터를 생성하지 않습니다:

```json
{
  "run_mode": "OFFICIAL",
  "source_type": "OFFICIAL",
  "approved_for_official": true,
  "dataset_id": "official-dataset-id",
  "metric_id": "M02",
  "model_version": "approved-output-version",
  "model_connected": true,
  "official_contract": {"business_unit_count":20,"ground_truth_process_count":5},
  "business_unit_ids": ["실제로 사전 정의한 고유 ID 20개를 기입"],
  "files": {
    "process_result": {"path": "data/evaluation/process_result.json", "sha256": "64 hex characters"},
    "ground_truth": {"path": "data/evaluation/ground_truth.json", "sha256": "64 hex characters"},
    "event_log": {"path": "data/evaluation/td03.csv", "sha256": "64 hex characters"}
  }
}
```

M02는 연결된 AI 엔진의 출력 export를 받으며 historical V6.2 weights를 필수로 요구하지 않습니다. M06은 승인 V6.2 measurement bundle을 받습니다. model_connected는 데이터 반입자의
출처 선언이며 이 코드가 신규 CSV inference를 수행한다는 의미가 아닙니다.
해시는 무결성 검증이고 공식 출처의 전자서명을 대체하지 않습니다.
DEV/REFERENCE 출처 표기, synthetic/dev_only 표기, 개발 dataset 해시는 거부합니다. frozen 원본 동일 해시는 M06 승인 bundle 반입을 제외하고 거부합니다.
표기를 제거하거나 변환한 데이터의 실제 출처를 bytes만으로 식별할 수 없으므로 공식 반입 manifest를 검토해야 합니다.
Ground Truth는 평가 입력에만 사용합니다.

## M02 공통 입력

ground_truth는 scenario ID를 사용하며 다음 형태입니다:

```json
{"processes":[{"id":"process-id","procedures":[{"id":"step-id","label":"절차명"}]}]}
```

공식 GT는 5개 scenario입니다. ID는 각 배열 내 고유해야 합니다.
OFFICIAL process_result의 processes는 사전 process ID와 procedures를 포함합니다. GT와 ID가 같은 맵 내에서만 비교하며 GT가 없는 추가 맵도 Accuracy 분모에 포함합니다. 절차 evidence_type 기본값은 direct이고 auxiliary/trajectory는 직접 정답에 포함되지 않습니다. REFERENCE는 저장된 best_instance_id를 사용합니다. OFFICIAL은 별도 pairing 없이 사전 ID로 비교할 수 있습니다. 업무20개 business_unit_ids 및 SHA-256을 가진 event_log(TD-03 CSV 또는 JSON)가 필요하며 선언된 업무 ID는 모델 입력에 전달하지 않습니다. 업무20종 실제 수행 사실과 TD-04의 업무명/절차 ID/화면/순서/허용 별칭은 반입 검토 대상입니다.

### M02 선택적 공식 pairing

구조는 `evaluation_contracts/m02-pairing.schema.json`에 정의되어 있으며 실제 pairing 데이터는 제공하지 않습니다.

```json
{
  "version": "1.0",
  "fixed_at": "2026-01-01T00:00:00Z",
  "ground_truth_independent": true,
  "pairs": [
    {"scenario_id": "OFFICIAL-SC01", "execution_id": "EXEC-001", "process_instance_id": "INSTANCE-001", "selection_method": "execution_linked"}
  ]
}
```

위 한 행은 구조 설명용입니다. pairing을 제출하는 경우에만 5개 GT scenario 각각에 정확히 한 pairing이 필요합니다. 미제출 시 사전 process ID를 사용합니다.
selection_method는 `execution_linked` 또는 `predeclared`만 허용합니다.
고정 시각은 timezone을 포함하고 source 검증 시작 이전이어야 합니다.
지정한 instance가 존재하며 그 execution_id가 pairing의 execution_id와 같아야 합니다.
미지정 instance를 GT 점수로 선택하지 않습니다. 연결되지 않은 맵도 Accuracy 분모에 유지합니다. 동일 instance 중복 pairing은 거부합니다.
`files.pairing.path/sha256`으로 무결성을 검증하고 run manifest에
pairing_file, pairing_sha256, pairing_fixed_at, pairing_pairs, selection_method를 기록합니다.

고정 시각과 GT 독립성은 반입자의 선언입니다. 프로그램은 선언·해시·ID 연결을 검증하고
GT 기반 선택 기능을 제공하지 않지만, 외부에서 사후 선택 후 시각을 소급 기재했는지까지 증명하지는 못합니다.
시험 운영에서는 pairing의 사전 확정 기록 또는 실행/session 연결 근거를 보관해야 합니다.

### M02 승인 alias

구조는 `evaluation_contracts/m02-aliases.schema.json`입니다. 실제 승인 alias 파일은 생성하지 않았습니다.

```json
{"version":"1.0","aliases":[{"canonical":"교류학생관리(IN)","accepted":["교류학생관리 IN"]}]}
```

등록된 canonical/accepted 모두 NFKC → casefold → 모든 Unicode whitespace 제거 → strip을 적용합니다.
정규화 후 충돌하는 alias, 빈 canonical은 거부합니다. 부분 문자열·fuzzy·semantic 매칭은 없습니다.
REFERENCE는 `evaluation_contracts/m02_aliases.json`이 존재하면 읽고, 없으면 정규화만 사용합니다.
OFFICIAL은 이 Reference 위치를 자동 사용하지 않습니다. 공식 manifest의 files.aliases에
path, sha256, fixed_at을 명시해야 하며 파일은 data/evaluation 내부에 있어야 합니다.
fixed_at은 timezone을 포함하고 source 검증 시작 이전이어야 합니다. files.aliases가 없으면 alias를 사용하지 않습니다.
검증한 bytes를 메모리에 보관해 해당 실행 동안 사용합니다.
run manifest의 alias_file/alias_sha256 및 input_sha256에 기록하며 미사용 시 null입니다.

## M06 공식 입력

manifest 공식 contract: `source=approved_v6_2_measurement_bundle, workflow_count=563, embedding_dimension=128, cluster_count=12`. model_version=V6.2, feature_space=workflow_embedding_128, timezone을 포함한 시험 전 fixed_at이 필요합니다. files.clustering에 JSON path/sha256을 기록합니다.
JSON은 workflow_ids(고유 문자열563개), features(563×128), labels(563개/군집12종), row_order="workflow_ids"입니다. 같은 index는 반드시 같은 workflow입니다. 원본 출처와 정렬을 반입 시 확인합니다. 누락된 bundle은 OFFICIAL_M06_BUNDLE_MISSING이며 80차원/DEVELOPMENT 입력으로 fallback하지 않습니다. scikit-learn이 없으면 교차 검증 불가로 NOT_CONFIGURED이며 공식 점수를 확정하지 않습니다.

## M05 공식 입력과 CleaningModelAdapter

manifest.files.events의 JSON:

```json
{"events":[{"id":"event-id","features":{"event_type":"click"},"label":"REMOVE","category":"duplicate"}]}
```

manifest는 official_contract의 official_event_count=200, keep=100, remove=100, official_dataset_must_be_held_out=true 및 held_out=true, used_for_training=false, used_for_development=false를 요구합니다. false이거나 누락이면 adapter 호출 전에 거부합니다. 학습/개발 경로의 파일은 공식 반입 경로로 사용하지 않습니다.
200개 고유 ID, KEEP/REMOVE 각 100개, REMOVE category는 duplicate/noise/repeated_action/
irrelevant_action 각 25개입니다. config.cleaning_model_version과 adapters.cleaning argv를 설정합니다.
stdin JSON으로 id/features만 전달합니다. label/category/ground_truth/expected_label/prediction 키가
features 내부에 중첩되어 있어도 거부합니다. 정답의 파생 특성 역시 입력하지 않아야 합니다.
stdout 응답은 `{"model_version":"configured-version","predictions":[{"id":"event-id","label":"KEEP"}]}`.
모든 ID를 정확히 한 번 반환해야 합니다. stderr는 진단용이며 기본 제한 시간은 120초입니다.

## M03 구조 및 검증

OFFICIAL contract: business_unit_count=20, generation_attempt_per_business_unit=1, official_denominator=20. business_unit_ids 고유20개와 files.event_log를 요구합니다. M02/M03 manifest가 모두 등록되면 TD-03 SHA-256과 업무 ID 집합이 같아야 합니다. TD-05 20업무 정의도 사전 고정합니다. 별도 수집 dataset을 만들지 않습니다.

BusinessUnit: id, name, steps[{id,label}].
StructuredScenario: id, name, business_unit_id, generator_version,
steps[{id,action,expected_outcome}]. `validate_business_unit`/`validate_scenario`가 필수 필드와 ID를 검증합니다.
ScenarioGeneratorAdapter.generate가 이 둘을 연결하는 계약입니다.
현재 공통 validator는 id/action/expected_outcome만 검사하며 공식 M03 성공 판정기는 아직 연결되지 않았습니다. 연결 시 KTL 필수 단계 순서·action/target 검증과 20회 분모를 적용해야 합니다. 현재 validator 통과만으로 공식 생성 성공을 인정하지 않습니다.
현재 실제 생성기는 미연결이며 UI에는 V6.2 representative_path를 입력 예제로만 보여줍니다.
SP-only 경로에 의미나 동작을 임의로 부여하지 않습니다. 12개 모델을 공식 20개 업무 단위로 바꾸지 않습니다.

## 외부 integration 계약

`backend/contracts.py`에 Python Protocol을 정의했습니다.

| 인터페이스 | 입력 | 응답 계약 |
| --- | --- | --- |
| CollectorAdapter.collect | required_events | collected_events: scenario_id, execution_id, event_id, event_type |
| TestRunnerAdapter.execute | StructuredScenario 목록 | 모든 실행 attempt: scenario_id, success, evidence |
| LLMCodeGeneratorAdapter.generate | StructuredScenario | code, language=python, framework=selenium, model, version |
| CodeValidationAdapter.validate | 생성 code 객체 | syntax_pass, execution_pass |

M04 실패 실행은 분모에서 제외하지 않으며 M07은 syntax와 execution 모두 성공해야 합니다.
현재 외부 engine을 호출하지 않고 EXTERNAL_MODULE_PENDING을 반환합니다.
기존 Selenium script는 비활성 legacy 자료입니다. 향후 담당자가 실제 adapter 및 결과 검증을 연결해야 합니다.
내부 ownership은 registry에만 존재하며 시험관 API/UI에 제공하지 않습니다.
