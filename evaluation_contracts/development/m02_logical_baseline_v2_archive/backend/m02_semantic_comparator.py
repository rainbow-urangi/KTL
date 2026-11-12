"""Self-contained, GT-post-hoc business procedure comparator.
Only final generated action/target/screen/order fields can match; raw evidence is
never inspected. Target aliases are local to action + typed screen + procedure.
"""
import math
import unicodedata

CONTRACT = 'ACTION_SCREEN_TARGET_ORDER_V2'
VERSION = 'm02-semantic-comparator-2'
ACTIONS = frozenset(('PAGE_ENTER', 'MENU_ENTER', 'QUERY', 'VIEW', 'DETAIL_OPEN',
    'SELECT', 'INPUT', 'SAVE', 'REGISTER', 'UPDATE', 'CONFIRM', 'RESULT_CHECK',
    'POPUP_OPEN', 'POPUP_CLOSE'))
SCREEN_KINDS = frozenset(('page_path', 'page_title', 'menu_path', 'popup_title'))

class SemanticSchemaError(ValueError):
    pass

def normalize(value):
    if not isinstance(value, str):
        return ''
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())

def normalize_screen(kind, value):
    # URL paths can be case-sensitive; do not casefold or remove internal whitespace.
    return value.strip() if kind == 'page_path' and isinstance(value, str) else normalize(value)

def gt_procedure(step):
    """Require explicit semantics. Never infer action/screen from a GT label."""
    action = step.get('action_type')
    screen = step.get('screen_context')
    label = step.get('target_label', step.get('label'))
    aliases = step.get('allowed_aliases', [])
    if (action not in ACTIONS or not isinstance(screen, dict)
            or screen.get('kind') not in SCREEN_KINDS or not normalize(screen.get('value'))
            or not normalize(label) or not isinstance(aliases, list)
            or any(not normalize(alias) for alias in aliases)
            or type(step.get('step_order')) is not int or step['step_order'] < 1):
        raise SemanticSchemaError('GT_SEMANTIC_SCHEMA_REQUIRED: explicit action_type, typed screen_context, target_label (or label), positive step_order and scoped string aliases required')
    return action, screen['kind'], normalize_screen(screen['kind'], screen['value']), {normalize(label), *(normalize(a) for a in aliases)}

def generated_screen(step, kind):
    # Exact final generated fields only. Never scan raw evidence, source nodes or labels.
    if kind == 'page_path':
        return step.get('menu_page', '')
    if kind == 'page_title':
        return step.get('page_title', '')
    if kind == 'menu_path':
        menu = step.get('menu') or {}
        return menu.get('selected_path_text') or menu.get('path_text') or ''
    if kind == 'popup_title':
        popup = step.get('popup') or {}
        return (popup.get('target_popup') or {}).get('title') or popup.get('active_popup_title') or ''
    return ''

def compatible(step, requirement):
    action, screen_kind, screen_value, targets = requirement
    return (step.get('evidence_type') == 'direct' and step.get('matching_eligible') is True
        and step.get('resolution_status') == 'RESOLVED' and step.get('action_type') == action
        and normalize_screen(screen_kind, generated_screen(step, screen_kind)) == screen_value
        and bool(normalize(step.get('target_field_label')))
        and normalize(step.get('target_field_label')) in targets)

def align(actual, truth, requirements):
    """Deterministic order-preserving, one-to-one maximum alignment; no map selection."""
    n, m = len(actual), len(truth)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            match = 1 + table[i + 1][j + 1] if compatible(actual[i], requirements[j]) else -1
            table[i][j] = max(match, table[i + 1][j], table[i][j + 1])
    i = j = 0
    hits = {}
    while i < n and j < m:
        if compatible(actual[i], requirements[j]) and table[i][j] == 1 + table[i + 1][j + 1]:
            hits[j] = i
            i += 1
            j += 1
        elif table[i + 1][j] > table[i][j + 1]:
            i += 1
        else:
            j += 1  # deterministic tie: retain earlier generated candidate
    return hits

