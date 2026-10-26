"""Raw-event inference with inherited frozen boundary and selected hybrid representation."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from model.workflow_candidate_v1.src.data import read_csv,sanitize_raw,time_of,sha
from model.workflow_candidate_v1.src.neural import seed_all,load_model,predict
from model.workflow_candidate_v1.src.analysis import segments,represent,cluster,process_maps
from model.workflow_candidate_v1.src.adapter import canonical_for_generator
from .representation import components,combine


def infer_events(streams,artifacts):
    artifacts=Path(artifacts)
    selection=json.loads((artifacts/'selected_model.json').read_text())
    config=json.loads((artifacts/'representation_config.json').read_text())
    neural=json.loads((artifacts/'model_config.json').read_text())
    if sha(artifacts/'model.pt')!=selection['boundary_weights_sha256']:raise ValueError('Boundary checkpoint changed')
    seed_all(neural['seed']);model=load_model(artifacts/'model.pt',neural)
    output=predict(model,streams,neural)
    probs=[p for p,_ in output];hidden=[h for _,h in output]
    workflows=segments(streams,[p>=neural['boundary_threshold'] for p in probs],probs)
    if not workflows:raise ValueError('No raw events supplied')
    existing,_=represent(workflows,streams,hidden,neural)
    blocks,signatures=components(workflows,streams,hidden,existing,config)
    embedding=combine(blocks,config['candidates'][selection['candidate']])
    if len(workflows)>1:labels,diagnostic=cluster(embedding,dict(neural,cluster_distance_thresholds=config['cluster_distance_thresholds']))
    else:labels=np.zeros(1,dtype=int);diagnostic={'selected':{'cluster_count':1,'silhouette':None,'dbi':None}}
    tables=process_maps(workflows,labels,streams,embedding)
    return dict(mode='DEVELOPMENT',candidate=selection['candidate'],workflows=workflows,cluster_labels=labels.tolist(),clustering=diagnostic,tables=tables,
                canonical=[canonical_for_generator(tables,p['process_model_id']) for p in tables['process_models']])


def infer_csv(path,artifacts):
    streams=defaultdict(list)
    for row in read_csv(path):
        e=sanitize_raw(row,'raw_input');streams[e['session_id']].append(e)
    return infer_events([sorted(v,key=lambda e:(time_of(e),e['event_id'])) for _,v in sorted(streams.items())],artifacts)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--events',required=True);parser.add_argument('--artifacts',default=str(Path(__file__).resolve().parents[1]/'artifacts'));parser.add_argument('--output',required=True)
    args=parser.parse_args();Path(args.output).write_text(json.dumps(infer_csv(args.events,args.artifacts),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
