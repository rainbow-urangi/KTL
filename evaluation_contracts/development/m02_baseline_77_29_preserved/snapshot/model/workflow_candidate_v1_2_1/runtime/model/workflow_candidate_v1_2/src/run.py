"""Single predeclared boundary candidate; fixed representation C and clustering."""
import json
import shutil
import platform
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import torch
import sklearn
from model.workflow_candidate_v1.src.data import load_logical,read_csv,sha,boundary_labels
from model.workflow_candidate_v1.src.neural import load_model as load_encoder,predict as encode
from model.workflow_candidate_v1.src.analysis import segments,represent,cluster,boundary_metrics,segmentation_metrics,process_maps as old_maps
from model.workflow_candidate_v1.training.run import split_data
from model.workflow_candidate_v1_1.src.representation import components,combine
from model.workflow_candidate_v1_1.src.audit import business_summary,process_audit
from model.workflow_candidate_v1_1.src.run import write,dump
from .features import decisions,EXTRA_NAMES
from .neural import train,predict,save_model,load_model
from .process_map import process_maps
from .failures import inspect_errors
from .adapter import canonical_for_generator
from .report import create_report

BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[1]
V1=ROOT/'model/workflow_candidate_v1';V11=ROOT/'model/workflow_candidate_v1_1'

def snapshot():
    return {str(p.relative_to(ROOT)):sha(p) for d in ['model/workflow_candidate_v1','model/workflow_candidate_v1_1','model/v6_2','data','backend','frontend','evaluation_contracts'] for p in (ROOT/d).rglob('*') if p.is_file() and p.name!='.DS_Store'}

def extended_segmentation(w,streams,metadata):
    metrics=segmentation_metrics(w,streams,metadata)
    merged=set()
    for item in w:
        owners={metadata[(item['source_dataset'],eid)]['execution_id'] for eid in item['source_event_evidence']}
        if len(owners)>1:merged.update(owners)
    metrics['under_segmented_execution_count']=len(merged)
    return metrics

