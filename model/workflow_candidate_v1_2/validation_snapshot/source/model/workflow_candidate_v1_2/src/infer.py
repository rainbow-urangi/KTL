"""Offline raw-event inference; business/execution labels are never inputs."""
import argparse,json
from pathlib import Path
from collections import defaultdict
import numpy as np
from model.workflow_candidate_v1.src.data import read_csv,sanitize_raw,time_of,sha
from model.workflow_candidate_v1.src.neural import seed_all,load_model as load_encoder,predict as encode
from model.workflow_candidate_v1.src.analysis import represent,segments,cluster
from model.workflow_candidate_v1_1.src.representation import components,combine
from .neural import load_model,predict
from .features import decisions
from .process_map import process_maps
from .adapter import canonical_for_generator


def infer_events(streams,artifacts):
    art=Path(artifacts);manifest=json.loads((art/'model_manifest.json').read_text())
    for name,digest in manifest['artifact_sha256'].items():
        if sha(art/name)!=digest:raise ValueError('Artifact hash mismatch: '+name)
    cfg=json.loads((art/'model_config.json').read_text());ecfg=json.loads((art/'representation_encoder_config.json').read_text());rcfg=json.loads((art/'representation_config.json').read_text())
    seed_all(cfg['seed']);out=predict(load_model(art/'model.pt',cfg),streams,cfg);probs=[p for p,_ in out]
    workflows=segments(streams,decisions(probs,streams,cfg),probs)
    if not workflows:raise ValueError('No events')
    hidden=[h for _,h in encode(load_encoder(art/'representation_encoder.pt',ecfg),streams,ecfg)]
    existing,_=represent(workflows,streams,hidden,ecfg);blocks,_=components(workflows,streams,hidden,existing,rcfg)
    x=combine(blocks,rcfg['candidates']['C_full'])
    if len(workflows)>1:labels,diagnostic=cluster(x,dict(ecfg,cluster_distance_thresholds=rcfg['cluster_distance_thresholds']))
    else:labels=np.zeros(1,dtype=int);diagnostic={'selected':{'cluster_count':1,'silhouette':None,'dbi':None}}
    tables=process_maps(workflows,labels,streams,x)
    return dict(mode='DEVELOPMENT',offline=True,workflows=workflows,cluster_labels=labels.tolist(),clustering=diagnostic,tables=tables,canonical=[canonical_for_generator(tables,p['process_model_id']) for p in tables['process_models']])

def infer_csv(path,artifacts):
    sessions=defaultdict(list)
    for raw in read_csv(path):
        e=sanitize_raw(raw,'raw_input');sessions[e['session_id']].append(e)
    return infer_events([sorted(ev,key=lambda e:(time_of(e),e['event_id'])) for _,ev in sorted(sessions.items())],artifacts)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--events',required=True);parser.add_argument('--artifacts',default=str(Path(__file__).resolve().parents[1]/'artifacts'));parser.add_argument('--output',required=True)
    args=parser.parse_args();Path(args.output).write_text(json.dumps(infer_csv(args.events,args.artifacts),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
