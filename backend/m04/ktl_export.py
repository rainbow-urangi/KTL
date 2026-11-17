"""Readable, privacy-safe presentation of an already stored M04 execution.

No execution, regrading, file writes, or raw evidence replacement happens here.
Browser traces and free text from targets, values, errors, and logs are excluded.
"""
import math
import re

from ..ktl_evidence import csv_bytes, info_rows, number, verdict


_TERMINAL = frozenset(('PASS', 'FAIL', 'ERROR', 'TIMEOUT', 'SKIPPED'))
_FAILURES = _TERMINAL - {'PASS'}
_EXECUTION = re.compile(r'M04-RUN-[0-9a-f]{32}\Z')
_CASE = re.compile(r'CASE-[0-9]{3}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_NAMES = {
    'BU01': '개인정보 조회', 'BU02': '일정 조회', 'BU03': '일정 등록',
    'BU04': '전체업무 목록 조회', 'BU05': '전체업무 상세조회',
    'BU06': '일일보고 조회', 'BU07': '일일보고 작성',
    'BU08': '주간보고 조회', 'BU09': '주간보고 작성',
    'BU10': '월간보고 조회', 'BU11': '월간보고 작성',
    'BU12': '명함 목록 조회', 'BU13': '명함 상세조회', 'BU14': '명함 등록',
    'BU15': '거래처 목록 조회', 'BU16': '거래처 상세조회', 'BU17': '거래처 정보 등록',
    'BU18': '자산 목록 조회', 'BU19': '자산 상세조회', 'BU20': '자산 등록',
    'CU01': '일정 조회', 'CU02': '일정 등록', 'CU03': '일일보고 조회',
    'CU04': '일일보고 작성', 'CU05': '주간보고 조회', 'CU06': '주간보고 작성',
    'CU07': '월간보고 조회', 'CU08': '월간보고 작성', 'CU09': '명함 상세조회', 'CU10': '명함 등록',
}
_ACTIONS = {'open': '열기', 'navigate': '이동', 'click': '클릭',
            'input': '입력', 'type': '입력', 'fill_empty': '빈칸입력',
            'clear': '초기화', 'submit': '저장', 'select': '선택',
            'back': '뒤로', 'forward': '앞으로', 'refresh': '새로고침', 'verify': '확인'}
_CHECKS = {'visible': '표시', 'focus': '초점', 'value': '입력값',
           'fill_empty': '빈칸입력', 'text_equals': '문구',
           'text_contains': '문구포함', 'count': '대상수', 'text_count': '문구수',
           'cards_search': '명함검색', 'cards_state': '명함상태',
           'text_equals_target': '문구비교', 'nonempty': '내용',
           'native_submit_response': '저장응답', 'url_path': '경로'}
_SOURCES = {'SCENARIO_COMPILER': '시나리오 변환 코드', 'PREPARED': '사전 준비 코드',
            'LLM': 'LLM 생성 코드', 'M03_COMPILED_SCRIPT': 'M03 시나리오 변환 코드',
            'M01_OBSERVED_REPLAY': 'M01 관측 동작 재생', 'CU02_SCHEDULE_REGISTRATION': 'CU02 개발 예제',
            'M07_PREPARED_SCRIPT': 'M07 사전 준비 코드', 'M07_GENERATED_SCRIPT': 'M07 생성 코드',
            'UPLOADED_FIXED_SCRIPT': '업로드한 고정 스크립트'}
_FAILURE_LABELS = {'FAIL': '실패', 'ERROR': '오류', 'TIMEOUT': '시간초과', 'SKIPPED': '미실행'}


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _shown(value):
    return '미보관' if value is None else str(value)


def _status(value):
    return '성공' if value == 'PASS' else '실패' if value in _FAILURES else '대기'


def _identity(value, pattern):
    return value if isinstance(value, str) and pattern.fullmatch(value) else '미보관'


def _case_name(case, index):
    identity = case.get('business_unit_id')
    if identity not in _NAMES:
        identity = case.get('workflow_id')
    return identity + ' ' + _NAMES[identity] if identity in _NAMES else '시나리오 ' + str(index)


def _evidence(case, index):
    identity = _identity(case.get('case_id'), _CASE)
    source = 'report.json · ' + (identity if identity != '미보관' else '시나리오 ' + str(index))
    checksum = case.get('code_sha256') or case.get('sha256')
    if isinstance(checksum, str) and _HASH.fullmatch(checksum):
        source += ' · code_sha256=' + checksum
    return source


def _business_steps(case):
    # Legacy action traces must not be relabeled as business steps.
    return [step for step in case.get('steps', []) if isinstance(step, dict)] \
        if case.get('step_evidence_mode') == 'BUSINESS_STEPS' and isinstance(case.get('steps'), list) else []


