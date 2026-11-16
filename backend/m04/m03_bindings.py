"""Reviewed DEVELOPMENT bindings for the unchanged frozen observed M03 inputs.

This is a deterministic execution adapter, not scenario generation or evaluation.
The original source remains in its own archive; every source operation maps to
one or more executable operations, including repeated observations of a field.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from . import checks


VERSION = 'm03-observed-dom-binding-v2-20261116'
ORIGIN = 'https://rainbowlab.ai.kr'
DOM_EVIDENCE_SHA256 = '17dc997807106ee2b69008a4291c0253174453ec66821463ce0c3395dff3f717'
_SOURCE_KEYS = ('business_unit_id', 'workflow_id', 'scenario_id', 'generator_version',
                'status', 'steps', 'issues', 'source_snapshot_sha256')
_PINS = {
    'BU01': 'c536143ec7f415db5f990d90263ad6fe5e1c41cadfdd23bf0fde147fe760a25c',
    'BU03': 'a47d82f3a73c5099460cfd47e64fe91faeefe21a602e53f34dcb385754fc6fa5',
    'BU05': 'ff0b271c1a1ada00f839d614afdcb196d8af68b13e8e779b84490f1c71b02797',
    'BU07': 'c38b82686ade6eba51a397052049dbe150ba5d9f0ffcab0e1a02a51a05b177cc',
    'BU09': '5168e93574c482d994f08211c626fc1ce742938f640545cdfd87ace0fba5f48d',
    'BU12': '72e92f0ca15005170784359ea2aad2714b26e47464846e60cc6e5928fd2ccd16',
    'BU13': 'd6e04ff3d33f53427d7c1e37a2a3fbcd6c23b204e756db834ac46a1245665f85',
    'BU14': '9c7eae733d9b7099eca09f65cf327732f227b7a48adc0cba564f7f084f637b97',
    'BU17': 'a5be508214ef4ea952e9fd629d4922321bb44e639cc9594600f08e8bfc9a37b0',
    'BU20': 'f98b605053e39c4ebab6d2905b69f395a328970cfee876400428b475a0366bad',
}
# Original frozen candidate.json (c3351712...) names, not inferred from output.
_NAMES = {
    'BU01': '개인정보 조회', 'BU03': '일정 등록', 'BU05': '전체업무 상세조회',
    'BU07': '일일보고 작성', 'BU09': '주간보고 작성', 'BU12': '명함 목록 조회',
    'BU13': '명함 상세조회', 'BU14': '명함 등록', 'BU17': '거래처 정보 등록',
    'BU20': '자산 등록',
}
_START_PATHS = {
    'BU01': '/mypage', 'BU05': '/mypage/work/overview', 'BU07': '/mypage/work/daily',
    'BU09': '/mypage/work/weekly', 'BU12': '/mypage/work/monthly', 'BU13': '/mypage/cards',
    'BU14': '/mypage/cards', 'BU17': '/mypage/clients', 'BU20': '/mypage/assets',
}
_FORM = '.work-report-form-modal__panel'
_DETAIL = '.work-report-detail-modal__panel'
_REGISTER = '.work-report-page__register'
_SAVE = '.work-report-form-modal__submit'
_MESSAGE = '.work-report-message-modal'
_MESSAGE_CONFIRM = '.work-report-message-modal__button'
_CARD_DETAIL = '.work-report-detail-modal__panel.business-card-detail-modal'
_CARD_COMPANY = (_CARD_DETAIL + ' .business-card-detail-modal__body > section:first-child '
                 '.business-card-detail-modal__grid > div:first-child > span')
_NOTICE = ('고정 M03 관측 순서에 현재 확인한 DOM 연결과 새 시험 입력을 결합합니다. '
           '원래 입력값을 복원하지 않으며 새 AI 생성·M03 정답 순서 평가·공식 10건 시험을 뜻하지 않습니다.')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def source_fingerprint(source):
    _require(isinstance(source, dict), 'M03 원본 객체가 필요합니다.')
    subset = {key: source.get(key) for key in _SOURCE_KEYS}
    return hashlib.sha256(json.dumps(subset, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _validate(source):
    checks.validate_source_data(source)
    bu = source.get('business_unit_id') if isinstance(source, dict) else None
    _require(bu in _PINS and source_fingerprint(source) == _PINS[bu],
             '검토한 고정 M03 원본의 식별자·동작·대상·입력 필드·순서와 다릅니다.')
    _require(source.get('status') == 'SUCCESS',
             'BU03 원본 생성 실패와 누락 단계 11건을 보존합니다. 실행할 수 없습니다.')
    _require(bu in _START_PATHS, '현재 DOM에서 확인하지 않은 업무입니다.')
    return bu


def _field_specs(source):
    seen, result = {}, []
    for step in source['steps']:
        for field in step.get('fields', []):
            selector = field['selector']
            if selector in seen:
                continue
            name = 'field_' + str(len(seen) + 1)
            seen[selector] = name
            spec = dict(name=name, label=field['label'], type='text', required=True,
                        default='', source_selector=selector,
                        notice='원래 값이 아닌 새 비민감 시험 입력을 지정하세요.')
            if selector.endswith('select'):
                spec.update(type='select', choices=['문서', '시스템', '소프트웨어', '하드웨어', '장비', '기타'])
            result.append(spec)
    if source['business_unit_id'] == 'BU05':
        result.append(dict(name='record_title', label='열어 볼 기존 시험 보고서의 정확한 제목',
                           type='text', required=True, default='',
                           notice='기존 KTL 시험 자료의 제목을 명시하세요. 첫 행을 임의 선택하지 않습니다.'))
    elif source['business_unit_id'] == 'BU13':
        result.append(dict(name='record_company', label='조회할 새 시험 명함의 정확한 회사명',
                           type='text', required=True, default='',
                           notice='KTL 표식의 회사명을 명시하세요. 원 관측의 이름과 같은 인물이라는 뜻이 아닙니다.'))
    if source['business_unit_id'] == 'BU09':
        result.append(dict(name='report_date', label='주간보고 기준일 · 현재 등록 화면과 같아야 함',
                           type='date', required=True, default='',
                           notice='YYYY-MM-DD. 날짜를 자동 변경하지 않으며 현재 폼 날짜가 다르면 저장 전에 중단합니다.'))
    return result, seen


def describe(source):
    from . import m03_schedule_binding
    if m03_schedule_binding.accepts(source):
        return m03_schedule_binding.describe(source)
    try:
        bu = _validate(source)
        specs, _ = _field_specs(source)
        return dict(name=_NAMES[bu], ready=True, binding_ready=True, parameters_required=bool(specs),
                    status='NEEDS_INPUT' if specs else 'READY',
                    message='실행 binding을 확인했습니다. 시험 입력을 지정한 뒤 고정하세요.' if specs else '실행 binding을 확인했습니다.',
                    parameters=specs, binding_version=VERSION, start_url=ORIGIN + _START_PATHS[bu],
                    source_step_count=len(source['steps']), notice=_NOTICE,
                    dom_evidence_sha256=DOM_EVIDENCE_SHA256)
    except (ValueError, TypeError, KeyError, OverflowError):
        # Fixed, value-free diagnoses; no raw source or account material is echoed.
        if isinstance(source, dict) and source.get('business_unit_id') == 'BU03' and source.get('status') == 'FAILED':
            message = 'BU03 원본은 FAILED이며 누락 단계가 있습니다. 실패를 제외하거나 순서를 보정하지 않습니다.'
        elif isinstance(source, dict) and source.get('business_unit_id') == 'BU13':
            message = 'BU13 원본 식별자·동작·순서가 검토한 관측과 다릅니다. 새 시험 회사명은 확인된 원본에만 연결합니다.'
        else:
            message = '검토한 고정 M03 원본과 다르거나 현재 DOM 실행 연결이 확인되지 않았습니다.'
        return dict(name=_NAMES.get(source.get('business_unit_id'), '') if isinstance(source, dict) else '',
                    ready=False, binding_ready=False, parameters_required=False, status='NOT_READY', message=message, parameters=[],
                    binding_version=VERSION, blockers=[message], notice=_NOTICE)


def _parameter_values(source, parameters):
    specs, names = _field_specs(source)
    supplied = {} if parameters is None else parameters
    _require(isinstance(supplied, dict) and set(supplied) == {s['name'] for s in specs},
             '표시한 새 시험 입력을 빠짐없이 지정하세요. 다른 입력 키는 허용하지 않습니다.')
    values = {}
    for spec in specs:
        value = supplied[spec['name']]
        _require(isinstance(value, str) and bool(value.strip()) and len(value) <= 1000
                 and all(ord(c) >= 32 and ord(c) != 127 and not '\ue000' <= c <= '\ue05d' for c in value),
                 '시험 입력은 빈 값·제어문자·Selenium 예약 키가 없는 1000자 이하 문자열이어야 합니다.')
        checks.validate_source_data(value, strict_literals=True)
        _require(value.strip().upper() not in {'[MASKED]', '[REDACTED]', '[HIDDEN]', '[숨김]', '-'}
                 and not re.fullmatch(r'[\s*＊•●]+', value), '마스킹 표식을 시험 입력으로 사용할 수 없습니다.')
        if spec['type'] == 'select':
            _require(value in spec['choices'], '현재 확인한 자산 구분을 선택하세요.')
        if spec['type'] == 'date':
            _report_date(value)
        values[spec['name']] = value
    if specs:
        marker_name = {'BU05': 'record_title', 'BU13': 'record_company'}.get(source['business_unit_id'])
        if marker_name is None:
            marker_name = names[next(f['selector'] for s in source['steps'] for f in s.get('fields', [])
                                     if f['label'] in {'제목', '회사명', '자산명'})]
        _require(values[marker_name].startswith(('KTL-', 'KTL ')),
                 '기존 실제 자료와 구분하도록 제목·회사명·자산명에는 KTL 시험 표식을 사용하세요.')
    return values, names


def _report_date(value):
    _require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value),
             '주간보고 기준일은 실제 YYYY-MM-DD 날짜여야 합니다.')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError('주간보고 기준일은 실제 YYYY-MM-DD 날짜여야 합니다.') from None


def _weekly_display_title(value, title):
    # Same first-Sunday month boundary as workReports.js getWeeklyPeriodInfo.
    current = _report_date(value)
    first_sunday = 1 + (6 - current.replace(day=1).weekday()) % 7
    if first_sunday == 1:
        week = (current.day - 1) // 7 + 1
    elif current.day < first_sunday:
        week = 1
    else:
        week = (current.day - first_sunday) // 7 + 2
    return f'{current.year % 100:02d}-{current.month} {week}주차 {title}'


def _css(value):
    return dict(by='css selector', value=value)


def _check(kind, target=None, expected=None, **kwargs):
    result = dict(kind=kind, **kwargs)
    if target is not None:
        result['target'] = _css(target)
    if expected is not None:
        result['expected'] = expected
    return result


def prepare(source, parameters=None):
    bu = _validate(source)
    values, field_names = _parameter_values(source, parameters)
    steps, definitions, mapping = [], [], []
    report = bu in {'BU07', 'BU09'}
    table = 'table.work-report-table' if report or bu == 'BU05' else 'table.business-card-table'
    marker = None
    if field_names:
        marker_field = next(f for s in source['steps'] for f in s.get('fields', [])
                            if f['label'] in {'제목', '회사명', '자산명'})
        marker = values[field_names[marker_field['selector']]]
    display_marker = _weekly_display_title(values['report_date'], marker) if bu == 'BU09' else marker
    marker_target = table + (' tbody .work-report-table__title button' if report else ' tbody td')
    def marker_check(count):
        return _check('text_count', marker_target, display_marker, count=count)
    def add(original, action, target, conditions, *, field_index=None, value=None, match_text=None, row_match=None):
        order = len(steps) + 1
        row = dict(order=order, action=action, target=target,
                   expected_result='고정 실행 조건으로 현재 화면 결과를 확인한다.',
                   source_order=original['order'], source_step_id=original['source_step_id'])
        if field_index is not None:
            row['source_field_index'] = field_index
        if value is not None:
            row['value'] = value
        if match_text is not None:
            row['match_text'] = match_text
        if row_match is not None:
            row['row_match'] = deepcopy(row_match)
        steps.append(row)
        definitions.append(dict(order=order, action=action, target=_css(target), checks=conditions))
        return order
    for original in source['steps']:
        orders, action = [], original['action']
        if action == 'NAVIGATE':
            if bu == 'BU01' and original['order'] == 1:
                orders.append(add(original, 'click', 'button.mypage-sidebar__section-button',
                    [_check('visible', 'button.mypage-sidebar__section-button[aria-expanded="true"]', True)],
                    match_text=original['target']))
            elif bu == 'BU01':
                orders.append(add(original, 'click', 'button.mypage-sidebar__submenu-button',
                    [_check('url_path', expected='/mypage/personal-info'), _check('visible', '#personal-name', True)],
                    match_text=original['target']))
            elif bu == 'BU12':
                orders.append(add(original, 'click', 'button.mypage-sidebar__section-button',
                    [_check('url_path', expected='/mypage/cards'), _check('visible', 'table.business-card-table', True)],
                    match_text=original['target']))
            else:
                raise ValueError('검토하지 않은 이동 단계입니다.')
        elif action == 'DETAIL_OPEN' and bu == 'BU05':
            orders.append(add(original, 'click', table + ' tbody .work-report-table__title button',
                [_check('visible', _DETAIL, True),
                 _check('text_equals', _DETAIL + ' .work-report-detail-modal__meta dd:nth-of-type(5)', values['record_title']),
                 _check('nonempty', _DETAIL + ' .work-report-detail-modal__content', property='text')], match_text=values['record_title']))
        elif action == 'DETAIL_OPEN' and bu == 'BU13':
            company = values['record_company']
            orders.append(add(original, 'click', table + ' tbody .business-card-table__title button',
                [_check('visible', _CARD_DETAIL, True), _check('text_equals', _CARD_COMPANY, company),
                 _check('text_count', table + ' tbody tr td:nth-child(3)', company, count=1)],
                row_match=dict(rows=table + ' tbody tr', cell='td:nth-child(3)', expected=company)))
        elif action == 'REGISTER':
            conditions = [_check('visible', _FORM, True), marker_check(0)]
            if bu == 'BU09':
                current = _report_date(values['report_date'])
                shown = values['report_date'].replace('-', '.') + ' (' + '월화수목금토일'[current.weekday()] + ')'
                conditions.append(_check('text_equals', _FORM + ' .work-report-form-modal__date-button', shown))
            # Only the observed input controls are required empty. Their original
            # selectors are reused verbatim, not replaced by semantic aliases.
            seen = set()
            for s in source['steps']:
                for f in s.get('fields', []):
                    if f['selector'] not in seen and not f['selector'].endswith('select'):
                        seen.add(f['selector']); conditions.append(_check('value', f['selector'], ''))
            orders.append(add(original, 'click', _REGISTER, conditions, match_text='등록'))
        elif action == 'INPUT':
            for index, field in enumerate(original['fields']):
                selector = field['selector']; value = values[field_names[selector]]
                effective_action = 'select' if selector.endswith('select') else 'input'
                orders.append(add(original, effective_action, selector, [_check('value', selector, value)],
                                  field_index=index, value=value))
        elif action == 'SAVE':
            message = ('일일업무가 저장되었습니다.' if bu == 'BU07' else '주간업무가 저장되었습니다.') if report else '등록되었습니다.'
            orders.append(add(original, 'click', _SAVE,
                [_check('visible', _FORM, False), _check('text_contains', _MESSAGE + '__panel', message), marker_check(1)],
                match_text='저장'))
        elif action == 'CONFIRM':
            if bu == 'BU13':
                orders.append(add(original, 'click', _CARD_DETAIL + ' .work-report-detail-modal__actions button',
                    [_check('visible', _CARD_DETAIL, False), _check('visible', table, True),
                     _check('text_count', table + ' tbody tr td:nth-child(3)', values['record_company'], count=1)],
                    match_text='확인'))
            else:
                detail = bu == 'BU05'
                target = _DETAIL + ' .work-report-detail-modal__actions button' if detail else _MESSAGE_CONFIRM
                conditions = [_check('visible', _DETAIL if detail else _MESSAGE, False), _check('visible', table, True)]
                if marker:
                    conditions.append(marker_check(1))
                orders.append(add(original, 'click', target, conditions, match_text='확인'))
        else:
            raise ValueError('검토하지 않은 M03 동작은 실행 동작으로 변환하지 않습니다.')
        _require(bool(orders), '원본 단계를 누락할 수 없습니다.')
        mapping.append(dict(source_order=original['order'], source_action=action, source_target=original['target'],
                            source_step_id=original['source_step_id'], source_event_ids=deepcopy(original['source_event_ids']),
                            source_node_ids=deepcopy(original['source_node_ids']), effective_orders=orders,
                            source_field_count=len(original.get('fields', []))))
        if bu == 'BU13':
            mapping[-1].update(execution_target_policy='EXPLICIT_NEW_TEST_RECORD_COMPANY',
                               target_parameter='record_company', historical_target_identity_verified=False)
    scenario = dict(scenario_id=source['scenario_id'], scenario_name=_NAMES[bu],
                    business_unit_id=bu, workflow_id=source['workflow_id'], status='SUCCESS',
                    start_url=ORIGIN + _START_PATHS[bu], steps=steps,
                    run_mode='DEVELOPMENT', official=False, binding_version=VERSION)
    contract = checks.prepare_contract(dict(scenario, execution_contract=dict(version=1,
        scenario_id=scenario['scenario_id'], steps=definitions)))
    notice = _NOTICE
    if bu == 'BU13':
        notice += ' BU13은 명시한 새 시험 회사명의 명함을 조회하며 원래 이름 대상과 동일한 인물·레코드라는 주장은 하지 않습니다.'
    prepared = dict(scenario=scenario, contract=contract, source_mapping=mapping, binding_version=VERSION,
                    parameters=values, source_fingerprint=source_fingerprint(source),
                    dom_evidence_sha256=DOM_EVIDENCE_SHA256, notice=notice)
    if bu == 'BU01':
        from .bu01_input_demo import extend
        return extend(prepared)
    return prepared
