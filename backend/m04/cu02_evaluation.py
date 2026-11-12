"""CU02 등록 업무 전체를 한 건으로 세는 개발용 10건 평가 입력."""
from copy import deepcopy
from datetime import datetime
import re
import uuid

from ..evaluators import require
from .cu02 import parameters, prepare


CASE_COUNT = 10
COUNTING_UNIT = 'SCHEDULE_REGISTRATION'
INPUT_KEYS = {'date', 'title', 'description', 'browser'}
PRESENTATION_KEYS = {'visible_browser', 'action_delay_ms', 'keep_open_seconds'}


def presentation(payload):
    visible = payload.get('visible_browser', False)
    delay = payload.get('action_delay_ms', 0)
    hold = payload.get('keep_open_seconds', 0)
    require(type(visible) is bool and type(delay) is int and 0 <= delay <= 2000
            and type(hold) is int and 0 <= hold <= 60,
            '브라우저 표시·동작 간격·유지 시간을 확인하세요.')
    require(visible or (delay == 0 and hold == 0), '동작 간격과 유지 시간은 새 창 실행에서만 지정하세요.')
    return dict(visible_browser=visible, action_delay_ms=delay, keep_open_seconds=hold)


def build(payload, fixed_at):
    require(isinstance(payload, dict) and set(payload) <= INPUT_KEYS | PRESENTATION_KEYS,
            'CU02 날짜·제목·내용·브라우저와 실행 표시 설정만 지정하세요.')
    options = presentation(payload)
    values = parameters({key: value for key, value in payload.items() if key in INPUT_KEYS})
    require(len(values['title']) <= 105, '10건 평가의 제목은 번호를 제외하고 105자 이내로 입력하세요.')
    identity = uuid.uuid4().hex
    evaluation = dict(version=1, evaluation_id='CU02-EVAL-' + identity, workflow_id='CU02',
                      run_mode='DEVELOPMENT', official=False, fixed_at=fixed_at,
                      case_count=CASE_COUNT, counting_unit=COUNTING_UNIT,
                      counting_description='일정 1건의 신규 등록부터 저장 후 재조회까지 전체 성공을 1건으로 집계',
                      target_percent=90, required_success_count=9, cases=[])
    prepared = []
    for number in range(1, CASE_COUNT + 1):
        inputs = dict(values, title=values['title'] + f' [{identity[:8]}-{number:02d}]')
        item = prepare(inputs)
        prepared.append(item)
        evaluation['cases'].append(dict(case_id=f'CASE-{number:03d}', case_number=number,
                                       expected=deepcopy(item['parameters'])))
    return evaluation, prepared, options


def validate(evaluation, scripts, read_parameters):
    """Client bodies cannot provide metadata; internal snapshots must still agree."""
    require(isinstance(evaluation, dict)
            and isinstance(evaluation.get('evaluation_id'), str)
            and re.fullmatch(r'CU02-EVAL-[a-f0-9]{32}', evaluation['evaluation_id'])
            and evaluation.get('version') == 1
            and evaluation.get('workflow_id') == 'CU02'
            and evaluation.get('run_mode') == 'DEVELOPMENT' and evaluation.get('official') is False
            and evaluation.get('case_count') == CASE_COUNT
            and evaluation.get('counting_unit') == COUNTING_UNIT
            and evaluation.get('target_percent') == 90 and evaluation.get('required_success_count') == 9,
            'CU02 10건 평가의 집계 기준이 다릅니다.')
    stamp = evaluation.get('fixed_at')
    require(isinstance(stamp, str) and 1 <= len(stamp) <= 80, 'CU02 평가 사전 고정 시각이 필요합니다.')
    try:
        parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except ValueError:
        require(False, 'CU02 평가 사전 고정 시각이 잘못되었습니다.')
    require(parsed.tzinfo is not None, 'CU02 평가 사전 고정 시각에는 시간대가 필요합니다.')
    rows = evaluation.get('cases')
    require(isinstance(rows, list) and len(rows) == len(scripts) == CASE_COUNT,
            'CU02 평가는 고정 스크립트 10건을 각각 한 번 실행해야 합니다.')
    require(evaluation.get('script_ids') == [script['script_id'] for script in scripts]
            and len(set(evaluation['script_ids'])) == CASE_COUNT,
            'CU02 평가의 고정 스크립트 목록이 다릅니다.')
    titles = set()
    for number, (row, script) in enumerate(zip(rows, scripts), 1):
        require(isinstance(row, dict) and row.get('case_id') == f'CASE-{number:03d}'
                and row.get('case_number') == number
                and row.get('script_id') == script['script_id']
                and row.get('sha256') == script['sha256']
                and row.get('scenario_id') == script['scenario_id']
                and script.get('source_kind') == 'CU02_SCHEDULE_REGISTRATION'
                and script.get('workflow_id') == 'CU02' and script.get('business_step_required') is True,
                'CU02 평가 항목과 실행 원본의 연결이 다릅니다.')
        expected = read_parameters(script)
        require(row.get('expected') == expected and expected['title'] not in titles,
                'CU02 평가의 기대 입력값이 다르거나 제목이 중복되었습니다.')
        titles.add(expected['title'])
