"""Generate one PHOS-owned ICSSim run: process values, true state, Modbus traffic and labels.

Run with ICSSim's own interpreter, not the lab's (ICSSim needs ``pyModbusTCP``; the lab does not).
`scripts/icssim/generate_corpus.py` does that for every declared run; by hand, pass ``--icssim``
(ICSSim's ``src``), ``--out``, ``--scenario``, ``--seed`` and optionally ``--time-scale``.

**What this is.** ICSSim (MIT, Dehlaghi-Ghadim et al.) emulates a bottle-filling plant: a tank,
two valves, a conveyor and a bottle, controlled by two PLCs that serve Modbus TCP. This harness
runs ICSSim's own physics and PLC logic unchanged, at a pinned commit, and adds what PHOS needs
around it, by patching at run time rather than editing ICSSim's files (ADR 0122):

- **Identities.** Every Modbus client binds its own loopback address, so the traffic says who
  spoke: PLC-1 ``127.0.0.11``, PLC-2 ``127.0.0.12``, the operator console ``127.0.0.21`` and the
  attacker ``127.0.0.66``. The PLCs serve on ``127.0.0.11:5502`` and ``127.0.0.12:5503``.
- **Traffic.** Every read and write a PLC serves over the network is logged with its client
  address, function, tag and decoded value (``modbus.csv``). This is the parsed form of a capture.
- **Two views of the plant.** ``process.csv`` is what the control system reports, read from the
  PLCs' registers once per simulated second. ``truth.csv`` is the plant's real state from the
  physics, for judging only (ADR 0017's rule). They differ only when a reading is falsified.
- **Declared events.** Attacks and benign operator actions on a seeded schedule (``SCENARIOS``),
  written to ``events.json``; maintenance writes a work order to ``work_orders.csv``.
- **Time scale.** The plant runs on a scaled clock so an hour of plant time takes minutes. Every
  component reads the same scaled clock, so the physics integrates the same simulated
  milliseconds; only wall time shrinks. Thread scheduling still varies, so a run is reproducible
  in its schedule and its plant, not bit for bit.

Nothing here scores anything. Generated data is never committed (ADR 0006).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import socket
import sys
import threading
import time as real_time_module
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

PLC1_IP, PLC2_IP = "127.0.0.11", "127.0.0.12"
OPERATOR_IP, ATTACKER_IP = "127.0.0.21", "127.0.0.66"
ROLES = {PLC1_IP: "plc1", PLC2_IP: "plc2", OPERATOR_IP: "operator", ATTACKER_IP: "attacker"}

# ----------------------------------------------------------------------------- the scaled clock


class SimClock:
    """Simulated time: starts at a fixed epoch and runs ``scale`` times faster than wall time."""

    EPOCH = 1_767_225_600.0  # 2026-01-01T00:00:00Z, so every run's timestamps start the same

    def __init__(self, scale: float) -> None:
        """Start the clock now, running ``scale`` simulated seconds per wall second."""
        self.scale = scale
        self._real_start = real_time_module.monotonic()

    def time(self) -> float:
        """Return simulated unix seconds."""
        return self.EPOCH + (real_time_module.monotonic() - self._real_start) * self.scale

    def elapsed(self) -> float:
        """Return simulated seconds since the run started."""
        return self.time() - self.EPOCH

    def sleep(self, seconds: float) -> None:
        """Sleep for ``seconds`` of simulated time."""
        if seconds > 0:
            real_time_module.sleep(seconds / self.scale)

    def sleep_until(self, sim_seconds: float) -> None:
        """Sleep until ``sim_seconds`` after the run's start."""
        self.sleep(sim_seconds - self.elapsed())


# ----------------------------------------------------------------------------- the shared store


class MemoryConnector:
    """ICSSim's physics store, in process and locked, replacing its sqlite file."""

    def __init__(self) -> None:
        """Start empty; ICSSim's factory initialises every tag."""
        self._values: dict[str, float] = {}
        self._lock = threading.Lock()

    def initialize(self, values, clear_old=False) -> None:  # noqa: ANN001
        """Set every ``(tag, value)`` pair. ICSSim's signature."""
        with self._lock:
            for key, value in values:
                self._values[key] = float(value)

    def set(self, key, value) -> None:  # noqa: ANN001
        """Set one tag."""
        with self._lock:
            self._values[key] = float(value)

    def get(self, key) -> float:  # noqa: ANN001
        """Return one tag."""
        with self._lock:
            return self._values[key]

    def snapshot(self) -> dict[str, float]:
        """Return every tag at one instant."""
        with self._lock:
            return dict(self._values)


