# M07 생성 원본과 문법·실행 검사 기록
import ast
import base64
import csv
import io
import json
import re
import threading
import uuid
import zipfile
from copy import deepcopy
from pathlib import Path

from ..evaluators import EvaluationError, require
from .. import execution_contexts
from ..integration_store import ingest
from ..m03_integration import validate_scenario_result
from ..m03_management import scenario_deleted
from ..m04.store import M04Manager, _RunLock, _encoded, _masked, _now, _sha
from .generator import PROMPT_VERSION, GenerationError, generate, readiness, settings
from .prepared import read_codes
from .provider_state import ProviderState


ACTIVE = {'QUEUED', 'GENERATING', 'VALIDATING'}
M03_ID = re.compile(r'DEV-M03-\d{8}T\d{6}-[a-f0-9]{12}')


def _scenario_declared(tree, identity):
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if (any(isinstance(target, ast.Name) and target.id == 'SCENARIO_ID' for target in targets)
                    and isinstance(node.value, ast.Constant) and node.value.value == identity):
                return True
    return False


class M07Manager(M04Manager):
    _execution_pattern = re.compile(r'M07-GEN-[a-f0-9]{32}')
    _session_kind = 'M07'

    def __init__(self, root, config_provider, generator=None, session=None):
        self.root = Path(root).resolve()
        self.config_provider = config_provider
        self.session = session
        self.generator = generator or generate
        self.directory = self._safe(self.root / 'data/development/m07_codes')
        self.execution_directory = self._safe(self.directory / 'generations')
        self.execution_directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._active = self._process = None
        self.provider_state = ProviderState(self._safe(self.directory / 'provider_state.json'),
                                           read=self._json, write=self._write)
        self._recover()

    def _sync(self, job):
        for case in job['cases']:
            if job['status'] == 'VALIDATING' and case['syntax_status'] == 'PASS':
                case['execution_status'] = case['status']
            passed = all(case[key] == 'PASS' for key in ('generation_status', 'syntax_status', 'execution_status'))
            case['final_status'] = 'PASS' if passed else 'PENDING' if any(case[key] in {'PENDING', 'RUNNING'}
                                        for key in ('generation_status', 'syntax_status', 'execution_status')) else 'FAIL'
        self._counts(job)
        self._measurement(job)

    @staticmethod
    def _measurement(job):
        if job.get('measurement_version') != 1 or job.get('code_source') == 'PREPARED':
            return
        cases, counts = job['cases'], job['counts']
        denominator = 20 if job.get('meeting_protocol') is True else len(cases)
        attempted = sum(c.get('generation_http_attempted') is True for c in cases)
        unknown = sum(c.get('generation_invoked') is True and c.get('generation_http_attempted') is None for c in cases)
        completed = job['status'] == 'COMPLETED' and len(cases) == denominator and attempted == denominator and not unknown
        pending = job['status'] in ACTIVE or job['status'] == 'GENERATED' and attempted == len(cases) and not unknown
        measurement = dict(version=1, evaluation_status='COMPLETED' if completed else 'PENDING' if pending else 'NOT_READY',
                           registered_count=len(cases), provider_http_attempt_count=attempted,
                           provider_http_unknown_count=unknown,
                           not_attempted_count=sum(c.get('generation_http_attempted') is False for c in cases),
                           generation_invocation_count=sum(c.get('generation_invoked') is True for c in cases),
                           provider_response_count=sum(c.get('provider_response_observed') is True for c in cases),
                           provider_http_inferred_count=sum(c.get('generation_http_inferred') is True for c in cases),
                           browser_started_count=sum(c.get('browser_started') is True for c in cases),
                           generation_percent=None, syntax_percent=None, integrated_percent=None, browser_percent=None,
                           syntax_target_percent=80, syntax_target_met=None,
                           integrated_reference_target_percent=80, integrated_reference_target_met=None, official_pass=None)
        measurement.update({key: counts[key] for key in ('generated_code_count', 'syntax_pass_count', 'execution_pass_count', 'both_pass_count')})
        if job.get('meeting_protocol') is True:
            measurement.update(denominator=20, denominator_policy='MEETING_FIXED_20', required_count=20)
        if completed:
            measurement.update(generation_percent=100 * counts['generated_code_count'] / denominator,
                               syntax_percent=100 * counts['syntax_pass_count'] / denominator,
                               integrated_percent=100 * counts['both_pass_count'] / denominator)
            if measurement['browser_started_count']:
                measurement['browser_percent'] = 100 * counts['execution_pass_count'] / measurement['browser_started_count']
            measurement['syntax_target_met'] = measurement['syntax_percent'] >= 80
            measurement['integrated_reference_target_met'] = measurement['integrated_percent'] >= 80
        job['measurement'] = measurement

    def _provider_current(self, model=None):
        return self.provider_state.current(model or settings(self.root, self.config_provider())['model'])

    def current_provider_state(self):
        return self._provider_current()

    def _public_job(self, job):
        value = deepcopy(job)
        value['provider_state'] = self._provider_current()
        return value

    @staticmethod
    def _transport(case, proof):
        for source, target in (('http_request_attempted', 'generation_http_attempted'),
                               ('provider_response_observed', 'provider_response_observed')):
            value = proof.get(source)
            case[target] = value if type(value) is bool else None
        case['generation_http_inferred'] = (case['generation_http_attempted'] is None
                                            and isinstance(proof.get('request_id'), str) and bool(proof['request_id']))

    @staticmethod
    def _skip_provider_cases(job, cases, state):
        job['provider_stop'] = deepcopy(state)
        for case in cases:
            case.update(generation_status='SKIPPED', syntax_status='SKIPPED', execution_status='SKIPPED', status='SKIPPED',
                        generation_invoked=False, generation_http_attempted=False, provider_response_observed=False,
                        not_attempted_reason=state.get('reason') or 'HTTP_429_STOP',
                        error='Provider 제한으로 요청하지 않았습니다.')

    def _save(self, job):
        self._sync(job)
        super()._save(job)

    @staticmethod
    def _counts(job):
        cases = job['cases']
        job['counts'] = dict(generation_request_count=len(cases),
                             generated_code_count=sum(c['generation_status'] == 'PASS' for c in cases),
                             syntax_pass_count=sum(c['syntax_status'] == 'PASS' for c in cases),
                             execution_pass_count=sum(c['execution_status'] == 'PASS' for c in cases),
                             both_pass_count=sum(all(c[k] == 'PASS' for k in ('generation_status', 'syntax_status', 'execution_status')) for c in cases))

    def _interrupt(self, job, reason):
        for case in job['cases']:
            active_execution = (job['status'] == 'VALIDATING'
                                and (case['status'] in {'PENDING', 'RUNNING'} or case['execution_status'] == 'RUNNING')
                                and (case.get('started_at') or case['status'] == 'RUNNING' or case['execution_status'] == 'RUNNING'))
            if active_execution:
                self._interrupted_case(case, reason)
                case['execution_status'] = 'FAIL'
            for key in ('generation_status', 'syntax_status', 'execution_status', 'status'):
                if case[key] in {'PENDING', 'RUNNING'}:
                    case[key] = 'SKIPPED'
        job.update(status='INTERRUPTED', completed_at=_now(), error=reason, result=None)
        self._log(job, None, reason)
        self._save(job)

    def _recover(self):
        with self.lock:
            lock = self._global_lock()
            if not lock:
                return
            try:
                for path in self.execution_directory.glob('*/execution.json'):
                    if not self._session_has(self._session_kind, path.parent.name):
                        continue
                    job = self._json(path)
                    if job.get('status') in ACTIVE:
                        self._interrupt(job, '이전 작업이 중단되어 점수를 계산하지 않았습니다.')
            finally:
                lock.close()

    def _source(self, run_id, scenario_id):
        require(isinstance(run_id, str) and M03_ID.fullmatch(run_id), '저장된 DEVELOPMENT M03 실행 ID가 필요합니다.')
        self._session_check('RESULT', run_id)
        folder = self._safe(self.root / 'results/development' / run_id)
        result = self._json(folder / 'result.json')
        payload = self._json(folder / 'received_payload.json')
        require(result.get('metric_id') == 'M03' and result.get('run_mode') == 'DEVELOPMENT'
                and result.get('status') == 'COMPLETED', '저장된 M03 생성 결과가 필요합니다.')
        rows = payload.get('scenarios', [])
        matches = [row for row in rows if isinstance(row, dict) and row.get('scenario_id') == scenario_id]
        require(len(matches) == 1 and validate_scenario_result(matches[0])['success'], '유효한 M03 시나리오가 필요합니다.')
        source = deepcopy(matches[0])
        details = payload.get('details', {})
        synthetic = source.get('synthetic') is True or source.get('generator_mode') == 'MOCK' or details.get('synthetic') is True
        return source, synthetic

    def context(self):
        config = self.config_provider()
        ready = readiness(self.root, config)
        ready.update(self._readiness())
        ready['message'] = readiness(self.root, config)['message'] if not ready['configured'] else ready['message']
        scenarios = []
        paths = [path for path in sorted((self.root / 'results/development').glob('DEV-M03-*/received_payload.json'), reverse=True)
                 if self._session_has('RESULT', path.parent.name)]
        for path in paths[:200]:
            try:
                payload = self._json(path)
                for row in payload.get('scenarios', []):
                    if (isinstance(row, dict) and validate_scenario_result(row)['success']
                            and not scenario_deleted(self.root, path.parent.name, row['scenario_id'])):
                        source, synthetic = self._source(path.parent.name, row['scenario_id'])
                        source_hash = _sha(_encoded(source))
                        try:
                            self._execution_inputs(source, path.parent.name)
                            source.update(execution_ready=True, execution_notice='')
                        except EvaluationError as exc:
                            source.update(execution_ready=False, execution_notice=str(exc))
                        source.update(m03_run_id=path.parent.name, source_synthetic=synthetic, source_scenario_sha256=source_hash)
                        scenarios.append(source)
            except (EvaluationError, OSError, ValueError, TypeError):
                continue
        return dict(run_mode='DEVELOPMENT', readiness=ready, scenarios=scenarios, provider_state=self._provider_current(),
                    target_url=settings(self.root, config)['target_url'])

    def workflows(self):
        from .workflows import catalog
        return dict(catalog(self.root), readiness=self._readiness())

    def meeting_context(self):
        from .meeting import schema
        from ..m04.cu02 import login_configured
        config = self.config_provider()
        ready = dict(readiness(self.root, config), **self._readiness())
        ready.update(model_display_name=config.get('m07', {}).get('model_display_name', 'GPT 루나'),
                     login_configured=login_configured(self.root))
        ready['message'] = ('실제 LLM 코드 생성 준비 완료' if ready['configured']
                            else '업무 컴퓨터의 API 키와 실제 모델 ID를 연결하면 생성할 수 있습니다.')
        return dict(schema(), run_mode='DEVELOPMENT', measurement_protocol='M07_MEETING_20_V1', readiness=ready,
                    provider_state=self._provider_current())

    def create_meeting(self, payload):
        from .meeting import prepare_batch
        items = prepare_batch(payload)
        if not readiness(self.root, self.config_provider())['configured'] and self.generator is generate:
            raise EvaluationError('업무 컴퓨터의 API 키와 실제 모델 ID를 연결하세요. 실행하지 않은 결과는 생성하지 않습니다.', 'NOT_CONFIGURED')
        if self._provider_current()['blocked']:
            raise EvaluationError('LLM 공급자 대기 상태입니다. 제한 해제 후 새 작업으로 시작하세요.', 'NOT_READY')
        refs = [dict(m03_run_id=None, scenario_id=row['scenario']['scenario_id']) for row in items]
        sources = [(ref, row['scenario'], False) for ref, row in zip(refs, items)]
        inputs = [self._execution_inputs(row['scenario']) for row in items]
        return self._create_sources(sources, inputs, {}, False, meeting_items=items)

    def prepare_workflows(self, payload):
        from .workflows import prepare_batch
        from ..m04.cu02 import login_configured
        prepared = prepare_batch(payload)
        if not login_configured(self.root):
            raise EvaluationError('준비 코드 실행을 위한 시험 계정 설정이 필요합니다.', 'NOT_CONFIGURED')
        refs = [dict(m03_run_id=None, scenario_id=item['scenario']['scenario_id']) for item in prepared]
        uploads = [dict(scenario_id=item['scenario']['scenario_id'],
                        filename=item['scenario']['workflow_id'].lower() + '-prepared-' + str(item['case_number']) + '.py',
                        code_base64=base64.b64encode(item['code'].encode('utf-8')).decode('ascii'),
                        sha256=_sha(item['code'].encode('utf-8'))) for item in prepared]
        registered = read_codes(self.root, uploads, refs)
        sources = [(ref, item['scenario'], False) for ref, item in zip(refs, prepared)]
        inputs = [self._execution_inputs(item['scenario']) for item in prepared]
        response = self._create_sources(sources, inputs, registered, True, workflows=prepared)
        return dict(response, workflows=[item['scenario']['workflow_id'] for item in prepared])

    def execution_context(self, m03_run_id, scenario_id):
        source, _ = self._source(m03_run_id, scenario_id)
        require(not scenario_deleted(self.root, m03_run_id, scenario_id), '삭제한 시나리오의 실행 조건은 편집할 수 없습니다.')
        return {'execution_context': execution_contexts.editor(self.root, m03_run_id, source, self.config_provider())}

    def save_execution_context(self, payload):
        require(isinstance(payload, dict) and set(payload) == {'m03_run_id', 'scenario_id', 'execution_contract', 'expected_results'},
                '시나리오 ID, 실행 계약, 단계 기대 결과가 필요합니다.')
        run_id, scenario_id = payload['m03_run_id'], payload['scenario_id']
        source, _ = self._source(run_id, scenario_id)
        require(not scenario_deleted(self.root, run_id, scenario_id), '삭제한 시나리오의 실행 조건은 저장할 수 없습니다.')
        with self.lock:
            value = execution_contexts.save(self.root, run_id, source, self.config_provider(),
                                            payload['execution_contract'], payload['expected_results'])
        return {'execution_context': value}

    def save_execution_plan(self, payload):
        require(isinstance(payload, dict) and set(payload) == {'m03_run_id', 'scenario_id', 'execution_plan'},
                'M03 실행 ID, 시나리오 ID와 별도 실행 계획이 필요합니다.')
        run_id, scenario_id = payload['m03_run_id'], payload['scenario_id']
        source, _ = self._source(run_id, scenario_id)
        require(not scenario_deleted(self.root, run_id, scenario_id), '삭제한 시나리오의 실행 계획은 저장할 수 없습니다.')
        with self.lock:
            value = execution_contexts.save_plan(self.root, run_id, source, self.config_provider(), payload['execution_plan'])
        return {'execution_context': value}

    def select_scenarios(self, payload):
        require(isinstance(payload, dict) and set(payload) == {'items'} and isinstance(payload['items'], list)
                and 1 <= len(payload['items']) <= 20, '저장된 시나리오 또는 원본 참조 1~20건이 필요합니다.')
        available = self.context()['scenarios']
        selected = []
        for position, item in enumerate(payload['items'], 1):
            require(isinstance(item, dict) and isinstance(item.get('scenario_id'), str),
                    '각 입력에 scenario_id가 필요합니다.')
            if 'm03_run_id' in item and 'steps' not in item:
                require(set(item) == {'m03_run_id', 'scenario_id', 'source_scenario_sha256'}
                        and isinstance(item.get('source_scenario_sha256'), str)
                        and re.fullmatch(r'[a-f0-9]{64}', item['source_scenario_sha256']),
                        '원본 참조에는 M03 실행 ID, 시나리오 ID와 원본 SHA-256이 필요합니다.')
                matches = [row for row in available if row['m03_run_id'] == item['m03_run_id']
                           and row['scenario_id'] == item['scenario_id']
                           and row['source_scenario_sha256'] == item['source_scenario_sha256']]
            else:
                raw_hash = _sha(_encoded(item))
                matches = [row for row in available if row['scenario_id'] == item['scenario_id']
                           and row['source_scenario_sha256'] == raw_hash]
            require(len(matches) == 1, '입력 ' + str(position) + '이 저장된 M03 원본과 일치하지 않거나 중복됩니다. 실행 ID와 원본 해시를 확인하세요.')
            row = matches[0]
            if row['execution_ready'] is not True:
                raise EvaluationError('입력 ' + str(position) + '의 실행 조건을 먼저 저장하세요.', 'NOT_READY')
            selected.append(dict(m03_run_id=row['m03_run_id'], scenario_id=row['scenario_id'],
                                 source_scenario_sha256=row['source_scenario_sha256']))
        require(len({row['scenario_id'] for row in selected}) == len(selected), '동일 시나리오를 여러 시험 건수로 선택할 수 없습니다.')
        return dict(scenario_refs=selected, selected_count=len(selected))

    def list_runs(self):
        self._recover()
        values = [self._json(p) for p in self.execution_directory.glob('*/execution.json')
                  if self._session_has(self._session_kind, p.parent.name)]
        values.sort(key=lambda item: item['started_at'], reverse=True)
        return {'generations': [{k: v for k, v in self._public_job(job).items() if k not in {'cases', 'logs'}} for job in values],
                'provider_state': self._provider_current()}

    def read(self, execution_id):
        self._recover()
        return {'generation': self._public_job(self._job(execution_id)), 'provider_state': self._provider_current()}

    def create(self, payload):
        require(isinstance(payload, dict) and payload.get('run_mode', 'DEVELOPMENT') == 'DEVELOPMENT', 'M07 DEVELOPMENT 요청이 필요합니다.')
        require(set(payload) <= {'run_mode', 'scenario_refs', 'm03_run_id', 'scenario_ids', 'prepared_codes'}, '지원하지 않는 생성 요청 항목입니다.')
        prepared_request = 'prepared_codes' in payload
        if not prepared_request and not readiness(self.root, self.config_provider())['configured'] and self.generator is generate:
            raise EvaluationError('OpenAI API 키와 KTL_M07_MODEL 설정이 필요합니다.', 'NOT_CONFIGURED')
        if not prepared_request and self._provider_current()['blocked']:
            raise EvaluationError('Provider 대기 상태입니다. 현재 제한과 다음 요청 가능 시각을 확인하세요.', 'NOT_READY')
        refs = payload.get('scenario_refs')
        if refs is None:
            ids = payload.get('scenario_ids')
            require(isinstance(ids, list), '시나리오 선택이 필요합니다.')
            refs = [dict(m03_run_id=payload.get('m03_run_id'), scenario_id=value) for value in ids]
        require(isinstance(refs, list) and 1 <= len(refs) <= 20
                and all(isinstance(row, dict) and isinstance(row.get('scenario_id'), str) for row in refs), '서로 다른 시나리오 1~20건을 선택하세요.')
        require(len({row['scenario_id'] for row in refs}) == len(refs), '중복 시나리오는 별도 시험 건수로 등록할 수 없습니다.')
        for row in refs:
            self._session_check('RESULT', row.get('m03_run_id'))
        registered = read_codes(self.root, payload['prepared_codes'], refs) if prepared_request else {}
        require(all(not scenario_deleted(self.root, row.get('m03_run_id'), row['scenario_id']) for row in refs),
                '삭제한 M03 시나리오는 새 코드 생성에 사용할 수 없습니다.')
        sources = [(row, *self._source(row.get('m03_run_id'), row['scenario_id'])) for row in refs]
        for ref, source, _ in sources:
            if 'source_scenario_sha256' in ref:
                require(isinstance(ref['source_scenario_sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', ref['source_scenario_sha256'])
                        and _sha(_encoded(source)) == ref['source_scenario_sha256'],
                        '선택한 M03 원본이 변경되었습니다. 원본을 확인하고 다시 선택하세요.')
        prepared_inputs = [self._execution_inputs(source, ref['m03_run_id']) for ref, source, _ in sources]
        return self._create_sources(sources, prepared_inputs, registered, prepared_request)

    def _create_sources(self, sources, prepared_inputs, registered, prepared_request, *, workflows=None, meeting_items=None):
        with self.lock:
            run_lock = self._global_lock()
            if not run_lock:
                raise EvaluationError('M07 작업이 실행 중입니다.', 'RUNNING')
            try:
                self._recover_locked()
                identity = 'M07-GEN-' + uuid.uuid4().hex
                self._session_claim(self._session_kind, identity)
                folder = self._safe(self.execution_directory / identity)
                folder.mkdir()
                cases = []
                for index, ((ref, source, synthetic), prepared) in enumerate(zip(sources, prepared_inputs), 1):
                    contract = prepared['contract']
                    case_id = 'CASE-' + str(index).zfill(3)
                    case_dir = self._safe(folder / case_id)
                    case_dir.mkdir()
                    raw = _encoded(source)
                    (case_dir / 'source_scenario.json').write_bytes(raw)
                    execution_raw = _encoded(prepared['scenario'])
                    (case_dir / 'execution_scenario.json').write_bytes(execution_raw)
                    contract_raw = _encoded(contract)
                    (case_dir / 'execution_contract.json').write_bytes(contract_raw)
                    cases.append(dict(case_id=case_id, scenario_id=source['scenario_id'],
                                      scenario_name=source.get('scenario_name', source['scenario_id']),
                                      source_m03_run_id=ref['m03_run_id'], source_synthetic=synthetic,
                                      source_scenario_sha256=_sha(raw), status='PENDING',
                                      execution_contract_sha256=_sha(contract_raw), execution_contract_version=contract['version'],
                                      execution_scenario_sha256=_sha(execution_raw), execution_context_revision_id=prepared['revision_id'],
                                      business_step_required=True,
                                      generation_status='PENDING', syntax_status='PENDING', execution_status='PENDING',
                                      final_status='PENDING', steps=[], error=None))
                    if meeting_items is not None:
                        item = meeting_items[index - 1]
                        item_raw = _encoded(item['source_raw'])
                        with (case_dir / 'meeting_input.json').open('xb') as output:
                            output.write(item_raw)
                        cases[-1].update(source_kind='MEETING_SCENARIO_INPUT', input_id=item['input_id'],
                                         meeting_input_sha256=_sha(item_raw), code_source='LLM')
                    if prepared.get('execution_plan') is not None:
                        plan_raw = _encoded(prepared['execution_plan'])
                        (case_dir / 'execution_plan.json').write_bytes(plan_raw)
                        cases[-1]['execution_plan_sha256'] = _sha(plan_raw)
                    if prepared_request:
                        record = registered[source['scenario_id']]
                        metadata = dict(code_source='PREPARED', generated_by_llm=False,
                                        scenario_id=source['scenario_id'], source_filename=record['source_filename'],
                                        source_file_sha256=record['source_file_sha256'], registered_at=_now())
                        origin = _encoded(metadata)
                        for name, content in (('prepared_code.py', record['raw']), ('prepared_source.json', origin)):
                            with (case_dir / name).open('xb') as output:
                                output.write(content)
                        cases[-1].update(code_source='PREPARED', generated_by_llm=False,
                                         source_filename=record['source_filename'], source_file_sha256=record['source_file_sha256'],
                                         prepared_source_sha256=_sha(origin))
                        if workflows is not None:
                            item = workflows[index - 1]
                            for name, content in item['source_files'].items():
                                with (case_dir / name).open('xb') as output:
                                    output.write(content)
                            cases[-1].update(source_kind='RBEM_PREPARED_WORKFLOW', workflow_id=source['workflow_id'],
                                             workflow_case_number=item['case_number'], browser='chrome',
                                             source_workflow_files={name: _sha(content) for name, content in item['source_files'].items()},
                                             generation_invoked=False, generation_http_attempted=False,
                                             provider_response_observed=False)
                    else:
                        cases[-1].update(generation_invoked=False, generation_http_attempted=False,
                                         provider_response_observed=False)
                job = dict(execution_id=identity, generation_id=identity, status='QUEUED', run_mode='DEVELOPMENT',
                           started_at=_now(), completed_at=None, cases=cases, logs=[], result=None, error=None,
                           artifacts=[dict(name=name, url=f'/api/development/m07/generations/{identity}/artifacts/{name}')
                                      for name in ('report.json', 'log.jsonl', 'steps.csv', 'code.zip', 'screenshots.zip')])
                if prepared_request:
                    job.update(code_source='PREPARED', generated_by_llm=False)
                else:
                    job.update(measurement_version=1, provider_model=settings(self.root, self.config_provider())['model'])
                if workflows is not None:
                    job.update(source_kind='RBEM_PREPARED_WORKFLOW', browser='chrome',
                               workflow_ids=list(dict.fromkeys(item['scenario']['workflow_id'] for item in workflows)))
                if meeting_items is not None:
                    batch_raw = _encoded({'items': [item['source_raw'] for item in meeting_items]})
                    with (folder / 'meeting_inputs.json').open('xb') as output:
                        output.write(batch_raw)
                    job.update(meeting_protocol=True, measurement_protocol='M07_MEETING_20_V1',
                               required_count=20, target_percent=80, code_source='LLM',
                               source_kind='MEETING_LLM_BATCH', meeting_inputs_sha256=_sha(batch_raw),
                               model_display_name=self.config_provider().get('m07', {}).get('model_display_name', 'GPT 루나'))
                job.update(visible_browser=True, action_delay_ms=350, keep_open_seconds=3)
                if getattr(self, 'session', None) is not None:
                    job['server_session_id'] = self.session.id
                self._save(job)
                self._launch(identity, 'generate', run_lock)
                return {'generation': self._public_job(job)}
            except BaseException:
                run_lock.close()
                raise

    def _recover_locked(self):
        for path in self.execution_directory.glob('*/execution.json'):
            if not self._session_has(self._session_kind, path.parent.name):
                continue
            job = self._json(path)
            if job.get('status') in ACTIVE:
                self._interrupt(job, '이전 작업이 중단되어 점수를 계산하지 않았습니다.')

    def _launch(self, identity, phase, run_lock, browser_lock=None):
        self._active = identity
        threading.Thread(target=self._work, args=(identity, phase, run_lock, browser_lock),
                         daemon=True, name='M07-' + identity[-8:]).start()

    def validate(self, identity):
        with self.lock:
            job = self._job(identity)
            require(job['status'] == 'GENERATED', '생성 완료 후 한 번만 검사할 수 있습니다.')
            # 이전 생성 기록에 없는 검증 근거를 실패 점수로 만들지 않음
            for case in job['cases']:
                if case.get('generation_status') == 'PASS':
                    if (not isinstance(case.get('execution_contract_sha256'), str)
                            or not re.fullmatch(r'[0-9a-f]{64}', case['execution_contract_sha256'])
                            or not self._case_path(job, case, 'execution_contract.json').is_file()):
                        raise EvaluationError('이전 생성 기록에는 독립 실행 조건이 없습니다. 원본을 보관하고 현재 조건으로 새로 생성하세요.', 'NOT_READY')
            ready = self._readiness()
            if not ready['selenium'] or not ready['chrome']:
                raise EvaluationError(ready['message'], 'NOT_CONFIGURED')
            run_lock = self._global_lock()
            if not run_lock:
                raise EvaluationError('M07 작업이 실행 중입니다.', 'RUNNING')
            lock_dir = self._safe(self.root / 'data/development/m04_runner')
            lock_dir.mkdir(parents=True, exist_ok=True)
            browser_lock = _RunLock(self._safe(lock_dir / 'runner.lock'))
            if not browser_lock.acquire():
                run_lock.close()
                raise EvaluationError('다른 Selenium 실행이 진행 중입니다.', 'RUNNING')
            try:
                job.update(status='VALIDATING', validation_started_at=_now())
                self._save(job)
                self._launch(identity, 'validate', run_lock, browser_lock)
                return {'generation': self._public_job(job)}
            except BaseException:
                browser_lock.close()
                run_lock.close()
                raise

    def cancel(self, identity):
        with self.lock:
            job = self._job(identity)
            if job['status'] in ACTIVE:
                self._safe(self._job_path(identity).parent / 'cancel.request').touch(exist_ok=True)
                job['cancel_requested'] = True
            return {'generation': self._public_job(job)}

    def _case_path(self, job, case, name):
        return self._safe(self._job_path(job['execution_id']).parent / case['case_id'] / name)

    def _check(self, job, case):
        for name, key in (('source_scenario.json', 'source_scenario_sha256'), ('script.py', 'sha256'),
                          ('response.json', 'response_sha256'), ('prompt.json', 'prompt_sha256'),
                          ('execution_scenario.json', 'execution_scenario_sha256'),
                          ('execution_contract.json', 'execution_contract_sha256'),
                           ('execution_plan.json', 'execution_plan_sha256'),
                          ('prepared_code.py', 'source_file_sha256'),
                          ('prepared_source.json', 'prepared_source_sha256'),
                          ('meeting_input.json', 'meeting_input_sha256')):
            if key in case:
                require(_sha(self._case_path(job, case, name).read_bytes()) == case[key], '보관 원본 SHA-256 불일치: ' + name)
        if job.get('meeting_protocol') is True:
            self._check_meeting_inputs(job)
        if job.get('code_source') == 'PREPARED':
            require(case.get('code_source') == 'PREPARED' and case.get('generated_by_llm') is False
                    and case.get('prepared_source_sha256') and case.get('source_file_sha256'),
                    '등록 코드의 출처 근거가 일치하지 않습니다.')
            origin = self._json(self._case_path(job, case, 'prepared_source.json'))
            require(origin.get('code_source') == 'PREPARED' and origin.get('generated_by_llm') is False
                    and origin.get('scenario_id') == case['scenario_id']
                    and origin.get('source_filename') == case.get('source_filename')
                    and origin.get('source_file_sha256') == case.get('source_file_sha256')
                    and ('sha256' not in case or case['sha256'] == case['source_file_sha256']),
                    '등록 코드 원본과 표시·검사 파일이 일치하지 않습니다.')
        if case.get('source_kind') == 'RBEM_PREPARED_WORKFLOW':
            hashes = case.get('source_workflow_files')
            require(isinstance(hashes, dict) and set(hashes) == {'workflow_definition.json', 'workflow_parameters.json'},
                    '준비 업무의 정의와 입력 원본이 필요합니다.')
            require(all(_sha(self._case_path(job, case, name).read_bytes()) == expected for name, expected in hashes.items()),
                    '준비 업무의 정의·입력 SHA-256이 다릅니다.')
            require(case.get('source_m03_run_id') is None and case.get('generated_by_llm') is False,
                    '준비 업무의 코드 출처가 다릅니다.')

    def _check_meeting_inputs(self, job):
        from .meeting import prepare_batch
        raw = self._safe(self._job_path(job['execution_id']).parent / 'meeting_inputs.json').read_bytes()
        require(_sha(raw) == job.get('meeting_inputs_sha256') and job.get('required_count') == 20,
                '사전에 고정한 20개 입력 원본의 SHA-256이 다릅니다.')
        items = prepare_batch(json.loads(raw))
        require(len(job['cases']) == len(items) == 20 and job.get('code_source') == 'LLM',
                '회의용 시험은 실제 LLM 입력 20건으로 고정해야 합니다.')
        for item, case in zip(items, job['cases']):
            require(case.get('input_id') == item['input_id'] and case.get('source_m03_run_id') is None
                    and case.get('source_kind') == 'MEETING_SCENARIO_INPUT' and case.get('code_source') == 'LLM'
                    and case.get('scenario_id') == item['scenario']['scenario_id']
                    and case.get('source_scenario_sha256') == _sha(_encoded(item['scenario']))
                    and case.get('meeting_input_sha256') == _sha(_encoded(item['source_raw'])),
                    '20개 입력과 사례·실행 조건의 연결이 다릅니다.')

    def _generate(self, job):
        job['status'] = 'GENERATING'
        self._save(job)
        config = self.config_provider()
        for index, case in enumerate(job['cases']):
            if self._cancelled(job['execution_id']):
                self._interrupt(job, '사용자 생성 중단')
                return
            if job.get('code_source') != 'PREPARED':
                state = self._provider_current(job.get('provider_model'))
                if state['blocked']:
                    self._skip_provider_cases(job, job['cases'][index:], state)
                    break
            case.update(generation_status='RUNNING', generation_started_at=_now())
            self._save(job)
            try:
                self._check(job, case)
                if job.get('code_source') == 'PREPARED':
                    raw = self._case_path(job, case, 'prepared_code.py').read_bytes()
                    with self._case_path(job, case, 'script.py').open('xb') as output:
                        output.write(raw)
                    case.update(generation_status='PASS', sha256=_sha(raw), code_sha256=_sha(raw),
                                generated_by_llm=False, business_step_required=True)
                    self._log(job, case['case_id'], '등록한 원본 코드 불러오기 완료')
                    self._check(job, case)
                    case['generation_completed_at'] = _now()
                    self._save(job)
                    continue
                scenario_file = 'execution_scenario.json' if case.get('execution_scenario_sha256') else 'source_scenario.json'
                source = self._json(self._case_path(job, case, scenario_file))
                generation_input = dict(source, execution_contract=self._json(self._case_path(job, case, 'execution_contract.json')))
                if job.get('meeting_protocol') is True:
                    generation_input['meeting_protocol'] = True
                case.update(generation_invoked=True, generation_http_attempted=None, provider_response_observed=None)
                value = self.generator(self.root, config, generation_input)
                self._transport(case, value)
                code = value['code'].encode('utf-8')
                require(0 < len(code) <= 262144 and value.get('generated_by_llm') is True, 'LLM 생성 원본 근거가 필요합니다.')
                response = value.get('response_bytes') or _encoded(value['response'])
                prompt = _encoded({key: value.get(key) for key in ('instructions', 'input', 'prompt_version', 'requested_model')})
                for name, raw in (('script.py', code), ('response.json', response), ('prompt.json', prompt)):
                    with self._case_path(job, case, name).open('xb') as output:
                        output.write(raw)
                case.update(generation_status='PASS', sha256=_sha(code), code_sha256=_sha(code),
                            response_sha256=_sha(response), prompt_sha256=_sha(prompt),
                            model=value.get('model'), request_id=value.get('request_id'),
                            prompt_version=value.get('prompt_version'), generated_by_llm=True,
                            business_step_required=True)
                self._log(job, case['case_id'], '코드 생성 원본 보관 완료')
            except Exception as exc:
                if isinstance(exc, GenerationError):
                    proof = exc.evidence
                    self._transport(case, proof)
                    response = proof.get('response_bytes') or _encoded(proof.get('response', {}))
                    prompt = _encoded({key: proof.get(key) for key in ('instructions', 'input', 'prompt_version', 'requested_model')})
                    for name, raw, key in (('response.json', response, 'response_sha256'), ('prompt.json', prompt, 'prompt_sha256')):
                        with self._case_path(job, case, name).open('xb') as output:
                            output.write(raw)
                        case[key] = _sha(raw)
                    case.update(model=proof.get('model'), request_id=proof.get('request_id'), prompt_version=proof.get('prompt_version'))
                    response_value = proof.get('response', {})
                    if isinstance(response_value, dict) and type(response_value.get('http_status')) is int and response_value['http_status'] == 429:
                        try:
                            state = self.provider_state.record(job.get('provider_model') or proof.get('requested_model') or proof.get('model'),
                                response_value, generation_id=job['generation_id'], evidence_sha256=case['response_sha256'])
                        except EvaluationError:
                            state = self._provider_current(job.get('provider_model'))
                        self._skip_provider_cases(job, job['cases'][index + 1:], state)
                case.update(generation_status='ERROR', syntax_status='SKIPPED', execution_status='SKIPPED',
                            status='SKIPPED', error=_masked(exc))
                self._log(job, case['case_id'], case['error'])
            case['generation_completed_at'] = _now()
            self._save(job)
            if job.get('provider_stop'):
                break
        if self._cancelled(job['execution_id']):
            self._interrupt(job, '사용자 생성 중단')
            return
        self._archive(job)
        job.update(status='GENERATED', generated_at=_now())
        self._save(job)

    def _archive(self, job):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('generation.json', _encoded(dict(generation_id=job['generation_id'], cases=job['cases'])))
            if job.get('meeting_protocol') is True:
                self._check_meeting_inputs(job)
                archive.writestr('meeting_inputs.json', self._safe(self._job_path(job['execution_id']).parent / 'meeting_inputs.json').read_bytes())
            for case in job['cases']:
                self._check(job, case)
                for name in ('source_scenario.json', 'execution_scenario.json', 'execution_contract.json', 'execution_plan.json', 'script.py',
                             'response.json', 'prompt.json', 'prepared_code.py', 'prepared_source.json',
                             'workflow_definition.json', 'workflow_parameters.json', 'meeting_input.json'):
                    path = self._case_path(job, case, name)
                    if path.exists():
                        archive.writestr(case['case_id'] + '/' + name, path.read_bytes())
        raw = buffer.getvalue()
        with self._safe(self._job_path(job['execution_id']).parent / 'code.zip').open('xb') as output:
            output.write(raw)
        job['archive_sha256'] = _sha(raw)

    def _validate(self, job):
        if job.get('meeting_protocol') is True:
            self._check_meeting_inputs(job)
        archive = self._safe(self._job_path(job['execution_id']).parent / 'code.zip').read_bytes()
        require(_sha(archive) == job['archive_sha256'], '생성 원본 묶음 SHA-256 불일치')
        for case in job['cases']:
            if self._cancelled(job['execution_id']):
                self._interrupt(job, '사용자 검사 중단')
                return
            if case['generation_status'] != 'PASS':
                continue
            self._check(job, case)
            checked_code = self._case_path(job, case, 'script.py').read_bytes()
            case['validation_code_sha256'] = _sha(checked_code)
            require(case['validation_code_sha256'] == case['code_sha256'], '화면 코드와 문법 검사 원본이 다릅니다.')
            try:
                tree = ast.parse(checked_code, filename='script.py')
            except (SyntaxError, UnicodeError, ValueError) as exc:
                case.update(syntax_status='FAIL', execution_status='SKIPPED', status='SKIPPED',
                            error='Python 문법 오류' + (' (행 ' + str(exc.lineno) + ')' if isinstance(exc, SyntaxError) else ''))
                self._save(job)
                continue
            case['syntax_status'] = 'PASS'
            imports = any((isinstance(node, ast.Import) and any(a.name.split('.')[0] == 'selenium' for a in node.names))
                          or (isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] == 'selenium') for node in ast.walk(tree))
            if (not imports or not any(isinstance(node, ast.Assert) for node in ast.walk(tree))
                    or not _scenario_declared(tree, case['scenario_id'])):
                case.update(status='SKIPPED', error='Selenium import, 일치하는 SCENARIO_ID 및 기대 결과 assert가 필요합니다.')
                self._save(job)
                continue
            try:
                self._run_case(job, case)
                if (case.get('business_step_required') and case['status'] == 'PASS'
                        and (case.get('business_step_complete') is not True or case.get('independent_checks_passed') is not True)):
                    case.update(status='FAIL', execution_status='FAIL', error='필수 업무 단계와 기대 결과 검증이 완료되지 않았습니다.')
            except Exception as exc:
                case.update(status='ERROR', execution_status='ERROR', error=_masked(exc))
            self._save(job)
            self._check(job, case)
        if self._cancelled(job['execution_id']):
            self._interrupt(job, '사용자 검사 중단')
            return
        self._sync(job)
        job.update(status='COMPLETED', completed_at=_now())
        self._sync(job)
        ready = job.get('measurement_version') != 1 or job['measurement']['evaluation_status'] == 'COMPLETED'
        if job.get('meeting_protocol') is True:
            if ready:
                self._evaluate_meeting(job, archive)
            else:
                job['result'] = None
                job['error'] = '20건 전체의 실제 LLM 요청·검사 근거가 아직 완비되지 않았습니다.'
        elif ready and job['counts']['generated_code_count']:
            self._evaluate(job, archive)
            if job.get('measurement_version') == 1:
                job['legacy_result'] = deepcopy(job['result'])
                job['result_scope'] = 'LEGACY_GENERATED_CODE_COUNT'
        else:
            job['result'] = None
            job['error'] = '전체 등록 요청의 HTTP 시도 근거 또는 생성 코드가 없어 점수를 계산할 수 없습니다.'
        self._save(job)

    def _evaluate_meeting(self, job, archive):
        from ..run_storage import save_run
        self._check_meeting_inputs(job)
        measurement = job.get('measurement', {})
        require(measurement.get('evaluation_status') == 'COMPLETED'
                and measurement.get('provider_http_attempt_count') == 20
                and job['status'] == 'COMPLETED', '실제 LLM 요청 20건의 완료 근거가 필요합니다.')
        require(all(case['final_status'] in {'PASS', 'FAIL'} for case in job['cases']), '20건 모두 최종 판정이 필요합니다.')
        require(_sha(archive) == job['archive_sha256'], '검사한 코드 원본 묶음 SHA-256이 다릅니다.')
        for case in job['cases']:
            self._check(job, case)
        folder = self._job_path(job['execution_id']).parent
        hashes = {str((folder / name).relative_to(self.root)).replace('\\', '/'): _sha((folder / name).read_bytes())
                  for name in ('meeting_inputs.json', 'code.zip')}
        counts = deepcopy(job['counts'])
        score = 100 * counts['both_pass_count'] / 20
        rows = [{key: case.get(key) for key in ('case_id', 'input_id', 'scenario_id', 'generation_status',
                'syntax_status', 'execution_status', 'final_status', 'code_sha256', 'validation_code_sha256',
                'meeting_input_sha256', 'model', 'request_id', 'error')} for case in job['cases']]
        details = dict(measurement_protocol='M07_MEETING_20_V1', denominator_policy='MEETING_FIXED_20',
                       denominator=20, formula='both_pass_count / 20 * 100', raw_counts=counts,
                       generated_by_llm=counts['generated_code_count'] > 0, actual_llm_request_count=20,
                       measurement=deepcopy(measurement),
                       meeting_inputs_sha256=job['meeting_inputs_sha256'], archive_sha256=job['archive_sha256'])
        received = dict(generation_id=job['generation_id'], run_mode='DEVELOPMENT', code_source='LLM',
                        counts=counts, cases=deepcopy(job['cases']), details=deepcopy(details))
        result = dict(status='COMPLETED', source_type='DEVELOPMENT', score=score, sample_count=20,
                      details=details, input_sha256=hashes, evaluator_version='m07-meeting-fixed-20-v1',
                      provenance=dict(source_module='llm-meeting-20-validator', source_version='v1',
                                      external_run_id=job['generation_id'], submitted_at=_now()))
        job['result'] = save_run(self.root, 'M07', 'DEVELOPMENT', self.config_provider(), result, rows, received=received)
        job['result_scope'] = 'MEETING_FIXED_20'

    def _evaluate(self, job, archive):
        if job.get('code_source') == 'PREPARED':
            counts = job['counts']
            total = counts['generated_code_count']
            value = 100 * counts['both_pass_count'] / total
            target = self.config_provider().get('targets', {}).get('M07', 80)
            job['result'] = dict(run_id=job['generation_id'], metric_id='M07', run_mode='DEVELOPMENT',
                                 status='COMPLETED', score=value, sample_count=total, target=target, operator='>=',
                                 threshold_met=value >= target, official_pass=None, completed_at=_now(),
                                 details=dict(code_source='PREPARED', generated_by_llm=False,
                                              source_module='prepared-code-validator', raw_counts=deepcopy(counts),
                                              formula='both_pass_count / registered_code_count * 100',
                                              denominator_policy='REGISTERED_CODE_COUNT', denominator=total,
                                              notice='등록한 원본 코드의 실제 문법·실행 검사 결과입니다. LLM 생성 성능에는 포함하지 않습니다.'))
            job['result']['pass'] = None
            job['result']['provenance'] = dict(code_source='PREPARED', generated_by_llm=False,
                                              source_module='prepared-code-validator', external_run_id=job['generation_id'])
            return
        dataset = 'm07-development-' + job['archive_sha256'][:12]
        folder = self._safe(self.root / 'data/evaluation' / dataset)
        folder.mkdir(parents=True, exist_ok=True)
        manifest = dict(dataset_id=dataset, metric_id='M07', run_mode='DEVELOPMENT', source_type='DEVELOPMENT',
                        official=False, data_class='DEVELOPMENT', synthetic=any(c['source_synthetic'] for c in job['cases']),
                        files=[dict(path='code.zip', sha256=_sha(archive))])
        for name, raw in (('code.zip', archive), ('data_manifest.json', _encoded(manifest))):
            path = self._safe(folder / name)
            if path.exists():
                require(path.read_bytes() == raw, '보관 평가 입력 불일치')
            else:
                with path.open('xb') as output:
                    output.write(raw)
        config = deepcopy(self.config_provider())
        config.setdefault('integration_datasets', {})[dataset] = dict(run_mode='DEVELOPMENT', manifest=(folder / 'data_manifest.json').relative_to(self.root).as_posix())
        payload = dict(external_run_id=job['generation_id'], dataset_id=dataset, run_mode='DEVELOPMENT',
                       source_module='llm-selenium-validator', source_version='m07-development-v1', submitted_at=_now(),
                       dataset_manifest_sha256=_sha(_encoded(manifest)), counts=job['counts'], cases=job['cases'],
                       details=dict(generation_id=job['generation_id'], generated_by_llm=True,
                                    synthetic=manifest['synthetic'], archive_sha256=job['archive_sha256']))
        job['result'] = ingest(self.root, config, 'M07', payload)
        job['dataset_id'] = dataset

    def _work(self, identity, phase, run_lock, browser_lock):
        job = self._job(identity)
        try:
            self._generate(job) if phase == 'generate' else self._validate(job)
        except BaseException as exc:
            job.update(status='ERROR', completed_at=_now(), error=_masked(exc), result=None)
            self._save(job)
        finally:
            self._active = None
            if browser_lock:
                browser_lock.close()
            run_lock.close()

    def code(self, identity, case_id):
        job = self._job(identity)
        case = next((c for c in job['cases'] if c['case_id'] == case_id), None)
        require(case is not None, '코드 사례를 찾을 수 없습니다.')
        self._check(job, case)
        path = self._case_path(job, case, 'script.py')
        raw = path.read_bytes() if path.exists() else b''
        result = {'case': case, 'code': raw.decode('utf-8')}
        if job.get('code_source') == 'PREPARED' or job.get('meeting_protocol') is True and raw:
            digest = _sha(raw)
            expected = case.get('source_file_sha256') if job.get('code_source') == 'PREPARED' else case.get('code_sha256')
            result.update(code_base64=base64.b64encode(raw).decode('ascii'),
                          identity_verification=dict(verified=digest == expected,
                                                     source_sha256=expected, display_sha256=digest))
        return result

    def export_m04(self, identity, payload, manager):
        require(isinstance(payload, dict) and set(payload) == {'case_ids'}, '고정할 코드 목록이 필요합니다.')
        ids = payload['case_ids']
        require(isinstance(ids, list) and 1 <= len(ids) <= 10 and all(isinstance(x, str) for x in ids)
                and len(set(ids)) == len(ids), 'M04 고정 대상은 서로 다른 코드 1~10건입니다.')
        with self.lock:
            run_lock = self._global_lock()
            if not run_lock:
                raise EvaluationError('M07 작업이 실행 중입니다.', 'RUNNING')
            try:
                job = self._job(identity)
                require(job.get('source_kind') != 'RBEM_PREPARED_WORKFLOW' and job.get('meeting_protocol') is not True,
                        '직접 입력·준비 코드는 M07에서 검사하세요. M04 고정 등록에는 M03 원본 연결이 필요합니다.')
                require(job['status'] == 'GENERATED', 'M04 고정 대상은 실행 검사 전에 선택해야 합니다.')
                cases = [c for c in job['cases'] if c['case_id'] in ids]
                require(len(cases) == len(ids), '코드 사례를 찾을 수 없습니다.')
                requests = []
                for case in cases:
                    require(case['generation_status'] == 'PASS', '생성된 원본 코드가 필요합니다.')
                    self._check(job, case)
                    raw = self._case_path(job, case, 'script.py').read_bytes()
                    try:
                        tree = ast.parse(raw)
                    except (SyntaxError, ValueError, UnicodeError):
                        raise EvaluationError('문법 오류 코드가 포함되어 고정할 수 없습니다.') from None
                    selenium = any((isinstance(n, ast.Import) and any(a.name.split('.')[0] == 'selenium' for a in n.names))
                                   or (isinstance(n, ast.ImportFrom) and (n.module or '').split('.')[0] == 'selenium') for n in ast.walk(tree))
                    require(selenium and any(isinstance(n, ast.Assert) for n in ast.walk(tree))
                            and _scenario_declared(tree, case['scenario_id']),
                            'Selenium, 일치하는 SCENARIO_ID 및 assert가 포함된 코드가 필요합니다.')
                    requests.append(dict(filename=case['case_id'].lower() + '.py', python_base64=base64.b64encode(raw).decode('ascii'),
                                         scenario_id=case['scenario_id'], scenario_name=case['scenario_name'],
                                         m03_run_id=case['source_m03_run_id'], source_m07_generation_id=identity, source_m07_case_id=case['case_id']))
                scripts = [manager.register(request)['script'] for request in requests]
                job.setdefault('m04_exports', []).append(dict(fixed_at=_now(), case_ids=ids, script_ids=[s['script_id'] for s in scripts]))
                self._save(job)
                return dict(scripts=scripts, m04_url='/metrics/m04?mode=DEVELOPMENT')
            finally:
                run_lock.close()

    def artifact(self, identity, name):
        job = self._job(identity)
        require(name in {'report.json', 'log.jsonl', 'steps.csv', 'code.zip', 'screenshots.zip'}, '지원하지 않는 M07 파일입니다.')
        if name == 'screenshots.zip':
            from ..m04.store import verified_screenshots
            buffer = io.BytesIO()
            manifest = dict(generation_id=identity, run_mode='DEVELOPMENT', cases=[])
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                def entry(filename, raw):
                    info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, raw)
                for case in job['cases']:
                    folder = self._case_path(job, case, 'before.png').parent
                    for metadata, raw in verified_screenshots(case, folder):
                        entry(case['case_id'] + '/' + metadata['file'], raw)
                    fields = ('phase', 'file', 'sha256', 'policy', 'captured_at', 'status', 'reason')
                    manifest['cases'].append(dict(case_id=case['case_id'], scenario_id=case['scenario_id'],
                                                 screenshots=[{key: frame.get(key) for key in fields} for frame in case.get('screenshots', [])]))
                entry('screenshots.json', _encoded(manifest))
            return buffer.getvalue(), 'application/zip'
        if name == 'report.json':
            return _encoded(job), 'application/json; charset=utf-8'
        if name == 'log.jsonl':
            return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in job['logs']).encode('utf-8'), 'application/x-ndjson'
        if name == 'steps.csv':
            output = io.StringIO(newline='')
            fields = ('execution_id', 'case_id', 'scenario_id', 'record_type', 'sequence', 'action', 'target',
                      'expected_result', 'status', 'started_at', 'completed_at', 'duration_ms', 'failure_selector', 'error',
                      'independent_checks_passed', 'check_results')
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for case in job['cases']:
                records = [('business_step' if case.get('step_evidence_mode') == 'BUSINESS_STEPS' else 'action', step)
                           for step in case['steps']]
                records.extend(('action', step) for step in case.get('action_logs', []))
                for kind, step in records:
                    row = dict(step, execution_id=identity, case_id=case['case_id'], scenario_id=case['scenario_id'], record_type=kind)
                    writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value for key, value in row.items()})
            return output.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8'
        raw = self._safe(self._job_path(identity).parent / 'code.zip').read_bytes()
        require(_sha(raw) == job.get('archive_sha256'), '생성 원본 묶음 SHA-256 불일치')
        return raw, 'application/zip'

    def screenshot(self, identity, case_id, phase):
        from ..m04.store import verified_screenshots
        require(phase in {'before', 'after'}, '지원하지 않는 화면 근거 단계입니다.')
        job = self._job(identity)
        case = next((value for value in job['cases'] if value['case_id'] == case_id), None)
        require(case is not None, '화면 근거 사례를 찾을 수 없습니다.')
        folder = self._case_path(job, case, 'before.png').parent
        frames = verified_screenshots(case, folder)
        for metadata, raw in frames:
            if metadata['phase'] == phase:
                return raw, 'image/png'
        raise EvaluationError('이 단계의 마스킹 화면 근거가 없습니다.', 'NOT_FOUND')
