# ADR 0371 — The derived valve law agrees on the literals and the comparisons, and is refused on the guard

- **Status:** Accepted
- **Date:** 2026-10-29
- **PART:** Atlas, build brief H, rung H1. Verdict. Written by an agent that did not build the
  derivation
- **Supersedes:** nothing
- **Depends on:** [ADR 0370](0370-code-laws-are-derived-from-the-controller-program.md),
  [ADR 0369](0369-h1-runs-now-and-the-later-rungs-wait-for-the-bid.md),
  [ADR 0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md)

## Context

ADR 0370 declared rung H1 before any code existed. The derivation was built by a different
session in commit `4e3f25a` on `build/h-triangulation`. This record is the verdict, and the
session that writes it did not write that commit.

ADR 0370 was in `HEAD` before the command ran. `eval_runs/build/lane-h/` did not exist, so the
one look was unspent. The command was run once:

```
uv run python scripts/lane_h_code_laws.py --icssim data/icssim-source/repo
```

Result name `code-law:valve-agreement`. Exit status 1. Report:
`eval_runs/build/lane-h/h1-code-law-agreement.md`, committed with this record. It was not run a
second time, the derivation was not edited, and nothing was tuned. `eval_runs/log.jsonl` was not
appended. No corpus, capture or historian file was opened. `controller_valve` was not edited and
its literals did not move. This is a derivation checked against one hand transcription, not a
measurement (ADR 0073).

The three declared files were digested on disk before the run and each matched the digest
ADR 0370 records: `src/PLC1.py` `4651130b…f51316`, `src/Configs.py` `242e19fe…d23bd3`,
`src/ics_sim/Device.py` `57466025…64ae92`. The code under test, as judged:
`src/phos/atlas/code_law/source.py` `be14049c…c36a477d`, `parse.py` `371164cf…42ed9b91`,
`law.py` `1228ab66…c2e5c359c`, `derive.py` `8ef26c33…081f00d4`, `certificate.py`
`18ef2302…2da9d68111`, `agreement.py` `c5828b47…0a413fd4a6`, `report.py` `efcae691…b130c4571a`,
`scripts/lane_h_code_laws.py` `f82f58aa…d813cd`.
<!-- evidence-ack: src/Configs.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

## Decision

**Refused. Six of the seven bars are met. Bar 4 is not met, in exactly the way ADR 0370 named
in advance, and ADR 0370 says missing any one bar is a refusal of the derivation. Do not rerun
the command, do not edit `controller_valve`, and do not hard-code the release literal to rescue
the bar.**

