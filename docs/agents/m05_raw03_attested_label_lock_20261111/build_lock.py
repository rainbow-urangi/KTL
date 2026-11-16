"""Build a new evidence-backed label lock without reading or executing predictions."""
import csv, hashlib, json, shutil
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PRIOR = ROOT / "docs/agents/m05_quota_free_blind_audit_20261111"
RAW_AUDIT = ROOT / "docs/agents/m05_raw03_blind_audit_20261111"
csv.field_size_limit(100_000_000)
assert not (OUT / "target_label_lock.json").exists(), "Never overwrite an existing label lock"
NOW = datetime.now(timezone.utc).isoformat()

def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for x in iter(lambda:f.read(1024*1024),b""): h.update(x)
    return h.hexdigest()
def canon(o): return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def rowsha(r): return hashlib.sha256(canon(r)).hexdigest()
def readcsv(p):
    with p.open(encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f); rows=list(r); return list(r.fieldnames),rows
def writejson(n,o): (OUT/n).write_text(json.dumps(o,ensure_ascii=False,indent=2)+"\n")

audit=json.loads((RAW_AUDIT/"audit_snapshot_pre_prediction.json").read_text())
protected=dict(audit["protected_sources_and_previous_audits"])
protected.update(audit["artifacts"])
protected[str((RAW_AUDIT/"audit_snapshot_pre_prediction.json").relative_to(ROOT))]=sha(RAW_AUDIT/"audit_snapshot_pre_prediction.json")
for p,h in protected.items(): assert sha(ROOT/p)==h,p
for x in audit["history_inventory"]: assert sha(ROOT/x["path"])==x["sha256"],x["path"]
_, prior=readcsv(PRIOR/"partial_label_candidates_NOT_FOR_EVALUATION.csv")
assert len(prior)==18 and Counter(r["proposed_label"] for r in prior)=={"KEEP":10,"REMOVE":8}
context=json.loads((RAW_AUDIT/"raw_context_index.json").read_text())["events"]
rawpath=ROOT/"data/evaluation/m05_heldout_raw_03/events.csv"
_,raw=readcsv(rawpath)
assert len(raw)==67

question="제목을 빠르게 세 번 클릭한 구간과 내용의 마지막 두 번 클릭한 구간에서, 칸이 비어 있는 상태로 글자 선택이나 커서 이동 없이 다시 누르기만 하셨나요? 내용은 그전에 붙여넣기 기록도 있는데, 첫 붙여넣기가 반영되지 않았는지 또는 중간에 지우셨는지도 기억나시면 알려주세요."
answer="목을 빠르게 세 번 클릭한 구간과 내용의 마지막 두 번 클릭한 구간에서, 칸이 비어 있는 상태로 글자 선택이나 커서 이동 없이 다시 누르기만 하셨나요? 내용은 그전에 붙여넣기 기록도 있는데, 첫 붙여넣기가 반영되지 않았는지 또는 중간에 지우셨는지도 기억나시면 알려주세요. --> 네 이런 행동을 한 것이 기억납니다."
attestation={
 "source":"Direct user reply in the parent conversation, relayed verbatim through transcript_evidence.",
 "message_id":None,"message_timestamp":None,"recorded_at_utc":NOW,
 "assistant_question_verbatim":question,"user_answer_verbatim":answer,
 "evidence_type":"RETROSPECTIVE_USER_RECOLLECTION_NOT_RAW_TELEMETRY",
 "scope_used":"The user confirmed recollection of the described empty-field reclicks without text selection or cursor movement in the fast title triple-click group and final description two-click group.",
 "not_established":["Whether paste30 failed to insert or was subsequently deleted","Exact deletion or cancellation time","Raw click value or selection fields; these remain null/missing","Complete training/development nonuse"],
 "event_mapping":{"title_fast_triple_click":[25,26,27],"description_last_two_clicks":[36,37]},
 "mapping_basis":"Exact matching chronological groups in source raw03. The user did not supply event IDs; the reviewer mapped the described groups to their raw source positions.",
 "boundary":"This supports the label together with raw context. It is not a claim that raw telemetry alone measured blank values at each click."
}
writejson("user_attestation.json",attestation)

