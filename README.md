# Rainbow KTL 성능평가

Python 3.10 이상의 로컬 평가 API와 웹 UI입니다. 기본 서버는 표준 라이브러리를 사용하며 OFFICIAL M06 교차 검증에는 scikit-learn이 필요합니다.

Windows/Python 3.12 새 환경의 현재 실행 절차는 [집 PC 실행 안내](docs/HOME_SETUP.txt)를 확인하세요. 저장소의 `scripts/start_local.ps1` 또는 `scripts/start_local.py`로 시작합니다. 기본 개발 canonical 입력을 포함하며, 개인 인증정보·이전 실행 결과·외부 실제 생성기 연결은 별도로 준비합니다.

평가 변경 전 [R&D_COMPLIANCE.md](R&D_COMPLIANCE.md)와 [공식 데이터 매트릭스](docs/compliance/OFFICIAL_EVALUATION_DATA_MATRIX.md)를 확인하세요.

```sh
python3 -m backend.server
```

<http://127.0.0.1:8000>에서 REFERENCE/OFFICIAL 모드를 선택합니다.
M01~M07 각각 `/metrics/m01` ~ `/metrics/m07` 페이지가 있습니다.

- **REFERENCE**: 실제 보관된 V6.2 산출물을 읽어 평가 프로그램을 검증합니다. 공식 시험성적이 아닙니다.
- **OFFICIAL**: 공식 manifest와 입력 SHA-256, 필요한 모델/adapter 연결을 요구합니다. 현재 공식 데이터는 없습니다.
- **DEVELOPMENT**: 수집 CSV 비교, 시나리오 생성·보관, 고정 스크립트와 GPT 코드의 개발 시험 모드입니다. 공식 시험성적이 아닙니다.

현재 M02는 legacy GT 7종과 저장된 단일 실행의 직접 절차를 실제 비교합니다.
M06은 feature matrix가 없어 DBI 없이 군집 요약을 제공합니다.
M03은 입력 context 조회, 생성 API 호출, 외부 결과 접수 및 저장한 시나리오 조회를 제공합니다. 기본 canonical 변환은 새 AI 추론이 아니며 정답 업무 순서가 없으면 평가를 대기합니다.
M05 계산기는 완성되어 있지만 실제 정제 모델과 200개 시험 이벤트가 필요합니다.
M01은 실제 CSV 진단·고정 기준 비교, M04는 M01 동작 가져오기·고정 Python 실행·외부 결과 조회, M07은 명시적 GPT 코드 생성과 문법·실행 상태 표시를 제공합니다. 가져오기·생성·실제 실행은 별도 동작입니다.
M04 DEVELOPMENT 화면의 **CU02 일정 등록**에서는 날짜·제목·내용을 입력하며 기본 브라우저는 Chrome입니다. **CU02 10건 평가 실행**을 누르면 서로 다른 제목의 일정 10건을 각각 신규 등록하고, 새로고침·상세 조회로 저장값을 확인합니다. 일정 1건의 등록부터 재조회까지 전체 성공을 평가 1건으로 세며, 성공·실패·진행·대기 건수와 완료 후 성공률을 표시합니다. 9/10건 이상이면 개발 목표 90% 달성입니다. 한 번 누르면 실제 일정 10건이 저장되며 자동 재시도하지 않습니다. 단건 확인은 기존 **CU02 실행 준비 → 선택 스크립트 실행**을 사용합니다.

CU02는 창을 열기 전에 시험 계정으로 인증하고, 로그인된 일정관리 화면부터 표시합니다. 실행 전에는 신규등록 창의 제목·내용이 빈 상태인지 검사하고 캡처합니다. 실행 후에는 재조회한 상세창의 제목·내용이 기대값과 일치하는지 확인하고 같은 폼에서 캡처합니다. 화면의 문자·이미지는 마스킹하며, 값의 일치는 실행 조건과 독립 DOM 검사 기록으로 확인합니다. 10건의 입력·스크립트·집계 기준은 실행 전에 SHA와 함께 고정하며 보고서와 원본 archive에 보관합니다. 로그인 설정은 `.env.local`의 `KTL_M04_RBEM_USERNAME`, `KTL_M04_RBEM_PASSWORD`를 사용하며 코드·증빙에는 인증값을 저장하지 않습니다. 이 기능은 CU02를 대상으로 한 DEVELOPMENT 평가이며 공식 시험성적이나 GPT/M03 생성 시험을 뜻하지 않습니다.

