# V6.2 runtime metadata 복구

이번 작업은 historical reference CSV의 preprocessing 상태만 복구합니다.
모델 학습, weight 저장, 모델 forward, boundary 계산, prototype optimization,
Ward clustering, consensus K search, process 출력 생성은 수행하지 않습니다.
기존 frozen/reference 파일 및 M02/M06 evaluator는 변경하지 않습니다.

## 복구 근거와 검증

`scripts/recover_v62_runtime.py`는 검토된 notebook, bundle, historical CSV의
SHA-256을 고정하여 다른 데이터로 metadata를 fit하는 것을 거부합니다.
전체 notebook을 실행하지 않고 cell 7의 검토된 preprocessing 함수와
원래 `tr_num`, `mu`, `sd` 대입식만 실행합니다. semantic encoder도 호출하지 않습니다.

CSV를 두 번 독립적으로 읽어 vocabulary, structural vocabulary, mean/std,
training/validation event 순서 hash가 모두 같은지 확인한 후 저장합니다.
checkpoint는 제한된 pickle 타입과 tensor descriptor만 읽습니다.
PyTorch 모델 객체나 weight tensor를 만들지 않습니다.

검증된 historical split은 32,273 events, 32 streams, training 25,808건,
validation 6,465건입니다. stream별 시간순 앞 80%를 사용하며, 전체 데이터에서
delta_sec를 먼저 계산한 후 split합니다. 새로운 입력을 이 크기로 제한하지 않습니다.

| 범주형 feature | 복구 vocabulary 크기 | checkpoint shape |
| --- | ---: | --- |
| event_type | 4 | 4 × 128 |
| interaction_type | 19 | 19 × 128 |
| element_tag | 8 | 8 × 128 |
| api_method | 3 | 3 × 128 |

모든 vocabulary는 `<PAD>`=0, `<UNK>`=1입니다. 실제 token 이름을 보존하며
예시의 `PAD`/`UNK`로 변경하지 않습니다. 빈 문자열과 미등록 값은 UNK로 처리됩니다.
빈도 동률에서는 원본 `Counter.most_common()`의 최초 등장 순서를 유지합니다.
세 structural vocabulary는 bundle의 token 목록과 순서까지 완전히 일치합니다.

| 수치 feature | mean | std (epsilon 포함) |
| --- | ---: | ---: |
| log1p(delta_sec) | 0.4013843536376953 | 0.6648135185241699 |
| log1p(step_duration_ms) | 4.696194648742676 | 2.4875926971435547 |
| log1p(api_latency_ms) | 1.1665234565734863 | 2.041043996810913 |
| api_status_code / 600 | 0.085780069231987 | 0.1457352489233017 |

원래 식은 float32 배열의 `mean(0)`, `std(0) + 1e-6`이며 ddof=0입니다.
현재 복구 환경은 Python 3.10.5, NumPy 1.23.5, pandas 2.2.3입니다.
과거 학습 환경의 정확한 라이브러리 버전과 삭제된 원본 stats/vocab 파일은 없어,
원본과의 독립적인 byte 단위 비교는 UNRESOLVED입니다. 동일한 source와 원본 코드로
결정성 있게 재구성했고 shape 및 structural mapping 검증을 통과했다는 범위로 해석합니다.

## Sidecar와 loader

`model/v6_2/runtime/`에 다음 네 파일을 저장합니다.

- `categorical_vocabs.json`: 실제 token → ID.
- `feature_stats.json`: feature 순서, mean/std, dtype, 계산 규칙.
- `preprocessing_contract.json`: 역사적 text/byte/semantic/identity 처리 계약과 미확정 정책.
- `runtime_manifest.json`: source 경로·SHA-256, 생성 UTC 시각, 복구 방식·환경·검증 결과,
  sidecar hash, unresolved 항목.

`load_runtime()`은 파일 존재, source/sidecar hash, 실제 bundle version/shape,
필수 metadata, feature 순서와 수치 유효성을 검사합니다. 실패 시
`RuntimeMetadataError`를 발생시키며 fallback 값을 만들지 않습니다.
성공은 `metadata_verified`이고 `inference_ready`는 여전히 false입니다.
현재 loader는 provenance 확인을 위해 historical CSV도 필요합니다.
향후 배포 환경에서 reference 데이터를 분리하는 정책은 별도 설계 대상입니다.
manifest 자체는 서명되지 않았으므로 hash 검증은 승인자의 전자서명을 대체하지 않습니다.

