"""Freeze only an exact independently approved DEVELOPMENT recovery snapshot."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.evaluators import digest,read_json,require
from backend.m02_recovery_candidate import SNAPSHOT,CHECKS,verify
folder=ROOT/SNAPSHOT
manifest=read_json(folder/'manifest.json');gate=read_json(folder/'independent_verification.json')
require(manifest['run_mode']=='DEVELOPMENT','DEVELOPMENT only')
for path,h in manifest['sha256'].items():require(digest(ROOT/path)==h,'Changed dependency: '+path)
require(gate.get('verdict')=='PASS' and gate.get('snapshot_manifest_sha256')==digest(folder/'manifest.json') and all(gate.get(k)=='PASS' for k in CHECKS),'Independent PASS for exact snapshot required')
record=dict(status='FROZEN',snapshot_manifest_sha256=digest(folder/'manifest.json'),independent_verification_sha256=digest(folder/'independent_verification.json'),run_mode='DEVELOPMENT',score_computed=False)
(folder/'freeze.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
verify(ROOT)
print(json.dumps(record))
