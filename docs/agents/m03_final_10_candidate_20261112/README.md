# M03_FINAL_10_CANDIDATE

동결 시각(UTC): 2026-11-12T07:58:23.502479+00:00

후보 10종 동결입니다. baseline/공식 측정 또는 생성 성공 판정이 아닙니다.

선정: BU01, BU03, BU05, BU07, BU09, BU12, BU13, BU14, BU17, BU20

| BU | 업무 | source workflow / process | 입력 상태 | 선정 이유 |
|---|---|---|---|---|
| BU01 | 개인정보 조회 | WF-0002 / PM-015 | BLOCKED_SOURCE_SCOPE_OR_ACTION | 개인정보 단순 조회 대표; 작성 중심 편향 방지 |
| BU03 | 일정 등록 | WF-0003 / PM-020 | BLOCKED_SOURCE_SCOPE_OR_ACTION | 사용자 우선 포함; 일정 등록/날짜 상호작용 |
| BU05 | 전체업무 상세조회 | WF-0005 / PM-021 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 전체업무 상세조회; 목록과 상세 동작 구분 |
| BU07 | 일일보고 작성 | WF-0007 / PM-010 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 사용자 우선 포함; 일일보고 작성 |
| BU09 | 주간보고 작성 | WF-0009 / PM-019 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 사용자 우선 포함; 주간보고 작성 |
| BU12 | 명함 목록 조회 | WF-0012 / PM-017 | BLOCKED_SOURCE_SCOPE_OR_ACTION | 명함 목록 조회; 상세/등록과 구분 |
| BU13 | 명함 상세조회 | WF-0013 / PM-012 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 명함 상세조회; 동일 도메인 목록→상세→등록 coverage |
| BU14 | 명함 등록 | WF-0014 / PM-013 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 명함 등록; 보고서 외 객체 등록 |
| BU17 | 거래처 정보 등록 | WF-0018 / PM-007 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 사용자 우선 포함; 거래처 정보 등록 |
| BU20 | 자산 등록 | WF-0022 / PM-002 | IDENTIFIED_UNIQUE_WORKFLOW_NOT_EXECUTED | 사용자 우선 포함; 자산 등록 |

## 중요 제한
- BU01/BU12 종료 경계는 AMBIGUOUS. 다음 실행 시작 전까지를 검사 창으로만 사용했으며 완료로 추정하지 않았습니다. MENU_ENTER는 현재 REAL action 허용 목록 밖입니다.
- BU03의 WF-0003에는 BU03 14개 source event와 밖의 4개가 함께 있습니다. BU02/03 혼합 흐름을 잘라내거나 GT로 보정하지 않았습니다.
- 3건은 source/input blocker로 남깁니다. 나머지 7건은 고유 workflow와 raw event 경계가 일치한다는 뜻일 뿐 생성 성공을 보장하지 않습니다.
- 기존 6/10의 개별 결과, score, prediction 파일을 열람하지 않았습니다. 단, REAL에 결합된 엔진 산출 source process map을 매핑 검증 목적으로 열람했습니다. 완전한 engine-output-blind 선정이라고 주장하지 않습니다.
- 부모에게서 기존 6/10 진단이 있다는 사실은 전달받았습니다. 다른 과거 스레드/사람의 열람 이력은 이 기록으로 증명하지 않습니다.
- 구 TD-05 draft는 현재 20 BU와 ID/명칭이 달라 제외. 현재 실행 manifest의 사용자 확인/PDF 참조를 사용했습니다.
- 10개는 교체 금지. blocker 때문에 쉬운 BU로 바꾸지 않습니다. generator/GT/model/API/score 변경 또는 baseline 실행은 하지 않았습니다.

## 검증
실제 snapshot hash와 현재 REAL config의 binding 일치 확인. execution manifest의 event ID를 raw event 순서에 대조하여 source step event와 교차 확인. 전체 event ID 근거/파일 hash는 JSON에 보관.

JSON SHA-256: `c3351712b13e482389b5b3c55238a107f48ced502fd1d6f7053c3f3753c5545a`

문서만 작성하여 backend/evaluation 변경 후 회귀 테스트 조건은 해당하지 않습니다. 생성/evaluation 테스트는 실행하지 않았습니다.
