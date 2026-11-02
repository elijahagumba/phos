# ADR 0404 — ADR 0402's co-tag claim was wrong: the cyber relay freezes all thirteen registers, and the pair is more symmetric than recorded

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** Correction to ADR 0402 finding 6, and to every surface that repeated it
- **Supersedes:** [ADR 0402](0402-the-grfics-capture-harness-is-declared-and-the-cyber-half-runs-on-the-bridge.md)
  **finding 6 only.** ADR 0402's other four facts, its two-run scope and its fences stand unchanged.
  ADR 0403's measured numbers stand unchanged; one sentence of its interpretation does not
- **Depends on:** [ADR 0402](0402-the-grfics-capture-harness-is-declared-and-the-cyber-half-runs-on-the-bridge.md),
  [ADR 0403](0403-both-grfics-runs-were-captured-and-the-pair-disagrees-as-predicted.md),
  [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md)

## Context

ADR 0402 finding 6 recorded two claims about the cyber relay's register window:

1. A 1-register relay "left the HMI's other points reading `0`".
2. A 13-register relay "freezes the target correctly and leaves the other twelve tags live
   (measured: `Level` held at 43.8834 while `Pressure` 2698.58 and the flows 1793.80 / 642.17 kept
   moving)".

**Claim 1 is right. Claim 2 is wrong, and the inference drawn from both — that the pair is
asymmetric because the cyber half freezes a block while the physical half freezes one tag — is
right for a different reason than the one recorded.**

Both claims were re-tested against the live stack after the captures were committed. The
measurements below are new; nothing was re-run against the captured data.

## What was measured

**The relay freezes the whole block.** `modbus_relay.py`'s `FAULT_FROZEN` branch caches
`self._frozen = list(true_values)` on the first poll and returns it forever after
(`attacker/cyber_injects/modbus_relay.py`, `FaultState.apply`). Read directly from the attacker's
listener six seconds apart:

```
read1: [65535, 41972, 0, 0, 8320, 7469, 5976, 2542, 55324, 28878, 30843, 8659, 26032]
read2: [65535, 41972, 0, 0, 8320, 7469, 5976, 2542, 55324, 28878, 30843, 8659, 26032]
ALL 13 IDENTICAL: True
```

**A 1-register relay serves the target and zero-pads the rest.** A relay holding only address 109,
read as the HMI's 13-register block, returned:

```
[0, 0, 0, 0, 0, 0, 0, 0, 0, 28864, 0, 0, 0]
```

Only the held register is non-zero. The pymodbus server zero-pads an unmapped read rather than
erroring, so the HMI receives thirteen values in which twelve are `0`.

**So `Pressure` does not keep moving during a cyber freeze.** With the full 13-register relay in
place behind the ARP redirect, all four HMI points sampled were identical across three samples six
seconds apart:

```
sample 1: ProductFlow 39.826  Pressure 2698.137  Level 43.917
sample 2: ProductFlow 39.826  Pressure 2698.137  Level 43.917
sample 3: ProductFlow 39.826  Pressure 2698.137  Level 43.917
```

The original "`Pressure` 2698.58 and the flows kept moving" observation was taken **before** the ARP
redirect was in the path — the HMI was still polling the real PLC at that moment, which is exactly
the condition the session had already identified as a passthrough. It was read as evidence about the
relay when it was evidence that the relay was not yet connected.

## Decision

1. **Finding 6's second claim is retracted.** A 13-register relay does not leave the other twelve
   tags live; it freezes all thirteen, because that is what its frozen mode does with the list it
   was handed. `Pressure` freezes with `Level`.

2. **The pair is therefore more symmetric than ADR 0402 and ADR 0403 recorded, and the asymmetry is
   in the right place.** Both runs freeze the value the HMI sees for the target tag. They differ in
   **where** the freeze enters:

   - `97201` physical: the engine's `measured` is frozen, so **everything downstream agrees** —
     `measured`, the PLC register, and the HMI all hold one value. That is the design doc's "PLC and
     HMI are fooled identically".
   - `97206` cyber: the engine and the PLC register keep moving, and only the HMI's view is frozen.
     That is the design doc's "the PLC and HMI disagree".

   **That is the tell, and it was already visible in the captured data** — ADR 0403's table shows
   `measured` spread **0.0000** in the physical run against **8.2942** in the cyber run, with `true`
   spread 15.1862 against 8.2942. The numbers never depended on the wrong claim. Only the
   *explanation* of why the cyber run's mechanism differs did.

3. **One collateral the captured files cannot show, and it is stated rather than hidden.** Because
   the relay freezes the whole block, the cyber run also froze eleven tags that the physical run left
   live. `hmi_values.csv` records only `Level`, so **the captures do not contain the evidence for
   this across the whole block** — it was established on the live stack after the fact. A future
   capture that wants that evidence should record more than one HMI point per sample. This is a
   gap in the capture, not in the measurements of `Level`.

4. **`capture.py` is unchanged.** It already serves the full block, which is correct — a narrower
   relay would serve zeros for twelve tags and produce a completely different event. The code was
   right; the comment beside it was not, and the comment is corrected here.

5. **Every surface that repeated the wrong claim is corrected in this change**, with the correction
   named rather than made silently: ADR 0402 carries a pointer to this record, and `PROGRESS.md`,
   `README.md`, `easy to reads/164` and its index entry are rewritten to say what was measured.

## Consequences

- **The pair is easier to describe and stronger than it looked.** Two runs, same target, same event
  shape, same frozen value at the HMI, differing in whether the freeze is upstream or downstream of
  the PLC. That is exactly the comparison the design doc proposes.
- **ADR 0403's numbers are untouched.** The correction changes the interpretation, not a
  measurement. Nothing is re-captured, and re-capturing would not change the table.
- **A gap is now known**: the captures record one HMI tag, so a block-wide statement about the HMI
  cannot be made from the files alone. Recorded so the next capture is designed better rather than
  the claim being made anyway.
- **Nothing is measured.** v1 stays **8 of 12**. A capture is not a score, no rate is produced, and
  no cross-zone evidence exists on this corpus (ADR 0401).

## What would reverse this

Asserting the retracted claim again; treating the cyber run as having left co-tags live; quoting the
"`Pressure` kept moving" observation as evidence about the relay when it was taken before the relay
was in the path; claiming block-wide HMI behaviour from `hmi_values.csv`; or letting this correction
be read as changing any number ADR 0403 recorded.
