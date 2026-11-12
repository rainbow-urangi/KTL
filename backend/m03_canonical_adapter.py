"""관측된 canonical 절차를 M03 JSON으로 옮기는 DEVELOPMENT 전용 adapter.

새 모델 추론·GPT·GT 후보 선택을 수행하지 않는다. stdin/stdout JSON 계약은
backend.evaluators.call_adapter에서 실행하는 로컬 argv adapter용이다.
"""
import csv
import hashlib
import io
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path

from .evaluators import EvaluationError, require
from .m03_integration import _no_truth, _project_path, nonempty


ROOT = Path(__file__).resolve().parents[1]
MAX_REQUEST_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_STEPS = 1000
SOURCE_MODULE = 'canonical-procedure-adapter'
SOURCE_VERSION = 'canonical-to-m03-v2-occurrences'
GENERATION_METHOD = 'DETERMINISTIC_CANONICAL_ADAPTER'
CANONICAL_SCHEMAS = {'workflow-canonical-1', 'workflow-canonical-1.1', 'workflow-canonical-1.2'}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'Duplicate canonical adapter JSON keys are prohibited')
        value[key] = item
    return value


def _json(raw):
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise EvaluationError('Canonical adapter requires finite UTF-8 JSON', 'ERROR') from None


def _entries(root, analysis):
    require(isinstance(analysis, dict), 'Verified analysis_input is required')
    entries = analysis.get('files')
    require(isinstance(entries, list) and 1 <= len(entries) <= 100,
            'Verified analysis_input files are required')
    result = {}
    for entry in entries:
        require(isinstance(entry, dict) and nonempty(entry.get('path')),
                'Analysis file path is required')
        value = entry['path']
        require(not Path(value).is_absolute(), 'Analysis paths must be project-relative')
        path = _project_path(root, value)
        relative = path.relative_to(root).as_posix()
        expected = entry.get('sha256')
        require(isinstance(expected, str) and re.fullmatch(r'[a-fA-F0-9]{64}', expected) is not None,
                'Analysis file SHA-256 is required')
        require(relative not in result, 'Duplicate analysis file paths are prohibited')
        result[relative] = (path, expected.lower())
    return result


def _select_path(root, entries, explicit, suffix, basename=None):
    if explicit is not None:
        require(nonempty(explicit), 'Canonical source selection path must be nonempty')
        relative = _project_path(root, explicit).relative_to(root).as_posix()
        require(relative in entries and Path(relative).suffix.lower() == suffix,
                'Selected canonical source must be a registered analysis file')
        return relative
    choices = [name for name in entries if Path(name).suffix.lower() == suffix
               and (basename is None or Path(name).name == basename)]
    require(len(choices) == 1, 'Select one unambiguous canonical source file explicitly')
    return choices[0]


def _read(root, entry):
    path, expected = entry
    _project_path(root, path.relative_to(root).as_posix())
    try:
        with path.open('rb') as source:
            raw = source.read(MAX_SOURCE_BYTES + 1)
    except OSError:
        raise EvaluationError('Registered canonical source cannot be read', 'ERROR') from None
    require(0 < len(raw) <= MAX_SOURCE_BYTES, 'Canonical source must be at most 4 MiB')
    require(hashlib.sha256(raw).hexdigest() == expected, 'Canonical source SHA-256 mismatch')
    return raw


def _models(raw):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
        fields = reader.fieldnames
        require(isinstance(fields, list) and len(set(fields)) == len(fields)
                and all(nonempty(field) for field in fields), 'Canonical model CSV headers must be unique')
        _no_truth({field: True if field.lower().replace('-', '_') == 'evaluation_only' else None
                   for field in fields})
        rows = list(reader)
    except (UnicodeError, csv.Error):
        raise EvaluationError('Canonical model metadata requires UTF-8 CSV', 'ERROR') from None
    require({'process_model_id', 'canonical_instance_id', 'mode'} <= set(fields),
            'Canonical model metadata requires model, instance and mode fields')
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
            'Canonical model CSV rows must match the headers')
    _no_truth(rows)
    return rows


