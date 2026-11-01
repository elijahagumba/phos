"""The GRFICS generator reads the registry, refuses held-out, and never invents a run (ADR 0400).

These tests exercise the refusal surface rather than the simulation, which is not built yet. The
properties they pin are the ones ADR 0144 and ADR 0400 make mandatory: the design comes from the
registry, the held-back half is unreachable, a moved pin stops the run, and a note that does not
describe runs is refused rather than guessed at.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "grfics" / "generate_corpus.py"
_spec = importlib.util.spec_from_file_location("grfics_generate_corpus", _SCRIPT)
assert _spec is not None and _spec.loader is not None
grfics = importlib.util.module_from_spec(_spec)
# Register before executing: a `@dataclass` resolves its annotations through `sys.modules`, and a
# module that is not registered there fails with `AttributeError: 'NoneType' object has no ...`.
sys.modules[_spec.name] = grfics
_spec.loader.exec_module(grfics)


def test_the_development_entries_parse_into_ten_runs() -> None:
    runs = grfics.registry_runs(grfics.DEV_ENTRY)
    assert len(runs) == 10
    assert runs[0].seed == 97201
    assert runs[-1].seed == 97210


def test_the_bridge_entry_is_a_different_corpus_with_the_same_run_ids() -> None:
    """ADR 0401: the same design, a different topology, and never pooled with grfics-v3."""
    bridge = {run.seed for run in grfics.registry_runs("grfics-v3-bridge")}
    declared = {run.seed for run in grfics.registry_runs("grfics-v3")}
    assert bridge == declared, "the bridge corpus must carry the declared run ids"
    assert grfics.DEV_ENTRY == "grfics-v3-bridge"


def test_the_bridge_entry_says_what_topology_it_drops() -> None:
    """ADR 0401: the entry must name the difference, or a reader could take it for grfics-v3."""
    import json

    raw = json.loads(grfics.REGISTRY.read_text(encoding="utf-8"))
    entry = next(x for x in raw["datasets"] if x["name"] == "grfics-v3-bridge")
    note = entry["status_note"].lower()
    # The four things a reader must be told: what it is not, why, what is missing, and the
    # instruction not to pool it with the declared corpus.
    assert "not grfics-v3" in note
    assert "macvlan" in note
    assert "dmz" in note and "drops" in note
    assert "never be pooled" in note
    assert any("not a substitute" in c.lower() for c in entry["caveats"])


def test_the_frozen_pair_is_present_and_differs_only_by_cause() -> None:
    """97201 and 97206 are the same target and event shape with different causes (ADR 0400)."""
    runs = {run.seed: run for run in grfics.registry_runs(grfics.DEV_ENTRY)}
    physical, cyber = runs[97201], runs[97206]
    assert (physical.mode, physical.target) == (cyber.mode, cyber.target)
    assert physical.cause == "physical"
    assert cyber.cause == "cyber"


def test_no_target_carries_prose_punctuation() -> None:
    for run in grfics.registry_runs(grfics.DEV_ENTRY):
        assert run.target == run.target.rstrip("."), run.target
        assert " " not in run.target


def test_every_cause_is_one_the_design_names() -> None:
    for run in grfics.registry_runs(grfics.DEV_ENTRY):
        assert run.cause in {"physical", "cyber", "quiet"}


def test_the_held_out_entry_is_refused_by_name() -> None:
    with pytest.raises(grfics.RefusedError, match="held back"):
        grfics.registry_runs(grfics.HELD_OUT_ENTRY)


def test_the_held_out_cli_role_refuses_with_a_nonzero_code() -> None:
    assert grfics.main(["held-out"]) == 2


def test_an_unknown_entry_is_refused() -> None:
    with pytest.raises(grfics.RefusedError, match="no registry entry"):
        grfics.registry_runs("grfics-does-not-exist")


def test_a_note_without_runs_is_refused_rather_than_guessed() -> None:
    assert grfics._parse_runs("no seeds are declared in this sentence") == ()


def test_the_seven_devices_adr_0144_names_are_declared_in_one_place() -> None:
    assert len(grfics.REQUIRED_DEVICES) == 7
    assert grfics.REQUIRED_DEVICES[:4] == ("flow_1", "flow_2", "flow_3", "flow_4")
    assert grfics.REQUIRED_DEVICES[4:] == ("analyzer_a", "analyzer_b", "analyzer_c")


def test_the_pin_and_the_licence_digest_are_the_ones_adr_0144_recorded() -> None:
    assert grfics.GRFICS_COMMIT == "37bdf101f3ad0706a7595bd01d696ce7b84db436"
    assert (
        grfics.GRFICS_LICENSE_SHA256
        == "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad"
    )


def test_the_checkout_lives_under_data_so_git_never_sees_it() -> None:
    root = _SCRIPT.parents[2]
    assert grfics.GRFICS_DIR.is_relative_to(root / "data")
    assert grfics.DEV_DIR.is_relative_to(root / "data")
