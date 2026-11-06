# M04 스크립트 고정 및 실행 기록
import ast
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import queue
import re
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
import zipfile
import zlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from ..evaluators import EvaluationError, require
from .. import execution_contexts
from ..integration_store import ingest


def _now():
    return datetime.now(timezone.utc).isoformat()


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _masked(value):
    text = str(value)
    text = re.sub(r'(?i)(bearer\s+)[^\s,;\"\']+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:password|passwd|secret|token|cookie|authorization)\s*[=:]\s*)[^\s,;]+', r'\1[REDACTED]', text)
    text = re.sub(r'([?&][^=\s&]+)=([^&\s]*)', r'\1=[REDACTED]', text)
    return text[:4000]


SCREENSHOT_POLICY = 'text-and-images-masked-v1'
SCREENSHOT_NOTICE = '문자·이미지가 마스킹된 실행 화면입니다. 판정은 독립 DOM/API 검사로 확인하며 이미지 일치 점수를 계산하지 않습니다.'


def _screenshot_records(value):
    require(isinstance(value, list) and len(value) <= 2, 'Invalid execution screenshot metadata')
    records, phases = [], set()
    for item in value:
        require(isinstance(item, dict), 'Invalid execution screenshot record')
        phase = item.get('phase')
        require(phase in {'before', 'after'} and phase not in phases and item.get('policy') == SCREENSHOT_POLICY,
                'Invalid execution screenshot phase or masking policy')
        status = item.get('status')
        require(status in {'CAPTURED', 'NOT_CAPTURED'}, 'Invalid execution screenshot status')
        stamp = item.get('captured_at')
        require(isinstance(stamp, str) and len(stamp) <= 80, 'Screenshot capture timestamp required')
        try:
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        except ValueError:
            raise EvaluationError('Invalid screenshot capture timestamp')
        require(parsed.tzinfo is not None, 'Screenshot capture timestamp timezone required')
        if status == 'CAPTURED':
            require(item.get('file') == phase + '.png' and isinstance(item.get('sha256'), str)
                    and re.fullmatch(r'[0-9a-f]{64}', item['sha256']) and item.get('reason') is None,
                    'Invalid captured screenshot file or hash')
        else:
            require(item.get('file') is None and item.get('sha256') is None
                    and isinstance(item.get('reason'), str) and re.fullmatch(r'[a-z_]{1,60}', item['reason']),
                    'Invalid unavailable screenshot evidence')
        records.append({key: item.get(key) for key in ('phase', 'file', 'sha256', 'policy', 'captured_at', 'status', 'reason')})
        phases.add(phase)
    return records


def _valid_png(raw):
    require(isinstance(raw, bytes) and 33 <= len(raw) <= 10 * 1024 * 1024 and raw.startswith(b'\x89PNG\r\n\x1a\n'),
            'Invalid masked screenshot PNG')
    offset, seen_header, seen_data = 8, False, False
    allowed = {b'IHDR', b'IDAT', b'IEND', b'PLTE', b'tRNS', b'sRGB', b'gAMA', b'cHRM', b'iCCP', b'pHYs'}
    while offset < len(raw):
        require(offset + 12 <= len(raw), 'Truncated masked screenshot PNG')
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + size
        require(kind in allowed and end <= len(raw), 'Unsupported or truncated screenshot PNG chunk')
        require(zlib.crc32(raw[offset + 4:end - 4]) & 0xffffffff == struct.unpack('>I', raw[end - 4:end])[0],
                'Masked screenshot PNG checksum mismatch')
        if not seen_header:
            require(kind == b'IHDR' and size == 13, 'Screenshot PNG header required')
            width, height = struct.unpack('>II', raw[offset + 8:offset + 16])
            require(0 < width <= 16384 and 0 < height <= 16384 and width * height <= 100000000, 'Screenshot PNG dimensions exceed limits')
            seen_header = True
        elif kind == b'IHDR':
            raise EvaluationError('Duplicate screenshot PNG header')
        if kind == b'IDAT':
            seen_data = True
        if kind == b'IEND':
            require(size == 0 and end == len(raw) and seen_data, 'Invalid screenshot PNG end')
            return
        offset = end
    raise EvaluationError('Screenshot PNG end is missing')


def verified_screenshots(case, folder):
    """M04/M07 공용 마스킹 PNG 메타데이터·해시 검증."""
    records = _screenshot_records(case.get('screenshots', []))
    result, directory = [], Path(folder).resolve(strict=True)
    for item in records:
        if item['status'] != 'CAPTURED':
            continue
        target = directory / item['file']
        require(not target.is_symlink() and target.resolve().parent == directory, 'Unsafe screenshot file path')
        if not target.is_file():
            raise EvaluationError('Masked screenshot is unavailable', 'NOT_FOUND')
        raw = target.read_bytes()
        require(_sha(raw) == item['sha256'], 'Masked screenshot SHA-256 mismatch')
        _valid_png(raw)
        result.append((item, raw))
    return result


class _RunLock:
    # 서버 간 단일 실행 잠금
    def __init__(self, path):
        self.file = path.open('a+b')
        self.locked = False

    def acquire(self):
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b'0')
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.locked = True
            return True
        except (OSError, BlockingIOError):
            self.file.close()
            return False

    def close(self):
        if self.file.closed:
            return
        if self.locked:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()


