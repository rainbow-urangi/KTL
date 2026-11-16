"""Pure, allowlisted GT-independent semantic boundary restoration.
No file IO, execution labels, TD-04, aliases, scores or model calls are inputs.
"""
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from .business_process_serializer import serialize, canonical_bytes

VERSION = 'business-process-serializer-4-semantic-2'
# Exact, generic UI verbs. No business names, BU IDs, endpoints or event exceptions.
LEXICON = {
    'SAVE': ['저장', 'save'], 'REGISTER': ['등록', 'register', '추가', 'add'],
    'UPDATE': ['수정', 'update', '변경 적용'], 'QUERY': ['조회', '검색', 'search', 'query'],
    'VIEW': ['보기', 'view'], 'DETAIL_OPEN': ['상세', '상세 보기', 'details'],
    'CONFIRM': ['확인', 'confirm', 'ok'], 'RESULT_CHECK': ['결과 확인', 'check result'],
    'POPUP_CLOSE': ['닫기', 'close', '취소', 'cancel'],
    'SELECT': ['선택', 'select'],
}
RULES = {'version': VERSION, 'lexicon': LEXICON,
    'split': 'ONE_RAW_EVENT_ATOM_BEFORE_ANY_MERGE',
    'compression': 'ADJACENT_SAME_EXPLICIT_INTERACTION_COMPLETE_ID_NAME_TYPE_SELECTOR_LABEL_INPUT_ONLY',
    'http': 'EVIDENCE_ONLY_NO_RECENT_ACTION_CAUSAL_PROMOTION',
    'missing': 'UNRESOLVED_RETAINED', 'sidecars': 'ALLOWLISTED_LEDGER_NO_COMPLETION_INFERENCE'}
RULES_HASH = hashlib.sha256(canonical_bytes(RULES)).hexdigest()

def pick(value, keys):
    value = value if isinstance(value, dict) else {}
    return {k: copy.deepcopy(value[k]) for k in keys if k in value}

def allowed_event(row):
    """Never copies raw_payload, analysis, task IDs, values or arbitrary nested data."""
    context = row.get('locators_json', {})
    if isinstance(context, str):
        context = json.loads(context or '{}')
    if not isinstance(context, dict):
        raise ValueError('Invalid raw context')
    element = context.get('element') or {}
    event = pick(context.get('event_context'), ['interaction_id', 'action', 'event_sequence', 'event_time'])
    popup = pick(context.get('popup_context'), ['active_popup_id', 'active_popup_title', 'lifecycle_action'])
    popup['target_popup'] = pick((context.get('popup_context') or {}).get('target_popup'),
        ['popup_id', 'title', 'role', 'opener_event_id', 'closer_event_id', 'opener_interaction_id', 'closer_interaction_id'])
    api = pick(context.get('api_context'), ['method', 'path', 'status', 'related_strategy'])
    return {
        'event_id': str(row['event_id']), 'session_id': str(row['session_id']),
        'event_time': row.get('event_time', ''), 'event': event,
        'page_title': row.get('page_title', ''),
        'page_path': urlsplit(row.get('page_url', '')).path,
        'element_text': row.get('element_text', '') or element.get('element_text', ''),
        'associated_label': row.get('associated_label', '') or element.get('associated_label', ''),
        'selector': row.get('target_selector', '') or element.get('selector_css', ''),
        'tag': row.get('element_tag', '') or element.get('element_tag', ''),
        'input': pick(context.get('input_context'), ['id', 'name', 'type', 'associated_label']),
        'popup': popup,
        'menu': pick(context.get('menu_context'), ['selected_label', 'path_text', 'selected_path_text', 'parser', 'source']),
        'ui_outcome': pick(context.get('ui_outcome'), ['message', 'source_interaction_id', 'type']),
        'http_method': row.get('api_method', '') or api.get('method', ''),
        'http_endpoint_raw': row.get('api_path', '') or api.get('path', ''),
        'http_status': row.get('api_status_code', '') or api.get('status', ''),
        'http_relationship_strategy': api.get('related_strategy', ''),
    }

def normalized(text):
    return ' '.join(str(text or '').strip().casefold().split())

def classify(event, source_action):
    action = event['event'].get('action', '')
    target = event['input'].get('associated_label') or event['associated_label'] or event['element_text'] or ''
    if source_action == 'input' or action in ('input', 'change', 'paste'):
        field = event['input'].get('associated_label') or event['associated_label'] or event['input'].get('id') or event['input'].get('name') or ''
        return ('INPUT' if field and field not in ('[REDACTED]', '[IDENTITY_CONTEXT]') else 'UNRESOLVED', field, 'SEM-INPUT')
    if action in ('popup_open', 'popup_close'):
        return ('POPUP_OPEN' if action == 'popup_open' else 'POPUP_CLOSE',
                event['popup'].get('target_popup', {}).get('title') or event['popup'].get('active_popup_title') or target, 'SEM-POPUP')
    if source_action == 'page_entry' or action in ('page_view', 'route_change'):
        return ('PAGE_ENTER', event['page_title'] or event['page_path'], 'SEM-PAGE')
    text = normalized(event['element_text'])
    candidates = [kind for kind, words in LEXICON.items() if text in [normalized(w) for w in words]]
    if len(candidates) == 1:
        return candidates[0], event['element_text'], 'SEM-EXACT-VERB'
    if source_action == 'selection' and target and event['selector']:
        return 'SELECT', target, 'SEM-TYPED-SELECTION'
    if source_action == 'detail_open' and target:
        return 'DETAIL_OPEN', target, 'SEM-TYPED-DETAIL'
    return 'UNRESOLVED', target, 'SEM-UNRESOLVED'

