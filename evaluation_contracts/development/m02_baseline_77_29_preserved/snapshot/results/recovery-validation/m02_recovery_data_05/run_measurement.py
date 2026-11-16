from pathlib import Path
import json,csv,hashlib,math,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT));OUT=Path(__file__).parent
from backend.m02_recovery_candidate import generate
from backend.m02_user_confirmed_comparator import evaluate
from backend.evaluators import csv_evidence
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
folder=ROOT/'evaluation_contracts/development/m02_generic_preservation_v3_r2';m=json.loads((folder/'manifest.json').read_text());gate=json.loads((folder/'independent_verification.json').read_text());freeze=json.loads((folder/'freeze.json').read_text())
def verify():
 assert gate['verdict']=='PASS' and gate['snapshot_manifest_sha256']==sha(folder/'manifest.json')==freeze['snapshot_manifest_sha256']
 assert freeze['independent_verification_sha256']==sha(folder/'independent_verification.json')
 for p,h in m['sha256'].items():assert sha(ROOT/p)==h,p
verify();base=json.loads((ROOT/'evaluation_contracts/development/m02_recovery_rules_v1/manifest.json').read_text())
raw=list(csv.DictReader((ROOT/'data/development/m02_recovery_data_04/events.csv').open()));byid={int(r['id']):r for r in raw}
ex03=[]
for xid,bu,a,b in [('04-BU03','BU03',90960,90980)]:
 ex03.append(dict(execution_id=xid,business_unit_id=bu,session_id=byid[a]['session_id'],start_event_id=byid[a]['event_id'],end_event_id=byid[b]['event_id'],start_raw_id=a,end_raw_id=b,source='RAW_ONLY chronological lifecycle; one execution each identified by explicit menu and popup lifecycle; no model/GT prediction',menu_reentry_observed=True))
save('execution_manifest04.json',ex03)
manifest03=dict(base,raw_events='data/development/m02_recovery_data_04/events.csv',predictions='results/recovery-validation/m02_generic_preservation_v3_r2/predictions04.json',execution_manifest=str((OUT/'execution_manifest04.json').relative_to(ROOT)))
sc03,art03=generate(ROOT,manifest03);sc01,art01=generate(ROOT,base)
for prefix,artifacts in [('03',art03),('01',art01)]:
 for name,obj in artifacts.items():save(prefix+'_'+name,obj)
raw05=list(csv.DictReader((ROOT/'data/development/m02_recovery_data_05/events.csv').open()));by05={int(r['id']):r for r in raw05}
ex05=[dict(execution_id='05-BU09',business_unit_id='BU09',session_id=by05[91091]['session_id'],start_event_id=by05[91091]['event_id'],end_event_id=by05[91123]['event_id'],start_raw_id=91091,end_raw_id=91123,source='RAW_ONLY: upper menu to page close, single weekly registration/save lifecycle; no model/GT prediction',menu_reentry_observed=True)]
save('execution_manifest05.json',ex05)
manifest05=dict(base,raw_events='data/development/m02_recovery_data_05/events.csv',predictions=str((OUT/'predictions05.json').relative_to(ROOT)),execution_manifest=str((OUT/'execution_manifest05.json').relative_to(ROOT)))
sc05,art05=generate(ROOT,manifest05)
for name,obj in art05.items():save('05_'+name,obj)
save('cohort_manifest.json',dict(mode='DEVELOPMENT',executions=ex03+ex05+[x for x in json.loads((ROOT/base['execution_manifest']).read_text()) if x['business_unit_id'] in ('BU07','BU17','BU20')],source_sha256={str(f.relative_to(ROOT)):sha(f) for d in ('01','04','05') for f in (ROOT/('data/development/m02_recovery_data_'+d)).iterdir() if f.is_file()},frozen_manifest_sha256=sha(folder/'manifest.json')))
# Read GT only after full frozen generation. Evaluate every repetition independently.
truth=json.loads((ROOT/base['td04']).read_text());roles=json.loads((ROOT/base['roles']).read_text())
allresults=[];allrows=[]
for dataset,scope,executions in [('m02_recovery_data_05',sc05,ex05),('m02_recovery_data_04',sc03,ex03),('m02_recovery_data_01',sc01,json.loads((ROOT/base['execution_manifest']).read_text()))]:
 for ex in executions:
  bu=ex['business_unit_id'];xid=ex['execution_id']
  if dataset.endswith('01') and bu not in ('BU07','BU17','BU20'):continue
  selected=[]
  for p in scope['processes']:
   if p['id']==bu:selected=[s for s in p['procedures'] if s['execution_ids']==[xid]]
  generated=dict(processes=[dict(id=bu,procedures=selected)])
  t=dict(truth,processes=[p for p in truth['processes'] if p['id']==bu]);r=dict(roles,processes=[p for p in roles['processes'] if p['id']==bu])
  score,count,stats,evidence=evaluate(generated,t,r)
  summary=dict(stats['per_business_unit'][0],dataset=dataset,execution_id=xid,missing=[e['ground_truth_step'] for e in evidence if not e['required_included']],week_selection_status='Actual date-picker selection with verified weekly registration context; original intent chronology preserved' if bu=='BU09' else None)
  allresults.append(summary);save(xid+'_result.json',dict(summary=summary,stats=stats,evidence=evidence));allrows += [dict(row_type='required_step',dataset=dataset,execution_id=xid,**e) for e in evidence]
  allrows += [dict(row_type='generated_step',dataset=dataset,execution_id=xid,**s) for s in selected]
def aggregate(xs):
 g=sum(x['generated_count'] for x in xs);c=sum(x['matched_count'] for x in xs);s=sum(x['included_required_count'] for x in xs);q=sum(x['required_count'] for x in xs);a=100*c/g;co=100*s/q
 return dict(generated=g,matched=c,satisfied=s,required=q,accuracy=a,completeness=co,score=math.sqrt(a*co),target_met=math.sqrt(a*co)>=75)
summary=dict(status='DEVELOPMENT_EXACT_FIVE_EXECUTIONS_NOT_OFFICIAL',scope='Recovery04 BU03, recovery05 BU09, recovery01 BU07/BU17/BU20 exactly one execution each; prior BU09 excluded; no best-instance choice',per_execution=allresults,per_business_unit={bu:aggregate([x for x in allresults if x['business_unit_id']==bu]) for bu in ('BU03','BU07','BU09','BU17','BU20')},overall=aggregate(allresults),excluded_from_task_scope=[dict(dataset='m02_recovery_data_04',source='raw rows90949-90959',reason='login prelude, retained in model input and generated scope audit'),dict(dataset='m02_recovery_data_05',source='raw rows91087-91090',reason='boot/page/API prelude before first menu; preserved in full model input and generated scope audit')],scope05=sc05['scope_summary'],scope03=sc03['scope_summary'],scope01=sc01['scope_summary'])
save('result.json',summary);allrows += [dict(row_type='execution_summary',**x) for x in allresults];allrows.append(dict(row_type='aggregate',**summary['overall']));(OUT/'evidence.csv').write_text(csv_evidence(allrows))
verify();save('postrun_manifest.json',dict(frozen_dependencies_unchanged=True,frozen_manifest_sha256=sha(folder/'manifest.json'),freeze_sha256=sha(folder/'freeze.json'),artifact_sha256={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='postrun_manifest.json'}));print(json.dumps(summary,ensure_ascii=False,indent=2))
