# ml/dataset.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random

import torch
from torch.utils.data import Dataset

from vocab import Vocab


DROP_EXACT = {
    "API:POST_/Chk/sessionchk_2xx",
}

DROP_PREFIX = (
    "API:GET_/static/",
    "API:GET_/resources/",
    "API:GET_/favicon",
)


def should_drop_activity(activity: str | None) -> bool:
    if not activity:
        return True

    if activity in DROP_EXACT:
        return True

    return any(activity.startswith(prefix) for prefix in DROP_PREFIX)


def rle_dedupe_rows(rows: list[dict]) -> list[dict]:
    """
    seq_text_clean과 같은 철학:
    heartbeat 제거 + 연속 중복 제거.
    단, source_event_pk 등 event-level 정보를 유지하기 위해 row 단위로 처리한다.
    """
    out = []
    prev = None

    for r in rows:
        act = r.get("activity")
        if should_drop_activity(act):
            continue

        if act == prev:
            continue

        out.append(r)
        prev = act

    return out


def status_bucket(code) -> str:
    if code is None:
        return "none"

    try:
        code = int(code)
    except Exception:
        return "other"

    if 200 <= code < 300:
        return "2xx"
    if 300 <= code < 400:
        return "3xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return "other"


def delta_bucket(ms: int | None) -> str:
    if ms is None:
        return "none"

    if ms < 1_000:
        return "lt_1s"
    if ms < 5_000:
        return "1s_5s"
    if ms < 30_000:
        return "5s_30s"
    if ms < 120_000:
        return "30s_2m"
    return "gt_2m"


def parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


@dataclass
class CaseSequence:
    case_id: int
    rows: list[dict]
    variant_id: int | None = None


class BrowserEventDataset(Dataset):
    """
    기존 ETL 산출물(event_log 기반 row)을 그대로 받아서
    Transformer 입력 tensor로 변환하는 Dataset.
    """

    def __init__(
        self,
        cases: list[CaseSequence],
        activity_vocab: Vocab,
        l1_vocab: Vocab,
        api_method_vocab: Vocab,
        status_vocab: Vocab,
        delta_vocab: Vocab,
        max_len: int = 256,
        mask_prob: float = 0.15,
        mode: str = "self_supervised",
    ):
        self.cases = cases
        self.activity_vocab = activity_vocab
        self.l1_vocab = l1_vocab
        self.api_method_vocab = api_method_vocab
        self.status_vocab = status_vocab
        self.delta_vocab = delta_vocab
        self.max_len = max_len
        self.mask_prob = mask_prob
        self.mode = mode

    def __len__(self) -> int:
        return len(self.cases)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        item = self.cases[idx]
        rows = item.rows[: self.max_len]

        activity_ids = []
        l1_ids = []
        api_method_ids = []
        status_ids = []
        delta_ids = []

        prev_ts = None

        for r in rows:
            ts = parse_ts(r.get("ts"))

            if ts is None or prev_ts is None:
                d_ms = None
            else:
                d_ms = int((ts - prev_ts).total_seconds() * 1000)

            prev_ts = ts if ts is not None else prev_ts

            activity_ids.append(self.activity_vocab.encode(r.get("activity")))
            l1_ids.append(self.l1_vocab.encode(r.get("activity_l1")))
            api_method_ids.append(self.api_method_vocab.encode(r.get("api_method")))
            status_ids.append(self.status_vocab.encode(status_bucket(r.get("api_status_code"))))
            delta_ids.append(self.delta_vocab.encode(delta_bucket(d_ms)))

        seq_len = len(activity_ids)

        # Next Event Prediction label
        # position i에서 i+1 activity를 맞히도록 구성
        next_activity_labels = activity_ids[1:] + [self.activity_vocab.pad_id]

        # Masked Event Prediction label
        masked_activity_ids = activity_ids[:]
        mlm_labels = [self.activity_vocab.pad_id] * seq_len

        if self.mode == "self_supervised":
            for i in range(seq_len):
                if random.random() < self.mask_prob:
                    mlm_labels[i] = activity_ids[i]
                    masked_activity_ids[i] = self.activity_vocab.mask_id

        return {
            "case_id": torch.tensor(item.case_id, dtype=torch.long),
            "activity_ids": torch.tensor(masked_activity_ids, dtype=torch.long),
            "original_activity_ids": torch.tensor(activity_ids, dtype=torch.long),
            "l1_ids": torch.tensor(l1_ids, dtype=torch.long),
            "api_method_ids": torch.tensor(api_method_ids, dtype=torch.long),
            "status_ids": torch.tensor(status_ids, dtype=torch.long),
            "delta_ids": torch.tensor(delta_ids, dtype=torch.long),
            "next_activity_labels": torch.tensor(next_activity_labels, dtype=torch.long),
            "mlm_labels": torch.tensor(mlm_labels, dtype=torch.long),
            "length": torch.tensor(seq_len, dtype=torch.long),
            "variant_id": torch.tensor(item.variant_id if item.variant_id is not None else -999, dtype=torch.long),
        }


def collate_browser_events(batch: list[dict], pad_id: int) -> dict[str, torch.Tensor]:
    max_len = max(int(x["length"]) for x in batch)

    def pad_1d(t: torch.Tensor, value: int = 0):
        if t.numel() >= max_len:
            return t[:max_len]
        return torch.cat(
            [t, torch.full((max_len - t.numel(),), value, dtype=t.dtype)],
            dim=0,
        )

    out = {
        "case_id": torch.stack([x["case_id"] for x in batch]),
        "activity_ids": torch.stack([pad_1d(x["activity_ids"], pad_id) for x in batch]),
        "original_activity_ids": torch.stack([pad_1d(x["original_activity_ids"], pad_id) for x in batch]),
        "l1_ids": torch.stack([pad_1d(x["l1_ids"], 0) for x in batch]),
        "api_method_ids": torch.stack([pad_1d(x["api_method_ids"], 0) for x in batch]),
        "status_ids": torch.stack([pad_1d(x["status_ids"], 0) for x in batch]),
        "delta_ids": torch.stack([pad_1d(x["delta_ids"], 0) for x in batch]),
        "next_activity_labels": torch.stack([pad_1d(x["next_activity_labels"], pad_id) for x in batch]),
        "mlm_labels": torch.stack([pad_1d(x["mlm_labels"], pad_id) for x in batch]),
        "length": torch.stack([x["length"] for x in batch]),
        "variant_id": torch.stack([x["variant_id"] for x in batch]),
    }

    # True = padding position
    attention_mask = out["activity_ids"].eq(pad_id)
    out["attention_mask"] = attention_mask

    return out