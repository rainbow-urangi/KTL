from __future__ import annotations

import json

from .base_adapter import BaseCaseAdapter
from .csv_adapter import CSVCaseAdapter


def build_adapter(db_cfg, train_cfg) -> BaseCaseAdapter:
    """Build the configured case source without leaking source details to callers."""
    source = str(train_cfg.data_source).strip().lower()
    if source == "db":
        from .current_db_adapter import CurrentDBCaseAdapter

        return CurrentDBCaseAdapter(db_cfg, train_cfg)
    if source == "csv":
        if not train_cfg.csv_path:
            raise ValueError("DATA_SOURCE=csv requires CSV_PATH")
        if not train_cfg.column_mapping_path:
            raise ValueError("DATA_SOURCE=csv requires COLUMN_MAPPING_PATH")
        try:
            with open(train_cfg.column_mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Could not read COLUMN_MAPPING_PATH={train_cfg.column_mapping_path!r}: {exc}"
            ) from exc
        if not isinstance(mapping, dict):
            raise ValueError("Column mapping JSON must contain an object")
        return CSVCaseAdapter(
            csv_path=train_cfg.csv_path,
            column_mapping=mapping,
            min_seq_len=train_cfg.min_seq_len_clean,
            max_seq_len=train_cfg.max_seq_len,
        )
    raise ValueError(f"Unsupported DATA_SOURCE={train_cfg.data_source!r}; use 'db' or 'csv'")


def __getattr__(name: str):
    # Keep CSV-only tooling usable when the optional pymysql dependency is absent.
    if name == "CurrentDBCaseAdapter":
        from .current_db_adapter import CurrentDBCaseAdapter

        return CurrentDBCaseAdapter
    raise AttributeError(name)


__all__ = [
    "BaseCaseAdapter",
    "CSVCaseAdapter",
    "CurrentDBCaseAdapter",
    "build_adapter",
]
