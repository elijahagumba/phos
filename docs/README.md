<img src="../.github/assets/readme/record.svg" width="100%" alt="The record: everything PHOS has measured, including what didn't work. Each number here can be rebuilt from this repository. Each limit says what would lift it.">

<br>

### Start here

1. **The short version:** the [release note](release.md).
2. **The papers**, each a breakdown of code already in this repository:
   - [The operator gets eight alerts](whitepaper/hn_technical_post.md)
   - [What the page refuses](whitepaper/eight-alert-non-admission.md)
   - [A function code is not a download](whitepaper/modbus-is-not-a-program-transfer.md)
   - [Membership is declared, not inferred](whitepaper/topology-is-declared-not-inferred.md)
   - [The detectors that were refused](whitepaper/lanes-that-were-refused.md)
   - [A score is not a rank](whitepaper/a-score-is-not-a-rank.md)
3. **What Atlas does on real data:** the section below, each result linked to its record.
4. **What it will not claim:** the [refusal register](refusal-register.md).
5. **How each number was earned:** every result has a decision record in [adr/](adr/), written
   before the score it reports.

<br>

### What Atlas measured

**On real testbed data.** HAI is a public dataset recorded from a hardware-in-the-loop industrial
testbed. On its three editions not used to build the detector, at the budget of 8 alerts an
operator can read in a shift, Atlas caught **42 of 50**, **53 of 58** and **36 of 52** attacks. The
best baseline checked, scored the same way, caught 36, 10 and 6. On all three, Atlas was above
every one of 500 random draws of the same budget.
[ADR 0116](adr/0116-a2-status-four-of-five-beyond-chance.md)

**A better idea that failed the real test.** A learned map of the plant, which caught far more
falsified sensors on simulated plants, was taken once to those same editions. It caught fewer
attacks than the current detector on two of them and more on none, so it was not adopted.
[ADR 0143](adr/0143-the-plant-map-fails-the-gate.md)

**Naming the lying sensor, on simulated plants.** Explaining the current detector's alerts, the
plant map named the falsified instrument on **146 of 150** runs it had never seen, none wrong, and
reconstructed the true value within 5% of the instrument's range.
[ADR 0170](adr/0170-every-control-coupling-is-a-loop-and-bars-only-its-outputs.md)

**A real plant with no attacks.** On six wind turbines at Kelmarsh over 2019 to 2022, the
unchanged detector raised 74 alerts in about 26,000 shifts; the turbines' own status logs explained
57 of them. On 2023 and 2024, held back and scored once, it raised 29 and the logs explained 23.
[ADR 0165](adr/0165-kelmarsh-round-2-trains-on-2018.md),
[ADR 0178](adr/0178-kelmarsh-held-back-years-were-scored-once.md)

**What does not work yet.** On harder simulated cases, such as a fault during maintenance or two
sensors failing together, the leading explanation was right 33 times in 54, and right and wrong
answers carried the same confidence, so no confidence figure is shown
([ADR 0176](adr/0176-w5-held-back-confidence-is-declared.md)). A later version of the reasoning,
built to look for the evidence that tells two explanations apart, was right on all 60 held-back
cases where it named one and declined to name one on the rest. Those cases came from the same five
kinds of situation it was built around, and its confidence is still not shown
([ADR 0260](adr/0260-build-d-is-merged-and-its-bars-stand.md)). On real network captures from the
4SICS lab, most traffic was Siemens S7, which Atlas does not decode yet
([ADR 0177](adr/0177-4sics-development-days-are-declared.md)). And its queue still does not rank:
across five corpora, looked at once, 57 of 203 attacks had a true alert in the top tenth of their
shift's queue, where half was the bar
([ADR 0212](adr/0212-a3-queue-rank-is-declared.md)). Reordering cannot fix most of that: many
shifts hold more attacks than there are top slots, and on the one corpus Atlas was built on even a
perfect ordering reaches only 21 of 38. On simulated plants, a hostile command from a station the
plant already trusts is still not named, though the new evidence for it appeared on every hostile
write and on no legitimate one ([ADR 0260](adr/0260-build-d-is-merged-and-its-bars-stand.md)).


