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
  <img src=".github/assets/readme/alert.svg" width="600" alt="An Atlas alert about an unexpected function code on a learned SCADA to PLC link. Assessment: unresolved, because unauthorised control activity and planned maintenance rest on exactly the same fact. What would settle it: a write from a device that has never commanded this target.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/chain.svg" width="600" alt="How it reasons: observation, a reading; deviation, a departure from normal; evidence, a weighed fact; hypothesis, an explanation; narrative, the story with its rivals kept.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/boundary.svg" width="600" alt="What Atlas can say: it treats the plant as one machine, keeps every explanation it can't rule out, names the fact that would settle it, and stays silent when explanations tie. What it can't say yet: tell maintenance from an attack without the work order, rank its own alert queue, learn from a labelled command capture, or prove itself on a real plant.">
</p>

<br>

<p align="center">
  <a href="docs/bets/001-the-second-insider.md"><img src=".github/assets/readme/sentiel.svg" width="600" alt="Sentiel, the people engine, can't see the second insider. A public insider-threat dataset holds two labelled insiders and Sentiel finds one. At least 14 of its 34 signals must move at once before any alert, and 31 of the second insider's 42 days could never have raised one. The bet: let depth count, not just breadth. Success, written down before running: find both insiders in the top 48. Our own prediction: it won't be enough."></a>
</p>

<br>

<p align="center">
  <a href="docs/"><b>Read the record</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  everything PHOS has measured, including what didn't work
</p>

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
  <sub>Source-available under the <a href="LICENSE">PolyForm Noncommercial License 1.0.0</a>. Commercial use requires a licence.</sub>
</p>
