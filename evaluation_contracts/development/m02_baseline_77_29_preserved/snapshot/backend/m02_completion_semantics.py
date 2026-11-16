"""Pure GT-independent serializer extension for explicit raw UI completion states.
No route aliases, BU rules, GT or score inputs. Frozen source steps are retained.
"""
import copy
import hashlib
import json
import re
from .semantic_enrichment import LEXICON, normalized

VERSION = 'business-process-serializer-4-semantic-3.1-completion'
RULES = dict(version=VERSION, outcome='ONE_OBSERVED_UI_OUTCOME_ONE_STATE',
    causality='UNIQUE_SAME_SESSION_PAGE_EXPLICIT_WRITE_INTERACTION_ONLY',
    success='COMPLETE_DECLARATIVE_SUCCESS_CLAUSE_NO_CONDITIONAL_FUTURE_MODAL_QUESTION_INSTRUCTION',
    interruption='ALL_CANONICAL_OPERATIONS_AND_RAW_INPUT_SUBMIT_EXACT_WRITE_VERB_OR_UNKNOWN_TYPED_SUBMIT',
    unsupported='RETAIN_RAW_UNRESOLVED_NO_STATE_INVENTION',
    http='GET_AND_WRITE_PRESERVED_AUXILIARY_NO_RECENT_ACTION_PROMOTION',
    context='RAW_ONLY_NO_CURRENT_DEPLOYMENT_ROUTE_REGISTRY',
    conservation='ALL_PRIOR_STEPS_UNCHANGED_NO_DROP_OR_COMPRESSION')

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
RULES_HASH=hashlib.sha256(canonical(RULES)).hexdigest()

def affirmative_success(message):
    """Conservative complete assertions; uncertain language remains raw evidence."""
    if not isinstance(message,str):return False
    text=' '.join(message.casefold().split())
    if re.search(r'실패|오류|취소|않|못|불가|예정|겠|는지|나요|습니까|을\s*수|아마|듯|추정|예상|가능|만약|경우|여부|확인해|주세요|[?？]|\b(?:fail\w*|error\w*|cancel\w*|not|unsuccess\w*|cannot|could|will|would|should|may|might|can|if|whether|please|perhaps|possibly|probably|unless|when|wish|hope|expect|assume|seems|appears)\b',text):return False
    # Clause endings, not partial past-tense stems. Following explanatory clauses
    # are allowed only when no global uncertainty/failure marker exists.
    clauses=[c.strip() for c in re.split(r'[.!。！]+',text) if c.strip()]
    korean=r'[^.!?]*?(?:저장|등록|수정|처리)(?:이|가)?\s*(?:되었습니다|됐습니다|완료되었습니다|완료됐습니다|완료)'
    english=r'(?:[\w -]+?\s+(?:was|were|has been|have been)\s+)?(?:successfully\s+(?:saved|created|registered|updated)|(?:saved|created|registered|updated)\s+successfully)'
    return any(re.fullmatch(korean,c) or re.fullmatch(english,c) for c in clauses)

def raw_operation_attempt(event):
    """Same generic write verb lexicon as semantic enrichment; no endpoint rules.

    Unknown typed submissions remain potential operations. Ordinary lifecycle/UI
    observations do not block an explicitly linked operation's own response.
    """
    action=event.get('event',{}).get('action')
    if action in ('input','change','paste','submit'):return True
    if action not in ('click','pointerup','keydown'):return False
    text=normalized(event.get('element_text') or event.get('associated_label'))
    if any(text in {normalized(v) for v in LEXICON[kind]} for kind in ('SAVE','REGISTER','UPDATE')):return True
    field=event.get('input') or {}
    return normalized(field.get('type'))=='submit'

