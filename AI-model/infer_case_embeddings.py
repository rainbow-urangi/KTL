# ml/infer_case_embeddings.py
from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from adapters import build_adapter
from config import DBConfig, TrainConfig
from vocab import Vocab
from dataset import BrowserEventDataset, CaseSequence, collate_browser_events
from model import EventTransformerEncoder


def load_vocabs(model_dir: str) -> dict[str, Vocab]:
    return {
        "activity": Vocab.load(os.path.join(model_dir, "activity_vocab.json")),
        "l1": Vocab.load(os.path.join(model_dir, "l1_vocab.json")),
        "api_method": Vocab.load(os.path.join(model_dir, "api_method_vocab.json")),
        "status": Vocab.load(os.path.join(model_dir, "status_vocab.json")),
        "delta": Vocab.load(os.path.join(model_dir, "delta_vocab.json")),
    }


def build_cases_from_db(db_cfg: DBConfig, train_cfg: TrainConfig) -> list[CaseSequence]:
    """Backward-compatible entry point for callers that explicitly need DB data."""
    from adapters.current_db_adapter import CurrentDBCaseAdapter

    return CurrentDBCaseAdapter(db_cfg, train_cfg).load_cases()


@torch.no_grad()
def infer_embeddings():
    db_cfg = DBConfig()
    train_cfg = TrainConfig()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    vocabs = load_vocabs(train_cfg.model_dir)
    cases = build_adapter(db_cfg, train_cfg).load_cases()
    if not cases:
        raise RuntimeError("No usable cases found for embedding inference")

    dataset = BrowserEventDataset(
        cases=cases,
        activity_vocab=vocabs["activity"],
        l1_vocab=vocabs["l1"],
        api_method_vocab=vocabs["api_method"],
        status_vocab=vocabs["status"],
        delta_vocab=vocabs["delta"],
        max_len=train_cfg.max_seq_len,
        mask_prob=0.0,
        mode="inference",
    )

    collate_fn = lambda batch: collate_browser_events(
        batch,
        pad_id=vocabs["activity"].pad_id,
    )

    loader = DataLoader(
        dataset,
        batch_size=train_cfg.batch_size,
        shuffle=False,
        collate_fn=collate_fn,
    )

    ckpt = torch.load(os.path.join(train_cfg.model_dir, "model.pt"), map_location=device)

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

    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    all_case_ids = []
    all_variant_ids = []
    all_embeddings = []

    for batch in tqdm(loader, desc="infer embeddings"):
        batch = {k: v.to(device) if torch.is_tensor(v) else v for k, v in batch.items()}

        out = model(
            activity_ids=batch["activity_ids"],
            l1_ids=batch["l1_ids"],
            api_method_ids=batch["api_method_ids"],
            status_ids=batch["status_ids"],
            delta_ids=batch["delta_ids"],
            attention_mask=batch["attention_mask"],
        )

        pooled = model.pool_sequence(
            hidden_states=out["hidden_states"],
            attention_mask=batch["attention_mask"],
        )

        all_case_ids.extend(batch["case_id"].cpu().numpy().tolist())
        all_variant_ids.extend(batch["variant_id"].cpu().numpy().tolist())
        all_embeddings.append(pooled.cpu().numpy())

    embeddings = np.concatenate(all_embeddings, axis=0)

    Path(train_cfg.model_dir).mkdir(parents=True, exist_ok=True)

    np.save(os.path.join(train_cfg.model_dir, "case_embeddings.npy"), embeddings)

    with open(os.path.join(train_cfg.model_dir, "case_embedding_index.json"), "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "case_id": int(cid),
                    "variant_id": int(vid),
                    "embedding_index": i,
                }
                for i, (cid, vid) in enumerate(zip(all_case_ids, all_variant_ids))
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[saved] {os.path.join(train_cfg.model_dir, 'case_embeddings.npy')}")
    print(f"[saved] {os.path.join(train_cfg.model_dir, 'case_embedding_index.json')}")


if __name__ == "__main__":
    infer_embeddings()
