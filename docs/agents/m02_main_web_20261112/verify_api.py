"""Explicitly authorized M02 API reproduction; no browser clicks."""
import csv,io,json,math,threading,urllib.request,hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer
from backend.server import Service,make_handler
from backend.m02_main_web import DATASET,FREEZE,OUTPUT
root=Path.cwd();out=root/'docs/agents/m02_main_web_20261112'
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Service(root)))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
try:
 with urllib.request.urlopen(urllib.request.Request(base+'/api/evaluations/m02/run?mode=DEVELOPMENT&dataset_id='+DATASET,method='POST'),timeout=150) as response:result=json.load(response)
 with urllib.request.urlopen(base+result['evidence_file']) as response:evidence=response.read()
 rows=list(csv.DictReader(io.StringIO(evidence.decode('utf-8-sig'))));required=[r for r in rows if r['row_type']=='required_step'];generated=[r for r in rows if r['row_type']=='generated_step'];matched=sum(r['direct_match']=='True' for r in required);satisfied=sum(r['required_included']=='True' for r in required)
 a=100*matched/len(generated);c=100*satisfied/len(required);score=math.sqrt(a*c)
 assert (len(generated),matched,satisfied,len(required))==(31,20,25,27)
 assert abs(result['score']-score)<1e-10
 assert abs(result['details']['accuracy']-a)<1e-10 and abs(result['details']['completeness']-c)<1e-10
 assert result['threshold_met'] is True
 assert evidence==(root/FREEZE/'snapshot'/OUTPUT/'evidence.csv').read_bytes()
 assert hashlib.sha256(evidence).hexdigest()==result['evidence_sha256']
 assert sum(len(b['generated_process']) for b in result['details']['per_business_unit'])==31
 with urllib.request.urlopen(base+result['result_file']) as response:assert json.load(response)==result
 (out/'api_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 (out/'api_evidence.csv').write_bytes(evidence)
 report=dict(status='PASS',run_id=result['run_id'],accuracy=a,completeness=c,score=score,counts=[31,20,25,27],evidence_sha256=result['evidence_sha256'],csv_recalculation='PASS',browser_click='NOT_PERFORMED_USER_OWNED',method=result['measurement_method'])
 (out/'api_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
finally:server.shutdown();server.server_close();thread.join()
