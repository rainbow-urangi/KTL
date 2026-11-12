"""Uploaded CSV -> unchanged candidate inference -> verified M03 inputs.

This module creates DEVELOPMENT evidence only. A worker-journal CSV does not
prove capture/tab boundaries; its learned process medoids are never labelled
as a capture execution view, business truth, or an executable test contract.
"""
from collections import defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import uuid

from .evaluators import EvaluationError, require
from .m01 import M01CsvStore
from .m01.upload import parse_csv


ANALYSIS_PATTERN = r'UPLOAD-ANALYSIS-[a-f0-9]{32}'
DIRECTORY = Path('data/development/uploaded_analysis')
VERSION = 'uploaded-csv-analysis-v1'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _path(root, relative):
    """Reject every symlink component, including trusted-store parent paths."""
    relative = Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts,
            '분석 경로는 프로젝트 내부 상대 경로여야 합니다.')
    current = root
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), '분석 입력·출력에 심볼릭 링크를 사용할 수 없습니다.')
    require(current.resolve().is_relative_to(root), '분석 경로가 프로젝트 범위를 벗어났습니다.')
    return current


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def _table(rows):
    if not rows:
        return b''
    fields = list(dict.fromkeys(key for row in rows for key in row))
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                         if isinstance(value, (dict, list)) else value for key, value in row.items()})
    return buffer.getvalue().encode('utf-8')


def _run_inference(streams, directory):
    # Import only on an explicit analysis call, not at web-server startup.
    from model.workflow_candidate_v1_3.src.infer_cli import candidate_identity
    from model.workflow_candidate_v1_3.src.artifacts import materialize, UPSTREAM
    from model.workflow_candidate_v1_3.src.infer import infer_events
    identity = candidate_identity()
    stage = directory / 'verified-artifacts'
    proof = materialize(UPSTREAM, stage)
    result = infer_events(streams, stage)
    return result, proof, identity


def _streams(rows):
    from model.workflow_candidate_v1.src.data import RAW_FIELDS, sanitize_raw, time_of
    require(all(field in rows[0] for field in RAW_FIELDS), '분석에 필요한 원본 이벤트 열이 없습니다.')
    groups, seen = defaultdict(list), set()
    for row in rows:
        require(bool(row['event_id'].strip()) and row['event_id'] not in seen,
                '분석 event_id는 비어 있지 않고 고유해야 합니다.')
        seen.add(row['event_id'])
        require(bool(row['session_id'].strip()), '분석 session_id가 필요합니다.')
        try:
            stamp = datetime.fromisoformat(row['event_time'].replace('Z', '+00:00'))
            require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
                    '분석 event_time에 시간대가 필요합니다.')
        except (ValueError, TypeError):
            raise EvaluationError('분석 event_time 형식을 확인하세요.', 'NOT_READY') from None
        event = sanitize_raw(row, 'uploaded_csv')
        groups[event['session_id']].append(event)
    # Only model streams use the inherited sorting policy. Original row order
    # remains intact in source_input.json and the immutable source copy.
    return [sorted(events, key=lambda event: (time_of(event), event['event_id']))
            for _, events in sorted(groups.items())], list(RAW_FIELDS)


def _forward_evidence(result, streams):
    evidence = result.get('forward_evidence')
    require(isinstance(evidence, dict) and evidence.get('completed') is True
            and evidence.get('evidence_type') == 'COMPLETED_TORCH_FORWARD_HOOKS'
            and type(evidence.get('boundary_forward_calls')) is int
            and evidence['boundary_forward_calls'] == len(streams)
            and type(evidence.get('representation_forward_calls')) is int
            and evidence['representation_forward_calls'] == len(streams)
            and evidence.get('input_stream_count') == len(streams)
            and evidence.get('input_event_count') == sum(map(len, streams)),
            '실제 모델 forward 완료 근거를 확인할 수 없습니다.')
    return deepcopy(evidence)


