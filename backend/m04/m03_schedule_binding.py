"""Reviewed BU03 execution remediation; the failed M03 result stays unchanged.

The M02 workflow mixes another business and misses four raw boundary events.
Eight modal clicks also point at calendar backgrounds. These observations remain
references, not guessed commands. Only independently identified native controls
are executed, with new test values and a persisted-state check after refresh.
"""
from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re

from . import checks


VERSION = 'm03-bu03-reviewed-execution-v1'
SOURCE_PIN = 'a47d82f3a73c5099460cfd47e64fe91faeefe21a602e53f34dcb385754fc6fa5'
RAW = 'evaluation_contracts/development/m02_baseline_77_29_preserved/snapshot/data/development/current_site_unseen_validation_v1/events.csv'
RAW_SHA256 = '01a1aa94e5a1df4edddbb86cc8f5be0a538cd157dd11533b5bf82af1a461d746'
OBSERVED = 'data/runtime/rainbow-m03-frozen-20261112/results/development/m03_current_semantics_20261109/business_steps.json'
OBSERVED_SHA256 = '86b1e77c8ca4ec365806d7d145d99ffa802bc097347b3db16ed9b3f600503f39'
URL = 'https://rainbowlab.ai.kr/mypage/schedule'
FORM = 'form.schedule-modal__panel'
TITLE, DESCRIPTION = '#schedule-title', '#schedule-description'
MONTH = '.schedule-page .calendar-toolbar__month'
_KEYS = ('business_unit_id', 'workflow_id', 'scenario_id', 'generator_version',
         'status', 'steps', 'issues', 'source_snapshot_sha256')
NOTICE = 'M03 생성 실패는 유지하고, 원본 관측과 확인한 화면 요소로 별도 실행계획을 고정합니다.'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def accepts(source):
    if not isinstance(source, dict) or source.get('business_unit_id') != 'BU03':
        return False
    try:
        raw = json.dumps({key: source.get(key) for key in _KEYS}, ensure_ascii=False,
                         sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        return hashlib.sha256(raw).hexdigest() == SOURCE_PIN
    except (TypeError, ValueError, OverflowError):
        return False


def describe(source):
    _require(accepts(source), '검토한 BU03 원본과 다릅니다.')
    return dict(name='일정 등록', ready=True, binding_ready=True, status='NEEDS_INPUT',
                writes_business_data=True,
                parameters_required=True, parameters=[
                    dict(name='date', label='시험 날짜', type='text', required=True, default='',
                         notice='현재 월의 YYYY-MM-DD'),
                    dict(name='title', label='일정 제목', type='text', required=True, default=''),
                    dict(name='description', label='일정 내용', type='text', required=True, default='')],
                binding_version=VERSION, source_step_count=len(source['steps']),
                start_url=URL, notice=NOTICE, source_generation_status='FAILED',
                execution_source_kind='REVIEWED_REMEDIATION', message='새 시험 입력을 지정하세요.')


def _read(root, name, expected):
    root = Path(root).resolve()
    path = root
    for part in Path(name).parts:
        path /= part
        _require(not path.is_symlink() and path.resolve() == path, '연결된 BU03 원본 경로는 허용하지 않습니다.')
    _require(path.is_file(), 'BU03 관측 원본이 없습니다.')
    raw = path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == expected, 'BU03 관측 원본 SHA-256이 변경됐습니다.')
    return raw


def provenance(root, source):
    """Verify original bytes and preserve all 18 rows, including model omissions."""
    _require(accepts(source), '검토한 BU03 원본과 다릅니다.')
    checks.validate_source_data(source)
    raw = _read(root, RAW, RAW_SHA256)
    snapshot = json.loads(_read(root, OBSERVED, OBSERVED_SHA256))
    matches = [p for p in snapshot['processes'] if p['canonical_instance_id'] == source['workflow_id']]
    _require(len(matches) == 1 and len(matches[0]['business_steps']) == 16, 'BU03 M02 업무절차 연결이 다릅니다.')
    observed = matches[0]['business_steps']
    model_ids = {identity for step in observed for identity in step['source_event_ids']}
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
    _require(len(rows) == 260, 'BU03 원본 행 수가 다릅니다.')
    ledger = []
    execute = {32: [2], 36: [3], 43: [4], 44: [4], 46: [5]}
    for number in range(32, 50):
        row = rows[number - 2]
        mode = 'execute' if number in execute else ('check' if number in {33, 47, 48, 49} else 'reference')
        ledger.append(dict(csv_row=number, event_id=row['event_id'],
                           observed_interaction=row['interaction_type'], original_target=row['target_selector'],
                           disposition=mode, effective_orders=execute.get(number, []),
                           in_m02_business_steps=row['event_id'] in model_ids,
                           causal_link_policy='original-only; API correlation is fallback, not proven causality'))
    _require(rows[34]['target_selector'] == TITLE and rows[41]['target_selector'] == DESCRIPTION
             and rows[44]['element_tag'] == 'form', '관측 입력란·native form 근거가 다릅니다.')
    return dict(version=1, kind='REVIEWED_EXECUTION_REMEDIATION', source_fingerprint=SOURCE_PIN,
                source_generation_status=source['status'], source_issues=deepcopy(source['issues']),
                raw_csv=dict(path=RAW, sha256=RAW_SHA256), observed_process=dict(path=OBSERVED, sha256=OBSERVED_SHA256),
                source_window=dict(first_csv_row=32, last_csv_row=49, row_count=18),
                observed_rows=ledger, ambiguous_click_rows=[35, 37, 38, 39, 40, 41, 42, 45],
                additional_verification_orders=[6, 7, 8],
                exact_historical_click_replay=False, new_model_inference=False,
                original_m03_status_modified=False, official=False)