| # | Bar, as ADR 0370 words it | Result |
| --- | --- | --- |
| 1 | **Literal agreement.** The four constants are exactly `0.0`, `1.0`, `3.0` and `1.0`, each carrying the file and the line it was read from. | The report prints `close 0.0 from src/PLC1.py:18; open 1.0 from src/PLC1.py:20; release_mode 3.0 from src/Configs.py:49; belt_past_filler 1.0 from src/PLC1.py:26`. Every citation was checked against the pinned source by hand: line 18 is `self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 0)`, line 20 is the same call with `1`, line 26 is `… or belt_position > 1.0`, and `Configs.py`:49 is `TAG_TANK_INPUT_VALVE_MODE: {… 'default': 3}`. `TAG_TANK_OUTPUT_VALVE_MODE` at line 57 also defaults to `3`, so the two the derivation requires to agree do agree. **Met.** |
| 2 | **Comparison agreement, input side.** Strictly above `level_max` writes close; otherwise strictly below `level_min` writes open; otherwise nothing is required. The `if` / `elif` order is the source's order. Both band ends are inside the band. | The report prints `above the maximum closes, below the minimum opens, the band is silence`, and the rule block `1. tank_level_value > tank_level_max → writes 0.0 (line 17)`, `2. tank_level_value < tank_level_min → writes 1.0 (line 19)`, `Otherwise: nothing is required, which is silence.` `PLC1.py` lines 17–20 are an `if` on the maximum then an `elif` on the minimum with no `else`, so the order is the source's and both comparisons are strict. **Met.** |
| 3 | **Comparison agreement, output side.** Strictly above `bottle_max` **or** strictly past the belt literal writes close; every other reading, including either equality, writes open. | The report prints `full or past the filler closes, every other reading opens`, and `1. bottle_level_value > bottle_level_max or bottle_distance_to_filler_value > 1.0 → writes 0.0 (line 26)`, `Otherwise: writes 1.0.` `PLC1.py` lines 26–29 are that `or` with an `else` that writes `1`. Both comparisons are strict, so either equality opens. **Met.** |
| 4 | **Guard agreement.** The derived law is stated only when both valve modes are the release literal, and is unstated otherwise. | The report prints `the source states the comparison whenever a mode is not manual, and src/ics_sim/Device.py:404 names only 1.0, 2.0 as manual, so the stated set is wider than the single release literal 3.0`. `Device.py` lines 404–414 are `_check_manual_input`, returning true at mode `1` and mode `2` and false otherwise. The derived law therefore states the comparison at every mode except 1 and 2; `controller_valve` states it only at `3.0`. **Not met.** |
| 5 | **Equal decisions on every enumerated case.** The derived law and `controller_valve` return the same required value on a deterministic enumeration covering, for each side, the value below, equal to and above each threshold, and each mode in `{1.0, 2.0, 3.0}` on each mode tag. One disagreeing case fails this bar. | The report prints `1620 cases, none parted`, and the list of cases that parted is `- none`. The enumeration is 5 levels × 3 bottle levels × 3 belt positions × 3 input modes × 3 output modes × 2 input valves × 2 output valves = 1620, which is the declared case set exactly and is exhaustive over it, not sampled. **Met.** See the reading below for what that agreement covers. |
| 6 | **Certificate shape.** Every break carries the law, the rows it was evaluated on, and the comparison that came out false. A certificate has no field that can hold a confidence, a probability, a weight, a magnitude or a score, its text is refused by the same score-word check as a placed sentence (ADR 0323), and it is not a `LawBreak` subclass: admission stays `type(item) is LawBreak` (ADR 0322). | The report prints `126 certificates checked, each naming its rows and its false comparison`. Independent arithmetic over the enumeration reaches the same 126: 36 input-side breaks and 90 output-side breaks among the stated cases. `LawCertificate` does not inherit from `LawBreak`, carries `law_name`, `side`, `at`, `rows`, `required_because`, `comparison`, `required`, `actual` and `statement`, and has no field whose name could hold a score word; every break is exactly a `LawBreak` and was admitted to the page. **Met.** |
| 7 | **The tree stays green.** `uv run pytest -q`, `uv run mypy --strict src` and `uv run ruff check` are clean, and `src/phos/atlas/declared_law.py` has an **empty diff**. | Row 7 of the report says `not computed here`, which is the module declining to assert about itself rather than a finding. This session ran the four commands. `uv run pytest -q`: `4879 passed, 11 skipped, 85 deselected in 168.62s (0:02:48)`, exit status 0. `uv run mypy --strict src`: `Success: no issues found in 276 source files`. `uv run ruff check`: `All checks passed!`. `git diff --quiet origin/main -- src/phos/atlas/declared_law.py` exited 0. **Met.** |

Bars 1 to 5 together are what ADR 0370 means by "equals `controller_valve` literal for literal".
Bar 4 is one of them, so the derivation does not equal the hand law, and the result is a
refusal. The hand law is left exactly as it was written.

## What the refusal is, and what it is not

**It is the divergence ADR 0370 named before the code existed.** That record wrote: "A
derivation that emits 'mode is not 1 and not 2' has **not** produced the literal `3.0`, so it
does not meet the first bar, and the result is a refusal. It is not fixed by widening
`controller_valve`, and it is not fixed by hard-coding `3.0` into the derivation to make the
comparison pass." That is what came out. The derivation reads `_check_manual_input` and reports
what it says.

**It is not a defect in the build.** The builder had a cheap way to make bar 4 pass — type the
release literal into the guard, or compare the derived guard against the three modes anyone
would think to try. Neither was done. `DerivedGuard.states_only` answers the bar from the
guard's *form*, so the answer does not depend on which modes the enumeration happens to hold,
and `agreement.py` reports the bar not met. The release literal is read from `Configs.TAG_LIST`,
not written into `derive.py`: no `3.0` appears in `derive.py` or `parse.py` at all.

**It is not the hand law being wrong, and not the derivation being wrong.** The two sentences
are both faithful to something. `controller_valve` is faithful to the mode the plant's tag
table defaults to. The derivation is faithful to the function the controller actually calls.
They agree at modes 1, 2 and 3 and part at 4 and above. ADR 0370 forbids closing that gap by
moving either one, and this record does not.

## Three readings a later session should not have to re-derive

**What bar 5's "1620 cases, none parted" covers.** Of those 1620 cases, 1440 have a mode of 1
or 2 on at least one tag. On every one of those both laws are unstated — the derived law
because the guard calls the valve manual, the hand law because the mode is not `3.0` — so the
agreement there is agreement in silence, not agreement on a decision. The 180 cases with both
modes at `3.0` are the ones where either law says anything, and 126 of those produced a break
on which the two laws wrote identical sentences. The bar is met exactly as ADR 0370 words it,
because `{1.0, 2.0, 3.0}` is the mode set that record declared. It is worth stating plainly
that mode `4.0`, where the two laws are known to part, is outside the declared enumeration by
construction: bar 5 could not have caught the divergence, and bar 4 is the bar that does.

