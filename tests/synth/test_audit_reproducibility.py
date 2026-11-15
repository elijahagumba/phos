"""The reproducibility audit catches both ways of failing, and is tested on a generator that does.

PART R5's audit makes two claims: the same family and seed produce the same bytes in a *fresh*
process, and a different seed produces a different plant. The second half is the one that is easy
to get wrong — a generator that ignored its seed entirely would pass the first half perfectly, and
a sanity check that only ever runs against a generator that works cannot tell you it would have
noticed.

So most of this module points the audit at **stub generators that fail on purpose**: one that
writes the same plant whatever seed it is given, one that writes something different every run,
and one that falls over. Each is expected to be reported as the specific thing it is. The real
generator is audited once at the end, which is the measurement PART R5 actually asks for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.audit_reproducibility import (
    AuditError,
    Comparison,
    audit_family,
    digests,
    generate_once,
    main,
    structure_of,
)

STUB_HEAD = '''\
"""A stand-in generator, for testing the audit rather than the simulator."""

import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("command")
parser.add_argument("family")
parser.add_argument("seed", type=int)
parser.add_argument("--hours", type=float, default=1.0)
parser.add_argument("--validity-hours", type=float, default=1.0)
parser.add_argument("--events", type=int, default=0)
parser.add_argument("--out", type=Path, required=True)
arguments = parser.parse_args()
'''

STUB_FOOTER = """
directory = arguments.out / f"{arguments.family}-{arguments.seed}"
directory.mkdir(parents=True)
(directory / "plant.json").write_text(json.dumps(plant), encoding="utf-8")
(directory / "telemetry.csv").write_text(payload, encoding="utf-8")
"""


def _stub(tmp_path: Path, name: str, body: str) -> Path:
    """Write a stand-in generator with the real one's command line and return its path."""
    path = tmp_path / f"{name}.py"
    path.write_text(STUB_HEAD + body + STUB_FOOTER, encoding="utf-8")
    return path


def _plant_document(signals: int = 3, parameters: dict[str, float] | None = None) -> str:
    """Return a minimal ``plant.json`` of the shape ``structure_of`` reads."""
    return json.dumps(
        {
            "signals": [{"key": f"tag_{index}"} for index in range(signals)],
            "components": [{"component_id": "tank"}],
            "controllers": [{"controller_id": "level"}],
            "units": [{"unit_id": "tank"}],
            "parameters": parameters if parameters is not None else {"trains": 2.0},
        }
    )


def test_the_structure_read_is_the_plants_own_description(tmp_path: Path) -> None:
    """Not the digests. Noise alone changes every digest while leaving the plant identical."""
    directory = tmp_path / "plant"
    directory.mkdir()
    (directory / "plant.json").write_text(_plant_document(signals=4), encoding="utf-8")

    structure = structure_of(directory)

    assert structure["signals"] == 4
    assert structure["first_tag"] == "tag_0"
    assert structure["parameters"] == (("trains", 2.0),)


def test_two_plants_differing_only_in_a_parameter_are_structurally_different(
    tmp_path: Path,
) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    one.mkdir()
    other.mkdir()
    (one / "plant.json").write_text(_plant_document(parameters={"trains": 2.0}), encoding="utf-8")
    (other / "plant.json").write_text(_plant_document(parameters={"trains": 5.0}), encoding="utf-8")

    assert structure_of(one) != structure_of(other)


