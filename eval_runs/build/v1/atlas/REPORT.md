# Lane A — A1, A6, A3

Judged by the roadmap sentences in `docs/v1-roadmap.md` §2.1.

| Criterion | Verdict | Number | Record |
| --- | --- | --- | --- |
| A1 | not met | The table exists and marks each opponent checked or unchecked. One command checks hai-20.07, batch-distillation and data4cyber against the committed JSON (they matched) and reprints hai-21.03, hai-22.04, hai-23.05 and batadal. Those validation rows are not regenerated from the files. | `docs/adr/0210-the-g1-table-reprints-its-validation-rows.md`. Command: `uv run python scripts/measure_baseline_table.py`. Table: `eval_runs/v1/g1-baseline-table.md`. |
| A6 | met | No parameter differs between corpora beyond the declared sample-period rule. BATADAL's consistency windows are `windows_for_period` of its declared 3600 s period (ADR 0112, before the score). At 1 s that function is the frozen HAI windows. G1 threshold 3.0, 8 alerts per 8-hour shift, HAICon delta 180 samples, and the consistency constants are the same on every corpus. | `docs/adr/0211-a6-is-one-configuration.md`. Audit: `eval_runs/build/v1/atlas/a6-parameters.md`. |
| A3 | not met | 57/203. hai-20.07 19/38, hai-21.03 14/50, hai-22.04 13/58, hai-23.05 8/52, batadal 3/5. At least half of all those attacks would be 102/203. All five corpora were scored; the denominator did not shrink. | `eval_runs/build/v1/atlas/a3-queue-rank.json`, result `atlas-v1-consistency:a3-queue-rank`. Declaration: `docs/adr/0212-a3-queue-rank-is-declared.md`. |
