"""Which signals share a physical unit, and the four ways a topology can be wrong.

The module under test holds no statistics and makes no detection decision. It holds a *claim*:
that these signals are instrumented on the same piece of plant. Everything worth testing about it
is therefore about the claim's integrity — that it is total, that it is a partition, that it
matches the corpus it says it matches, and that it cannot be edited after construction — plus the
audit path that lets a domain expert check the claim by eye.

The fixtures below are deliberately tiny and hand-built. The real HAI map is exercised separately
in `test_hai_topology.py`, which skips when the git-ignored corpus is absent; these tests must
pass on a fresh clone, so nothing here reads a corpus.
"""

import re
from pathlib import Path

import pytest

from phos.atlas import (
    SCHEMA_VERSION,
    Subsystem,
    SubsystemMap,
    TopologyError,
    load_topology,
    render_topology,
)

PUMP = Subsystem(
    subsystem_id="pump",
    label="Feedwater pump",
    signals=frozenset({"FLOW", "SPEED"}),
    source="Figure 2 of the fictional manual.",
)
TANK = Subsystem(
    subsystem_id="tank",
    label="Return water tank",
    signals=frozenset({"LEVEL"}),
    source="Figure 3 of the fictional manual.",
)
CORPUS = ["FLOW", "SPEED", "LEVEL"]


def write_topology(directory: Path, body: str) -> Path:
    """Write a topology file into ``directory`` and return its path."""
    path = directory / "topology.toml"
    path.write_text(body, encoding="utf-8")
    return path


VALID_TOML = """
schema_version = 1
corpus = "fictional"

[[subsystems]]
subsystem_id = "pump"
label = "Feedwater pump"
source = "Figure 2 of the fictional manual."
signals = ["FLOW", "SPEED"]

[[subsystems]]
subsystem_id = "tank"
label = "Return water tank"
source = "Figure 3 of the fictional manual."
signals = ["LEVEL"]
"""


# --------------------------------------------------------------------------------------------
# Subsystem
# --------------------------------------------------------------------------------------------


def test_a_subsystem_is_frozen_and_hashable() -> None:
    with pytest.raises(ValueError, match="frozen"):
        PUMP.subsystem_id = "other"  # type: ignore[misc]
    assert len({PUMP, TANK, PUMP}) == 2


def test_a_subsystem_refuses_blank_identity_fields() -> None:
    with pytest.raises(ValueError, match="at least 1 character"):
        Subsystem(subsystem_id="", label="X", source="somewhere", signals=frozenset({"A"}))
    with pytest.raises(ValueError, match="at least 1 character"):
        Subsystem(subsystem_id="x", label="", source="somewhere", signals=frozenset({"A"}))
    with pytest.raises(ValueError, match="at least 1 character"):
        Subsystem(subsystem_id="x", label="X", source="", signals=frozenset({"A"}))


def test_a_subsystem_source_may_not_be_whitespace() -> None:
    # A blank-looking source defeats the whole audit path, so it is refused like an empty one.
    with pytest.raises(ValueError, match="source"):
        Subsystem(subsystem_id="x", label="X", source="   ", signals=frozenset({"A"}))


# --------------------------------------------------------------------------------------------
# SubsystemMap — the happy path and the API contract
# --------------------------------------------------------------------------------------------


def test_a_map_over_a_covered_corpus_constructs() -> None:
    topology = SubsystemMap([PUMP, TANK], CORPUS)
    assert len(topology) == 2
    assert [s.subsystem_id for s in topology] == ["pump", "tank"]


def test_every_signal_round_trips_through_its_subsystem() -> None:
    # Acceptance criterion 2: signals_in(subsystem_for(k).id) contains k, for every k.
    topology = SubsystemMap([PUMP, TANK], CORPUS)
    for signal in CORPUS:
        owner = topology.subsystem_for(signal)
        assert signal in topology.signals_in(owner.subsystem_id)


