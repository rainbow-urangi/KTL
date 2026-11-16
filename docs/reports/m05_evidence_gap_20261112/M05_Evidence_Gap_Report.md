# M05 Evidence Gap Report
## 기존 417행·고정 target20의 증빙 상태와 재개 조건

작성 기준: 2026-11-11 23:36 UTC 이후 점검 (한국시간 2026-11-12 오전).
대상 저장소: /Users/sooeunkim/workspace/RainbowKTL
대상 bundle: data/held_out/m05/raw01_raw02_raw03_target20_20261111/

**결론: 기존 데이터의 오염을 확인한 것이 아니라, 현 계약의 측정 허용 요건을 아직 증명하지 못한 상태다. 측정 BLOCKED를 유지한다.**

raw01/02/03 총 417행, 고정 target20(KEEP10/REMOVE10), 원본 lock 및 frozen engine은 그대로 보존했다. 이번 작업에서 prediction, score, F1, confusion 계산, 실제 수집, 재라벨링, 계약 변경, 승인 registry 생성은 하지 않았다. 이 문서는 현재 확인한 기록과 한계를 설명하는 감사 보고서이며, 누락된 과거 로그·라벨 생성 기록을 대신하는 사후 증빙이 아니다.

## 1. 핵심 결과

- 읽기 전용 재검증에서 raw 417행, 3개 세션, 313개 task/case 및 417개 timestamp 증빙이 통과했다. 모든 행을 유지한 frozen normalization 결과도 준비된 입력과 정확히 일치한다.
- frozen engine의 immutable artifact 17개와 active config 1개, 합계 18개 hash 검증이 통과했다.
- target20의 ID·순서·binary label·category·rationale·원본 위치가 보존되어 있다. REMOVE category는 noise2/repeated_action8이며 현재 계약에 category별 quota 또는 4종 포함 의무는 없다.
- 역사 CSV 12개, 34,553행을 같은 frozen normalizer로 다시 대조했다. training32,273행과 development2,280행에서 전체417에 대한 event ID 및 정확한 model feature hash 중복은 각각 0이다. 이는 확인한 원천 범위의 결과이며 모든 과거 사용 이력의 완전성 증명은 아니다.
- 실제 validator는 manifest의 used_for_training/used_for_development가 null이어서 PRIOR_USE_DECLARATIONS_REQUIRED에서 차단된다. 이를 false로 임의 변경하지 않았다.
- 추가로 남은 주요 gate는 사용 이력의 완전성·책임자 확인, collection/export 완전성의 독립 검토, labeler/개별 label 시각 및 full-context lock의 귀속, collection 시작부터 lock까지의 실제 prediction 실행·조회 로그, 정확한 binding에 대한 별도 독립 승인이다.
- 원래 attestation에 없던 사용자 질문·답변의 실제 대화 ID와 시각을 복구했다. 기존 파일은 수정하지 않았고, 이 회고가 raw 계측이나 미사용 이력의 증명으로 바뀌지는 않는다.
- 실제 DBeaver CSV 내보내기 로그9건을 새로 찾았다. 그러나 로그가 가리키는 Downloads 원파일은 현재 없고 로그에 session ID·row count·file hash가 없어서 raw01/02/03와의 정확한 연결은 아직 후보 수준이다.

## 2. 적용 계약과 판정 범위

우선 기준은 R&D_COMPLIANCE.md의 최신 M05 운영 기준, evaluation_contracts/m05_user20.json, backend/m05_full_context.py 및 backend/m05_timestamp_evidence.py다. 구현 설명은 docs/agents/m05_full_context_implementation/README.md에 있다.

현재 운영 계약은 DEVELOPMENT, target20, KEEP10/REMOVE10, binary REMOVE/KEEP F1≥0.79, 전체 raw sequence 1회 처리 후 고정20개만 평가다. 기존 문서의 200건·100/100·category25는 이 경로에서 stale 기록이다. 오래된 main web/target-only 경로를 대체 경로로 사용해서는 안 된다. FINAL PDF를 변경하거나 현재20건 계약을 KTL의 공식 수용 승인으로 간주하지 않는다.

다음 상태를 구별한다.
- **확인됨:** 명시한 파일과 범위의 실제 구조·hash·대조 검사에 근거한다.
- **부분 확인:** 기록은 존재하지만 전체 모집단·기간·실행 경로를 덮지 못한다.
- **미확인:** 요구한 사실을 증명하는 원천 또는 귀속이 없다. 오염·실행·조회가 있었다는 판정과 다르다.
- **향후 산출물:** 적법한 실제 측정 뒤에만 생성해야 한다. 지금 없다는 이유로 만들어 채우지 않는다.

## 3. 계약 요구사항별 실제 상태

