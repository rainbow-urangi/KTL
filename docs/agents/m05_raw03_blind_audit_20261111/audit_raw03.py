"""Independent source-only audit. No model, adapter, evaluator, or prediction imports or reads."""
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RAW = ROOT / "data/evaluation/m05_heldout_raw_03"
PRIOR = ROOT / "docs/agents/m05_quota_free_blind_audit_20261111"
csv.field_size_limit(100_000_000)
KST = timezone(timedelta(hours=9))
FREEZE = datetime(2026, 11, 9, 10, 56, 51, tzinfo=KST)
NOW = datetime.now(timezone.utc).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def rowsha(r):
    return hashlib.sha256(canon(r)).hexdigest()

def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows

def write_json(name, o):
    (OUT / name).write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n")

old_snapshot = json.loads((PRIOR / "audit_snapshot_pre_prediction.json").read_text())
protected = dict(old_snapshot["protected_sources_and_previous_audits"])
protected.update(old_snapshot["artifacts"])
protected[str((PRIOR / "audit_snapshot_pre_prediction.json").relative_to(ROOT))] = sha(PRIOR / "audit_snapshot_pre_prediction.json")
prior_mismatches = [p for p, h in protected.items() if sha(ROOT / p) != h]
assert not prior_mismatches, prior_mismatches

raw = {}
for name in ("events.csv", "tasks.csv", "sessions.csv"):
    cols, rows = read_csv(RAW / name)
    raw[name] = {"columns": cols, "rows": rows, "sha256": sha(RAW / name)}
    protected[str((RAW / name).relative_to(ROOT))] = raw[name]["sha256"]
events, tasks, sessions = (raw[n]["rows"] for n in ("events.csv", "tasks.csv", "sessions.csv"))
_, old_labels = read_csv(PRIOR / "partial_label_candidates_NOT_FOR_EVALUATION.csv")
assert len(old_labels) == 18
assert Counter(r["proposed_label"] for r in old_labels) == {"KEEP": 10, "REMOVE": 8}

issues = []
for name, data in raw.items():
    for n, row in enumerate(data["rows"], 1):
        if None in row or any(v is None for v in row.values()):
            issues.append({"code": "CSV_FIELD_COUNT_MISMATCH", "file": name, "position": n})
    ids = [r["id"] for r in data["rows"]]
    if len(ids) != len(set(ids)):
        issues.append({"code": "DUPLICATE_PRIMARY_ID", "file": name})
sids = {r["id"] for r in sessions}
tids = {r["id"] for r in tasks}
eids = {r["event_id"] for r in events}
if len(eids) != len(events) or "" in eids:
    issues.append({"code": "EVENT_ID_INVALID"})
if any(r["session_id"] not in sids for r in events + tasks):
    issues.append({"code": "SESSION_FK_MISSING"})
if any(r["task_id"] not in tids for r in events):
    issues.append({"code": "TASK_FK_MISSING"})
