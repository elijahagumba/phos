# ADR 0068 — The Atlas operator queue cannot be ranked by any severity it carries

- **Status:** Accepted
- **Date:** 2026-08-26
- **PART:** Build 1 (operator queue)
- **Supersedes:** nothing
- **Depends on:** [ADR 0051](0051-saturated-fp-load-is-a-refused-claim.md),
  [ADR 0060](0060-sentiel-clock-a-routing-and-cert-curve.md),
  [ADR 0065](0065-cert-6b-queue-autopsy-no-exclusive-stem.md)

## Context

`atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events` on HAI is a frozen public row:
**53.26** false positives per normal hour, window recall 1.00, 424 alerts. That is a *rate*, and
a rate describes an experience nobody had measured. The same run leaves **424 subsystem events
over 7.89 normal hours** — one shift — of which **6** overlap a labelled attack window under the
vertical's own overlap-aware rule. An operator reading that queue front to back reads 424 things
to find 6.

Sentiel has had the right shape since Session S4: `phos.sentiel.cert_curve` reports recall against
a ticket budget rather than a rate, and `phos.eval.metrics.precision_at_budget` has existed since
that session. **Atlas has never called it.** `phos.atlas.grouping` is scrupulous about being a
counting change — "no evidence is discarded, filtered or re-scored on the way through" — which
leaves the queue in time order with no severity on it at all.

The question this session asked is the operator's: rank that queue, cut it to a budget someone
could work, and see what survives.

## Decision

1. **Ranking is a new stage in a new module**, `src/phos/atlas/queue.py`, under detector names
   `atlas-queue:<key>`. It consumes finished subsystem events and never appends to
   `eval_runs/log.jsonl`. `grouping.py` is **not** modified: its promise to re-score nothing
   stands, and the frozen 53.26 row is measured by the same code that always measured it.
   `scripts/evaluate_atlas_queue.py` re-runs the vertical on the same split with the same seed,
   so the queue ranked is the queue logged.

2. **Three declared keys were scored**, because the honest answer might be that none of them rank:
   the largest raw joint distance among an event's members (`magnitude`), the strongest member's
   calibrated probability (`weight`), and how many of the unit's signals departed (`breadth`).

3. **Measured on HAI, seed 11, threshold search forbidden** (`eval_runs/atlas/hai-operator-queue.md`):

   | Key | Distinct scores | Ranks of the 6 true alerts, of 424 | TP in top 48 | Verdict |
   | --- | ---: | --- | ---: | --- |
   | `magnitude` | 424 | 187, 204, 255, 320, 348, 359 | **0** | Ranked the wrong way |
   | `weight` | **1** | — (every cut struck) | — | Did not rank |
   | `breadth` | 4 | 285, 286, 340, 341, 350, 351 | **0** | Ranked the wrong way |

4. **No key ranks the queue towards the incidents.** A random draw of 48 alerts from this queue
   expects **0.68** true positives. `magnitude` finds **0**, and its true alerts sit between the
   44th and 85th percentile — the back half. The loudest 96 alerts contain no attack at all. This
   is a stronger statement than "precision is low": the severity signal points away from the
   incidents, so **no threshold on it will help.**

5. **`weight` is a constant.** All 424 events carry `0.03375934410417169`, the isotonic
   calibrator's ceiling. `docs/atlas-report.md` already recorded that weights top out at 0.034
   across four knots because only 140 of 4,249 calibration candidates fall in attack windows.
   The queue measurement sharpens that: on the operator's queue the weight is not merely
   compressed, it carries **zero** ranking information.

6. **`atlas-queue:weight` at budget 48 — 6 true positives, precision 0.1250, window recall 1.00 —
   is REFUSED and must never be quoted.** It is the tiebreak's number. With a 424-way tie the
   queue is timestamp order, and HAI's attacks fall early in the test slice. `cut_is_arbitrary`
   struck it, along with every other tied cut. In particular it must **not** be compared to CERT
   6B's 0.104: one is a detector's operating point, the other is a sort order.

7. **An arbitrary cut is an executable refusal.** When the last alert taken and the first alert
   dropped share a score, `BudgetOutcome.cut_is_arbitrary` is set and `QueueCurve.honest_points`
   omits the point. This is ADR 0051's idiom applied to a budget rather than to an FP load.

8. **Frozen rows are untouched.** 646.58 ungated, 53.26 grouped, `hai[after]` at 424 alerts and
   recall 1.00 all stand, pinned by `tests/atlas/test_queue_report_freeze.py`. Do not retune
   `_shrink`, `joint_k`, `dwell_samples` or `templates.py` to make a key rank.

## Consequences

**Gained.** The reason 53 alerts an hour cannot be handed to an operator as "your top ten this
shift" is now measured rather than assumed, and it is not the threshold. There is no severity on a
subsystem event. Atlas now has Sentiel's shape — a budget curve — and the first thing that curve
did was refuse.

**Gained, second.** The arbitrary-cut refusal fired on its first outing, on precisely the number
that would otherwise have been reported as a headline beating the Sentiel ruler.

**Cost.** Atlas has no operator queue, and the mechanism that would deliver one reports a refusal
on the only corpus with a declared topology. Nothing here moves Atlas closer to a control room.

**Unexplained, and named rather than papered.** More than a quarter of the queue is pinned in a
band 0.03 wide near magnitude 10.10, and the whole of that block falls in a contiguous stretch
from 22:54 to 02:05 — hours after the 20:21–21:04 attacks. Whether that is a saturating distance,
an operating-point shift between train and test, or both, was **not** diagnosed in this session.

**What this points at.** A severity for a subsystem event has to come from somewhere other than
distance from the fitted manifold. Persistence of an event across windows, coincidence across
subsystems, and the absence of a covering work order (Session E3, `atlas/work_orders.py`) are the
obvious candidates. None is started, and none should be without its own record.

## Alternatives considered

- **Report `atlas-queue:weight` at 48 as a result.** Rejected. A 424-way tie is not a ranking, and
  quoting it would make the sort order look like a detector.
- **Retune `_shrink` or `joint_k` until `magnitude` ranks.** Rejected. Forbidden by the programme
  lock, and it is threshold search on the test split wearing a different hat.
- **Invert the ranking, since truth sits at the back.** Rejected, and this is the tempting one. It
  would fit a sign to two attack windows on one corpus, and the inverted queue's top would then be
  the alerts closest to the band edge — an artefact of where the threshold sits, not a severity.
- **Drop `breadth` for tying so heavily.** Rejected. Measuring that a coarse map cannot separate
  424 events into more than four levels is the result, not a nuisance.
- **Append the queue rows to the experiment log.** Rejected, following ADR 0065. A ranked
  re-count of a logged alert set is a diagnostic and lives in `eval_runs/atlas/`.