| 항목 | 계약 요구 | 실제 기록과 확인 범위 | 남은 gap / 상태 |
|---|---|---|---|
| 1. 계약·평가 규모 | schema=m05-full-context-v1, dataset ID=디렉터리명, target20, KEEP10/REMOVE10, category quota 없음 | manifest 및 m05_user20.json이 현재20건 구조와 연결됨. labels counts/unique IDs 재검증 | 구조 확인됨. KTL 공식 수용은 별도 미확인 |
| 2. 파일 격리·hash | repository 내부, bundle 아래 원천·label/evidence, raw CSV 전부 선언, byte SHA-256 | bundle 분리, raw3개 hash·mapping·row_count·선언 목록 및 원본 복사 동일성 확인 | 제공된 파일 범위 확인됨. 별도 미제공 export 존재 여부는 제외 |
| 3. engine freeze | 고정 freeze SHA, FROZEN_AFTER_INDEPENDENT_PASS, 18개 artifact/config, 실행 argv/모델 검증 | 2026-11-09T01:56:51.019524Z freeze 및 현재18개 검사 통과 | 확인됨. 새 실행 또는 engine 변경 없음 |
| 4. prior-use 선언 | used_for_training=false, used_for_development=false | 둘 다 null | 첫 runtime blocker. 근거 없이 false 선언 금지 |
| 5. collection scope·collector | COMPLETE_SESSIONS_AND_TASKS, collector ID/version/timezone/reason, 전체 event_count, 시작/종료 | collection.json에 ID/version/Asia-Seoul/종료 근거, 417행, 3세션. 각 공급 세션의 sequence 연속성·collector boot·page_close 기록 | 제공 export 내부 연속성은 확인. 서버 누락·삭제·export 필터까지 완전성은 미확인 |
| 6. 시각·freeze 이후 수집 | collection 및 모든 event가 freeze 이후, 현재 이전. 명시 offset 또는 hash-bound timestamp policy, event/session identity와 UTC·epoch 일치 | 417개 payload의 event_time/epoch/raw_payload event_time 및 CSV wall-time 일치. raw bytes와 features.ts 불변 | 제공 행에 대해 통과. 파일 mtime이나 호스트 시간 추정은 사용 안 함 |
| 7. 세션·task 완전성 | 정확한 ordered event_ids, source IDs, complete=true, completion_evidence, UTC 경계, 모든 그룹 커버 | sessions.json 3개, tasks.json313개, 모든 event의 정확한 그룹·경계 재검증 | 공급된 행 기준 통과. 원천 DB 전체를 증명하는 것은 아님 |
| 8. frozen normalization | hash-pinned 원본 AST 정의 그대로, 행 손실·중복·cross-session case collision 없음. input은 id/features(case_id,activity,ts)만 | 417개 event/313case, normalization candidate와 완전 일치. 전체 raw digest·normalized digest 재현 | 확인됨. 정제 엔진·model prediction은 실행 안 함 |
| 9. 역사 inventory | training/development 각각 nonempty source CSV·hash, 동일 normalizer로 모든 source row 재현, 전체417 ID+feature hash 중복 없음 | training1개32,273행, development11개2,280행, 모두 원천 hash/내용 재현. ID/feature hash 중복0 | 해당12개에 대해 확인. 다른 기기·서버·삭제파일·미기록 실험의 완전성 제외 |
| 10. history completeness | provenance reviewer·reviewed_at, complete_history_attested=true, audit method SOURCE_HISTORY_RECONCILIATION, raw/inventory digest, coverage_complete=true 및 findings | inventory와 감사 JSON은 존재하나 reviewer/time=null, attested=false, coverage_complete=false | 핵심 미확인. 독립 책임자가 범위·누락·보존기간을 확인할 원천이 필요 |
| 11. target selection | 20 unique IDs가 full input에 join, CSV 순서=selection, raw digest·선정 원칙 | target_selection.json 및 원본 target lock이 정확히20개 순서 고정. 나머지397행 context only | ID·순서·의미 보존 확인. 실제 당시 비노출은 항목16의 별도 요건 |
| 12. label 내용·출처 | 정확한 LABEL_FIELDS, KEEP10/REMOVE10, REMOVE 4종 중 하나, KEEP category 비어 있음, rationale·행별 raw provenance | candidate CSV header, counts, categories, rationale, zero-based index·one-based record·timestamp·source/session/case/hash 모두 확인 | 내용/구조 확인됨. label의 당시 귀속·시간은 아래 gap |
| 13. held_out field | 각 CSV 행의 held_out 정확한 문자열 true | 20행 모두 공란. 원본 source label도 미사용 여부를 비워 둠 | 미확인. manifest false/label true만 채워서 통과시키면 안 됨 |
| 14. labeler·시각 | labeler가 lock과 일치, UTC labeled_at, collection end≤각 label 시각≤lock≤현재 | 20행 모두 labeler/labeled_at 공란. source lock에 batch 생성시각은 있으나 개별 생성시각과 동일하지 않음 | 미확인. prior18은 full collection 종료 전 후보가 이미 존재하므로 특히 단순 소급 시각 부여 금지 |
| 15. full-context lock | target/selection/raw/normalized 4개 digest, locked_at, prediction_blind=true, labeler | label_binding_candidate.json의 4개 digest는 바인딩됨. locked_at/prediction_blind/labeler=null. source lock은 별도 PREDICTION_BLIND_LABEL_LOCK_NOT_EVALUATION_MANIFEST | 내용 lock과 실행용 full-context lock은 다름. 기존 lock 자체를 교체·수정하지 않음 |
| 16. prediction 실행·조회 무노출 | audit의 matching raw/lock digest, complete=true, runs=[], views=[], 독립 reviewer, reviewed_until≥lock. 실제 source_logs nonempty | INCOMPLETE JSON에 runs/views=null, complete=false, reviewer/time=null, source_logs=[]. 기존15개 project record는 자기보고·test/과거 결과일 뿐 exhaustiveness 없음 | 핵심 미확인. 빈 배열을 새로 써서 과거 0건을 증명할 수 없음 |
| 17. 원천 로그 기간 | 각 source log가 raw digest에 연결, entries=[], collection start 이전~lock 이후를 모두 커버 | 필요 기간 2026-11-11T12:09:46.818Z~13:47:09.237438Z. 해당 whole-period prediction/access source가 현재 미확보 | current attempt 없음·shell history 검색0만으로 충족 안 됨. export 로그도 prediction audit를 대신하지 못함 |
| 18. 사용자 회고 traceability | raw와 회고 구분, 질문/답변·event·source/hash·잔여 불확실성, prediction 전 확보 | user_attestation.json·source lock·현재 계약 연결. 이번에 실제 질문13:41:16Z·답변13:43:49Z를 대화에서 확인, lock13:47:09Z 이전 | 질문/답변 출처 보강. raw click value/selection 및 paste30 경과는 UNKNOWN 유지. 개별 labeler나 전체 비노출 증명 아님 |
| 19. 별도 독립 full-context 승인 | approvals registry PASS, canonical manifest/raw/normalized/freeze 정확한 binding, reviewer가 labeler/provenance preparer와 다름, lock 이후, 지정 evidence_review | evaluation_contracts/m05_full_context_approvals.json 없음 | 미확인. engine PASS·label 내용 PASS·bundle preparation PASS로 대체 불가. 이 보고서도 승인 아님 |
| 20. 1회 실행·실패 유지 | normalized input keyed durable claim, 실행 전·후 재검증, 실패/timeout/uncertain 재시도 금지 | 구현 존재. results/development/m05_full_context/attempts 및 일치 claim 없음 | 해당 저장 경로 관측만 확인. 직접 adapter·외부 실행 전혀 없음의 증명은 아님 |
| 21. full prediction provenance | 실제 실행 후417개 ID 정확히 일치, model/version/case/activity/index/reason/duplicate 연결, target20만 사후 join | 실데이터 full prediction 미산출 | 향후 실제 승인 실행 후만 확인할 항목. 지금 생성 금지 |
| 22. 결과 evidence·중앙 계산 | attempt/input/validated_manifest/normalization/locked_target_snapshot/full_predictions/evidence.csv/result/run_manifest, artifact hash, TP+FP+FN+TN=20, 독립 CSV 재계산 | 현 bundle의 실제 결과 파일 없음 | 향후 산출물. F1 미산출은 실패점수나 오염 판정이 아님. 결과 생성으로 현재 gap 해결 불가 |
| 23. 웹·다운로드 | isolated localhost8768, /validate nonprediction, /measure 재검증, run-specific verified download, stale 결과 차단 | 코드 경로 확인. 이번 작업은 validate_bundle read-only와 collection/hash 검사만 수행 | 실제 browser 측정/CSV download acceptance는 아직 실행하지 않음. 사용자 재개 승인 필요 |
| 24. 변경 방지·과거 snapshot | raw/lock/engine/target 의미·계약 보호, 과거 기록을 현재 결과로 덮어쓰지 않음 | 기존 preparation 보호129개 중128개 일치. R&D_COMPLIANCE 한 차이는 기존14:04Z contract-sync의 after hash와 정확히 일치 | 이번 작업의 기존 파일 변경 없음. 과거 정당한 문서 sync를 오염으로 오인하지 않음 |

