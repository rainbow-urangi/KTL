# M05 사용자 확인 결합 사전 label lock

## 결과

**20건 label lock 완료: KEEP10 / REMOVE10. 평가 실행은 held-out 이력 및 별도 검증 gate 때문에 BLOCKED. prediction과 점수는 생성하지 않았다.**

기존18개 label은 그대로 유지했고, raw03 제목 #26 및 내용 #37을 repeated_action REMOVE로 추가했다. 제목·내용 각1건이라는 요청 범위를 지켰다. 최초 focus22, 제목 재시작 클릭25, 내용 마지막 구간 첫 클릭36, 실제 입력28/38/39와 저장40~44는 원본에서 보존한다. title27은 이번 target에 추가하지 않았으며 KEEP으로 재판정한 것도 아니다.

## raw와 사용자 확인의 구분

raw만 본 앞선 감사의 BLOCKED 판단과 파일을 수정하지 않았다. 새로운 직접 사용자 회고 확인은 user_attestation.json에 질문/답변 원문과 함께 별도 저장했다.

- 제목25→26→27은 같은 session/popup/target의 빠른 클릭이다. 클릭26은 25의166ms 뒤다. 클릭 value=null과 selection 미기록은 그대로다. 사용자가 빈 칸에서 선택·커서 이동 없이 재클릭했음을 확인했으므로 이 확인과 raw 문맥을 결합했다.
- 내용36→37은1068ms 간격이고, 후행 paste38의 직전 value=''와 selection0..0, change39, 저장42=201이 있다. 사용자가 마지막 두 클릭 당시 빈 상태였음을 확인했다.
- 앞선 paste30이 반영되지 않았는지 중간에 삭제했는지와 정확한 시점은 여전히 UNKNOWN이다. 그 불명확성이 마지막 두 클릭 시점의 빈 상태에 관한 직접 확인 자체를 반증하지는 않는다. 이를 raw에 원래 기록된 값처럼 취급하거나 사후 삽입하지 않았다.

두 신규 label의 evidence class는 RAW_CONTEXT_PLUS_DIRECT_USER_RECOLLECTION이다. raw-only 객관 측정이라고 주장하지 않는다.

## freeze와 gate

target_labels20.csv와 그 SHA-256, 원본/이전 감사/사용자 증언 해시는 target_label_lock.json에 사전 고정했다. lock 자체 해시는 target_label_lock.sha256에 있다. 원본9개 raw CSV와 이전 audit hash도 검증한다. prior18_preserved.csv는 기존18행 파일의 byte-identical 복사본이다.

가용17개 이력의 ID/session/raw row/raw content 비중복은 재검증했지만, 완전한 학습·개발 이력과 actual engine feature-content 비중복은 미확정이다. held_out/used_for_training/used_for_development는 비워 두었으며 평가 manifest가 아니다. 현재 engine freeze metadata 및 independent verification도 별도다.

전체 raw context를 삭제·정렬·수정하지 않았고 모델/엔진/adapter/prediction을 읽거나 실행하지 않았다. 평가 성공이나 공식 수용을 선언하지 않는다.

## 재현 검증

python3 docs/agents/m05_raw03_attested_label_lock_20261111/verify_lock.py

lock 생성 스크립트는 기존 lock이 있으면 덮어쓰지 않고 중단한다. backend/평가 구현 변경이 없으므로 전체 backend unit test는 실행하지 않았다.
