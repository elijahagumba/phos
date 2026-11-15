# Event coverage: what this simulator can already make happen, and what it cannot

PART R4 asks for an audit before any code, against a target catalogue of attacks, faults,
maintenance and operator behaviour, and says plainly: **do not rewrite items that exist.** This is
that audit. It was taken by reading the package, not by reading its documentation.

Status means:

- **exists** — the effect is implemented, labelled, and tested. R4 adds nothing.
- **partial** — the effect is implemented but something R4 asks for is missing: usually the label
  kind, or the ability to place it on a *generated* plant rather than a hand-written one.
- **missing** — nothing in the package produces it.

## The finding that shapes the rest of R4

`phos.synth.injection.Injection` has exactly two methods — `actuator_overrides` and
`reading_overrides` — so the package can manipulate a plant at two layers: what the instruments
report, and what the actuators do. `phos.synth.traffic.modbus_frames` then builds the capture *from
the completed run*, and takes no manipulation of any kind (its one hook, `dropouts`, drops frames
that the realism model already decided to lose).

So **there is no network layer**. Every attack that acts on the wire rather than on the process —
modification in transit, a polling flood, replay of captured traffic — is not merely unimplemented
but has nowhere to attach. That is one gap with three names, and it is the largest piece of work in
R4.

The second structural finding is smaller and worth stating because it is easy to misread: faults
and maintenance *effects* mostly exist, in `phos.synth.realism`, as **benign phenomena**. What is
missing is not the physics but the *label*: a stuck transmitter planned by `plan_realism` is
recorded as `SENSOR_FAULT` realism, and R4 wants it recorded as a fault, with the layer it acted on
and whether it had a physical effect. Re-implementing those effects would be the mistake this audit
exists to prevent.

## A note on the technique names

Where a public ICS ATT&CK technique fits, it is named. The mapping is **a reading of the technique
descriptions, not an authoritative classification** — several of these items sit across two
techniques and one (replay) has no dedicated technique at all. A label that said otherwise would be
a claim this repository has not earned, so each is given as the closest fit and nothing more.

## Attacks

| Target item | Technique (closest fit) | Status | Where it lives / what is missing |
|---|---|---|---|
| Sensor spoofing — freeze | T0856 Spoof Reporting Message | **exists** | `injection.HoldReading`; `realism.SensorFault.stuck_at` for the benign twin |
| Sensor spoofing — constant bias | T0856 | **exists** | `attacks.manipulations.ReadingBlend`, `AttackType.BLATANT` and `LIAR` |
| Sensor spoofing — slow ramp drift | T0856 | **exists** | `attacks.manipulations.ReadingTrack`, `AttackType.STEALTH_DRIFT` |
| Sensor spoofing — replay | T0856 | **built in R4** | `events.SensorReplay` — a signal replays a stretch of its own earlier readings on a loop, so every statistic of it alone is right and only its disagreement with the rest gives it away |
| Unauthorised command injection | T0855 Unauthorized Command Message | **exists** | `AttackType.ROGUE_COMMAND`, `command.WriteAuthority`, `command.PlannedCommandSource`. Scored apart from a known-station write (ADR 0034) |
| Command injection shaped like the operator | T0855 | **exists** | `AttackType.MIMIC_COMMAND` |
| Stealthy variants inside normal ranges | — (a property, not a technique) | **exists** | `AttackType.CORRELATION_BREAK` and `STEALTH_DRIFT`; `spec.strength_of` and `DifficultyLevel` |
| Value modification in transit | T0830 Adversary-in-the-Middle | **built in R4** | `wire.InTransitChange` — one block's read responses rewritten in a window, paired request-to-response to target one meter |
| Polling flood | T0814 Denial of Service | **built in R4** | `wire.PollBurst` — extra well-formed reads injected on a real conversation |
| Replay of captured traffic | T0830 (no dedicated technique) | **built in R4** | `wire.TrafficReplay` — a window of frames copied to a later instant, sequence numbers reused on purpose |
| Control-logic parameter tampering | T0836 Modify Parameter | **deferred, with reason** | Not built. A controller's gain, integral time and limits are *internal* plant state, not something an external manipulation reaches through the sensor or actuator layer the `Injection` model is built on — nor through the process layer the leak added. Building it means routing every one of the six templates' controller construction through a time-varying parameter source: a cross-cutting change to all of them and the base `Plant` for one attack, which belongs in its own declaration rather than smuggled into R4. See the closing section |

Input-hostile attacks (`AttackType.MALFORMED_RECORD`, `OUT_OF_RANGE`, `TRUNCATED`,
`POISONED_BASELINE`) are **out of scope for R4**: they attack a *file reader* rather than a plant,
they are already implemented in `attacks.hostile`, and ADR 0017 and ADR 0041 record that surviving
them is robustness and not detection. R4 adds nothing to them.

## Faults