def _procedure_lineage(procedure):
    lineage = {}
    for key in ('source_workflow_id', 'source_process_model_id', 'source_session_id'):
        if key in procedure:
            require(nonempty(procedure[key]), 'Canonical procedure lineage identifiers must be nonempty text')
            lineage[key] = procedure[key]
    if 'source_csv_rows' in procedure:
        rows = procedure['source_csv_rows']
        require(isinstance(rows, list) and bool(rows)
                and all(type(row) is int and row > 0 for row in rows),
                'Canonical procedure source rows must be positive integers')
        lineage['source_csv_rows'] = deepcopy(rows)
    return lineage


def generate_canonical(root, payload):
    """SHA 고정 원본과 사전 선택 ID만 사용한다. 입력·원본 파일은 수정하지 않는다."""
    root = Path(root).resolve()
    require(isinstance(payload, dict) and set(payload) == {
        'business_unit_id', 'workflow_id', 'business_definition', 'analysis_input'},
        'Canonical adapter request fields do not match the generation contract')
    _no_truth(payload)
    require(nonempty(payload.get('business_unit_id')) and nonempty(payload.get('workflow_id')),
            'Business and workflow IDs are required')
    definition = payload['business_definition']
    require(isinstance(definition, dict) and all(definition.get(key) == payload[key]
            for key in ('business_unit_id', 'workflow_id')), 'Business definition identity mismatch')
    model_id = definition.get('canonical_process_model_id')
    instance_id = definition.get('canonical_instance_id')
    require(nonempty(model_id) and nonempty(instance_id), 'Preselected canonical model and instance IDs are required')
    require(payload['workflow_id'] == instance_id, 'Workflow must equal the preselected canonical instance ID')
    entries = _entries(root, payload['analysis_input'])
    canonical_path = _select_path(root, entries, definition.get('canonical_input_path'), '.json')
    models_path = _select_path(root, entries, definition.get('canonical_models_path'), '.csv', 'process_models.csv')
    document = _json(_read(root, entries[canonical_path]))
    _no_truth(document)
    candidates = document if isinstance(document, list) else document.get('canonical') if isinstance(document, dict) else None
    require(isinstance(candidates, list) and bool(candidates) and all(isinstance(row, dict) for row in candidates),
            'Canonical source requires a nonempty canonical model array')
    selected = [row for row in candidates if row.get('process_model_id') == model_id]
    require(len(selected) == 1, 'Preselected canonical model must occur exactly once')
    canonical = selected[0]
    require(canonical.get('schema_version') in CANONICAL_SCHEMAS, 'Unsupported canonical source schema')
    if canonical['schema_version'] == 'workflow-canonical-1.2':
        require(canonical.get('canonical_kind') == 'CAPTURE_OBSERVED_SEQUENCE',
                'Canonical 1.2 must identify its capture observed sequence scope')
    models = [row for row in _models(_read(root, entries[models_path])) if row['process_model_id'] == model_id]
    require(len(models) == 1 and models[0]['canonical_instance_id'] == instance_id,
            'Preselected canonical instance does not match the registered model metadata')
    require(models[0]['mode'] == 'DEVELOPMENT', 'This canonical adapter accepts DEVELOPMENT sources only')
    procedures = canonical.get('procedures')
    require(isinstance(procedures, list) and 1 <= len(procedures) <= MAX_STEPS,
            'Canonical source requires 1..1000 observed procedures')
    steps = []
    node_semantics = {}
    occurrences = set()
    for index, procedure in enumerate(procedures, 1):
        require(isinstance(procedure, dict) and type(procedure.get('order')) is int
                and procedure['order'] == index, 'Canonical procedure order must already be continuous')
        require(nonempty(procedure.get('id')) and nonempty(procedure.get('action')),
                'Canonical procedure IDs and actions must be valid')
        node_id = procedure.get('node_id', procedure['id'])
        require(nonempty(node_id) and node_id == procedure['id'], 'Canonical graph node identity must preserve the original ID')
        occurrence_id = procedure.get('occurrence_id', 'OCC-' + str(index).zfill(4))
        require(nonempty(occurrence_id) and occurrence_id not in occurrences,
                'Canonical occurrence IDs must be valid and unique')
        occurrences.add(occurrence_id)
        target = procedure.get('target')
        require(isinstance(target, dict) and bool(target), 'Canonical target must be an object')
        target_text = json.dumps(target, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        require(nonempty(target_text), 'Canonical target exceeds the M03 text limit')
        evidence = procedure.get('evidence')
        require(isinstance(evidence, list) and bool(evidence) and all(nonempty(item) for item in evidence),
                'Observed canonical procedure evidence is required')
        if 'http_method' in procedure:
            require(isinstance(procedure['http_method'], str) and len(procedure['http_method']) <= 32,
                    'Canonical HTTP method must be a short string')
        lineage = _procedure_lineage(procedure)
        node_key = (lineage.get('source_process_model_id', model_id), node_id)
        signature = (procedure['action'], procedure.get('http_method'), target_text)
        require(node_key not in node_semantics or node_semantics[node_key] == signature,
                'Revisited canonical graph nodes must keep their action, target and method')
        node_semantics[node_key] = signature
        step = dict(id=procedure['id'], node_id=node_id, occurrence_id=occurrence_id,
                    order=procedure['order'], action=procedure['action'], target=target_text,
                    target_details=deepcopy(target), evidence=deepcopy(evidence))
        if 'http_method' in procedure:
            step['http_method'] = procedure['http_method']
        step.update(lineage)
        steps.append(step)
    sources = {name: entries[name][1] for name in (canonical_path, models_path)}
    identity = json.dumps(dict(adapter_version=SOURCE_VERSION, business_unit_id=payload['business_unit_id'], workflow_id=instance_id,
                               process_model_id=model_id, sources=sources), sort_keys=True, separators=(',', ':'))
    result = dict(business_unit_id=payload['business_unit_id'], workflow_id=instance_id,
                scenario_id='CANON-SCN-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24],
                status='SUCCESS', steps=steps, source_module=SOURCE_MODULE, source_version=SOURCE_VERSION,
                generation_method=GENERATION_METHOD, model_inference_during_generation=False,
                generated_by_llm=False, synthetic=False, official=False, data_class='DEVELOPMENT',
                source_canonical_schema=canonical['schema_version'], source_process_model_id=model_id,
                source_canonical_instance_id=instance_id, source_files_sha256=sources,
                target_representation='COMPACT_SORTED_JSON_TARGET_V1')
    for key in ('canonical_kind', 'source_workflow_ids', 'source_process_model_ids', 'source_session_ids',
                'source_csv_sha256', 'source_capture_manifest_sha256', 'capture_policy_sha256'):
        if key in canonical:
            result[key] = deepcopy(canonical[key])
    return result


def main(root=None):
    try:
        if root is None:
            configured_root = os.environ.get('KTL_RUNTIME_ROOT')
            if configured_root is not None:
                require(bool(configured_root.strip()), 'KTL_RUNTIME_ROOT must not be empty')
                root = Path(configured_root).resolve()
            else:
                root = ROOT
        else:
            root = Path(root).resolve()
        require(root.is_dir(), 'Canonical adapter runtime root must be an existing directory')
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        require(0 < len(raw) <= MAX_REQUEST_BYTES, 'Canonical adapter request must be at most 1 MiB')
        result = generate_canonical(root, _json(raw))
        sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
        return 0
    except (EvaluationError, OSError, ValueError, TypeError, UnicodeError, RecursionError):
        sys.stderr.write('M03 canonical adapter could not validate the request or registered source.\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
