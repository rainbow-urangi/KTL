# 2026-10-26 연동 기준 변경 및 회귀 검사

근거: 사용자 첨부 최신 KTL 협의 지시. 보관 PDF는 2026-09-18 판이며 원본은 수정하지 않았습니다. 최신 서명본 반입·대조는 남은 작업입니다.

## 오래된 상수·설명 검색 결과

| 위치 | 발견 내용 / 조치 |
|---|---|
| backend/official_contracts.py | M03 업무20, M04 스크립트20 → 각각10. M07 공식 요청/생성20 및 고정분모 계약 추가 |
| backend/evaluators.py METRICS | 표시 수량 M03/M04를10, M07을20으로 변경. 평가 클래스는 그대로 유지 |
| backend/data_sources.py | M03 구판 업무20 안내를10으로 변경, 공식 M03 외부 결과 접수 경로 사용 |
| backend/external_results.py | M07 동적 분모를 OFFICIAL_FIXED_20과 기존 비공식 정책으로 분리. 공식 개별 결과로 교집합 산출 |
| frontend/integration-samples.json | M01 주 카드, M07 generated18/both15 예시를 교체. M03 8/10, M04 9/10, M07 16/20 |
| frontend/integration-sandbox.html/js | M01 중심 안내 제거, M03/M04/M07 순서 및 생성/평가 버튼·실제 서버 응답 표시 |
| backend/registry.py | M01 소유 표기를 legacy로 변경; 기존 endpoint 유지 |
| docs/external-integration-api.md | M01 주 연동 안내, M04 공식20, M07 공식 동적 C2 설명 교체 |
| R&D_COMPLIANCE.md | 최신 협의 부록 및 M03/M04/M07 수량·분모 반영; 구판 PDF의 출처와 날짜 보존 |
| backend/official_contracts.py / data_sources.py의 M06 | 구판 모델 수량/차원 계약은 이번 구현 변경 금지 범위라 유지. 연동 문서에는 최종 엔진 embedding+label 설명만 사용 |
| test-data, data, model, 과거 results | 역사적 수량·산출물은 변경하지 않음 |

Sandbox와 연동 API 문서에는 M06의 V6.2 고정/563 workflows/128 dimensions/12 clusters 문구가 없습니다. 남은 M07 generated_code_count 분모는 비공식 호환 정책으로 명시했고 공식 계산에는 사용하지 않습니다. M02의 업무20 계약은 변경 대상이 아닙니다.

## 검증 범위

Python 테스트 10개 추가(신규 계약9, 생성 HTTP1), 기존 Python 테스트3개 수정, Sandbox JavaScript 검사1개 갱신. M03 필수항목·순서·중복·고정 업무목록·Mock 공식 거부, M04 9/10 및8/10, M07 16/20 및15/20·고정 C2·개별 결과 대조를 검사합니다. 모든 공식 계약 fixture는 임시 디렉터리 안에서만 생성·삭제합니다.

전체 `python3 -m unittest discover -s tests -v`, `node tests/test_frontend.cjs`, `node tests/test_integration_sandbox.cjs`로 검증합니다. HTTP 테스트는 localhost 바인딩 허용 환경에서 실행합니다. 기본 샌드박스에서는 바인딩이 거부되므로 해당 오류와 코드 실패를 구분합니다.

보호 대상 model/data/test-data/backend/model_runner의 기존 파일315개 SHA-256과 M02/M05/M06 evaluator 본문을 작업 전과 대조했으며 변경이 없습니다. 실제 모델 실행·학습, 실제 Selenium/LLM 실행, 공식 데이터 생성은 수행하지 않았습니다.

## 호환성과 남은 작업

M01 endpoint와 회귀 검사는 유지됩니다. 기존 M04 successful_execution_count를 유지하고 passed_execution_count 별칭을 지원합니다. 기존 비공식 M07 counts 입력은 유지합니다. OFFICIAL은 의도적으로 새 계약을 적용하므로 구판 M04 20건과 M07 미완성/개별 근거 없는 요청은 422입니다. 저장된 과거 결과는 재작성하지 않습니다.

REAL M03 adapter 연결, 최신 서명 KTL 문서 확보, M05 수량 상충 확인, 별도 승인하의 M06 구현 계약 검토가 필요합니다. M03 공식10종과 M07 공식20개 입력 시나리오의 실제 확보·연결 근거도 시험 전에 준비해야 하며 Mock을 증거로 대체하지 않습니다.

최종 결과: Python 전체108개 PASS, 일반 화면 DOM24개 PASS, Sandbox JavaScript 검사 PASS, `git diff --check` PASS. 공식 M03 fixture의 macOS 임시 경로를 resolve하여 경로 검증과 일치시켰습니다.