payloads, times, received, sequences = [], [], [], []
context = []
for n, r in enumerate(events, 1):
    d = json.loads(r["locators_json"])
    payloads.append(d)
    ec, rp, ic = d.get("event_context", {}), d.get("raw_payload", {}), d.get("input_context", {})
    ts = datetime.fromisoformat(ec["event_time"].replace("Z", "+00:00"))
    rt = datetime.fromisoformat(d["analysis"]["server_quality_guard"]["received_at"].replace("Z", "+00:00"))
    times.append(ts); received.append(rt); sequences.append(ec["event_sequence"])
    if ec["event_id"] != r["event_id"]: issues.append({"code": "EVENT_ID_MISMATCH", "position": n})
    if d["session"]["page_session_id"] != r["session_id"]: issues.append({"code": "PAYLOAD_SESSION_MISMATCH", "position": n})
    if datetime.fromisoformat(r["event_time"]).replace(tzinfo=KST) != ts: issues.append({"code": "EXPORT_PAYLOAD_TIME_MISMATCH", "position": n})
    if abs(d["analysis"]["event_ts_ms"] - ts.timestamp() * 1000) > 0.1: issues.append({"code": "EPOCH_TIME_MISMATCH", "position": n})
    if ts <= FREEZE: issues.append({"code": "NOT_AFTER_RECORDED_FREEZE", "position": n})
    if rt < ts: issues.append({"code": "RECEIVED_BEFORE_EVENT", "position": n})
    signature = {k: r[k] for k in ("session_id", "page_url", "target_selector", "selector_xpath", "element_tag", "associated_label")}
    signature["active_popup_id"] = ec.get("active_popup_id")
    context.append({
        "source_file": str((RAW / "events.csv").relative_to(ROOT)),
        "source_position_1based": n, "csv_record_number_including_header": n + 1,
        "raw_id": r["id"], "event_id": r["event_id"], "session_id": r["session_id"],
        "source_event_sequence": ec["event_sequence"], "event_time_kst": r["event_time"],
        "event_time_utc": ec["event_time"], "received_at_utc": rt.isoformat(),
        "interaction_type": r["interaction_type"], "interaction_id": ec["interaction_id"],
        "target_signature": signature, "target_signature_sha256": rowsha(signature),
        "raw_row_sha256": rowsha(r), "source_sha256": raw["events.csv"]["sha256"],
        "input_value": ic.get("value"), "input_value_present": "value" in ic,
        "input_data": r["input_data"], "pasted_text": ic.get("pasted_text"),
        "selection_start": rp.get("selection_start"), "selection_end": rp.get("selection_end"),
        "selection_start_present": "selection_start" in rp, "selection_end_present": "selection_end" in rp,
        "api_method": r["api_method"], "api_path": r["api_path"], "api_status_code": r["api_status_code"],
        "element_text": r["element_text"], "ui_outcome": d.get("ui_outcome")
    })
if sequences != list(range(1, len(events) + 1)): issues.append({"code": "NONCONTIGUOUS_SEQUENCE"})
backtracks = [{"previous_position": i, "position": i + 1} for i in range(1, len(times)) if times[i] < times[i - 1]]
for r in tasks:
    start, end = (datetime.fromisoformat(r[k]) for k in ("start_time", "end_time"))
    if start > end or abs((end-start).total_seconds() * 1000 - int(r["duration_ms"])) > 0.01:
        issues.append({"code": "TASK_TIME_OR_DURATION_MISMATCH", "id": r["id"]})
for r in sessions:
    vals = [datetime.fromisoformat(e["event_time"]) for e in events if e["session_id"] == r["id"]]
    if min(vals) != datetime.fromisoformat(r["start_time"]) or max(vals) != datetime.fromisoformat(r["end_time"]):
        issues.append({"code": "SESSION_ENVELOPE_MISMATCH", "id": r["id"]})

history_paths = [x["path"] for x in old_snapshot["history_inventory"]]
history_paths += ["data/evaluation/m05_heldout_raw_01/events.csv", "data/evaluation/m05_heldout_raw_02/events.csv"]
expected_history = {x["path"]: x["sha256"] for x in old_snapshot["history_inventory"]}
raw_row_hashes = {rowsha(r) for r in events}
raw_content_hashes = {rowsha({k:v for k,v in r.items() if k not in ("id", "event_id")}) for r in events}
inventory = []
for p in history_paths:
    cols, rows = read_csv(ROOT / p)
    is_events = "event_type" in cols
    h = sha(ROOT / p)
    inventory.append({
        "path": p, "resolved_path": str((ROOT / p).resolve().relative_to(ROOT)),
        "sha256": h, "prior_sha256_matches": h == expected_history.get(p, protected.get(p)),
        "source_type": "event_rows" if is_events else "event_reference_index", "row_count": len(rows),
        "event_id_overlap": sorted({r.get("event_id") for r in rows} & eids),
        "session_id_overlap": sorted({r.get("session_id") for r in rows} & sids),
        "canonical_raw_row_overlap": sorted({rowsha(r) for r in rows} & raw_row_hashes) if is_events else [],
        "id_excluded_raw_content_overlap": sorted({rowsha({k:v for k,v in r.items() if k not in ("id","event_id")}) for r in rows} & raw_content_hashes) if is_events else []
    })
