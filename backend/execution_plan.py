"""Immutable observed M03 -> explicitly bound execute/check/reference plan.

CSV/manifest evidence supplies identity and native control facts, never input values.
The compiled scenario still passes the existing strict M04 contract validator.
"""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path

from .evaluators import EvaluationError
from . import execution_target_bindings
from .m04.checks import prepare_contract, validate_source_data, _target, _safe_literal, _auth_target


VERSION = 1
_TRUTH = {'ground_truth', 'groundtruth', 'expected_events', 'expected_label', 'gt_steps', 'gt_label',
          'evaluation_pairing', 'match_result', 'm03_evaluation_reference', 'm03_evaluation_references',
          'evaluation_reference', 'reference'}
_TEXT_CONTROLS = {'text', 'search', 'email', 'tel', 'url', 'number', 'date', 'datetime-local',
                  'month', 'week', 'time', 'textarea'}
_MAX_BYTES = 16 * 1024 * 1024


class ObservationBundle(dict):
    """Created by the server-side byte verifier, not accepted as HTTP payload data."""


def _require(condition, reason):
    if not condition:
        raise EvaluationError(reason, 'NOT_READY')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def source_digest(source):
    return hashlib.sha256(encoded(source)).hexdigest()


def _guard(value):
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key).casefold().replace('-', '_').replace(' ', '_')
            _require(name not in _TRUTH and not (name == 'evaluation_only' and item is True),
                     '실행계획에는 평가 정답이나 reference를 넣을 수 없습니다.')
            _guard(item)
    elif isinstance(value, list):
        for item in value:
            _guard(item)
    validate_source_data(value, strict_literals=True)


def _read(root, spec):
    _require(isinstance(spec, dict) and set(spec) == {'path', 'sha256'}
             and isinstance(spec.get('path'), str) and isinstance(spec.get('sha256'), str)
             and len(spec['sha256']) == 64, '관측 원본의 상대 경로와 SHA-256이 필요합니다.')
    root = Path(root).resolve()
    relative = Path(spec['path'])
    _require(not relative.is_absolute() and not relative.drive and relative.parts
             and all(part not in {'.', '..'} for part in relative.parts), '관측 원본은 실행 root 내부 상대 경로여야 합니다.')
    path = root
    for part in relative.parts:
        path /= part
        _require(not path.is_symlink() and path.resolve() == path, '연결된 관측 원본 경로는 허용하지 않습니다.')
    _require(path.is_file() and path.stat().st_size <= _MAX_BYTES, '관측 원본 파일이 없거나 크기 제한을 초과했습니다.')
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == spec['sha256'], '관측 원본 SHA-256이 일치하지 않습니다.')
    return raw


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, '관측 원본 JSON에 중복 키가 있습니다.')
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def load_observations(root, source, plan, config=None):
    """Bind exact original bytes to immutable M03 event/row/session provenance."""
    try:
        return _load_observations(root, source, plan, config)
    except EvaluationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, csv.Error, RecursionError, OverflowError):
        raise EvaluationError('관측 원본 CSV·manifest 형식과 계보를 확인하세요.', 'NOT_READY') from None


