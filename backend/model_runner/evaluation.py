"""모델 처리 후 시간 구간 매핑 및 기존 M02/M06 evaluator 연결."""
from datetime import datetime
from collections import Counter
from . import DATASET, read_csv, checked_files, write_json
from ..evaluators import M02Evaluator,M06Evaluator,EvaluationError,require,read_json,digest,csv_evidence
from ..run_storage import save_run


def temporal_mapping(executions,instances):
    def time(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
    rows=[]
    for execution in executions:
        start,end=time(execution['start_time']),time(execution['end_time']);duration=(end-start).total_seconds()
        require(duration>0,'Positive execution interval required')
        candidates=[]
        for instance in instances:
            if instance['session_id']!=execution['session_id']:continue
            a,b=time(instance['start_time']),time(instance['end_time'])
            require(b>=a,'Invalid instance interval')
            overlap=max(0,(min(end,b)-max(start,a)).total_seconds())
            if overlap>0:candidates.append((overlap,instance['instance_id']))
        best=max((v[0] for v in candidates),default=0);winners=[v[1] for v in candidates if v[0]==best]
        rows.append({'execution_id':execution['execution_id'],'session_id':execution['session_id'],
            'process_instance_id':winners[0] if len(winners)==1 else '', 'overlap_seconds':best,'overlap_ratio':best/duration,
            'mapping_status':'MAPPED' if len(winners)==1 else 'AMBIGUOUS' if winners else 'UNMAPPED',
            'mapping_method':'same_session_max_temporal_overlap','candidate_instance_ids':'|'.join(winners)})
    counts=Counter(r['process_instance_id'] for r in rows if r['mapping_status']=='MAPPED')
    for row in rows:row['instance_reuse_count']=counts.get(row['process_instance_id'],0)
    return rows


def evaluate_run(root,config,manifest):
    from pathlib import Path
    out=Path(manifest['output_directory']);base=root/'data/evaluation'/DATASET
    hashes=dict(manifest['input_sha256']);hashes[str(out/'run_manifest.json')]=digest(out/'run_manifest.json')
    hashes.update({str(out/name):value for name,value in manifest['output_sha256'].items()})
    results={}
    diagnostics=read_json(out/'diagnostics.json')
    for metric in ('M02','M06'):
        result={'dataset_id':DATASET,'source_type':'DEVELOPMENT','status':manifest['status'],'score':None,'sample_count':None,
            'input_sha256':dict(hashes),'model_run_id':manifest['run_id'],'model_reference_version':'V6.2',
            'evaluator_version':M02Evaluator.version if metric=='M02' else 'M06Evaluator-v1',
            'error':manifest.get('error'),'details':{'model_output_directory':str(out),'model_counts':manifest['counts'],
            'historical_equivalence_verified':False,'feature_space':'80-d frozen prototype seed assignment consensus' if metric=='M06' else None}}
        rows=[]
        try:
            for name,expected in manifest['output_sha256'].items():require(digest(out/name)==expected,'Model output hash mismatch: '+name)
            if metric=='M02':
                data=read_json(base/'data_manifest.json')
                if manifest.get('dataset_manifest_sha256'):
                    require(digest(base/'data_manifest.json')==manifest['dataset_manifest_sha256'],'Dataset manifest changed after model run')
                result['input_sha256'][str(base/'data_manifest.json')]=digest(base/'data_manifest.json')
                result['input_sha256'].update(checked_files(base,data['derived_artifacts'],['execution_manifest.csv','evaluation_pairing.csv','ground_truth.csv']))
                executions=read_csv(base/'execution_manifest.csv');pairing=read_csv(base/'evaluation_pairing.csv');gt=read_csv(base/'ground_truth.csv')
                require(len({r['execution_id'] for r in executions})==len(executions),'Duplicate execution ID')
                require(len(pairing)==len(executions) and {r['execution_id'] for r in pairing}=={r['execution_id'] for r in executions},'Pairing/execution ID mismatch')
                instances=read_csv(out/'process_instances.csv') if manifest['status']=='COMPLETED' else []
                mapping=temporal_mapping(executions,instances)
                if manifest['status']!='COMPLETED':
                    for row in mapping:row['mapping_status']='MODEL_OUTPUT_UNAVAILABLE'
                (out/'execution_instance_mapping.csv').write_text(csv_evidence(mapping),encoding='utf-8')
                pairs={r['execution_id']:r for r in pairing};steps=read_csv(out/'process_instance_steps.csv') if instances else []
                actual=[];truth=[];direct_rows=[]
                for m in mapping:
                    pair=pairs[m['execution_id']];bid=pair['business_unit_id']
                    required=[{'id':str(r['step_order']),'label':r['step_label']} for r in gt if r['business_unit_id']==bid and r['required'].lower()=='true']
                    require(required and all(r['status']=='FINAL' for r in gt if r['business_unit_id']==bid),'FINAL required GT missing')
                    row={**m,'business_unit_id':bid,'business_unit_name':pair['business_unit_name'],'execution_number':pair['execution_number'],
                        'gt_procedure_count':len(required),'model_procedure_count':None,'direct_match_count':None,'accuracy':None,'completeness':None,'score':None}
                    if m['mapping_status']=='MAPPED':
                        detected=[{'id':r['instance_step_id'],'label':r['display_label'],'evidence_type':'direct'} for r in steps if r['instance_id']==m['process_instance_id']]
                        a={'id':m['execution_id'],'procedures':detected};g={'id':m['execution_id'],'procedures':required}
                        if detected:
                            score,n,detail,evidence=M02Evaluator().evaluate({'processes':[a]},{'processes':[g]})
                            row.update(model_procedure_count=len(detected),direct_match_count=detail['correctly_mapped'],accuracy=detail['accuracy'],completeness=detail['completeness'],score=score)
                            actual.append(a);truth.append(g);direct_rows.extend(evidence)
                    rows.append(row)
                result['details'].update(mapping_method='same_session_max_temporal_overlap',mapped_execution_count=len(actual),total_execution_count=len(executions),
                    coverage=len(actual)/len(executions),aggregate_scope='Mapped executions only; per-execution comparison; shared instance reuse disclosed',ground_truth_count=len({r['business_unit_id'] for r in gt}))
                if actual:
                    score,n,detail,_=M02Evaluator().evaluate({'processes':actual},{'processes':truth})
                    result.update(score=score,sample_count=n,status='COMPLETED',error=None);result['details'].update(detail)
                elif manifest['status']=='COMPLETED':result.update(status='BLOCKED',error='No unambiguous mapped instance with procedures')
                (out/'m02_direct_matches.csv').write_text(csv_evidence(direct_rows or [{'status':result['status']}]),encoding='utf-8')
            elif manifest['status']=='COMPLETED':
                features=read_csv(out/'workflow_consensus_features.csv');labels=read_csv(out/'workflow_cluster_labels.csv')
                require([r['workflow_id'] for r in features]==[r['workflow_id'] for r in labels],'Workflow ID alignment mismatch')
                score,n,detail,rows=M06Evaluator().evaluate([[float(r[f'f{i:02}']) for i in range(80)] for r in features],[r['cluster_label'] for r in labels])
                result.update(score=score,sample_count=n,status='COMPLETED',error=None);result['details'].update(detail)
            else:
                result['sample_count']=manifest['counts'].get('latent_workflow_count')
                result['details'].update(required_k=diagnostics.get('required_k'),workflow_count=result['sample_count'])
        except (EvaluationError,ValueError,KeyError,OSError) as exc:
            result.update(status='ERROR',score=None,error=str(exc))
        if metric=='M02':
            for filename in ['execution_instance_mapping.csv','m02_direct_matches.csv']:
                if (out/filename).exists():result['input_sha256'][str(out/filename)]=digest(out/filename)
        results[metric]=save_run(root,metric,'DEVELOPMENT',config,result,rows)
    return results