def extend(snapshot):
    result=copy.deepcopy(snapshot)
    raw=result['raw_evidence_ledger']
    positions={e['event_id']:i for i,e in enumerate(raw)}
    if len(positions)!=len(raw):raise ValueError('Duplicate raw event identity')
    writes={};claimed=set();audit=[]
    for process in result['processes']:
        for step in process['business_steps']:
            claimed.update(step['source_event_ids'])
            if step['action_type'] not in ('SAVE','REGISTER','UPDATE'):continue
            for e in step['evidence']:
                interaction=e['event'].get('interaction_id')
                if interaction:writes.setdefault((e['session_id'],interaction),[]).append((process,step,e))
    for event in raw:
        outcome=event.get('ui_outcome') or {}
        if not outcome:continue
        origin=outcome.get('source_interaction_id')
        candidates=writes.get((event['session_id'],origin),[]) if origin else []
        reason=None
        if event['event_id'] in claimed:reason='ALREADY_CANONICAL_NO_DUPLICATION'
        elif not affirmative_success(outcome.get('message')):reason='OUTCOME_NOT_EXPLICIT_SUCCESS'
        elif len(candidates)!=1:reason='MISSING_OR_AMBIGUOUS_EXPLICIT_WRITE_LINK'
        else:
            process,write,source=candidates[0]
            if not event['page_path'] or source['page_path']!=event['page_path']:reason='PAGE_MEMBERSHIP_UNPROVEN'
            elif positions[source['event_id']]>=positions[event['event_id']]:reason='OUTCOME_NOT_AFTER_WRITE'
            else:
                # An intervening INPUT/write starts or changes an operation; never
                # attach an old success to a new operation merely by proximity.
                intervening=[s for p in result['processes'] for s in p['business_steps']
                    if s['action_type'] in ('INPUT','SAVE','REGISTER','UPDATE','UNRESOLVED')
                    and any(e['session_id']==event['session_id'] and e['page_path']==event['page_path'] for e in s['evidence'])
                    and any(positions[source['event_id']]<positions[x]<positions[event['event_id']] for x in s['source_event_ids'])]
                if any(raw_operation_attempt(e)
                    and e['session_id']==event['session_id'] and e['page_path']==event['page_path']
                    for e in raw[positions[source['event_id']]+1:positions[event['event_id']]]):intervening.append(True)
                if intervening:reason='INTERVENING_OPERATION_AMBIGUITY'
        record=dict(source_event_id=event['event_id'],origin_interaction_id=origin,
            status=reason or 'EXPLICIT_SUCCESS_STATE',rule_id='SEM-EXPLICIT-UI-COMPLETION')
        if reason is None:
            sid='OUTCOME-'+event['event_id']
            state=copy.deepcopy(write)
            state.update(generated_step_id=sid,action_type='RESULT_CHECK',target=outcome['message'],
                target_field_label=outcome['message'],source_event_ids=[event['event_id']],source_node_ids=[],
                evidence=[copy.deepcopy(event)],related_evidence=[],merged_from_event_ids=[],
                serializer_rule_id='SEM-EXPLICIT-UI-COMPLETION',resolution_status='RESOLVED',
                semantic_status='DIRECT_OBSERVED_UI_COMPLETION_STATE',
                completion_observation=dict(kind='SUCCESS_MESSAGE',write_step_id=write['generated_step_id'],
                    write_source_event_ids=write['source_event_ids'],outcome_source_event_ids=[event['event_id']],
                    source_interaction_id=origin,context_source='EXPLICIT_CAUSAL_WRITE_RAW_MENU',
                    inferred_click=False),
                field_provenance=dict(target='raw.ui_outcome.message',page='raw.page_path',
                    context='explicit source_interaction_id -> write raw menu'),
                popup=event['popup'],input_field={},selector=event['selector'],tag=event['tag'],
                split_from=None,field_identity={},step_order=0)
            # Preserve write menu only as causal context, never as source node identity.
            process['business_steps'].append(state);claimed.add(event['event_id'])
            record.update(generated_step_id=sid,write_step_id=write['generated_step_id'])
        audit.append(record)
    for process in result['processes']:
        process['business_steps'].sort(key=lambda s:min(positions[e] for e in s['source_event_ids']))
        for order,step in enumerate(process['business_steps'],1):step['step_order']=order
    result.update(serializer_version=VERSION,serializer_rules_hash=RULES_HASH,
        completion_rule_audit=audit,generated_business_step_count=sum(len(p['business_steps']) for p in result['processes']),
        semantic_readiness='PENDING_INDEPENDENT_VERIFICATION',
        raw_unclaimed_event_ids=[e for e in result.get('raw_unclaimed_event_ids',[]) if e not in claimed])
    return result
