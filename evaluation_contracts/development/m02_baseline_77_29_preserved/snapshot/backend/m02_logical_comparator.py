"""Evaluation-only logical business procedures. No model/raw/node evidence access.
No physical screen is mandatory unless the authoritative GT declares one. Logical
context, action/intent, target and ordered one-to-one direct evidence ARE mandatory.
"""
import math
import unicodedata

CONTRACT = 'LOGICAL_BUSINESS_PROCEDURE_V1'
VERSION = 'm02-logical-comparator-2-completion'
ROLES = frozenset(('ENTER_CONTEXT','SELECT_OBJECT','INPUT_INFORMATION','INITIATE_REGISTRATION',
    'COMMIT_REGISTRATION','SAVE_INFORMATION','INSPECT_COMPLETION','END_WORKFLOW'))
WRITE_ACTIONS = frozenset(('SAVE','REGISTER','UPDATE'))

class LogicalSchemaError(ValueError):
    pass

class LogicalMeaningIncomplete(ValueError):
    def __init__(self, uncertainties):
        self.uncertainties = uncertainties
        super().__init__('LOGICAL_COMPARISON_INCOMPARABLE: '+ '; '.join(
            item['required_step_id']+':'+item['reason'] for item in uncertainties))

def normalize(value):
    return ''.join(unicodedata.normalize('NFKC',value).casefold().split()) if isinstance(value,str) else ''

def subject(value, role):
    """Symmetric grammatical action suffix removal; not a new alias dictionary."""
    text=normalize(value)
    suffixes={'SELECT_OBJECT':('선택','select'),'INPUT_INFORMATION':('입력','input')}.get(role,())
    for suffix in suffixes:
        if text.endswith(suffix) and len(text)>len(suffix):return text[:-len(suffix)]
    return text

def final_projection(step):
    """Reads ONLY final action/target/menu/page/order and eligibility, never evidence."""
    menu=step.get('menu') if isinstance(step.get('menu'),dict) else {}
    path=menu.get('selected_path_text') or menu.get('path_text') or ''
    menu_leaf=path.split('>')[-1].strip() if isinstance(path,str) else ''
    return dict(id=step.get('id'),action=step.get('action_type'),
        target=step.get('target_field_label',step.get('target','')),execution_ids=step.get('execution_ids',[]),
        menu_leaf=menu_leaf,menu_path=path,menu_source=menu.get('source',''),menu_parser=menu.get('parser',''),completion=step.get('completion_observation'),page_title=step.get('page_title',''),page=step.get('menu_page',''),
        order=step.get('comparison_order',step.get('step_order')),
        eligible=step.get('evidence_type')=='direct' and step.get('matching_eligible') is True
            and step.get('resolution_status')=='RESOLVED')

def context_state(projection, requirement):
    expected={normalize(requirement['logical_context']['name']),
        *(normalize(x) for x in requirement['logical_context'].get('allowed_aliases',[]))}
    if projection.get('menu_source')=='url' or projection.get('menu_parser')=='location_path':
        logical='UNKNOWN'  # URL namespace is not a human menu; no historical translation guessed.
    elif projection['menu_leaf']:
        logical='MATCH' if normalize(projection['menu_leaf']) in expected else 'CONFLICT'
    elif normalize(projection['page_title']) in expected or normalize(projection['page']) in expected:
        logical='MATCH'
    else:
        logical='UNKNOWN'  # no guessed URL translation or wildcard for missing menu
    physical=requirement.get('physical_screen')
    if physical:
        field={'page_path':'page','page_title':'page_title','menu_path':'menu_path','popup_title':'target'}.get(physical['kind'])
        value=projection.get(field,'') if field else ''
        if physical['kind']=='popup_title' and projection['action'] not in ('POPUP_OPEN','POPUP_CLOSE'):value=''
        if not value:return 'UNKNOWN'
        if physical['kind']=='page_path':
            if value.strip()!=physical['value'].strip():return 'CONFLICT'
        elif normalize(value)!=normalize(physical['value']):return 'CONFLICT'
    return logical

