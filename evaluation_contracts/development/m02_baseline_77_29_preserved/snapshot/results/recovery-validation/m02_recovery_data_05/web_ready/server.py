"""Read-only, loopback DEVELOPMENT presentation adapter; frozen evaluator reused unchanged."""
from pathlib import Path
import sys,json,hashlib,math,argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
from backend.m02_user_confirmed_comparator import evaluate
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
def verify():
 post=read(OUT/'postrun_manifest.json'); frozen=ROOT/'evaluation_contracts/development/m02_generic_preservation_v3_r2'
 assert sha(frozen/'manifest.json')==post['frozen_manifest_sha256']
 for p,h in read(frozen/'manifest.json')['sha256'].items():assert sha(ROOT/p)==h,p
 for p,h in post['artifact_sha256'].items():assert sha(OUT/p)==h,p
 for p,h in read(OUT/'cohort_manifest.json')['source_sha256'].items():assert sha(ROOT/p)==h,p
 return post

def measure():
 verify();base=read(ROOT/'evaluation_contracts/development/m02_recovery_rules_v1/manifest.json');truth=read(ROOT/base['td04']);roles=read(ROOT/base['roles']);cohort=read(OUT/'cohort_manifest.json')['executions'];rows=[]
 assert len(cohort)==5 and {e['business_unit_id'] for e in cohort}=={'BU03','BU07','BU09','BU17','BU20'}
 for ex in cohort:
  bu=ex['business_unit_id'];prefix='05' if bu=='BU09' else '03' if bu=='BU03' else '01';sc=read(OUT/(prefix+'_scope.json'))
  selected=[s for p in sc['processes'] if p['id']==bu for s in p['procedures'] if s['execution_ids']==[ex['execution_id']]]
  _,_,stats,ev=evaluate({'processes':[{'id':bu,'procedures':selected}]},dict(truth,processes=[p for p in truth['processes'] if p['id']==bu]),dict(roles,processes=[p for p in roles['processes'] if p['id']==bu]))
  rows.append(dict(stats['per_business_unit'][0],missing=[e['ground_truth_step'] for e in ev if not e['required_included']]))
 g=sum(x['generated_count'] for x in rows);m=sum(x['matched_count'] for x in rows);s=sum(x['included_required_count'] for x in rows);q=sum(x['required_count'] for x in rows);a=100*m/g;c=100*s/q
 result=dict(mode='DEVELOPMENT',official_pass=None,dataset='m02_recovery_data_05 exact-five cohort',execution_count=5,method='Frozen process maps re-evaluated; no model inference or tuning',per_business_unit=rows,overall=dict(generated=g,matched=m,satisfied=s,required=q,accuracy=a,completeness=c,score=math.sqrt(a*c),target=75,target_met=math.sqrt(a*c)>=75),evidence_sha256=sha(OUT/'evidence.csv'))
 old=read(OUT/'result.json')['overall']
 for k in ('generated','matched','satisfied','required','accuracy','completeness','score'):assert abs(result['overall'][k]-old[k])<1e-10,k
 return result
class Handler(BaseHTTPRequestHandler):
 def reply(self,status,data,kind):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  try:
   if self.path=='/':return self.reply(200,(HERE/'index.html').read_bytes(),'text/html; charset=utf-8')
   if self.path=='/api/result':verify();return self.reply(200,json.dumps(read(OUT/'result.json')).encode(),'application/json')
   if self.path=='/evidence.csv':verify();return self.reply(200,(OUT/'evidence.csv').read_bytes(),'text/csv; charset=utf-8')
   self.reply(404,b'Not found','text/plain')
  except Exception as e:self.reply(409,json.dumps({'error':str(e)}).encode(),'application/json')
 def do_POST(self):
  if self.path!='/api/measure':return self.reply(404,b'Not found','text/plain')
  if self.headers.get('Content-Type')!='application/json':return self.reply(415,b'JSON required','text/plain')
  try:self.reply(200,json.dumps(measure(),ensure_ascii=False).encode(),'application/json; charset=utf-8')
  except Exception as e:self.reply(409,json.dumps({'error':str(e)}).encode(),'application/json')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8767);a=p.parse_args();verify();print('DEVELOPMENT read-only adapter: http://127.0.0.1:'+str(a.port),flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