def _load_observations(root, source, plan, config):
    _require(isinstance(source, dict) and isinstance(plan, dict), '원본 시나리오와 실행계획 객체가 필요합니다.')
    _require(plan.get('source_scenario_sha256') == source_digest(source), '실행계획의 M03 원본 SHA-256이 다릅니다.')
    specs = plan.get('observation_sources')
    _require(isinstance(specs, dict) and {'csv', 'capture_manifest'} <= set(specs)
             <= {'csv', 'capture_manifest', 'command_trace'}
             and all(isinstance(specs[key], dict) for key in specs), 'CSV와 capture manifest 원본 연결이 필요합니다.')
    _require(specs['csv'].get('sha256') == source.get('source_csv_sha256')
             and specs['capture_manifest'].get('sha256') == source.get('source_capture_manifest_sha256'),
             '실행계획의 관측 SHA가 M03 원본 계보와 다릅니다.')
    raw = _read(root, specs['csv'])
    manifest_raw = _read(root, specs['capture_manifest'])
    manifest = _json(manifest_raw)
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    headers, rows = reader.fieldnames, list(reader)
    required = {'id', 'event_id', 'session_id', 'event_time', 'interaction_type', 'page_url', 'target_selector',
                'element_tag', 'input_control_type', 'locators_json', 'capture_run_id', 'capture_tab_id',
                'capture_frame_id', 'capture_root_tab_id', 'capture_tab_path'}
    _require(headers and len(headers) == len(set(headers)) and required <= set(headers)
             and rows and all(None not in row and all(v is not None for v in row.values()) for row in rows),
             '관측 CSV의 필수 열·행 구조를 확인하세요.')
    _require(isinstance(manifest, dict) and manifest.get('csv_sha256') == specs['csv']['sha256']
             and manifest.get('csv_byte_count') == len(raw) and manifest.get('columns') == headers
             and manifest.get('event_count') == len(rows) and manifest.get('capture_scope_version') == 2
             and manifest.get('active') is False, 'capture manifest와 CSV 바이트·열·건수가 다릅니다.')
    evidence = manifest.get('event_evidence')
    _require(isinstance(evidence, list) and len(evidence) == len(rows), '관측 manifest의 이벤트 근거가 부족합니다.')
    _require(type(manifest.get('target_tab_id')) is int and manifest.get('capture_tab_paths')
             == {str(manifest['target_tab_id']): [manifest['target_tab_id']]},
             '현재 실행계획은 단일 관측 root tab만 지원합니다. 분기 tab을 추측 연결하지 않습니다.')
    by_event, contexts, sequences, sessions = {}, set(), {}, []
    for number, (row, ev) in enumerate(zip(rows, evidence), 1):
        _require(isinstance(ev, dict) and type(ev.get('csv_row')) is int and ev['csv_row'] == number
                 and row['id'] == str(number), '관측 csv_row는 헤더 제외 1기반 원본 ordinal이어야 합니다.')
        _require(all(isinstance(row.get(k), str) and row[k] for k in ('event_id', 'session_id', 'event_time'))
                 and row['event_id'] not in by_event, '관측 이벤트 ID·session·시간 누락 또는 중복이 있습니다.')
        _require(all(ev.get(k) == row[k] for k in ('event_id', 'session_id', 'event_time')),
                 '관측 event ID·session·시간이 manifest와 다릅니다.')
        _require(row['capture_run_id'] == manifest.get('run_id')
                 and row['capture_root_tab_id'] == str(manifest.get('target_tab_id'))
                 and row['capture_tab_id'] == str(ev.get('tab_id'))
                 and row['capture_frame_id'] == str(ev.get('frame_id')), '관측 capture·tab·frame 연결이 다릅니다.')
        contexts.add((row['capture_tab_id'], row['capture_frame_id']))
        _require(len(contexts) == 1, '현재 실행계획은 동시 tab·frame을 추측 연결하지 않습니다.')
        sid, sequence = row['session_id'], ev.get('event_sequence')
        _require(type(sequence) is int and sequence > sequences.get(sid, 0),
                 '관측 event_sequence는 원 session 안에서 유일하게 증가해야 합니다.')
        sequences[sid] = sequence
        if not sessions or sessions[-1]['session_id'] != sid:
            _require(sid not in {entry['session_id'] for entry in sessions}, '교차 session 순서를 추측할 수 없습니다.')
            if sessions:
                _require(rows[number - 2]['interaction_type'] == 'page_close'
                         and row['interaction_type'] == 'collector_boot' and number < len(rows)
                         and rows[number]['session_id'] == sid and rows[number]['interaction_type'] == 'page_view',
                         'session 전환에는 page_close와 새 collector_boot/page_view 근거가 필요합니다.')
            sessions.append(dict(session_id=sid, first_csv_row=number))
        path = _json(row['capture_tab_path'])
        _require(isinstance(path, list) and path and path[0] == manifest.get('target_tab_id')
                 and str(path[-1]) == row['capture_tab_id']
                 and manifest.get('capture_tab_paths', {}).get(row['capture_tab_id']) == path,
                 '관측 tab의 root·opener 계보가 다릅니다.')
        by_event[row['event_id']] = dict(csv_row=number, row=copy.deepcopy(row), evidence=copy.deepcopy(ev))
    steps = source.get('steps')
    _require(isinstance(steps, list) and steps, 'M03 관측 절차가 없습니다.')
    all_ids, occurrences = set(), set()
    for number, step in enumerate(steps, 1):
        ids = step.get('evidence')
        occurrence = step.get('occurrence_id')
        _require(step.get('order') == number and type(step.get('order')) is int
                 and isinstance(ids, list) and ids and len(ids) == len(set(ids))
                 and isinstance(occurrence, str) and occurrence and occurrence not in occurrences,
                 'M03 관측 order·occurrence·event 근거가 필요합니다. node ID로 역추정하지 않습니다.')
        occurrences.add(occurrence)
        _require(all(eid in by_event and eid not in all_ids for eid in ids), 'M03 관측 근거가 원본에 없거나 중복됩니다.')
        _require(step.get('source_csv_rows') == [by_event[eid]['csv_row'] for eid in ids]
                 and all(step.get('source_session_id') == by_event[eid]['row']['session_id'] for eid in ids),
                 'M03 원본의 event·csv_row·session 계보가 다릅니다.')
        all_ids.update(ids)
    bindings = execution_target_bindings.load(root, source, plan, manifest, rows, config,
        read=_read, parse_json=_json, raw_files=dict(csv=raw, capture_manifest=manifest_raw))
    return ObservationBundle(rows=copy.deepcopy(rows), rows_by_event_id=by_event,
        csv_sha256=specs['csv']['sha256'], capture_manifest_sha256=specs['capture_manifest']['sha256'],
        source_scenario_sha256=source_digest(source), observation_sources=copy.deepcopy(specs),
        execution_target_bindings=bindings)


