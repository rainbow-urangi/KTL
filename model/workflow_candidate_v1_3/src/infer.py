"""Actual unchanged neural inference with versioned postprocessing and provenance."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
import sklearn
from model.workflow_candidate_v1.src.data import sanitize_raw, time_of, sha
from model.workflow_candidate_v1.src.neural import load_model as load_encoder, predict as encode
from model.workflow_candidate_v1.src.analysis import represent, segments
from model.workflow_candidate_v1_1.src.representation import components, combine
from model.workflow_candidate_v1_2.src.neural import seed_all, load_model, predict
from model.workflow_candidate_v1_2.src.features import decisions
from .adapter import canonical_for_generator
from .capture_lineage import POLICY_PATH, capture_view, load_capture
from .compat import cluster
from .process_map import process_maps


def _forward(model, callback, streams, config):
    completed = []
    handle = model.register_forward_hook(lambda *_: completed.append(True))
    try:
        result = callback(model, streams, config)
    finally:
        handle.remove()
    if len(completed) != len(streams):
        raise ValueError('Neural forward evidence does not match input stream count')
    return result, len(completed)


def infer_events(streams, artifacts):
    art = Path(artifacts)
    manifest = json.loads((art / 'model_manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['artifact_sha256'].items():
        if sha(art / name) != expected:
            raise ValueError('Artifact hash mismatch: ' + name)
    cfg = json.loads((art / 'model_config.json').read_text(encoding='utf-8'))
    ecfg = json.loads((art / 'representation_encoder_config.json').read_text(encoding='utf-8'))
    rcfg = json.loads((art / 'representation_config.json').read_text(encoding='utf-8'))
    if not streams or any(not stream for stream in streams):
        raise ValueError('Nonempty event streams are required')
    seed_all(cfg['seed'])
    boundary = load_model(art / 'model.pt', cfg)
    output, boundary_calls = _forward(boundary, predict, streams, cfg)
    probabilities = [p for p, _ in output]
    workflows = segments(streams, decisions(probabilities, streams, cfg), probabilities)
    encoder = load_encoder(art / 'representation_encoder.pt', ecfg)
    encoded, encoder_calls = _forward(encoder, encode, streams, ecfg)
    hidden = [h for _, h in encoded]
    existing, _ = represent(workflows, streams, hidden, ecfg)
    blocks, _ = components(workflows, streams, hidden, existing, rcfg)
    vectors = combine(blocks, rcfg['candidates']['C_full'])
    if len(workflows) > 1:
        labels, diagnostic = cluster(vectors, dict(ecfg, cluster_distance_thresholds=rcfg['cluster_distance_thresholds']))
    else:
        labels = np.zeros(1, dtype=int)
        diagnostic = {'selected': {'cluster_count': 1, 'silhouette': None, 'dbi': None}}
    tables = process_maps(workflows, labels, streams, vectors)
    canonical = [canonical_for_generator(tables, model['process_model_id']) for model in tables['process_models']]
    return dict(candidate_id='workflow_candidate_v1_3', base_model_id='workflow_candidate_v1_2',
        mode='DEVELOPMENT', official=False, offline=True, workflows=workflows, cluster_labels=labels.tolist(),
        clustering=diagnostic, tables=tables, canonical=[item for item in canonical if item is not None],
        policy_sha256=hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest(),
        forward_evidence=dict(completed=True, evidence_type='COMPLETED_TORCH_FORWARD_HOOKS',
            boundary_forward_calls=boundary_calls, representation_forward_calls=encoder_calls,
            input_stream_count=len(streams), input_event_count=sum(map(len, streams)),
            boundary_weight_sha256=sha(art / 'model.pt'), representation_weight_sha256=sha(art / 'representation_encoder.pt'),
            device=str(next(boundary.parameters()).device), sklearn_version=sklearn.__version__, retrained=False))


def infer_capture(csv_path, manifest_path, artifacts, *, stage_callback=None):
    mark = stage_callback if stage_callback is not None else lambda _: None
    mark('CAPTURE_VALIDATION')
    capture = load_capture(csv_path, manifest_path)
    sessions = defaultdict(list)
    for raw in capture['rows']:
        event = sanitize_raw(raw, 'raw_input')
        sessions[event['session_id']].append(event)
    # This is exactly the old model entrypoint's ordering. Capture-view ordering is separate.
    streams = [sorted(events, key=lambda e: (time_of(e), e['event_id'])) for _, events in sorted(sessions.items())]
    mark('MODEL_ANALYSIS')
    result = infer_events(streams, artifacts)
    mark('CAPTURE_COMPOSITION')
    result['capture_view'] = capture_view(capture, result)
    result['input_provenance'] = dict(csv_path=capture['csv_path'], csv_sha256=capture['csv_sha256'],
        capture_manifest_path=capture['capture_manifest_path'], capture_manifest_sha256=capture['capture_manifest_sha256'])
    return result
