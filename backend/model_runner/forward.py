"""검증된 V6.2 가중치 forward. 입력은 raw events와 runtime/semantic 자원뿐입니다."""
from collections import Counter
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from . import notebook_ops as op
from .process_export import export_processes
from ..evaluators import EvaluationError, require


def encode(values, vocab):
    values=[op.safe_str(v) for v in values]
    unknown=Counter(v for v in values if v and v not in vocab)
    return np.asarray([vocab.get(v,1) for v in values],dtype=np.int64), {
        'count':sum(unknown.values()),'rate':sum(unknown.values())/len(values) if values else 0,
        'denominator':len(values),'nonempty_count':sum(bool(v) for v in values),'null_to_unk_count':sum(not v for v in values),'observed_values':dict(unknown),'policy':'OOV -> UNK (1)'}


def consensus_guard(segment_count, workflow_count):
    if segment_count < op.SEGMENT_CONSENSUS_K_MIN or workflow_count < op.WORKFLOW_CONSENSUS_K_MIN:
        raise EvaluationError(f'Consensus requires segments >= {op.SEGMENT_CONSENSUS_K_MIN}, workflows >= {op.WORKFLOW_CONSENSUS_K_MIN}; observed {segment_count}, {workflow_count}', 'INSUFFICIENT_DATA_FOR_CONSENSUS')


def semantic_features(encoder, texts):
    # Notebook cell 7: nonempty texts use E5 passage prefix; empty texts remain zero.
    texts=[op.safe_str(x) for x in texts]
    indices=[i for i,s in enumerate(texts) if s]
    output=np.zeros((len(texts),384),dtype='float32')
    if indices:
        output[indices]=encoder.encode(['passage: '+texts[i] for i in indices],batch_size=op.SEMANTIC_BATCH_SIZE,
            normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False).astype('float32')
    return output


