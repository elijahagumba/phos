"""The graded plant model (ADR 0130, ADR 0133) on the test tank."""

import numpy
import pytest
import tests.atlas.plant_map_fixture as tank
from tests.atlas.test_plant_map import SETTINGS, _fit

from phos.atlas.consistency import TrainFile
from phos.atlas.interventions import IntervenedLink
from phos.atlas.network_links import NetworkClaim
from phos.atlas.plant_map_fit import fit_map
from phos.atlas.plant_map_model import PlantMap
from phos.atlas.plant_map_naming import Verdict, name_instrument
from phos.atlas.plant_model import (
    Grade,
    declared_pairs,
    grade_links,
    halves,
    intervened_pairs,
    network_pairs,
    stable_pairs,
    trusted_drivers,
    trusted_map,
)

#: The tank's plumbing, as a drawing would state it.
DRAWING = (("inflow", "level"), ("outflow", "level"), ("valve", "inflow"), ("level", "quality"))


@pytest.fixture(scope="module")
def train() -> tank.Run:
    return tank.simulate(12_000, seed=1)


def _files(run: tank.Run) -> list[TrainFile]:
    return [TrainFile(values=run.reported, attack=numpy.zeros(run.reported.shape[0], bool))]


def test_declared_pairs_come_from_loops_and_couplings() -> None:
    pairs = declared_pairs(tank.roles(), DRAWING)
    assert ("level", "valve") in pairs and ("target", "valve") in pairs
    assert set(DRAWING) <= pairs


def test_b_and_c_pairs_and_a_narrowed_claim() -> None:
    assert intervened_pairs([IntervenedLink("target", "valve", 4, 4, 0)]) == {("target", "valve")}
    claims = [
        NetworkClaim("plc", "level", ("valve", "pump"), 10, narrowed="valve"),
        NetworkClaim("plc", "flow", ("valve", "pump"), 10),
    ]
    assert network_pairs(claims) == {("level", "valve"), ("flow", "valve"), ("flow", "pump")}


def test_halves_split_one_file_in_two(train: tank.Run) -> None:
    first, second = halves(_files(train))
    assert first[0].values.shape[0] + second[0].values.shape[0] == train.reported.shape[0]


def test_every_learned_link_gets_its_grades(train: tank.Run) -> None:
    plant = _fit(train)
    first, second = (_fit_files(h) for h in halves(_files(train)))
    graded = grade_links(
        plant, declared_pairs(tank.roles(), DRAWING), stable=stable_pairs(first, second)
    )
    by_pair = {(g.driver, g.target): g for g in graded}
    assert by_pair[("inflow", "level")].best is Grade.DECLARED
    assert all(g.best in {None, Grade.DECLARED, Grade.STABLE} for g in graded)


def _fit_files(files: list[TrainFile]) -> PlantMap:
    return fit_map(files, tank.NAMES, tank.roles(), 1.0, SETTINGS)


def test_the_trusted_map_names_the_lying_level_and_cannot_place_what_it_has_no_evidence_for(
    train: tank.Run,
) -> None:
    plant = _fit(train)
    allowed = trusted_drivers(plant, declared_pairs(tank.roles(), DRAWING))
    trusted = trusted_map(_files(train), tank.NAMES, tank.roles(), 1.0, allowed, SETTINGS)
    assert tank.OUTFLOW not in trusted.targets  # nothing declared drives it
    run = tank.simulate(6_000, seed=3, liar=(3_000, 5_000, 1.0))
    named = [
        name_instrument(trusted, run.reported, row=r, column=tank.LEVEL, onset=3_000)
        for r in range(3_100, 4_200, 100)
    ]
    hits = [n for n in named if n.verdict is Verdict.NAMED and n.instrument == tank.LEVEL]
    assert len(hits) * 2 >= len(named)
    assert all(n.instrument in {None, tank.LEVEL} for n in named)
    outflow = name_instrument(trusted, run.reported, row=3_500, column=tank.OUTFLOW, onset=3_000)
    assert outflow.verdict is Verdict.NO_MODEL
