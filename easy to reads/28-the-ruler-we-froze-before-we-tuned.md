# 28 — The ruler we froze before we tuned

PHOS now has a joint plant model, a command graph, competing explanations, and a long list of
refusals. What it did not have was a **single table** that a sceptical researcher could trust was
locked *before* anyone went looking for a prettier ROC.

Clock B starts there. [ADR 0062](../docs/adr/0062-clock-b-freeze-before-optimise.md) freezes
PHOS Benchmark v1. The first table copies numbers you already know:

- HAI Mahalanobis is still **646.58** false positives per normal hour at recall 1.00. Grouping
  cuts the *queue count* to **53.26**. That is not a control room, and it is not 2–3 pages a day.
- Distillation ungated Mahalanobis is still **18.72** per hour, **8.6×** quieter than Gaussian,
  perturbation recall 0.60. Two-to-three a day stays **refused**.
- CERT 6B at 48 alerts is still precision **0.104**. The `:precision` policy is still a **loss**
  at 0.083. Peer advantage stays retired.
- Known-station unique lead is still **0 of 16**. Unknown-master unique lead is still **1 of 4**,
  a diagnostic, not a field rate. They are not pooled. Public command lead is **REFUSED**
  (no labelled capture).
- Teaching HAI and testing BATADAL as "transfer" is **REFUSED** until someone declares a shared
  plant-state schema. Different column names are not a protocol.

The table is printed by `uv run python scripts/evaluate_phos_benchmark.py`. Seed 11 is not a
search knob. Nobody is allowed to hunt thresholds on that split.

Ablation ladders have names (Gaussian → … → reachability; counts → … → aggregation with peer
retired). Their toy-fixture counts are not public rows. Distillation 18.72 false positives per
hour is 449.28 per day; that arithmetic is why 2–3/day stays refused. CERT 5 true positives in
48 alerts is still 0.104.

Behind the freeze, Clock B now prints a research scoreboard (`clock-b-research.md`): declared-phase
transitions refuse an inferred distillation phase; command reconstruction completeness is not a
lead rate; sequences do not replace CERT 6B; identity peer stays empty; TEP / Electra / HVAC /
further Modbus hunts were not dual-surface confirmed and were not acquired.

P1 is still a conversation with a person who owns a historian and, if it exists, a declared map.
Clock B does not skip that conversation by building an API.

If the next model loses to Mahalanobis on this frozen ruler, Mahalanobis wins.