history = {
    "scope": "The prior recorded 15 training/development CSV files plus raw01/raw02 event files. All are source event rows or event-reference indexes, not engine predictions. External, deleted, undocumented and unavailable histories are not covered.",
    "inference_feature_hashes_checked": False,
    "limitation": "Raw-content hashes retain nested provenance, session IDs and timestamps and are not model-facing feature hashes.",
    "files": inventory
}
write_json("history_inventory.json", history)
validation = {
    "status": "RAW_STRUCTURALLY_VALID" if not issues else "RAW_VALIDATION_ISSUES", "created_at_utc": NOW,
    "raw_files": {n: {k:v for k,v in d.items() if k != "rows"} | {"record_count": len(d["rows"])} for n,d in raw.items()},
    "event_count": len(events), "task_count": len(tasks), "session_count": len(sessions),
    "session_ids": sorted(sids), "interaction_counts": dict(Counter(r["interaction_type"] for r in events)),
    "source_sequence_contiguous": sequences == list(range(1, len(events)+1)), "source_order_preserved": True,
    "timestamps": {"first_utc": min(times).isoformat(), "last_utc": max(times).isoformat(),
        "first_kst": min(times).astimezone(KST).isoformat(), "last_kst": max(times).astimezone(KST).isoformat(),
        "received_min_utc": min(received).isoformat(), "received_max_utc": max(received).isoformat(),
        "all_after_recorded_freeze": min(times) > FREEZE, "source_order_backtracks": backtracks},
    "freeze_reference": {"kst": FREEZE.isoformat(), "utc": FREEZE.astimezone(timezone.utc).isoformat(),
        "authority": "Previously recorded independent raw audit cutoff. Current engine metadata not read by blind reviewer; independent freeze re-verification remains separate."},
    "checks": {"unique_event_ids": len(eids) == len(events), "parsed_json_count": len(payloads),
        "history_files": len(inventory), "prior_history_hash_mismatches": sum(not x["prior_sha256_matches"] for x in inventory),
        "history_event_id_overlap_count": sum(len(x["event_id_overlap"]) for x in inventory),
        "history_session_id_overlap_count": sum(len(x["session_id_overlap"]) for x in inventory),
        "history_canonical_raw_row_overlap_count": sum(len(x["canonical_raw_row_overlap"]) for x in inventory),
        "history_id_excluded_raw_content_overlap_count": sum(len(x["id_excluded_raw_content_overlap"]) for x in inventory)},
    "issues": issues, "held_out_certified": False, "history_inventory_sha256": sha(OUT / "history_inventory.json")
}
write_json("raw_validation.json", validation)
write_json("raw_context_index.json", {"source_order_preserved": True, "events": context})

def excerpt(positions):
    return [context[n-1] for n in positions]

