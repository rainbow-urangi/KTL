from __future__ import annotations

import torch
import torch.nn as nn

from model import EventTransformerEncoder


class HighLevelBusinessExtractor(nn.Module):
    """Add abstract step classification to the existing event encoder."""

    def __init__(self, encoder: EventTransformerEncoder, num_step_types: int):
        super().__init__()
        self.encoder = encoder
        self.num_step_types = num_step_types
        self.step_type_head = nn.Linear(encoder.d_model, num_step_types)

    def forward(
        self,
        activity_ids: torch.Tensor,
        l1_ids: torch.Tensor,
        api_method_ids: torch.Tensor,
        status_ids: torch.Tensor,
        delta_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        out = self.encoder(
            activity_ids=activity_ids,
            l1_ids=l1_ids,
            api_method_ids=api_method_ids,
            status_ids=status_ids,
            delta_ids=delta_ids,
            attention_mask=attention_mask,
        )
        hidden_states = out["hidden_states"]
        return {
            "hidden_states": hidden_states,
            "boundary_logits": out["boundary_logits"],
            "step_type_logits": self.step_type_head(hidden_states),
            "next_activity_logits": out.get("next_activity_logits"),
            "mlm_activity_logits": out.get("mlm_activity_logits"),
        }