def test_subsystem_for_refuses_a_signal_outside_the_corpus() -> None:
    topology = SubsystemMap([PUMP, TANK], CORPUS)
    with pytest.raises(TopologyError, match="'PRESSURE'"):
        topology.subsystem_for("PRESSURE")


def test_signals_in_refuses_an_unknown_subsystem() -> None:
    topology = SubsystemMap([PUMP, TANK], CORPUS)
    with pytest.raises(TopologyError, match="'turbine'"):
        topology.signals_in("turbine")


def test_a_map_is_immutable_through_every_public_route() -> None:
    # Acceptance criterion 5. Three ways a caller might try to edit a constructed map.
    topology = SubsystemMap([PUMP, TANK], CORPUS)

    with pytest.raises(AttributeError):
        topology.subsystems = ()  # type: ignore[misc]

    # The tuple of subsystems is a copy of nothing the map consults again, and a Subsystem is
    # frozen, so there is no reachable mutable state.
    assert isinstance(topology.subsystems, tuple)
    with pytest.raises(AttributeError):
        topology.subsystems.append(PUMP)  # type: ignore[attr-defined]

    # signals_in hands back a frozenset, which has no mutation API at all.
    assert isinstance(topology.signals_in("pump"), frozenset)


def test_construction_copies_its_inputs_so_a_later_edit_cannot_reach_it() -> None:
    declared = [PUMP, TANK]
    topology = SubsystemMap(declared, CORPUS)
    declared.clear()
    assert len(topology) == 2


# --------------------------------------------------------------------------------------------
# The four construction invariants (§3.4), plus the one the API contract implies
# --------------------------------------------------------------------------------------------


def test_an_unassigned_corpus_signal_is_refused_and_named() -> None:
    with pytest.raises(TopologyError) as caught:
        SubsystemMap([PUMP], ["FLOW", "SPEED", "LEVEL", "PRESSURE"])
    message = str(caught.value)
    assert "not assigned to any subsystem" in message
    assert "'LEVEL'" in message
    assert "'PRESSURE'" in message


def test_a_doubly_assigned_signal_is_refused_and_both_owners_named() -> None:
    overlapping = Subsystem(
        subsystem_id="tank",
        label="Return water tank",
        signals=frozenset({"LEVEL", "FLOW"}),
        source="Figure 3 of the fictional manual.",
    )
    with pytest.raises(TopologyError) as caught:
        SubsystemMap([PUMP, overlapping], CORPUS)
    message = str(caught.value)
    assert "more than one subsystem" in message
    assert "'FLOW'" in message
    assert "pump" in message
    assert "tank" in message


def test_a_phantom_signal_is_refused_and_named() -> None:
    with pytest.raises(TopologyError) as caught:
        SubsystemMap([PUMP, TANK], ["FLOW", "SPEED"])
    message = str(caught.value)
    assert "not present in the corpus" in message
    assert "'LEVEL'" in message


def test_an_empty_subsystem_is_refused_and_named() -> None:
    empty = Subsystem(
        subsystem_id="ghost",
        label="Nothing at all",
        signals=frozenset(),
        source="Nowhere.",
    )
    with pytest.raises(TopologyError) as caught:
        SubsystemMap([PUMP, TANK, empty], CORPUS)
    assert "'ghost'" in str(caught.value)
    assert "no signals" in str(caught.value)


def test_two_subsystems_may_not_share_an_identifier() -> None:
    # Not one of the four in §3.4, but signals_in(subsystem_id) is ill-defined without it.
    twin = Subsystem(
        subsystem_id="pump",
        label="A different pump",
        signals=frozenset({"LEVEL"}),
        source="Figure 4 of the fictional manual.",
    )
    with pytest.raises(TopologyError) as caught:
        SubsystemMap([PUMP, twin], CORPUS)
    assert "'pump'" in str(caught.value)
    assert "more than once" in str(caught.value)