def field_identity(event, label):
    field = event['input']
    return {key: value or '' for key, value in dict(selector=event['selector'],
        id=field.get('id'), name=field.get('name'), type=field.get('type'), label=label).items()}

def enrich(models, nodes, occurrences, raw_events):
    base = serialize(models, nodes, occurrences)  # validates frozen occurrence binding
    raw = [allowed_event(r) for r in raw_events]
    lookup = {r['event_id']: r for r in raw}
    if len(lookup) != len(raw):
        raise ValueError('Ambiguous raw event ID')
    positions = {r['event_id']: i for i, r in enumerate(raw)}
    claimed = set()
    for process in base['processes']:
        steps = []
        for original in process['business_steps']:
            for eid in sorted(original['source_event_ids'], key=lambda x: positions.get(x, -1)):
                if eid not in lookup:
                    raise ValueError('Missing raw source event: ' + eid)
                event = lookup[eid]
                if event['session_id'] != original['occurrence_evidence'].get('source_session_id', event['session_id']):
                    raise ValueError('Raw source session mismatch')
                category, label, rule = classify(event, original['source_action'])
                # Boundary restoration uses raw semantic atoms, never execution ownership.
                atom = {k: copy.deepcopy(v) for k, v in original.items() if k not in ('evidence', 'graph_node_evidence', 'occurrence_evidence')}
                atom.update(action_type=category, target=label, target_field_label=label,
                    menu_page=event['page_path'], page_title=event['page_title'], menu=event['menu'],
                    popup=event['popup'], input_field=event['input'], selector=event['selector'], tag=event['tag'],
                    source_event_ids=[eid], evidence=[event],
                    split_from=original['generated_step_id'], business_unit_ownership='NOT_ASSIGNED_PRE_SCOPE',
                    process_id=process['source_process_id'], workflow_id=process['canonical_instance_id'],
                    serializer_rule_id=rule, semantic_status='UNRESOLVED' if category == 'UNRESOLVED' else 'DIRECT_GENERATED_SEMANTIC_ACTION',
                    resolution_status='UNRESOLVED' if category == 'UNRESOLVED' else 'RESOLVED',
                    field_provenance={'target': 'raw.input.associated_label|raw.associated_label|raw.element_text', 'page': 'raw.page_url'},
                    merged_from_event_ids=[], field_identity=field_identity(event, label))
                prior = steps[-1] if steps else None
                interaction = event['event'].get('interaction_id')
                def key(s):
                    e = s['evidence'][-1]
                    return (e['session_id'], e['page_path'], e['popup'].get('active_popup_id'),
                        s['field_identity'], e['event'].get('interaction_id'))
                if (prior and category == prior['action_type'] == 'INPUT' and interaction
                        and event['selector'] and (atom['field_identity']['id'] or atom['field_identity']['name'])
                        and key(prior) == key(atom)
                        and positions[eid] == positions[prior['source_event_ids'][-1]] + 1
                        and prior['source_instance_id'] == atom['source_instance_id']):
                    prior['source_event_ids'].append(eid)
                    prior['source_node_ids'] = list(dict.fromkeys(prior['source_node_ids'] + atom['source_node_ids']))
                    prior['evidence'].append(event)
                    prior['merged_from_event_ids'].append(eid)
                    prior['serializer_rule_id'] = 'SEM-INPUT-SAME-INTERACTION'
                else:
                    steps.append(atom)
                claimed.add(eid)
        for order, step in enumerate(steps, 1):
            step.update(generated_step_id=f"{process['source_process_id']}-C{order:03d}", step_order=order)
        process['business_steps'] = steps
        for evidence in process['unlinked_technical_evidence']:
            evidence['raw_evidence'] = []
            for eid in evidence['source_event_ids']:
                if eid not in lookup:
                    raise ValueError('Missing HTTP source event')
                evidence['raw_evidence'].append(lookup[eid])
                claimed.add(eid)
    interactions = {}
    for p in base['processes']:
        for step in p['business_steps']:
            for interaction in {e['event'].get('interaction_id') for e in step['evidence']}:
                if interaction:
                    interactions.setdefault(interaction, []).append(step)
    for event in raw:
        origin = event['ui_outcome'].get('source_interaction_id')
        candidates = interactions.get(origin, [])
        if origin and len(candidates) == 1 and candidates[0]['evidence'][0]['session_id'] == event['session_id']:
            candidates[0].setdefault('related_evidence', []).append(dict(event, relationship_status='EXPLICIT_OUTCOME_INTERACTION_EVIDENCE_ONLY'))
    # Preserve all sidecars, including outcome messages and noncanonical events.
    # They are not promoted to generated business steps or direct matches.
    base.update(serializer_version=VERSION, serializer_rules_hash=RULES_HASH,
        generated_business_step_count=sum(len(p['business_steps']) for p in base['processes']),
        raw_evidence_ledger=raw, raw_unclaimed_event_ids=[e['event_id'] for e in raw if e['event_id'] not in claimed],
        merge_policy=RULES['compression'], denominator_policy='POST_GENERATION_EXECUTION_SCOPE_REQUIRED',
        semantic_readiness='PENDING_INDEPENDENT_VERIFICATION')
    return base
