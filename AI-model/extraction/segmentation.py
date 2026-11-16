from __future__ import annotations


def boundary_probs_to_segments(
    boundary_probs: list[float],
    threshold: float = 0.5,
    min_step_len: int = 1,
) -> list[dict]:
    """Convert event-level step-start probabilities to inclusive segments."""
    if not boundary_probs:
        return []
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if min_step_len < 1:
        raise ValueError("min_step_len must be at least 1")

    starts = [0]
    for index in range(1, len(boundary_probs)):
        if boundary_probs[index] >= threshold and index - starts[-1] >= min_step_len:
            starts.append(index)

    # Merge a short final tail into its predecessor.
    if len(starts) > 1 and len(boundary_probs) - starts[-1] < min_step_len:
        starts.pop()

    segments = []
    for order, start in enumerate(starts, start=1):
        next_start = starts[order] if order < len(starts) else len(boundary_probs)
        segments.append(
            {
                "step_order": order,
                "start_idx": start,
                "end_idx": next_start - 1,
            }
        )
    return segments
