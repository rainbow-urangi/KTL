"""Reproducible DEVELOPMENT training and diagnostics, independent of product APIs."""
import argparse
import csv
import json
import platform
import sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import torch
import sklearn
from ..src.data import load_logical,boundary_labels,sha
from ..src.features import rule_boundaries,event_vector,normalized_path
from ..src.neural import train,predict,save_model,load_model
from ..src.analysis import (boundary_metrics,segments,segmentation_metrics,represent,cluster,similarities,business_evaluation,process_maps)
from ..src.adapter import canonical_for_generator

PACKAGE=Path(__file__).resolve().parents[1]
ROOT=PACKAGE.parents[1]

def dump(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def write(path,rows,empty_fields=None):
    fields=list(rows[0]) if rows else empty_fields or ['status']
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def split_data(streams,metadata,labels,predicate):
    chunks=[];masks=[]
    for stream,y in zip(streams,labels):
        chosen=[predicate(metadata[(e['source_dataset'],e['event_id'])]) for e in stream]
        masks.append([False]+[chosen[i] and chosen[i-1] for i in range(1,len(stream))])
        begin=None
        for i,take in enumerate(chosen+[False]):
            if take and begin is None:begin=i
            if not take and begin is not None:
                chunks.append((stream[begin:i],y[begin:i]));begin=None
    return chunks,masks

def snapshot():
    paths=[]
    for base in ['model/v6_2','data/development','backend','frontend','evaluation_contracts']:
        paths.extend(p for p in (ROOT/base).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='.DS_Store')
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}

