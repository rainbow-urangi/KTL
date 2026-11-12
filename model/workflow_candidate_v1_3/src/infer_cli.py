"""Normal product command: strict artifacts -> actual inference -> capture view."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from .artifacts import UPSTREAM, materialize
from .infer import infer_capture
from .errors import ValidationError


def candidate_identity():
    package = Path(__file__).resolve().parents[1]
    repo = package.parents[1]
    raw = (package / 'manifest.json').read_bytes()
    manifest = json.loads(raw)
    for group in ('source_sha256', 'upstream_source_sha256'):
        for relative, expected in manifest[group].items():
            path = (repo / relative).resolve()
            if not path.is_relative_to(repo) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValidationError('CANDIDATE_SOURCE_HASH_MISMATCH', 'Candidate or inherited source hash mismatch')
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', required=True)
    parser.add_argument('--capture-manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--artifacts', default=str(UPSTREAM))
    parser.add_argument('--artifact-stage')
    args = parser.parse_args(argv)
    output = Path(args.output).absolute()
    stage = Path(args.artifact_stage).absolute() if args.artifact_stage else output.with_name(output.stem + '-verified-artifacts')
    if output.exists() or output.is_symlink():
        parser.error('Output must be a new file')
    state = {'stage': 'SOURCE_IDENTITY'}
    try:
        source_manifest_sha = candidate_identity()
        state['stage'] = 'ARTIFACT_REPRODUCTION'
        proof = materialize(args.artifacts, stage)
        result = infer_capture(args.events, args.capture_manifest, stage,
                               stage_callback=lambda phase: state.update(stage=phase))
        result['artifact_proof'] = proof
        result['candidate_manifest_sha256'] = source_manifest_sha
        state['stage'] = 'OUTPUT_STORAGE'
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        failure = dict(status='ERROR', stage=state['stage'], error_type=type(error).__name__,
                       failure_code=error.code if isinstance(error, ValidationError) else 'CANDIDATE_EXECUTION_ERROR',
                       reason=error.safe_reason if isinstance(error, ValidationError)
                       else 'Candidate execution failed without emitting raw input or exception values')
        sys.stderr.write(json.dumps(failure) + '\n')
        return 1
    print(json.dumps(dict(status='COMPLETED', candidate_id=result['candidate_id'],
                         output=str(output), policy_sha256=result['policy_sha256'],
                         workflow_count=len(result['workflows']),
                         process_model_count=len(result['tables']['process_models']),
                         capture_procedure_count=len(result['capture_view']['canonical']['procedures'])), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