def support_context_state(support,reference):
    """GT-free SAME/DIFFERENT/UNKNOWN logical context, never page-string inequality.

    A different explicit menu proves conflict. A generic/missing page title does
    not prove that an INPUT/write belongs to another logical business context.
    """
    identity=normalize(reference['menu_leaf'] or reference['page_title'] or reference['page'])
    if not identity:return 'UNKNOWN'
    support_url=support.get('menu_source')=='url' or support.get('menu_parser')=='location_path'
    reference_url=reference.get('menu_source')=='url' or reference.get('menu_parser')=='location_path'
    if (support_url or reference_url) and support.get('page') and support['page']==reference.get('page'):
        return 'MATCH'  # Operation membership only, never a GT menu translation.
    if support_url or reference_url:return 'UNKNOWN'
    if support['menu_leaf']:
        return 'MATCH' if normalize(support['menu_leaf'])==identity else 'CONFLICT'
    if identity in {normalize(support['page_title']),normalize(support['page'])}:return 'MATCH'
    return 'UNKNOWN'

def support_relation(support,reference):
    context=support_context_state(support,reference)
    left,right=support.get('execution_ids',[]),reference.get('execution_ids',[])
    known_execution=(isinstance(left,list) and isinstance(right,list)
        and len(left)==len(right)==1 and isinstance(left[0],str) and bool(left[0])
        and isinstance(right[0],str) and bool(right[0]))
    if context=='CONFLICT' or (known_execution and left!=right):return 'CONFLICT'
    if context=='UNKNOWN' or not known_execution:return 'UNKNOWN'
    return 'MATCH'

def phase_affecting(projection):
    return projection['action'] in WRITE_ACTIONS or projection['action'] in ('INPUT','UNRESOLVED',None)

def phase(projections,index):
    """GT-free phase with direct support proof and explicit uncertainty propagation.

    Prefix states mean possible INPUT since the last verified operation boundary.
    REGISTER is a registration boundary here, NOT evidence of a completed write.
    An unknown INPUT cannot establish COMMIT or be skipped to establish INITIATE.
    A later verified INPUT/boundary may eliminate earlier irrelevant uncertainty.
    """
    current=projections[index]
    if current['action']!='REGISTER' or not current['eligible']:return 'UNKNOWN'
    possible={False}
    for support in projections[:index]:
        if not phase_affecting(support):continue
        relation=support_relation(support,current)
        if relation=='CONFLICT':continue
        if relation=='MATCH' and support['eligible']:
            if support['action']=='INPUT':possible={True}
            elif support['action'] in WRITE_ACTIONS:possible={False}
            else:possible={False,True}
        elif not support['eligible'] or support['action'] in ('UNRESOLVED',None):
            possible={False,True}
        elif support['action']=='INPUT':possible.add(True)
        elif support['action'] in WRITE_ACTIONS:possible.add(False)
    if possible=={True}:return 'COMMIT'
    if possible!={False}:return 'UNKNOWN'
    seen_input=False
    for position in range(index+1,len(projections)):
        support=projections[position]
        if not phase_affecting(support):continue
        relation=support_relation(support,current)
        if relation=='CONFLICT':continue
        if relation!='MATCH' or not support['eligible']:
            # An eligible INPUT with unknown membership supplies no positive proof;
            # a later verified INPUT can still suffice. Possible write/bad support
            # may truncate the operation, so it cannot be ignored.
            if support['eligible'] and support['action']=='INPUT':continue
            return 'UNKNOWN'
        if support['action']=='INPUT':seen_input=True
        elif support['action'] in WRITE_ACTIONS:
            if not seen_input:return 'UNKNOWN'
            return 'INITIATE' if verified_write_state(projections,position,current)=='VERIFIED' else 'UNKNOWN'
        else:return 'UNKNOWN'
    return 'UNKNOWN'

def verified_write_state(projections,index,reference):
    """Shared completed-write proof; no GT, raw outcomes or future save shortcut."""
    support=projections[index]
    if support['action'] not in WRITE_ACTIONS:return 'NOT_WRITE'
    relation=support_relation(support,reference)
    if relation=='CONFLICT':return 'DIFFERENT'
    if relation!='MATCH' or not support['eligible']:return 'UNKNOWN'
    if support['action'] in ('SAVE','UPDATE'):return 'VERIFIED'
    value=phase(projections,index)
    if value=='COMMIT':return 'VERIFIED'
    if value=='INITIATE':return 'NOT_WRITE'
    return 'UNKNOWN'