### Runtime gate의 정확한 의미

실제 unmodified manifest를 validate_bundle에 전달한 결과는 PRIOR_USE_DECLARATIONS_REQUIRED다. validator가 첫 실패에서 멈추므로 이후 gate가 “통과했다”는 뜻이 아니다. 다른 항목은 변경되지 않은 실제 파일을 읽어 개별 요구조건에 대조했다. 선언이나 lock을 수정해 다음 gate를 억지로 진행하지 않았다.

collection 하위 검사와 frozen source normalization은 구조/시각/행 대응 확인을 위한 읽기 전용 검사이며 정제 prediction 호출이 아니다. calculate, evaluate, call_adapter 및 실제 F1 재계산은 호출하지 않았다.

## 4. 시간축과 label 귀속의 중요한 구분

모든 시각은 UTC다. 한국시간은 +9시간이다.

| 시각 | 기록 | 해석 |
|---|---|---|
| 2026-11-09 01:56:51.019524 | engine freeze | 현재 raw 수집 이전 |
| 2026-11-11 12:09:46.818 | full collection 시작 | 첫 raw01 event |
| 2026-11-11 12:48:19.427204 | raw02 blind audit snapshot | 그 시점까지의 후보/자기보고 |
| 2026-11-11 13:11:39.690944 | quota-free prior18 snapshot | 최종417 collection 종료 이전에 prior18 후보가 이미 존재 |
| 2026-11-11 13:28:28.909 | full collection 종료 | 마지막 raw03 event |
| 2026-11-11 13:40:53.691514 | raw03 review | prior18 보존 및 추가2개 미확정 기록, label 내용은 유지 |
| 2026-11-11 13:41:16.509972 | 사용자에게 질문 | 실제 대화 원천 확인 |
| 2026-11-11 13:43:49.537248 | 사용자 직접 회고 답변 | 실제 대화 원천 확인, source lock보다 앞섬 |
| 2026-11-11 13:47:09.237438 | source target20 lock 생성 | batch lock 시각. 각 label의 최초 생성시각이라는 뜻은 아님 |
| 2026-11-11 13:58:13.975721 | full-context preparation | 구조적 mapping/binding 준비. 독립 라벨·실행 승인 아님 |

