# M05 DEVELOPMENT 측정 결과 (2026-11-12)

최신 사용자 승인으로 과거 strict held-out provenance 부족은 이번 DEVELOPMENT 평가의 blocker가 아니다. 원본 manifest와 label을 수정하지 않고 별도 `m05_development_authorization.json`을 정확한 hash에 결합했다. 과거 held-out 부족 판정은 참고 한계로 보존하며 KTL의 공식 수용 승인이라고 주장하지 않는다.

- full sequence 417, 원래 case 313, target 20 (KEEP10/REMOVE10), context397 제외.
- 기존 frozen engine 단 1회 호출. 전체 prediction KEEP417.
- TP0 / FP0 / FN10 / TN10, Precision0 / Recall0 / F1 0.00. 목표0.79 미충족.
- FN: noise2 collector_boot는 기존 drop rule 대상 아님; repeated_action8은 모두 원래 1-event case로 case-local RLE 적용 범위 밖. 5건은 직전 동일 클릭이 다른 case이며 3건 메뉴 재진입은 다른 UI lifecycle 이벤트가 끼어 단순 연속 RLE만으로 처리할 수 없음.
- 원본 raw/label, frozen engine/config 모두 변경 전후 hash 동일. labels held_out/작성자/작성시각의 미확인값을 true/확정값으로 조작하지 않았다.
- 전체 regression422 PASS, M05 focused79 PASS. 웹 HTTP 측정·저장결과 재조회·CSV 다운로드/재계산 PASS, 반복 측정 차단 PASS. 실제 브라우저 클릭 검증은 별도 Independent Verification 대상.
- 엔진/정제 rule/adapter/입력 case는 변경하지 않았다. 최소 개선은 collector 기술 이벤트 처리 범위와 정제 sequence boundary 계약 검토이며 사용자 승인 전 구현하지 않는다.

## 재현/열람
`python3 -m backend.m05_readiness_web` → http://127.0.0.1:8768 → dataset 선택 → 근거 검증: 이미 완료된 결과만 조회하며 재실행하지 않음. CSV 다운로드 가능.
`python3 scripts/recalculate_m05_full_context_csv.py results/development/m05_full_context/17c2d026e82515776864efab58802ed616364c18ef83686117adedb1b1974274` 는 engine 재실행 없이 CSV 검산.
