"""Fixed-catalog required-event presence evaluation; original CSVs stay unchanged.

This DEVELOPMENT policy deliberately does not assert event order or causality.
Evidence contains hashes and CSS/path token hashes, never input values, titles,
request bodies, or observed selectors/URLs. Legacy comparison formats are separate.
"""
from collections import Counter, deque
from copy import deepcopy
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import uuid

from ..evaluators import EvaluationError, require
from .compare import _actual, _canonical_api, _canonical_url, _identifier, _read_json
from .score import FORMULA, TARGET, COUNT_KEYS, LEGACY_FIELDS, measure, token, _safe_cell, _unescape, _same_measurement
from .upload import (EVENT_TYPES, MAPPING_VERSION, REQUIRED_FIELDS, TEXT_INPUT_TYPES,
                     TYPE_MAPPING, category, capture_scope, missing_fields, parse_csv)


FORMAT = 'm01-required-presence-evidence-v3'
POLICY = 'REQUIRED_EVENT_PRESENCE_MAXIMUM_ONE_TO_ONE_V1'
VERSION = 'm01-required-event-presence-dev-v1'
MAX_SESSIONS = 10
MAX_REQUIREMENTS = 64
MAX_ALTERNATIVES = 16
MAX_MATCH_CELLS = 10000000
MAX_EVIDENCE_ROWS = 500000
MAX_CATALOG_BYTES = 256 * 1024
MATCH_FIELDS = ('interaction_type', 'page_url', 'data_testid', 'target_selector',
                'api_path', 'api_method', 'element_tag', 'input_control_type')
ALTERNATIVE_FIELDS = frozenset(('event_type', 'selector_match', 'api_match') + MATCH_FIELDS)
DOM_TYPES = frozenset(('click', 'input', 'select_change', 'submit_save', 'popup', 'key_input'))
GENERIC_SELECTORS = frozenset(('btn', 'button', 'btn-primary', 'btn-secondary', 'primary',
                               'secondary', 'active', 'selected', 'form', 'input', 'modal'))
_SELECTOR_TOKEN = re.compile(r'\[[^\]]*\]|:[A-Za-z_-][\w-]*(?:\([^)]*\))?|[.#]?[A-Za-z_][\w-]*|\s+|[^\s]')
_NTH = re.compile(r':nth-(?:child|of-type)\([1-9][0-9]*\)\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_NTH_TOKENS = frozenset(hashlib.sha256((':nth-' + kind + '(' + str(index) + ')').encode('utf-8')).hexdigest()
                        for kind in ('child', 'of-type') for index in range(1, 201))
EVIDENCE_FIELDS = (('row_kind', 'format_version', 'metadata_key', 'metadata_value') + LEGACY_FIELDS
                   + ('expected_event_id_sha256', 'requirement_sha256', 'alternatives_json', 'matched_alternative',
                      'csv_row', 'actual_event_id', 'actual_event_id_sha256', 'actual_session_id_sha256',
                      'raw_row_sha256', 'raw_event_type', 'raw_interaction_type', 'raw_element_tag',
                      'raw_input_control_type', 'ktl_type', 'missing_fields',
                      'actual_selector_tokens_json', 'actual_api_segments_json')
                   + tuple('required_' + name + '_sha256' for name in REQUIRED_FIELDS)
                   + tuple('actual_' + name + '_sha256' for name in MATCH_FIELDS))


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _catalog():
    from .scenarios import catalog
    return catalog()


def _text(value, label, maximum=1000):
    require(isinstance(value, str) and 0 < len(value) <= maximum and value == value.strip()
            and not any(ord(char) < 32 for char in value), 'Invalid presence ' + label)
    return value


def _selector_tokens(value):
    # Combinator whitespace is insignificant; descendant whitespace is retained.
    value = re.sub(r'\s*([>+~,])\s*', r'\1', re.sub(r'\s+', ' ', value.strip()))
    return _SELECTOR_TOKEN.findall(value) if len(value) <= 8192 else []


def _selector(value):
    _text(value, 'selector')
    require(not any(char in value for char in ('*', '\\', '\x00', '@', '\n', '\r')),
            'Presence selectors require stable literal CSS components')
    attributes = re.findall(r'\[\s*([\w-]+)', value)
    require(all(name.lower() in {'name', 'type', 'role', 'data-testid', 'data-test'} for name in attributes),
            'Presence selector attributes are restricted to stable control identifiers')
    named = re.findall(r'[.#]([A-Za-z_][\w-]*)', value)
    require(named and any(name.lower() not in GENERIC_SELECTORS for name in named),
            'Presence selectors require a specific class or id, with a fixed page URL')
    require(not re.search(r':(?!nth-child\(|nth-of-type\()[A-Za-z-]+', value),
            'Presence selectors do not support inferred or text predicates')
    require(len(_selector_tokens(value)) <= 256, 'Presence selector has too many components')
    return value


