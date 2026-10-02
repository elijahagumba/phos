"""Whether an attack can be found by looking for the machinery instead of for the attack.

This is the most important file in D2, and it is the one to distrust first if Atlas ever scores
suspiciously well on this data. Everything else here builds adversaries; this checks that the
adversaries do not announce themselves.

The failure being guarded against is specific. If a manipulated run differs from a normal one by
*anything except the manipulation* — a formatting difference, a timing difference, an ordering
difference, a variance that collapses, a value that leaves a range no normal value leaves — then a
detector can learn that artefact instead of learning the attack, and every detection number
measured on this corpus afterwards is worthless. Worse, it is worthless in the flattering
direction.

Four claims are checked, in increasing order of how hard they are to fake:

1. **Zero magnitude is bit-identical.** A subtlety of 1.0 produces a run whose every reported value
   and every true value equals the clean run's, exactly. Not close — equal.
2. **The dial is monotone.** At a *fixed window*, raising subtlety never increases the departure,
   and drives it to zero. The window has to be fixed: the shipped battery puts each difficulty at
   a different hour, and the plant's own rhythm then dominates the comparison.
3. **A minimal attack is statistically indistinguishable from normal.** A two-sample
   Kolmogorov-Smirnov test at the 5% level cannot separate the attacked window from the clean one.
4. **The corpus carries no structural tell.** Same row count, same columns, same decimal places,
   same timestamp spacing, same frame count, same value formatting — so nothing about the *file*
   says which one has attacks in it.
"""

import math
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import pytest
from tests.synth.attacks.conftest import (
    CHLORINE_DOSE,
    CLEARWELL_LEVEL,
    INTAKE_SPEED,
    LEVEL_SETPOINT,
    LEVEL_SETPOINT_CHANGE,
    PLANT,
    RAW_INFLOW,
    a_spec,
)
from tests.synth.attacks.test_generate import BASE

from phos.synth.attacks.battery import AttackDatasetConfig
from phos.synth.attacks.generate import (
    CAPTURE_FILE,
    TELEMETRY_FILE,
    generate_attack_dataset,
    telemetry_lines,
)
from phos.synth.attacks.inject import inject
from phos.synth.attacks.spec import AttackPlan, AttackType

# One fixed window for every sweep in this file, so the only thing that varies is the dial.
WINDOW_START = 6.0
WINDOW_HOURS = 3.0
FIRST = int(WINDOW_START * 120)
LAST = int((WINDOW_START + WINDOW_HOURS) * 120)

KS_CRITICAL_AT_5_PERCENT = 1.358
"""The Kolmogorov distribution's two-sample critical coefficient at alpha = 0.05. The statistic is
compared against ``c * sqrt((n + m) / (n * m))``; textbook, closed form, and no new dependency."""


def a_plan(attack_type: AttackType, subtlety: float, **fields: object) -> AttackPlan:
    """Return a plan of one type at one subtlety, always in the same window."""
    return AttackPlan.model_validate(
        {
            "attack_id": f"{attack_type.value.lower()}-{subtlety}",
            "type": attack_type,
            "subtlety": subtlety,
            "start_hours": WINDOW_START,
            "duration_hours": WINDOW_HOURS,
            **fields,
        }
    )


EVERY_KIND: tuple[tuple[AttackType, dict[str, object]], ...] = (
    (AttackType.BLATANT, {"target": INTAKE_SPEED}),
    (AttackType.STEALTH_DRIFT, {"target": CHLORINE_DOSE}),
    (AttackType.CORRELATION_BREAK, {"target": RAW_INFLOW, "reference": INTAKE_SPEED}),
    (AttackType.LIAR, {"target": CLEARWELL_LEVEL, "reference": LEVEL_SETPOINT}),
    (AttackType.MIMIC, {"target": LEVEL_SETPOINT, "mimics": LEVEL_SETPOINT_CHANGE}),
    (AttackType.ROGUE_COMMAND, {"target": LEVEL_SETPOINT, "issuer": "scada"}),
    (
        AttackType.MIMIC_COMMAND,
        {"target": LEVEL_SETPOINT, "issuer": "hmi", "mimics": LEVEL_SETPOINT_CHANGE},
    ),
)

IDS = [kind.value for kind, _ in EVERY_KIND]


