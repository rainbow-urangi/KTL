"""Read-only reproduction freeze verification; no engine execution."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
EXPECTED="077eb74cb94c998fd2bdb3d304ad1eaf1a22c6881c794979926042c5dd975931"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=Path(__file__).with_name('freeze.json')
assert sha(p)==EXPECTED,'Freeze manifest changed'
f=json.loads(p.read_text())
for e in f['immutable_implementation_artifacts']+[f['baseline_freeze']]:
 assert sha(ROOT/e['path'])==e['sha256'],e['path']
proof=f['protected_originals_and_labels']; p=ROOT/proof['manifest_path']
assert sha(p)==proof['manifest_sha256']
for name,h in json.loads(p.read_text()).items():
 q=Path(name);q=q if q.is_absolute() else ROOT/q
 assert sha(q)==h,name
run=ROOT/f['measurement']['run_directory']
for name,key in [('run_manifest.json','run_manifest_sha256'),('evidence.csv','evidence_csv_sha256'),('result.json','result_sha256')]:
 assert sha(run/name)==f['measurement'][key],name
print('PASS: exact DEVELOPMENT reproduction freeze; known has_api limitation retained; not official-ready')
