"""The simulator cannot reach a real device, a real network, or another program.

PART S0's fifth hard rule and PART R4's own test requirement: all attack code acts only on
simulated in-memory signals and on files this package writes. No sockets, no scanning, no real
devices.

That rule is worth a test rather than a promise because the code it governs is attack code, and
because the failure is silent: a module that imported `socket` would still pass every other test
in the suite. It is enforced by reading the source with `ast` rather than by watching what runs, so
a path nothing happens to exercise is covered too.

**It already caught something.** PART R3 added ``import subprocess`` to `phos.synth.outputs` to ask
``git rev-parse`` for the commit hash. Shelling out is not reaching a device, and the intent behind
the rule was not aimed at it — but the rule is drawn around exactly that shape, and a generator
that spawns processes is the thing it exists to prevent. The commit is now read out of ``.git`` as
two small text files, which is also faster and cannot hang.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import phos.synth

FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "socket",
        "socketserver",
        "ssl",
        "asyncio",
        "selectors",
        "subprocess",
        "multiprocessing",
        "requests",
        "httpx",
        "urllib",
        "urllib3",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
        "paramiko",
        "scapy",
        "pymodbus",
        "snap7",
    }
)
"""What the simulator may not import, and why each group is here.

The network clients are obvious. `subprocess` and `multiprocessing` are here because spawning a
program is the other way code reaches outside this process, and a rule about reaching real devices
that permitted it would have a hole in the shape of ``os.system``. `scapy`, `pymodbus` and `snap7`
are packet and protocol *libraries*: `phos.synth.traffic` writes Modbus frames with `struct` on
purpose, and importing a library that can also put them on a wire would mean the only thing
stopping it was that nobody called that function."""

ALSO_FORBIDDEN: frozenset[str] = frozenset({"os.system", "os.popen", "os.spawnl", "os.execv"})
"""Attribute calls that reach outside the process without importing anything suspicious."""


def _modules() -> tuple[Path, ...]:
    """Return every module in the simulator package."""
    return tuple(sorted(Path(str(phos.synth.__file__)).parent.rglob("*.py")))


def _top_level(name: str) -> str:
    """Return the top-level package of a dotted import name."""
    return name.split(".")[0]


def _imported(path: Path) -> set[str]:
    """Return the top-level packages a module imports, read from its source."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    reached: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            reached.update(_top_level(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            reached.add(_top_level(node.module))
    return reached


def test_the_package_has_modules_to_check() -> None:
    """Guard on the guard: a glob that matched nothing would pass every test below."""
    assert len(_modules()) > 20


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_no_module_imports_a_way_out_of_this_process(path: Path) -> None:
    offending = sorted(_imported(path) & FORBIDDEN_MODULES)

    assert not offending, (
        f"{path.name} imports {offending}. The simulator acts only on in-memory signals and on "
        "files it writes itself; nothing in it may reach a device, a network or another program."
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_no_module_shells_out_through_an_attribute_call(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    offending = sorted(name for name in ALSO_FORBIDDEN if name in source)

    assert not offending, f"{path.name} calls {offending}"


def test_the_traffic_writer_builds_its_own_bytes() -> None:
    """The positive half of the claim: frames are assembled, not borrowed from a packet library.

    Without this, the import ban above would be satisfied by a package that had simply not got
    round to using scapy yet. `phos.synth.traffic` encodes with `struct` and writes a file, and
    `tests/synth/test_traffic.py` reads the result back through Atlas's real dissector — so the
    frames are known to be correct without any library that could also transmit them.
    """
    source = (Path(str(phos.synth.__file__)).parent / "traffic.py").read_text(encoding="utf-8")

    assert "import struct" in source
    assert "def write_pcap" in source


def test_the_commit_hash_is_read_rather_than_asked_for() -> None:
    """The specific regression this file caught, pinned so it cannot come back.

    Checked as an import and as a mechanism, not as a word: `outputs.py` *mentions* subprocess, in
    the docstring that explains why it does not use one. A text search would have failed on the
    explanation of its own fix — and so does the phrase "rev-parse". A text search failed on both,
    twice, which is a trap this suite has now walked into three times. Only the AST and the
    behaviour are checked here.
    """
    from phos.synth.outputs import git_commit

    outputs = Path(str(phos.synth.__file__)).parent / "outputs.py"

    assert "subprocess" not in _imported(outputs)
    commit = git_commit()
    assert commit is None or (len(commit) == 40 and all(c in "0123456789abcdef" for c in commit))
    assert git_commit(Path("/")) is None, "nowhere to look should mean None, not a guess"
