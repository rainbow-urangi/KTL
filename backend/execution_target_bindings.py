"""Reviewed archive associations, never inferred descendants or direct causal IDs.

Only trusted runtime configuration can authorize a specific click target override.
Original CSV/manifest/trace/index/summary bytes remain immutable.
"""
import copy
from datetime import datetime
import hashlib
import json

from .evaluators import EvaluationError


ASSOCIATION = 'REVIEWED_ARCHIVED_COMMAND_COMPLETION_WINDOW'
CLOCK = 'PREVIOUS_COMPLETION_LT_EVENT_LE_CURRENT_COMPLETION'
_FILES = {'collection_index', 'final_index', 'command_trace', 'attempt_summary', 'next_attempt_summary', 'command_logger'}
_ARCHIVE_PATHS = {'command_trace', 'attempt_summary', 'next_attempt_summary', 'command_logger', 'csv', 'capture_manifest'}
_FIELDS = {'version', 'business_unit_id', 'source_scenario_sha256', 'capture_run_id', 'target_tab_id',
           'event_id', 'csv_row', 'element_tag', 'observed_target', 'command_target', 'command_index',
           'capture_start_index', 'next_capture_start_index', 'association_method', 'clock_policy',
           'files', 'archive_paths', 'review_evidence_sha256'}


def _require(condition, message):
    if not condition:
        raise EvaluationError(message, 'NOT_READY')


def digest(value):
    return hashlib.sha256((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                     allow_nan=False) + '\n').encode('utf-8')).hexdigest()


def registry(config):
    options = (config or {}).get('m07', {})
    return options.get('execution_target_bindings', {}) if isinstance(options, dict) else {}


def _utc(value):
    _require(isinstance(value, str) and value.endswith('Z'), 'archive 명령 시각은 원 UTC 완료 시각이어야 합니다.')
    return datetime.fromisoformat(value[:-1] + '+00:00')


