# ADR 0459 — A single-file run record and a local viewer

- **Status:** Accepted
- **Date:** 2026-11-17
- **PART:** V0 — run viewer and run file (ground rules and recon)
- **Supersedes:** nothing
- **Depends on:** [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md),
  [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md)

## Context

PHOS builds simulated plants (`src/phos/synth/`), runs Atlas against them (`scripts/evaluate_atlas_synthetic.py`), and runs a breaking harness (`src/phos/referee/`). None of these produce a single portable record of what happened in one run: telemetry, topology, labels, timeline events, Atlas detections/hypotheses/narratives, and per-event verdicts live in separate files or not at all.

A viewer is needed so a person can open one run, see the plant drawing, play back what happened, and see what Atlas saw — without network, without cloud, and without modifying the run file. This is not part of Atlas itself: the viewer never imports Atlas, and `src/phos/atlas/` is untouched. The only code allowed to import Atlas's public interface is a recorder module (`src/phos/referee/record.py` or equivalent under `src/phos/referee/`), and it feeds Atlas telemetry and capture files only — never labels, manifests or seeds.

This follows V0 (ground rules and recon): `docs/viewer/recon.md` records the repository layout, synth output formats, referee outputs, and that Node v26.8.1 is available with no JavaScript build toolchain; `docs/viewer/PLAN.md` records the package layout and this ADR's decisions.

## Decisions

### Decision 1 — A `.phosrun` file is a ZIP container, versioned

A `.phosrun` is a deterministic ZIP container: fixed ZIP timestamps (1980-01-01), members sorted alphabetically, fixed compression, `run_id = SHA-256` over member content hashes, no wall-clock time in the content hash. Writing the same run twice yields byte-identical files.

Members (all UTF-8 JSON or JSON Lines unless binary):

- `header.json` — format name `"phosrun"`, `format_version`, `run_id`, `kind` (`"simulated"` or `"real_data"`), `title`, `created_by` (tool + code version + git commit if known), seed information (family, master seed, child seeds for simulated runs), `pool` (`"dev"`, `"public"`, `"private"`, `"retired"`, `"real_data"`), the `MODEL_NOT_REALITY_CAVEAT` text for simulated runs, plain-language summary text, and a table of member names to SHA-256 hashes and sizes.
- `plant.json` — for simulated runs, the serialised `PlantSpec`; for real-data runs, a descriptor (dataset name, tags, units, known structure).
- `structure.json` — what the viewer draws: nodes (id, type, display name, tags owned), edges (flow connections), subsystem grouping (from the ground-truth subsystem map), layout hints.
- `timeline.json` — every event: id, kind, type/technique, start/end times, affected tags/devices, layer of effect, physical-effect flag, plain-language description.
- `telemetry/index.json` + `telemetry/chunk_NNNNN.*` — columnar telemetry in fixed-size time chunks; index lists columns (tag, unit, valid range, role), sample period, start time, chunk map, per-chunk min/max per column; pre-computed min-max pyramid overview levels.
- `labels.json` — collapsed label runs per timestamp range (normal, attack, fault, maintenance), consistent with the repo's label convention.
- `atlas/` (optional; absent if no detector ran): `detector.json` (adapter name, version, configuration), `alerts.jsonl` (time, tags, subsystem, severity, plain text), `hypotheses.jsonl` (time, ranked hypotheses with confidences, supporting/contradicting evidence references, or "insufficient evidence"), `narratives.jsonl` (the text explanation Atlas produced). Stores only what Atlas returned through its public interface — never internals, rules or model parameters.
- `scores.json` (optional) — per-run metrics from the scorer with scorer version.
- `traffic/summary.json` (optional) — per-interval packet counts, command writes, polled registers, notable messages linked to timeline events; `traffic/capture.pcap` optional and only below a size limit.
- `thumbnail.svg` — deterministic drawing of plant structure for the library view, generated from `structure.json`.

Readers refuse an unknown MAJOR version with a clear message.

### Decision 2 — The format library lives in `src/phos/runrecord/`

