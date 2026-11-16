from pathlib import Path
import sys,json,csv,hashlib,urllib.request
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT));OUT=Path(__file__).parent
from backend.m03_integration import evaluate_scenarios
from backend.evaluators import csv_evidence
from jsonschema import Draft202012Validator
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
assert not (OUT/'scenarios.json').exists(),'Do not rerun generation batch'
cp=ROOT/'docs/agents/m03_final_10_candidate_20261112/M03_FINAL_10_CANDIDATE.json'
assert sha(cp)=='c3351712b13e482389b5b3c55238a107f48ced502fd1d6f7053c3f3753c5545a'
c=json.loads(cp.read_text());assert len(c['selection'])==10
protected=dict(c['source_sha256'])
# Only approved MENU_ENTER generator changed; candidate/source/config remain frozen.
protected['backend/m03_real_generator.py']=sha(ROOT/'backend/m03_real_generator.py')
for p in ['evaluation_contracts/m03-scenario.schema.json','backend/evaluators.py','backend/external_results.py']:
 protected[p]=sha(ROOT/p)
for p,h in protected.items():assert sha(ROOT/p)==h,p
save('pre_run_manifest.json',dict(started_at=datetime.now(timezone.utc).isoformat(),candidate_sha256=sha(cp),protected_sha256=protected,run_mode='DEVELOPMENT',single_generation_batch=True,limitations=c['scope_limits'][:2]))
schema=json.loads((ROOT/'evaluation_contracts/m03-scenario.schema.json').read_text());validator=Draft202012Validator(schema)
from backend.server import Service, make_handler
from http.server import ThreadingHTTPServer
import threading
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Service(ROOT)))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base_url='http://127.0.0.1:'+str(server.server_port)
rows=[];audits=[]
for item in c['selection']:
 req=dict(business_unit_id=item['business_unit_id'],workflow_id=item['mapping']['workflow_id'],generator_mode='REAL',run_mode='DEVELOPMENT')
 request=urllib.request.Request(base_url+'/api/m03/generate',data=json.dumps(req).encode(),headers={'Content-Type':'application/json','Origin':base_url})
 started=datetime.now(timezone.utc).isoformat()
 with urllib.request.urlopen(request) as response:status=response.status;row=json.load(response)
 rows.append(row);save(item['business_unit_id']+'-api.json',dict(request=req,http_status=status,response=row,started_at=started,completed_at=datetime.now(timezone.utc).isoformat()))
 errors=[e.message for e in validator.iter_errors(row)]
 audits.append(dict(business_unit_id=item['business_unit_id'],name=item['name'],workflow_id=req['workflow_id'],source_process_id=item['mapping']['source_process_id'],scenario_id=row['scenario_id'],generated_steps=len(row['steps']),json_schema_valid=not errors,json_schema_errors=errors,required_fields_present=all(k in row for k in schema['required']) and all(all(k in s for k in ['order','action','target']) for s in row['steps']),generator_status=row['status'],issues=row.get('issues',[]),source_scope='MIXED' if item['mapping']['source_event_ids_outside_execution_window'] else 'SINGLE_EXECUTION_WINDOW',execution_status=item['source_execution_status'],input_limitations=item['issues']))
server.shutdown();server.server_close();thread.join()
save('scenarios.json',rows)
score,count,details,evidence=evaluate_scenarios(dict(run_mode='DEVELOPMENT',scenarios=rows))
for a,e in zip(audits,evidence):a.update(e);a['overall']='PASS' if e['success'] else 'FAIL'
(OUT/'evidence.csv').write_text(csv_evidence(evidence));(OUT/'case_audit.csv').write_text(csv_evidence(audits));save('case_audit.json',audits)
save('result.json',dict(status='DEVELOPMENT_PASS' if score>=80 else 'DEVELOPMENT_FAIL',candidate_id=c['candidate_id'],score=score,count=count,target=80,threshold_met=score>=80,official_pass=None,details=details,evidence=evidence,limitations=['Frozen candidate cohort, NOT historical 6/10 cohort.','BU01/BU12 execution end ambiguous; BU03 full frozen workflow mixes BU02/03. Not official-ready.','Generation used live HTTP API. Evaluation used unchanged central evaluate_scenarios; UI not changed or clicked. No registered dataset/config changes or integration-store submission.']))
for p,h in protected.items():assert sha(ROOT/p)==h,p
assert sha(cp)=='c3351712b13e482389b5b3c55238a107f48ced502fd1d6f7053c3f3753c5545a'
save('manifest.json',dict(completed_at=datetime.now(timezone.utc).isoformat(),candidate_sha256=sha(cp),protected_sha256=protected,protected_unchanged=True,output_sha256={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json'}))
print(json.dumps(dict(score=score,count=count,details=details,cases=[{k:a[k] for k in ['business_unit_id','generated_steps','schema_valid','step_order_valid','action_present','target_present','overall','issues']} for a in audits]),ensure_ascii=False,indent=2))
