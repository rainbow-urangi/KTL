from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize workflow JSONL")
    parser.add_argument("--workflows", default="", help="Workflow JSONL")
    parser.add_argument("--clusters", default="", help="Optional cluster CSV")
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.workflows and not args.clusters:
        raise ValueError("Provide --workflows, --clusters, or both")
    cluster_by_case = {}
    if args.clusters:
        with open(args.clusters, "r", encoding="utf-8-sig", newline="") as f:
            cluster_by_case = {
                str(row["case_id"]): row["cluster_id"] for row in csv.DictReader(f)
            }
    if not args.workflows:
        counts = Counter(cluster_by_case.values())
        for group in sorted(counts, key=str):
            print(f"Cluster {group}")
            print(f"case_count: {counts[group]}")
            print("(add --workflows to summarize activities and sequences)")
            print()
        return
    grouped = defaultdict(list)
    with open(args.workflows, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                workflow = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at workflow line {line_number}") from exc
            group = cluster_by_case.get(str(workflow.get("case_id")), "all")
            grouped[group].append(workflow)

    for group in sorted(grouped, key=str):
        workflows = grouped[group]
        print(f"Cluster {group}" if group != "all" else "All workflows")
        print(f"case_count: {len(workflows)}")
        activities = Counter()
        step_types = Counter()
        sequences = Counter()
        for workflow in workflows:
            sequence = []
            for step in workflow.get("steps", []):
                step_types[step.get("step_type", "UNKNOWN")] += 1
                evidence = step.get("evidence_activities", [])
                activities.update(evidence)
                sequence.extend(evidence)
            sequences[tuple(sequence)] += 1
        print("top step types:")
        for label, count in step_types.most_common(args.top):
            print(f"- {label}: {count}")
        print("top activities:")
        for activity, count in activities.most_common(args.top):
            print(f"- {activity}: {count}")
        representative = sequences.most_common(1)
        print("representative sequence:")
        print(" → ".join(representative[0][0]) if representative else "(none)")
        print()


if __name__ == "__main__":
    main()