groups = [
    {"name": "first_title_reclicks", "candidate_positions": [23,24,25,26,27],
     "decision": "AMBIGUOUS_NOT_GT", "reason": "제목 최초 focus22 후 재클릭23~27과 change28이 관측된다. 모든 click의 value=null이고 selection은 미기록이다. change는 값이 보고된 시점이며 실제 입력 시작을 증명하지 않는다. 제목 문자열은 곧 내용 paste30에도 등장하므로 선택/복사 준비 가능성을 배제할 수 없다. 새 폼/동일 target/빠른 간격만으로 빈 값 불변을 확정하지 않는다.",
     "context": excerpt(list(range(19,31)))},
    {"name": "first_description_after_earlier_paste", "candidate_positions": [31,32,33,34,37],
     "decision": "AMBIGUOUS_NOT_GT", "reason": "내용 최초 focus29 다음 paste30이 먼저 기록되며, 이후 재클릭31~34가 있다. refocus36→추가클릭37→paste38의 국소 문맥은 반복처럼 보이나 paste30와 paste38은 모두 직전 value=''를 기록한다. 그 사이의 미기록 삭제/선택 또는 첫 paste 취소 여부를 raw에서 구분할 수 없다. 따라서 paste38의 빈 값을 click37 시점까지 소급하지 않는다. click37 value=null이며 selection 미기록이다. 실제 input/change39, 등록40/submit41, POST42=201은 보존한다.",
     "context": excerpt(list(range(29,45)))},
    {"name": "second_title_after_paste", "candidate_positions": [54,55],
     "decision": "AMBIGUOUS_NOT_GT", "reason": "빈 제목 paste52가 재클릭53~55보다 먼저 있다. 이후 change56에는 _02가 추가된 값이 있다. 텍스트 선택·커서 이동·수정 준비 가능성을 배제할 수 없으며 null은 빈 값이 아니다.",
     "context": excerpt(list(range(45,58)))},
    {"name": "second_form_refocus", "candidate_positions": [51,59],
     "decision": "EXCLUDED_FOCUS_REQUIRED_NOT_GT", "reason": "제목48→내용50→제목51 및 내용57→제목58→내용59는 서로 다른 필드 간 focus 이동이다. paste52/60을 위한 재진입을 무의미한 연속 재클릭으로 취급하지 않는다.",
     "context": excerpt([48,49,50,51,52,56,57,58,59,60,61,62,63,64,65,66])}
]
write_json("ambiguous_candidates_NOT_GT.json", {
    "status": "NO_ADDITIONAL_OBJECTIVE_REMOVE", "new_labels": [], "groups": groups,
    "not_keep_labels": "Excluded or ambiguous events have not been relabeled KEEP. They remain unlabeled.",
    "user_statement_status": "Collection intent is supporting context, not a replacement for raw value/selection evidence."
})
shutil.copyfile(PRIOR / "partial_label_candidates_NOT_FOR_EVALUATION.csv", OUT / "partial_label_candidates_NOT_FOR_EVALUATION.csv")
assert sha(PRIOR / "partial_label_candidates_NOT_FOR_EVALUATION.csv") == sha(OUT / "partial_label_candidates_NOT_FOR_EVALUATION.csv")
report = {
    "status": "BLOCKED_ADDITIONAL_REMOVE_EVIDENCE_REQUIRED", "created_at_utc": NOW,
    "contract": {"mode": "DEVELOPMENT", "total": 20, "KEEP": 10, "REMOVE": 10, "category_quotas": None},
    "result": {"raw03_events_reviewed": len(events), "new_confirmed_remove": 0, "preserved_keep": 10, "preserved_remove": 8,
        "preserved_total": 18, "missing_objective_remove": 2, "target20_lock_created": False,
        "preserved_previous_csv_byte_identical": True, "new_predictions": 0, "scores_generated": False},
    "held_out": {"status": "SUPPORTED_WITHIN_AVAILABLE_SOURCE_HISTORY_NOT_CERTIFIED", "held_out_field": "blank",
        "history_files_checked": len(inventory), "complete_training_development_nonuse_certified": False,
        "engine_feature_content_nonoverlap_check": "NOT_PERFORMED_BY_BLIND_LABELER",
        "outside_or_deleted_history_certified": False},
    "blindness": {"engine_code_read": False, "adapter_code_read": False, "prediction_files_read": False,
        "engine_or_adapter_executed": False, "prediction_based_selection": False},
    "limitations": ["수집 의도와 raw 값/선택 상태 증거를 구분했다.", "change event 시간은 입력 시작 시간이 아니다.",
        "click value=null은 빈 문자열 또는 값 불변 증거가 아니다.", "저장 성공은 확인되지만 모든 재클릭의 무의미함을 증명하지 않는다.",
        "raw03은 신규 session이지만 같은 site/install/tab의 연속 사용으로 독립 업무 객체라고 주장하지 않는다.",
        "학습/개발 이력 completeness와 실제 model feature-content 미중복은 별도 검증이 필요하다."],
    "next_evidence": "현재 raw에서 두 건 확정은 불가하다. 녹화나 전후 value/selection을 직접 기록한 동시 증거가 있으면 해당 event ID와 대조한다. 없으면 새 폼의 빈 필드에서 최초 focus, 추가 클릭, paste 직전 value='' 및 selection 0..0, 실제 입력/저장까지 온전한 새 수집을 수행하고 독립 검토한다. 선행 paste 뒤 재클릭이나 여러 필드 사이 focus 전환은 피한다. 원본에 누락 증거를 사후 삽입하지 않는다.",
    "tests": {"raw_and_hash_audit": "PASS" if not issues else "ISSUES", "backend_or_engine_changed": False,
        "backend_full_unit_tests": "NOT_RUN: documentation/source-only audit, no backend/evaluation implementation change."}
}
write_json("review_report.json", report)
readme = """# M05 raw03 prediction-blind 독립 감사

## 결론

**BLOCKED_ADDITIONAL_REMOVE_EVIDENCE_REQUIRED. 기존 KEEP 10 / REMOVE 8, 총18건을 그대로 유지한다. raw03에서 객관적으로 확정한 추가 REMOVE는 0건이며 2건이 부족하다. target20 lock과 prediction/점수는 만들지 않았다.**

67개 event의 원래 순서, 1개 session과 업무 등록 2회의 전후 문맥을 확인했다. 두 등록은 POST /api/schedules 201로 성공했다. 저장 성공과 재클릭의 제거 가능성은 별도 판단이다.

## 판단 근거

- 첫 제목: focus22 뒤 click23~27, change28이다. click26/27은 166/167ms 연속 클릭이지만 value=null이고 selection이 없다. change28은 입력 시작 시점을 보장하지 않는다. 뒤이어 같은 문자열이 내용에 paste30되므로 제목 선택/복사 가능성을 배제하지 않는다.
- 첫 내용: paste30이 click31~34보다 먼저다. focus36→click37→paste38만 떼면 반복 후보처럼 보이지만, 앞선 paste30과 후행 paste38 모두 직전 빈 값을 기록한다. 미기록 삭제/선택 또는 첫 paste 취소 여부가 없어 click37 당시 빈 값인지 확정할 수 없다. click37을 잠정 검토했으나 최종 채택하지 않았다.
- 두 번째 제목: paste52 뒤 click53~55, 수정 값 change56이다. 빈 필드 재클릭으로 판정하지 않는다.
- 두 번째 폼의 click51/59는 다른 필드를 거쳐 돌아온 focus다. 입력을 위한 필드 재진입을 제거하지 않는다.
- 모호한 후보는 KEEP 정답으로 바꾼 것이 아니라 미확정이다. category 수나 20건에 맞추어 label을 만들지 않았다.

raw source position은 헤더 제외 1부터이며 csv record는 그 값에 1을 더한다. 상세 event ID, raw ID, session, popup, target signature/hash, KST/UTC 시각, 값/selection, 앞뒤 보존 문맥은 raw_context_index.json과 ambiguous_candidates_NOT_GT.json에 있다.

## 무결성과 held-out 범위

기존 감사 및 18행 CSV의 hash를 재확인했고 partial CSV는 byte-identical 복사본이다. 원본 CSV, 과거 감사, 모델, 엔진, adapter, 평가 계약을 변경하지 않았다. 기존 15개 학습/개발 source/index와 raw01/02, 총17개 파일에 대해 event ID/session/raw row/id-excluded raw content 중복을 비교했다. 실제 결과와 원본 해시는 raw_validation.json 및 history_inventory.json을 따른다.

수집 시각은 기존 감사의 freeze cutoff 2026-11-09 10:56:51 KST 이후다. 이 cutoff의 현재 엔진 메타데이터 재검증은 별도이며 이 labeler는 엔진/adapter/prediction을 읽거나 실행하지 않았다.

외부·삭제·미기록 학습/개발 이력이나 실제 inference feature-content의 미중복은 인증하지 않는다. raw content hash에는 nested ID/time이 남아 있으므로 feature hash가 아니다. held_out 필드는 비워 두고 공식/완전한 미사용을 주장하지 않는다.

## 다음 증거

기존 녹화나 동시 기록된 전후 value/selection 증거가 있으면 event ID와 대조할 수 있다. 없으면 선행 paste가 없는 새 빈 필드에서 최초 focus를 보존하고 추가 클릭 뒤 바로 paste하되, paste 직전 value='' 및 selection 0..0, 실제 입력/저장까지 기록하는 새 수집이 필요하다. 두 건 확보를 미리 보장하지 않는다. 누락 증거를 원본에 사후 삽입하지 않는다.

## 검증

python3 docs/agents/m05_raw03_blind_audit_20261111/verify_audit.py

backend나 평가 구현을 수정하지 않았으므로 backend 전체 unit test는 실행하지 않았다. 이 검증은 raw integrity, history overlap, 기존18행/원본/산출물 hash 및 prediction 미생성 상태만 확인한다.
"""
(OUT / "README.md").write_text(readme)

