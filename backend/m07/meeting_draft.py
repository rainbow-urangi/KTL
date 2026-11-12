"""검토 버튼으로만 불러오는 업무 정의 기반 20개 입력 초안.

여기서 사용하는 것은 실행 대상과 기대 조건이며 Python 코드가 아니다.
초안을 시험 데이터 승인이나 실제 LLM 생성·실행 증빙으로 취급하지 않는다.
"""
from copy import deepcopy
from datetime import date, timedelta
import uuid

from . import workflows
from .meeting import prepare_batch
from .workflow_templates import build
from ..m04 import cu02


def _replace(value, before, after):
    if isinstance(value, str):
        return value.replace(before, after)
    if isinstance(value, list):
        return [_replace(item, before, after) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, before, after) for key, item in value.items()}
    return value


def draft():
    base = workflows.defaults()
    identity = uuid.uuid4().hex[:8]
    items = []
    for workflow_id, name, kind, procedures in workflows.WORKFLOWS:
        for variant in (1, 2):
            values = deepcopy(base)
            values.update(title=f'KTL LLM {identity} {workflow_id}-{variant}',
                          company=f'KTL 시험회사 {identity} {variant}',
                          description=f'KTL LLM 시험 {workflow_id} 입력 {variant}')
            if kind == '등록' and variant == 2:
                values['date'] = (date.fromisoformat(base['date']) + timedelta(days=1)).isoformat()
            input_id = f'INPUT-{len(items)+1:03d}'
            scenario_id = f'{workflow_id}-LLM-{identity}-{variant}'
            if workflow_id == 'CU02':
                # The existing definition builder also returns a PREPARED script.
                # Only its human-defined scenario/contract is selected here; no
                # Python bytes are returned, stored or passed to the LLM.
                source = cu02.prepare({key: values[key] for key in ('date', 'title', 'description')} | {'browser': 'chrome'})
                steps, contract = deepcopy(source['scenario']['steps']), deepcopy(source['contract'])
                checkpoints = source['scenario']['screenshot_checkpoints']
            else:
                template = workflows.schedule_query(values, scenario_id) if workflow_id == 'CU01' else build(workflow_id, values, scenario_id)
                steps, contract, checkpoints = deepcopy(template['steps']), deepcopy(template['contract']), template['checkpoints']
            contract['scenario_id'] = scenario_id
            if kind == '조회' and variant == 2:
                if workflow_id == 'CU01':
                    steps = _replace(steps, 'nth-child(1 of ', 'nth-child(2 of ')
                    contract = _replace(contract, 'nth-child(1 of ', 'nth-child(2 of ')
                else:
                    steps = _replace(steps, 'tr:first-child', 'tr:nth-child(2)')
                    contract = _replace(contract, 'tr:first-child', 'tr:nth-child(2)')
            for step, rule in zip(steps, contract['steps']):
                if step['action'] in {'open', 'navigate'}:
                    step['url'] = rule['target']['url']
                elif step['action'] in {'input', 'type'}:
                    step['value'] = next(check['expected'] for check in rule['checks']
                                         if check['kind'] == 'value' and check.get('target') == rule['target'])
                elif step['action'] == 'select':
                    step['value'] = values['date']
            hints = (
                '실제 업무 절차: ' + ' → '.join(procedures) + '. '
                '로그인과 Chrome 초기화는 ktl_runtime의 인증 도우미를 사용한다. '
                '입력 단계에서는 계약의 모든 value 조건을 채우고 실제 값을 비교한다. '
                '조회는 계약이 가리키는 기존 행을 클릭한 후 상세값을 확인하며 개인정보를 출력하지 않는다. '
                '날짜 버튼을 열면 .work-date-calendar__month는 YYYY.MM이고, '
                '.work-date-calendar button[aria-label="이전 달"], button[aria-label="다음 달"]로 월을 이동한다. '
                '날짜는 .work-date-calendar button[aria-label="YYYY-MM-DD"]를 클릭한다. '
                '보고서 저장 성공 알림은 .work-report-message-modal__button으로 닫는다. '
                '저장 후 새로고침한 목록에서 생성한 제목(보고서) 또는 회사명(명함)이 일치하는 행을 구별해 상세창을 연다. '
                '보고서 목록 .work-report-table tbody tr의 .work-report-table__title button을 사용한다. '
                '명함 목록 .business-card-table tbody tr의 세 번째 td가 회사명이며 .business-card-table__title button으로 상세를 연다. '
                '내용과 업무일자 또는 명함 필드가 비동기로 채워질 때까지 기대값을 기다린다. '
                '다른 요소나 다른 기록으로 임의 변경하지 않는다.'
            )
            conditions = ['등록은 시험 계정의 빈 신규등록 폼에서 진행하고 고유 시험 제목·회사명을 사용한다.'] if kind == '등록' else [
                f'조회 대상에 기존 기록이 최소 {variant}개 필요하다. 일정은 지정 날짜의 기록을 사용한다.']
            scenario = dict(scenario_id=scenario_id, scenario_name=name + (' · 기본 입력' if variant == 1 else ' · 두 번째 입력'),
                            business_unit_id=workflow_id, workflow_id=workflow_id, steps=steps,
                            execution_contract=contract, screenshot_checkpoints=deepcopy(checkpoints),
                            description=hints, preconditions=conditions)
            items.append(dict(input_id=input_id, scenario=scenario))
    prepare_batch({'items': items})
    return dict(draft=True, approved_for_official=False,
                description='PDF의 10개 업무에서 서로 다른 입력·조회 대상을 구성한 검토용 20건 초안입니다. '
                            '회의에서 확정한 입력 목록이 아니며 URL·선택자·기대값·기존 기록을 확인한 뒤 사용하세요. '
                            '코드나 성공 결과를 포함하지 않으며 생성 버튼은 실제 LLM에 새 코드를 요청합니다.',
                items=items)
