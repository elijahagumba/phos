# Round 3 decisions

2026-10-19 — ADR 0174 declares the one Kelmarsh held-back score before any held-back zip is opened. Scorer `atlas-v1-consistency` unchanged. Status-log rule is the one ADR 0165 kept. Command `uv run python scripts/round3_kelmarsh.py`. Result name `round-3:kelmarsh-heldback`. `authorized` is false until sha256 is committed. PMU and grid-meter archives are checksummed and not passed to `detect`.

2026-10-19 — ADR 0175 names W5 seeds 97401–97420 (development) and 97501–97520 (held back), and five scenario kinds, before any of those plants is generated. The calibration rule stays ADR 0171. Held-back seeds are not built until a later declaration.

2026-10-19 — Development W5, out of fold, k=3, 160 samples: 46 contentful leads, 28 right, 18 wrong. Right and wrong share calibrated scores near 0.6. High band empty. Wrong leads below 0.5: 0. Bar not met. ADR 0176 freezes that fit and authorizes one look at 97501–97520.

2026-10-19 — Held-back W5, one look, seeds 97501–97520: 54 contentful leads, 33 right, 21 wrong. Every contentful lead calibrated at 0.604. High band empty. Wrong leads in the high band: 0. Wrong leads below 0.5: 0. Bar not met.

2026-10-19 — ADR 0177: 4SICS command graph is learned on 151020 and compared with 151021. 151022 is not opened. No catch is reported.

2026-10-19 — Kelmarsh held-back, one look: 29 alerts, 23 explained, share 0.793, 0.000456 unexplained per shift. Development was 74, 57, 0.770, 0.000646. Meters not scored. ADR 0178. No tuning.

2026-10-19 — 4SICS development: day 151020 learned 0 command relationships. Day 151021, 8 unknown-command findings, 0.333 per hour. Modbus decoded 0 then 19 frames. Port 102 was not decoded. No catches.