def test_digests_cover_every_file_and_no_directory(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("one", encoding="utf-8")
    (tmp_path / "b.json").write_text("two", encoding="utf-8")
    (tmp_path / "nested").mkdir()

    found = digests(tmp_path)

    assert sorted(found) == ["a.csv", "b.json"]
    assert found["a.csv"] != found["b.json"]
    assert len(found["a.csv"]) == 64


def test_a_generator_that_ignores_its_seed_is_reported_as_a_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half of the audit that is easy to leave as decoration. Here it fires.

    This stub is perfectly deterministic — it would pass a reproducibility check written without
    the converse — and it draws the same plant for every seed, which makes it a stored fixture
    wearing a generator's command line.
    """
    stub = _stub(
        tmp_path,
        "fixture",
        f"plant = json.loads({_plant_document()!r})\npayload = 'always the same\\n'\n",
    )
    monkeypatch.setattr("scripts.audit_reproducibility.GENERATOR", stub)

    comparison = audit_family("level_flow", 1, 1.0, events=0, validity_hours=1.0)

    assert comparison.identical
    assert not comparison.structurally_varied
    assert not comparison.passed
    assert "FAIL" in comparison.summary()


def test_a_generator_that_is_not_reproducible_is_reported_as_differing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named files, not a bare verdict: which output moved is the first thing to look at."""
    stub = _stub(
        tmp_path,
        "drifting",
        "import time\n"
        f"plant = json.loads({_plant_document()!r})\n"
        "plant['parameters']['trains'] = float(arguments.seed)\n"
        "payload = f'{time.time_ns()}\\n'\n",
    )
    monkeypatch.setattr("scripts.audit_reproducibility.GENERATOR", stub)

    comparison = audit_family("level_flow", 1, 1.0, events=0, validity_hours=1.0)

    assert not comparison.identical
    assert comparison.differences == ("telemetry.csv",)
    assert comparison.structurally_varied
    assert not comparison.passed


def test_a_generator_that_fails_is_an_audit_error_not_a_reproducibility_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two must not be confused: one says the simulator is broken, the other says the audit is.

    Reporting a crashed generator as "not reproducible" would send whoever reads it looking for a
    stray random stream when the actual message was on stderr.
    """
    stub = tmp_path / "broken.py"
    stub.write_text(
        'import sys\nsys.stderr.write("the family does not exist\\n")\nsys.exit(2)\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.audit_reproducibility.GENERATOR", stub)

    with pytest.raises(AuditError, match="exit 2"):
        generate_once("nonsense", 1, 1.0, tmp_path / "out", events=0, validity_hours=1.0)


def test_a_generator_that_writes_nothing_is_refused_rather_than_compared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two empty directories are byte-identical, which is the most dangerous kind of pass."""
    stub = tmp_path / "empty.py"
    stub.write_text(
        "import sys\nfrom pathlib import Path\n"
        'Path(sys.argv[sys.argv.index("--out") + 1]).mkdir(parents=True)\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.audit_reproducibility.GENERATOR", stub)

    with pytest.raises(AuditError, match="expected one"):
        generate_once("level_flow", 1, 1.0, tmp_path / "out", events=0, validity_hours=1.0)


def test_the_command_line_returns_two_when_the_audit_itself_could_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Distinct from the 1 a reproducibility failure returns, so a CI step can tell them apart."""
    stub = tmp_path / "broken.py"
    stub.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    monkeypatch.setattr("scripts.audit_reproducibility.GENERATOR", stub)

    assert main(["--family", "level_flow", "--hours", "1", "--validity-hours", "1"]) == 2


def test_the_command_line_returns_one_when_a_family_fails_the_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _stub(
        tmp_path,
        "fixture2",
        f"plant = json.loads({_plant_document()!r})\npayload = 'always the same\\n'\n",
    )
    monkeypatch.setattr("scripts.audit_reproducibility.GENERATOR", stub)

    assert (
        main(
            [
                "--family",
                "level_flow",
                "--hours",
                "1",
                "--validity-hours",
                "1",
                "--events",
                "0",
            ]
        )
        == 1
    )


def test_a_comparison_passes_only_when_both_halves_hold() -> None:
    def comparison(identical: bool, varied: bool) -> Comparison:
        return Comparison(
            family="level_flow",
            seed=1,
            identical=identical,
            differences=() if identical else ("telemetry.csv",),
            files=8,
            structurally_varied=varied,
            varied_fields=("signals",) if varied else (),
        )

    assert comparison(True, True).passed
    assert not comparison(True, False).passed
    assert not comparison(False, True).passed
    assert not comparison(False, False).passed
    assert "pass" in comparison(True, True).summary()


def test_the_real_generator_is_reproducible_across_fresh_processes_and_varies_with_its_seed() -> (
    None
):
    """The measurement PART R5 asks for, on one family at the shortest useful run.

    One family rather than five: the other four are audited by
    ``python scripts/audit_reproducibility.py --all-families``, which is the command the part
    records a result for. What belongs in the default suite is that the audit and the generator
    still agree — three real generations at two hours each, which is seconds rather than minutes.
    """
    comparison = audit_family("level_flow", 7701, 2.0, events=0, validity_hours=1.0)

    assert comparison.identical, f"differed across processes: {comparison.differences}"
    assert comparison.structurally_varied, "a new seed drew the same plant"
    assert comparison.files >= 7
