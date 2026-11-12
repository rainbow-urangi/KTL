"""회의의 M07 20종 일괄 입력 계약. 코드 생성ㆍ실행ㆍ공식 판정은 하지 않는다.

M03와 같은 시나리오 형식만 재사용한다. 사용자 입력을 M03 산출물 또는
승인 시험 자료로 승격하지 않으며 원본 행과 실행 준비 검사를 분리한다.
"""
from copy import deepcopy
import hashlib
import json
import math
from urllib.parse import urlsplit

from ..evaluators import EvaluationError, require
from ..m03_integration import validate_scenario_result
from ..m04.checks import prepare_contract, validate_source_data


REQUIRED_COUNT = 20
TARGET_PERCENT = 80
SOURCE_KIND = 'MEETING_SCENARIO_INPUT'
SOURCE_DOCUMENT = dict(name='음성 261015_145752 ktl.txt',
                       sha256='05417f10d108345d726804ac2062bbe61c6cc8ceabe85d71011aad97bb041ad2',
                       timestamps=['32:39', '33:34–33:44', '34:28–34:54', '35:51'])
MAX_BATCH_BYTES = 256 * 1024
MAX_STEPS = 100
_SCENARIO_REQUIRED = {'scenario_id', 'scenario_name', 'business_unit_id', 'workflow_id',
                      'steps', 'execution_contract'}
_SCENARIO_OPTIONAL = {'description', 'preconditions', 'screenshot_checkpoints'}
_STEP_FIELDS = {'order', 'action', 'target', 'expected_result', 'url', 'value'}


def _json_input(value, depth=0, budget=None):
    """직접 함수 호출에도 HTTP JSON과 같은 제한을 적용한다."""
    budget = [50000] if budget is None else budget
    budget[0] -= 1
    require(depth <= 16 and budget[0] >= 0, '입력 JSON의 중첩이나 항목 수가 너무 많습니다.')
    if isinstance(value, dict):
        require(all(isinstance(key, str) and len(key) <= 256 for key in value), '입력 JSON 키는 256자 이내 문자열이어야 합니다.')
        for item in value.values():
            _json_input(item, depth + 1, budget)
    elif isinstance(value, list):
        require(len(value) <= 1000, '입력 JSON 배열이 너무 큽니다.')
        for item in value:
            _json_input(item, depth + 1, budget)
    elif isinstance(value, str):
        require(len(value) <= 4096 and not any(ord(char) < 32 and char not in '\n\r\t' for char in value)
                and not any(0xD800 <= ord(char) <= 0xDFFF or ord(char) == 127 for char in value),
                '입력 문자열의 길이와 제어 문자를 확인하세요.')
    else:
        require(value is None or type(value) in {bool, int} or type(value) is float and math.isfinite(value),
                '입력은 유한한 JSON 값이어야 합니다.')


def _text(value, label, limit=256):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit
            and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value),
            label + '은 앞뒤 공백과 제어 문자가 없는 ' + str(limit) + '자 이내 문자열이어야 합니다.')
    return value


def _http_url(value):
    _text(value, '실행 URL', 2048)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise EvaluationError('실행 URL 형식을 확인하세요.', 'ERROR') from None
    require(parsed.scheme in {'http', 'https'} and bool(parsed.hostname) and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment
            and '?' not in value and '#' not in value and not any(char.isspace() for char in value)
            and (port is None or 1 <= port <= 65535),
            '실행 URL에는 HTTP(S) 주소만 사용하고 인증정보ㆍqueryㆍfragment를 제외하세요.')