assert len({context[n-1]["target_signature_sha256"] for n in [25,26,27]})==1
assert len({context[n-1]["target_signature_sha256"] for n in [36,37,38,39]})==1
assert all(context[n-1]["input_value"] is None for n in [25,26,27,36,37])
assert context[37]["input_value"]=="" and context[37]["selection_start"]==0 and context[37]["selection_end"]==0
assert context[41]["api_status_code"]=="201"
assert [context[n-1]["interaction_type"] for n in [25,26,27,28]]==["click","click","click","change"]
assert [context[n-1]["interaction_type"] for n in [36,37,38,39]]==["click","click","paste","change"]

def row(n):return context[n-1]
accepted=[
 {"source_position_1based":26,"event_id":row(26)["event_id"],"expected_label":"REMOVE","remove_category":"repeated_action",
  "evidence_class":"RAW_CONTEXT_PLUS_DIRECT_USER_RECOLLECTION","raw_evidence":row(26),
  "canonical_click_preserved":row(25),"original_focus_preserved":row(22),
  "context":[row(n) for n in [22,23,24,25,26,27,28,29,30,40,41,42,43,44]],
  "delta_from_preceding_click_ms":166,
  "rationale":"동일 session/popup/제목 target의 연속 click25→26→27에서 25를 보존한다. 26은 166ms 뒤의 추가 클릭이며 사이에 다른 기록 event가 없다. raw click value=null/selection 미기록 한계는 유지한다. 사용자가 이 빠른 제목 클릭 구간은 빈 칸에서 선택·커서 이동 없이 다시 누른 행동임을 회고 확인했고, 후행 change28 및 정상 저장42와 충돌하지 않는다. 이 결합 증거로 26을 repeated_action REMOVE로 잠근다. 27은 이번20 target으로 추가 선택하지 않으며 KEEP으로 판정하지 않는다."},
 {"source_position_1based":37,"event_id":row(37)["event_id"],"expected_label":"REMOVE","remove_category":"repeated_action",
  "evidence_class":"RAW_CONTEXT_PLUS_DIRECT_USER_RECOLLECTION","raw_evidence":row(37),
  "canonical_click_preserved":row(36),"context":[row(n) for n in range(29,45)],
  "delta_from_preceding_click_ms":1068,
  "rationale":"내용의 마지막 click36→37에서 36을 보존한다. 37은 1068ms 뒤 동일 session/popup/target의 추가 클릭이며 사이에 다른 기록 event가 없다. 사용자는 이 마지막 두 클릭 당시 빈 칸에서 선택·커서 이동 없이 누른 행동을 확인했다. 후행 paste38은 value='' 및 selection0..0, change39는 실제 입력값, 저장42는201을 기록한다. 선행 paste30의 미반영/삭제 경과는 UNKNOWN이나, 그 경과 불명은 마지막 클릭 시점의 빈 상태에 대한 직접 확인을 부정하는 증거가 아니다. raw-only 증명으로 바꾸지 않고 결합 증거로 37을 repeated_action REMOVE로 잠근다.",
  "earlier_paste_resolution":"UNKNOWN: neither failed insertion nor deletion is asserted."}
]
writejson("additional_label_evidence.json",{"accepted":accepted,"not_selected": {"title_27":"Not a target in this 20-event lock; not relabeled KEEP.","other_raw03_candidates":"Remain outside the target lock."}})