class _WorkerGroup:
    # 서버 종료 시 브라우저 자식 프로세스 정리
    def __init__(self, process):
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [('ProcessTime', ctypes.c_longlong), ('JobTime', ctypes.c_longlong), ('LimitFlags', wintypes.DWORD),
                        ('MinWorkingSet', ctypes.c_size_t), ('MaxWorkingSet', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperations', 'WriteOperations', 'OtherOperations', 'ReadBytes', 'WriteBytes', 'OtherBytes')]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('Basic', BasicLimits), ('Io', IoCounters), ('ProcessMemory', ctypes.c_size_t),
                        ('JobMemory', ctypes.c_size_t), ('PeakProcessMemory', ctypes.c_size_t), ('PeakJobMemory', ctypes.c_size_t)]

        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.SetInformationJobObject.restype = wintypes.BOOL
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.AssignProcessToJobObject.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.CreateJobObjectW(None, None)
        require(handle, 'Windows execution group creation failed')
        limits = ExtendedLimits()
        limits.Basic.LimitFlags = 0x2000
        configured = api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        assigned = configured and api.AssignProcessToJobObject(handle, wintypes.HANDLE(process._handle))
        if not assigned:
            error = ctypes.get_last_error()
            api.CloseHandle(handle)
            if process.poll() is None:
                raise OSError(error, 'Windows execution group assignment failed')
            return
        self.handle = handle
        self.api = api

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class M04Manager:
    case_timeout_seconds = 90
    _script_pattern = re.compile(r'[a-f0-9]{32}')
    _execution_pattern = re.compile(r'M04-RUN-[a-f0-9]{32}')
    _session_kind = 'M04'

    def __init__(self, root, config_provider, session=None):
        self.root = Path(root).resolve()
        self.config_provider = config_provider
        self.session = session
        self.directory = self._safe(self.root / 'data/development/m04_runner')
        self.script_directory = self._safe(self.directory / 'scripts')
        self.execution_directory = self._safe(self.directory / 'executions')
        self.script_directory.mkdir(parents=True, exist_ok=True)
        self.execution_directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._active = None
        self._process = None
        self._recover()

    def _session_has(self, kind, identity):
        session = getattr(self, 'session', None)
        return session is None or session.has(kind, identity)

    def _session_check(self, kind, identity):
        session = getattr(self, 'session', None)
        if session is not None:
            session.check(kind, identity)

    def _session_claim(self, kind, identity, record=None):
        session = getattr(self, 'session', None)
        if session is not None:
            session.claim(kind, identity)
            if record is not None:
                record['server_session_id'] = session.id

    def _safe(self, path):
        path = Path(path).absolute()
        require(path.is_relative_to(self.root), 'M04 path must remain under project root')
        current = self.root
        for part in path.relative_to(self.root).parts:
            current = current / part
            require(not current.is_symlink() and current.resolve() == current, 'M04 linked paths are prohibited')
        return path

    def _write(self, path, value):
        path = self._safe(path)
        temp = self._safe(path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp'))
        try:
            with temp.open('xb') as output:
                output.write(_encoded(value))
                output.flush()
                os.fsync(output.fileno())
            for attempt in range(20):
                try:
                    temp.replace(path)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(.025)
        finally:
            if temp.exists():
                temp.unlink()

    def _json(self, path):
        path = self._safe(path)
        for attempt in range(20):
            try:
                raw = path.read_bytes()
                return json.loads(raw.decode('utf-8'))
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.025)

    def _global_lock(self):
        lock = _RunLock(self._safe(self.directory / 'runner.lock'))
        return lock if lock.acquire() else None

    def _recover(self):
        with self.lock:
            global_lock = self._global_lock()
            if not global_lock:
                return
            try:
                for path in self.execution_directory.glob('*/execution.json'):
                    if not self._session_has(self._session_kind, path.parent.name):
                        continue
                    job = self._json(path)
                    if job.get('status') in {'QUEUED', 'RUNNING'}:
                        self._interrupt(job, '이전 실행이 중단되어 결과를 평가하지 않았습니다.')
            finally:
                global_lock.close()

    @staticmethod
    def _readiness():
        try:
            selenium = importlib.util.find_spec('selenium') is not None
        except (ValueError, ImportError):
            selenium = False
        candidates = [shutil.which(name) for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome')]
        for env in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if os.environ.get(env):
                candidates.append(str(Path(os.environ[env]) / 'Google/Chrome/Application/chrome.exe'))
        chrome = any(value and Path(value).is_file() for value in candidates)
        return {'selenium': selenium, 'chrome': chrome,
                'message': '실행 환경 준비 완료' if selenium and chrome else 'Selenium 및 Chrome 설치 확인 필요'}

    def scripts(self):
        records = [self._json(path) for path in self.script_directory.glob('*/script.json')
                   if self._session_has('SCRIPT', path.parent.name)]
        for row in records:
            if row.get('business_step_required'):
                try:
                    self._script(row['script_id'])
                    folder = self._safe(self.script_directory / row['script_id'])
                    self._fixed_execution(row, folder)
                    row.update(execution_ready=True, execution_notice='')
                except (EvaluationError, OSError, ValueError, TypeError):
                    row.update(execution_ready=False, execution_notice='실행 대상과 기대 상태를 먼저 준비하세요.')
        records.sort(key=lambda row: row['fixed_at'], reverse=True)
        return {'scripts': records, 'readiness': self._readiness(), 'run_mode': 'DEVELOPMENT'}

    def _script(self, script_id):
        require(isinstance(script_id, str) and self._script_pattern.fullmatch(script_id), 'Invalid script_id')
        self._session_check('SCRIPT', script_id)
        path = self._safe(self.script_directory / script_id / 'script.json')
        require(path.is_file(), 'Script not found')
        value = self._json(path)
        require(value.get('script_id') == script_id, 'Script identity mismatch')
        raw = self._safe(path.parent / 'script.py').read_bytes()
        require(_sha(raw) == value['sha256'], 'Fixed script SHA-256 mismatch')
        for name, key in (('source_scenario.json', 'source_scenario_sha256'),
                          ('execution_scenario.json', 'execution_scenario_sha256'),
                          ('execution_contract.json', 'execution_contract_sha256')):
            if value.get(key):
                require(_sha(self._safe(path.parent / name).read_bytes()) == value[key], 'Fixed evidence SHA-256 mismatch: ' + name)
        self._prepared_files(value, path.parent, raw)
        return value, raw

    def _prepared_files(self, metadata, folder, raw):
        # 사전 작성 원본의 출처·바이트 검증
        if metadata.get('code_source') != 'PREPARED':
            return {}
        require(metadata.get('generated_by_llm') is False
                and metadata.get('source_file_sha256') == metadata.get('sha256') == _sha(raw)
                and metadata.get('code_sha256') == _sha(raw), 'Prepared code provenance mismatch')
        filename = metadata.get('source_filename')
        require(isinstance(filename, str) and 1 <= len(filename) <= 120 and filename.lower().endswith('.py')
                and re.fullmatch(r'[^/\\:\x00-\x1f]+', filename) and filename not in {'.py', '..py'},
                'Prepared Python filename required')
        proof_raw = self._safe(folder / 'prepared_source.json').read_bytes()
        require(_sha(proof_raw) == metadata.get('prepared_source_sha256'), 'Prepared source evidence SHA-256 mismatch')
        proof = json.loads(proof_raw.decode('utf-8'))
        require(isinstance(proof, dict) and set(proof) == {'code_source', 'generated_by_llm', 'scenario_id',
                'source_filename', 'source_file_sha256', 'registered_at'}, 'Invalid prepared source evidence')
        require(proof.get('generated_by_llm') is False
                and all(proof.get(key) == metadata.get(key) for key in
                        ('code_source', 'scenario_id', 'source_filename', 'source_file_sha256')),
                'Prepared source evidence mismatch')
        try:
            stamp = datetime.fromisoformat(proof['registered_at'].replace('Z', '+00:00'))
            require(stamp.tzinfo is not None, 'Prepared source timestamp requires timezone')
        except (ValueError, TypeError, AttributeError):
            raise EvaluationError('Invalid prepared source timestamp') from None
        original = self._safe(folder / 'prepared_code.py').read_bytes()
        require(original == raw, 'Prepared original bytes mismatch')
        return {'prepared_source.json': proof_raw, 'prepared_code.py': original}

    def _execution_inputs(self, scenario, run_id=None):
        # 실제 대상과 기대 상태 확인 기준
        return execution_contexts.resolve(self.root, run_id, scenario, self.config_provider())

    def _execution_contract(self, scenario, run_id=None):
        return self._execution_inputs(scenario, run_id)['contract']

    def _fixed_execution(self, metadata, folder):
        source = self._json(folder / 'source_scenario.json')
        if metadata.get('execution_scenario_sha256'):
            source = self._json(folder / 'execution_scenario.json')
        if metadata.get('execution_contract_sha256'):
            source = dict(source, execution_contract=self._json(folder / 'execution_contract.json'))
            result = self._execution_inputs(source)
            result['revision_id'] = metadata.get('execution_context_revision_id')
            return result
        return self._execution_inputs(source, metadata.get('source_m03_run_id'))

    def register(self, payload):
        require(isinstance(payload, dict), 'JSON object required')
        require(payload.get('run_mode', 'DEVELOPMENT') == 'DEVELOPMENT', 'M04 runner supports DEVELOPMENT only')
        strict_requested = payload.get('require_business_steps', False)
        require(type(strict_requested) is bool, 'require_business_steps must be boolean')
        filename = payload.get('filename')
        require(isinstance(filename, str) and 1 <= len(filename) <= 120 and filename.lower().endswith('.py')
                and re.fullmatch(r'[^/\\:\x00-\x1f]+', filename) and filename not in {'.py', '..py'}, 'Python filename required')
        encoded = payload.get('python_base64')
        require(isinstance(encoded, str) and len(encoded) <= 350000, 'Python source must be at most 256 KiB')
        try:
            raw = base64.b64decode(encoded, validate=True)
            require(0 < len(raw) <= 262144, 'Python source must be at most 256 KiB')
            code = raw.decode('utf-8-sig')
            tree = ast.parse(code, filename=filename)
        except (ValueError, UnicodeError, SyntaxError) as exc:
            raise EvaluationError('Invalid Python source: ' + _masked(exc), 'ERROR') from exc
        require(any(isinstance(node, ast.Assert) for node in ast.walk(tree)), 'At least one Python assert required')
        require(any((isinstance(node, ast.Import) and any(alias.name == 'selenium' or alias.name.startswith('selenium.') for alias in node.names))
                    or (isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] == 'selenium')
                    for node in ast.walk(tree)), 'Selenium import required')
        scenario_id = payload.get('scenario_id')
        scenario_name = payload.get('scenario_name') or scenario_id
        require(isinstance(scenario_id, str) and 0 < len(scenario_id.strip()) <= 256, 'scenario_id required')
        require(isinstance(scenario_name, str) and 0 < len(scenario_name.strip()) <= 256, 'Invalid scenario_name')
        source_id = payload.get('m03_run_id') or None
        snapshot = None
        synthetic = False
        llm_source = None
        llm_files = {}
        prepared_source = False
        contract = None
        execution_scenario = None
        context_revision = None
        if source_id:
            require(isinstance(source_id, str) and re.fullmatch(r'DEV-M03-[A-Za-z0-9-]+', source_id), 'DEVELOPMENT M03 run_id required')
            self._session_check('RESULT', source_id)
            directory = self._safe(self.root / 'results/development' / source_id)
            result = self._json(directory / 'result.json')
            source = self._json(directory / 'received_payload.json')
            require(result.get('run_mode') == 'DEVELOPMENT' and result.get('metric_id') == 'M03', 'DEVELOPMENT M03 result required')
            require(isinstance(source, dict) and isinstance(source.get('scenarios'), list), 'M03 scenario evidence required')
            matches = [row for row in source['scenarios'] if isinstance(row, dict) and row.get('scenario_id') == scenario_id]
            require(len(matches) == 1, 'scenario_id not found in source M03 result')
            from ..m03_management import scenario_deleted
            if re.fullmatch(r'DEV-M03-\d{8}T\d{6}-[a-f0-9]{12}', source_id):
                require(not scenario_deleted(self.root, source_id, scenario_id), 'Deleted M03 scenario cannot be registered')
            snapshot = matches[0]
            details = source.get('details') if isinstance(source.get('details'), dict) else {}
            synthetic = (source.get('synthetic') is True or details.get('synthetic') is True
                         or snapshot.get('synthetic') is True or snapshot.get('generator_mode') == 'MOCK')
        generation_id = payload.get('source_m07_generation_id')
        if generation_id is not None:
            require(isinstance(generation_id, str) and re.fullmatch(r'M07-GEN-[a-f0-9]{32}', generation_id), 'Invalid M07 generation ID')
            self._session_check('M07', generation_id)
            case_id = payload.get('source_m07_case_id')
            require(isinstance(case_id, str) and re.fullmatch(r'CASE-\d{3}', case_id), 'Invalid M07 case ID')
            source_dir = self._safe(self.root / 'data/development/m07_codes/generations' / generation_id)
            generation = self._json(source_dir / 'execution.json')
            require(generation.get('status') == 'GENERATED', 'M04 코드는 M07 실행 검사 전에 고정해야 합니다.')
            matches = [row for row in generation['cases'] if row['case_id'] == case_id]
            require(len(matches) == 1, 'M07 source case not found')
            llm_source = matches[0]
            prepared_source = llm_source.get('code_source') == 'PREPARED'
            require(llm_source.get('generated_by_llm') is (False if prepared_source else True)
                    and llm_source.get('generation_status') == 'PASS'
                    and llm_source['scenario_id'] == scenario_id and llm_source['source_m03_run_id'] == source_id
                    and llm_source['sha256'] == _sha(raw), 'M07 code provenance mismatch')
            require(snapshot is not None and _sha(_encoded(snapshot)) == llm_source['source_scenario_sha256'],
                    'M07 source scenario snapshot mismatch')
            require(_sha(self._safe(source_dir / case_id / 'source_scenario.json').read_bytes())
                    == llm_source['source_scenario_sha256'], 'M07 source scenario evidence SHA-256 mismatch')
            require(self._safe(source_dir / case_id / 'script.py').read_bytes() == raw, 'M07 source bytes mismatch')
            if prepared_source:
                llm_files.update(self._prepared_files(llm_source, source_dir / case_id, raw))
            else:
                for name, key in (('response.json', 'response_sha256'), ('prompt.json', 'prompt_sha256')):
                    content = self._safe(source_dir / case_id / name).read_bytes()
                    require(_sha(content) == llm_source[key], 'M07 source evidence hash mismatch')
                    llm_files[name] = content
            if llm_source.get('execution_contract_sha256'):
                content = self._safe(source_dir / case_id / 'execution_contract.json').read_bytes()
                require(_sha(content) == llm_source['execution_contract_sha256'], 'M07 execution contract SHA-256 mismatch')
                execution_scenario = snapshot
                if llm_source.get('execution_scenario_sha256'):
                    effective_raw = self._safe(source_dir / case_id / 'execution_scenario.json').read_bytes()
                    require(_sha(effective_raw) == llm_source['execution_scenario_sha256'], 'M07 execution scenario SHA-256 mismatch')
                    execution_scenario = json.loads(effective_raw)
                contract = self._execution_contract(dict(execution_scenario, execution_contract=json.loads(content)))
                context_revision = llm_source.get('execution_context_revision_id')
            for path in self.script_directory.glob('*/script.json'):
                if not self._session_has('SCRIPT', path.parent.name):
                    continue
                existing = self._json(path)
                if (existing.get('source_m07_generation_id') == generation_id and existing.get('source_m07_case_id') == case_id
                        and existing.get('sha256') == _sha(raw)):
                    self._script(existing['script_id'])
                    return {'script': existing}
        script_id = uuid.uuid4().hex
        directory = self._safe(self.script_directory / script_id)
        metadata = dict(script_id=script_id, filename=filename, scenario_id=scenario_id.strip(), scenario_name=scenario_name.strip(),
                        sha256=_sha(raw), fixed_at=_now(), source_m03_run_id=source_id, source_synthetic=synthetic,
                        run_mode='DEVELOPMENT', script_language='python', script_framework='selenium',
                        source_kind='UPLOADED_FIXED_SCRIPT', generated_by_llm=None,
                        llm_generation_evidence_available=False)
        uses_steps = any(isinstance(node, ast.ImportFrom) and node.module == 'ktl_runtime'
                         and any(alias.name == 'business_step' for alias in node.names) for node in ast.walk(tree))
        metadata['business_step_required'] = strict_requested or uses_steps or bool(llm_source and llm_source.get('business_step_required'))
        metadata['step_evidence_mode'] = 'BUSINESS_STEPS' if metadata['business_step_required'] else 'LEGACY_TRACE'
        if metadata['business_step_required']:
            require(uses_steps, 'ktl_runtime.business_step import required for business-step script')
            declared = [node.value.value for node in ast.walk(tree)
                        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Constant)
                        and any(isinstance(target, ast.Name) and target.id == 'SCENARIO_ID'
                                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
            require(scenario_id in declared, 'Matching literal SCENARIO_ID required for business-step script')
            require(snapshot is not None, 'M03 scenario snapshot required for business-step script')
            if contract is None:
                prepared = self._execution_inputs(snapshot, source_id)
                execution_scenario, contract = prepared['scenario'], prepared['contract']
                context_revision = prepared['revision_id']
        if llm_source is not None:
            metadata.update(source_m07_generation_id=generation_id, source_m07_case_id=case_id)
            if prepared_source:
                metadata.update(source_kind='M07_PREPARED_SCRIPT', code_source='PREPARED', generated_by_llm=False,
                                llm_generation_evidence_available=False, scripts_manually_modified=False,
                                source_filename=llm_source['source_filename'], source_file_sha256=llm_source['source_file_sha256'],
                                code_sha256=llm_source['code_sha256'], prepared_source_sha256=llm_source['prepared_source_sha256'])
            else:
                metadata.update(source_kind='M07_GENERATED_SCRIPT', generated_by_llm=True, llm_generation_evidence_available=True,
                                response_sha256=llm_source['response_sha256'], prompt_sha256=llm_source['prompt_sha256'],
                                model=llm_source.get('model'), request_id=llm_source.get('request_id'))
        self._session_claim('SCRIPT', script_id, metadata)
        directory.mkdir()
        with (directory / 'script.py').open('xb') as output:
            output.write(raw)
        if snapshot is not None:
            self._write(directory / 'source_scenario.json', snapshot)
            metadata['source_scenario_sha256'] = _sha((directory / 'source_scenario.json').read_bytes())
        if contract is not None:
            self._write(directory / 'execution_scenario.json', execution_scenario)
            metadata['execution_scenario_sha256'] = _sha((directory / 'execution_scenario.json').read_bytes())
            metadata['execution_context_revision_id'] = context_revision
            self._write(directory / 'execution_contract.json', contract)
            metadata['execution_contract_sha256'] = _sha((directory / 'execution_contract.json').read_bytes())
            metadata['execution_contract_version'] = contract['version']
        self._write(directory / 'script.json', metadata)
        for name, content in llm_files.items():
            with (directory / name).open('xb') as output:
                output.write(content)
        return {'script': metadata}

    def read_script(self, script_id):
        metadata, raw = self._script(script_id)
        return {'script': metadata, 'code': raw.decode('utf-8-sig')}

    def _job_path(self, execution_id):
        require(isinstance(execution_id, str) and self._execution_pattern.fullmatch(execution_id), 'Invalid execution_id')
        return self._safe(self.execution_directory / execution_id / 'execution.json')

    def _job(self, execution_id):
        path = self._job_path(execution_id)
        self._session_check(self._session_kind, execution_id)
        require(path.is_file(), 'Execution not found')
        job = self._json(path)
        require(job.get('execution_id') == execution_id, 'Execution identity mismatch')
        return job

    def _save(self, job):
        self._session_check(self._session_kind, job['execution_id'])
        result = job.get('result')
        if isinstance(result, dict) and result.get('run_mode') == 'DEVELOPMENT' and result.get('run_id'):
            self._session_claim('RESULT', result['run_id'])
        self._write(self._job_path(job['execution_id']), job)

    def list_runs(self):
        self._recover()
        executions = []
        for path in self.execution_directory.glob('*/execution.json'):
            if not self._session_has(self._session_kind, path.parent.name):
                continue
            job = self._json(path)
            executions.append({key: value for key, value in job.items() if key not in {'logs', 'cases'}})
        executions.sort(key=lambda value: value['started_at'], reverse=True)
        return {'executions': executions, 'run_mode': 'DEVELOPMENT'}

    def read(self, execution_id):
        self._recover()
        return {'execution': self._job(execution_id)}

    def create(self, payload):
        require(isinstance(payload, dict), 'JSON object required')
        require(payload.get('run_mode', 'DEVELOPMENT') == 'DEVELOPMENT', 'M04 runner supports DEVELOPMENT only')
        ids = payload.get('script_ids')
        require(isinstance(ids, list) and 1 <= len(ids) <= 10 and all(isinstance(value, str) for value in ids)
                and len(set(ids)) == len(ids), 'Select 1..10 unique script_ids')
        with self.lock:
            global_lock = self._global_lock()
            if not global_lock:
                raise EvaluationError('M04 execution is already running', 'RUNNING')
            try:
                for path in self.execution_directory.glob('*/execution.json'):
                    if not self._session_has(self._session_kind, path.parent.name):
                        continue
                    stale = self._json(path)
                    if stale.get('status') in {'QUEUED', 'RUNNING'}:
                        self._interrupt(stale, '이전 실행이 중단되어 결과를 평가하지 않았습니다.')
                scripts = [self._script(value) for value in ids]
                contracts = {}
                for metadata, _ in scripts:
                    if metadata.get('business_step_required'):
                        source_dir = self._safe(self.script_directory / metadata['script_id'])
                        contracts[metadata['script_id']] = self._fixed_execution(metadata, source_dir)
                execution_id = 'M04-RUN-' + uuid.uuid4().hex
                self._session_claim(self._session_kind, execution_id)
                directory = self._safe(self.execution_directory / execution_id)
                directory.mkdir()
                cases = []
                for index, (metadata, raw) in enumerate(scripts, 1):
                    case_id = 'CASE-' + str(index).zfill(3)
                    case_dir = self._safe(directory / case_id)
                    case_dir.mkdir()
                    with (case_dir / 'script.py').open('xb') as output:
                        output.write(raw)
                    self._write(case_dir / 'script.json', metadata)
                    source = self._safe(self.script_directory / metadata['script_id'] / 'source_scenario.json')
                    if source.exists():
                        source_raw = source.read_bytes()
                        require(_sha(source_raw) == metadata['source_scenario_sha256'], 'Source scenario SHA-256 mismatch')
                        with (case_dir / 'source_scenario.json').open('xb') as output:
                            output.write(source_raw)
                    prepared = contracts.get(metadata['script_id'])
                    contract = prepared['contract'] if prepared else None
                    contract_hash = None
                    execution_scenario_hash = None
                    if contract is not None:
                        self._write(case_dir / 'execution_scenario.json', prepared['scenario'])
                        execution_scenario_hash = _sha((case_dir / 'execution_scenario.json').read_bytes())
                        self._write(case_dir / 'execution_contract.json', contract)
                        contract_hash = _sha((case_dir / 'execution_contract.json').read_bytes())
                    for name, key in (('response.json', 'response_sha256'), ('prompt.json', 'prompt_sha256')):
                        if metadata.get('generated_by_llm') is True:
                            content = self._safe(self.script_directory / metadata['script_id'] / name).read_bytes()
                            require(_sha(content) == metadata[key], 'LLM evidence SHA-256 mismatch')
                            with (case_dir / name).open('xb') as output:
                                output.write(content)
                    for name, content in self._prepared_files(metadata, self.script_directory / metadata['script_id'], raw).items():
                        with (case_dir / name).open('xb') as output:
                            output.write(content)
                    cases.append(dict(case_id=case_id, script_id=metadata['script_id'], scenario_id=metadata['scenario_id'],
                                      scenario_name=metadata['scenario_name'], script_name=metadata['filename'], sha256=metadata['sha256'],
                                      fixed_at=metadata['fixed_at'], source_m03_run_id=metadata['source_m03_run_id'],
                                      source_synthetic=metadata['source_synthetic'], status='PENDING', steps=[], action_logs=[],
                                      business_step_required=metadata.get('business_step_required', False),
                                      execution_contract_sha256=contract_hash,
                                      execution_scenario_sha256=execution_scenario_hash,
                                      execution_context_revision_id=prepared.get('revision_id') if prepared else None,
                                      execution_contract_version=contract.get('version') if contract else None,
                                      step_evidence_mode=metadata.get('step_evidence_mode', 'LEGACY_TRACE'),
                                      source_scenario_sha256=metadata.get('source_scenario_sha256'),
                                      generated_by_llm=metadata.get('generated_by_llm'),
                                      llm_generation_evidence_available=metadata.get('llm_generation_evidence_available', False),
                                      source_m07_generation_id=metadata.get('source_m07_generation_id'),
                                      source_m07_case_id=metadata.get('source_m07_case_id')))
                    if metadata.get('code_source') == 'PREPARED':
                        cases[-1].update({key: metadata[key] for key in ('code_source', 'source_kind', 'source_filename',
                            'source_file_sha256', 'code_sha256', 'prepared_source_sha256', 'scripts_manually_modified')})
                artifacts = [dict(name=name, url=f'/api/development/m04/executions/{execution_id}/artifacts/{name}')
                             for name in ('report.json', 'log.jsonl', 'steps.csv', 'scripts.zip', 'screenshots.zip')]
                job = dict(execution_id=execution_id, status='QUEUED', started_at=_now(), completed_at=None,
                           run_mode='DEVELOPMENT', cases=cases, logs=[], result=None, error=None, artifacts=artifacts,
                           counts=dict(total_execution_count=len(cases), successful_execution_count=0, failed_execution_count=0))
                if getattr(self, 'session', None) is not None:
                    job['server_session_id'] = self.session.id
                self._provenance(job)
                self._save(job)
                self._active = execution_id
                thread = threading.Thread(target=self._execute, args=(execution_id, global_lock), daemon=True, name='M04-' + execution_id[-8:])
                thread.start()
                return {'execution': deepcopy(job)}
            except BaseException:
                global_lock.close()
                raise

    def cancel(self, execution_id):
        with self.lock:
            job = self._job(execution_id)
            if job['status'] in {'QUEUED', 'RUNNING'}:
                path = self._safe(self._job_path(execution_id).parent / 'cancel.request')
                path.touch(exist_ok=True)
                job['cancel_requested'] = True
            return {'execution': job}

    def _cancelled(self, execution_id):
        return self._safe(self._job_path(execution_id).parent / 'cancel.request').exists()

    def _log(self, job, case_id, message):
        if len(job['logs']) < 2000:
            job['logs'].append({'time': _now(), 'case_id': case_id, 'message': _masked(message)})

    def _interrupt(self, job, reason):
        for case in job['cases']:
            if case['status'] in {'PENDING', 'RUNNING'}:
                self._interrupted_case(case, reason)
        job.update(status='INTERRUPTED', completed_at=_now(), result=None, error=reason)
        self._counts(job)
        self._log(job, None, reason)
        self._save(job)

    @staticmethod
    def _interrupted_case(case, reason):
        # 시작된 실행과 미실행 구분
        started = bool(case.get('started_at')) or case.get('status') == 'RUNNING'
        case.update(status='FAIL' if started else 'SKIPPED', error=case.get('error') or reason)
        if started:
            case['error_message'] = case.get('error_message') or case['error']
            case['completed_at'] = case.get('completed_at') or _now()
            for step in case.get('steps', []):
                if step.get('status') == 'RUNNING':
                    step.update(status='FAIL', error=step.get('error') or case['error'], completed_at=case['completed_at'])
                    if case.get('failed_step') is None:
                        case['failed_step'] = step.get('sequence')
                    if not case.get('failure_selector'):
                        case['failure_selector'] = step.get('failure_selector') or step.get('actual_selector')

    @staticmethod
    def _counts(job):
        job['counts'] = dict(total_execution_count=len(job['cases']),
                             successful_execution_count=sum(case['status'] == 'PASS' for case in job['cases']),
                             failed_execution_count=sum(case['status'] in {'FAIL', 'ERROR', 'TIMEOUT', 'SKIPPED'} for case in job['cases']))

    @staticmethod
    def _kill(process):
        if process.poll() is not None and os.name == 'nt':
            return
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def _run_case(self, job, case):
        script = self._safe(self._job_path(job['execution_id']).parent / case['case_id'] / 'script.py')
        require(_sha(script.read_bytes()) == case['sha256'], 'Execution snapshot SHA-256 mismatch')
        self._prepared_files(case, script.parent, script.read_bytes())
        runner = self._safe(self.root / 'backend/m04/runner.py')
        require(runner.is_file(), 'M04 runner not configured')
        case.update(status='RUNNING', started_at=_now())
        case['runner_sha256'] = _sha(runner.read_bytes())
        self._save(job)
        started = time.monotonic()
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        command = [sys.executable, '-I', '-B', '-u', str(runner), '--script', str(script)]
        source = self._safe(script.parent / 'source_scenario.json')
        execution_scenario = source
        if case.get('business_step_required'):
            require(source.is_file(), 'Business step scenario snapshot required')
            require(_sha(source.read_bytes()) == case.get('source_scenario_sha256'), 'Business step scenario SHA-256 mismatch')
            if case.get('execution_scenario_sha256'):
                execution_scenario = self._safe(script.parent / 'execution_scenario.json')
                require(execution_scenario.is_file() and _sha(execution_scenario.read_bytes()) == case['execution_scenario_sha256'],
                        'Execution scenario SHA-256 mismatch')
            command.extend(['--scenario', str(execution_scenario), '--require-business-steps'])
            contract = self._safe(script.parent / 'execution_contract.json')
            require(contract.is_file() and _sha(contract.read_bytes()) == case.get('execution_contract_sha256'),
                    'Execution contract SHA-256 mismatch')
            command.extend(['--contract', str(contract)])
            checks = self._safe(self.root / 'backend/m04/checks.py')
            if checks.is_file():
                case['checks_sha256'] = _sha(checks.read_bytes())
        case.setdefault('action_logs', [])
        process = subprocess.Popen(command,
                                   cwd=script.parent, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', bufsize=1,
                                   env={key: value for key, value in os.environ.items()
                                        if key not in {'OPENAI_API_KEY', 'KTL_M07_OPENAI_API_KEY'}}, **options)
        self._process = process
        case['worker_pid'] = process.pid
        messages = queue.Queue(maxsize=128)
        stop_reader = threading.Event()

        def enqueue(value):
            while not stop_reader.is_set():
                try:
                    messages.put(value, timeout=.1)
                    return
                except queue.Full:
                    pass

        def output_reader():
            try:
                while True:
                    line = process.stdout.readline(65537)
                    if not line:
                        break
                    enqueue(line[:65536])
            finally:
                enqueue(None)

        terminal = None
        ended = False
        reason = None
        group = None
        try:
            group = _WorkerGroup(process)
            self._save(job)
            threading.Thread(target=output_reader, daemon=True).start()
            while not ended or process.poll() is None:
                if self._cancelled(job['execution_id']):
                    reason = 'CANCELLED'
                    self._kill(process)
                    break
                if time.monotonic() - started >= self.case_timeout_seconds:
                    reason = 'TIMEOUT'
                    self._kill(process)
                    break
                try:
                    line = messages.get(timeout=.05)
                except queue.Empty:
                    continue
                if line is None:
                    ended = True
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    self._log(job, case['case_id'], line.rstrip())
                    self._save(job)
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get('event') in {'step', 'business_step', 'business_step_started'} and isinstance(event.get('step'), dict):
                    step = event['step']
                    cleaned = {key: _masked(value) if isinstance(value, str) else value
                               for key, value in step.items() if key in {'sequence', 'step_id', 'action', 'target', 'expected_result', 'status', 'started_at', 'completed_at', 'duration_ms', 'error',
                                                                        'action_count', 'browser_read_count', 'assertion_count', 'passed_assertion_count', 'failure_selector', 'selector', 'business_step_order',
                                                                        'independent_checks_passed', 'check_results'}}
                    destination = case['steps'] if event['event'].startswith('business_step') else case['action_logs']
                    existing = next((row for row in destination if event['event'].startswith('business_step') and row.get('sequence') == cleaned.get('sequence')), None)
                    if existing is not None:
                        existing.update(cleaned)
                    elif len(destination) < 1000:
                        destination.append(cleaned)
                    if event['event'] == 'step' and not case.get('business_step_required') and len(case['steps']) < 500:
                        case['steps'].append(deepcopy(cleaned))
                elif event.get('event') == 'result':
                    terminal = event
                elif event.get('event') == 'screenshot':
                    item = _screenshot_records([event.get('screenshot')])[0]
                    previous = {row['phase']: row for row in case.get('screenshots', [])}
                    require(item['phase'] not in previous or previous[item['phase']] == item,
                            'Execution screenshot evidence changed')
                    previous[item['phase']] = item
                    case['screenshots'] = list(previous.values())
                    verified_screenshots(case, script.parent)
                elif event.get('event') == 'log':
                    self._log(job, case['case_id'], event.get('message', ''))
                self._save(job)
            returncode = process.wait(timeout=5)
            if reason == 'CANCELLED':
                case.update(status='FAIL', error='사용자 실행 중단')
            elif reason == 'TIMEOUT':
                case.update(status='TIMEOUT', error='스크립트 실행 시간 초과')
            elif not isinstance(terminal, dict):
                case.update(status='ERROR', error='실행 종료 근거 누락')
            else:
                status = terminal.get('status')
                assertions = terminal.get('assertion_count')
                passed = terminal.get('passed_assertion_count')
                fixed_hash = _sha(script.read_bytes())
                require(fixed_hash == case['sha256'], 'Execution script changed during execution')
                self._prepared_files(case, script.parent, script.read_bytes())
                require(terminal.get('code_sha256') == case['sha256'], 'Worker code SHA-256 mismatch')
                screenshots = _screenshot_records(terminal.get('screenshots', []))
                observed = {row['phase']: row for row in case.get('screenshots', [])}
                for item in screenshots:
                    require(item['phase'] not in observed or observed[item['phase']] == item,
                            'Worker screenshot evidence mismatch')
                case['screenshots'] = screenshots
                verified_screenshots(case, script.parent)
                if case.get('business_step_required'):
                    require(_sha(source.read_bytes()) == case['source_scenario_sha256'], 'Business step scenario changed during execution')
                    if case.get('execution_scenario_sha256'):
                        require(_sha(execution_scenario.read_bytes()) == case['execution_scenario_sha256'], 'Execution scenario changed during execution')
                valid = (status == 'PASS' and returncode == 0 and type(assertions) is int and assertions >= 1
                         and type(passed) is int and assertions == passed and terminal.get('browser_started') is True
                         and type(terminal.get('action_count')) is int and terminal['action_count'] >= 1)
                if case.get('business_step_required'):
                    require(_sha(contract.read_bytes()) == case['execution_contract_sha256'], 'Execution contract changed during execution')
                    if case.get('checks_sha256'):
                        require(_sha(checks.read_bytes()) == case['checks_sha256'], 'Independent checker changed during execution')
                    valid = (valid and terminal.get('business_step_complete') is True
                             and terminal.get('independent_checks_passed') is True
                             and terminal.get('execution_contract_sha256') == case['execution_contract_sha256'])
                evidence = terminal.get('business_steps')
                if terminal.get('step_evidence_mode') == 'BUSINESS_STEPS' and isinstance(evidence, list):
                    case['steps'] = [{key: _masked(value) if isinstance(value, str) else value for key, value in step.items()}
                                     for step in evidence if isinstance(step, dict)][:500]
                for key in ('step_evidence_mode', 'business_step_complete', 'independent_checks_passed', 'required_step_count', 'success_step_count', 'failed_step', 'error_message', 'failure_selector'):
                    value = terminal.get(key)
                    if key != 'step_evidence_mode' or value is not None:
                        case[key] = _masked(value) if isinstance(value, str) else value
                status = 'PASS' if valid else 'FAIL' if status == 'FAIL' and returncode == 1 else 'ERROR'
                case.update(status=status, assertion_count=assertions, passed_assertion_count=passed,
                            browser_started=terminal.get('browser_started') is True, action_count=terminal.get('action_count'),
                            code_sha256=terminal.get('code_sha256'), browser_version=_masked(terminal.get('browser_version') or ''),
                            selenium_version=_masked(terminal.get('selenium_version') or ''))
                if status != 'PASS':
                    case['error'] = _masked(terminal.get('error') or ('독립 실행 검사 완료 근거 불충족'
                                           if case.get('business_step_required') else '브라우저 동작 및 assert 완료 근거 불충족'))
            case['returncode'] = returncode
        finally:
            self._kill(process)
            if group:
                group.close()
            stop_reader.set()
            if process.stdout:
                process.stdout.close()
            self._process = None
            case.update(completed_at=_now(), duration_ms=round((time.monotonic() - started) * 1000))
            if case.get('business_step_required') and case.get('business_step_complete') is not True:
                definitions = self._json(execution_scenario).get('steps', [])
                for position, definition in enumerate(definitions, 1):
                    row = next((row for row in case['steps'] if row.get('sequence') == position), None)
                    if row is None:
                        case['steps'].append(dict(sequence=position, action=_masked(definition.get('action', '')),
                                                  target=_masked(definition.get('target', '')), expected_result=_masked(definition.get('expected_result', '')),
                                                  status='SKIPPED', error='필수 단계 미실행'))
                    elif row.get('status') == 'RUNNING':
                        row.update(status='FAIL', error=case.get('error') or '단계 실행 중단', completed_at=case['completed_at'])
                case.update(step_evidence_mode='BUSINESS_STEPS', business_step_complete=False,
                            required_step_count=len(definitions), success_step_count=sum(row.get('status') == 'PASS' for row in case['steps']))
                failed = next((row for row in case['steps'] if row.get('status') != 'PASS'), None)
                if failed:
                    case['failed_step'] = failed['sequence']
            case.update(execution_id=job['execution_id'], start_time=case.get('started_at'), end_time=case.get('completed_at'))
            if case.get('status') != 'PASS' and not case.get('error_message'):
                case['error_message'] = case.get('error')
            case['runtime_ms'] = case['duration_ms']
            self._counts(job)
            self._save(job)

    def _provenance(self, job):
        # 실행 전 고정 스크립트 및 출처 보관
        execution = self._job_path(job['execution_id']).parent
        for case in job['cases']:
            source = self._safe(execution / case['case_id'] / 'script.py')
            require(_sha(source.read_bytes()) == case['sha256'], 'Execution snapshot SHA-256 mismatch')
            self._prepared_files(case, source.parent, source.read_bytes())
        if job.get('dataset_id'):
            directory = self._safe(self.root / 'data/evaluation' / job['dataset_id'])
            manifest = self._json(directory / 'data_manifest.json')
            raw = self._safe(directory / 'scripts.zip').read_bytes()
            require(_sha(raw) == manifest['files'][0]['sha256'], 'Fixed script archive SHA-256 mismatch')
            require(_sha(_encoded(manifest)) == job['dataset_manifest_sha256'], 'M04 manifest SHA-256 mismatch')
            return self._submission(job, directory, manifest, raw)
        inputs = dict(run_mode='DEVELOPMENT', official=False, data_class='DEVELOPMENT', script_language='python',
                      script_framework='selenium', scripts_manually_modified=False, execution_id=job['execution_id'],
                      scripts=[{key: value for key, value in case.items() if key not in {'steps', 'status', 'error', 'worker_pid'}} for case in job['cases']])
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('fixed_scripts.json', _encoded(inputs))
            for case in job['cases']:
                for name in ('script.py', 'script.json', 'source_scenario.json', 'execution_scenario.json', 'execution_contract.json', 'response.json', 'prompt.json', 'prepared_source.json', 'prepared_code.py'):
                    path = self._safe(execution / case['case_id'] / name)
                    if path.exists():
                        archive.writestr(case['case_id'] + '/' + name, path.read_bytes())
        raw = archive_buffer.getvalue()
        archive_sha = _sha(raw)
        dataset_id = 'm04-development-' + archive_sha[:12]
        directory = self._safe(self.root / 'data/evaluation' / dataset_id)
        directory.mkdir(parents=True, exist_ok=True)
        manifest = dict(dataset_id=dataset_id, metric_id='M04', run_mode='DEVELOPMENT', source_type='DEVELOPMENT',
                        data_class='DEVELOPMENT', official=False, synthetic=any(case['source_synthetic'] for case in job['cases']),
                        fixed_at=min(case['fixed_at'] for case in job['cases']), scripts_manually_modified=False,
                        script_language='python', script_framework='selenium', files=[dict(path='scripts.zip', sha256=archive_sha)])
        for name, value in (('scripts.zip', raw), ('data_manifest.json', _encoded(manifest))):
            path = self._safe(directory / name)
            if path.exists():
                require(path.read_bytes() == value, 'M04 provenance content differs')
            else:
                with path.open('xb') as output:
                    output.write(value)
        job['dataset_id'] = dataset_id
        job['dataset_manifest_sha256'] = _sha(_encoded(manifest))
        return self._submission(job, directory, manifest, raw)

    def _submission(self, job, directory, manifest, raw):
        config = deepcopy(self.config_provider())
        dataset_id = job['dataset_id']
        config.setdefault('integration_datasets', {})[dataset_id] = dict(run_mode='DEVELOPMENT', manifest=(directory / 'data_manifest.json').relative_to(self.root).as_posix())
        payload = dict(external_run_id=job['execution_id'], dataset_id=dataset_id, run_mode='DEVELOPMENT',
                       source_module='selenium-fixed-script-runner', source_version='m04-development-v2', submitted_at=_now(),
                       dataset_manifest_sha256=_sha(_encoded(manifest)), counts=job['counts'], cases=job['cases'],
                       details=dict(execution_id=job['execution_id'], synthetic=manifest['synthetic'],
                                    generated_by_llm=False if any(case.get('generated_by_llm') is False for case in job['cases']) else True if all(case.get('generated_by_llm') is True for case in job['cases']) else None,
                                    llm_generation_evidence_available=all(case.get('llm_generation_evidence_available') is True for case in job['cases']),
                                    script_registration='UPLOADED_FIXED_SCRIPT', logs=job['logs']))
        if any(case.get('code_source') == 'PREPARED' for case in job['cases']):
            payload['details']['code_source'] = 'PREPARED' if all(case.get('code_source') == 'PREPARED' for case in job['cases']) else 'MIXED'
        return config, payload, raw

    def _execute(self, execution_id, global_lock):
        job = self._job(execution_id)
        try:
            job['status'] = 'RUNNING'
            self._save(job)
            for case in job['cases']:
                if self._cancelled(execution_id):
                    self._interrupt(job, '사용자 실행 중단')
                    return
                try:
                    self._run_case(job, case)
                except Exception as exc:
                    case.update(status='ERROR', error=_masked(exc), completed_at=_now())
                    self._log(job, case['case_id'], case['error'])
                    self._counts(job)
                    self._save(job)
                if self._cancelled(execution_id):
                    self._interrupt(job, '사용자 실행 중단')
                    return
            self._counts(job)
            config, payload, archive = self._provenance(job)
            result = ingest(self.root, config, 'M04', payload)
            job.update(status='COMPLETED', completed_at=_now(), result=result)
            self._save(job)
        except BaseException as exc:
            job.update(status='ERROR', completed_at=_now(), result=None, error=_masked(exc))
            for case in job['cases']:
                if case['status'] in {'PENDING', 'RUNNING'}:
                    case.update(status='SKIPPED', error='실행 기록 저장 오류')
            self._counts(job)
            try:
                self._save(job)
            except OSError:
                pass
        finally:
            self._active = None
            global_lock.close()

    def artifact(self, execution_id, name):
        job = self._job(execution_id)
        require(name in {'report.json', 'log.jsonl', 'steps.csv', 'execution.json', 'logs.json', 'scripts.zip', 'screenshots.zip'}, 'Unknown M04 artifact')
        if name == 'screenshots.zip':
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                def add_file(filename, raw):
                    entry = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, raw)
                for case in sorted(job['cases'], key=lambda value: value['case_id']):
                    require(re.fullmatch(r'CASE-[0-9]{3}', case['case_id']), 'Invalid screenshot case ID')
                    folder = self._safe(self._job_path(execution_id).parent / case['case_id'])
                    for item, raw in verified_screenshots(case, folder):
                        add_file(case['case_id'] + '/' + item['file'], raw)
                add_file('manifest.json', _encoded(dict(execution_id=execution_id, policy=SCREENSHOT_POLICY,
                    notice=SCREENSHOT_NOTICE, cases=[dict(case_id=case['case_id'], screenshots=case.get('screenshots', [])) for case in job['cases']])))
            return buffer.getvalue(), 'application/zip'
        if name in {'report.json', 'execution.json'}:
            return _encoded(job), 'application/json; charset=utf-8'
        if name == 'logs.json':
            return _encoded(job['logs']), 'application/json; charset=utf-8'
        if name == 'log.jsonl':
            return b''.join((json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8') for row in job['logs']), 'application/x-ndjson; charset=utf-8'
        if name == 'steps.csv':
            buffer = io.StringIO(newline='')
            fields = ['execution_id', 'case_id', 'scenario_id', 'record_type', 'sequence', 'action', 'target', 'expected_result', 'status', 'started_at', 'completed_at', 'duration_ms', 'failure_selector', 'error', 'independent_checks_passed', 'check_results']
            writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for case in job['cases']:
                records = [('business_step', step) for step in case.get('steps', [])] if case.get('step_evidence_mode') == 'BUSINESS_STEPS' else []
                records += [('browser_trace', step) for step in case.get('action_logs', case.get('steps', []))]
                for record_type, step in records:
                    row = dict(step, execution_id=job['execution_id'], case_id=case['case_id'], scenario_id=case['scenario_id'], record_type=record_type)
                    writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value
                                     for key, value in row.items()})
            return buffer.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8'
        require(job.get('dataset_id'), 'Script archive not ready')
        path = self._safe(self.root / 'data/evaluation' / job['dataset_id'] / 'scripts.zip')
        raw = path.read_bytes()
        manifest = self._json(path.parent / 'data_manifest.json')
        require(_sha(raw) == manifest['files'][0]['sha256'], 'Fixed script archive SHA-256 mismatch')
        return raw, 'application/zip'

    def screenshot(self, execution_id, case_id, phase):
        require(isinstance(case_id, str) and re.fullmatch(r'CASE-[0-9]{3}', case_id), 'Invalid screenshot case ID')
        require(phase in {'before', 'after'}, 'Invalid screenshot phase')
        job = self._job(execution_id)
        case = next((row for row in job['cases'] if row.get('case_id') == case_id), None)
        if case is None:
            raise EvaluationError('Screenshot case not found', 'NOT_FOUND')
        folder = self._safe(self._job_path(execution_id).parent / case_id)
        for item, raw in verified_screenshots(case, folder):
            if item['phase'] == phase:
                return raw, 'image/png'
        raise EvaluationError('Masked screenshot was not captured', 'NOT_FOUND')
