"""Private, model-scoped provider cooldown; never retry or expose credentials."""
from datetime import datetime, timedelta, timezone
import math
import re

from ..evaluators import EvaluationError
from .generator import ERROR_CODES, ERROR_TYPES


def _time(value=None):
    value = datetime.now(timezone.utc) if value is None else value
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Aware provider timestamp required')
    return value.astimezone(timezone.utc)


def _model(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,200}', value) is not None


class ProviderState:
    """The caller supplies its existing guarded, atomic JSON read/write helpers."""

    def __init__(self, path, *, read, write, clock=None):
        self.path, self.read, self.write = path, read, write
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.storage_failed = False

    def _load(self):
        if not self.path.exists():
            return dict(version=1, models={})
        if self.path.stat().st_size > 262144:
            raise ValueError('Provider state size exceeded')
        value = self.read(self.path)
        if (not isinstance(value, dict) or set(value) != {'version', 'models'} or value['version'] != 1
                or type(value['version']) is not int or not isinstance(value['models'], dict)
                or len(value['models']) > 128):
            raise ValueError('Invalid provider state')
        for model, row in value['models'].items():
            if (not _model(model) or not isinstance(row, dict)
                    or set(row) != {'observed_at', 'next_eligible_at', 'retry_after_seconds', 'http_status',
                                    'error_type', 'error_code', 'generation_id', 'evidence_sha256'}
                    or type(row['http_status']) is not int or row['http_status'] != 429
                    or row['error_type'] is not None and row['error_type'] not in ERROR_TYPES
                    or row['error_code'] is not None and row['error_code'] not in ERROR_CODES
                    or type(row['retry_after_seconds']) not in (int, float)
                    or not math.isfinite(row['retry_after_seconds']) or not 0 <= row['retry_after_seconds'] <= 86400
                    or row['generation_id'] is not None and not re.fullmatch(r'M07-GEN-[a-f0-9]{32}', row['generation_id'])
                    or row['evidence_sha256'] is not None and not re.fullmatch(r'[a-f0-9]{64}', row['evidence_sha256'])):
                raise ValueError('Invalid provider cooldown')
            if _time(row['next_eligible_at']) != _time(row['observed_at']) + timedelta(seconds=row['retry_after_seconds']):
                raise ValueError('Provider cooldown timestamps differ')
        return value

    def current(self, model):
        result = dict(version=1, provider='openai', model=model if _model(model) else None,
                      blocked=False, reason=None, http_status=None, error_type=None, error_code=None,
                      retry_after_seconds=None, next_eligible_at=None, observed_at=None)
        try:
            if self.storage_failed:
                raise ValueError('Provider state persistence failed')
            row = self._load()['models'].get(model) if _model(model) else None
            if row:
                result.update({key: row[key] for key in ('http_status', 'error_type', 'error_code',
                              'retry_after_seconds', 'next_eligible_at', 'observed_at')})
                result['blocked'] = _time(self.clock()) < _time(row['next_eligible_at'])
                result['reason'] = 'HTTP_429_COOLDOWN' if result['blocked'] else 'COOLDOWN_EXPIRED'
        except (EvaluationError, OSError, ValueError, TypeError, KeyError, OverflowError):
            result.update(blocked=True, reason='PROVIDER_STATE_INVALID')
        return result

    def record(self, model, response, *, generation_id=None, observed_at=None, evidence_sha256=None):
        """Trusted internal API, including a known-response seed; never an HTTP payload."""
        if not _model(model) or not isinstance(response, dict) or type(response.get('http_status')) is not int or response['http_status'] != 429:
            raise EvaluationError('유효한 provider model과 HTTP429 근거가 필요합니다.', 'NOT_READY')
        diagnostic = response.get('diagnostics', {})
        diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
        headers = diagnostic.get('numeric_headers', {})
        retry = headers.get('retry-after') if isinstance(headers, dict) else None
        if type(retry) not in (int, float) or not math.isfinite(retry) or not 0 <= retry <= 86400:
            retry = 60
        try:
            observed = _time(self.clock() if observed_at is None else observed_at)
        except (ValueError, TypeError, OverflowError):
            raise EvaluationError('유효한 provider 관측 시각이 필요합니다.', 'NOT_READY') from None
        error_type, error_code = diagnostic.get('error_type'), diagnostic.get('error_code')
        row = dict(observed_at=observed.isoformat(), next_eligible_at=(observed + timedelta(seconds=retry)).isoformat(),
                   retry_after_seconds=retry, http_status=429,
                   error_type=error_type if isinstance(error_type, str) and error_type in ERROR_TYPES else None,
                   error_code=error_code if isinstance(error_code, str) and error_code in ERROR_CODES else None,
                   generation_id=generation_id if isinstance(generation_id, str) and re.fullmatch(r'M07-GEN-[a-f0-9]{32}', generation_id) else None,
                   evidence_sha256=evidence_sha256 if isinstance(evidence_sha256, str) and re.fullmatch(r'[a-f0-9]{64}', evidence_sha256) else None)
        try:
            value = self._load()
            previous = value['models'].get(model)
            if previous and _time(previous['next_eligible_at']) >= _time(row['next_eligible_at']):
                return self.current(model)
            if model not in value['models'] and len(value['models']) >= 128:
                raise ValueError('Provider model capacity exceeded')
            value['models'][model] = row
            self.write(self.path, value)
        except (EvaluationError, OSError, ValueError, TypeError, KeyError, OverflowError):
            self.storage_failed = True
            raise EvaluationError('Provider 대기 상태를 안전하게 저장하지 못했습니다.', 'NOT_READY') from None
        return self.current(model)
