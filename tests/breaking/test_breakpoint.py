"""Reducing per-attack outcomes to the boundary each attack type crosses."""

from tests.breaking.conftest import ground_truth

from phos.breaking import FingerprintStatus, assess_fingerprint
from phos.breaking.breakpoint import breaking_points
from phos.breaking.outcome import AttackOutcome
from phos.breaking.truth import SignalExcursion, TrueStateVerdict
from phos.synth import PlantDescription
from phos.synth.attacks import AttackType, DifficultyLevel


def sweep_outcome(
    plant: PlantDescription,
    subtlety: float,
    *,
    detected: bool,
    dangerous: bool = False,
    attack_type: AttackType = AttackType.BLATANT,
    targets: tuple[str, ...] = ("pump_pct",),
) -> AttackOutcome:
    """One point on a sweep, with everything but the dial held fixed."""
    excursions: tuple[SignalExcursion, ...] = ()
    if dangerous:
        excursions = (
            SignalExcursion(
                signal="level_m",
                envelope_low=0.0,
                envelope_high=10.0,
                window_low=10.0,
                window_high=40.0,
                excess=30.0,
                margin=0.03,
            ),
        )
    return AttackOutcome(
        attack_id=f"{attack_type.value}-{subtlety}",
        attack_type=attack_type,
        subtlety=subtlety,
        difficulty=DifficultyLevel.for_subtlety(subtlety),
        detected=detected,
        n_alerts=1 if detected else 0,
        fingerprint=assess_fingerprint(
            ground_truth("x", attack_type, subtlety=subtlety, targets=targets), plant
        ),
        true_state=TrueStateVerdict(
            attack_id=f"{attack_type.value}-{subtlety}",
            dangerous=dangerous,
            excursions=excursions,
        ),
    )


def test_a_clean_sweep_reports_the_boundary_it_crossed(plant: PlantDescription) -> None:
    rows = breaking_points(
        [
            sweep_outcome(plant, 0.0, detected=True),
            sweep_outcome(plant, 0.3, detected=True),
            sweep_outcome(plant, 0.6, detected=False),
            sweep_outcome(plant, 0.9, detected=False),
        ]
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.caught_hardest == 0.3
    assert row.missed_easiest == 0.6
    assert row.monotone
    assert "breaks between 0.30 and 0.60" in row.describe()


def test_a_ragged_sweep_is_reported_as_ragged_rather_than_as_a_point(
    plant: PlantDescription,
) -> None:
    """Each band sits at a different hour of the plant's day; monotonicity is not guaranteed."""
    rows = breaking_points(
        [
            sweep_outcome(plant, 0.0, detected=True),
            sweep_outcome(plant, 0.3, detected=False),
            sweep_outcome(plant, 0.6, detected=True),
            sweep_outcome(plant, 0.9, detected=False),
        ]
    )
    row = rows[0]
    assert not row.monotone
    assert row.caught_hardest == 0.6
    assert row.missed_easiest == 0.3
    assert "ragged" in row.describe()


def test_a_type_caught_everywhere_does_not_claim_to_have_no_limit(
    plant: PlantDescription,
) -> None:
    rows = breaking_points(
        [sweep_outcome(plant, 0.0, detected=True), sweep_outcome(plant, 0.9, detected=True)]
    )
    row = rows[0]
    assert row.caught_everywhere
    assert row.missed_easiest is None
    assert "did not reach its limit" in row.describe()


def test_a_type_never_caught_is_named_as_a_whole_blind_spot(plant: PlantDescription) -> None:
    rows = breaking_points(
        [sweep_outcome(plant, 0.0, detected=False), sweep_outcome(plant, 0.9, detected=False)]
    )
    row = rows[0]
    assert row.blind_everywhere
    assert row.caught_hardest is None
    assert "no breaking point" in row.describe()


def test_the_inert_control_is_excluded_from_the_boundary(plant: PlantDescription) -> None:
    rows = breaking_points(
        [
            sweep_outcome(plant, 0.0, detected=True),
            sweep_outcome(plant, 1.0, detected=False),
        ]
    )
    row = rows[0]
    assert len(row.outcomes) == 1
    assert len(row.inert) == 1
    assert row.missed_easiest is None
    assert row.n_missed == 0


def test_a_detection_on_the_inert_control_is_counted_where_a_reader_will_see_it(
    plant: PlantDescription,
) -> None:
    rows = breaking_points(
        [sweep_outcome(plant, 0.0, detected=True), sweep_outcome(plant, 1.0, detected=True)]
    )
    assert rows[0].detected_inert == 1


def test_dangerous_misses_are_counted_on_the_row(plant: PlantDescription) -> None:
    rows = breaking_points(
        [
            sweep_outcome(plant, 0.6, detected=False, dangerous=True),
            sweep_outcome(plant, 0.9, detected=False),
        ]
    )
    assert rows[0].n_dangerous_misses == 1
    assert rows[0].n_missed == 2


def test_clean_and_caveated_results_never_share_a_row(plant: PlantDescription) -> None:
    """The same type on a drifting sensor and on a driftless one are two separate rows."""
    rows = breaking_points(
        [
            sweep_outcome(
                plant, 0.0, detected=True, attack_type=AttackType.LIAR, targets=("level_m",)
            ),
            sweep_outcome(
                plant, 0.3, detected=True, attack_type=AttackType.LIAR, targets=("steady_sensor",)
            ),
        ]
    )
    assert len(rows) == 2
    assert {row.fingerprint for row in rows} == {
        FingerprintStatus.CLEAN,
        FingerprintStatus.CAVEATED,
    }


def test_rows_are_ordered_deterministically(plant: PlantDescription) -> None:
    rows = breaking_points(
        [
            sweep_outcome(plant, 0.0, detected=True, attack_type=AttackType.STEALTH_DRIFT),
            sweep_outcome(plant, 0.0, detected=True, attack_type=AttackType.BLATANT),
        ]
    )
    assert [row.attack_type for row in rows] == [AttackType.BLATANT, AttackType.STEALTH_DRIFT]


def test_no_outcomes_yields_no_rows() -> None:
    assert breaking_points([]) == ()