def load(root, source, plan, manifest, rows, config, *, read, parse_json, raw_files):
    ids = {item.get('target_binding_id') for item in plan.get('items', [])
           if isinstance(item, dict) and 'target_binding_id' in item}
    _require(all(isinstance(value, str) and value and len(value) <= 128 for value in ids),
             'target binding ID를 확인하세요.')
    trace_spec = plan['observation_sources'].get('command_trace')
    if not ids:
        _require(trace_spec is None, '원 command trace는 승인 target binding과 함께 사용하세요.')
        return {}
    configured = registry(config)
    _require(isinstance(configured, dict) and ids <= set(configured) and isinstance(trace_spec, dict),
             'runtime에 승인된 target binding과 원 command trace가 필요합니다.')
    _require(source.get('official') is False and manifest.get('official') is False,
             '이 검토된 archive target binding은 개발 실행에만 사용할 수 있습니다.')
    cache = {}

    def bytes_for(spec):
        key = digest(spec)
        if key not in cache:
            cache[key] = read(root, spec)
        return cache[key]

    result = {}
    for binding_id in ids:
        entry = configured[binding_id]
        _require(isinstance(entry, dict) and set(entry) == _FIELDS and type(entry.get('version')) is int
                 and entry['version'] == 1 and entry.get('association_method') == ASSOCIATION
                 and entry.get('clock_policy') == CLOCK, '승인 target binding의 고정 계약을 확인하세요.')
        _require(entry.get('source_scenario_sha256') == digest(source)
                 and entry.get('business_unit_id') == source.get('business_unit_id') == manifest.get('scenario_id')
                 and entry.get('capture_run_id') == manifest.get('run_id')
                 and type(entry.get('target_tab_id')) is int and entry['target_tab_id'] == manifest.get('target_tab_id'),
                 'target binding의 원 시나리오·업무·capture·tab이 다릅니다.')
        files, archive = entry.get('files'), entry.get('archive_paths')
        _require(isinstance(files, dict) and set(files) == _FILES and isinstance(archive, dict)
                 and set(archive) == _ARCHIVE_PATHS and files.get('command_trace') == trace_spec,
                 '승인 원 index·trace·summary·logger 파일 연결이 필요합니다.')
        proof = entry.get('review_evidence_sha256')
        _require(isinstance(proof, dict) and proof and all(isinstance(k, str) and isinstance(v, str)
                 and len(v) == 64 and all(c in '0123456789abcdef' for c in v) for k, v in proof.items()),
                 '독립 UI·DOM 검토 근거 SHA-256이 필요합니다.')
        raw = {key: bytes_for(spec) for key, spec in files.items()}
        indexed = dict(raw_files, **{key: raw[key] for key in _ARCHIVE_PATHS - {'csv', 'capture_manifest'}})
        for key in ('collection_index', 'final_index'):
            index = parse_json(raw[key])
            _require(isinstance(index, list) and all(isinstance(record, dict) and isinstance(record.get('path'), str)
                     for record in index), '원 archive index 구조를 확인하세요.')
            paths = [record['path'] for record in index]
            _require(len(paths) == len(set(paths)), '원 archive index의 경로가 중복됩니다.')
            by_path = {record['path']: record for record in index}
            for name, payload in indexed.items():
                record = by_path.get(archive[name], {})
                _require(record.get('sha256') == hashlib.sha256(payload).hexdigest()
                         and type(record.get('bytes')) is int and record['bytes'] == len(payload),
                         '원 archive index의 trace·CSV·manifest·summary·logger SHA가 다릅니다.')
        trace = parse_json(raw['command_trace'])
        _require(isinstance(trace, list) and trace and all(isinstance(record, dict)
                 and set(record) == {'at', 'label'} and isinstance(record['label'], str) for record in trace),
                 '원 command trace의 시각·label 구조를 확인하세요.')
        times = [_utc(record['at']) for record in trace]
        _require(times == sorted(times), '원 command trace 순서를 변경하거나 시간을 역전시킬 수 없습니다.')
        summary, following = parse_json(raw['attempt_summary']), parse_json(raw['next_attempt_summary'])
        start, command, end = (entry.get(key) for key in ('capture_start_index', 'command_index', 'next_capture_start_index'))
        _require(all(type(number) is int for number in (start, command, end))
                 and 0 <= start < command < end < len(trace)
                 and isinstance(summary, dict) and isinstance(following, dict)
                 and type(summary.get('action_offset')) is int and summary['action_offset'] == start
                 and type(following.get('action_offset')) is int and following['action_offset'] == end,
                 '원 capture의 명령 ordinal과 다음 capture 경계가 다릅니다.')
        _require(summary.get('business_unit_id') == entry['business_unit_id']
                 and summary.get('run_id') == entry['capture_run_id'] and summary.get('target_tab_id') == entry['target_tab_id']
                 and summary.get('csv_sha256') == plan['observation_sources']['csv']['sha256']
                 and summary.get('csv_bytes') == len(raw_files['csv']) and summary.get('event_count') == len(rows)
                 and summary.get('status') == 'COMPLETED'
                 and trace[start]['label'] == 'CAPTURE_START ' + entry['business_unit_id']
                 and trace[end]['label'] == 'CAPTURE_START ' + str(following.get('business_unit_id'))
                 and not any(record['label'].startswith('CAPTURE_START ') for record in trace[start + 1:end]),
                 '원 summary·trace의 업무·capture·CSV 연결이 다릅니다.')
        _require(trace[command]['label'] == 'CLICK ' + str(entry.get('command_target')),
                 '승인된 원 클릭 명령 selector와 정확히 같아야 합니다.')
        number = entry.get('csv_row')
        _require(type(number) is int and 1 <= number <= len(rows), '승인 target binding의 원 csv_row가 다릅니다.')
        row = rows[number - 1]
        _require(row['event_id'] == entry.get('event_id') and row['interaction_type'] == 'click'
                 and row['element_tag'] == entry.get('element_tag') and row['target_selector'] == entry.get('observed_target'),
                 '승인 target binding의 원 click·event·selector가 다릅니다.')
        observed_at = _utc(row['event_time'])
        _require(_utc(manifest['started_at']) <= _utc(summary['started_at']) <= times[start]
                 < observed_at <= times[command] <= _utc(manifest['stopped_at'])
                 <= _utc(summary['completed_at']) < times[end]
                 and _utc(manifest['stopped_at']) < _utc(following['started_at']) <= times[end]
                 and times[command - 1] < observed_at <= times[command],
                 '원 click은 승인된 capture와 이전·현재 명령 완료 시각 경계 안에 있어야 합니다.')
        candidates = [candidate for candidate in rows if candidate['interaction_type'] == 'click'
                      and times[command - 1] < _utc(candidate['event_time']) <= times[command]]
        _require(len(candidates) == 1 and candidates[0]['event_id'] == row['event_id'],
                 '완료 시각 구간의 원 click이 유일하지 않아 명령 대응을 추정할 수 없습니다.')
        result[binding_id] = dict(binding_id=binding_id, registration_sha256=digest(entry),
            association_method=ASSOCIATION, clock_policy=CLOCK, direct_causal_id_proven=False,
            command_index=command, event_id=row['event_id'], csv_row=number,
            observed_target=entry['observed_target'], command_target=entry['command_target'],
            proof_files_sha256={key: hashlib.sha256(value).hexdigest() for key, value in raw.items()},
            review_evidence_sha256=copy.deepcopy(proof))
    return result


def approved_action(binding_id, target, observed, bundle, config):
    bindings = bundle.get('execution_target_bindings', {})
    value = bindings.get(binding_id)
    current = registry(config)
    _require(isinstance(value, dict) and isinstance(current, dict) and binding_id in current
             and value.get('registration_sha256') == digest(current[binding_id]),
             '검증 후 승인 target binding이 없거나 바뀌었습니다.')
    _require(len(observed) == 1 and target == {'by': 'css selector', 'value': value['command_target']}
             and observed[0]['row']['event_id'] == value['event_id'] and observed[0]['csv_row'] == value['csv_row']
             and observed[0]['row']['target_selector'] == value['observed_target']
             and observed[0]['row']['interaction_type'] == 'click',
             '승인된 정확한 원 click과 command selector에만 binding을 사용할 수 있습니다.')
    return copy.deepcopy(value)
