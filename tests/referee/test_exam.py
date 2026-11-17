"""`phos.referee.exam`: a frozen, hashed exam record, and building one from a seed pool."""

from __future__ import annotations

from pathlib import Path

import pytest

from phos.referee.exam import Exam, ExamEntry, ExamError, exam_hash, make_exam
from phos.referee.seeds import SeedEntry, SeedPool, SeedVault


def _vault_with_dev_seeds(tmp_path: Path, count: int) -> SeedVault:
    vault = SeedVault(
        {
            SeedPool.DEV: tmp_path / "dev.seedvault.json",
            SeedPool.PUBLIC: tmp_path / "public.seedvault.json",
            SeedPool.PRIVATE: tmp_path / "private.seedvault.json",
            SeedPool.RETIRED: tmp_path / "retired.seedvault.json",
        }
    )
    vault.add(SeedPool.DEV, [SeedEntry(family="level_flow", seed=seed) for seed in range(count)])
    return vault


def test_exam_id_is_a_function_of_its_content() -> None:
    entry = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    exam = Exam.build([entry], "s6.0", "abc123")
    assert exam.exam_id == exam_hash([entry], "s6.0", "abc123")


def test_same_entries_give_the_same_id_every_time() -> None:
    entry = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    first = Exam.build([entry], "s6.0", "abc123")
    second = Exam.build([entry], "s6.0", "abc123")
    assert first.exam_id == second.exam_id


def test_a_different_scorer_version_gives_a_different_id() -> None:
    entry = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    first = Exam.build([entry], "s6.0", "abc123")
    second = Exam.build([entry], "s6.1", "abc123")
    assert first.exam_id != second.exam_id


def test_reordering_entries_changes_the_id() -> None:
    a = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    b = ExamEntry(family="level_flow", seed=2, hours=4.0, event_seed=2, pool=SeedPool.DEV)
    forward = Exam.build([a, b], "s6.0", None)
    backward = Exam.build([b, a], "s6.0", None)
    assert forward.exam_id != backward.exam_id


def test_round_trips_through_json() -> None:
    entry = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    exam = Exam.build([entry], "s6.0", "abc123")
    restored = Exam.from_json(exam.to_json())
    assert restored == exam


def test_editing_an_entry_without_changing_the_id_is_refused() -> None:
    entry = ExamEntry(family="level_flow", seed=1, hours=4.0, event_seed=1, pool=SeedPool.DEV)
    exam = Exam.build([entry], "s6.0", "abc123")
    tampered = exam.to_json().replace('"seed": 1', '"seed": 2')
    with pytest.raises(ExamError, match="does not match"):
        Exam.from_json(tampered)


def test_make_exam_draws_size_entries_in_pool_order(tmp_path: Path) -> None:
    vault = _vault_with_dev_seeds(tmp_path, count=5)
    exam = make_exam(vault, SeedPool.DEV, "s6.0", None, size=3, hours=4.0)
    assert len(exam.entries) == 3
    assert [entry.seed for entry in exam.entries] == sorted(entry.seed for entry in exam.entries)
    assert all(entry.pool is SeedPool.DEV for entry in exam.entries)
    assert all(entry.event_seed == entry.seed for entry in exam.entries)


def test_make_exam_refuses_a_pool_smaller_than_the_requested_size(tmp_path: Path) -> None:
    vault = _vault_with_dev_seeds(tmp_path, count=2)
    with pytest.raises(ExamError, match="fewer"):
        make_exam(vault, SeedPool.DEV, "s6.0", None, size=5)


def test_make_exam_is_deterministic_for_the_same_pool_file(tmp_path: Path) -> None:
    vault = _vault_with_dev_seeds(tmp_path, count=4)
    first = make_exam(vault, SeedPool.DEV, "s6.0", "abc", size=4)
    second = make_exam(vault, SeedPool.DEV, "s6.0", "abc", size=4)
    assert first.exam_id == second.exam_id