**One column of the report overstates for one row.** The literal table's heading is "As the
source writes it". For `close` and `open` that column is read from the source's own node and
reads `0` and `1`, which is what `PLC1.py` writes. For `release_mode` and `belt_past_filler` it
is reconstructed from the derived float instead, so it prints `3.0` where `Configs.py`:49 writes
`3`. The belt row coincides, because the source writes `1.0` there. The value, the file and the
line are right in every row, which is what bar 1 asks for, so the bar is met; but in a
programme about transcription fidelity, a column that claims to quote the source and does not
should be read with that in mind, and a successor should take `literal_text` from the node for
every literal.

**The derivation reads half of what the guard does.** `_check_manual_input` does two things: it
forces the actuator to `0` at mode 1 and to `1` at mode 2, and it returns false otherwise so
the comparison runs. The derivation reads the second half and discards the first, so its law is
silent at modes 1 and 2, where the source is in fact deterministic. No bar in ADR 0370 asks for
the manual writes, so no bar fails on this, and the hand law is silent there too. It is a real
piece of the controller's behaviour that the derived law does not carry, and a later rung that
wants the derivation to stand on its own rather than beside the hand law will have to read it.

A fourth, smaller note: because `DerivedGuard` can only represent an exclusion list,
`states_only` is a constant false for every law this module can build. That is the honest answer
for this source, and it is why bar 4 is reported from the form rather than from trials. It also
means the class, as written, could not report guard agreement for a source whose guard were
shaped as an equality. A successor that meets bar 4 needs a guard type that can hold both
shapes.

## The builder's claims, checked

The build session reported 4879 passed, 11 skipped, 85 deselected, `mypy --strict` clean over
658 files, `ruff` clean, and an empty diff on `declared_law.py`. Each was re-run here.
`uv run pytest -q` printed `4879 passed, 11 skipped, 85 deselected in 168.62s (0:02:48)` and exited 0, which is the claimed count exactly. `mypy --strict src tests scripts` is clean over 658 source files, which is
the scope that count comes from; the scope bar 7 words is `mypy --strict src`, which is clean
over 276. Both are clean, so the bar is met and the difference is scope, not a discrepancy in
the result. `ruff check` printed `All checks passed!`. `declared_law.py` has an empty diff
against `origin/main`, and so do `src/phos/atlas/packet/` and `law_inlet.py`. No file brief G
owns was touched. Nothing was added to `eval_runs/log.jsonl`.

## What this result does and does not establish

**Established.** On the pinned ICSSim checkout, a valve law can be read out of the controller's
own program without running it: three files are read as text, each refused unless its sha256
matches, and `ast.parse` builds a tree that is never executed. `roles.toml` was not read, so the
check is not circular. The four literals, the input comparison, the output comparison and every
decision on the declared enumeration came out the same as the hand copy. On those four of the
five agreement bars, the hand transcription of October is confirmed by a machine that never
saw it. The one place it is not confirmed is the guard, and that place was predicted in advance.

**Not established.** This is agreement with one person's transcription of one comparison in one
Python control program. A derivation that was wrong in exactly the way the hand copy is wrong
would have met every bar; ADR 0370 said so before the run and this result does not close that.
Nothing here is a detection claim. No corpus was scored, no held-out corpus was opened, no
attack was generated, and no rate, recall, percentage or coverage figure exists for this rung —
agreement on a derivation says nothing about whether Atlas would catch any named departure, and
ADR 0336's finding that the law page is empty on every corpus run is untouched. Nothing here
transfers to ladder logic, to structured text, or to a vendor's binary format: ICSSim's
controller is Python, and reading a Python file with `ast` is not reading an IEC 61131-3
program. No derived law was placed on the law page; H1 ends at agreement, and wiring one into
the register needs its own declaration. The six laws stay six. v1 stays 8 of 12. P1 stays
blocked.

## Consequences

The only hand-copied law in the tree now has a check, and the check found something. H2's
foundation is a derivation that is right about the literals and the comparisons and wrong about
the guard, which is a more useful starting point than an untested agreement would have been: a
successor knows which one line to fix and knows that fixing it means a guard type that holds
both shapes, not a literal typed in by hand.

H2, H3 and H4 stay closed until after 6 January 2027, or until a later record opens them
(ADR 0369). Reaching that date is not a declaration. ADR 0378 and note 158 stay reserved for
the programme close, which this record is not: H1 has a verdict, and the close needs the other
rungs either judged or explicitly left closed.

## What would reverse this

Editing `controller_valve`, or its literals, to match the derived law. Hard-coding `3.0` into
the derivation. Widening the hand law's release test to the derived guard's exclusion list.
Reading `roles.toml` as a source. Rerunning the declared command to get a different answer — the
first result is the result, and a changed derivation is a new declaration with a new report path.
Reporting bar 4 as met, or this verdict as anything other than refused. Restating "1620 cases,
none parted" as a coverage figure, a rate or a score. Placing a derived law on the law page
without its own declaration. Opening H2, H3 or H4 on the strength of this record.
