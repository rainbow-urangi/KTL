"""Read-only verification of locked labels, source references and evidence hashes."""
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
