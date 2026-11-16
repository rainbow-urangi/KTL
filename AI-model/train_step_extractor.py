from __future__ import annotations

import argparse
import csv
import json
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, Subset
from tqdm import tqdm

from adapters import build_adapter
from adapters.csv_adapter import normalize_case_id
from config import DBConfig, TrainConfig
from dataset import BrowserEventDataset, collate_browser_events
from extraction.high_level_extractor import HighLevelBusinessExtractor
from extraction.model_io import load_pretrained_encoder, load_vocabs
from extraction.step_labels import STEP_LABELS, STEP_LABEL_TO_ID


IGNORE_BOUNDARY = -1.0
IGNORE_STEP_TYPE = -100


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _parse_boundary(value: str, row_number: int) -> float:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return 1.0
    if normalized in {"0", "false", "no", "n"}:
        return 0.0
    raise ValueError(f"Invalid is_step_start at label row {row_number}: {value!r}")


def load_labels(path: str) -> dict[int, dict[int, tuple[float, int]]]:
    labels: dict[int, dict[int, tuple[float, int]]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"case_id", "event_index", "is_step_start", "abstract_step_type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Label CSV is missing required columns: {sorted(missing)}")
        for row_number, row in enumerate(reader, start=2):
            case_id = normalize_case_id(row["case_id"])
            try:
                event_index = int(row["event_index"])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid event_index at label row {row_number}: {row['event_index']!r}"
                ) from exc
            if event_index < 0:
                raise ValueError(f"event_index must be >= 0 at label row {row_number}")
            boundary = _parse_boundary(row["is_step_start"], row_number)
            step_name = str(row.get("abstract_step_type") or "").strip()
            if step_name and step_name not in STEP_LABEL_TO_ID:
                raise ValueError(
                    f"Unknown abstract_step_type at label row {row_number}: {step_name!r}"
                )
            step_id = STEP_LABEL_TO_ID.get(step_name, IGNORE_STEP_TYPE)
            labels.setdefault(case_id, {})[event_index] = (boundary, step_id)
    return labels


class StepLabeledDataset(Dataset):
    def __init__(self, base: BrowserEventDataset, labels: dict[int, dict[int, tuple[float, int]]]):
        self.base = base
        self.labels = labels

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, index: int) -> dict:
        item = self.base[index]
        length = int(item["length"])
        case_id = int(item["case_id"])
        boundary = torch.full((length,), IGNORE_BOUNDARY, dtype=torch.float32)
        step_type = torch.full((length,), IGNORE_STEP_TYPE, dtype=torch.long)
        for event_index, (boundary_value, step_id) in self.labels.get(case_id, {}).items():
            if event_index < length:
                boundary[event_index] = boundary_value
                step_type[event_index] = step_id
        item["boundary_labels"] = boundary
        item["step_type_labels"] = step_type
        return item


def collate_step_batch(batch: list[dict], pad_id: int) -> dict:
    max_len = max(int(item["length"]) for item in batch)
    boundary_labels = torch.full((len(batch), max_len), IGNORE_BOUNDARY)
    step_type_labels = torch.full(
        (len(batch), max_len), IGNORE_STEP_TYPE, dtype=torch.long
    )
    for index, item in enumerate(batch):
        length = min(int(item["length"]), max_len)
        boundary_labels[index, :length] = item.pop("boundary_labels")[:length]
        step_type_labels[index, :length] = item.pop("step_type_labels")[:length]
    out = collate_browser_events(batch, pad_id)
    out["boundary_labels"] = boundary_labels
    out["step_type_labels"] = step_type_labels
    return out


def compute_loss(model, batch, boundary_loss_fn, step_loss_fn):
    out = model(
        activity_ids=batch["activity_ids"],
        l1_ids=batch["l1_ids"],
        api_method_ids=batch["api_method_ids"],
        status_ids=batch["status_ids"],
        delta_ids=batch["delta_ids"],
        attention_mask=batch["attention_mask"],
    )
    boundary_mask = batch["boundary_labels"].ne(IGNORE_BOUNDARY)
    type_mask = batch["step_type_labels"].ne(IGNORE_STEP_TYPE)
    if not boundary_mask.any():
        raise RuntimeError("A batch contained no boundary labels")
    boundary_loss = boundary_loss_fn(
        out["boundary_logits"][boundary_mask], batch["boundary_labels"][boundary_mask]
    )
    if type_mask.any():
        type_loss = step_loss_fn(
            out["step_type_logits"][type_mask], batch["step_type_labels"][type_mask]
        )
    else:
        type_loss = out["step_type_logits"].sum() * 0.0
    return boundary_loss + type_loss, boundary_loss, type_loss, out, boundary_mask, type_mask