def completion_scope_state(projections,index):
    """A check needs a completed write in its current logical operation.

    Registration start or a pending/ambiguous INPUT/write cannot be skipped to use
    a stale earlier save. A support write may use a different physical page; only
    its independently explicit logical context/execution must be the same.
    """
    reference=projections[index]
    for position in range(index-1,-1,-1):
        support=projections[position]
        if not phase_affecting(support):continue
        if support_relation(support,reference)=='CONFLICT':continue
        state=verified_write_state(projections,position,reference)
        if state=='VERIFIED':return 'VERIFIED'
        # No verified completed write after this relevant pending/unknown operation.
        return 'UNKNOWN'
    return 'UNKNOWN'

def candidate_state(projections,index,requirement):
    p=projections[index];role=requirement['logical_role']
    if not p['eligible']:return 'INCOMPATIBLE'
    state_role=role in ('END_WORKFLOW','INSPECT_COMPLETION')
    observation=p.get('completion')
    if state_role and observation:
        if p['action']!='RESULT_CHECK' or observation.get('kind')!='SUCCESS_MESSAGE':return 'INCOMPATIBLE'
        ctx=context_state(p,requirement)
        if ctx!='MATCH':return 'UNKNOWN_CONTEXT' if ctx=='UNKNOWN' else 'INCOMPATIBLE'
        write_index=next((j for j,x in enumerate(projections[:index]) if x['id']==observation.get('write_step_id')),None)
        if write_index is None or verified_write_state(projections,write_index,p)!='VERIFIED':return 'UNKNOWN_COMPLETION_SCOPE'
        if completion_scope_state(projections,index)!='VERIFIED':return 'UNKNOWN_COMPLETION_SCOPE'
        return 'MATCH'
    if role=='END_WORKFLOW' and requirement.get('end_definition')=={'kind':'NORMAL_COMPLETION_STATE'}:
        return 'UNKNOWN_COMPLETION_STATE'
    if role=='INSPECT_COMPLETION' and not observation:
        return ('UNKNOWN_COMPLETION_SCOPE' if completion_scope_state(projections,index)!='VERIFIED' else 'UNKNOWN_COMPLETION_STATE') if p['action']=='RESULT_CHECK' else 'INCOMPATIBLE'
    allowed={'ENTER_CONTEXT':{'PAGE_ENTER','MENU_ENTER'},'SELECT_OBJECT':{'SELECT'},
        'INPUT_INFORMATION':{'INPUT'},'INITIATE_REGISTRATION':{'REGISTER'},
        'COMMIT_REGISTRATION':{'REGISTER'},'SAVE_INFORMATION':{'SAVE'},
        'INSPECT_COMPLETION':{'RESULT_CHECK'},'END_WORKFLOW':{'SELECT','CONFIRM'}}[role]
    if p['action'] not in allowed:return 'INCOMPATIBLE'
    if requirement.get('declared_action_type') and p['action']!=requirement['declared_action_type']:return 'INCOMPATIBLE'
    forms=[requirement['source_label'],*requirement['allowed_aliases']]
    if role=='ENTER_CONTEXT':
        target_ok=normalize(p['target']) in {normalize(x) for x in forms} or context_state(p,requirement)=='MATCH'
    else:
        target_ok=bool(subject(p['target'],role)) and subject(p['target'],role) in {subject(x,role) for x in forms}
    if not target_ok:return 'INCOMPATIBLE'
    ctx=context_state(p,requirement)
    if ctx!='MATCH':return 'UNKNOWN_CONTEXT' if ctx=='UNKNOWN' else 'INCOMPATIBLE'
    if role in ('INITIATE_REGISTRATION','COMMIT_REGISTRATION'):
        value=phase(projections,index)
        if value=='UNKNOWN':return 'UNKNOWN_REGISTRATION_PHASE'
        if value!=('INITIATE' if role=='INITIATE_REGISTRATION' else 'COMMIT'):return 'INCOMPATIBLE'
    if role=='INSPECT_COMPLETION':
        # A direct result check is separate from an acknowledgement/passive outcome.
        if completion_scope_state(projections,index)!='VERIFIED':
            return 'UNKNOWN_COMPLETION_SCOPE'
    if role=='END_WORKFLOW' and index!=len(projections)-1:return 'INCOMPATIBLE'
    return 'MATCH'

