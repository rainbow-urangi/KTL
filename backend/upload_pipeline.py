"""Request-scoped links from a verified M01 upload to its actual analysis.

Selection belongs to the requesting page. Reading a page never runs a model or
silently substitutes the legacy development dataset.
"""
from copy import deepcopy
import re
import threading
import uuid

from .evaluators import EvaluationError, digest, require
from .m01 import M01CsvStore
from .uploaded_analysis import analyze_upload, apply_analysis_config


class UploadPipeline:
    def __init__(self, root, session=None):
        self.root = root
        self.session = session
        self._lock = threading.RLock()
        self._analyses = {}
        self._latest = {}
        self._running = set()

    def dataset(self, dataset_id):
        require(isinstance(dataset_id, str) and re.fullmatch(r'[0-9a-f]{32}', dataset_id),
                'Invalid uploaded CSV dataset ID')
        return M01CsvStore(self.root, session=self.session).read(dataset_id, limit=1)['dataset']

    def state(self, dataset_id, analysis_id=None):
        dataset = self.dataset(dataset_id)
        with self._lock:
            identity = analysis_id or self._latest.get(dataset_id)
            snapshot = deepcopy(self._analyses.get(identity)) if identity else None
            running = dataset_id in self._running
        if analysis_id and snapshot is None:
            raise EvaluationError('현재 서버 세션의 분석 결과를 찾을 수 없습니다. M03에서 다시 생성하세요.', 'NOT_FOUND')
        if snapshot:
            require(snapshot.get('csv_dataset_id') == dataset_id,
                    '분석 결과와 선택한 업로드 CSV가 다릅니다.')
            require(snapshot.get('source_csv_sha256') == dataset['sha256'],
                    '분석 원본과 업로드 CSV의 SHA-256이 다릅니다.')
        return dict(snapshot or {}, csv_dataset_id=dataset_id, filename=dataset['filename'],
                    source_csv_sha256=dataset['sha256'], analysis_id=identity,
                    status='RUNNING' if running and not analysis_id else (snapshot or {}).get('status', 'NOT_READY'),
                    run_mode='DEVELOPMENT', official_pass=None)

    def config(self, config, dataset_id, analysis_id=None):
        state = self.state(dataset_id, analysis_id)
        if state['status'] != 'COMPLETED' or not state.get('m03_settings'):
            raise EvaluationError(state.get('error') or 'M03 시나리오 생성 시 업로드 CSV를 분석합니다.', 'NOT_READY')
        from .m03_integration import _project_path
        manifest = _project_path(self.root, state.get('input_manifest'))
        require(manifest.is_file() and digest(manifest) == state.get('input_manifest_sha256'),
                '분석 후 M03 입력 manifest의 SHA-256이 변경됐습니다.')
        effective = apply_analysis_config(config, state)
        effective['_upload_pipeline'] = {key: state[key] for key in ('csv_dataset_id', 'analysis_id', 'source_csv_sha256')}
        return effective

    def analyze(self, dataset_id):
        dataset = self.dataset(dataset_id)
        with self._lock:
            if dataset_id in self._running:
                raise EvaluationError('이 CSV를 분석하고 있습니다.', 'RUNNING')
            self._running.add(dataset_id)
        try:
            snapshot = analyze_upload(self.root, dataset_id, session=self.session)
            require(isinstance(snapshot, dict) and isinstance(snapshot.get('analysis_id'), str),
                    '분석 결과 ID가 없습니다.')
            require(snapshot.get('csv_dataset_id') == dataset_id
                    and snapshot.get('source_csv_sha256') == dataset['sha256'],
                    '분석 결과가 업로드 CSV와 연결되지 않았습니다.')
            # Failed attempts also become the latest attempt; do not revive an
            # older successful analysis after a failed run.
            with self._lock:
                self._analyses[snapshot['analysis_id']] = deepcopy(snapshot)
                self._latest[dataset_id] = snapshot['analysis_id']
            return snapshot
        except Exception:
            failure = dict(analysis_id='UPLOAD-ANALYSIS-' + uuid.uuid4().hex,
                           csv_dataset_id=dataset_id, source_csv_sha256=dataset['sha256'],
                           status='ERROR', model_status='ERROR',
                           error='업로드 CSV 분석을 완료하지 못했습니다. 분석 로그를 확인하세요.')
            with self._lock:
                self._analyses[failure['analysis_id']] = failure
                self._latest[dataset_id] = failure['analysis_id']
            return deepcopy(failure)
        finally:
            with self._lock:
                self._running.discard(dataset_id)