M07 DEVELOPMENT의 기본 화면은 회의록(32:39~35:51)에 맞춘 **시험 입력 20건**입니다. 서로 다른 시나리오 20개를 JSON으로 붙여넣거나 파일로 올려 **입력 확인 → LLM 코드 20건 생성 → 원본 확인 → Chrome 문법·실행 검사** 순서로 사용합니다. 코드 생성은 입력별 실제 LLM 요청 1회씩 수행하고, 검사는 별도 버튼으로 고정한 생성 원본을 실행합니다. 20행의 생성·문법·실행 PASS/FAIL을 표시하며 최종 성공률은 `문법·실행 모두 통과 / 20 × 100`입니다. 16/20=80%, 15/20=75%이며 생성 실패도 분모 20에 남습니다. 실제 요청 근거가 없는 미시도 항목은 점수를 만들지 않고 대기합니다.

**입력 초안 불러오기**는 PDF의 10개 업무에서 입력값·조회 대상을 달리한 20건을 검토용으로 제공합니다. 회의에서 확정된 시험 목록이나 실행 결과가 아니며 사용 전에 날짜·기존 자료·선택자·기대값을 확인합니다. LLM에는 업무 정의와 독립 검사 조건을 보내며 준비된 Python 코드로 출력을 대체하지 않습니다. 실제 생성 코드의 화면·검사 원본 SHA를 대조하고 입력·프롬프트·응답·코드·실행 근거를 보관합니다. 로그인은 Chrome 창 생성 전에 인증 도우미로 처리하고, 실제 업무 조작·검사는 LLM이 생성한 코드가 수행합니다.

모델 표시명은 **GPT 루나**입니다. 업무 컴퓨터의 `.env.local`에 `KTL_M07_OPENAI_API_KEY`와 실제 API 모델 식별자 `KTL_M07_MODEL`을 설정하거나 같은 이름의 환경변수를 사용합니다. 표시명을 임의의 API 모델 ID로 변환하지 않습니다. 키·모델 미설정 시 연결 대기를 표시하며 실제 LLM 호출·성공 증빙을 만들지 않습니다. 기존 M03 연결·PREPARED 코드는 접힌 보조 도구에서 사용할 수 있고 별도 개발 기록으로 구분합니다. 새 M04·M07 실행의 기본 브라우저는 Chrome이며 이전 고정 원본과 기록은 보존합니다.
기존 `scripts/selenium_runner.py`는 비활성 legacy 도구이며 현재 API에서 호출하지 않습니다.

결과는 `results/reference/REF-Mxx-.../`와 `results/official/EVAL-Mxx-.../`에 분리됩니다.
각 실행에 `result.json`, `evidence.csv`, `run_manifest.json`을 저장합니다.
REFERENCE의 `official_pass`와 호환용 `pass`는 항상 null입니다.

[평가 명세](docs/evaluation-spec.md), [데이터·adapter 계약](docs/data-contracts.md)을 참고하세요.
목표는 M01 ≥65%, M02 ≥75%, M03 ≥80%, M04 ≥90%, M05 F1 ≥0.79, M06 DBI ≤1.0, M07 ≥80%입니다.
M02 OFFICIAL은 TD-03 업무20종/GT5종이며 V6.2 고정 사용을 강제하지 않습니다. M03은 공식 평가 업무10종에 각각 한 번 생성 요청합니다. M04는 사전 고정 Selenium/Python 스크립트10건을 각1회 실행합니다.
M06 OFFICIAL은 승인 V6.2 563×128 embedding과 final12군집 label만 사용합니다. 현재 bundle은 PARTIAL이며 정확한 matrix가 없어 `OFFICIAL_M06_BUNDLE_MISSING`입니다. 개발용80차원 feature로 대체하지 않습니다.
M07은 등록한 시험 건수를 기준으로 실제 요청·생성·문법 통과·실행 통과·통합 통과를 구분합니다. 공식 설계 수량은20건이며, 미시도·공급자 제한으로 완료되지 않은 측정은 null입니다. 생성 코드 수를 분모로 계산한 과거 부분 결과는 현재 측정과 구분해 표시합니다.

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
