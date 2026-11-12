"""The sklearn keyword alias only; clustering geometry and selection are unchanged."""
from collections import Counter
import inspect
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score, davies_bouldin_score


def agglomerative(threshold, *, estimator=None):
    estimator = AgglomerativeClustering if estimator is None else estimator
    parameters = inspect.signature(estimator).parameters
    keyword = 'metric' if 'metric' in parameters else 'affinity' if 'affinity' in parameters else None
    if keyword is None:
        raise ValueError('Unsupported sklearn clustering distance interface')
    return estimator(n_clusters=None, distance_threshold=threshold, linkage='average', **{keyword: 'cosine'})


def cluster(embeddings, config):
    candidates, best = [], None
    for threshold in config['cluster_distance_thresholds']:
        labels = agglomerative(threshold).fit_predict(embeddings)
        counts = Counter(int(x) for x in labels)
        k = len(counts)
        valid = 1 < k < len(labels)
        sil = float(silhouette_score(embeddings, labels, metric='cosine')) if valid else None
        dbi = float(davies_bouldin_score(embeddings, labels)) if valid else None
        singleton = sum(n == 1 for n in counts.values()) / len(labels)
        objective = sil - 0.1 * singleton if valid else None
        record = dict(threshold=threshold, cluster_count=k, silhouette=sil, dbi=dbi,
                      singleton_fraction=singleton, objective=objective, cluster_sizes=dict(counts))
        candidates.append(record)
        if objective is not None and (best is None or objective > best[0]):
            best = (objective, labels, record)
    if best is None:
        labels = np.zeros(len(embeddings), dtype=int)
        chosen = dict(threshold=None, cluster_count=1, silhouette=None, dbi=None,
                      reason='No valid unsupervised threshold')
    else:
        _, labels, chosen = best
    return labels, dict(mode='DEVELOPMENT', official_m06=False,
                        selection='max cosine silhouette - 0.1 * singleton fraction; no BU metadata',
                        selected=chosen, candidates=candidates)