`write_run(...)` builds a `.phosrun` from components, deterministically. `read_header(path)` reads only `header.json` for fast library scanning. `open_run(path)` is a lazy reader exposing structure, timeline, labels, telemetry (range queries by tag and time with automatic overview-level selection), atlas data, scores and traffic summary. `verify(path)` checks every member hash and the run_id, reporting exactly what is wrong.

Command line: `phos-run inspect FILE | verify FILE | list DIR`.

`phos.runrecord` never imports `phos.atlas` or anything in `src/phos/atlas/`. A test pins this.

### Decision 3 — The viewer lives in `src/phos/viewer/`

A small local HTTP server (standard library or a permissively licensed micro-framework) serves a JSON API and vendored static files. Endpoints: list runs (headers only, cached with an on-disk index in the viewer's own data folder, rebuilt when files change), get one run's header/structure/timeline/scores/atlas summary, and range queries for telemetry (tags, start, end, max points, returning min-max decimated data).

Command: `phos-view [--runs-dir DIR]`, starts the server on a free local port, opens the default browser. Binds to `127.0.0.1` only, makes no outbound network requests, sends no telemetry. All assets vendored in the repo with licences recorded; no CDN links; no npm build toolchain — front end runs from plain files.

Viewed data is read-only: the viewer never modifies, deletes or moves a `.phosrun`. Notes/stars live in a separate sidecar in the viewer's own data folder.

### Decision 4 — The recorder is the only code that imports Atlas

A recorder module under `src/phos/referee/` (following the package layout in `docs/viewer/PLAN.md`) runs Atlas on a generated run through its public interface only, read-only, and writes the `atlas/` and `scores.json` members into the `.phosrun`. It gives Atlas telemetry and packet files only — never labels, manifests or seeds. If the referee scorer exists it is used; otherwise raw Atlas outputs are recorded and `scores.json` is left absent.

No other package imports `phos.atlas`. `tests/referee/test_independence.py` is extended to cover the viewer and runrecord packages.

### Decision 5 — `PHOS_RUNS_DIR` governs where runs live

Runs write to the folder named by `PHOS_RUNS_DIR`, defaulting to `~/PHOS_runs` (outside the repository). Private exam runs go to a separate subfolder never inside the repository. Git-ignore rules added; a test confirms private runs are never committed.

## Success is

- `docs/viewer/FORMAT.md` fully specifies the format with a worked example and a version number.
- `docs/viewer/PLAN.md` and `docs/viewer/recon.md` exist (recon and plan already written).
- `src/phos/runrecord/` implements `write_run`, `read_header`, `open_run`, `verify` and the `phos-run` CLI.
- `src/phos/viewer/` implements `phos-view` and the library screen; backend + plain HTML/CSS/JS front end.
- `uv run pytest -q`, `ruff`, `mypy --strict` all green; coverage meets the repo threshold.
- Commit and push.

## Success is not

- A detection claim. `.phosrun` stores what Atlas returned; it never manufactures one.
- Importing `phos.atlas` anywhere in `src/phos/viewer/` or `src/phos/runrecord/`.
- Network access, CDN assets, or an npm build step in the viewer.
- Modifying a `.phosrun` from the viewer.

## Related decisions

- [ADR 0015](0015-simulated-plants-the-injection-hook-and-the-true-state-record.md) — simulated plants and true-state record.
- [ADR 0029](0029-synthetic-dataset-library-is-not-a-public-corpus.md) — synthetic library is not a public corpus.
- [ADR 0040](0040-no-labelled-public-command-corpus.md) — no labelled public command corpus.
- [ADR 0073](0073-a-synthetic-command-and-maintenance-harness-that-measures-nothing.md) — synthetic command-and-maintenance harness.
- [ADR 0454](0454-d3-synthetic-evaluation-harness-for-atlas.md) — D3 evaluation harness for Atlas.
- [ADR 0457](0457-proprietary-simulation-public-methodology-independent-validation.md) — proprietary simulation, public methodology.
- [ADR 0458](0458-the-simulation-engine-was-never-closed-and-the-licence-is-what-protects-it.md) — simulator was never closed; licence is what protects it.