def ks_statistic(first: Sequence[float], second: Sequence[float]) -> float:
    """Return the two-sample Kolmogorov-Smirnov statistic: the largest gap between the two ECDFs."""
    left, right = sorted(first), sorted(second)
    merged = sorted({*left, *right})
    largest = 0.0
    for value in merged:
        low = sum(1 for item in left if item <= value) / len(left)
        high = sum(1 for item in right if item <= value) / len(right)
        largest = max(largest, abs(low - high))
    return largest


def ks_separates(first: Sequence[float], second: Sequence[float]) -> bool:
    """Return whether a KS test at the 5% level can tell the two samples apart."""
    n, m = len(first), len(second)
    threshold = KS_CRITICAL_AT_5_PERCENT * math.sqrt((n + m) / (n * m))
    return ks_statistic(first, second) > threshold


class TestZeroMagnitudeIsBitIdentical:
    """The strongest claim available, and the one every other property rests on."""

    @pytest.mark.parametrize(("kind", "fields"), EVERY_KIND, ids=IDS)
    def test_a_fully_subtle_attack_leaves_the_run_untouched(
        self, kind: AttackType, fields: dict[str, object]
    ) -> None:
        clean = inject(PLANT, a_spec(), [])
        run = inject(PLANT, a_spec(), [a_plan(kind, 1.0, **fields)], allow_inert=True)
        # Every value, every sample, bit for bit. Anything less than equality here means a
        # zero-magnitude attack is findable, and therefore that a small one is too.
        assert [step.report.values for step in run.attacked.steps] == [
            step.report.values for step in clean.attacked.steps
        ]
        assert [step.truth.values for step in run.attacked.steps] == [
            step.truth.values for step in clean.attacked.steps
        ]

    @pytest.mark.parametrize(("kind", "fields"), EVERY_KIND, ids=IDS)
    def test_and_the_written_corpus_is_identical_too(
        self, kind: AttackType, fields: dict[str, object]
    ) -> None:
        # The values could match while the file differed — a different label, a different
        # rounding. Compare the rows that carry measurements.
        clean = telemetry_lines(inject(PLANT, a_spec(), []))
        attacked = telemetry_lines(
            inject(PLANT, a_spec(), [a_plan(kind, 1.0, **fields)], allow_inert=True)
        )
        assert [",".join(row.split(",")[2:]) for row in clean] == [
            ",".join(row.split(",")[2:]) for row in attacked
        ]

    def test_the_departure_recorded_for_it_is_exactly_zero(self) -> None:
        run = inject(
            PLANT,
            a_spec(),
            [a_plan(AttackType.BLATANT, 1.0, target=INTAKE_SPEED)],
            allow_inert=True,
        )
        assert run.attacks[0].peak_truth_departure() == 0.0
        assert run.attacks[0].peak_report_departure() == 0.0
        assert not run.attacks[0].physical_effect


class TestTheDialIsMonotone:
    """Turning subtlety up genuinely reduces the departure, at a fixed window."""

    @pytest.mark.parametrize(("kind", "fields"), EVERY_KIND, ids=IDS)
    def test_raising_subtlety_never_raises_the_departure(
        self, kind: AttackType, fields: dict[str, object]
    ) -> None:
        departures = []
        for subtlety in (0.0, 0.4, 0.75, 0.99, 1.0):
            run = inject(PLANT, a_spec(), [a_plan(kind, subtlety, **fields)], allow_inert=True)
            record = run.attacks[0]
            departures.append(max(record.peak_truth_departure(), record.peak_report_departure()))
        assert departures == sorted(departures, reverse=True), departures
        assert departures[-1] == 0.0
        assert departures[0] > 0.0

    @pytest.mark.parametrize(("kind", "fields"), EVERY_KIND, ids=IDS)
    def test_the_dial_reaches_nearly_invisible_before_it_reaches_zero(
        self, kind: AttackType, fields: dict[str, object]
    ) -> None:
        # The near-invisible band has to be genuinely near-invisible, or the corpus does not
        # actually span the range this PART is for.
        blatant = inject(PLANT, a_spec(), [a_plan(kind, 0.0, **fields)], allow_inert=True)
        subtle = inject(PLANT, a_spec(), [a_plan(kind, 0.99, **fields)], allow_inert=True)
        loud = max(
            blatant.attacks[0].peak_truth_departure(),
            blatant.attacks[0].peak_report_departure(),
        )
        quiet = max(
            subtle.attacks[0].peak_truth_departure(),
            subtle.attacks[0].peak_report_departure(),
        )
        assert quiet > 0.0
        assert quiet < loud / 20.0


