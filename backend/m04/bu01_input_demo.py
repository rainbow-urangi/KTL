"""User-requested BU01 text-entry demonstration; never submits the profile.

These supplemental M04 steps are separate from the frozen M03 observations.
Selectors and ordering were checked against the actual personal-info form.
The native date picker retains its current value; this module handles text boxes.
"""
from copy import deepcopy

from . import checks


VERSION = 'bu01-text-entry-demo-v2-empty-only'
FORM = 'form.personal-info-page'
PATH = '/mypage/personal-info'
FIELDS = (
    ('#personal-name', '성명', '김민준'),
    ('#personal-email-primary', '업무용 이메일', 'minjun.kim@example.com'),
    ('#personal-email-secondary', '보조 이메일', 'rainbow.research@example.com'),
    ('#personal-duty', '담당업무', '기술개발'),
    ('#personal-office-phone', '전화번호', '02-0000-2040'),
    ('#personal-emergency-phone', '비상연락망', '010-0000-2040'),
    ('#personal-postal-code', '우편번호', '00000'),
    ('input[placeholder="주소"]', '주소', '서울특별시 강동구 천호동'),
    ('input[placeholder="상세주소"]', '상세주소', '레인보우 기술연구소'),
    ('#personal-gender', '성별', '표기 안 함'),
    ('#personal-introduction', '자기소개', '레인보우 기술연구소에서 기술개발 업무를 담당하고 있습니다.'),
    ('#personal-workplace', '근무처', '레인보우 기술연구소'),
    ('#personal-position', '직위', '주임연구원'),
    ('#personal-degree', '학위', '학사'),
)


def _target(selector):
    return dict(by='css selector', value=FORM + ' ' + selector)


def extend(prepared):
    result = deepcopy(prepared)
    scenario = result['scenario']
    if scenario.get('business_unit_id') != 'BU01':
        raise ValueError('BU01 입력 시연은 검토된 BU01 실행 연결에만 추가합니다.')
    original_count = len(scenario['steps'])
    definitions = result['contract']['steps']
    supplemental = []

    def add(action, selector, expectations, label, phase, value=None):
        order = len(scenario['steps']) + 1
        step = dict(order=order, action=action, target=FORM + ' ' + selector,
                    expected_result=label, execution_origin='USER_REQUESTED_BU01_INPUT_DEMO')
        if value is not None:
            step['value'] = value
        scenario['steps'].append(step)
        definitions.append(dict(order=order, action=action, target=_target(selector), checks=expectations))
        supplemental.append(dict(order=order, phase=phase, target=_target(selector),
                                 origin='USER_REQUESTED_M04_SUPPLEMENT', observed_in_m03=False))

    # Verify the reviewed inventory without changing existing personal values.
    selectors = [FORM + ' ' + selector for selector, _, _ in FIELDS]
    inventory = ', '.join(selectors)
    add('verify', '#personal-name',
        [dict(kind='url_path', expected=PATH),
         dict(kind='count', target=dict(by='css selector', value=inventory), expected=len(FIELDS))]
        + [dict(kind='visible', target=_target(selector), expected=True) for selector, _, _ in FIELDS],
        '개인정보 수정 화면의 입력란을 확인한다.', 'PREFLIGHT')

    for selector, label, value in FIELDS:
        add('fill_empty', selector,
            [dict(kind='fill_empty', target=_target(selector), expected=value)],
            label + '이 비어 있으면 시험 값을 입력하고 기존 값은 유지한다.', 'FILL_EMPTY', value=value)
    add('verify', '#personal-name',
        [dict(kind='url_path', expected=PATH)]
        + [dict(kind='fill_empty', target=_target(selector), expected=value) for selector, _, value in FIELDS],
        '빈 입력란에 입력한 값과 기존 값 보존을 확인한다.', 'FILLED_FORM')

    scenario['binding_version'] = VERSION
    scenario['execution_purpose'] = '개인정보 텍스트 입력 시연'
    scenario['screenshot_checkpoints'] = dict(before=original_count + 1,
                                             after=len(scenario['steps']))
    result['contract'] = checks.prepare_contract(dict(scenario, execution_contract=dict(
        version=1, scenario_id=scenario['scenario_id'], steps=definitions)))
    result.update(binding_version=VERSION, remediation_provenance=dict(
        kind='USER_REQUESTED_BU01_INPUT_DEMO', original_m03_step_count=original_count,
        original_m03_modified=False, execution_scope='DEVELOPMENT_TEXT_ENTRY_ONLY',
        input_policy='EMPTY_ONLY_IN_REVIEWED_FORM_ORDER',
        persisted_business_writes=False, submit_included=False, field_count=len(FIELDS),
        unchanged_controls=['#personal-birth-date'], supplemental_steps=supplemental))
    return result
