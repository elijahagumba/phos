# law-inlet:invariants

- **Corpus:** `data/phos-icssim-dev` (development tier; held-out is refused by this script)
- **Declared by:** ADR 0333
- **Runs:** 13 · **inlets:** 39 · **pages:** 52 · **placed sentences:** 104
- **Stations the plant named:** ['operator', 'plc1', 'plc2']
- **Ceiling:** 8

## Bars (each declared 0)

| Bar | Count | Met |
| --- | --- | --- |
| 1 placed sentence does not name its law | 0 | yes |
| 2 placed sentence carries a score-word | 0 | yes |
| 3 page longer than the ceiling | 0 | yes |
| 4 register name not in exactly one list | 0 | yes |
| 5 page is not the earliest eight | 0 | yes |
| 6 LawBreak subclass admitted | 0 | yes |
| 7 inlet built from a refused frame | 0 | yes |
| 8 empty register not three empty lists | 0 | yes |

**All eight met:** yes

## Reported beside the bars, and not a bar

- Corpus reports with more breaks than the ceiling: 13
- Frames the dissector refused and the inlet was offered: 3
- Page lengths: 0: 39, 8: 13

Bars 1 to 4 are counted over corpus-built pages. Bar 5 is counted over corpus pages and over a constructed twelve-break page per run, because ordinary rows need not produce a ninth break. Bars 6, 7 and 8 are probes. None of these counts is a detection rate, a false-alarm rate, a recall, a latency or a magnitude, and none may be restated as one. A break is a false law, not an attack. The page does not name the cause. An empty page is not a safe plant. Synthetic results are a simulated diagnosis, not a field rate (ADR 0073).
