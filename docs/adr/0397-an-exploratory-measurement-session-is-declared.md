# ADR 0397 — An exploratory measurement session is declared, and both halves of it are named

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** Exploratory. Atlas measurement, and build brief G's execution
- **Supersedes:** nothing. It opens no lane that another record already owns, and it edits no
  frozen knob
- **Depends on:** [ADR 0286](0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md),
  [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md),
  [ADR 0316](0316-the-joint-command-vector-is-declared.md),
  [ADR 0122](0122-a-phos-generated-icssim-corpus.md)

## Context

The last four measurement programmes ended in refusals, not wins: VAR on HAI was louder (ADR 0064),
the 6B autopsy found no exclusive stem (ADR 0065), the correlation target could not invert
(ADR 0066), and the operator queue could not be ranked (ADR 0068). Build brief E closed without
reaching the stronger engine (ADR 0297). The H1 code-law lane has now been refused twice
(ADRs 0371, 0383).

On 1 November 2026 Elijah asked for something narrower than another programme: **a session of
heavy thinking and iteration, to see whether the measurements could be pushed, and to see the
results.** Not a promise that they will be. Curiosity, declared as such, with the discipline intact.

He also asked that the session establish whether Atlas can understand the protocols plants
actually speak, rather than Modbus alone, because that is the difference between an engine that can
be handed to a European plant and one that cannot.

Both halves are in scope. They are independent and produce no shared result.

## Decision

1. **This is an exploratory session with no success criterion attached to discovery.** A refusal is
   the expected outcome and is a result. Nothing here may be reported as a detection claim, a field
   rate, or a capability. The session reports what it measured, including what it could not measure.

2. **Half A: push an existing measurement, and pick the one with the sharpest known blocker.** The
   session takes **lane 3's accumulator**, already built as `src/phos/atlas/drift_consistency.py`
   and already refused, and asks one question: is the delay failure recorded in ADR 0286 a property
   of the *statistic* or of the *alert-placement rule it was fed through*?

   The reason for this choice, stated before anything runs. Lane 3 is the strongest result the
   programme has produced and the only one that lost on a technicality it did not control:
   `liar_freeze` **1 of 10 → 10 of 10**, attacks **32 of 70 → 53 of 70**, nothing lost, benign only
   5 of 20 → 8 of 20 — and it failed because a saturated accumulator becomes its group's `best` and
   `level` pins at `ONSET_LEVEL`, which **disqualifies a weak member episode from placing its own
   earlier alert**. That is ADR 0286's finding, and it says explicitly: *"It is not a refutation of
   accumulation."*

   The question is therefore not "can we catch more" — it already does. It is **whether the two
   halves can be separated by changing where the alert is placed, without touching the statistic,
   the budget, the threshold, or any frozen name.**

3. **Half A does not edit the frozen engine.** `phos.atlas.consistency` is not modified. The
   published `budget_alerts`, `events`, `THRESHOLD`, `ONSET_LEVEL`, `ONSET_FRACTION`,
   `ALERTS_PER_SHIFT`, `SHIFT_SECONDS` and the detrend window stay exactly as they are. Any
   alternative placement rule is a **new function beside** the existing one, on a new result name,
   and the existing row must still reproduce unchanged. Lane 3's own development report is the
   comparison and is not rewritten.

4. **Half A's bar, frozen here before any run.** On `phos-icssim-dev2` (development tier,
   iterate-freely under `docs/rules/data-tiers.md`), with lane 3's statistic at its module default:

   - **Attacks caught within eight alerts a shift: strictly more than 32 of 70.** Not "no worse" —
     the frozen engine's count is the floor and a tie is not progress.
   - **No attack the frozen engine catches is lost.** The paired set may not shrink.
   - **Median detection delay over the paired set: no worse than the frozen engine's 1 s**, under
     both the paired and the own-set readings. The brief does not pin which definition, so both are
     reported and **both must hold**. This is the half that failed before.
   - **Benign events drawing an alert: no higher than 5 of 20.** The frozen engine's figure is the
     ceiling; 8 of 20 was lane 3's cost and is not acceptable at any recall.

   All four halves together, or the lane is refused again and the refusal is written up. A partial
   win is a refusal, in the same voice as a refusal.

