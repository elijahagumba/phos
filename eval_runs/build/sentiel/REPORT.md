# Sentiel investigation

CCH0959 is Cedric Cyrus Harrison, an industrial engineer. From 2 August to
30 September 2010 he did two things. Through August he browsed job sites and
sent seven messages to Mario.Truman.Telsa@lockheed.com, each ending in the
words "resume salary position management experience". In September he connected
a thumb drive more often, still on his own machine, PC-0588, and on 14
September he mailed his supervisor that he was resigning.

Sentiel's 34 features count how many hosts, files, messages and drive
connects a person has. They do not say which host or which recipient. His
counts barely moved. He already logged on once a day, already used one
machine, and already copied about two files to a drive. The labelled days
rise to a median of three connects and three or four copies. Seven connects
rank about 14,200th in the cache. Ten file copies rank about 14,700th. The
job pages sit inside days of about 60 hosts, so the host count does not move
either. The frozen scorer's best day for him is 3 September, score 9.20,
rank 957 of 210,814. The 48-alert cut is 13.70.

The part that is actually rare is a return to a web host nobody else has
used. From 1 July that happens on 23 person-days: 20 of his, on
lockheedmartinjobs.com and lockheedmartin.com, and 3 of CSF0929's, on
wikileaks.org. No one else does it. A host counts only after the first
visit, which is why the earlier "new name" scores missed the month of
repeats. The first lockheedmartinjobs.com page is on 2 August, and that
midnight is outside his label.

## What was built

One challenger, `exclusive-host-return`, declared in ADR 0195 before this
score. A person-day scores the number of hosts that the same person
requested on an earlier day and that nobody else had requested before that
day. The 34 features and the frozen 6B sum were left alone. The queue is
the same 210,814 person-days, ranked by `(-score, user_id, timestamp)` and
cut at 48.

## Whether it worked

It did, on r3.1.

| | |
| --- | ---: |
| CCH0959 best rank | 1 |
| CCH0959 labelled days in the top 48 | 20 |
| CSF0929 labelled days in the top 48 | 3 |
| Malicious days in the 48 | 23 |
| Precision at 48 | 0.479 |
| Chance | 0.012 |
| Innocent people in the 48 | 1 |
| Innocent people with a score above 0 | 0 |

The one innocent person is AAC0070. All 25 of the remaining slots are his
days at score 0. The rank key breaks ties by user id, and 23 positive days
leave 25 slots. The signal did not mark him. It marked only the two
insiders, on 23 days.

The 20 days are the August job-site returns plus 1 September. The later
September drive days stay at 0. The signal finds the repeated exclusive
host. It does not find the thumb-drive counts.

No refinement was made. `decisions.md` records that.

CERT r4.2 was not fetched and not scored. ADR 0196 reserves the one-shot:
scorer `exclusive-host-return`, budget 48, result name
`exclusive-host-return:cert-r4.2@48`, command
`uv run python scripts/score_exclusive_host_return.py --release r4.2 --out eval_runs/build/sentiel/exclusive-host-return-r42.json`.
That command refuses today.

## Correction at merge (19 October)

Read with ADR 0195's note and ADR 0196's amendment. The r3.1 count was known from the
investigation before the hypothesis was declared, so it describes r3.1 rather than testing it.
Counting only real alerts, the signal raises 23 alerts on r3.1 and all 23 are labelled; the
0.479 figure counted 25 zero-score tie days. In r3.1 no innocent user ever returns to a host nobody
else has used, which may be an artefact of how CERT generates its data. r4.2 will report the realism
check declared in ADR 0196.