def evaluate(generated, ground_truth):
    processes = generated.get('processes')
    required_processes = ground_truth.get('processes')
    if not isinstance(processes, list) or not isinstance(required_processes, list) or not required_processes:
        raise SemanticSchemaError('Nonempty GT processes and generated process list required')
    def by_id(values):
        result = {}
        for value in values:
            pid = value.get('id')
            if not isinstance(pid, str) or not pid or pid in result:
                raise SemanticSchemaError('Unique nonempty process IDs required')
            result[pid] = value
        return result
    actual_by_id, truth_by_id = by_id(processes), by_id(required_processes)
    total, defined, matched = 0, 0, 0
    evidence, prepared = [], {}
    generated_ids = set()
    for pid, process in actual_by_id.items():
        rows = process.get('procedures')
        if not isinstance(rows, list):
            raise SemanticSchemaError('Generated procedures list required')
        orders = []
        for step in rows:
            sid = step.get('id')
            order = step.get('comparison_order', step.get('step_order'))
            if not sid or sid in generated_ids or type(order) is not int or order < 1:
                raise SemanticSchemaError('Unique generated step IDs and positive comparison order required')
            generated_ids.add(sid)
            orders.append(order)
        if len(orders) != len(set(orders)):
            raise SemanticSchemaError('Ambiguous generated comparison order')
        prepared[pid] = sorted(rows, key=lambda s: s.get('comparison_order', s.get('step_order')))
        total += len(rows)
    # Validate ALL GT before any alignment or metric computation.
    requirements = {}
    for pid, process in truth_by_id.items():
        gt_ids = set()
        rows = process.get('procedures')
        if not isinstance(rows, list) or not rows or any(not isinstance(s, dict) for s in rows):
            raise SemanticSchemaError('Nonempty required procedures required')
        contracts = []
        alias_owners = {}
        for step in rows:
            if not step.get('id') or step['id'] in gt_ids:
                raise SemanticSchemaError('Unique GT procedure IDs required')
            gt_ids.add(step['id'])
            contract = gt_procedure(step)
            for alias in contract[3]:
                key = (*contract[:3], alias)
                owner = normalize(step.get('target_label', step.get('label')))
                if key in alias_owners and alias_owners[key] != owner:
                    raise SemanticSchemaError('Ambiguous aliases within same action/screen')
                alias_owners[key] = owner
            contracts.append((step, contract))
        contracts.sort(key=lambda pair: pair[0]['step_order'])
        if len({s['step_order'] for s, _ in contracts}) != len(contracts):
            raise SemanticSchemaError('Unique GT step order required')
        requirements[pid] = contracts
        defined += len(contracts)
    for pid in dict.fromkeys([*truth_by_id, *actual_by_id]):
        actual = prepared.get(pid, [])
        pairs = requirements.get(pid, [])
        truth = [s for s, _ in pairs]
        hits = align(actual, truth, [c for _, c in pairs])
        matched += len(hits)
        used = set(hits.values())
        for j, required in enumerate(truth):
            step = actual[hits[j]] if j in hits else None
            evidence.append(dict(process_id=pid, required_step_id=required['id'],
                ground_truth_step=required.get('label', required.get('target_label', '')),
                required_action_type=required['action_type'], required_screen_context=required['screen_context'],
                detected_step=step['target_field_label'] if step else '',
                detected_id=step['id'] if step else '', direct_match=step is not None))
        for i, step in enumerate(actual):
            if i not in used:
                evidence.append(dict(process_id=pid, required_step_id='', ground_truth_step='',
                    detected_step=step.get('target_field_label', ''), detected_id=step['id'], direct_match=False))
    if total == 0:
        raise SemanticSchemaError('No generated procedures: measurement unavailable')
    accuracy, completeness = 100 * matched / total, 100 * matched / defined
    return math.sqrt(accuracy * completeness), len(truth_by_id), dict(
        accuracy=accuracy, completeness=completeness, correctly_mapped=matched,
        evaluated_procedures=total, included_required=matched, defined_required=defined,
        formula='sqrt(Accuracy * Completeness)', auxiliary_evidence_counted=False,
        matching_method=CONTRACT), evidence