현재 validator는 모든 labeled_at_utc가 전체 collection 종료 이후이기를 요구한다(backend/m05_full_context.py:265). 따라서 prior18의 최초 생성시각을 13:47로 재기록하거나, 원본 batch lock 시각을 전 행에 넣는 것은 허용되지 않는다.

13:40 및 13:47 기록은 수집 종료 후 기존18개의 보존 검토가 있었음을 뒷받침하지만, 그 기록만으로 책임 있는 labeler의 개별 labeling 시각까지 자동 복원되지는 않는다. 실제 당시 검토/작업 기록에서 행별 결정 귀속과 시각을 확인할 수 있는지를 구분해 검토해야 한다. “최초 후보 시각”, “동일 label 보존을 재검토한 시각”, “파일 lock 시각”은 별도 사실이다. 당시 원천이 없으면 UNKNOWN을 유지하며, 지금 새 회고문이나 서명을 받아 과거 계측 로그로 바꾸지 않는다. 이 보고서는 그 시간 요건을 완화하지 않는다.

### 복구한 사용자 회고 원천

- 질문: 메시지 Sentinel_04964c6512708191a08f046ae29a96fe, 2026-11-11T13:41:16.509972+00:00.
- 답변: 메시지 Sentinel_28f235eb610c819198bac651f0898415, 2026-11-11T13:43:49.537248+00:00.
- 사용자가 답한 핵심 문구: “네 이런 행동을 한 것이 기억납니다.”
- 관련 event: raw03 #26 2acf909a-1edc-4e9e-b576-e78d2a317d4e, #37 faa9bcd5-3d41-4159-8678-3893c7f25914.
- 확인되는 범위: 빈 칸에서 선택/커서 이동 없이 재클릭했다는 설명에 대한 회고가 source lock 전에 존재.
- 확인되지 않는 범위: raw에 없는 각 click의 value/selection 계측, 선행 paste30 미반영 또는 삭제의 경과, 학습·개발 미사용, 전체 prediction 실행/조회 0건.
- source user_attestation.json의 message_id/message_timestamp=null은 이번 작업에서 그대로 보존했다. 위 정보는 기존 대화 원천을 현재 조회하여 보고서에 출처만 추가한 것이다.

## 5. 실제 증빙 복구 시도와 결과

### 5.1 저장소와 동일 Mac에서 확인한 범위

1. raw3개와 sessions/tasks 원본9개, prepared bundle, source label lock, 계약/validator/timestamp 코드, 기존 audit/report·test log·result manifest의 존재와 scope를 확인했다.
2. actual manifest를 그대로 읽어 fail-closed 상태를 재현했다. frozen18개 및 full sequence/timestamp417을 검증했다.
3. 역사12개 CSV를 같은 normalizer로 다시 읽고 inventory equality와 전체417 중복을 검사했다. 현재 data/ 하위의 역사 events.csv 목록과 비교했다.
4. 관련 data/source/lock이 Git에서 아직 tracked 기록으로 제공되지 않음을 확인했다. 따라서 현재 repository commit history만으로 개별 라벨 생성이나 export 시각을 복원하지 않았다.
5. ../AI-model의 최대3단계 log/history/manifest/CSV 이름 후보에서는 config.py 외 관련 기록을 찾지 못했다. 이 제한된 검색이 다른 위치·백업·원격 기록 부재의 증명은 아니다.
6. full-context attempts 디렉터리와 해당 normalized hash claim이 현재 존재하지 않음을 확인했다. 기존 preparation의 shell history 결과도 부분 관측으로만 취급했다.
7. 실제 대화의 질문과 답변 시각/ID를 확인했다. 기존 user_attestation과 두 event 연결은 유지했다.
8. DBeaver debug/activity 로그, collector 소스의 로그 보존 방식 및 기존 DB 연결 경로를 조사했다. 아래 원천 복구 결과를 확인했다.

### 5.2 DBeaver export 기록: 복구됨, raw byte binding은 미완료

원천 A:
- /Users/sooeunkim/Library/DBeaverData/workspace6/.metadata/dbeaver-debug.log
- 관찰 크기36,646 bytes
- SHA-256: 6a99a5cd36eb2289a417b552b4b7b903bb512628c401e27300c798f9caafdc5c
- 관찰 로그 범위: 2026-11-03 14:14:38.648부터 2026-11-12 08:30:59.621까지 local wall time. 현재 Mac KST(+0900)와 activity-log app-open epoch가 서로 부합하나, 모든 과거 시계 설정 이력을 별도 증명한 것은 아니다.
- 455–465행에는 11/11 21:13:50의 수집DB 접속 및 SQL editor Script-35.sql 기록이 있다.

