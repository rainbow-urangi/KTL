"""서버가 보관한 M03 원생성과 평가 정답의 사전 존재를 연결한다."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .evaluators import EvaluationError, require
from .m03_reference import MAX_REFERENCE_BYTES, _safe_path, _timestamp


ORIGIN_ID = re.compile(r'M03-GEN-[0-9a-f]{32}')
MAX_RECEIPT_BYTES = 4 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def _folder(root, identity):
    require(isinstance(identity, str) and ORIGIN_ID.fullmatch(identity), 'Invalid M03 origin_generation_id')
    root = Path(root).resolve()
    path = root / 'results/m03_generations' / identity
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        require(not current.is_symlink() and current.resolve() == current, 'Linked M03 origin paths are prohibited')
    return path


def _json(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_RECEIPT_BYTES + 1)
        require(len(raw) <= MAX_RECEIPT_BYTES, 'M03 origin evidence exceeds size limit')
        value = json.loads(raw.decode('utf-8'))
        require(isinstance(value, dict), 'M03 origin evidence must be an object')
        return value, raw
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise EvaluationError('Stored M03 origin evidence cannot be read', 'ERROR') from None


def _reference_snapshot(root, config, dataset_id):
    """내용을 모델에 전달하지 않고 생성 시작 전에 등록된 정답 bytes의 SHA만 고정한다."""
    registry = config.get('m03_evaluation_references', {})
    require(isinstance(registry, dict), 'm03_evaluation_references must be an object')
    entry = registry.get(dataset_id)
    if entry is None:
        return None
    require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'}, 'M03 reference registration requires path and sha256')
    path, relative = _safe_path(root, entry['path'])
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_REFERENCE_BYTES + 1)
    except OSError:
        raise EvaluationError('Registered M03 reference cannot be snapshotted', 'ERROR') from None
    require(0 < len(raw) <= MAX_REFERENCE_BYTES, 'M03 reference exceeds snapshot size limit')
    actual = hashlib.sha256(raw).hexdigest()
    require(isinstance(entry['sha256'], str) and actual == entry['sha256'].lower(), 'M03 reference snapshot SHA-256 mismatch')
    return dict(path=relative, sha256=actual)


def _dataset_snapshot(root, config, dataset_id, mode):
    if dataset_id is None:
        return None
    registered = config.get('integration_datasets', {}).get(dataset_id)
    require(isinstance(registered, dict) and registered.get('run_mode') == mode, 'M03 generation dataset is not registered for mode')
    path, relative = _safe_path(root, registered.get('manifest'))
    manifest, raw = _json(path)
    require(manifest.get('dataset_id') == dataset_id, 'M03 generation dataset ID mismatch')
    official = (mode == 'OFFICIAL' and manifest.get('source_type') == 'OFFICIAL'
                and manifest.get('run_mode') == 'OFFICIAL' and manifest.get('approved_for_official') is True
                and manifest.get('synthetic') is not True and manifest.get('official') is not False)
    entries = manifest.get('files')
    require(isinstance(entries, (dict, list)) and bool(entries), 'M03 generation dataset input hashes required')
    input_hashes = {}
    for entry in entries.values() if isinstance(entries, dict) else entries:
        require(isinstance(entry, dict) and isinstance(entry.get('path'), str), 'Invalid M03 generation input entry')
        source = (Path(root).resolve() if isinstance(entries, dict) else path.parent) / entry['path']
        require(source.is_relative_to(Path(root).resolve()), 'M03 generation input escaped project')
        checked, name = _safe_path(root, source.relative_to(Path(root).resolve()).as_posix())
        try:
            digest = hashlib.sha256()
            with checked.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1048576), b''):
                    digest.update(chunk)
        except OSError:
            raise EvaluationError('M03 generation input cannot be read', 'ERROR') from None
        actual = digest.hexdigest()
        require(actual == entry.get('sha256'), 'M03 generation dataset input SHA-256 mismatch')
        require(name not in input_hashes, 'Duplicate M03 generation input path')
        input_hashes[name] = actual
    return dict(path=relative, sha256=hashlib.sha256(raw).hexdigest(), official_input=official,
                input_files_sha256=input_hashes)


def begin_generation(root, config, request, analysis_input=None):
    identity = 'M03-GEN-' + uuid.uuid4().hex
    dataset_id = request.get('dataset_id')
    if dataset_id is not None:
        require(isinstance(dataset_id, str) and bool(dataset_id.strip()) and len(dataset_id) <= 256, 'M03 generation dataset_id required')
    mode = request.get('run_mode', 'DEVELOPMENT')
    dataset = _dataset_snapshot(root, config, dataset_id, mode)
    if dataset and dataset['official_input']:
        files = analysis_input.get('files', []) if isinstance(analysis_input, dict) else []
        submitted = {entry.get('path'): entry.get('sha256') for entry in files if isinstance(entry, dict)}
        dataset['official_input'] = bool(files and len(submitted) == len(files)
                                         and submitted == dataset['input_files_sha256'])
        if dataset['official_input']:
            analysis_path, _ = _safe_path(root, analysis_input.get('manifest_path'))
            _, analysis_raw = _json(analysis_path)
            require(hashlib.sha256(analysis_raw).hexdigest() == analysis_input.get('manifest_sha256'),
                    'M03 original analysis manifest SHA-256 mismatch')
    snapshot = _reference_snapshot(root, config, dataset_id) if dataset_id else None
    receipt = dict(origin_generation_id=identity, schema_version='m03-generation-origin-v1',
                   started_at=datetime.now(timezone.utc).isoformat(), dataset_id=dataset_id,
                   business_unit_id=request['business_unit_id'], workflow_id=request['workflow_id'],
                   run_mode=mode, generator_mode=request.get('generator_mode', 'MOCK'),
                   dataset=dataset, reference_at_generation=snapshot,
                   analysis_input=analysis_input, status='STARTED')
    folder = _folder(root, identity)
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / 'started.json').open('xb') as output:
        output.write(encoded(receipt))
    return receipt


def complete_generation(root, receipt, scenario):
    scenario['origin_generation_id'] = receipt['origin_generation_id']
    raw = encoded(scenario)
    require(len(raw) <= MAX_RECEIPT_BYTES, 'M03 generation snapshot exceeds size limit')
    folder = _folder(root, receipt['origin_generation_id'])
    with (folder / 'response.json').open('xb') as output:
        output.write(raw)
    completed = dict(receipt, status='COMPLETED', completed_at=datetime.now(timezone.utc).isoformat(),
                     response_sha256=hashlib.sha256(raw).hexdigest(),
                     response_serialization='CANONICAL_JSON_UTF8_SORTED_V1')
    with (folder / 'receipt.json').open('xb') as output:
        output.write(encoded(completed))
    return scenario


def fail_generation(root, receipt):
    folder = _folder(root, receipt['origin_generation_id'])
    failed = dict(receipt, status='ERROR', completed_at=datetime.now(timezone.utc).isoformat())
    with (folder / 'receipt.json').open('xb') as output:
        output.write(encoded(failed))


def generate_recorded(root, config, payload):
    from .m03_integration import _real_input, generate, nonempty
    require(isinstance(payload, dict) and set(payload) <= {
        'business_unit_id', 'workflow_id', 'run_mode', 'generator_mode', 'dataset_id'}, 'Unsupported generation request field')
    require(all(nonempty(payload.get(key)) for key in ('business_unit_id', 'workflow_id')), 'M03 generation business/workflow IDs required')
    mode = payload.get('run_mode', 'DEVELOPMENT')
    engine = payload.get('generator_mode', 'MOCK')
    require(isinstance(mode, str) and mode in {'DEVELOPMENT', 'REFERENCE', 'OFFICIAL'}, 'Invalid generation mode')
    require(isinstance(engine, str) and engine in {'MOCK', 'REAL'}, 'Invalid generator mode')
    require(mode != 'OFFICIAL' or (engine == 'REAL' and nonempty(payload.get('dataset_id'))),
            'Official M03 generation requires REAL and a registered dataset_id')
    verified_real_input = _real_input(Path(root).resolve(), config) if engine == 'REAL' else None
    receipt = begin_generation(root, config, payload, verified_real_input[1] if verified_real_input is not None else None)
    try:
        result = generate(root, config, {key: value for key, value in payload.items() if key != 'dataset_id'},
                          verified_real_input=verified_real_input)
        if mode == 'OFFICIAL':
            require(result.get('official') is not False and result.get('data_class') not in {'DEVELOPMENT', 'REFERENCE'},
                    'Development generator output cannot become official M03 evidence')
            require(receipt.get('dataset', {}).get('official_input') is True,
                    'Official M03 generation inputs are not bound to the approved dataset')
        return complete_generation(root, receipt, result)
    except (EvaluationError, OSError, ValueError) as exc:
        fail_generation(root, receipt)
        if isinstance(exc, EvaluationError):
            exc.origin_generation_id = receipt['origin_generation_id']
            raise
        raise EvaluationError('Unable to preserve M03 generation evidence. Origin ID: ' + receipt['origin_generation_id'], 'ERROR') from None


def assess_origins(root, payload, reference, reference_hashes, dataset_manifest_sha256):
    checks = []
    identities = []
    for scenario in payload['scenarios']:
        identity = scenario.get('origin_generation_id')
        if identity is None:
            checks.append(dict(business_unit_id=scenario['business_unit_id'], origin_generation_id=None,
                               official_eligible=False, reason='NO_SERVER_GENERATION_RECEIPT'))
            continue
        folder = _folder(root, identity)
        receipt, _ = _json(folder / 'receipt.json')
        started_receipt, _ = _json(folder / 'started.json')
        require(all(receipt.get(key) == value for key, value in started_receipt.items() if key != 'status'),
                'M03 original generation start evidence changed')
        original, raw = _json(folder / 'response.json')
        require(receipt.get('origin_generation_id') == identity and receipt.get('status') == 'COMPLETED', 'M03 generation receipt is not completed')
        require(receipt.get('response_sha256') == hashlib.sha256(raw).hexdigest()
                and original == scenario and encoded(scenario) == raw, 'M03 original generation snapshot SHA-256 mismatch')
        require(receipt.get('business_unit_id') == scenario['business_unit_id']
                and receipt.get('workflow_id') == scenario.get('workflow_id'), 'M03 original generation identity mismatch')
        bound_dataset = receipt.get('dataset_id') is not None
        require(not bound_dataset or receipt.get('dataset_id') == payload['dataset_id'], 'M03 original generation dataset mismatch')
        dataset = receipt.get('dataset') or {}
        require(not bound_dataset or dataset.get('sha256') == dataset_manifest_sha256, 'M03 original generation dataset manifest changed')
        started = _timestamp(receipt.get('started_at'), 'M03 original generation started_at')
        require(started <= _timestamp(receipt.get('completed_at'), 'M03 original generation completed_at'),
                'M03 original generation time order mismatch')
        snapshot = receipt.get('reference_at_generation')
        same_reference = bool(snapshot and reference_hashes.get(snapshot.get('path')) == snapshot.get('sha256'))
        predates = bool(reference and _timestamp(reference['fixed_at'], 'M03 reference fixed_at') <= started)
        real = (receipt.get('generator_mode') == 'REAL' and receipt.get('run_mode') == 'OFFICIAL'
                and scenario.get('generator_mode') == 'REAL' and scenario.get('synthetic') is False
                and scenario.get('official') is not False and scenario.get('data_class') not in {'DEVELOPMENT', 'REFERENCE'})
        eligible = bool(same_reference and predates and real and dataset.get('official_input') is True)
        previous = any((folder / 'evaluations').glob('*.json'))
        checks.append(dict(business_unit_id=scenario['business_unit_id'], origin_generation_id=identity,
                           original_started_at=receipt['started_at'], original_completed_at=receipt['completed_at'],
                           original_response_sha256=receipt['response_sha256'], reference_sha256_at_generation=snapshot.get('sha256') if snapshot else None,
                           reference_preexisted=bool(same_reference and predates), evaluated_before=previous,
                           official_eligible=eligible, reason='PREEXISTING_REFERENCE_BOUND' if eligible else 'POSTHOC_OR_NONOFFICIAL_ORIGIN'))
        identities.append(identity)
    eligible = bool(checks and all(item['official_eligible'] for item in checks))
    classification = ('ORIGINAL_GENERATION_EVALUATION' if eligible and not any(item.get('evaluated_before') for item in checks)
                      else 'RE_EVALUATION_WITH_PREEXISTING_REFERENCE' if eligible else 'POSTHOC_REEVALUATION')
    return dict(official_eligible=eligible, classification=classification,
                submitted_at_role='EVALUATION_RECEIVED_TIME_ONLY', origins=checks), identities


def record_assessment(root, identities, result):
    for identity in identities:
        folder = _folder(root, identity) / 'evaluations'
        require(not folder.is_symlink(), 'Linked M03 assessment paths are prohibited')
        folder.mkdir(exist_ok=True)
        path = folder / (result['run_id'] + '.json')
        with path.open('xb') as output:
            output.write(encoded(dict(run_id=result['run_id'], classification=result['details']['generation_provenance']['classification'],
                                      official_eligible=result['details']['official_eligible'], completed_at=result['completed_at'])))