```python
from model.v6_2.inference.loader import load_runtime
from model.v6_2.inference.schema import validate_csvs

runtime = load_runtime()
report = validate_csvs(
    "data/training/raw/example/events.csv",
    "data/training/raw/example/sessions.csv",
    runtime["vocabularies"],
)
```

위 예시는 schema 검사만 수행합니다. 모델 inference는 구현하지 않았습니다.
validator는 필수 열, ID null/중복, timestamp, session 참조 및 user mapping 충돌,
numeric parse/음수, OOV를 보고합니다. OOV는 실패 조건이 아니며 vocabulary를
확장하지 않습니다. OOV rate 분모는 해당 feature의 non-null 값 수이고,
null count는 별도로 기록합니다. tasks.csv는 선택 입력이며 모델에 전달하지 않습니다.
ID와 timestamp 검사는 원본 notebook보다 엄격한 새 입력 계약입니다.
schema 통과가 모델 inference 준비 완료를 뜻하지 않습니다.

## Historical 데이터 위치

현재 `data/training/v6_2_source/`의 세 CSV를 유지했습니다.
AGENTS.md는 `data/reference/v6_2_source/`를 정책 경로로 설명합니다.
작업 전 코드/문서 검색에서는 현재 historical 경로를 사용하는 기존 실행 코드는
없었고, notebook은 원래 Colab 데이터 경로를 자동 탐색했습니다.

향후 이동 계획은 다음과 같습니다.

1. 세 CSV의 hash를 기록하고 `data/reference/v6_2_source/`로 이동합니다.
2. 복구 도구의 명시적 reference 경로와 runtime provenance 경로를 갱신합니다.
3. source hash가 이동 전후 동일한지 검증하고 loader/provenance 테스트를 수행합니다.
4. frozen/reference 디렉터리는 변경하지 않습니다.

이번에는 이동하지 않았으며, manifest는 실제 현재 경로를 기록합니다.

## user_id 확인 사항

원본 `derive_worker_id()`는 다음 우선순위에서 첫 nonempty 값을 선택합니다.

`actor_key → login_id → user_id → worker_id → employee_id → workflow_key의 #W 앞부분 → session_id → worker_0`

따라서 events.user_id가 존재하고 actor_key/login_id가 비어 있으면 user_id가
low-level stream identity가 됩니다. 정책상 앞으로는 상위 trajectory에만 사용해야 합니다.
현재 historical events.csv에는 user_id 열이 없어 이 fallback을 제거해도 해당
데이터의 선택 경로는 바뀌지 않습니다. 다만 새 데이터에서는 stream, delta_sec,
window, split 등이 달라질 수 있으므로 원본 함수를 이번 단계에서 수정하지 않았습니다.
sessions.user_id는 기존처럼 trajectory 연결용이며 feature 복구에는 사용하지 않습니다.

## 미확정 항목

- E5 정확한 model/tokenizer revision과 당시 local weights.
- 원본 학습 환경 버전 및 삭제된 stats/vocab과의 독립 대조.
- 새 CSV의 low-level stream identity와 timezone 처리 정책.
- 새 stream boundary calibration 정책.
- 새로운 workflow의 고정 consensus cluster assignment 정책.

notebook에는 revision/commit/snapshot 지정이 없습니다. 기본 Hugging Face cache와
sentence-transformers cache에서 해당 E5 모델 자료를 찾지 못했고, 이 실행 환경에
별도 cache 경로 환경변수도 설정되어 있지 않았습니다. 확인하지 않은 다른 장치나
원래 Colab cache의 부재까지 의미하지 않습니다. 최신 revision을 다운로드하거나
임의로 고정하지 않았으며 `semantic_revision_status: unresolved`로 기록합니다.

## 허용된 테스트

```sh
python3 -B -m unittest discover -s tests -p 'test_v62_runtime.py' -v
```

schema, vocabulary recovery, checkpoint shape, numeric 결정성, manifest hash,
loader fail-fast만 검사합니다. 기존 평가/클러스터링/모델 inference 테스트는
이번 작업 범위에서 실행하지 않습니다. 복구 CLI는 이미 runtime이 있으면 덮어쓰지 않습니다.