def _prepare_m03(root, directory, result, snapshot):
    from .m03_canonical_adapter import SOURCE_MODULE, SOURCE_VERSION
    models = result['tables']['process_models']
    indexed = {row['process_model_id']: row for row in models}
    require(len(indexed) == len(models), '분석 프로세스 모델 ID가 중복됐습니다.')
    definitions, represented, empty = [], set(), []
    # The M03 receipt binds both derived inputs and their original uploaded
    # byte/row lineage. These stay local to the subprocess adapter.
    files = [dict(path=name, sha256=_sha((directory / name).read_bytes()))
             for name in ('source.csv', 'source_input.json')]
    candidates = result.get('canonical')
    require(isinstance(candidates, list), '분석 canonical 배열을 확인하세요.')
    for canonical in candidates:
        require(isinstance(canonical, dict), '분석 canonical 형식을 확인하세요.')
        model_id = canonical.get('process_model_id')
        require(model_id in indexed and model_id not in represented,
                'canonical 프로세스 모델 대응이 고유하지 않습니다.')
        represented.add(model_id)
        if not canonical.get('procedures'):
            empty.append(model_id)
            continue
        model = indexed[model_id]
        require(model.get('mode') == 'DEVELOPMENT' and isinstance(model.get('canonical_instance_id'), str)
                and bool(model['canonical_instance_id'])
                and canonical.get('canonical_instance_id') == model['canonical_instance_id']
                and canonical.get('canonical_kind') == 'LEARNED_PROCESS_MEDOID',
                '학습 관측 대표의 모델·워크플로 대응을 확인하세요.')
        definitions.append((canonical, model))
    empty.extend(row['process_model_id'] for row in models if row['process_model_id'] not in represented)
    snapshot['counts'].update(canonical_count=len(definitions), empty_canonical_count=len(empty),
                              procedure_count=sum(len(c['procedures']) for c, _ in definitions))
    snapshot['empty_canonical_models'] = empty
    snapshot['empty_canonical_diagnostics'] = [dict(process_model_id=model_id,
        reason=indexed[model_id].get('canonical_status') or 'NO_NONEMPTY_CANONICAL',
        scope='LEARNED_PROCESS_MEDOID', excluded_from_generation=True)
        for model_id in empty]
    if not definitions:
        snapshot.update(status='NOT_READY', error_code='NO_NONEMPTY_CANONICAL',
                        error='생성 가능한 관측 절차 대표가 없습니다. 전체 분석 결과는 보관했습니다.')
        return
    if len(definitions) > 10:
        snapshot.update(status='NOT_READY', error_code='CANONICAL_SELECTION_REQUIRED',
                        error='관측 절차 대표가 10개를 초과합니다. 전체 분석 결과를 보관했으며 임의로 제외하지 않았습니다.')
        return
    units = []
    for index, (canonical, model) in enumerate(definitions, 1):
        relative = Path('m03') / f'model-{index:03d}'
        for name, raw in (('canonical_workflows.json', _encoded([canonical])),
                          ('process_models.csv', _table([model]))):
            _write(directory / relative / name, raw)
            files.append(dict(path=(relative / name).as_posix(), sha256=_sha(raw)))
        workflow = model['canonical_instance_id']
        units.append(dict(business_unit_id=f'UPLOAD-PM-{index:03d}', workflow_id=workflow,
                          business_name=f'업로드 관측 절차 대표 {index}',
                          start_screen='선택한 학습 관측 workflow의 첫 원본 절차',
                          end_condition='같은 workflow의 마지막 관측 절차까지 변환',
                          required_procedures=[f'원본 관측 절차 {step["order"]}: {step["action"]}'
                                               for step in canonical['procedures']],
                          scope='LEARNED_PROCESS_MEDOID',
                          scope_notice='모델이 선택한 관측 대표이며 업무 정답·전체 업무 완료·실행 조건을 뜻하지 않습니다.',
                          canonical_process_model_id=model['process_model_id'], canonical_instance_id=workflow,
                          canonical_input_path=(directory / relative / 'canonical_workflows.json').relative_to(root).as_posix(),
                          canonical_models_path=(directory / relative / 'process_models.csv').relative_to(root).as_posix()))
    manifest = dict(dataset_id='uploaded-analysis-' + snapshot['analysis_id'].split('-')[-1], synthetic=False,
                    source_run_id=snapshot['analysis_id'], workflow_ids=[unit['workflow_id'] for unit in units], files=files)
    path = directory / 'analysis_manifest.json'
    _write(path, _encoded(manifest))
    snapshot.update(input_manifest=path.relative_to(root).as_posix(),
                    input_manifest_sha256=_sha(path.read_bytes()),
                    m03_settings=dict(generator_mode='REAL', transport='SUBPROCESS',
                                      input_manifest=path.relative_to(root).as_posix(),
                                      source_module=SOURCE_MODULE, source_version=SOURCE_VERSION, business_units=units),
                    status='COMPLETED')