@torch.no_grad()
def evaluate(model, loader, device) -> dict[str, float]:
    model.eval()
    bce = nn.BCEWithLogitsLoss()
    ce = nn.CrossEntropyLoss()
    losses = []
    boundary_correct = boundary_count = type_correct = type_count = 0
    for batch in loader:
        batch = {key: value.to(device) for key, value in batch.items()}
        loss, _, _, out, boundary_mask, type_mask = compute_loss(model, batch, bce, ce)
        losses.append(float(loss.item()))
        predicted_boundaries = out["boundary_logits"].ge(0)
        boundary_correct += int(
            predicted_boundaries[boundary_mask]
            .eq(batch["boundary_labels"][boundary_mask].bool())
            .sum()
        )
        boundary_count += int(boundary_mask.sum())
        if type_mask.any():
            type_correct += int(
                out["step_type_logits"][type_mask]
                .argmax(-1)
                .eq(batch["step_type_labels"][type_mask])
                .sum()
            )
            type_count += int(type_mask.sum())
    return {
        "loss": float(np.mean(losses)) if losses else 0.0,
        "boundary_accuracy": boundary_correct / max(boundary_count, 1),
        "step_type_accuracy": type_correct / max(type_count, 1) if type_count else 0.0,
        "boundary_label_count": boundary_count,
        "step_type_label_count": type_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune workflow step extraction heads")
    parser.add_argument("--labels", required=True, help="Step label CSV")
    parser.add_argument("--pretrained", default="", help="Override pretrained model.pt")
    parser.add_argument("--output", default="", help="Override step_extractor.pt path")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--lr", type=float, default=None)
    return parser.parse_args()


def train() -> None:
    args = parse_args()
    set_seed()
    cfg = TrainConfig()
    db_cfg = DBConfig()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vocabs = load_vocabs(cfg.model_dir)
    cases = build_adapter(db_cfg, cfg).load_cases()
    labels = load_labels(args.labels)
    cases = [case for case in cases if case.case_id in labels]
    if not cases:
        raise RuntimeError("No loaded cases matched the label CSV case_id values")

    pretrained_path = args.pretrained or os.path.join(cfg.model_dir, "model.pt")
    encoder, _, enc_config = load_pretrained_encoder(
        pretrained_path, vocabs, cfg, device
    )
    model = HighLevelBusinessExtractor(encoder, len(STEP_LABELS)).to(device)

    base_dataset = BrowserEventDataset(
        cases, vocabs["activity"], vocabs["l1"], vocabs["api_method"],
        vocabs["status"], vocabs["delta"], max_len=enc_config["max_len"],
        mask_prob=0.0, mode="inference",
    )
    dataset = StepLabeledDataset(base_dataset, labels)
    indices = list(range(len(dataset)))
    random.shuffle(indices)
    split = max(1, int(len(indices) * 0.8))
    train_indices = indices[:split]
    valid_indices = indices[split:] or indices[:]
    collate_fn = lambda batch: collate_step_batch(batch, vocabs["activity"].pad_id)
    batch_size = args.batch_size or cfg.batch_size
    train_loader = DataLoader(
        Subset(dataset, train_indices), batch_size=batch_size, shuffle=True,
        collate_fn=collate_fn,
    )
    valid_loader = DataLoader(
        Subset(dataset, valid_indices), batch_size=batch_size, shuffle=False,
        collate_fn=collate_fn,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr or cfg.lr, weight_decay=0.01)
    bce = nn.BCEWithLogitsLoss()
    ce = nn.CrossEntropyLoss()
    best_metrics = None
    output_path = Path(args.output or os.path.join(cfg.model_dir, "step_extractor.pt"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, (args.epochs or cfg.epochs) + 1):
        model.train()
        train_losses = []
        for batch in tqdm(train_loader, desc=f"step epoch {epoch} train"):
            batch = {key: value.to(device) for key, value in batch.items()}
            loss, _, _, _, _, _ = compute_loss(model, batch, bce, ce)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_losses.append(float(loss.item()))

        metrics = evaluate(model, valid_loader, device)
        metrics.update(epoch=epoch, train_loss=float(np.mean(train_losses)))
        print(
            f"[epoch {epoch}] train_loss={metrics['train_loss']:.4f} "
            f"valid_loss={metrics['loss']:.4f} "
            f"boundary_acc={metrics['boundary_accuracy']:.4f} "
            f"step_type_acc={metrics['step_type_accuracy']:.4f}"
        )
        if best_metrics is None or metrics["loss"] < best_metrics["loss"]:
            best_metrics = metrics
            torch.save(
                {
                    "extractor_state_dict": model.state_dict(),
                    "encoder_config": enc_config,
                    "train_config": cfg.__dict__,
                    "step_labels": STEP_LABELS,
                    "metrics": best_metrics,
                },
                output_path,
            )
            metrics_path = output_path.with_name("step_metrics.json")
            with metrics_path.open("w", encoding="utf-8") as f:
                json.dump(best_metrics, f, ensure_ascii=False, indent=2)
            print(f"[save] {output_path}")


if __name__ == "__main__":
    train()
