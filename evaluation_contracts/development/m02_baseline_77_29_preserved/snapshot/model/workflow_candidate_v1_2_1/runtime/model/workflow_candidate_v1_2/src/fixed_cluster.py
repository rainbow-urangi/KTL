"""Fixed DEVELOPMENT-only threshold; no candidate search or fallback relabeling."""
from collections import Counter
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score,davies_bouldin_score

def cluster(x,config):
    assert config['selection_on_inference'] is False
    labels=AgglomerativeClustering(n_clusters=config['n_clusters'],distance_threshold=config['distance_threshold'],affinity=config['affinity'],linkage=config['linkage']).fit_predict(x)
    k=len(set(labels));valid=1<k<len(labels)
    selected=dict(threshold=config['distance_threshold'],cluster_count=k,silhouette=float(silhouette_score(x,labels,metric='cosine')) if valid else None,dbi=float(davies_bouldin_score(x,labels)) if valid else None,cluster_sizes={int(k):int(v) for k,v in Counter(labels).items()})
    return labels,dict(mode='DEVELOPMENT',official_m06=False,selection='fixed historical DEVELOPMENT threshold; no search',selected=selected)
