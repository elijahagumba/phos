# 70 — The sealed years, and a confidence test that contains mistakes

The later Kelmarsh years were scored once, with the same detector as the earlier years, and
nothing was adjusted afterwards.

In 2019–2022 the six turbines raised 74 alerts. The turbines' own logs explained 57. In
2023–2024 they raised 29, and the logs explained 23. The leftover alerts are rare: a few
thousandths of an alert per shift. The power-meter files are a different kind of record, so
they were not run through that detector. None of this is a claim that an attack was caught.
Nobody labelled an attack in these files.

A second test asked whether a confident explanation is usually right, on purpose-built plants
that sometimes make Atlas pick the wrong story. On the plants it had not practised on, 33 of
54 explanations were right and 21 were wrong, and every one of them was given the same
confidence. Nothing was confident enough to clear the bar. The bar is not met.

The third look was real network traffic from a conference lab, published by Netresec from the
4SICS event (<https://www.netresec.com/?page=PCAP4SICS>). There are no attacks in the two days
that were opened. Atlas could read a handful of Modbus commands and could not read the S7
traffic, which is most of the capture. The day it was supposed to learn from contained no
Modbus commands, so the map of who talks to whom came out empty. The next day produced eight
"never seen before" command notes, about one every three hours. Those notes are not catches.
