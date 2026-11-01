# ADR 0382 — The derived valve rule is the candidate, a guard holds both shapes, and they are compared on an extended mode set

- **Status:** Accepted
- **Date:** 2026-10-30
- **PART:** Atlas, build brief H, rung H1. Declaration. No code exists
- **Supersedes:** nothing. [ADR 0370](0370-code-laws-are-derived-from-the-controller-program.md),
  [ADR 0371](0371-code-laws-derived-from-the-controller-program-are-judged.md) and
  [ADR 0380](0380-the-valve-mode-tags-can-hold-a-value-outside-one-two-and-three.md)
  stand unedited. H1's refusal is not reversed. This record replaces no law
- **Depends on:** [ADR 0371](0371-code-laws-derived-from-the-controller-program-are-judged.md),
  [ADR 0380](0380-the-valve-mode-tags-can-hold-a-value-outside-one-two-and-three.md),
  [ADR 0370](0370-code-laws-are-derived-from-the-controller-program.md),
  [ADR 0369](0369-h1-runs-now-and-the-later-rungs-wait-for-the-bid.md),
  [ADR 0368](0368-triangulation-and-a-self-search-are-named-after-brief-g.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0322](0322-a-slot-enters-only-as-a-law-break.md),
  [ADR 0321](0321-the-controller-comparison-is-true-or-false.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0371 refused H1 on bar 4. The law derived from PLC1 states the valve comparison at every
mode except `1.0` and `2.0`, because that is what `_check_manual_input` in
`src/ics_sim/Device.py` lines 404 to 414 does. `controller_valve` in
`src/phos/atlas/declared_law.py` states the comparison only at mode `3.0`. The two agree at
modes 1, 2 and 3 and part everywhere else.
<!-- evidence-ack: src/ics_sim/Device.py — AlirezaDehlaghi/ICSSIM's own layout in the pinned checkout under data/, not a path in this repository -->

ADR 0380 showed the gap is live: a mode outside `{1, 2, 3}` is reachable on the pinned ICSSim
checkout. An operator's `3` becomes `3.3` under the checkout's own man-in-the-middle rewrite.
Nothing below the operator console's prompt enforces the domain.

Elijah has decided the direction: **adopt the derived rule as the candidate**, because it is
the controller's own logic, and because reading laws out of code is the method that could
transfer to a real plant. That decision is recorded here, before any code that would carry it
exists. It does not keep the derived law. It does not edit `controller_valve`. It does not
rewrite ADR 0371 or ADR 0380.

ADR 0371 also recorded two limits of the current derivation that this declaration names as
bars, so they cannot be dropped in silence:

- `DerivedGuard` can only hold an exclusion list, so it cannot represent the hand guard
  (equals `3.0`) and cannot compare the two forms except by trying values.
- `_check_manual_input` forces the actuator to `0` at mode 1 and to `1` at mode 2. The
  derivation reads only the fall-through that lets the comparison run, and drops the forced
  writes.

Nothing in this record is a measurement. No corpus is opened. No detection claim is made.
v1 stays 8 of 12. P1 stays blocked. H2, H3 and H4 stay closed until after 6 January 2027, or
until a later record opens them (ADR 0369).

## Decision

**A guard type that holds both an exclusion list and an equality can represent the derived
guard (not in `{1.0, 2.0}`) and the hand guard (equals `3.0`), so the two can be compared on
a domain that includes modes outside `{1, 2, 3}`. The derived rule becomes the candidate
replacement for `controller_valve`. It replaces nothing until a later verdict ADR says
kept.**

The four literals of `controller_valve` are not moved. `controller_valve` itself is not
edited. `3.0` is not typed into `src/phos/atlas/code_law/derive.py` or `parse.py`. The
release literal continues to be read from `Configs.TAG_LIST`, as ADR 0370 required.

### The extended enumeration, computed here so the run cannot choose a smaller set

ADR 0370's mode set was `{1.0, 2.0, 3.0}` on each of the two mode tags. This record extends
it. The process-value grid is unchanged: five tank levels (below the minimum, equal to the
minimum, inside the band, equal to the maximum, above the maximum), three bottle levels
(below, equal, above the bottle maximum), three belt positions (below, equal, above the
filler literal), and both values of each valve.

The mode set on each tag is:

```
{0.0, 1.0, 2.0, 3.0, 3.3, 4.0, 100.0}
```

- `0.0` is below the console range.
- `1.0` and `2.0` are the modes `_check_manual_input` names.
- `3.0` is the tag-table default and the hand law's equality.
- `3.3` is the value ADR 0380 showed the MITM rewrite produces from an operator's `3`.
- `4.0` is the integer ADR 0370 named as the place the two laws part.
- `100.0` is a value well above the console range. It is a stand-in for any such value, not a
  plant constant and not a score.

Seven modes on the input tag, seven on the output tag. The product is:

```
5 levels × 3 bottle levels × 3 belt positions × 7 input modes × 7 output modes
  × 2 input valves × 2 output valves
= 8820 cases
```

That product is exhaustive over the declared grid, not sampled. Seed `20261030` for any
ordering the enumeration needs. One omitted case, or one extra mode that this record did not
name used in place of one it did, fails the enumeration bar.

Of those 8820, arithmetic on the declared sets (not a run) splits them as:

| Kind of mode pair | Pairs | Cases (× 180) |
|---|---|---|
| Both tags at `3.0` | 1 | 180 |
| Both tags outside `{1.0, 2.0}`, and not both `3.0` | 24 | 4320 |
| At least one tag in `{1.0, 2.0}` | 24 | 4320 |

The 180 are the cases on which both laws decide. The 4320 with a manual tag are agreement in
silence, which this record does not treat as agreement on a decision. The remaining 4320 are
the live gap: the derived guard states the comparison and the hand guard does not. The run
lists those disagreements. It does not close them by editing either law.

### The bars, not reworded

Each is met or not met. There is no partial credit and no tuning knob.

1. **Literal agreement, quoted from the source node.** The derived law's four constants are
   exactly `0.0`, `1.0`, `3.0` and `1.0`, for close, open, release mode and belt-past-filler
   respectively, each carrying the file and line it was read from. For every literal, the
   stored source text is the text of the source node at that citation, not a string rebuilt
   from the derived float. So close and open quote `0` and `1` as `PLC1.py` writes them,
   release mode quotes `3` as `Configs.py` writes it, and the belt quotes `1.0` as `PLC1.py`
   writes it.
2. **Comparison agreement on both sides.** Input: strictly above `level_max` writes close;
   otherwise strictly below `level_min` writes open; otherwise nothing is required. The
   `if` / `elif` order is the source's order. Both band ends are inside the band. Output:
   strictly above `bottle_max` **or** strictly past the belt literal writes close; every
   other reading, including either equality, writes open.
3. **Guard comparison is on the guard's form.** The derived guard is an exclusion list
   (stated when the mode is not in `{1.0, 2.0}`). The hand guard is an equality (stated when
   the mode equals `3.0`). The check that they differ, and the check that each is the shape
   named here, inspects that form. It does not answer by trying a hand-picked list of modes
   and seeing which ones fire. A form that can hold only an exclusion list cannot meet this
   bar, because it cannot represent the hand guard.
4. **Forced actuator writes at modes 1 and 2 are a stated fact.** The derived law reports
   that `_check_manual_input` writes the actuator to close (`0`) at mode `1.0` and to open
   (`1`) at mode `2.0`. That fact is present on the derived law. It is not dropped, and it
   is not folded into the comparison rule. The hand law remaining silent at those modes is
   not a defect of this bar.
5. **Every disagreement on the extended enumeration is listed, with a certificate.** On the
   8820 cases named above, every case where the two laws differ in standing or in sentences
   is listed. Each listed case carries a certificate naming the law, the rows it was
   evaluated on, and the comparison that came out false. When they differ on whether the
   law is stated, that comparison is the guard comparison that parted them. When they differ
   on the required actuator value, that comparison is the valve comparison that parted them.
   Omitting a disagreement fails this bar. Editing either law so the list is empty fails
   this bar.
6. **Certificate shape.** A certificate has no field that can hold a confidence, a
   probability, a weight, a magnitude or a score, and its text is refused by the same
   score-word check that guards a placed sentence (ADR 0323). A certificate is not a
   `LawBreak` subclass: admission to the page stays `type(item) is LawBreak` (ADR 0322).
7. **The tree stays green.** `uv run pytest -q`, `uv run mypy --strict src` and
   `uv run ruff check` are clean, and `src/phos/atlas/declared_law.py` has an **empty
   diff**.

Missing any one of them is a refusal of this step, recorded in the verdict. `controller_valve`
stays as written. The derived rule stays a candidate.

### The command

```
uv run python scripts/lane_h_guard_form.py --icssim data/icssim-source/repo
```

Run only after this record is in `HEAD`. The script does not exist when this record is
written; writing it is the next session's build, not this one. Do not rerun
`scripts/lane_h_code_laws.py` against ADR 0370. That look is spent (ADR 0371).

- **Result name:** `code-law:guard-form`
- **Report path:** `eval_runs/build/lane-h/h1-guard-form.md`
- **Verdict ADR:** 0383, written by an agent that did not build the guard type.

The report states, for each of the seven bars, met or not met, and quotes the source lines
the derivation read. It lists every disagreement. It states no rate, no percentage and no
score. It is not appended to `eval_runs/log.jsonl`. It is run once. A second run of the same
command to get a different answer is not this declaration: the first result is the result,
and a changed derivation is a new declaration.

The three files ADR 0370 pinned remain the files this run may read, as text, never imported,
never executed, with the same digests. A digest that does not match is a refusal of the run.
`roles.toml` is not a source.

### What this result will not show

It is not a detection claim. It produces no rate, no recall, no coverage figure and no
field number. Agreement on a derivation still says nothing about whether Atlas would catch
any named departure, and ADR 0336's empty law page is untouched.

Nothing here transfers to a vendor PLC. A vendor PLC may reject an out-of-range mode in
firmware. ICSSim's controller is Python, and reading a Python file with `ast` is not reading
an IEC 61131-3 program.

Agreement in silence is not agreement on a decision. The 4320 cases that carry a mode of
`1.0` or `2.0` on at least one tag are both laws unstated. They do not confirm the candidate.

Keeping the derived rule as a candidate is not placing it on the law page, and not replacing
`controller_valve`. Wiring it into the register needs a verdict that says kept, and then its
own placement declaration.

### What this rung does not do

It does not score a detection corpus, open a held-out corpus, read a red-tier corpus, or
generate an attack. It does not edit `src/phos/atlas/packet/`, `declared_law.py`,
`law_inlet.py`, the six law predicates, or any file a brief G lane owns under ADR 0344. It
does not move `controller_valve`'s literals. It does not open H2, H3 or H4. It does not
start Intelligence, an API, a UI, a socket or a TAP, and it does not unblock P1.

## Consequences

**Gained, whatever the result.** The adoption decision is on disk before the type exists, so
the run cannot choose the hand rule to make a bar easier. The two guard shapes can be named
in the same type, which is the limit ADR 0371 said a successor had to close before the forms
could be compared. The enumeration includes the reachable value ADR 0380 named.

**Cost, stated now so the verdict cannot overclaim.** A candidate is not a replacement. H1
stays refused. The six laws stay six. A derivation that is wrong in exactly the way the
controller program is wrong would still meet every bar that only asks about that program.
That limit was named in ADR 0370 and is not closed here.

## What would reverse this

Editing `controller_valve`, or its four literals. Hard-coding `3.0` into `derive.py` or
`parse.py`. Rewriting ADR 0371 or ADR 0380, or reading this record as a reversal of H1's
refusal. Answering the guard bar by trying a hand-picked mode list. Dropping the forced
writes at modes 1 and 2. Running `scripts/lane_h_code_laws.py` against ADR 0370 again.
Running the command named here before this record is in `HEAD`. Reporting a partially-met
bar as met. Putting a score-word, a confidence, a weight or a magnitude on a certificate.
Placing the derived law on the law page without a verdict that says kept. Appending
`eval_runs/log.jsonl`. Opening H2, H3 or H4 on the strength of this record. Quoting 8820,
4320, 180, `3.3` or `100.0` as a detection figure, a rate or a score.