def _scenario(value, position):
    label = '입력 ' + str(position)
    require(isinstance(value, dict) and _SCENARIO_REQUIRED <= set(value)
            and set(value) <= _SCENARIO_REQUIRED | _SCENARIO_OPTIONAL,
            label + '에는 시나리오 정의와 실행 계약만 입력하세요. 코드ㆍ평가결과ㆍM03 증빙은 허용하지 않습니다.')
    for key in ('scenario_id', 'scenario_name', 'business_unit_id', 'workflow_id'):
        _text(value[key], label + '의 ' + key)
    if 'description' in value:
        require(isinstance(value['description'], str) and len(value['description']) <= 2000,
                label + '의 description은 2000자 이내 문자열이어야 합니다.')
    if 'preconditions' in value:
        conditions = value['preconditions']
        require(isinstance(conditions, list) and len(conditions) <= 20, label + '의 preconditions는 문자열 배열이어야 합니다.')
        for condition in conditions:
            _text(condition, label + '의 사전조건', 2000)
    steps = value['steps']
    require(isinstance(steps, list) and 1 <= len(steps) <= MAX_STEPS, label + '은 1~100개 실행 단계가 필요합니다.')
    for index, step in enumerate(steps, 1):
        require(isinstance(step, dict) and {'order', 'action', 'target', 'expected_result'} <= set(step)
                and set(step) <= _STEP_FIELDS, label + '의 단계에는 동작ㆍ대상ㆍ기대 결과만 입력하세요.')
        _text(step['action'], label + ' 단계 ' + str(index) + '의 action', 32)
        _text(step['target'], label + ' 단계 ' + str(index) + '의 target')
        _text(step['expected_result'], label + ' 단계 ' + str(index) + '의 expected_result', 2000)
        if step.get('action') in {'open', 'navigate'}:
            require('url' in step, label + '의 화면 이동 단계에 URL이 필요합니다.')
            _http_url(step['url'])
        else:
            require('url' not in step, label + '의 URL은 open/navigate 단계에만 지정하세요.')
        if step.get('action') in {'input', 'type', 'select'}:
            require(isinstance(step.get('value'), str) and 0 < len(step['value']) <= 2000,
                    label + '의 입력ㆍ선택 단계에 실제 value 문자열이 필요합니다.')
        elif 'value' in step:
            require(step.get('action') == 'clear' and step['value'] == '',
                    label + '의 value는 입력ㆍ선택 또는 빈 값의 clear 단계에만 지정하세요.')
    require(validate_scenario_result(value)['success'], label + '의 시나리오 형식과 단계 순서를 확인하세요.')
    try:
        contract = prepare_contract(value)
    except ValueError as exc:
        raise EvaluationError(label + '의 실행 조건을 확인하세요: ' + str(exc), 'NOT_READY') from None
    for step, definition in zip(steps, contract['steps']):
        if step['action'] in {'open', 'navigate'}:
            _http_url(definition['target']['url'])
            require(step['url'] == definition['target']['url'], label + '의 단계 URL과 실행 계약 URL이 일치해야 합니다.')
    if 'screenshot_checkpoints' in value:
        points = value['screenshot_checkpoints']
        require(isinstance(points, dict) and set(points) == {'before', 'after'}
                and all(type(point) is int and 1 <= point <= len(steps) for point in points.values())
                and points['before'] <= points['after'], label + '의 화면 기록 단계가 유효하지 않습니다.')
    return contract


