from __future__ import annotations

import json
from pathlib import Path

from .workflow_schema import WorkflowPrediction, workflow_to_dict


def export_workflows_jsonl(
    workflows: list[WorkflowPrediction],
    output_path: str,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for workflow in workflows:
            f.write(json.dumps(workflow_to_dict(workflow), ensure_ascii=False) + "\n")
