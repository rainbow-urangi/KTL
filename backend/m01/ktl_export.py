"""Human-readable M01 evidence derived from the verified original comparison."""
import csv
import hashlib
import io

from ..evaluators import require
from ..ktl_evidence import csv_bytes, info_rows, number, verdict
from .score import _unescape, token, verify


TYPES = dict(navigation='이동', click='클릭', input='입력', select_change='선택',
             submit_save='제출', popup='팝업', network='네트워크', key_input='키입력')
FIELDS = dict(session_id='세션', event_time='시각', event_type='유형',
              page_url='주소', page_title='제목', target_key='대상')


def export_ktl_evidence(result, original):
    verification = verify(original, result)
    require(verification.get('verified') is True, 'M01 original evidence must pass verification')
    measurement = result.get('measurement')
    require(isinstance(measurement, dict), 'M01 weighted measurement is unavailable')
    counts = measurement['counts']
    rows = info_rows('M01 수집정확도', result['comparison_id'], result.get('created_at'),
                     result['run_mode'], time_label='비교시각(KST)')
    base = '/api/development/m01/comparisons/' + result['comparison_id']
    for label, value in (
        ('시나리오', result.get('scenario_name', '')),
        ('기준', result.get('scenario_version', '')),
        ('데이터셋', result['dataset_id']),
        ('범위', '선택세션' if result.get('session_id') is not None else 'CSV전체'),
        ('세션해시', token(result.get('session_id') or '')),
        ('정책', result.get('matching_policy', result.get('evaluator_version', ''))),
        ('대상', '필수이벤트'),
        ('검산', '일치'),
        ('근거파일', base + '/evidence.csv'),
        ('근거해시', hashlib.sha256(original).hexdigest()),
    ):
        rows.append({'구분': '정보', '검증 항목': label, '실제 결과': value,
                     '근거': '수집 여부; 업무 완료·입력 정확성 제외' if label == '대상' else
                             '원본 CSV 재계산' if label == '검산' else ''})
    for kind, digest in result.get('input_sha256', {}).items():
        if kind in ('collector_csv', 'expected_csv'):
            rows.append({'구분': '정보', '검증 항목':
                         '수집해시' if kind == 'collector_csv' else '기준해시',
                         '실제 결과': digest, '근거': 'SHA-256'})
    scenario = result.get('scenario_name', '')
    rows.extend([
        {'구분': '요약', '업무/시나리오': scenario, '검증 항목': 'C1 수집률',
         '분자': counts['collected_required_event_count'], '분모': counts['defined_required_event_count'],
         '측정값': number(measurement['c1']), '단위': '%', '근거': '수집수/필수수'},
        {'구분': '요약', '업무/시나리오': scenario, '검증 항목': 'C2 누락률',
         '분자': counts['missing_required_field_count'],
         '분모': counts['total_collected_events'] * counts['required_field_count'],
         '측정값': number(measurement['c2']), '단위': '%', '근거': '누락필드수/전체필드수'},
        {'구분': '요약', '업무/시나리오': scenario, '검증 항목': 'C3 유형커버리지',
         '분자': counts['collected_event_type_count'], '분모': counts['defined_event_type_count'],
         '측정값': number(measurement['c3']), '단위': '%', '근거': '관측유형수/정의유형수'},
        {'구분': '요약', '업무/시나리오': scenario, '검증 항목': '수집정확도',
         '기대 결과': number(measurement['target']) + '% 이상',
         '판정': verdict(measurement.get('threshold_met')),
         '측정값': number(measurement['collection_accuracy']), '단위': '%',
         '근거': measurement['formula']},
    ])
    parsed = [{key: _unescape(value) for key, value in row.items()}
              for row in csv.DictReader(io.StringIO(original.decode('utf-8-sig'), newline=''))]
    actual = {row['csv_row']: row for row in parsed if row['row_kind'] == 'COLLECTED'}
    labels = {row['expected_event_id']: row.get('label', '')
              for row in result.get('presence_truth', {}).get('expected', [])}
    for item in parsed:
        if item['row_kind'] != 'EXPECTED':
            continue
        included = item['status'] == 'MATCHED'
        observed = actual.get(item.get('matched_csv_row'), {})
        missing = [name for name in observed.get('missing_fields', '').split(',') if name]
        rows.append({'구분': '이벤트', '번호': item['sequence'], '업무/시나리오': scenario,
                     '검증 항목': labels.get(item['expected_event_id']) or TYPES.get(
                         item['expected_event_type'], '필수 이벤트'),
                     '기대 결과': '수집', '실제 결과': '수집' if included else '누락',
                     '판정': verdict(included), '분자': int(included), '분모': 1,
                     '근거': item['expected_event_id'] + (
                         ' · 원본행=' + item['matched_csv_row'] + ' · 누락필드=' + str(len(missing))
                         if included else '')})
    for field in measurement.get('required_fields', []):
        missing_count = measurement['missing_fields'][field]
        rows.append({'구분': '필드', '검증 항목': FIELDS.get(field, field),
                     '기대 결과': '완비', '실제 결과': '누락' if missing_count else '완비',
                     '분자': measurement['missing_fields'][field], '분모': counts['total_collected_events'],
                     '단위': '건', '근거': '누락수/수집수 · ' + field})
    for event_type, count in measurement.get('type_counts', {}).items():
        rows.append({'구분': '유형', '검증 항목': TYPES.get(event_type, event_type),
                     '실제 결과': count, '단위': '건', '근거': '선택범위 · ' + event_type})
    unclassified = measurement.get('unclassified_event_count')
    if type(unclassified) is int and unclassified >= 0:
        rows.append({'구분': '유형', '검증 항목': '미분류', '실제 결과': unclassified,
                     '단위': '건', '근거': '유형 분류 없음 · C3 유형수 제외'})
    return csv_bytes(rows)