def _behavior_key(scenario, contract):
    # 이름ㆍ설명ㆍID만 바꾼 동일한 실행을 독립된 시험으로 중복 집계하지 않는다.
    behavior = dict(steps=[{key: step[key] for key in ('order', 'action', 'url', 'value') if key in step}
                           for step in scenario['steps']],
                    contract_steps=contract['steps'])
    return hashlib.sha256(json.dumps(behavior, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')).hexdigest()


def prepare_batch(payload):
    """20개 독립 입력을 검증하고 원본 의미를 보존한 행을 반환한다.

    `source_raw`는 업로드한 `{input_id, scenario}` 행의 독립 복사본이다.
    정규화 계약은 별도 실행 준비 단계가 보관하며 원본에 덮어쓰지 않는다.
    """
    _json_input(payload)
    require(isinstance(payload, dict) and set(payload) == {'items'}, 'M07 일괄 입력은 {items: [...]} 형식이어야 합니다.')
    items = payload['items']
    require(isinstance(items, list) and len(items) == REQUIRED_COUNT, '서로 다른 시나리오 입력을 정확히 20건 등록하세요.')
    require(len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')) <= MAX_BATCH_BYTES,
            'M07 일괄 입력은 256 KiB 이내여야 합니다.')
    try:
        validate_source_data(payload, strict_literals=True)
    except ValueError as exc:
        raise EvaluationError('시나리오에 인증정보ㆍ평가 정답을 넣을 수 없습니다: ' + str(exc), 'ERROR') from None
    result, input_ids, scenario_ids, behaviors = [], set(), set(), set()
    for position, row in enumerate(items, 1):
        require(isinstance(row, dict) and set(row) == {'input_id', 'scenario'}, '각 입력에는 input_id와 scenario만 지정하세요.')
        input_id = _text(row['input_id'], 'input_id')
        contract = _scenario(row['scenario'], position)
        scenario_id = row['scenario']['scenario_id']
        behavior = _behavior_key(row['scenario'], contract)
        require(input_id not in input_ids and scenario_id not in scenario_ids,
                'input_id와 scenario_id는 20건 모두 서로 달라야 합니다.')
        require(behavior not in behaviors, 'ID나 이름만 바꾼 동일 실행 입력은 별도 시나리오로 집계할 수 없습니다.')
        input_ids.add(input_id)
        scenario_ids.add(scenario_id)
        behaviors.add(behavior)
        result.append(dict(input_id=input_id, scenario=deepcopy(row['scenario']), source_raw=deepcopy(row)))
    return result


normalize_batch = prepare_batch


def schema():
    """작성 안내와 단일 placeholder. 시험 입력 20건을 자동으로 선정하지 않는다."""
    placeholder = dict(input_id='REPLACE_INPUT_ID', scenario=dict(
        scenario_id='REPLACE_SCENARIO_ID', scenario_name='실제 시험 시나리오 이름으로 교체',
        business_unit_id='REPLACE_BUSINESS_ID', workflow_id='REPLACE_WORKFLOW_ID',
        steps=[dict(order=1, action='open', target='실제 업무 화면 이름으로 교체',
                    url='https://example.invalid/replace-path', expected_result='실제 화면의 기대 상태로 교체')],
        execution_contract=dict(version=1, scenario_id='REPLACE_SCENARIO_ID', steps=[
            dict(order=1, action='open', target=dict(url='https://example.invalid/replace-path'),
                 checks=[dict(kind='url_path', expected='/replace-path'),
                         dict(kind='visible', target=dict(by='css selector', value='#replace-real-selector'), expected=True)])])))
    text = dict(type='string', minLength=1, maxLength=256)
    step = dict(type='object', additionalProperties=False, required=['order', 'action', 'target', 'expected_result'],
                properties=dict(order=dict(type='integer', minimum=1), action=dict(type='string'), target=text,
                                expected_result=dict(type='string', minLength=1, maxLength=2000),
                                url=dict(type='string', format='uri'), value=dict(type='string', maxLength=2000)))
    css = dict(type='object', additionalProperties=False, required=['by', 'value'],
               properties=dict(by=dict(const='css selector'), value=dict(type='string', minLength=1, maxLength=2048)))
    target = dict(oneOf=[dict(type='object', additionalProperties=False, required=['url'],
                             properties=dict(url=dict(type='string', format='uri'))), css])
    check = dict(type='object', required=['kind'], properties=dict(kind=dict(type='string')),
                 description='기존 prepare_contract의 typed condition 형식을 사용합니다. URLㆍCSSㆍ기대값은 실행 전에 확정하세요.')
    contract_step = dict(type='object', additionalProperties=False, required=['order', 'action', 'target', 'checks'],
                         properties=dict(order=dict(type='integer', minimum=1), action=dict(type='string'),
                                         target=target, checks=dict(type='array', minItems=1, items=check)))
    scenario = dict(type='object', additionalProperties=False, required=sorted(_SCENARIO_REQUIRED), properties=dict(
        scenario_id=text, scenario_name=text, business_unit_id=text, workflow_id=text,
        steps=dict(type='array', minItems=1, maxItems=MAX_STEPS, items=step),
        execution_contract=dict(type='object', required=['version', 'scenario_id', 'steps'], additionalProperties=False,
                                properties=dict(version=dict(const=1), scenario_id=text,
                                                steps=dict(type='array', minItems=1, maxItems=MAX_STEPS,
                                                           items=contract_step))),
        description=dict(type='string', maxLength=2000),
        preconditions=dict(type='array', maxItems=20, items=dict(type='string', minLength=1, maxLength=2000)),
        screenshot_checkpoints=dict(type='object', required=['before', 'after'], additionalProperties=False,
                                    properties=dict(before=dict(type='integer', minimum=1), after=dict(type='integer', minimum=1)))))
    input_schema = dict(type='object', additionalProperties=False, required=['items'], properties=dict(
        items=dict(type='array', minItems=REQUIRED_COUNT, maxItems=REQUIRED_COUNT,
                   items=dict(type='object', additionalProperties=False, required=['input_id', 'scenario'],
                              properties=dict(input_id=text, scenario=scenario)))))
    return dict(version=1, source_kind=SOURCE_KIND, required_count=REQUIRED_COUNT, target_percent=TARGET_PERCENT,
                denominator=REQUIRED_COUNT, browser='chrome', source_document=deepcopy(SOURCE_DOCUMENT),
                max_batch_bytes=MAX_BATCH_BYTES, input_schema=input_schema, example_item=deepcopy(placeholder),
                fields=dict(items='20개 {input_id, scenario} 행',
                            scenario_required=sorted(_SCENARIO_REQUIRED), scenario_optional=sorted(_SCENARIO_OPTIONAL),
                            step_required=['order', 'action', 'target', 'expected_result'],
                            contract='version=1, scenario_id, steps[{order, action, target, checks}]'),
                example=dict(items=[placeholder]), example_only=True,
                notice='예시는 작성 형식만 보여줍니다. 실제 URLㆍ선택자ㆍ기대 결과를 확인한 서로 다른 시나리오 20건을 준비하세요. '
                       '입력 등록은 M03 산출물 또는 공식 승인 증빙을 의미하지 않습니다.')
