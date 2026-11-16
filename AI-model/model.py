# ml/model.py
from __future__ import annotations

import torch
import torch.nn as nn


class EventTransformerEncoder(nn.Module):
    """
    Browser event sequence를 학습하는 Transformer Encoder.

    1차 목적:
    - Next Activity Prediction
    - Masked Activity Prediction

    이후 확장:
    - Step Boundary Prediction
    - Abstract Step Type Prediction
    """

    def __init__(
        self,
        activity_vocab_size: int,
        l1_vocab_size: int,
        api_method_vocab_size: int,
        status_vocab_size: int,
        delta_vocab_size: int,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 3,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        max_len: int = 256,
    ):
        super().__init__()

        self.d_model = d_model
        self.max_len = max_len

        self.activity_emb = nn.Embedding(activity_vocab_size, d_model, padding_idx=0)
        self.l1_emb = nn.Embedding(l1_vocab_size, d_model, padding_idx=0)
        self.api_method_emb = nn.Embedding(api_method_vocab_size, d_model, padding_idx=0)
        self.status_emb = nn.Embedding(status_vocab_size, d_model, padding_idx=0)
        self.delta_emb = nn.Embedding(delta_vocab_size, d_model, padding_idx=0)
        self.pos_emb = nn.Embedding(max_len, d_model)

        self.input_norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )

        self.encoder = nn.TransformerEncoder(
            encoder_layer=encoder_layer,
            num_layers=num_layers,
        )

        # Self-supervised heads
        self.next_activity_head = nn.Linear(d_model, activity_vocab_size)
        self.mlm_activity_head = nn.Linear(d_model, activity_vocab_size)

        # 이후 fine-tuning에서 사용할 head
        self.boundary_head = nn.Linear(d_model, 1)

    def encode(
        self,
        activity_ids: torch.Tensor,
        l1_ids: torch.Tensor,
        api_method_ids: torch.Tensor,
        status_ids: torch.Tensor,
        delta_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        batch_size, seq_len = activity_ids.shape
        device = activity_ids.device

        positions = torch.arange(seq_len, device=device).unsqueeze(0).expand(batch_size, seq_len)

        x = (
            self.activity_emb(activity_ids)
            + self.l1_emb(l1_ids)
            + self.api_method_emb(api_method_ids)
            + self.status_emb(status_ids)
            + self.delta_emb(delta_ids)
            + self.pos_emb(positions)
        )

        x = self.input_norm(x)
        x = self.dropout(x)

        h = self.encoder(
            x,
            src_key_padding_mask=attention_mask,
        )

        return h

    def forward(
        self,
        activity_ids: torch.Tensor,
        l1_ids: torch.Tensor,
        api_method_ids: torch.Tensor,
        status_ids: torch.Tensor,
        delta_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        h = self.encode(
            activity_ids=activity_ids,
            l1_ids=l1_ids,
            api_method_ids=api_method_ids,
            status_ids=status_ids,
            delta_ids=delta_ids,
            attention_mask=attention_mask,
        )

        return {
            "hidden_states": h,
            "next_activity_logits": self.next_activity_head(h),
            "mlm_activity_logits": self.mlm_activity_head(h),
            "boundary_logits": self.boundary_head(h).squeeze(-1),
        }

    def pool_sequence(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        case-level embedding 생성.
        padding이 아닌 토큰의 평균 pooling.
        """
        valid = (~attention_mask).float().unsqueeze(-1)
        summed = (hidden_states * valid).sum(dim=1)
        denom = valid.sum(dim=1).clamp_min(1.0)
        return summed / denom