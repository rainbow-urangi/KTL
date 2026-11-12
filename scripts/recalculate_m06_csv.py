"""Independent sklearn DBI calculation from exported coordinates, no model/GT imports."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def recalculate(path):
    import numpy as np
    import sklearn
    from sklearn.metrics import davies_bouldin_score
    path = Path(path)
    vectors, identities, summaries = {}, {}, []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row['record_type'] == 'workflow_coordinate':
            i, d = int(row['row_index']), int(row['dimension'])
            identity = (row['workflow_id'], row['cluster'])
            if i in identities and identities[i] != identity:
                raise ValueError('Inconsistent workflow identity/label')
            identities[i] = identity
            vector = vectors.setdefault(i, {})
            if d in vector:
                raise ValueError('Duplicate coordinate')
            value = float(row['value'])
            if not math.isfinite(value):
                raise ValueError('Nonfinite coordinate')
            vector[d] = value
        elif row['record_type'] == 'cluster_summary':
            summaries.append(row)
    if not vectors or sorted(vectors) != list(range(len(vectors))):
        raise ValueError('Missing/noncontiguous workflow rows')
    dimension = len(vectors[0])
    if not dimension or any(sorted(v) != list(range(dimension)) for v in vectors.values()):
        raise ValueError('Missing/inconsistent dimensions')
    if len({v[0] for v in identities.values()}) != len(vectors):
        raise ValueError('Duplicate workflow IDs')
    matrix = np.asarray([[vectors[i][d] for d in range(dimension)] for i in range(len(vectors))], dtype=np.float64)
    labels = [identities[i][1] for i in range(len(vectors))]
    score = float(davies_bouldin_score(matrix, labels))
    if len(summaries) != len(set(labels)) or {r['cluster'] for r in summaries} != set(labels):
        raise ValueError('Cluster summary mismatch')
    native = sum(float(r['max_ratio']) for r in summaries) / len(summaries)
    if not math.isfinite(native) or not math.isclose(score, native, rel_tol=1e-8, abs_tol=1e-8):
        raise ValueError('CSV summary/sklearn mismatch')
    return dict(status='PASS', csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), evidence_rows=len(rows),
                workflow_count=len(vectors), dimensions=dimension, cluster_count=len(set(labels)),
                sklearn_dbi=score, csv_native_dbi=native, absolute_difference=abs(score-native),
                target=1.0, operator='<=', threshold_met=score <= 1.0, official_pass=None,
                sklearn_version=sklearn.__version__, numpy_version=np.__version__)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence_csv')
    args = parser.parse_args()
    print(json.dumps(recalculate(args.evidence_csv), indent=2))
