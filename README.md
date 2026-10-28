<img src=".github/assets/readme/poster.svg" width="100%" alt="PHOS. Security that tells you what it doesn't know. Atlas, for industrial plants. A plant names the laws in force. Each named law is held, broken, or unstated. Only a broken law takes a slot. The page holds at most eight, ordered by time, then by the law's name. Every sentence names its law, then the fact. A score is refused. A break is a false law. The page does not name the cause. Held means the check ran and the law stood. Unstated means the plant named the law and supplied nothing that law can be checked against. An empty register checks nothing. joint_move, subfloor_walk, band_handoff, program_transfer, allowed_writer, controller_valve. Research pre-release.">

**PHOS is a behavioural cybersecurity company.** It builds systems that learn what normal looks like in one place and report what no longer fits, with the evidence attached. It does not keep a list of known attacks.

The thesis is that **"normal" is not one thing.** A water treatment plant and a corporate network are different kinds of environment, with different physics, different rhythms and different reasons for a thing to be unusual. One model stretched across both is worse at each. So PHOS builds two engines, each engineered for its own world: **Atlas** for industrial plants, **Sentiel** for enterprise networks. A third part, **PHOS Intelligence**, is planned to correlate what the two engines independently conclude.

Atlas is the work right now, so most of this page is Atlas.

## The problem

An industrial plant runs on the judgement of the people in its control room. A security system that guesses spends that judgement. Spend it twice and the third page goes unread.

The industry's answer has been to score everything and sort by the score. That produces a queue nobody finishes and a number nobody can explain. PHOS takes the opposite position: a system that cannot support a claim should be allowed to say so, and the page an operator reads should hold only what it can defend.

## What Atlas does

The plant writes down the laws it runs by. Atlas checks whether each one still holds, and reports the ones that do not, **at most eight a shift**. It attaches no score, ranks nothing, and names no cause. Where the plant's own record cannot settle what happened, Atlas says so and stops.

**Atlas is a witness, not a judge.** It says what it saw, names the law that makes it matter, and stops. A line on the page is not a verdict. It means someone should go and look.

It is not a SCADA system, not personnel tracking, and not revision tracking. It does not connect to a control network.

| Law | A break is |
| --- | --- |
| `joint_move` | Two tags written inside the ordinary band, close together in time |
| `subfloor_walk` | One tag stepped across that band for a fixed length |
| `band_handoff` | The same ordinary value on a second tag later, and no booking names both tags |
| `program_transfer` | A download, an upload, or an online edit, and nothing booked covers that act |
| `allowed_writer` | A write from a station the plant did not name |
| `controller_valve` | A valve that is not the value the plant's own comparison writes |

A law the plant names but this page cannot check is listed and takes no line. An empty page is not a claim that the plant is safe: it means the checks ran and the laws stood, or the plant named a law and supplied nothing to check it against. The code is [`src/phos/atlas/declared_law.py`](src/phos/atlas/declared_law.py).

## What makes this different

Three commitments, each of which costs something:

**It is allowed to say nothing.** `insufficient_evidence` is an honourable answer. Most products cannot ship it, because a quiet dashboard looks like a broken one.

**Every conclusion reconstructs from stored evidence.** No opaque score reaches a user. Competing explanations stay visible rather than being collapsed into one answer, and confidence is not shown at all until it is calibrated against held-out data.

**The failures are published.** This repository contains the measurements that did not work and the detectors that were built and then refused. Three examples, all in the record:

- A detector caught **more** attacks, 53 of 70 against the frozen engine's 32, and lost nothing. It arrived later, median 1 s to 5 s. The bar forbade a later alarm, so it was refused. [ADR 0286](docs/adr/0286-an-appended-column-cannot-win-a-slot-without-taking-the-alert.md)
- A better-fitting predictor cut false alarms on unseen quiet data from 28.00 a day to 20.00–24.00, and cut attacks caught from 32 to 23–25, at every setting. Part of the frozen engine's detection turns out to be a side effect of its own misfit. [ADR 0288](docs/adr/0288-the-linear-predictors-misfit-is-load-bearing.md)
- The operator queue was ranked by residual magnitude. The loudest alerts pointed **away** from the attacks, so the magnitude was taken off the page entirely. [ADR 0068](docs/adr/0068-the-atlas-operator-queue-cannot-be-ranked.md)

A vendor who publishes the detectors it refused is making a different kind of promise from one who publishes only its wins.

## What it will not guess

A download, an upload and an online edit are three different acts, and Atlas keeps them apart. It will not decide from a byte on the wire that one of them happened; that has to come from the plant's own record. It cannot tell whether the act was booked, because the booking lives in scheduled downtime, a commissioning window or a check-in sheet, and Atlas has none of those yet.

So it will not call a contractor doing a requested change an intruder, and it will not call an intruder a contractor. Someone with a valid login sets off no alarm by the login itself. What they change is how the plant runs.

<img src=".github/assets/readme/alert.svg" width="100%" alt="An Atlas alert. A command this link does not usually see. It might be an attack or planned maintenance. The same fact supports both, so Atlas will not pick. What would decide it: a command from a machine that has never commanded this one.">

## Measured

These are measurements of the older residual detectors, which remain in the repository so published figures still reproduce. They are not the declared-law page, and that page carries no score.

**On real testbed data.** On HAI 21.03, 22.04 and 23.05, inside eight alerts an operator can read in a shift, Atlas caught **42 of 50**, **53 of 58** and **36 of 52**: together **131 of 160**. The best baseline checked, scored the same way, caught 36, 10 and 6: together **52**. These editions had already been seen by this detector, so that figure is a status rather than a held-out result, and it is reported as one. [ADR 0116](docs/adr/0116-a2-status-four-of-five-beyond-chance.md)

