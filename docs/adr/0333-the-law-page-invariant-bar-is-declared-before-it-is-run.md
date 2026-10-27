# ADR 0333 — The law-page invariant bar is declared before it is run

- **Status:** Accepted
- **Date:** 2026-10-26
- **PART:** Atlas, the law-page inlet. `docs/zero-to-one-master-plan.md` Q1, section 4, "Replay"
- **Supersedes:** nothing
- **Depends on:** [ADR 0325](0325-the-law-page-inlet-is-a-named-map.md),
  [ADR 0326](0326-a-score-word-is-not-placed-and-an-unchecked-law-stays-listed.md),
  [ADR 0323](0323-every-sentence-names-the-law-it-came-from.md),
  [ADR 0324](0324-the-operating-plan-loads-in-both-tools.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0325 named the map from plant-supplied rows onto the arguments `assess_plant`
already takes. `inlet_from_tables` is in `src/phos/atlas/law_inlet.py` and its tests
construct their own rows. That record reserved the result name `law-inlet:invariants`,
named `phos-icssim-dev` as the corpus, and refused to authorise the run. This is that
separate declaration. It names the command and freezes the bar. It produces no number.

Where the record stands. v1 is 8 of 12 (ADR 0264): met A1, A2, A4, A5, A6, C1, S1, S2;
open A3, A7, S3, C2. `current_session` is P1, a blocked human conversation. The six laws
and the ceiling 8 are as ADR 0317–0323 left them. `OPERATOR_PAGE_CEILING` is the integer
8 from `docs/v1-roadmap.md` section 2.0 and is not touched here. The frozen rows — ungated
Mahalanobis 18.72 FP/hour, HAI transfer 646.58, CERT 6B 0.104 at 48 — are not read, not
recomputed and not overwritten by this record or by the run it declares.

Which clock this is on. `docs/zero-to-one-master-plan.md` section 3 keeps two clocks that
do not share a result. This is the **law clock**. The residual clock's outstanding declared
score is ADR 0316's joint command vector on `phos-icssim-dev5`; that corpus is not generated
here, that command is not run here, and its result, whenever a session on that clock takes
it, does not order `law_page` and does not become a law.

What the run is for. Section 4 of the plan calls the law page's stress bar invariant: the
run exercises the structural refusals on a development corpus and reports counts. It is not
a detection measurement. No recall, no false-alarm rate, no latency and no magnitude is
produced, and none may be read out of it afterwards.

Which seeds. The corpus is the already-declared development half. Its runs are fixed in
`scripts/icssim/generate_corpus.py` under `RUNS["development"]` by ADR 0122, extended by
ADR 0285: three `normal` runs at seeds 96001, 96002, 96003 and ten `mixed` runs at seeds
96011 through 96020, thirteen runs in all. `docs/rules/data-tiers.md` lists
`phos-icssim-dev` under iterate-freely. **No held-back seeds are used and no new seed block
is registered.** `phos-icssim-heldout`, `heldout2`, `heldout3`, `heldout4`, `heldout4-walk`
and `heldout5` stay unopened. The HAI editions and BATADAL are not read.

What the issuer is, concretely. `allowed_writer` is membership in a set the plant wrote.
The station string is a field the caller supplies; `inlet_from_tables` does not derive it
from a Modbus function code, and a function code offered as a program act is refused. This
record does not revive the frozen command-lead figures — known-station 0 of 16 and
unknown-master 1 of 4 stay apart, unpooled and unquoted.

## Decision

**The eight structural invariants in section 4 of the operating plan are the bar for
`law-inlet:invariants`, on `phos-icssim-dev`, and they are written here before the harness
that measures them exists.**

- **Code under test:** `src/phos/atlas/declared_law.py`, `src/phos/atlas/law_inlet.py`,
  `src/phos/atlas/packet/messages.py`, `src/phos/atlas/packet/modbus.py`. The law module
  imports none of `consistency.py`, `command_consistency.py`, `walk_consistency.py`,
  `drift_consistency.py`, `bending_consistency.py`, `breadth_consistency.py`, `queue.py`,
  `grouping.py`, `shift_brief.py`, `handoff_page.py` or `leap_stack.py`, and the run does
  not import them either.
- **sha256, per file:**

  | sha256 | File |
  | --- | --- |
  | `65501ba758da0f21e23c1a0c8669f09f744756ac6a4b4cc9c2c92fb7d84134d2` | `src/phos/atlas/declared_law.py` |
  | `6db2d6dd848974e4773b476b86061941744215a3535bbd72b2612031a1188c63` | `src/phos/atlas/law_inlet.py` |
  | `7cc2a6705a74a5b5fafc4b5e6394ecd3631859fda266c46e7b0f0aecb6de7127` | `src/phos/atlas/packet/messages.py` |
  | `b6ab88cc835c37f633070e194448bce1273b202846f8cd3f823368bd6920f888` | `src/phos/atlas/packet/modbus.py` |

- **sha256, combined:** `45b966642feea7ed9acc209fec80dc25c25303c76e88e9b477b7552b0d7fd12e`.
  The four paths are taken in lexicographic order and **each path string is mixed in before
  that file's bytes**, so a rename is a different set. `src/phos/eval/trusted_station.py`'s
  `challenger_sha256()` covers that lane and not this one, which is why the digests here are
  stated per file and recomputed the same way at score time. This record is never in its own
  digest set.
- **Tree:** `4dac107749531c1f9319af2a5d543bc9403b225a`.
- **Corpus:** `data/phos-icssim-dev`, generated by
  `python scripts/icssim/generate_corpus.py development`. Thirteen runs, seeds as named in
  Context. The payload is not committed. `data/phos-icssim-dev/roles.toml` is the committed
  part and is read from ICSSim's own pinned source, never inferred from the data.
- **Inlet arguments for the run:** `setpoint_tags` is the six tags `roles.toml` marks
  `setpoint` — `tank_input_valve_mode`, `tank_level_min`, `tank_level_max`,
  `tank_output_valve_mode`, `conveyor_belt_engine_mode`, `bottle_level_max`.
  `controller_tags` is `PLC1_CONTROLLER_TAGS`, the ten-field map already quoted in
  `law_inlet.py`. `allowed_stations` is the set the run's register names; where the run
  passes the empty set, `allowed_writer` is unstated and that is not a break.
- **Command:** `uv run python scripts/lane_law_inlet_invariants.py --corpus data/phos-icssim-dev`
- **Result name:** `law-inlet:invariants`
- **Report path:** `eval_runs/build/lane-law-inlet/invariants.md`

### The script does not exist at this commit

`scripts/lane_law_inlet_invariants.py` is not in the tree at `4dac107`. It is written after
this record is in HEAD and before the run, under the same discipline as `modbus.py`: check
before read, cap before allocate, refuse rather than raise. Writing it may not change any of
the four files whose digests are above, and may not change a bar below. If building it shows
that an invariant as worded cannot be checked, the run does not happen and a verdict ADR says
which one and why. Naming the command here is what stops the bar moving to meet a number.

### Bars, not reworded

Each is a count over the whole corpus and each is met or not met. There is no tolerance and
no per-run exemption.

1. Placed sentences that do not begin with their law's name, a period and a space: **0**.
2. Placed sentences containing the word confidence, probability, weight, magnitude or score:
   **0**. The refusal is the word. A decimal the plant already uses is not a score-word.
3. Pages whose length exceeds `OPERATOR_PAGE_CEILING`: **0**.
4. Reports in which some law name in the register appears in more than one of held, broken
   and unstated, or in none of the three: **0**.
5. Reports with nine or more breaks whose placed page is not exactly the eight earliest by
   time, then by law name: **0**. The ninth break in time is absent, including when a person
   would have called it severe.
6. `LawBreak` subclass instances admitted to a page: **0**. Admission is
   `type(item) is LawBreak`, and a subclass is refused before the page is ordered.
7. Inlets built from a frame the dissector refused: **0**. A malformed frame becomes a
   `MalformedFrame`; `inlet_from_tables` raises on a non-empty `malformed` and returns no
   inlet, so no `LawBreak` can descend from one.
8. Empty-register reports returning anything other than three empty lists: **0**.

### Reported beside the bars, and not a bar

The run also reports the number of runs scored, the number of pages built, the distribution
of page lengths, and how many of the eight slots ordinary operation fills. Those are counts
for the verdict to quote. None of them is a threshold here, and none may be restated as a
detection rate, a false-alarm rate or a queue-ranking result.

### The fallback, declared now

**If ordinary operation fills the eight slots, the queue is unstaffable on this corpus, the
predicates stay exactly as written, and the verdict ADR says so.** That outcome is a result,
not a failure to produce one. It does not license retuning a predicate, widening an admission
rule, raising the ceiling, or adding a seventh law. The ceiling 8 moves only when a partner
names a different integer in a new record. `controller_valve`'s literals — close 0.0, open
1.0, release mode 3.0, belt past the filler 1.0 — are ICSSim's PLC1 numbers and are not
retuned onto another plant.

### What a break is, restated

Only a broken law is a `LawBreak`, and only that list enters the page. Held has no timestamp
and takes no slot. Unstated is the plant having named a law and supplied nothing that law can
be checked against; it is recorded once and is not dropped. **A break is a false law, not an
attack.** The page does not name the cause. An empty page is not a safe plant.

## Consequences

**Gained.** The bar for `law-inlet:invariants` is frozen before the harness that measures it
exists, so neither the invariant list nor the corpus can be adjusted to suit a count. The
corpus, the seeds, the four digests and the command are on the record, so the run is
reproducible and a second run under a different command is visibly a different thing. The
fallback is declared, so an unstaffable page is already a stateable result.

**Cost.** This record contains no number. It opens no capture and no historian file, generates
no corpus and scores none. `eval_runs/log.jsonl` is not appended, here or by the run.
`phos-icssim-dev` is not opened in this record. Held-out stays unopened. The residual files
stay on disk, unedited and unimported. ADR 0316 stays the residual clock's outstanding score
and is not run here.

v1 stays **8 of 12**, with A3, A7, S3 and C2 open. This declaration moves no criterion; the
invariant counts, when they exist, are structural and judge none of the four. The frozen
measurements stay frozen and unpooled. Results from the synthetic harness are a simulated
diagnosis and not a field rate (ADR 0073), and no claim from this run may say the plant map
improves detection on real plant data (ADR 0143). No Intelligence, API, UI or TAP is started.
P1 remains a blocked human conversation, and this record does not unblock it.

**Before this reaches `main`.** ADR 0044 counts a decision record as an advancement, so the
merge that carries this one also moves `encyclopedia/`, `easy to reads/` and `README.md`. That
has not been done in this commit.
