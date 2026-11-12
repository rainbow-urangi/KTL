"""Run only after a separate verifier writes PASS for the exact manifest hash."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.m02_user_confirmed_candidate import run
if __name__=='__main__':
 print(json.dumps(run(ROOT,json.loads((ROOT/'backend/config.json').read_text())),ensure_ascii=False,indent=2))
