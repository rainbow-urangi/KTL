# 별도 root에서 표준 서버로 시험하기

`backend.server`는 `--root`로 시험용 프로젝트 root를 선택할 수 있다. 포트만 바꾸는 것과 달리 설정·입력·결과 저장 범위를 함께 분리한다. 옵션을 생략하면 기존 설치 프로젝트 root와 포트 8000을 사용한다. 실행 중인 기존 서버의 설정이나 프로세스는 바꾸지 않는다.

## 실행

제품 코드가 있는 `KTL/KTL` 폴더에서 실행한다. 아래 `<isolated_project_root>`는 사전에 준비한 별도 시험 폴더의 절대 경로로 바꾼다.

```powershell
..\.venv-m04\Scripts\python.exe -B -m backend.server --root "<isolated_project_root>" --port 0
```

`--port 0`은 사용 가능한 로컬 포트를 할당하고 실제 주소를 즉시 stdout에 출력한다.

```text
Rainbow KTL: http://127.0.0.1:<actual_port>
```

이 주소를 시험 요청에 사용한다. 고정 포트가 필요하면 `--port`에 별도 포트를 지정한다. 바인딩은 계속 `127.0.0.1`로 제한된다. 잘못된 root 또는 읽을 수 없는 `backend/config.json`은 바인딩 전에 오류로 종료하며 설치 프로젝트의 설정으로 돌아가지 않는다. 종료할 때는 이 시험 프로세스에 Ctrl+C를 보내거나 자신이 띄운 프로세스만 종료한다.

## 폴더와 설정 계약

```text
<isolated_project_root>/
  backend/config.json
  data/evaluation/<dataset>/... 입력과 SHA manifest
  data/development/...         시험 연결 설정 등
  results/...                 시험 결과 전용
  frontend/...                웹 UI도 사용할 경우 명시적으로 준비
```

`Service(root=...)`의 기존 상대 경로 의미를 그대로 사용한다. runtime root에 제품 Python 소스를 복사할 필요는 없다. API 시험만 한다면 frontend는 필요하지 않다. UI까지 쓰면 현재 제품의 정적 파일을 그 root에 준비해야 하며 설치 프로젝트의 화면 파일로 자동 fallback하지 않는다.

설치 프로젝트의 `backend/config.json`을 직접 수정하지 말고 별도 root의 설정을 준비한다. `m03.input_manifest`, integration dataset manifest, canonical/model CSV 등은 해당 root를 기준으로 등록하고 실제 바이트 SHA를 고정한다. 기존 경로 검증과 GT 누출 금지는 동일하게 적용된다. generation 입력 경로의 symlink 금지 등 기존 제한을 우회하지 않는다.

SUBPROCESS adapter 설정 예시는 다음과 같다. `scripts/start_local.py`는 현재 Python 환경을 PATH 앞에 넣어 같은 환경의 `python`을 사용한다. 별도 실행 환경이 필요하면 해당 환경의 경로를 로컬에서 지정한다.

```json
{
  "adapters": {
    "scenario_generation": [
      "python",
      "-B", "-m", "backend.m03_canonical_adapter"
    ]
  }
}
```

이 예시는 adapter 항목만 보여 준다. 정상 config에는 targets, official_manifests, m03 업무 정의/분석 manifest 및 시험할 integration dataset 등록도 필요하다. 입력 자료·모델·artifact를 staging할 때 원본을 수정하지 않고 고정된 바이트와 SHA를 보존한다. 새 시험 설정을 기존 승인 설정으로 자동 승격하지 않는다.

## subprocess의 코드와 데이터 경계

`call_adapter`는 기존과 같이 subprocess cwd를 `Service.root`로 둔다. 제품 checkout의 위치를 subprocess `PYTHONPATH` 앞에 추가하여 `python -m backend.m03_canonical_adapter`가 별도 root에서도 실제 제품 모듈을 찾게 한다. `KTL_RUNTIME_ROOT`에는 이 Service의 절대 root를 전달하고 Python bytecode 쓰기는 비활성화한다. 기존 부모 환경의 다른 KTL_RUNTIME_ROOT 값은 해당 호출의 Service root로 대체한다.

canonical adapter의 root 선택 순서는 직접 Python 호출의 명시 root 인자, `KTL_RUNTIME_ROOT` 환경, 환경 변수가 없는 경우 기존 설치 ROOT다. 환경 변수가 정의됐지만 공백이거나 없는 디렉터리이면 오류로 종료한다. 잘못된 명시값 때문에 설치 프로젝트로 fallback하지 않는다. CLI 서버가 adapter를 실행할 때는 항상 Service root를 전달한다.

root는 subprocess 실행 환경으로만 전달하며 생성 요청 JSON에 root/config/reference 필드를 추가하지 않는다. adapter stdin의 기존 업무 정의와 분석 입력 계약, GT whitelist 및 평가 계약은 그대로 유지한다. 실행 코드 fingerprint는 실제 설치 제품 코드에서 계산한다.

## 격리되는 저장 범위

다음은 모두 선택한 root 아래에 저장된다.

- 결과 실행 폴더와 `results/development/latest-M03.json` 등 지표별 포인터.
- `results/m03_generations/`의 원생성 started/response/receipt 및 사후 평가 연결.
- `results/integrations/`의 중복 예약과 접수 인덱스.
- `results/model-runs/` 등 공통 분석 결과와 전역 포인터.
- `data/development/`의 연결 설정, CSV·비교·실행 관련 자료.

서버 세션 소유권은 프로세스별 `RuntimeSession`으로 분리된다. 같은 root를 재시작하면 새 세션 화면의 이전 이력은 보이지 않지만 파일과 중복 예약은 남는다. 서로 다른 root는 같은 external_run_id를 각각 사용할 수 있고, 같은 root의 중복 예약은 서버 재시작 후에도 유지된다.

`--root`는 저장 경로 선택 기능이며 신뢰하지 않는 임의 adapter 실행을 OS 수준에서 sandbox하는 기능은 아니다. 등록된 제품 adapter는 root 경계를 지키며, 별도 사용자 명령의 외부 파일 쓰기까지 막는 권한 격리를 제공하지 않는다.

## 확인한 시험

```powershell
..\.venv-m04\Scripts\python.exe -B -m unittest discover -s tests -p test_runtime_isolation.py -v
```

신규 6개 합성 회귀는 실제 표준 CLI, 실제 loopback HTTP handler, 실제 canonical subprocess를 사용한다. 생성→접수→receipt/latest/reservation, 두 root의 격리, 새 서버 세션, 중복 예약 유지, 잘못된 root의 거부를 확인한다. 설치 프로젝트의 config/data/results는 실행 전후 파일 목록과 raw SHA가 같아야 한다.

정답이 없는 합성 시험에서는 결과 archive가 COMPLETED여도 `evaluation_status=NOT_READY`, `score=null`, `official_pass=null`을 확인한다. 이 검증은 실제 모델 forward, CU01~CU10 실제 생성 시험, 공식 업무 순서 평가의 증명이 아니다. 해당 실행 근거는 별도로 보관한다.
