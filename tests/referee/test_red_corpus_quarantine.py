"""The referee does not fit a corpus the tier rule marks never-read.

ADR 0461. The six entry points that were built around HAI, BATADAL and SWaT raise
before they open a path. The names they would have fitted are the ones
``phos.genesis.tiercheck.resolve`` already refuses, plus SWaT, which the same
rule bars by licence.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from tests.lab_only import RULES_ABSENT_REASON

from phos.eval import Dataset
from phos.genesis.tiercheck import resolve
from phos.guards import tiers
from phos.referee.demo import batadal_detector, hai_detector, swat_detector
from phos.referee.detectors import (
    AtlasDetector,
    _build_batadal_code_law_detections,
    _build_batadal_flow_anomaly_detections,
    _build_hai_code_law_detections,
)
from phos.referee.quarantine import QUARANTINE_ADR, QuarantinedCorpusError

REPO = Path(__file__).resolve().parents[2]
REFEREE = REPO / "src" / "phos" / "referee"

# The rule is read while this module is being **imported**, so no marker exists yet to be
# honoured and a module-level skip is the only thing that runs early enough — the same reason
# `tests/genesis/test_tiercheck.py` carries one. `docs/rules/` symlinks into `.cursor/rules/`,
# a forbidden path, so in the public tree this import would raise and take the whole collection
# down with it (ADR 0440). Every assertion below still runs in the lab, where the rule is present.
_RULE_PATH = REPO / "docs" / "rules" / "data-tiers.md"
if not _RULE_PATH.is_file():  # pragma: no cover - public tree only
    pytest.skip(
        f"docs/rules/data-tiers.md is absent. {RULES_ABSENT_REASON}",
        allow_module_level=True,
    )

RULE = _RULE_PATH.read_text(encoding="utf-8")

#: Path prefixes a red corpus would be opened through. None of these may remain
#: in the referee package: a constant that names the file is still a way to open it.
FORBIDDEN_PATHS = (
    "data/hai/",
    "data/hai-21.03",
    "data/hai-22.04",
    "data/hai-23.05",
    "data/batadal/",
)


def _red_names() -> list[str]:
    """Every never-read name the shipped rule lists, sorted."""
    return sorted(tiers.parse(RULE).red)


def _body_after_docstring(fn: Callable[..., Any]) -> list[ast.stmt]:
    """The function body, docstring skipped, taken from the source as it is shipped."""
    source = inspect.getsource(fn)
    # getsource keeps the indent of a method. dedent would also strip a docstring's
    # relative indent incorrectly for some shapes, so shift by the def line only.
    lines = source.splitlines()
    indent = len(lines[0]) - len(lines[0].lstrip())
    shifted = "\n".join(line[indent:] if line.startswith(" " * indent) else line for line in lines)
    tree = ast.parse(shifted)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    body = list(function.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


class TestTheResolverNamesTheRedCorpora:
    def test_the_rule_names_the_five_validation_corpora(self) -> None:
        red = set(_red_names())
        assert {"hai", "hai-21.03", "hai-22.04", "hai-23.05", "batadal"} <= red

    @pytest.mark.parametrize("corpus", _red_names())
    def test_every_never_read_name_is_refused(self, corpus: str) -> None:
        verdict = resolve(REPO, corpus)
        assert verdict.refused, corpus
        assert verdict.tier == "red"

    def test_swat_is_barred_by_the_licence_sentence(self) -> None:
        assert "Never use" in RULE
        assert "SWaT" in RULE


class TestTheEntryPointsRefuseBeforeAPathOpens:
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda: hai_detector(), id="hai"),
            pytest.param(lambda: batadal_detector(), id="batadal"),
            pytest.param(lambda: swat_detector(Path("data/swat/train.csv")), id="swat"),
            pytest.param(
                lambda: _build_batadal_code_law_detections(cast(Dataset, object())),
                id="batadal-code-law",
            ),
            pytest.param(
                lambda: _build_batadal_flow_anomaly_detections(cast(Dataset, object())),
                id="batadal-flow",
            ),
            pytest.param(
                lambda: _build_hai_code_law_detections(cast(Dataset, object())),
                id="hai-code-law",
            ),
        ],
    )
    def test_each_entry_point_raises_and_names_the_record(self, call: Callable[[], None]) -> None:
        with pytest.raises(QuarantinedCorpusError) as caught:
            call()
        assert QUARANTINE_ADR in str(caught.value)
        assert caught.value.corpus

    @pytest.mark.parametrize(
        "fn",
        [
            hai_detector,
            batadal_detector,
            swat_detector,
            _build_batadal_code_law_detections,
            _build_batadal_flow_anomaly_detections,
            _build_hai_code_law_detections,
        ],
    )
    def test_the_raise_is_the_first_act(self, fn: Callable[..., Any]) -> None:
        body = _body_after_docstring(fn)
        assert body, fn
        assert isinstance(body[0], ast.Raise), f"{fn} does work before it refuses"

    def test_the_run_path_does_not_call_the_quarantined_builders(self) -> None:
        banned = {
            "_build_batadal_code_law_detections",
            "_build_batadal_flow_anomaly_detections",
            "_build_hai_code_law_detections",
        }
        tree = ast.parse(textwrap.dedent(inspect.getsource(AtlasDetector.run)))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert called.isdisjoint(banned)

    def test_the_package_does_not_name_a_red_corpus_path(self) -> None:
        offenders: list[str] = []
        for path in sorted(REFEREE.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in FORBIDDEN_PATHS:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO)} names {needle}")
        assert offenders == []