shutil.copyfile(PRIOR/"partial_label_candidates_NOT_FOR_EVALUATION.csv",OUT/"prior18_preserved.csv")
assert (OUT/"prior18_preserved.csv").read_bytes()==(PRIOR/"partial_label_candidates_NOT_FOR_EVALUATION.csv").read_bytes()
targets=[]
for r in prior:
 targets.append({"event_id":r["event_id"],"expected_label":r["proposed_label"],"remove_category":r["proposed_remove_category"],
 "source_file":r["source_file"],"source_position_1based":int(r["source_position_1based"]),"raw_id":r["raw_id"],
 "session_id":r["session_id"],"source_event_sequence":int(r["source_event_sequence"]),"event_time_kst":r["event_time_kst"],
 "source_sha256":r["source_sha256"],"raw_row_sha256":r["raw_row_sha256"],"held_out":"","used_for_training":"","used_for_development":"",
 "label_provenance":"PRESERVED_PRIOR_BLIND_REVIEW","rationale":r["rationale"]})
for a in accepted:
 r=a["raw_evidence"]
 targets.append({"event_id":r["event_id"],"expected_label":"REMOVE","remove_category":"repeated_action",
 "source_file":r["source_file"],"source_position_1based":r["source_position_1based"],"raw_id":r["raw_id"],
 "session_id":r["session_id"],"source_event_sequence":r["source_event_sequence"],"event_time_kst":r["event_time_kst"],
 "source_sha256":r["source_sha256"],"raw_row_sha256":r["raw_row_sha256"],"held_out":"","used_for_training":"","used_for_development":"",
 "label_provenance":"RAW_CONTEXT_PLUS_DIRECT_USER_RECOLLECTION","rationale":a["rationale"]})
assert len(targets)==20 and len({r["event_id"] for r in targets})==20
assert Counter(r["expected_label"] for r in targets)=={"KEEP":10,"REMOVE":10}
for r in targets:
 _, rr=readcsv(ROOT/r["source_file"]);e=rr[r["source_position_1based"]-1]
 assert e["event_id"]==r["event_id"] and rowsha(e)==r["raw_row_sha256"] and sha(ROOT/r["source_file"])==r["source_sha256"]
