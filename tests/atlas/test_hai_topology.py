"""The authored HAI map, checked against the corpus it claims to describe.

`test_topology.py` proves the machinery on hand-built fixtures and must pass on a fresh clone.
This module proves the *claim* — that `data/hai/topology.toml` is a total, non-overlapping
partition of the signals HAI 21.03 actually contains — and therefore needs the git-ignored corpus.
It skips cleanly when the corpus is absent.

The signal set every assertion here runs against is read out of the loaded corpus rather than
written down, so a corpus revision that adds, drops or renames a column fails these tests instead
of silently leaving a signal unmapped. Both HAI files are checked, not just the labelled one: the
train and test captures are separate downloads, and BATADAL has already demonstrated in this
project that two files of one corpus can disagree about their own column names.
"""

import json
from functools import cache
from pathlib import Path

import pytest

from phos.atlas import Subsystem, load_topology, render_topology
from phos.eval import LabelledCsvAdapter

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TOPOLOGY_PATH = DATA_DIR / "hai" / "topology.toml"
MANIFEST_PATH = DATA_DIR / "hai" / "manifest.json"


def manifests() -> list[tuple[str, dict[str, object]]]:
    """Return every HAI corpus file on disk, as ``(role, manifest fields)`` pairs.

    The HAI manifest describes the labelled test capture and carries its attack-free training
    counterpart under ``train``. Both are separate downloads, so both are checked.
    """
    if not (TOPOLOGY_PATH.is_file() and MANIFEST_PATH.is_file()):
        return []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    candidates: list[tuple[str, dict[str, object]]] = [("test", manifest)]
    if "train" in manifest:
        candidates.append(("train", manifest["train"]))
    return [
        (role, fields) for role, fields in candidates if (DATA_DIR / str(fields["path"])).is_file()
    ]


AVAILABLE = manifests()

pytestmark = pytest.mark.skipif(
    not AVAILABLE,
    reason=(
        f"HAI corpus not present; run scripts/fetch_datasets.py --all (see {DATA_DIR}/README.md)"
    ),
)

ROLES = [role for role, _ in AVAILABLE]


@cache
def corpus_signals(role: str) -> frozenset[str]:
    """Return the signal keys one HAI file actually contains, as PHOS loads them.

    Read from the corpus rather than hardcoded, per acceptance criterion 1. A signal key is the
    `Observation.feature` `LabelledCsvAdapter` produces, which is the CSV column name — the same
    string the topology file declares.

    Cached: loading a corpus is the expensive part of this module and every test wants the set.
    """
    fields = dict(next(entry for name, entry in AVAILABLE if name == role))
    adapter_fields = {
        key: value
        for key, value in fields.items()
        if key in LabelledCsvAdapter.model_fields and key != "path"
    }
    dataset = LabelledCsvAdapter.model_validate(
        {**adapter_fields, "path": str(DATA_DIR / str(fields["path"]))}
    ).load()
    return frozenset(observation.feature for observation in dataset.observations)


@pytest.mark.parametrize("role", ROLES)
def test_the_hai_topology_is_total_over_the_corpus_it_describes(role: str) -> None:
    # Acceptance criterion 1, and the headline: construction itself enforces totality, a
    # partition, no phantom signals and no empty subsystem, so a map that loads at all has
    # already satisfied all four. What this asserts is that the *authored* file does.
    topology = load_topology(TOPOLOGY_PATH, corpus_signals(role), corpus="hai")

    assigned = {signal for subsystem in topology for signal in subsystem.signals}
    assert assigned == corpus_signals(role)


@pytest.mark.parametrize("role", ROLES)
def test_every_hai_signal_round_trips_through_its_subsystem(role: str) -> None:
    # Acceptance criterion 2, on the real signal set rather than a fixture.
    topology = load_topology(TOPOLOGY_PATH, corpus_signals(role), corpus="hai")
    for signal in sorted(corpus_signals(role)):
        owner = topology.subsystem_for(signal)
        assert signal in topology.signals_in(owner.subsystem_id)


def test_the_hai_files_agree_on_their_signal_set() -> None:
    # BATADAL's train and test files disagree on column names (' L_T1' vs 'L_T1'), which made a
    # model fitted on one and scored on the other match nothing and report a silent zero recall.
    # One topology serves both HAI files, so the same disagreement would make one of them fail
    # construction. Asserted directly so the cause is named rather than inferred from a raise.
    if len(ROLES) < 2:
        pytest.skip("only one HAI file present; nothing to compare")
    assert corpus_signals("test") == corpus_signals("train")


def test_every_hai_subsystem_names_the_documentation_it_came_from() -> None:
    # Acceptance criterion 4. `Subsystem` already refuses a blank or whitespace source, so this
    # asserts something stronger: that each source is substantive enough to be checkable, and
    # that none of them is the one answer §2 forbids.
    topology = load_topology(TOPOLOGY_PATH, corpus_signals(ROLES[0]), corpus="hai")
    for subsystem in topology:
        assert len(subsystem.source.split()) >= 20, subsystem.subsystem_id
        assert "manual" in subsystem.source.lower(), subsystem.subsystem_id
        assert "correlat" not in subsystem.source.lower().replace("uncorrelat", ""), (
            f"{subsystem.subsystem_id} cites co-movement as its source, which is the circular "
            "derivation ADR 0010 forbids"
        )


def test_the_granularity_is_process_level_for_plant_and_per_machine_for_simulation() -> None:
    # Pins the granularity decision recorded in ADR 0010 so that a later change to it is a
    # deliberate edit to a failing test rather than a silent re-partition. The three real
    # processes are whole because HAI's manual documents no point-to-unit partition for them;
    # P4 is split three ways because the manual names a machine in every P4 point's description.
    topology = load_topology(TOPOLOGY_PATH, corpus_signals(ROLES[0]), corpus="hai")
    sizes = {s.subsystem_id: len(s.signals) for s in topology}
    assert sizes == {
        "p1-boiler": 38,
        "p2-turbine": 22,
        "p3-water-treatment": 7,
        "p4-steam-turbine": 7,
        "p4-hydro-turbine": 4,
        "p4-power-grid": 1,
    }
    assert sum(sizes.values()) == 79


def test_the_hai_map_renders_completely_for_a_domain_expert() -> None:
    # Acceptance criterion 6: this is the audit path for the declared-not-inferred policy, so it
    # has to show everything an expert would need to say "no, that transmitter is on the other
    # tank" — every subsystem, its label, its source, and every one of its signals.
    topology = load_topology(TOPOLOGY_PATH, corpus_signals(ROLES[0]), corpus="hai")
    rendered = render_topology(topology)

    for subsystem in topology:
        assert subsystem.subsystem_id in rendered
        assert subsystem.label in rendered
        for signal in subsystem.signals:
            assert signal in rendered
    for signal in corpus_signals(ROLES[0]):
        assert signal in rendered
    assert "79 signal(s) across 6 subsystem(s)" in rendered


def test_a_topology_loaded_against_the_wrong_corpus_is_refused() -> None:
    # The realistic operator error: pointing HAI's topology at BATADAL's signal set. It fails on
    # the corpus identifier, before it can fail as 122 phantom and 43 unassigned signals.
    with pytest.raises(ValueError, match="batadal"):
        load_topology(TOPOLOGY_PATH, corpus_signals(ROLES[0]), corpus="batadal")


def test_the_declared_subsystems_are_the_frozen_type() -> None:
    topology = load_topology(TOPOLOGY_PATH, corpus_signals(ROLES[0]), corpus="hai")
    assert all(isinstance(subsystem, Subsystem) for subsystem in topology)
