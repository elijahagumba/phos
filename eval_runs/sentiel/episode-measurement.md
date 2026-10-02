# Sentiel episodes on CERT r3.1 — coverage at an operator budget

**This does not supersede PART 6B.** The frozen row is reproduced from the trace cache
as a gate before any number below is computed, and it is unchanged:

- `aggregate:gaussian:peer set (34 features)` at **48** alerts — precision **0.1042**, window recall **0.5**, sample recall **0.0943**

- Corpus: **210,814** scored entity-days, **53** of them labelled malicious across **2** insider(s)
- Episodes assembled: **40** (compression **12.7** entity-days per episode)
- Seed: `7` — Commit: `9549ebf9a9f7229b96a7af1fd68f5b3a4a5b342b`

## The comparison at a fixed budget

| Budget | Queue | Items read | Entity-days contained | Malicious entity-days shown | Insiders named | Coverage |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 48 | per-day (6B) | 48 | 48 | 5 | 1 | 9.4% |
| 48 | episodes | 40 | 506 | 9 | 1 | 17.0% |
| 20 | per-day (6B) | 20 | 20 | 4 | 1 | 7.5% |
| 20 | episodes | 20 | 289 | 9 | 1 | 17.0% |
| 100 | per-day (6B) | 100 | 100 | 5 | 1 | 9.4% |
| 100 | episodes | 40 | 506 | 9 | 1 | 17.0% |
| 200 | per-day (6B) | 200 | 200 | 5 | 1 | 9.4% |
| 200 | episodes | 40 | 506 | 9 | 1 | 17.0% |

**At 48 items the episode queue shows 9 of 53 malicious entity-days against the per-day queue's 5, and names 1 of 2 insider(s) against 1. It costs 12.7 entity-days per item read. Whether the difference in coverage is separable from chance needs a null beside it, which this comparison does not carry: on CERT r3.1 it is not (ADR 0076, register R18).**

Of the entity-days inside the episodes an analyst reads at budget 48, **458** sit below the anchor threshold — behaviour the per-day queue could not have shown at this budget at all.

## The episodes an analyst would read

