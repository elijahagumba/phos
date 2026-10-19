"""Lane T runs: one hostile known-operator write and one authorised run per seed."""

import pytest

from phos.atlas.command_effect import OUTSIDE_OPERATING_MODE, SETPOINT_JUMP, WRITE_AND_HIDE
from phos.atlas.templates import (
    ENGINEERING_MAINTENANCE_TEMPLATE_ID,
    UNAUTHORISED_CONTROL_TEMPLATE_ID,
)
from phos.eval.trusted_station import (
    HOSTILE_SETPOINT,
    WRITE_AT,
    CaseScore,
    SeedScore,
    challenger_sha256,
    false_alarm_count,
    held_back_allowed,
    render_held_back,
    run_case,
    run_quiet,
    score_case,
    score_development,
)
from phos.reasoning import INSUFFICIENT_EVIDENCE_TEMPLATE_ID
from phos.synth.plants.water import CLEARWELL_LEVEL, ENGINEERING, LEVEL_SETPOINT


def test_silence_is_zero_and_maintenance_about_the_write_is_not_a_false_alarm() -> None:
    assert false_alarm_count(silent=True, concerns_write=False, lead="") == 0
    assert (
        false_alarm_count(
            silent=False,
            concerns_write=True,
            lead=ENGINEERING_MAINTENANCE_TEMPLATE_ID,
        )
        == 0
    )
    assert (
        false_alarm_count(
            silent=False,
            concerns_write=True,
            lead=UNAUTHORISED_CONTROL_TEMPLATE_ID,
        )
        == 1
    )
    assert false_alarm_count(silent=False, concerns_write=False, lead="sensor_or_device_fault") == 1


def test_held_back_is_refused_until_the_declaration_is_committed_and_the_file_is_absent() -> None:
    assert not held_back_allowed(output_exists=False, declaration_in_head=False)
    assert not held_back_allowed(output_exists=True, declaration_in_head=True)
    assert held_back_allowed(output_exists=False, declaration_in_head=True)


def test_the_challenger_digest_is_a_sha256_and_a_miss_is_not_met() -> None:
    digest = challenger_sha256()
    assert len(digest) == 64
    assert int(digest, 16) >= 0
    silent = CaseScore(
        kind="hostile",
        issuer="hmi",
        n_facts=2,
        lead="insufficient_evidence",
        tied=(),
        uniquely_leads=False,
        false_alarms=0,
        concerns_write=True,
    )
    quiet = CaseScore(
        kind="authorised",
        issuer="hmi",
        n_facts=0,
        lead="",
        tied=(),
        uniquely_leads=False,
        false_alarms=0,
        concerns_write=False,
    )
    text = render_held_back((SeedScore(97901, silent, quiet),), tests_green=True)
    assert "0 of 1. not met." in text
    assert "0.00 (0 of 1). met." in text
    assert "Known-link both-support tests green: met." in text


def test_development_refuses_a_held_back_seed() -> None:
    with pytest.raises(ValueError, match="97801"):
        score_development((97901,))


def test_the_operator_write_moves_the_clearwell_and_h1_does_not_uniquely_lead() -> None:
    hostile = run_case(97801, kind="hostile")
    network = hostile.description.control_network
    assert network is not None
    assert network.operator != ENGINEERING
    issued = [command for step in hostile.steps for command in step.issued]
    assert len(issued) == 1
    assert issued[0].issuer == network.operator
    assert issued[0].signal == LEVEL_SETPOINT
    assert issued[0].applied == HOSTILE_SETPOINT

    held = run_quiet(97801)
    later = WRITE_AT + 8
    moved = hostile.steps[later].truth.values[CLEARWELL_LEVEL]
    still = held.steps[later].truth.values[CLEARWELL_LEVEL]
    assert moved != still

    scored = score_case(hostile, kind="hostile")
    assert scored.n_facts == 1
    assert scored.lead == INSUFFICIENT_EVIDENCE_TEMPLATE_ID
    assert scored.uniquely_leads is False
    authorised = score_case(run_case(97801, kind="authorised"), kind="authorised")
    assert authorised.n_facts == 0
    assert authorised.false_alarms == 0
    assert authorised.issuer == network.operator


def test_h2_false_alarms_on_the_authorised_jump() -> None:
    enabled = frozenset({SETPOINT_JUMP, OUTSIDE_OPERATING_MODE})
    authorised = score_case(run_case(97801, kind="authorised"), kind="authorised", enabled=enabled)
    hostile = score_case(run_case(97801, kind="hostile"), kind="hostile", enabled=enabled)

    assert authorised.n_facts == 1
    assert authorised.false_alarms == 1
    assert hostile.n_facts == 1
    assert hostile.uniquely_leads is False


def test_h3_attaches_on_the_frozen_reading_and_not_on_the_authorised_run() -> None:
    enabled = frozenset({WRITE_AND_HIDE})
    hostile = score_case(run_case(97801, kind="hostile"), kind="hostile", enabled=enabled)
    authorised = score_case(run_case(97801, kind="authorised"), kind="authorised", enabled=enabled)

    assert hostile.n_facts == 1
    assert hostile.false_alarms == 0
    assert hostile.uniquely_leads is False
    assert authorised.n_facts == 0
    assert authorised.false_alarms == 0
