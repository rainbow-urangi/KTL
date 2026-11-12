"""GT-free raw business-intent abstraction. Model membership IDs are provenance only."""
import copy,hashlib,re
from urllib.parse import urlsplit
from .semantic_enrichment import allowed_event,LEXICON,normalized,pick
from .m02_completion_semantics import affirmative_success,raw_operation_attempt,canonical

VERSION='business-process-abstraction-1.4'
from .m02_generic_preservation import opening_for, nav_click, date_picker_proof, compress
RULES=dict(version=VERSION,input='RAW_EVENTS_PLUS_FROZEN_MEMBERSHIP_IDS_ONLY',
 form='IDENTICAL_PROVEN_BUSINESS_CONTEXT_EXPLICIT_FORM_SESSION_PAGE_MAP_CONTIGUOUS',
 intent='DIRECT_RAW_USER_ACTION_GENERIC_VERBS_AND_EXPLICIT_POPUP_OPENERS',
 input_fields='LOSSLESS_LABEL_ID_NAME_TYPE_SELECTOR_SOURCE_LIST_NO_RAW_VALUES',
 causality='CENTRAL_VALIDATED_OPENER_ALL_EVENT_INTERACTION_REFS_SESSION_PAGE_ORDER_NO_FALLBACK_OR_STALE_OPERATION',
 completion='AFFIRMATIVE_EXPLICIT_UI_OR_POPUP_OPENER_ON_COMMIT_WRITE_ATTRIBUTE_ONLY',
 mechanical='ROUTE_POPUP_FOCUS_HTTP_SUBMIT_OUTCOME_CONTEXT_UNLESS_INDEPENDENT_USER_INTENT',
 http_endpoint='CASE_PRESERVING_PATH_NUMERIC_UUID_SEGMENTS_TYPED_RAW_ENDPOINT_RETAINED',
 ownership='POST_SERIALIZATION_SOURCE_EVENT_IDS_NO_EXECUTION_OR_GT_INPUT',
 graph_trace='SEPARATE_ALL_GRAPH_AND_OCCURRENCE_EVENT_NODE_REFERENCES_NO_CANONICAL_REASSIGNMENT',
 missing='UNKNOWN_INTENT_RETAINED_NO_GUESSED_FORM_CONTEXT_OR_CAUSE',
 recovery='TREE_NAV_EXACT_LABEL;CAPTURED_DIALOG_DESCENDANT_INPUT_SAME_PAGE_OPEN_LIFECYCLE;VALIDATED_FORM_OPENER_CONTEXT;LINKED_SUCCESS_TEXT_NONINTERACTIVE_CONTIGUOUS_PAGE_LIFECYCLE;CALENDAR_CELL_EXPLICIT_CREATE_FORM;DISTINCT_CAUSAL_POPUP_CLOSE;STRUCTURAL_NAV;LIVE_PARENT_STACK;DIRECT_NESTED_DATE_PICKER;LOSSLESS_ADJACENT_COMPRESSION')
RULES_HASH=hashlib.sha256(canonical(RULES)).hexdigest()
WRITES={'SAVE','REGISTER','UPDATE'}

def object_label(title):
    value=(title or '').strip()
    for suffix in ('등록','작성','수정','입력','register','create','edit','input'):
        if normalized(value).endswith(normalized(suffix)) and len(value)>len(suffix):return value[:-len(suffix)].strip()
    return value

def normalized_endpoint(value):
    path=urlsplit(str(value or '')).path
    parts=[]
    for part in path.split('/'):
        if re.fullmatch(r'\d+',part):part='{id}'
        elif re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',part):part='{uuid}'
        parts.append(part)
    return '/'.join(parts)

def raw_atoms(rows):
    result=[]
    for row in rows:
        atom=allowed_event(row);context=row.get('locators_json') or {}
        if isinstance(context,str):
            import json
            context=json.loads(context)
        input_context=context.get('input_context') or {}
        atom['form']=pick(context.get('form_context'),['form_id','form_selector','form_name','purpose'])
        atom['input_form']=pick(input_context,['form_id','form_selector','form_name','form_purpose'])
        atom['input_key']=pick(input_context,['key','code'])
        atom['input_detected']=input_context.get('detected',False)
        atom['popup_containment']=pick(context.get('popup_context'),['is_inside_popup','active_popup_id'])
        atom['element_role']=(context.get('element') or {}).get('role','')
        atom['grid']=pick(context.get('grid_context'),['detected','grid_selector','grid_type','grid_role','cell_value'])
        atom['popup_stack']=[pick(x,['popup_id','opened_at','opened_by_event_id','opened_by_interaction_id']) for x in (context.get('popup_context') or {}).get('stack',[])]
        atom['popup']['target_popup'].update(pick((context.get('popup_context') or {}).get('target_popup'),['opened_at']))
        target=(context.get('popup_context') or {}).get('target_popup') or {}
        atom['popup'].setdefault('target_popup',{}).update(pick(target,['selector_css','selector_xpath','tag','source_action']))
        result.append(atom)
    return result

