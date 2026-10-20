# Round 3

19 October 2026. Three measurements. None of them is a detection claim on a live plant.
Hypothesis confidence is not shown to a user.

## Job 1 — Kelmarsh, real turbines

The scorer is `atlas-v1-consistency`, unchanged. Train is 2018. A status-log row explains an
alert when it covers that time and the service category is not `System OK (32)`. Development
is the 2019–2022 score already on disk. Held back is 2023–2024, scored once. The PMU and
grid-meter archives were downloaded and checked. Their columns are not the five turbine
signals, so they were not scored.

| Half | Alerts | Explained by the turbine log | Share | Unexplained alerts per shift | Bar |
| --- | ---: | ---: | ---: | ---: | --- |
| Development, 2019–2022 | 74 | 57 | 0.770 | 0.000646 | No detection bar. Not a detection claim. |
| Held back, 2023–2024 | 29 | 23 | 0.793 | 0.000456 | Same. No tuning after this look. |

Six alerts in 2023–2024 were not explained, across 13,158 shifts.

## Job 2 — Confidence, with wrong answers

Five synthetic situations on a water plant: a plain sensor fault, a fault during a real work
order, a small lie near normal, two sensors failing together, and a mimic attack during a work
order. The confidence rule is the one already written down: group a lead by the shape of its
evidence, and call it high only when that shape has been right often enough. Fit on seeds
97401–97420. Seeds 97501–97520 were scored once.

| Half | Contentful leads | Right | Wrong | High-confidence leads | Wrong leads in the high band | Bar |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Development | 46 | 28 | 18 | 0 | 0 | Not met |
| Held back | 54 | 33 | 21 | 0 | 0 | Not met |

The bar asked for high-confidence explanations to be right at least 80% of the time, and for
wrong leads to be mostly low. Nothing reached the high band. On the held-back seeds every
contentful lead, right or wrong, was given the same confidence, 0.604. That sits in the
0.6–0.8 band of the reliability chart: 54 leads, 33 right, observed frequency 0.611. The chart
is `w5-heldback.svg`. Wrong leads in the high band: 0. Wrong leads below 0.5: 0.

Right and wrong leads wore the same evidence shape, so the rule could not give the wrong ones
a lower number.

## Job 3 — 4SICS, real network traffic

Development days only, from Netresec's 4SICS Geek Lounge captures. Credit Netresec, 4SICS and
CS3Sthlm. Source: <https://www.netresec.com/?page=PCAP4SICS>. Day 151022 was not opened.
There are no attacks in these files, so this table has no catches.

The command graph was learned on 20 October 2015 and compared with 21 October 2015.

| Half | Command alerts per hour | What the graph learned | Bar |
| --- | ---: | --- | --- |
| 20 October, learn | — | No command relationships. Atlas decoded no Modbus on this day. | Not a catch count. |
| 21 October, score | 0.333 (8 findings over about 24 hours) | Still nothing learned. The 8 findings are unknown relationships against that empty graph. | Not met as a command baseline. Not a catch. |

Atlas decoded Modbus: 0 frames on the 20th, 19 on the 21st. It did not decode the bulk of the
traffic. The busiest undissected port was 102, the usual S7 port (about 47,000 frames on the
20th and about 173,000 on the 21st). DNS (port 53), and on the 21st also web and telnet ports,
were counted and not decoded. Frames that were not TCP or UDP were counted separately
(9,610 on the 20th, 36,817 on the 21st).

The eight findings are all one machine, 192.168.2.42, sending Modbus toward 192.168.88.20,
.50, .60, .61, .95 and .100. That is who talked. It is not a graph of normal learned from the
day before, because that day contained no decoded commands.

## What blocked a result

- The meter archives are a different instrument from the ten-minute turbine SCADA. Scoring them
  would have been a new detector. They were left unscored.
- The confidence rule cannot mark a lead high, or mark a wrong lead low, when right and wrong
  leads rest on the same kind of evidence.
- The first 4SICS day does not contain Modbus commands, so there was no command graph to learn.
  Atlas does not decode S7, which is most of the capture.
