"""Copy verified native output; bind current shared execution without measuring."""
from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.m02_integrated_candidate import SNAPSHOT,runtime_inventory,REQUIRED_DEPENDENCIES
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 source=ROOT/'evaluation_contracts/development/m02_track_a_native_submit_v1'
 assert sha(source/'manifest.json')=='f3447df9f978496014cd1fed57b8973b0a1e49f78e3f03687b1fe346a2ba53b7'
 m=json.loads((source/'manifest.json').read_text());hashes=dict(m['input_code_sha256'])
 for n,h in hashes.items():
  p=Path(n) if Path(n).is_absolute() else ROOT/n
  assert sha(p)==h,n
 for n,h in m['outputs'].items():assert sha(source/n)==h,n
 out=ROOT/SNAPSHOT;out.mkdir(exist_ok=False)
 for n in m['outputs']:shutil.copyfile(source/n,out/n)
 inventory=runtime_inventory(ROOT)
 for n in inventory+['scripts/freeze_m02_shared_integration.py']:
  hashes[n]=sha(ROOT/n)
 report=Path('/Users/sooeunkim/Documents/Codex/2026-11-05/task-4/TRACK_A_M02_RECOVERY_01_INDEPENDENT_VERIFICATION.txt')
 hashes[str(report)]=sha(report);hashes[str(source/'manifest.json')]=sha(source/'manifest.json')
 # Freeze all development input bundles, including M06/M03 configured sources.
 for p in (ROOT/'data/development/current_site_unseen_validation_v1').rglob('*'):
  if p.is_file():hashes[str(p.relative_to(ROOT))]=sha(p)
 for key,item in m['generated_artifacts'].items():
  item['path']=SNAPSHOT+'/'+Path(item['path']).name
  hashes[item['path']]=sha(ROOT/item['path'])
 m.update(input_code_sha256=hashes,runtime_inventory=inventory,comparison_dependencies=sorted(set(inventory)|set(REQUIRED_DEPENDENCIES)),shared_web_integration_pending=True,
  isolated_producer_manifest_sha256=sha(source/'manifest.json'),isolated_review_sha256=sha(report),
  remaining_definition_items=17,remaining_raw_evidence_gaps=3,integration_verification='PENDING',score_computed=False)
 (out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 print(sha(out/'manifest.json'))
if __name__=='__main__':main()
