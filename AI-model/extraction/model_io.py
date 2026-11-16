from __future__ import annotations

import os

import torch

from model import EventTransformerEncoder
from vocab import Vocab


def load_vocabs(model_dir: str) -> dict[str, Vocab]:
    return {
        name: Vocab.load(os.path.join(model_dir, f"{name}_vocab.json"))
        for name in ("activity", "l1", "api_method", "status", "delta")
    }


def encoder_config(checkpoint: dict, fallback_cfg) -> dict:
    saved = checkpoint.get("train_config", {})
    return {
        "d_model": int(saved.get("d_model", fallback_cfg.d_model)),
        "nhead": int(saved.get("nhead", fallback_cfg.nhead)),
        "num_layers": int(saved.get("num_layers", fallback_cfg.num_layers)),
        "dim_feedforward": int(
            saved.get("dim_feedforward", fallback_cfg.dim_feedforward)
        ),
        "dropout": float(saved.get("dropout", fallback_cfg.dropout)),
        "max_len": int(saved.get("max_seq_len", fallback_cfg.max_seq_len)),
    }


def build_encoder(vocabs: dict[str, Vocab], config: dict) -> EventTransformerEncoder:
    return EventTransformerEncoder(
        activity_vocab_size=len(vocabs["activity"]),
        l1_vocab_size=len(vocabs["l1"]),
        api_method_vocab_size=len(vocabs["api_method"]),
        status_vocab_size=len(vocabs["status"]),
        delta_vocab_size=len(vocabs["delta"]),
        **config,
    )


def load_pretrained_encoder(
    checkpoint_path: str,
    vocabs: dict[str, Vocab],
    fallback_cfg,
    device: torch.device,
) -> tuple[EventTransformerEncoder, dict, dict]:
    if not os.path.isfile(checkpoint_path):
        raise FileNotFoundError(f"Pretrained model not found: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    config = encoder_config(checkpoint, fallback_cfg)
    encoder = build_encoder(vocabs, config)
    encoder.load_state_dict(checkpoint["model_state_dict"])
    return encoder.to(device), checkpoint, config