def validate_truth(truth,sidecar):
    if sidecar.get('contract')!=CONTRACT:raise LogicalSchemaError('Logical contract mismatch')
    declarations=sidecar.get('processes')
    if not isinstance(declarations,list):raise LogicalSchemaError('Logical role declarations required')
    if len({p['id'] for p in truth['processes']})!=len(truth['processes']):raise LogicalSchemaError('Duplicate GT process ID')
    by_id={p['id']:p for p in declarations}
    if len(by_id)!=len(declarations) or set(by_id)!={p['id'] for p in truth['processes']}:
        raise LogicalSchemaError('GT/sidecar process identities differ')
    result={}
    for process in truth['processes']:
        rows=process['procedures'];declared=by_id[process['id']]['procedures']
        if not rows or len(rows)!=len(declared):raise LogicalSchemaError('Required procedures changed')
        if len({s['id'] for s in rows})!=len(rows):raise LogicalSchemaError('Duplicate GT step ID')
        if any(type(s.get('step_order')) is not int or s['step_order']<1 for s in rows):
            raise LogicalSchemaError('Positive source step order required')
        if len({s['step_order'] for s in rows})!=len(rows):raise LogicalSchemaError('Duplicate source step order')
        alias_owners={};requirements=[]
        for source,r in zip(rows,declared):
            if (r.get('required_step_id')!=source['id'] or r.get('source_label')!=source['label']
                or r.get('source_order')!=source['step_order'] or r.get('allowed_aliases')!=source.get('allowed_aliases',[])):
                raise LogicalSchemaError('GT identity/label/order/aliases changed')
            context=r.get('logical_context')
            if r.get('logical_role') not in ROLES or not isinstance(context,dict) or not normalize(context.get('name')):
                raise LogicalSchemaError('Logical action/context unresolved; no wildcards permitted')
            if (context['name']!=source.get('menu_screen_name')
                or context.get('allowed_aliases',[])!=source.get('menu_screen_aliases',[])):
                raise LogicalSchemaError('Logical menu names/aliases must be conserved from authoritative GT')
            if r.get('declared_action_type')!=source.get('action_type'):
                raise LogicalSchemaError('Authoritative action constraint changed')
            declared_actions={'ENTER_CONTEXT':{'PAGE_ENTER','MENU_ENTER'},'SELECT_OBJECT':{'SELECT'},
                'INPUT_INFORMATION':{'INPUT'},'INITIATE_REGISTRATION':{'REGISTER'},'COMMIT_REGISTRATION':{'REGISTER'},
                'SAVE_INFORMATION':{'SAVE'},'INSPECT_COMPLETION':{'RESULT_CHECK'},'END_WORKFLOW':{'SELECT','CONFIRM'}}
            if r.get('declared_action_type') and r['declared_action_type'] not in declared_actions[r['logical_role']]:
                raise LogicalSchemaError('Authoritative action conflicts with logical role; no guess permitted')
            if r.get('end_definition')!=(source.get('direct_end_definition') or ({'kind':'NORMAL_COMPLETION_STATE'} if r['logical_role']=='END_WORKFLOW' else None)):
                raise LogicalSchemaError('End definition must come from authoritative GT')
            if r.get('end_definition') and r['end_definition'] not in ({'kind':'EXPLICIT_END_CONTROL'},{'kind':'NORMAL_COMPLETION_STATE'}):
                raise LogicalSchemaError('Unsupported end declaration; no inferred termination')
            if not isinstance(r['allowed_aliases'],list) or any(not normalize(x) for x in r['allowed_aliases']):
                raise LogicalSchemaError('Invalid scoped aliases')
            if r.get('physical_screen')!=source.get('screen_context'):
                raise LogicalSchemaError('Physical constraint may only come from authoritative GT')
            if r.get('physical_screen') and (r['physical_screen'].get('kind') not in ('page_path','page_title','menu_path','popup_title')
                or not normalize(r['physical_screen'].get('value'))):
                raise LogicalSchemaError('Unsupported/empty physical constraint')
            for alias in [r['source_label'],*r['allowed_aliases']]:
                key=(r['logical_role'],normalize(context['name']),subject(alias,r['logical_role']))
                owner=subject(r['source_label'],r['logical_role'])
                if key in alias_owners and alias_owners[key]!=owner:raise LogicalSchemaError('Ambiguous scoped alias')
                alias_owners[key]=owner
            requirements.append(r)
        result[process['id']]=sorted(requirements,key=lambda r:r['source_order'])
    return result

