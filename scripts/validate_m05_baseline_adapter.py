"""DEVELOPMENT functional equivalence, not held-out selection or scoring."""
import csv, hashlib, json, sys, subprocess
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'AI-model'))
from dataset import rle_dedupe_rows
from adapters.csv_adapter import read_standard_rows, _timestamp_sort_key, STANDARD_FIELDS
from backend.m05_baseline_adapter import load_rules,predict
from backend.m05_heldout import validate_engine
OUT=ROOT/'results/development/m05_baseline_adapter_candidate'
CFG=ROOT/'evaluation_contracts/development/m05_baseline_adapter_candidate'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    rules,_=load_rules(CFG/'rules.json')
    engine=json.loads((CFG/'engine.json').read_text());argv=validate_engine(ROOT,engine)
    summary={'scope':'DEVELOPMENT_FUNCTIONAL_ONLY','score':None,'held_out_created':False,'datasets':[]}
    for name in ('current_site_dev_01','current_site_dev_02'):
        path=ROOT/'data/evaluation'/name/'events.csv'
        with path.open() as f: headers=next(csv.reader(f))
        mapping={k:k for k in STANDARD_FIELDS if k in headers}
        mapping.update(case_id='task_id',source_event_pk='event_id',ts='event_time')
        rows=read_standard_rows(str(path),mapping)
        assert all(r['case_id'] is not None and r['source_event_pk'] for r in rows)
        events=[{'id':r['source_event_pk'],'features':{k:r[k] for k in ('activity','case_id','ts')}} for r in rows]
        result=predict(events,rules);assert result==predict(events,rules)
        wire=subprocess.run(argv,input=json.dumps({'events':events}),text=True,capture_output=True,check=True)
        assert json.loads(wire.stdout)==result
        grouped={}
        for r in rows:grouped.setdefault(r['case_id'],[]).append(r)
        expected=set()
        for rs in grouped.values():
            rs.sort(key=_timestamp_sort_key)
            expected.update(r['source_event_pk'] for r in rle_dedupe_rows(rs))
        assert expected=={p['id'] for p in result['predictions'] if p['label']=='KEEP'}
        assert [r['source_event_pk'] for r in rows]==[p['id'] for p in result['predictions']]
        out=OUT/(name+'_predictions.csv')
        with out.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(result['predictions'][0])+['source_csv','source_sha256'])
            w.writeheader();w.writerows(dict(p,source_csv=str(path.relative_to(ROOT)),source_sha256=sha(path)) for p in result['predictions'])
        summary['datasets'].append({'dataset':name,'source_sha256':sha(path),'events':len(rows),'labels':dict(Counter(p['label'] for p in result['predictions'])),'reasons':dict(Counter(p['remove_reason'] for p in result['predictions'] if p['label']=='REMOVE')),'cases':len(grouped),'mapping':mapping,'existing_engine_equivalence':True,'deterministic':True,'event_id_provenance':True,'cli_contract':True,'prediction_sha256':sha(out)})
    summary['original_dataset_sha256']=sha(ROOT.parent/'AI-model/dataset.py')
    assert summary['original_dataset_sha256']==sha(CFG/'dataset_original.py')
    (OUT/'functional_validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':run()
