# ADR 0041 — Input-hostile report must not overwrite detection

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle leftover — close the named 04–07 robustness gap without overwriting detection
- **Supersedes:** nothing
- **Amends:** nothing. [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md)
  already splits detection from robustness as *claims*. This record pins the *files*.
- **Depends on:** [ADR 0016](0016-the-graded-attack-library-flavour-separation-and-the-anti-fingerprint-discipline.md),
  [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
  [ADR 0039](0039-ranking-contract-lock-undoing-0036-0038-must-turn-existing-tests-red.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md)

## Context

Hostile configs 04–07 exist. They are software-survival cases, not plant attacks:

| Config | Corpus role |
|---|---|
| `configs/attacks/04-hostile-poisoned-baseline.toml` | poisoned baseline |
| `configs/attacks/05-hostile-malformed-records.toml` | malformed records |
| `configs/attacks/06-hostile-out-of-range.toml` | out-of-range values |
| `configs/attacks/07-hostile-truncated.toml` | truncated file |

Both breaking reports still print `_No input-hostile corpora were measured._`
(`eval_runs/breaking/breaking-report.md`, and the issuer-split copies). That line is honest.
ADR 0017's caveat still applies: a crash is a defect; a loud refusal is correct behaviour;
`COMPLETED` is only safe if the untouched holdout did not shift. Passing those cases is not
security. `INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT` still travels with the flavour.

The detection file is where the frozen D2 maps live. Scored apart, not pooled, not the cycle
contract:

| Issuer kind | Unique led | Moved | n | ADR |
|---| ---: | ---: | ---: | --- |
| Known-station (`scada` / `hmi`) | **0** | 6 | 16 | 0038 / 0039 |
| Unknown-master (silent `engineering`) | **1** | 4 | 4 | 0038 / 0039 |

The **1 of 4** is a D2 diagnostic with `ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. Session 4
forbade running 04–07 as the *headline*. Session 5 (ADR 0040) did not measure them either.
The gap is named. It is closable without cheating a contract. Closing it must not erase the
file that holds the maps.

Today `write_report` always writes `eval_runs/breaking/breaking-report.md`. `--output-stem`
copies *after* that write. A hostile-only regeneration assembled into the same object would
replace the canonical detection report with a document whose maps, FP/hour rows, and command
tables are empty. That is how a named robustness gap becomes a detection-history defect.

This record is the rule **even before, and while, the CLI lands**. Implementation may follow.
The file contract does not wait for it.

## Decision

**Measuring input-hostile corpora 04–07 must write a separate report stem.** The two files are
`eval_runs/breaking/input-hostile-robustness.md` and
`eval_runs/breaking/input-hostile-robustness.json`. They must never overwrite
`eval_runs/breaking/breaking-report.md` (or `.json`). It must never overwrite the issuer-split
detection copies (`breaking-report-known-station`, `breaking-report-unknown-master`).

A hostile-only run that cannot honour that split must refuse to write, not fall through to the
detection path. A combined run that still emits one `BreakingReport` object is not licence to
replace the detection file with a robustness-only body.

The detection file remains the home of the breaking-point maps and of known-station **0/16**
and unknown-master **1/4**. Robustness numbers live only under the robustness stem. They are
not copied into a lead-rate cell, a breaking-point row, or a pooled "led in n of m".

## Options considered

**(a) Append robustness into the same file as detection.** Rejected. The renderer already has
a separate *section*. That is not a separate *artifact*. A hostile-only regeneration would
drop the detection sections (empty `clean_map`, empty `command_results`) and still write
`breaking-report.md`. Frozen 0/16 and 1/4 would vanish from the canonical path. ADR 0017's
"reported separately" would be true in prose and false on disk.

**(b) Separate stem — `input-hostile-robustness.md` / `.json`.** Accepted. Two claims, two
files, same directory. A later engineer can regenerate robustness without touching detection,
and can read detection without meeting a software-survival table that looks like a new map.

**(c) Skip measuring 04–07 forever.** Rejected. The reports already name the gap. The configs
already exist. Flavour separation (ADR 0016) already makes a hostile case unscorable as a
missed detection. Measuring them is closable without weakening known-link indistinguishability,
without pooling issuer kinds, and without quoting a robustness pass as ≥70%. Leaving the gap
open forever would treat a file-overwrite risk as if it were a scientific prohibition.

## What this does not earn

Closing the named robustness gap, on a separate stem, does **not** earn:

- live sites, a plant TAP, or a partner deployment;
- the ≥70% command-lead cycle contract (still unearned; D2 0/16 and 1/4 are not that
  contract, and 04–07 cannot become its denominator);
- 2–3 Atlas pages/day on any public process type;
- calibrated hypothesis confidence, or permission to surface it.

It does not earn FastAPI, sockets in `src/phos`, or L1 shadow as a running system. L1 TAP
work stays **conversation-only**: a written I/O-edge design is allowed; plugging a TAP is
not. Category lock is unchanged.

## Consequences

**Gained.** Robustness can be measured without destroying the detection history. The overwrite
path is named before the CLI changes, so a later implementation has a test to fail rather than
a file to discover missing.

**Cost.** Two artifacts must be kept current. A reader who opens only `breaking-report.md`
will still see "no input-hostile corpora were measured" until a robustness run writes the
other stem. That line in the detection file must not be "fixed" by merging the tables.

**Still true, and not relaxed by a green robustness row:**

- `INPUT_HOSTILE_IS_NOT_SECURITY_CAVEAT` remains. Passing 04–07 is not product security. It
  is software survival on rubbish we wrote, against a model of a plant, with no live attack
  surface and no adversary who did not read this file.
- Hostile results never enter a lead rate or the breaking-point map. They have no
  `attack_intervals` (ADR 0016). There is no route that should grow 0/16 or 1/4.
- No FastAPI. No listener. L1 TAP remains conversation-only.

**Rejected:** using `--output-stem` as sufficient protection while the canonical write still
clobbers `breaking-report.md`; folding a robustness table into section 6 of a detection
regeneration and calling the claims separate; quoting a `COMPLETED` hostile case as detection
recall; running 04–07 as the cycle headline (ADR 0039).

## When to revisit

When a robustness run has actually written `input-hostile-robustness.md` / `.json` without
touching the detection stem, the detection file's "no input-hostile corpora were measured"
line may be cross-referenced to that stem. It is not deleted in favour of a merged table.

Do not revisit in order to put robustness numbers into the command-lead cells, to declare
product security, to stand up FastAPI, or to treat a TAP conversation as L1 running. A new
public command-labelled row is still ADR 0040's revisit condition, not this one's.

## Landed (same day)

`write_report(..., stem=...)` and `scripts/evaluate_breaking_points.py --hostile-only` write
`eval_runs/breaking/input-hostile-robustness.md` / `.json` and do not write `breaking-report.md`.
Seed-7 verdicts: malformed **REFUSED** (`ParserError`); out-of-range, poisoned baseline, and
truncated **COMPLETED**; none **CRASHED**. Poisoned baseline holdout out-of-band shift **0.1342**.
Detection reports still print `_No input-hostile corpora were measured._` That line is now a
cross-reference to the robustness stem, not a claim that 04–07 were never run. This landing
does not earn live sites, ≥70%, 2–3 pages/day, or product security.