def _condition(condition):
    require(isinstance(condition, dict) and 'event_type' in condition
            and set(condition) <= ALTERNATIVE_FIELDS, 'Invalid presence alternative fields')
    require(condition['event_type'] in EVENT_TYPES, 'Presence event_type must be a canonical M01 category')
    result = {'event_type': condition['event_type']}
    for name in MATCH_FIELDS:
        if name in condition:
            result[name] = _text(condition[name], name)
    if 'page_url' in result:
        result['page_url'] = _canonical_url(result['page_url'])
        require(result['page_url'], 'Presence page_url must be an absolute HTTP(S) URL without credentials')
    if 'api_path' in result:
        result['api_path'] = _canonical_api(result['api_path'])
        require(result['api_path'], 'Presence api_path must be an absolute API path')
    for name in ('interaction_type', 'element_tag', 'input_control_type'):
        if name in result:
            result[name] = result[name].lower()
    if 'api_method' in result:
        result['api_method'] = result['api_method'].upper()
        require(re.fullmatch(r'[A-Z]{1,20}', result['api_method']), 'Invalid presence API method')
    if 'target_selector' in result:
        _selector(result['target_selector'])
        result['selector_match'] = condition.get('selector_match', 'exact')
        require(result['selector_match'] in {'exact', 'contains'}, 'Invalid presence selector policy')
    else:
        require('selector_match' not in condition, 'Selector policy needs a selector')
    if 'api_path' in result:
        result['api_match'] = condition.get('api_match', 'exact')
        require(result['api_match'] in {'exact', 'prefix'}, 'Invalid presence API policy')
        require(result['api_match'] != 'prefix' or result['api_path'].strip('/'), 'Root API prefix is too broad')
    else:
        require('api_match' not in condition, 'API policy needs an API path')
    kind = result['event_type']
    if kind in DOM_TYPES:
        require(result.get('page_url') and (result.get('target_selector') or result.get('data_testid')),
                'DOM presence requirements need a fixed page URL and a specific target')
    elif kind == 'navigation':
        require(result.get('page_url'), 'Navigation presence requirements need a fixed page URL')
    elif kind == 'network':
        require(result.get('api_path') and result.get('api_method'), 'Network presence requirements need path and method')
    return result


def _condition_proof(condition):
    result = {'event_type': condition['event_type'],
              'fields': {name: token(condition[name]) for name in MATCH_FIELDS if name in condition}}
    if 'target_selector' in condition:
        result['selector_match'] = condition['selector_match']
        if condition['selector_match'] == 'contains':
            result['selector_tokens'] = [token(part) for part in _selector_tokens(condition['target_selector'])]
    if 'api_path' in condition:
        result['api_match'] = condition['api_match']
        if condition['api_match'] == 'prefix':
            result['api_segments'] = [token(part) for part in condition['api_path'].strip('/').split('/')]
    return result


def _requirements(scenario):
    rows = scenario.get('requirements')
    require(isinstance(rows, list) and 0 < len(rows) <= MAX_REQUIREMENTS, 'Invalid presence requirement count')
    normalized, identities = [], set()
    for item in rows:
        require(isinstance(item, dict) and {'id', 'label', 'alternatives'} <= set(item)
                and set(item) <= {'id', 'label', 'alternatives', 'source_step_indexes', 'definition_basis'},
                'Invalid presence requirement')
        identity = _text(item['id'], 'requirement ID', 120)
        require(identity not in identities, 'Duplicate presence requirement ID')
        identities.add(identity)
        _text(item['label'], 'requirement label', 160)
        alternatives = item['alternatives']
        require(isinstance(alternatives, list) and 0 < len(alternatives) <= MAX_ALTERNATIVES,
                'Invalid presence alternative count')
        normalized.append(dict(id=identity, label=item['label'], alternatives=[_condition(row) for row in alternatives]))
    return normalized


def _requirement_proof(item):
    return dict(id=item['id'], alternatives=[_condition_proof(condition) for condition in item['alternatives']])


def _contains_tokens(expected, actual):
    # Collector-added positional selectors may be ignored only where the fixed
    # requirement did not specify one. Specified field/label positions stay exact.
    for start in range(len(actual)):
        position = start
        for part in expected:
            while position < len(actual) and actual[position] in _NTH_TOKENS and actual[position] != part:
                position += 1
            if position >= len(actual) or actual[position] != part:
                break
            position += 1
        else:
            return True
    return False


def _proof_matches(condition, actual):
    if not actual['actual_event_id_sha256'] or condition['event_type'] != actual['ktl_type']:
        return False
    for name, expected in condition['fields'].items():
        if name == 'target_selector' and condition.get('selector_match') == 'contains':
            if not _contains_tokens(condition['selector_tokens'], actual['_selector_tokens']):
                return False
        elif name == 'api_path' and condition.get('api_match') == 'prefix':
            parts = condition['api_segments']
            if actual['_api_segments'][:len(parts)] != parts:
                return False
        elif expected != actual['actual_' + name + '_sha256']:
            return False
    return True