| 로그 줄 | 2026-11-11 local 시각 | 실제 로그에 남은 Downloads 출력 파일명 |
|---|---|---|
| 467 | 21:15:59.296 | sessions_202611112115.csv |
| 471 | 21:16:11.784 | events_202611112116.csv |
| 475 | 21:16:21.501 | tasks_202611112116.csv |
| 479 | 21:39:19.267 | sessions_202611112139.csv |
| 483 | 21:39:27.500 | events_202611112139.csv |
| 487 | 21:39:36.629 | tasks_202611112139.csv |
| 491 | 22:34:10.777 | sessions_202611112234.csv |
| 495 | 22:34:18.365 | events_202611112234.csv |
| 499 | 22:34:25.882 | tasks_202611112234.csv |

이9개 출력 파일은 현재 /Users/sooeunkim/Downloads/에 없다. 로그에는 SQL본문·session ID·row count·export bytes/hash가 없어 3묶음을 raw01/02/03와 확정 연결할 수 없다. 시간·파일종류·순서가 대응하는 **내보내기 기록 후보**이며, 각 raw의 byte-identical receipt로 주장하지 않는다. 이 로그는 CSV export 발생을 뒷받침하지만 collector-to-DB completeness와 prediction 실행/조회 0건은 증명하지 않는다.

원천 B:
- /Users/sooeunkim/Library/DBeaverData/workspace6/.metadata/.activity-logs/1793682890_896792f8-9e57-44bd-baf1-e5d39a37f407.log
- 관찰 크기5,401 bytes
- SHA-256: 383ba410fd7a8b12dd3998a3f2a64e97c295850e584c1810ba17f6e2ec7785be
- 104줄의 SQL_EDITOR_EXECUTE_QUERY·DATA_TRANSFER_START(CSV) 활동 기록. SQL 본문/session IDs는 없고 상대 elapsed timestamp를 사용한다.
- APP_OPEN의 startTime1793682874963은 2026-11-03T05:14:34.963Z. 실행/내보내기 보조 원천으로만 쓴다.

DBeaver의 persisted Scripts와 credential을 제외한 metadata에서 대상3개 session ID/2026-11-11 텍스트를 찾지 못했다. 현재 Script-35.sql의 날짜 조건은 2026-10-14여서 이를 11/11 당시 실행한 SQL로 간주할 수 없다. Query Manager UI가 존재하더라도 이 조사에서는 당시 SQL이 저장된 audit 파일을 찾지 못했고 현재 메모리 UI는 확인하지 않았다.

### 5.3 Collector 및 원격 DB 접근의 확인 범위

- /Users/sooeunkim/Downloads/rainbow-dev/background.js: 101,241 bytes, SHA-256 d796da92462c90e3f5598f940664ac397984576ef72ff4e3e140e920fd78388b.
- 같은 폴더의 manifest.json: version0.1.20, SHA-256 3b2130830e8131bcd345b97bf0a3b63c58f9688500e130ce95635a2ee7506845.
- source의 full upload logging=false, queue console logging=true. pending queue soft/hard limits2000/2100, 성공 upload rows는 pending에서 제거된다. 현재 pending queue는 전송완료의 영구 archive가 아니다.
- 이 결과는 현재 소스의 구현 내용이며 실제 수집 당시 설치된 extension의 동일 checksum을 증명한 것이 아니다. console 로그 설정만으로 과거 durable log 보존을 주장하지 않는다.
- 기존 SSH tunnel의 local127.0.0.1:3307 listener를 확인한 뒤, 기존 문서화 계정/기존 터널에서 읽기 전용 metadata 조회를1회 시도했다. MySQL 초기 handshake에서 ERROR2013 “Lost connection to MySQL server at reading initial communication packet”로 실패했다. SQL 실행 이전에 실패하여 서버 row count·audit/binlog/general log·웹/컨테이너 로그·보존 정책을 조회하지 못했다.
- 신규 SSH 연결, tunnel 재시작, 설정 변경, key 등록은 하지 않았다. 자격증명/개인키 내용을 보고서에 포함하지 않는다.
- repo 결과 경로 및 /private/tmp의 관련 후보에서는 실데이터 full-context attempt/prediction의 durable audit를 확보하지 못했다. prediction 내용을 읽지는 않았다.

실행되지 않은 SQL을 실행 성공으로 보고하지 않는다. 다음 단계는 DB 담당자가 기존 연결을 정상화하거나 당시 보존된 query/export/ingest/audit 기록을 제공하는 것이다. 새 연결·복구·설정 작업은 범위와 권한을 확인한 뒤 진행해야 한다.

### 5.4 관측과 부재를 해석하는 한계

- 현재 파일이 존재하지 않는다는 사실은 과거 삭제·다른 실행 경로·외부 기기를 배제하지 못한다.
- 검색 결과0은 검색한 원천/기간/필드 안에서만 의미가 있다.
- hash는 현재 bytes의 동일성을 보장하며 과거 생성 시각·실제 행위·전체 로그 coverage를 독자적으로 보장하지 않는다.
- 일부 원천 로그가 남아 있다는 사실도 그 서비스의 모든 요청·모든 view를 기록했음을 보장하지 않는다.
- 과거 synthetic test PASS는 구현 동작 확인이지 실제417에 대한 held-out 승인이나 no-view 증거가 아니다.
- 현재 engine이 deterministic rules이고 freeze가 수집보다 앞선다는 점은 유용하지만, 이후 별도 실행·조회·개발 사용이 없었다는 전체 이력을 대신하지 않는다.