verify = '''"""Read-only artifact/hash verifier. Never reads prediction files."""
import csv, hashlib, json
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
csv.field_size_limit(100_000_000)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
snapshot = json.loads((OUT / "audit_snapshot_pre_prediction.json").read_text())
for group in ("protected_sources_and_previous_audits", "artifacts"):
    for p,h in snapshot[group].items(): assert sha(ROOT/p)==h, p
for x in snapshot["history_inventory"]: assert sha(ROOT/x["path"])==x["sha256"], x["path"]
old=ROOT/"docs/agents/m05_quota_free_blind_audit_20261111/partial_label_candidates_NOT_FOR_EVALUATION.csv"
new=OUT/"partial_label_candidates_NOT_FOR_EVALUATION.csv"
assert old.read_bytes()==new.read_bytes()
rows=list(csv.DictReader(new.open(newline="")))
assert len(rows)==18 and Counter(r["proposed_label"] for r in rows)=={"KEEP":10,"REMOVE":8}
assert all(r["held_out"]=="" for r in rows)
for r in rows:
    raw=list(csv.DictReader((ROOT/r["source_file"]).open(newline="")))
    e=raw[int(r["source_position_1based"])-1]
    assert e["event_id"]==r["event_id"]
    assert hashlib.sha256(json.dumps(e,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()==r["raw_row_sha256"]
v=json.loads((OUT/"raw_validation.json").read_text())
assert not v["issues"]
assert v["checks"]["history_files"]==17
assert all(v["checks"][k]==0 for k in ("prior_history_hash_mismatches","history_event_id_overlap_count","history_session_id_overlap_count","history_canonical_raw_row_overlap_count","history_id_excluded_raw_content_overlap_count"))
assert not snapshot["target_lock_created"]
report=json.loads((OUT/"review_report.json").read_text())
assert report["result"]["new_confirmed_remove"]==0 and report["result"]["new_predictions"]==0
print(json.dumps({"status":"PASS","review_status":report["status"],"labels":{"KEEP":10,"REMOVE":8},"missing_remove":2,"target_lock_created":False,"raw_and_prior_audits_unchanged":True,"held_out_certified":False},ensure_ascii=False))
'''
(OUT / "verify_audit.py").write_text(verify)
assert all(sha(ROOT/p)==h for p,h in protected.items())
artifacts = {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "audit_snapshot_pre_prediction.json"}
write_json("audit_snapshot_pre_prediction.json", {
    "kind": "AUDIT_SNAPSHOT_NOT_TARGET_LOCK", "created_at_utc": NOW, "status": report["status"],
    "target_lock_created": False, "prediction_executions_by_this_review": 0,
    "protected_sources_and_previous_audits": protected,
    "history_inventory": [{"path":x["path"],"sha256":x["sha256"]} for x in inventory], "artifacts": artifacts
})
print(json.dumps({"report":report["result"],"raw_validation":validation["status"],"checks":validation["checks"],"issues":issues,"timestamps":validation["timestamps"]},ensure_ascii=False,indent=2))
