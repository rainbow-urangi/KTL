"""Read-only artifact/hash verifier. Never reads prediction files."""
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
