"""The refusal register is complete, seeded, and still true of HEAD.

U6's confirmation pass (ADR 0081) re-read R1-R26 against the code and the committed
reports at HEAD. These pins exist so a later edit that drops an entry, empties a lift
column, re-claims the withdrawn 1.8x ratio, or quotes a z-score the U2 JSON does not
rank as largest, turns red before the register is published as current.

R27 was appended on 2026-11-05 by ADR 0422, outside the Usefulness Phase, under the
register's own §0 rule 1. The U6 seed set stays pinned as the first twenty-six entries
in order, so an append cannot quietly renumber or displace one; R27 carries its own pin.

Numbers in the register are checked against the artefacts that computed them, not
re-derived here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from phos.atlas.command_eval import discover_labelled_command_corpora
from phos.eval.decision_study import CRUDE_RUN_LABEL
from phos.sentiel.failure import (
    PART_6B_ALERT_THRESHOLD,
    depth_blind_ceiling_notice,
    features_required,
)
from phos.sentiel.featurise import PEER_FEATURES
from phos.sentiel.templates import sentiel_templates

REPO = Path(__file__).resolve().parents[2]
REGISTER = REPO / "docs" / "refusal-register.md"
ROADMAP = REPO / "docs" / "usefulness-phase-roadmap.md"
STATE = REPO / ".phos_usefulness_state.json"
CERT_JSON = REPO / "eval_runs" / "sentiel" / "cert-failure-classification.json"
TAXONOMY = REPO / "eval_runs" / "atlas" / "hai-error-taxonomy.md"
QUEUE = REPO / "eval_runs" / "atlas" / "hai-operator-queue.md"
U3 = REPO / "eval_runs" / "synth" / "u3-diagnostic.md"
U5_JSON = REPO / "eval_runs" / "usefulness" / "u5-decision-study.json"
LOG = REPO / "eval_runs" / "log.jsonl"

ROW = re.compile(
    r"^\| (R\d+) \| (?P<refusal>.+?) \| (?P<evidence>.+?) \| (?P<lift>.+?) \|$",
    re.MULTILINE,
)


def register_text() -> str:
    """Return the committed refusal register."""
    return REGISTER.read_text(encoding="utf-8")


def rows() -> dict[str, tuple[str, str, str]]:
    """Return ``{id: (refusal, evidence, lift)}`` for every four-column refusal row.

    Only tables headed ``# | Refusal | Evidence | What would lift it`` are read, so a
    later confirmation note cannot overwrite an entry by repeating its id.
    """
    parsed: dict[str, tuple[str, str, str]] = {}
    in_refusal_table = False
    for line in register_text().splitlines():
        if line.startswith("| # | Refusal |"):
            in_refusal_table = True
            continue
        if in_refusal_table and line.startswith("|---"):
            continue
        if in_refusal_table:
            match = ROW.match(line)
            if match is None:
                in_refusal_table = False
                continue
            parsed[match.group(1)] = (
                match.group("refusal"),
                match.group("evidence"),
                match.group("lift"),
            )
    return parsed


class TestTheRegisterExistsAndIsSeeded:
    def test_the_register_is_committed(self) -> None:
        assert REGISTER.is_file(), "docs/refusal-register.md is the U6 deliverable"

    def test_r1_through_r26_are_the_u6_seed_set_in_order(self) -> None:
        parsed = list(rows())
        expected = [f"R{n}" for n in range(1, 27)]
        assert parsed[:26] == expected, f"expected R1-R26 first and in order, got {parsed}"

    def test_every_id_is_unique_and_numbered_without_a_gap(self) -> None:
        parsed = list(rows())
        assert parsed == [f"R{n}" for n in range(1, len(parsed) + 1)], (
            f"ids must run R1..R{len(parsed)} with no gap and no repeat, got {parsed}"
        )

    def test_r27_is_the_protocol_reach_refusal(self) -> None:
        """ADR 0422's criterion. Appended after U6, pinned here so it cannot be softened.

        The entry says Atlas cannot *read* a plant that does not speak Modbus/TCP. It is a
        statement about parsing, never about detection, and a refused protocol lane sharpens
        it rather than lifting it.
        """
        refusal, evidence, lift = rows()["R27"]
        assert "Modbus/TCP" in refusal
        assert "cannot read" in refusal.lower()
        assert "ADR 0422" in evidence
        assert "ADR 0012" in evidence
        assert "refused" in lift.lower(), "a refused lane must still count as a result"
        for word in ("recall", "precision", "false-alert", "FP/hour"):
            assert word not in refusal, f"R27 is about reach, not performance: found {word!r}"

    def test_r27_strikes_s7comm_for_the_envelope_and_names_what_it_did_not_lift(self) -> None:
        """ADR 0348 judged the S7comm lane met on 2026-11-05.

        Rule 5 of §0 says a lifted refusal is struck through with the date and the record,
        never deleted. The strike has to be narrow: this lane read the ISO-on-TCP envelope and
        explicitly did not read S7 itself, so R27 keeps the other seven languages and R28
        carries the part that did not land.
        """
        refusal, evidence, _lift = rows()["R27"]
        assert "cannot read" in refusal.lower(), "the refusal statement itself must stand"
        assert "~~S7comm~~" in evidence, "a kept lane is struck through, not deleted"
        assert "R28" in evidence, "the strike must point at the entry that sharpens it"
        assert "iso-tsap" in evidence, "the strike covers the envelope, not the application"
        # The seven languages the lane did not touch stay un-struck.
        for language in ("DNP3", "IEC 60870-5-104", "EtherNet/IP", "OPC UA", "IEC 61850"):
            assert language in evidence, f"{language} must stay in R27 until its own lane lands"
            assert f"~~{language}~~" not in evidence, f"{language} was never lifted"

    def test_r28_is_the_s7_application_refusal(self) -> None:
        """ADR 0348's own ceiling, pinned so a later session cannot claim S7 was read.

        The lane's evidence is a publication gap, not a failed search, so the lift column must
        name a Siemens document rather than more effort.
        """
        refusal, evidence, lift = rows()["R28"]
        assert "S7" in refusal
        assert "cannot read" in refusal.lower()
        assert "ADR 0347" in evidence and "ADR 0348" in evidence
        assert "not an open standard" in evidence
        assert "iso-tsap" in evidence, "the module must be recorded as naming the envelope"
        assert "Siemens" in lift, "the lift is a published frame format, not another search"
        assert "No amount of further searching" in lift, "the refusal must not invite a re-run"
        for word in ("recall", "precision", "false-alert", "FP/hour"):
            assert word not in refusal, f"R28 is about reach, not performance: found {word!r}"

    def test_r29_is_the_unmeasured_inflow_refusal(self) -> None:
        """Rung H2's own worked example, refused for want of a measurement (ADR 0372).

        The brief asked for level change against flow in and flow out. Exactly one of the
        thirteen tags is a flow and it is the outlet. The simulator computes an inflow and never
        publishes it, so the entry must say *unmeasured* rather than *unmodelled*, and the lift
        column must name the instrument: a single flow meter is what moves this.
        """
        refusal, evidence, lift = rows()["R29"]
        assert "mass balance" in refusal.lower()
        assert "inlet" in refusal.lower()
        assert "no inflow is measured" in refusal, "the limit is measurement, not modelling"
        assert "thirteen" in evidence, "the denominator is the whole tag list, not a sample"
        assert "tank_output_flow_value" in evidence, "the one flow must be named as the outlet"
        assert "never publishes it as a tag" in evidence, (
            "the simulator does compute an inflow; the entry must not claim otherwise"
        )
        assert "tank_input_valve_status" in evidence, (
            "the inlet is a valve state, and the entry must say so"
        )
        assert "ADR 0372" in evidence
        assert "data-tiers.md" in evidence, (
            "the never-read corpora must be recorded as unable to supply it"
        )
        assert "flow meter" in lift, "the lift is one instrument, named"
        assert "no_inflow_no_rise" in lift, (
            "the entry must say what Atlas can still state about the inlet"
        )
        for word in ("recall", "precision", "false-alert", "FP/hour"):
            assert word not in refusal, f"R29 is about a missing measurement: found {word!r}"

    def test_r30_keeps_the_physics_unreadable_by_the_engine(self) -> None:
        """The ground-truth boundary, pinned (ADR 0372, ADR 0132).

        This is the entry most likely to be "fixed" by a later session importing the truth graph
        into a law, which would quietly make the engine read the answer key. The evidence must
        keep naming the docstring and the test that forbid it, and the lift column must keep
        saying that lifting the entry may not let Atlas discover physics from traffic.
        """
        refusal, evidence, lift = rows()["R30"]
        assert "derive" in refusal.lower()
        assert "ground truth" in refusal.lower()
        assert "icssim_truth" in evidence, "the forbidden source must be named"
        assert "nothing that learns may read it" in evidence, "the docstring is the evidence"
        assert "test_interventions.py" in evidence, "the enforcing test must stay cited"
        assert "never from a tag's name" in evidence, (
            "the tag-name shortcut must stay closed, or two tags relate by their spelling"
        )
        assert "hand declarations" in evidence, (
            "the three laws' true standing is a hand copy, the thing H1 exists to distrust"
        )
        assert "controller_valve" in evidence
        assert "declaring its own physics" in lift, "the lift is the plant's declaration"
        assert "must not make it start" in lift, (
            "lifting this entry may not license discovering physics from traffic"
        )
        for word in ("confidence", "probability", "magnitude", "score"):
            assert word not in refusal, (
                f"R30's own statement must not carry a page-refused word: {word!r}"
            )

    def test_every_entry_has_evidence_and_a_lift(self) -> None:
        for rid, (refusal, evidence, lift) in rows().items():
            assert refusal.strip(), f"{rid} has an empty refusal"
            assert evidence.strip(), f"{rid} has no evidence"
            assert lift.strip(), f"{rid} has no statement of what would lift it"

    @pytest.mark.lab_only
    def test_the_standing_procedure_references_the_append_procedure(self) -> None:
        text = ROADMAP.read_text(encoding="utf-8")
        standing = text.split("## 1.", 1)[0]
        assert "docs/refusal-register.md" in standing
        assert "§0" in standing or "section 0" in standing.lower() or "append" in standing.lower()


class TestSeedRefusalsStillMatchTheCode:
    def test_r6_labelled_command_corpora_are_still_empty(self) -> None:
        assert discover_labelled_command_corpora(Path("data")) == []
        assert "It does not" in rows()["R6"][1] or "does not" in rows()["R6"][0].lower()

    def test_r5_weight_is_still_a_constant_across_the_queue(self) -> None:
        text = QUEUE.read_text(encoding="utf-8")
        assert "`atlas-queue:weight` — 1 distinct score(s)" in text
        evidence = rows()["R5"][1]
        assert "424-way constant" in evidence
        assert "ADR 0068" in evidence

    def test_r3_records_that_transfer_was_measured_and_is_louder(self) -> None:
        evidence = rows()["R3"][1]
        lift = rows()["R3"][2]
        assert "1078.99" in evidence
        assert "646.58" in evidence
        assert "louder" in evidence.lower()
        assert "U5" not in lift or "did not" in lift.lower()


class TestU1NumbersAreTheTaxonomyReport:
    def test_r7_pair_is_the_committed_taxonomy_pair(self) -> None:
        taxonomy = TAXONOMY.read_text(encoding="utf-8")
        evidence = rows()["R7"][1]
        assert "**55.74%**" in taxonomy
        assert "**55.81%**" in taxonomy
        assert "55.74%" in evidence
        assert "55.81%" in evidence

    def test_r8_zero_of_seventy_nine_is_still_the_screen(self) -> None:
        taxonomy = TAXONOMY.read_text(encoding="utf-8")
        assert "0 of its 79 data columns" in taxonomy
        assert "0 of its 79" in rows()["R8"][1]


class TestU2NumbersAreTheCommittedJson:
    def test_r14_ceiling_is_computed_not_remembered(self) -> None:
        required = features_required(PART_6B_ALERT_THRESHOLD)
        assert required == 14
        assert len(PEER_FEATURES) == 34
        evidence = rows()["R14"][1]
        assert "13.700640148454447" in evidence
        assert "**14**" in evidence
        assert "31 of `CCH0959`'s 42" in evidence

    def test_r15_largest_abs_z_matches_the_json(self) -> None:
        payload = json.loads(CERT_JSON.read_text(encoding="utf-8"))
        shifts = payload["baseline_shifts"]["CCH0959"]
        ranked = [
            (abs(row["shift_z"]), row["feature"], row["shift_z"])
            for row in shifts
            if row["shift_z"] is not None
        ]
        ranked.sort(reverse=True)
        largest_abs, feature, _raw = ranked[0]
        evidence = rows()["R15"][1]
        assert feature in evidence, f"register must name {feature}, the largest abs(z)"
        assert f"{largest_abs:.2f}" in evidence
        assert "largest shift on any of the 34 features is **z = 1.07**" not in evidence
        cch = next(item for item in payload["visibility"] if item["user_id"] == "CCH0959")
        assert f"{cch['malicious_median']:.3f}" in evidence
        assert f"{cch['own_ordinary_median']:.3f}" in evidence
        assert str(cch["best_rank"]) in evidence

    def test_r18_coverage_null_is_the_json_null(self) -> None:
        payload = json.loads(CERT_JSON.read_text(encoding="utf-8"))
        coverage = payload["episode_nulls"]["malicious_days"]
        evidence = rows()["R18"][1]
        assert f"{coverage['mean']:.2f}" in evidence
        assert f"[{int(coverage['low'])}, {int(coverage['high'])}]" in evidence
        assert f"{coverage['p_at_least_observed']:.3f}" in evidence
        assert "1.8" in evidence

    def test_r23_sentiel_templates_still_declare_no_contradiction(self) -> None:
        for template in sentiel_templates():
            assert template.contradicted_by == ()
        assert "no contradictory patterns" in rows()["R23"][1].lower()

    def test_r24_ceiling_notice_still_travels_with_the_render(self) -> None:
        notice = depth_blind_ceiling_notice()
        assert "14 of 34" in notice
        assert "31 of" in notice
        assert "42" in notice
        assert "depth_blind_ceiling_notice()" in rows()["R24"][1]


class TestU3AndU5CommittedArtefacts:
    def test_r21_matches_the_committed_diagnostic(self) -> None:
        diagnostic = U3.read_text(encoding="utf-8")
        evidence = rows()["R21"][1]
        assert "unique leader `insufficient_evidence`" in diagnostic
        assert "graph findings `1`" in diagnostic
        assert "command evidence `3`" in diagnostic
        assert "insufficient_evidence" in evidence
        assert "1 graph finding" in evidence
        assert "3 command evidence" in evidence

    def test_r25_crude_run_is_still_n_human_zero(self) -> None:
        payload = json.loads(U5_JSON.read_text(encoding="utf-8"))
        assert payload["n_human"] == 0
        assert payload["label"] == CRUDE_RUN_LABEL
        evidence = rows()["R25"][1]
        assert "`n_human` **0**" in evidence
        lift = rows()["R25"][2]
        assert "U7" in lift
        assert "not started" in lift.lower()


class TestStaleLiftColumnsStayCorrected:
    def test_r4_no_longer_names_u5_as_the_lift(self) -> None:
        lift = rows()["R4"][2]
        assert "(U5)" not in lift
        assert "R25" in lift or "U7" in lift

    def test_r20_no_longer_names_u5_as_if_it_had_not_run(self) -> None:
        lift = rows()["R20"][2]
        assert "or U5 with plant-literate operators" not in lift
        assert "R25" in lift or "U7" in lift or "did not" in lift.lower()


class TestThePhaseDidNotInventALogRow:
    def test_nothing_in_the_register_session_appended_a_public_row(self) -> None:
        # Presence of the file is the contract; U6 writes no detector name.
        assert LOG.is_file()
        text = register_text()
        assert "eval_runs/log.jsonl" in text
        assert "Not a row in `eval_runs/log.jsonl`" in text or "never enter" in text.lower()

    @pytest.mark.lab_only
    def test_u7_is_named_and_not_started(self) -> None:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        u7 = next(item for item in state["items"] if item["id"] == "U7")
        assert u7["status"] == "not_started"
        assert "U7" not in state["items_completed"]
        u6 = next(item for item in state["items"] if item["id"] == "U6")
        assert u6["status"] == "complete"
        assert "usefulness_score" not in state
        assert "usefulness_score" in state["keys_that_must_not_exist"]
        assert "accuracy" in state["keys_that_must_not_exist"]
