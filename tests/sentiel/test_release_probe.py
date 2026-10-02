"""The read-only CERT release probe: labels and headers, without a download.

Two kinds of test here, and the distinction matters.

Most of them run against a hand-built corpus, so they pin the probe's *logic* — it counts insiders
per scenario, it applies the reader's two header rules, and it says "unchecked" rather than
"compatible" when a release's events are absent.

The last class runs against the real ``answers`` archive and is skipped when it is not on disk. It
checks the one thing a fixture cannot: that every quote in `SCENARIO_REGISTERS` is really CERT's
own wording. The register readings are a judgement about prose, and a judgement whose supporting
quote has drifted from the source is worse than no judgement at all.
"""

from pathlib import Path

import pytest
from scripts.probe_cert_release import (
    SCENARIO_REGISTERS,
    SCENARIOS_FILENAME,
    DetectionRegister,
    ProbeError,
    header_compatibility,
    main,
    probe_release,
    read_scenario_descriptions,
    render,
    scenario_profiles,
)

from phos.sentiel.cert import EMAIL_SPEC, LOGON_SPEC

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REAL_ANSWERS = DATA_DIR / "cert-insider-threat" / "answers"

INSIDERS_CSV = """dataset,scenario,details,user,start,end
3.1,1,r3.1-1.csv,CSF0929,07/01/2010 01:24:58,07/16/2010 06:52:00
4.2,1,r4.2-1,AAM0658,01/04/2010 09:00:00,01/05/2010 17:00:00
4.2,2,r4.2-2,PNL0301,02/04/2010 09:00:00,02/05/2010 17:00:00
4.2,2,r4.2-2,LCC0819,03/04/2010 09:00:00,03/05/2010 17:00:00
4.2,3,r4.2-3,CSC0217,04/04/2010 09:00:00,04/05/2010 17:00:00
"""

