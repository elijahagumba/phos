"""Separation counts facts that bear opposite ways on the lead and the runner-up."""

from phos.reasoning.separation import separation_count


def test_only_a_fact_with_opposite_roles_counts() -> None:
    """Shared support does not separate. Each opposite fact counts once."""
    assert separation_count(["a", "b"], [], ["b"], ["a"]) == 1
    assert separation_count(["a"], ["c"], ["c"], ["a"]) == 2
    assert separation_count(["a"], [], ["a"], []) == 0
    assert separation_count([], [], [], []) == 0