| # | User | Start | End | Days | Carried | Peak | Trajectory | Malicious days |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| 1 | `CSF0929` | 2010-07-02 | 2010-07-23 | 12 | 7 | 19.32 | falling | 9 |
| 2 | `DGC0484` | 2010-12-09 | 2010-12-22 | 6 | 5 | 18.63 | rising | 0 |
| 3 | `TDB0268` | 2011-01-04 | 2011-01-08 | 3 | 2 | 18.22 | rising | 0 |
| 4 | `CJP0221` | 2011-01-07 | 2011-01-13 | 3 | 2 | 18.10 | rising | 0 |
| 5 | `DGC0484` | 2010-07-02 | 2010-07-23 | 9 | 7 | 17.84 | falling | 0 |
| 6 | `LXW0999` | 2010-07-17 | 2010-07-19 | 2 | 1 | 17.60 | falling | 0 |
| 7 | `NLR0174` | 2010-07-26 | 2010-08-13 | 8 | 7 | 17.41 | falling | 0 |
| 8 | `BGM0010` | 2011-04-07 | 2011-04-29 | 10 | 9 | 17.13 | rising | 0 |
| 9 | `JZA0447` | 2010-09-28 | 2011-01-21 | 49 | 46 | 17.05 | falling | 0 |
| 10 | `TDB0268` | 2011-05-13 | 2011-05-14 | 2 | 1 | 16.51 | rising | 0 |
| 11 | `CCH0252` | 2010-08-16 | 2010-08-24 | 4 | 3 | 16.15 | falling | 0 |
| 12 | `YEV0902` | 2011-03-15 | 2011-04-25 | 14 | 13 | 16.02 | falling | 0 |
| 13 | `DGC0484` | 2010-10-13 | 2010-10-22 | 4 | 2 | 15.84 | rising | 0 |
| 14 | `CSG0640` | 2010-12-30 | 2011-04-15 | 41 | 40 | 15.70 | falling | 0 |
| 15 | `BSB0995` | 2011-01-09 | 2011-05-01 | 71 | 70 | 15.56 | falling | 0 |
| 16 | `MEL0063` | 2010-07-12 | 2010-09-08 | 20 | 19 | 15.48 | rising | 0 |
| 17 | `RCH0166` | 2011-01-31 | 2011-03-07 | 16 | 15 | 15.33 | falling | 0 |
| 18 | `ZAS0669` | 2010-09-29 | 2010-10-05 | 3 | 2 | 15.31 | rising | 0 |
| 19 | `YXG0504` | 2010-10-09 | 2010-10-15 | 2 | 1 | 15.30 | falling | 0 |
| 20 | `TJC0370` | 2011-02-07 | 2011-03-18 | 10 | 9 | 15.07 | rising | 0 |
| 21 | `YXG0504` | 2010-10-23 | 2010-10-27 | 3 | 2 | 15.05 | falling | 0 |
| 22 | `LMR0049` | 2010-08-24 | 2010-11-04 | 25 | 24 | 15.05 | falling | 0 |
| 23 | `RHB0200` | 2010-07-12 | 2010-08-28 | 15 | 14 | 14.83 | falling | 0 |
| 24 | `QRF0629` | 2011-02-02 | 2011-03-12 | 12 | 11 | 14.82 | rising | 0 |
| 25 | `CJP0221` | 2010-07-15 | 2010-07-22 | 4 | 3 | 14.67 | rising | 0 |
| 26 | `JRV0778` | 2010-09-10 | 2010-10-05 | 9 | 8 | 14.56 | falling | 0 |
| 27 | `DGC0484` | 2010-11-05 | 2010-11-24 | 6 | 5 | 14.44 | rising | 0 |
| 28 | `LUP0038` | 2010-11-10 | 2011-05-13 | 75 | 74 | 14.17 | falling | 0 |
| 29 | `RTH0015` | 2011-02-18 | 2011-03-07 | 6 | 5 | 14.05 | rising | 0 |
| 30 | `CJP0221` | 2011-05-13 | 2011-05-14 | 2 | 1 | 13.97 | rising | 0 |
| 31 | `CBL0969` | 2011-05-13 | 2011-05-13 | 1 | 0 | 13.97 | single | 0 |
| 32 | `ESB0859` | 2010-11-15 | 2010-12-13 | 7 | 6 | 13.96 | falling | 0 |
| 33 | `WAW0624` | 2011-02-25 | 2011-03-10 | 5 | 4 | 13.85 | falling | 0 |
| 34 | `XOH0359` | 2011-01-20 | 2011-01-26 | 4 | 3 | 13.84 | falling | 0 |
| 35 | `YEV0902` | 2010-08-12 | 2010-08-30 | 6 | 5 | 13.84 | falling | 0 |
| 36 | `TKW0289` | 2011-03-27 | 2011-04-27 | 13 | 12 | 13.79 | rising | 0 |
| 37 | `WMH0866` | 2011-02-18 | 2011-03-25 | 12 | 11 | 13.75 | falling | 0 |
| 38 | `ECF0196` | 2011-01-19 | 2011-01-25 | 3 | 2 | 13.72 | rising | 0 |
| 39 | `HAM0510` | 2010-07-02 | 2010-07-03 | 2 | 1 | 13.71 | rising | 0 |
| 40 | `KGM0616` | 2010-09-08 | 2010-09-30 | 7 | 6 | 13.70 | falling | 0 |

## Was the boundary rule fitted? The whole sweep, so you can see it was not

The declared default is a **7-day** gap — inherited from the correlation window
`SentielConfig` already sets — at the **0.90** extension floor. Every other cell was
computed by the same code and is reported here rather than discarded.