def analyze_upload(root, dataset_id, session=None):
    """Analyze every original row; session is the existing server ownership guard."""
    root = Path(root).resolve()
    require(isinstance(dataset_id, str) and re.fullmatch(r'[a-f0-9]{32}', dataset_id), 'CSV dataset ID 형식을 확인하세요.')
    source = _path(root, Path('data/development/m01_uploads') / dataset_id / 'source.csv')
    _path(root, Path('data/development/m01_uploads') / dataset_id / 'manifest.json')
    directory = _path(root, DIRECTORY / ('UPLOAD-ANALYSIS-' + uuid.uuid4().hex))
    directory.mkdir(parents=True, exist_ok=False)
    snapshot = dict(version=VERSION, analysis_id=directory.name, csv_dataset_id=dataset_id,
                    run_mode='DEVELOPMENT', official=False, official_pass=None, score=None, status='RUNNING', model_status='NOT_STARTED',
                    started_at=_now(), stage='SOURCE_VALIDATION', source_csv_sha256=None,
                    output_directory=directory.relative_to(root).as_posix(), input_manifest=None, m03_settings=None,
                    counts={}, forward_evidence=None, source_input=None, error=None, error_code=None)
    _write(directory / 'analysis-before.json', _encoded(snapshot))
    try:
        report = M01CsvStore(root, session=session).read(dataset_id, offset=0, limit=1)
        raw = source.read_bytes()
        expected = report['dataset']['sha256']
        require(_sha(raw) == expected, '검증 후 원본 CSV의 SHA가 변경됐습니다.')
        headers, rows = parse_csv(raw)
        from .m03_integration import _no_truth
        _no_truth({name: None for name in headers})
        snapshot['source_csv_sha256'] = expected
        snapshot['counts'] = dict(event_count=len(rows), session_count=len({row.get('session_id') for row in rows}))
        snapshot['source_input'] = dict(csv_dataset_id=dataset_id, path=source.relative_to(root).as_posix(),
            sha256=expected, byte_count=len(raw), row_count=len(rows), columns=headers,
            row_number_policy='data_row is one-based, physical_csv_row=data_row+1; original file order preserved',
            rows=[dict(data_row=index, physical_csv_row=index + 1, worker_ordinal=row.get('id', ''),
                       event_id=row.get('event_id', ''), session_id=row.get('session_id', ''), event_time=row.get('event_time', ''))
                  for index, row in enumerate(rows, 1)],
            capture_evidence_supplied=False,
            scope_notice='Uploaded CSV scope only; tab/frame/run continuity is not inferred.')
        _write(directory / 'source_input.json', _encoded(snapshot['source_input']))
        _write(directory / 'source.csv', raw)
        snapshot['stage'] = 'MODEL_INPUT_VALIDATION'
        streams, fields = _streams(rows)
        snapshot['model_input_fields'] = fields
        snapshot['stage'] = 'CANDIDATE_INFERENCE'
        result, proof, identity = _run_inference(streams, directory)
        require(_sha(source.read_bytes()) == expected, '모델 분석 중 원본 CSV의 SHA가 변경됐습니다.')
        snapshot['forward_evidence'] = _forward_evidence(result, streams)
        require(result.get('candidate_id') == 'workflow_candidate_v1_3' and result.get('official') is False
                and result.get('mode') == 'DEVELOPMENT', '분석 후보 모델 구분을 확인하세요.')
        snapshot['model_status'] = 'COMPLETED'
        snapshot['candidate_manifest_sha256'] = identity
        snapshot['stage'] = 'OUTPUT_STORAGE'
        result.update(input_provenance=dict(csv_dataset_id=dataset_id, csv_sha256=expected,
                                          source_input='source_input.json', capture_evidence_supplied=False),
                      artifact_proof=proof, candidate_manifest_sha256=identity)
        _write(directory / 'inference.json', _encoded(result))
        _write(directory / 'canonical_workflows.json', _encoded(result['canonical']))
        for name, table in result['tables'].items():
            require(re.fullmatch(r'[a-z_]+', name) and isinstance(table, list), '분석 출력 표 형식을 확인하세요.')
            _write(directory / 'tables' / (name + '.csv'), _table(table))
        snapshot['counts'].update(workflow_count=len(result['workflows']),
                                  process_model_count=len(result['tables']['process_models']))
        snapshot['stage'] = 'M03_INPUT_PREPARATION'
        _prepare_m03(root, directory, result, snapshot)
        if snapshot['status'] == 'COMPLETED':
            # Validate the same input contract used by the real generator without
            # invoking any generator, external HTTP endpoint, or model again.
            from .m03_integration import development_context
            development_context(root, apply_analysis_config({}, snapshot))
        require(_sha(source.read_bytes()) == expected, '분석 입력 준비 중 원본 CSV의 SHA가 변경됐습니다.')
    except ModuleNotFoundError:
        snapshot.update(status='NOT_READY', error_code='MODEL_DEPENDENCY_MISSING', error='현재 Python 환경에 분석 모델 의존성이 없습니다.')
    except EvaluationError as error:
        snapshot.update(status='NOT_READY' if error.status in {'NOT_READY', 'NOT_CONFIGURED', 'NOT_FOUND'} else 'ERROR',
                        error_code='ANALYSIS_VALIDATION_FAILED', error=str(error))
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        snapshot.update(status='ERROR', error_code=getattr(error, 'code', 'UPLOADED_ANALYSIS_FAILED'),
                        error=getattr(error, 'safe_reason', '업로드 CSV 분석을 완료하지 못했습니다.'), error_type=type(error).__name__)
    if snapshot['status'] != 'COMPLETED':
        snapshot['m03_settings'] = None
        snapshot['input_manifest'] = None
    if snapshot['model_status'] == 'NOT_STARTED':
        snapshot['model_status'] = 'ERROR'
    snapshot['completed_at'] = _now()
    snapshot['output_sha256'] = {path.relative_to(root).as_posix(): _sha(path.read_bytes())
                                 for path in sorted(directory.rglob('*')) if path.is_file()}
    _write(directory / 'snapshot.json', _encoded(snapshot))
    return snapshot


def apply_analysis_config(base, snapshot):
    """Request-scoped config; never write backend/config.json or a global binding."""
    require(isinstance(snapshot, dict) and snapshot.get('status') == 'COMPLETED'
            and isinstance(snapshot.get('m03_settings'), dict)
            and re.fullmatch(ANALYSIS_PATTERN, snapshot.get('analysis_id', '')),
            '완료된 업로드 분석 입력이 필요합니다.')
    config = deepcopy(base)
    config['m03'] = deepcopy(snapshot['m03_settings'])
    config.setdefault('adapters', {})['scenario_generation'] = [sys.executable, '-B', '-X', 'utf8', '-m', 'backend.m03_canonical_adapter']
    return config
