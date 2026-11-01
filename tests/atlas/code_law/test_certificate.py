"""Certificates: a person holding the rows can recheck the break without PHOS."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from tests.atlas.code_law.fixtures import CONFIGS_TEXT, DEVICE_TEXT, PLC1_TEXT

from phos.atlas.code_law import (
    CertificateRow,
    DerivedValveLaw,
    Disagreement,
    LawCertificate,
    certified_breaks,
    derive_valve_law,
    pinned_source_from_text,
)
from phos.atlas.declared_law import (
    CONTROLLER_VALVE,
    ControllerSample,
    LawBreak,
    LawRegister,
    law_page,
)

AT = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
SCORE_WORDS = ("confidence", "probability", "weight", "magnitude", "score")


def _law() -> DerivedValveLaw:
    derivation = derive_valve_law(
        pinned_source_from_text(plc1=PLC1_TEXT, configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    )
    assert derivation.law is not None
    return derivation.law


def _sample(**over: float) -> ControllerSample:
    values: dict[str, float] = {
        "level": 5.0,
        "level_min": 3.0,
        "level_max": 7.0,
        "input_valve": 1.0,
        "input_mode": 3.0,
        "bottle_level": 0.8,
        "bottle_max": 1.8,
        "belt": 0.0,
        "output_valve": 1.0,
        "output_mode": 3.0,
    }
    values.update(over)
    return ControllerSample(at=AT, **values)


def test_agreement_produces_no_break_and_no_certificate() -> None:
    assert certified_breaks(_law(), _sample()) == ()


def test_a_manual_mode_produces_nothing_because_the_law_is_not_stated() -> None:
    assert certified_breaks(_law(), _sample(input_mode=1.0, input_valve=0.0)) == ()


def test_a_disagreeing_input_side_carries_one_certificate() -> None:
    # Above the maximum the rule writes close; the valve is open.
    found = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))
    assert len(found) == 1
    certified = found[0]
    assert certified.certificate.side == "input valve"
    assert certified.certificate.required == 0.0
    assert certified.certificate.actual == 1.0
    assert certified.certificate.at == AT
    assert certified.certificate.law_name == CONTROLLER_VALVE.name


def test_both_sides_can_disagree_and_each_gets_its_own_certificate() -> None:
    found = certified_breaks(
        _law(), _sample(level=2.0, input_valve=0.0, belt=2.0, output_valve=1.0)
    )
    assert [certified.certificate.side for certified in found] == [
        "input valve",
        "output valve",
    ]


def test_the_certificate_names_the_rows_the_comparison_used() -> None:
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    rows = {row.signal: row.value for row in certified.certificate.rows}
    assert rows["tank_level_value"] == 8.0
    assert rows["tank_level_max"] == 7.0
    assert rows["tank_level_min"] == 3.0
    assert rows["tank_input_valve_status"] == 1.0
    assert rows["tank_input_valve_mode"] == 3.0
    assert rows["tank_output_valve_mode"] == 3.0


def test_the_certificate_quotes_the_branch_that_fired_and_the_equality_that_failed() -> None:
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    assert certified.certificate.required_because == "tank_level_value 8 > tank_level_max 7"
    assert certified.certificate.comparison == "tank_input_valve_status 1 == 0"


def test_an_otherwise_value_says_no_branch_fired() -> None:
    certified = certified_breaks(_law(), _sample(output_valve=0.0))[0]
    assert certified.certificate.side == "output valve"
    assert certified.certificate.required == 1.0
    assert "no branch fired" in certified.certificate.required_because


def test_no_certificate_field_can_hold_a_score() -> None:
    for kind in (LawCertificate, CertificateRow, Disagreement):
        for field in dataclasses.fields(kind):
            folded = field.name.casefold()
            for word in SCORE_WORDS:
                assert word not in folded


def test_a_disagreement_is_not_a_law_break_subclass() -> None:
    assert not issubclass(Disagreement, LawBreak)
    assert not issubclass(LawCertificate, LawBreak)


def test_no_certificate_text_carries_a_score_word() -> None:
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    texts = (
        certified.certificate.statement,
        certified.certificate.comparison,
        certified.certificate.required_because,
        certified.certificate.side,
        certified.certificate.law_name,
    )
    for text in texts:
        for word in SCORE_WORDS:
            assert word not in text.casefold()


def test_the_statement_names_the_law_first() -> None:
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    assert certified.certificate.statement.startswith(f"{CONTROLLER_VALVE.name}. ")


def test_a_certificate_is_not_a_law_break_subclass() -> None:
    assert not issubclass(LawCertificate, LawBreak)
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    assert not isinstance(certified.certificate, LawBreak)


def test_the_break_is_exactly_a_law_break_so_page_admission_is_unchanged() -> None:
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    assert type(certified.law_break) is LawBreak
    register = LawRegister(laws=(CONTROLLER_VALVE,))
    assert law_page([certified.law_break], register=register) == (certified.law_break,)


def test_the_break_and_its_certificate_agree_on_the_sentence() -> None:
    certified = certified_breaks(_law(), _sample(level=8.0, input_valve=1.0))[0]
    assert certified.law_break.statement == certified.certificate.statement
    assert certified.law_break.time == certified.certificate.at
