# ADR 0383 - The guard-form run is refused: six bars hold by construction, and all 4320 products still part

- **Status:** Accepted
- **Date:** 2026-10-30
- **PART:** Atlas, build brief H, rung H1. Verdict. Written by a session that did not build the
  guard type or the derivation
- **Supersedes:** nothing. [ADR 0382](0382-the-derived-valve-rule-is-the-candidate-and-a-guard-holds-both-shapes.md)
  is not edited, and neither are 0370, 0371, 0380
- **Depends on:** [ADR 0382](0382-the-derived-valve-rule-is-the-candidate-and-a-guard-holds-both-shapes.md),
  [ADR 0380](0380-the-valve-mode-tags-can-hold-a-value-outside-one-two-and-three.md),
  [ADR 0371](0371-code-laws-derived-from-the-controller-program-are-judged.md),
  [ADR 0370](0370-code-laws-are-derived-from-the-controller-program.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0382 was in `HEAD` at `ab4fba1`, `eval_runs/build/lane-h/h1-guard-form.md` did not exist,
and ADR number 0383 was free on every branch in this clone. The three files ADR 0370 pins were
digested on disk before the run and each matched:

| File | sha256 on disk |
|---|---|
| `src/PLC1.py` | `4651130bba9f137108c0426a6fdeb829db8705ea7eeedd40dfab378c9cf51316` |
| `src/Configs.py` | `242e19fe346550fc4614f3511d6eacd91c0dfadb3e9591fd616570352ad23bd3` |
| `src/ics_sim/Device.py` | `574660255d62e29e27015baaa797005071a11f14317af9525b6525258464ae92` |
<!-- evidence-ack: src/Configs.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/PLC1.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

The declared command was run once, after that commit:

```
uv run python scripts/lane_h_guard_form.py --icssim data/icssim-source/repo
```

Exit status 1. Result name `code-law:guard-form`. Report
[`eval_runs/build/lane-h/h1-guard-form.md`](../../eval_runs/build/lane-h/h1-guard-form.md),
4396 lines, 649311 bytes, committed with this record. It was not rerun. Nothing was tuned, no
bar was reworded, and `eval_runs/log.jsonl` was not appended. This is a derivation checked
against one hand transcription, not a measurement (ADR 0073). No corpus, capture or historian
file was opened. `controller_valve` was not edited and its literals did not move.

The tree was green before the run, measured by this session and not by the script:

| Gate | Result |
|---|---|
| `uv run pytest -q` | `4899 passed, 11 skipped, 85 deselected in 132.47s` |
| `uv run mypy --strict src` | `Success: no issues found in 276 source files` |
| `uv run ruff check` | `All checks passed!` |
| `git diff --quiet main -- src/phos/atlas/declared_law.py` | exit 0, **empty diff** |

The code under test, as judged: `source.py` `be14049c…c36a477d`, `parse.py`
`bfae2195…d32ac0d`, `law.py` `fce85ccf…75471638`, `derive.py` `3474e3c8…f11e47d`,
`certificate.py` `237f8537…161922d3`, `agreement.py` `7bcdf1ae…dadb2f25`, `report.py`
`4db42f11…0625743`, `scripts/lane_h_guard_form.py` `524b659b…7657d0ae`.

## Decision

**Refused. Every one of the seven bars is met, and rung H1 is still refused, because three of
those bars could not have come out otherwise on this source. The derived rule stays a
candidate. The refusal is not the one ADR 0382 hoped to earn: bars 3, 5 and 6 hold by
construction, so the bar set cannot demonstrate the replacement it was written to test.
`controller_valve` stays as written. Do not rerun the command, do not edit either law, and do
not build H2, H3 or H4 on the strength of this record.**

| # | Bar, as ADR 0382 words it | Result |
| --- | --- | --- |
| 1 | **Literal agreement, quoted from the source node.** The derived law's four constants are exactly `0.0`, `1.0`, `3.0` and `1.0`, for close, open, release mode and belt-past-filler respectively, each carrying the file and line it was read from. For every literal, the stored source text is the text of the source node at that citation, not a string rebuilt from the derived float. So close and open quote `0` and `1` as `PLC1.py` writes them, release mode quotes `3` as `Configs.py` writes it, and the belt quotes `1.0` as `PLC1.py` writes it. | The report prints `close 0.0 written 0 from src/PLC1.py:18; open 1.0 written 1 from src/PLC1.py:20; release_mode 3.0 written 3 from src/Configs.py:49; belt_past_filler 1.0 written 1.0 from src/PLC1.py:26`. Every citation was checked against the pinned source by hand: line 18 is `self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 0)`, line 20 is the same call with `1`, line 26 is `… or belt_position > 1.0`, and `Configs.py`:49 is `TAG_TANK_INPUT_VALVE_MODE: {… 'default': 3}`. The text is taken from the node by `number_text`, which is `ast.unparse`, and is not rebuilt from the float, so the column ADR 0371 found overstating is now honest: it reads `3`, not `3.0`. `TAG_TANK_OUTPUT_VALVE_MODE` at `Configs.py`:57 also defaults to `3`, and `derive.py` refuses if the two defaults disagree. **Met.** |
| 2 | **Comparison agreement on both sides.** Input: strictly above `level_max` writes close; otherwise strictly below `level_min` writes open; otherwise nothing is required. The `if` / `elif` order is the source's order. Both band ends are inside the band. Output: strictly above `bottle_max` **or** strictly past the belt literal writes close; every other reading, including either equality, writes open. | The report prints `above the maximum closes, below the minimum opens, the band is silence; full or past the filler closes, every other reading opens`, and the rule blocks `1. tank_level_value > tank_level_max → writes 0.0 (line 17)`, `2. tank_level_value < tank_level_min → writes 1.0 (line 19)`, `Otherwise: nothing is required, which is silence.` The output block reads `1. bottle_level_value > bottle_level_max or bottle_distance_to_filler_value > 1.0 → writes 0.0 (line 26)`, `Otherwise: writes 1.0.` `PLC1.py` lines 17 to 20 are an `if` on the maximum then an `elif` on the minimum with no `else`, and lines 26 to 29 are that `or` with an `else` writing `1`. The chain is walked in source order by `_branches`, the operators are read from the nodes, and both comparisons are strict. **Met.** |
| 3 | **Guard comparison is on the guard's form.** The derived guard is an exclusion list (stated when the mode is not in `{1.0, 2.0}`). The hand guard is an equality (stated when the mode equals `3.0`). The check that they differ, and the check that each is the shape named here, inspects that form. It does not answer by trying a hand-picked list of modes and seeing which ones fire. A form that can hold only an exclusion list cannot meet this bar, because it cannot represent the hand guard. | The report prints `derived form is exclusion of {1.0, 2.0}; hand form is equality at 3.0; forms differ`. `guard_from_device` reads the two `if mode == N` branches out of `_check_manual_input` and builds an `EXCLUSION`; `hand_guard` builds an `EQUALITY` at the release literal. `differs_in_form_from` is `self.form is not other.form` and `states_only` returns `False` for any exclusion without consulting a value, so neither answer depends on which modes anyone tried. `test_guard_form_cannot_be_answered_by_trying_modes` walks the whole mode set and gets the form's answer every time, and a hand guard built as an exclusion is shown to fail the bar. **Met, by construction.** See the reading below: this bar is met whatever the source says. |
| 4 | **Forced actuator writes at modes 1 and 2 are a stated fact.** The derived law reports that `_check_manual_input` writes the actuator to close (`0`) at mode `1.0` and to open (`1`) at mode `2.0`. That fact is present on the derived law. It is not dropped, and it is not folded into the comparison rule. The hand law remaining silent at those modes is not a defect of this bar. | The report prints `mode 1.0 writes 0.0 (0 at src/ics_sim/Device.py:409); mode 2.0 writes 1.0 (1 at src/ics_sim/Device.py:412)`. `Device.py` lines 408 to 413 are `if mode == 1: self._set(actuator_tag, 0); return True` then `elif mode == 2: self._set(actuator_tag, 1); return True`. `forced_writes_from_device` reads each `_set` inside a branch that returns `True`, takes the value's text from that call's node, and stores them on `law.forced_writes`, separate from `law.rules`: `required()` walks only the rule's branches and never consults the forced writes, so the fact is carried and not folded in. `test_dropping_the_forced_writes_fails_bar_4` shows the bar fails when they are absent. **Met.** |
| 5 | **Every disagreement on the extended enumeration is listed, with a certificate.** On the 8820 cases named above, every case where the two laws differ in standing or in sentences is listed. Each listed case carries a certificate naming the law, the rows it was evaluated on, and the comparison that came out false. When they differ on whether the law is stated, that comparison is the guard comparison that parted them. When they differ on the required actuator value, that comparison is the valve comparison that parted them. Omitting a disagreement fails this bar. Editing either law so the list is empty fails this bar. | The report prints `8820 cases on modes [0.0, 1.0, 2.0, 3.0, 3.3, 4.0, 100.0]; 4320 disagreements listed, each with a certificate`, and the file holds 4320 entries. The enumeration is the declared product, 5 levels × 3 bottle levels × 3 belt positions × 7 modes × 7 modes × 2 × 2, exhaustive and not sampled, and `_enumeration_bar` fails if the count or the mode set is not exactly that. The 4320 matches the declaration's own arithmetic for the 24 mode pairs with at least one tag outside `{1.0, 2.0}` and not both `3.0`, times 180. Every entry carries a `LawCertificate` built by `disagreement_certificate`, with the law named `controller_valve`, nine rows, and the guard comparison that parted them. There are no `actuator` entries: among the 180 cases where both laws speak, the two sentences coincide, which is the agreement ADR 0371 recorded. **Met.** |
| 6 | **Certificate shape.** A certificate has no field that can hold a confidence, a probability, a weight, a magnitude or a score, and its text is refused by the same score-word check that guards a placed sentence (ADR 0323). A certificate is not a `LawBreak` subclass: admission to the page stays `type(item) is LawBreak` (ADR 0322). | The report prints `154 certificates checked, each naming its rows and its false comparison`. `LawCertificate` carries `law_name`, `side`, `at`, `rows`, `required_because`, `comparison`, `required`, `actual` and `statement`, and no field name folds to a score word; `test_no_guard_field_can_hold_a_score` and the field walk in `_certificate_bar` check the dataclasses rather than trusting them. Neither `LawCertificate` nor `Disagreement` inherits from `LawBreak`, the check asserts that, and every break it inspects is exactly a `LawBreak` and was admitted by `law_page`. The statement is built by `cited_statement`, which refuses the five words in any case. **Met, with the text gap recorded below.** |
| 7 | **The tree stays green.** `uv run pytest -q`, `uv run mypy --strict src` and `uv run ruff check` are clean, and `src/phos/atlas/declared_law.py` has an **empty diff**. | Row 7 of the report says `not computed here: the suite, mypy --strict src, ruff and an empty diff on declared_law.py are reported by the session that runs them`. This session ran all four, before the run and again after it. `uv run pytest -q`: `4899 passed, 11 skipped, 85 deselected in 132.47s`, exit status 0. `uv run mypy --strict src`: `Success: no issues found in 276 source files`. `uv run ruff check`: `All checks passed!`. `git diff --quiet main -- src/phos/atlas/declared_law.py` exited 0. The reporting script also writes the report and derives the law in the same process, so the artifact does not exist until a result does; that coupling is noted below and does not change this row. **Met, by this session, not by the report.** |

Bar 7 is met. Every bar the report computes at all is met. **The step is still refused**, and the
reason is not a missed measurement.

### Why a step whose bars all pass is refused

The script's overall standing is `not met` because its own row 7 says it cannot answer for
itself. That is honest, and this record is the session that answered it. Taken bar by bar, the
law that came out meets all seven as ADR 0382 words them. What a reader should not conclude from
that is that the candidate earned its case. Three of these bars could not have come out
otherwise on this source, and one could not have come out otherwise on any source.

**Bar 3 is a statement about the code, not about the plant.** It asks that the two guard shapes
be representable and inspected as forms. The derived guard is an exclusion because
`_check_manual_input` is written as two equalities that fall through; the hand guard is an
equality because `_MODE_RELEASE` is a constant. `differs_in_form_from` compares two enum members.
Any source with that guard shape, and any hand law written as an equality, meets this bar. It is
a real improvement on ADR 0371, where `DerivedGuard` could hold only one shape and the comparison
was impossible. It is not evidence that the two laws now agree, and it is the reason bar 5 has
something honest to list.

**Bar 5 is met by the gap it lists, not by agreement.** The declaration's own split says 4320
cases are the live gap. The run lists 4320. A bar that reads "list every disagreement" is met by
an accurate list, and an accurate list of a total disagreement is met trivially. To their credit
the builders refused the cheap way out: `_enumeration_bar` fails when the list is empty, so
editing either law to agree would have failed the bar rather than passed it, and
`test_dropping_a_disagreement_fails_bar_5` pins that. The result is a well-formed record of a
parting that ADR 0380 made live, not a demonstration that the derived rule replaces the hand one.

**Bar 6 cannot be observed to fail on this source.** The 154 certificates checked are the breaks
the derived law produces where both laws speak, and none of them represents a disagreement,
because the two sentences coincide there. The bar's field and inheritance checks are real and
pinned by tests, but its text check has a gap that is only visible by reading the code: the
`comparison` and `required_because` strings are rendered by f-strings and are never passed
through `cited_statement`, and the bar's own scan of those two fields tests a literal tuple
rather than calling `_score_word`. The derived law cannot currently emit a score word, so no
certificate is wrong today. The bar is recorded met on what was checked, and the mechanism is
named so a successor does not read it as enforced.

**Bar 7 does not make the report reproducible.** The reporting script derives the law, computes
the bars and writes the artifact in one process, so the artifact only appears once the run has
succeeded. That is why the pre-flight cannot have it both ways on the same commit, and it is a
process fact this record states rather than a defect it fixes.

### The old ADR 0370 run cannot be reproduced from `HEAD`

**The builder rewrote `derive.py`, `agreement.py` and `report.py` in place, and also `parse.py`,
`law.py` and `certificate.py`.** Seven of the eight code-law modules changed between `4e3f25a`
and `ab4fba1`; only `source.py` is byte-identical. The digests ADR 0371 recorded for `parse.py`,
`law.py`, `derive.py`, `certificate.py`, `agreement.py` and `report.py` no longer exist anywhere
in `HEAD`, and `scripts/lane_h_code_laws.py` changed too, by one docstring line.

So the report ADR 0371 committed at `eval_runs/build/lane-h/h1-code-law-agreement.md` describes a
challenger that is not in this tree. Re-running its command against `HEAD` would exercise
different code and could write a different report, and the rule that the first result is the
result (ADR 0370, ADR 0371) applies to that command as it was declared. **Do not rerun it.** The
old report stands as the record of what that code did on 29 October 2026; it is not a
reproduction recipe for anything in `HEAD`. ADR 0382 declared this run as a new command with its
own result name and report path, which is the honest way to change a derivation, and that is
what the five-phase cycle exists to require.

### The two guards are still opposite in the direction that matters

Restating the parting in the source's own terms, because the count alone hides it. The derived
rule follows `_check_manual_input`: the comparison runs unless a mode is `1` or `2`, so an
unexpected mode such as `3.3` or `4.0` is treated as automatic. The hand rule follows the tag
table's default: the comparison runs only at exactly `3.0`, so every mode other than `3.0` is
treated as manual, including the `3.3` ADR 0380 showed a man-in-the-middle rewrite produces and
including `4.0`, which ADR 0370 named as the place they part. On the one mode this plant reaches
by accident, the derived rule **checks the valve and the hand rule is silent**. A plant whose
valve is left wrong at `3.3` is seen by one of them and not the other. That is the whole
argument for the derived rule, and this run neither makes it nor settles it.

## What this result does not show

It is not a detection claim. It produces no rate, no recall, no coverage figure and no field
number. Agreement on a derivation says nothing about whether Atlas would catch any named
departure, and ADR 0336's empty law page is untouched.

Nothing here transfers to a vendor PLC. ICSSim's controller is Python, and reading a Python file
with `ast` is not reading an IEC 61131-3 program. A vendor PLC may reject an out-of-range mode in
firmware, in which case the gap this record lists cannot arise on it.

It does not show that the derived rule is better, only that it is different, and the difference
is named above. A derivation wrong in exactly the way the controller program is wrong would meet
every bar, which ADR 0370 said in advance and this result does not close. A second independent
reading, or a plant whose engineers confirm the rule, would close it. Neither exists.

It does not place a derived law on the law page, and it does not replace `controller_valve`.
Keeping the derived rule as a candidate is not a verdict that says kept.

It does not open H2, H3 or H4, which stay closed until after 6 January 2027 or until a later
record opens them (ADR 0369). It does not start Intelligence, an API, a UI, a socket or a TAP,
and it does not unblock P1.

## Consequences

**Gained.** A guard type now holds an exclusion list and an equality in one place and compares
them by form, which was ADR 0371's named precondition for comparing the two guards at all. The
forced writes at modes 1 and 2 are a stated fact on the derived law rather than a dropped
half of `_check_manual_input`. The literal column quotes the source node for all four literals,
closing the overstatement ADR 0371 recorded. The extended enumeration includes the reachable
`3.3`, so the parting is recorded on a value a plant can produce.

**What the run cost, stated plainly.** 4320 of 8820 cases disagree, all of them on standing. The
extended mode set did not narrow the gap; it measured it. A step whose purpose was to replace a
hand copy with the controller's own logic now has its bars all passing and its substance
unmoved, which is the exact failure mode `docs/rules/live-work.md` warns about: claiming a step
is done without the record supporting it. The record says refused, and the reason is in this
paragraph.

**What stays as it was.** `controller_valve` and its four literals. H1's refusal under ADR 0371.
ADR 0370, 0371, 0380 and 0382, unedited. The six laws stay six. v1 stays 8 of 12. P1 stays
blocked. H2, H3 and H4 stay closed. The old report at `h1-code-law-agreement.md` stays as the
record of code that is no longer in the tree.

**What a successor needs.** A new declaration, not a rerun of either command. The open question
is not "does the guard type hold both shapes" but "which rule does PHOS keep, and on what
evidence". ADR 0380 stated the source fact and refused to pick. This record will not pick either.
A plant's engineers confirming the rule is the evidence that would, and that is a conversation,
not a harness.

## What would reverse this

Editing `controller_valve`, or its four literals. Hard-coding `3.0` into `derive.py` or
`parse.py`. Rerunning `scripts/lane_h_guard_form.py` to get a different answer. Rerunning
`scripts/lane_h_code_laws.py` against ADR 0370, whose code is not in `HEAD`. Reporting a
partially-met bar as met, or reporting bar 7 as answered by the report when it was answered by
this session. Reading bars 3, 5 or 6 as evidence that the candidate earned its case rather than
as bars that could not fail here. Restoring the old code-law bytes to make the ADR 0371 report
reproducible, which would silently change what the ADR 0382 run measured. Putting a score-word,
a confidence, a weight or a magnitude on a certificate. Placing the derived law on the law page
without a verdict that says kept. Appending `eval_runs/log.jsonl`. Opening H2, H3 or H4 on the
strength of this record. Quoting 8820, 4320, 180 or 154 as a detection figure, a rate or a score.
