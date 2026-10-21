# v1 scorecard — 8 of 12

20 October 2026, last. The A7 command now rebuilds four of the five pinned records from the corpora and all four matched, grouped block included (ADR 0269), which closes A1's copied-block caveat. A7 stays not met: the benchmark's three headline numbers are frozen constants that cannot be regenerated under their own names, and nobody outside the project has run the command. C2 is the only reachable row left.

20 October 2026, later still. S3's second challenger was declared and scored once and lost: `declared-new-destination` surfaced 21 distinct labelled insiders on CERT r4.2 against frozen 6B's 59, below the chance null of 35.29 and a subset of 6B's set (ADR 0272). S3 stays not met and both its shots are spent. The count does not move. A7 and C2 stay the reachable rows.

20 October 2026, later. A1 is met (ADR 0264): the G1 command recomputed HAI 21.03,
22.04, 23.05 and BATADAL from the files and the table matched. The grouped block
was not rendered again. A7 and C2 stay open.

20 October 2026. S2 is met (ADR 0262): a directory-email register declared in
`cc0eac2` before the score names destinations on CERT r3.1 and r4.2. Hosts and
machines stay unnamed. The 19 October sprint left S2 unmet; that count is the
paragraph under this one.

19 October 2026. The reviewer pass of build brief C counted 7. Elijah counted S2 as not met
(ADR 0230): its six features were scored with an empty register, so every value is zero by
construction, and that does not show which host, destination or machine. The pass sentence for
each row is the one frozen in `docs/v1-roadmap.md` §2.

| # | Verdict | Number | Record |
| --- | --- | --- | --- |
| A1 | met | One command recomputes every corpus, including hai-21.03, hai-22.04, hai-23.05 and batadal, and the rebuilt markdown matches the committed table. The grouped block was a committed copy until ADR 0269; it is now rendered from recomputed scores and matched, so that caveat is closed. | ADR 0264, ADR 0269. `eval_runs/v1/g1-baseline-table.md` |
| A2 | met | 5 of 5 strictly higher than grouped MinMax within 8 alerts a shift (37/38, 42/50, 53/58, 36/52, 5/5); beyond every chance draw on 4. A status, not a held-out verdict. | ADR 0116. `eval_runs/v1/a2-status.md` |
| A3 | not met | 57 of 203 attacks have a true alert in the top 10% of their shift's queue; the bar is 102. hai-20.07 19/38, hai-21.03 14/50, hai-22.04 13/58, hai-23.05 8/52, batadal 3/5. Scored once. | ADR 0212. `eval_runs/build/v1/atlas/a3-queue-rank.json` |
| A4 | met | Consistency evidence separates maintenance from a device fault, which neither path separates alone, on 20 of 20 development and 20 of 20 held-back simulated seeds. | `eval_runs/build/lane-d/REPORT.md` |
| A5 | met | 158 of 180 maintenance alerts close with a cited work order (88%; the bar is 70%). 0 of 80 attack alerts and 0 of 40 disguised alerts close. Simulated; real-world coverage not measured. | ADR 0164. `eval_runs/build/lane-b/REPORT.md` |
| A6 | met | No detector parameter differs between corpora beyond `windows_for_period` applied to each corpus's declared sample period, a rule written before the BATADAL score. No validation corpus was rescored. | ADR 0211. `eval_runs/build/v1/atlas/a6-parameters.md` |
| A7 | not met | One command rebuilds four of the five pinned records from the corpora — the G1 table with its grouped block, A2 status, and both consistency records — and every digit matched (all ten rows `record intact`, 54 digits). The benchmark record is checked, not regenerated: its 646.58, 18.72 and 0.104 are frozen constants, and roadmap §5 rule 2 makes a new result take a new name, so they cannot be regenerated under their own names. Four of five is not every, and nobody outside the project has run it. | ADR 0268, ADR 0269. `docs/reproduce.md` |
| S1 | met | Bet 001 declared, run once on CERT r3.1 and published. All three formulas lost. | ADR 0148 |
| S2 | met | The empty-register zeros stay recorded. A second register, every LDAP email address, was declared before the score (ADR 0261, commit `cc0eac2`). On r3.1, destination sum 1950179, max 29, 310296 days named an address, 2 insiders. On r4.2, destination sum 2274118, max 32, 292539 days named an address, 70 insiders. Host and machine features are 0 because the directory has no such column. The 34 were not weighted. | ADR 0262. `eval_runs/build/v1/sentiel/s2-directory-r31.json`, `s2-directory-r42.json` |
| S3 | not met | Two shots, each declared first and each scored once at 48 tickets a day on r4.2, against frozen 6B's 59 and a chance null of 35.29. `exclusive-host-return` 1 distinct insider; 0 of 930 innocent users have a host no one else requested. `declared-new-destination` 21, a strict subset of 6B's 59, so it adds no person; 930 of 930 innocent users have a positive new-destination day. Neither is rerun. | ADR 0202, ADR 0272. `eval_runs/build/v1/sentiel/s3-r42.json`, `s3-declared-new-destination-r42.json` |
| C1 | met | A report for every registered template, including `insufficient_evidence`; the checker rejects any sentence without a stored evidence id. | ADR 0155. `eval_runs/build/lane-c/REPORT.md` |
| C2 | not met | The onboarding tool suggests a role and kind with evidence, tested on fixtures and HAI 20.07 names. The command runs from `~/dev/phos` and writes a brief; the timed sheet is still blank. | ADR 0220. `eval_runs/build/v1/tools/c2-trial.md` |

## What the sprint moved

Met before and still met: A2, A4, A5, C1, S1. Met in the sprint: A6. Measured once and not met: A3,
S3. Not met: A1, A7, C2, S2.

## Rule check

S3's re-declaration (ADR 0202) was committed before the holdout lift, and the lift before the one
score. ADR 0203 taught the reader r4.2's four extra email columns after the lift, from the headers
only; the labels and the scoring rule were not touched. A3's declaration (ADR 0212) was committed
before the one look. Each result file exists once. Nothing appended `eval_runs/log.jsonl`. The
lanes were merged to `main` in the order tools, Atlas, Sentiel.

## 20 October

Met: A1, A2, A4, A5, A6, C1, S1, S2. Not met: A3, A7, S3, C2. S2's empty-register
files were not overwritten. The directory score's declaration commit precedes the
result files. The G1 regeneration was declared in ADR 0263 and matched (ADR 0264).
A3 and S3 were not rescored. `eval_runs/log.jsonl` was not appended.

## Public tests (ADR 0267)

The public repository's test job was failing 26 tests. Twenty-one were missing
`roles.toml`; the public ignore list now keeps those declarations. Four experiment
pins skip only when the file is absent. The log prefix carries the lab digest and
the exported digest. This does not move a v1 row. v1 stays 8 of 12.