class TestAMinimalAttackIsIndistinguishable:
    """A statistical test, not an eyeball: can a KS test at 5% separate the windows?"""

    def sample(self, subtlety: float, key: str, kind: AttackType, **fields: object) -> list[float]:
        """Return the reported series inside the window, under one attack at one subtlety."""
        run = inject(PLANT, a_spec(), [a_plan(kind, subtlety, **fields)], allow_inert=True)
        return [step.report.values[key] for step in run.attacked.steps[FIRST:LAST]]

    def clean_sample(self, key: str) -> list[float]:
        """Return the reported series inside the window with no attack at all."""
        run = inject(PLANT, a_spec(), [])
        return [step.report.values[key] for step in run.attacked.steps[FIRST:LAST]]

    def test_the_test_can_separate_an_obvious_attack(self) -> None:
        # The control on the control: a KS test that separated nothing would pass every other
        # test in this class for the wrong reason.
        assert ks_separates(
            self.clean_sample(INTAKE_SPEED),
            self.sample(0.0, INTAKE_SPEED, AttackType.BLATANT, target=INTAKE_SPEED),
        )

    @pytest.mark.parametrize(("kind", "fields"), EVERY_KIND, ids=IDS)
    def test_a_zero_magnitude_attack_is_not_separable(
        self, kind: AttackType, fields: dict[str, object]
    ) -> None:
        key = str(fields["target"])
        assert not ks_separates(self.clean_sample(key), self.sample(1.0, key, kind, **fields))

    def test_a_minimal_correlation_break_is_not_separable_per_signal(self) -> None:
        # The whole point of this attack: at any strength it leaves the signal's own distribution
        # where it was. At a minimal strength it leaves everything where it was.
        key = RAW_INFLOW
        assert not ks_separates(
            self.clean_sample(key),
            self.sample(
                0.999, key, AttackType.CORRELATION_BREAK, target=key, reference=INTAKE_SPEED
            ),
        )

    def test_a_minimal_liar_is_not_separable(self) -> None:
        key = CLEARWELL_LEVEL
        assert not ks_separates(
            self.clean_sample(key),
            self.sample(0.999, key, AttackType.LIAR, target=key, reference=LEVEL_SETPOINT),
        )


class TestNoVarianceCollapse:
    """A transmitter that stops being noisy announces itself to the crudest check there is."""

    def test_a_fully_falsified_reading_still_wobbles_like_the_instrument_it_came_from(
        self,
    ) -> None:
        run = inject(
            PLANT,
            a_spec(),
            [
                a_plan(
                    AttackType.CORRELATION_BREAK,
                    0.0,
                    target=RAW_INFLOW,
                    reference=INTAKE_SPEED,
                )
            ],
        )
        during = [step.report.values[RAW_INFLOW] for step in run.attacked.steps[FIRST:LAST]]
        declared = run.description.signal(RAW_INFLOW).noise_stddev
        assert statistics.pstdev(during) == pytest.approx(declared, rel=0.4)

    def test_the_liar_s_falsified_level_wobbles_too(self) -> None:
        run = inject(
            PLANT,
            a_spec(),
            [a_plan(AttackType.LIAR, 0.0, target=CLEARWELL_LEVEL, reference=LEVEL_SETPOINT)],
        )
        during = [step.report.values[CLEARWELL_LEVEL] for step in run.attacked.steps[FIRST:LAST]]
        assert statistics.pstdev(during) > 0.0

    def test_a_held_setpoint_does_not_wobble_because_a_real_one_does_not(self) -> None:
        # The right answer here is zero, and it comes out of the same rule: the jitter is the
        # signal's own declared noise, and a setpoint declares none.
        run = inject(
            PLANT,
            a_spec(),
            [
                a_plan(
                    AttackType.MIMIC,
                    0.0,
                    target=LEVEL_SETPOINT,
                    mimics=LEVEL_SETPOINT_CHANGE,
                )
            ],
        )
        during = [step.report.values[LEVEL_SETPOINT] for step in run.attacked.steps[FIRST:LAST]]
        assert statistics.pstdev(during) == 0.0


