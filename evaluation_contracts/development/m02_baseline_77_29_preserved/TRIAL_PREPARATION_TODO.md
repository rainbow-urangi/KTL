# M02 시험 준비 TODO

DEVELOPMENT baseline 77.28981596002805% (Accuracy 64.51612903225806%, Completeness 92.5925925925926%). 31 generated, 20 direct matched, 25/27 satisfied. 정확히 5종×1회. OFFICIAL 판정 아님. 추가 tuning 중단.

- [ ] Collector 수정본 extension build/reload와 실행 중 버전/hash 확인. 소스 hash만으로 현재 탭 적용을 주장하지 않음.
- [ ] 실제 업무 웹에서 popup/button/calendar target capture 검증: event.target, composedPath, foreground modal/actionable target 보존, background calendar 오인식 없음. 기존 raw는 수정하지 않음.
- [ ] 성능측정 웹 실제 브라우저에서 DEVELOPMENT 평가 세트 선택 및 측정 버튼 클릭.
- [ ] BU별 결과/전체 77.29% 및 목표 75% 표시, OFFICIAL 아님 표시 확인.
- [ ] evidence CSV 실제 다운로드 및 baseline SHA-256 105f5ab3fff0f21013d9923828df4d4e2f18919ff593659a8800a2313361240d 대조.
- [ ] 다운로드 evidence와 생성 31/직접 20/충족 25/필수 27, 산식 sqrt(Accuracy*Completeness) 재계산 일치 확인.
- [ ] 시험 실행 직전 preserved manifest 전체 hash 재확인 및 환경/version 기록.

기존 web_ready는 독립 로컬 adapter이며 frozen 주 웹 서버를 변경한 것이 아님. 저장된 process maps를 unchanged evaluator로 재평가하며 모델 inference를 새로 실행하는 버튼으로 오해하지 않음. 기존 HTTP/단위 검증과 실제 브라우저 검증을 구분함.

현재 명시적 runtime/browser 증빙이 없으므로 위 항목은 완료 처리하지 않음. 이 보존 작업은 기존 모델·규칙·evaluator·raw·결과를 수정하거나 재측정하지 않았음. snapshot은 hash 기반 불변 보존 규약이며 OS write-lock/WORM은 아님.
