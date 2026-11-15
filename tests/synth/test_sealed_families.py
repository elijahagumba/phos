"""A sealed family is absent until the environment admits it, and then it is an ordinary family.

PART R2 task 5. The seal has to hold in three ways and each is worth its own assertion:

1. **Absent from every listing.** `list_families()` does not return it, and neither does
   `list_families(include_sealed=True)` while the switch is off — asking politely is not the
   switch.
2. **Absent by name.** `get_family("gas_pressure")` fails exactly as it fails for a family that
   does not exist, and the message does not hint that there is one more. A listing that said
   "there is another, but you may not have it" would leak the thing sealing is for.
3. **Absent from the builder.** Because the sealed package is only imported when the switch is
   on, its *process template* is unregistered too, so a spec naming a sealed process cannot be
   built at all. That is a stronger guarantee than hiding it from a listing, and it is the one
   that matters if a sealed spec ever leaks on to a disk somebody else can read.

**Why the subprocesses.** `phos.synth.families` caches whether it has imported the sealed package,
and once imported a module stays imported. Checking the sealed-off behaviour in this interpreter
would therefore test whatever the rest of the suite happened to do first. Each case below runs in
a fresh interpreter with an explicit environment, which is the only honest way to assert what a
process that was never given the switch can see.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from phos.synth.families import SEALED_ENV_VAR, sealed_allowed

REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_ID = "gas_pressure"
SEALED_PROCESS = "gas-pressure-v1"


def _run(script: str, *, allow_sealed: bool) -> str:
    """Run a script in a fresh interpreter, with the sealed switch on or off.

    Returns:
        Everything the script printed.

    Raises:
        AssertionError: If the script failed, with its stderr, because a crash here is a finding
            about the seal rather than a flaky test.
    """
    environment = dict(os.environ)
    environment.pop(SEALED_ENV_VAR, None)
    if allow_sealed:
        environment[SEALED_ENV_VAR] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT / "src"), str(REPO_ROOT), environment.get("PYTHONPATH", "")]
    )
    finished = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=environment,
        cwd=REPO_ROOT,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr
    return finished.stdout


def test_the_switch_is_off_in_this_suite_by_default() -> None:
    """Guard on the guard.

    If a developer exported the variable in their shell, every assertion below would be testing
    the opposite of what it says, and all of them would still pass.
    """
    assert not sealed_allowed(), (
        f"{SEALED_ENV_VAR} is set in this environment; unset it before running the suite"
    )


def test_a_sealed_family_is_absent_from_both_listings_without_the_switch() -> None:
    output = _run(
        "from phos.synth.families import family_ids\n"
        "print(family_ids())\n"
        "print(family_ids(include_sealed=True))\n",
        allow_sealed=False,
    )

    assert SEALED_ID not in output


def test_asking_politely_is_not_the_switch() -> None:
    """``include_sealed=True`` on its own admits nothing. The environment is the only door."""
    output = _run(
        "from phos.synth.families import list_families\n"
        "print([f.family_id for f in list_families(include_sealed=True)])\n",
        allow_sealed=False,
    )

    assert SEALED_ID not in output


def test_a_sealed_family_is_refused_by_name_as_though_it_did_not_exist() -> None:
    output = _run(
        "from phos.synth.families import FamilyError, get_family\n"
        f"try:\n"
        f"    get_family({SEALED_ID!r})\n"
        f"    print('REACHABLE')\n"
        f"except FamilyError as error:\n"
        f"    print('REFUSED', error)\n",
        allow_sealed=False,
    )

    assert output.startswith("REFUSED")
    assert "no family" in output
    for leak in ("sealed", "PHOS_SYNTH_ALLOW_SEALED", "allow", "hidden", "private", "exam"):
        assert leak not in output, (
            f"the refusal mentions {leak!r}, which tells the reader a sealed family exists"
        )


def test_a_sealed_process_cannot_be_built_without_the_switch() -> None:
    """The guarantee that survives a sealed spec leaking on to a disk."""
    output = _run(
        "from phos.synth.templates import process_names\nprint(process_names())\n",
        allow_sealed=False,
    )

    assert SEALED_PROCESS not in output


def test_the_switch_admits_the_family_and_its_process() -> None:
    output = _run(
        "from phos.synth.families import family_ids, get_family\n"
        "from phos.synth.templates import process_names\n"
        "print('sealed_listed', family_ids(include_sealed=True))\n"
        "print('default_listing', family_ids())\n"
        f"print('process', {SEALED_PROCESS!r} in process_names())\n"
        f"print('label', get_family({SEALED_ID!r}).label)\n",
        allow_sealed=True,
    )

    lines = dict(line.split(" ", 1) for line in output.strip().splitlines())
    assert SEALED_ID in lines["sealed_listed"]
    assert SEALED_ID not in lines["default_listing"], (
        "even with the switch on, the default listing stays the open set"
    )
    assert lines["process"] == "True"
    assert lines["label"]


def test_a_value_other_than_one_does_not_open_the_seal() -> None:
    """``=1`` and nothing else, so a stray ``=0`` or ``=false`` does not read as consent."""
    for value in ("0", "false", "yes", "", "true"):
        environment = dict(os.environ)
        environment[SEALED_ENV_VAR] = value
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(REPO_ROOT / "src"), str(REPO_ROOT), environment.get("PYTHONPATH", "")]
        )
        finished = subprocess.run(
            [
                sys.executable,
                "-c",
                "from phos.synth.families import family_ids\nprint(family_ids())\n",
            ],
            capture_output=True,
            text=True,
            env=environment,
            cwd=REPO_ROOT,
            check=False,
        )
        assert finished.returncode == 0, finished.stderr
        assert SEALED_ID not in finished.stdout, f"{SEALED_ENV_VAR}={value!r} opened the seal"


def test_a_sealed_plant_draws_and_runs_like_any_other() -> None:
    """Behind the switch there is nothing special about it, which is the other half of the claim.

    A sealed family that could not actually produce a plant would be a worse problem than one
    that leaked: the private exam would be made of specs nobody had ever run.
    """
    output = _run(
        "from datetime import UTC, datetime, timedelta\n"
        "from phos.synth.families import get_family\n"
        "from phos.synth.plant import RunSpec\n"
        "from phos.synth.plant_spec import PlantSpec\n"
        "from phos.synth.templates import build_from_spec\n"
        "from phos.synth.topology import subsystems, subsystems_from_components\n"
        "run = RunSpec(seed=4, start=datetime(2026, 11, 12, tzinfo=UTC),\n"
        "              duration=timedelta(minutes=30), sample_interval=timedelta(seconds=30))\n"
        f"family = get_family({SEALED_ID!r})\n"
        "spec = family.draw(8801)\n"
        "again = family.draw(8801)\n"
        "rebuilt = PlantSpec.from_json(spec.to_json())\n"
        "def telemetry(s):\n"
        "    plant = build_from_spec(s, run)\n"
        "    keys = s.describe().signal_keys()\n"
        "    return [tuple(plant.step(None).report.values[k] for k in keys)\n"
        "            for _ in range(run.n_steps)]\n"
        "print('deterministic', spec == again)\n"
        "print('round_trips', telemetry(rebuilt) == telemetry(spec))\n"
        "print('differs', telemetry(family.draw(8802)) != telemetry(spec))\n"
        "print('grouped', subsystems_from_components(spec) == subsystems(spec.describe()))\n"
        "print('roles', set(spec.describe().signal_keys()) == set(spec.roles))\n"
        "print('signals', len(spec.signals))\n",
        allow_sealed=True,
    )

    lines = dict(line.split(" ", 1) for line in output.strip().splitlines())
    assert lines["deterministic"] == "True"
    assert lines["round_trips"] == "True"
    assert lines["differs"] == "True"
    assert lines["grouped"] == "True"
    assert lines["roles"] == "True"
    assert int(lines["signals"]) > 4


def test_the_sealed_package_holds_no_scoring() -> None:
    """The seal is a loading switch. If exam logic arrives here, the separation has gone.

    PART S6's referee is what decides to examine a detector on an unseen process. A generator
    that knew which of its plants were the exam could favour them — by widening a bound, by
    making one easier, or simply by a developer reading the code and remembering.

    The check is on what the code *does*, not on what its prose says: these modules explain why a
    held-back process is worth holding back, and that explanation mentions detectors. What they
    must not do is import anything that measures one, or define anything that scores.
    """
    package = REPO_ROOT / "src" / "phos" / "synth" / "families_sealed"
    forbidden_packages = ("phos.eval", "phos.atlas", "phos.referee", "phos.breaking", "sklearn")
    forbidden_names = ("score", "recall", "precision", "alert", "detect", "verdict", "metric")

    for module in sorted(package.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                reached = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                reached = [node.module] if node.module else []
            else:
                reached = []
            for name in reached:
                assert not any(name.startswith(bad) for bad in forbidden_packages), (
                    f"{module.name} imports {name!r}; measuring a detector belongs to the referee"
                )
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                lowered = node.name.lower()
                assert not any(bad in lowered for bad in forbidden_names), (
                    f"{module.name} defines {node.name!r}; scoring belongs to the referee"
                )


@pytest.mark.parametrize("path", ["families.py", "randomise.py", "plant_spec.py", "templates.py"])
def test_the_open_machinery_does_not_import_the_sealed_package(path: str) -> None:
    """Only `families.py` may name the sealed package, and only inside a function.

    It mentions it twice — once in its own docstring explaining the switch, once in the lazy
    import that acts on it. Nothing else may reach for it at all: an open module that imported
    the sealed package at the top would register its families on every run, and the switch would
    be decoration.
    """
    source = (REPO_ROOT / "src" / "phos" / "synth" / path).read_text(encoding="utf-8")
    mentions = source.count("families_sealed")

    assert mentions <= (2 if path == "families.py" else 0), (
        f"{path} reaches for the sealed package {mentions} time(s)"
    )
