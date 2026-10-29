# Loud is a refuse, not a quieter number

**What this is:** Session C2. If a corpus floods the operator, the report can
now finish as **REFUSED** — the same status field as a successful measurement —
without rewriting the recall or the false-positive rate.

**Why it exists:** We already *said* saturated load is a reason to stay silent.
The harness still printed a detection row. Distillation at 18.72 false alarms
per normal hour and Data4Cyber's refused ruler stayed honest in ADRs. Future
rows needed a mechanism so "detection" cannot be claimed while the queue is
saturated.

## What changed

A caller can attach a declared line (the breaking harness uses one false alarm
per hour). Cross it and the claim is refused. The numbers stay on the page.

Public distillation and Data4Cyber were **not** run through that line to make
2–3 pages a day look earned. Their log names stay measured. Opt-in is the
point.

## What this is not

Not a dwell retune. Not 2–3/day. Not a rewrite of historical `log.jsonl` lines.

The decision is [ADR 0051](../docs/adr/0051-saturated-fp-load-is-a-refused-claim.md).
Note 22 is the snapshot assumptions (C1).
