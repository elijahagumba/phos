# Eight slots. What does not get in is the decision.

*The alert budget is two constants in the source, not a tuned threshold. This paper is about the harder half, which is what the page refuses to admit once the eight slots are full, and why that refusal is the design rather than a limit on it.*

[The record](../README.md) · [Front page](../../README.md)

A shift in this repository is not a mood and not a threshold search. It is two constants in `src/phos/atlas/consistency.py`:

```python
SHIFT_SECONDS: Final = 8 * 3600
ALERTS_PER_SHIFT: Final = 8
```

28,800 seconds. Eight alerts. Three different functions spend that budget, and they do not call each other. `budget_alerts` ranks events by score. `shift_page` and `shift_brief` do not. Eviction, where those two use the word's work, means a slot that is never allocated. The function returns a new tuple. Nothing is popped from a heap.

This is a description of committed code and of fixtures. It is not a control-room deployment, and it is not a field rate.

## The frozen allocator

`budget_alerts` bins events by `(onset_time - origin) // SHIFT_SECONDS`. Inside one bin it sorts by descending score and keeps `ALERTS_PER_SHIFT` of them. The alert row is the event onset, not the peak.

If fewer than eight events exist, the spare slots are second alerts. A second alert is allowed only when the peak sits in the same shift and at least `SECOND_ALERT_MIN_SEPARATION` samples after the onset. That constant is 30, in `src/phos/atlas/consistency_windows.py`. The second alert's score is `event.score * 1e-3`. It is the same event, stamped at the peak, and deliberately cheaper than any first alert. A later sort that treats score as importance will not let a spare peak jump a real onset.

That function is the one the public testbed numbers were produced with. On HAI 21.03, 22.04 and 23.05 it is the budget behind 131 of 160 attacks caught, against 52 for the best baseline this lab reproduced (ADR 0116, ADR 0201). The opponent is a baseline we implemented. It is not "the published state of the art". HAI is a testbed. It is not a customer's plant.

`shift_page` and `shift_brief` import `ALERTS_PER_SHIFT` and `SHIFT_SECONDS`. They do not import `budget_alerts`. `tests/atlas/test_program_transfer.py::test_shift_page_does_not_call_budget_alerts` replaces `budget_alerts` with a function that raises `AssertionError`. The page still returns. Editing `budget_alerts` to make room for a transfer would be a different program, and ADR 0303 names that edit as a reversal.

## Non-admission of everything except an unbooked transfer

`shift_page` in `src/phos/atlas/program_transfer.py` takes alerts some other allocator already chose, plus program-transfer reports. The rules, in order:

1. Naive timestamps raise `ValueError`. A span greater than or equal to `SHIFT_SECONDS` raises `ValueError("shift_page takes one shift")`. The comparison is `>=`. A span of exactly one shift is refused.
2. A report with `alert` false is omitted before the sort. A booked transfer occupies nothing.
3. The remaining transfers sort by `(time, act name)` and are truncated to eight. Earliest stay. A shared time keeps the earlier act name.
4. Residual capacity is `8 - len(kept)`. Other alerts fill it, sorted by `(-score, time, key)`. The lowest score is what leaves.
5. An unbooked transfer is not removed to save an other alert. If the unbooked transfers themselves exceed eight, every other alert is omitted.

`tests/atlas/test_program_transfer.py::test_eight_others_and_one_unbooked_transfer_stay_inside_eight` builds eight other alerts scored 8 down to 1, adds one unbooked download, and asserts length 8, the download present, instruction `Go and look.`, lead `None`, and the lowest other key absent. `test_the_lowest_other_score_is_what_leaves` uses scores that are not already sorted, so the test is of the key and not of input order. `test_nine_unbooked_transfers_keep_eight` asserts the ninth time is absent and the page length is still 8.

There is no ninth slot. There is no score at which a sensor hit outranks an unbooked transfer. Priority is categorical. It is not a weight.

## The brief is the same rule against a different residual

`shift_brief` in `src/phos/atlas/shift_brief.py` does not call `shift_page`. Its residual is not a scored `OtherAlert`. It is the open process hits from three checkers:

- `joint_moves`: two or more tags inside `SETPOINT_BAND = (6.5, 7.5)`, gap at most `EVENT_WINDOW` (300 seconds), span at most `EVENT_SPAN` (600 seconds). One in-band write returns nothing. The score on a joint move is the count of tags. It is a count.
- `subfloor_walks`: one tag, at least `WALK_STEPS = 720` in-band steps, consecutive gap at most one second. 719 steps return nothing.
- `handoff_notices`: the same in-band value on a second tag, gap strictly longer than 300 seconds and strictly shorter than one shift. A booking that names both tags and covers the hour clears that handoff. It does not clear a transfer.

Unbooked transfers occupy the front of the tuple even when a process hit is earlier in time. Process hits fill only the residual, earliest first, then kind, then name. If the resulting tuple is longer than eight, `shift_brief` raises `RuntimeError("shift brief exceeded eight")`. The truncation above makes that branch unreachable for a finite inlet. The raise is the guard.

ADR 0312's fixture is eight open handoffs and four unbooked transfers. `handoff_page` on the process inlet alone returns eight handoffs. `shift_brief` returns eight slots, four of them transfers. Four handoffs are absent from the brief. `band_handoffs` still returns them if called on its own. The page does not delete a detection. It declines to show it.

`BriefSlot.lead` is typed `None` and defaults to `None`. A winner cannot be assigned without changing the type. `pyproject.toml` sets mypy `strict = true` on `src`, `tests`, and `scripts`.

## Packing is a third spender of the same eight

`pack_incidents` in `src/phos/atlas/incident_pack.py` does not call `group_evidence` and does not call `budget_alerts`. Membership is an incident id the caller already supplied. Two different ids never merge because they were close in time. Alerts of one id join when the gap is within 300 seconds and the chain spans at most 600. The representative is the earliest alert. Its score is the strongest member, so the packed incident can still compete. `incidents_inside_budget` then keeps at most eight representatives.

ADR 0304 records the fixture: five incidents, unpacked top 8 reach 3 and miss 2, packed reach all 5, misses go from 2 to 0, page length stays 8. No corpus was scored. The refused 53 of 70 from lane 3 is not this function's inheritance. ADR 0300 says incident packing does not inherit that number, and this module's docstring says the same thing in shorter words: a counting change on a fixture, not a detection claim.

## What a later session is not allowed to do

Drop an unbooked transfer so a lower score can stay. Call `budget_alerts` from the page. Widen `(6.5, 7.5)` so a walk becomes visible to the joint check. Treat a slot count on a hand-built inlet as a plant result. Grow the page to nine because the shift was busy. Surface the `1/2` that `transfer_report` feeds to `tied_lead_ids`. That constant exists so the tie is non-empty. It is not a field of `TransferReport` or `BriefSlot`.

---

[The record](../README.md) · [Front page](../../README.md)