def _selectors(row):
    choices = {row.get('target_selector', '')}
    locators = _json(row['locators_json']) if row.get('locators_json') else {}
    if isinstance(locators, dict) and isinstance(locators.get('selector_css'), str):
        choices.add(locators['selector_css'])
    key = row.get('target_key', '')
    if key.startswith('css:'):
        choices.add(key[4:])
    return {value.strip() for value in choices if isinstance(value, str) and value.strip()}


def _execute(action, target, observed):
    rows = [item['row'] for item in observed]
    kinds = {row['interaction_type'] for row in rows}
    if action in {'open', 'navigate'}:
        _require(kinds <= {'page_view', 'route_change'} and target.get('url')
                 and all(row['page_url'] == target['url'] for row in rows),
                 'open/navigate에는 실제 page_view·route_change와 동일한 원본 URL이 필요합니다.')
        return
    _require('value' in target and all(target['value'] in _selectors(row) for row in rows),
             '실행 selector는 해당 원본 event의 CSS 근거와 정확히 같아야 합니다.')
    if action == 'click':
        _require(kinds == {'click'}, 'click 변환에는 실제 원본 click 이벤트가 필요합니다.')
    elif action in {'input', 'type', 'clear'}:
        _require(kinds <= {'input', 'change', 'paste'}
                 and all(row['element_tag'].lower() in {'input', 'textarea'}
                         and row['input_control_type'].lower() in _TEXT_CONTROLS for row in rows)
                 and not _auth_target(target), '입력에는 원본 native 입력 종류와 CSS 근거가 필요합니다.')
    elif action == 'select':
        _require(kinds <= {'change', 'input'} and all(row['element_tag'].lower() == 'select'
                 and row['input_control_type'].lower() in {'select-one', 'select-multiple', 'select'} for row in rows),
                 'select 변환에는 실제 native select 근거가 필요합니다.')
    elif action == 'submit':
        _require(kinds == {'submit'}, 'submit 변환에는 실제 submit 이벤트가 필요합니다.')
    else:
        _require(False, '원본 근거로 입증되지 않은 동작으로 변환할 수 없습니다.')


