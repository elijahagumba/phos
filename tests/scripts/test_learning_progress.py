"""The progress report keeps throughput and progress apart (ADR 0121)."""

from __future__ import annotations

from scripts.learning_progress import _render


def test_throughput_is_never_rendered_as_progress() -> None:
    payload: dict[str, object] = {
        "throughput": {
            "failures_diagnosed": 14,
            "eligible_failures": 14,
            "failures_by_mechanism": {"inlet_subthreshold": 10},
            "tasks": 1,
            "attempts": 18,
            "compute_seconds": 2000.0,
        },
        "progress": {"survived_red_team": [], "validated_improvements": 0},
        "tasks": [],
    }
    text = _render(payload)
    throughput, progress = text.split("## Progress")
    assert "attempts: 18" in throughput
    assert "Validated improvements: 0" in progress
    assert "18" not in progress
