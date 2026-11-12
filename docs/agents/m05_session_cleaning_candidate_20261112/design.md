# M05 최소 개선 후보 (측정 전 설계)

기존 RLE는 case_id(task)별 정렬/비교이며 case 경계에서 reset한다. FN 반복 8건은 모두 단일 이벤트 case에 있다. 단순 session 전체 activity RLE는 다른 target, popup, 입력값/커서 변화까지 합칠 위험이 있어 적용하지 않는다.

1. collector_boot + html + API/outcome 없음만 기술 noise로 추가.
2. 같은 session/정확한 page/selector/tag/popup의 연속 input/textarea focus click을 비교. 2초 이내이며 다음 동일 필드 paste의 명시적 이전 값 공백과 selection0..0으로 뒷받침되는 경우에만 첫 클릭을 남긴다. null은 빈 값이 아니며 change/keydown/다른 target 등이 있으면 reset. 사용자 라벨 회상은 엔진 입력으로 쓰지 않는다.
3. 동일 session에서 nav DOM ancestry/label의 클릭 직후 route 변경으로 관찰한 목적지를 기억한다. 같은 목적지에 다시 nav를 누르고 다음 사용자 동작까지 route/API/popup/outcome이 전혀 없는 경우만 반복 메뉴로 제거. 처음 메뉴/route는 보존한다. 이 연결은 temporal observation이지 직접 causal ID로 가장하지 않는다.

기존 baseline/source/GT/raw는 보존하고 별도 후보 모듈/config/결과 경로로 평가한다. full417/target20 구조, 중앙 binary 산식과 CSV 재계산은 기존 것을 사용한다. ID/업무명/GT/category는 규칙 조건에 들어가지 않는다. 모델 학습/architecture/threshold 변경 없음.

한계: 관측되지 않은 UI side effect/이후 지연 응답은 증명할 수 없다. 보수적 입력규칙 때문에 raw value/selection이 없는 정답 REMOVE가 KEEP으로 남을 수 있다. 새로운 UI/수집 누락 데이터의 일반 성능 보장은 아니다. 현재 데이터는 DEVELOPMENT에 사용되었으므로 새 held-out 성능 주장 금지.