def _edges(requirements, actual):
    require(len(requirements) * len(actual) <= MAX_MATCH_CELLS, 'Presence comparison exceeds the supported size')
    return [[index for index, event in enumerate(actual)
             if any(_proof_matches(condition, event) for condition in item['alternatives'])]
            for item in requirements]


def _maximum_pairs(edges):
    """Stable augmenting-path assignment; depth is bounded by 64 requirements."""
    occupied = {}

    def augment(requirement, visited):
        for event in edges[requirement]:
            if event in visited:
                continue
            visited.add(event)
            if event not in occupied or augment(occupied[event], visited):
                occupied[event] = requirement
                return True
        return False

    for requirement in range(len(edges)):
        augment(requirement, set())
    return {requirement: event for event, requirement in occupied.items()}


def _independent_maximum(edges):
    # Separate iterative breadth-first checker avoids reusing the producer's DFS.
    assigned, owner = {}, {}
    for origin in range(len(edges)):
        queue, previous, visited = deque([origin]), {}, {origin}
        endpoint = None
        while queue and endpoint is None:
            requirement = queue.popleft()
            for event in edges[requirement]:
                if event in previous:
                    continue
                previous[event] = requirement
                if event not in owner:
                    endpoint = event
                    break
                child = owner[event]
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        if endpoint is not None:
            while True:
                requirement = previous[endpoint]
                old_event = assigned.get(requirement)
                assigned[requirement], owner[endpoint] = endpoint, requirement
                if old_event is None:
                    break
                endpoint = old_event
    return len(assigned)


def _safe_kind(value, allowed):
    value = value.strip().lower()
    return value if value in allowed else 'unknown'


def _actual_proof(raw, number):
    actual = _actual(raw, number)
    # The collector may encode a popup lifecycle in either event_type or
    # interaction_type. This does not turn popup_close into popup_open.
    if not actual['interaction_type'] and raw.get('event_type', '').strip().lower() in {'popup_open', 'popup_close'}:
        actual['interaction_type'] = raw['event_type'].strip().lower()
    actual.update(element_tag=raw.get('element_tag', '').strip().lower(),
                  input_control_type=raw.get('input_control_type', '').strip().lower())
    identity = token(actual['event_id'])
    fields = {name: token(actual.get(name) or '') for name in MATCH_FIELDS}
    result = dict(row_kind='COLLECTED', csv_row=number,
                  actual_event_id='event-' + identity[:16] if identity else '', actual_event_id_sha256=identity,
                  actual_session_id_sha256=token(raw.get('session_id', '')), raw_row_sha256=_sha(_encoded(raw)),
                  raw_event_type=_safe_kind(raw.get('event_type', ''), set(TYPE_MAPPING) | set(EVENT_TYPES) | {'dom_event'}),
                  raw_interaction_type=_safe_kind(raw.get('interaction_type', ''), set(TYPE_MAPPING) | set(EVENT_TYPES)),
                  raw_element_tag=_safe_kind(raw.get('element_tag', ''), {'input', 'textarea', 'select', 'button', 'a', 'div', 'span', 'form', 'body', 'html', 'label', 'section', 'main', 'td', 'th', 'tr', 'option'}),
                  raw_input_control_type=_safe_kind(raw.get('input_control_type', ''), TEXT_INPUT_TYPES | {'textarea', 'select', 'checkbox', 'radio', 'hidden', 'date', 'datetime-local', 'button', 'submit'}),
                  ktl_type=actual['event_type'] or 'unclassified', missing_fields=','.join(missing_fields(raw)))
    result.update({'actual_' + name + '_sha256': value for name, value in fields.items()})
    result.update({'required_' + name + '_sha256': token(raw.get(name, '').strip()) for name in REQUIRED_FIELDS})
    result['_selector_tokens'] = [token(part) for part in _selector_tokens(actual.get('target_selector') or '')]
    result['_api_segments'] = [token(part) for part in (actual.get('api_path') or '').strip('/').split('/')] if actual.get('api_path') else []
    return result


def _truth_report(scenario, requirements, catalog_info):
    expected = []
    for sequence, item in enumerate(requirements, 1):
        first = item['alternatives'][0]
        row = {key: first.get(key, '') for key in ('event_type',) + MATCH_FIELDS}
        row.update(expected_event_id=item['id'], sequence=sequence, label=item['label'], alternatives=item['alternatives'])
        expected.append(row)
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=('expected_event_id', 'sequence', 'label', 'alternatives_json'))
    writer.writeheader()
    writer.writerows(dict(expected_event_id=item['id'], sequence=index, label=item['label'],
                         alternatives_json=_encoded(item['alternatives']).decode('utf-8'))
                     for index, item in enumerate(requirements, 1))
    raw = output.getvalue().encode('utf-8-sig')
    truth = dict(truth_id=_sha(raw)[:32], filename='required_events.csv', sha256=_sha(raw),
                 event_count=len(expected), scenario_name=scenario['scenario_name'], scenario_version=scenario['scenario_version'],
                 source='fixed_required_event_catalog', legacy_csv=False, matching_policy=POLICY, run_mode='DEVELOPMENT',
                 catalog_version=catalog_info['version'], catalog_sha256=catalog_info['sha256'])
    return {'truth': truth, 'expected': expected, 'run_mode': 'DEVELOPMENT'}, raw


