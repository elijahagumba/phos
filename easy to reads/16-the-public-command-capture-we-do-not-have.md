# The public command capture we do not have

**What this is:** Session 5 of the command-lead honesty programme, completed **by refusal**.
The public files were opened. The shopping list is no longer “we have not looked.” There is
still **no labelled public command corpus**.

**Why it exists:** the cycle contract still asks that unauthorised control be the top-ranked
explanation in **≥70%** of confirmed command-attack windows on every public corpus with network
traffic. Completing sessions 1–5 does not earn that. A named gap is the honest session. A number
invented from process clocks is not.

## We can read the tape. The captions are about the shift.

Think of a security camera on a plant floor. The footage is real. The captions say “lunch hour,”
“night shift,” “the solar plant is being manipulated.” That is a **process phase**. It is not a
labelled list of **who turned which valve**.

Data4Cyber ships `.pcapng`. Atlas’s packet path **opens it**. That is a real finding: an earlier
clause that “pcapng is not yet the dpkt path” is false for this corpus
([ADR 0040](../docs/adr/0040-no-labelled-public-command-corpus.md), amending
[ADR 0033](../docs/adr/0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)
on that clause only). Readable packets are not command ground truth.

The labels on disk are **1 Hz process phases** (`attack_active`, `attack_phase`). They mark
whether a second of the plant story was “normal,” reconnaissance, or a named manipulation.
They do not mark **this write was the attacker’s control action**.

A publisher clock named “command execution window” is still a wall-clock span. Mapping that
span onto the capture does **not** invent command-action labels. Inside the same span the
capture still holds **120** legitimate EMS writes and **82,315** Modbus messages, mostly
ordinary polling ([ADR 0040](../docs/adr/0040-no-labelled-public-command-corpus.md)). Analogy:
a train timetable that says the 14:00 service ran is not a passenger list. Overlap of clocks
is not “this hand moved this switch.”

About **1.6 hours** of normal CSV seconds (**5,880** rows) cannot be the false-positives-per-hour
ruler ([ADR 0003](../docs/adr/0003-window-level-recall-and-false-positives-per-normal-hour.md),
[ADR 0040](../docs/adr/0040-no-labelled-public-command-corpus.md)). That is judging a control
room’s daily false-alarm rate from a short quiet morning. Do not quote a Data4Cyber FP/hour.

Using the attacker’s IP as a label would make “unknown master” tautological. Identity is not a
control-action window.

## A spreadsheet of packets is not the packets

s7-data-modification is a parsed packet **table** (parquet). Feeding it as a capture would skip
the dissector the security argument is built around
([ADR 0012](../docs/adr/0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md)).
Atlas’s only protocol dissector is Modbus/TCP. A table is not a pcap.

3W Petrobras class labels 1–9 remain **faults** (slugging, hydrates, and the rest). A broken pump
is not an attacker. Collapsing those classes to “attack” would be a false statement. There is
no command capture.

Licence confirmation is not a measurement. Files beat papers
([ADR 0033](../docs/adr/0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)).

## Five sessions of plumbing do not earn the contract

Sessions 1–4 made ranking, silence, and story-attachment **honest** on the plants we wrote.
Session 5 asked for a licence-confirmed public command capture Atlas already dissects, with
issuer kinds scored apart — or a refusal that names the gap. The discovery seam stayed empty.
The tripwire test that this repository holds no labelled command corpus still **passes**, on
purpose.

Frozen D2, scored **apart**, not remeasured, not pooled, not the cycle contract
([ADR 0038](../docs/adr/0038-a-windows-story-attaches-graph-findings-by-entity-reachability.md),
[ADR 0039](../docs/adr/0039-ranking-contract-lock-undoing-0036-0038-must-turn-existing-tests-red.md),
restated in [ADR 0040](../docs/adr/0040-no-labelled-public-command-corpus.md)):

| Issuer kind | Moved up | Unique lead | n |
| --- | ---: | ---: | ---: |
| Known-station (`scada` / `hmi`) | 6 | **0** | 16 |
| Unknown-master (silent `engineering`) | 4 | **1** | 4 |

The **1 of 4** is a D2 diagnostic with the standing caveat that an attribution rank is **not**
a detection rate. It is not ≥70%. It is not a field rate. It must not be pooled with known-
station **0 of 16**. False positives on that synthetic unknown-master corpus remain
**1.1650 per normal hour**. Do not quote its recall as detection.

Green tests prove the plumbing. They are not a licence to sit this engine on a live plant.
Nothing in this repository is live-plant ready.

## What this is not

- Not a labelled public command corpus. Data4Cyber is readable Modbus traffic with process-phase
  labels. It is **not** command-action ground truth.
- Not the ≥70% cycle command contract. Completing sessions 1–5 did **not** earn it.
- Not a Data4Cyber false-alarm rate. Not parquet-as-pcap. Not 3W-as-attack.
- Not a reason to grow the synthetic unknown-master battery until a denominator appears.
- Not a live-plant product. Public-data results are not a deployment. There is no
  ten-day ship plan in this repository. Live sites remain unauthorized
  ([ADR 0040](../docs/adr/0040-no-labelled-public-command-corpus.md)).

## Where to read more

- The refusal: [ADR 0040](../docs/adr/0040-no-labelled-public-command-corpus.md)
- What command evidence can and cannot tell apart:
  [Atlas: listening to commands](07-atlas-listening-to-commands.md)
- How silence and story attachment were made honest before this session:
  [silence, clocks, and who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md)
