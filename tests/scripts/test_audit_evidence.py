"""Telling a cited commit apart from a checksum, and an explained citation from a new orphan."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.audit_evidence import (
    audit,
    blocks_of,
    classify,
    main,
    paragraph_at,
    read_acknowledgement,
    render,
    resolve_cited_path,
    without_acknowledgements,
)


def _classify(line: str, token: str) -> str:
    return classify(line, line.index(token), token)


@pytest.mark.parametrize(
    "line",
    [
        "The one score declared in ADR 0254 was run after commit `592d051`:",
        "Lanes Q, R, and T were built on `7ff682c` and merged to `main` in the order",
        "The run is `uv run python scripts/score.py` at `b3d2dd8`. Report:",
        "The tree was read at commit `2a814ceb` on 2026-10-04.",
    ],
)
def test_a_commit_citation_is_a_commit(line: str) -> None:
    token = line.split("`")[-2]
    assert _classify(line, token) == "commit"


@pytest.mark.parametrize(
    ("line", "token"),
    [
        ("Payload: `d.zip`, 134,034,872 bytes, MD5 `a540979c63120c9a0295ff974933580f`", "a540979c"),
        ("   md5 `ca8efbb6dbcfae3516583937eb5b5402`) and `Kelmarsh.zip` (174,604,722", "ca8ef"),
        ("2026-10-04 (blobs `2591ce26`, `cafe86ac`, `8b3e3fcb`). The paper adds", "2591ce26"),
        ("| Version pin | **found.** Pin `5789064` / `v2_0`, not the concept DOI. |", "5789064"),
        ("pointed at figshare file `24844280`, which is `r6.2.tar.bz2` —", "24844280"),
    ],
)
def test_somebody_elses_identifier_is_not_a_commit(line: str, token: str) -> None:
    assert _classify(line, token) == "foreign"


def test_an_all_digit_token_is_never_a_commit() -> None:
    assert _classify("superseded by `4824287500` in the register", "4824287500") == "foreign"


def test_a_token_with_no_cue_is_reported_rather_than_guessed() -> None:
    assert _classify("The value `deadbeef1234` sits alone.", "deadbeef1234") == "unclassified"


@pytest.mark.parametrize(
    "value",
    [
        "data/*",
        "data/<name>/manifest.json",
        "data/synth/",
        "src/phos/atlas/*.py",
    ],
)
def test_a_glob_or_an_uncommitted_payload_is_not_a_dangling_path(value: str) -> None:
    assert resolve_cited_path(value) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("tests/atlas/test_engine.py::test_a_narrative_drills_down", "tests/atlas/test_engine.py"),
        ("src/phos/atlas/multivariate.py:697", "src/phos/atlas/multivariate.py"),
        ("eval_runs/build/d/REPORT.md", "eval_runs/build/d/REPORT.md"),
    ],
)
def test_a_node_id_or_a_line_resolves_to_its_file(value: str, expected: str) -> None:
    assert resolve_cited_path(value) == Path(expected)


def test_a_marker_does_not_reach_a_citation_in_another_paragraph() -> None:
    """A marker is scoped to its own block.

    The bug this guards: "upstream" in an unrelated ADR title filed one of our own commits as
    somebody else's, because the marker was matched against the whole file.
    """
    lines = [
        "Pass criteria frozen at `93156a5`.",
        "",
        "| [0135](0135-decisive-witnesses-and-upstream-first.md) | Two naming rules |",
    ]
    blocks = paragraph_at(lines)
    assert "upstream" not in blocks[0]
    assert "upstream" in blocks[2]


def test_a_marker_sentence_that_wraps_is_still_found() -> None:
    lines = [
        "The bytes are locked by sha256. That commit is the publisher's head",
        "and it is not in this repository; it is the pin every entry uses.",
    ]
    blocks = paragraph_at(lines)
    assert "not in this repository" in blocks[0]
    assert "not in this repository" in blocks[1]


def test_a_blank_line_ends_a_paragraph() -> None:
    blocks = paragraph_at(["first", "", "second"])
    assert blocks[0] == "first"
    assert blocks[1] == ""
    assert blocks[2] == "second"


ABSENT_COMMIT = "0123456789abcdef0123456789abcdef01234567"
OTHER_COMMIT = "76543210fedcba9876543210fedcba9876543210"
REASON = "the lane that carried it is deliberately unmerged"


def _record(tmp_path: Path, body: str) -> Path:
    record = tmp_path / "0999-a-record-under-test.md"
    record.write_text(body, encoding="utf-8")
    return record


def test_a_citation_that_stops_resolving_fails_the_gate(tmp_path: Path) -> None:
    """The whole point of the gate: a new orphan nobody has explained fails the build."""
    _record(tmp_path, f"The score was run after commit `{ABSENT_COMMIT}`.\n")

    result = audit([str(tmp_path)], "HEAD")

    assert [cited.value for cited in result.orphans] == [ABSENT_COMMIT]
    assert [cited.value for cited in result.unacknowledged] == [ABSENT_COMMIT]
    assert not result.gated


def test_the_failing_citation_is_named_with_its_file_and_line(tmp_path: Path) -> None:
    _record(tmp_path, f"A line of prose.\n\nRun after commit `{ABSENT_COMMIT}`.\n")

    report = render(audit([str(tmp_path)], "HEAD"), "HEAD")

    assert f"0999-a-record-under-test.md:3  {ABSENT_COMMIT}" in report
    assert "The gate fails" in report


def test_an_absent_cited_path_fails_the_gate_by_default(tmp_path: Path) -> None:
    """An absent path is never waved through because it is only a path."""
    _record(tmp_path, "The report is at `eval_runs/no-such-run/REPORT.md`.\n")

    result = audit([str(tmp_path)], "HEAD")

    assert [cited.value for cited in result.unacknowledged] == ["eval_runs/no-such-run/REPORT.md"]
    assert not result.gated


def test_an_acknowledged_citation_passes_the_gate(tmp_path: Path) -> None:
    _record(
        tmp_path,
        f"The score was run after commit `{ABSENT_COMMIT}`.\n"
        f"<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert [ack.token for ack in result.acknowledged] == [ABSENT_COMMIT]
    assert not result.unacknowledged
    assert result.gated
    assert not result.clean, "acknowledging an item does not make it resolve"


def test_acknowledging_does_not_hide_the_item_from_the_report(tmp_path: Path) -> None:
    """An acknowledged item is still listed. The gate is not a way of shortening the audit."""
    _record(
        tmp_path,
        f"Run after commit `{ABSENT_COMMIT}`.\n<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n",
    )

    report = render(audit([str(tmp_path)], "HEAD"), "HEAD")

    assert "## Orphaned commits (1)" in report
    assert "## Acknowledged where they are cited (1)" in report


def test_an_acknowledgement_that_no_longer_matches_its_citation_fails(tmp_path: Path) -> None:
    """The record moved and the marker did not, so the marker vouches for nothing.

    This is what stops an acknowledgement drifting onto a different citation: it is bound to
    the token it names, so repointing the citation breaks the match in both directions.
    """
    _record(
        tmp_path,
        f"Run after commit `{OTHER_COMMIT}`.\n<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert [ack.token for ack in result.stale] == [ABSENT_COMMIT]
    assert [cited.value for cited in result.unacknowledged] == [OTHER_COMMIT]
    assert not result.gated


def test_an_acknowledgement_of_a_citation_that_now_resolves_is_stale(tmp_path: Path) -> None:
    """Someone fixed the citation. The marker has to go, rather than wait for a new orphan."""
    _record(
        tmp_path,
        "The report is at `scripts/audit_evidence.py`.\n"
        "<!-- evidence-ack: scripts/audit_evidence.py — this path was never written here -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert [ack.token for ack in result.stale] == ["scripts/audit_evidence.py"]
    assert not result.gated


def test_an_acknowledgement_does_not_reach_into_another_paragraph(tmp_path: Path) -> None:
    _record(
        tmp_path,
        f"Run after commit `{ABSENT_COMMIT}`.\n\n"
        f"<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert [cited.value for cited in result.unacknowledged] == [ABSENT_COMMIT]
    assert [ack.token for ack in result.stale] == [ABSENT_COMMIT]
    assert not result.gated


def test_the_same_citation_is_not_acknowledged_twice(tmp_path: Path) -> None:
    _record(
        tmp_path,
        f"Run after commit `{ABSENT_COMMIT}`.\n"
        f"<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n"
        f"<!-- evidence-ack: {ABSENT_COMMIT} — a second reason, which covers nothing new -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert len(result.acknowledged) == 1
    assert len(result.stale) == 1
    assert not result.gated


def test_an_acknowledgement_is_not_itself_read_as_a_citation(tmp_path: Path) -> None:
    """The marker names a token. Read as prose it would cite it again and skew the audit."""
    _record(
        tmp_path,
        f"Run after commit `{ABSENT_COMMIT}`.\n<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert len(result.orphans) == 1


def test_a_reason_in_a_marker_cannot_change_how_a_citation_is_classified(tmp_path: Path) -> None:
    """A marker is kept out of the prose, so its wording cannot refile a neighbouring commit."""
    _record(
        tmp_path,
        f"Run after commit `{ABSENT_COMMIT}`.\n"
        "<!-- evidence-ack: zzz — this commit is not in this repository at all -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert not result.external
    assert [cited.value for cited in result.orphans] == [ABSENT_COMMIT]


@pytest.mark.parametrize(
    "body",
    [
        f": {ABSENT_COMMIT}",
        f": {ABSENT_COMMIT} — known",
        f": {ABSENT_COMMIT} — not built",
        f" {ABSENT_COMMIT} — {REASON}",
        f": — {REASON}",
    ],
)
def test_a_marker_without_a_stated_reason_is_refused(body: str) -> None:
    """Acknowledging an item is stating why. Listing a SHA states nothing."""
    with pytest.raises(ValueError):
        read_acknowledgement(body)


def test_a_marker_with_a_reason_is_read(tmp_path: Path) -> None:
    token, reason = read_acknowledgement(f": {ABSENT_COMMIT} — {REASON}")
    assert (token, reason) == (ABSENT_COMMIT, REASON)


def test_a_malformed_marker_fails_the_gate_rather_than_being_ignored(tmp_path: Path) -> None:
    """A typo must not quietly stop acknowledging the thing it was written for."""
    _record(
        tmp_path,
        f"Run after commit `{ABSENT_COMMIT}`.\n<!-- evidence-ack {ABSENT_COMMIT} {REASON} -->\n",
    )

    result = audit([str(tmp_path)], "HEAD")

    assert len(result.malformed) == 1
    assert not result.gated


def test_a_marker_that_is_not_a_complete_comment_is_reported(tmp_path: Path) -> None:
    _record(tmp_path, f"Run after commit `{ABSENT_COMMIT}`.\n<!-- evidence-ack: oops\n")

    result = audit([str(tmp_path)], "HEAD")

    assert len(result.malformed) == 1
    assert "one line" in result.malformed[0].problem


def test_the_strict_flag_is_the_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """What CI runs.

    One exit code for a record that explains itself, one for a record that does not.
    """
    record = _record(tmp_path, f"Run after commit `{ABSENT_COMMIT}`.\n")
    assert main(["--paths", str(tmp_path), "--strict"]) == 1

    record.write_text(
        f"Run after commit `{ABSENT_COMMIT}`.\n<!-- evidence-ack: {ABSENT_COMMIT} — {REASON} -->\n",
        encoding="utf-8",
    )
    assert main(["--paths", str(tmp_path), "--strict"]) == 0
    capsys.readouterr()


def test_without_the_strict_flag_the_audit_only_reports(tmp_path: Path) -> None:
    _record(tmp_path, f"Run after commit `{ABSENT_COMMIT}`.\n")
    assert main(["--paths", str(tmp_path)]) == 0


def test_a_marker_line_does_not_split_the_paragraph_it_sits_in() -> None:
    """Blanking a marker must not turn its line into a paragraph break.

    A marker written on its own line is the readable placement, and it would be useless if it
    fell out of the block holding the citation it names.
    """
    marker = "<!-- evidence-ack: src/phos/api/ — not built here -->"
    lines = ["cites `src/phos/api/`", marker, "and the prose continues"]

    assert blocks_of(lines) == [0, 0, 0], "the marker's line is not a paragraph break"

    scanned = [without_acknowledgements(line) for line in lines]
    assert "evidence-ack" not in " ".join(scanned), "the marker is kept out of the prose"
    assert len(scanned[1]) == len(marker), "blanking a marker preserves column offsets"

    joined = paragraph_at(lines, scanned)[0]
    assert joined.split() == ["cites", "`src/phos/api/`", "and", "the", "prose", "continues"]
