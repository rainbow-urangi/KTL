"""일반 lifecycle 신호와 명시적 offline lookahead. BU/입력값은 사용하지 않습니다."""
import numpy as np
from model.workflow_candidate_v1.src.features import features as base_features,normalized_path,target_role
from model.workflow_candidate_v1.src.data import time_of

EXTRA_NAMES=['popup_active_before','popup_open','popup_close','since_close_events','recent_popup_close','current_get','current_post','current_patch','current_put','current_delete','last_api_family_change','previous_successful_mutation','previous_user_navigation','previous_user_button','previous_user_item','previous_user_input','previous_user_container','current_button','current_item','current_grid_cell','current_container','completion_to_navigation','page_action_transition','terminal_page_close','next_popup_open_direct','next_popup_close_direct','next_api_get_direct','next_api_mutation_direct','next_route_direct','next_user_navigation','recent_mutation','input_inside_popup']
USER_ACTIONS={'click','change','input','paste','submit'}

def role(e):
    basic=target_role(e)
    if basic=='navigation':return 'navigation'
    if e.get('element_tag')=='button':return 'button'
    if basic=='input_control':return 'input'
    if basic=='item':return 'item'
    if 'cell' in e.get('target_selector','').lower():return 'grid_cell'
    if e.get('element_tag')=='div' and basic!='dialog_control':return 'container'
    return basic

def features(stream,config):
    base=base_features(stream,config);extras=[]
    popup=False;last_close=None;last_mutation=None;last_api=None;previous_user=None
    for i,e in enumerate(stream):
        it=e.get('interaction_type','');method=e.get('api_method','').upper();current_role=role(e)
        api=normalized_path(e.get('api_path',''));page=normalized_path(e.get('page_url',''))
        recent_close=last_close is not None and time_of(e)-time_of(stream[last_close])<=config['lifecycle_window_seconds']
        recent_mutation=last_mutation is not None and time_of(e)-time_of(stream[last_mutation])<=config['lifecycle_window_seconds']
        next_popup_open=next_popup_close=next_get=next_write=next_route=next_nav=False
        # Stop at the next user action: do not attribute its popup to this event.
        if it in USER_ACTIONS:
            for later in stream[i+1:i+1+config['offline_lookahead_events']]:
                if time_of(later)-time_of(e)>config['offline_lookahead_seconds']:break
                lit=later.get('interaction_type','')
                if lit in USER_ACTIONS:
                    next_nav=role(later)=='navigation';break
                next_popup_open |= lit=='popup_open';next_popup_close |= lit=='popup_close'
                next_get |= later.get('api_method','').upper()=='GET'
                next_write |= later.get('api_method','').upper() in {'POST','PATCH','PUT','DELETE'}
                next_route |= lit=='route_change'
        prev_role=role(previous_user) if previous_user else ''
        prev=stream[i-1] if i else None
        previous_mutation=bool(prev and prev.get('api_method','').upper() in {'POST','PATCH','PUT','DELETE'} and prev.get('api_status_code','').startswith('2'))
        page_action=bool(previous_user and normalized_path(previous_user.get('page_url',''))!=page and it in USER_ACTIONS)
        extras.append([popup,it=='popup_open',it=='popup_close',min((i-last_close)/20,1) if last_close is not None else 1,recent_close,
                       method=='GET',method=='POST',method=='PATCH',method=='PUT',method=='DELETE',bool(api and last_api and api!=last_api),previous_mutation,
                       prev_role=='navigation',prev_role=='button',prev_role=='item',prev_role=='input',prev_role=='container',current_role=='button',current_role=='item',current_role=='grid_cell',current_role=='container',
                       bool((recent_close or recent_mutation) and current_role=='navigation' and it in USER_ACTIONS),page_action,it=='page_close',
                       next_popup_open,next_popup_close,next_get,next_write,next_route,next_nav,recent_mutation,bool(popup and it in {'input','change','paste'})])
        if it=='popup_open':popup=True
        elif it=='popup_close':popup=False;last_close=i
        elif it=='route_change':popup=False
        if api:last_api=api
        if method in {'POST','PATCH','PUT','DELETE'} and e.get('api_status_code','').startswith('2'):last_mutation=i
        if it in USER_ACTIONS:previous_user=e
    return np.concatenate([base,np.asarray(extras,dtype=np.float32)],axis=1)

def decisions(probabilities,streams,config):
    return [np.asarray([bool(i and p>=config['boundary_threshold'] and e.get('interaction_type') not in config['nonstarting_events']) for i,(e,p) in enumerate(zip(s,prob))]) for s,prob in zip(streams,probabilities)]
