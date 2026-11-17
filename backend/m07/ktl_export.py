"""Read-only Korean evidence view of a preserved ten-code syntax result."""
from datetime import datetime
import math
import re

from ..evaluators import require
from ..ktl_evidence import csv_bytes, info_rows, number, verdict


BUSINESS_NAMES = {
    'CU01': '일정 조회', 'CU02': '일정 등록', 'CU03': '일일보고 조회',
    'CU04': '일일보고 작성', 'CU05': '주간보고 조회', 'CU06': '주간보고 작성',
    'CU07': '월간보고 조회', 'CU08': '월간보고 작성',
    'CU09': '명함 상세조회', 'CU10': '명함 등록',
}


def existing_ktl_csv(result, cases, *, run_id, manifest_sha256, source_generation_id):
    """Validate saved evidence consistency; never recheck the Python source."""
    require(isinstance(result, dict) and result.get('run_id') == run_id
            and re.fullmatch(r'M07-CHECK-[a-f0-9]{32}', run_id)
            and result.get('status') == 'COMPLETED' and result.get('sample_count') == 10
            and result.get('source_manifest_sha256') == manifest_sha256
            and re.fullmatch(r'[a-f0-9]{64}', manifest_sha256)
            and result.get('source_generation_id') == source_generation_id
            and re.fullmatch(r'M07-GEN-[a-f0-9]{32}', source_generation_id)
            and result.get('official_pass') is None and result.get('new_generation') is False
            and type(result.get('gpt_request_count')) is int and result['gpt_request_count'] == 0
            and type(result.get('browser_started_count')) is int and result['browser_started_count'] == 0,
            '보관 문법검사 결과의 출처·범위가 다릅니다.')
    require(isinstance(cases, list) and len(cases) == 10 and isinstance(result.get('cases'), list)
            and len(result['cases']) == 10, '보관 문법검사 10건이 필요합니다.')
    identifiers = set()
    for source, actual in zip(cases, result['cases']):
        require(isinstance(source, dict) and isinstance(actual, dict)
                and isinstance(source.get('case_id'), str)
                and re.fullmatch(r'CASE-0(?:0[1-9]|10)', source['case_id'])
                and source['case_id'] not in identifiers
                and all(actual.get(key) == source.get(key) for key in
                        ('case_id', 'scenario_id', 'workflow_id', 'code_sha256', 'expected_syntax_status'))
                and re.fullmatch(r'[a-f0-9]{64}', source.get('code_sha256', ''))
                and actual.get('syntax_status') in ('PASS', 'FAIL')
                and actual.get('expected_syntax_status') in ('PASS', 'FAIL')
                and type(actual.get('matches_expected')) is bool
                and actual['matches_expected'] == (actual['syntax_status'] == actual['expected_syntax_status']),
                '보관 문법검사와 원본 코드·기존 판정의 연결이 다릅니다.')
        identifiers.add(source['case_id'])
    passed = sum(row['syntax_status'] == 'PASS' for row in result['cases'])
    matched = sum(row['matches_expected'] for row in result['cases'])
    require(type(result.get('syntax_pass_count')) is int and result['syntax_pass_count'] == passed
            and type(result.get('syntax_fail_count')) is int and result['syntax_fail_count'] == 10 - passed
            and type(result.get('matches_expected_count')) is int and result['matches_expected_count'] == matched
            and type(result.get('score')) in (int, float) and math.isfinite(result['score'])
            and result['score'] == passed / 10 * 100 and result.get('target') == 80
            and type(result.get('threshold_met')) is bool and result['threshold_met'] == (result['score'] >= 80),
            '보관 문법검사의 점수·분모·판정이 서로 다릅니다.')
    checked_at = result.get('checked_at')
    require(isinstance(checked_at, str), '보관 문법검사 시각이 필요합니다.')
    try:
        timestamp = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
    except ValueError:
        timestamp = None
    require(timestamp is not None and timestamp.tzinfo is not None, '보관 문법검사 시각의 시간대가 필요합니다.')

    rows = info_rows('M07', run_id, checked_at, mode='DEVELOPMENT', time_label='검사시각(KST)')
    source_ref = run_id + '.json'
    rows.extend([
        {'구분': '정보', '검증 항목': '범위', '실제 결과': '기존코드 문법검사', '분모': 10,
         '근거': 'Python 문법 · 코드실행 미포함'},
        {'구분': '정보', '검증 항목': '출처', '실제 결과': '기존LLM', '근거': source_generation_id},
        {'구분': '정보', '검증 항목': '목록해시', '실제 결과': manifest_sha256, '근거': source_ref},
        {'구분': '정보', '검증 항목': 'GPT호출', '실제 결과': '미호출', '측정값': '0', '단위': '회',
         '근거': 'gpt_request_count=0'},
        {'구분': '정보', '검증 항목': '코드실행', '실제 결과': '미실행', '측정값': '0', '단위': '회',
         '근거': 'browser_started_count=0'},
        {'구분': '요약', '검증 항목': '문법통과율', '기대 결과': '80.00% 이상',
         '실제 결과': str(result['syntax_pass_count']) + '/10', '판정': verdict(result['threshold_met']),
         '분자': result['syntax_pass_count'], '분모': 10, '측정값': number(result['score']), '단위': '%',
         '근거': '정상코드/기존코드 × 100 · ' + source_ref},
        {'구분': '검산', '검증 항목': '판정일치', '기대 결과': '일치',
         '실제 결과': '일치' if matched == 10 else '불일치',
         '판정': '일치' if matched == 10 else '불일치',
         '분자': result['matches_expected_count'], '분모': 10,
         '측정값': number(matched / 10 * 100), '단위': '%',
         '근거': '기존판정 비교 · 문법통과율과 별도'},
    ])
    for index, (source, actual) in enumerate(zip(cases, result['cases']), 1):
        business = source.get('business_unit_id')
        name = business + ' ' + BUSINESS_NAMES[business] if isinstance(business, str) and business in BUSINESS_NAMES else '기존 코드 ' + source['case_id']
        previous = '정상' if actual['expected_syntax_status'] == 'PASS' else '오류'
        comparison = '일치' if actual['matches_expected'] else '불일치'
        rows.append({'구분': '문법', '번호': index, '업무/시나리오': name,
                     '검증 항목': 'Python 문법', '기대 결과': '정상',
                     '실제 결과': '정상' if actual['syntax_status'] == 'PASS' else '오류',
                     '판정': verdict(actual['syntax_status'] == 'PASS'),
                     '근거': source_ref + ' · ' + source['case_id'] + ' · 기존판정=' + previous
                             + ' · 비교=' + comparison + ' · 코드SHA-256=' + source['code_sha256']})
    return csv_bytes(rows)
