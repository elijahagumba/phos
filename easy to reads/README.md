# Easy to reads

Plain-English walkthroughs of what PHOS has actually built, and — just as important — what the
measurements refuse to let us claim.

These notes are for anyone who should not have to start at the architecture decision records. They
use everyday analogies. They do not replace the technical record. If a number here disagrees with
`PROGRESS.md`, an ADR, or `eval_runs/log.jsonl`, those files win.

The complete path-level reference (every package, ADR, frozen number, and absence) is
encyclopedia/ (lab record, not published). Use that when you need a file name, not a story.

## How to use this folder

Read them in order the first time. After that, jump.

1. [What PHOS is](01-what-phos-is.md) — two engines, one idea, and why one universal model would fail
2. [One shared language](02-one-shared-language.md) — the vocabulary every screen and engine must use
3. [How we keep score](03-how-we-keep-score.md) — catching incidents vs drowning operators
4. [Learning what normal looks like](04-learning-what-normal-looks-like.md) — study, then sit a test you have never seen
5. [Competing explanations](05-competing-explanations.md) — a shortlist, not a genius detective; a ceiling tie is silence
6. [Atlas: the plant as one machine](06-atlas-the-plant-as-one-machine.md) — the industrial engine
7. [Atlas: listening to commands](07-atlas-listening-to-commands.md) — watching who turns the valves; known-station 0/16, unknown-master unique lead 1/4 (a diagnostic, not ≥70%)
8. [Plants we built to break Atlas](08-plants-we-built-to-break-atlas.md) — crash-test dummies; hostile 04–07 measured as software-survival on a separate report, not as detection
9. [When the recipe changes](09-when-the-recipe-changes.md) — batch processes and settling
10. [Sentiel: watching people, not plants](10-sentiel-watching-people-not-plants.md) — the enterprise engine
11. [Data hygiene and label disagreements](11-data-hygiene-and-label-disagreements.md) — files beat papers
12. [The distillation column: first number](12-batch-distillation-todays-work.md) — first non-water plant, first honest (loud) number
13. [Quieter queues, unknown masters, and busy days](13-quieter-queues-and-honest-ranking.md) — gating, command ranking, SOC scoring; contracts still unearned; alphabetical first place is not a unique lead
14. [The dataset library is not a public corpus](14-the-dataset-library-is-not-a-public-corpus.md) — 342 windows and 2,400 person-days we designed; dwell and chronic measured; cycle budgets still unearned
15. [Silence, clocks, and who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md) — comparable-stretch silence; stories attach by shared device, not by sharing a clock
16. [The public command capture we do not have](16-the-public-command-capture-we-do-not-have.md) — Session 5 complete by refusal; Data4Cyber packets are readable, labels are process phases, not command ground truth
17. [The public record must move with the code](17-the-public-record-must-move-with-the-code.md) — every `main` advancement updates encyclopedia, these notes, and README (ADR 0044)
18. [A grid we measured without claiming a control room](18-a-grid-we-measured-without-claiming-a-control-room.md) — Data4Cyber Track A; 6.6× is not 10×; FP/hour refused; not a command corpus
19. [A battery table with no captions](19-a-battery-table-with-no-captions.md) — S7 process parquet has no labels; labelled Track A refused; packets still not a pcap
20. [The recipe log made Atlas louder](20-the-recipe-log-made-atlas-louder.md) — distillation `Executing step` joined; phase-conditional recall up, false alarms up; 2–3/day still refused
21. [The stamps that public files cannot give](21-the-stamps-public-files-cannot-give.md) — Session C0: split scorecard; 70%/10×/2–3 on ZIPs are not pass/fail
22. [The snapshot model says what it assumes](22-the-snapshot-says-what-it-assumes.md) — Session C1: temporal independence, linear feasible set, named breaks (ADR 0050)
23. [Loud is a refuse, not a quieter number](23-loud-is-a-refuse.md) — Session C2: opt-in `REFUSED` when FP/hour crosses a declared line (ADR 0051)
24. [Scale is a named option; 10× is a table](24-scale-is-an-option-ten-x-is-a-table.md) — Sessions C3–C4: within-mode standardisation; joint-vs-univariate table (ADR 0052–0053)
25. [Dynamics are an experiment; switching can starve](25-dynamics-are-an-experiment.md) — Sessions C5–C8: VAR residual; starved-mode fallback; matching-physics forgery unhandled (ADR 0054–0055)
26. [Faults stay faults; stamps stay stamps; work orders stay empty](26-faults-stamps-and-empty-inlets.md) — C9, D, E: 3W faults; command stamp; reconstructability; still no public command corpus; work-order inlet (ADR 0056–0059)
27. [Sentiel routing is written; the partner is the next gate](27-sentiel-routing-and-the-partner-gate.md) — S1–S5, Ω1–Ω2: peer routing without rewriting 6B; CERT curve; Clock A published; P1 blocked (ADR 0060–0061)
28. [The ruler we froze before we tuned](28-the-ruler-we-froze-before-we-tuned.md) — PHOS Benchmark v1 cites frozen public rows and refuses the rest; Clock B is research, not a skip of the partner conversation
29. [Three roles are not the same plant](29-three-roles-are-not-the-same-plant.md) — Declared flow/pressure/pump transfer; BATADAL→HAI zero-shot is louder than in-plant HAI; SWaT form-gated (ADR 0063)
30. [Yesterday's plant is not today's snapshot](30-var-on-hai-is-louder.md) — VAR(1) on HAI is louder than snapshot Mahalanobis; refused as the public detector (ADR 0064)
31. [The 48 alerts are not one stem](31-the-48-alerts-are-not-one-stem.md) — CERT 6B top-48 autopsy: no stem led every hit and none of the misses, so there is no quieter family detector (ADR 0065)
32. [Yesterday's covariance is not a correlation we can invert](32-correlation-cannot-invert-on-hai.md) — correlation-target Mahalanobis singular on HAI; do not retune shrinkage (ADR 0066)
33. [The queue is sorted the wrong way round](33-the-queue-is-sorted-the-wrong-way.md) — 424 alerts, 6 real, and every severity Atlas carries sorts the real ones to the back; the flattering 0.1250 was the clock, not the detector (ADR 0068)
34. [The alibi nobody ships](34-a-work-order-is-the-alibi-nobody-ships.md) — SAP PM / Maximo exports finally reach the work-order inlet; no public corpus ships one, so coverage stays refused (ADR 0069)
35. [The facet a sentence should not have been carrying](35-the-facet-a-sentence-should-not-have-been-carrying.md) — four matchers decided an explanation's role by parsing a prefix off human-readable prose; the fact is now a typed field and every verdict is proved identical (ADR 0070)
36. [The evidence we were throwing away](36-the-evidence-we-were-throwing-away.md) — Atlas measured how devices command, stamped it, stored it, and discarded the meaning at the last step; it now reaches the two explanations about somebody operating a device, and supports both equally because nothing in the data says which (ADR 0071)
37. [A person is not a day](37-a-person-is-not-a-day.md) — grouping Sentiel's person-days into episodes shows 9 malicious entity-days at budget 48 against a per-day 5; that difference sits inside chance (ADR 0072, ratio withdrawn by ADR 0076 / R18)
38. [The writes that were not doing anything](38-the-writes-that-were-not-doing-anything.md) — the simulator's control-network writes were cosmetic, so two built capabilities could never be tested; writes now cause the process to move, authority is declared, and a maintenance calendar that cannot see the attacks makes both **exercisable** — tooling, not capability, and no number moved (ADR 0073)

39. [The phase that is allowed to fail](39-the-phase-that-is-allowed-to-fail.md) — after four honest negatives in a row, the pivot from *does it work* to *is it useful to a human*; two hard stops an agent may not pass, and "this does not work" written in as a permitted result (ADR 0074)

40. [The alarms were never about the plant](40-the-alarms-were-never-about-the-plant.md) — the same fitted model alarms on 55.74% of sixty hours of declared-normal HAI it never saw, against 55.81% of the slice that produces 53.26/hour; the false alarms are a 29-minute fit of a 3.15-hour cycle, not a fact about the plant. Nothing was retuned and 53.26 still stands (ADR 0075)
41. [Twelve situations Atlas cannot tell apart in advance](41-twelve-situations-atlas-cannot-tell-apart-in-advance.md) — a diagnostic plant where the missing kinds of trouble can actually happen; four questions answered as SYNTHETIC-DERIVED, not as detection (ADR 0078)
42. [An alert you can read without a probability](42-an-alert-you-can-read-without-a-probability.md) — U4 plain-English narrative render; unresolved is first-class; Sentiel's depth-blind ceiling appears in the page itself (ADR 0079)
43. [A study without operators is not a field result](43-a-study-without-operators-is-not-a-field-result.md) — U5 three-arm instrument; crude non-operator run; not operational usefulness (ADR 0080)
44. [A list of what we cannot do is a deliverable](44-a-list-of-what-we-cannot-do-is-a-deliverable.md) — U6 confirms the refusal register against HEAD; four entries had drifted and were rewritten (ADR 0081)
45. [Teaching Atlas from ordinary days, not from the attack file](45-teaching-atlas-from-ordinary-days.md) — normal-score CDF (ADR 0083): HAI 3.55 FP/hr logged beside frozen 53.26; distillation parity; incomplete dual win
46. [Fourteen voices or none](46-fourteen-voices-or-none.md) — Sentiel needs 14 of 34 measurements to agree before a day can alert, and the insider it misses never gave it 14; ADR 0084 opens the non-saturating aggregation session with its rules fixed before any try; three formulas are declared in note 54 and none is scored
47. [The fifteen-second gap was ordinary](47-the-fifteen-second-gap-was-ordinary.md) — command behaviour learned from the gaps that happened, at the bell curve's own tail; on twenty simulated operator runs, false alarms went from 0.75 per run to 0.20, and the unauthorised write is still in the brief on 20 of 20 (Gaussian 19 of 20); seed 11 still raises one ordinary-run alarm, on a different feature (ADR 0086)
48. [Five editions of the same plant, one of them on the shelf](48-five-editions-of-the-same-plant.md) — every HAI file is named in the registry; the later editions are not downloaded, because some are Git LFS pointers and the oldest is not a comma-separated file (ADR 0087)
49. [A score for when the alarm is a bit early](49-a-score-for-when-the-alarm-is-early.md) — eTaPR checked against the authors' package on a hand-built case; recall inside an eight-hour shift, with the alert count left as an argument (ADR 0088)
50. [Three published detectors, checked against their own table](50-three-published-detectors.md) — MinMax, Steadytime and Histogram from Wolsing et al. 2022, run on HAI 20.07; the paper's point scores were not reproduced (ADR 0089)
51. [The authors' own alarms match ours](51-the-authors-own-alarms-match-ours.md) — their pipeline on HAI 20.07 raises the same alarms as note 50, and still not the paper's 73 and 7 (ADR 0090)
52. [The contest's four knobs](52-the-contests-four-knobs.md) — HAICon 2020 published pi 0.7, rho 0.1, alpha 0.5 and a 180-sample tail; the tail does not fit the fractional delta (ADR 0091)
53. [The long tests are the real files](53-the-long-tests-are-the-real-files.md) — the half-hour suite was the downloaded corpora; the ordinary run leaves them out, and the full run puts them back (ADR 0092)
54. [Three formulas, before any score](54-three-formulas-before-a-score.md) — the three ways Sentiel might add a deep day without fourteen signals at once, written down before any of them is tried on the insiders (ADR 0093)
55. [The liar is named before it is run](55-the-liar-is-named-before-it-is-run.md) — 360 held-out liar runs, seeds 94001-94020, and a pass mark of more than half, written down before any of them is scored (ADR 0094)
56. [The first table, and where Atlas loses](56-the-first-table-and-where-atlas-loses.md) — eight alerts a shift: Atlas is behind a range check on both scored HAI editions, ahead on the water network, and two HAI editions are not scored (ADR 0095)
57. [The eight HAI 21.03 files have checksums](57-the-eight-hai-files-have-checksums.md) — all eight payloads are on disk, each with a sha256, and they are not in git (ADR 0097)
58. [Two later HAI editions are files, and nothing has been scored on them](58-two-later-hai-editions-are-files.md) — 22.04 and 23.05 match their Git LFS checksums and stay unscored (ADR 0098)
59. [Grouping is written down before it is scored](59-grouping-is-written-down-before-it-is-scored.md) — one shared rule, the sandbox's seconds, and no corpus scored (ADR 0099)
60. [Grouping raises the count, and Atlas still loses](60-grouping-raises-the-count-and-atlas-still-loses.md) — the same rule on every detector: Atlas 23/38 and 15/50 against a range check at 32/38 and 36/50, both rows seen (ADR 0100)
61. [The next look is written down before it happens](61-the-next-look-is-written-down.md) — HAI 22.04 and 23.05, denominators 58 and 52, one command, not yet run (ADR 0101)
62. [The clean look, and Atlas loses both](62-the-clean-look-and-atlas-loses-both.md) — 5/58 against 6/58, and 3/52 against 4/52; grouping leaves Atlas behind on both (ADR 0102)
63. [The frozen candidate gets one look, written down first](63-the-frozen-candidate-gets-one-look.md) — the 4 October detector, its own grouping and the shared wrapper, declared before it is scored on HAI 22.04 and 23.05 (ADR 0103)
64. [The frozen candidate on clean HAI](64-the-frozen-candidate-on-clean-hai.md) — 53 of 58 and 36 of 52, margins of 43 and 30 past the grouped range check; seen by this detector, and not a judgement of Atlas (ADR 0104)
65. [Four checks, written down first](65-four-checks-written-down-first.md) — chance, the driving measurement, the two controls, and whether the two rows were different lists, declared before they run (ADR 0105)
66. [Four checks on the frozen candidate](66-four-checks-on-the-frozen-candidate.md) — random alerts average about 4 and 3, one valve command drives 11 of 53, and the two controls land on 21 and 15 (ADR 0106)
68. [The first parallel build](68-the-first-parallel-build.md) — reports and the command check land on main; naming 96 of 156, confidence not yet honest (ADRs 0155–0163)
69. [Naming the lying sensor](69-naming-the-lying-sensor.md) — 146 of 150 unseen runs named right; a real wind farm stays quiet; Sentiel still one of two (ADRs 0164–0194)
70. [The sealed years, and a confidence test that contains mistakes](70-the-sealed-years-and-a-confidence-test.md) — Kelmarsh 2023–2024 scored once; confidence did not separate right from wrong; 4SICS has no catches (ADRs 0174–0178)
70. [Quiet on years it never saw](70-quiet-on-years-it-never-saw.md) — 29 alerts in two unseen years on a real wind farm, 23 explained; confidence and S7 not there yet (ADRs 0174–0178)
71. [A signal we do not trust yet](71-a-signal-we-do-not-trust-yet.md) — returns to sites nobody else uses find both insiders, possibly because of how the dataset was made (ADRs 0195–0196)
72. [Six of twelve](72-six-of-twelve.md) — v1 at 6 of 12: one configuration holds; the queue ranking and the Sentiel signal fail their one look; S2 not counted (ADRs 0202–0230)
73. [The queue, and the explanation](73-the-queue-and-the-explanation.md) — build D merged: no ranker beats the champion, and the oracle stops at 21 of 38; 60 of 60 on the same five scenarios, and the high mark cannot reach its line; a trusted station still leads 0 of 20 (ADR 0260)
74. [Which address, not which machine](74-which-address-not-which-machine.md) — v1 at 7 of 12: S2 names directory email addresses on both CERT releases; websites and computers stay unnamed (ADRs 0261–0262)
75. [The table comes back the same](75-the-table-comes-back-the-same.md) — v1 at 8 of 12: the four validation datasets were scored again and the table matched; the grouped block was not recomputed (ADR 0264)
76. [The rules nobody was reading](76-the-rules-nobody-was-reading.md) — the always-apply rules had never loaded in one of the two tools, and the progress counter nothing incremented; no measurement, no result moved (ADRs 0265, 0266)
77. [The public tests, and the one command](77-the-public-tests-and-the-one-command.md) — the public copy had been failing twenty-six tests for days: twenty-one wanted role declarations its ignore list was dropping, four wait for frozen experiment files it does not carry, and one needed a second fingerprint for the sanitised log (ADR 0267)
78. [The second way to ask who is new](78-the-second-way-to-ask-who-is-new.md) — S3's second challenger, writing to a colleague never written to before, surfaced 21 insiders against the old scorer's 59, below a random draw's 35.29 and adding nobody it misses; S3 stays not met and v1 stays 8 of 12 (ADRs 0270-0272)
79. [The numbers come back from the files](79-the-numbers-come-back-from-the-files.md) — one command now rebuilds four of the five v1 records from the recordings, grouped block included, and every digit matched; A7 still fails on three frozen constants that cannot be regenerated and on the outside run (ADRs 0268, 0269)
80. [The plan for a stronger engine](80-the-plan-for-a-stronger-engine.md) — the goal is an engine genuinely better than v1's, so: let it see commands, judge the sensors together, add up small changes over time, let the prediction bend — and build our own plant first, because no usable real data is left to practise on (ADR 0273)
81. [The machine that had never spoken](81-the-machine-that-had-never-spoken.md) — the engine now sees who gave the orders: 87 of 120 attacks against 49, and an attacker quietly mapping the plant goes from 0 of 20 to 20 of 20, with no new false alarms; the harder question could not be asked (ADRs 0275, 0276)
82. [The patient detector that arrives late](82-the-patient-detector-that-arrives-late.md) — keeping a running tally of how wrong each instrument has been catches the frozen sensor 10 times out of 10 instead of 1, and 53 attacks instead of 32, losing none — and it was turned down, because it notices four seconds later and a bolted-on column cannot win an alert in this engine without also moving that alert's timing (ADR 0286)
83. [The session that thought the project was parked](83-the-session-that-thought-the-project-was-parked.md) — a fresh session in another tool reads the rules, reads the tracker exactly as told, and concludes the project is parked on a blocked conversation, because every rule still names P1 and none mentions the live engine programme; one signpost file fixes it and lifts nothing (ADR 0287)
84. [The model that understood too much](84-the-model-that-understood-too-much.md) — letting the engine's prediction bend cut false alarms from 28 a day to 20 and wrong maintenance alerts from 5 in 20 to 1, and it caught eight fewer attacks at every setting, because a cleverer model also explains the attack; the old model's crudeness was doing work (ADR 0288)
85. [The record the front page could not show](85-the-record-the-front-page-could-not-show.md) — ninety-four build-record files never reached the public copy because its ignore list dropped `eval_runs/build`, the scorecard among them (ADR 0289)
86. [The bar that was measuring the wrong thing](86-the-bar-that-was-measuring-the-wrong-thing.md) — A3's top tenth was one slot, because the shift queue is shorter than eight alerts; the fraction is retired and four bars are frozen in operator units (ADR 0290)
87. [Two branches, one number](87-two-branches-one-number.md) — the same decision number was taken twice because each session looked only at its own branch; a check now refuses a number another branch already used for a different record, and does not reopen the clash already settled (ADR 0292)
88. [A table with no messages](88-a-table-with-no-messages.md) — the one kept lane reads control messages, and the recordings the shipped engine was scored on are sensor tables; with no messages the extra columns are zeros and the alerts stay, shown on a made-up table, and the recordings were not opened (ADR 0293)
89. [Three rescues, and one question still unasked](89-three-rescues-and-one-question-still-unasked.md) — the package, the one look, the new alert-placement rule, and keeping both bent and straight scores are refused; the plant-ratio attacker waits on a declaration that does not mention the detector's line (ADR 0294)
90. [The flow is on or off](90-the-flow-is-on-or-off.md) — the bottle plant's outflow is a fixed rate or zero, so the new attack nudges the level by 3 to 8 percent and sets the flow to the legal value, written down before any detector runs (ADR 0295)
91. [The joint look caught fewer](91-the-joint-look-caught-fewer.md) — on the development runs the joint column caught 15 of 32 attacks and the shipped engine caught 16; the new attack was 2 of 4 for each, and the nudge was not changed (ADR 0296)
92. [The stronger engine was not reached](92-the-stronger-engine-was-not-reached.md) — the four-lane programme is closed; one change was kept, two gains were turned down, the joint look caught fewer, and the empty numbers are not a to-do list (ADR 0297)
93. [Five questions, none of them a promise](93-five-questions-none-of-them-a-promise.md) — the next programme asks five questions and assumes none will work; the first job is a fair test of the engine we already have (ADR 0298)
94. [The release note adds no measurement](94-the-release-note-adds-no-measurement.md) — the public cards stay, and one page restates the recorded figures; three drafted sentences had rounded a band toward its flattering end (ADR 0299)
95. [A kept day halves what is left](95-a-kept-day-halves-what-is-left.md) — a day that counts cuts the remaining misses of one class in half, inside the same eight alerts a shift and without more false alarms; five such days would be a 32-fold cut, and none of that has been measured (ADR 0300)
96. [The in-range command is declared](96-the-in-range-command-is-declared.md) — the test writes the setpoint inside the band operators already use and holds the inlet valve off, and the engines we already have have not been scored on it yet (ADR 0301)
97. [Go and look](97-go-and-look.md) — a download, an upload, and an online edit are three acts, a register write is none of them, and an unbooked one says go and look with both stories kept (ADR 0302)
98. [Eight on the page](98-eight-on-the-page.md) — an unbooked program change keeps a place among the eight alerts a shift, and a booked one does not (ADR 0303)
99. [More incidents in the same eight](99-more-incidents-in-the-same-eight.md) — counting the repeats of one incident once lets five incidents fit where three did, and the page stays at eight (ADR 0304)
100. [Two setpoints together](100-two-setpoints-together.md) — one setpoint inside the ordinary band is quiet, and two tags moving together are one move (ADR 0305)
101. [The booking that would decide](101-the-booking-that-would-decide.md) — the page names the booking that would take the alert down, and supplying it does not pick a story (ADR 0306)
102. [A slow walk across the band](102-a-slow-walk-across-the-band.md) — one tag stepped 720 times inside the ordinary band is invisible to the joint check, and 719 steps are not enough (ADR 0307)
103. [Both classes on one page](103-both-classes-on-one-page.md) — four joint moves and four walks, each checker misses half, and together the page of eight misses none (ADR 0308)
104. [The engines we have caught every one](104-the-engines-we-have-caught-every-one.md) — on a simulated plant both engines caught all 13 in-range commands, so no new detector was built (ADR 0309)
105. [The same value, after the window](105-the-same-value-after-the-window.md) — a second tag takes the same ordinary number after the joint window, the stack misses all twelve, and a page of eight misses four (ADR 0310)
106. [All three on one page](106-all-three-on-one-page.md) — two joint moves, two walks, and eight handoffs; the stack misses all eight handoffs, and the shared page misses four (ADR 0311)
107. [The transfer keeps its place](107-the-transfer-keeps-its-place.md) — four unbooked program changes stay when eight handoffs fill the page, and a booking that names both tags clears a handoff without picking a story (ADR 0312)
108. [One slow walk was missed](108-one-slow-walk-was-missed.md) — on a simulated plant both engines missed 1 of 9 slow walks, so the detector written down beforehand may be built, and it is not built in that record (ADR 0313)
109. [The walk column is written down before it is scored](109-the-walk-column-is-written-down-before-it-is-scored.md) — the inlet valve against the controller's own constants, declared and not yet scored (ADR 0314)
110. [The walk column missed the same one](110-the-walk-column-missed-the-same-one.md) — scored once, it missed the same 1 of 9, and it is not kept (ADR 0315)
111. [The joint command is declared](111-the-joint-command-is-declared.md) — two setpoints move together, the tank's inside the band operators already use and the bottle's inside 1.3 to 2.0, and the engines we already have have not been scored on it yet (ADR 0316)
112. [A broken law is a slot](112-a-broken-law-is-a-slot.md) — a slot exists only when a declared law is false, time orders the page, and fewer than eight is a complete page (ADR 0317)
113. [An undeclared law is silence](113-an-undeclared-law-is-silence.md) — a plant names the laws in force, an empty register is silence, and a slot for an undeclared name is refused (ADR 0318)
114. [Only a broken law takes a slot](114-only-a-broken-law-takes-a-slot.md) — a declared law is held, broken, or unstated, and only broken takes one of the eight places (ADR 0319)
115. [An unnamed station is silence](115-an-unnamed-station-is-silence.md) — a write from outside the declared set is one break, an empty set is unstated, and a station the plant named does not break this law (ADR 0320)
116. [The controller comparison is true or false](116-the-controller-comparison-is-true-or-false.md) — agreement is silence, disagreement is one break per side, and manual mode is unstated (ADR 0321)
117. [A slot enters only as a law break](117-a-slot-enters-only-as-a-law-break.md) — the exact type is required, and a subclass that carries a magnitude is refused (ADR 0322)
118. [Every sentence names the law it came from](118-every-sentence-names-the-law-it-came-from.md) — the law's name, then the fact, and a score-word is refused (ADR 0323)

## The one sentence to keep

PHOS does not catalogue known attacks. It learns what *normal* looks like, flags statistically
meaningful departures, holds several explanations at once, and **refuses to speak** when the
evidence or the data cannot support a claim.

Nothing in this repository is a live-plant or live-SOC product. Public-data results are not a
deployment.

Session 5 refused a labelled public command corpus. The files were read; the gap is named.

Note 37 groups Sentiel's person-days into episodes: 9 malicious entity-days at budget 48
against a per-day 5. That difference sits inside chance (permuted mean 6.63, 95% [5, 9]);
the ratio once read off it is withdrawn. Two capabilities built properly carry nothing on
this corpus, reported as nulls.

Note 38 fixes a defect in the simulator rather than adding a capability: its control-network
writes were cosmetic, so unauthorised-command attribution and the maintenance join could be
built but never exercised. Both can now be exercised. **Neither is measured**, command lead
stays 0 of 16, and an engineer and an intruder still look identical to the evidence.

Note 39 defines the phase after Clock A. Its first job is to find out what kind of
uncertainty generates our false alerts, because *our model is wrong* and *the data could not have
told us* point in opposite directions and PHOS cannot currently tell which it is in.

Note 40 answers that first job. It is *our model is wrong*, in 418 of 418 false alerts, and the
evidence that shows it was already inside the dataset: point the model as fitted at sixty hours of
declared-normal running and it alarms on 55.74% of it. We did **not** make Atlas quieter — 53.26
still stands, nothing was retuned, and the lever that would fix it needs a calibrator that does not
require labelled attacks. What stays blocked on the outside world is narrower than we thought: work
orders, and a second plant.

Note 41 is the place those blocked kinds can be constructed at all. Twelve seeded situations, four
diagnostic questions, and a banner that says SYNTHETIC-DERIVED first. Command attribution sees a
known-station write; a work order moves the story toward maintenance; an attacker inside a
sanctioned window is inspectable on one seed and absent on another; taking the capture away does
not make Atlas more confident. None of it is a detection claim.

Note 42 is the first page a person can act on without a probability. Unresolved is first-class.
Sentiel's depth-blind ceiling is printed on the page.

Note 43 is the study we can run without operators, and why that table is not a field result.
Plant-literate recruiting is U7, which is not started.

Note 44 is the end-of-phase check on the refusal register. Twenty-six entries were re-read
against the code; four had drifted and were rewritten rather than left looking finished. U7
is still not started.

Note 45 records ADR 0083: a normal-score CDF calibrator unlocked a longer HAI fit (**3.55** FP/hr
at recall 1.00), now logged as `hai[designed-normal-score][after]` beside frozen isotonic **53.26**.
Batch-distillation detection stayed at parity with designed. Dual-corpus success was not met.

Note 46 explains the ceiling ADR 0076 found in Sentiel (14 of 34 measurements must agree; 31 of
the second insider's 42 days could never alert) and records ADR 0084 opening the session to fix
it. The rules come first: no dial-turning, no favoured measurements, candidates committed before
they run, and success means the second insider appears without losing the first. Not implemented.

Note 67 is the October build's sealed envelope (ADR 0144). The practice seeds and the held-back
seeds are named, the wind farms and the 4SICS days are split, and ten GRFICS runs are named
before any of those files is opened. The scorecard headings are blank. TU Wien is not in this note.

Note 76 is the orchestration runtime (ADRs 0265, 0266). The six always-apply rule files had never
reached one of the two tools building PHOS, and the role descriptions were repeating frozen figures
from memory — one naming a stage of work that had closed weeks earlier. The progress file every
session is told to update stood two months stale, because the test protecting the frozen numbers
also pinned the counter, so any honest advance would have turned the suite red. The rules now load
from one copy, the role descriptions quote no figures, a script moves the counter from the records
and refuses to touch anything frozen, and the test keeps the contract without the counter. Nothing
was measured; no result moved. Five guards warn before the five expensive mistakes and none has been
turned into a refusal.

Note 77 is the public test failure (ADR 0267). Twenty-one tests were looking for
role files the public ignore list was dropping; those files are declarations, and
the ignore list now keeps them. Four experiment pins skip only when the file is
absent, and still fail here if the bytes move. The old experiment log has two named
fingerprints, one for this checkout and one for the exported copy. The one command
that rebuilds every version-1 number is still open, and the onboarding timer is
still blank.

Note 78 is S3's second challenger (ADRs 0270, 0271, 0272). The register of staff email addresses from note 74 made it possible to ask a question about who, not how many: did this person write to a colleague they had never written to before? It was frozen by fingerprint and declared with its pass rule before r4.2 was opened, then run once. It surfaced 21 of the 70 labelled insiders against the 34-feature scorer's 59, which is also below the 35.29 a uniform daily draw would expect, and all 21 are people that scorer already finds. The reading written before the run explains it: 930 of 930 innocent people have days where they email someone new, so a budget of 48 a day skims the top of an ordinary count. Both S3 shots are spent and neither is rerun. What the register still cannot name is which machine and which website a person touched.

Note 79 is the one command (ADRs 0268, 0269). Four of the five version-1 records are now rebuilt from the corpora rather than checked against fingerprints, the grouped half of the results table included, and all ten rows came back intact across fifty-four digits. Nothing was written and the result log still holds 185 rows. A7 still fails, and the reason is a collision between two of the project's own rules: the three frozen headline numbers cannot be regenerated under their own names, because the freeze requires a new result to take a new name. Narrowing the sentence to the four records that do rebuild would have been a pass bought by rewording, so the criterion is reported as failed instead.

Note 80 is the plan for the engine after version 1 (ADR 0273). The detector v1 ships is good and frozen; the goal for the public release is one that is genuinely stronger. Three measured weaknesses set the agenda: the catches lean on one idea concentrated in one instrument, the engine never sees what the control system commanded, and each sensor is judged alone and only at its loudest. The awkward part is that there is nothing real left to practise on — the five judging datasets have all been seen, the one we may still iterate on already gives 37 of 38, and every other candidate is licence-barred, paywalled, unlabelled or not about the plant. So the first step is generating a plant of our own, with both the readings and the control traffic, half of it sealed. Each step's record number is reserved in advance, so whichever exist are the steps done.

Note 81 is lane 1 of the stronger engine (ADRs 0275, 0276). The engine learns from quiet days which machines normally read from the plant and which normally give it orders, and treats a stranger doing either as worth an alert. On twenty runs it had never seen, with the pass rule committed beforehand, attacks caught went from 49 of 120 to 87, false alarms stayed at 6 of 40, and reconnaissance went from 0 of 20 to 20 of 20 — a thing no reading-only detector can ever see, because an attacker who only looks never moves the plant. It is also shallow: an attacker working from the operator's own machine is not a stranger. The attack that would test the real claim turned out to be physically identical to a genuine maintenance job, so the simulated plant cannot ask that question yet.

Note 82 is lane 3 (ADR 0286). Instead of asking "is this reading badly wrong right now?", keep a
running tally of how wrong each instrument has been and alert when the total stops looking like an
ordinary day. It works: the frozen sensor that the old engine caught once in ten is caught ten times
out of ten, attacks caught go from 32 of 70 to 53, and nothing is lost. It was still turned down,
because it notices four seconds later on the attacks both versions find, and its bar said a bigger
number bought with a slower alarm is not progress. The lasting finding is the reason, not the tally:
in this engine a bolted-on column has to score high to win one of the eight alerts a shift, and
scoring high is the same thing that makes it take over when that alert is raised. Those cannot be
separated without a new alerting rule written beside the frozen one.

Note 83 is what a session in a different tool knows when it starts (ADR 0287). Checked rather than
assumed, before the build moved to Cursor: most of the rule loading works, and six of seven files
arrive unaided. But every one of them, and the progress tracker, still says the live work is a
blocked human conversation, and none of them points at the engine programme that has been running
since 20 October. So a fresh session concludes the project is parked and new work is forbidden. The
fix is one short signpost file that lifts nothing; the deeper contradiction between the lock, the
tracker and the live work is made legible rather than resolved, because resolving it is Elijah's call
and not a tidy-up for whichever session noticed.

Note 84 is lane 4 (ADR 0288). Let the prediction bend, so the engine stops being surprised by a valve
that saturates or a controller sitting in its deadband. It worked on the half it was aimed at: false
alarms on quiet days it had never seen fell from 28 a day to 20, and ordinary maintenance wrongly
alerting fell from 5 times in 20 to 1. It also caught eight fewer attacks, at every amount of bend
tried, and missed the frozen sensor entirely. The reason is the lasting part: the alarm is surprise, a
crude model is surprised easily, and a clever model explains more of what it sees — the attack
included. The old straight line was not purely a defect; its crudeness was load-bearing. Turned down,
because its standard required both halves — and worth noting that the programme has no way to record a
quieter engine as a win, which is a gap in the standard rather than in the work.

Note 85 is the record the front page could not show (ADR 0289). One test was still
failing in the public copy, on a pin inside a folder called `eval_runs/build` that
the public ignore list was dropping as if it held compiled output. Ninety-four
files never arrived, the scorecard among them, so the front page's eight of twelve
linked to a page that was not there. The ignore list now keeps the folder. Nothing
was measured.

Note 86 is the bar that was measuring the wrong thing (ADR 0290). A3's top tenth of
a shift queue turned out to be one slot for four attacks in five, because the queues
are shorter than the eight alerts an operator reads; counted in alerts, 172 of 203
attacks appear in their first shift and none later than the ninth alert. The fraction
is retired as an instrument, A3's 57 of 203 stands unrescored, and Bet 003 freezes
four bars in operator units. Nothing was measured against them.

Notes 85 and 86 were written as notes 78 and 79 on an unmerged branch, at the same time
as the notes that now hold those numbers, and were renumbered on merge (ADR 0291).

The record of that renumber says the public copy was still private, which was true when it was
written. Later the same day the public copy was opened, with the new numbers already in it. The
original sentence stays. Nothing was measured.

Note 87 is two branches, one number (ADR 0292). The same decision number was taken twice
because each session listed the numbers on its own branch and could not see the other. A check
now refuses a new record whose number another branch already gave to a different file. The clash
that was already settled is left settled. Nothing was measured.

Note 88 is a table with no messages (ADR 0293). The one kept lane reads control messages, and
the recordings the shipped engine was scored on are tables of sensor readings. With no messages
the extra columns are zeros, and a column of zeros never opens an alert, so the alerts stay.
That was shown on a made-up table. The recordings were not opened, and the one look has not
been spent. Nothing was measured.

Note 89 is three rescues, and one question still unasked (ADR 0294). The one lane that passed
already has a name, so it is not wrapped up as a stronger engine, and the one look at the old
recordings is not taken. The tally that arrived late is not saved by a new way of placing
alerts. The quieter prediction is not kept beside the sensitive one. The question the
recordings cannot ask yet, an attacker who moves level and flow the way the plant does, waits
on a description in the plant's own units that does not mention the detector's line. Nothing
was measured.

Note 90 is the flow is on or off (ADR 0295). The plant's outflow is one fixed rate while the
outlet valve is open and the tank holds water, and zero otherwise. The attack nudges the level
by 3 to 8 percent, a band already fixed, and sets the flow to whichever of those two values
the nudged level and the real valve allow. No detector has seen it yet. Nothing was measured.

Note 91 is the joint look caught fewer (ADR 0296). On the development runs the joint column
caught 15 of 32 attacks and the shipped engine caught 16. The new attack was 2 of 4 for each.
The nudge was not changed. The sealed runs were not opened. Nothing else was measured.

Note 92 is the stronger engine was not reached (ADR 0297). The four-lane programme is closed.
One change was kept. Two gains were turned down. Looking at the instruments together caught
fewer than the engine already shipped. The empty record numbers are not a to-do list, and
there is no new plan in their place. Nothing was measured.

Note 93 is five questions, none of them a promise (ADR 0298). The next programme writes
the questions down before measuring any of them. The first is whether a command can be
wrong while every sensor looks ordinary, tested first on the engine we already have.
A later test passes only if a candidate catches more attacks inside the same eight alerts
a shift and does not raise more false alarms. Nothing was measured.

Note 94 is the release note adds no measurement (ADR 0299). The public cards stay. One
page restates the figures already on record, including what was turned down. Three
sentences drafted for the announcement had rounded a result toward the end that sounds
better, and those sentences are corrected to the recorded bands. Nothing was measured.

Note 95 is a kept day halves what is left (ADR 0300). The bar for a day is to catch at
least half of the attacks the current engine still misses, inside the same eight alerts
a shift, without raising the false alarms. Five days that clear that bar would leave
one thirty-second of those misses. Nothing was measured.

Note 96 is the in-range command is declared (ADR 0301). The new attack writes the tank's
upper limit inside 6.5 to 7.5, the band an ordinary setpoint already uses, and holds the
inlet valve off. No sensor is rewritten. The two engines already kept have not been run
on it. The slow walk is specified and is not generated unless that run misses nothing.
Nothing was measured.

Note 97 is go and look (ADR 0302). A download, an upload, and an online edit are three
acts. A register write is not one of them. When nothing booked the act, the page says
go and look and keeps both stories. A missing booking is not called an attack. Nothing
was measured.

Note 98 is eight on the page (ADR 0303). An unbooked program change keeps its place
among the eight alerts a shift can show. A booked one does not take a place. The
alert that leaves is another one, the one with the lowest score. Nothing was measured.

Note 99 is more incidents in the same eight (ADR 0304). Three loud incidents were
filling the page by repeating. Counting each incident once leaves room for the two
quieter ones. The misses on that example go from two to none. Nothing was measured.

Note 100 is two setpoints together (ADR 0305). One tag written inside the ordinary
band raises nothing. Two tags close together are one move, timed at the first write.
Twelve of those pairs leave at most half of them off a page of eight. Nothing was
measured.

Note 101 is the booking that would decide (ADR 0306). The alert names the booking
that would take it down. Supplying that booking clears the alert and leaves both
stories in place. Nothing was measured.

Note 102 is a slow walk across the band (ADR 0307). One tag, 720 steps inside the
ordinary band, a second apart. The joint check sees nothing. 719 steps are not a
walk. Nothing was measured.

Note 103 is both classes on one page (ADR 0308). Four joint moves and four walks.
Each checker misses the other class, four out of eight. Together, all eight fit and
none are missed. Nothing was measured.

Note 104 is the engines we have caught every one (ADR 0309). On a simulated plant,
both engines caught all 13 of the in-range commands. They also flagged 4 of 17 routine
maintenance jobs. No new detector was built. The slow walk is note 108.

Note 105 is the same value, after the window (ADR 0310). A second tag takes that
number once the joint check can no longer see it. Twelve of those pairs: the page
that holds the other two classes misses all twelve, and keeping eight misses four.
Nothing was measured.

Note 106 is all three on one page (ADR 0311). Two joint moves, two walks, and eight
handoffs. The stack misses every handoff. The shared page misses four of them.
Nothing was measured.

Note 107 is the transfer keeps its place (ADR 0312). Four unbooked program changes
stay when eight handoffs already fill the page. A booking that names both tags
takes that handoff down and does not pick a story. Nothing was measured.

Note 108 is one slow walk was missed (ADR 0313). On a simulated plant, both engines
missed 1 of 9 slow walks and caught the other 8. False alerts were 19 each. The
detector written down before that score may be built, and it is not built in that
record.

Note 109 is the walk column written down before it is scored (ADR 0314). The
inlet valve is compared with the constant the plant's own controller writes, one
sample at a time, and the column is quiet inside the band. It has not been scored
in that record.

Note 110 is the walk column missed the same one (ADR 0315). Scored once, it
missed the same 1 of 9. False alerts stayed at 19. The column is not kept.

Note 111 is the joint command declared (ADR 0316). Two setpoints move together
from the operator's console, and nothing else is rewritten. The engines we
already have have not been scored on it. The new column is described and not
written.

Note 112 is a broken law is a slot (ADR 0317). A slot exists only when a
declared law is false. Time orders the page. Fewer than eight broken laws is
a complete page. Nothing was scored. Version 1 still stands at eight of twelve.

Note 113 is an undeclared law is silence (ADR 0318). A plant names the laws
in force. An empty register stays empty. A slot for a name the plant did not
declare is refused. Nothing was scored. Version 1 still stands at eight of
twelve.

Note 114 is only a broken law takes a slot (ADR 0319). A declared law is
held, broken, or unstated. Held and unstated are listed and take no place. A
missing inlet is unstated. Nothing was scored. Version 1 still stands at
eight of twelve.

Note 115 is an unnamed station is silence (ADR 0320). A write from outside
the declared set is one break. An empty set is unstated. A station the plant
named does not break this law. Nothing was scored. Version 1 still stands at
eight of twelve.

Note 116 is the controller comparison is true or false (ADR 0321). Agreement
is silence. Disagreement is one break per side. Manual mode is unstated.
There is no divisor. Nothing was scored. Version 1 still stands at eight of
twelve.

Note 117 is a slot enters only as a law break (ADR 0322). The exact type is
required. A subclass that carries a magnitude is refused. Nothing was scored.
Version 1 still stands at eight of twelve.

Note 118 is every sentence names the law it came from (ADR 0323). Held,
broken, and unstated each name their law, then the fact. A score-word is
refused. An uncited break is not placed. Nothing was scored. Version 1 still
stands at eight of twelve.

Note 119 is the plan loads before anyone builds (ADR 0324). Both tools load
the same lock. The plan is the sequence. Nothing was scored. Version 1 still
stands at eight of twelve.

Note 120 is the inlet is named before it is built (ADR 0325). Named rows go
in. A function code stays a function code. The declaration opened no capture.
Nothing was scored. Version 1 still stands at eight of twelve.

Note 121 is the inlet copies named rows (ADR 0325). The function exists. The
tests build the rows. Nothing was scored. Version 1 still stands at eight of
twelve.

Note 122 is the front door names the three standings (ADR 0325). Held,
broken, or unstated. Only a broken law takes a slot. Nothing was scored.
Version 1 still stands at eight of twelve.

Note 123 is a named law stays on the list (ADR 0326). A score-word is not
placed. A law this page cannot check stays unstated. Nothing was scored.
Version 1 still stands at eight of twelve.

Note 124 is the front door shows the path (ADR 0327). The page comes first.
The older numbers are labelled as the older engine. A price for the company
has no date. Nothing was scored. Version 1 still stands at eight of twelve.

Note 126 is the name is the plant's word (ADR 0329). A line is refused for the
claim it makes, not for what the plant calls the law. One such name no longer
hides the other broken laws reported with it. Nothing was scored. Version 1
still stands at eight of twelve.

Note 130 is the bar was written down twice (ADR 0333, ADR 0335). A fix moved
one of the four files the bar had pinned, so the bar was written again over
the new code. The eight counts were copied by script and checked to the byte,
not retyped. Nothing was scored. Version 1 still stands at eight of twelve.

Note 131 is the page kept its word, and the plant said nothing (ADR 0336).
All eight counts came back zero, so the bar is met. The plant broke none of
its own laws, so all 104 lines the counts judged came off a page the harness
invents to test its own ordering. An empty page is not a safe plant. Version 1
still stands at eight of twelve.

Note 132 is declined. It is the plain-English companion of a commercial
record, and commercial material is not published (ADR 0342). The number stays
in the sequence so the gap is named rather than vanished; what the note says
is not restated here. The measurement rules do not move. Version 1 still
stands at eight of twelve.

Note 139 is protocols are named before they are read (ADR 0344). Further
industrial languages may be named ahead of a partner's capture, in this
programme only. Each one still needs its own bar before a byte is parsed.
Modbus is still the only one the code reads. Nothing was scored. Version 1
still stands at eight of twelve. Notes 141–151 are reserved for that programme
and are not findings.

Note 140 is the stream stops at a cap (ADR 0345). The caps were written down
before the code: 131072 bytes, 256 conversations, 16 out-of-order pieces, 256
pairs, 60 seconds. The code now exists in two new files the old Modbus path does
not call. A repeat is refused rather than spliced, a gap is waited for rather
than zero-filled, and a length that lies is refused before any byte is removed.
The record that judges it against that bar is not written. Nothing was scored.
Version 1 still stands at eight of twelve.

Note 152 is three witnesses, and a search for what they miss (ADR 0368). The
next Atlas programme is named and waits for the protocol work to close: rules
read from the controller program, physics rules, the engineers' rules, a
prediction of what all three miss, and a search for it. Found attacks stay in
the lab. Nothing was built or scored. Version 1 still stands at eight of
twelve.

Note 154 is the first sentence was not true (ADR 0381). The public front page
opened by claiming a company, and there is none; the sentence is corrected.
Diagrams, mathematics and charts are admitted by decision under the freeze,
every chart value read from the record at build time, and one chart is refused
because the record does not hold it. These notes publish; note 132 is held
back with the commercial record it walks through, and its number stays and is
declined. Nothing was scored. Version 1 still stands at eight of twelve.
