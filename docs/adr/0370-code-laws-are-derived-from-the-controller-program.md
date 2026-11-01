# ADR 0370 — The valve law derived from PLC1 must equal the one copied by hand, or it is refused

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Atlas, build brief H, rung H1. Declaration. No code exists
- **Supersedes:** nothing
- **Depends on:** [ADR 0369](0369-h1-runs-now-and-the-later-rungs-wait-for-the-bid.md),
  [ADR 0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md),
  [ADR 0321](0321-the-controller-comparison-is-true-or-false.md),
  [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

`CONTROLLER_VALVE` in `src/phos/atlas/declared_law.py` is the only law in the register that was
copied by hand out of a controller program. The copy is four literals and two comparisons:

```
_VALVE_CLOSED   = 0.0   # what the quoted line writes to close a valve
_VALVE_OPEN     = 1.0   # what the quoted line writes to open a valve
_MODE_RELEASE   = 3.0   # the release value; any other mode is manual
_BELT_PAST_FILLER = 1.0 # the belt distance the quoted output line compares with >
```

with the input side closing strictly above `level_max`, opening strictly below `level_min`, and
saying nothing inside the band including either end; and the output side closing when the
bottle is strictly above its maximum **or** the belt is strictly past the filler, and opening
otherwise. The comment above those literals names the source: PLC1 at
`bcfd1844d3f063850c69f2643f6a052bac03d8ec`, which is not in this repository, as quoted in
`data/phos-icssim-dev/roles.toml`.

ADR 0336 found the law page empty on every corpus run. Nothing in the tree checks whether the
hand copy is faithful. If a human mis-transcribed a comparison, every run since has been silent
for the wrong reason, and no test would say so.

H1 builds the derivation that would replace the copying, and checks it against the copy first.
Nothing in this record is a measurement. No corpus is opened. No detection claim is made.
v1 stays 8 of 12. P1 stays blocked.

## Decision

**A valve law is derived automatically from the pinned ICSSim controller source, and the bar is
that it equals `controller_valve` literal for literal. A derived law that disagrees is refused,
and `controller_valve` is not edited.**

### What the derivation reads, and nothing else

The pinned checkout at `bcfd1844d3f063850c69f2643f6a052bac03d8ec`, under `data/`, which git
never sees (ADR 0006, ADR 0122). Three files, with the digests `data/phos-icssim-dev/roles.toml`
already records:
<!-- evidence-ack: bcfd1844d3f063850c69f2643f6a052bac03d8ec — the pinned ICSSIM checkout's head under data/, not a commit in this repository -->

| File | sha256 |
|---|---|
| `src/PLC1.py` | `4651130bba9f137108c0426a6fdeb829db8705ea7eeedd40dfab378c9cf51316` |
| `src/Configs.py` | `242e19fe346550fc4614f3511d6eacd91c0dfadb3e9591fd616570352ad23bd3` |
| `src/ics_sim/Device.py` | `574660255d62e29e27015baaa797005071a11f14317af9525b6525258464ae92` |
<!-- evidence-ack: src/Configs.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

A digest that does not match at run time is a refusal of the run, not a warning. The derivation
reads those three files as source text. It does **not** import them, execute them, or start a
simulator. It does not read a corpus, a capture, a historian row, or `roles.toml` itself —
`roles.toml` is a hand-written artefact and using it would make the check circular.

ICSSim source is not copied into this repository. The derivation quotes the lines it used into
its report and into each certificate, which is a quotation of an MIT-licensed file, not a
vendoring of it.

### Which literal comes from where, declared before the run

This is written down now so the run cannot choose a provenance that makes the bar easier.

- `0.0` and `1.0` are the second argument of the `self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, …)`
  and `self._set(TAG.TAG_TANK_OUTPUT_VALVE_STATUS, …)` calls in `PLC1._logic`.
- `1.0` for the belt is the right-hand side of `belt_position > 1.0` in the same function.
- `3.0` is the `'default'` of `TAG_TANK_INPUT_VALVE_MODE` and of `TAG_TANK_OUTPUT_VALVE_MODE`
  in the `TAG_LIST` table of `Configs.py`. It is not in `PLC1.py`.
- The guard is `_check_manual_input` in `ics_sim/Device.py`, which forces the actuator off at
  mode `1`, on at mode `2`, and otherwise returns false so the comparison runs.

**The known disagreement risk, named in advance.** `Device.py` defines manual as mode `1` or
mode `2`. `controller_valve` defines release as mode exactly `3.0`. These are not the same
predicate: at mode `4.0` the derived form would run the comparison and the hand form would call
it unstated. A derivation that emits "mode is not 1 and not 2" has **not** produced the literal
`3.0`, so it does not meet the first bar, and the result is a refusal. It is not fixed by
widening `controller_valve`, and it is not fixed by hard-coding `3.0` into the derivation to
make the comparison pass. If that is what comes out, the verdict records it and the hand law
stays as written.

### The bars, not reworded

Each is met or not met. There is no partial credit and no tuning knob.

1. **Literal agreement.** The derived law's four constants are exactly `0.0`, `1.0`, `3.0` and
   `1.0`, for close, open, release mode and belt-past-filler respectively, each carrying the
   file and line it was read from.
2. **Comparison agreement, input side.** The derived input rule is: strictly above `level_max`
   writes close; otherwise strictly below `level_min` writes open; otherwise nothing is
   required. The `if` / `elif` order is the source's order. Both band ends are inside the band.
3. **Comparison agreement, output side.** The derived output rule is: strictly above
   `bottle_max` **or** strictly past the belt literal writes close; every other reading,
   including either equality, writes open.
4. **Guard agreement.** The derived law is stated only when both valve modes are the release
   literal, and is unstated otherwise.
5. **Equal decisions on every enumerated case.** The derived law and `controller_valve` return
   the same required value on a deterministic enumeration of controller samples that covers,
   for each side, the value below, the value equal to and the value above each threshold, and
   each mode in `{1.0, 2.0, 3.0}` on each of the two mode tags. Seed `20261029` for any ordering
   the enumeration needs; the enumeration itself is exhaustive over those cases, not sampled.
   One disagreeing case fails this bar.
6. **Certificate shape.** Every break the derived law produces carries the law, the rows it was
   evaluated on, and the comparison that came out false, so that a person holding the rows can
   recheck it without PHOS. A certificate has no field that can hold a confidence, a
   probability, a weight, a magnitude or a score, and its text is refused by the same score-word
   check that guards a placed sentence (ADR 0323). A certificate is not a `LawBreak` subclass:
   admission to the page stays `type(item) is LawBreak` (ADR 0322).
7. **The tree stays green.** `uv run pytest -q`, `uv run mypy --strict src` and
   `uv run ruff check` are clean, and `src/phos/atlas/declared_law.py` has an **empty diff**.

Bars 1 to 5 together are what "equals `controller_valve` literal for literal" means. Missing any
one of them is a refusal of the derivation, recorded in the verdict, with the hand law
untouched.

### The command

```
uv run python scripts/lane_h_code_laws.py --icssim data/icssim-source/repo
```

Run only after this record is in `HEAD`. The script does not exist when this record is written;
writing it is the H1 build, which is a different session.

- **Result name:** `code-law:valve-agreement`
- **Report path:** `eval_runs/build/lane-h/h1-code-law-agreement.md`
- **Verdict ADR:** 0371, written by an agent that did not build the derivation.

The report states, for each of the seven bars, met or not met, and quotes the source lines the
derivation read. It states no rate, no percentage and no score. It is not appended to
`eval_runs/log.jsonl`.

### What this rung does not do

It does not score a detection corpus, open a held-out corpus, read a red-tier corpus, or
generate an attack. It does not edit `src/phos/atlas/packet/`, `declared_law.py`,
`law_inlet.py`, the six law predicates, or any file a brief G lane owns under ADR 0344. It does
not move `controller_valve`'s literals (ADR 0368 Decision 6). It does not place a derived law on
the law page: H1 ends at agreement, and wiring a derived law into the register is a later
declaration. It does not open H2, H3 or H4, which ADR 0369 closed until after 6 January 2027.
It does not start Intelligence, an API, a UI, a socket or a TAP, and it does not unblock P1.

## Consequences

**Gained, whatever the result.** The only hand-copied law in the tree acquires a check. If the
derivation agrees, the copying has a mechanical replacement and H2 has a foundation. If it
disagrees, the tree learns that on a simulator whose source it can read, before a real plant's
program is ever involved, and the verdict names which of the seven bars failed.

**Cost, stated now so the verdict cannot overclaim.** The bar is agreement with a human's
transcription of one comparison in one Python program. A derivation that is wrong in exactly the
way the hand copy is wrong would meet every bar. That is a real limit of this rung and it is not
closed by H1; only a second independent reading, or a plant whose engineers confirm the rule,
would close it. Nothing in this rung says the derivation transfers to ladder logic, structured
text, or a vendor's binary format — ICSSim's controller is Python. Nothing in this rung is a
detection claim: the result is a simulated diagnosis, not a field rate (ADR 0073), and agreement
on a derivation says nothing about whether Atlas would catch any named attack.

## What would reverse this

Editing `controller_valve`, or its literals, to match a derived law. Hard-coding `3.0` into the
derivation rather than reading it from `TAG_LIST`. Reading `roles.toml` as a source, which makes
the check circular. Running the command before this record is in `HEAD`. Reporting a
partially-met bar as met. Putting a score-word, a confidence, a weight or a magnitude on a
certificate. Placing a derived law on the law page without its own declaration. Appending
`eval_runs/log.jsonl`. A second run of the same command to get a different answer: the first
result is the result, and a changed derivation is a new declaration.
