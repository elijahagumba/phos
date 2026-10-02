"""Corrupting the file rather than the plant, and the claim that is never allowed to follow.

The boundary test matters more than any individual corruption: whatever these produce, none of it
can reach a corpus's attack intervals, because `HostileGroundTruth` has no method that makes one.
That is checked here against the real types rather than asserted in a comment.
"""

import math

import pytest
from tests.synth.attacks.conftest import CLEARWELL_LEVEL, PLANT, a_spec

from phos.synth import PLANT_IDS, run_plant
from phos.synth.attacks.hostile import MALFORMED_KINDS, apply_hostile, is_finite_row
from phos.synth.attacks.spec import (
    INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT,
    AttackFlavour,
    AttackType,
    HostileGroundTruth,
    HostilePlan,
)
from phos.synth.plant import PlantDescription

HEADER = "timestamp,label,clearwell_level_m,raw_inflow_m3ph"


@pytest.fixture(scope="module")
def description() -> PlantDescription:
    """The works' declaration, whose spans decide what counts as impossible."""
    return run_plant(PLANT, a_spec(hours=1.0)).description


@pytest.fixture(scope="module")
def corpus() -> tuple[str, ...]:
    """A small clean corpus in the prepared-CSV shape D1 writes."""
    rows = [
        f"2026-04-01T{hour:02d}:{minute:02d}:00+00:00,0,{2.5 + row * 0.001:.5f},{180.0:.5f}"
        for row, (hour, minute) in enumerate((index // 60, index % 60) for index in range(100))
    ]
    return (HEADER, *rows)


def a_plan(**overrides: object) -> HostilePlan:
    """Return a hostile plan with the given fields replaced."""
    fields: dict[str, object] = {
        "attack_id": "hostile",
        "type": AttackType.MALFORMED_RECORD,
        "fraction": 0.1,
    }
    fields.update(overrides)
    return HostilePlan.model_validate(fields)


class TestTheBoundary:
    """The one thing this module may never do."""

    @pytest.mark.parametrize(
        ("attack_type", "target"),
        [
            (AttackType.MALFORMED_RECORD, ""),
            (AttackType.OUT_OF_RANGE, CLEARWELL_LEVEL),
            (AttackType.TRUNCATED, ""),
            (AttackType.POISONED_BASELINE, CLEARWELL_LEVEL),
        ],
    )
    def test_every_corruption_is_recorded_as_input_hostile(
        self,
        attack_type: AttackType,
        target: str,
        corpus: tuple[str, ...],
        description: PlantDescription,
    ) -> None:
        _, record = apply_hostile(corpus, a_plan(type=attack_type, target=target), description)
        assert record.flavour is AttackFlavour.INPUT_HOSTILE
        assert isinstance(record, HostileGroundTruth)

    def test_no_corruption_can_produce_something_the_harness_would_score(self) -> None:
        # The absence of a road, not a rule about which road to take.
        assert not hasattr(HostileGroundTruth, "interval")

    def test_the_caveat_refuses_the_security_claim(self) -> None:
        assert "not evidence that PHOS is secure" in INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT
        assert "never appears in a corpus's attack intervals" in (
            INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT
        )


class TestTheSharedContract:
    """What every corruption does, whatever it does."""

    @pytest.mark.parametrize(
        ("attack_type", "target"),
        [
            (AttackType.MALFORMED_RECORD, ""),
            (AttackType.OUT_OF_RANGE, CLEARWELL_LEVEL),
            (AttackType.TRUNCATED, ""),
            (AttackType.POISONED_BASELINE, CLEARWELL_LEVEL),
        ],
    )
    def test_the_header_survives_so_the_corpus_still_loads(
        self,
        attack_type: AttackType,
        target: str,
        corpus: tuple[str, ...],
        description: PlantDescription,
    ) -> None:
        lines, _ = apply_hostile(corpus, a_plan(type=attack_type, target=target), description)
        assert lines[0] == HEADER

    @pytest.mark.parametrize(
        ("attack_type", "target"),
        [
            (AttackType.MALFORMED_RECORD, ""),
            (AttackType.OUT_OF_RANGE, CLEARWELL_LEVEL),
            (AttackType.TRUNCATED, ""),
            (AttackType.POISONED_BASELINE, CLEARWELL_LEVEL),
        ],
    )
    def test_corruption_is_reproducible(
        self,
        attack_type: AttackType,
        target: str,
        corpus: tuple[str, ...],
        description: PlantDescription,
    ) -> None:
        plan = a_plan(type=attack_type, target=target)
        assert apply_hostile(corpus, plan, description) == apply_hostile(corpus, plan, description)

    @pytest.mark.parametrize(
        ("attack_type", "target"),
        [
            (AttackType.MALFORMED_RECORD, ""),
            (AttackType.OUT_OF_RANGE, CLEARWELL_LEVEL),
            (AttackType.POISONED_BASELINE, CLEARWELL_LEVEL),
        ],
    )
    def test_a_fraction_of_nothing_corrupts_nothing(
        self,
        attack_type: AttackType,
        target: str,
        corpus: tuple[str, ...],
        description: PlantDescription,
    ) -> None:
        lines, record = apply_hostile(
            corpus, a_plan(type=attack_type, target=target, fraction=0.0), description
        )
        assert lines == corpus
        assert record.rows_affected == 0

    @pytest.mark.parametrize(
        ("attack_type", "target"),
        [
            (AttackType.MALFORMED_RECORD, ""),
            (AttackType.OUT_OF_RANGE, CLEARWELL_LEVEL),
            (AttackType.TRUNCATED, ""),
            (AttackType.POISONED_BASELINE, CLEARWELL_LEVEL),
        ],
    )
    def test_every_corruption_says_what_it_did_in_words(
        self,
        attack_type: AttackType,
        target: str,
        corpus: tuple[str, ...],
        description: PlantDescription,
    ) -> None:
        _, record = apply_hostile(corpus, a_plan(type=attack_type, target=target), description)
        assert len(record.description) > 40

    def test_a_corpus_with_no_data_rows_is_refused(self, description: PlantDescription) -> None:
        with pytest.raises(ValueError, match="nothing to corrupt"):
            apply_hostile((HEADER,), a_plan(), description)

    @pytest.mark.parametrize("attack_type", [AttackType.OUT_OF_RANGE, AttackType.POISONED_BASELINE])
    def test_a_column_the_corpus_does_not_carry_is_refused(
        self, attack_type: AttackType, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        with pytest.raises(ValueError, match="does not carry"):
            apply_hostile(corpus, a_plan(type=attack_type, target="turbine_speed_rpm"), description)


class TestMalformedRecords:
    """Records that violate the format, in every way the format can be violated."""

    def test_the_right_number_of_records_are_damaged(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, record = apply_hostile(corpus, a_plan(fraction=0.1), description)
        damaged = sum(
            1 for before, after in zip(corpus[1:], lines[1:], strict=True) if before != after
        )
        assert damaged == record.rows_affected == 10

    def test_every_kind_of_damage_appears(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = apply_hostile(corpus, a_plan(fraction=0.1), description)
        rows = lines[1:]
        widths = {len(row.split(",")) for row in rows}
        assert 3 in widths  # a field removed
        assert 5 in widths  # a field too many
        assert any("not-a-number" in row for row in rows)
        assert any("2026-13-45" in row for row in rows)
        assert any(row.split(",")[2] == "" for row in rows)

    def test_the_damage_kinds_are_cycled_rather_than_repeated(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        # Five kinds, five damaged rows, so each appears exactly once — a corpus that only ever
        # produced the first kind would test one branch of a loader many times.
        lines, record = apply_hostile(corpus, a_plan(fraction=0.05), description)
        assert record.rows_affected == len(MALFORMED_KINDS)
        damaged = [
            after for before, after in zip(corpus[1:], lines[1:], strict=True) if before != after
        ]
        assert len({len(row.split(",")) for row in damaged}) >= 2

    def test_undamaged_records_are_untouched(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = apply_hostile(corpus, a_plan(fraction=0.1), description)
        unchanged = [
            after for before, after in zip(corpus[1:], lines[1:], strict=True) if before == after
        ]
        assert len(unchanged) == 90


class TestOutOfRange:
    """Numbers a parser will accept and an instrument could never produce."""

    def test_the_values_are_impossible_for_the_instrument_that_carries_them(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        plan = a_plan(type=AttackType.OUT_OF_RANGE, target=CLEARWELL_LEVEL, fraction=0.1)
        lines, _ = apply_hostile(corpus, plan, description)
        spec = description.signal(CLEARWELL_LEVEL)
        changed = [
            after.split(",")[2]
            for before, after in zip(corpus[1:], lines[1:], strict=True)
            if before != after
        ]
        assert changed
        for value in changed:
            number = float(value)
            assert not math.isfinite(number) or not spec.low <= number <= spec.high

    def test_both_non_finite_floats_are_present(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        plan = a_plan(type=AttackType.OUT_OF_RANGE, target=CLEARWELL_LEVEL, fraction=0.1)
        lines, _ = apply_hostile(corpus, plan, description)
        text = "\n".join(lines)
        assert "inf" in text
        assert "nan" in text

    def test_only_the_named_column_is_touched(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        plan = a_plan(type=AttackType.OUT_OF_RANGE, target=CLEARWELL_LEVEL, fraction=0.1)
        lines, _ = apply_hostile(corpus, plan, description)
        for before, after in zip(corpus[1:], lines[1:], strict=True):
            before_fields, after_fields = before.split(","), after.split(",")
            assert before_fields[0] == after_fields[0]
            assert before_fields[1] == after_fields[1]
            assert before_fields[3] == after_fields[3]

    def test_a_reader_can_tell_which_records_are_unusable(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        plan = a_plan(type=AttackType.OUT_OF_RANGE, target=CLEARWELL_LEVEL, fraction=0.1)
        lines, record = apply_hostile(corpus, plan, description)
        unusable = sum(1 for row in lines[1:] if not is_finite_row(row, 2))
        assert 0 < unusable <= record.rows_affected


class TestTruncation:
    """A file that stops early, and stops badly."""

    def test_the_tail_is_gone(self, corpus: tuple[str, ...], description: PlantDescription) -> None:
        lines, record = apply_hostile(
            corpus, a_plan(type=AttackType.TRUNCATED, fraction=0.2), description
        )
        assert len(lines) == len(corpus) - record.rows_affected
        assert record.rows_affected == 20

    def test_the_last_surviving_record_stops_mid_field(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        # A cut at a line boundary is the easy case. A half-written record is what a process
        # killed during a flush actually leaves.
        lines, _ = apply_hostile(
            corpus, a_plan(type=AttackType.TRUNCATED, fraction=0.2), description
        )
        assert lines[-1] not in corpus
        assert len(lines[-1].split(",")) < len(HEADER.split(","))

    def test_at_least_one_record_always_survives(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = apply_hostile(
            corpus, a_plan(type=AttackType.TRUNCATED, fraction=1.0), description
        )
        assert len(lines) >= 2

    def test_the_records_before_the_cut_are_untouched(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = apply_hostile(
            corpus, a_plan(type=AttackType.TRUNCATED, fraction=0.2), description
        )
        assert lines[1:-1] == corpus[1 : len(lines) - 1]


class TestPoisonedBaseline:
    """The one that raises no error anywhere, which is why it is the worst."""

    def poisoned(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> tuple[tuple[str, ...], HostileGroundTruth]:
        """Poison the first 30% of the corpus."""
        return apply_hostile(
            corpus,
            a_plan(type=AttackType.POISONED_BASELINE, target=CLEARWELL_LEVEL, fraction=0.3),
            description,
        )

    def test_nothing_is_malformed(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = self.poisoned(corpus, description)
        for row in lines[1:]:
            assert len(row.split(",")) == len(HEADER.split(","))
            assert is_finite_row(row, 2)

    def test_every_value_stays_inside_the_instrument_span(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = self.poisoned(corpus, description)
        spec = description.signal(CLEARWELL_LEVEL)
        for row in lines[1:]:
            assert spec.low <= float(row.split(",")[2]) <= spec.high

    def test_only_the_fitting_window_is_touched(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, record = self.poisoned(corpus, description)
        assert record.rows_affected == 30
        assert lines[31:] == corpus[31:]

    def test_the_bias_arrives_gradually_rather_than_as_a_step(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = self.poisoned(corpus, description)
        added = [
            float(after.split(",")[2]) - float(before.split(",")[2])
            for before, after in zip(corpus[1:31], lines[1:31], strict=True)
        ]
        assert added[0] == pytest.approx(0.0, abs=1e-9)
        assert added == sorted(added)
        assert added[-1] > added[0]

    def test_it_moves_what_a_model_would_learn_as_normal(
        self, corpus: tuple[str, ...], description: PlantDescription
    ) -> None:
        lines, _ = self.poisoned(corpus, description)
        before = [float(row.split(",")[2]) for row in corpus[1:31]]
        after = [float(row.split(",")[2]) for row in lines[1:31]]
        assert sum(after) / len(after) > sum(before) / len(before)


def test_every_input_hostile_type_has_a_corruption(description: PlantDescription) -> None:
    """No type may be declared without something that applies it."""
    hostile = [t for t in AttackType if t.flavour is AttackFlavour.INPUT_HOSTILE]
    rows = (HEADER, "2026-04-01T00:00:00+00:00,0,2.50000,180.00000")
    for attack_type in hostile:
        target = CLEARWELL_LEVEL if attack_type != AttackType.MALFORMED_RECORD else ""
        apply_hostile(rows, a_plan(type=attack_type, target=target, fraction=0.5), description)


def test_the_plants_all_declare_the_column_a_hostile_case_would_name() -> None:
    """Every plant carries at least one signal an input-hostile case can be pointed at."""
    for plant_id in PLANT_IDS:
        description = run_plant(plant_id, a_spec(hours=1.0)).description
        assert description.signal_keys()


class TestIsFiniteRow:
    """The helper a reader uses to say which records are unusable."""

    def test_a_finite_value_is_finite(self) -> None:
        assert is_finite_row("2026-04-01T00:00:00+00:00,0,2.50000,180.00000", 2)

    def test_a_non_finite_value_is_not(self) -> None:
        assert not is_finite_row("2026-04-01T00:00:00+00:00,0,inf,180.00000", 2)
        assert not is_finite_row("2026-04-01T00:00:00+00:00,0,nan,180.00000", 2)

    def test_a_value_that_is_not_a_number_is_not(self) -> None:
        assert not is_finite_row("2026-04-01T00:00:00+00:00,0,not-a-number,180.00000", 2)

    def test_a_record_too_short_to_hold_the_column_is_not(self) -> None:
        assert not is_finite_row("2026-04-01T00:00:00+00:00,0", 2)

    def test_an_empty_field_is_not(self) -> None:
        assert not is_finite_row("2026-04-01T00:00:00+00:00,0,,180.00000", 2)
