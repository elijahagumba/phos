# ADR 0380 — The valve mode tags can hold a value outside 1, 2 and 3, and the simulator ships an attacker that puts one there

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Atlas, build brief H, rung H1. A source finding. No measurement, no corpus
- **Supersedes:** nothing
- **Depends on:** [ADR 0371](0371-code-laws-derived-from-the-controller-program-are-judged.md),
  [ADR 0370](0370-code-laws-are-derived-from-the-controller-program.md),
  [ADR 0369](0369-h1-runs-now-and-the-later-rungs-wait-for-the-bid.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0371 refused H1 on bar 4. The derived law and the hand-copied `controller_valve` part on the
guard: `_check_manual_input` calls a valve manual at mode `1` and at mode `2` and automatic
everywhere else, while `controller_valve` calls it released at exactly `3.0` and unstated
everywhere else. They agree at modes 1, 2 and 3 and part at 4 and above.

That refusal leaves one factual question unanswered, and the answer decides whether the gap is
an abstract difference between two sentences or a difference that a real reading could land on:
**in the pinned ICSSim checkout, can `tank_input_valve_mode` or `tank_output_valve_mode` ever
hold a value other than 1, 2 or 3?** ADR 0371 did not ask it, and ADR 0370's enumeration could
not answer it, because that record declared the mode set `{1.0, 2.0, 3.0}` by construction.

This record answers it from source text and nothing else. The pinned checkout
`bcfd1844d3f063850c69f2643f6a052bac03d8ec` under `data/` was read as text. Nothing was imported,
executed or simulated. No corpus, capture or historian file was opened. No score was run, no
report written to `eval_runs/`, nothing appended to `eval_runs/log.jsonl`. `controller_valve`,
`src/phos/atlas/code_law/`, ADR 0370 and ADR 0371 were not edited. This record does not choose
between the hand rule and the derived rule; that is a human decision and it is not taken here.

The three files ADR 0370 declares were digested before reading and each matched:

| File | sha256 | Matches ADR 0370 |
|---|---|---|
| `src/PLC1.py` | `4651130bba9f137108c0426a6fdeb829db8705ea7eeedd40dfab378c9cf51316` | yes |
| `src/Configs.py` | `242e19fe346550fc4614f3511d6eacd91c0dfadb3e9591fd616570352ad23bd3` | yes |
| `src/ics_sim/Device.py` | `574660255d62e29e27015baaa797005071a11f14317af9525b6525258464ae92` | yes |
<!-- evidence-ack: src/Configs.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

The question reaches past those three, so six more files of the same checkout were read. They
are not in ADR 0370's table, were not read by the derivation, and are digested here so a later
session can confirm it read the same bytes:

| File | sha256 |
|---|---|
| `src/HMI2.py` | `05c57a525ec55bb1de1551572eecbf0075de6e94ee038b41c60965c8d1c48803` |
| `src/ics_sim/protocol.py` | `c2f3eb608676d634681b5ef8828a7e3fed929a3605f3c327aaef56ee46ec9467` |
| `src/ics_sim/connectors.py` | `fb480f0d276e38e3be3aca5f56426550e379c7a396f14838bd889bd57e8f1993` |
| `src/ics_sim/ScapyAttacker.py` | `92372dd53f79a1a2c5cc6673fee3d62b15c2c2a5098ca0a9e2aeee5da8a99bba` |
| `src/ics_sim/Attacks.py` | `8b0ca360bb87d6546bb72c930a07a8845df0fc3447685d2a7baceb1d09e02f37` |
| `src/AttackerMachine.py` | `4a1b665816297fd9bbf4676dc5fadd28b6f18f6ccef7afc92c2c3b95b5a6aa3a` |
<!-- evidence-ack: src/AttackerMachine.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/HMI2.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Attacks.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/ScapyAttacker.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/connectors.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/protocol.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

`src/AttackerBase.py` `ae973a31…badf418`, `src/CommandInjectionAgent.py` `f8944124…49cf7d` and
`src/DDosAgent.py` `adccb3e6…c755a1` were read to rule them out and are digested for the same
reason. `data/phos-icssim-dev/roles.toml` was not read: it is the hand-written quotation ADR 0370
forbids as a source.
<!-- evidence-ack: src/AttackerBase.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/CommandInjectionAgent.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/DDosAgent.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

## Decision

**Reachable. Under the simulator's intended operation the two tags only ever hold 1, 2 or 3, but
nothing in the checkout enforces that, and the repository's own man-in-the-middle attacker turns
an operator's `3` into `3.3` by design. The derived law's guard is therefore the one that holds
at a value the plant can actually carry, and the hand law's is not. This record states that and
nothing more: it does not move either rule.**

### Everything that writes the two tags

Searching the whole checkout for `VALVE_MODE` and `valve_mode` outside `venv/` gives eight hits,
two of which are the name definitions. There are exactly two writers.

**1. The PLC writes the tag-table default at startup.** `src/ics_sim/Device.py:395-397`, in
`PLC._before_start`:
<!-- evidence-ack: src/ics_sim/Device.py:395-397 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
for tag, value in self.tags.items():
    if self._is_output_tag(tag) and self._is_local_tag(tag):
        self._set(tag, value['default'])
```

Both mode tags are `'type': 'output'` on `'plc': 1`, and `PLC1.__init__` passes `1`
(`src/PLC1.py:10`), so both are local to PLC1 and both are written. The value is the `'default'`
of the tag table, `3` in each case — `src/Configs.py:49` and `src/Configs.py:57`:
<!-- evidence-ack: src/Configs.py:49 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/Configs.py:57 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py:10 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
TAG_TANK_INPUT_VALVE_MODE:              {'id': 1, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
TAG_TANK_OUTPUT_VALVE_MODE:             {'id': 6, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
```

**2. The operator console writes what the operator typed.** `src/HMI2.py:47` and `src/HMI2.py:50`:
<!-- evidence-ack: src/HMI2.py:47 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/HMI2.py:50 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
elif input1 == 4:
    self._send(TAG.TAG_TANK_INPUT_VALVE_MODE, input2)

elif input1 == 5:
    self._send(TAG.TAG_TANK_OUTPUT_VALVE_MODE, input2)
```

and `input2` is bounded, for these two menu entries only, in `HMI2.__get_choice`
(`src/HMI2.py:77-79`):
<!-- evidence-ack: src/HMI2.py:77-79 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
input2 = int(input('Command (1 to 3): '))
if input2 < 1 or input2 > 3:
    raise ValueError('Just 1, 2, and 3 are acceptable for command')
```

That `int()` and that range test are **the only validation of a valve mode anywhere in the
checkout**, and they live in a terminal prompt in the operator console, not in the PLC, not in
the tag table, and not in the protocol layer. A `ValueError` there is caught by
`HMI2._operate` (`src/HMI2.py:55-58`) and printed; no write happens. So on this path the value
is an `int` in `{1, 2, 3}`.
<!-- evidence-ack: src/HMI2.py:55-58 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

**Nothing else writes them.** `CommandInjectionAgent` flips a value between 0 and 1, but its
three targets — one live, two commented out — are `TAG_TANK_INPUT_VALVE_STATUS`,
`TAG_TANK_OUTPUT_VALVE_STATUS` and `TAG_CONVEYOR_BELT_ENGINE_STATUS`
(`src/CommandInjectionAgent.py:48-50`), the actuator tags, not the mode tags. `DDosAgent` calls
`self._receive(self.__target)` only (`src/DDosAgent.py:38`) and never writes. `PLC2` handles
`TAG_CONVEYOR_BELT_ENGINE_MODE`, a third tag on a different PLC. `HMI1` displays, `HMI3` writes
the three setpoints. `FactorySimulation` writes the four sensor tags. The scapy replay attack
resends sniffed packets unchanged, so it cannot introduce a value that was not already on the
wire. Nothing outside `*.py` mentions either tag.
<!-- evidence-ack: src/CommandInjectionAgent.py:48-50 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/DDosAgent.py:38 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

### Nothing between the wire and the guard constrains the value

The question is not only who writes, but what the stack would accept. Nothing in it narrows the
value at all. `ModbusBase.encode` (`src/ics_sim/protocol.py:58-63`) is the whole of it:
<!-- evidence-ack: src/ics_sim/protocol.py:58-63 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
def encode(self, number):

    number = int(number * self._precision_factor)

    if number > self._max_int:
        raise ValueError('input number exceed max limit')
```

with `_precision_factor` 10 000 and `_max_int` 2³², so the register pair carries any multiple of
0.0001 from 0 to 429 496.7295. There is no enum, no range, no integer check and no per-tag rule;
the one refusal is the ceiling. `decode` (`protocol.py:43-56`) divides by the same factor and so
always returns a **float**, never an int. `ServerModbus.set` and `get` (`protocol.py:115-120`)
write and read the holding registers directly. `ActuatorConnector.write`
(`src/ics_sim/Device.py:56-58`) and every `Connector.set` in `src/ics_sim/connectors.py` pass the
value through untouched: a grep of `connectors.py` and `protocol.py` for `min(`, `max(`, `clamp`,
`round` or `if value` returns nothing.
<!-- evidence-ack: src/ics_sim/Device.py:56-58 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/connectors.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

The guard that consumes the value, `_check_manual_input` at `src/ics_sim/Device.py:404-414`,
tests two equalities and falls through:
<!-- evidence-ack: src/ics_sim/Device.py:404-414 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
mode = self._get(control_tag)

if mode == 1:
    self._set(actuator_tag, 0)
    return True
elif mode == 2:
    self._set(actuator_tag, 1)
    return True
return False
```

So any value that is neither 1 nor 2 — `3.3`, `0`, `4`, `2.5`, `429 496.7295` — makes the
automatic comparison run. There is no branch that treats an unexpected mode as an error, and no
log line that notices one.

### The repository ships an attack that produces such a value

`ScapyAttacker.inject_callback` (`src/ics_sim/ScapyAttacker.py:140-156`) is the man-in-the-middle.
It rewrites the data words of every Modbus packet of length 11 (a write request) or 7 (a read
response) that passes through it:
<!-- evidence-ack: src/ics_sim/ScapyAttacker.py:140-156 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
value = ScapyAttacker.modbus_base.decode([modbus_packet.Data0, modbus_packet.Data1])

new_value = value + (value * ScapyAttacker.error)
values = ScapyAttacker.modbus_base.encode(new_value)
```

`modbus_packet.Reference` — the register address — is read at `ScapyAttacker.py:160`, but
only to fill in a log record. It is **never** compared against anything, so the rewrite
applies to every tag alike. The mode tags are written over this exact path: `HMI2._send` goes to
`ClientModbus.send`, which calls `write_multiple_registers` (`protocol.py:90-92`), which is a
length-11 write request.

`error` is the attack's `--parameter`, defaulting to `noise=0.1` in both
`Attacks._do_mitm_scapy_attack` (`src/ics_sim/Attacks.py:32`) and
`AttackerBase._mitm_scapy_attack` (`src/AttackerBase.py:107`), and `AttackerMachine` puts
fourteen runs of it into its shipped scenario (`src/AttackerMachine.py:23`):
<!-- evidence-ack: src/AttackerBase.py:107 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/AttackerMachine.py:23 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Attacks.py:32 — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

```python
self.__attack_scenario += ['mitm-scapy'] * 14
```

An operator selecting "3) Send command for auto operation" during one of those windows writes
`3`, and the PLC's register receives `3 + 3 × 0.1 = 3.3`. `encode(3.3)` is `int(33000.000…)`, so
the stored value is exactly 3.3, and `decode` hands `_check_manual_input` the float `3.3`. Mode
3.3 is not 1 and not 2, so the comparison runs — which is what the derived law says and is not
what `controller_valve` says, because 3.3 is not `3.0`.

### What PHOS's own generator writes

`scripts/icssim/phos_icssim.py` writes a valve mode in four places, and every one of them writes
1, 2 or 3:

| Event kind | Line | Value written |
|---|---|---|
| `in_range_command` hold and release | 572, 575 | `VALVE_FORCE_OFF` = 1, then `VALVE_RELEASE` = 3 (defined at 243-244) |
| `maintenance` / `mimic_maintenance` | 593, 597 | the same 1, then 3 |
| `rogue_command` | 635, 637 | `2`, then `3` |
| `replay` | 648, 650 | `1`, then `3` |

So no corpus PHOS has generated contains a mode outside `{1, 2, 3}` on either tag, and the
generator contains no path that could put one there. That is a statement about what the
generator writes, read from the generator. It is not a statement about what any recorded run
contains, because no corpus was opened.

## The answer, in one line each

- **Under the simulator's intended operation — the PLC's default write and the operator console
  — the two tags hold only 1, 2 or 3.** That is enforced in exactly one place, a terminal prompt.
- **A value outside `{1, 2, 3}` is reachable.** Nothing below that prompt validates, the Modbus
  layer carries any multiple of 0.0001 up to 429 496.7295 as a float, and the checkout's own
  MITM attacker multiplies every write it sees by 1.1 with no regard for which register it is,
  turning an operator's `3` into `3.3`.
- **Not settled from source alone:** whether any particular recorded run actually contains such
  a value, and how often. That is a question about a capture, and no capture was opened here.

## What this establishes, and what it does not

**Established.** The mode a valve law must reason about is a float with no enforced domain, and
the one narrow domain in the checkout is a human-facing prompt that an attacker in the same
repository bypasses without targeting it. At mode 3.3 the derived guard and the hand guard give
different answers, and 3.3 is a value this plant can carry. The difference ADR 0371 recorded is
not an artefact of two ways of wording the same thing.

**Not established, and deliberately not decided.** This record does not say which rule is right.
A law that speaks at 3.3 is not obviously better than one that stays silent there: the hand rule
is faithful to the mode the tag table calls normal, the derived rule is faithful to the function
the controller calls, and a plant's engineers might sign either. Choosing is Elijah's, and it
needs its own declaration whichever way it goes. Nothing here is a measurement: no corpus was
scored, no held-out corpus opened, no attack generated, and there is no rate, recall, latency or
coverage figure in this record, because reading source cannot produce one. Nothing here says
Atlas would notice a mode of 3.3, or that noticing it would be useful; the law page is still
empty on every corpus run (ADR 0336). Nothing here transfers off ICSSim: that a Python
simulator's Modbus layer does not validate says nothing about a vendor PLC, which may well
reject an out-of-range mode in firmware. H1 stays refused. The six laws stay six. v1 stays 8 of
12. P1 stays blocked. H2, H3 and H4 stay closed until after 6 January 2027 or a later record
(ADR 0369), and this record does not open them.

## Consequences

A successor that wants to close bar 4 now knows the gap is live rather than theoretical, and
knows the shape of the fix: ADR 0371 already recorded that `DerivedGuard` can only hold an
exclusion list, so a guard type that holds both an exclusion list and an equality is needed
before the two forms can even be compared. This record adds that the exclusion list is the one
that matches the plant's reachable values, which is an argument about the hand law and not only
about the derivation. It is an argument, not a verdict.

It also names a second thing the derivation does not carry. ADR 0371 noted that
`_check_manual_input` writes the actuator at modes 1 and 2 and that the derived law drops it.
With no domain on the mode, that omission is wider than it looked: the derived law is silent on
two determinate behaviours, and undefined-by-silence on an unbounded set of others.

## What would reverse this

Editing `controller_valve` or the derivation on the strength of this record — it is a finding,
not a declaration, and neither rule moves without one. Reading it as a verdict on H1; ADR 0371
is the verdict and it stands. Reading "reachable" as "observed": no run was examined. Quoting
3.3, 0.1, 14 or 429 496.7295 as a detection figure, a rate or a score — they are a product, a
default, a scenario count and a transport ceiling read out of source text. Claiming a real PLC
behaves this way. Opening H2, H3 or H4 because this record is interesting.