| Gap (days) | Floor quantile | Floor score | Episodes | Entity-days | Carried days | Longest |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.50 | 1.594 | 46 | 203 | 155 | 21 |
| 1 | 0.75 | 2.783 | 46 | 130 | 82 | 11 |
| 1 | 0.90 | 4.242 | 46 | 94 | 46 | 5 |
| 1 | 0.95 | 5.365 | 46 | 80 | 32 | 4 |
| 1 | 0.99 | 7.999 | 47 | 60 | 12 | 3 |
| 2 | 0.50 | 1.594 | 45 | 404 | 356 | 106 |
| 2 | 0.75 | 2.783 | 46 | 207 | 159 | 34 |
| 2 | 0.90 | 4.242 | 46 | 112 | 64 | 7 |
| 2 | 0.95 | 5.365 | 46 | 89 | 41 | 5 |
| 2 | 0.99 | 7.999 | 46 | 61 | 13 | 3 |
| 3 | 0.50 | 1.594 | 38 | 1,093 | 1,045 | 232 |
| 3 | 0.75 | 2.783 | 43 | 351 | 303 | 93 |
| 3 | 0.90 | 4.242 | 44 | 158 | 110 | 21 |
| 3 | 0.95 | 5.365 | 46 | 100 | 52 | 6 |
| 3 | 0.99 | 7.999 | 46 | 63 | 15 | 3 |
| 7 | 0.50 | 1.594 | 36 | 4,569 | 4,521 | 238 |
| 7 | 0.75 | 2.783 | 37 | 1,726 | 1,678 | 184 |
| 7 **(declared)** | 0.90 | 4.242 | 40 | 506 | 458 | 75 |
| 7 | 0.95 | 5.365 | 42 | 173 | 125 | 25 |
| 7 | 0.99 | 7.999 | 44 | 74 | 26 | 6 |
| 14 | 0.50 | 1.594 | 33 | 5,297 | 5,249 | 238 |
| 14 | 0.75 | 2.783 | 36 | 3,344 | 3,296 | 184 |
| 14 | 0.90 | 4.242 | 38 | 1,316 | 1,268 | 116 |
| 14 | 0.95 | 5.365 | 39 | 441 | 393 | 55 |
| 14 | 0.99 | 7.999 | 40 | 94 | 46 | 8 |

## Weak-signal accumulation

What accumulating an episode's days added over its single loudest day.

