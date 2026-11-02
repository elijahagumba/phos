# ADR 0402 — The GRFICS capture harness is declared, and the cyber half does run on the bridge

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS capture. Driver for `grfics-v3-bridge`, runs `97201` and `97206`
- **Supersedes:** nothing. ADR 0401's corpus registration, ADR 0400's generator rules and ADR 0144's
  run design are unchanged and are relied on, not edited
- **Depends on:** [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md),
  [ADR 0400](0400-the-refused-lane-e-modules-stay-and-the-grfics-generator-is-named.md),
  [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md)

## Context

ADR 0401 registered `grfics-v3-bridge` and left `data/grfics-dev/` empty. ADR 0400 named the
generator, which lists the twenty declared runs and produces no data. This record declares the
driver that fills that gap, after four facts were established by hand against the real stack.

**Credit:** GRFICSv3 is Fortiphyd's. Fortiphyd permitted research use by email and asks for credit.
Its checkout stays under `data/grfics-source/`, is git-ignored, and no line of its source enters this
repository.

### The four facts, established before any code

The work order that opened this session predicted the cyber half might be impossible on a bridge,
because §4.1 of GRFICSv3's own design doc freezes the HMI's view by ARP-spoofing it between itself and
its gateway, and a single bridge has no gateway to sit behind. **The prediction is wrong, and the
reason matters.** Each fact below was measured on the running stack, not read off the source.

1. **The pinned commit exposes fault injection through a normal interface.** Yes.
   `simulation/simulation/main.cc` listens on `127.0.0.1:55555` and accepts
   `{"request":"write","data":{"inputs":{...}}}`; `TE::update` reads `tank_level_fault_mode` and
   `tank_level_fault_severity` from it (`TE_process.cc:307-311`). The mode enum is
   `0 none / 1 frozen / 2 drift / 3 noise / 4 dropout` (`TE_process.cc:7-11`). No C++ was edited and
   no image was rebuilt. Verified live: writing `{"tank_level_fault_mode":1}` froze `measured` at
   44.0844 while `outputs.liquid_level` fell to 43.9821.

2. **`true` and `measured` are both readable from inside the simulation container, in one call.**
   `TE::get_state_json()` (`TE_process.cc:561-626`) returns `outputs` (the engine's true physical
   values), `state` (every fault mode and severity) and `measured` (what the Modbus device scripts
   expose) in a single response to one `{"request":"read"}`. **This is stronger than the fallback the
   work order allowed.** The tell is engine-true-vs-HMI, not the weaker PLC-vs-HMI, and the two sides
   are sampled by one request rather than two that could drift apart.

3. **ScadaLTS reaches the PLC over the bridge with no router.** Yes. With the ICS subnet as a plain
   Docker bridge on `192.168.95.0/24`, the HMI's `init.sh` route add fails harmlessly
   (`Nexthop has invalid gateway`, because `192.168.90.200` does not exist) and the bridge's own
   connected route covers the PLC. Measured: `192.168.95.2:502` established to
   `192.168.95.107:48834`. The HMI polls with **one FC 04 request for input registers 100–112
   (13 registers)** per cycle and writes the decoded values into its `pointValues` table.

4. **The cyber half runs on the bridge.** This is the finding that reverses the work order's
   premise, so it is recorded with the mechanism rather than as a bare yes.
   - `attacker/cyber_injects/modbus_relay.py` — Fortiphyd's own validated relay — needs no gateway.
     It needs a TCP connection to land on it. That makes its requirement a **shared L2 segment with
     the victim**, not a gateway, and a single bridge is exactly one shared L2 segment.
   - Measured live: `arpspoof -i eth0 -t 192.168.95.107 192.168.95.2` from the attacker container
     rewrote the HMI's ARP cache entry for the PLC to the attacker's MAC
     (`aa:a5:63:18:3d:55` → `52:ad:2f:30:e1:27`). `iptables -t nat -A PREROUTING -p tcp --dport 502
     -j REDIRECT --to-ports 502` made the HMI's connection terminate at the relay. Measured:
     `192.168.95.6:502` established to `192.168.95.107:34846`, and the relay's own
     `true=… reported=…` log showing `reported` held while `true` moved.
   - The tell was demonstrated, not inferred. Sampled simultaneously with the freeze in effect:
     HMI `Level` **43.9048** constant across five samples while engine `true` fell **44.1262 →
     43.9864**. Restarting the relay to hold a *different* register value moved the HMI to
     **43.8864** — so the HMI is following the relay, not merely going stale because its polling
     broke. That distinction is the difference between a real capture and a plausible-looking one.

**A bridge is a weaker topology than macvlan in a different way, and it must be named.** ARP spoofing
between the attacker and a victim on one segment is *easier* here than in the declared topology — but
the evidence the design doc's exercise is built on (router firewall logs, Suricata on the router's
interface, arpmon) does not exist, because there is no router. Fact 4 makes a cyber capture
*possible*; it does not make this corpus capable of cross-zone evidence. ADR 0401's fence stands.

### Two findings that shape the harness

5. **ScadaLTS archives a point only when its value changes.** With the physical freeze active, `Level`
   produced **no new `pointValues` rows at all** for the rest of the event while `Pressure` kept
   updating; the engine's `measured` was confirmed constant at 43.902187 across the same window. A
   driver that reads the HMI from `pointValues` would therefore report "no data" exactly when the
   event is most interesting, and a reader could mistake a stalled archive for a stalled plant.
   The harness reads the HMI's **current** point value, not its archive, and records a
   `hmi_archive_gap` flag when the archive stops advancing. The relay-side equivalent — an exact
   repeat of the whole 13-register block on consecutive polls — is Fortiphyd's own documented replay
   signature and is recorded per sample, not silently dropped.

