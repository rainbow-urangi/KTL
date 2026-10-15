"""Recover historical preprocessing metadata; never train or run model inference.

Run from the repository root: python3 -B -m scripts.recover_v62_runtime
Only the reviewed, hash-pinned notebook's preprocessing definitions are executed.
"""
import ast
import hashlib
import json
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from model.v6_2.inference.bundle_metadata import read_bundle_metadata

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = "model/v6_2/reference/business_flow_extraction_deep_unsupervised_v6_2.ipynb"
BUNDLE = "model/v6_2/frozen/model_bundle.pt"
DATASET = "data/training/v6_2_source"
NOTEBOOK_SHA = "c53cc08dcab8ec5ddf758198422ecc5e3a1d5dbdda08b2d65a111af0fba7acf4"
BUNDLE_SHA = "b08696d705cb0ea5466bab70ae2de729bae33ba5a7cfa9bc2b6bbd8b28708774"
REFERENCE_SHA = {"events.csv": "1828ccf4b8ebf1b65b8e39ded66e174e7335c36b8725f44c38bc94be556f8c0f",
                 "sessions.csv": "d7e3bf8dcf425e498c3f98570832d31c362a415d6dc2150bdc549a5e26019bb2",
                 "tasks.csv": "6882983664c967021f7552adcb44195a0a880372e9e6e239e54a2a2da5719784"}
NUMERIC = ["log1p_delta_sec", "log1p_step_duration_ms", "log1p_api_latency_ms", "api_status_code_div_600"]
DEFINITIONS = {"safe_str", "url_path", "structural_api_family", "structural_page_path",
               "structural_title", "derive_worker_id", "build_event_text", "build_semantic_text",
               "Vocab", "prep", "temporal_split", "raw_num"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def notebook_namespace(root=ROOT):
    path = root / NOTEBOOK
    check(sha256(path) == NOTEBOOK_SHA, "검토된 reference notebook hash와 다릅니다")
    notebook = json.loads(path.read_text(encoding="utf-8"))
    tree = ast.parse("".join(notebook["cells"][7]["source"]))
    definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in DEFINITIONS]
    check({n.name for n in definitions} == DEFINITIONS, "preprocessing 정의 누락")
    namespace = {"pd": pd, "np": np, "Counter": Counter, "urlparse": urlparse}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), "<reviewed historical preprocessing>", "exec"), namespace)
    assignments = {}
    for cell in (3, 7):
        for node in ast.parse("".join(notebook["cells"][cell]["source"])).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try:
                    assignments[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return namespace, notebook, tree, assignments


def recover_once(root=ROOT):
    check(sha256(root / DATASET / "events.csv") == REFERENCE_SHA["events.csv"], "historical events hash 불일치; 새 CSV로 복구할 수 없습니다")
    ns, notebook, tree, constants = notebook_namespace(root)
    # Exactly the original CSV parser, dtype inference, sorting and per-stream split.
    raw = pd.read_csv(root / DATASET / "events.csv", encoding="utf-8-sig", low_memory=False)
    frame = ns["prep"](raw)
    train, valid = ns["temporal_split"](frame)
    vocabulary = {c: ns["Vocab"](train[c]).stoi for c in constants["cat_cols"]}
    structural = {c: ns["Vocab"](train[c]).itos for c in constants["STRUCTURAL_FIELDS"]}
    # Execute only the original numeric-statistics assignments, in their original order.
    numeric_nodes = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id in {"tr_num", "mu", "sd"}]
    check(len(numeric_nodes) == 3, "numeric statistics 원본 정의 누락")
    ns["trdf"] = train
    exec(compile(ast.Module(body=numeric_nodes, type_ignores=[]), "<historical numeric statistics>", "exec"), ns)
    stats = {"numeric_feature_order": NUMERIC, "mean": ns["mu"].tolist(), "std": ns["sd"].tolist(),
             "dtype": str(ns["tr_num"].dtype), "ddof": 0, "std_epsilon": 1e-6,
             "normalization": "(raw_num - mean) / std", "fit_scope": "historical per-stream training split only"}
    check(np.isfinite(ns["tr_num"]).all() and np.isfinite(ns["mu"]).all()
          and np.isfinite(ns["sd"]).all() and (ns["sd"] > 0).all(), "수치 통계가 유효하지 않습니다")
    split = {"event_count": len(frame), "stream_count": int(frame.stream_id.nunique()),
             "training_count": len(train), "validation_count": len(valid),
             "training_event_indices_sha256": hashlib.sha256(train.global_event_idx.to_numpy(dtype="<i8").tobytes()).hexdigest(),
             "validation_event_indices_sha256": hashlib.sha256(valid.global_event_idx.to_numpy(dtype="<i8").tobytes()).hexdigest()}
    return vocabulary, stats, structural, split, constants, notebook, tree


