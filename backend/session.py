# 현재 서버 실행 구간의 데이터 범위
import threading
import uuid
from datetime import datetime, timezone

from .evaluators import EvaluationError


class RuntimeSession:
    def __init__(self):
        self.id = 'SERVER-' + uuid.uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._owned = {}
        self._lock = threading.RLock()

    def claim(self, kind, identity):
        if not isinstance(identity, str) or not identity:
            return
        with self._lock:
            self._owned.setdefault(kind, set()).add(identity)

    def has(self, kind, identity):
        with self._lock:
            return isinstance(identity, str) and identity in self._owned.get(kind, ())

    def check(self, kind, identity):
        if not self.has(kind, identity):
            raise EvaluationError('이전 서버 세션의 데이터입니다. 현재 세션에서 다시 진행하세요.', 'SESSION_EXPIRED')

    def filter(self, kind, rows, key):
        return [row for row in rows if isinstance(row, dict) and self.has(kind, row.get(key))]

    def ids(self, kind):
        with self._lock:
            return tuple(self._owned.get(kind, ()))
