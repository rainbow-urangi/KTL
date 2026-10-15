# Rainbow KTL 성능평가

Python 3.10 이상의 로컬 평가 API와 웹 UI입니다. 기본 서버는 표준 라이브러리를 사용하며 OFFICIAL M06 교차 검증에는 scikit-learn이 필요합니다.

평가 변경 전 [R&D_COMPLIANCE.md](R&D_COMPLIANCE.md)와 [공식 데이터 매트릭스](docs/compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md)를 확인하세요.

```sh
python3 -m backend.server
```

<http://127.0.0.1:8000>에서 REFERENCE/OFFICIAL 모드를 선택합니다.
M01~M07 각각 `/metrics/m01` ~ `/metrics/m07` 페이지가 있습니다.

- **REFERENCE**: 실제 보관된 V6.2 산출물을 읽어 평가 프로그램을 검증합니다. 공식 시험성적이 아닙니다.
- **OFFICIAL**: 공식 manifest와 입력 SHA-256, 필요한 모델/adapter 연결을 요구합니다. 현재 공식 데이터는 없습니다.
- **DEV**: 임시 unit test fixture만 허용하며 API 실행 모드가 아닙니다.

현재 M02는 legacy GT 7종과 저장된 단일 실행의 직접 절차를 실제 비교합니다.
M06은 feature matrix가 없어 DBI 없이 군집 요약을 제공합니다.
M03은 12개 프로세스 모델의 시나리오 생성 입력 미리보기와 계약 검증까지 제공합니다.
M05 계산기는 완성되어 있지만 실제 정제 모델과 200개 시험 이벤트가 필요합니다.
M01/M04/M07은 외부 연동 계약과 화면만 제공합니다.
기존 `scripts/selenium_runner.py`는 비활성 legacy 도구이며 현재 API에서 호출하지 않습니다.

결과는 `results/reference/REF-Mxx-.../`와 `results/official/EVAL-Mxx-.../`에 분리됩니다.
각 실행에 `result.json`, `evidence.csv`, `run_manifest.json`을 저장합니다.
REFERENCE의 `official_pass`와 호환용 `pass`는 항상 null입니다.

[평가 명세](docs/evaluation-spec.md), [데이터·adapter 계약](docs/data-contracts.md)을 참고하세요.
목표는 M01 ≥65%, M02 ≥75%, M03 ≥80%, M04 ≥90%, M05 F1 ≥0.79, M06 DBI ≤1.0, M07 ≥80%입니다.
M02 OFFICIAL은 TD-03 업무20종/GT5종이며 V6.2 고정 사용을 강제하지 않습니다. M03은 같은 TD-03의 20업무에 각각 한 번 생성 요청합니다. M04는 사전 고정 Selenium/Python 스크립트20건을 각1회 실행합니다.
M06 OFFICIAL은 승인 V6.2 563×128 embedding과 final12군집 label만 사용합니다. 현재 bundle은 PARTIAL이며 정확한 matrix가 없어 `OFFICIAL_M06_BUNDLE_MISSING`입니다. 개발용80차원 feature로 대체하지 않습니다.
M07 분모는 `generated_code_count`입니다. Sandbox의 요청20/생성18/both PASS15는 83.333…%이며 요청 수는 진단용입니다.

V6.2 승인 기준: 이벤트 32,273, 세그먼트 5,167, 워크플로우 563,
프로세스 인스턴스 1,619, 모델 12개.
`model/v6_2/frozen/`, `reference/`, `runtime/`은 수정하지 않습니다.
재학습, 경계 변경, prototype 최적화, 재클러스터링, 범용 CSV inference는 수행하지 않습니다.
Ground Truth는 평가에만 사용합니다.

```sh
python3 -m unittest discover -s tests -v
node --check frontend/app.js
node tests/test_frontend.cjs
```

서비스는 localhost에만 바인딩되며 브라우저의 동일 출처 요청만 허용합니다.

## DEVELOPMENT 평가 연결

현재 실제 개발 데이터 `current_site_dev_01`은 웹에서 `?mode=DEVELOPMENT`로 구분합니다. M02 또는 M06의 개발 실행 버튼은 raw events 전체에 frozen V6.2 forward를 수행하고 두 evaluator의 결과를 함께 저장합니다. GT와 execution manifest는 모델 처리 후 시간 구간 매핑·평가에만 사용됩니다. `POST /api/evaluations/m02/run?mode=DEVELOPMENT` 또는 `m06`으로도 실행할 수 있습니다.

E5는 `results/model-cache/semantic_source.json`에 고정 revision과 로컬 snapshot 경로가 필요합니다. 실행에 사용한 commit과 파일 해시는 model run manifest에 기록됩니다. historical equivalence는 미검증이며 OFFICIAL runner는 제공하지 않습니다. 기존 frozen/reference/runtime은 변경하지 않습니다.

산출물은 `results/model-runs/dev/<run_id>/`, 평가 결과는 `results/development/<run_id>/`에 저장합니다. workflow 수가 기존 consensus 최소 K를 충족하지 않으면 feature까지만 저장하고 `INSUFFICIENT_DATA_FOR_CONSENSUS`, score=null로 종료합니다. K를 낮추거나 과거 WP에 강제 배정하지 않습니다. 일반 사이트용 inference 서비스는 아닙니다.

외부 M01/M04/M07 엔진은 [외부 결과 API 계약](docs/external-integration-api.md)을 사용합니다. 원시 count를 중앙에서 검증·계산하며 실제 외부 결과가 없으면 `EXTERNAL_MODULE_PENDING`입니다.
