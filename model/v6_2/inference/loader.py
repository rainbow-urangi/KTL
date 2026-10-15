"""Verify runtime provenance only. No weight loading, forward pass or inference."""
import hashlib
import json
import math
from pathlib import Path

from .bundle_metadata import read_bundle_metadata

ROOT = Path(__file__).resolve().parents[3]
SIDECARS = {"categorical_vocabs.json", "feature_stats.json", "preprocessing_contract.json"}


class RuntimeMetadataError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RuntimeMetadataError(message)


def load_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(value, dict), f"JSON 객체가 필요합니다: {path.name}")
        return value
    except (OSError, ValueError) as exc:
        raise RuntimeMetadataError(f"metadata 읽기 실패: {path.name}: {exc}") from exc


def checked_path(root, relative):
    require(isinstance(relative, str) and relative, "유효한 상대 경로가 필요합니다")
    path = (root / relative).resolve()
    require(not Path(relative).is_absolute() and path.is_relative_to(root), "저장소 외부 경로는 허용하지 않습니다")
    require(path.is_file(), f"필수 파일이 없습니다: {relative}")
    return path


def verify_hash(path, expected):
    require(isinstance(expected, str) and len(expected) == 64, "SHA-256 metadata 누락")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"SHA-256 불일치: {path.name}")


def load_runtime(root=ROOT):
    root = Path(root).resolve()
    directory = "model/v6_2/runtime/"
    manifest = load_json(checked_path(root, directory + "runtime_manifest.json"))
    try:
        require(manifest["model_version"] == "v6.2" and manifest["runtime_format_version"] == 1, "runtime version 불일치")
        require(manifest["validation_status"] == "passed_for_deterministic_preprocessing_recovery", "검증되지 않은 runtime metadata")
        require(manifest["inference_ready"] is False, "이 loader는 preprocessing metadata만 지원합니다")
        sources = manifest["source_files_sha256"]
        require(isinstance(sources, dict), "source hashes 누락")
        for label in ("source_bundle", "reference_notebook"):
            path = manifest[label + "_path"]
            require(sources.get(path) == manifest[label + "_sha256"], "provenance hash 필드 불일치")
        dataset = manifest["reference_dataset_path"]
        require({"events.csv", "sessions.csv"} <= manifest["reference_dataset_sha256"].keys(), "reference dataset hashes 누락")
        for name, expected in manifest["reference_dataset_sha256"].items():
            require(name in {"events.csv", "sessions.csv", "tasks.csv"}, "지원하지 않는 reference 파일")
            require(sources.get(dataset + "/" + name) == expected, "reference dataset hash 필드 불일치")
        for relative, expected in sources.items():
            verify_hash(checked_path(root, relative), expected)
        bundle = read_bundle_metadata(checked_path(root, manifest["source_bundle_path"]))
        require(bundle["version"] == manifest["model_version"], "bundle/runtime version 불일치")
        require(set(manifest["sidecar_sha256"]) == SIDECARS, "필수 sidecar hash 목록 불일치")
        data = {}
        for name in SIDECARS:
            path = checked_path(root, directory + name)
            verify_hash(path, manifest["sidecar_sha256"][name])
            data[name] = load_json(path)
        contract = data["preprocessing_contract.json"]
        stats = data["feature_stats.json"]
        vocab = data["categorical_vocabs.json"]
        require(contract["model_version"] == "v6.2", "contract version 불일치")
        required_contract = {"categorical_feature_order", "numeric_feature_order", "text_fields", "structural_fields",
                            "max_text_bytes", "event_window", "event_stride", "segment_window", "segment_stride",
                            "semantic_model_name", "semantic_weight", "semantic_input_construction", "PAD_policy",
                            "UNK_policy", "null_handling_policy", "timestamp_sorting_policy", "session_stream_identity_policy"}
        require(required_contract <= contract.keys(), "필수 preprocessing contract 누락")
        require(list(vocab) == contract["categorical_feature_order"], "categorical ordering 불일치")
        for name, mapping in vocab.items():
            require(mapping.get("<PAD>") == 0 and mapping.get("<UNK>") == 1, "PAD/UNK ID 불일치")
            require(all(type(v) is int for v in mapping.values()) and sorted(mapping.values()) == list(range(len(mapping))), "vocabulary ID 불일치")
            require(len(mapping) == manifest["validation"]["categorical_checkpoint_shapes"][name]["checkpoint_shape"][0], "checkpoint shape 불일치")
            require(len(mapping) == bundle["checkpoints"]["event_transformer.pt"]["model_state_dict"][f"cat.{name}.weight"].shape[0], "실제 checkpoint shape 불일치")
        require(stats["numeric_feature_order"] == contract["numeric_feature_order"] and len(stats["numeric_feature_order"]) == 4, "numeric ordering 불일치")
        for name in ("mean", "std"):
            require(len(stats[name]) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in stats[name]), "수치 통계 누락 또는 비유한 값")
        require(all(v > 0 for v in stats["std"]), "std는 양수여야 합니다")
        require(contract["semantic_revision_status"] == manifest["semantic_revision_status"], "semantic status 불일치")
        return {"manifest": manifest, "vocabularies": vocab, "stats": stats, "contract": contract,
                "status": "metadata_verified", "inference_ready": False}
    except (KeyError, TypeError, AttributeError) as exc:
        raise RuntimeMetadataError(f"필수 runtime metadata 누락 또는 형식 오류: {exc}") from exc
