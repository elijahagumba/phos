"""The published bounds table says what the code actually draws.

PART R2 asks for every randomised parameter and its bounds to be documented. A table maintained by
hand would be wrong within a month and nobody would know, so it is generated from the registry and
this module is what makes the two stay equal: change a bound and this test fails until the document
is regenerated.

It also pins the thing that would quietly undo the whole arrangement — a sealed family's bounds
appearing in a document read by whoever is being examined on it.
"""

from __future__ import annotations

import pytest
from scripts.document_families import (
    BEGIN_MARKER,
    END_MARKER,
    README_PATH,
    DocumentationError,
    current_section,
    main,
    rendered_section,
    rewritten,
)

from phos.synth.families import list_families

DOCUMENT = README_PATH.read_text(encoding="utf-8")


def test_the_committed_table_matches_the_registry() -> None:
    assert current_section(DOCUMENT) == rendered_section(), (
        "a family's bounds have changed; regenerate with "
        "`python scripts/document_families.py --write`"
    )


def test_the_checker_agrees() -> None:
    assert main([]) == 0


def test_every_open_family_and_bound_is_in_the_document() -> None:
    for family in list_families():
        assert f"`{family.family_id}`" in DOCUMENT
        for bound in family.bounds():
            assert f"`{bound.name}`" in DOCUMENT, f"{family.family_id}:{bound.name} is undocumented"


def test_the_sealed_family_is_not_in_the_document() -> None:
    """Its bounds are not published. The table is read by whoever is being examined on it."""
    assert "gas_pressure" not in DOCUMENT
    assert "Gas pressure network" not in DOCUMENT
    assert "compressor" not in DOCUMENT.lower()


def test_a_document_with_no_markers_is_refused_rather_than_silently_unchecked() -> None:
    with pytest.raises(DocumentationError, match="stops being checked"):
        current_section("# A document somebody stripped the markers out of\n")


def test_regenerating_is_idempotent() -> None:
    once = rewritten(DOCUMENT)

    assert rewritten(once) == once
    assert once.count(BEGIN_MARKER) == 1
    assert once.count(END_MARKER) == 1


def test_the_table_carries_the_reason_for_each_bound_not_just_its_range() -> None:
    """A range with no argument beside it is a number nobody can disagree with."""
    section = current_section(DOCUMENT)

    for family in list_families():
        for bound in family.bounds():
            assert bound.why in section, f"{family.family_id}:{bound.name} lost its reason"
