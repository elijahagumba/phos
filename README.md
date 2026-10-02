<p align="center">
  <img src="brand/readme/hero.svg" width="600" alt="PHOS. Security that tells you what it doesn't know. Behavioural security for industrial systems. Research pre-release.">
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
  <img src="brand/readme/alert.svg" width="600" alt="An Atlas alert about an unexpected function code on a learned SCADA to PLC link. Assessment: unresolved, because unauthorised control activity and planned maintenance rest on exactly the same fact. What would settle it: a write from a device that has never commanded this target.">
</p>

<br>

<p align="center">
  <img src="brand/readme/chain.svg" width="600" alt="How it reasons: observation, a reading; deviation, a departure; evidence, a weighed fact; hypothesis, an explanation; narrative, the story with its rivals kept.">
</p>

<br>

<p align="center">
  <img src="brand/readme/boundary.svg" width="600" alt="What Atlas can say: it treats the plant as one machine, keeps every explanation it can't rule out, names the fact that would settle it, and stays silent when explanations tie. What it can't say yet: tell maintenance from an attack without the work order, rank its own alert queue, learn from a labelled command capture, or prove itself on a real plant.">
</p>

<br>

<p align="center">
  <a href="docs/atlas-report.md">Atlas report</a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/refusal-register.md">Refusal register</a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/synthetic-harness-method.md">Simulated plants</a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/adr/">Design decisions</a>
</p>

<br>

### Run it

```bash
uv sync
uv run pytest -q
```

The suite needs no datasets. Public corpora are downloaded separately and never committed; see
[data/README.md](data/README.md).

<br>

<p align="center">
  <sub>Research pre-release. Not deployable, and never run on a live plant.</sub><br>
  <sub>Atlas models industrial plants. Sentiel, its enterprise sibling, is research only.</sub><br>
  <sub>Built by one researcher with AI coding agents. Every published number reproduces from this repository and the public datasets it names.</sub><br>
  <sub>Source-available under the <a href="LICENSE">PolyForm Noncommercial License 1.0.0</a>. Commercial use requires a licence.</sub>
</p>
