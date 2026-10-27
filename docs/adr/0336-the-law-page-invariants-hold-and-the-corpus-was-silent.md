# ADR 0336: the law-page invariants hold, and the corpus was silent

- **Date:** 27 October 2026
- **Status:** accepted
- **PART:** Atlas, the law-page inlet. `docs/zero-to-one-master-plan.md` Q1, section 4, "Replay"
- **Judges:** [ADR 0335](0335-the-invariant-bar-is-redeclared-over-the-fixed-score-word-refusal.md),
  whose eight bars are [ADR 0333](0333-the-law-page-invariant-bar-is-declared-before-it-is-run.md)'s
  bars unchanged
- **Depends on:** [ADR 0329](0329-the-score-word-refusal-covers-the-fact-not-the-law-name.md),
  [ADR 0325](0325-the-law-page-inlet-is-a-named-map.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

ADR 0335 declared `law-inlet:invariants` over the merged tree, pinned four files by sha256, fixed the
command, the result name and the report path, and declared eight counts each of which is met at 0 or
not met. It also declared a fallback in advance: if ordinary operation fills the eight slots, the
queue is unstaffable on this corpus and the predicates stay exactly as written.

The corpus did not exist on disk when that record was written. `data/phos-icssim-dev/` held only its
committed `roles.toml`. It was generated on 27 October 2026 by
`scripts/icssim/generate_corpus.py setup` and then `development`, which clones ICSSIM at the pinned
commit `bcfd1844d3f063850c69f2643f6a052bac03d8ec` — that commit is not in this
repository — and produces thirteen runs: three `normal` at seeds
96001 to 96003 and ten `mixed` at seeds 96011 to 96020. The payload is gitignored and is not
committed. `roles.toml` was already in the tree and did not change.

Before the run, the four digests were recomputed by the method ADR 0333 defined, which the harness
does not do itself. They reproduce the record exactly, combined
`098b20c1731b502225b2fbe112c979dfa987d3b58870707d5dcf0ba8542044bc`. The declared tree was scored.

## Decision

**Kept. All eight bars are met at 0. The declared fallback does not apply, because ordinary operation
produced no breaks at all.**

The command was run once, as declared:

```
uv run python scripts/lane_law_inlet_invariants.py --corpus data/phos-icssim-dev
```

Its last line reads `law-inlet:invariants: all eight met = True`. The report is at
`eval_runs/build/lane-law-inlet/invariants.md`. `eval_runs/log.jsonl` was not appended.

### The eight bars, as declared and as measured

| Bar | Declared | Measured | Met |
| --- | --- | --- | --- |
| 1 placed sentence does not name its law | 0 | 0 | yes |
| 2 placed sentence carries a score-word | 0 | 0 | yes |
| 3 page longer than the ceiling | 0 | 0 | yes |
| 4 register name not in exactly one list | 0 | 0 | yes |
| 5 page is not the earliest eight | 0 | 0 | yes |
| 6 `LawBreak` subclass admitted | 0 | 0 | yes |
| 7 inlet built from a refused frame | 0 | 0 | yes |
| 8 empty register not three empty lists | 0 | 0 | yes |

### Reported beside the bars, and not a bar

Thirteen runs scored. Thirty-nine inlets built. Fifty-two pages. One hundred and four placed
sentences. Stations the plant named: `operator`, `plc1`, `plc2`. Ceiling 8. Page lengths: thirty-nine
of length 0 and thirteen of length 8. Reports with more breaks than the ceiling: thirteen. Malformed
frames offered to the inlet and refused: three.

None of these is a detection rate, a false-alarm rate, a recall, a latency or a magnitude, and none
may be restated as one.

## The finding that changes how the result reads

**The plant never broke a declared law. Every one of the thirty-nine corpus-derived pages is empty.**

The thirteen pages of length 8, and the thirteen reports with more breaks than the ceiling, are not
the plant. They are the constructed probe: `_score_run` builds, once per run, a
`LawReport` whose `broken` is `probe_breaks(register, at)`, which is `PROBE_BREAKS = 12` breaks one
second apart on that run's own clock. Twelve exceeds the ceiling by four, so each of those thirteen
reports is counted over-ceiling and each page truncates to exactly 8. ADR 0335 anticipated this for
bar 5 and said so: the probe exists "because ordinary rows need not produce a ninth break."

So the fallback does not fire. Ordinary operation did not fill the eight slots; it filled none of
them. The queue was not shown to be unstaffable on this corpus. It was shown to be empty on this
corpus, which is a different sentence and a weaker one.

**Bars 1 and 2 got no exercise from the corpus.** All one hundred and four placed sentences are the
probe's, exactly thirteen pages of eight. Thirty-nine empty pages place no sentences, so the two
sentence-level bars, including the score-word refusal that ADR 0329 had just fixed and that this
whole re-declaration existed to put under test, were counted entirely over constructed input. Bar 3
likewise never saw a corpus page that could have exceeded the ceiling.

**Bar 4 is the one bar the corpus genuinely exercised.** Thirty-nine real assessments partitioned the
six-law register, and the partition held in every one. Two shapes recur: `held 3 broken 0 unstated 3`
where the historian carried rows, and `held 0 broken 0 unstated 6` where the inlet was built from the
controller tags alone and had no series to assess. Both are legitimate partitions and both were
checked independently of the function under test.

**A documentation defect in the harness, recorded and not fixed here.** The report's own caveat says
"Bars 1 to 4 are counted over corpus-built pages. Bar 5 is counted over corpus pages and over a
constructed twelve-break page per run." That under-describes itself: `_check_report` tallies bars 1
to 5 over every report it is given, which is the three corpus inlets and the one constructed probe
per run. No count moves either way, since all are 0. But a reader of the report alone would conclude
the one hundred and four sentences came from the plant, and they did not. The harness is not among
the four files ADR 0335 pinned, so correcting that sentence does not disturb the digest set; it is
left for a separate change rather than edited after the run it describes.

The report also names ADR 0333 as the declaring record, because that string is in the script rather
than in the pinned code. The bars are identical, so the attribution is right about what was measured
and stale about which record pins the tree. Same treatment: recorded, not edited after the fact.

## What this result is, and what it is not

It is evidence that the law page upholds its eight invariants under the input it was given: the
sentence form, the score-word refusal, the ceiling, the three-way partition, the earliest-eight
ordering, the subclass refusal, the refused-frame guard and the empty-register shape. The ordering
and truncation guarantees were tested at twelve breaks, which is the case that matters, and they
held.

It is not evidence that the plant is safe. An empty page is not a safe plant. It is not a detection
claim, a recall, or a false-alarm rate. It does not score the residual detector, and it does not
order the law page relative to it. It says nothing about any plant other than this simulation, and
synthetic results are a simulated diagnosis rather than a field rate (ADR 0073).

It is also not evidence that the score-word refusal works on plant-derived sentences, because there
were none. That is the gap this run leaves, and naming it is the point of writing the verdict rather
than quoting the eight zeros.

## Consequences

**Kept.** `law-inlet:invariants` is met on `phos-icssim-dev`. Q1 engineering stops at
`inlet_from_tables`, as ADR 0325 and the operating plan have it. Nothing is retuned: no predicate, no
admission rule, no ceiling, no seventh law, no literal in `controller_valve`.

**The corpus is silent, and that is now a known property of it.** A later record that wants the
sentence-level bars exercised on plant-derived breaks needs a corpus in which a declared law is
actually broken, declared as its own step with its own bar. This record does not open that, does not
name a corpus for it, and does not authorise generating one.

**The command is spent.** Do not rerun it on `phos-icssim-dev`. A second run that reported the same
eight zeros would add nothing, and a second run that reported different ones would mean the corpus or
the tree moved, which is a different record.

**Cost.** One number produced, and a fair reading of it is narrower than the eight zeros suggest. The
honest summary is two sentences rather than one: the invariants hold, and the corpus did not test the
two bars this re-declaration was written for.

## Refused

Restating the thirteen over-ceiling reports or the thirteen full pages as the plant filling an
operator's shift. Restating the thirty-nine empty pages as a low false-alarm rate, a quiet plant, or
a safe plant. Quoting any count here as a recall, a precision, a latency or a magnitude. Rerunning
the command and reporting the better result. Moving a bar, in this record or a successor, so that a
count can be met. Retuning a predicate, widening an admission rule, raising `OPERATOR_PAGE_CEILING`
or adding a seventh law because the corpus was silent. Opening a held-out split, or reading a
red-tier corpus, because the development corpus produced no breaks. Treating a kept invariant bar as
a detection result, a ship authorisation, or a reason to start Intelligence, an API, a UI or a TAP.
P1 stays a blocked human conversation.