def main(dataset,output=PACKAGE):
    output=Path(output);art=output/'artifacts';diag=output/'diagnostics'
    art.mkdir(parents=True,exist_ok=True);diag.mkdir(parents=True,exist_ok=True)
    config=json.loads((PACKAGE/'config/default.json').read_text())
    protected=snapshot()
    streams,metadata,manifest=load_logical(ROOT,Path(dataset))
    labels=[boundary_labels(s,metadata) for s in streams]
    chunks,train_masks=split_data(streams,metadata,labels,lambda r:r['repetition'] in ('1','2'))
    _,holdout_masks=split_data(streams,metadata,labels,lambda r:r['repetition']=='3')
    full_masks=[[False]+[True]*(len(s)-1) for s in streams]
    baseline=[rule_boundaries(s,config) for s in streams]
    print('Training main GRU on R1/R2 only',flush=True)
    model,training=train(chunks,config)
    save_model(model,art/'model.pt')
    prediction=predict(model,streams,config)
    reloaded=predict(load_model(art/'model.pt',config),streams,config)
    reproducible=all(np.array_equal(a[0],b[0]) and np.array_equal(a[1],b[1]) for a,b in zip(prediction,reloaded))
    if not reproducible:raise AssertionError('Save/load inference differs')
    probabilities=[p for p,_ in prediction];hidden=[h for _,h in prediction]
    cuts=[p>=config['boundary_threshold'] for p in probabilities]
    evaluations={}
    for name,pred in [('rule',baseline),('neural',cuts)]:
        evaluations[name]={split:{'exact':boundary_metrics(labels,pred,masks,0),'tolerant':boundary_metrics(labels,pred,masks,config['boundary_tolerance_events'])}
                           for split,masks in [('all_development',full_masks),('training',train_masks),('internal_holdout',holdout_masks)]}
        wf=segments(streams,pred,probabilities if name=='neural' else None)
        evaluations[name]['segmentation']=segmentation_metrics(wf,streams,metadata)
    dump(diag/'boundary_evaluation.json',dict(holdout_notice='INTERNAL DEVELOPMENT HOLDOUT; NOT INDEPENDENT UNSEEN VALIDATION',session_starts_excluded=len(streams),evaluation=evaluations))
    workflows=segments(streams,cuts,probabilities)
    embeddings,signatures=represent(workflows,streams,hidden,config)
    cluster_labels,cluster_diagnostic=cluster(embeddings,config)
    # All predictions and clustering complete before business labels are inspected.
    business=business_evaluation(workflows,cluster_labels,streams,metadata)
    tables=process_maps(workflows,cluster_labels,streams,embeddings)
    write(diag/'predicted_workflows.csv',workflows)
    write(diag/'workflow_embeddings.csv',[dict(workflow_instance_id=w['workflow_instance_id'],**{f'dim_{i:03}':float(v) for i,v in enumerate(emb)}) for w,emb in zip(workflows,embeddings)])
    write(diag/'workflow_similarity.csv',similarities(workflows,embeddings,signatures))
    write(diag/'cluster_assignments.csv',[dict(workflow_instance_id=w['workflow_instance_id'],cluster_id=int(c)) for w,c in zip(workflows,cluster_labels)])
    for name,rows in tables.items():write(diag/(name+'.csv'),rows)
    dump(diag/'canonical_workflows.json',[canonical_for_generator(tables,p['process_model_id']) for p in tables['process_models']])
    for name,pred in [('rule_baseline_boundaries',baseline),('neural_boundary_predictions',cuts)]:
        rows=[]
        for si,s in enumerate(streams):
            for i,e in enumerate(s):
                rows.append(dict(source_dataset=e['source_dataset'],source_session_id=e['session_id'],event_id=e['event_id'],event_time=e['event_time'],
                                 predicted_boundary=bool(pred[si][i]),probability=float(probabilities[si][i]) if name.startswith('neural') else None,
                                 session_start=i==0))
        write(diag/(name+'.csv'),rows)
    dump(diag/'clustering_diagnostics.json',cluster_diagnostic)
    cv=[]
    bus=sorted({r['business_unit_id'] for r in metadata.values()})
    rng=np.random.RandomState(config['seed']);rng.shuffle(bus)
    for fold in range(config['group_cv_folds']):
        held=set(bus[fold::config['group_cv_folds']])
        fold_chunks,_=split_data(streams,metadata,labels,lambda r:r['business_unit_id'] not in held)
        _,mask=split_data(streams,metadata,labels,lambda r:r['business_unit_id'] in held)
        print(f'Training group diagnostic fold {fold+1}',flush=True)
        cvmodel,cvtrain=train(fold_chunks,config)
        fold_predictions=predict(cvmodel,streams,config)
        foldcuts=[p>=config['boundary_threshold'] for p,_ in fold_predictions]
        cv.append(dict(fold=fold+1,held_out_business_units=sorted(held),training_positive=cvtrain['positive'],training_negative=cvtrain['negative'],
                       neural=boundary_metrics(labels,foldcuts,mask,config['boundary_tolerance_events']),rule=boundary_metrics(labels,baseline,mask,config['boundary_tolerance_events'])))
    # Label-only output is segregated from inference diagnostics.
    label_rows=[]
    for si,s in enumerate(streams):
        for i,e in enumerate(s):
            r=metadata[(e['source_dataset'],e['event_id'])]
            label_rows.append(dict(event_id=e['event_id'],source_dataset=e['source_dataset'],execution_id=r['execution_id'],business_unit_id=r['business_unit_id'],repetition=r['repetition'],boundary_label=labels[si][i],training_scored=train_masks[si][i],holdout_scored=holdout_masks[si][i]))
    write(output/'training/boundary_labels.csv',label_rows)
    dump(art/'model_config.json',config)
    dump(art/'preprocessing_config.json',dict(raw_field_allowlist='src/data.py:RAW_FIELDS',session_order='source_dataset/session_id, timestamp, event_id',state_reset='source session only',causal=True,execution_metadata_removed=True,active_membership_selection_bias=True))
    dump(art/'feature_config.json',dict(input_dimension=config['hash_dim']+config['previous_hash_dim']+12,embedding_dimension=embeddings.shape[1],hash='SHA-256 signed hashing, normalized char ngrams 3..5',temporal_features=12,semantic_encoder=None,semantic_note='Frozen pretrained encoder not used; static allowlisted title hashed; all free-form text discarded',config=config))
    dump(art/'normalization_config.json',dict(volatile_tokens=['UUID','numeric ID','date/timestamp','long hex'],query_fragment_removed=True,input_data_removed=True,element_text_removed=True,target_selector_used_only_for_generic_role=True,page_title_allowlist=config['safe_page_titles']))
    code_hashes={str(p.relative_to(PACKAGE)):sha(p) for sub in ['src','training','config'] for p in (PACKAGE/sub).glob('*') if p.suffix in ('.py','.json')}
    tm=dict(source_dataset=manifest['dataset_id'],dataset_manifest_sha256=sha(Path(dataset)/'dataset_manifest.json'),execution_manifest_sha256=sha(Path(dataset)/'execution_manifest.csv'),source_files=manifest['sources'],train_repetitions=[1,2],holdout_repetitions=[3],holdout_notice='INTERNAL DEVELOPMENT HOLDOUT; NOT INDEPENDENT UNSEEN VALIDATION',split_execution_ids={split:sorted({r['execution_id'] for r in metadata.values() if (r['repetition']=='3')==(split=='holdout')}) for split in ['train','holdout']},random_seed=config['seed'],python_version=platform.python_version(),pytorch_version=torch.__version__,numpy_version=np.__version__,sklearn_version=sklearn.__version__,pretrained_encoder=None,pretrained_revision=None,hyperparameters=config,training_timestamp=datetime.now(timezone.utc).isoformat(),code_sha256=code_hashes,boundary_training=training,parameter_count=sum(p.numel() for p in model.parameters()),device='cpu',threshold_selection='fixed 0.5 before training; no holdout tuning',group_cv=cv)
    dump(art/'training_manifest.json',tm)
    assert protected==snapshot(),'Protected original files changed'
    dump(diag/'protected_files_verification.json',dict(unchanged=True,sha256=protected))
    hold=evaluations['neural']['internal_holdout']['tolerant']['f1']
    group_mean=float(np.mean([r['neural']['f1'] for r in cv]))
    verdict=('MORE_DEVELOPMENT_DATA_NEEDED' if min(r['neural']['f1'] for r in cv)<0.5
             else 'MODEL_NEEDS_MINOR_ADJUSTMENT' if hold<0.8 or business['mixed_business_cluster_count']>0
             else 'READY_FOR_UNSEEN_VALIDATION')
    development=dict(mode='DEVELOPMENT',official_pass=None,total_events=sum(map(len,streams)),source_session_count=len(streams),boundary_training_counts={k:training[k] for k in ('positive','negative','pos_weight')},
                     boundary=evaluations,group_cross_validation=cv,group_neural_f1_mean=group_mean,business_evaluation=business,embedding_dimension=int(embeddings.shape[1]),clustering=cluster_diagnostic['selected'],process_model_count=len(tables['process_models']),process_step_count=len(tables['process_steps']),parameter_count=tm['parameter_count'],deterministic_save_load_inference=reproducible,
                     oov_policy='No UNK; SHA-256 feature hashing; unseen structural token remains represented; collisions possible',
                     oov_probe_distinct_vectors=not np.array_equal(event_vector({'page_url':'/unseen/path/123'},config),event_vector({'page_url':'/novel/route/456'},config)),
                     v62_comparison={'dev_01':{'events':273,'segments':7,'workflows':2},'dev_02':{'events':320,'segments':3,'workflows':1},'source':'user supplied frozen-forward reference counts; V6.2 not rerun','same_dataset_comparison':False},
                     limitations=['Active membership already curated using execution ranges; not a continuous unfiltered validation.','Internal holdout previously inspected; no independent unseen validation.','Training state reset only at split gaps; evaluation context may include prior train events but no labels.','No pretrained semantic encoder; free-form content deliberately excluded.','Process labels are structural action categories, not validated business procedures.','Group CV masks transitions whose adjacent event belongs to training; fold contexts remain causal and label-free.'],
                     decision_policy='Development recommendation only: group-fold F1 below 0.5 -> more development data; otherwise holdout F1 below 0.8 or mixed BU clusters -> adjustment; otherwise unseen validation. Not a KTL criterion.',conclusion=verdict)
    dump(diag/'development_evaluation.json',development)
    mm=dict(model_id='workflow_candidate_v1',mode='DEVELOPMENT',official=False,architecture='feature projection -> 1-layer causal GRU -> MLP',inference_contract='raw CSV only; no execution manifests or BU features',parameter_count=tm['parameter_count'],embedding_dimension=int(embeddings.shape[1]),clustering_policy=cluster_diagnostic['selection'],canonical_schema='workflow-canonical-1',artifact_sha256={p.name:sha(p) for p in art.glob('*') if p.is_file() and p.name!='model_manifest.json'},source_sha256=code_hashes)
    dump(art/'model_manifest.json',mm)
    report(development,diag/'development_report.md')
    print(json.dumps({k:development[k] for k in ['total_events','boundary_training_counts','embedding_dimension','clustering','process_model_count','conclusion']},ensure_ascii=False,indent=2),flush=True)
    print('BOUNDARY',json.dumps(evaluations,ensure_ascii=False),flush=True)
    print('GROUP_CV',json.dumps(cv,ensure_ascii=False),flush=True)

