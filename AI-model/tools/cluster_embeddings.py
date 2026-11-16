from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster case embeddings")
    parser.add_argument("--embeddings", default="")
    parser.add_argument("--index", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--method", choices=("auto", "hdbscan", "kmeans"), default="auto")
    parser.add_argument("--clusters", type=int, default=None, help="KMeans cluster count")
    parser.add_argument("--min-cluster-size", type=int, default=5)
    return parser.parse_args()


def cluster(embeddings: np.ndarray, args) -> tuple[np.ndarray, str]:
    if args.method in {"auto", "hdbscan"} and len(embeddings) >= args.min_cluster_size:
        try:
            import hdbscan

            labels = hdbscan.HDBSCAN(min_cluster_size=args.min_cluster_size).fit_predict(embeddings)
            return labels, "hdbscan"
        except ImportError:
            if args.method == "hdbscan":
                raise RuntimeError("hdbscan is not installed; use --method kmeans")
            print("[warning] hdbscan unavailable; falling back to KMeans")
    elif args.method == "hdbscan":
        raise ValueError(
            "HDBSCAN needs at least --min-cluster-size embedding rows"
        )

    try:
        from sklearn.cluster import KMeans
    except ImportError as exc:
        raise RuntimeError("Clustering requires either hdbscan or scikit-learn") from exc
    cluster_count = args.clusters or min(8, max(2, round(math.sqrt(len(embeddings)))))
    cluster_count = min(cluster_count, len(embeddings))
    labels = KMeans(n_clusters=cluster_count, random_state=42, n_init=10).fit_predict(embeddings)
    return labels, "kmeans"


def main() -> None:
    args = parse_args()
    model_dir = os.getenv("MODEL_DIR", "./artifacts/event_transformer_v0")
    embeddings_path = args.embeddings or os.path.join(model_dir, "case_embeddings.npy")
    index_path = args.index or os.path.join(model_dir, "case_embedding_index.json")
    output_path = Path(args.output or os.path.join(model_dir, "case_embedding_clusters.csv"))
    embeddings = np.load(embeddings_path)
    if embeddings.ndim != 2 or len(embeddings) == 0:
        raise ValueError("Embeddings must be a non-empty 2D array")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    if len(index) != len(embeddings):
        raise ValueError(
            f"Index/embedding size mismatch: {len(index)} != {len(embeddings)}"
        )
    labels, method = cluster(embeddings, args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=("case_id", "embedding_index", "cluster_id", "variant_id_existing"),
        )
        writer.writeheader()
        for position, (item, label) in enumerate(zip(index, labels)):
            writer.writerow(
                {
                    "case_id": item["case_id"],
                    "embedding_index": item.get("embedding_index", position),
                    "cluster_id": int(label),
                    "variant_id_existing": item.get("variant_id", ""),
                }
            )
    print(f"[saved] {output_path} ({method}, {len(set(labels.tolist()))} clusters)")


if __name__ == "__main__":
    main()
