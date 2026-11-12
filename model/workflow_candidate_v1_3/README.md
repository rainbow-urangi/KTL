# workflow_candidate_v1_3 (DEVELOPMENT)

기존 v1/v1_1/v1_2 소스와 weight를 보존하는 별도 후보입니다. 경계 모델과 표현 인코더의 실제 forward, 12필드 모델 입력, 기존 session별 시간 정렬·특징·경계 threshold·군집 거리·선택 산식을 유지합니다. 재학습 명령은 제공하지 않습니다. 새 후처리는 sklearn의 `metric`/`affinity` 인자 호환, action이 있는 workflow만을 대상으로 하는 medoid 선택, 검증된 capture 실행뷰입니다.

```powershell
python -X utf8 -B -m model.workflow_candidate_v1_3.src.infer_cli --events <original-events.csv> --capture-manifest <original-capture-manifest.json> --output <new-directory/result.json>
```

`--artifacts` 기본값은 기존 v1_2/artifacts입니다. `--artifact-stage` 기본값은 출력 파일 옆 `<output-stem>-verified-artifacts` 새 폴더입니다. 7개 기존 pinned SHA를 먼저 확인하고, JSON은 CRLF→LF 결과가 기존 pinned SHA와 정확히 같을 때만 새 staging에 정본을 재현합니다. binary 변환, 의미 변경, SHA 수정, 기존 폴더 덮어쓰기를 거부합니다. 원본 upstream manifest 바이트를 복사하고 source/staged/pinned SHA와 재현 방법을 별도 proof에 남깁니다. 실행 결과와 staging을 기존 원본·운영 저장 경로 밖으로 지정합니다.

출력의 `workflows`, `cluster_labels`, `clustering`, `tables`, `canonical`은 모든 learned 분석 결과입니다. lifecycle-only workflow와 model은 유지하되 해당 model은 `NO_ACTIONFUL_WORKFLOW`, canonical은 생성하지 않습니다. actionful 후보끼리의 cosine medoid를 사용합니다.

`capture_view`는 learned medoid와 별도인 `CAPTURE_OBSERVED_SEQUENCE`입니다. 단일 capture/run/root-tab/frame, CSV SHA·byte count·header·건수, manifest의 모든 event ID/session/time/context와 연속 csv_row를 검증합니다. CSV id=worker ordinal을 확인하고 archive 순서를 보존합니다. session-local event_sequence를 전역 정렬키로 사용하지 않습니다. session 전환에는 동일 tab/frame에서 page_close→collector_boot/page_view 근거가 필요합니다. 세션 재진입·동시 다중 tab/frame·불완전 계보는 실패합니다. 이런 분기 자료는 원본에 남기고 임의 연결하지 않습니다.

실제 분석의 모든 process_steps event 근거를 원본 ordinal에 대응하여 관측 절차를 구성합니다. 기존 signature와 source workflow/model/session이 같고 **actionful 부분열에서 인접한 절차**만 압축합니다. 기존 process_map과 동일하게 중간 lifecycle 행은 절차 압축을 끊지 않습니다. 예를 들어 A→lifecycle→A는 A 한 절차에 두 action 이벤트를 근거로 남기며, 중간 lifecycle도 원래 csv_row의 lineage와 제외 diagnostics에 남습니다. 원본 node ID 재방문, session, workflow/model ID, event ID와 csv_row를 보존합니다. 관측 실행은 전형적 업무 전체의 의미나 독립 정답을 보증하지 않으며 포함률을 M03 합격 기준으로 사용하지 않습니다.

`capture_view.canonical`은 `workflow-canonical-1.2`, `canonical_kind=CAPTURE_OBSERVED_SEQUENCE`, 별도 `CAPTURE-PM-* / CAPTURE-WF-*` 식별자를 사용합니다. `capture_view.process_model`은 이 실행뷰의 등록용 행이며 learned `tables.process_models`에 섞지 않습니다. M03 등록 시 이 canonical을 1원소 배열 JSON으로, process_model을 별도 CSV로 작성하고 각각 SHA를 고정할 수 있습니다. 정답은 모델·생성기에 전달하지 않으며 독립 정답이 없으면 평가는 NOT_READY/null입니다.

`forward_evidence`는 경계 모델과 표현 모델의 완료된 torch forward hook 수를 실제 실행에서 기록합니다. callback/mock 합성 검사는 실제 weight forward나 CU 시험 증거와 구분합니다.

```powershell
python -X utf8 -B -m unittest discover -s model/workflow_candidate_v1_3/tests -v
```

`policy.json`은 재시험 전에 고정하는 일반 정책이며 SHA가 결과와 candidate manifest에 기록됩니다. `manifest.json`은 새 후보 source SHA와 기존 pinned artifact identity를 별도로 기록합니다. 새 후보는 기존 승인 버전을 자동 대체하지 않습니다.
