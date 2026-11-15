"""What the randomisation modules are, and the one thing none of them may reach for.

PART S0 created `families`, `randomise` and `validity` empty, and this module asserted exactly
that: three docstrings and three empty public surfaces. PART R2 filled the first two and PART R3
the third, so the assertion that they are empty has been replaced by the assertion that they are
not. That assertion earned its keep on the way: it failed when R3 built the gate, which is
precisely what "still empty until its own part" was written to detect.

The Atlas check is the part that matters and it has been widened. PART R2 asks for a test that no
module it adds imports Atlas, and rather than list them — a list that goes stale the moment a
family is added — this walks every module in the package and allows exactly one exception, named
and argued below.

The check reads each module's source with `ast` rather than inspecting ``sys.modules``, because by
the time this file runs the suite has imported Atlas many times over for its own tests, so an
interpreter-wide check would assert nothing.
"""

import ast
from pathlib import Path
from types import ModuleType

import phos.synth
from phos.synth import families, randomise, validity

FILLED: tuple[ModuleType, ...] = (families, randomise, validity)
"""The three modules PART S0 created empty, all of them now built: `families` and `randomise` in
PART R2, `validity` in PART R3."""

ATLAS_IMPORT_ALLOWED: frozenset[str] = frozenset({"phos/synth/topology.py"})
"""The one module that may import Atlas, and why.

`phos.synth.topology` renders a generated plant's subsystem map in the format
`phos.atlas.topology.load_topology` reads, and it imports that module's ``SCHEMA_VERSION`` and
value types so the two cannot drift apart. Re-declaring the schema here instead would mean a
generated corpus could claim a version Atlas no longer accepts, and nothing would notice until a
measurement failed. It is a read of a public format, not a use of a detector.
"""


def _imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def _package_modules() -> tuple[Path, ...]:
    root = Path(str(phos.synth.__file__)).parent
    return tuple(sorted(root.rglob("*.py")))


def test_every_randomisation_module_documents_itself() -> None:
    for module in FILLED:
        assert module.__doc__, f"{module.__name__} must document what it is for"


def test_the_filled_modules_declare_a_public_surface() -> None:
    for module in FILLED:
        assert module.__all__, f"{module.__name__} holds behaviour now and must name it"


def test_the_gate_refuses_as_well_as_passes() -> None:
    """What replaced "validity is still empty".

    The emptiness assertion was S0's and R2's statement that no plant was being accepted by code
    nobody had reviewed. Now that the gate exists the equivalent statement is that it can say no:
    a gate whose only outcome is a pass is the same absence of review wearing a module.
    """
    assert "check" in validity.__all__
    assert "Verdict" in validity.__all__
    assert validity.Verdict(plant_id="p", process="q", hours=1.0).passed
    refused = validity.Verdict(
        plant_id="p",
        process="q",
        hours=1.0,
        findings=(validity.Finding("conservation", "mass is not conserved", "level"),),
    )
    assert not refused.passed
    assert "mass is not conserved" in refused.summary()


def test_no_module_in_the_package_imports_atlas_except_the_one_that_may() -> None:
    root = Path(str(phos.synth.__file__)).parent.parent.parent
    offenders: dict[str, list[str]] = {}
    for path in _package_modules():
        relative = path.relative_to(root).as_posix()
        if relative in ATLAS_IMPORT_ALLOWED:
            continue
        reaching = sorted(name for name in _imported_names(path) if name.startswith("phos.atlas"))
        if reaching:
            offenders[relative] = reaching

    assert not offenders, (
        "the simulator must not depend on the detector it generates data for: "
        f"{offenders}. If a module genuinely needs a public Atlas format, argue it in "
        "ATLAS_IMPORT_ALLOWED rather than widening this test."
    )


def test_the_allowed_exception_is_real() -> None:
    root = Path(str(phos.synth.__file__)).parent.parent.parent
    for relative in ATLAS_IMPORT_ALLOWED:
        path = root / relative
        assert path.exists(), f"{relative} is allowed to import Atlas but does not exist"
        assert any(name.startswith("phos.atlas") for name in _imported_names(path)), (
            f"{relative} no longer imports Atlas; take it out of ATLAS_IMPORT_ALLOWED rather "
            "than leaving a standing permission nothing uses"
        )