def _parameters(plan):
    _require(plan.get('parameter_source') == 'NEW_TEST_PARAMETERS' and isinstance(plan.get('parameters'), dict),
             '새 시험 매개변수의 출처와 parameters 객체를 명시하세요.')
    result = copy.deepcopy(plan['parameters'])
    for name, value in result.items():
        _require(isinstance(name, str) and name and len(name) <= 64 and isinstance(value, str) and len(value) <= 2000,
                 '시험 매개변수 이름과 문자열 값을 확인하세요.')
        _require(not any(marker in value.casefold() for marker in ('[redacted', '[masked', '<redacted', '<masked', '[숨김', '[마스킹')),
                 '마스킹된 원본을 시험 입력값으로 복원하거나 사용할 수 없습니다.')
        _safe_literal(value)
    return result


def _checks(values, parameters):
    _require(isinstance(values, list) and values, '실행·확인 항목마다 기존 typed checks가 필요합니다.')
    bound = copy.deepcopy(values)
    for condition in bound:
        _require(isinstance(condition, dict), 'typed check 객체가 필요합니다.')
        if 'expected_param' in condition:
            name = condition.pop('expected_param')
            _require('expected' not in condition and isinstance(name, str) and name in parameters,
                     'expected_param은 새 시험 매개변수 하나를 참조해야 합니다.')
            condition['expected'] = parameters[name]
    return bound


def prepare(source, plan, config=None, *, observations=None):
    """Pure compilation after load_observations; no I/O, GPT or browser calls."""
    try:
        return _prepare(source, plan, config, observations)
    except EvaluationError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise EvaluationError('실행계획의 동작·기대 결과·계보 형식을 확인하세요.', 'NOT_READY') from None