def build_sidecars(root=ROOT):
    source_paths = [BUNDLE, NOTEBOOK, "model/v6_2/frozen/run_manifest.json",
                    DATASET + "/events.csv", DATASET + "/sessions.csv"]
    if (root / DATASET / "tasks.csv").exists():
        source_paths.append(DATASET + "/tasks.csv")
    before = {p: sha256(root / p) for p in source_paths}
    check(before[BUNDLE] == BUNDLE_SHA, "승인 bundle hash와 다릅니다")
    for name, expected in REFERENCE_SHA.items():
        if DATASET + "/" + name in before:
            check(before[DATASET + "/" + name] == expected, f"historical {name} hash 불일치")
    bundle = read_bundle_metadata(root / BUNDLE)
    check(bundle["version"] == "v6.2", "bundle version 불일치")
    first = recover_once(root)
    second = recover_once(root)
    check(first[:4] == second[:4], "독립 복구 2회의 결과가 다릅니다")
    vocabs, stats, structural, split, cfg, notebook, tree = first
    checks = {}
    for name, mapping in vocabs.items():
        tensor = bundle["checkpoints"]["event_transformer.pt"]["model_state_dict"][f"cat.{name}.weight"]
        check(mapping.get("<PAD>") == 0 and mapping.get("<UNK>") == 1, "PAD/UNK 불일치")
        check(sorted(mapping.values()) == list(range(len(mapping))), "vocabulary ID 불일치")
        check(len(mapping) == tensor.shape[0], f"{name}: checkpoint shape 불일치")
        checks[name] = {"vocabulary_size": len(mapping), "checkpoint_shape": list(tensor.shape), "status": "passed"}
    check(structural == bundle["structural_vocabs"], "structural vocabulary 순서/값 불일치")
    check(structural == bundle["checkpoints"]["event_boundary_model.pt"]["structural_vocab"], "boundary vocabulary 불일치")
    raw_num = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "raw_num")
    # Inspect the ordered stack arguments directly, independent of AST walk order.
    stack = next(n for n in ast.walk(raw_num) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "stack")
    expressions = [ast.unparse(n) for n in stack.args[0].elts]
    check(expressions == ["np.log1p(frame['delta_sec'].values)", "np.log1p(frame['step_duration_ms'].values)",
                          "np.log1p(frame['api_latency_ms'].values)", "frame['api_status_code'].values / 600.0"], "numeric 순서 불일치")
    forward_tree = ast.parse("".join(notebook["cells"][9]["source"]))
    event_class = next(n for n in forward_tree.body if isinstance(n, ast.ClassDef) and n.name == "EventTransformer")
    forward = next(n for n in event_class.body if isinstance(n, ast.FunctionDef) and n.name == "forward")
    check(any(isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == "cat_cols"
              for n in ast.walk(forward)), "forward categorical 순서 확인 실패")
    check(list(vocabs) == cfg["cat_cols"] == ["event_type", "interaction_type", "element_tag", "api_method"], "categorical 순서 불일치")
    for key, variable in {"event_window": "EVENT_WINDOW", "event_stride": "EVENT_STRIDE",
                          "segment_window": "SEGMENT_WINDOW", "segment_stride": "SEGMENT_STRIDE",
                          "semantic_encoder": "SEMANTIC_MODEL_NAME", "semantic_weight": "SEMANTIC_WEIGHT"}.items():
        check(bundle["config"][key] == cfg[variable], f"notebook/bundle config 불일치: {key}")
    contract = {
        "model_version": "v6.2", "status": "historical_preprocessing_recovered",
        "inference_ready": False, "categorical_feature_order": cfg["cat_cols"], "numeric_feature_order": NUMERIC,
        "numeric_expressions": expressions, "structural_fields": cfg["STRUCTURAL_FIELDS"],
        "text_fields": [["EVT", "event_type"], ["INT", "interaction_type"], ["TAG", "element_tag"],
                        ["TEXT", "element_text"], ["LABEL", "associated_label"], ["API", "api_path"],
                        ["PAGE", "page_title"], ["PATH", "url_path(page_url)"], ["TESTID", "data_testid"]],
        "text_construction": "nonempty [TAG] value fields joined by one space; first 1200 characters",
        "max_text_bytes": cfg["MAX_TEXT_BYTES"], "byte_policy": "UTF-8 errors=ignore; truncate bytes; uint8 + 1; zero padding; int64",
        "event_window": cfg["EVENT_WINDOW"], "event_stride": cfg["EVENT_STRIDE"],
        "segment_window": cfg["SEGMENT_WINDOW"], "segment_stride": cfg["SEGMENT_STRIDE"],
        "semantic_model_name": cfg["SEMANTIC_MODEL_NAME"], "semantic_weight": cfg["SEMANTIC_WEIGHT"],
        "semantic_dim": bundle["config"]["semantic_dim"],
        "semantic_input_construction": {"fields": [["PAGE", "page_title"], ["LABEL", "associated_label"], ["TEXT", "element_text"]],
             "format": "TAG: value", "separator": " | ", "truncate_characters": 700, "prefix": "passage: ",
             "normalize_embeddings": True, "empty_text": "zero vector; encoder not called"},
        "semantic_revision_status": "unresolved", "semantic_revision": None, "tokenizer_revision": None,
        "PAD_policy": {"token": "<PAD>", "id": 0}, "UNK_policy": {"token": "<UNK>", "id": 1,
             "behavior": "unknown and empty categorical values map to UNK; never extend vocabulary"},
        "null_handling_policy": {"strings": "strip whitespace; None/NaN and case-insensitive nan,none,null,nat,[null] become empty",
             "numeric": "missing column or pd.to_numeric(errors=coerce) missing value becomes 0",
             "timestamps_observed": "pd.to_datetime(errors=coerce); invalid becomes NaT",
             "validator": "reject missing/invalid required timestamps; report numeric parse errors; allow nullable category values"},
        "timestamp_sorting_policy": {"initial": ["event_time_parsed", "id if present"], "kind": "stable",
             "global_event_idx": "0..N-1 after sort", "within_stream_split": ["event_time_parsed", "global_event_idx"],
             "timezone_policy": {"status": "unresolved", "reason": "reference code does not explicitly normalize timezone"}},
        "delta_sec_policy": "per-stream timestamp diff; clip lower=0; fillna=0 before training split",
        "training_split": {"ratio": 0.8, "groupby_sort": False,
             "cut": "max(1,min(n-1,int(n*0.8))) for n>=2; otherwise n", "usage": "historical recovery only"},
        "session_stream_identity_policy": {"status": "unresolved",
             "observed_priority": ["actor_key", "login_id", "user_id", "worker_id", "employee_id", "workflow_key.split('#W')[0]", "session:<session_id>", "worker_0"],
             "historical_events_user_id_present": False,
             "required_future_policy": "user_id only for higher-level trajectory; no local feature or stream identity",
             "session_mapping_observed": "session_id preferred over id; empty keys/users removed; duplicate key keep=last"},
        "input_data_policy": "evidence/enrichment/export only; excluded from model features",
        "ground_truth_policy": "evaluation only; excluded from all model inputs and recovery",
        "boundary_policy": {"status": "unresolved"}, "new_consensus_assignment_policy": {"status": "unresolved"},
        "schema_validation_policy": {"events_required": ["event_id", "session_id", "event_time", *cfg["cat_cols"], "element_text", "associated_label", "api_path"],
             "sessions_required": "user_id and either session_id or id", "tasks": "optional; no model features",
             "identity_nulls": "reject", "duplicate_event_id": "reject", "category_oov": "report only; map to UNK later",
             "note": "New input validation is stricter than the historical notebook for IDs and timestamps."},
    }
    check(before == {p: sha256(root / p) for p in source_paths}, "복구 중 source hash가 변경되었습니다")
    manifest = {
        "model_version": "v6.2", "runtime_format_version": 1,
        "source_bundle_path": BUNDLE, "source_bundle_sha256": before[BUNDLE],
        "reference_notebook_path": NOTEBOOK, "reference_notebook_sha256": before[NOTEBOOK],
        "reference_dataset_path": DATASET,
        "reference_dataset_role": "historical reference only; not a future training dataset",
        "reference_dataset_sha256": {Path(p).name: before[p] for p in source_paths if p.startswith(DATASET + "/")},
        "source_files_sha256": before, "generated_at": datetime.now(timezone.utc).isoformat(),
        "recovery_method": "Hash-pinned notebook preprocessing definitions and original tr_num/mu/sd assignments; two independent historical CSV reads and reconstructions",
        "statement": "This runtime metadata was reconstructed from the historical V6.2 reference dataset and reference notebook without model retraining.",
        "validation_status": "passed_for_deterministic_preprocessing_recovery", "inference_ready": False,
        "validation": {"categorical_checkpoint_shapes": checks, "structural_vocabulary_exact_match": True,
             "two_recoveries_identical": True, "numeric_feature_order_verified": True,
             "categorical_forward_order_verified": True, "historical_split": split,
             "original_numeric_stats_comparison": "UNRESOLVED: original feature_stats.json was not retained",
             "original_categorical_mapping_comparison": "UNRESOLVED: original categorical vocabulary files were not retained"},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "unresolved": ["semantic revision/tokenizer/local weights", "original training environment versions",
                       "new input stream identity policy", "new stream boundary calibration policy",
                       "new workflow consensus assignment policy"],
        "semantic_revision_status": "unresolved",
    }
    return {"categorical_vocabs.json": vocabs, "feature_stats.json": stats,
            "preprocessing_contract.json": contract, "runtime_manifest.json": manifest}


def main():
    output = ROOT / "model/v6_2/runtime"
    if output.exists():
        raise SystemExit("runtime 디렉터리가 이미 있습니다. 기존 metadata를 덮어쓰지 않습니다.")
    documents = build_sidecars()
    encoded = {name: (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
               for name, data in documents.items() if name != "runtime_manifest.json"}
    manifest = documents["runtime_manifest.json"]
    manifest["sidecar_sha256"] = {name: hashlib.sha256(content).hexdigest() for name, content in encoded.items()}
    encoded["runtime_manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    # All validations complete before the first output write. Manifest is the commit marker.
    output.mkdir()
    for name, content in encoded.items():
        with (output / name).open("xb") as handle:
            handle.write(content)
    print(json.dumps({"validation": manifest["validation"], "stats": documents["feature_stats.json"],
                      "vocabularies": documents["categorical_vocabs.json"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