def _checks(step):
    return [check for check in step.get('check_results', []) if isinstance(check, dict)] \
        if isinstance(step.get('check_results'), list) else []


def _condition_values(check):
    """Show recorded states and counts without disclosing free-text values."""
    kind = check.get('kind')
    expected, observed = check.get('expected'), check.get('observed')
    recorded = check.get('observation_status') in {'RECORDED', 'PARTIAL', 'REDACTED'}
    actual = '성공' if check.get('status') == 'PASS' else '실패' if check.get('status') in _FAILURES else '미확인'
    if not recorded:
        actual = '미확인'
    wanted, detail = '충족', ''
    if kind == 'visible':
        wanted = '표시' if expected is True else '숨김' if expected is False else '미확인'
        count = _count(observed.get('visible_count')) if isinstance(observed, dict) and recorded else None
        actual = '표시' if count is not None and count > 0 else '숨김' if count == 0 else '미확인'
        if count is not None:
            detail = '표시 ' + str(count) + '개'
    elif kind in {'count', 'text_count'}:
        desired_count = _count(expected.get('count')) if kind == 'text_count' and isinstance(expected, dict) else _count(expected)
        actual_count = _count(observed) if recorded else None
        wanted = str(desired_count) + '개' if desired_count is not None else '미확인'
        actual = str(actual_count) + '개' if actual_count is not None else '미확인'
    elif kind == 'nonempty':
        wanted = '존재'
        found = observed.get('left_nonempty') if isinstance(observed, dict) and recorded else None
        actual = '존재' if found is True else '없음' if found is False else '미확인'
    elif kind == 'text_equals_target':
        wanted = '일치'
        equal = observed.get('equal') if isinstance(observed, dict) and recorded else None
        actual = '일치' if equal is True else '불일치' if equal is False else '미확인'
    elif kind in {'value', 'text_equals', 'url_path'}:
        wanted = '일치'
        actual = ('일치' if actual == '성공' else '불일치' if actual == '실패' else '미확인') \
            if observed is not None else '미확인'
    elif kind == 'text_contains':
        wanted = '포함'
        found = observed.get('match_found') if isinstance(observed, dict) and recorded else None
        actual = '포함' if found is True else '없음' if found is False else '미확인'
    elif kind == 'focus':
        wanted = '활성' if expected is True else '비활성' if expected is False else '충족'
        actual = '활성' if recorded and observed is True else '비활성' if recorded and observed is False else '미확인'
    if check.get('observation_status') == 'REDACTED':
        detail = '입력값 비공개'
    return wanted, actual, detail


