from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class WorkflowStep:
    step_order: int
    step_type: str
    start_idx: int
    end_idx: int
    confidence: float
    evidence_activities: list[str]


@dataclass
class WorkflowPrediction:
    case_id: int
    model_version: str
    steps: list[WorkflowStep]


def workflow_to_dict(workflow: WorkflowPrediction) -> dict:
    return asdict(workflow)