6. **The HMI's block read constrains the cyber inject's shape.** The relay must serve the **whole
   13-register block**. Measured: a 1-register relay (address 109 only) left the HMI's other points
   reading `0`, because the block read is answered from a single register window. **The cyber twin
   therefore freezes the whole block and the physical fault freezes one tag.** The pair shares a
   target and event shape, not a mechanism, and a comparison of the two must say so.

   > **Corrected by [ADR 0404](0404-the-cyber-relay-freezes-all-thirteen-registers-and-the-pair-is-more-symmetric.md).**
   > The first half of this finding holds: a narrow relay does zero the tags it does not serve. The
   > claim that a 13-register relay "leaves the other twelve tags live" is **wrong** — it freezes all
   > thirteen, because that is what frozen mode does with the list it is handed. `Pressure` freezes
   > with `Level`. The pair is therefore more symmetric than stated here: both runs freeze the HMI's
   > value for the target, and they differ in whether the freeze enters upstream of the PLC (physical,
   > so PLC and HMI agree and are both wrong) or downstream of it (cyber, so they disagree). That is
   > the tell. The "`Pressure` kept moving" observation was taken before the ARP redirect was in the
   > path, which is why it looked like evidence about the relay.

## Decision

1. **`scripts/grfics/capture.py` is the driver, and it is declared here before its first run.** One
   invocation drives one run and writes one directory under `data/grfics-dev/`. It refuses any seed
   outside `{97201, 97206}` and refuses every `973xx` seed, so the held-back half stays unreachable
   by construction rather than by a caller's care.

2. **Only the declared pair is in scope: `97201` (physical/frozen/tank_level) and `97206`
   (cyber/frozen/tank_level).** The other eight development runs are not driven. A ten-seed sweep
   before the pair is shown to be distinguishable would spend the corpus to avoid the question
   (ADR 0400 Decision 4).

3. **Each run directory carries the six streams the work order names**, all stamped from one clock:
   `true_values.csv`, `measured_values.csv`, `hmi_values.csv`, `modbus.csv`, `events.json`,
   `manifest.json`. The clock is the host's wall clock sampled on every observation, and
   `manifest.json` names it and records the measured per-container offset so a reader can see the
   sampling error rather than assume it away. Measured: all four containers were within **+33 to +77
   ms** of the host.

4. **The event is 10 quiet minutes then 20 minutes of the named event (ADR 0144)**, with the
   timestamps of quiet-start, event-start and event-end recorded in `events.json` in the same shape
   as `data/phos-icssim-dev/*/events.json` (`kind`, `start`, `end`, `label`, `params`).

5. **The cyber half is driven only through Fortiphyd's own validated mechanism** — `arpspoof`,
   an `iptables` REDIRECT, and `modbus_relay.py --mode 1` on the full 13-register block. The harness
   starts and stops these inside the attacker container and records exactly what it ran in
   `manifest.json`. It does not reimplement the relay, and it does not substitute an easier
   mechanism that would look like a cyber capture without being one.

6. **If fact 4 had failed, the harness would capture `97201` alone and the record would say so.** It
   did not fail. The cyber run is only captured if the ARP redirect and the relay are both observed
   working in that run; a run whose relay never received a connection is written as **refused**, not
   as a cyber capture with missing columns. That check is a gate, not a note.

7. **Fences carried unchanged.** `grfics-v3-bridge`, never `grfics-v3`. No cross-zone claim: no
   firewall, Suricata or arpmon evidence exists on this corpus and none may be reported from it. No
   detection claim — **a capture is not a measurement**, nothing here scores Atlas, no recall or rate
   or accuracy is produced, and `eval_runs/log.jsonl` is not appended. No held-out seed. No GRFICS
   source or payload committed. Fortiphyd credited in this record and in any write-up.

8. **The harness is a script with tests, not a library addition.** It lives beside
   `generate_corpus.py`, is invoked by hand, and adds no dependency to `pyproject.toml`: the Modbus
   frames are parsed from a `tcpdump` capture written by a sidecar container sharing the target's
   network namespace, not by a new Python Modbus client.

## Consequences

- **`data/grfics-dev/` stops being empty**, and the tank-level pair becomes a capture rather than a
  registry entry. That is the first time this corpus has produced anything.
- **The cyber twin is real on this host**, so the pair the programme exists for can be posed. It
  cannot be posed *as the design doc poses it*: with no router there is no firewall or IDS evidence
  and no cross-zone path, so the pair tests the PLC-vs-HMI tell alone.
- **The pair is not symmetric.** The physical run freezes one tag at the source; the cyber run freezes
  the whole 13-register block in flight. Any later comparison must carry that difference rather than
  average it away.
- **The HMI archive is not a reliable sample source during a freeze** (finding 5). This is now known
  before a harness is written around it, which is the cheaper order.
- **Nothing is measured.** v1 stays **8 of 12**, no frozen row is read, and P1 remains the blocked
  human conversation. A capture does not advance P1 and is not a substitute for a real plant
  (R4, ADR 0143).

## What would reverse this

Reporting a `grfics-v3-bridge` capture as `grfics-v3`; claiming cross-zone, firewall, Suricata or
arpmon evidence from this corpus; calling a capture a measurement or quoting a rate, recall or
accuracy from it; driving any seed outside `{97201, 97206}` or any `973xx` seed; writing a cyber run
whose relay never received the HMI's connection as if it were a capture; committing GRFICS source or
any payload; or presenting the physical and cyber runs as the same mechanism rather than the same
target and event shape.
