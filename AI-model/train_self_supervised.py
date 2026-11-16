# ml/train_self_supervised.py
from __future__ import annotations

import os
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm

from adapters import build_adapter
from config import DBConfig, TrainConfig
from vocab import Vocab
from dataset import (
    BrowserEventDataset,
    CaseSequence,
    collate_browser_events,
    status_bucket,
)
from model import EventTransformerEncoder


def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_cases_from_db(
    db_cfg: DBConfig,
    train_cfg: TrainConfig,
) -> list[CaseSequence]:
    """Backward-compatible entry point for callers that explicitly need DB data."""
    from adapters.current_db_adapter import CurrentDBCaseAdapter

    return CurrentDBCaseAdapter(db_cfg, train_cfg).load_cases()


def build_vocabs(cases: list[CaseSequence]) -> dict[str, Vocab]:
    activities = []
    l1s = []
    api_methods = []
    statuses = []
    deltas = ["none", "lt_1s", "1s_5s", "5s_30s", "30s_2m", "gt_2m"]

    for c in cases:
        for r in c.rows:
            activities.append(str(r.get("activity") or ""))
            l1s.append(str(r.get("activity_l1") or ""))
            api_methods.append(str(r.get("api_method") or "none"))
            statuses.append(status_bucket(r.get("api_status_code")))

    return {
        "activity": Vocab.build(activities, min_freq=1),
        "l1": Vocab.build(l1s, min_freq=1),
        "api_method": Vocab.build(api_methods, min_freq=1),
        "status": Vocab.build(statuses, min_freq=1),
        "delta": Vocab.build(deltas, min_freq=1),
    }


def save_vocabs(vocabs: dict[str, Vocab], model_dir: str):
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    for name, vocab in vocabs.items():
        vocab.save(os.path.join(model_dir, f"{name}_vocab.json"))


def train():
    set_seed(42)

    db_cfg = DBConfig()
    train_cfg = TrainConfig()

    Path(train_cfg.model_dir).mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    cases = build_adapter(db_cfg, train_cfg).load_cases()
    if len(cases) < 10:
        raise RuntimeError("학습 가능한 case가 너무 적습니다. seq_len_clean 조건 또는 ETL 결과를 확인하세요.")

    vocabs = build_vocabs(cases)
    save_vocabs(vocabs, train_cfg.model_dir)

    dataset = BrowserEventDataset(
        cases=cases,
        activity_vocab=vocabs["activity"],
        l1_vocab=vocabs["l1"],
        api_method_vocab=vocabs["api_method"],
        status_vocab=vocabs["status"],
        delta_vocab=vocabs["delta"],
        max_len=train_cfg.max_seq_len,
        mask_prob=0.15,
        mode="self_supervised",
    )

    train_size = int(len(dataset) * 0.8)
    valid_size = len(dataset) - train_size
    train_ds, valid_ds = random_split(dataset, [train_size, valid_size])

    collate_fn = lambda batch: collate_browser_events(
        batch,
        pad_id=vocabs["activity"].pad_id,
    )

    train_loader = DataLoader(
        train_ds,
        batch_size=train_cfg.batch_size,
        shuffle=True,
        collate_fn=collate_fn,
    )

    valid_loader = DataLoader(
        valid_ds,
        batch_size=train_cfg.batch_size,
        shuffle=False,
        collate_fn=collate_fn,
    )

    model = EventTransformerEncoder(
        activity_vocab_size=len(vocabs["activity"]),
        l1_vocab_size=len(vocabs["l1"]),
        api_method_vocab_size=len(vocabs["api_method"]),
        status_vocab_size=len(vocabs["status"]),
        delta_vocab_size=len(vocabs["delta"]),
        d_model=train_cfg.d_model,
        nhead=train_cfg.nhead,
        num_layers=train_cfg.num_layers,
        dim_feedforward=train_cfg.dim_feedforward,
        dropout=train_cfg.dropout,
        max_len=train_cfg.max_seq_len,
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=train_cfg.lr, weight_decay=0.01)

    ce_loss = nn.CrossEntropyLoss(ignore_index=vocabs["activity"].pad_id)

    best_valid_loss = float("inf")

    for epoch in range(1, train_cfg.epochs + 1):
        model.train()
        train_losses = []

        for batch in tqdm(train_loader, desc=f"epoch {epoch} train"):
            batch = {k: v.to(device) if torch.is_tensor(v) else v for k, v in batch.items()}

            out = model(
                activity_ids=batch["activity_ids"],
                l1_ids=batch["l1_ids"],
                api_method_ids=batch["api_method_ids"],
                status_ids=batch["status_ids"],
                delta_ids=batch["delta_ids"],
                attention_mask=batch["attention_mask"],
            )

            next_logits = out["next_activity_logits"]
            mlm_logits = out["mlm_activity_logits"]

            next_loss = ce_loss(
                next_logits.reshape(-1, next_logits.size(-1)),
                batch["next_activity_labels"].reshape(-1),
            )

            mlm_loss = ce_loss(
                mlm_logits.reshape(-1, mlm_logits.size(-1)),
                batch["mlm_labels"].reshape(-1),
            )

            loss = next_loss + mlm_loss

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            train_losses.append(float(loss.item()))

        valid_loss = evaluate(
            model=model,
            loader=valid_loader,
            ce_loss=ce_loss,
            device=device,
            pad_id=vocabs["activity"].pad_id,
        )

        avg_train_loss = float(np.mean(train_losses))

        print(
            f"[epoch {epoch}] "
            f"train_loss={avg_train_loss:.4f} "
            f"valid_loss={valid_loss:.4f}"
        )

        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss

            ckpt_path = os.path.join(train_cfg.model_dir, "model.pt")
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "train_config": train_cfg.__dict__,
                    "vocab_sizes": {
                        "activity": len(vocabs["activity"]),
                        "l1": len(vocabs["l1"]),
                        "api_method": len(vocabs["api_method"]),
                        "status": len(vocabs["status"]),
                        "delta": len(vocabs["delta"]),
                    },
                    "best_valid_loss": best_valid_loss,
                },
                ckpt_path,
            )

            with open(os.path.join(train_cfg.model_dir, "metrics.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "best_valid_loss": best_valid_loss,
                        "last_train_loss": avg_train_loss,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            print(f"[save] {ckpt_path}")


@torch.no_grad()
def evaluate(
    model: EventTransformerEncoder,
    loader: DataLoader,
    ce_loss: nn.Module,
    device: torch.device,
    pad_id: int,
) -> float:
    model.eval()
    losses = []

    for batch in tqdm(loader, desc="valid"):
        batch = {k: v.to(device) if torch.is_tensor(v) else v for k, v in batch.items()}

        out = model(
            activity_ids=batch["activity_ids"],
            l1_ids=batch["l1_ids"],
            api_method_ids=batch["api_method_ids"],
            status_ids=batch["status_ids"],
            delta_ids=batch["delta_ids"],
            attention_mask=batch["attention_mask"],
        )

        next_logits = out["next_activity_logits"]
        mlm_logits = out["mlm_activity_logits"]

        next_loss = ce_loss(
            next_logits.reshape(-1, next_logits.size(-1)),
            batch["next_activity_labels"].reshape(-1),
        )

        mlm_loss = ce_loss(
            mlm_logits.reshape(-1, mlm_logits.size(-1)),
            batch["mlm_labels"].reshape(-1),
        )

        loss = next_loss + mlm_loss
        losses.append(float(loss.item()))

    return float(np.mean(losses)) if losses else 0.0


if __name__ == "__main__":
    train()
