"""Create pre-comparison DEVELOPMENT snapshot; no GT/evaluator access."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.business_process_serializer import serialize, canonical_bytes

def verified(path, digest):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Frozen provenance input hash mismatch")
    return json.loads(data)

def main(destination, occurrences, occurrence_sha256, predictions, prediction_sha256):
    # Explicit expected hashes must come from the independent precomparison audit.
    occurrence_values = verified(occurrences, occurrence_sha256)
    verified(predictions, prediction_sha256)
    inputs = ["data/development/current_site_unseen_validation_v1/m02_frozen_output/process_models.json",
              "data/development/current_site_unseen_validation_v1/m02_frozen_output/process_nodes.json"]
    values = [json.loads((ROOT / p).read_text()) for p in inputs]
    result = serialize(*values, occurrence_values)
    data = canonical_bytes(result)
    files = inputs + ["backend/business_process_serializer.py", "docs/agents/M02_BUSINESS_SERIALIZER_CONTRACT.md", "scripts/freeze_m02_business_serializer.py"]
    manifest = {"mode": "DEVELOPMENT", "official": False, "stage": "PRE_GT_COMPARISON",
        "verification": "PENDING_INDEPENDENT_VERIFICATION", "score_computed": False,
        "semantic_readiness": result["semantic_readiness"],
        "files": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files},
        "provenance_inputs": {str(Path(occurrences).resolve()): occurrence_sha256, str(Path(predictions).resolve()): prediction_sha256},
        "provenance_binding": "Independent audit confirms prediction hash matches frozen map; canonical instance/order/node checked at runtime",
        "output_sha256": hashlib.sha256(data).hexdigest(),
        "process_count": len(result["processes"]), "business_step_count": result["generated_business_step_count"]}
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=False)
    (out / "business_steps.json").write_bytes(data)
    (out / "manifest.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest, indent=2))
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("destination")
    for name in ("occurrences", "occurrence-sha256", "predictions", "prediction-sha256"):
        p.add_argument("--" + name, required=True)
    main(**vars(p.parse_args()))
