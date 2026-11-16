"""Hash-verified inference launcher. Never accepts execution GT as a separate input."""
import pathlib,json,hashlib,subprocess,sys,argparse
base=pathlib.Path(__file__).resolve().parent
m=json.loads((base/'VALIDATION_CANDIDATE_MANIFEST.json').read_text())
for rel,digest in m['file_sha256'].items():
    if hashlib.sha256((base/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen candidate hash mismatch: '+rel)
p=argparse.ArgumentParser();p.add_argument('--events',required=True);p.add_argument('--output',required=True);a=p.parse_args()
subprocess.run([sys.executable,'-B','-m','model.workflow_candidate_v1_2.src.infer','--events',str(pathlib.Path(a.events).resolve()),'--artifacts',str(base/'artifacts'),'--output',str(pathlib.Path(a.output).resolve())],cwd=base/'runtime',check=True)
