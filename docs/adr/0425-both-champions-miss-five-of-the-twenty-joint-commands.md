# ADR 0425 — Both champions miss five of the twenty joint commands, so the specified detector may be built

- **Status:** Accepted
- **Date:** 2026-11-09
- **GENESIS:** E-0003, serving Q-0003
- **Verdict:** **refused**, computed from the measured values against the bars declared on 2026-11-09

## Context

The declaration was committed before the run as `8448518f8606cfa09f6df7b5795b19bca4dd4938`. The command was `uv run python scripts/lane_e_icssim_baseline.py --corpus data/phos-icssim-dev5` on `phos-icssim-dev5`, measured from `8448518` and reported in `eval_runs/build/lane-daily/joint-champions.md`.

## Decision

**The result is refused.**

- b1. The corpus scored here holds twenty `joint_command` events. This is the denominator check and it comes before the other two. The count was computed on 9 November 2026 from committed code alone, by drawing the schedule for each of the eight declared seeds 98011 to 98018 and counting that class, which gives 2, 3, 4, 3, 2, 2, 2 and 2. No corpus was opened to get it, and ADR 0316 fixed both the seeds and the scenario, so a different count would mean the thing being scored is not the thing that was declared. (`joint_events == 20`) — measured **20**, met
- b2. Neither champion misses a single joint command, so the engine Atlas already ships sees this class and the detector ADR 0316 specified is not built. This bar and b3 are deliberately incompatible, exactly as ADR 0316 wrote the gate: the record says this score has no pass bar and is the denominator, so the verdict has to name which branch the corpus fell on rather than report a number both branches could satisfy. Expect the automatic verdict to read as a refusal whichever way it goes, because one of these two bars must be missed. (`joint_m_champion == 0`) — measured **5**, missed
- b3. At least one joint command is missed by both champions, which is the branch where the detector ADR 0316 specified may be built, as specified there and not otherwise. This is the hypothesis above. Being met is permission to build a module later under its own record, and it is not itself a detection claim, a recall, or a false-alarm rate. (`joint_m_champion >= 1`) — measured **5**, met

**Failure cases and unexpected results.**

Bar b2 is missed, and it was written to be missed if b3 held: the two are deliberately incompatible because ADR 0316 states this score has no pass bar and is the denominator. M_champion is 5, not 0, so the branch where Atlas already sees this class did not happen. No bar was moved, the run was not repeated, and the champion files were not edited.

**Notes.**

The hypothesis held and its mechanism held with it. Both champions miss 5 of the 20 joint commands and are identical on every printed number: 5 misses each, 38 false alerts each, 1.187500 per hour each, median delay 0.500000 s each. A tie on both keeps the frozen detector by ADR 0316's rule, so the champion is frozen. Lane 1 reduces exactly to the engine it extends here, because its two live components are a write from a role that never wrote in training and a read from a role that never read, while this class writes from the operator console that already writes in training and reads nothing unusual. The breadth column matches too and is not a champion. The denominator was computed from committed code before any directory was opened, giving 2, 3, 4, 3, 2, 2, 2, 2 per seed, and the generated corpus holds exactly that. Generation ran under python3 rather than python, which is not on this machine's path; the generator is standard library only and spawns the pinned ICSSim virtual environment for the simulation, so the interpreter reading the argument list is not part of the measurement. The false-alert rate equals the walk column's committed 1.187500 per hour, 38 over 32 hours against 19 over 16, which is this generator's budgeted alert load rather than a property of either class. One benign setpoint of 18 drew an alert and all 10 maintenance events were quiet. The gate ADR 0316 set is now open: the detector it specified may be built under its own record, and it is not built here. 15 of 20 is not a recall figure; the corpus is synthetic, one plant, one protocol, and ADR 0143 stands.

## Consequences

**The gate ADR 0316 set is open, and nothing walks through it here.** That record said the detector
it specified may be built only if `M_champion` is greater than 0. It is 5. So the module
`src/phos/atlas/joint_consistency.py` may now be built, as specified in ADR 0316 and not otherwise,
under its own declaration. This record does not build it, does not declare it, and does not reserve
a number for it.
<!-- evidence-ack: src/phos/atlas/joint_consistency.py — specified by ADR 0316 and not built; this record opens that gate and deliberately does not walk through it -->

**The oldest open promise in the project is settled.** ADR 0316 was committed on 23 October 2026 and
never scored. `docs/atlas-engineering-roadmap.md` Act I names closing it first, on the ground that
nothing new is honest while something already declared is unfinished. It is closed by a number
rather than by a record explaining why it would not be taken.

**The computed verdict word is `refused`, and that is the declaration working rather than failing.**
ADR 0316 states in its own text that this score has no pass bar and is the denominator. A question
whose two answers are both results cannot be expressed as one bar that a good outcome meets, so
E-0003 declared both branches as incompatible bars, b2 and b3, and said in b2's own text to expect a
refusal whichever way the corpus fell. The substantive outcome is which branch was named. ADR 0418
hit the same shape and recorded it; this is the second time, so it is a property of the method and
not an accident.

**Lane 1 reduced exactly to the engine it extends, on this class.** Every printed number is identical
between them. That is a statement about this class only: lane 1's two live components look for a
writer or a reader that training never saw, and this attack uses the console that writes in training.
It is not a judgement of lane 1 on any other class, and ADR 0276's held-out result is untouched.

**What does not move.** No detector is built. No bar was moved and the run was not repeated.
`phos-icssim-heldout5` stays generated nowhere and opened never; it is on the score-once tier from
ADR 0316's commit. The walk score is not rerun and no divisor is retuned. `phos-icssim-dev4` and
`phos-icssim-dev4-walk` are not regenerated. `eval_runs/log.jsonl` is not appended. The champion
files are not edited and their digests are unchanged. No frozen row moves. 15 of 20 is not a recall
figure and 1.187500 per hour is not a false-alarm result: both are a synthetic one-plant denominator,
and ADR 0143 stands, so nothing here says the plant map improves detection on real plant data.
Nothing here is evidence for A2, A3 or A7. v1 stays **8 of 12**. Intelligence, the API and the UI stay
closed, and **P1 stays the blocked human conversation.**

---

Rendered by `scripts/genesis.py adr E-0003`. A refusal is a result; it is recorded the same way a kept result is, and is not removed from the record later.