SCENARIOS_TXT = """Brief Scenario Descriptions

1. User who did not previously use removable drives or work after
hours begins logging in after hours.

2. User begins surfing job websites and soliciting employment from a
competitor.

3. System administrator becomes disgruntled.
"""


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A cert-insider-threat directory holding the answers and no events, as before a download."""
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "insiders.csv").write_text(INSIDERS_CSV, encoding="utf-8")
    (answers / SCENARIOS_FILENAME).write_text(SCENARIOS_TXT, encoding="utf-8")
    return tmp_path


# ------------------------------------------------------------------------------------------------
# Reading CERT's prose
# ------------------------------------------------------------------------------------------------


class TestScenarioDescriptions:
    def test_a_hard_wrapped_paragraph_is_rejoined_into_one_sentence(self, corpus: Path) -> None:
        """CERT wraps at column 70; a description must be quotable as one string."""
        descriptions = read_scenario_descriptions(corpus / "answers")
        assert descriptions["1"] == (
            "User who did not previously use removable drives or work after hours begins "
            "logging in after hours."
        )

    def test_every_numbered_paragraph_is_found(self, corpus: Path) -> None:
        assert sorted(read_scenario_descriptions(corpus / "answers")) == ["1", "2", "3"]

    def test_the_file_may_be_named_directly(self, corpus: Path) -> None:
        direct = read_scenario_descriptions(corpus / "answers" / SCENARIOS_FILENAME)
        assert direct == read_scenario_descriptions(corpus / "answers")

    def test_a_missing_file_gives_no_descriptions_rather_than_raising(self, tmp_path: Path) -> None:
        """The descriptions are commentary; the insider counts stand without them."""
        assert read_scenario_descriptions(tmp_path) == {}


# ------------------------------------------------------------------------------------------------
# Probe 1 — the scenarios
# ------------------------------------------------------------------------------------------------


class TestScenarioProfiles:
    def test_insiders_are_counted_per_scenario(self, corpus: Path) -> None:
        profiles = scenario_profiles(corpus / "answers", "r4.2")
        assert [(p.scenario, p.insiders) for p in profiles] == [("1", 1), ("2", 2), ("3", 1)]

    def test_only_the_named_release_is_counted(self, corpus: Path) -> None:
        """r3.1's row shares scenario 1 with r4.2's and must not be added to it."""
        profiles = scenario_profiles(corpus / "answers", "r3.1")
        assert [(p.scenario, p.insiders) for p in profiles] == [("1", 1)]

    def test_each_profile_carries_cert_description_and_the_register_read_from_it(
        self, corpus: Path
    ) -> None:
        profiles = {p.scenario: p for p in scenario_profiles(corpus / "answers", "r4.2")}
        assert profiles["1"].description.startswith("User who did not previously")
        reading = profiles["1"].reading
        assert reading is not None
        assert reading.detection_register is DetectionRegister.SELF_RELATIVE

    def test_scenarios_are_ordered_numerically(self, corpus: Path) -> None:
        """Ordered by number, not by string, so scenario 10 would not sort before scenario 2."""
        profiles = scenario_profiles(corpus / "answers", "r4.2")
        assert [p.scenario for p in profiles] == ["1", "2", "3"]

    def test_a_release_with_no_labels_is_refused(self, corpus: Path) -> None:
        """An empty label set makes every count vacuous, so it is refused rather than reported."""
        with pytest.raises(ProbeError, match="cannot read the labels"):
            scenario_profiles(corpus / "answers", "r9.9")


# ------------------------------------------------------------------------------------------------
# Probe 2 — the headers
# ------------------------------------------------------------------------------------------------


class TestHeaderCompatibility:
    def test_a_header_the_reader_accepts_is_reported_readable(self, tmp_path: Path) -> None:
        (tmp_path / "logon.csv").write_text("id,date,user,pc,activity\n", encoding="utf-8")
        [log] = header_compatibility(tmp_path, [LOGON_SPEC])
        assert log.readable
        assert (log.missing, log.unaccounted) == ((), ())

    def test_a_missing_required_column_is_named(self, tmp_path: Path) -> None:
        (tmp_path / "logon.csv").write_text("id,date,user,pc\n", encoding="utf-8")
        [log] = header_compatibility(tmp_path, [LOGON_SPEC])
        assert log.missing == ("activity",)
        assert not log.readable

    def test_a_column_the_spec_cannot_account_for_is_named(self, tmp_path: Path) -> None:
        """The reader refuses these too: a column silently dropped is a schema change unnoticed."""
        (tmp_path / "logon.csv").write_text(
            "id,date,user,pc,activity,session_id\n", encoding="utf-8"
        )
        [log] = header_compatibility(tmp_path, [LOGON_SPEC])
        assert log.unaccounted == ("session_id",)
        assert not log.readable

    def test_an_ignored_column_is_not_treated_as_a_schema_change(self, tmp_path: Path) -> None:
        """`LogSpec.ignored` exists so an unlisted column is the thing that stands out."""
        (tmp_path / "email.csv").write_text(
            "id,date,to,from,size,attachments,content\n", encoding="utf-8"
        )
        [log] = header_compatibility(tmp_path, [EMAIL_SPEC])
        assert log.readable

    def test_an_absent_log_is_reported_absent_rather_than_broken(self, tmp_path: Path) -> None:
        [log] = header_compatibility(tmp_path, [LOGON_SPEC])
        assert not log.present
        assert not log.readable

    def test_a_header_is_read_without_reading_the_rest_of_the_file(self, tmp_path: Path) -> None:
        """r3.1's http.csv is 12 GB. The probe must be bounded by a line, not by a file."""
        path = tmp_path / "logon.csv"
        body = "\n".join(f'{{X{n}}},01/02/2010 06:34:00,U{n},PC-1,"Logon' for n in range(5_000))
        path.write_text(f"id,date,user,pc,activity\n{body}\n", encoding="utf-8")
        [log] = header_compatibility(tmp_path, [LOGON_SPEC])
        assert log.readable


