"""GT-free structural preservation. No process IDs, scores, URLs or date values."""
import copy
import re

BOUNDARIES={'route_change','page_view','screen_change','page_close','collector_boot'}
def nav_click(e):
    return (e.get('event',{}).get('action')=='click' and bool(e.get('element_text'))
            and not e.get('popup',{}).get('active_popup_id')
            and e.get('tag') in ('button','a','li')
            and bool(re.search(r'(^| > )nav(?:[.# >]|$)',e.get('selector') or '')))

def opening_for(event,events,positions,popup_id=None):
    """A parent survives only if captured stack identity proves every nested boundary."""
    popup_id=popup_id or event.get('popup',{}).get('active_popup_id')
    if not popup_id or not event.get('page_path'):return None
    current=[x for x in event.get('popup_stack',[]) if x.get('popup_id')==popup_id]
    for prior in reversed(events[:positions[event['event_id']]]):
        if prior['session_id']!=event['session_id']:continue
        action=prior['event'].get('action');target=prior.get('popup',{}).get('target_popup') or {}
        if prior['page_path']!=event['page_path'] or action in BOUNDARIES:return None
        if action=='popup_open' and target.get('popup_id')==popup_id:
            if current and (len(current)!=1 or any(current[0].get(k)!=target.get(k) for k in ('opened_at','opened_by_event_id'))):return None
            return prior
        if action in ('popup_open','popup_close'):
            if target.get('popup_id')==popup_id:return None
            live=[x for x in prior.get('popup_stack',[]) if x.get('popup_id')==popup_id]
            if len(current)!=1 or len(live)!=1 or not current[0].get('opened_at'):return None
            if any(current[0].get(k)!=live[0].get(k) for k in ('opened_at','opened_by_event_id')):return None
    return None

def date_picker_proof(event,events,positions,validated_openers):
    """Explicit calendar day click closes its own nested picker in a live parent."""
    popup=event.get('popup',{});eid=event['event_id']
    if (event['event'].get('action')!='click' or event.get('tag') not in ('button','td')
        or not event.get('popup_containment',{}).get('is_inside_popup')
        or not re.search(r'calendar.*(?:__day|[._ -]day|gridcell)',event.get('selector',''),re.I)
        or not event.get('element_text')):return None
    opened=opening_for(event,events,positions)
    if not opened or not validated_openers.get(opened['event_id'],{}).get('valid'):return None
    target=opened['popup']['target_popup'];parent=target.get('parent_popup_id')
    if not parent or popup.get('active_parent_popup_id')!=parent:return None
    parent_open=opening_for(event,events,positions,parent)
    if not parent_open:return None
    for later in events[positions[eid]+1:]:
        if later['session_id']!=event['session_id']:continue
        a=later['event'].get('action');p=later.get('popup',{});t=p.get('target_popup') or {}
        if later['page_path']!=event['page_path'] or a in BOUNDARIES:return None
        if a=='popup_close' and t.get('popup_id')==target.get('popup_id'):
            refs=[p.get('closer_event_id'),later['event'].get('cause_event_id'),later['event'].get('related_event_id')]
            if not any(refs) or any(x!=eid for x in refs if x):return None
            if t.get('opened_at')!=target.get('opened_at'):return None
            return dict(click_source_event_id=eid,picker_open_source_event_id=opened['event_id'],
                picker_close_source_event_id=later['event_id'],parent_open_source_event_id=parent_open['event_id'],
                opener_source_event_id=validated_openers[opened['event_id']]['source_event_id'],
                parent_popup_title=parent_open['popup']['target_popup'].get('title'),date_inferred=False)
        if a in ('click','input','change','submit','popup_open','popup_close'):return None
    return None

def compress(steps,lookup,positions,add_source):
    """Only adjacent intent owners. All merged source evidence remains on the owner."""
    kept=[]
    for step in steps:
        if kept:
            before=kept[-1];a=lookup[before['intent_source_event_ids'][-1]];b=lookup[step['intent_source_event_ids'][0]]
            same=(a['session_id']==b['session_id'] and a['page_path']==b['page_path'] and before['process_id']==step['process_id'])
            rule=None
            # Navigation ancestry alone cannot prove that the first action is
            # auxiliary (siblings may be Export/Refresh). Disabled until raw
            # expansion/opener evidence identifies a real descendant submenu.
            proof=step.get('selection_provenance') or {}
            if same and step.get('selection_kind')=='DATE_PICKER_DAY' and before['intent_source_event_ids']==[proof.get('opener_source_event_id')]:rule='BA-DATE-PICKER-OPEN-AUXILIARY'
            # Repeated input notifications may share a form, but no unknown action is crossed.
            if same and before['action_type']==step['action_type']=='INPUT' and before.get('form_identity') and before['form_identity']==step.get('form_identity') and before.get('business_context') and before.get('business_context')==step.get('business_context') and not any(e['event'].get('action') in BOUNDARIES | {'popup_open','popup_close'} for e in lookup.values() if e['session_id']==a['session_id'] and positions[a['event_id']]<positions[e['event_id']]<positions[b['event_id']]):
                rule='BA-CONTIGUOUS-SAME-FORM-INPUT'
                step['fields']=before.get('fields',[])+step.get('fields',[])
                step['intent_source_event_ids']=before['intent_source_event_ids']+step['intent_source_event_ids']
            if rule:
                for eid in before['source_event_ids']:add_source(step,lookup[eid],'MERGED_AUXILIARY_OR_SAME_ACTION')
                step.setdefault('merge_provenance',[]).extend(before.get('merge_provenance',[]))
                step['merge_provenance'].append(dict(rule_id=rule,merged_generated_step_id=before['generated_step_id'],source_event_ids=list(before['source_event_ids'])))
                kept.pop()
        kept.append(step)
    return kept


def same_live_form(a,b):
    """Frozen segmentation is not a form lifetime. Require shared raw opening proof."""
    refs=[(s.get('form_lifecycle_provenance') or {}).get('opening_source_event_id') for s in (a,b)]
    if not refs[0] or refs[0]!=refs[1] or not a.get('form_identity') or a['form_identity']!=b.get('form_identity'):return False
    for step in (a,b):
        es={e['event_id']:e for e in step.get('evidence',[])};opening=es.get(refs[0])
        if not opening or refs[0] not in step.get('source_event_ids',[]) or opening['event'].get('action')!='popup_open':return False
        target=opening.get('popup',{}).get('target_popup') or {}
        if not target.get('opened_at') or not target.get('opened_by_event_id'):return False
        for eid in step.get('intent_source_event_ids',[]):
            e=es.get(eid)
            if not e or e['session_id']!=opening['session_id'] or e['page_path']!=opening['page_path'] or e.get('popup',{}).get('active_popup_id')!=target.get('popup_id'):return False
            live=[x for x in e.get('popup_stack',[]) if x.get('popup_id')==target.get('popup_id')]
            if len(live)!=1 or any(live[0].get(k)!=target.get(k) for k in ('opened_at','opened_by_event_id')):return False
    return True
