from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from urllib.parse import urlsplit

from dataset import CaseSequence, parse_ts, rle_dedupe_rows, status_bucket

from .base_adapter import BaseCaseAdapter


STANDARD_FIELDS = (
    "case_id",
    "source_event_pk",
    "ts",
    "activity",
    "activity_l1",
    "activity_l2",
    "event_type",
    "interaction_type",
    "page_url",
    "page_title",
    "api_path",
    "api_method",
    "api_status_code",
    "element_tag",
    "associated_label",
    "element_text",
)


def _clean(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def normalize_case_id(value) -> int:
    """Return a reproducible integer ID while allowing external string IDs."""
    cleaned = _clean(value)
    if cleaned is None:
        raise ValueError("case_id is empty")
    try:
        return int(cleaned)
    except ValueError:
        digest = hashlib.sha256(cleaned.encode("utf-8")).digest()[:8]
        return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def generic_activity(row: dict) -> str:
    event_type = (_clean(row.get("event_type")) or "").lower()
    interaction = (_clean(row.get("interaction_type")) or "").lower()
    page_url = _clean(row.get("page_url"))
    api_path = _clean(row.get("api_path"))
    api_method = _clean(row.get("api_method"))

    if event_type in {"page_view", "pageview"}:
        path = urlsplit(page_url or "unknown").path or "unknown"
        return f"NAV:{path}"
    if api_path and api_method:
        return f"API:{api_method.upper()}_{api_path}_{status_bucket(row.get('api_status_code'))}"
    if interaction == "click":
        target = row.get("associated_label") or row.get("element_text") or row.get("element_tag") or "unknown"
        return f"CLICK:{target}"
    if interaction in {"input", "change", "keyup", "keydown", "textinput"}:
        target = row.get("associated_label") or row.get("element_tag") or "unknown"
        return f"INPUT:{target}"
    if interaction == "submit":
        target = row.get("page_title") or row.get("page_url") or "unknown"
        return f"SUBMIT:{target}"
    return f"EVT:{interaction or event_type or 'unknown'}"


def _timestamp_sort_key(row: dict) -> tuple[bool, float, int]:
    parsed = parse_ts(row.get("ts"))
    if parsed is None:
        return True, float(row["_row_index"]), row["_row_index"]
    try:
        timestamp = parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        timestamp = float(row["_row_index"])
    return False, timestamp, row["_row_index"]


def read_standard_rows(csv_path: str, column_mapping: dict[str, str]) -> list[dict]:
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    invalid_mapping = {
        field: source
        for field, source in column_mapping.items()
        if not isinstance(field, str) or not isinstance(source, str)
    }
    if invalid_mapping:
        raise ValueError(f"Column mapping keys and values must be strings: {invalid_mapping}")
    if not column_mapping.get("case_id"):
        raise ValueError("Column mapping must define 'case_id'")

    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = {
            source
            for source in column_mapping.values()
            if source and source not in headers
        }
        if missing:
            print(f"[warning] mapped CSV columns not found; values will be empty: {sorted(missing)}")

        for row_index, source_row in enumerate(reader):
            standard = {
                field: _clean(source_row.get(column_mapping.get(field, "")))
                for field in STANDARD_FIELDS
            }
            raw_case_id = standard["case_id"]
            standard["source_case_id"] = raw_case_id
            standard["_row_index"] = row_index
            standard["_activity_was_missing"] = not bool(standard["activity"])
            try:
                standard["case_id"] = normalize_case_id(raw_case_id)
            except ValueError:
                standard["case_id"] = None
            if not standard["activity"]:
                standard["activity"] = generic_activity(standard)
            rows.append(standard)
    return rows


class CSVCaseAdapter(BaseCaseAdapter):
    def __init__(
        self,
        csv_path: str,
        column_mapping: dict[str, str],
        min_seq_len: int = 5,
        max_seq_len: int = 256,
    ):
        self.csv_path = csv_path
        self.column_mapping = column_mapping
        self.min_seq_len = min_seq_len
        self.max_seq_len = max_seq_len

    def load_cases(self) -> list[CaseSequence]:
        rows = read_standard_rows(self.csv_path, self.column_mapping)
        grouped: dict[int, list[dict]] = {}
        missing_case_ids = 0
        for row in rows:
            case_id = row.get("case_id")
            if case_id is None:
                missing_case_ids += 1
                continue
            grouped.setdefault(case_id, []).append(row)

        cases = []
        for case_id, case_rows in grouped.items():
            case_rows.sort(key=_timestamp_sort_key)
            clean_rows = rle_dedupe_rows(case_rows)
            if len(clean_rows) < self.min_seq_len:
                continue
            cases.append(
                CaseSequence(
                    case_id=case_id,
                    rows=clean_rows[: self.max_seq_len],
                )
            )

        cases.sort(key=lambda case: case.case_id)
        if missing_case_ids:
            print(f"[warning] skipped rows with missing case_id={missing_case_ids}")
        print(f"[data] candidate cases={len(grouped)}")
        print(f"[data] usable cases={len(cases)}")
        return cases