**Four attempts at a stronger engine, and the three that failed.** After v1 froze, four independent
ideas were tried against a plant PHOS generated so that both the physics and the control traffic
were recorded for the same minutes — something no public corpus provides. Each was measured against
the frozen detector under the same alert budget, and each had its pass condition written down first.

*Kept:* giving the engine the control traffic, so it can see that a station which never issues
commands has started issuing them. On twenty runs it had never seen, attacks caught went from 49 of
120 to **87 of 120**, and an attacker quietly mapping the plant from **0 of 20 to 20 of 20** — a
thing no amount of watching the physics can see, because reading never moves the plant. The gain is
**attribution**, and it is shallow by construction: an attacker working from the operator's own
console defeats it. [ADR 0276](adr/0276-lane-1-met-its-bar-on-held-out-runs.md)

*Refused:* a running tally of how wrong each instrument has been caught **53 of 70 attacks against
32**, losing none, and took a frozen sensor from 1 of 10 to **10 of 10** — and it noticed about four
seconds later, which its pass condition forbade. The reason it cannot be fixed by tuning is the
finding: on a full alert budget, a new signal has to score high to win a slot at all, and scoring
high is the same thing that makes it take over *when* the alert is raised.
[ADR 0286](adr/0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md)

*Refused:* letting the prediction bend, so the engine stops being surprised by a valve that
saturates or a controller in its deadband. False alarms on unseen quiet data fell from 28 a day to
**20–24**, and attacks caught fell from 32 to **23–25** at every setting tried. The alarm is
surprise; a crude model is surprised easily and a faithful one explains more of what it sees,
including the attack. Part of the old detector's sensitivity was a side effect of its misfit.
[ADR 0288](adr/0288-the-linear-predictors-misfit-is-load-bearing.md)

*Untestable:* judging all the signals together needs an attack that is invisible in every single
signal — one consistent with the plant's own correlations. No corpus contains one, and building that
attacker is a harder problem than the detector.

All four results are on a simulated plant, which makes them diagnosis and not proof. One capability
was added; three routes are now mapped dead ends with the reasons recorded.

> **Closed, 21 October 2026 ([ADR 0297](adr/0297-build-brief-e-is-closed-without-a-stronger-engine.md)).**
> The programme above is finished. The joint question was then asked on the attack this plant can
> host: breadth caught 15 of 32 attacks and the frozen engine 16 of 32
> ([ADR 0296](adr/0296-legal-flow-does-not-give-breadth-the-catches.md)). The stronger engine was
> not reached. There is no successor plan on this page. The paragraphs above are left as written.
>
> **Successor, 21 October 2026 ([ADR 0298](adr/0298-five-questions-succeed-the-closed-stronger-engine-programme.md)).**
> Five questions are now open. None is a claim that it will work. The first is whether a command
> can be wrong while every sensor stays ordinary, and the first measurement is of the detector
> we already have. A later evaluation, not yet run, passes only if a candidate catches more
> attacks than that detector inside the same alert budget and does not raise more false alarms.

### A broken law, or silence

The operator page in `src/phos/atlas/declared_law.py` admits a slot only when a declared law is false. A law the facts satisfy is silence. A law the plant did not name is not evaluated. A declared law is held, broken, or unstated, and only a broken law takes a slot. A law the plant names that this page has no check for is listed and takes no slot. The page keeps the earliest breaks, at most 8, ordered by time and then by law name. Residual magnitude does not create a slot and does not sort one. Every sentence is the law's name, then the fact. A sentence that carries a confidence, a probability, a weight, a magnitude, or a score is refused, and a break whose sentence does not name its law is not placed.

The laws are boolean. Two setpoints inside the ordinary band are one move, or they are nothing. A walk of the frozen length is one walk, or it is nothing. An open handoff is a break until a booking names both tags. An unbooked program transfer is a break. A station outside a declared set is a break, and an empty set means that law was not stated. The controller comparison is the PLC's own rule, with no divisor: agreement is silence, a valve that is not the value that rule writes is one break, and manual mode means the law was not in force.

