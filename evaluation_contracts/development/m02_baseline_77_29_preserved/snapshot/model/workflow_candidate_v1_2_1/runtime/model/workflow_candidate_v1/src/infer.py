"""Raw CSV inference entry point: execution manifest and BU metadata are not accepted."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from .data import read_csv,sanitize_raw,time_of
from .neural import load_model,predict,seed_all
from .analysis import segments,represent,cluster,process_maps
from .adapter import canonical_for_generator


def infer_csv(path, artifacts):
    config=json.loads((Path(artifacts)/'model_config.json').read_text())
    seed_all(config['seed'])
    streams=defaultdict(list)
    for r in read_csv(path):
        e=sanitize_raw(r,'raw_input')
        streams[e['session_id']].append(e)
    streams=[sorted(v,key=lambda e:(time_of(e),e['event_id'])) for _,v in sorted(streams.items())]
    if sum(map(len,streams))<2:raise ValueError('At least two raw events required')
    model=load_model(Path(artifacts)/'model.pt',config)
    predictions=predict(model,streams,config)
    cuts=[p>=config['boundary_threshold'] for p,_ in predictions]
    workflows=segments(streams,cuts,[p for p,_ in predictions])
    embeddings,_=represent(workflows,streams,[h for _,h in predictions],config)
    if len(workflows)>1:
        labels,diagnostic=cluster(embeddings,config)
    else:
        import numpy as np
        labels=np.zeros(1,dtype=int);diagnostic={'cluster_count':1,'silhouette':None,'dbi':None}
    tables=process_maps(workflows,labels,streams,embeddings)
    return dict(mode='DEVELOPMENT',workflows=workflows,clustering=diagnostic,
                canonical=[canonical_for_generator(tables,p['process_model_id']) for p in tables['process_models']],tables=tables)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--events',required=True);p.add_argument('--artifacts',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();Path(args.output).write_text(json.dumps(infer_csv(args.events,args.artifacts),ensure_ascii=False,indent=2)+'\n')
