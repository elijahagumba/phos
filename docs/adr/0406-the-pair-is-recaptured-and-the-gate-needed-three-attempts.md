# ADR 0406 — The pair is recaptured, the block freeze is in the files, and the gate needed three attempts to be honest

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS capture, second pass. Runs `97201` and `97206` on `grfics-v3-bridge`
- **Supersedes:** nothing. ADRs 0402–0405 stand. ADR 0403's v1 numbers are unchanged and its files
  are preserved
- **Depends on:** [ADR 0405](0405-the-pair-is-recaptured-with-all-thirteen-hmi-tags.md),
  [ADR 0404](0404-the-cyber-relay-freezes-all-thirteen-registers-and-the-pair-is-more-symmetric.md),
  [ADR 0403](0403-both-grfics-runs-were-captured-and-the-pair-disagrees-as-predicted.md),
  [ADR 0401](0401-grfics-runs-through-a-bridge-and-that-is-a-different-corpus.md)

## Context

ADR 0405 declared a recapture with all thirteen HMI tags, so that ADR 0404's correction — the relay
freezes the whole block, not one tag — would be **in the files** rather than only in a live-stack
measurement. It named its own falsifier: the block freeze must be visible in `97206`'s HMI stream and
absent in `97201`.

Getting there took three failed attempts. Each failure was a real defect with a real cause, and each
is recorded rather than smoothed, because the sequence is the most useful part of this record.

**Credit:** GRFICSv3 is Fortiphyd's. Research use permitted by email; Fortiphyd asks for credit.

## The three failures

**1. No live baseline.** The first thirteen-tag cyber run armed the relay *and* the ARP spoof before
sampling began, so every HMI tag was frozen from sample one — including the 594 s quiet phase that
exists to record a live plant. The engine moved throughout (34.64 → 38.47) while the screen sat at
34.5693. Caught by comparing quiet-phase spread against event-phase spread per tag, which is only
possible because the wider stream exists. **Fixed** by starting the relay polling early but applying
the ARP spoof and redirect in `_start_event`, so the quiet phase sees a real plant.

**2. A refusal that fired when nothing was wrong.** Fixing (1) introduced an inverted check —
`_relay_served() and armed_checked`, with `armed_checked` initialised `False` — so the run refused
itself at t=600 s while the relay was serving normally. A false refusal is as damaging as a missed
one: it discards a valid run and reports a mechanism failure that did not happen. **Fixed** to a
plain `_relay_served()`, with three tests pinning the block-present, empty-log and no-block cases.

**3. The gate measured the wrong quantity, twice.** The first version compared the *instantaneous gap*
between HMI and register against 0.5. On a near-equilibrium plant the frozen value sits close to the
live one: measured, the HMI held 43.9719 for sixty seconds while the register moved across a 0.235
band, so the gap never exceeded 0.16 and a working freeze was refused as a passthrough. The second
version used whole-event spread with a 0.05 tolerance, and a *single* pre-freeze sample made the
spread 0.0549 — refused again.

Both were threshold tests, and widening either to fit would have been a constant chosen after seeing
a failure, which this project refuses. **The gate no longer uses a tolerance on the value.** It skips
a transition window of `TRANSITION_SAMPLES = 10` — declared in code before the run, against a
measured transition of 1–2 samples — then requires the HMI to hold **exactly one value** for the rest
of the event while the register keeps moving. Exact constancy, no epsilon.

## The captured pair

| | `97201` physical | `97206` cyber |
| --- | --- | --- |
| Tags live in quiet, frozen in event | **1** (`Level`) | **6** (`Level`, `Pressure`, `PurgeValve`, `PurgeFlow`, `ProductValve`, `ProductFlow`) |
| Tags constant throughout | 4 (`AValve`, `AFlow`, `BValve`, `BFlow`) | 7 (the four above, plus `AComp`, `BComp`, `CComp`) |
| `Level` quiet spread → event spread | 0.2899 → **0.0000** | 0.2396 → **0.0000** |
| `Pressure` quiet → event | 10.3029 → **10.4005** (still moving) | 11.2795 → **0.0000** (frozen) |
| Engine `measured` during event | frozen at one value | **kept moving** |

**The falsifier is satisfied.** ADR 0404's correction is now visible in the recorded files: the cyber
run freezes every HMI tag that was moving, the physical run freezes only the tag the engine faulted,
and the engine keeps moving only in the cyber run. That is the design doc's tell recorded in a form a
reader can check without starting a container.

**Four tags are constant in both runs and carry no evidence either way.** `AValve`, `AFlow`, `BValve`
and `BFlow` do not move even in the quiet phase of a healthy plant, because the simulated plant holds
them fixed. They must not be counted as "frozen by the attack"; the table separates them for that
reason. `AComp`, `BComp` and `CComp` are constant only in the cyber run's quiet phase here, which is
plant state and not a mechanism effect — they are recorded as constant, not as evidence.

## Decision

1. **Both runs are kept, and they replace the v1 pair as the current captures.** v1 stays on disk
   under `data/grfics-dev/v1-<run>/`, so ADR 0403's table remains reproducible from the files that
   produced it (ADR 0405 Decision 2).

2. **ADR 0405's falsifier is met and is recorded as met.** The block freeze is in `97206` and absent
   in `97201`, per tag, in the CSVs.

3. **The gate is exact-constancy, not a threshold.** The number `TRANSITION_SAMPLES = 10` is the only
   tunable, it was declared before the successful run, and it is ten times the measured transition.
   Six tests pin the gate's behaviour including the single-pre-freeze-sample case that refused a
   working run.

4. **The three failures are part of the result, not an embarrassment to hide.** Two of them produced
   wasted runs and one produced a false refusal. Recording them is what makes the fourth attempt
   trustworthy, and the near-equilibrium near-miss is exactly the distractor GRFICSv3's own design
   doc names.

5. **Nothing is measured.** No recall, rate, accuracy or confidence is computed. `eval_runs/log.jsonl`
   is not appended, no frozen row is read, and **v1 stays 8 of 12**. A capture is not a score.

6. **No cross-zone claim.** One Docker bridge, no router, so no firewall, Suricata or arpmon evidence
   exists on this corpus and none is claimed (ADR 0401).

## Consequences

- **The pair can now be posed with the block evidence attached**, which is what ADR 0405 set out to
  achieve. A reader can see, per tag, which run froze what.
- **The harness is more trustworthy than when it started**, but only because three defects were found
  by measurement rather than by inspection. The pattern worth keeping: every one of them was caught by
  checking a mechanism's *effect* against a live plant at a known time, not by re-reading the code.
- **The v1 archive grows to two more directories.** Four run directories total, two current and two
  v1, named rather than inferred.
- **Still an emulated plant.** Any later result is a diagnosis, not proof (R4, ADR 0143), and it does
  not advance P1.

## What would reverse this

Reporting a `grfics-v3-bridge` capture as `grfics-v3`; claiming cross-zone, firewall or IDS evidence;
calling a capture a measurement or quoting a rate from it; counting the four permanently-constant tags
as attack evidence; replacing the exact-constancy gate with a tolerance on the value; widening
`TRANSITION_SAMPLES` after a failure; overwriting the v1 archive; or driving a `973xx` seed or any of
the other eight development runs without a new declaration.
