"""Read-only integrity validation. No generator/evaluator/model execution."""
from pathlib import Path
import hashlib,json
here=Path(__file__).resolve().parent
root=here.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path=here/'freeze_manifest.json'
assert sha(manifest_path)==(here/'freeze_manifest.sha256').read_text().split()[0]
m=json.loads(manifest_path.read_text())
for name,expected in m['sha256'].items():
    assert sha(root/name)==expected,name
assert len(m['candidate_ids'])==10 and len(set(m['candidate_ids']))==10
assert m['result']==dict(success=9,failure=1,total=10,success_rate=90.0,target=80.0)
print(json.dumps(dict(status='PASS',checked_files=len(m['sha256']),freeze_id=m['freeze_id'],manifest_sha256=sha(manifest_path))))
