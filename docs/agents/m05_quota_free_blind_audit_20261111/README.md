# M05 quota-free prediction-blind 재검토

## 결론

**ADDITIONAL_REMOVE_RAW_REQUIRED. KEEP 10 / REMOVE 8, 총18개 부분후보. 최소 REMOVE 2건이 더 필요하다.**

raw_01 전체203개와 raw_02 전체147개 source sequence를 검토했다. 기존 prediction 전 후보14건은 모든 CSV 필드 그대로 보존했다. category별 고정 quota 없이 추가4건만 repeated_action으로 채택했고, 최종20 target lock과 prediction은 생성·실행하지 않았다.

## 추가 채택

- raw_01 #72: 빈 주간보고 제목 필드의 연속 추가 클릭. 최초71과 paste73/change74를 보존한다. paste73에서 이전 값이 빈 문자열, selection 0..0임을 확인했다.
- raw_02 #42, #52: 이미 열린 일정 관리 화면의 active 메뉴 재선택. 최초13/route14는 보존한다. 각 클릭 뒤 다음 실제 행동까지 새 route/API/UI 변화가 기록되지 않는다.
- raw_02 #71: 이미 열린 명함 관리 화면의 같은 메뉴 재선택. 최초59/route60 및 상세조회·닫힘65~70을 보존한다.

분포는 noise2 / repeated_action6이다. duplicate나 irrelevant_action을 억지로 넣지 않았다. 현재18개는 최종 GT 또는 평가 입력 manifest가 아니다.

## 제외한 핵심 후보

raw_02 #107/#108은 이미 입력된 제목을 149/151ms 간격으로 다중 클릭한 뒤 내용에 같은 제목 문자열을 paste한다. 텍스트 선택·복사 준비일 가능성을 배제할 수 없어 제외했다. click value=null은 값이나 selection 불변의 증거가 아니다.

raw_01 #21은 긴 간격 뒤 작업을 재개하는 focus일 수 있다. 배경 클릭·table cell·선택 완료 클릭·동일 날짜 확인도 업무 의미가 모호하므로 제외했다. 서로 다른 인증 request, 다른 업무 객체, popup lifecycle/outcome/structure, 세션 경계는 단순 반복으로 제거하지 않는다.

## held-out 및 원본 무변경

기존 이력15개 파일의 SHA가 모두 동일하고, 이전 raw ID/session/row/raw-content 비교의 중복0 근거를 재확인했다. raw01/02 6개 원본과 이전 감사 파일의 SHA도 동일하다. 이것은 전체 과거 학습·개발 미사용 또는 실제 engine feature-content 비중복 인증이 아니다. held_out는 비워 두었다.

엔진/adapter 코드와 prediction 결과는 읽거나 실행하지 않았다. raw 구조·세션 문맥과 별도 raw 검토 결과만 사용했다. 입력 source 순서를 바꾸거나 raw 내용을 가공하지 않았다. backend/모델/계약/기존 감사 문서는 수정하지 않았다.

## 최소 추가 수집

수학적 부족분은 **REMOVE 2건**, 실제 업무 전체 흐름을 담은 새 수집1회 이상이다. 필요한 보고서를 작성할 때 비어 있는 제목과 내용 필드 각각에서 최초 focus 뒤 추가 클릭1회를 하고 실제 내용을 입력하는 반복행위가 가장 구분하기 쉽다. 최초 focus는 보존한다. 대안은 빈 필드에서 최초 클릭+추가2클릭이다.

이미 채운 텍스트를 다중 클릭해 선택·복사하는 행위는 피한다. 수집 전 의도·canonical 보존 원칙·시각을 기록하고 events/tasks/sessions를 실제 시작부터 종료까지 보존한다. 새 raw는 다시 독립 검토하며 후보 수를 미리 보장하지 않는다. 새로운 기술 이벤트나 무관행위를 category 수량에 맞춰 만들 필요는 없다.

## 파일

- partial_label_candidates_NOT_FOR_EVALUATION.csv: 기존14+추가4, 평가 실행 금지.
- additional_label_evidence.json: 추가4의 source/session/position/row SHA, 세부 문맥, 보존할 최초 행동.
- ambiguous_candidates_NOT_GT.json: 제외 사유와 원본 위치. KEEP 판정으로 대체한 파일이 아니다.
- review_report.json: 계약 범위, 부족2건, held-out 한계, 수집 지침.
- audit_snapshot_pre_prediction.json: 원본/기존 감사/새 산출물 hash snapshot. 최종 target lock이 아니다.
- verify_audit.py: 원본/과거자료/부분후보/hash와 카운트만 검증. 모델이나 evaluator를 import/실행하지 않는다.