def align(states):
    n=len(states);m=len(states[0]) if states else 0
    table=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n-1,-1,-1):
        for j in range(m-1,-1,-1):
            hit=1+table[i+1][j+1] if states[i][j]=='MATCH' else -1
            table[i][j]=max(hit,table[i+1][j],table[i][j+1])
    hits={};i=j=0
    while i<n and j<m:
        if states[i][j]=='MATCH' and table[i][j]==1+table[i+1][j+1]:hits[j]=i;i+=1;j+=1
        elif table[i+1][j]>table[i][j+1]:i+=1
        else:j+=1
    return hits

def evaluate(generated,truth,sidecar):
    requirements=validate_truth(truth,sidecar)  # full GT contract before alignment/metrics
    processes=generated.get('processes')
    if not isinstance(processes,list):raise LogicalSchemaError('Generated process list required')
    actual={p['id']:p for p in processes}
    if len(actual)!=len(processes):raise LogicalSchemaError('Duplicate generated process ID')
    total=defined=matches=0;evidence=[];uncertainties=[];seen_ids=set()
    for pid in dict.fromkeys([*requirements,*actual]):
        steps=actual.get(pid,{}).get('procedures',[])
        projections=[final_projection(s) for s in steps]
        if any(not p['id'] or p['id'] in seen_ids or type(p['order']) is not int or p['order']<1 for p in projections):
            raise LogicalSchemaError('Unique generated IDs and positive comparison order required')
        if len({p['id'] for p in projections})!=len(projections) or len({p['order'] for p in projections})!=len(projections):
            raise LogicalSchemaError('Duplicate generated ID/order')
        seen_ids.update(p['id'] for p in projections)
        projections.sort(key=lambda p:p['order']);req=requirements.get(pid,[])
        if req and projections:
            if any(not isinstance(p['execution_ids'],list) or len(p['execution_ids'])!=1 or not isinstance(p['execution_ids'][0],str) or not p['execution_ids'][0] for p in projections):
                raise LogicalSchemaError('Unique assigned execution identity required; no cross-execution matching')
            if len({p['execution_ids'][0] for p in projections})!=1:
                raise LogicalSchemaError('Multiple executions require a fixed evaluation identity contract; no best-instance selection')
        total+=len(projections);defined+=len(req)
        states=[[candidate_state(projections,i,r) for r in req] for i in range(len(projections))]
        hits=align(states);matches+=len(hits);used=set(hits.values())
        for j,r in enumerate(req):
            hit=projections[hits[j]] if j in hits else None
            if hit is None:
                unknown=sorted({row[j] for row in states if row[j].startswith('UNKNOWN')})
                if r['logical_role']=='END_WORKFLOW' and r.get('end_definition')!={'kind':'EXPLICIT_END_CONTROL'}:unknown.append('NORMAL_COMPLETION_STATE_EVIDENCE_UNAVAILABLE_OR_UNALIGNED')
                if unknown:uncertainties.append(dict(process_id=pid,required_step_id=r['required_step_id'],reason='|'.join(unknown)))
            evidence.append(dict(process_id=pid,required_step_id=r['required_step_id'],
                ground_truth_step=r['source_label'],required_logical_role=r['logical_role'],
                required_logical_context=r['logical_context']['name'],
                detected_step=hit['target'] if hit else '',detected_id=hit['id'] if hit else '',direct_match=hit is not None))
        evidence.extend(dict(process_id=pid,required_step_id='',ground_truth_step='',
            detected_step=p['target'],detected_id=p['id'],direct_match=False) for i,p in enumerate(projections) if i not in used)
    # Incomparable source/semantic evidence is never silently scored as zero.
    if uncertainties:raise LogicalMeaningIncomplete(uncertainties)
    if not total or not defined:raise LogicalSchemaError('No generated/required procedures; measurement unavailable')
    accuracy=100*matches/total;completeness=100*matches/defined
    return math.sqrt(accuracy*completeness),len(requirements),dict(accuracy=accuracy,completeness=completeness,
        correctly_mapped=matches,evaluated_procedures=total,included_required=matches,defined_required=defined,
        formula='sqrt(Accuracy * Completeness)',auxiliary_evidence_counted=False,matching_method=CONTRACT),evidence