# ----------------------------------------------------------------------------- scenarios


@dataclass(frozen=True)
class Event:
    """One declared event, in simulated seconds from the run's start."""

    kind: str
    start: float
    end: float
    label: str  # "attack" or "benign"
    params: dict[str, float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    """A run's length and the event kinds its seeded schedule may draw."""

    duration_s: int
    kinds: tuple[str, ...]
    events: int


#: ``normal`` has operator activity and maintenance only; the attack scenarios add attacks.
SCENARIOS: dict[str, Scenario] = {
    "normal": Scenario(duration_s=4 * 3600, kinds=("setpoint", "maintenance"), events=6),
    "mixed": Scenario(
        duration_s=2 * 3600,
        kinds=(
            "setpoint",
            "maintenance",
            "liar_freeze",
            "liar_offset",
            "rogue_command",
            "recon",
            "replay",
            "mimic_maintenance",
        ),
        events=8,
    ),
    # ADR 0285. A separate scenario, because a ninth event does not fit the frozen two-hour
    # `mixed` run and that one must stay reproducible: lane 1's held-out score rests on it.
    "mixed2": Scenario(
        duration_s=9000,
        kinds=(
            "setpoint",
            "maintenance",
            "liar_freeze",
            "liar_offset",
            "rogue_command",
            "recon",
            "replay",
            "mimic_maintenance",
            "creep_many",
        ),
        events=9,
    ),
}

ATTACK_KINDS = {
    "liar_freeze",
    "liar_offset",
    "rogue_command",
    "recon",
    "replay",
    "mimic_maintenance",
    "creep_many",
}
DURATIONS = {  # simulated seconds, (low, high)
    "setpoint": (1, 1),
    "maintenance": (300, 900),
    "liar_freeze": (180, 600),
    "liar_offset": (180, 600),
    "rogue_command": (60, 240),
    "recon": (30, 120),
    "replay": (60, 180),
    "mimic_maintenance": (300, 900),
    "creep_many": (300, 900),
}

#: `creep_many` biases these continuous readings. ADR 0285.
CREEP_SIGNALS = (
    "tank_level_value",
    "tank_output_flow_value",
    "bottle_level_value",
    "bottle_distance_to_filler_value",
)
#: Multiplicative bias per affected instrument, drawn in this band: it reports value x (1 + f),
#: which is what a miscalibrated or tampered transmitter does. A statement about instruments, not
#: about any detector's threshold, and never adjusted after one has been run. ADR 0285.
CREEP_FRACTION = (0.03, 0.08)
WARMUP_S = 600  # no event in the first ten simulated minutes
GAP_S = 300  # at least five minutes between events


def schedule(name: str, seed: int) -> list[Event]:
    """Draw a run's events from its seed.

    Every declared kind appears at least once, in a seeded order; remaining slots draw kinds at
    random. Events are laid out in time order, never overlap, never start in the warm-up, and are
    at least `GAP_S` apart.
    """
    scenario = SCENARIOS[name]
    rng = random.Random(seed)
    kinds = list(scenario.kinds)
    rng.shuffle(kinds)
    while len(kinds) < scenario.events:
        kinds.append(rng.choice(scenario.kinds))
    kinds = kinds[: scenario.events]
    lengths = [float(rng.randint(*DURATIONS[kind])) for kind in kinds]
    budget = scenario.duration_s - 120 - WARMUP_S - GAP_S * len(kinds) - sum(lengths)
    if budget < 0:
        raise ValueError(f"scenario {name!r} cannot fit its events in {scenario.duration_s} s")
    cuts = sorted(rng.uniform(0.0, budget) for _ in kinds)
    events: list[Event] = []
    cursor = float(WARMUP_S)
    previous_cut = 0.0
    for kind, length, cut in zip(kinds, lengths, cuts, strict=True):
        start = cursor + GAP_S + (cut - previous_cut)
        previous_cut = cut
        params: dict[str, float | str] = {}
        if kind == "setpoint":
            params = {"tag": "tank_level_max", "value": round(rng.uniform(6.5, 7.5), 2)}
        elif kind == "liar_offset":
            params = {"offset": round(rng.uniform(1.0, 3.0), 2)}
        elif kind == "rogue_command":
            params = {"tag": rng.choice(["tank_input_valve_mode", "tank_output_valve_mode"])}
        elif kind == "creep_many":
            chosen = rng.sample(CREEP_SIGNALS, rng.randint(3, len(CREEP_SIGNALS)))
            params = {tag: round(rng.uniform(*CREEP_FRACTION), 4) for tag in sorted(chosen)}
        events.append(
            Event(
                kind=kind,
                start=round(start, 1),
                end=round(start + length, 1),
                label="attack" if kind in ATTACK_KINDS else "benign",
                params=params,
            )
        )
        cursor = start + length
    return events


# ----------------------------------------------------------------------------- the harness


class Harness:
    """Patches ICSSim at run time, runs it, injects events and records everything."""

    def __init__(self, icssim_src: Path, out: Path, scale: float) -> None:
        """Patch ICSSim for this run; nothing starts until `run`."""
        self.out = out
        self.clock = SimClock(scale)
        self.store = MemoryConnector()
        self.modbus_rows: list[list[object]] = []
        self.modbus_lock = threading.Lock()
        self.tampered: dict[str, object] = {}  # tag -> callable(true_value) -> reported value
        self._patch(icssim_src)

    # -- patching ---------------------------------------------------------------------------

    def _patch(self, icssim_src: Path) -> None:
        sys.path.insert(0, str(icssim_src))
        os.chdir(self.out)
        (self.out / "logs").mkdir(exist_ok=True)
        (self.out / "storage").mkdir(exist_ok=True)

        import Configs
        import ics_sim.connectors as connectors
        import ics_sim.Device as device  # noqa: N813 - ICSSim's module name
        import ics_sim.helper as helper
        from pyModbusTCP.client import ModbusClient

        clock = self.clock
        store = self.store

        def milli() -> int:
            return round(clock.time() * 1000)

        def milli_cycle(cycle: int) -> int:
            return round(clock.time() * 1000 / cycle) * cycle

        helper.current_milli_time = milli
        helper.current_milli_cycle_time = milli_cycle
        device.current_milli_time = milli
        device.current_milli_cycle_time = milli_cycle
        device.time = SimpleNamespace(sleep=clock.sleep, time=clock.time)
        connectors.ConnectorFactory.build = staticmethod(lambda connection: store)
        device.ConnectorFactory = connectors.ConnectorFactory

        Configs.Controllers.PLCs = {
            1: {"name": "PLC1", "ip": PLC1_IP, "port": 5502, "protocol": "ModbusWriteRequest-TCP"},
            2: {"name": "PLC2", "ip": PLC2_IP, "port": 5503, "protocol": "ModbusWriteRequest-TCP"},
        }
        Configs.Connection.CONNECTION = {"type": "sqlite", "path": "unused.sqlite", "name": "t"}

        # Every client binds its owner's address, so the server sees who spoke.
        original_open = ModbusClient._open

        def bound_open(client: ModbusClient) -> None:
            source = getattr(client, "phos_source_ip", None)
            if source is None:
                return original_open(client)
            if client.is_open:
                client.close()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(client.timeout)
            sock.bind((source, 0))
            sock.connect((client.host, client.port))
            client._sock = sock
            return None

        ModbusClient._open = bound_open

        # Sensor tampering: a compromised field device reports what the attack says.
        harness = self
        original_read = device.SensorConnector.read

        def tampered_read(connector, tag) -> float:  # noqa: ANN001
            value = original_read(connector, tag)
            rule = harness.tampered.get(tag)
            return value if rule is None else rule(value)

        device.SensorConnector.read = tampered_read

        self.configs = Configs
        self.device = device

    # -- components ---------------------------------------------------------------------------

    def _bind_clients(self, component, ip: str) -> None:  # noqa: ANN001
        for client in getattr(component, "clients", {}).values():
            client.client.phos_source_ip = ip

    def _log_server(self, plc, plc_name: str) -> None:  # noqa: ANN001
        """Wrap a PLC's register bank so every networked read or write is logged."""
        bank = plc.server.server.data_bank
        codec = plc.server
        tags_by_register = {
            codec.get_registers(data["id"]): name
            for name, data in self.configs.TAG.TAG_LIST.items()
        }
        harness = self

        def logged(method, function):  # noqa: ANN001, ANN202
            # pyModbusTCP calls the bank as (address, count_or_words, srv_info), positionally.
            def wrapper(address, payload=1, srv_info=None):  # noqa: ANN001, ANN202
                result = method(address, payload, srv_info)
                if srv_info is not None:
                    tag = tags_by_register.get(address, f"register_{address}")
                    words = payload if function == "write" else result
                    try:
                        value = codec.decode(list(words)[:2]) if words else ""
                    except (ValueError, TypeError):
                        value = ""
                    client = srv_info.client.address
                    with harness.modbus_lock:
                        harness.modbus_rows.append(
                            [
                                round(harness.clock.time(), 3),
                                client,
                                ROLES.get(client, "unknown"),
                                plc_name,
                                function,
                                tag,
                                value,
                            ]
                        )
                return result

            return wrapper

        bank.get_holding_registers = logged(bank.get_holding_registers, "read")
        bank.set_holding_registers = logged(bank.set_holding_registers, "write")

    def run(self, events: list[Event], duration_s: int) -> None:
        """Start the plant, the operator, the events and the recorder; stop at the end."""
        from FactorySimulation import FactorySimulation
        from ics_sim.protocol import ClientModbus
        from PLC1 import PLC1
        from PLC2 import PLC2

        factory = FactorySimulation()
        plc1, plc2 = PLC1(), PLC2()
        self._bind_clients(plc1, PLC1_IP)
        self._bind_clients(plc2, PLC2_IP)
        self._log_server(plc1, "plc1")
        self._log_server(plc2, "plc2")
        tags = self.configs.TAG.TAG_LIST

        def client(ip: str, plc: int):  # noqa: ANN202
            config = self.configs.Controllers.PLCs[plc]
            made = ClientModbus(config["ip"], config["port"])
            made.client.phos_source_ip = ip
            return made

        # Separate connections for polling and for commands: a client is not thread-safe.
        operator_poller = {1: client(OPERATOR_IP, 1), 2: client(OPERATOR_IP, 2)}
        operator = {1: client(OPERATOR_IP, 1), 2: client(OPERATOR_IP, 2)}
        attacker = {1: client(ATTACKER_IP, 1), 2: client(ATTACKER_IP, 2)}
        stop = threading.Event()

        factory.start()
        plc1.start()
        plc2.start()

        def operator_poll() -> None:
            """The operator console reads every tag from its PLC once per simulated second."""
            while not stop.is_set():
                for data in tags.values():
                    try:
                        operator_poller[data["plc"]].receive(data["id"])
                    except Exception:
                        pass
                self.clock.sleep(1.0)

        def send(side: dict, tag: str, value: float) -> None:
            data = tags[tag]
            side[data["plc"]].send(data["id"], value)

        def run_event(event: Event) -> None:
            self.clock.sleep_until(event.start)
            if stop.is_set():
                return
            k = event.kind
            if k == "setpoint":
                send(operator, str(event.params["tag"]), float(event.params["value"]))
            elif k in ("maintenance", "mimic_maintenance"):
                side = operator  # mimic: the attacker uses the compromised console itself
                send(side, "tank_output_valve_mode", 1)
                if k == "maintenance":
                    self._work_order(event)
                self.clock.sleep_until(event.end)
                send(side, "tank_output_valve_mode", 3)
            elif k == "liar_freeze":
                frozen = self.store.get("tank_level_value")
                self.tampered["tank_level_value"] = lambda _v, f=frozen: f
                self.clock.sleep_until(event.end)
                self.tampered.pop("tank_level_value", None)
            elif k == "creep_many":
                for tag, fraction in event.params.items():
                    self.tampered[str(tag)] = (
                        lambda v, f=float(fraction): v * (1.0 + f)  # type: ignore[misc]
                    )
                self.clock.sleep_until(event.end)
                for tag in event.params:
                    self.tampered.pop(str(tag), None)
            elif k == "liar_offset":
                offset = float(event.params["offset"])
                self.tampered["tank_level_value"] = lambda v, o=offset: max(0.0, v - o)
                self.clock.sleep_until(event.end)
                self.tampered.pop("tank_level_value", None)
            elif k == "rogue_command":
                tag = str(event.params["tag"])
                send(attacker, tag, 2)  # force the valve open
                self.clock.sleep_until(event.end)
                send(attacker, tag, 3)
            elif k == "recon":
                while self.clock.elapsed() < event.end and not stop.is_set():
                    for data in tags.values():
                        try:
                            attacker[data["plc"]].receive(data["id"])
                        except Exception:
                            pass
                    self.clock.sleep(0.2)
            elif k == "replay":
                # Replays the operator's own maintenance command sequence, at the wrong time.
                send(attacker, "tank_output_valve_mode", 1)
                self.clock.sleep_until(event.end)
                send(attacker, "tank_output_valve_mode", 3)

        threads = [threading.Thread(target=operator_poll, daemon=True)]
        threads += [threading.Thread(target=run_event, args=(e,), daemon=True) for e in events]
        recorder = threading.Thread(target=self._record, args=(plc1, plc2, duration_s, stop))
        for thread in [*threads, recorder]:
            thread.start()
        recorder.join()
        stop.set()
        for component in (factory, plc1, plc2):
            component.stop()

    # -- recording ---------------------------------------------------------------------------

    def _work_order(self, event: Event) -> None:
        path = self.out / "work_orders.csv"
        new = not path.exists()
        with path.open("a", newline="") as handle:
            writer = csv.writer(handle)
            if new:
                writer.writerow(["work_order", "start", "end", "asset", "action"])
            writer.writerow(
                [
                    f"WO-{int(event.start)}",
                    round(SimClock.EPOCH + event.start, 1),
                    round(SimClock.EPOCH + event.end, 1),
                    "tank_output_valve",
                    "planned valve service: output valve held closed",
                ]
            )

    def _record(self, plc1, plc2, duration_s: int, stop: threading.Event) -> None:  # noqa: ANN001
        tags = list(self.configs.TAG.TAG_LIST)
        process = (self.out / "process.csv").open("w", newline="")
        truth = (self.out / "truth.csv").open("w", newline="")
        p_writer, t_writer = csv.writer(process), csv.writer(truth)
        p_writer.writerow(["timestamp", *tags])
        t_writer.writerow(["timestamp", *tags])
        plcs = {1: plc1, 2: plc2}
        second = 0
        while second <= duration_s and not stop.is_set():
            self.clock.sleep_until(float(second))
            stamp = round(SimClock.EPOCH + second, 1)
            reported = []
            for tag in tags:
                data = self.configs.TAG.TAG_LIST[tag]
                reported.append(round(plcs[data["plc"]].server.get(data["id"]), 4))
            true_state = self.store.snapshot()
            p_writer.writerow([stamp, *reported])
            t_writer.writerow([stamp, *[round(true_state[tag], 4) for tag in tags]])
            second += 1
        process.close()
        truth.close()
        with (self.out / "modbus.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "client", "role", "plc", "function", "tag", "value"])
            with self.modbus_lock:
                writer.writerows(self.modbus_rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Generate one run directory from the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--icssim", type=Path, required=True, help="ICSSim's src directory")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--time-scale", type=float, default=20.0)
    parser.add_argument("--duration-s", type=int, default=None, help="override, for smoke tests")
    args = parser.parse_args()

    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; a run directory is written once")
    out.mkdir(parents=True, exist_ok=True)
    scenario = SCENARIOS[args.scenario]
    duration = args.duration_s or scenario.duration_s
    events = [e for e in schedule(args.scenario, args.seed) if e.end <= duration - 60]
    (out / "events.json").write_text(json.dumps([asdict(e) for e in events], indent=2) + "\n")

    harness = Harness(args.icssim.resolve(), out, args.time_scale)
    started = real_time_module.time()
    harness.run(events, duration)
    manifest = {
        "generator": "scripts/icssim/phos_icssim.py",
        "generator_sha256": _sha256(Path(__file__).resolve()),
        "scenario": args.scenario,
        "seed": args.seed,
        "duration_s": duration,
        "time_scale": args.time_scale,
        "epoch": SimClock.EPOCH,
        "wall_seconds": round(real_time_module.time() - started, 1),
        "files": {
            name: _sha256(out / name)
            for name in ("process.csv", "truth.csv", "modbus.csv", "events.json")
            if (out / name).exists()
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    os._exit(0)  # ICSSim's Modbus servers run non-daemon threads; the run is complete


if __name__ == "__main__":
    main()
