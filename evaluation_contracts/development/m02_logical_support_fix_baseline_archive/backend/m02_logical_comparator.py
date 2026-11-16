"""Evaluation-only logical business procedures. No model/raw/node evidence access.
No physical screen is mandatory unless the authoritative GT declares one. Logical
context, action/intent, target and ordered one-to-one direct evidence ARE mandatory.
"""
import math
import unicodedata

CONTRACT = 'LOGICAL_BUSINESS_PROCEDURE_V1'
VERSION = 'm02-logical-comparator-1'
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
        menu_leaf=menu_leaf,menu_path=path,page_title=step.get('page_title',''),page=step.get('menu_page',''),
        order=step.get('comparison_order',step.get('step_order')),
        eligible=step.get('evidence_type')=='direct' and step.get('matching_eligible') is True
            and step.get('resolution_status')=='RESOLVED')

def context_state(projection, requirement):
    expected={normalize(requirement['logical_context']['name']),
        *(normalize(x) for x in requirement['logical_context'].get('allowed_aliases',[]))}
    if projection['menu_leaf']:
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

def phase(projections,index):
    """GT-free registration phase from final generated business action sequence."""
    current=projections[index]
    identity=normalize(current['menu_leaf'] or current['page_title'] or current['page'])
    if not identity:return 'UNKNOWN'
    def same(p):return normalize(p['menu_leaf'] or p['page_title'] or p['page'])==identity
    before=[]
    for p in reversed(projections[:index]):
        if not same(p):continue
        if p['action'] in WRITE_ACTIONS:break
        before.append(p['action'])
    if 'INPUT' in before:return 'COMMIT'
    seen_input=False
    for p in projections[index+1:]:
        if not same(p):continue
        if p['action']=='INPUT':seen_input=True
        if p['action'] in WRITE_ACTIONS:return 'INITIATE' if seen_input else 'UNKNOWN'
    return 'UNKNOWN'

def candidate_state(projections,index,requirement):
    p=projections[index];role=requirement['logical_role']
    if not p['eligible']:return 'INCOMPATIBLE'
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
        if not any(x['action'] in WRITE_ACTIONS and context_state(x,requirement)=='MATCH' for x in projections[:index]):
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
            if r.get('end_definition')!=source.get('direct_end_definition'):
                raise LogicalSchemaError('End definition must come from authoritative GT')
            if r.get('end_definition') and r['end_definition']!={'kind':'EXPLICIT_END_CONTROL'}:
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
                if r['logical_role']=='END_WORKFLOW' and not r.get('end_definition'):unknown.append('END_REALIZATION_UNSPECIFIED_NO_DIRECT_END_CONTROL')
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
