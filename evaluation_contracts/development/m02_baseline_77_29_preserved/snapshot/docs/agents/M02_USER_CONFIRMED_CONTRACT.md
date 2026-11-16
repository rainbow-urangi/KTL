# M02 user-confirmed contract — 2026-11-08

Source: user message Sentinel_e373f8d92bf08191ba5045efd67aef84. DEVELOPMENT only.

- 업무는 메뉴 클릭부터. 기존 PAGE_ENTER나 이미 열린 화면은 메뉴 클릭의 대체 증거가 아니다.
- 일일업무=일일보고, 주간업무=주간보고. 명시적 raw popup title에서 승인된 일일/주간 화면 alias가 확인되면 넓은 메뉴 context를 구체화한다. 그 외 객체명 popup은 기존 유효 메뉴 context를 덮어쓰지 않으며, 승인 alias는 메뉴 target과 context에 대칭 적용한다. URL 또는 BU ID로 화면을 추정하지 않는다.
- 일정/보고서는 날짜·제목·내용 필수. 거래처/자산은 기타·파일 제외 모두 필수. 테스트 데이터 입력 필드는 필수이고 등록 성공은 필수 입력 조건 충족 근거이다.
- 기존 직접 INPUT이 명시적 동일 form_identity/session/page/popup, 동일 execution/process의 후속 COMMIT과 연결되고 기존 causal SUCCESS_POPUP/UI_OUTCOME이 있을 때만 입력 완료 의미를 인정한다. 등록 클릭/HTTP 200만으로 성공을 만들지 않는다. 중간 취소·미해결 동작·다른 등록 시작은 연결을 차단한다.
- 테스트는 가상 데이터 의미이며 특정 입력값/객체 일치를 요구하지 않는다. INPUT_INFORMATION은 위의 완료된 직접 입력+동일 논리 context로 판단한다. 전체 필드를 새로 생성하거나 누락 날짜 선택 action을 만들어내지 않는다.

## Preservation and limitations

기존 source scope, raw events, field values, source IDs, baseline snapshots는 수정하지 않는다. 비교 때 deepcopy에 required_input_proof 해석 속성만 추가한다. source_event_ids/evidence에 성공 evidence를 복사·삽입하지 않고 별도의 proof 참조로 남긴다. Generated count와 분모는 기존 scope 계약을 그대로 유지한다. BU별 조건, 점수 최적화, threshold/model 조정 없음.

명시적 form evidence가 없는 시작 등록 동작은 alias를 알더라도 자동으로 화면을 붙이지 않는다. 성공 근거 없는 일정 등록, 관찰되지 않은 메뉴 클릭/날짜·주차 선택 등은 여전히 unresolved일 수 있다. 사용자 의미 확인은 실제 raw event 생성 근거가 아니다.

기존 18.49%/22.33% 및 M06/M03 산출물은 보존한다. 새 module 추가는 legacy runtime_inventory guard를 바꾸므로 기존 snapshot의 재측정 게이트를 갱신하지 않는다. 새 manifest와 별도 독립 PASS를 사용하는 CLI만 추가했으며 기존 웹 경로는 변경하지 않았다. 공식 성적서 판정과 KTL 계약 승인 아님.

## Verification gate

독립 verifier가 evaluation_contracts/development/m02_user_confirmed_v1/independent_verification.json에 verdict=PASS, snapshot_manifest_sha256, gt_leakage_check=PASS, provenance_check=PASS, generic_contract_check=PASS를 기록해야만 실제 DEVELOPMENT 측정이 가능하다. 개발자가 gate를 쓰지 않는다. 검증 전 실제 GT 대조/점수 계산 금지.

검증 PASS 이후: PYTHONDONTWRITEBYTECODE=1 python3 scripts/measure_m02_user_confirmed.py

산출물은 기존 run_storage DEVELOPMENT 경로에 저장된다. 결과 확인 후 추가 tuning 없이 사용자에게 보고한다.