# ------------------------------------------------------------------------------------------------
# The whole probe
# ------------------------------------------------------------------------------------------------


class TestProbeRelease:
    def test_labels_are_probed_when_the_events_are_not_on_disk(self, corpus: Path) -> None:
        """The normal case for a release nobody has downloaded."""
        probe = probe_release(corpus, "r4.2")
        assert probe.insiders == 4
        assert not probe.events_on_disk
        assert probe.logs == ()

    def test_headers_are_probed_when_the_events_are_on_disk(self, corpus: Path) -> None:
        release = corpus / "r4.2"
        release.mkdir()
        (release / "logon.csv").write_text("id,date,user,pc,activity\n", encoding="utf-8")
        probe = probe_release(corpus, "r4.2")
        assert probe.events_on_disk
        assert {log.filename for log in probe.logs} == {
            "logon.csv",
            "device.csv",
            "http.csv",
            "email.csv",
            "file.csv",
        }
        readable = [log.filename for log in probe.logs if log.readable]
        assert readable == ["logon.csv"]

    def test_a_missing_answers_file_is_refused_with_the_command_that_fetches_it(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ProbeError, match="fetch_datasets"):
            probe_release(tmp_path, "r4.2")

    def test_the_registers_present_are_summarised(self, corpus: Path) -> None:
        probe = probe_release(corpus, "r4.2")
        assert probe.registers() == {
            DetectionRegister.SELF_RELATIVE,
            DetectionRegister.ACCOUNT_NOT_ACTOR,
        }
        assert probe.insiders_in(DetectionRegister.SELF_RELATIVE) == 3
        assert probe.insiders_in(DetectionRegister.ACCOUNT_NOT_ACTOR) == 1
        assert probe.insiders_in(DetectionRegister.PEER_RELATIVE) == 0