| User | Days | Anchor | Carried | Families in episode | Best single day | Families only carried days spoke for |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `CSF0929` | 12 | 5 | 7 | 4 | 4 | RELATIONSHIP |
| `DGC0484` | 6 | 1 | 5 | 3 | 3 | — |
| `TDB0268` | 3 | 1 | 2 | 2 | 2 | — |
| `CJP0221` | 3 | 1 | 2 | 4 | 4 | — |
| `DGC0484` | 9 | 2 | 7 | 3 | 3 | — |
| `LXW0999` | 2 | 1 | 1 | 3 | 3 | — |
| `NLR0174` | 8 | 1 | 7 | 4 | 4 | — |
| `BGM0010` | 10 | 1 | 9 | 4 | 4 | — |
| `JZA0447` | 49 | 3 | 46 | 4 | 4 | — |
| `TDB0268` | 2 | 1 | 1 | 3 | 3 | — |
| `CCH0252` | 4 | 1 | 3 | 4 | 3 | RELATIONSHIP |
| `YEV0902` | 14 | 1 | 13 | 3 | 2 | DATA_HANDLING |
| `DGC0484` | 4 | 2 | 2 | 3 | 3 | — |
| `CSG0640` | 41 | 1 | 40 | 4 | 3 | RELATIONSHIP |
| `BSB0995` | 71 | 1 | 70 | 4 | 3 | RELATIONSHIP |
| `MEL0063` | 20 | 1 | 19 | 4 | 3 | RELATIONSHIP |
| `RCH0166` | 16 | 1 | 15 | 3 | 2 | DATA_HANDLING |
| `ZAS0669` | 3 | 1 | 2 | 3 | 3 | — |
| `YXG0504` | 2 | 1 | 1 | 3 | 3 | — |
| `TJC0370` | 10 | 1 | 9 | 3 | 3 | — |
| `YXG0504` | 3 | 1 | 2 | 3 | 2 | ACCESS |
| `LMR0049` | 25 | 1 | 24 | 4 | 4 | — |
| `RHB0200` | 15 | 1 | 14 | 3 | 3 | RELATIONSHIP |
| `QRF0629` | 12 | 1 | 11 | 3 | 3 | RELATIONSHIP |
| `CJP0221` | 4 | 1 | 3 | 4 | 4 | — |
| `JRV0778` | 9 | 1 | 8 | 4 | 3 | RELATIONSHIP |
| `DGC0484` | 6 | 1 | 5 | 3 | 3 | DATA_HANDLING |
| `LUP0038` | 75 | 1 | 74 | 4 | 3 | ACCESS, PEER |
| `RTH0015` | 6 | 1 | 5 | 3 | 3 | — |
| `CJP0221` | 2 | 1 | 1 | 3 | 3 | — |
| `CBL0969` | 1 | 1 | 0 | 4 | 4 | — |
| `ESB0859` | 7 | 1 | 6 | 3 | 3 | — |
| `WAW0624` | 5 | 1 | 4 | 4 | 4 | DATA_HANDLING |
| `XOH0359` | 4 | 1 | 3 | 4 | 3 | RELATIONSHIP |
| `YEV0902` | 6 | 1 | 5 | 4 | 4 | RELATIONSHIP |
| `TKW0289` | 13 | 1 | 12 | 4 | 3 | RELATIONSHIP |
| `WMH0866` | 12 | 1 | 11 | 4 | 4 | — |
| `ECF0196` | 3 | 1 | 2 | 3 | 3 | — |
| `HAM0510` | 2 | 1 | 1 | 4 | 4 | — |
| `KGM0616` | 7 | 1 | 6 | 4 | 3 | RELATIONSHIP |

**18 of 40** episodes in the queue gained something from accumulation that no single day of them could have supplied.
- Cross-domain breadth is counted over the FOUR declared BehaviourFamily values, and one of them (PEER) rests on features with no labelled positive anywhere in the data PHOS reads. An episode spanning three families is close to the ceiling, not modestly broad, and no ratio here should be read without n_families_available beside it.

## The declared graph, and what it could and could not be asked

DECLARED GRAPH: 1,000 users, 1,000 accounts, 999 reporting lines (0 unresolvable, 1 rootless). Distinct values per level: business_unit=1, functional_unit=6, department=22, team=37. Levels that separate nobody: business_unit. No user-device or user-resource edge exists — the directory declares none.

- r3.1's directory puts all 1,000 employees in business unit '1', so DeclaredRelation.ORG_UNRELATED — the directory knows both people and places them nowhere near each other — NEVER OCCURS on this corpus. A path finding cut at that relation would read zero on every entity-day for a structural reason and would be mistaken for a measured negative. The cut is therefore DISTANT_HOPS, one level in, decided from the directory's own shape: department takes 22 distinct values, business unit takes one.
- CERT r3.1 DECLARES NO USER-TO-DEVICE RELATIONSHIP. The LDAP directory carries role, unit, supervisor and email and nothing about machines; psychometric.csv carries five personality scores. Every user-device pair in the release exists only in the activity logs, so any 'this person has no relationship to that machine' edge would be inferred from behaviour — the circularity this graph refuses. No such edge is built, and no path finding rests on one.
- CERT r3.1 DECLARES NO OWNER FOR ANY FILE OR WEB HOST. Filenames and hosts appear only as fields of activity rows. A 'resource this person should not reach' claim would therefore be a claim about what they have reached before, which is the self-baseline PART 6A already measures, not a statement about declared structure.

### Path findings — firing rates, not detection rates

