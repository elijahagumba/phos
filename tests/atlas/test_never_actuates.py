"""Atlas observes plants. It does not write coils or registers to them.

Three pins live here, and they are different in kind.

**No live actuation.** Scanning `src/phos/atlas/**/*.py` must not find a Modbus client, a TCP
connect to port 502, or a function that would write a coil or register to a host. Naming FC 5, 6
and 16 while *dissecting a capture* is the opposite act: reading bytes that already happened.

**Issuer kind is a graph lookup.** `classify_command_issuer` lives in `phos.breaking.commands`. A
scada or hmi node that already issued on the learned baseline is a known station even when the
attack identifier contains ``rogue``. `ROGUE_COMMAND` is not an argument. The large fixtures that
already prove scada-on-graph vs silent engineering are in `tests/breaking/test_commands.py`; this
module calls the same classifier rather than rebuilding them.

**The two issuer kinds stay two numbers.** `CommandIssuerKind` holds both members, and the
breaking report test that refuses to render 0/16 and 1/4 as one pooled lead rate must still exist
as a file. That 1/4 is a D2 diagnostic, not ≥70%.
"""

import ast
import inspect
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.breaking.test_commands import _graph_with_scada_issuer

from phos.atlas.packet import DeviceCommandGraph, FunctionCode, device_entity_id, is_write
from phos.breaking.commands import CommandIssuerKind, classify_command_issuer
from phos.synth.attacks.battery import load_battery
from phos.synth.attacks.spec import AttackFlavour
from phos.synth.plants.water import WATER_DESCRIPTION

REPO = Path(__file__).resolve().parents[2]
ATLAS_ROOT = REPO / "src" / "phos" / "atlas"
HOSTILE_CONFIGS = REPO / "configs" / "attacks"
POOLED_LEAD_TEST = REPO / "tests" / "breaking" / "test_report.py"
POOLED_LEAD_TEST_NAME = (
    "test_frozen_zero_of_sixteen_and_one_of_four_are_not_rendered_as_one_pooled_lead_rate"
)

_CLIENT_MODULE_MARKERS: tuple[str, ...] = ("pymodbus", "modbus_tcp", "pymodbustcp")
_CLIENT_CALL_NAMES = frozenset(
    {
        "create_connection",
        "write_coil",
        "write_coils",
        "write_register",
        "write_registers",
    }
)
_CLIENT_FUNCDEF_NAMES = _CLIENT_CALL_NAMES | {
    "write_single_coil",
    "write_single_register",
    "write_multiple_coils",
    "write_multiple_registers",
}
_CONNECT_NAMES = frozenset({"connect", "create_connection", "open_connection"})

_HOSTILE_FILES: tuple[str, ...] = (
    "04-hostile-poisoned-baseline.toml",
    "05-hostile-malformed-records.toml",
    "06-hostile-out-of-range.toml",
    "07-hostile-truncated.toml",
)


def _atlas_python_files() -> tuple[Path, ...]:
    """Every Atlas module the actuation scan must read."""
    files = tuple(sorted(path for path in ATLAS_ROOT.rglob("*.py") if path.is_file()))
    assert files, f"no Python files under {ATLAS_ROOT}"
    return files


def _call_name(node: ast.Call) -> str:
    """The attribute or bare name being called, or empty when the form is not a name."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _mentions_port_502(node: ast.AST) -> bool:
    """Whether a call argument names TCP port 502 or a ``:502`` endpoint."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant):
            if child.value == 502:
                return True
            if isinstance(child.value, str) and ":502" in child.value:
                return True
    return False


