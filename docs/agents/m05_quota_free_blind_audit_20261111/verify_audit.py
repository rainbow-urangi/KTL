import csv,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
snapshot=json.loads((OUT/"audit_snapshot_pre_prediction.json").read_text())
for key in ("protected_sources_and_previous_audits","artifacts"):
    for p,h in snapshot[key].items():assert sha(ROOT/p)==h,p
for x in snapshot["history_inventory"]:assert sha(ROOT/x["path"])==x["sha256"],x["path"]
with (OUT/"partial_label_candidates_NOT_FOR_EVALUATION.csv").open(newline="") as f:rows=list(csv.DictReader(f))
with (ROOT/"docs/agents/m05_raw02_blind_audit_20261111/partial_label_candidates_NOT_FOR_EVALUATION.csv").open(newline="") as f:old=list(csv.DictReader(f))
assert rows[:14]==old and len(rows)==18
assert Counter(r["proposed_label"] for r in rows)=={"KEEP":10,"REMOVE":8}
assert len({r["event_id"] for r in rows})==18
assert all(r["held_out"]=="" for r in rows)
for r in rows:
    with (ROOT/r["source_file"]).open(newline="") as f:raw=list(csv.DictReader(f))
    q=raw[int(r["source_position_1based"])-1]
    assert q["event_id"]==r["event_id"]
    h=hashlib.sha256(json.dumps(q,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
    assert h==r["raw_row_sha256"]
assert snapshot["target_lock_created"] is False
print(json.dumps({"status":"PASS","review_status":"ADDITIONAL_REMOVE_RAW_REQUIRED","labels":{"KEEP":10,"REMOVE":8},"missing_remove":2,"raw_and_prior_audits_unchanged":True,"held_out_certified":False,"target_lock_created":False},ensure_ascii=False))
