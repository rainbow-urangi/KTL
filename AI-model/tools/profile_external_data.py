from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# Support the documented `python tools/profile_external_data.py` invocation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.csv_adapter import read_standard_rows
from dataset import rle_dedupe_rows, status_bucket


def ratio(count: int, total: int) -> float:
    return count / total if total else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile external event CSV data")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--min-seq-len", type=int, default=5)
    return parser.parse_args()


def print_distribution(name: str, values, limit: int = 20) -> None:
    print(f"{name}:")
    for value, count in Counter(value or "<missing>" for value in values).most_common(limit):
        print(f"  {value}: {count}")


def main() -> None:
    args = parse_args()
    with open(args.mapping, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    rows = read_standard_rows(args.csv, mapping)
    grouped = {}
    for row in rows:
        if row["case_id"] is not None:
            grouped.setdefault(row["case_id"], []).append(row)
    lengths = [len(case_rows) for case_rows in grouped.values()]
    usable = sum(
        len(rle_dedupe_rows(case_rows)) >= args.min_seq_len
        for case_rows in grouped.values()
    )
    total = len(rows)

    print(f"rows: {total}")
    print(f"case count: {len(grouped)}")
    print(f"avg events per case: {statistics.mean(lengths):.2f}" if lengths else "avg events per case: 0")
    print(f"median events per case: {statistics.median(lengths):.2f}" if lengths else "median events per case: 0")
    print(f"min/max events per case: {min(lengths)}/{max(lengths)}" if lengths else "min/max events per case: 0/0")
    print(f"missing timestamp ratio: {ratio(sum(not row.get('ts') for row in rows), total):.4f}")
    print(f"missing case_id ratio: {ratio(sum(row.get('case_id') is None for row in rows), total):.4f}")
    print(f"activity missing ratio: {ratio(sum(row['_activity_was_missing'] for row in rows), total):.4f}")
    print_distribution("event_type distribution", (row.get("event_type") for row in rows))
    print_distribution("interaction_type distribution", (row.get("interaction_type") for row in rows))
    print_distribution("api_method distribution", (row.get("api_method") for row in rows))
    print_distribution("status bucket distribution", (status_bucket(row.get("api_status_code")) for row in rows))
    print(f"usable cases with seq_len >= {args.min_seq_len}: {usable}")
    print_distribution("top 30 activities", (row.get("activity") for row in rows), limit=30)
    noise = Counter(
        row["activity"]
        for row in rows
        if row["activity"].startswith(("EVT:unknown", "API:GET_/static/", "API:GET_/resources/", "API:GET_/favicon"))
    )
    print("candidate noise activities:")
    if noise:
        for activity, count in noise.most_common(30):
            print(f"  {activity}: {count}")
    else:
        print("  (none detected)")


if __name__ == "__main__":
    main()