def process(events, runtime, bundle, semantic_path, output, diagnostics):
    """평가 metadata/GT/실행 경계 파일을 받지 않습니다."""
    forbidden={'business_unit_id','business_unit_name','execution_id','ground_truth','step_label'}
    require(not forbidden.intersection(events.columns),'Evaluation metadata in model input')
    from sentence_transformers import SentenceTransformer
    torch.manual_seed(op.SEED)
    df=op.prep(events)
    encoder=SentenceTransformer(str(semantic_path),device='cpu')
    semantic=semantic_features(encoder,df.semantic_text.tolist())
    require(semantic.shape==(len(df),384),'Semantic dimension mismatch')
    vocabs=runtime['vocabularies'];struct={c:{v:i for i,v in enumerate(tokens)} for c,tokens in bundle['structural_vocabs'].items()};checkpoints=bundle['checkpoints']
    arrays={'bytes':np.stack([op.byte_encode(s,op.MAX_TEXT_BYTES) for s in df.event_text]),'semantic':semantic,
            'num':(op.raw_num(df)-np.asarray(runtime['stats']['mean'],dtype='float32'))/np.asarray(runtime['stats']['std'],dtype='float32')}
    diagnostics['oov']={}
    for col,vocab in {**vocabs,**struct}.items():
        arrays[col],diagnostics['oov'][col]=encode(df[col],vocab)
    def frozen(model, filename, key):
        model.load_state_dict(checkpoints[filename][key],strict=True)
        model.eval(); model.requires_grad_(False)
        return model
    em=frozen(op.EventTransformer(vocabs,384),'event_transformer.pt','model_state_dict')
    eb=frozen(op.NeuralBoundary(op.D_MODEL,struct),'event_boundary_model.pt','boundary_state_dict')
    sm=frozen(op.SegmentTransformer(op.D_MODEL),'segment_transformer.pt','segment_model_state_dict')
    wb=frozen(op.WorkflowBoundary(op.D_MODEL),'workflow_boundary_model.pt','workflow_boundary_state_dict')
    wt=frozen(op.WorkflowTransitionContrastive(op.D_MODEL),'workflow_transition_model.pt','state_dict')
    emb=np.zeros((len(df),op.D_MODEL),dtype='float32');ec=np.zeros(len(df),dtype='float32')
    probs=np.zeros(len(df),dtype='float32');pc=np.zeros(len(df),dtype='float32')
    with torch.inference_mode():
        loader=DataLoader(op.EventWindowDataset(op.make_windows(df,op.EVENT_WINDOW,op.EVENT_STRIDE),arrays),batch_size=op.BATCH_SIZE,collate_fn=op.collate)
        for b in loader:
            h=em(b,mask_events=False);p=torch.sigmoid(eb(h,b)).numpy();hv=h.numpy()
            for i,n in enumerate(b['lengths'].tolist()):
                ids=b['global_idx'][i,:n].numpy();emb[ids]+=hv[i,:n];ec[ids]+=1
                probs[ids[1:]]+=p[i,:n-1];pc[ids[1:]]+=1
        emb/=np.maximum(ec[:,None],1);probs/=np.maximum(pc,1)
        op.event_threshold_rows=[]
        segdf,members=op.make_segments(df,emb,probs)
        diagnostics['event_thresholds']=op.event_threshold_rows
        diagnostics['event_count']=len(df);diagnostics['latent_segment_count']=len(segdf)
        segdf.to_csv(output/'latent_segments.csv',index=False)
        if len(segdf)<2:
            diagnostics['latent_workflow_count']=0
            pd.DataFrame(columns=['workflow_id']+[f'f{i:02}' for i in range(80)]).to_csv(output/'workflow_consensus_features.csv',index=False)
            consensus_guard(len(segdf),0)
        base=np.stack([emb[x].mean(0) for x in members]);sh=np.zeros_like(base);sc=np.zeros(len(base),dtype='float32')
        loader=DataLoader(op.SegmentSeqDataset(segdf,base,op.SEGMENT_WINDOW,op.SEGMENT_STRIDE,mask_prob=0),batch_size=op.BATCH_SIZE,collate_fn=op.seg_collate)
        for b in loader:
            h=sm(b,mask=False).numpy()
            for i,n in enumerate(b['lengths'].tolist()):
                ids=b['segment_idx'][i,:n].numpy();sh[ids]+=h[i,:n];sc[ids]+=1
        sh/=np.maximum(sc[:,None],1)
        wp=np.zeros(len(segdf),dtype='float32');wc=np.zeros_like(wp);transition=np.zeros_like(wp)
        for _,g in segdf.groupby('stream_id',sort=False):
            ids=g.sort_values('start_global_idx').segment_idx.to_numpy()
            for st in range(0,len(ids),op.SEGMENT_STRIDE):
                sub=ids[st:st+op.SEGMENT_WINDOW]
                if len(sub)<2:continue
                p=torch.sigmoid(wb(torch.tensor(sh[sub]).unsqueeze(0))).squeeze(0).numpy()
                wp[sub[1:]]+=p;wc[sub[1:]]+=1
            if len(ids)>1:
                q,k=wt(torch.tensor(sh[ids[:-1]]),torch.tensor(sh[ids[1:]]))
                transition[ids[1:]]=op._robust_surprise_to_score(1-(q*k).sum(-1).numpy())
        wp/=np.maximum(wc,1)
        wp=((1-op.WORKFLOW_TRANSITION_BLEND_WEIGHT)*wp+op.WORKFLOW_TRANSITION_BLEND_WEIGHT*transition).astype('float32')
        workflows=[];workflow_members=[];diagnostics['workflow_thresholds']=[]
        for sid,g in segdf.groupby('stream_id',sort=False):
            ids=g.sort_values('start_global_idx').segment_idx.to_numpy()
            th,meta=op.threshold_calibrated(wp[ids][1:],return_meta=True) if len(ids)>1 else (1.0,{'mode':'single_segment'})
            starts=[0]+[i for i in range(1,len(ids)) if wp[ids[i]]>=th];filt=[0]
            for pos in starts[1:]:
                if pos-filt[-1]>=op.MIN_WORKFLOW_SEGMENTS:filt.append(pos)
            if len(ids)-filt[-1]<op.MIN_WORKFLOW_SEGMENTS and len(filt)>1:filt.pop()
            diagnostics['workflow_thresholds'].append({'stream_id':str(sid),'threshold':float(th),**meta})
            for j,start in enumerate(filt):
                sub=ids[start:filt[j+1] if j+1<len(filt) else len(ids)];idx=len(workflows)
                workflows.append({'workflow_idx':idx,'workflow_id':f'W{idx+1:05d}','stream_id':sid,'segment_start':int(sub[0]),'segment_end':int(sub[-1]),'segment_count':len(sub),'start_time':segdf.loc[sub[0],'start_time'],'end_time':segdf.loc[sub[-1],'end_time'],'boundary_threshold':th})
                workflow_members.append(sub)
        wf=pd.DataFrame(workflows);vectors=np.stack([sh[x].mean(0) for x in workflow_members]);diagnostics['latent_workflow_count']=len(wf)
        wf.to_csv(output/'latent_workflows.csv',index=False)
        ensemble=checkpoints['prototype_consensus_bundle.pt'];features={};runs={}
        for level,x in [('segment',sh),('workflow',vectors)]:
            runs[level]=[]
            for state in ensemble[level]['seed_states']:
                m=op.NeuralPrototypeModel(op.D_MODEL,state['k']);m.load_state_dict(state['state_dict'],strict=True);m.eval();m.requires_grad_(False)
                _,logits=m(torch.tensor(x));runs[level].append({'seed':state['seed'],'k':state['k'],'assignment':logits.argmax(-1).numpy()})
            features[level]=op._assignment_feature(runs[level])
        require(features['workflow'].shape==(len(wf),80),'Workflow consensus must be 80-dimensional')
        feature_df=pd.DataFrame(features['workflow'],columns=[f'f{i:02}' for i in range(80)]);feature_df.insert(0,'workflow_id',wf.workflow_id)
        feature_df.to_csv(output/'workflow_consensus_features.csv',index=False)
        diagnostics['required_k']={'segment':[op.SEGMENT_CONSENSUS_K_MIN,op.SEGMENT_CONSENSUS_K_MAX],'workflow':[op.WORKFLOW_CONSENSUS_K_MIN,op.WORKFLOW_CONSENSUS_K_MAX]}
        consensus_guard(len(segdf),len(wf))
        for level,frame,lo,hi,prefix in [('segment',segdf,10,18,'SP'),('workflow',wf,7,12,'WP')]:
            labels,search,summary=op._consensus_k_search(features[level],runs[level],lo,hi,level,5)
            conf,margin=op._consensus_item_metrics(features[level],labels)
            frame[level+'_prototype']=[f'{prefix}{x:02d}' for x in labels];frame[level+'_prototype_confidence']=conf
            diagnostics[level+'_consensus']=summary
            search.to_csv(output/(level+'_k_search.csv'),index=False)
        pd.DataFrame({'workflow_id':wf.workflow_id,'cluster_label':wf.workflow_prototype}).to_csv(output/'workflow_cluster_labels.csv',index=False)
        context={'df':df,'segdf':segdf,'workflow_df':wf,'workflow_members':workflow_members,'safe_str':op.safe_str,'DATASET_NAME':'current_site_dev_01'}
        exported=export_processes(context)
        for name,frame in exported.items():
            frame.to_csv(output/(name+'.csv'),index=False,encoding='utf-8-sig');diagnostics[name+'_count']=len(frame)
        diagnostics['weights_updated']=False