| Target item | Status | Where it lives / what is missing |
|---|---|---|
| Sensor drift | **partial** | `realism.SensorFault.offset` and `PhenomenonKind.EQUIPMENT_AGEING` produce it. Missing: a fault *label* distinct from realism, and the R4 record |
| Sensor dropout | **partial** | `realism.CommsDropout`, and `traffic.modbus_frames` already honours it on the wire. Missing: the fault label and record |
| Fouling | **exists** | `PhenomenonKind.EQUIPMENT_AGEING`; the water works' filter headloss is a worked example of an unmeasured accumulating state |
| Stuck valve | **built in R4** | `events._stuck_valve` schedules `HoldActuator` as a fault, held where the actuator actually was (read from a normal run), with no issuer |
| Pump trip | **built in R4** | `events._pump_trip` drives an actuator to zero for a window |
| Leak | **built in R4** | `events.Leak`, through the new `injection.ProcessLoss` layer — removes inventory from the true state, so the loop chases the falling level and the conservation balance stops closing. Verified to move the residual, which is the proof it emerges from the physics rather than being painted on |

## Maintenance

| Target item | Status | Where it lives / what is missing |
|---|---|---|
| Work-order register | **exists** | `maintenance.plan_maintenance`, `WorkOrder`, `MaintenanceCalendar`, with SAP PM and Maximo exports. Deliberately blind to the attack schedule (ADR 0069), and that must not change |
| Controller in manual for a window | **built in R4** | `events._loop_in_manual` holds an actuator where it was, labelled maintenance |
| Sensor offline | **built in R4** | `events._sensor_offline` holds a reading under a work order |
| Valve exercised | **built in R4** | `events.ValveExercise` strokes a valve out and back as a triangle in time, under a work order |

**The register and the effects must stay independent.** `maintenance.py`'s whole argument is that
its calendar is laid out without seeing the attack schedule, so an attack inside a covered window
is a coincidence between two rhythms rather than a construction. R4 adds maintenance *effects*; if
those effects were scheduled from the same draw as the attacks, that argument would be destroyed.
Whatever R4 builds must take its windows from the calendar or from its own stream, never from a
schedule that has seen the attacks.

## Operator behaviour

| Target item | Status | Where it lives / what is missing |
|---|---|---|
| Scheduled setpoint changes | **exists** | `plant.BenignEvent`, `plant.lay_out_events`, and every family's `DisturbanceSpec` |
| Stochastic placement | **exists** | `lay_out_events` draws the gaps; R2's families draw the schedule's bounds |
| Batch start and stop | **exists** | `plants.batch` and `plants.batch_mix` step through a recipe; the phase signal is published |
| Mode changes | **partial** | A batch plant's phase is a mode and it changes. A continuous plant has no mode concept at all |
| Manual operations | **partial** | `OPERATOR_INTERVENTION` covers taking a loop to manual. Missing: the operator *write* on the wire that would accompany it on a real plant |
| Harmless self-corrected errors | **missing** | Nothing produces an operator making a mistake and putting it right — a setpoint typed wrong and corrected a minute later. This is the single most valuable benign shape in the catalogue, because it is the one a naive detector will always call an attack |

## What R4 built, and the one thing it did not

Built:

1. **The network layer** the audit found had no attachment point — `phos.synth.wire`, three
   transforms on an already-built capture: a value changed in transit, a poll burst, a traffic
   replay. Applied after `modbus_frames` so that function is untouched and the golden corpora still
   match, and read back through the real dissector with no malformed frames.
2. **Three faults** — stuck valve, pump trip, leak — in `phos.synth.events`. The leak needed a new
   process layer (`injection.ProcessLoss`), because a leak is neither a sensor nor an actuator
   manipulation: it removes inventory from the true state, so the loop chases the falling level and
   the conservation balance stops closing. That the residual moves is checked, because a balance
   that kept closing would be the tell that nothing really leaked.
3. **Three maintenance effects** — sensor offline, valve exercised, controller in manual — each
   with a work order behind it in the label.
4. **The sensor replay**, the one sensor-layer attack gap.
5. **One label record per event** (`events.EventRecord`), carrying everything R4 asks for,
   including the field the existing `AttackGroundTruth` does not: the layer. Two of its fields —
   whether a physical effect occurred and whether the event stayed in the normal range — are
   *measured* by `assess_events` against a normal run of the same plant, not declared, so a stealth
   result is earned rather than asserted.

**Not built, and deliberately: control-logic parameter tampering.** A controller's gain, integral
time and output limits are *internal* plant state. Nothing external reaches them: the `Injection`
model perturbs a plant "through the plant's own mechanisms" — the sensor and actuator layers — and
the leak added a process layer, but a loop's own tuning is none of those. Changing it means every
one of the six templates routing its controller construction through a time-varying parameter
source, a cross-cutting change to all of them and the base `Plant` for a single attack. That is a
design decision with its own cost and belongs in its own declaration, not smuggled into R4 where it
would be the one effect built unlike all the others. It is listed here as deferred rather than done
so the gap is visible, and the operator self-corrected error is deferred with it: both are setpoint
or parameter events that want a cleaner operator-write path than R4 builds, and pairing them keeps
that path a single later piece of work.

**What R4 does not build at all:** no attack search, no optimisation, no scoring. Events are
scripted from seeds. PART S7's breaker is where a search belongs, and it is a separate package for
the reason ADR 0435 gives for sealing — a generator that could aim at a detector's weak spot is no
longer generating data, it is tuning against a target.

**Nothing in R4 touches a real device or a real network.** Every effect acts on in-memory
simulated signals or on files this package writes. `tests/synth/test_no_network.py` asserts it over
the whole package rather than trusting it.