def _evidence(result, requirements, comparison_rows, collected):
    proofs = [_requirement_proof(item) for item in requirements]
    published = {name: result['measurement'][name] for name in
                 ('c1', 'c2', 'c3', 'collection_accuracy', 'formula', 'target', 'threshold_met', 'counts', 'field_policy', 'mapping_version')}
    metadata = dict(comparison_id=result['comparison_id'], dataset_id=result['dataset_id'], truth_id=result['truth_id'],
                    scenario_name=result['scenario_name'], scenario_version=result['scenario_version'],
                    collector_csv_sha256=result['input_sha256']['collector_csv'], expected_csv_sha256=result['input_sha256']['expected_csv'],
                    scope_kind='selected_session', session_id_sha256=token(result['session_id']),
                    mapping_version=MAPPING_VERSION, matching_policy=POLICY,
                    catalog_version=result['catalog_version'], catalog_sha256=result['catalog_sha256'],
                    requirements_sha256=_sha(_encoded(proofs)), reported_measurement=_encoded(published).decode('utf-8'))
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=EVIDENCE_FIELDS)
    writer.writeheader()

    def write(row):
        writer.writerow({key: _safe_cell(value) for key, value in dict(row, format_version=FORMAT).items()})

    for name, value in metadata.items():
        write(dict(row_kind='METADATA', metadata_key=name, metadata_value=value))
    for item, proof, comparison in zip(requirements, proofs, comparison_rows):
        write(dict(comparison, row_kind='EXPECTED', expected_event_id_sha256=token(item['id']),
                   requirement_sha256=_sha(_encoded(proof)), alternatives_json=_encoded(proof['alternatives']).decode('utf-8')))
    for actual in collected:
        row = {key: value for key, value in actual.items() if not key.startswith('_')}
        row.update(actual_selector_tokens_json=_encoded(actual['_selector_tokens']).decode('utf-8'),
                   actual_api_segments_json=_encoded(actual['_api_segments']).decode('utf-8'))
        write(row)
    return output.getvalue().encode('utf-8-sig')


def _valid_hash(value, empty=False):
    return (empty and value == '') or (isinstance(value, str) and _HASH.fullmatch(value) is not None)


def _proof_condition(value):
    require(isinstance(value, dict) and set(value) <= {'event_type', 'fields', 'selector_match', 'selector_tokens', 'api_match', 'api_segments'}
            and value.get('event_type') in EVENT_TYPES, 'Invalid evidence presence alternative')
    fields = value.get('fields')
    require(isinstance(fields, dict) and set(fields) <= set(MATCH_FIELDS) and all(_valid_hash(item) for item in fields.values()),
            'Invalid evidence presence condition hashes')
    if value['event_type'] in DOM_TYPES:
        require('page_url' in fields and ('target_selector' in fields or 'data_testid' in fields), 'Incomplete DOM presence evidence')
    elif value['event_type'] == 'navigation':
        require('page_url' in fields, 'Incomplete navigation presence evidence')
    elif value['event_type'] == 'network':
        require('api_path' in fields and 'api_method' in fields, 'Incomplete network presence evidence')
    for name, field, modes, extra in (('selector_match', 'target_selector', {'exact', 'contains'}, 'selector_tokens'),
                                     ('api_match', 'api_path', {'exact', 'prefix'}, 'api_segments')):
        if field in fields:
            require(value.get(name) in modes, 'Invalid evidence matching policy')
            tokenized = value[name] in {'contains', 'prefix'}
            require((extra in value) == tokenized, 'Incomplete evidence token condition')
            if tokenized:
                require(isinstance(value[extra], list) and 0 < len(value[extra]) <= 256
                        and all(_valid_hash(part) for part in value[extra]), 'Invalid evidence condition tokens')
        else:
            require(name not in value and extra not in value, 'Orphan evidence matching policy')
    return value


