# ADR 0325 — The law-page inlet is a named map

- **Status:** Accepted
- **Date:** 2026-10-23
- **PART:** Atlas, the law-page inlet
- **Supersedes:** nothing
- **Depends on:** [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0324](0324-the-operating-plan-loads-in-both-tools.md)

## Context

`assess_plant` already takes setpoint steps, program acts, bookings, work orders, tag bookings, writes, an allowed-station set, a register, and one optional controller sample. The operator page has no path from a historian row or a dissected Modbus message to those arguments. A function code is not a station and not a download, an upload, or an online edit. The caller supplies the station name.

This record names that path. It does not build it. It opens no capture and no historian file. It generates no corpus and scores none. `eval_runs/log.jsonl` is not appended. Held-out stays unopened. The residual files stay unedited and unimported by this record. v1 stays 8 of 12. ADR 0316 stays the residual clock and is not run here.

The later invariant score, when a separate declaration names its command, uses the development corpus `phos-icssim-dev`. That directory is not opened in this record. The result name reserved for that score is `law-inlet:invariants`. This record does not authorise the run.

## Decision

**Rows the caller already named become `assess_plant`'s arguments. A function code does not become a station or a program act. A malformed frame does not become a break.**

The function is `inlet_from_tables` in `src/phos/atlas/law_inlet.py`. It returns a `LawInlet` and nothing else. It does not call `assess_plant`. It does not open a file. It does not import `consistency.py`, `command_consistency.py`, `walk_consistency.py`, `drift_consistency.py`, `bending_consistency.py`, `breadth_consistency.py`, `queue.py`, `grouping.py`, `shift_brief.py`, `handoff_page.py`, or `leap_stack.py`.

`LawInlet` carries exactly the arguments `assess_plant` already takes: `steps`, `transfers`, `register`, `bookings`, `work_orders`, `tag_bookings`, `writes`, `allowed_stations`, and `controller`. No score, confidence, probability, weight, or magnitude field.

The tables are:

- **Historian rows.** Each row is a tag, a timezone-aware time, and a value. A row becomes a `SetpointStep` only when its tag is in the `setpoint_tags` set the caller passed. A tag outside that set is not a step. The function does not decide that a tag looks like a setpoint.
- **Controller sample.** Omitting `controller_tags` leaves `controller` as `None`. Passing the map requires the ten field names already on `ControllerSample`: `level`, `level_min`, `level_max`, `input_valve`, `input_mode`, `bottle_level`, `bottle_max`, `belt`, `output_valve`, `output_mode`. Each name maps to one historian tag. Each of those tags has exactly one row, and those rows share one timezone-aware time. That is one `ControllerSample`. A missing row, a second row, a second time, an empty tag, a repeated tag, or a field outside those ten raises, and no inlet is returned. `PLC1_CONTROLLER_TAGS` may be passed by the caller. It is the tag names already written on `ControllerSample`. The function does not apply it on its own.
- **Writes.** A `WriterWrite` the caller built is copied. A dissected pair is a station string plus a `ModbusMessage`. The station is the string. The time is the message timestamp. `function_code`, `unit_id`, `src`, and `dst` are not read. An empty station raises.
- **Malformed frames.** A non-empty `malformed` sequence raises before any inlet is built. A `MalformedFrame` does not become a `LawBreak`.
- **Transfers.** Each pair is a `ProgramAct` the caller supplied and a timezone-aware time. An `int` is refused through `refuse_function_code`, and no inlet is returned. No parameter accepts a function code as an act.
- **Bookings, work orders, tag bookings, the allowed-station set, and the register** are copied through. The register is required. An empty register is stored and not filled.

A naive time raises. The inlet is not returned.

### Fallback

If the map cannot be built without inferring a station from a function code, or without treating a function code as a download, an upload, or an online edit, this declaration is refused and `law_inlet.py` is not added. The tables above do not need that inference. The inlet is built.

### Invariant bar

Reserved for `law-inlet:invariants`. Not run in this record. Pinned by the inlet's own tests on rows the test constructs:

1. Every placed sentence starts with its law name, a period, and a space.
2. No placed sentence contains confidence, probability, weight, magnitude, or score.
3. The page length is at most 8.
4. The register is partitioned across held, broken, and unstated.
5. A ninth break by time is absent.
6. A `LawBreak` subclass is refused.
7. A malformed Modbus frame stays a `MalformedFrame` and never becomes a `LawBreak`.
8. An empty register yields three empty lists.

A count from a later score is a count of false laws. It is not a detection rate. The predicates are not retuned if ordinary rows fill the page.

### Options

1. Infer the station from the function code, the unit id, or the endpoint, and treat function 16 as a download. Refused. That is the fallback this record exists to close.
2. Open `phos-icssim-dev` while naming the map. Refused. The corpus stays unopened until a score declaration is in HEAD.
3. A function that copies named columns onto the arguments `assess_plant` already takes, and raises when a function code or a malformed frame is offered as an act or a write. Chosen.

## Consequences

**Gained.** The inlet has one shape, named before the module exists. A later edit that reads `function_code` to choose a station or an act contradicts this record.

**Cost.** This record does not place a slot. It does not score `phos-icssim-dev`. v1 stays 8 of 12. The ceiling, the window, and the walk length stay where they are.

## What would reverse this

Reading a function code, a unit id, or an endpoint to produce a station or a `ProgramAct`. Returning an inlet that carries a score. Calling `assess_plant` inside `inlet_from_tables`. Importing a residual detector. Opening a capture or a historian file from this module. Treating this record as a detection rate, as 8 of 12 moving, as 10×, as 2–3 a day, or as at least 70%.
