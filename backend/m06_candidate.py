"""Measure persisted engine embeddings and labels only; never run inference/clustering."""
import hashlib
import json
import math
import platform
from pathlib import Path
from .evaluators import EvaluationError, M06Evaluator, csv_evidence, require, read_json
from .run_storage import save_run

DATASET = 'v1_2_1_unseen_m06_development'
BUNDLE = Path('data/development/current_site_unseen_validation_v1/m06_frozen_output')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(root):
    import numpy as np
    directory = Path(root) / BUNDLE
    manifest = read_json(directory / 'manifest.json')
    require(manifest['run_mode'] == 'DEVELOPMENT', 'Development bundle required')
    hashes = {str(BUNDLE / 'manifest.json'): sha(directory / 'manifest.json')}
    for name in ('predictions.json', 'workflow_embeddings.npy'):
        require(sha(directory / name) == manifest['files'][name]['sha256'], 'M06 frozen artifact hash mismatch: ' + name)
        hashes[str(BUNDLE / name)] = sha(directory / name)
    predictions = read_json(directory / 'predictions.json')
    matrix = np.load(directory / 'workflow_embeddings.npy', allow_pickle=False)
    ids = [row['workflow_instance_id'] for row in predictions['workflows']]
    labels = predictions['cluster_labels']
    require(matrix.ndim == 2 and matrix.shape[0] == len(ids) == len(labels), 'Embedding/workflow/label alignment mismatch')
    require(len(ids) == len(set(ids)) and all(isinstance(x, str) and x for x in ids), 'Unique workflow IDs required')
    return matrix.tolist(), labels, ids, hashes, manifest

def prepare(root):
    try:
        features, labels, ids, hashes, manifest = load(root)
        # Validate without accepting or tuning cluster assignments.
        _, _, details, _ = M06Evaluator().evaluate(features, labels)
        return {'status':'READY', 'dataset_id':DATASET, 'details':dict(details, workflow_count=len(ids),
            model_version=manifest['model_version'], feature_space='persisted workflow embedding',
            input_sha256=hashes, notice='DEVELOPMENT · 공식 시험성적 아님; inference/reclustering 없음')}
    except (OSError, ValueError, KeyError, TypeError, EvaluationError, ImportError) as exc:
        return {'status':'BLOCKED', 'dataset_id':DATASET, 'details':{'missing':[str(exc)]}, 'error':str(exc)}

def calculate(root):
    import numpy as np
    import sklearn
    from sklearn.metrics import davies_bouldin_score
    features, labels, ids, hashes, manifest = load(root)
    score, count, detail, summaries = M06Evaluator().evaluate(features, labels)
    reference = float(davies_bouldin_score(np.asarray(features, dtype=np.float64), labels))
    # sklearn pairwise Euclidean uses a dot-product identity; allow
    # absolute/relative 1e-8 roundoff, without rounding either DBI.
    tolerance = 1e-8 * max(1.0, abs(reference))
    require(abs(score-reference) <= tolerance, 'M06 sklearn cross-check mismatch')
    clusters = list(dict.fromkeys(labels))
    centroids = {k:[sum(v) / labels.count(k) for v in zip(*[f for f,l in zip(features,labels) if l == k])] for k in clusters}
    rows = []
    for i, (identifier, label, vector) in enumerate(zip(ids, labels, features)):
        for dimension, value in enumerate(vector):
            rows.append(dict(record_type='workflow_coordinate', row_index=i, workflow_id=identifier, cluster=label, dimension=dimension, value=value))
    for cluster, vector in centroids.items():
        for dimension, value in enumerate(vector):
            rows.append(dict(record_type='centroid_coordinate', cluster=cluster, dimension=dimension, value=value))
    scatter = {r['cluster']:r['scatter'] for r in summaries}
    for left in clusters:
        for right in clusters:
            if left != right:
                distance = math.dist(centroids[left], centroids[right])
                rows.append(dict(record_type='cluster_pair', cluster=left, other_cluster=right, distance=distance,
                    ratio=(scatter[left]+scatter[right])/distance))
    rows.extend(dict(record_type='cluster_summary', **r) for r in summaries)
    evidence = csv_evidence(rows)
    detail.update(workflow_count=count, model_version=manifest['model_version'], feature_space='persisted workflow embedding',
        sklearn_dbi=reference, sklearn_version=sklearn.__version__, numpy_version=np.__version__, python_version=platform.python_version(),
        cross_check_pass=True, cross_check_absolute_difference=abs(score-reference), cross_check_tolerance=tolerance,
        sklearn_input_dtype='float64 (same values as native evaluator)', singleton_cluster_count=sum(r['workflow_count']==1 for r in summaries),
        formula='Si=mean Euclidean distance to centroid; Mij=centroid distance; DBI=mean_i max_j((Si+Sj)/Mij)',
        measurement_count=1, row_alignment='NPY row i = predictions.workflows[i].workflow_instance_id = predictions.cluster_labels[i]',
        evidence_sha256=hashlib.sha256(evidence.encode('utf-8')).hexdigest(), evidence_record_count=len(rows),
        evidence_schema='long CSV: workflow_coordinate / centroid_coordinate / cluster_pair / cluster_summary',
        notice='DEVELOPMENT only; no inference, training, clustering, GT or official promotion', source_manifest=manifest)
    return dict(status='COMPLETED', score=score, sample_count=count, dataset_id=DATASET, source_type='DEVELOPMENT',
        evaluator_version='M06-frozen-engine-output-v1', input_sha256=hashes, details=detail), summaries, evidence

def run(root, config):
    try:
        result, summaries, evidence = calculate(root)
    except (OSError, ValueError, KeyError, TypeError, EvaluationError, ImportError) as exc:
        return save_run(Path(root), 'M06', 'DEVELOPMENT', config, dict(status='BLOCKED',score=None,sample_count=None,
            dataset_id=DATASET,source_type='DEVELOPMENT',error=str(exc),details={'missing':[str(exc)]}), [])
    result = save_run(Path(root), 'M06', 'DEVELOPMENT', config, result, summaries)
    directory = Path(root) / 'results/development' / result['run_id']
    (directory / 'evidence.csv').write_text(evidence, encoding='utf-8')
    return result