def verify(raw, result=None):
    """Recalculate v3 matches and C1/C2/C3 using only exported private hashes."""
    require(isinstance(raw, bytes) and 0 < len(raw) <= 128 * 1024 * 1024, 'Presence evidence exceeds the supported size')
    require(result is None or isinstance(result, dict), 'Presence result must be a JSON object')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        require(reader.fieldnames == list(EVIDENCE_FIELDS), 'Unrecognized presence evidence CSV schema')
        rows = []
        for row in reader:
            require(len(rows) <= 100100 and None not in row and all(value is not None for value in row.values()),
                    'Invalid presence evidence row')
            rows.append({name: _unescape(value) for name, value in row.items()})
    except (ValueError, UnicodeError, csv.Error):
        raise EvaluationError('Invalid UTF-8 presence evidence CSV')
    require(rows and all(row['format_version'] == FORMAT and row['row_kind'] in {'METADATA', 'EXPECTED', 'COLLECTED'} for row in rows),
            'Invalid presence evidence format')
    metadata = {}
    for row in rows:
        if row['row_kind'] == 'METADATA':
            require(row['metadata_key'] and row['metadata_key'] not in metadata, 'Duplicate presence evidence metadata')
            metadata[row['metadata_key']] = row['metadata_value']
    require(set(metadata) == {'comparison_id', 'dataset_id', 'truth_id', 'scenario_name', 'scenario_version',
                              'collector_csv_sha256', 'expected_csv_sha256', 'scope_kind', 'session_id_sha256',
                              'mapping_version', 'matching_policy', 'catalog_version', 'catalog_sha256',
                              'requirements_sha256', 'reported_measurement'}, 'Incomplete presence evidence metadata')
    require(metadata['scope_kind'] == 'selected_session' and metadata['matching_policy'] == POLICY
            and metadata['mapping_version'] == MAPPING_VERSION and metadata['catalog_version'], 'Presence evidence policy mismatch')
    for name in ('comparison_id', 'dataset_id', 'truth_id'):
        _identifier(metadata[name], 'presence evidence ' + name)
    require(all(_valid_hash(metadata[name]) for name in ('collector_csv_sha256', 'expected_csv_sha256', 'session_id_sha256', 'catalog_sha256', 'requirements_sha256')),
            'Invalid presence evidence metadata hash')
    expected = [row for row in rows if row['row_kind'] == 'EXPECTED']
    collected = [row for row in rows if row['row_kind'] == 'COLLECTED']
    require(0 < len(expected) <= MAX_REQUIREMENTS and 0 < len(collected) <= 100000, 'Invalid presence evidence counts')
    requirements, identities = [], set()
    for index, row in enumerate(expected, 1):
        identity = row['expected_event_id']
        require(identity and identity not in identities and row['expected_event_id_sha256'] == token(identity)
                and row['sequence'] == str(index), 'Invalid presence evidence requirement identity')
        identities.add(identity)
        try:
            alternatives = json.loads(row['alternatives_json'])
        except (ValueError, RecursionError):
            raise EvaluationError('Invalid presence alternatives JSON')
        require(isinstance(alternatives, list) and 0 < len(alternatives) <= MAX_ALTERNATIVES, 'Invalid presence alternative count')
        proof = dict(id=identity, alternatives=[_proof_condition(item) for item in alternatives])
        require(row['requirement_sha256'] == _sha(_encoded(proof)), 'Presence requirement hash mismatch')
        requirements.append(proof)
    require(metadata['requirements_sha256'] == _sha(_encoded(requirements)), 'Presence requirement collection hash mismatch')
    numbers, unique, seen_ids, missing, types = {}, [], {}, Counter(), Counter()
    last_row = 1
    for row in collected:
        require(re.fullmatch(r'[1-9][0-9]{0,8}', row['csv_row']), 'Invalid presence source row number')
        number = int(row['csv_row'])
        require(number > last_row, 'Presence collected source rows must remain in original order')
        last_row = number
        require(all(_valid_hash(row[name], empty=True) for name in row if name.endswith('_sha256') and name != 'requirement_sha256')
                and _valid_hash(row['raw_row_sha256']), 'Invalid presence event hash')
        require(row['actual_session_id_sha256'] == metadata['session_id_sha256'], 'Presence evidence mixes sessions')
        kind = category(dict(event_type=row['raw_event_type'], interaction_type=row['raw_interaction_type'],
                             element_tag=row['raw_element_tag'], input_control_type=row['raw_input_control_type']))
        require(row['ktl_type'] == (kind or 'unclassified'), 'Presence category evidence mismatch')
        missing_here = [name for name in REQUIRED_FIELDS if not row['required_' + name + '_sha256']]
        require(row['missing_fields'] == ','.join(missing_here), 'Presence missing-field evidence mismatch')
        missing.update(missing_here)
        types[kind] += 1
        for field, target in (('actual_selector_tokens_json', '_selector_tokens'), ('actual_api_segments_json', '_api_segments')):
            try:
                parts = json.loads(row[field])
            except (ValueError, RecursionError):
                raise EvaluationError('Invalid presence event token JSON')
            require(isinstance(parts, list) and len(parts) <= 4096 and all(_valid_hash(part) for part in parts),
                    'Invalid presence event tokens')
            row[target] = parts
        identity = row['actual_event_id_sha256']
        require(row['actual_event_id'] == ('event-' + identity[:16] if identity else ''), 'Presence event display identity mismatch')
        if identity in seen_ids and identity:
            require(seen_ids[identity]['raw_row_sha256'] == row['raw_row_sha256'], 'Conflicting presence event IDs')
        else:
            if identity:
                seen_ids[identity] = row
            unique.append(row)
        numbers[number] = row
    used, matched = set(), 0
    for row, requirement in zip(expected, requirements):
        require(row['status'] in {'MATCHED', 'MISSING'}, 'Invalid presence match status')
        if row['status'] == 'MISSING':
            require(not row['matched_event_id'] and not row['matched_csv_row'] and not row['matched_alternative'],
                    'Missing presence requirement claims an event')
            require(row['expected_event_type'] == requirement['alternatives'][0]['event_type'], 'Presence displayed event type mismatch')
            continue
        require(re.fullmatch(r'[1-9][0-9]{0,8}', row['matched_csv_row']) and re.fullmatch(r'0|[1-9][0-9]*', row['matched_alternative']),
                'Invalid presence matched row or alternative')
        actual = numbers.get(int(row['matched_csv_row']))
        alternative = int(row['matched_alternative'])
        require(actual is not None and alternative < len(requirement['alternatives'])
                and _proof_matches(requirement['alternatives'][alternative], actual), 'Presence match does not satisfy the fixed requirement')
        identity = actual['actual_event_id_sha256']
        require(identity not in used and row['matched_event_id'] == actual['actual_event_id']
                and row['expected_event_type'] == requirement['alternatives'][alternative]['event_type'], 'Presence event was reused or misidentified')
        used.add(identity)
        matched += 1
    require(matched == _independent_maximum(_edges(requirements, unique)), 'Presence matches are not a maximum one-to-one assignment')
    counts = dict(defined_required_event_count=len(expected), collected_required_event_count=matched,
                  total_collected_events=len(collected), required_field_count=len(REQUIRED_FIELDS),
                  missing_required_field_count=sum(missing.values()), defined_event_type_count=len(EVENT_TYPES),
                  collected_event_type_count=sum(bool(types[name]) for name in EVENT_TYPES))
    c1 = Fraction(100 * matched, len(expected))
    c2 = Fraction(100 * counts['missing_required_field_count'], len(collected) * len(REQUIRED_FIELDS))
    c3 = Fraction(100 * counts['collected_event_type_count'], len(EVENT_TYPES))
    weighted = Fraction(1, 2) * c1 + Fraction(3, 10) * (100 - c2) + Fraction(1, 5) * c3
    calculated = dict(c1=float(c1), c2=float(c2), c3=float(c3), collection_accuracy=float(weighted),
                      formula=FORMULA, target=TARGET, threshold_met=weighted >= TARGET, counts=counts,
                      field_policy='RAW_REQUIRED_FIELDS', mapping_version=MAPPING_VERSION)
    try:
        published = json.loads(metadata['reported_measurement'])
    except (ValueError, RecursionError):
        raise EvaluationError('Invalid presence published measurement')
    _same_measurement(calculated, published)
    require(published.get('mapping_version') == MAPPING_VERSION, 'Presence published mapping mismatch')
    if result is not None:
        _same_measurement(calculated, result.get('measurement'))
        require(all(metadata[name] == result.get(name) for name in ('comparison_id', 'dataset_id', 'truth_id', 'scenario_name', 'scenario_version', 'catalog_version', 'catalog_sha256', 'matching_policy')),
                'Presence result provenance mismatch')
        require(token(result.get('session_id') or '') == metadata['session_id_sha256']
                and result.get('input_sha256', {}).get('collector_csv') == metadata['collector_csv_sha256']
                and result.get('input_sha256', {}).get('expected_csv') == metadata['expected_csv_sha256'], 'Presence result source hash or session mismatch')
        require(result.get('official_pass') is None and result.get('run_mode') == 'DEVELOPMENT'
                and result.get('summary', {}).get('matched_count') == matched
                and result.get('summary', {}).get('expected_count') == len(expected), 'Presence result count or mode mismatch')
        report = result.get('presence_truth', {})
        native = report.get('expected', [])
        require(len(native) == len(expected), 'Presence result requirements are incomplete')
        reproduced = []
        for item in native:
            reproduced.append(_requirement_proof(dict(id=item['expected_event_id'], label=item['label'],
                                                      alternatives=[_condition(condition) for condition in item['alternatives']])))
        require(reproduced == requirements, 'Presence result and evidence requirements differ')
        require(len(result.get('rows', [])) == len(expected) and all(
            all(str(actual.get(name, '') if actual.get(name) is not None else '') == evidence[name]
                for name in ('expected_event_id', 'sequence', 'expected_event_type', 'matched_event_id', 'matched_csv_row', 'status', 'matched_alternative'))
            for actual, evidence in zip(result['rows'], expected)), 'Presence result and evidence matches differ')
    return dict(status='VERIFIED', verified=True, recalculated=calculated, differences=[], evidence_format=FORMAT,
                evidence_sha256=_sha(raw), matching_policy=POLICY,
                notice='Recalculated from private event hashes, fixed requirement token hashes, and one-to-one maximum presence matching. DEVELOPMENT only.')


