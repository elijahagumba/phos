# Bet 002 — What v1 has to do

**Status: open.** These criteria were frozen on 4 October 2026, before any comparison between Atlas
and a published method had been run. This page's commit date in this repository is the public
record of that. v1 is targeted for January 2027.

If a criterion fails, v1 ships saying which, or it slips. It does not ship with the bar moved. A
criterion changed after a result it judges becomes a new criterion with a new name, shown beside
this one.

## The yardstick

Most published work scores industrial detectors with numbers that ignore how many alerts a person
can actually read. PHOS's headline is **attacks caught within an operator's budget: 8 alerts per
8-hour shift.** In each shift, a detector's alerts are ranked by its own score, only the top 8
count, and an attack is caught if at least one of those 8 is about it. The field's standard
scores (eTaPR, with the settings the HAI competition used, and point-adjusted F1) are reported
beside it.

## Atlas v1

1. **Measured where others measure.** Every public industrial dataset PHOS may use commercially
   is scored for Atlas and for every published method rebuilt so far, in one table that
   regenerates with one command.
2. **Better where it matters.** Judged on the five datasets that label attacks: HAI 20.07, 21.03,
   22.04, 23.05 and BATADAL. Atlas must catch more attacks within the budget than the best
   opponent on **at least three of the five**. A dataset that cannot be scored counts as a loss.
3. **Only real opponents count.** A published method is an opponent only once our rebuild is
   checked: run with its authors' own code, agreeing with that code, or matching the paper's own
   table. If fewer than two such opponents exist, this criterion fails rather than being skipped.
4. **A queue that ranks.** At least half of all attacks have a real alert in the top 10% of their
   shift's queue.
5. **Network against physics.** Checking whether the plant did what the network told it to
   separates explanations that neither view can separate alone, on most of a set of simulated runs
   declared before measuring.
6. **Alerts that settle themselves.** Given a maintenance system's export, at least 70% of
   maintenance-caused alerts close with a cited work order, and no attack-caused alert closes.
7. **One configuration** for every dataset. No setting is chosen per dataset by looking.
8. **Reproduced** by someone outside the project, with one command.

## Sentiel v1

1. **Bet 001 settled** and published, whichever way it goes.
2. **Which, not only how many.** Signals that know *which* people and machines someone touches.
3. **Finds more people.** On a larger insider-threat release, at 48 tickets a day, more labelled
   insiders than today's scorer, beside what chance alone would find.

## What would make this bet meaningless

Rebuilding opponents badly. A weak rebuild makes anything look good. That is why only checked
opponents count, and why the first three rebuilt (MinMax, Steadytime and Histogram, from Wolsing et
al., 2022) are not yet opponents: on HAI 20.07 their attack-window rates are close to the paper's,
but their false-alarm counts are not.
