<img src=".github/assets/readme/cover.svg" width="100%" alt="PHOS. Security that tells you what it doesn't know. Atlas, for industrial plants. Research pre-release.">

PHOS is the company.

A plant names the laws in force. Each named law is held, broken, or unstated. Only a broken law takes a slot. The page holds at most eight, ordered by time, then by the law's name. Every sentence names its law, then the fact. A score is refused. A break is a false law. The page does not name the cause. Held means the check ran and the law stood. Unstated means the plant named the law and supplied nothing that law can be checked against. An empty register checks nothing.

That paragraph is the operator page. The older detectors remain in the repository so the published measurements can still be reproduced. They do not enter that page. Someone with a valid login sets off no alarm by the login itself. What they change is how the plant runs.

Sentiel is the other engine, for enterprise networks. PHOS is going to build it. The work right now is Atlas, so this page is Atlas. Sentiel is not ready to stand next to it.

The code of that page is `src/phos/atlas/declared_law.py`.

<img src=".github/assets/readme/laws.svg" width="100%" alt="Six laws. joint_move: two tags written inside the ordinary band, close together in time. subfloor_walk: one tag stepped across that band for a fixed length. band_handoff: the same ordinary value on a second tag later, and no booking names both tags. program_transfer: a download, an upload, or an online edit, and nothing booked covers that act. allowed_writer: a write from a station the plant did not name. controller_valve: a valve that is not the value the plant's own comparison writes.">

A law this page has no check for is listed and takes no line. An empty list of laws checks nothing. There is no screen, no service, and no connection to a control network. The next step is one plant that exports its files and writes the laws. If no plant agrees, the product sequence stops. The page stays. A price for the company has no date here.

The pictures below are measurements of the older detectors. They are not the page. The page does not carry a score.

<img src=".github/assets/readme/company.svg" width="100%" alt="A named law is held, broken, or unstated. Only a broken law takes a slot. At most eight. A score is refused. A break is not an attack.">

<img src=".github/assets/readme/measured.svg" width="100%" alt="Measured. On three editions of HAI, a real industrial testbed, Atlas caught 131 of 160 attacks at 8 alerts a shift; the best baseline checked caught 52. On simulated runs it never saw, the lying sensor was named in 146 of 150, none named wrong. 0 of 80 simulated attacks were closed as maintenance, including 40 disguised as maintenance. On a real wind farm with no attacks in it, in two years held back and scored once, 6 of 29 alerts were not explained by the turbines' own logs. Simulated plants are a diagnosis, not a real-plant result.">

<img src=".github/assets/readme/alert.svg" width="100%" alt="An Atlas alert. A command this link does not usually see. It might be an attack or planned maintenance. The same fact supports both, so Atlas will not pick. What would decide it: a command from a machine that has never commanded this one.">

<img src=".github/assets/readme/boundary.svg" width="100%" alt="What Atlas can say: it treats the plant as one machine, says what a change might be, names what would decide it, stays quiet when it cannot tell, and names the lying sensor on simulated plants. What it can't do yet: close a maintenance alert without that hour's job sheet, rank its own alert list, learn from a labelled command capture, or prove itself on a real plant.">

[Release note](docs/release.md)<br>
[The record](docs/)<br>
Everything PHOS has measured, including what didn't work.<br>
[Eight alerts](docs/whitepaper/hn_technical_post.md)<br>
[What the page refuses](docs/whitepaper/eight-alert-non-admission.md)<br>
[A function code is not a download](docs/whitepaper/modbus-is-not-a-program-transfer.md)<br>
[Membership is declared, not inferred](docs/whitepaper/topology-is-declared-not-inferred.md)<br>
[The detectors that were refused](docs/whitepaper/lanes-that-were-refused.md)<br>
[A score is not a rank](docs/whitepaper/a-score-is-not-a-rank.md)<br>
[A broken law, or silence](docs/#a-broken-law-or-silence)

### A plant

PHOS is looking for one site that can export historian files and write down which laws to check. The page will not show a score. PHOS will not connect to the control network. If you operate or secure an industrial site and can do that, write to [elijahagumba.research@proton.me](mailto:elijahagumba.research@proton.me).

### Run it

```bash
uv sync
uv run phos demo
```

About fifteen seconds. The demo runs the older detectors on a simulated water plant for 120
hours. It is not the operator page. Then the demo shows what actually happened, and says so
plainly when it missed or raised a false alarm. Try `--scenario operator` and
`--scenario attacker` too.

```bash
uv run pytest -q
```

The test suite needs no datasets. Public corpora are downloaded separately and never committed; see
[data/README.md](data/README.md).

Research pre-release. Not deployable, and never run on a live plant.

Atlas is the industrial engine, and the work right now. Sentiel, for enterprise networks, is planned and not ready to stand next to it.

Built by one researcher with AI coding agents. Every published number reproduces from this repository and the public datasets it names.

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires a licence.

PHOS
