"""Readable CSV presentation; evaluators and original evidence remain unchanged."""
import csv
from datetime import datetime, timedelta, timezone
import io
import math
import unicodedata


INPUT_COLUMNS = ('구분', '번호', '업무/시나리오', '검증 항목', '기대 결과', '실제 결과',
                 '판정', '분자', '분모', '측정값', '단위', '근거')
COLUMNS = ('구분', '번호', '업무', '항목', '기대', '결과',
           '판정', '분자', '분모', '측정값', '단위', '근거')
KST = timezone(timedelta(hours=9))


def number(value, digits=2):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return ''
    return format(value, '.' + str(digits) + 'f')


def local_time(value):
    if not isinstance(value, str) or not value.strip():
        return '기록 없음'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return '시간대 확인 필요'
        return parsed.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return '시각 확인 필요'


def verdict(value):
    if value is True:
        return '통과'
    if value is False:
        return '미달'
    return '대기'


def info_rows(metric_id, run_id, when, mode='DEVELOPMENT', *, time_label='평가시각(KST)'):
    rows = [dict(구분='정보', **{'검증 항목': key, '실제 결과': value}) for key, value in (
        ('시험', metric_id), ('실행ID', run_id), (time_label, local_time(when)),
        ('평가', {'DEVELOPMENT': '개발', 'REFERENCE': '참고', 'OFFICIAL': '공식'}.get(mode, mode)),
        ('공식', '미판정'),
    )]
    rows[3]['근거'] = mode
    rows[4]['근거'] = 'official_pass=null'
    return rows


def _cell(value):
    if value is None:
        return ''
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError('Readable evidence cells must be scalar values')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Readable evidence cells must be finite')
    text = str(value)
    text = ''.join(' ' if char.isspace() else char for char in text
                   if unicodedata.category(char) not in {'Cc', 'Cf'} or char.isspace())
    text = ' '.join(text.split())
    if text.startswith(('=', '+', '-', '@')):
        text = "'" + text
    return text


def csv_bytes(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator='\r\n')
    writer.writeheader()
    for row in rows:
        if not isinstance(row, dict) or set(row) - set(INPUT_COLUMNS):
            raise ValueError('Readable evidence row has unsupported columns')
        writer.writerow({label: _cell(row.get(key)) for key, label in zip(INPUT_COLUMNS, COLUMNS)})
    return output.getvalue().encode('utf-8-sig')
