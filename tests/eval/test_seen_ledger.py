"""ADR 0117's ledger in ``data/registry.json``: what each Atlas corpus is for, and who has seen it.

The five judging corpora have all been scored by ``atlas-v1-consistency`` (ADR 0116), so none of
them can judge a claim about unseen data again. HAI 20.07 is the only one the arena may iterate
on; the other four are kept from agents and read only at a promotion gate.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from scripts.fetch_datasets import DATA_ROLES, DatasetEntry, load_registry

from phos.eval.build_declaration import DECLARED_HELD_OUT

JUDGING: tuple[str, ...] = ("hai-20.07", "hai-21.03", "hai-22.04", "hai-23.05", "batadal")


def atlas_entries() -> list[DatasetEntry]:
    return [entry for entry in load_registry().datasets if entry.domain == "ATLAS"]


def test_every_judging_corpus_is_seen_and_none_is_held_out() -> None:
    registry = load_registry()
    for name in JUDGING:
        entry = registry.by_name(name)
        assert entry.seen, name
        assert entry.role != "held-out", name


def test_hai_20_07_is_the_only_development_judging_corpus() -> None:
    registry = load_registry()
    roles = {name: registry.by_name(name).role for name in JUDGING}
    assert roles == {
        "hai-20.07": "development",
        "hai-21.03": "validation",
        "hai-22.04": "validation",
        "hai-23.05": "validation",
        "batadal": "validation",
    }


def test_the_integrated_hai_slice_shares_hai_21_03s_role() -> None:
    registry = load_registry()
    assert registry.by_name("hai").role == registry.by_name("hai-21.03").role


def test_haiend_is_seen_by_proxy_and_has_no_role() -> None:
    entry = load_registry().by_name("haiend-23.05")
    assert entry.role is None
    assert any("proxy" in record.by for record in entry.seen)


def test_the_held_out_bank_is_the_declared_list() -> None:
    """Held-out names follow the registry, including the TU Wien half from ADR 0163."""
    held_out = [entry.name for entry in atlas_entries() if entry.role == "held-out"]
    assert held_out == list(DECLARED_HELD_OUT)


def test_every_role_is_a_declared_tier() -> None:
    for entry in atlas_entries():
        assert entry.role is None or entry.role in DATA_ROLES, entry.name


def an_entry(**changes: object) -> DatasetEntry:
    base = load_registry().by_name("batadal").model_dump()
    return DatasetEntry.model_validate(base | changes)


def test_a_held_out_corpus_with_a_seen_record_is_refused() -> None:
    seen = [{"by": "a detector", "evidence": "ADR 0000"}]
    with pytest.raises(ValidationError, match="cannot have been seen"):
        an_entry(role="held-out", seen=seen)


def test_an_unknown_role_is_refused() -> None:
    with pytest.raises(ValidationError, match="unknown role"):
        an_entry(role="test")


def test_an_unseen_held_out_corpus_is_accepted() -> None:
    assert an_entry(role="held-out", seen=[]).role == "held-out"