def menu_context(event):
    menu=event.get('menu') or {}
    if menu.get('source')=='url' or menu.get('parser')=='location_path':return ''
    text=menu.get('selected_path_text') or menu.get('path_text') or ''
    return text.split('>')[-1].strip()

def is_form_popup(popup):
    selector=popup.get('selector_css','')
    return popup.get('tag')=='form' or bool(re.search(r'(^|[ >.#_-])form([ >.#_-]|$)',selector,re.I))

def validated_popup_opener(event,lookup,positions,interactions):
    """Validate recorded references only; no nearest-action/last-user inference."""
    popup=event.get('popup') or {};target=popup.get('target_popup') or {};context=event.get('event') or {}
    if any('fallback' in str(context.get(k,'')).casefold() or 'recent_action' in str(context.get(k,'')).casefold() for k in ('related_strategy','relationship_strategy')):
        return None,'UNVERIFIED_OPENER_STRATEGY'
    event_refs=[popup.get('opener_event_id'),target.get('opened_by_event_id'),target.get('opener_event_id'),context.get('cause_event_id'),context.get('parent_event_id'),context.get('related_event_id')]
    interaction_refs=[popup.get('opener_interaction_id'),target.get('opened_by_interaction_id'),target.get('opener_interaction_id'),context.get('related_interaction_id')]
    candidates=set()
    for reference in event_refs:
        if not reference:continue
        if not isinstance(reference,str) or reference not in lookup:return None,'MISSING_OPENER_SOURCE'
        candidates.add(reference)
    for reference in interaction_refs:
        if not reference:continue
        ids=interactions.get((event['session_id'],reference),set())
        if len(ids)!=1:return None,'AMBIGUOUS_OR_MISSING_OPENER_INTERACTION'
        candidates.update(ids)
    if len(candidates)!=1:return None,'MISSING_OR_CONFLICTING_OPENER_REFERENCES'
    source=lookup[next(iter(candidates))]
    if source['session_id']!=event['session_id'] or not source['page_path'] or source['page_path']!=event['page_path']:
        return None,'INCOMPATIBLE_OPENER_SESSION_PAGE'
    if positions[source['event_id']]>=positions[event['event_id']]:return None,'OPENER_NOT_BEFORE_POPUP'
    return source['event_id'],'VALIDATED_EXPLICIT_POPUP_OPENER'

def original_membership_trace(snapshot,raw_ids):
    """Graph and occurrence roles are trace-only, never canonical map assignment."""
    graph={};occurrences={};unresolved=[]
    for collection,target,role in [('graph_evidence',graph,'ORIGINAL_GRAPH_PROVENANCE_ONLY'),('source_occurrence_evidence',occurrences,'ORIGINAL_OCCURRENCE_PROVENANCE_ONLY')]:
        for i,record in enumerate(snapshot.get(collection,[])):
            for j,eid in enumerate(record.get('source_event_evidence',[])):
                ref=dict(source_path=collection+'['+str(i)+'].source_event_evidence['+str(j)+']',
                    source_event_id=eid,node_id=record.get('node_id'),process_model_id=record.get('process_model_id'),relationship_role=role)
                if collection=='source_occurrence_evidence':ref.update(process_instance_id=record.get('process_instance_id'),step_order=record.get('step_order'))
                if eid in raw_ids:target.setdefault(eid,[]).append(ref)
                else:unresolved.append(dict(ref,reason='SOURCE_EVENT_NOT_IN_RAW_LEDGER'))
    return graph,occurrences,unresolved

