# Lane Q — a queue that ranks

The champion catches the HAI 20.07 attacks and does not put the recoverable ones first.
Reordering the same alerts, without adding or removing one, does not beat that order on
the held-back shifts. v1's A3 stays 57 of 203.

## Diagnosis, HAI 20.07

ADR 0212, unchanged. The champion's scores reproduce 19 of 38.

| Ordering | A3 | Recall within 8 |
| --- | ---: | ---: |
| Champion score | 19/38 | 37/38 |
| Random, `numpy.random.default_rng(97651)`, one draw | 7/38 | 20/38 |
| Oracle: true alerts before benign alerts | 21/38 | 37/38 |

The oracle is the ceiling. One attack has no alert. Every other miss is a shift with more
attacks than top-10% slots. The two attacks the oracle saves are both in `test1.csv.gz`
shift 0. The benigns in those slots are unfamiliar column-sets in which several signals
moved together, and the explanation probe supports `process_disturbance` without
contradicting it. One buried true alert is a witness disagreement with no strong innocent
member. The other has the same shape as the benigns in front of it.

Thirty benign alerts sit ahead of some true alert. Twenty of those thirty have a
member-column set that already appeared on a training-normal event. One of 41 true alerts
does. Twenty-nine of the thirty have a strong innocent member (`sensor_or_device_fault` 25,
`process_disturbance` 4, `engineering_maintenance` none: these rows have no work order).
Onset unit: P1 on 29, P4 on 1. Onset signal `P1_PCV02Z` on 19, and the set `{P1_PCV02Z}`
on 17. Those familiar alarms are not the two benigns sitting in the only recoverable slots.

## Variants on development

Declared in ADR 0231 before the run. A variant that lowered recall within 8 on either
development set is rejected.

| Variant | HAI A3 | HAI recall within 8 | Seeds 97651–97670 A3 | Seed recall within 8 |
| --- | ---: | ---: | ---: | ---: |
| Champion | 19/38 | 37/38 | 19/20 | 20/20 |
| `familiarity` | 19/38 | 37/38 | 19/20 | 20/20 |
| `innocent` | 17/38 | 34/38 | 15/20 | 20/20 |
| `cross-path` | 13/38 | 28/38 | 10/20 | 20/20 |
| `familiarity-cross` | 16/38 | 32/38 | 10/20 | 20/20 |
| `cross-innocent` | 13/38 | 28/38 | 10/20 | 20/20 |
| `all-three` | 16/38 | 32/38 | 10/20 | 20/20 |

`familiarity` changed no seed's pass. The margin is zero. The champion already misses one
development seed (97660). That is the seed-to-seed noise, and the margin is smaller than
it. The other five pass 97660 and lower HAI recall within 8, because promoting a witness
or demoting a strong innocent explanation also pushes together-shaped true alerts out of
the eight an operator would read. They are rejected.

Every development seed contained a benign process event and an alert inside the hold.
Quiet training was seed 97001, 24 hours, per plant.

## Held-back

Frozen ranker: `familiarity` (`atlas-queue-v2:familiarity`), ADR 0232, sha256
`b5e0eed03bf0799f5f5db5d0898cda63a07ce2d27234e7c155ee45df97c0188b`.
Command: `PYTHONPATH=src:. .venv/bin/python scripts/measure_d_queue.py held-back`.
Run once.

| Ordering | A3 | Recall within 8 |
| --- | ---: | ---: |
| Champion | 20/20 | 20/20 |
| `familiarity` | 20/20 | 20/20 |

A3 is not strictly higher. Recall is not lower. The bar is not met (ADR 0233). The run
was not repeated.

What the ranker does: an alert whose member columns already fired together on quiet
training is placed behind an alert whose column set is new. On these shifts the hold and
the plant's own events did not separate that way, so the order that decides the top 10%
stays the champion's.

## Gate, not run

ADR 0234. Command: `PYTHONPATH=src:. .venv/bin/python scripts/measure_d_queue_gate.py`.
Result name: `atlas-queue-v2:familiarity-gate`. The process exits before opening a corpus.
The bar, if Elijah authorises one look: A3 strictly higher than 57 of 203 in total and on
at least three of the five judging corpora, recall within 8 not lower on any, chance draws
from seed 97651 reported. Whatever that look finds, v1's A3 stays not met. A pass would be
a v2 measurement under that result name.
