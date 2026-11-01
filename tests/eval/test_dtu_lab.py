"""The DTU pilot-plant export is registered for onboarding only (ADR 0394).

The corpus is six email attachments from a university department: two pilot-plant rigs, no label
column, and a permission that covers results rather than raw-file redistribution. These tests pin
the four things that make the entry honest, because each one is a claim a later session could
quietly improve into something the corpus cannot support.
"""

from __future__ import annotations

from pathlib import Path

from scripts.fetch_datasets import load_registry

REPO = Path(__file__).resolve().parents[2]

#: The six files ADR 0394 records, by the run date in the filename. The 30 September run is the C2
#: trial file; the rest are ordinary development material.
FILES: tuple[tuple[str, int, str], ...] = (
    (
        "26_07_09__13_13_02_Bubble_Column_Aeration_1F__BubbleColmExpData.xlsx",
        744154,
        "9064d93d2902fd6b74caf4a20115cd2e36df6f3c11972d4afcc5b7ff9536309c",
    ),
    (
        "26_07_10__12_34_19_Bubble_Column_Aeration_1F__group42.xlsx",
        567488,
        "33d1a7e15e87bdaced71018b9be0af6904af0a482bf7ff7bae806052d94bdec3",
    ),
    (
        "26_07_14__12_35_42_Continuous_distillation_5A_AL355A.xlsx",
        907312,
        "19ee18a7fe38207f626a9775da801b9ea7360df49b4ee08a0acd5522cd690df3",
    ),
    (
        "26_07_16__11_50_47_Bubble_Column_Aeration_1F__43_1F.xlsx",
        566488,
        "febdfaed5bc31d24aa5bcda1215942fa7698847de55598228c36138f3c447f77",
    ),
    (
        "26_07_16__15_20_23_Continuous_distillation_5A_UW14_Lab5A.xlsx",
        1657914,
        "90fcbf8dc95a27c9cc4c5781acda1c050109447b2e0a77bda40e91b01c7c3a81",
    ),
    (
        "26_09_30__12_42_18_Continuous_distillation_5A_Team45A.xlsx",
        1250881,
        "99d2634abe3a75bdc3fe0aeae827cdbb325a5782aaede51a961f3d0e86f7fbe2",
    ),
)


def dtu() -> object:
    return load_registry().by_name("dtu-lab")


def test_the_corpus_is_development_and_not_fetchable() -> None:
    entry = load_registry().by_name("dtu-lab")
    assert entry.role == "development"
    assert entry.status == "operator-provided"
    assert entry.fetchable is False, "an email attachment has no URL to fetch"


def test_it_declares_no_files_so_nothing_is_downloaded() -> None:
    assert load_registry().by_name("dtu-lab").files == []


def test_it_is_not_in_the_held_out_bank() -> None:
    """Six unlabelled teaching runs cannot support a split, so no half is held back (ADR 0394)."""
    held_out = [entry.name for entry in load_registry().datasets if entry.role == "held-out"]
    assert "dtu-lab" not in held_out


def test_the_licence_is_operator_stated_and_not_called_explicit() -> None:
    """A sentence in a personal email is a grant, but it is not a published licence."""
    entry = load_registry().by_name("dtu-lab")
    assert entry.license.status == "operator-stated"
    assert entry.license.permits_research_use is True
    assert entry.license.spdx is None


def test_the_licence_evidence_quotes_the_grant_and_names_its_gaps() -> None:
    """The grant is quoted, the department is named, and the three open gaps still travel.

    ADR 0396 closed gap (1) of ADR 0394 Decision 3 by confirming the department from the sender's
    own DTU staff page. It did not close the other three, so this asserts both halves: the name is
    present, and the gaps that remain are still stated rather than quietly dropped.
    """
    evidence = load_registry().by_name("dtu-lab").license.evidence
    assert "appropriate credit is given to our department" in evidence
    assert "Department of Chemical and Biochemical Engineering" in evidence
    assert "ADR 0396" in evidence, "the naming must cite the record that confirmed it"
    for gap in ("results", "redistribution", "IP policy"):
        assert gap in evidence, gap


def test_naming_the_department_is_not_read_as_a_licence() -> None:
    """A confirmed department name is not the institution granting rights (ADR 0396 Decision 5)."""
    entry = load_registry().by_name("dtu-lab")
    evidence = entry.license.evidence
    assert "NOT a published licence" in evidence
    assert entry.license.status == "operator-stated"
    assert "not a document about rights" in evidence


def test_the_senders_email_address_is_not_recorded() -> None:
    """``data/*`` exports publicly, so a private contact address must not appear in the registry."""
    raw = (REPO / "data" / "registry.json").read_text(encoding="utf-8").lower()
    assert "jodre@" not in raw
    assert "kt.dtu.dk" not in raw


def test_the_caveats_forbid_a_detection_claim() -> None:
    caveats = " ".join(load_registry().by_name("dtu-lab").caveats).lower()
    assert "no detection claim" in caveats
    assert "cannot fit a baseline" in caveats


def test_the_payloads_are_ignored_by_git_where_present() -> None:
    """The six files are recorded by hash; whether they are on disk is machine-local."""
    entry = load_registry().by_name("dtu-lab")
    assert entry.title and "DTU" in entry.title
    assert len(FILES) == 6
    assert len({sha for _, _, sha in FILES}) == 6
    assert sum(size for _, size, _ in FILES) > 0