def report(d,path):
    ev=d['boundary'];s=ev['neural']['segmentation'];c=d['clustering'];b=d['business_evaluation']
    lines=['# Workflow candidate v1 DEVELOPMENT 보고서','',
           '**INTERNAL DEVELOPMENT HOLDOUT — NOT INDEPENDENT UNSEEN VALIDATION**','',
           f"CPU 단방향 GRU: projection 64 → GRU 64×1 → MLP 32 → sigmoid. 파라미터 {d['parameter_count']:,}개.",
           f"전체 {d['total_events']} events. 학습 positive {d['boundary_training_counts']['positive']}, negative {d['boundary_training_counts']['negative']}. weighted BCE 사용.",'',
           '| 모델/분할 | Precision | Recall | F1 | 예측 boundary |','|---|---:|---:|---:|---:|']
    for model in ['rule','neural']:
        for split in ['all_development','training','internal_holdout']:
            m=ev[model][split]['tolerant'];lines.append(f"| {model}/{split} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['predicted_boundary_count']} |")
    lines+=['', '위 표는 ±1 event, 동일 source session 내 one-to-one 매칭. exact 결과도 JSON에 보관. 세션 시작은 모델 예측이 아니므로 경계 성능에서 제외.',
            f"예측 workflow {s['predicted_workflow_count']}, exact segmentation {s['correct_segmentation_exact']}/60, 과분할 execution {s['over_segmented_execution_count']}, 병합된 predicted workflow {s['under_segmented_workflow_count']}.",
            f"Embedding {d['embedding_dimension']}차원. cluster/process model {d['process_model_count']}개. silhouette {c.get('silhouette')}, DBI {c.get('dbi')} (DEVELOPMENT, 공식 M06 아님).",
            f"동일 BU 세 반복의 대표 cluster 일치 {b['same_bu_three_repetitions_consistent']}/{b['business_count']}; event-weighted purity {b['overall_event_weighted_purity']:.4f}. 분할 fragment를 event 수 최다 cluster에 귀속하는 진단이며 exact grouping 성공률이 아님.",
            f"BU 그룹 3-fold neural F1 평균 {d['group_neural_f1_mean']:.4f}. 서로 다른 split에서 얻은 참고 진단이며 공식 일반화 성능이 아님.",'',
            '## 혼동 진단','', '| 업무 pair | 같은 cluster 실행 pair / 전체 |','|---|---:|']
    for p in b['requested_pair_analysis']:lines.append(f"| {p['business_a']} / {p['business_b']} | {p['same_cluster_execution_pairs']} / {p['total_execution_pairs']} |")
    lines+=['', '## 해석과 한계','',
            f"조회·상세·등록을 같은 cluster로 합친 경우가 많다. 가장 높은 혼동 pair: {[(p['business_a'],p['business_b'],p['same_cluster_execution_pairs']) for p in b['confusion_pairs'][:8]]}. 높은 silhouette과 20/20 반복 일치만으로 업무 구분 성공을 판단하지 않는다.",
            'V6.2 frozen-forward 참고값은 dev_01 273→7 segments→2 workflows, dev_02 320→3→1이다. 이번 866 events와 데이터가 달라 성능 향상을 직접 주장하지 않는다. 구조 OOV는 UNK 대신 결정적 해싱으로 처리하며 기존 모델·API·데이터는 변경하지 않았다.',
            f"BU 그룹 F1은 {[round(r['neural']['f1'],4) for r in d['group_cross_validation']]}; 규칙 기준은 {[round(r['rule']['f1'],4) for r in d['group_cross_validation']]}. 내부 반복 holdout 개선이 새로운 업무 유형으로 이어지지 않았다. 이것이 가장 큰 failure mode이다.",
            '과분할/병합이 남아 있으면 프로세스맵 또한 불완전하다. 특히 같은 화면에서 반복되는 조회와 팝업 동작은 task 종료를 명시하지 않아 경계가 모호할 수 있다. 순서·사용자·수행 속도가 다른 연속 원시 세션이 필요하다.',
            '학습 threshold와 epoch는 config에서 사전 고정했다. 최종 downstream 산출물은 neural prediction을 사용하며 baseline보다 개선이 없는 경우에도 결과를 숨기지 않는다.',
            '활성 event 선택 자체에 기존 실행 범위가 사용되었다. 추론은 실행 경계로 분할하거나 상태를 초기화하지 않지만, 이 선별로 만들어진 간격이 경계 단서가 될 수 있다. 미선별 연속 로그 검증이 필요하다.',
            '독립 raw CSV 추론 경로를 제공한다. 자유 입력 텍스트는 제거하고 static title만 허용한다. 사전 학습 semantic encoder는 사용하지 않았다.',
            '기존 M03 API는 변경하지 않았다. canonical adapter는 생성기 전달용 절차/evidence만 제공하며 자동 시나리오 생성 성공을 주장하지 않는다.','',
            '**최종 판정: '+d['conclusion']+'**','']
    path.write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',default=str(ROOT/'data/development/current_site_20x3_v3'));args=parser.parse_args();main(args.dataset)