def _imported_modules(tree: ast.AST) -> Iterator[str]:
    """Yield every module path an import statement names."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module
            for alias in node.names:
                yield f"{node.module}.{alias.name}"


def _actuation_offences(path: Path, tree: ast.AST) -> list[str]:
    """Return human-readable reasons ``path`` would speak to a PLC rather than a pcap."""
    offences: list[str] = []
    relative = path.relative_to(REPO)
    for module in _imported_modules(tree):
        lowered = module.lower()
        if any(marker in lowered for marker in _CLIENT_MODULE_MARKERS):
            offences.append(f"{relative}: client import {module!r}")
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in _CLIENT_FUNCDEF_NAMES:
                offences.append(
                    f"{relative}:{node.lineno}: function {node.name} would actuate a live host"
                )
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _CLIENT_CALL_NAMES:
                offences.append(f"{relative}:{node.lineno}: call {name}()")
            elif name in _CONNECT_NAMES and _mentions_port_502(node):
                offences.append(f"{relative}:{node.lineno}: {name}() to port 502")
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _CLIENT_CALL_NAMES | _CLIENT_FUNCDEF_NAMES:
                    offences.append(
                        f"{relative}:{node.lineno}: imported actuation name {alias.name!r}"
                    )
    return offences


def _classifier_body() -> str:
    """The body of `classify_command_issuer` with the docstring stripped."""
    source = textwrap.dedent(inspect.getsource(classify_command_issuer))
    tree = ast.parse(source)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    statements = func.body
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    return ast.unparse(ast.Module(body=statements, type_ignores=[]))


def _graph_with_issuer(node_id: str) -> DeviceCommandGraph:
    """The water baseline graph with ``node_id`` as the learned issuer.

    Reuses `_graph_with_scada_issuer` for scada. HMI is the same edge rewritten onto the operator
    station, so this file does not duplicate the CommandEdge fixture.
    """
    graph = _graph_with_scada_issuer()
    if node_id == "scada":
        return graph
    network = WATER_DESCRIPTION.control_network
    assert network is not None
    ip = network.node(node_id).ip
    edge = graph.edges[0]
    rewritten = edge.model_copy(
        update={
            "issuer": device_entity_id(ip),
            "issuer_ip": ip,
        }
    )
    return graph.model_copy(update={"edges": (rewritten,)})


def test_atlas_never_actuates_a_live_modbus_device() -> None:
    """Fail on client libraries and live connects; allow FC 5/6/16 dissection of pcaps."""
    offences: list[str] = []
    for path in _atlas_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offences.extend(_actuation_offences(path, tree))
    assert offences == []


def test_dissecting_write_function_codes_in_a_capture_is_not_actuation() -> None:
    """FC 5, 6 and 16 are facts about frames already captured, not coils Atlas writes."""
    assert FunctionCode.WRITE_SINGLE_COIL == 5
    assert FunctionCode.WRITE_SINGLE_REGISTER == 6
    assert FunctionCode.WRITE_MULTIPLE_REGISTERS == 16
    assert is_write(FunctionCode.WRITE_SINGLE_COIL)
    assert is_write(FunctionCode.WRITE_SINGLE_REGISTER)
    assert is_write(FunctionCode.WRITE_MULTIPLE_REGISTERS)


def test_classify_command_issuer_does_not_take_rogue_command_or_an_attack_id() -> None:
    """Classification cannot see AttackType.ROGUE_COMMAND: it is not a parameter."""
    assert set(inspect.signature(classify_command_issuer).parameters) == {
        "issuer",
        "description",
        "graph",
    }
    body = _classifier_body()
    assert "ROGUE_COMMAND" not in body
    assert "AttackType" not in body
    assert "attack_id" not in body


@pytest.mark.parametrize("station", ["scada", "hmi"])
def test_a_learned_scada_or_hmi_edge_is_known_station_even_if_the_attack_id_says_rogue(
    station: str,
) -> None:
    """A write from a station already on the graph is known-station, whatever the attack is named.

    The same classifier, with the scada fixture, is already asserted in
    `tests/breaking/test_commands.py::test_a_polling_scada_write_is_a_known_station`. This pin
    adds the HMI operator and the claim that a ``rogue`` attack id cannot change the answer.
    """
    rogue_attack_id = f"wt-rogue-command-from-{station}"
    graph = _graph_with_issuer(station)
    kind = classify_command_issuer(station, WATER_DESCRIPTION, graph)
    assert kind is CommandIssuerKind.KNOWN_STATION
    assert "rogue" in rogue_attack_id
    assert "attack_id" not in inspect.signature(classify_command_issuer).parameters


def test_a_silent_engineering_write_on_the_same_graph_is_still_an_unknown_master() -> None:
    """Known-station and unknown-master stay a graph lookup, not a shared ROGUE_COMMAND bucket."""
    kind = classify_command_issuer("engineering", WATER_DESCRIPTION, _graph_with_scada_issuer())
    assert kind is CommandIssuerKind.UNKNOWN_MASTER


def test_command_issuer_kind_holds_known_station_and_unknown_master_apart() -> None:
    assert {member.name for member in CommandIssuerKind} == {"KNOWN_STATION", "UNKNOWN_MASTER"}
    assert CommandIssuerKind.KNOWN_STATION.value == "known_station"
    assert CommandIssuerKind.UNKNOWN_MASTER.value == "unknown_master"


def test_frozen_zero_of_sixteen_and_one_of_four_are_not_one_pooled_lead_rate_file() -> None:
    """Path check: the report test that refuses a pooled 0/16+1/4 must still be on disk."""
    assert POOLED_LEAD_TEST.is_file()
    source = POOLED_LEAD_TEST.read_text(encoding="utf-8")
    assert f"def {POOLED_LEAD_TEST_NAME}" in source


def test_configs_04_to_07_are_input_hostile_with_one_case_each() -> None:
    """The four named hostile files: INPUT_HOSTILE flavour, exactly one case, no detection attacks.

    The broader 'every INPUT_HOSTILE corpus' pin is
    `tests/synth/attacks/test_generate.py::TestTheCommittedBattery.test_every_input_hostile_kind_gets_a_corpus_of_its_own`.
    This names 04-07 specifically. Surviving them is software robustness, not a security claim.
    """
    for name in _HOSTILE_FILES:
        config = load_battery(HOSTILE_CONFIGS / name)
        assert config.flavour is AttackFlavour.INPUT_HOSTILE, name
        assert len(config.hostile) == 1, name
        assert config.attacks == (), name