def prepare(root, source, parameters):
    proof = provenance(root, source)
    _require(isinstance(parameters, dict) and set(parameters) == {'date', 'title', 'description'},
             '시험 날짜·일정 제목·내용을 지정하세요.')
    values = deepcopy(parameters)
    _require(all(isinstance(value, str) and value.strip() and len(value) <= 1000
                 and all(ord(c) >= 32 and ord(c) != 127 and not '\ue000' <= c <= '\ue05d' for c in value)
                 for value in values.values()), '시험 입력의 빈 값·제어문자·길이를 확인하세요.')
    checks.validate_source_data(values, strict_literals=True)
    _require(re.fullmatch(r'\d{4}-\d{2}-\d{2}', values['date']), '시험 날짜는 YYYY-MM-DD 형식이어야 합니다.')
    try:
        day = date.fromisoformat(values['date'])
    except ValueError:
        raise ValueError('실제로 존재하는 시험 날짜를 지정하세요.') from None
    today = datetime.now(timezone(timedelta(hours=9))).date()
    _require((day.year, day.month) == (today.year, today.month), '현재 월의 시험 날짜를 지정하세요.')
    _require(values['title'].startswith(('KTL-', 'KTL ')) and len(values['title']) <= 120,
             '일정 제목에는 KTL 시험 표식을 사용하세요(120자 이하).')
    _require(values['description'].strip().upper() not in {'[MASKED]', '[REDACTED]', '[HIDDEN]'}
             and not re.fullmatch(r'[\s*＊•●]+', values['description']), '마스킹 표식을 입력값으로 사용할 수 없습니다.')
    index = (day.replace(day=1).weekday() + 1) % 7 + day.day
    cell = '.schedule-page .monthly-calendar__grid > .monthly-calendar__cell:nth-child(' + str(index) + ')'
    date_target = cell + ' .monthly-calendar__date-number'
    event_target = cell + ' button.schedule-event__title'
    css = lambda value: dict(by='css selector', value=value)
    visible = lambda target, value: dict(kind='visible', target=css(target), expected=value)
    equal = lambda target, value: dict(kind='text_equals', target=css(target), expected=value)
    value = lambda target, text: dict(kind='value', target=css(target), expected=text)
    count = lambda number: dict(kind='text_count', target=css(event_target), expected=values['title'], count=number)
    steps, definitions = [], []

    def add(action, target, conditions, expected, **extra):
        order = len(steps) + 1
        steps.append(dict(order=order, action=action, target=target, expected_result=expected, **extra))
        definitions.append(dict(order=order, action=action,
                                target=dict(url=target) if action == 'open' else css(target), checks=conditions))

    add('open', URL, [dict(kind='url_path', expected='/mypage/schedule'), equal(MONTH, day.strftime('%Y.%m')),
                      equal('.schedule-viewer-bar__copy strong', '내 일정'), equal(date_target, str(day.day)), count(0)],
        '본인 일정의 대상 날짜와 동일 제목 부재를 확인한다', url=URL)
    add('click', date_target, [visible(FORM, True), equal(FORM + ' h2', '업무 등록'),
                              value(TITLE, ''), value(DESCRIPTION, '')], '빈 신규 일정 폼을 확인한다')
    add('input', TITLE, [value(TITLE, values['title'])], '새 시험 제목을 확인한다', value=values['title'])
    add('input', DESCRIPTION, [value(DESCRIPTION, values['description'])], '새 시험 내용을 확인한다', value=values['description'])
    add('submit', FORM, [visible(FORM, False), count(1)], 'native form 제출 후 새 일정을 확인한다')
    add('refresh', '.schedule-page', [visible(FORM, False), equal(MONTH, day.strftime('%Y.%m')), count(1)],
        '새로고침한 일정 목록에서 저장 상태를 확인한다')
    add('click', event_target, [visible(FORM, True), value(TITLE, values['title']),
                              value(DESCRIPTION, values['description'])],
        '저장된 일정을 다시 열어 제목과 내용을 확인한다', match_text=values['title'])
    add('click', FORM + ' button[aria-label="닫기"]', [visible(FORM, False), count(1)], '조회한 일정을 닫는다')
    scenario = dict(scenario_id=source['scenario_id'], business_unit_id='BU03', workflow_id=source['workflow_id'],
                    scenario_name='일정 등록', status='SUCCESS', source_generation_status='FAILED',
                    execution_source_kind='REVIEWED_REMEDIATION', run_mode='DEVELOPMENT', official=False,
                    steps=steps, binding_version=VERSION, screenshot_checkpoints=dict(before=2, after=7))
    contract = checks.prepare_contract(dict(scenario, execution_contract=dict(version=1,
                                       scenario_id=source['scenario_id'], steps=definitions)))
    mapping = [dict(source_order=step['order'], source_step_id=step['source_step_id'],
                    source_action=step['action'], source_target=step['target'],
                    mapping_relation='REMEDIATION_ALIGNMENT_NOT_EVENT_CAUSALITY',
                    source_event_ids=deepcopy(step['source_event_ids']),
                    source_node_ids=deepcopy(step['source_node_ids']), effective_orders=orders)
               for step, orders in zip(source['steps'], ([1], [2], [3], [4], [5]))]
    return dict(scenario=scenario, contract=contract, source_mapping=mapping,
                binding_version=VERSION, parameters=values, source_fingerprint=SOURCE_PIN,
                remediation_provenance=proof, notice=NOTICE, revision_id=None)