| Finding | Entity-days it fired on | Labelled malicious | Chance would give | Beats chance |
| --- | ---: | ---: | ---: | :---: |
| `distant_internal_recipients` | 132,513 | 35 | 33.3 | yes |
| `max_declared_hops` | 191,966 | 52 | 48.3 | yes |
| `mean_declared_hops` | 191,966 | 52 | 48.3 | yes |
| `shared_device_distant` | 35,842 | 3 | 9.0 | **no** |

Declared role-interaction policy verdicts: **INSUFFICIENT=1,202,878**.

- PATH FINDINGS HAVE NO LABELLED POSITIVE ON CERT r3.1. The two labelled insiders are scenarios 1 and 2 — a user who begins working after hours and using removable drives, and a user who escalates thumb-drive use before leaving. Neither is a path scenario. The CERT scenarios that ARE path-shaped — 3 (a sysadmin plants a keylogger on his supervisor's machine and then logs in as him) and 4 (a user works from another user's machine) — appear in r4.2 and r5.2, whose event archives are not on disk. Anything measured here describes how often these findings FIRE, never how well they DETECT.

## Sequence anomaly

- Alert cut, read off the attack-free training distribution: **6.9272** nats per gram
- Entity-days clearing it: **2,108**, of which **1** are labelled malicious — chance alone would give **0.5** (above chance)
- Rank agreement with the order-blind baseline: **0.642**

- Every PART 6B count feature is invariant to the order of an entity-day's events: sums and cardinalities cannot see order. So a sequence score can only earn its place by firing where the counts do not. SequenceScores reports the ordered surprise beside the bag-of-tokens surprise on the same day, and the run-level report gives their rank correlation, because a sequence score that merely re-expresses volume is a more expensive way to say nothing.

## Findings a reader must not miss

- r3.1's directory puts all 1,000 employees in business unit '1', so DeclaredRelation.ORG_UNRELATED — the directory knows both people and places them nowhere near each other — NEVER OCCURS on this corpus. A path finding cut at that relation would read zero on every entity-day for a structural reason and would be mistaken for a measured negative. The cut is therefore DISTANT_HOPS, one level in, decided from the directory's own shape: department takes 22 distinct values, business unit takes one.
- The declared interaction policy was asked about 1,202,878 internal recipient pair(s) and returned INSUFFICIENT for every one: CERT r3.1 ships no policy about which roles may talk to which. This is phos.sentiel.interaction refusing correctly, wired end to end for the first time.
- EvidenceKind.SEQUENCE_ANOMALY was emitted 26 time(s) — the first any PHOS engine has produced. EvidenceKind.RELATIONSHIP_CHANGE carried 417 declared-path finding(s).

## Read every number above with these

**What was measured and what was merely built.** The compression ratio, the coverage comparison and the weak-signal profile are MEASURED on CERT r3.1 against its two labelled insiders. The declared-graph path findings and the sequence-anomaly evidence are BUILT and exercised end to end, and their FIRING RATES are measured — but r3.1 contains no labelled positive for either, so neither has a detection claim of any kind attached to it.

- An EPISODE IS A LARGER UNIT OF READING THAN AN ENTITY-DAY. Compressing N entity-days into M episodes is a gain only if an analyst can work an episode for less than the N/M days it replaces. Every episode reports n_days so the trade is visible; no number in this module assumes an episode and a day cost the same to triage.
- Two labelled insiders means insider coverage takes only the values 0, 0.5 and 1.0. It is not a rate and must not be read as one. The malicious ENTITY-DAY count (53) is the finer denominator and is the one to read.
- This re-counts PART 6B's own scores in a different unit. No model was refitted, no threshold was searched against a label, and the frozen 48-alert row is reproduced as a gate before any number here is computed. It does not supersede that row.
- CERT is SYNTHETIC. Simulated insiders may be more persistent, and therefore more episodic, than real ones; a compression ratio measured here is not a claim about an enterprise.
