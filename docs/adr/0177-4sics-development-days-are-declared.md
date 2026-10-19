# ADR 0177 — The 4SICS development days are scored as benign traffic

- **Status:** Accepted (a declaration; this record has no alert count)
- **Date:** 2026-10-19
- **PART:** Round 3, Job 3
- **Depends on:** [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md)

## Context

ADR 0144 names `4SICS-GeekLounge-151020.pcap` and `151021.pcap` as development,
and `151022.pcap` as held back. The captures are unlabelled. They are not a
command corpus. Credit and a link are required:
<https://www.netresec.com/?page=PCAP4SICS>.

Atlas dissects Modbus/TCP. It does not dissect DNP3, S7comm, or EtherNet/IP.

## Decision

1. Learn the device-command graph on 151020. Compare 151021 with that graph,
   using the default graph policy. Do not swap the days after seeing the count.
2. The command is `uv run python scripts/round3_4sics.py`. Result name
   `round-3:4sics-development`.
3. A graph finding is a command alert. Alerts per hour are that count divided
   by the scored day's clock. There is no catch count. Confidence is not
   reported. `151022` is refused before it is opened.
4. Undissected frames are counted by destination port. A well-known port name
   in that count is a label for the port, not a decode.

## Consequences

A number here is a false-alarm count on conference-lab traffic. It is not a
detection claim.

## What would reverse this

Opening 151022. Reporting a catch. Retuning the graph window to quiet the count
and then quoting the quieter number as the measurement.
