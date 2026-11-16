# ml/vocab.py
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass


PAD = "<PAD>"
UNK = "<UNK>"
MASK = "<MASK>"
CLS = "<CLS>"


@dataclass
class Vocab:
    token_to_id: dict[str, int]
    id_to_token: list[str]

    @classmethod
    def build(cls, values: list[str], min_freq: int = 1) -> "Vocab":
        counter = Counter(v for v in values if v)
        id_to_token = [PAD, UNK, MASK, CLS]

        for token, freq in counter.most_common():
            if freq >= min_freq and token not in id_to_token:
                id_to_token.append(token)

        token_to_id = {t: i for i, t in enumerate(id_to_token)}
        return cls(token_to_id=token_to_id, id_to_token=id_to_token)

    def encode(self, token: str | None) -> int:
        if not token:
            return self.token_to_id[UNK]
        return self.token_to_id.get(str(token), self.token_to_id[UNK])

    def decode(self, idx: int) -> str:
        if 0 <= idx < len(self.id_to_token):
            return self.id_to_token[idx]
        return UNK

    @property
    def pad_id(self) -> int:
        return self.token_to_id[PAD]

    @property
    def unk_id(self) -> int:
        return self.token_to_id[UNK]

    @property
    def mask_id(self) -> int:
        return self.token_to_id[MASK]

    @property
    def cls_id(self) -> int:
        return self.token_to_id[CLS]

    def __len__(self) -> int:
        return len(self.id_to_token)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id_to_token": self.id_to_token,
                    "token_to_id": self.token_to_id,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    @classmethod
    def load(cls, path: str) -> "Vocab":
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return cls(
            token_to_id={k: int(v) for k, v in obj["token_to_id"].items()},
            id_to_token=obj["id_to_token"],
        )