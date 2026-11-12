"""Freeze boundary, run all label-free clustering, then run post-hoc audits."""
import csv
import json
import platform
import shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import torch
import sklearn
from sklearn.metrics import adjusted_rand_score
from model.workflow_candidate_v1.src.data import read_csv,sha,load_logical,boundary_labels
from model.workflow_candidate_v1.src.neural import seed_all,load_model,predict
from model.workflow_candidate_v1.src.analysis import represent,segments,cluster,process_maps,boundary_metrics,segmentation_metrics
from model.workflow_candidate_v1.training.run import split_data
from .representation import components,combine
from .audit import business_summary,process_audit
from .report import create_report

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
V1=ROOT/'model/workflow_candidate_v1'

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['status']);writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})

def protected_hashes():
    paths=[]
    for directory in ['model/workflow_candidate_v1','model/v6_2','data','backend','frontend','evaluation_contracts']:
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.name!='.DS_Store')
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}

def main():
    protected=protected_hashes()
    cfg=json.loads((BASE/'config/representation.json').read_text())
    neural_cfg=json.loads((V1/'artifacts/model_config.json').read_text())
    manifest=json.loads((V1/'artifacts/model_manifest.json').read_text())
    for f,h in manifest['artifact_sha256'].items():assert sha(V1/'artifacts'/f)==h
    for f,h in manifest['source_sha256'].items():assert sha(V1/f)==h
    streams,metadata,dataset=load_logical(ROOT,ROOT/'data/development/current_site_20x3_v3')
    seed_all(neural_cfg['seed'])
    model=load_model(V1/'artifacts/model.pt',neural_cfg)
    outputs=predict(model,streams,neural_cfg)
    probabilities=[p for p,_ in outputs];hidden=[h for _,h in outputs]
    cuts=[p>=neural_cfg['boundary_threshold'] for p in probabilities]
    workflows=segments(streams,cuts,probabilities)
    old_wf=read_csv(V1/'diagnostics/predicted_workflows.csv')
    assert len(workflows)==len(old_wf)==61
    for new,old in zip(workflows,old_wf):
        for k in ['workflow_instance_id','start_event_id','end_event_id','start_time','end_time','source_dataset','source_session_id']:assert new[k]==old[k]
        for k in ['stream_index','begin','end','event_count']:assert new[k]==int(old[k])
        assert new['source_event_evidence']==json.loads(old['source_event_evidence'])
    old_preds={(r['source_dataset'],r['event_id']):r for r in read_csv(V1/'diagnostics/neural_boundary_predictions.csv')}
    assert sum(map(len,streams))==len(old_preds)
    for stream,prob,pred in zip(streams,probabilities,cuts):
        for e,p,cut in zip(stream,prob,pred):
            old=old_preds[(e['source_dataset'],e['event_id'])]
            assert float(p)==float(old['probability']) and bool(cut)==(old['predicted_boundary']=='True')
    existing,unused=represent(workflows,streams,hidden,neural_cfg)
    saved=read_csv(V1/'diagnostics/workflow_embeddings.csv')
    reference=np.asarray([[float(row[f'dim_{j:03}']) for j in range(existing.shape[1])] for row in saved],dtype=np.float32)
    np.testing.assert_array_equal(existing,reference)
    blocks,evidence=components(workflows,streams,hidden,existing,cfg)
    write(BASE/'diagnostics/structural_signatures.csv',evidence)
    runs={};cluster_cfg=dict(neural_cfg,cluster_distance_thresholds=cfg['cluster_distance_thresholds'])
    # No business metadata is inspected anywhere in this loop.
    for name,weights in cfg['candidates'].items():
        x=combine(blocks,weights);labels,diagnostic=cluster(x,cluster_cfg)
        repeat,repeat_diagnostic=cluster(x.copy(),cluster_cfg)
        assert np.array_equal(labels,repeat) and diagnostic==repeat_diagnostic
        rng=np.random.RandomState(neural_cfg['seed']);perm=rng.permutation(len(x))
        permuted,_=cluster(x[perm],cluster_cfg);restored=np.empty_like(permuted);restored[perm]=permuted
        stability=float(adjusted_rand_score(labels,restored))
        tables=process_maps(workflows,labels,streams,x)
        runs[name]=dict(embeddings=x,labels=labels,diagnostic=diagnostic,tables=tables,permutation_ari=stability)
        directory=BASE/'diagnostics'/name
        dump(directory/'clustering_diagnostics.json',diagnostic)
        write(directory/'workflow_embeddings.csv',[dict(workflow_instance_id=w['workflow_instance_id'],**{f'dim_{j:04}':float(v) for j,v in enumerate(vector)}) for w,vector in zip(workflows,x)])
        write(directory/'cluster_assignments.csv',[dict(workflow_instance_id=w['workflow_instance_id'],cluster_id=int(c)) for w,c in zip(workflows,labels)])
        for table,rows in tables.items():write(directory/(table+'.csv'),rows)
        print('Clustering complete:',name,'clusters',diagnostic['selected']['cluster_count'],flush=True)
    dump(BASE/'diagnostics/clustering_stage_manifest.json',dict(all_candidates_completed_before_posthoc=True,configuration_sha256=sha(BASE/'config/representation.json'),inputs=['raw structural fields','frozen GRU hidden states','v1 existing embeddings'],business_labels_used=False,files={name:{f:sha(BASE/'diagnostics'/name/f) for f in ['cluster_assignments.csv','workflow_embeddings.csv','clustering_diagnostics.json']} for name in runs}))
    # Frozen v1 assignment is a comparison, not a new clustering selection.
    old_labels=np.array([int(r['cluster_id']) for r in read_csv(V1/'diagnostics/cluster_assignments.csv')])
    old_diagnostic=json.loads((V1/'diagnostics/clustering_diagnostics.json').read_text())
    runs={'v1':dict(embeddings=existing,labels=old_labels,diagnostic=old_diagnostic,tables=process_maps(workflows,old_labels,streams,existing),permutation_ari=None),**runs}
    summaries=[]
    for name,run in runs.items():
        business=business_summary(workflows,run['labels'],streams,metadata)
        audit=process_audit(run['tables'],workflows,streams,metadata)
        directory=BASE/'diagnostics'/name
        dump(directory/'business_evaluation.json',business)
        dump(directory/'process_map_audit.json',audit)
        write(directory/'observed_variants.csv',audit['variants'])
        selected=run['diagnostic']['selected']
        row=dict(candidate=name,embedding_dimension=run['embeddings'].shape[1],cluster_count=selected['cluster_count'],silhouette=selected.get('silhouette'),dbi=selected.get('dbi'),threshold=selected.get('threshold'),
                 bu_consistency=business['same_bu_three_repetitions_consistent'],cluster_purity=business['overall_event_weighted_purity'],merged_bu_pairs=business['merged_bu_pairs'],fragmented_bus=business['fragmented_bus'],primary_fragmented_bus=business['primary_fragmented_bus'],
                 A_process_models=audit['summary']['A_models'],B_process_models=audit['summary']['B_models'],cross_business_method_collision_nodes=audit['summary']['cross_business_method_collision_nodes'],cross_business_unobserved_triples=audit['summary']['cross_business_unobserved_triples'],all_read_write_collision_nodes=audit['summary']['all_read_write_collision_nodes'],permutation_ari=run['permutation_ari'])
        summaries.append(row)
        run.update(business=business,audit=audit)
    labels=[boundary_labels(s,metadata) for s in streams]
    _,holdout=split_data(streams,metadata,labels,lambda r:r['repetition']=='3')
    boundary=boundary_metrics(labels,cuts,holdout,neural_cfg['boundary_tolerance_events'])
    segmentation=segmentation_metrics(workflows,streams,metadata)
    old_eval=json.loads((V1/'diagnostics/development_evaluation.json').read_text())
    assert boundary==old_eval['boundary']['neural']['internal_holdout']['tolerant']
    assert segmentation==old_eval['boundary']['neural']['segmentation']
    dump(BASE/'diagnostics/boundary_verification.json',dict(unchanged_probabilities=True,unchanged_workflow_membership=True,unchanged_existing_embedding=True,model_sha256=sha(V1/'artifacts/model.pt'),holdout=boundary,segmentation=segmentation,holdout_notice='INTERNAL DEVELOPMENT HOLDOUT; NOT INDEPENDENT UNSEEN VALIDATION'))
    write(BASE/'diagnostics/candidate_comparison.csv',summaries)
    pair_rows=[]
    for pair in runs['v1']['business']['merged_bu_pair_list']:
        a,b=pair;row={'business_a':a,'business_b':b}
        for name,run in runs.items():
            row[name+'_any_event_merge']=pair in run['business']['merged_bu_pair_list']
            detail=next(p for p in run['business']['confusion_pairs'] if p['business_a']==a and p['business_b']==b)
            row[name+'_primary_pair_collisions']=detail['same_cluster_execution_pairs']
        pair_rows.append(row)
    write(BASE/'diagnostics/v1_confused_pairs_comparison.csv',pair_rows)
    for filename in ['model.pt','model_config.json','preprocessing_config.json','normalization_config.json']:
        shutil.copyfile(V1/'artifacts'/filename,BASE/'artifacts'/filename)
    for filename in ['predicted_workflows.csv','neural_boundary_predictions.csv']:
        shutil.copyfile(V1/'diagnostics'/filename,BASE/'diagnostics'/filename)
    shutil.copyfile(BASE/'config/representation.json',BASE/'artifacts/representation_config.json')
    dump(BASE/'artifacts/selected_model.json',dict(candidate='C_full',boundary_weights_sha256=sha(BASE/'artifacts/model.pt'),selection_review='../diagnostics/selection_review.json'))
    create_report(BASE,summaries,boundary,segmentation,runs)
    assert protected==protected_hashes(),'Protected originals changed'
    dump(BASE/'diagnostics/protected_files_verification.json',dict(unchanged=True,sha256=protected))
    dump(BASE/'artifacts/experiment_manifest.json',dict(mode='DEVELOPMENT',official=False,trained=False,created_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),dataset=dataset['dataset_id'],dataset_manifest_sha256=sha(ROOT/'data/development/current_site_20x3_v3/dataset_manifest.json'),boundary_parent='workflow_candidate_v1',boundary_weights_sha256=sha(BASE/'artifacts/model.pt'),configuration=cfg,python=platform.python_version(),pytorch=torch.__version__,numpy=np.__version__,sklearn=sklearn.__version__,code_sha256={str(p.relative_to(BASE)):sha(p) for p in (BASE/'src').glob('*.py')},immutable_v1_code_sha256={str(p.relative_to(ROOT)):sha(p) for p in (V1/'src').glob('*.py')},artifacts_sha256={p.name:sha(p) for p in (BASE/'artifacts').glob('*') if p.is_file() and p.name not in ('experiment_manifest.json','model_manifest.json')}))
    dump(BASE/'artifacts/model_manifest.json',dict(model_id='workflow_candidate_v1_1',selected_candidate='C_full',mode='DEVELOPMENT',official=False,trained=False,embedding_dimension=1152,
        boundary_architecture='Unchanged v1 GRU',boundary_parent='workflow_candidate_v1',weights=cfg['candidates']['C_full'],
        artifact_sha256={p.name:sha(p) for p in (BASE/'artifacts').glob('*') if p.is_file() and p.name!='model_manifest.json'},
        code_sha256={str(p.relative_to(BASE)):sha(p) for sub in ['src','tests'] for p in (BASE/sub).glob('*.py')}))
    print(json.dumps(summaries,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
