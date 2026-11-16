from __future__ import annotations

import argparse
import os
import warnings

import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from adapters import build_adapter
from config import DBConfig, TrainConfig
from dataset import BrowserEventDataset, collate_browser_events
from extraction.high_level_extractor import HighLevelBusinessExtractor
from extraction.model_io import build_encoder, load_pretrained_encoder, load_vocabs
from extraction.segmentation import boundary_probs_to_segments
from extraction.step_labels import ID_TO_STEP_LABEL, STEP_LABELS
from extraction.workflow_exporter import export_workflows_jsonl
from extraction.workflow_schema import WorkflowPrediction, WorkflowStep


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer case-level workflow JSONL")
    parser.add_argument("--output", default="", help="Output JSONL path")
    parser.add_argument("--step-model", default="", help="Fine-tuned step checkpoint")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--min-step-len", type=int, default=1)
    return parser.parse_args()


def load_extractor(cfg, vocabs, device, step_model_path: str):
    if step_model_path:
        if not os.path.isfile(step_model_path):
            raise FileNotFoundError(f"Step extractor checkpoint not found: {step_model_path}")
        checkpoint = torch.load(step_model_path, map_location=device)
        saved_labels = checkpoint.get("step_labels", STEP_LABELS)
        if saved_labels != STEP_LABELS:
            raise ValueError("Step checkpoint label ordering does not match STEP_LABELS")
        enc_config = checkpoint.get("encoder_config")
        if not enc_config:
            raise ValueError("Step checkpoint is missing encoder_config")
        encoder = build_encoder(vocabs, enc_config)
        model = HighLevelBusinessExtractor(encoder, len(STEP_LABELS))
        model.load_state_dict(checkpoint["extractor_state_dict"])
        return model.to(device), enc_config, "event_transformer_v0_step_extractor"

    pretrained_path = os.path.join(cfg.model_dir, "model.pt")
    encoder, _, enc_config = load_pretrained_encoder(
        pretrained_path, vocabs, cfg, device
    )
    model = HighLevelBusinessExtractor(encoder, len(STEP_LABELS)).to(device)
    warnings.warn(
        "No fine-tuned step extractor was supplied. Boundary and step-type heads "
        "are untrained, so workflow quality will be low.",
        RuntimeWarning,
    )
    return model, enc_config, "event_transformer_v0_untrained_steps"


@torch.no_grad()
def infer() -> None:
    args = parse_args()
    cfg = TrainConfig()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vocabs = load_vocabs(cfg.model_dir)
    cases = build_adapter(DBConfig(), cfg).load_cases()
    if not cases:
        raise RuntimeError("No usable cases found for workflow inference")

    step_model_path = args.step_model or cfg.step_model_path
    model, enc_config, model_version = load_extractor(
        cfg, vocabs, device, step_model_path
    )
    model.eval()
    dataset = BrowserEventDataset(
        cases, vocabs["activity"], vocabs["l1"], vocabs["api_method"],
        vocabs["status"], vocabs["delta"], max_len=enc_config["max_len"],
        mask_prob=0.0, mode="inference",
    )
    collate_fn = lambda batch: collate_browser_events(batch, vocabs["activity"].pad_id)
    loader = DataLoader(
        dataset, batch_size=cfg.batch_size, shuffle=False, collate_fn=collate_fn
    )
    case_by_id = {case.case_id: case for case in cases}
    workflows = []
    threshold = args.threshold if args.threshold is not None else cfg.boundary_threshold

    for batch in tqdm(loader, desc="infer workflows"):
        batch = {key: value.to(device) for key, value in batch.items()}
        out = model(
            activity_ids=batch["activity_ids"], l1_ids=batch["l1_ids"],
            api_method_ids=batch["api_method_ids"], status_ids=batch["status_ids"],
            delta_ids=batch["delta_ids"], attention_mask=batch["attention_mask"],
        )
        boundary_probs = torch.sigmoid(out["boundary_logits"]).cpu()
        step_probs = torch.softmax(out["step_type_logits"], dim=-1).cpu()
        case_ids = batch["case_id"].cpu().tolist()
        lengths = batch["length"].cpu().tolist()

        for batch_index, (case_id, length) in enumerate(zip(case_ids, lengths)):
            boundaries = boundary_probs[batch_index, :length].tolist()
            segments = boundary_probs_to_segments(
                boundaries, threshold=threshold, min_step_len=args.min_step_len
            )
            case = case_by_id[int(case_id)]
            steps = []
            for segment in segments:
                start, end = segment["start_idx"], segment["end_idx"]
                mean_probs = step_probs[batch_index, start : end + 1].mean(dim=0)
                step_type_id = int(mean_probs.argmax())
                evidence = [
                    str(row.get("activity") or "")
                    for row in case.rows[start : end + 1]
                ]
                steps.append(
                    WorkflowStep(
                        step_order=segment["step_order"],
                        step_type=ID_TO_STEP_LABEL[step_type_id],
                        start_idx=start,
                        end_idx=end,
                        confidence=float(mean_probs[step_type_id]),
                        evidence_activities=evidence,
                    )
                )
            workflows.append(
                WorkflowPrediction(
                    case_id=int(case_id), model_version=model_version, steps=steps
                )
            )

    output_path = args.output or cfg.workflow_output_path
    export_workflows_jsonl(workflows, output_path)
    print(f"[saved] {output_path} ({len(workflows)} workflows)")


if __name__ == "__main__":
    infer()