class TestNoValueLeavesTheRangeNormalValuesOccupy:
    """A falsified reading outside the instrument's span is a range check away from being found."""

    @pytest.mark.parametrize(("kind", "fields"), EVERY_KIND, ids=IDS)
    def test_every_reported_value_stays_inside_its_instrument_span(
        self, kind: AttackType, fields: dict[str, object]
    ) -> None:
        run = inject(PLANT, a_spec(), [a_plan(kind, 0.0, **fields)])
        for signal in run.description.signals:
            values = [step.report.values[signal.key] for step in run.attacked.steps]
            assert min(values) >= signal.low
            assert max(values) <= signal.high


class TestTheCorpusCarriesNoStructuralTell:
    """Nothing about the file may say which one has attacks in it."""

    @pytest.fixture(scope="class")
    def pair(self, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
        """Write one corpus with a blatant attack and one with a zero-magnitude one."""
        root = tmp_path_factory.mktemp("pair")
        loud = AttackDatasetConfig.model_validate(
            {
                **BASE,
                "name": "loud",
                "attacks": [
                    {
                        "attack_id": "a",
                        "type": "BLATANT",
                        "subtlety": 0.0,
                        "start_hours": WINDOW_START,
                        "duration_hours": WINDOW_HOURS,
                        "target": INTAKE_SPEED,
                    }
                ],
            }
        )
        quiet = AttackDatasetConfig.model_validate(
            {
                **BASE,
                "name": "quiet",
                "attacks": [
                    {
                        "attack_id": "a",
                        "type": "BLATANT",
                        "subtlety": 0.75,
                        "start_hours": WINDOW_START,
                        "duration_hours": WINDOW_HOURS,
                        "target": INTAKE_SPEED,
                    }
                ],
            }
        )
        first, _ = generate_attack_dataset(loud, root / "loud")
        second, _ = generate_attack_dataset(quiet, root / "quiet")
        return first, second

    def test_both_corpora_have_the_same_shape(self, pair: tuple[Path, Path]) -> None:
        loud, quiet = pair
        first = (loud / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()
        second = (quiet / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()
        assert len(first) == len(second)
        assert first[0] == second[0]

    def test_every_record_carries_the_same_number_of_fields(self, pair: tuple[Path, Path]) -> None:
        loud, _ = pair
        rows = (loud / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()
        widths = {len(row.split(",")) for row in rows}
        assert len(widths) == 1

    def test_every_value_carries_the_same_number_of_decimals(self, pair: tuple[Path, Path]) -> None:
        # A value written to a different precision inside an attack window would be a tell that
        # has nothing to do with the attack.
        loud, _ = pair
        rows = (loud / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()[1:]
        places = {len(field.split(".")[1]) for row in rows for field in row.split(",")[2:]}
        assert places == {5}

    def test_the_timestamps_are_evenly_spaced_through_the_attack(
        self, pair: tuple[Path, Path]
    ) -> None:
        loud, _ = pair
        rows = (loud / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()[1:]
        stamps = [datetime.fromisoformat(row.split(",")[0]) for row in rows]
        gaps = {(later - earlier).total_seconds() for earlier, later in pairwise(stamps)}
        assert gaps == {30.0}

    def test_the_labels_are_the_only_column_that_differs_in_kind(
        self, pair: tuple[Path, Path]
    ) -> None:
        loud, _ = pair
        rows = (loud / TELEMETRY_FILE).read_text(encoding="utf-8").splitlines()[1:]
        assert {row.split(",")[1] for row in rows} == {"0", "1"}

    def test_an_attack_that_touches_no_wire_leaves_the_capture_the_same_size(
        self, pair: tuple[Path, Path]
    ) -> None:
        # A blatant actuator attack adds no commands. If the capture changed size anyway, some
        # part of the machinery would be leaking into the traffic.
        loud, quiet = pair
        assert (loud / CAPTURE_FILE).stat().st_size == (quiet / CAPTURE_FILE).stat().st_size


def test_the_standing_caveat_is_what_this_file_defends() -> None:
    """The tests above can only ever be evidence for the caveat, never a replacement for it."""
    from phos.synth.attacks.spec import ATTACKS_ARE_OURS_CAVEAT

    assert "leaked fingerprint" in ATTACKS_ARE_OURS_CAVEAT
    assert "upper bound" in ATTACKS_ARE_OURS_CAVEAT


def test_the_window_constants_line_up_with_the_sampling_rate() -> None:
    """Guard the index arithmetic the sweeps above depend on."""
    spec = a_spec()
    assert spec.interval_seconds == 30.0
    assert spec.instant(FIRST) == datetime(2026, 4, 1, 6, 0, tzinfo=UTC)
    assert spec.instant(LAST) == datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