class TestTheReport:
    def test_a_release_with_no_peer_relative_scenario_says_the_claim_stays_untested(
        self, corpus: Path
    ) -> None:
        """The finding the probe exists to deliver, in the words a reader has to act on."""
        report = render(probe_release(corpus, "r4.2"))
        assert "CANNOT test a peer-relative claim" in report
        assert "PEER_REGISTER_UNTESTED_CAVEAT stands" in report

    def test_absent_events_are_reported_unchecked_rather_than_compatible(
        self, corpus: Path
    ) -> None:
        """Unchecked and compatible are the two things this probe must never confuse."""
        report = render(probe_release(corpus, "r4.2"))
        assert "NOT on disk" in report
        assert "NOTHING below was checked" in report
        assert "Unchecked is not the same as compatible" in report
        assert "readable as-is" not in report

    def test_a_scenario_is_reported_with_the_quote_its_reading_rests_on(self, corpus: Path) -> None:
        report = render(probe_release(corpus, "r4.2"))
        assert "read from:" in report
        assert "at markedly higher rates than their previous activity" in report

    def test_each_log_is_reported_as_readable_broken_or_absent(self, corpus: Path) -> None:
        """The three header verdicts, and the difference between them is the point of the probe."""
        release = corpus / "r4.2"
        release.mkdir()
        (release / "logon.csv").write_text("id,date,user,pc,activity\n", encoding="utf-8")
        (release / "device.csv").write_text(
            "id,date,user,pc,session_id\n", encoding="utf-8"
        )  # missing `activity`, and carries a column no spec accounts for
        report = render(probe_release(corpus, "r4.2"))
        assert "logon.csv: readable as-is" in report
        assert (
            "device.csv: NEEDS WORK — missing required activity; unaccounted-for session_id"
            in report
        )
        assert "http.csv: NOT FOUND" in report
        assert "NOTHING below was checked" not in report

    def test_a_scenario_with_no_reading_is_reported_unread_rather_than_guessed_at(
        self, tmp_path: Path
    ) -> None:
        """A release holding a scenario this probe has not read must say so."""
        answers = tmp_path / "answers"
        answers.mkdir()
        (answers / "insiders.csv").write_text(
            "dataset,scenario,details,user,start,end\n"
            "9.9,42,r9.9-42,ZZZ0001,01/04/2010 09:00:00,01/05/2010 17:00:00\n",
            encoding="utf-8",
        )
        report = render(probe_release(tmp_path, "r9.9"))
        assert "scenario 42: 1 insider(s) — UNREAD" in report
        assert "read from:" not in report

    def test_the_probe_runs_end_to_end_and_writes_nothing(
        self, corpus: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = sorted(path.name for path in corpus.rglob("*"))
        assert main(["--release", "r4.2", "--corpus", str(corpus)]) == 0
        assert "70" not in capsys.readouterr().out  # the fixture holds 4, not r4.2's real 70
        assert sorted(path.name for path in corpus.rglob("*")) == before

    def test_a_release_the_labels_do_not_hold_exits_non_zero(
        self, corpus: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["--release", "r9.9", "--corpus", str(corpus)]) == 1
        assert "probe refused" in capsys.readouterr().err


# ------------------------------------------------------------------------------------------------
# Against the real answers archive
# ------------------------------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REAL_ANSWERS / SCENARIOS_FILENAME).is_file(),
    reason=(
        "the real CERT answers archive is not present. Fetch it with:\n"
        "    python scripts/fetch_datasets.py cert-insider-threat --yes"
    ),
)
class TestTheReadingsMatchCertsOwnWords:
    @pytest.mark.parametrize("scenario", sorted(SCENARIO_REGISTERS))
    def test_every_quote_is_verbatim_from_cert(self, scenario: str) -> None:
        """A register reading whose quote has drifted from the source is worse than none.

        The readings in `SCENARIO_REGISTERS` are a judgement about CERT's prose. This is what keeps
        the judgement checkable: the words it rests on must still be in the file it read them from.
        """
        descriptions = read_scenario_descriptions(REAL_ANSWERS)
        assert scenario in descriptions, f"CERT does not describe scenario {scenario}"
        quote = SCENARIO_REGISTERS[scenario].quote
        assert quote in descriptions[scenario], (
            f"scenario {scenario}'s reading quotes {quote!r}, which is not in CERT's own "
            f"description: {descriptions[scenario]!r}"
        )

    def test_r42_holds_seventy_insiders_across_three_scenarios_not_five(self) -> None:
        """The release's actual shape, which is not the one it is usually described with.

        CERT ships five scenario descriptions, and r4.2 contains the first three of them. Any plan
        that budgeted for five scenarios' worth of positives in r4.2 was budgeting for r5.2.
        """
        probe = probe_release(REAL_ANSWERS.parent, "r4.2")
        assert probe.insiders == 70
        assert [(p.scenario, p.insiders) for p in probe.scenarios] == [
            ("1", 30),
            ("2", 30),
            ("3", 10),
        ]

    def test_no_release_on_disk_carries_a_peer_relative_positive(self) -> None:
        """The measurement behind ADR 0022's caveat, extended past r3.1.

        `peer_anomaly` needs a labelled insider who is unremarkable against their own past and
        remarkable against their team's. If some release had one, that release would be the one to
        integrate; none does.
        """
        for release in ("r3.1", "r4.2"):
            probe = probe_release(REAL_ANSWERS.parent, release)
            assert probe.insiders_in(DetectionRegister.PEER_RELATIVE) == 0
            assert DetectionRegister.PEER_RELATIVE not in probe.registers()

    def test_the_reader_can_already_read_every_log_of_the_release_it_was_written_against(
        self,
    ) -> None:
        """The probe's header rules must agree with the reader that actually reads r3.1.

        Skipped along with the class when the corpus is absent, and skipped on its own when only
        the answers were fetched.
        """
        probe = probe_release(REAL_ANSWERS.parent, "r3.1")
        if not probe.events_on_disk:
            pytest.skip("only the answers archive is on disk, not the r3.1 release")
        unreadable = [log.filename for log in probe.logs if not log.readable]
        assert unreadable == []