## 6. 기존417을 살릴 수 있는 현실적인 해소 절차

이 절차는 **기존 기록의 회수·대조 제안**이며 신규 수집이나 측정 재개 승인이 아니다.

### A. collection/export 원천을 우선 대조

- 원본 export task/SQL/query 설정, DB session ID, 최초/최종 sequence, row_count, export 완료·오류·retry 기록, contemporaneous DB snapshot/백업을 확보한다.
- SQL의 WHERE/JOIN/LIMIT, GUI filter, row cap, timezone 변환, CSV quoting/encoding, export 대상 session3개가 원본 bytes와 연결되는지 확인한다.
- collector 전송 queue/ack/drop/retry·서버 ingest receipt·session close·task completion 기록을 해당 세션에 한정해 대조한다.
- 제공417행의 연속성과 서버 row count를 구분하고, deleted/late-arriving event 여부까지 원천이 덮는지 판단한다.
- 기존 로그/백업을 읽는 것과 live 서비스에 새 조회를 하는 것을 구별한다. 이번 조사에서는 기존 터널을 통한 읽기 전용 metadata 조회를1회 시도했으나 초기 handshake에서 실패하여 서버 SQL은 실행되지 않았다. 연결 복구·신규 접근이 필요하면 그 범위와 권한을 먼저 확인한다.

### B. 실제 사용 이력의 모집단을 확정

- 관련 training/development job registry, CLI/CI/notebook 실행 기록, input manifest와 dataset hash, 원격 실행/저장소·artifact registry를 나열한다.
- raw를 가져간 계정·프로세스·복사본·기기를 기간과 함께 연결한다. 없는 source는 없다고 명시하고 coverage_complete로 치환하지 않는다.
- 확인 가능한 원천을 같은 frozen normalization으로 다시 대조하고 raw417 전체의 ID+feature fingerprint 비중복을 유지한다.
- 독립 reviewer는 어떤 환경·기간·경로가 증거로 덮였고 무엇이 남았는지 검토한다. 지금 작성한 reviewer 의견은 현재의 검토 결과일 뿐 과거 원천 로그가 새로 생긴 것으로 취급하지 않는다.

### C. label 귀속은 기존 당시 기록으로만 복구

- original20/prior18 파일의 당시 생성·검토 작업 기록, 책임 annotator identity, 이벤트별 확정 시간, full collection 종료 뒤 보존 검토의 원천을 회수한다.
- raw03 두 건의 실제 사용자 Q/A 시각은 복구했지만 이를20건 labeler/time으로 확장하지 않는다.
- 원본 label·category·rationale·순서를 유지한다. 새로 labeling한 것처럼 현재 시각을 넣거나 batch lock 시각을 일괄 배정하지 않는다.
- 당시의 기록으로 현재 계약의 시간 요건을 만족한다고 입증할 수 없다면 현재 데이터는 계속 BLOCKED다. 계약 수정이나 사후 증빙 작성으로 푸는 방법은 권고하지 않는다.

### D. prediction 실행·조회 coverage를 별도로 복구

- 12:09:46.818Z부터13:47:09.237438Z까지 모든 relevant runner, direct CLI/adapter, web/API, terminal/tool execution, prediction 저장·열람·download 경로의 기존 원천 로그를 확인한다.
- collection/export 로그와 prediction execution/access 로그를 혼합하지 않는다. raw를 읽어 blind label을 검토한 일과 prediction을 열람한 일도 구분한다.
- run/artifact가 없다는 관측만으로 empty prediction_runs/views 또는 empty source-log entries를 생성하지 않는다.
- 누락·rotation·retention·시계 근거·logger 중단 여부까지 기록해야 “전체 기간 coverage”라고 할 수 있다.

### E. 최종 검토와 승인

A~D의 실제 원천이 충분한 경우에만, 원본과 별도로 정확한 binding을 독립 reviewer가 심사할 수 있다. 기존 labeler·provenance preparer와 다른 reviewer가 현재 전체 계약을 확인해야 하며, 구현 테스트나 이 gap report를 PASS approval로 옮겨 적으면 안 된다.

원천을 충분히 복구하지 못하면 “현재 계약으로 평가 적격성을 입증하지 못함”으로 남긴다. 그 경우에만 신규 데이터 수집을 별도 선택지로 사용자에게 제시한다. 기존417을 오염 데이터로 단정하거나 버리지 않는다.

## 7. 신규 수집이 승인될 경우의 최소 감사 설계

**아직 수행하지 않은 제안이다. 사용자 승인 전에는 새 수집·새 target/label 작성·실제 예측을 시작하지 않는다. 기존417/target20/freeze는 그대로 남긴다.**

### 수집 전에 먼저 준비해야 하는 기록

