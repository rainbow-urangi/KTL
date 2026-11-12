"""Evidence-only UTC validation; never alters raw rows or frozen engine features.

Policies are bound to byte-hashed raw exports and independently reviewed through
full-context approval. A timezone name alone is not evidence for a naive export.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .evaluators import EvaluationError, require

POLICY_SCHEMA = 'm05-timestamp-evidence-v1'
AUTHORITY_SCHEMA = 'm05-export-timezone-authority-v1'


def parsed_datetime(value):
    require(isinstance(value, str) and value.strip(), 'TIMESTAMP_MISSING')
    # Python versions differ: recent fromisoformat() silently truncates excess
    # fractional digits. Evidence parsing must be identical and lossless on all
    # supported runtimes; reject unsupported precision before calling it.
    require(all(len(part) <= 6 for part in re.findall(r'[.,]([0-9]+)', value)),
            'TIMESTAMP_PRECISION_UNSUPPORTED')
    require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}'
                         r'(?:[.,][0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?', value) is not None,
            'INVALID_TIMESTAMP_FORMAT')
    offset = re.search(r'([+-])([0-9]{2}):([0-9]{2})$', value)
    require(offset is None or (int(offset[2]) < 24 and int(offset[3]) < 60),
            'INVALID_TIMESTAMP_OFFSET')
    try:
        # Decimal comma is equivalent, but Python 3.10 does not accept it.
        # Normalize only this validation-local string, never raw or features.ts.
        return datetime.fromisoformat(value.replace(',', '.').replace('Z', '+00:00'))
    except ValueError as exc:
        raise EvaluationError('INVALID_TIMESTAMP') from exc


def aware_instant(value):
    value = parsed_datetime(value)
    require(value.tzinfo is not None and value.utcoffset() is not None,
            'TIMESTAMP_TIMEZONE_REQUIRED')
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise EvaluationError('INVALID_TIMESTAMP') from exc


def named_timezone(name):
    require(isinstance(name, str), 'INVALID_TIMESTAMP_TIMEZONE')
    if name == 'UTC':
        return timezone.utc
    match = re.fullmatch(r'([+-])(\d{2}):(\d{2})', name)
    if match:
        hours, minutes = int(match[2]), int(match[3])
        require(hours <= 14 and minutes < 60 and (hours < 14 or minutes == 0),
                'INVALID_TIMESTAMP_TIMEZONE')
        return timezone(timedelta(minutes=(hours * 60 + minutes) * (1 if match[1] == '+' else -1)))
    # Abbreviations such as CST are ambiguous. Require an IANA region or offset.
    require('/' in name, 'INVALID_TIMESTAMP_TIMEZONE')
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise EvaluationError('INVALID_TIMESTAMP_TIMEZONE') from exc


def local_instant(value, tz):
    """Reject nonexistent or ambiguous local wall times rather than choosing fold."""
    candidates = set()
    try:
        for fold in (0, 1):
            candidate = value.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
            if candidate.astimezone(tz).replace(tzinfo=None) == value:
                candidates.add(candidate)
    except (ValueError, OverflowError) as exc:
        raise EvaluationError('INVALID_TIMESTAMP') from exc
    require(len(candidates) == 1, 'AMBIGUOUS_OR_NONEXISTENT_LOCAL_TIMESTAMP')
    return candidates.pop()


def json_path(value, path):
    require(isinstance(path, list) and path and all(isinstance(k, str) and k for k in path),
            'INVALID_TIMESTAMP_EVIDENCE_PATH')
    for key in path:
        require(isinstance(value, dict) and key in value, 'TIMESTAMP_EVIDENCE_FIELD_MISSING')
        value = value[key]
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_TIMESTAMP_PAYLOAD_KEY')
        result[key] = value
    return result


def epoch_instant(value, form):
    require(type(value) in (str, int, float), 'INVALID_TIMESTAMP_EPOCH')
    try:
        number = Decimal(str(value))
        require(number.is_finite(), 'INVALID_TIMESTAMP_EPOCH_PRECISION')
        sign, digits, exponent = number.as_tuple()
        # Never multiply/quantize Decimals under the process-wide precision:
        # even an extremely small nonzero fraction must not round away.
        scale = exponent + {'unix_s': 6, 'unix_ms': 3, 'unix_us': 0}[form]
        if not any(digits):
            micros = 0
        else:
            if scale < 0:
                places = -scale
                require(places < len(digits) and not any(digits[-places:]),
                        'INVALID_TIMESTAMP_EPOCH_PRECISION')
                digits, scale = digits[:-places], 0
            # All representable Python datetimes are below 10**18 epoch us.
            require(len(digits) + scale <= 18, 'INVALID_TIMESTAMP_EPOCH_RANGE')
            coefficient = 0
            for digit in digits:
                coefficient = coefficient * 10 + digit
            micros = coefficient * 10 ** scale * (-1 if sign else 1)
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=micros)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise EvaluationError('INVALID_TIMESTAMP_EPOCH') from exc


def raw_bindings(refs):
    require(isinstance(refs, list) and refs and all(isinstance(r, dict) for r in refs),
            'TIMESTAMP_RAW_BINDING_REQUIRED')
    result = []
    for ref in refs:
        require(isinstance(ref.get('path'), str) and isinstance(ref.get('sha256'), str),
                'TIMESTAMP_RAW_BINDING_REQUIRED')
        result.append({'path': ref['path'], 'sha256': ref['sha256']})
    return result


def prepare_policy(collection, clock_evidence, read_evidence, check_artifact):
    """Validate a policy and all authority artifacts before consuming any row.

    Callbacks are the full-context bundle's existing hash/path-enforcing readers.
    No policy preserves the previous explicit-offset-only behavior.
    """
    policy = clock_evidence.get('timestamp_policy')
    if policy is None:
        return None
    require(isinstance(policy, dict) and policy.get('schema_version') == POLICY_SCHEMA,
            'INVALID_TIMESTAMP_POLICY')
    bindings = raw_bindings(collection.get('raw_files'))
    require(policy.get('raw_files') == bindings and policy.get('timestamp_column') == 'event_time',
            'TIMESTAMP_RAW_BINDING_MISMATCH')
    require(policy.get('timezone') == collection.get('timezone'), 'TIMESTAMP_TIMEZONE_CONFLICT')
    named_timezone(policy.get('timezone'))
    sources = policy.get('payload_sources', [])
    require(isinstance(sources, list), 'INVALID_TIMESTAMP_PAYLOAD_SOURCES')
    for source in sources:
        require(isinstance(source, dict) and isinstance(source.get('column'), str) and source['column'],
                'INVALID_TIMESTAMP_PAYLOAD_SOURCE')
        for key in ('event_id_path', 'session_id_path'):
            path = source.get(key)
            require(isinstance(path, list) and path and all(isinstance(k, str) and k for k in path),
                    'TIMESTAMP_IDENTITY_BINDING_REQUIRED')
        stamps = source.get('timestamps')
        require(isinstance(stamps, list) and stamps, 'TIMESTAMP_PAYLOAD_FIELDS_REQUIRED')
        for stamp in stamps:
            require(isinstance(stamp, dict) and stamp.get('format') in ('iso8601', 'unix_s', 'unix_ms', 'unix_us'),
                    'INVALID_TIMESTAMP_PAYLOAD_FORMAT')
            path = stamp.get('path')
            require(isinstance(path, list) and path and all(isinstance(k, str) and k for k in path),
                    'INVALID_TIMESTAMP_EVIDENCE_PATH')
    authority = policy.get('timezone_authority')
    if authority is not None:
        record = read_evidence(authority)
        require(isinstance(record, dict) and record.get('schema_version') == AUTHORITY_SCHEMA,
                'INVALID_TIMEZONE_AUTHORITY')
        for key in ('dataset_id', 'collector_id', 'collector_version'):
            require(record.get(key) == collection.get(key), 'TIMEZONE_AUTHORITY_IDENTITY_MISMATCH')
        require(record.get('raw_files') == bindings and record.get('timestamp_column') == 'event_time'
                and record.get('timezone') == policy['timezone'], 'TIMEZONE_AUTHORITY_BINDING_MISMATCH')
        require(all(isinstance(record.get(k), str) and record[k].strip()
                    for k in ('authority', 'reviewer', 'findings')), 'TIMEZONE_AUTHORITY_INSUFFICIENT')
        aware_instant(record.get('recorded_at_utc'))
        refs = record.get('source_artifacts')
        require(isinstance(refs, list) and refs, 'TIMEZONE_AUTHORITY_SOURCE_REQUIRED')
        for ref in refs:
            check_artifact(ref)
    require(sources or authority is not None, 'TIMESTAMP_TIMEZONE_EVIDENCE_REQUIRED')
    return policy


def resolve_event_time(row, policy):
    """Return UTC and method only. The caller retains the original ts verbatim."""
    raw = parsed_datetime(row.get('event_time'))
    aware = raw.tzinfo is not None and raw.utcoffset() is not None
    if policy is None:
        return aware_instant(row.get('event_time')), 'raw_explicit_offset'
    tz = named_timezone(policy['timezone'])
    observed = []
    for source in policy.get('payload_sources', []):
        text = row.get(source['column'])
        require(isinstance(text, str) and text.strip(), 'TIMESTAMP_PAYLOAD_MISSING')
        try:
            payload = json.loads(text, object_pairs_hook=unique_object, parse_float=Decimal)
        except (ValueError, TypeError) as exc:
            raise EvaluationError('INVALID_TIMESTAMP_PAYLOAD_JSON') from exc
        require(json_path(payload, source['event_id_path']) == row.get('event_id')
                and json_path(payload, source['session_id_path']) == row.get('session_id'),
                'TIMESTAMP_PAYLOAD_IDENTITY_MISMATCH')
        for stamp in source['timestamps']:
            value = json_path(payload, stamp['path'])
            # Decimal preserves source JSON numeric precision without float rounding.
            if isinstance(value, Decimal):
                value = str(value)
            observed.append(aware_instant(value) if stamp['format'] == 'iso8601'
                            else epoch_instant(value, stamp['format']))
    require(not observed or all(value == observed[0] for value in observed),
            'TIMESTAMP_EVIDENCE_CONFLICT')
    if aware:
        instant = aware_instant(row['event_time'])
        local = instant.astimezone(tz)
        require(raw.utcoffset() == local.utcoffset()
                and raw.replace(tzinfo=None) == local.replace(tzinfo=None),
                'TIMESTAMP_EXPORT_TIMEZONE_CONFLICT')
    elif observed:
        instant = observed[0]
        # A bound UTC payload disambiguates DST folds, but must reproduce the
        # exact CSV wall time in the declared exporter timezone.
        require(instant.astimezone(tz).replace(tzinfo=None) == raw,
                'TIMESTAMP_EXPORT_PAYLOAD_CONFLICT')
    else:
        require(policy.get('timezone_authority') is not None, 'TIMESTAMP_TIMEZONE_EVIDENCE_REQUIRED')
        instant = local_instant(raw, tz)
    require(not observed or instant == observed[0], 'TIMESTAMP_EVIDENCE_CONFLICT')
    return instant, ('raw_explicit_offset+payload' if aware and observed else
                     'raw_explicit_offset' if aware else 'bound_payload' if observed else 'timezone_authority')
