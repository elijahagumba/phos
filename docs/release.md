# PHOS research pre-release

PHOS is the company. Atlas is the engine this note is about. Atlas watches how an industrial plant normally runs. When something looks off, it says what it might be, and what would decide it. It will not call it an attack if it does not know. Sentiel, for enterprise networks, is planned. This note is Atlas.

This page restates figures already in the record. It adds no measurement. The source is available under the [PolyForm Noncommercial License 1.0.0](../LICENSE). Commercial use needs a licence. The work is not deployable, and it is not a live plant.

## Run it

Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run phos demo
```

About fifteen seconds. A simulated water plant runs for 120 hours, something writes to its controller, and Atlas writes its brief. The demo then says what actually happened, including when Atlas missed or raised a false alarm. `--scenario operator` and `--scenario attacker` are the other two incidents. A demonstration, not a measurement.

```bash
uv run pytest -q
```

The test suite needs no datasets. Public corpora are downloaded separately and never committed. [data/README.md](../data/README.md) is how they are fetched.

One command rebuilds four of the five pinned v1 records and checks every pinned digit. [reproduce.md](reproduce.md). The three headline constants stay frozen under their own names, and nobody outside the project has run the command, so criterion A7 is not met.

## Real testbed data

On HAI 21.03, 22.04 and 23.05, inside 8 alerts an operator can read in a shift, Atlas caught **42 of 50**, **53 of 58** and **36 of 52**. Together that is **131 of 160**. The best baseline checked, scored the same way, caught 36, 10 and 6, together **52**. [ADR 0116](adr/0116-a2-status-four-of-five-beyond-chance.md). The wording is "the best baseline we checked". These editions are seen by this detector, so the figure is a status.

Version 1 meets **8 of 12** criteria written down before those comparisons. The four that are not met: the alert queue's ranking (A3), a reproduction an outsider can run (A7), Sentiel finding more people (S3), and the onboarding trial (C2). [Bet 002](bets/002-atlas-and-sentiel-v1.md).

## Limits that stand

Atlas cannot rank its own alert queue. On HAI the loudest alerts point away from the attacks. [ADR 0068](adr/0068-the-atlas-operator-queue-cannot-be-ranked.md).

Atlas cannot separate maintenance from an attack without that hour's work order. The same fact supports both explanations. [R1](refusal-register.md).

Sentiel is the enterprise-network engine. PHOS is going to build it. It is not ready to stand next to Atlas, so this note does not describe it.

## Simulated, and labelled as such

Giving the engine the control traffic, on twenty runs it had never seen: attacks caught went from **49 of 120 to 87 of 120**, reconnaissance from **0 of 20 to 20 of 20**, benign alerts **6 of 40 unchanged**. The gain is attribution. An attacker at the operator's own console defeats it. [ADR 0276](adr/0276-lane-1-met-its-bar-on-held-out-runs.md). A simulated plant is a diagnosis, not a result about a real plant.

A running tally caught **53 of 70** attacks against the frozen engine's 32, and lost none. At that setting the median delay moved from **1 s to 5 s**. The pass condition forbade a later alarm, so the tally was refused. [ADR 0286](adr/0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md).

A predictor that can bend moved false alarms on unseen quiet data from **28.00 a day to between 20.00 and 24.00**, and attacks caught from **32 to between 23 and 25**, at every amount of bend. It was refused. Part of the frozen engine's detection is a side effect of its misfit. [ADR 0288](adr/0288-the-linear-predictors-misfit-is-load-bearing.md).

Judging every signal together needed an attack that stays inside each signal's ordinary range and inside the plant's own relationships. That attacker could not be posed on a continuous level-flow ratio, because this plant's outflow is a constant or zero. The attack that could be posed, `legal_flow`, caught **15 of 32** on the development runs against the frozen engine's **16 of 32**. [ADR 0296](adr/0296-legal-flow-does-not-give-breadth-the-catches.md). The stronger-engine programme is closed. [ADR 0297](adr/0297-build-brief-e-is-closed-without-a-stronger-engine.md).

## Left unsaid

This note does not carry a 10× reduction as a pass, a claim of 2 to 3 alerts a day, a command lead at or above 70 percent, the two issuer kinds pooled into one rate, a confidence shown as a probability, or a simulated result stated as a result about a real plant.

The longer record, including the refusals, is [here](README.md).
