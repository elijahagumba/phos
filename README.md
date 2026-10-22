<p align="center">
  <img src=".github/assets/readme/hero.svg?v=2" width="600" alt="PHOS. Security that tells you what it doesn't know. Atlas, for industrial plants. Research pre-release.">
</p>

<br>

PHOS is the company.

Atlas is the engine, and it is the one this page is about. Atlas watches an industrial plant. It learns how that plant normally runs. When something looks off, Atlas says what it might be, and what would decide it. Atlas will not call it an attack if it does not know.

Someone with a valid login sets off no alarm. What they change is how the plant runs. Atlas is built for that.

Sentiel is the other engine, for enterprise networks. PHOS is going to build it. The work right now is Atlas, so this page is Atlas. Sentiel is not ready to stand next to it.

You can hand that paragraph back to someone. The figures below are Atlas: what it has measured, one alert, and what it cannot say yet.

<br>

<p align="center">
  <img src=".github/assets/readme/about.svg?v=2" width="600" alt="PHOS is the company. Atlas is the engine for industrial plants. Atlas watches how a plant normally runs. When something looks off, it says what it might be, and what would decide it. It will not call it an attack if it does not know. Sentiel, for enterprise networks, is planned. The work right now is Atlas.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/results.svg?v=2" width="600" alt="Measured. On three editions of HAI, a real industrial testbed, Atlas caught 131 of 160 attacks at 8 alerts a shift; the best baseline checked caught 52. On simulated runs it never saw, the lying sensor was named in 146 of 150, none named wrong. 0 of 80 simulated attacks were closed as maintenance, including 40 disguised as maintenance. On a real wind farm with no attacks in it, in two years held back and scored once, 6 of 29 alerts were not explained by the turbines' own logs. Simulated plants are a diagnosis, not a real-plant result.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/alert.svg?v=2" width="600" alt="An Atlas alert. A command this link does not usually see. It might be an attack or planned maintenance. The same fact supports both, so Atlas will not pick. What would decide it: a command from a machine that has never commanded this one.">
</p>

<br>

<p align="center">
  <img src=".github/assets/readme/boundary.svg?v=2" width="600" alt="What Atlas can say: it treats the plant as one machine, says what a change might be, names what would decide it, stays quiet when it cannot tell, and names the lying sensor on simulated plants. What it can't do yet: close a maintenance alert without that hour's job sheet, rank its own alert list, learn from a labelled command capture, or prove itself on a real plant.">
</p>

<br>

<p align="center">
  <a href="docs/release.md"><b>Release note</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/"><b>Read the record</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  everything PHOS has measured, including what didn't work
</p>

<br>

### Run a plant?

PHOS is looking for its first plant to run alongside, passively, learning from historian data and a
copy of the network traffic. If you operate or secure an industrial site and want to see what Atlas
makes of it, write to [elijahagumba.research@proton.me](mailto:elijahagumba.research@proton.me).

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
  <sub>Atlas is the industrial engine, and the work right now. Sentiel, for enterprise networks, is planned and not ready to stand next to it.</sub><br>
  <sub>Built by one researcher with AI coding agents. Every published number reproduces from this repository and the public datasets it names.</sub><br>
  <sub>Source-available under the <a href="LICENSE">PolyForm Noncommercial License 1.0.0</a>. Commercial use requires a licence.</sub><br>
  <sub>PHOS</sub>
</p>