**On a real wind farm**, two years held back and scored once, with no attacks in it: 6 of 29 alerts were not explained by the turbines' own logs. [ADR 0178](docs/adr/0178-kelmarsh-held-back-years-were-scored-once.md)

**On simulated plants**, which are a diagnosis and not a result about a real plant: giving the engine the control traffic took attacks caught from **49 of 120 to 87 of 120** on twenty runs it had never seen, and reconnaissance from **0 to 20 of 20**, with benign alerts unchanged at 6 of 40. The gain is attribution, and an attacker working from the operator's own console defeats it. The lying sensor was named in **146 of 150** runs, none named wrong. **0 of 80** simulated attacks were closed as maintenance, including 40 dressed up as maintenance. [ADR 0276](docs/adr/0276-lane-1-met-its-bar-on-held-out-runs.md)

**Against its own criteria.** Version 1 meets **8 of 12** criteria written down before any of these comparisons were run. The four unmet are the alert queue's ranking, a reproduction an outsider can run, Sentiel finding more people, and the onboarding trial.

<img src=".github/assets/readme/measured.svg" width="100%" alt="Measured. On three editions of HAI, a real industrial testbed, Atlas caught 131 of 160 attacks at 8 alerts a shift; the best baseline checked caught 52. On simulated runs it never saw, the lying sensor was named in 146 of 150, none named wrong. 0 of 80 simulated attacks were closed as maintenance, including 40 disguised as maintenance. On a real wind farm with no attacks in it, in two years held back and scored once, 6 of 29 alerts were not explained by the turbines' own logs. Simulated plants are a diagnosis, not a real-plant result.">

## What Atlas cannot do

Stated plainly, because a reader will find these out anyway:

- **It cannot rank its own alert queue.** On HAI the loudest alerts point away from the attacks.
- **It cannot separate maintenance from an attack without that hour's work order.** The same fact supports both explanations, and no public corpus ships a maintenance export.
- **It has never run on a live plant.** Every figure here comes from published corpora or simulation.
- **It has not been reproduced by anyone outside the project.**

<img src=".github/assets/readme/boundary.svg" width="100%" alt="What Atlas can say: it treats the plant as one machine, says what a change might be, names what would decide it, stays quiet when it cannot tell, and names the lying sensor on simulated plants. What it can't do yet: close a maintenance alert without that hour's job sheet, rank its own alert list, learn from a labelled command capture, or prove itself on a real plant.">

## Sentiel, the second engine

Sentiel is for enterprise networks, where "normal" is a person's working pattern rather than a pump's physics. Its job is the same speech contract in a different world: for a person on a day, hold competing explanations open — `compromised_account`, `insider_misuse`, `peer_anomaly`, `legitimate_change`, `insufficient_evidence` — and report the evidence for each rather than a single verdict with a number on it.

**Where it honestly stands: not ready to stand next to Atlas.** On the public insider-threat corpus it finds one of two insiders, and the bet to find the other ran once and lost. A peer-group advantage that looked real was measured, failed to survive, and was retired rather than quietly kept. Sentiel finding more people is one of the four v1 criteria that version 1 does not meet.

It is on this page because PHOS is two engines and one ontology, not because it is finished.

<img src=".github/assets/readme/sentiel.svg" width="100%" alt="Sentiel finds one of two insiders; the bet to find the other ran once and lost.">

## Where this goes

The next step is **one plant**: a site that exports its own historian files and writes down, in its own words, the laws it runs by. Everything on this page was measured on published corpora and simulation, and no amount of either substitutes for one real plant's notion of normal.

If a plant agrees, the second year builds on its data. If no plant agrees, the product sequence stops, and the page and the record stay as they are. That is written down rather than left implied.

## The record

Everything PHOS has measured, including what did not work.

[Release note](docs/release.md) · [The full record](docs/) · [The refusal register](docs/refusal-register.md)

[Eight alerts](docs/whitepaper/hn_technical_post.md) · [What the page refuses](docs/whitepaper/eight-alert-non-admission.md) · [A function code is not a download](docs/whitepaper/modbus-is-not-a-program-transfer.md) · [Membership is declared, not inferred](docs/whitepaper/topology-is-declared-not-inferred.md) · [The detectors that were refused](docs/whitepaper/lanes-that-were-refused.md) · [A score is not a rank](docs/whitepaper/a-score-is-not-a-rank.md)

## Talk to us

**If you operate or secure an industrial site** and can export historian files and write down which laws matter: that is the conversation PHOS most wants to have. The page will not show a score, and PHOS will not connect to your control network.

**If you are a researcher**, the measurements reproduce and the corpora are named. Disagreements about method are welcome in [Discussions](../../discussions).

Write to [elijahagumba.research@proton.me](mailto:elijahagumba.research@proton.me).

## Run it

Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run phos demo
```

About fifteen seconds. The demo runs the older detectors on a simulated water plant for 120 hours. It is not the operator page. The demo then says what actually happened, including when it missed or raised a false alarm. `--scenario operator` and `--scenario attacker` are the other two incidents.

```bash
uv run pytest -q
```

The test suite needs no datasets. Public corpora are downloaded separately and never committed; see [data/README.md](data/README.md).

---

Research pre-release. Not deployable, and never run on a live plant.

Built by one researcher with AI coding agents. Every published number reproduces from this repository and the public datasets it names.

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires a licence.

PHOS