def _prepare(source, plan, config, observations):
    _require(isinstance(plan, dict) and set(plan) <= {'version', 'source_scenario_sha256', 'observation_sources',
             'parameter_source', 'parameters', 'items', 'source_mapping'} and type(plan.get('version')) is int
             and plan['version'] == VERSION, '지원하는 실행계획 version과 필드를 확인하세요.')
    _guard(plan)
    _require(isinstance(observations, ObservationBundle), '서버가 검증한 관측 원본 bundle이 필요합니다.')
    digest = source_digest(source)
    _require(plan.get('source_scenario_sha256') == digest == observations.get('source_scenario_sha256')
             and plan.get('observation_sources') == observations.get('observation_sources'),
             'M03 원본 또는 검증된 관측 연결이 실행계획과 다릅니다.')
    parameters = _parameters(plan)
    items = plan.get('items')
    _require(isinstance(items, list) and items and len(items) <= 1000, '분류한 실행계획 items가 필요합니다.')
    sources = {step['order']: step for step in source['steps']}
    expected_ids = {eid for step in source['steps'] for eid in step['evidence']}
    used, mapping, definitions, steps, normalized_items = set(), [], [], [], []
    previous_row, execute_count = 0, 0
    for index, item in enumerate(items, 1):
        _require(isinstance(item, dict) and item.get('kind') in {'execute', 'check', 'reference'},
                 '관측 항목을 execute/check/reference로 명시하세요.')
        kind = item['kind']
        allowed = {'kind', 'source_refs'} | ({'reason'} if kind == 'reference' else {'target', 'expected_result', 'checks'})
        if kind == 'execute':
            allowed |= {'action', 'value_param', 'target_binding_id'}
        _require(set(item) <= allowed, '실행계획 분류에 지원하지 않는 필드가 있습니다.')
        refs = item.get('source_refs')
        _require(isinstance(refs, list) and refs, '원본 order와 event ID의 source_refs가 필요합니다.')
        observed, linked, ids = [], [], []
        for ref in refs:
            _require(isinstance(ref, dict) and set(ref) == {'order', 'event_ids'}
                     and type(ref.get('order')) is int and ref['order'] in sources
                     and isinstance(ref.get('event_ids'), list) and ref['event_ids'],
                     'source_refs는 원본 order와 event_ids를 명시해야 합니다.')
            original = sources[ref['order']]
            for eid in ref['event_ids']:
                _require(isinstance(eid, str) and eid in original['evidence'] and eid not in used,
                         '원본 event 근거가 없거나 실행계획에 중복 분류되었습니다.')
                used.add(eid)
                record = observations['rows_by_event_id'][eid]
                observed.append(record)
                ids.append(eid)
            linked.append(dict(source_order=ref['order'], source_occurrence_id=original['occurrence_id'],
                source_node_id=original.get('node_id', original.get('id')), event_ids=copy.deepcopy(ref['event_ids']),
                source_csv_rows=[observations['rows_by_event_id'][eid]['csv_row'] for eid in ref['event_ids']],
                source_session_ids=list(dict.fromkeys(observations['rows_by_event_id'][eid]['row']['session_id'] for eid in ref['event_ids']))))
        positions = [entry['csv_row'] for entry in observed]
        _require(positions == sorted(set(positions)) and positions[0] > previous_row,
                 '실행계획은 원본 capture ordinal을 뒤바꾸거나 시간으로 재배열할 수 없습니다.')
        previous_row = positions[-1]
        mapped = dict(plan_item=index, kind=kind, source_refs=linked, execution_order=None)
        normalized_items.append(copy.deepcopy(item))
        if kind == 'reference':
            _require(isinstance(item.get('reason'), str) and item['reason'].strip() and len(item['reason']) <= 2000,
                     '참조 관측을 실행하지 않는 이유를 명시하세요.')
            mapping.append(mapped)
            continue
        action = item.get('action') if kind == 'execute' else 'verify'
        target = _target(item.get('target'))
        if kind == 'execute':
            if 'target_binding_id' in item:
                _require(action == 'click' and not _auth_target(target),
                         '승인 archive target binding은 인증 입력이 아닌 실제 click에만 사용할 수 있습니다.')
                mapped['target_binding'] = execution_target_bindings.approved_action(
                    item['target_binding_id'], target, observed, observations, config)
            else:
                _execute(action, target, observed)
            execute_count += 1
        expected = item.get('expected_result')
        _require(isinstance(expected, str) and expected.strip() and len(expected) <= 2000,
                 '독립 업무 정의에 따른 실행 기대 결과가 필요합니다.')
        order = len(steps) + 1
        step = dict(order=order, action=action, target=target.get('url', target.get('value')), expected_result=expected)
        if action in {'open', 'navigate'}:
            step['url'] = target['url']
        if action in {'input', 'type', 'select'}:
            name = item.get('value_param')
            _require(isinstance(name, str) and name in parameters, '입력값은 별도의 새 시험 매개변수로 바인딩해야 합니다.')
            step['value'] = parameters[name]
        else:
            _require('value_param' not in item, '이 동작은 value_param을 받을 수 없습니다.')
        steps.append(step)
        definitions.append(dict(order=order, action=action, target=target, checks=_checks(item.get('checks'), parameters)))
        mapped['execution_order'] = order
        mapping.append(mapped)
    _require(used == expected_ids, '모든 M03 관측 event를 execute/check/reference로 빠짐없이 분류하세요.')
    _require(execute_count > 0 and steps, '실제 실행 동작과 독립 검사가 있는 계획이 필요합니다.')
    effective = copy.deepcopy(source)
    effective['steps'] = steps
    effective['execution_contract'] = dict(version=1, scenario_id=source['scenario_id'], steps=definitions)
    contract = prepare_contract(effective, config)
    effective['execution_contract'] = copy.deepcopy(contract)
    normalized = dict(version=VERSION, source_scenario_sha256=digest,
        observation_sources=copy.deepcopy(plan['observation_sources']), parameter_source='NEW_TEST_PARAMETERS',
        parameters=parameters, items=normalized_items, source_mapping=mapping)
    if 'source_mapping' in plan:
        _require(plan['source_mapping'] == mapping, '저장된 실행계획의 원본 occurrence 연결이 다릅니다.')
    return dict(scenario=effective, contract=contract, execution_plan=normalized)