No corpus was scored for this page. The frozen residual detector was not edited. Version 1 stays **8 of 12**. This page is not a detection claim.
[ADR 0317](adr/0317-a-slot-exists-only-when-a-declared-law-is-false.md),
[ADR 0318](adr/0318-a-slot-requires-a-declared-law.md),
[ADR 0319](adr/0319-only-a-broken-law-takes-a-slot.md),
[ADR 0320](adr/0320-an-unnamed-station-is-silence-until-the-set-is-named.md),
[ADR 0321](adr/0321-the-controller-comparison-is-true-or-false.md),
[ADR 0322](adr/0322-a-slot-enters-only-as-a-law-break.md),
[ADR 0323](adr/0323-every-sentence-names-the-law-it-came-from.md),
[ADR 0326](adr/0326-a-score-word-is-not-placed-and-an-unchecked-law-stays-listed.md).

### What the engines we already have caught, on a simulated plant

These scores were declared before they were run. A simulated plant is a diagnosis, not a result about a real plant.

An in-range command writes the tank's upper limit inside the band a normal setpoint already uses, 6.5–7.5, and holds the inlet valve off. Both engines we already have caught **13 of 13**. The miss count was 0, so the column written down in advance was not built. False alerts were 11 and 11, **0.343750** per hour. What caught them is the ordinary signal column.
[ADR 0309](adr/0309-the-champions-missed-none-of-the-in-range-commands.md).

A setpoint walked across that same band in 720 steps: both engines caught **8 of 9**. The miss count was 1.
[ADR 0313](adr/0313-the-champions-missed-one-of-the-slow-walks.md).
The column that compares the inlet valve with the constant the plant's own controller writes missed that same 1 of 9. Half of 1, rounded down, is 0, so the column was not kept. The divisor was **2.000000**, and a full disagreement sat on the threshold.
[ADR 0315](adr/0315-the-walk-column-does-not-halve-the-remaining-miss.md).

A joint command, two setpoints written together, was declared and not scored.
[ADR 0316](adr/0316-the-joint-command-is-declared-before-either-champion-is-scored.md).

[How the current detector entered the engine →](adr/0107-the-consistency-detector-enters-the-engine.md)

<details>
<summary>Earlier measurements, before the current detector</summary>

An earlier Atlas, treating the plant as one connected machine rather than watching each sensor
alone, cut false alarms on a slice of HAI from 8,390 to 647 an hour without missing an attack, and
grouping alarms by physical unit cut what an operator would read by a further 12 times. That still
left about 53 false alarms an hour, and the slice held only two attack windows. A calibration fitted
only on ordinary operation read 3.55 an hour; it is
[recorded beside the original number](adr/0083-calibrator-without-labelled-positives.md). The
current detector replaced that approach and is measured by attacks caught within the alert budget.

[Read the August 2026 Atlas report, kept as written →](atlas-report.md)

</details>

<br>

### What PHOS refuses to claim

Twenty-six things PHOS will not say, each with the evidence that rules it out and what would change
that. Atlas cannot tell maintenance from an attack without the work order for that hour. It cannot
rank its own alert queue: the loudest 96 alerts on HAI contained none of the real attacks.

[Read the refusal register →](refusal-register.md)

<br>

### How the simulated plants avoid fooling us

Three simulated plants (water treatment, power generation and a batch reactor) record their true
internal state separately from what their sensors report, so a miss is judged against what actually
happened. The attacks were written by people who could read the detector. Five rules stop the
simulator from quietly favouring Atlas, and each was tested by breaking it on purpose to make sure
the build fails. Of the three plants, one currently supports a detection claim.

[Read the method →](synthetic-harness-method.md)

<br>

### What Sentiel found, and what failed

