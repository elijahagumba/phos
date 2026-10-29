# 19 — A battery table with no captions

The S7 campaign looked, on the record page, like the next public power plant: a battery and a
PV inverter, process values at one sample per second, and labels that said `normal` or
`data_modification`. The licence is confirmed. The process file is small.

We opened the process file. It has **13,912** rows and **21** columns: a clock, voltages,
powers, a couple of on/off commands. It does **not** have a label column. The words
`normal` and `data_modification` belong to a **different** file — a parsed packet *table* —
which is not a packet capture, and which we did not score as one.

Analogy: a plant historian with no attack column, sitting next to a separate spreadsheet of
which network packets were edited. Pretending the historian is labelled would be inventing
captions. PHOS refuses that. Labelled Track A on this corpus is **refused**
([ADR 0047](../docs/adr/0047-s7-process-parquet-is-unlabelled-track-a-refused.md)).

This is not a quieter detector. It is not ≥70%. It is not a 2–3/day queue. The grid
measurement in [note 18](18-a-grid-we-measured-without-claiming-a-control-room.md) still
stands, with every caveat it already had.

If a sentence here disagrees with ADR 0047, those files win.