def export_ktl_evidence(job):
    """Return twelve-column UTF-8 BOM CSV from the supplied execution snapshot."""
    if not isinstance(job, dict):
        raise ValueError('M04 execution snapshot must be a dictionary')
    cases = [case for case in job.get('cases', []) if isinstance(case, dict)] if isinstance(job.get('cases'), list) else []
    counts = job.get('counts') if isinstance(job.get('counts'), dict) else {}
    result = job.get('result') if isinstance(job.get('result'), dict) else {}
    execution_id = _identity(job.get('execution_id'), _EXECUTION)
    rows = info_rows('M04 자동실행 성공률', execution_id, job.get('completed_at') or job.get('started_at'),
                     mode='DEVELOPMENT', time_label='완료시각(KST)' if job.get('completed_at') else '시작시각(KST)')
    total = _count(counts.get('total_execution_count'))
    success = _count(counts.get('successful_execution_count'))
    failed = _count(counts.get('failed_execution_count'))
    observed_success = sum(case.get('status') == 'PASS' for case in cases)
    observed_failures = sum(case.get('status') in _FAILURES for case in cases)
    consistent = (total is not None and total > 0 and total == len(cases) and success == observed_success
                  and failed == observed_failures and success + failed == total)
    score = result.get('score')
    complete = (job.get('status') == 'COMPLETED' and result.get('status') == 'COMPLETED' and consistent
                and type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100
                and math.isclose(score, success / total * 100, rel_tol=0, abs_tol=1e-8))
    measured = score if complete else None
    target = result.get('target')
    if type(target) not in (int, float) or not math.isfinite(target):
        target = 90
    met = result.get('threshold_met')
    if type(met) is not bool or not complete:
        met = measured >= target if complete else None
    actual_total = total if total is not None else len(cases)
    scope = ('단건 1/10건' if actual_total == 1 else
             '부분 ' + str(actual_total) + '/10건' if actual_total < 10 else
             '고정 10건' if actual_total == 10 else str(actual_total) + '건')
    dataset = _identity(job.get('dataset_id'), re.compile(r'm04-development-[0-9a-f]{12}\Z'))
    evaluator = _identity(result.get('evaluator_version'), re.compile(r'external-integration-v[0-9A-Za-z_.-]{1,80}\Z'))
    compilers = sorted({case['compiler_version'] for case in cases
                        if isinstance(case.get('compiler_version'), str)
                        and re.fullmatch(r'm03-selenium-compiler-[0-9A-Za-z_.-]{1,80}', case['compiler_version'])})
    source_keys = [case.get('code_source') if case.get('code_source') in _SOURCES else case.get('source_kind') for case in cases]
    sources = sorted({key + ' · ' + _SOURCES[key] if key in _SOURCES else '출처 미보관' for key in source_keys})
    rows.extend([
        {'구분': '정보', '검증 항목': '범위', '실제 결과': scope},
        {'구분': '정보', '검증 항목': '버전', '실제 결과': evaluator + ' / ' + (', '.join(compilers) or '미보관')},
        {'구분': '정보', '검증 항목': '데이터셋', '실제 결과': dataset},
        {'구분': '정보', '검증 항목': '출처', '실제 결과': ', '.join(sources) or '미보관'},
        {'구분': '정보', '검증 항목': '원본',
         '근거': ('/api/development/m04/executions/' + execution_id + '/artifacts/steps.csv') if execution_id != '미보관' else '원실행 ID 미보관'},
    ])
    if any(case.get('source_synthetic') is True for case in cases):
        rows.append({'구분': '정보', '검증 항목': '자료', '실제 결과': '합성 포함'})
    rows.append({'구분': '요약', '검증 항목': '성공률',
                 '기대 결과': number(target) + '% 이상',
                 '실제 결과': '성공 ' + _shown(success) + ' / 전체 ' + _shown(total)
                              + ' · 실패 ' + _shown(failed) + ('' if complete else ' · 대기'),
                 '판정': verdict(met), '분자': success, '분모': total, '측정값': number(measured), '단위': '%',
                 '근거': 'report.json · counts / result.score'})
    for index, case in enumerate(cases, 1):
        name, source = _case_name(case, index), _evidence(case, index)
        steps = _business_steps(case)
        checks = [check for step in steps for check in _checks(step)]
        needed_steps = _count(case.get('required_step_count'))
        needed_checks = _count(case.get('expected_check_count'))
        step_total = needed_steps if needed_steps is not None else len(steps) if steps else None
        check_total = needed_checks if needed_checks is not None else len(checks) if checks else None
        actual = ('단계 ' + str(sum(step.get('status') == 'PASS' for step in steps)) + '/' + _shown(step_total)
                  + ' · 조건 ' + str(sum(check.get('status') == 'PASS' for check in checks)) + '/' + _shown(check_total)) \
            if steps else '상세 미보관'
        status = case.get('status')
        if status in _FAILURE_LABELS:
            source += ' · ' + _FAILURE_LABELS[status]
        rows.append({'구분': '시나리오', '번호': index, '업무/시나리오': name,
                     '검증 항목': '실행', '기대 결과': '완료',
                     '실제 결과': actual, '판정': _status(status),
                     '분자': 1 if status == 'PASS' else 0 if status in _FAILURES else None,
                     '분모': 1, '단위': '건', '근거': source})
        for step_index, step in enumerate(steps, 1):
            step_status, conditions = step.get('status'), _checks(step)
            step_number = str(index) + '.' + str(step_index)
            rows.append({'구분': '단계', '번호': step_number, '업무/시나리오': name,
                         '검증 항목': _ACTIONS.get(step.get('action'), '동작'),
                         '기대 결과': '완료',
                         '실제 결과': '조건 ' + str(sum(check.get('status') == 'PASS' for check in conditions)) + '/' + str(len(conditions)) if conditions else '미확인',
                         '판정': _status(step_status), '단위': '단계', '근거': source + ' · 업무 단계 ' + str(step_index)})
            for check_index, check in enumerate(conditions, 1):
                check_status = check.get('status')
                expected, observation, detail = _condition_values(check)
                if check_status in _FAILURE_LABELS:
                    detail = (detail + ' · ' if detail else '') + _FAILURE_LABELS[check_status]
                rows.append({'구분': '조건', '번호': step_number + '.' + str(check_index), '업무/시나리오': name,
                             '검증 항목': _CHECKS.get(check.get('kind'), '조건'),
                             '기대 결과': expected, '실제 결과': observation,
                             '판정': _status(check_status), '단위': '항목',
                             '근거': source + ' · 단계 ' + str(step_index) + ' · 조건 ' + str(check_index)
                                     + (' · ' + detail if detail else '')})
    return csv_bytes(rows)