Sentiel, the engine that watches people, finds one of the two labelled insiders in CERT r3.1, a
public insider-threat dataset, and cannot see the other. The reason is arithmetic: at least 14 of
its 34 signals must move at once before anyone can be flagged. The fix, its success test and our
own prediction that it won't be enough were all written down before any code. The bet was run once
on 18 October 2026 and lost: no declared formula put the second insider in the top 48.
[ADR 0148](adr/0148-bet-001-is-scored-once.md)

A later investigation found a signal that puts both insiders in the alerts on that dataset: a
return to a web host nobody else uses. We treat it with caution. In this dataset no innocent person ever
returns to such a host, which may be how the dataset was generated rather than how people
behave, and the result was counted before it was declared. It was tested once on a larger
release it had not seen, CERT r4.2, at 48 alerts a day, and failed: it surfaced 1 of the labelled
insiders where the unchanged scorer surfaced 59, against 35 expected by chance. None of the 930
innocent people in that release used a web host nobody else used, so the signal was reading how the
dataset was made.
[ADR 0195](adr/0195-a-return-to-a-host-nobody-else-has-used.md),
[ADR 0202](adr/0202-forty-eight-tickets-a-day-supersedes-the-top-48.md)

[Read Bet 001: the second insider →](bets/001-the-second-insider.md)

The bar Atlas and Sentiel v1 must clear was fixed before any comparison was run. As of 21 October
2026, **8 of its 12** criteria are met. The four that are not — the alert queue's ranking, a
reproduction anyone outside the project can run, Sentiel's second insider, and the onboarding
trial — were each scored once and recorded as misses.

[Read Bet 002: what v1 has to do, and where it stands →](bets/002-atlas-and-sentiel-v1.md)

After that failure was read properly, a third bet was fixed on 20 October 2026. Atlas's shift
queues turned out to be shorter than the eight alerts an operator can read, so the criterion that
failed had been asking the attack to be the loudest alert of its shift rather than to be inside
the reading. Measured in alerts instead of percentages, 172 of 203 attacks appear in the shift
they began in, every one of them within the first nine alerts. The new bars are about the
thirty-one that appear in no alert at all, and about handing the operator a story rather than a
row.

[Read Bet 003: the first shift →](bets/003-the-first-shift.md)

<br>

### Why it is built this way

256 decision records, each with what was chosen, what was rejected and what it cost. The latest on this page is ADR 0323.
Several exist only to record a result that did not work. Five places to start:

- [The joint model, and the model that lost](adr/0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md)
- [A tie is a refusal, not an alphabetical winner](adr/0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)
- [There is no labelled public command capture](adr/0040-no-labelled-public-command-corpus.md)
- [The operator queue cannot be ranked](adr/0068-the-atlas-operator-queue-cannot-be-ranked.md)
- [The false alarms were the model's, not the plant's](adr/0075-the-hai-false-alert-load-is-modelling-error-not-missing-evidence.md)

[Browse every decision →](adr/)

<br>

<br>

### What is not in this repository, and why

This is the research record, not the whole lab. A few decision records cite documents that stay
behind, so if a link or a filename here does not resolve, it is one of these rather than something
missing:

| Kept back | What it is |
| --- | --- |
| `PROGRESS.md` | The chronological build log. Long, internal, and superseded for any reader by the decision records themselves |
| `encyclopedia/`, `easy to reads/` | The long-form reference and the plain-English walkthroughs. Written for whoever picks the work up next |
| The agent rules and the build briefs | How the lab is driven: the always-apply rules, the role definitions and the guards that warn before a known mistake |
| Commercial and partner material | What PHOS asks a design partner for, and how it intends to find one |
| Every data payload | No corpus is committed. `data/` carries manifests with checksums, never the files. Several corpora are licence-barred from redistribution regardless |

**Nothing load-bearing is behind that line.** Every number on these pages has its decision record
and its result file in this repository, and `docs/reproduce.md` is the one command that rebuilds
them. Where a claim rests on data that cannot be redistributed, the record says so and names the
licence rather than quietly omitting it.

<sub>The documents behind these pages are the working record, written as the research happened. They are dense by design.</sub>
