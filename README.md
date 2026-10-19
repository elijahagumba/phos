<p align="center">
  <img src=".github/assets/readme/hero.svg" width="600" alt="PHOS. Security that tells you what it doesn't know. Behavioural security for industrial systems. Research pre-release.">
</p>

<br>

<p align="center">
  An attacker with valid credentials breaks no signature.<br>
  What they change is how the plant behaves.
</p>

<p align="center">
  PHOS learns how a plant behaves when nothing is wrong. When that changes,<br>
  it writes down every explanation it can't rule out, and the one fact that would settle it.
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/about.svg" width="600" alt="What PHOS is: one way of reasoning, two engines. PHOS learns how a system normally behaves. When that changes, it keeps every explanation it can't rule out, weighs the evidence for and against each, and names the one fact that would settle it. Atlas, for industrial plants, watches a plant's process and its network together, checks what was commanded against what the plant actually did, and when a reading is falsified says which instrument is lying and what the true value probably was, so far on simulated plants. Sentiel, for people in an organisation, learns how each person normally works across logons, devices, web, email and files, and surfaces the few whose behaviour departs from their own and their peers'. Sentiel is research only.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/results.svg" width="600" alt="Measured. On three editions of HAI, a real industrial testbed, Atlas caught 131 of 160 attacks at 8 alerts a shift; the best baseline checked caught 52. On simulated runs it never saw, the lying sensor was named in 146 of 150, none named wrong. 0 of 80 simulated attacks were closed as maintenance, including 40 disguised as maintenance. On a real wind farm with no attacks in it, 17 alerts in four years were not explained by any log. Simulated plants are a diagnosis, not a real-plant result.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/alert.svg" width="600" alt="An Atlas alert about an unexpected function code on a learned SCADA to PLC link. Assessment: unresolved, because unauthorised control activity and planned maintenance rest on exactly the same fact. What would settle it: a write from a device that has never commanded this target.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/chain.svg" width="600" alt="How it reasons: observation, a reading; deviation, a departure from normal; evidence, a weighed fact; hypothesis, an explanation; narrative, the story with its rivals kept.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/boundary.svg" width="600" alt="What Atlas can say: it treats the plant as one machine, keeps every explanation it can't rule out, names the fact that would settle it, stays silent when explanations tie, and names the lying sensor on simulated plants. What it can't do yet: close a maintenance alert without the work order for that hour, rank its own alert queue, learn from a labelled command capture, or prove itself on a real plant.">
</p>

<br>

<p align="center">
  <a href="docs/bets/001-the-second-insider.md"><img src=".github/assets/readme/sentiel.svg" width="600" alt="Sentiel, the people engine, can't see the second insider. A public insider-threat dataset holds two labelled insiders and Sentiel finds one. At least 14 of its 34 signals must move at once before any alert, and the second insider's best rank is 957, where only the top 48 are seen. The bet, run once: let depth count, not just breadth. Three formulas were fixed before running, and none reached the second insider, as we predicted."></a>
</p>

<br>

<p align="center">
  <a href="docs/"><b>Read the record</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  everything PHOS has measured, including what didn't work
</p>

<br>

### Run a plant?

PHOS is looking for its first plant to run alongside, passively, learning from historian data and a
copy of the network traffic. If you operate or secure an industrial site and want to see what Atlas
makes of it, write to [elijah.phosfounder@proton.me](mailto:elijah.phosfounder@proton.me).

<br>

### Run it

```bash
uv sync
uv run phos demo
```

About fifteen seconds. A simulated water plant runs for 120 hours, something writes to its
controller, and Atlas writes its brief. Then the demo shows what actually happened, and says so
plainly when Atlas missed it or raised a false alarm. Try `--scenario operator` and
`--scenario attacker` too.

```bash
uv run pytest -q
```

The test suite needs no datasets. Public corpora are downloaded separately and never committed; see
[data/README.md](data/README.md).

<br>

<p align="center">
  <sub>Research pre-release. Not deployable, and never run on a live plant.</sub><br>
  <sub>Atlas models industrial plants. Sentiel, its enterprise sibling, is research only.</sub><br>
  <sub>Built by one researcher with AI coding agents. Every published number reproduces from this repository and the public datasets it names.</sub><br>
  <sub>Source-available under the <a href="LICENSE">PolyForm Noncommercial License 1.0.0</a>. Commercial use requires a licence.</sub><br>
  <sub>Phos Technologies Limited</sub>
</p>