with (OUT/"target_labels20.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(targets[0]));w.writeheader();w.writerows(targets)
writejson("gate_report.json",{
 "created_at_utc":NOW,"label_status":"LOCKED_KEEP10_REMOVE10",
 "evaluation_status":"BLOCKED_HELD_OUT_AUDIT_AND_INDEPENDENT_VERIFICATION",
 "label_evidence":"18 existing labels plus raw03 title26 and description37. New labels depend on direct retrospective user confirmation plus raw context, not raw-only values.",
 "gates":{"raw_integrity":"PASS_67_EVENTS_57_TASKS_1_SESSION","prior_artifact_hashes":"PASS_UNCHANGED",
 "available_history17_nonoverlap":"PASS_WITHIN_RECORDED_SCOPE","source_after_recorded_freeze":"PASS",
 "current_engine_freeze_reverification":"SEPARATE_NOT_PERFORMED_BY_BLIND_LABELER",
 "complete_training_development_history":"UNVERIFIED","actual_engine_feature_content_nonoverlap":"UNVERIFIED",
 "independent_label_lock_verification":"PENDING","evaluation_authorized_or_ready":False},
 "held_out_declared_true":False,"training_nonuse_declared_false":False,"development_nonuse_declared_false":False,
 "prediction_files_read":False,"engine_or_adapter_read_or_executed":False,"prediction_executions_by_this_review":0,
 "metrics_generated":False,"official_result":False,
 "earlier_paste_course":"UNKNOWN; no assertion of failed insertion or deletion.",
 "scope_limitation":"No engine-facing evaluation manifest or features are built here. Full raw01/02/03 context must remain intact for a later authorized one-shot evaluation after gates pass."
})
readme="""# M05 사용자 확인 결합 사전 label lock

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
"""
(OUT/"README.md").write_text(readme)

verify='''"""Read-only verification of locked labels, source references and evidence hashes."""
import csv, hashlib, json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
csv.field_size_limit(100_000_000)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=json.loads((OUT/"target_label_lock.json").read_text())
assert sha(OUT/"target_label_lock.json")== (OUT/"target_label_lock.sha256").read_text().split()[0]
for group in ("protected_sources_and_previous_audits","artifacts"):
 for p,h in lock[group].items():assert sha(ROOT/p)==h,p
for x in lock["history_inventory"]:assert sha(ROOT/x["path"])==x["sha256"],x["path"]
with (OUT/"target_labels20.csv").open(newline="") as f:rows=list(csv.DictReader(f))
assert len(rows)==20 and len({r["event_id"] for r in rows})==20
assert Counter(r["expected_label"] for r in rows)=={"KEEP":10,"REMOVE":10}
assert [int(r["source_position_1based"]) for r in rows[-2:]]==[26,37]
assert all(r["held_out"]==r["used_for_training"]==r["used_for_development"]=="" for r in rows)
old=ROOT/"docs/agents/m05_quota_free_blind_audit_20261111/partial_label_candidates_NOT_FOR_EVALUATION.csv"
assert old.read_bytes()==(OUT/"prior18_preserved.csv").read_bytes()
with old.open(newline="") as f:prior=list(csv.DictReader(f))
for p,r in zip(prior,rows[:18]):
 assert r["event_id"]==p["event_id"] and r["expected_label"]==p["proposed_label"] and r["remove_category"]==p["proposed_remove_category"]
 assert r["raw_row_sha256"]==p["raw_row_sha256"]
for r in rows:
 with (ROOT/r["source_file"]).open(newline="") as f:source=list(csv.DictReader(f))
 e=source[int(r["source_position_1based"])-1]
 assert e["event_id"]==r["event_id"]
 assert hashlib.sha256(json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()==r["raw_row_sha256"]
gate=json.loads((OUT/"gate_report.json").read_text())
assert gate["prediction_executions_by_this_review"]==0 and not gate["metrics_generated"] and not gate["gates"]["evaluation_authorized_or_ready"]
print(json.dumps({"status":"PASS","label_status":"LOCKED_KEEP10_REMOVE10","new_positions":[26,37],"evaluation_status":gate["evaluation_status"],"target_labels20_sha256":sha(OUT/"target_labels20.csv"),"lock_sha256":sha(OUT/"target_label_lock.json"),"predictions":0},ensure_ascii=False))
'''
(OUT/"verify_lock.py").write_text(verify)
for p,h in protected.items():assert sha(ROOT/p)==h,p
artifacts={str(p.relative_to(ROOT)):sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ["target_label_lock.json","target_label_lock.sha256"]}
lock={"kind":"PREDICTION_BLIND_LABEL_LOCK_NOT_EVALUATION_MANIFEST","created_at_utc":NOW,
 "labels":{"KEEP":10,"REMOVE":10},"remove_categories":dict(Counter(r["remove_category"] for r in targets if r["expected_label"]=="REMOVE")),
 "target_order":[r["event_id"] for r in targets],"new_target_positions_raw03":[26,37],
 "target_labels20_sha256":sha(OUT/"target_labels20.csv"),"prior18_unchanged":True,
 "label_source":"Raw evidence plus direct retrospective user confirmation for the two new events; prior18 unchanged.",
 "prediction_executions_by_this_review":0,"prediction_files_read":False,"target_changes_after_prediction_allowed":False,
 "evaluation_gate":"BLOCKED_HELD_OUT_AUDIT_AND_INDEPENDENT_VERIFICATION",
 "protected_sources_and_previous_audits":protected,"history_inventory":audit["history_inventory"],"artifacts":artifacts}
writejson("target_label_lock.json",lock)
(OUT/"target_label_lock.sha256").write_text(sha(OUT/"target_label_lock.json")+"  target_label_lock.json\n")
print(json.dumps({"label_status":"LOCKED_KEEP10_REMOVE10","target_labels20_sha256":sha(OUT/"target_labels20.csv"),"lock_sha256":sha(OUT/"target_label_lock.json"),"new_positions":[26,37],"new_event_ids":[r["event_id"] for r in targets[-2:]],"categories":lock["remove_categories"]},ensure_ascii=False))