class M01PresenceStore:
    def __init__(self, root, session=None):
        self.root = Path(root)
        self.session = session
        self.directory = self.root / 'data/development/m01_comparisons'

    def compare_all(self, payload, config):
        require(isinstance(payload, dict) and {'dataset_id', 'catalog_version', 'catalog_sha256'} <= set(payload)
                and set(payload) <= {'dataset_id', 'session_id', 'catalog_version', 'catalog_sha256'}, 'Presence comparison requires dataset and fixed catalog identity')
        dataset_id = _identifier(payload['dataset_id'], 'dataset ID')
        if self.session:
            self.session.check('CSV', dataset_id)
        current = deepcopy(_catalog())
        require(isinstance(current, dict) and _valid_hash(current.get('sha256')) and isinstance(current.get('version'), str)
                and payload['catalog_version'] == current['version'] and payload['catalog_sha256'] == current['sha256'], 'Presence catalog changed; reload the fixed scenario catalog')
        require(_sha(_encoded({name: value for name, value in current.items() if name != 'sha256'})) == current['sha256'],
                'Presence catalog content hash mismatch')
        require(len(_encoded(current)) <= MAX_CATALOG_BYTES and isinstance(current.get('scenarios'), list)
                and len(current['scenarios']) == 20, 'Presence evaluation requires the fixed 20-scenario catalog')
        scenarios, identities = [], set()
        for scenario in current['scenarios']:
            require(isinstance(scenario, dict), 'Invalid presence scenario')
            identity = _text(scenario.get('scenario_id'), 'scenario ID', 120)
            _text(scenario.get('scenario_name'), 'scenario name', 120)
            _text(scenario.get('scenario_version'), 'scenario version', 80)
            require(identity not in identities, 'Duplicate presence scenario ID')
            identities.add(identity)
            scenarios.append((scenario, _requirements(scenario)))
        folder = self.root / 'data/development/m01_uploads' / dataset_id
        manifest = _read_json(folder / 'manifest.json')
        try:
            raw = (folder / 'source.csv').read_bytes()
        except OSError:
            raise EvaluationError('Stored collector CSV is unavailable')
        require(manifest.get('dataset_id') == dataset_id and manifest.get('run_mode') == 'DEVELOPMENT'
                and _sha(raw) == manifest.get('sha256'), 'Stored collector CSV identity or hash mismatch')
        headers, source_rows = parse_csv(raw)
        scope = capture_scope(source_rows, headers)
        seen, sessions = {}, {}
        for number, row in enumerate(source_rows, 2):
            identity = row.get('event_id', '').strip()
            if identity:
                require(identity not in seen or seen[identity] == row, 'Conflicting rows share an event_id; presence comparison aborted')
                seen[identity] = row
            session_id = row.get('session_id', '')
            require(session_id and session_id == session_id.strip() and len(session_id) <= 1000
                    and not any(ord(char) < 32 for char in session_id), 'Presence evaluation requires nonempty valid session_id on every source row')
            sessions.setdefault(session_id, []).append((number, row))
        selected = payload.get('session_id')
        require(selected is None or (isinstance(selected, str) and selected in sessions), 'Selected collection session is unavailable')
        if selected is not None:
            sessions = {selected: sessions[selected]}
        require(len(sessions) <= MAX_SESSIONS, 'Presence CSV has too many sessions; select a single session')
        require(sum(len(rows) for rows in sessions.values()) * len(scenarios) <= MAX_EVIDENCE_ROWS,
                'Presence evidence exceeds the supported size; select a session or split the CSV')
        require(sum(len(requirements) for _, requirements in scenarios) * sum(len(rows) for rows in sessions.values()) <= MAX_MATCH_CELLS,
                'Presence matching exceeds the supported size; select a session or split the CSV')
        prepared = {}
        for session_id, rows in sessions.items():
            collected = [_actual_proof(row, number) for number, row in rows]
            unique, ids = [], set()
            for actual in collected:
                identity = actual['actual_event_id_sha256']
                if identity and identity in ids:
                    continue
                if identity:
                    ids.add(identity)
                unique.append(actual)
            prepared[session_id] = (rows, collected, unique)
        candidates = []
        catalog_info = {key: value for key, value in current.items() if key != 'scenarios'}
        catalog_info['scenario_count'] = 20
        for scenario, requirements in scenarios:
            truth_report, truth_raw = _truth_report(scenario, requirements, catalog_info)
            proofs = [_requirement_proof(item) for item in requirements]
            for session_id, (scoped_rows, collected, actual) in prepared.items():
                pairs = _maximum_pairs(_edges(proofs, actual))
                comparison_rows = []
                for index, item in enumerate(requirements):
                    event = actual[pairs[index]] if index in pairs else None
                    alternative = next((position for position, condition in enumerate(proofs[index]['alternatives'])
                                        if event is not None and _proof_matches(condition, event)), None)
                    chosen = item['alternatives'][alternative or 0]
                    comparison_rows.append(dict(expected_event_id=item['id'], sequence=index + 1,
                        expected_event_type=chosen['event_type'], expected_page_url=chosen.get('page_url', ''),
                        expected_data_testid=chosen.get('data_testid', ''), expected_target_selector=chosen.get('target_selector', ''),
                        expected_api_path=chosen.get('api_path', ''), expected_api_method=chosen.get('api_method', ''),
                        matched_event_id=event['actual_event_id'] if event else None,
                        matched_csv_row=int(event['csv_row']) if event else None, matched_alternative=alternative,
                        status='MATCHED' if event else 'MISSING',
                        reason=item['label'] + (' · 포함: 고유한 관측 이벤트가 사전 정의한 허용 조건을 충족합니다.' if event
                                               else ' · 누락: 사전 정의한 조건을 충족하는 미사용 이벤트가 없습니다.')))
                matched = len(pairs)
                result = dict(comparison_id=uuid.uuid4().hex, dataset_id=dataset_id, truth_id=truth_report['truth']['truth_id'],
                    scenario_id=scenario['scenario_id'], scenario_name=scenario['scenario_name'], scenario_version=scenario['scenario_version'],
                    created_at=datetime.now(timezone.utc).isoformat(), run_mode='DEVELOPMENT', status='DEVELOPMENT_EVENT_COMPARISON',
                    evaluator_version=VERSION, matching_policy=POLICY, catalog_version=current['version'], catalog_sha256=current['sha256'],
                    session_id=session_id, capture_scope=scope, rows=comparison_rows,
                    summary=dict(expected_count=len(requirements), matched_count=matched, missing_count=len(requirements) - matched,
                                 extra_event_count=len(actual) - matched, duplicate_event_rows=len(collected) - len(actual),
                                 source_event_count=len(source_rows), scoped_unique_event_count=len(actual),
                                 match_rate=100 * matched / len(requirements), score=None, official_pass=None),
                    score=None, official_pass=None, measurement=measure(len(requirements), matched, scoped_rows, session_id),
                    input_sha256=dict(collector_csv=_sha(raw), expected_csv=_sha(truth_raw)), presence_truth=truth_report,
                    notice='Development required-event presence measurement; event order and causal linkage are not evaluated. No official verdict.')
                result['evidence_file'] = '/api/development/m01/comparisons/' + result['comparison_id'] + '/evidence.csv'
                result['verification_file'] = '/api/development/m01/comparisons/' + result['comparison_id'] + '/verification'
                evidence = _evidence(result, requirements, comparison_rows, collected)
                verification = verify(evidence, result)
                directory = self.directory / result['comparison_id']
                directory.mkdir(parents=True, exist_ok=False)
                files = {'result.json': _encoded(result), 'truth.csv': truth_raw,
                         'truth_snapshot.json': _encoded(dict(truth=truth_report['truth'], expected=truth_report['expected'])),
                         'evidence.csv': evidence, 'verification.json': _encoded(verification)}
                for filename, content in files.items():
                    (directory / filename).write_bytes(content)
                record = dict(comparison_id=result['comparison_id'], run_mode='DEVELOPMENT', input_sha256=result['input_sha256'],
                              result_sha256=_sha(files['result.json']), truth_snapshot_sha256=_sha(files['truth_snapshot.json']),
                              evidence_sha256=_sha(evidence), verification_sha256=_sha(files['verification.json']), evidence_format=FORMAT)
                (directory / 'manifest.json').write_bytes(_encoded(record))
                if self.session:
                    self.session.claim('COMPARISON', result['comparison_id'])
                preset = dict(business_unit_id=scenario['scenario_id'], scenario_name=scenario['scenario_name'], scenario_version=scenario['scenario_version'])
                candidates.append(dict(scenario_id=scenario['scenario_id'], scenario_name=scenario['scenario_name'],
                                       scenario_version=scenario['scenario_version'], session_id=session_id, status='COMPLETED',
                                       preset=preset, truth=truth_report, result=result))
        require(_sha((folder / 'source.csv').read_bytes()) == _sha(raw), 'Collector CSV changed during presence evaluation')
        winner = max(candidates, key=lambda candidate: candidate['result']['measurement']['collection_accuracy'])
        return dict(status='COMPLETED', run_mode='DEVELOPMENT', dataset_id=dataset_id, matching_policy=POLICY,
                    catalog=catalog_info, scenario_count=20, evaluated_scenario_count=20,
                    evaluated_session_count=len(sessions), session_count=len(sessions),
                    candidate_count=len(candidates), completed_count=len(candidates), candidates=candidates,
                    session_id=winner['session_id'], representative=winner, result=winner['result'], truth=winner['truth'], official_pass=None)