1. **범위·역할:** 새 collection ID, 승인된 수집 환경/기기/계정·collector 버전, source/export 담당, labeler, provenance preparer, 별도 reviewer를 지정한다. labeler와 provenance preparer를 최종 승인 reviewer와 분리한다.
2. **freeze 기준점:** 기존 engine/config/normalizer·정의·argv의 hash를 기록하고 변경하지 않는다. 측정 조건은 기존20건 계약 그대로다.
3. **로그를 먼저 작동:** collection 시작 이전에 runner execution과 prediction artifact read/view/download를 추적하는 기록을 켜고 coverage 시작시각·환경·clock source·수집 대상·보존기간·회전 정책·logger health를 보관한다. 나중에 빈 로그를 생성하는 방식은 금지한다.
4. **모든 실행 경로 목록:** web/API만이 아니라 direct CLI, notebook, subprocess, copy/export 및 외부 실행 경로를 정의한다. 관리되지 않는 경로가 있으면 complete coverage를 선언하지 않는다. 별도 권한/보안 설정 변경은 그 범위 승인을 받은 뒤에만 한다.
5. **데이터 이용 ledger:** input dataset/session/file hash, 실행 목적(training/development/evaluation/annotation), 실행 ID·actor·UTC·결과·로그 hash를 기록한다. GT 파일은 inference/model input 경로에서 분리한다.

### 수집·export·label lock 시점에 남길 최소 항목

6. **전체 session/task:** collector boot부터 명시적인 session 종료까지 모든 raw event, session/task ID, monotonic sequence, timezone-aware event UTC 또는 identity-bound epoch/UTC, collector version을 저장한다. queue drop/retry/ack 및 ingest receipt를 같은 collection ID로 연결한다.
7. **원본 export receipt:** query text/hash·parameters·source snapshot/cutoff·session list·row counts·min/max sequence·export actor/시간·encoding·오류/필터/LIMIT·각 output SHA-256을 당시 남긴다. 원본 bytes를 그대로 보존한다.
8. **complete raw 먼저 고정:** 전체 수집과 export를 끝내고 raw file list/order/count·sessions/tasks·timestamp proof·normalization digest를 고정한다. 적당한20행만 먼저 잘라 정제 입력으로 쓰지 않는다.
9. **예측 전에 독립 label 확정:** full collection 종료 이후, prediction을 보지 않은 labeler가 KEEP10/REMOVE10을 raw 문맥으로 정하고 각 event ID·출처·binary label·category·rationale·labeler·실제 labeled_at_utc를 즉시 기록한다. REMOVE category quota는 만들지 않는다. 회고가 필요하면 질문·답변 원문/ID/시각·event mapping·불확실성을 그때 보관한다.
10. **실제 lock:** target CSV·selection·raw sequence·normalized input 4개 digest, 실제 lock time·labeler·blindness 선언을 남기고 이후 변경하지 않는다. label 문맥이 부족하면 측정을 보류한다. engine 성능을 예상해 target을 바꾸지 않는다.

### lock 이후, 측정 승인 전에 필요한 확인

11. **비노출 감사:** 수집 시작 전부터 실제 lock까지 연속된 원천 execution/access 로그와 logger health를 대조한다. 실제 prediction entries가0일 때만 validator가 요구하는 빈 결과를 기록한다. 원천 event가 있는 로그를 지우거나 query에서 불리한 event를 제외하지 않는다. summary는 immutable 원천에 path/hash로 연결하며 과거 범위를 가공해 늘리지 않는다.
12. **미사용·완전성 검토:** training/development inventory와 source ledger를 전체 input에 대해 대조하고, collection/export·history·blind lock의 coverage를 독립 확인한다. declaration만으로 gate를 열지 않는다.
13. **정확한 approval binding:** 별도 reviewer가 canonical manifest digest, raw sequence digest, normalized input digest, existing freeze digest가 일치하는 건을 심사한다. 계약의 지정 evidence_review 및 시각 요건을 그대로 유지한다.
14. **사용자에게 재개 승인 요청:** 증빙 검증 결과와 대상 bundle·고정20개·1회 전체 inference라는 범위를 보여준 뒤 실제 측정 승인을 받는다. 수집 승인과 측정 승인은 동일한 것으로 추정하지 않는다.
15. **승인된 1회만 실행:** durable attempt를 먼저 남기고 전체 sequence inference 후 고정20개만 중앙 계산한다. 실패/timeout/불확실 결과도 기록하고 자동 재시도하지 않는다. 결과·CSV·manifest·hash·독립 CSV 대조·브라우저 다운로드 검증을 보관한다.

### 최소 출발 판단

새 수집을 해도 원천 logger·export receipt·label 귀속 설계를 먼저 마련하지 않으면 같은 gap이 반복된다. 그러므로 “일단 새로 모은 뒤 나중에 증빙 작성”이 아니라 **감사 가능한 기록을 준비한 뒤 수집**하는 순서가 필요하다.

## 8. 주요 원천 및 SHA-256

경로는 별도 표시가 없으면 RainbowKTL 기준이다. 아래 hash는 bytes를 식별하며 해당 내용의 진실성·시간·완전성 자체를 보증하지 않는다.