def main():
    protected=snapshot();art=BASE/'artifacts';diag=BASE/'diagnostics'
    cfg=json.loads((BASE/'config/model.json').read_text());oldcfg=json.loads((V1/'artifacts/model_config.json').read_text())
    repcfg=json.loads((V11/'config/representation.json').read_text())
    streams,metadata,manifest=load_logical(ROOT,ROOT/'data/development/current_site_20x3_v3')
    labels=[boundary_labels(s,metadata) for s in streams]
    oldrows=read_csv(V1/'diagnostics/neural_boundary_predictions.csv');oldlookup={(r['source_dataset'],r['event_id']):r for r in oldrows}
    oldcuts=[np.array([oldlookup[(e['source_dataset'],e['event_id'])]['predicted_boundary']=='True' for e in s]) for s in streams]
    oldworkflows=segments(streams,oldcuts)
    errors,windows,anonymous=inspect_errors(streams,metadata,labels,oldcuts,oldworkflows,oldcfg)
    write(diag/'baseline_anonymous_execution_errors.csv',errors);write(diag/'baseline_boundary_windows.csv',windows)
    dump(diag/'pretraining_protocol.json',dict(configuration_sha256=sha(BASE/'config/model.json'),extra_features=EXTRA_NAMES,threshold=cfg['boundary_threshold'],training_protocol='One candidate, seed/epochs/lr fixed; R1/R2 only. No threshold search.',representation_config_sha256=sha(V11/'config/representation.json'),analysis='Boundary reference only; no BU/name/repetition used to derive general causes; error annotations attached after prediction.',offline_lookahead_seconds=cfg['offline_lookahead_seconds']))
    chunks,trainmask=split_data(streams,metadata,labels,lambda r:r['repetition'] in ('1','2'))
    _,holdmask=split_data(streams,metadata,labels,lambda r:r['repetition']=='3')
    fullmask=[[False]+[True]*(len(s)-1) for s in streams]
    print('Training one fixed boundary candidate',flush=True)
    model,training=train(chunks,cfg);save_model(model,art/'model.pt')
    output=predict(model,streams,cfg);probs=[p for p,_ in output];cuts=decisions(probs,streams,cfg)
    reload_output=predict(load_model(art/'model.pt',cfg),streams,cfg)
    assert all(np.array_equal(a[0],b[0]) for a,b in zip(output,reload_output))
    workflows=segments(streams,cuts,probs)
    # Encoder weights and all representation components remain frozen, only pooling ranges change.
    encoder=load_encoder(V1/'artifacts/model.pt',oldcfg)
    encoded=encode(encoder,streams,oldcfg);hidden=[h for _,h in encoded]
    existing,_=represent(workflows,streams,hidden,oldcfg)
    blocks,signatures=components(workflows,streams,hidden,existing,repcfg)
    embedding=combine(blocks,repcfg['candidates']['C_full']);assert embedding.shape[1]==1152
    clusters,cluster_diag=cluster(embedding,dict(oldcfg,cluster_distance_thresholds=repcfg['cluster_distance_thresholds']))
    clusters_repeat,_=cluster(embedding.copy(),dict(oldcfg,cluster_distance_thresholds=repcfg['cluster_distance_thresholds']))
    assert np.array_equal(clusters,clusters_repeat)
    tables=process_maps(workflows,clusters,streams,embedding)
    write(diag/'predicted_workflows.csv',workflows);write(diag/'structural_signatures.csv',signatures)
    write(diag/'workflow_embeddings.csv',[dict(workflow_instance_id=w['workflow_instance_id'],**{f'dim_{j:04}':float(v) for j,v in enumerate(x)}) for w,x in zip(workflows,embedding)])
    write(diag/'cluster_assignments.csv',[dict(workflow_instance_id=w['workflow_instance_id'],cluster_id=int(c)) for w,c in zip(workflows,clusters)])
    for name,rows in tables.items():write(diag/(name+'.csv'),rows)
    dump(diag/'clustering_diagnostics.json',cluster_diag)
    dump(diag/'canonical_workflows.json',[canonical_for_generator(tables,p['process_model_id']) for p in tables['process_models']])
    dump(diag/'pre_posthoc_manifest.json',dict(business_labels_used=False,representation_weights=repcfg['candidates']['C_full'],cluster_assignments_sha256=sha(diag/'cluster_assignments.csv'),workflow_embeddings_sha256=sha(diag/'workflow_embeddings.csv')))
    # Business labels enter only after the above predictions and clustering have been persisted.
    business=business_summary(workflows,clusters,streams,metadata);audit=process_audit(tables,workflows,streams,metadata)
    dump(diag/'business_evaluation.json',business);dump(diag/'process_map_audit.json',audit)
    # Isolate the generator fix with unchanged v1.1 workflows and clusters.
    oldemb=np.array([[float(r[f'dim_{j:04}']) for j in range(1152)] for r in read_csv(V11/'diagnostics/C_full/workflow_embeddings.csv')],dtype=np.float32)
    oldclusters=np.array([int(r['cluster_id']) for r in read_csv(V11/'diagnostics/C_full/cluster_assignments.csv')])
    fixed_old_maps=process_maps(oldworkflows,oldclusters,streams,oldemb)
    dump(diag/'generator_only_ablation.json',process_audit(fixed_old_maps,oldworkflows,streams,metadata))
    unchanged_generator=old_maps(workflows,clusters,streams,embedding)
    dump(diag/'boundary_only_ablation.json',process_audit(unchanged_generator,workflows,streams,metadata))
    evals={}
    for name,pred,w in [('v1_1',oldcuts,oldworkflows),('v1_2',cuts,workflows)]:
        evals[name]={split:{'exact':boundary_metrics(labels,pred,mask,0),'tolerant':boundary_metrics(labels,pred,mask,1)} for split,mask in [('all_development',fullmask),('training',trainmask),('internal_holdout',holdmask)]}
        evals[name]['segmentation']=extended_segmentation(w,streams,metadata)
    raw_cuts=[p>=cfg['boundary_threshold'] for p in probs]
    dump(diag/'lifecycle_guard_ablation.json',dict(without_guard={split:boundary_metrics(labels,raw_cuts,mask,1) for split,mask in [('all_development',fullmask),('internal_holdout',holdmask)]},suppressed_predictions=sum(int(np.count_nonzero(a & ~b)) for a,b in zip(raw_cuts,cuts)),description='No retuning: terminal/collector event start suppression isolated from learned logits'))
    cv=[];bus=sorted({r['business_unit_id'] for r in metadata.values()});np.random.RandomState(cfg['seed']).shuffle(bus)
    for fold in range(cfg['group_cv_folds']):
        held=set(bus[fold::cfg['group_cv_folds']]);chunks_cv,_=split_data(streams,metadata,labels,lambda r:r['business_unit_id'] not in held)
        _,mask=split_data(streams,metadata,labels,lambda r:r['business_unit_id'] in held)
        print('Group diagnostic fold',fold+1,flush=True)
        m,t=train(chunks_cv,cfg);out=predict(m,streams,cfg);pred=decisions([p for p,_ in out],streams,cfg)
        cv.append(dict(fold=fold+1,held_out_business_units=sorted(held),positive=t['positive'],negative=t['negative'],neural=boundary_metrics(labels,pred,mask,1)))
    olddev=json.loads((V1/'diagnostics/development_evaluation.json').read_text());oldcv=olddev['group_cross_validation']
    assert [x['held_out_business_units'] for x in cv]==[x['held_out_business_units'] for x in oldcv]
    dump(diag/'boundary_evaluation.json',dict(evaluation=evals,group_cv=cv,baseline_group_cv=oldcv,holdout_notice='INTERNAL DEVELOPMENT HOLDOUT; NOT INDEPENDENT UNSEEN VALIDATION'))
    error_posthoc=[]
    for err in errors:
        eid=next(k for k,v in anonymous.items() if v==err['anonymous_execution']);m=next(r for r in metadata.values() if r['execution_id']==eid)
        error_posthoc.append(dict(err,execution_id=eid,business_unit_id=m['business_unit_id'],repetition=m['repetition']))
    write(diag/'baseline_errors_posthoc.csv',error_posthoc)
    newerrors,newwindows,_=inspect_errors(streams,metadata,labels,cuts,workflows,cfg)
    write(diag/'remaining_execution_errors.csv',newerrors);write(diag/'remaining_boundary_windows.csv',newwindows)
    write(diag/'neural_boundary_predictions.csv',[dict(source_dataset=e['source_dataset'],event_id=e['event_id'],event_time=e['event_time'],probability=float(probs[si][i]),predicted_boundary=bool(cuts[si][i]),lifecycle_filter=e['interaction_type'] in cfg['nonstarting_events']) for si,s in enumerate(streams) for i,e in enumerate(s)])
    oldsummary=next(r for r in read_csv(V11/'diagnostics/candidate_comparison.csv') if r['candidate']=='C_full')
    gates={'boundary_all_not_worse':evals['v1_2']['all_development']['tolerant']['f1']>=evals['v1_1']['all_development']['tolerant']['f1'],
           'r3_not_worse':evals['v1_2']['internal_holdout']['tolerant']['f1']>=evals['v1_1']['internal_holdout']['tolerant']['f1'],
           'exact_not_worse':evals['v1_2']['segmentation']['correct_segmentation_exact']>=55,
           'development_dbi_at_most_one':cluster_diag['selected'].get('dbi') is not None and cluster_diag['selected']['dbi']<=1,
           'mixed_risk_not_worse':audit['summary']['B_models']<=int(oldsummary['B_process_models']),
           'http_method_contamination_reduced':audit['summary']['all_read_write_collision_nodes']==0,
           'group_mean_not_worse':bool(np.mean([x['neural']['f1'] for x in cv])>=np.mean([x['neural']['f1'] for x in oldcv])),
           'group_each_fold_not_worse':all(n['neural']['f1']>=o['neural']['f1'] for n,o in zip(cv,oldcv)),
           'cluster_purity_not_worse':business['overall_event_weighted_purity']>=float(oldsummary['cluster_purity']),
           'repetition_consistency_not_worse':business['same_bu_three_repetitions_consistent']>=int(oldsummary['bu_consistency']),
           'fragmentation_not_worse':business['fragmented_bus']<=int(oldsummary['fragmented_bus'])}
    summary=dict(total_events=sum(map(len,streams)),training_counts={k:training[k] for k in ['positive','negative','pos_weight']},boundary=evals,group_cv=cv,clustering=cluster_diag['selected'],embedding_dimension=1152,bu_consistency=business['same_bu_three_repetitions_consistent'],cluster_purity=business['overall_event_weighted_purity'],merged_bu_pairs=business['merged_bu_pairs'],fragmented_bus=business['fragmented_bus'],process_map_audit=audit['summary'],adoption_gates=gates,adopt_boundary_candidate=all(gates.values()),official_pass=None)
    summary['conclusion']='BOUNDARY_NEEDS_MINOR_ADJUSTMENT' if audit['summary']['upstream_mixed_workflow_count'] else 'READY_FOR_UNSEEN_VALIDATION' if all(gates.values()) else 'ADDITIONAL_DEVELOPMENT_DATA_NEEDED'
    dump(diag/'development_evaluation.json',summary)
    create_report(BASE,summary,oldsummary,error_posthoc,oldcv)
    dump(art/'model_config.json',cfg);shutil.copyfile(V11/'config/representation.json',art/'representation_config.json');shutil.copyfile(V1/'artifacts/model.pt',art/'representation_encoder.pt');shutil.copyfile(V1/'artifacts/model_config.json',art/'representation_encoder_config.json')
    dump(art/'feature_config.json',dict(base_dimensions=396,extra_dimensions=32,extra_names=EXTRA_NAMES,causal=False,offline_lookahead_seconds=cfg['offline_lookahead_seconds'],privacy='No free-form input/element text/BU/task_name features'))
    dump(art/'training_manifest.json',dict(mode='DEVELOPMENT',dataset=manifest['dataset_id'],dataset_manifest_sha256=sha(ROOT/'data/development/current_site_20x3_v3/dataset_manifest.json'),execution_manifest_sha256=sha(ROOT/'data/development/current_site_20x3_v3/execution_manifest.csv'),source_files=manifest['sources'],timestamp=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),seed=cfg['seed'],config=cfg,training=training,training_repetitions=[1,2],holdout_repetitions=[3],python=platform.python_version(),torch=torch.__version__,sklearn=sklearn.__version__,numpy=np.__version__,group_cv=cv,training_from_scratch=True,threshold_search=False,representation_encoder_frozen=True,holdout_notice='Previously analyzed INTERNAL DEVELOPMENT HOLDOUT; NOT INDEPENDENT UNSEEN VALIDATION',parameter_count=sum(p.numel() for p in model.parameters())))
    assert protected==snapshot(),'Protected files changed'
    dump(diag/'protected_files_verification.json',dict(unchanged=True,sha256=protected))
    dump(art/'model_manifest.json',dict(model_id='workflow_candidate_v1_2',mode='DEVELOPMENT',adopt_boundary_candidate=summary['adopt_boundary_candidate'],artifact_sha256={p.name:sha(p) for p in art.glob('*') if p.is_file() and p.name!='model_manifest.json'},code_sha256={str(p.relative_to(BASE)):sha(p) for p in (BASE/'src').glob('*.py')}))
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