def test_the_empty_map_over_the_empty_corpus_is_legal() -> None:
    # Degenerate but coherent: nothing to assign, nothing unassigned. Refusing it would make the
    # invariants inconsistent with each other.
    assert len(SubsystemMap([], [])) == 0


# --------------------------------------------------------------------------------------------
# Loading a declaration file
# --------------------------------------------------------------------------------------------


def test_a_valid_file_loads_into_a_map(tmp_path: Path) -> None:
    topology = load_topology(write_topology(tmp_path, VALID_TOML), CORPUS, corpus="fictional")
    assert [s.subsystem_id for s in topology] == ["pump", "tank"]
    assert topology.signals_in("pump") == frozenset({"FLOW", "SPEED"})


def test_a_file_for_a_different_corpus_is_refused(tmp_path: Path) -> None:
    # Acceptance-criterion-adjacent: this is what catches a topology pointed at the wrong corpus,
    # which would otherwise fail as a confusing wall of phantom and unassigned signals.
    with pytest.raises(TopologyError) as caught:
        load_topology(write_topology(tmp_path, VALID_TOML), CORPUS, corpus="hai")
    assert "'fictional'" in str(caught.value)
    assert "'hai'" in str(caught.value)


def test_an_unsupported_schema_version_is_refused(tmp_path: Path) -> None:
    body = VALID_TOML.replace("schema_version = 1", "schema_version = 99")
    with pytest.raises(TopologyError) as caught:
        load_topology(write_topology(tmp_path, body), CORPUS, corpus="fictional")
    assert "99" in str(caught.value)
    assert str(SCHEMA_VERSION) in str(caught.value)


def test_a_malformed_file_is_refused_with_its_path(tmp_path: Path) -> None:
    body = VALID_TOML.replace('label = "Feedwater pump"\n', "")
    path = write_topology(tmp_path, body)
    with pytest.raises(TopologyError) as caught:
        load_topology(path, CORPUS, corpus="fictional")
    assert str(path) in str(caught.value)


def test_unreadable_toml_is_refused_with_its_path(tmp_path: Path) -> None:
    path = write_topology(tmp_path, "this is not = = toml")
    with pytest.raises(TopologyError) as caught:
        load_topology(path, CORPUS, corpus="fictional")
    assert str(path) in str(caught.value)


def test_a_declaration_error_names_the_file_it_came_from(tmp_path: Path) -> None:
    # A raise from deep in SubsystemMap is useless if the operator cannot tell which of several
    # topology files produced it.
    path = write_topology(tmp_path, VALID_TOML)
    with pytest.raises(TopologyError) as caught:
        load_topology(path, ["FLOW", "SPEED"], corpus="fictional")
    assert str(path) in str(caught.value)
    assert "'LEVEL'" in str(caught.value)


# --------------------------------------------------------------------------------------------
# The audit path (§5.6)
# --------------------------------------------------------------------------------------------


def test_the_rendering_shows_every_subsystem_label_source_and_member() -> None:
    rendered = render_topology(SubsystemMap([PUMP, TANK], CORPUS))
    for expected in [
        "pump",
        "Feedwater pump",
        "Figure 2 of the fictional manual.",
        "FLOW",
        "SPEED",
        "tank",
        "Return water tank",
        "Figure 3 of the fictional manual.",
        "LEVEL",
    ]:
        assert expected in rendered
    assert "3 signal" in rendered


def test_the_rendering_lists_members_in_sorted_order() -> None:
    # An expert checking by eye needs a stable order, not insertion order.
    rendered = render_topology(SubsystemMap([PUMP, TANK], CORPUS))
    assert re.search(r"FLOW.*SPEED", rendered, flags=re.DOTALL)


def test_the_rendering_of_an_empty_map_says_so() -> None:
    assert "no subsystems" in render_topology(SubsystemMap([], []))