def abstract(snapshot,rows):
    events=raw_atoms(rows);lookup={e['event_id']:e for e in events}
    if len(lookup)!=len(events):raise ValueError('Duplicate raw event identity')
    if [e['event_id'] for e in events]!=[e['event_id'] for e in snapshot['raw_evidence_ledger']]:raise ValueError('Frozen raw identity/order mismatch')
    positions={e['event_id']:i for i,e in enumerate(events)};membership={};nodes={};workflows={}
    # Ignore all predicted action/label/resolution values. Only structural membership.
    for process in snapshot['processes']:
        pid=process['source_process_id'];workflows[pid]=process['canonical_instance_id']
        for step in process['business_steps']:
            for eid in step['source_event_ids']:
                membership.setdefault(eid,set()).add(pid);nodes.setdefault(eid,set()).update(step['source_node_ids'])
        for item in process['unlinked_technical_evidence']:
            for eid in item['source_event_ids']:
                membership.setdefault(eid,set()).add(pid);nodes.setdefault(eid,set()).update(item.get('source_node_ids',[]))
    graph_memberships,occurrence_memberships,unresolved_references=original_membership_trace(snapshot,set(lookup))
    interactions={}
    for event in events:
        interaction=event['event'].get('interaction_id')
        if interaction:interactions.setdefault((event['session_id'],interaction),set()).add(event['event_id'])
    popups={};opened_by={};popup_open_audit=[];validated_opens={};opener_validation={}
    for event in events:
        popup=(event.get('popup') or {}).get('target_popup') or {};popup_id=popup.get('popup_id')
        if popup_id:
            identity=(event['session_id'],popup_id)
            if identity in popups:
                for key in ('title','selector_css'):
                    if popups[identity].get(key) and popup.get(key) and popups[identity][key]!=popup[key]:raise ValueError('Conflicting captured popup identity')
            popups.setdefault(identity,{}).update(popup)
        if event['event'].get('action')=='popup_open':
            eid,reason=validated_popup_opener(event,lookup,positions,interactions)
            audit=dict(popup_open_event_id=event['event_id'],source_event_id=eid,valid=eid is not None,reason=reason)
            popup_open_audit.append(audit);opener_validation[event['event_id']]=audit
            if eid:
                opened_by.setdefault(eid,[]).append(event)
                if popup_id:validated_opens.setdefault((event['session_id'],popup_id),[]).append((event,eid))
    # A div dialog is a form only when captured editable descendants establish it.
    # No business name, path registry, GT or predicted label participates.
    def active_opening(event):
        return opening_for(event,events,positions)
    dialog_forms={}
    for event in events:
        opening=active_opening(event)
        popup=(opening['popup'].get('target_popup') or {}) if opening else {}
        popup_id=popup.get('popup_id');selector=popup.get('selector_css','')
        if (opening and popup.get('role')=='dialog' and selector
            and event['event'].get('action') in ('input','change','paste')
            and normalized(event.get('tag')) in ('input','textarea','select')
            and ((event.get('selector') or '').startswith(selector+' > ') or
                 (event.get('popup_containment',{}).get('is_inside_popup') is True and event['popup_containment'].get('active_popup_id')==popup_id))):
            dialog_forms.setdefault(opening['event_id'],[]).append(event['event_id'])
    def known_form(event):
        popup=event['popup'].get('target_popup') or {}
        return is_form_popup(popup) or event['event_id'] in dialog_forms
    def form_context(event):
        explicit=event.get('input_form') or event.get('form') or {}
        explicit_id=explicit.get('form_id') or explicit.get('form_selector')
        popup_id=event['popup'].get('active_popup_id')
        opening=active_opening(event)
        popup=(opening['popup'].get('target_popup') or {}) if opening else popups.get((event['session_id'],popup_id),{})
        dialog_key=opening['event_id'] if opening else None
        if explicit_id:key=('EXPLICIT',str(explicit_id),popup_id or '')
        elif popup_id and (is_form_popup(popup) or dialog_key in dialog_forms):key=('FORM_POPUP',popup_id,popup.get('selector_css',''))
        else:return None,'',menu_context(event)
        title=explicit.get('form_purpose') or explicit.get('purpose') or explicit.get('form_name') or popup.get('title','')
        context=menu_context(event)
        if not context:
            eligible=[(opening,reference) for opening,reference in validated_opens.get((event['session_id'],popup_id),[])
                if opening is active_opening(event)]
            if eligible:
                opening,reference=max(eligible,key=lambda pair:positions[pair[0]['event_id']])
                context=menu_context(lookup[reference])
        return (event['session_id'],event['page_path'],*key,normalized(title)),object_label(title),context
    def map_id(event):
        ids=sorted(membership.get(event['event_id'],set()))
        return ids[0] if len(ids)==1 else 'AMBIGUOUS_MODEL_MEMBERSHIP' if ids else 'UNMAPPED_RAW'
    def calendar_selection(event):
        grid=event.get('grid') or {}
        # Structural calendar marker, not a page, BU, date value or GT label.
        marker=grid.get('grid_selector','')
        if not (event['event'].get('action')=='click' and grid.get('detected') is True
            and re.search(r'(^|[. #_>\-])calendar([. #_>\-]|$)',marker,re.I)
            and event.get('element_text') and grid.get('cell_value')==event.get('element_text')
            and not event['popup'].get('active_popup_id')):return None
        opened=opened_by.get(event['event_id'],[])
        if len(opened)!=1 or not known_form(opened[0]):return None
        title=normalized((opened[0]['popup'].get('target_popup') or {}).get('title'))
        if not any(title.endswith(v) for v in (' 등록',' 작성',' register',' create',' add')):return None
        return opened[0]

    def classify(event):
        action=event['event'].get('action');text=normalized(event.get('element_text'));tag=normalized(event.get('tag'));field=event.get('input') or {}
        if action in ('input','change','paste'):
            if (tag=='select' or field.get('type') in ('checkbox','radio','date','datetime-local')) and not form_context(event)[0]:return 'SELECT'
            return 'INPUT'
        if action in ('popup_open','popup_close','page_view','route_change','screen_change','ui_outcome','collector_boot','page_close'):return None
        if event.get('http_method'):return None
        if action=='submit':return 'SUBMIT'
        if action not in ('click','detail_open','result_check'):return None
        if calendar_selection(event) or date_picker_proof(event,events,positions,opener_validation):return 'SELECT'
        if nav_click(event) and event.get('menu',{}).get('source') in ('url','nav','sidebar'):return 'MENU_ENTER'
        if action=='detail_open':return 'DETAIL_OPEN'
        if action=='result_check':return 'RESULT_CHECK'
        if (tag in ('input','textarea','select') or event.get('input_detected')) and field.get('type') not in ('submit','button','checkbox','radio'):return None
        if text in ('취소','cancel'):return 'CANCEL'
        for kind,words in LEXICON.items():
            if text in {normalized(w) for w in words}:return None if kind=='POPUP_CLOSE' else kind
        if text in ('×','x'):return None
        opened=opened_by.get(event['event_id'],[])
        if len(opened)==1:
            popup=opened[0]['popup'].get('target_popup') or {}
            if not known_form(opened[0]) and not affirmative_success(popup.get('title')):return 'DETAIL_OPEN'
        menu=event.get('menu') or {}
        if text and text==normalized(menu.get('selected_label')) and (menu.get('source') in ('nav','sidebar') or (menu.get('source')=='tree' and menu.get('parser')=='generic_dom_tree' and re.search(r'(^| > )nav(?:[.# >]|$)',event.get('selector') or '')) or event.get('element_role')=='menuitem'):return 'MENU_ENTER'
        if text and (tag in ('td','tr') or event.get('element_role') in ('option','gridcell')):return 'SELECT'
        return 'UNRESOLVED'
    steps=[];pending=None;disposition=[];event_step={}
    def add_source(step,event,kind):
        eid=event['event_id']
        if eid not in step['source_event_ids']:
            step['source_event_ids'].append(eid);step['evidence'].append(copy.deepcopy(event))
            step['source_node_ids']=sorted(set(step['source_node_ids'])|nodes.get(eid,set()))
        step.setdefault('evidence_roles',{})[eid]=kind
    for event in events:
        kind=classify(event);pid=map_id(event);form,purpose,context=form_context(event)
        action=event['event'].get('action');eid=event['event_id']
        if kind is None:
            context_conflict=pending and context and pending['business_context'] and normalized(context)!=normalized(pending['business_context'])
            if pending and (context_conflict or pending['form_identity']!=form or action in ('popup_open','popup_close','route_change','page_view','screen_change')):
                # Pure background HTTP/outcome does not carry form state; it does
                # not terminate a form run unless a genuine lifecycle boundary.
                if context_conflict or action in ('popup_open','popup_close','route_change','page_view','screen_change') or (action=='click' and normalized(event.get('tag')) in ('input','textarea','select')):pending=None
            disposition.append(dict(event_id=eid,disposition='CONTEXT_OR_TECHNICAL_EVIDENCE',generated_step_id=None));continue
        if (kind=='INPUT' and pending and form and pending['form_identity']==form and pending['process_id']==pid
                and normalized(context) and normalized(context)==normalized(pending['business_context'])):
            step=pending;add_source(step,event,'INPUT_FIELD');step['intent_source_event_ids'].append(eid)
        else:
            pending=None
            target=event['input'].get('associated_label') or event.get('associated_label') or event.get('element_text') or ''
            if kind=='INPUT' and form:target=purpose or 'FORM_INPUT'
            if kind=='MENU_ENTER':context=event.get('element_text') or context
            step=dict(generated_step_id='BA-'+eid,process_id=pid,workflow_id=workflows.get(pid,''),action_type='UNRESOLVED' if kind=='SUBMIT' else kind,
                intent_phase='UNKNOWN',target=target,target_field_label=target,business_object=purpose if kind=='INPUT' else '',
                menu_page=event['page_path'],page_title=event['page_title'],menu=copy.deepcopy(event['menu']),business_context=context,
                popup_title=popups.get((event['session_id'],event['popup'].get('active_popup_id')),{}).get('title',''),
                form_identity=form,fields=[],source_event_ids=[],intent_source_event_ids=[eid],source_node_ids=[],evidence=[],
                http_evidence=[],completion_evidence=[],serializer_rule_id='BA-INPUT-FORM' if kind=='INPUT' and form else 'BA-TREE-MENU' if kind=='MENU_ENTER' and event['menu'].get('source')=='tree' else 'BA-DIRECT-INTENT',
                resolution_status='UNRESOLVED' if kind in ('UNRESOLVED','SUBMIT') or pid=='AMBIGUOUS_MODEL_MEMBERSHIP' else 'RESOLVED',
                source_process_ids=sorted(membership.get(eid,set())),step_order=0)
            add_source(step,event,'DIRECT_USER_INTENT');steps.append(step)
            picker=date_picker_proof(event,events,positions,opener_validation)
            if picker:
                step['serializer_rule_id']='BA-NESTED-DATE-PICKER-DIRECT-SELECTION'
                step['selection_kind']='DATE_PICKER_DAY'
                step['selection_provenance']=picker
                for key,value in picker.items():
                    if key.endswith('_source_event_id'):add_source(step,lookup[value],'DIRECT_DATE_PICKER_LIFECYCLE')
                parent=lookup[picker['parent_open_source_event_id']]['popup']['target_popup']
                step['business_context']=object_label(parent.get('title',''))
            selection=calendar_selection(event)
            if selection:
                step['serializer_rule_id']='BA-CALENDAR-CELL-CREATE-OPENER'
                step['selection_kind']='CALENDAR_CELL'
                step['selected_cell_text']=event['element_text']
                step['selected_date']=None
                step['selection_provenance']=dict(click_source_event_id=eid,popup_source_event_id=selection['event_id'],raw_calendar_selector=event['grid']['grid_selector'],raw_cell_text=event['element_text'],date_inferred=False)
                add_source(step,selection,'DIRECT_CALENDAR_CREATE_POPUP')
            if kind=='INPUT' and form:pending=step
        opening=active_opening(event)
        if form and opening and known_form(opening):
            step['form_lifecycle_provenance']=dict(rule_id='BA-LIVE-FORM-OPENING',opening_source_event_id=opening['event_id'])
            add_source(step,opening,'LIVE_FORM_CONTEXT')
        if kind=='INPUT' or (kind=='SELECT' and (event['input'].get('id') or event['input'].get('name') or event['input'].get('associated_label'))):
            step['fields'].append(dict(label=event['input'].get('associated_label') or event.get('associated_label'),id=event['input'].get('id'),
                name=event['input'].get('name'),value_type=event['input'].get('type'),selector=event.get('selector'),source_event_id=eid,source_node_ids=sorted(nodes.get(eid,set()))))
        if form and form[2]=='FORM_POPUP':
            identity=(event['session_id'],event['popup'].get('active_popup_id'))
            for opening,reference in validated_opens.get(identity,[]):
                if opening is active_opening(event):
                    step.setdefault('context_provenance',[])
                    item=dict(rule_id='BA-VALIDATED-OPENER-MENU',opener_source_event_id=reference,popup_source_event_id=opening['event_id'],raw_menu=copy.deepcopy(lookup[reference]['menu']),page_path=opening['page_path'])
                    if item not in step['context_provenance']:step['context_provenance'].append(item)
            opening=active_opening(event)
            for proof_id in dialog_forms.get(opening['event_id'] if opening else None,[]):
                step.setdefault('form_detection_evidence',[])
                proof=dict(source_event_id=proof_id,rule_id='BA-DIALOG-DESCENDANT-INPUT',raw_selector=lookup[proof_id]['selector'])
                if proof not in step['form_detection_evidence']:step['form_detection_evidence'].append(proof)
        event_step[eid]=step
        disposition.append(dict(event_id=eid,disposition='BUSINESS_INTENT',generated_step_id=step['generated_step_id']))
    # A registration that explicitly opens an edit form is initiation. Otherwise
    # commit requires prior actual INPUT in identical captured form scope.
    for index,step in enumerate(steps):
        if step['action_type'] in ('SAVE','UPDATE'):step['intent_phase']='COMMIT'
        elif step['action_type']=='REGISTER':
            openings=[e for eid in step['intent_source_event_ids'] for e in opened_by.get(eid,[]) if known_form(e)]
            if len(openings)==1:
                step['intent_phase']='INITIATE'
                add_source(step,openings[0],'VALIDATED_FORM_OPENER_CONTEXT')
                step['serializer_rule_id']='BA-VALIDATED-FORM-OPENER'
            elif openings:step['intent_phase']='UNKNOWN'
            elif (step['form_identity'] and normalized(step['business_context'])
                and any(s['action_type']=='INPUT' and s['form_identity']==step['form_identity']
                    and normalized(s['business_context'])==normalized(step['business_context']) for s in steps[:index])):step['intent_phase']='COMMIT'
    by_interaction={}
    for step in steps:
        for eid in step['intent_source_event_ids']:
            event=lookup[eid];interaction=event['event'].get('interaction_id')
            if interaction:by_interaction.setdefault((event['session_id'],interaction),set()).add(step['generated_step_id'])
    by_id={s['generated_step_id']:s for s in steps};links=[];success_popups={}
    def unique_link(event,ref_ids=(),interaction=None):
        candidates=set()
        for reference in ref_ids:
            if reference:
                if reference not in event_step:return None,'MISSING_CAUSAL_SOURCE'
                candidates.add(event_step[reference]['generated_step_id'])
        if interaction:
            ids=by_interaction.get((event['session_id'],interaction),set())
            if len(ids)!=1:return None,'AMBIGUOUS_INTERACTION'
            candidates.update(ids)
        if len(candidates)!=1:return None,'MISSING_OR_CONFLICTING_CAUSAL_IDS'
        step=by_id[next(iter(candidates))];source=lookup[step['intent_source_event_ids'][-1]]
        if source['session_id']!=event['session_id'] or source['page_path']!=event['page_path'] or positions[source['event_id']]>=positions[event['event_id']]:return None,'INCOMPATIBLE_CAUSAL_CONTEXT'
        return step,'EXPLICIT_CAUSAL_ID'
    def has_pending(step,event):
        start=max(positions[x] for x in step['intent_source_event_ids']);end=positions[event['event_id']]
        for middle in events[start+1:end]:
            if middle['session_id']!=event['session_id'] or middle['page_path']!=event['page_path']:continue
            if (raw_operation_attempt(middle) or classify(middle) in ('UNRESOLVED','CANCEL')) and middle['event_id'] not in step['source_event_ids']:return True
        return False
    for event in events:
        action=event['event'].get('action');eid=event['event_id'];popup=event['popup'].get('target_popup') or {};outcome=event.get('ui_outcome') or {}
        message=outcome.get('message') if action=='ui_outcome' else popup.get('title') if action=='popup_open' else None
        if message and affirmative_success(message):
            refs=[];interaction=None
            if action=='popup_open':refs=[event['popup'].get('opener_event_id'),popup.get('opened_by_event_id'),event['event'].get('cause_event_id')]
            else:interaction=outcome.get('source_interaction_id')
            validated=opener_validation.get(eid) if action=='popup_open' else None
            if action=='popup_open' and (not validated or not validated['valid']):step=None;reason=validated['reason'] if validated else 'MISSING_VALIDATED_POPUP_OPENER'
            else:step,reason=unique_link(event,refs,interaction)
            if step and (step['action_type'] not in WRITES or step['intent_phase']!='COMMIT'):step=None;reason='NOT_COMPLETED_WRITE_INTENT'
            if step and has_pending(step,event):step=None;reason='PENDING_INTERVENING_OPERATION'
            if step:
                add_source(step,event,'COMPLETION_EVIDENCE');step['completion_evidence'].append(dict(source_event_id=eid,raw_order=positions[eid],kind='SUCCESS_POPUP' if action=='popup_open' else 'UI_OUTCOME',message=message,causal_rule=reason))
                if popup.get('popup_id'):success_popups.setdefault((event['session_id'],popup['popup_id']),[]).append((event,step))
            links.append(dict(event_id=eid,kind='COMPLETION',generated_step_id=step['generated_step_id'] if step else None,reason=reason))
        elif event.get('http_method'):
            api=event.get('api') or {};strategy=api.get('related_strategy','')
            if strategy not in ('explicit','explicit_event_id','explicit_interaction_id','correlation_id'):
                links.append(dict(event_id=eid,kind='HTTP',generated_step_id=None,reason='UNVERIFIED_HTTP_STRATEGY'));continue
            step,reason=unique_link(event,[api.get('related_event_id')],api.get('related_interaction_id'))
            method=event['http_method'].upper()
            compatible=step and ((method in ('POST','PUT','PATCH','DELETE') and step['action_type'] in WRITES) or (method in ('GET','HEAD','OPTIONS') and step['action_type'] in ('QUERY','VIEW','DETAIL_OPEN')))
            if compatible:add_source(step,event,'HTTP_EVIDENCE');step['http_evidence'].append(dict(source_event_id=eid,method=method,endpoint=normalized_endpoint(event.get('http_endpoint_raw')),normalized_endpoint=normalized_endpoint(event.get('http_endpoint_raw')),raw_endpoint=event.get('http_endpoint_raw'),status=event.get('http_status'),relationship_strategy=strategy))
            links.append(dict(event_id=eid,kind='HTTP',generated_step_id=step['generated_step_id'] if compatible else None,reason=reason if compatible else 'INCOMPATIBLE_READ_WRITE_INTENT'))
        elif action=='submit':
            step,reason=unique_link(event,[event['event'].get('cause_event_id'),event['event'].get('related_event_id')],event['event'].get('related_interaction_id'))
            if step and step['action_type'] in WRITES and not has_pending(step,event):
                add_source(step,event,'EXPLICIT_SUBMIT_EVIDENCE')
                own=event_step.get(eid)
                if own and own is not step:own['_mechanical_submit_of']=step['generated_step_id']
            links.append(dict(event_id=eid,kind='SUBMIT',generated_step_id=step['generated_step_id'] if step and step['action_type'] in WRITES else None,reason=reason))
    # Acknowledgements require a preceding validated popup in an uninterrupted
    # same-page lifecycle. A reused popup ID is not a durable causal reference.
    def unrelated_form_close(middle,opening,owner):
        # Only the same write can retire its input form while its success popup survives.
        target=middle['popup'].get('target_popup') or {}
        success=opening['popup'].get('target_popup') or {}
        closed=target.get('popup_id');alive=success.get('popup_id')
        if not closed or not alive or closed==alive:return False
        source=lookup[owner['intent_source_event_ids'][-1]]
        if source['popup'].get('active_popup_id')!=closed:return False
        linked,_=unique_link(middle,[middle['popup'].get('closer_event_id'),target.get('closer_event_id'),middle['event'].get('cause_event_id'),middle['event'].get('related_event_id')],middle['popup'].get('closer_interaction_id'))
        if linked is not owner:return False
        matches=[x for x in middle.get('popup_stack',[]) if x.get('popup_id')==alive]
        if len(matches)!=1:return False
        live=matches[0]
        if not success.get('opened_at') or live.get('opened_at')!=success['opened_at']:return False
        if live.get('opened_by_event_id') not in owner['intent_source_event_ids']:return False
        return True

    def acknowledgement_owner(first):
        candidates=[(opening,owner) for opening,owner in success_popups.get(
            (first['session_id'],first['popup'].get('active_popup_id')),[])
            if positions[opening['event_id']]<positions[first['event_id']]]
        if not candidates:return None
        opening,owner=max(candidates,key=lambda pair:positions[pair[0]['event_id']])
        if not first['page_path'] or first['page_path']!=opening['page_path']:return None
        if first['popup'].get('active_popup_title') and normalized(first['popup']['active_popup_title'])!=normalized(opening['popup']['target_popup'].get('title')):return None
        for middle in events[positions[opening['event_id']]+1:positions[first['event_id']]]:
            if middle['session_id']!=first['session_id']:continue
            if middle['event'].get('action')=='popup_close' and middle['page_path']==first['page_path'] and unrelated_form_close(middle,opening,owner):continue
            if (middle['page_path']!=first['page_path'] or
                middle['event'].get('action') in ('popup_open','popup_close','route_change','page_view','screen_change','page_close','collector_boot') or
                classify(middle) is not None or
                (middle['event'].get('action')=='click' and normalized(middle.get('tag')) in ('input','textarea','select'))):return None
        return owner
    kept=[]
    for step in steps:
        first=lookup[step['intent_source_event_ids'][0]]
        owner=acknowledgement_owner(first)
        if owner and (step['action_type']=='CONFIRM' or (
            step['action_type']=='UNRESOLVED' and first['event'].get('action')=='click'
            and normalized(first.get('tag')) in ('div','span','p')
            and not normalized(first.get('element_role'))
            and normalized(first.get('element_text'))==normalized(first['popup'].get('active_popup_title'))
            and affirmative_success(first.get('element_text')))):
            owner['serializer_rule_id']='BA-LINKED-SUCCESS-ACK'
            for eid in step['source_event_ids']:add_source(owner,lookup[eid],'SUCCESS_ACKNOWLEDGEMENT_CONTEXT')
            step['_mechanical_ack_of']=owner['generated_step_id']
        if not step.get('_mechanical_submit_of') and not step.get('_mechanical_ack_of'):kept.append(step)
    kept=compress(kept,lookup,positions,add_source)
    processes=[]
    for pid in dict.fromkeys(s['process_id'] for s in kept):
        own=[s for s in kept if s['process_id']==pid]
        for i,step in enumerate(own,1):
            step['step_order']=i;step['source_event_ids'].sort(key=positions.get)
            step['evidence'].sort(key=lambda e:positions[e['event_id']])
            step['intent_order']=min(positions[e] for e in step['intent_source_event_ids'])
            step['last_intent_order']=max(positions[e] for e in step['intent_source_event_ids'])
            step['source_process_ids']=sorted(set().union(*(membership.get(e,set()) for e in step['source_event_ids'])))
        processes.append(dict(source_process_id=pid,canonical_instance_id=workflows.get(pid,''),business_steps=own,unlinked_technical_evidence=[]))
    final_ids={s['generated_step_id'] for s in kept}
    owners={}
    for step in kept:
        for eid in step['source_event_ids']:owners.setdefault(eid,[]).append(step['generated_step_id'])
    for row in disposition:
        ids=owners.get(row['event_id'],[])
        if ids and (row['disposition']!='BUSINESS_INTENT' or row['generated_step_id'] not in final_ids):
            row.update(disposition='LINKED_SAME_INTENT_EVIDENCE',generated_step_id=ids[0] if len(ids)==1 else None)
        row['generated_step_ids']=ids
        row['source_process_ids']=sorted(membership.get(row['event_id'],set()))
        row['source_node_ids']=sorted(nodes.get(row['event_id'],set()))
        row['source_node_id_role']='CANONICAL_SERIALIZER_MEMBERSHIP'
        row['original_graph_memberships']=copy.deepcopy(graph_memberships.get(row['event_id'],[]))
        row['original_occurrence_memberships']=copy.deepcopy(occurrence_memberships.get(row['event_id'],[]))
    return dict(serializer_version=VERSION,serializer_rules_hash=RULES_HASH,processes=processes,
        raw_evidence_ledger=events,raw_event_disposition=disposition,causal_evidence_links=links,
        popup_opener_validation=popup_open_audit,unresolved_source_references=unresolved_references,
        original_technical_evidence_ledger=[copy.deepcopy(e) for p in snapshot['processes'] for e in p['unlinked_technical_evidence']],
        original_graph_evidence=copy.deepcopy(snapshot.get('graph_evidence',[])),
        original_occurrence_evidence=copy.deepcopy(snapshot.get('source_occurrence_evidence',[])),
        generated_business_step_count=len(kept),technical_evidence_count=snapshot['technical_evidence_count'],
        semantic_readiness='PENDING_INDEPENDENT_VERIFICATION',auxiliary_evidence_counted=False)