| 원천 | SHA-256 |
|---|---|
| backend/m05_full_context.py | 94814ef48092a51f95f44b908d169d403c05c625c783c0f84fae3a00954f83c9 |
| backend/m05_timestamp_evidence.py | 5c71cf1f048b4d8e6c2bb0eeb9617983ca438888e86729dde7f3a7bfda838678 |
| evaluation_contracts/m05_user20.json | 568e50fd652ee4d1bec7aad32472c17a11940ce472da184d3925bf94293b83e7 |
| R&D_COMPLIANCE.md | 328b136f7f7f11dad7d497d730ea618697e6f8c18a2f36f193689ff0be50c200 |
| evaluation_contracts/development/m05_baseline_frozen_v1/freeze.json | 23fde29b22c23976ccf02760f58b2c2490f3e5b054c385193fc7c463f5f00d10 |
| data/evaluation/m05_heldout_raw_01/events.csv (203행) | 8a797dadcd8341b39e1ce96487eaaafe8995a62dabce3d027495c0f34382b8b4 |
| data/evaluation/m05_heldout_raw_02/events.csv (147행) | 06a86358ada46c3b04c905c018af6004624348a214e210047633da4e28773b50 |
| data/evaluation/m05_heldout_raw_03/events.csv (67행) | c7b699fb540a2f7f67b5b218dbfd0df53b41fe8d4ccac3922b73a7842d1057f8 |
| docs/agents/m05_raw03_attested_label_lock_20261111/target_labels20.csv | 88f48576253211e47f8a39a857734e031d30a9bdbcf4da619e58fdd11cf3ceea |
| docs/agents/m05_raw03_attested_label_lock_20261111/target_label_lock.json | ad553f26834c14995ae31b38b4a884f4875585e0a81b0dd168507e652810b156 |
| docs/agents/m05_raw03_attested_label_lock_20261111/user_attestation.json | 51ac6de99be373248d62a56df1e12379b5cee602181e491335d391f770ed035c |
| bundle/manifest.json | 8e048e425d9cb789a5ba19bbf6b2b48005c787ede4d6b018aa9927f285fd647a |
| bundle/collection.json | edebb0093a936b9e3de1747ffc94c55ae0122466c59a1734f5e0ebb952392ad2 |
| bundle/target_labels.schema_candidate.csv | 3057c8c9e020f0a156b65df66a4284c8b51f219c174032a9e5c89c95746a9750 |
| bundle/label_binding_candidate.json | b8500a69ed468d64e682f22b6d380d4a6961f1d414dab7a999523b9ab07db77b |
| bundle/prediction_access_audit.INCOMPLETE.json | c87a27610ffc27e422e0509f25bfbe42380804d0a4cdb9c487991bc349f7f66a |
| bundle/history/training_inventory.json | 4649acbbacd3c1be1eb01ccb78d3fe3e3f9cf325336f59c59b68ec95c0ad1adb |
| bundle/history/development_inventory.json | 1e9a5e64aec91d1c457c4d638fc17ba61f9d2b22c54a996ce2ddf27e2edae085 |
| bundle/history/source_history_reconciliation.json | c263769a2164209ad3e77212b5c657345076010199f68607a203aa74452c299d |

bundle은 본 보고서 상단의 data/held_out/m05/raw01_raw02_raw03_target20_20261111/를 뜻한다.

Canonical digest (파일 byte hash와 구별):
- raw_sequence_sha256: 2c82ddb91814246ab22c584f8cd78d12821c080faf6377611143d83ab46009ad
- normalized_input_sha256: 8c855f793ee411a309a3b86d06f08203f33ecbe6b010d7ccb55bec985bda7855
- manifest canonical SHA-256: 1aabb9f92383586326d3afd42429b17fb28a56a335e81c6854c5108b46e7a5dd

주요 구현 근거:
- freeze/path/normalization: backend/m05_full_context.py:49–115
- collection/timestamp/session/task: :118–198 및 backend/m05_timestamp_evidence.py
- history completeness/overlap: :201–233
- target/schema/label time/lock/access: :238–281
- independent binding/approval: :285–309
- one-shot claim 및 actual run artifacts: :345–417
- browser validation/measure/download 분리: backend/m05_readiness_web.py
- CSV 검증 계약: backend/m05_full_context_csv.py, scripts/recalculate_m05_full_context_csv.py

## 9. 최종 권고

현재417은 **보존 + 측정 보류**가 적절하다. 이미 확인한 무결성·시각·target·bounded history 결과와 이번에 회수한 실제 원천은 유효한 진전이다. 그러나 source-history와 실행/조회 coverage, label 귀속/시간 및 독립 승인 gap이 남아 있으므로 평가 적격성을 PASS로 전환할 수는 없다.

복구 가능한 당시 기록을 먼저 회수하고, 그 범위가 계약에 미치지 못하면 그 사실을 보고한다. 기존 계약 변경, 빈 로그/과거 시각/새 과거 증빙 생성, prediction을 먼저 실행한 뒤 label 수정은 하지 않는다. 실제 측정 재개 또는 신규 수집은 각각 사용자 승인을 받은 다음에만 진행한다.


보고서 저장 직전 보호 대상80개 hash를 다시 확인했으며 불일치는0개였다. 새 보고서/점검 결과 외 기존 파일을 변경하지 않았다.