5. **Half A may not buy delay with catches or catches with false alerts.** The lane 3 dial is
   recorded in ADR 0286 and on no setting does it pass. A new placement rule that reproduces that
   trade is not a discovery and must not be reported as one. If the only way to pass is to weaken a
   half, the session writes the refusal and stops.

6. **Half B: execute build brief G's declared protocol lanes.** ADR 0344 named nine protocols ahead
   of a partner's capture and brief G exists to build them, but **every one of its verdict ADRs is
   still `Reserved`** — 0347, 0348, 0349, 0350, 0351, 0352, 0353, 0354, 0355, 0356, 0357, 0358,
   0359, 0360, 0364, 0365, 0366, 0367 — and `src/phos/atlas/packet/` contains **one** dissector,
   `modbus.py`. The programme has been declared and not executed.

   The nine, in the order brief G ranks them, are S7comm, DNP3, IEC 60870-5-104, EtherNet/IP,
   OPC UA, IEC 61850, S7comm-plus, Profinet and BACnet. Each keeps brief G's rule unchanged: **its
   own declaration ADR is committed before a byte of that protocol is parsed**, and the dissector
   matches or exceeds `modbus.py`'s discipline — check before reading, cap before allocating, refuse
   rather than raise, with no `try` block making that true, and its own seeded fuzz corpus held to
   the same four claims.

7. **Half B's standard is honest coverage, not a protocol count.** Brief G already says what
   "understand" means and this record does not soften it: *read what a passive capture can honestly
   expose; where the bytes are encrypted or integrity-protected, read the conversation's shape —
   who, when, how much, which visible message types — and refuse the rest. Do not claim parity with
   Modbus where the bytes do not allow it.* A dissector that says `unreadable` for OPC UA's secured
   payloads is correct, and a dissector that guesses is a failure however many protocols it adds.

   The bar for each lane, frozen here: it decodes its protocol's unsecured application data unit on
   a capture it did not author; it refuses every malformed frame as a named `MalformedFrame` and
   raises on none; it caps before allocating; and it reports which fields a passive capture cannot
   see rather than back-filling them. **A protocol whose bar is not met is recorded as refused, and
   that is a result.** Nothing is claimed by adding a file.

8. **Neither half opens a red-tier or held-out corpus.** `phos-icssim-dev`, `dev2`, `dev3`, `dev4`,
   `dev5` and `dtu-lab` are development. `phos-icssim-heldout`, `heldout2`, `heldout3`, `heldout4`,
   `heldout4-walk`, `heldout5`, the HAI editions other than the already-spent exceptions, BATADAL,
   and T1's seed sets are **not opened**. Half A is development-only and its result, if kept, would
   need a separate held-out declaration later; nothing in this record authorises one.

9. **Nothing frozen moves, and nothing is appended.** `eval_runs/log.jsonl` is not appended. The
   frozen rows — ungated distillation Mahalanobis **18.72**, HAI **646.58**, grouped **53.26**, CERT
   6B **0.104**, `:precision` **0.083**, command lead **0 of 16** and **1 of 4** — are not read,
   recomputed or overwritten. `controller_valve`, `_shrink`, `joint_k`, `dwell_samples`,
   `OPERATOR_PAGE_CEILING`, the 300-second event window and the 720-step walk are untouched. No
   template, prior or `EVIDENCE_STRENGTH` changes.

10. **Protocol acts still meet the law inlet only through a declaration.** ADR 0361 is `Reserved`
    and ADR 0362 judges it; this record does not fill either. A dissected message is a message, not
    a program act, and a function code is still not a download, an upload or an online edit
    (`refuse_function_code` stands).

## What would reverse this

Reporting a half as a win because the other half moved; passing on one delay definition while
failing the other; buying recall with false alerts or delay with lost catches; editing
`phos.atlas.consistency` or any frozen constant to make a result land; claiming protocol coverage
from a file count rather than a measured decode on a capture the lane did not author; treating an
encrypted protocol's visible envelope as parity with Modbus; opening a held-out corpus; appending
`eval_runs/log.jsonl`; or calling this session a detection claim, a field result, or a promise that
the measurements can be pushed.
